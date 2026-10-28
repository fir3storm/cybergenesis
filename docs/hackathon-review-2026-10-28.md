# Hackathon review — 2026-10-28

Assessment: credible indie-track contender, but not yet a defensible claim of novel autonomous cyber learning. Strongest story: visual defense rehearsal with deterministic policy gates, counterfactual comparison, and replayable evidence.

## High-priority findings
1. Arena resolves in at most one defended round: a reachable objective ends in Red victory; a blocked objective ends on the next loop entry. All five builtin scenarios reproduced one round with max_rounds=10. The chosen red path is recorded but does not drive a new per-round attack. See backend/app/arena/engine.py:66-109.
2. Benchmark does not measure live AI advantage: scripts/benchmark.py compares none/offline/simulate using expected_defense and five small topology templates. Add held-out topology comparisons of deterministic, live Meta, and learned strategies; report disruption, failures, latency, token cost and raw results.
3. Learning is outcome-count scoring, not model training. No held-out evaluation currently establishes improvement. Recent changes isolate scenario memory and add sessions; they do not resolve the arena engine issue.
4. Arena auditing is thinner than AGENTS.md requires: label/index checks instead of typed Pydantic response schemas; red rationale discarded; blue rationale not copied into round records; complete decision provenance absent.
5. Proofs apply to the synthetic graph model. HMAC verification requires a shared secret and is not public-key attestation or proof of production network security.
6. Submission documentation is stale: HACKATHON_SUBMISSION.md describes 13 backend tests and three scenarios.

## Verification scope
- Earlier this session: 23 focused backend arena tests, 28 frontend tests, TypeScript and production build passed.
- Full backend pytest attempted in this review; did not complete, remained at 40%; stopped review processes. Do not claim full-suite success.
- Ruff: 4 failures (one unused noqa in test_catalog.py; three broad Exception assertions in test_meta_client.py).
- Browser inspection blocked by unavailable browser bridge; no fresh end-to-end visual or live Meta verification claimed.
- All five built-in arena scenarios directly exercised offline at max_rounds=10: each returned one round, Blue victory.

## Competition context
Official event: https://dev.meta.ai/events/global-hackathon
Indie: creativity, technical ambition, working implementation. Startup: execution and production readiness.
Prior art: https://github.com/microsoft/CyberBattleSim and https://cymulate.com/
Combination and execution can differentiate this project; the broad category is established.

## Recommended submission focus
Demonstrate one unfamiliar topology, a real Meta proposal, a policy rejection or meaningful tradeoff, an independently replayed result, and a counterfactual with measured operational impact. Prioritize fixing the battle loop and measuring Meta's contribution over adding screens. Avoid asserting win probabilities without competitor and judge evidence.
