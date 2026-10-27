from pydantic import BaseModel, Field


class Interface(BaseModel):
    name: str
    enabled: bool = True
    mode: str = "routed"  # access|trunk|routed|host
    vlan: int = 1
    allowed_vlans: list[int] = []
    ip: str = ""
    prefix: int = 24
    zone: str = "internal"
    description: str = ""
    acl_in: str | None = None
    acl_out: str | None = None
    peer: str | None = None


class Vlan(BaseModel):
    id: int
    name: str = ""


class Route(BaseModel):
    prefix: str
    next_hop: str = ""
    proto: str = "connected"
    metric: int = 1


class AclEntry(BaseModel):
    seq: int = 10
    action: str = "permit"  # permit|deny
    proto: str = "ip"
    src: str = "any"
    dst: str = "any"
    dst_port: int | None = None
    log: bool = False


class Acl(BaseModel):
    name: str
    entries: list[AclEntry] = []


class FwPolicy(BaseModel):
    id: int = 1
    name: str = ""
    src_zone: str = "any"
    dst_zone: str = "any"
    src: str = "any"
    dst: str = "any"
    service: str = "any"
    action: str = "allow"  # allow|deny
    log: bool = True
    enabled: bool = True


class NatRule(BaseModel):
    type: str = "source"
    src: str = "any"
    dst: str = "any"
    translated: str = ""


class Vpn(BaseModel):
    name: str
    type: str = "ipsec"
    peer: str = ""
    enabled: bool = True


class Session(BaseModel):
    id: str
    active: bool = True
    compromised: bool = False


class User(BaseModel):
    name: str
    role: str = "user"
    mfa: bool = False
    sessions: list[Session] = []
    credential_version: int = 1


class Service(BaseModel):
    name: str
    port: int = 0
    proto: str = "tcp"
    enabled: bool = True
    exposed_zones: list[str] = []


class HostFirewall(BaseModel):
    enabled: bool = True
    rules: list[dict] = []  # [{action, port, src}]


class Patches(BaseModel):
    level: str = "current"
    missing: list[str] = []


class Mgmt(BaseModel):
    telnet: bool = False
    ssh: bool = True
    http: bool = False
    https: bool = True
    snmp_community: str | None = None


class DeviceConfig(BaseModel):
    hostname: str
    device_id: str = ""
    interfaces: list[Interface] = []
    vlans: list[Vlan] = [Vlan(id=1, name="default")]
    routes: list[Route] = []
    acls: list[Acl] = []
    fw_policies: list[FwPolicy] = []
    nat: list[NatRule] = []
    vpn: list[Vpn] = []
    users: list[User] = []
    services: list[Service] = []
    host_firewall: HostFirewall = HostFirewall()
    patches: Patches = Patches()
    mgmt: Mgmt = Mgmt()
    isolated: bool = False
    quarantine_vlan: int | None = None
    weaknesses: list[str] = []


class ConfigDiff(BaseModel):
    device_id: str
    author: str = "human"  # human|ai|system
    ops: list[dict] = Field(default_factory=list)  # [{op: set|add|remove|action, path, value}]
    summary: str = ""
