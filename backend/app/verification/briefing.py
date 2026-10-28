"""CISO board briefing: a one-page, plain-language summary of one verified run.

Every number comes from the stored run (verification metrics, executions,
policy decisions, approvals). An optional AI narrative may *rephrase* those
facts; it is schema-validated, length-bounded, labelled live/offline, and
never replaces the deterministic fact sheet beneath it.

Compliance tags are an indicative mapping of each executed defense action to
NIST CSF 2.0 subcategories and CIS Controls v8 safeguards. They show which
controls the run produced evidence for; they are not an audit opinion.
"""

from pydantic import BaseModel, Field, ValidationError

# action_type -> (NIST CSF 2.0 subcategories, CIS Controls v8)
CONTROL_MAP: dict[str, tuple[list[str], list[str]]] = {
    "block_connection": (["PR.IR-01", "RS.MI-01"], ["CIS 12 Network Infrastructure Mgmt", "CIS 13 Network Monitoring & Defense"]),
    "isolate_asset": (["RS.MI-01"], ["CIS 13 Network Monitoring & Defense"]),
    "quarantine_vlan": (["RS.MI-01", "PR.IR-01"], ["CIS 12 Network Infrastructure Mgmt", "CIS 13 Network Monitoring & Defense"]),
    "apply_patch": (["ID.RA-01", "PR.PS-02"], ["CIS 7 Continuous Vulnerability Mgmt"]),
    "disable_service": (["PR.PS-01", "RS.MI-01"], ["CIS 4 Secure Configuration"]),
    "enforce_mfa": (["PR.AA-03"], ["CIS 6 Access Control Mgmt"]),
    "revoke_session": (["PR.AA-05", "RS.MI-01"], ["CIS 6 Access Control Mgmt"]),
    "rotate_credential": (["PR.AA-01"], ["CIS 5 Account Mgmt"]),
    "harden_mgmt": (["PR.PS-01"], ["CIS 4 Secure Configuration", "CIS 12 Network Infrastructure Mgmt"]),
    "kill_process": (["RS.MI-01"], ["CIS 10 Malware Defenses"]),
    "deploy_decoy": (["DE.CM-01"], ["CIS 13 Network Monitoring & Defense"]),
    "restore_connectivity": (["RC.RP-01"], ["CIS 11 Data Recovery"]),
    "restore_snapshot": (["RC.RP-01", "PR.DS-11"], ["CIS 11 Data Recovery"]),
}
# Every verified run is itself a security test of the defense.
RUN_CONTROLS = (["ID.IM-02", "DE.AE-02"], [])

CSF_TITLES = {
    "PR.IR-01": "Networks and environments are protected from unauthorized logical access",
    "RS.MI-01": "Incidents are contained",
    "ID.RA-01": "Vulnerabilities in assets are identified",
    "PR.PS-02": "Software is maintained, replaced, and removed commensurate with risk",
    "PR.PS-01": "Configuration management practices are established and applied",
    "PR.AA-03": "Users, services, and hardware are authenticated",
    "PR.AA-05": "Access permissions and authorizations are managed",
    "PR.AA-01": "Identities and credentials are managed",
    "DE.CM-01": "Networks and network services are monitored",
    "RC.RP-01": "The recovery portion of the incident response plan is executed",
    "PR.DS-11": "Backups of data are created, protected, maintained, and tested",
    "ID.IM-02": "Improvements are identified from security tests and exercises",
    "DE.AE-02": "Potentially adverse events are analyzed",
}
DISCLAIMER = "Indicative control mapping from a synthetic simulation; evidence for a control, not an audit opinion."


def compliance_tags(executions: list[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    for csf in RUN_CONTROLS[0]:
        seen[csf] = {"framework": "NIST CSF 2.0", "id": csf, "title": CSF_TITLES[csf], "evidenced_by": ["verification replay"]}
    for e in executions:
        if not e.get("success"):
            continue
        csf_ids, cis_ids = CONTROL_MAP.get(e["action_type"], ([], []))
        ref = f"{e['action_type']} on {e['asset_id']}"
        for cid in csf_ids:
            seen.setdefault(cid, {"framework": "NIST CSF 2.0", "id": cid, "title": CSF_TITLES.get(cid, ""), "evidenced_by": []})
            seen[cid]["evidenced_by"].append(ref)
        for cis in cis_ids:
            seen.setdefault(cis, {"framework": "CIS Controls v8", "id": cis, "title": "", "evidenced_by": []})
            seen[cis]["evidenced_by"].append(ref)
    return sorted(seen.values(), key=lambda t: (t["framework"], t["id"]))


def fact_sheet(run: dict, scenario: dict, results: dict) -> dict:
    """Deterministic facts only. Missing values stay None and are shown as unknown."""
    ver = results.get("verification") or {}
    m = ver.get("metrics") or {}
    outcome = ver.get("outcome") or "NOT VERIFIED"
    execs = [e for e in results.get("executions", []) if e.get("success")]
    rejected = [p for p in results.get("policy", []) if not p.get("approved")]
    modes = sorted({d.get("mode") for d in results.get("decisions", []) if d.get("mode")})
    models = sorted({d.get("model") for d in results.get("decisions", []) if d.get("mode") == "live" and d.get("model")})
    usage = results.get("usage") or {}
    gap = m.get("optimality_gap")
    if m.get("primary_objective_blocked") is False:
        opt_verdict = "NOT_A_CUT"
    elif gap is None:
        opt_verdict = None
    elif gap == 0:
        opt_verdict = "OPTIMAL"
    else:
        opt_verdict = "SUBOPTIMAL"
    return {
        "run_id": run["id"], "scenario": scenario.get("name", run.get("scenario_id")),
        "threat": scenario.get("description", ""), "target": scenario.get("target_asset"),
        "outcome": outcome, "run_state": run.get("state"), "run_error": run.get("error"),
        "objective_blocked": m.get("primary_objective_blocked"),
        "effectiveness_pct": m.get("defense_effectiveness_pct"),
        "risk_before_pct": m.get("risk_before_pct"), "risk_after_pct": m.get("risk_after_pct"),
        "risk_after_ci95": m.get("risk_after_ci95"),
        "users_affected": m.get("users_affected"),
        "legit_paths_disrupted": m.get("operational_impact_disrupted_legit_paths"),
        "time_to_detect_s": m.get("time_to_detect_s"), "time_to_contain_s": m.get("time_to_contain_s"),
        "time_basis": m.get("time_basis"),
        "optimality_verdict": opt_verdict, "optimality_gap": gap,
        "actions": [f"{e['action_type']} on {e['asset_id']}" for e in execs],
        "policy_rejections": [f"{p['action_type']} on {p['asset_id']}: {'; '.join(p.get('reasons') or [])}" for p in rejected],
        "ai_modes": modes, "ai_models": models,
        "tokens": (usage.get("prompt_tokens") or 0) + (usage.get("completion_tokens") or 0),
    }


def _fmt(v, suffix=""):
    return "unknown" if v is None else f"{v}{suffix}"


def deterministic_narrative(f: dict) -> dict:
    blocked = f["outcome"] == "PASS"
    if blocked:
        headline = f"Simulated {f['scenario']} stopped before reaching {f['target']}; fix independently verified."
    elif f["outcome"] == "NOT VERIFIED":
        headline = f"Simulated {f['scenario']} run did not reach verification ({f['run_state']})."
    else:
        headline = f"Simulated {f['scenario']} NOT stopped: {f['target']} remained reachable after the response."
    ci = f["risk_after_ci95"]
    ci_text = f" (95% CI {ci[0]}-{ci[1]}%)" if ci else ""
    opt_text = ""
    if f.get("optimality_verdict") == "OPTIMAL":
        opt_text = " The defense is provably optimal (optimality verdict OPTIMAL, gap 0)."
    elif f.get("optimality_verdict") == "SUBOPTIMAL":
        opt_text = f" Optimality verdict SUBOPTIMAL: the defense used {f.get('optimality_gap')} edge(s) more than the proven minimum."
    elif f.get("optimality_verdict") == "NOT_A_CUT":
        opt_text = " Optimality verdict NOT_A_CUT: the defense did not cut every attack path."
    summary = (
        f"Breach likelihood moved from {_fmt(f['risk_before_pct'], '%')} to {_fmt(f['risk_after_pct'], '%')}{ci_text}. "
        f"{len(f['actions'])} defensive action(s) applied; {_fmt(f['users_affected'])} users affected and "
        f"{_fmt(f['legit_paths_disrupted'])} legitimate paths disrupted. "
        f"{len(f['policy_rejections'])} proposed action(s) were rejected by the policy gate."
        f"{opt_text}"
    )
    asks = []
    if not blocked:
        asks.append("Approve a follow-up exercise: the current response did not close the attack path.")
    if f["policy_rejections"]:
        asks.append("Review the policy rejections: the AI proposed actions the guardrails refused.")
    asks.append("Schedule this exercise to re-run after the next network change.")
    return {"headline": headline, "summary": summary, "board_asks": asks[:3], "mode": "offline", "model": "deterministic"}


class _AiNarrative(BaseModel):
    headline: str = Field(max_length=160)
    summary: str = Field(max_length=900)
    board_asks: list[str] = Field(default_factory=list, max_length=3)


NARRATIVE_SYSTEM = (
    "You write a 60-second board briefing for a CISO about ONE synthetic security exercise. "
    "Use ONLY the facts in the user message; do not add numbers, assets, or claims that are not there. "
    "If outcome is not PASS, say plainly that the defense did not work. Plain business language, no jargon. "
    'Reply as JSON: {"headline": str <=160 chars, "summary": str <=900 chars, "board_asks": [<=3 short strings]}'
)


async def ai_narrative(f: dict, run_id: str) -> dict:
    """Live rephrasing of the fact sheet; falls back to the deterministic text with the reason."""
    import json

    from app.integrations.meta_client import ProviderUnavailable, meta_client

    fallback = deterministic_narrative(f)
    try:
        data, _rec = await meta_client.chat_json(NARRATIVE_SYSTEM, json.dumps(f, default=str), run_id=run_id)
        n = _AiNarrative.model_validate(data)
    except ProviderUnavailable as e:
        return {**fallback, "fallback_reason": str(e)}
    except ValidationError as e:
        return {**fallback, "fallback_reason": f"AI narrative failed schema validation: {e.errors()[0].get('msg')}"}
    return {"headline": n.headline, "summary": n.summary, "board_asks": n.board_asks,
            "mode": "live", "model": meta_client.model}


def to_markdown(b: dict) -> str:
    f, n = b["facts"], b["narrative"]
    label = f"AI-drafted ({n['model']}) from the verified facts below" if n["mode"] == "live" else "deterministic summary (no AI)"
    lines = [f"# Board briefing: {f['scenario']}", "", f"**{n['headline']}**", "", n["summary"], "",
             f"_Narrative: {label}._" + (f" _AI unavailable: {n['fallback_reason']}_" if n.get("fallback_reason") else ""), "",
             "## Decisions requested"] + [f"- {a}" for a in n["board_asks"]] + [
             "", "## Verified facts",
             f"- Outcome: **{f['outcome']}** (run {f['run_id']})",
             f"- Risk: {_fmt(f['risk_before_pct'], '%')} -> {_fmt(f['risk_after_pct'], '%')}",
             f"- Users affected: {_fmt(f['users_affected'])} · legitimate paths disrupted: {_fmt(f['legit_paths_disrupted'])}",
             f"- Detect / contain: {_fmt(f['time_to_detect_s'], ' s')} / {_fmt(f['time_to_contain_s'], ' s')} ({f['time_basis'] or 'simulated'})",
             f"- Optimality: {f.get('optimality_verdict') or 'unknown'} (gap {_fmt(f.get('optimality_gap'))})",
             f"- Actions: {', '.join(f['actions']) or 'none'}",
             f"- Policy rejections: {'; '.join(f['policy_rejections']) or 'none'}",
             f"- AI involvement: modes {', '.join(f['ai_modes']) or 'none'}; models {', '.join(f['ai_models']) or 'none'}; {f['tokens']} tokens",
             "", "## Control evidence"]
    for t in b["compliance"]:
        lines.append(f"- {t['framework']} {t['id']}{(' ' + t['title']) if t['title'] else ''}: {', '.join(t['evidenced_by'])}")
    lines += ["", f"_{DISCLAIMER}_", "", "_Synthetic simulation only._"]
    return "\n".join(lines)
