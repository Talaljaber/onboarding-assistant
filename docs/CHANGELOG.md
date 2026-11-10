# Changelog

Compiled by the integrator at each wave gate from `docs/changelog/<task-id>.md`. Agents never edit this file.

### W0 — repo prep, data import, venv (integrator, 2026-11-11)
- What now exists: git identity and ignore rules, `.gitattributes`, `.env.example`, `CLAUDE.md`, pinned `requirements*.txt`, `.venv`, the six official CSVs with `SHA256SUMS.txt`, the e5 encoder in `models/e5`, `scripts/check_official.py`, `scripts/check_encoder.py`, root `conftest.py` + `pytest.ini`, `docs/` skeleton (PLAN, DECISIONS, evidence, research).
- Acceptance: `check_official.py` → "6 files OK"; `check_encoder.py` → "encoder OK: intfloat/multilingual-e5-small dim=384".
