# Feynman AI — Handoff for Aaditya

**Date:** July 17, 2026
**Branch to use:** `main`
**Product:** source-bounded, dynamic learning workspace. DSAP is the first content pack; it is not a hard-coded product boundary.

## What is working

- A Next.js frontend with a minimalist study intake and workspace:
  - `/study/new` accepts a subject, sources, learning approach, and live provider.
  - `/study/workspace` renders a model-authored whiteboard learning flow with reveal steps, prediction, retrieval, teach-back, source anchors, and a module copilot.
- A Django REST backend for source ingestion, subject packs, learner memory, attempts, study-plan generation, live interactions, and module chat.
- Fireworks/Qwen is the active local live provider:
  - model: `accounts/fireworks/models/qwen3p7-plus`
  - provider mode surfaced to the learner: `live_fireworks`
- OpenAI remains an optional server-side provider. It is never exposed to the browser and must not be claimed as active without a valid key.
- The first dynamic pack is DSAP Sampling and Aliasing. Uploaded PDFs can also generate a live source-bounded module.
- Generated lesson content is validated against server-owned source anchor IDs. Fixture output is test-only and is never silently substituted for a live provider.

## Run locally

### 1. Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item ..\.env.example .env
# Set FIREWORKS_API_KEY in backend\.env; do not commit it.
python manage.py migrate
python manage.py runserver 127.0.0.1:8000 --noreload
```

### 2. Frontend

```powershell
cd frontend
npm install
$env:NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000/api/v1"
npm run dev -- --hostname 127.0.0.1
```

Open `http://localhost:3000/study/new`.

## Verification commands

```powershell
# backend
cd backend
python manage.py check
python -m pytest -q
python -m compileall -q teachback

# frontend
cd frontend
npm test
npm run typecheck
npm run build
```

For a real smoke test, upload a PDF in `/study/new`, select **Qwen3 P7 Plus / Fireworks**, build a module, reveal its whiteboard actions, complete a checkpoint, and use the module copilot.

## Important safety and product boundaries

- Never commit `backend/.env`, `frontend/.env.local`, databases, raw uploads, or API keys.
- Uploads become reviewable candidate spans; they are not automatically authoritative instructional evidence.
- The first live manifest deliberately requires only four core scenes:
  `whiteboard → predict_checkpoint → retrieval → teach_back`.
  Visualizations and exam practice are optional extensions, so a valid learning loop never fails because the model omitted them.
- The product records concept-specific evidence and preferences. It must not infer fixed learning styles, IQ, personality, disability, or broad learner capability.

## Known limitations / best next work

1. **Persist generated study plans on the server.** The workspace currently stores the active module in browser local storage, so a different browser profile cannot reopen it.
2. **Make visuals genuinely on-demand.** The copilot can open an existing renderable visual, but it does not yet generate a new visualization after a learner asks for one.
3. **Finish non-PDF authoring ingestion.** PDF extraction works. Image OCR, audio transcription, video segmentation, and instructor approval tooling remain explicit future pipeline stages.
4. **Add production deployment settings.** SQLite is local-only; use PostgreSQL, object storage, CORS/host configuration, and authenticated source review for deployment.
5. **Run richer browser QA.** Add Playwright/axe checks for the complete uploaded-PDF flow, mobile, keyboard, and retry states.

## Useful files

- `README.md` — product overview and repository layout.
- `docs/runbook.md` — environment setup, provider behavior, and validation.
- `docs/CONTRACT.md` and `contracts/` — source, manifest, and dynamic-subject contracts.
- `docs/INGESTION_PIPELINE.md` — authoring-time media pipeline and review boundary.
- `frontend/src/components/StudyIntake.tsx` — live module setup.
- `frontend/src/components/StudyWorkspace.tsx` — learner workspace and module copilot.
- `backend/teachback/providers.py` — Fireworks/OpenAI provider boundary and structured output validation.
- `backend/teachback/study_plan_views.py` — study-plan, interaction, and chat API behavior.

## Current validation snapshot

- Backend suite: **51 passing tests** after the compact live-manifest update.
- Live Fireworks smoke test: an uploaded Chapter 7 DFT PDF produced a valid four-scene module in about 17 seconds.
- Browser route check: `/study/new` and `/study/workspace` load without console errors in a clean browser session.

If the live provider fails, keep the provider failure visible. Do not replace it with a fixture response or claim that a live model generated the module.
