# Specialized-agent handoff reports

These reports record the implementation handoff for the dynamic-subject build. The shared contract remains the authority; no agent may silently change IDs or response shapes.

| Agent | Changed areas | Verification | Known risk / follow-up |
|---|---|---|---|
| 0 - repository and provenance | Git repository, monorepo folders, root README and environment template | `git status`, `git remote -v`, `frontend/`, `backend/`, `contracts/` confirmed | No remote is configured yet; add the intended remote before publishing. |
| 1 - contract/source steward | `contracts/v2/`, DSAP source pack, 16 frozen cases, source and dynamic-subject docs | JSON fixtures load in backend tests; source IDs are checked against the pack | DSAP pack is intentionally `instructor_review_required` until domain approval. |
| 2 - Django backend | Subject/module/concept models, learner profile and memory, attempts, migrations, dynamic API | `python manage.py check`; `pytest -q` -> 45 passed | SQLite is local-only; PostgreSQL settings and production deployment remain future work. |
| 3 - provider and safety | Fireworks/Qwen and OpenAI provider boundary, structured-output handling, runtime metadata, source-bound checkpoint validation | Provider and API tests pass; live Fireworks smoke path verified separately | OpenAI live calls still require a real server-side key and account access; fixture mode is test-only. |
| 4 - landing and design system | Dynamic home, subject atlas, design tokens and existing visual language | Next typecheck/build pass; home and `/subjects` return HTTP 200 | Final visual regression should be done in a real browser at mobile and desktop widths. |
| 5/6 - learning and interaction surface | Dynamic source intake, model-authored scenes, whiteboard actions, visual payloads, checkpoint posts, and provider badges | Frontend tests pass; study setup/workspace routes return HTTP 200 | Rich media playback and a persisted review calendar remain future slices; the current module is generated from approved candidate context. |
| 7 - accessibility and QA | Accessibility checks plus dynamic contract/API cases | Frontend: 3 tests passed; backend: 45 tests passed | Full Playwright/axe coverage and a two-reviewer learning pilot are still submission-stage work. |
| 8/9 - integration and submission | `.env` files, runbook, cold-browser startup, provider/source provenance docs | Django on `127.0.0.1:8000`, Next.js on `localhost:3000`, key routes verified | Live Fireworks output is labeled `live_fireworks`; source candidates remain reviewable and no learning-gain claim is made. |

## Contract hash / version handoff

- Subject contract: `contracts/v2/subject-pack.schema.json`
- Learning modes: `contracts/v2/learning-mode.schema.json`
- Learner profile: `contracts/v2/learner-profile.schema.json`
- First pack: `contracts/v2/dsap-sampling-aliasing.json`, version `dsap-v1`
- First source pack: `contracts/v2/source-pack.json`, version `dsap-sampling-v1`
- Runtime default: `LLM_PROVIDER=fireworks`, surfaced as `live_fireworks` when the local key is configured
