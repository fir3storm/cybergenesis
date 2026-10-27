"""Read-only tools. No tool mutates the live twin; simulate_on_clone works on clones."""

from app.simulation.component_library import library


class ToolRefused(Exception):
    pass


def _get_twin_summary(ctx, args):
    return ctx.twin.to_dict() | {"config_hash": ctx.twin.config_hash()}


def _get_asset(ctx, args):
    aid = args["id"]
    assets = {a["id"]: a for a in ctx.twin.to_dict()["assets"]}
    if aid not in assets:
        raise ToolRefused(f"asset {aid} not in twin")
    return assets[aid]


def _list_telemetry(ctx, args):
    events = ctx.telemetry
    f = args.get("filter")
    if f:
        events = [e for e in events if f in str(e)]
    return events[: int(args.get("limit", 50))]


def _explain_path(ctx, args):
    return ctx.twin.explain_path(args["src"], args["dst"])


def _get_device_config(ctx, args):
    cfg = ctx.twin.device_configs.get(args["id"])
    if cfg is None:
        raise ToolRefused(f"no device config for {args['id']}")
    return cfg


def _list_findings(ctx, args):
    return ctx.findings


def _simulate_on_clone(ctx, args):
    from app.simulation.candidates import evaluate_candidates

    actions = args["actions"]
    attacked = ctx.twin.clone()
    results = evaluate_candidates(attacked, ctx.baseline_twin or attacked, ctx.scenario, actions)
    return results[0] if results else {"blocked": False, "disrupted": None}


def _get_mitre(ctx, args):
    lib = library()
    for s in lib["attack_steps"] + lib["defense_actions"]:
        if args["technique"] in (s.get("mitre", "") + s.get("d3fend", "")) or args["technique"] == s["id"]:
            return s
    return {"found": False, "technique": args["technique"]}


def _search_memory(ctx, args):
    sig = str(args.get("signature", "")).lower()
    return [m for m in ctx.memory if sig in str(m).lower()][:10]


TOOL_FUNCS = {
    "get_twin_summary": _get_twin_summary,
    "get_asset": _get_asset,
    "list_telemetry": _list_telemetry,
    "explain_path": _explain_path,
    "get_device_config": _get_device_config,
    "list_findings": _list_findings,
    "simulate_on_clone": _simulate_on_clone,
    "get_mitre": _get_mitre,
    "search_memory": _search_memory,
}

ALL_TOOLS = sorted(TOOL_FUNCS)


class ToolExecutor:
    def __init__(self, allowed: list[str]):
        self.allowed = set(allowed)
        self.log: list[dict] = []

    def call(self, ctx, tool_id: str, args: dict) -> dict:
        if tool_id not in TOOL_FUNCS:
            self.log.append({"tool": tool_id, "refused": "unknown tool"})
            raise ToolRefused(f"unknown tool: {tool_id}")
        if tool_id not in self.allowed:
            self.log.append({"tool": tool_id, "refused": "not in agent tool permissions"})
            raise ToolRefused(f"tool {tool_id} not granted to this agent")
        result = TOOL_FUNCS[tool_id](ctx, args or {})
        self.log.append({"tool": tool_id, "args": args, "ok": True})
        return result if isinstance(result, dict) else {"result": result}
