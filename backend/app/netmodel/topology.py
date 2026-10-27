from pydantic import BaseModel


class CableEnd(BaseModel):
    device: str
    port: str


class Cable(BaseModel):
    id: str
    a: CableEnd
    b: CableEnd
    media: str = "copper"
    speed: str = "1G"


def validate_cable(cable: Cable, manifests: dict, used_ports: set[tuple[str, str]]) -> list[str]:
    """Rules: one cable per port, media must match, port must exist on the manifest."""
    errors: list[str] = []
    for end in (cable.a, cable.b):
        m = manifests.get(end.device)
        if m is None:
            errors.append(f"device {end.device} not in catalog")
            continue
        ports = set()
        for p in m.hardware.ports:
            for i in range(p.count):
                ports.add(f"{p.prefix}{p.start + i}")
        if end.port not in ports:
            errors.append(f"port {end.port} does not exist on {end.device}")
        if (end.device, end.port) in used_ports:
            errors.append(f"port {end.device}:{end.port} already cabled")
    if cable.a.device in manifests and cable.b.device in manifests:
        def media_of(end: CableEnd) -> str | None:
            for p in manifests[end.device].hardware.ports:
                if end.port.startswith(p.prefix):
                    return p.media
            return None

        ma, mb = media_of(cable.a), media_of(cable.b)
        if ma and mb and ma != mb and cable.media not in (ma, mb):
            errors.append(f"media mismatch: {ma} vs {mb} (cable media {cable.media})")
    return errors
