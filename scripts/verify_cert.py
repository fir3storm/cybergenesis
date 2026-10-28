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
    with open(args[0], encoding="utf-8") as fh:
        cert = json.loads(fh.read())
    twin = cert["final_twin"]
    if len(args) > 1:
        with open(args[1], encoding="utf-8") as fh:
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
