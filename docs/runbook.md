# Feynman AI local runbook

## Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py check
python -m pytest -q
python manage.py runserver 127.0.0.1:8000
```

The checked-in local development environment uses `backend/.env`:

```text
LLM_PROVIDER=fireworks
OPENAI_MODEL=gpt-5.6
OPENAI_API_KEY=
FIREWORKS_API_KEY=your-fireworks-key
FIREWORKS_MODEL=accounts/fireworks/models/qwen3p7-plus
FIREWORKS_BASE_URL=https://api.fireworks.ai/inference/v1
```

The default local provider is Fireworks when `FIREWORKS_API_KEY` is configured. The learner UI exposes Fireworks and OpenAI only; the deterministic fixture is retained for backend tests and never silently replaces a live response.

## Frontend

In a second terminal:

```powershell
cd frontend
npm install
$env:NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000/api/v1"
npm run dev
```

Open `http://localhost:3000/study/new` for the current flow. Name a subject, upload a PDF/image/video/audio or add a URL, select a chapter or the full source collection, choose a learning method, and open the minimalist study desk. The module is generated from the selected source candidates; the learner loop is model-authored whiteboard actions -> prediction/retrieval/teach-back -> exam bridge. A 2D/3D scene is optional and can be opened later through the contextual module copilot when the generated manifest contains a renderable configuration.

The study desk includes a source-bounded module copilot at `POST /api/v1/study-plans/chat`. It can answer a question from server-owned source spans and return only typed controls such as next/previous scene, focus checkpoint, repeat explanation, change learning mode, or show an available visualization. It cannot execute browser code, accept source text, or create evidence quotes.

Uploads are sent to `POST /api/v1/study-sources/ingest`. PDF text is returned as page-located candidate spans; non-PDF media is retained with an explicit extraction/review state until its authoring pipeline is implemented. Every upload remains `awaiting_approval`, `autoApproved: false`, and `publishable: false`. `POST /api/v1/study-plans` asks the selected live provider for a typed module and rejects partial, malformed, or unapproved output.

The DSAP source pack is intentionally marked `instructor_review_required` in `contracts/v2/source-pack.json`. Until an instructor changes that approval state to `approved`, explanation checkpoints fail closed with `source_pack_not_approved`; this keeps unreviewed text from becoming evidence.

## Live OpenAI provider

Only enable this after a valid server-side key is available:

```powershell
$env:LLM_PROVIDER = "openai"
$env:OPENAI_MODEL = "gpt-5.6"
$env:OPENAI_API_KEY = "..."
python manage.py runserver 127.0.0.1:8000
```

Never put `OPENAI_API_KEY` in `frontend/.env.local` or browser code. If the provider is unavailable, the backend must fail closed as `human_review` rather than silently claiming a live result.

## Verification

- Backend: `python manage.py check` and `python -m pytest -q`
- Frontend: `npm run typecheck`, `npm run test`, `npm run build`
- Cold run: fresh browser, upload a source, build a live module, reveal generated actions, submit a checkpoint response, and verify the provider badge, source anchors, and review banner.
