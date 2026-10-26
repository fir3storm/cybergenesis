# Threat Model & Safety Boundaries

## In scope (allowed)
Synthetic assets, synthetic telemetry, typed predefined scenario steps, graph reachability simulation, allowlisted defensive state changes inside the twin, Meta API inference over synthetic evidence.

## Explicitly out of scope (not implemented, by design)
No real-target discovery or scanning; no exploitation, payloads, propagation, ransomware, credential harvesting, or destructive code; no remote command execution; runtime agents have no shell, no filesystem write, and no network egress except the Meta client; no action outside the twin in the MVP (anything external would require explicit human approval and is absent).

## Trust boundaries
1. **LLM → system:** model output is untrusted data. Pydantic schema validation, then deterministic policy validation. Text never becomes code or commands.
2. **Adversary agent → twin:** only scenario-JSON typed actions (`process_start`, `file_modification_burst`, `network_connection`, `auth_anomaly`, …) executed by the simulation engine.
3. **Defender → twin:** allowlist (`isolate_asset`, `block_connection`, `revoke_session`, `rotate_credential`, `apply_patch`, `disable_service`, `restore_connectivity`) + per-action preconditions (e.g., core assets can never be isolated). Every transition is recorded in `defense_executions` and evidence.
4. **API → clients:** typed schemas, unknown scenarios/actions rejected (422/403), API key never returned (`api_key_exposed: false`), local-development exposure only.

## Residual risks
A malicious prompt-injection via scenario text could bias an LLM proposal — mitigated because policy, not the LLM, authorises execution, and verification independently replays outcomes. Synthetic credentials (`admin-01` v1→v2) are labels, not secrets.
