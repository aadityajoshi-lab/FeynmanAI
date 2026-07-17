# Feynman AI contract freeze (legacy teach-back API)

The source-driven module builder uses the versioned manifest in
`contracts/v3/study-manifest.schema.json` and the dynamic routes documented in
`docs/DYNAMIC_SUBJECTS.md`. The photosynthesis teach-back endpoints below remain
only for regression tests and are not part of the learner module flow.

The contextual module copilot uses `contracts/v3/study-chat.schema.json` at
`POST /api/v1/study-plans/chat`. Visualization scenes are optional in a study
manifest; the copilot may open one only when the server-validated manifest
contains a renderable configuration.

This is the shared contract for the one-lesson Teach-Back Lab. The versioned
JSON Schemas and fixtures in `contracts/v1/` are the source of truth for the
Django API, frontend API client, and evaluation runner.

## Invariants

1. The server owns the source pack and canonical quotes. The browser sends
   lesson IDs, claim IDs, learner text, questions, and repairs; it never sends
   source anchors or authoritative source text.
2. A supported, misconception, or needs-precision claim must have at least one
   source anchor. A clarification answer must also have an approved anchor.
3. A clarification is read-only: it cannot mutate the claim verdict, probe,
   misconception type, or source anchors.
4. A revision changes only the selected claim and appends a revision record.
   `recordVersion` is incremented on each successful revision.
5. A stale `expectedVersion` returns HTTP 409. Invalid payloads return HTTP
   422. Invalid provider output is represented as `needs_human_review` and is
   never rendered as a verified answer.
6. `providerMode` is always visible: `codex_fixture`, `live_openai`, or
   `human_review`. Fixture output must not be described as live model output.

## Endpoint map

| Method | Path | Contract |
| --- | --- | --- |
| GET | `/api/v1/lessons/photosynthesis` | `lesson.schema.json` |
| POST | `/api/v1/sessions` | `create-session.schema.json` |
| POST | `/api/v1/sessions/{id}/audit` | `audit-request.schema.json` → `evidence-record.schema.json` |
| GET | `/api/v1/sessions/{id}/record` | `evidence-record.schema.json` |
| POST | `/api/v1/sessions/{id}/claims/{claimId}/clarifications` | clarification request/result schemas |
| POST | `/api/v1/sessions/{id}/claims/{claimId}/revisions` | revision request/result schemas |
| GET | `/api/v1/sessions/{id}/inspection` | read-only inspection object |

## Versioning

The public API is prefixed with `/api/v1`. Schema references are relative to
`contracts/v1/`. Changes to required fields, enum values, source IDs, or
record-version semantics require a new contract version and an orchestrator
review before agents edit against it.

## Validation commands

From the repository root, parse every JSON artifact before running services:

```powershell
Get-ChildItem contracts -Recurse -Filter *.json | ForEach-Object {
  Get-Content $_.FullName -Raw | ConvertFrom-Json | Out-Null
}
```

The backend must additionally validate fixtures against the schemas in its
pytest contract suite.
