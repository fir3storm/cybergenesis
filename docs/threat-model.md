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

## Red-team campaign boundary (Phase 1+)
The red team is an LLM *planner over a validated graph*, not an executor: Muse Spark returns a campaign (foothold / identity pivot / objective / typed steps) which `evaluate_campaign` checks deterministically — allowlisted step types, existing assets, and every hop an active traversable arc (or a compromised synthetic identity pivot). Invalid campaigns are rejected with feedback and one retry. Red moves are additionally hop-validated before application in every round.

## Human approval & token budget (Phase 4)
Defenses estimated to disrupt ≥2 legitimate paths (or isolating an identity asset) pause in `AWAITING_APPROVAL` when `HUMAN_APPROVAL_ENABLED=true`; an operator must call `/approve` or `/deny`, with auto-deny after `APPROVAL_TIMEOUT_SECONDS` (default 120). `AUTO_APPROVE=true` is a demo-only setting that still logs the approval event. Live Meta calls are capped by `MAX_TOKENS_PER_RUN` (default 20000); exceeding it forces a labelled offline fallback with the budget reason. Model usage is stored per run (locked dict) with prompt version + prompt hash.

## Device emulation boundary
All device windows, CLIs, faceplates and OS shells are **emulations over synthetic config state** — no real device connections, protocol traffic, or vendor software. Vendor and model names are used descriptively only; skins are vendor-inspired layout conventions with a colour accent, not copied GUIs or logos, and every device window carries "Emulated for simulation. Not affiliated with any vendor." CLI syntax emulation is original code rendering synthetic config. Weaknesses are synthetic classes (telnet_enabled, snmp_public_community, any_any_rule, rdp_exposed, missing_mfa, outdated_firmware) — never real exploits or credentials.

## Residual risks
A malicious prompt-injection via scenario text could bias an LLM proposal — mitigated because policy, not the LLM, authorises execution, and verification independently replays outcomes. Synthetic credentials (`admin-01` v1→v2) are labels, not secrets.
