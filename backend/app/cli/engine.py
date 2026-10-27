"""Backend-authoritative CLI engine. Output is rendered from twin device config;
config commands stage ConfigDiffs — nothing here mutates the twin directly."""

from app.devices.registry import BUILTIN_DEVICE_MAP, BY_ID

SESSIONS: dict[str, dict] = {}


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
    if "deny" in low and ("access-list" in low or "access_list" in low or low.startswith("acl ")):
        diff = {"ops": [{"op": "add_acl_deny", "value": {"command": cmd}}]}
        return "% ACL deny staged as pending ConfigDiff (commit from Device Manager > Pending Changes)", diff
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


def execute(twin, asset_id: str, command: str, user: str = "admin") -> dict:
    dialect = dialect_for(asset_id, twin)
    cfg = twin.device_configs.get(asset_id)
    if cfg is None:
        return {"output": f"% unknown device {asset_id}", "dialect": dialect, "diff": None}
    session = get_session(asset_id, user)
    output, diff = parse_command(dialect, cfg, command)
    session["history"].append(command)
    if diff:
        twin.pending_diffs[asset_id] = diff
    return {"output": output, "dialect": dialect, "diff": diff, "history": session["history"][-20:]}


def complete(twin, asset_id: str, prefix: str) -> list[str]:
    cmds = ["show running-config", "show interfaces", "show ip route", "show access-list", "show version",
            "configure terminal", "access-list CYBER deny ip any any", "harden", "shutdown", "write memory"]
    return [c for c in cmds if c.startswith(prefix)][:8]
