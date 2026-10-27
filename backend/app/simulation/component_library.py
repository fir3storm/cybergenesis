"""Component library: browseable catalog for Twin Designer + Attack Playbook."""

from app.simulation.twin import ALLOWED_ACTIONS, ATTACK_STEP_TYPES

ASSET_TYPES = [
    {"id": "gateway", "label": "Internet Gateway", "description": "External entry point of the twin", "default_posture": 0.4, "default_zone": "external"},
    {"id": "firewall", "label": "Firewall", "description": "Perimeter segmentation control", "default_posture": 0.9, "default_zone": "perimeter"},
    {"id": "web_server", "label": "Web Server", "description": "Public-facing HTTP service (DMZ)", "default_posture": 0.65, "default_zone": "dmz"},
    {"id": "app_server", "label": "Application Server", "description": "Internal application tier", "default_posture": 0.75, "default_zone": "internal"},
    {"id": "database", "label": "Database", "description": "Protected data tier", "default_posture": 0.85, "default_zone": "data"},
    {"id": "identity", "label": "Identity Provider", "description": "Authentication and session authority", "default_posture": 0.9, "default_zone": "identity"},
    {"id": "workstation", "label": "Workstation", "description": "Employee or admin endpoint", "default_posture": 0.6, "default_zone": "endpoints"},
    {"id": "file_server", "label": "File Server", "description": "Shared file services", "default_posture": 0.7, "default_zone": "internal"},
    {"id": "sensor", "label": "Security Sensor", "description": "Monitoring/telemetry sensor (non-traversable by default)", "default_posture": 0.95, "default_zone": "security"},
]

ATTACK_STEPS = [
    {"id": "process_start", "mitre": "TA0002 / T1059", "d3fend": "D3-PSA", "label": "Process Start", "description": "Synthetic suspicious process starts on the asset"},
    {"id": "file_modification_burst", "mitre": "TA0040 / T1486", "d3fend": "D3-FEV", "label": "File Modification Burst", "description": "High-volume synthetic file modifications"},
    {"id": "network_connection", "mitre": "TA0011 / T1071", "d3fend": "D3-NTF", "label": "Network Connection", "description": "Synthetic connection attempt along the topology"},
    {"id": "auth_anomaly", "mitre": "TA0006 / T1078", "d3fend": "D3-AA", "label": "Auth Anomaly", "description": "Synthetic authentication from an unusual context"},
    {"id": "session_created", "mitre": "TA0006 / T1133", "d3fend": "D3-AA", "label": "Session Created", "description": "Synthetic suspicious session established"},
    {"id": "authorization_failure", "mitre": "TA0006 / T1110", "d3fend": "D3-ACH", "label": "Authorization Failure", "description": "Synthetic unauthorized access attempt"},
    {"id": "config_modification", "mitre": "TA0005 / T1562", "d3fend": "D3-CM", "label": "Config Modification", "description": "Synthetic configuration change"},
    {"id": "security_detection", "mitre": "TA0005 / T1562.001", "d3fend": "D3-FAI", "label": "Security Detection", "description": "Sensor raises a synthetic detection"},
]

DEFENSE_ACTIONS = [
    {"id": "isolate_asset", "label": "Isolate Asset", "params_contract": "{asset_id}", "description": "Cut all connections of the asset (containment)"},
    {"id": "block_connection", "label": "Block Connection", "params_contract": "{asset_id=source, params:{source, target}}", "description": "Segment one connection (choke point)"},
    {"id": "revoke_session", "label": "Revoke Session", "params_contract": "{asset_id, params:{identity}}", "description": "Kill a synthetic identity session"},
    {"id": "rotate_credential", "label": "Rotate Credential", "params_contract": "{asset_id, params:{identity}}", "description": "Rotate a synthetic credential (version +1)"},
    {"id": "apply_patch", "label": "Apply Patch", "params_contract": "{asset_id}", "description": "Remove simulated vulnerabilities (does not stop active spread)"},
    {"id": "disable_service", "label": "Disable Service", "params_contract": "{asset_id: web/app server}", "description": "Disable an exposed simulated service"},
    {"id": "restore_connectivity", "label": "Restore Connectivity", "params_contract": "{asset_id}", "description": "Undo isolation"},
]

VERIFICATION_KINDS = ["reachability", "identity_access"]


def library() -> dict:
    return {
        "asset_types": ASSET_TYPES,
        "attack_steps": [s for s in ATTACK_STEPS if s["id"] in ATTACK_STEP_TYPES],
        "defense_actions": [d for d in DEFENSE_ACTIONS if d["id"] in ALLOWED_ACTIONS],
        "verification_kinds": VERIFICATION_KINDS,
        "zones": sorted({a["default_zone"] for a in ASSET_TYPES} | {"custom"}),
    }
