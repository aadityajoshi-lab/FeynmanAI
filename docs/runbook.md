# Feynman AI local runbook

Feynman's default local experience is Goal Mode: start with a capability, confirm a learning contract, complete one active task, and record observable evidence. The Source Desk and legacy dynamic-study routes remain available, but they are secondary to the goal workflow.

## Prerequisites

- Python with `venv` support
- Node.js and npm
- A free local port `8000` for Django and `3000` for Next.js

In PowerShell, use `npm.cmd` if an execution policy blocks `npm.ps1`.

## Backend setup

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py check
python manage.py runserver 127.0.0.1:8000 --noreload
```

`backend/.env` is local-only. Do not commit it. Configure the browser origins explicitly; they must exactly match the origin used to open the frontend:

```text
DJANGO_DEBUG=true
DJANGO_SECRET_KEY=feynman-dev-only-secret
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
DJANGO_CORS_ALLOWED_ORIGINS=http://127.0.0.1:3000,http://localhost:3000
DJANGO_CSRF_TRUSTED_ORIGINS=http://127.0.0.1:3000,http://localhost:3000
```

Do not use an arbitrary-origin CORS policy. The frontend bootstraps the Django CSRF cookie through `GET /api/v1/auth/csrf`, then sends browser credentials and `X-CSRFToken` on authenticated mutating requests. Keep both the CORS and CSRF origin allowlists synchronized with the deployed frontend URL.

## Frontend setup

In a second terminal:

```powershell
cd frontend
npm.cmd install
Copy-Item .env.example .env.local
$env:NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000/api/v1"
npm.cmd run dev -- --hostname 127.0.0.1
```

The durable configuration belongs in `frontend/.env.local`:

```text
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000/api/v1
```

Restart the Next.js process after changing `NEXT_PUBLIC_API_BASE_URL`; `NEXT_PUBLIC_*` values are compiled into the browser bundle. Do not run `npm.cmd run build` concurrently with `npm.cmd run dev`: both use `frontend/.next`, so restart the dev server after a production build before doing browser checks. Open `http://127.0.0.1:3000/` for the primary workflow. `http://localhost:3000/` also works when it remains present in the backend CORS and CSRF allowlists.

## Goal Mode browser smoke test

Use a fresh local test account or a clearly named disposable account. This flow is the acceptance check for the default experience.

1. Open `/` and enter a concrete capability, such as “Trace an operating-system scheduler.” Add starting point, time shape, and outcome only if useful.
2. Select **Build my learning contract**. If unsigned in, create an account or sign in on `/onboarding`; confirm that the pending goal survives the detour.
3. On `/goals/new`, review the visible contract and select **Confirm and begin**. Confirm that a goal overview is created and one next action is visible.
4. Open `/goals/<goalId>/learn`. Complete the single active task with an actual prediction, explanation, derivation, debug result, simulation, application, build result, or transfer attempt, then select **Submit evidence**.
5. Confirm the Evidence Rail updates and that the same record appears on `/evidence`. It should be an observed record unless it meets the required source-supported verification conditions.
6. In the Source Dock, select **Add context**. This opens the universal Source Desk at `/sources?goal=<goalId>`. Create a source-bounded notebook and add a small PDF or pasted-text source; wait for its extraction state to become ready.
7. Refresh the Source Desk and confirm the notebook/source remains present. Ask a question using only the selected ready source and confirm the response displays source/page anchors. Do not treat the answer itself as evidence.
8. Return to the goal workspace and confirm that unselected or deleted sources are not used for a grounded answer or generated output.
9. On `/evidence`, select one or more evidence records and choose an enrolled test course. Select **Share** and confirm the course receives only the selected records.
10. In a separate browser profile signed in as that course's instructor, open the cohort view and confirm the shared record is visible while private notebooks and raw chats are absent.
11. Back in the learner profile, open `/settings/privacy` and select **Revoke access** for the share. Refresh the instructor cohort view and confirm the record disappears immediately.
12. Repeat the workspace check at a narrow viewport. Source and Evidence controls must remain reachable through the responsive pane controls.

Steps 9–11 require a pre-provisioned institution workspace, an instructor, a course, and an enrolled learner. This is intentional: the API refuses a share unless the learner is enrolled, and an instructor sees only evidence covered by an active share. Use a separate disposable instructor account for this check.

## Automated verification

Run these from a clean terminal after migrations and dependency installation:

```powershell
# backend
cd backend
python manage.py check
python manage.py makemigrations --check --dry-run
python -m pytest -q

# frontend
cd frontend
npm.cmd run typecheck
npm.cmd test
npm.cmd run build
```

The backend suite covers goals, evidence, sharing/revocation, source scoping/deletion, notebook compatibility, and CORS behavior. The frontend suite covers API contracts, CSRF request headers, service-unavailable behavior, source selection, and evidence submission.

## Provider configuration

Provider credentials are server-only. Goal creation, contracts, routes, and evidence records do not require a browser-visible provider key.

The dynamic-module builder uses OpenAI when configured:

```text
LLM_PROVIDER=openai
LLM_PROVIDER=openai
OPENAI_API_KEY=your-openai-api-key
OPENAI_MODEL=gpt-5.6-terra-high
OPENAI_BASE_URL=
```

Optional source OCR can be configured with `MISTRAL_API_KEY`; without it, the local extraction path is used where supported. Never place OpenAI, OpenAI, Mistral, narration, or other provider keys in `frontend/.env.local` or browser code. A failed live provider call must remain a visible provider failure; the deterministic fixture is retained for automated tests and must not silently replace a failed live result.

## Secondary legacy study paths

These routes are kept for notebook compatibility and dynamic-module experiments. They are not the primary entry point.

- `/sources` is the current Source Desk route. It may be opened with `?goal=<goalId>` to create source context alongside a goal, or independently for a notebook. `/study/new` redirects to it for compatibility.
- `/study/workspace` and `/subjects` are legacy dynamic-module learning routes.
- `POST /api/v1/study-sources/ingest` performs bounded legacy-source ingestion.
- `POST /api/v1/study-plans` generates a legacy source-bounded module through the configured live provider.

The legacy source flow keeps source candidates reviewable. PDF extraction provides page-located candidate spans; non-PDF authoring stages may remain in an explicit extraction/review state. Do not represent unapproved or provider-generated content as verified learner evidence.
