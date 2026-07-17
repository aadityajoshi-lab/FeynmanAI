# Fireworks module-building workflow

The local module builder supports three explicit provider choices:

- `fireworks`: `accounts/fireworks/models/qwen3p7-plus` through the Fireworks OpenAI-compatible endpoint;
- `openai`: the server-side OpenAI provider when `OPENAI_API_KEY` is configured;
- `fixture`: offline deterministic output for tests only.

The browser never receives a provider key. The setup screen calls `GET /api/v1/providers`, then sends the chosen provider with `POST /api/v1/study-plans`.

## Local environment

Set these values in `backend/.env`:

```text
LLM_PROVIDER=fireworks
FIREWORKS_API_KEY=your-key
FIREWORKS_MODEL=accounts/fireworks/models/qwen3p7-plus
FIREWORKS_BASE_URL=https://api.fireworks.ai/inference/v1
OPENAI_API_KEY=
```

Restart Django after changing the file. The UI labels a provider as configured; the first module build is the real credential check. A provider error is shown to the learner and is never replaced by fixture output.

## Source-to-module flow

```text
PDF/image/audio/video/URL
→ validate MIME, size, checksum, and URL scheme
→ persist reviewable source metadata and candidate spans
→ run concurrent uploads from the browser
→ POST study plan with source IDs and provider choice
→ Fireworks returns typed outline/scenes JSON
→ Django rejects unknown source anchors or action types
→ study desk shows the generated outline and review status
```

PDF pages currently extract text with `pypdf`. Image OCR, audio transcription, video transcription, and URL fetching are represented as explicit pending pipeline states; they do not become evidence automatically.

## Direct smoke test

```powershell
$upload = curl.exe -sS -F "file=@inputs/Chapter 7- Discrete Fourier transform.pdf" -F "subjectId=dsap" -F "moduleId=chapter-7" http://127.0.0.1:8000/api/v1/study-sources/ingest | ConvertFrom-Json

curl.exe -sS -X POST http://127.0.0.1:8000/api/v1/study-plans `
  -H "Content-Type: application/json" `
  -d (@{ subjectId="dsap"; subjectTitle="Digital Signal Analysis and Processing"; moduleId="chapter-7"; sourceIds=@($upload.sourceId); chapterSelection="chapter_1"; provider="fireworks" } | ConvertTo-Json)
```

The returned manifest is a draft while `approvalStatus=instructor_review_required`. It may be inspected and edited, but it is not silently promoted to authoritative evidence.

For a repeatable end-to-end check that prints extraction counts, generated concept titles, scene types, and anchor validation, run:

```powershell
python scripts/verify_pdf_module.py
```
