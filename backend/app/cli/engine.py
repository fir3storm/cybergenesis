"""Backend-authoritative CLI engine. Output is rendered from twin device config;
config commands stage ConfigDiffs — nothing here mutates the twin directly."""

from app.devices.registry import BUILTIN_DEVICE_MAP, BY_ID

SESSIONS: dict[str, dict] = {}

# Per-dialect grammar: (phrase, modes, help). Overlays (eos, aoscx) inherit ios.
GRAMMAR: dict[str, list[tuple[str, tuple[str, ...], str]]] = {
    "ios": [("show running-config", ("exec",), "running configuration"), ("show interfaces", ("exec",), "interface status"),
            ("show ip route", ("exec",), "routing table"), ("show access-list", ("exec",), "ACL entries"),
            ("show version", ("exec",), "system version"), ("configure terminal", ("exec",), "enter config mode"),
            ("interface", ("config",), "select an interface"), ("shutdown", ("interface",), "disable selected interface"),
            ("no shutdown", ("interface",), "enable selected interface"), ("description", ("interface",), "set description"),
            ("access-list", ("config",), "add a typed ACL entry"), ("ip access-group", ("interface",), "bind an ACL"),
            ("end", ("config", "interface"), "leave config mode"), ("write memory", ("exec", "config"), "commit (Verified Commit)")],
    "asa": [("show running-config", ("exec",), "running configuration"), ("show interface", ("exec",), "interface status"),
            ("show route", ("exec",), "routing table"), ("show access-list", ("exec",), "ACL entries"),
            ("configure terminal", ("exec",), "enter config mode"), ("interface", ("config",), "select an interface"),
            ("shutdown", ("interface",), "disable selected interface"), ("access-list", ("config",), "add a typed ACL entry"),
            ("write memory", ("exec", "config"), "commit (Verified Commit)")],
    "junos": [("show configuration", ("exec",), "configuration"), ("show interfaces terse", ("exec",), "interfaces"),
              ("show route", ("exec",), "routing table"), ("configure", ("exec",), "enter configuration mode"),
              ("set interfaces", ("config",), "set an interface statement"), ("set firewall family inet filter", ("config",), "set a filter term"),
              ("commit check", ("config",), "validate candidate config"), ("commit", ("config",), "commit (Verified Commit)"),
              ("rollback", ("config",), "rollback candidate")],
    "fortios": [("show full-configuration", ("exec",), "full configuration"), ("show", ("exec",), "show configuration/status"), ("get system status", ("exec",), "system status"),
                ("config", ("exec",), "enter a config table"), ("edit", ("config",), "edit an entry"),
                ("set", ("config",), "set a field"), ("next", ("config",), "finish entry"), ("end", ("config",), "exit table")],
    "panos": [("show running-config", ("exec",), "running configuration"), ("show interface all", ("exec",), "interfaces"),
              ("configure", ("exec",), "enter configuration mode"), ("set rulebase security rules", ("config",), "set a security rule"),
              ("commit", ("config",), "commit (Verified Commit)")],
    "routeros": [("/interface print", ("exec",), "interfaces"), ("/ip address print", ("exec",), "addresses"),
                 ("/ip route print", ("exec",), "routes"), ("/ip firewall filter print", ("exec",), "filter rules"),
                 ("/ip firewall filter add", ("exec",), "add a filter rule (stages a diff)")],
    "bash": [("ls", ("exec",), "list files"), ("cat", ("exec",), "read a file"), ("ps", ("exec",), "processes"),
             ("ss", ("exec",), "sockets"), ("ip addr", ("exec",), "addresses"), ("systemctl status", ("exec",), "service status"),
             ("journalctl", ("exec",), "logs"), ("sudo", ("exec",), "run as root (emulated)")],
    "powershell": [("Get-Process", ("exec",), "processes"), ("Get-Service", ("exec",), "services"),
                   ("Get-NetFirewallRule", ("exec",), "firewall rules"), ("New-NetFirewallRule", ("exec",), "new firewall rule (stages a diff)"),
                   ("Get-WinEvent", ("exec",), "event log"), ("Get-LocalUser", ("exec",), "local users"),
                   ("Disable-LocalUser", ("exec",), "disable a user (stages a diff)"), ("Get-ADUser", ("exec",), "AD users"),
                   ("ipconfig", ("exec",), "IP configuration"), ("netstat", ("exec",), "connections"), ("Get-HotFix", ("exec",), "installed patches")],
}
GRAMMAR["eos"] = GRAMMAR["ios"]
GRAMMAR["aoscx"] = GRAMMAR["ios"]
GRAMMAR["zsh"] = GRAMMAR["bash"]
GRAMMAR["esxcli"] = GRAMMAR["bash"]
GRAMMAR["tmsh"] = GRAMMAR["bash"]
GRAMMAR["generic"] = GRAMMAR["bash"]
GRAMMAR["none"] = []

ERROR_MARKERS = {
    "ios": "% Invalid input detected at '^' marker.", "eos": "% Invalid input detected at '^' marker.",
    "aoscx": "% Invalid input detected at '^' marker.", "asa": "% Invalid input detected at '^' marker.",
    "junos": "syntax error, expecting <command>.", "fortios": "command parse error. return code -61",
    "panos": "Invalid syntax.", "routeros": "bad command name", "bash": "bash: {cmd}: command not found",
    "zsh": "zsh: command not found: {cmd}", "powershell": "The term '{cmd}' is not recognized as a cmdlet.",
    "esxcli": "Invalid command: {cmd}", "tmsh": "syntax error: unknown command",
}

ABBREVIATIONS = {"sh": "show", "int": "interface", "br": "brief", "conf": "configure", "term": "terminal",
                 "wr": "write", "mem": "memory", "run": "running-config", "rou": "route", "acc": "access-list"}


def grammar_for(dialect: str) -> list[tuple[str, tuple[str, ...], str]]:
    return GRAMMAR.get(dialect, GRAMMAR["bash"])


def expand_abbreviations(command: str) -> str:
    tokens = command.split()
    if len(tokens) < 2:
        return command
    expanded = [ABBREVIATIONS.get(t.lower(), t) for t in tokens]
    return " ".join(expanded)


def dialect_for(asset_id: str, twin) -> str:
    dev_id = BUILTIN_DEVICE_MAP.get(asset_id)
    if dev_id and dev_id in BY_ID:
        return BY_ID[dev_id].personality.cli
    return {"firewall": "fortios", "identity": "powershell", "database": "bash", "sensor": "bash"}.get(
        next((a["asset_type"] for a in twin.asset_defs if a["id"] == asset_id), ""), "bash")


def render_config(dialect: str, cfg: dict) -> str:
    host = cfg.get("hostname", "device")
    lines = [f"! {host} running-config (dialect: {dialect})", f"hostname {host}"]
    for i in cfg.get("interfaces", []):
        lines.append(f"interface {i['name']}")
        lines.append(f" description {i.get('description', '')}")
        lines.append(f" ip address {i.get('ip', '')}/{i.get('prefix', 24)}")
        lines.append(" no shutdown" if i.get("enabled", True) else " shutdown")
    for acl in cfg.get("acls", []):
        for e in acl.get("entries", []):
            lines.append(f"access-list {acl['name']} {e['action']} {e.get('proto', 'ip')} {e.get('src', 'any')} {e.get('dst', 'any')}")
    for u in cfg.get("users", []):
        lines.append(f"username {u['name']} role {u.get('role', 'user')} mfa {'on' if u.get('mfa') else 'off'}")
    mgmt = cfg.get("mgmt", {})
    if mgmt.get("telnet"):
        lines.append("line vty 0 4\n transport input telnet")
    if mgmt.get("snmp_community"):
        lines.append(f"snmp-server community {mgmt['snmp_community']} RO")
    return "\n".join(lines)


def parse_config_text(dialect: str, text: str) -> dict:
    """Parse rendered running-config back into config fields (round-trip for supported features)."""
    cfg: dict = {"interfaces": [], "acls": [], "users": [], "mgmt": {"telnet": False, "snmp_community": None}}
    current = None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("hostname "):
            cfg["hostname"] = line.split(None, 1)[1]
        elif line.startswith("interface "):
            current = {"name": line.split(None, 1)[1], "enabled": True, "ip": "", "description": ""}
            cfg["interfaces"].append(current)
        elif line.startswith("shutdown") and current is not None:
            current["enabled"] = False
        elif line.startswith("no shutdown") and current is not None:
            current["enabled"] = True
        elif line.startswith("ip address") and current is not None:
            current["ip"] = line.split()[2].split("/")[0]
        elif line.startswith("description") and current is not None:
            current["description"] = line[len("description"):].strip()
        elif line.startswith("access-list "):
            parts = line.split()
            cfg["acls"].append({"name": parts[1], "entries": [{"action": parts[2], "dst": parts[-1]}]})
        elif line.startswith("username "):
            parts = line.split()
            cfg["users"].append({"name": parts[1], "mfa": "on" in line})
        elif "transport input telnet" in line:
            cfg["mgmt"]["telnet"] = True
        elif line.startswith("snmp-server community"):
            cfg["mgmt"]["snmp_community"] = line.split()[2]
    return cfg


def parse_acl_command(command: str) -> dict | None:
    """Typed ACL grammar: access-list NAME [seq N] deny|permit proto src dst [eq port]
    (and dialect spellings: 'acl NAME ...', FortiOS 'set action deny', PAN-OS 'set rulebase ... action deny')."""
    low = command.strip().lower()
    tokens = low.replace(",", " ").split()
    action = next((t for t in tokens if t in ("deny", "permit", "allow", "drop")), None)
    if not action:
        return None
    action = "deny" if action in ("deny", "drop") else "permit"
    name = "CYBERGENESIS"
    seq = 10
    if "seq" in tokens:
        try:
            seq = int(tokens[tokens.index("seq") + 1])
        except (ValueError, IndexError):
            pass
    if tokens and tokens[0] in ("access-list", "acl") and len(tokens) > 1:
        name = tokens[1].upper()
    protos = ("tcp", "udp", "icmp", "ip", "any")
    proto = next((t for t in tokens if t in protos), "ip")
    rest = [t for t in tokens if t not in ("access-list", "acl", name.lower(), "seq", str(seq), action, proto)]
    src = rest[0] if rest else "any"
    dst = rest[1] if len(rest) > 1 else "any"
    port = None
    if "eq" in tokens:
        try:
            port = int(tokens[tokens.index("eq") + 1])
        except (ValueError, IndexError):
            pass
    entry = {"seq": seq, "action": action, "proto": proto, "src": src, "dst": dst, "dst_port": port, "log": True}
    return {"ops": [{"op": "add_acl_entry", "value": {"name": name, "entry": entry}}]}


def parse_command(dialect: str, cfg: dict, command: str) -> tuple[str, dict | None]:
    """Returns (output, staged_diff_or_None). Abbreviations: unique prefixes expanded by callers' help."""
    cmd = command.strip()
    low = cmd.lower()
    asset = cfg.get("hostname", "")
    if not cmd:
        return "", None
    if low in ("?", "help"):
        return "show running-config | show interfaces | show ip route | show access-list | configure terminal | exit", None
    if low.startswith(("show running-config", "show run", "sh run", "show configuration")):
        return render_config(dialect, cfg), None
    if low.startswith(("show interfaces", "sh ip int", "show ip interface")):
        rows = [f"{i['name']} {'up' if i.get('enabled', True) else 'down'} {i.get('ip', '')} peer={i.get('peer', '')}" for i in cfg.get("interfaces", [])]
        return "\n".join(rows) or "no interfaces", None
    if low.startswith(("show ip route", "show route", "get router info routing-table")):
        rows = [f"{r.get('proto', 'connected')} {r.get('prefix', '0.0.0.0/0')} via {r.get('next_hop', 'connected')}" for r in cfg.get("routes", [])]
        return "\n".join(rows) or "C 10.0.0.0/24 is directly connected", None
    if low.startswith(("show access-list", "show access", "get firewall policy")):
        rows = [f"{acl['name']}: " + ", ".join(f"{e['action']} {e.get('dst', 'any')}" for e in acl.get("entries", [])) for acl in cfg.get("acls", [])]
        return "\n".join(rows) or "no ACLs configured", None
    if low.startswith(("show version", "get system status", "show system info")):
        return f"{asset} dialect={dialect} (emulated, synthetic only)", None
    # config commands -> staged diffs
    if low.startswith(("access-list", "acl ")) or ("deny" in low and "access" in low):
        diff = parse_acl_command(cmd)
        if diff:
            e = diff["ops"][0]["value"]["entry"]
            return (f"% ACL {diff['ops'][0]['value']['name']} seq {e['seq']} {e['action']} staged as typed ConfigDiff "
                    f"(bind it with: ip access-group {diff['ops'][0]['value']['name']} in|out)"), diff
    if low.startswith("ip access-group"):
        parts = low.split()
        if len(parts) >= 4:
            diff = {"ops": [{"op": "bind_acl", "value": {"name": parts[2].upper(), "direction": parts[3],
                                                         "interface": "current"}}]}
            return f"% ACL {parts[2].upper()} bind ({parts[3]}) staged as pending ConfigDiff", diff
    if low.startswith(("no telnet", "harden", "no transport input telnet")):
        diff = {"ops": [{"op": "action", "value": {"action_type": "harden_mgmt", "params": {}}}]}
        return "% harden_mgmt staged as pending ConfigDiff", diff
    if low.startswith(("shutdown", "shut")):
        diff = {"ops": [{"op": "set", "path": "interfaces.0.enabled", "value": False}]}
        return "% interface shutdown staged as pending ConfigDiff", diff
    if low.startswith(("configure", "conf t", "edit", "set ")) :
        return "% configuration mode (emulated). Type a deny access-list line, 'harden', or 'show running-config'.", None
    if low.startswith(("write memory", "wr mem", "commit", "save", "end")):
        return "% commit requested — use Device Manager > Pending Changes > Commit (Verified Commit) so the same gate applies.", None
    if dialect in ("powershell",) and low.startswith("get-"):
        if "process" in low:
            return "Id ProcessName\n-- -----------\n1001 System\n1002 explorer\n6666 suspicious-synthetic"
        if "service" in low:
            return "Status Name\n------ ----\nRunning WinDefend\nRunning Dnscache"
        return f"% {cmd}: emulated PowerShell (synthetic output)"
    if low.startswith(("ls", "ps", "ss", "ip a", "systemctl", "journalctl", "cat ")):
        return {"ls": "bin etc home var", "ps": "root 1 systemd\nroot 666 suspicious-synthetic",
                "ss": "LISTEN 0.0.0.0:443 (synthetic)"}.get(low.split()[0], f"% emulated bash output for '{cmd}' (synthetic)")
    return f"% Invalid input detected at '^' marker. Type '?' for help. (dialect: {dialect})"


def get_session(device_id: str, user: str = "admin") -> dict:
    key = f"{device_id}:{user}"
    if key not in SESSIONS:
        SESSIONS[key] = {"device_id": device_id, "user": user, "history": [], "mode": "exec"}
    return SESSIONS[key]


PROMPTS = {"exec": "{host}>", "config": "{host}(config)#", "interface": "{host}(config-if)#"}


def execute(twin, asset_id: str, command: str, user: str = "admin") -> dict:
    dialect = dialect_for(asset_id, twin)
    cfg = twin.device_configs.get(asset_id)
    if cfg is None:
        return {"output": f"% unknown device {asset_id}", "dialect": dialect, "diff": None}
    session = get_session(asset_id, user)
    session.setdefault("mode", "exec")
    session.setdefault("interface", None)
    cmd = expand_abbreviations(command.strip())
    low = cmd.lower()

    # --- mode transitions + context-sensitive commands ---
    if low in ("configure terminal", "configure", "conf t", "edit system") and dialect != "none":
        session["mode"] = "config"
        out, diff = f"Entering configuration mode ({dialect}). Type '?' for context help.", None
    elif low.startswith("interface ") and session["mode"] in ("config", "interface"):
        session["interface"] = cmd.split(None, 1)[1]
        session["mode"] = "interface"
        out, diff = f"Entering interface configuration: {session['interface']}", None
    elif low in ("end", "exit") and session["mode"] != "exec":
        session["mode"] = "exec" if session["mode"] == "config" else "config"
        if low == "end":
            session["mode"] = "exec"
        out, diff = f"Mode: {session['mode']}", None
    elif low in ("shutdown", "no shutdown") and session["mode"] == "interface" and session.get("interface"):
        enabled = low.startswith("no")
        diff = {"ops": [{"op": "set", "path": f"interfaces.{session['interface']}.enabled", "value": enabled}]}
        out = f"% interface {session['interface']} {'enabled' if enabled else 'shutdown'} staged as pending ConfigDiff"
    elif low == "?":
        entries = [f"{phrase} — {help_}" for phrase, modes, help_ in grammar_for(dialect) if session["mode"] in modes]
        out, diff = "\n".join(entries) or "no commands in this mode", None
    else:
        output, diff = parse_command(dialect, cfg, cmd)
        if output.startswith("% Invalid input") or "command not found" in output or output.startswith("syntax error"):
            marker = ERROR_MARKERS.get(dialect, "% Invalid input detected at '^' marker.")
            output = marker.format(cmd=cmd.split()[0] if cmd.split() else cmd)
        out = output
    session["history"].append(command)
    if diff:
        for op in diff.get("ops", []):
            if op.get("op") == "bind_acl" and op["value"].get("interface") == "current":
                op["value"]["interface"] = session.get("interface", "eth0")
        twin.stage_diff(asset_id, diff)
    host = str(cfg.get("hostname", asset_id))
    return {"output": out, "dialect": dialect, "diff": diff, "history": session["history"][-20:],
            "mode": session["mode"], "interface": session.get("interface"),
            "prompt": PROMPTS[session["mode"]].format(host=host)}


def complete(twin, asset_id: str, prefix: str) -> list[str]:
    dialect = dialect_for(asset_id, twin)
    session = get_session(asset_id)
    mode = session.get("mode", "exec")
    return [phrase for phrase, modes, _h in grammar_for(dialect)
            if mode in modes and (phrase.lower().startswith(prefix.lower()) or prefix.lower().startswith(phrase.lower()))][:8]
