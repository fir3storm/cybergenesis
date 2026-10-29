# CYBERGENESIS — 3:00 demo narration

TTS: edge-tts, voice `en-US-GuyNeural`, rate -5%. Video: `docs/demo-final.mp4`, 180.000 s, 1440x810.
Live AI in the recorded take: Meta Muse Spark 1.3 (`meta/muse-spark-1.3`) served through Command Code.

## 0:00 Problem (Welcome screen, Judge Mode)
Security tools stop at detection. They raise alerts, but never prove a
defense works, and letting an AI change a firewall feels reckless.

## 0:14 Solution (Living Twin)
CYBERGENESIS gives defenders a safe place to fight and to prove. This is a
living digital twin of an enterprise network: every asset, link, service and
weakness, compiled from configuration. It is fully synthetic, so we can attack
it as hard as we like.

## 0:36 Attack and reasoning (Run Autonomous Defense Demo)
We launch a ransomware-style attack. The Observer turns telemetry into
structured evidence. Then Meta's Muse Spark, running live, investigates. Its
hypothesis cites the exact telemetry behind each claim, and separates what is
confirmed from what is speculation. The Strategist proposes a defense from the
attack graph alone, and every candidate is rehearsed on a cloned twin first.

## 1:07 Guardrails (policy gate, human approval)
But the AI never acts directly. A deterministic policy engine, with no language
model in it, validates every proposed action. Invalid plans are rejected as a
unit. High-impact defenses wait for a human, and here the operator approves.
Only allowlisted, typed actions can touch the twin. The AI has no shell, no
file system and no network access.

## 1:36 Prove (Outcome, Verification Lab)
Now the attack is replayed independently, and the verdict here is PASS. A
failure would be shown as FAIL, never hidden. Every run exports an
Ed25519-signed certificate that anyone can verify offline, checks the fix
against the graph's minimum cut, and writes a plain-language board briefing.

## 2:02 Arena, live (Arena: Play match, replay, decision evidence, held-out table)
The Arena puts both sides on the same twin, live. Muse Spark plays red, and
picks an attack route from paths the engine has already validated. Muse Spark
also plays blue, and picks a defense that must pass the same policy gate. If
red still has a route, it reroutes next round; if not, blue wins, and the
winner gets a signed proof. Every choice is logged with its evidence, and each
match feeds a score memory that steers the next one: training changes strategy
scores, never model weights. Across
held-out networks, each strategy is scored against the provable optimum, not
against itself.

## 2:44 Close (Welcome)
CYBERGENESIS does not merely detect attacks. It tests defenses, proves they
work, and shows its evidence. Built on Muse Spark for the Meta Global
Hackathon.
