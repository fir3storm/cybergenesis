"""Independent certificate checker. No LLM, no database.

Usage: python scripts/verify_cert.py certificate.json [twin.json] [--pubkey HEX]
Recomputes: the Ed25519 signature (public key only, needs the `cryptography`
package; pin the signer with --pubkey from GET /api/certificates/public-key),
the legacy HMAC (only when CERT_DEMO_KEY is set), the event hash chain,
reachability + frontier from the embedded final twin, and the min-cut claim.
Prints VALID or INVALID (with reasons).
"""

import hashlib
import hmac
import itertools
import json
import os
import sys
from collections import deque

DEMO_KEY = os.environ.get("CERT_DEMO_KEY")


def _check_ed25519(cert: dict, pinned: str | None, reasons: list[str]) -> bool:
    """True when a valid Ed25519 signature was checked; failures go to reasons."""
    block = cert.get("ed25519")
    if not block:
        if pinned:
            reasons.append("--pubkey given but the certificate carries no Ed25519 signature")
        return False
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError:
        print("note: `cryptography` not installed; Ed25519 signature not checked", file=sys.stderr)
        return False
    if pinned and pinned.lower() != str(block.get("public_key", "")).lower():
        reasons.append("Ed25519 public key does not match the pinned --pubkey (different signer)")
        return False
    body = {k: cert[k] for k in sorted(cert) if k not in ("signature", "ed25519")}
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(block["public_key"])).verify(
            bytes.fromhex(block["signature"]), json.dumps(body, sort_keys=True, default=str).encode())
    except (InvalidSignature, ValueError, KeyError):
        reasons.append("Ed25519 signature invalid (tampered or wrong key)")
        return False
    return True


def check_optimality_proof(proof) -> tuple[bool, list[str]]:
    """Standalone copy of app.verification.optimality.check_optimality_proof.

    Uses only the proof itself (hash, witness disjointness, cut check via BFS).
    Kept dependency-free apart from the stdlib so the script works anywhere.
    """
    reasons: list[str] = []
    if not isinstance(proof, dict):
        return False, ["proof is not an object"]
    for field in ("version", "source", "target", "graph_edges", "graph_sha256",
                  "witness_paths", "lower_bound", "defense_cut", "defense_cut_size",
                  "is_cut", "optimality_gap", "verdict"):
        if field not in proof:
            reasons.append(f"proof missing field: {field}")
    if reasons:
        return False, reasons
    if proof["version"] != 1:
        reasons.append(f"unsupported proof version: {proof['version']}")
    src, tgt = proof["source"], proof["target"]
    graph_edges = [list(e) for e in proof["graph_edges"]]
    edge_set = {tuple(e) for e in graph_edges}
    if len(edge_set) != len(graph_edges):
        reasons.append("graph_edges contains duplicate edges")
    if graph_edges != sorted(graph_edges):
        reasons.append("graph_edges is not sorted")
    blob = json.dumps(graph_edges, sort_keys=True, separators=(",", ":"))
    if hashlib.sha256(blob.encode()).hexdigest() != proof["graph_sha256"]:
        reasons.append("graph_sha256 mismatch (graph_edges tampered)")
    witness = [list(p) for p in proof["witness_paths"]]
    if proof["lower_bound"] != len(witness):
        reasons.append(f"lower_bound {proof['lower_bound']} != number of witness paths {len(witness)}")
    used: set = set()
    for i, path in enumerate(witness):
        if not path or path[0] != src or path[-1] != tgt:
            reasons.append(f"witness path {i} does not run {src}->{tgt}")
            continue
        for a, b in itertools.pairwise(path):
            if (a, b) not in edge_set:
                reasons.append(f"witness path {i} uses edge {a}->{b} not in graph_edges")
            if (a, b) in used:
                reasons.append(f"witness paths are not edge-disjoint: edge {a}->{b} reused")
            used.add((a, b))
    cut = [list(e) for e in proof["defense_cut"]]
    cut_set = {tuple(e) for e in cut}
    if proof["defense_cut_size"] != len(cut):
        reasons.append(f"defense_cut_size {proof['defense_cut_size']} != len(defense_cut) {len(cut)}")
    for a, b in cut:
        if (a, b) not in edge_set:
            reasons.append(f"defense_cut edge {a}->{b} not in graph_edges")
    adj: dict[str, list[str]] = {}
    for a, b in graph_edges:
        if (a, b) not in cut_set:
            adj.setdefault(a, []).append(b)
    seen = {src}
    q = deque([src])
    while q:
        node = q.popleft()
        for nb in adj.get(node, []):
            if nb not in seen:
                seen.add(nb)
                q.append(nb)
    has_path = tgt in seen
    is_cut = not has_path
    if bool(proof["is_cut"]) != is_cut:
        reasons.append(f"is_cut claim {proof['is_cut']} disagrees with recomputation (path remains: {has_path})")
    k = len(witness)
    verdict, gap = proof["verdict"], proof["optimality_gap"]
    if verdict == "NO_PATH_AT_BASELINE":
        full: dict[str, list[str]] = {}
        for a, b in graph_edges:
            full.setdefault(a, []).append(b)
        reach, q = {src}, deque([src])
        while q:
            for nb in full.get(q.popleft(), []):
                if nb not in reach:
                    reach.add(nb)
                    q.append(nb)
        if tgt in reach:
            reasons.append("verdict NO_PATH_AT_BASELINE but graph_edges contain a source->target path")
    if k == 0:
        if verdict != "NO_PATH_AT_BASELINE":
            reasons.append(f"verdict {verdict} inconsistent: no witness paths but verdict is not NO_PATH_AT_BASELINE")
        if gap is not None:
            reasons.append("optimality_gap must be null when there is no baseline path")
    elif not is_cut:
        if verdict != "NOT_A_CUT":
            reasons.append(f"verdict {verdict} inconsistent: defense_cut is not a cut")
        if gap is not None:
            reasons.append("optimality_gap must be null when defense is not a cut")
    else:
        expected_gap = len(cut) - k
        if gap != expected_gap:
            reasons.append(f"optimality_gap {gap} != defense_cut_size - lower_bound ({expected_gap})")
        expected_verdict = "OPTIMAL" if expected_gap == 0 else "SUBOPTIMAL"
        if verdict != expected_verdict:
            reasons.append(f"verdict {verdict} inconsistent: expected {expected_verdict}")
    return (not reasons), reasons


def derive_graph_edges(twin: dict, tgt: str) -> list:
    """Re-derive the gated baseline attack graph from an embedded twin dict.

    Mirrors DigitalTwin.live_graph for a baseline twin: directed arcs from
    connection dir flags (which already encode isolation/quarantine cuts),
    gated by hop_allowed (vulnerability / target / compromised-identity).
    """
    vulns = {a["id"]: (a.get("vulnerabilities") or []) for a in twin.get("assets", [])}
    any_comp = any(i.get("compromised") for i in (twin.get("identities") or {}).values())

    def hop_allowed(dest: str) -> bool:
        return dest == tgt or bool(vulns.get(dest)) or (any_comp and dest in ("database", "admin-workstation", "identity-provider"))

    edges = set()
    for c in twin.get("connections", []):
        if not c.get("traversable"):
            continue
        if c.get("dir_forward_active", c.get("active")) and hop_allowed(c["target"]):
            edges.add((c["source"], c["target"]))
        if c.get("dir_reverse_active", c.get("active")) and hop_allowed(c["source"]):
            edges.add((c["target"], c["source"]))
    return sorted([list(e) for e in edges])

def main() -> int:
    args = sys.argv[1:]
    pinned = None
    if "--pubkey" in args:
        i = args.index("--pubkey")
        if i + 1 >= len(args):
            print("error: --pubkey needs a hex value", file=sys.stderr)
            return 2
        pinned = args[i + 1]
        del args[i:i + 2]
    if not args:
        print("usage: verify_cert.py certificate.json [twin.json] [--pubkey HEX]")
        return 2
    # utf-8-sig: certificates re-saved on Windows (Notepad, PowerShell) often carry a BOM
    with open(args[0], encoding="utf-8-sig") as fh:
        cert = json.loads(fh.read())
    twin = cert["final_twin"]
    if len(args) > 1:
        with open(args[1], encoding="utf-8-sig") as fh:
            twin = json.loads(fh.read())
    reasons: list[str] = []

    # 1. signatures: Ed25519 (public key) and/or legacy HMAC (shared CERT_DEMO_KEY)
    ed_ok = _check_ed25519(cert, pinned, reasons)
    if DEMO_KEY:
        signed = {k: cert[k] for k in sorted(cert) if k != "signature"}
        expect = hmac.new(DEMO_KEY.encode(), json.dumps(signed, sort_keys=True, default=str).encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expect, cert.get("signature", "")):
            reasons.append("HMAC signature mismatch (tampered or wrong key)")
    elif not ed_ok and not reasons:
        print("error: no signature could be checked: certificate has no Ed25519 signature (or `cryptography` "
              "is missing) and CERT_DEMO_KEY is not set.", file=sys.stderr)
        return 2
    sig_note = "Ed25519 " + ("verified" if ed_ok else "absent") + (", HMAC verified" if DEMO_KEY else "")

    # 2. reachability from the embedded twin, honouring directed arcs + isolation
    conns = twin["connections"]
    isolated = {a["id"] for a in twin["assets"] if a["isolated"]}
    adj: dict[str, list[str]] = {}
    for c in conns:
        if not c["traversable"]:
            continue
        if c.get("dir_forward_active", c["active"]):
            adj.setdefault(c["source"], []).append(c["target"])
        if c.get("dir_reverse_active", c["active"]):
            adj.setdefault(c["target"], []).append(c["source"])
    src, tgt = cert["scenario"]["source"], cert["scenario"]["target"]
    seen = {src}
    q = deque([src])
    while q:
        node = q.popleft()
        for nb in adj.get(node, []):
            if nb not in seen and nb not in isolated:
                seen.add(nb)
                q.append(nb)
    reachable = tgt in seen
    if cert.get("kind") == "arena_match":
        # Arena winner proof: winner must agree with the recomputed objective.
        # Reachability scenarios recompute from the final twin graph; identity
        # scenarios recompute the synthetic session grant from the final twin.
        kind = cert["scenario"].get("verification_kind")
        if kind == "identity" or cert["scenario"].get("identity"):
            ident = (cert["final_twin"].get("identities") or {}).get(cert["scenario"].get("identity") or "", {})
            reachable = bool(ident.get("session_active") and ident.get("compromised"))
        if cert.get("target_reachable_final") != reachable:
            reasons.append("arena target_reachable_final disagrees with recomputation from final twin")
        if cert["winner"] == "red" and not reachable:
            reasons.append("arena claims RED wins but the objective is NOT reachable/granted in the final twin")
        if cert["winner"] == "blue" and reachable:
            reasons.append("arena claims BLUE wins but the objective IS reachable/granted in the final twin")
        if cert["winner"] not in ("red", "blue"):
            reasons.append("arena winner must be red or blue")
        if reasons:
            print("INVALID")
            for r in reasons:
                print(f" - {r}")
            return 1
        print(f"VALID — arena match {cert['match_id']}, scenario {cert['scenario']['id']}, "
              f"winner {cert['winner']}, rounds {cert['rounds_played']}, target reachable: {reachable}")
        return 0
    for camp in cert["campaigns"]:
        proof = camp["unreachable_proof"]
        if camp["outcome"] == "PASS" and reachable:
            reasons.append(f"campaign claims PASS but {tgt} IS reachable in the certified twin")
        if proof["target_reachable"] != reachable:
            reasons.append("frontier proof reachability disagrees with recomputation")

    # 2b. optimality proof (third-party checkable, from the proof alone)
    if cert.get("optimality_proof") is not None and cert.get("baseline_twin"):
        derived = derive_graph_edges(cert["baseline_twin"], cert["optimality_proof"]["target"])
        if derived != [list(e) for e in cert["optimality_proof"]["graph_edges"]]:
            reasons.append("optimality graph_edges do not match the graph re-derived from the embedded baseline twin")
        else:
            print("BASELINE: graph re-derived from embedded baseline twin matches optimality proof")
    elif cert.get("optimality_proof") is not None:
        print("BASELINE: not embedded (proof-format v1; internal consistency only)")
    proof = cert.get("optimality_proof")
    if proof is None:
        print("OPTIMALITY: not present (legacy certificate)")
    else:
        ok, opt_reasons = check_optimality_proof(proof)
        if ok:
            if proof["verdict"] == "OPTIMAL":
                print(f"OPTIMALITY: OPTIMAL (cut {proof['defense_cut_size']} = lower bound "
                      f"{proof['lower_bound']}, {len(proof['witness_paths'])} edge-disjoint witness paths)")
            elif proof["verdict"] == "SUBOPTIMAL":
                print(f"OPTIMALITY: SUBOPTIMAL by {proof['optimality_gap']} edge(s) "
                      f"(cut {proof['defense_cut_size']}, lower bound {proof['lower_bound']})")
            elif proof["verdict"] == "NOT_A_CUT":
                print(f"OPTIMALITY: NOT_A_CUT (cut {proof['defense_cut_size']}, lower bound {proof['lower_bound']})")
            else:
                print(f"OPTIMALITY: {proof['verdict']} (lower bound {proof['lower_bound']})")
        else:
            for r in opt_reasons:
                reasons.append(f"optimality proof: {r}")
            print(f"OPTIMALITY: INVALID ({'; '.join(opt_reasons)})")

    # 3. event hash chain is internally consistent (count + chain head present)
    if cert["events_count"] < 1 or len(cert["event_hash_chain"]) != 64:
        reasons.append("event hash chain missing or malformed")

    if reasons:
        print("INVALID")
        for r in reasons:
            print(f" - {r}")
        return 1
    print(f"VALID — run {cert['run_id']}, scenario {cert['scenario']['id']}, "
          f"campaigns {len(cert['campaigns'])}, target reachable: {reachable} [{sig_note}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
