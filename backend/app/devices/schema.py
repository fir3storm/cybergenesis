from pydantic import BaseModel


class OSPersonality(BaseModel):
    name: str
    version: str = ""


class Personality(BaseModel):
    cli: str = "generic"
    gui: str = "generic"
    skin: str = "generic"


class PortSpec(BaseModel):
    prefix: str
    start: int = 1
    count: int = 4
    speed: str = "1G"
    media: str = "copper"
    poe: bool = False


class Hardware(BaseModel):
    form: str = "1RU"
    ports: list[PortSpec] = []
    mgmt_port: str = "mgmt0"


class DeviceManifest(BaseModel):
    id: str
    vendor: str
    family: str
    model: str
    category: str  # router|switch|firewall|wireless|security|server|endpoint|virtual|ot|identity
    tier: str = "catalog"  # flagship|catalog
    os: OSPersonality
    personality: Personality = Personality()
    hardware: Hardware = Hardware()
    capabilities: list[str] = []
    default_config: dict = {}
    weaknesses: list[str] = []
    services: list[str] = []
    model3d: str = "appliance"
    icon: str = "server"
    mitre_defends: list[str] = []
