# Feynman AI

Feynman AI is a dynamic, source-bounded learning engine. Learners choose a subject and a learning method, interact with a whiteboard concept model, make a prediction, explain what they understand, and receive an evidence-backed next step. The first complete content pack is Digital Signal Analysis and Processing (DSAP), starting with Sampling and Aliasing.

## Repository layout

- `frontend/` — Next.js App Router client
- `backend/` — Django REST API and provider boundary
- `contracts/` — versioned JSON contracts, source pack, and frozen evaluation cases
- `docs/` — architecture, source provenance, and runbook

## Development status

The module builder uses the server-side Fireworks provider (`accounts/fireworks/models/qwen3p7-plus`) when configured. OpenAI remains available as a second live provider; the deterministic fixture is retained only for backend tests and is not offered in the learner flow. Provider failures remain visible; generated source content is never silently replaced by fixture output.

Local environment files are present at `backend/.env` and `frontend/.env.local`; copy `.env.example` when creating a fresh checkout. See [`docs/runbook.md`](docs/runbook.md) for startup and verification commands.

The local demo is available at:

- `http://localhost:3000/subjects`
- `http://localhost:3000/study/new` - upload material, choose chapter 1 or all, and choose a learning method
- `http://localhost:3000/study/workspace` - minimalist whiteboard, 2D/3D signal view, checkpoint, teach-back, and exam bridge
- `http://127.0.0.1:8000/api/v1/subjects`
- `POST http://127.0.0.1:8000/api/v1/study-sources/ingest` - bounded PDF/image/video candidate ingestion
- `POST http://127.0.0.1:8000/api/v1/study-plans` - fixture or live-provider study manifest generation
