# Submission Rules Check (verify before submitting)

Verified from the repo itself:
- [x] Repository is **public**: https://github.com/fir3storm/cybergenesis (`gh repo view` → PUBLIC)
- [x] License: **MIT** (`LICENSE` at repo root)
- [x] No secrets in tracked files: `backend/.env` is git-ignored (`git check-ignore backend/.env`); tracked files contain only empty `MODEL_API_KEY=` placeholders. Re-run before every push: `git grep -l "LLM_" -- .` must return nothing.
- [x] Primary AI is Meta Muse Spark via the Meta Model API (`muse-spark-1.3`, configurable via `META_MODEL`); offline mode is labelled, never faked.
- [x] One-command start: `scripts/start.ps1` / `scripts/start.sh` after first-time dependency and environment setup.
- [x] Safety scope: synthetic twin only — no real targets, scanning, exploitation, or credential material (see `docs/threat-model.md`).

Still to confirm against the official hackathon rules page before final submission (organizer-specific, cannot be verified from the repo):
- [ ] Allowed/required models and whether `muse-spark-1.3` via Meta Model API satisfies the "Meta AI" requirement as configured
- [ ] Required tech stack constraints, team size, and eligibility
- [ ] Video length limit and required content (plan: `docs/demo-script.md`, 3 minutes)
- [ ] Whether a hosted demo is allowed/required, and any repo-visibility deadline
- [ ] Submission form fields vs `HACKATHON_SUBMISSION.md`
