# Final Browser Acceptance Report — 2026-07-21

## 1. Scope and decision

This is the final hardening pass for the local OpenX/Feynman build. It combines fresh browser evidence with the repository checks below. The authorized QA account was used only inside the isolated in-app browser; no credential is recorded here.

Decision: **PASS WITH LIMITATIONS**.

The critical learner path, live Qwen generation, source extraction, source-grounded chat, evidence verification, artifact generation, auth boundaries, and responsive routes all produced fresh evidence. This is not a claim of a full production acceptance: local PDF file selection was not possible through this isolated browser, destructive source deletion was intentionally not completed, and the optional OpenAI key/Codex bridge were not exercised.

## 2. Implementation changes covered by this pass

- Qwen is now the default provider (LLM_PROVIDER=qwen) through the configured Fireworks-compatible transport. The model is accounts/fireworks/models/qwen3p7-plus.
- OpenAI remains an explicit optional provider; it is not silently substituted when the OpenAI key is absent.
- Provider health/configuration exposes Qwen, Fireworks legacy, OpenAI, Mistral, and fixture fallback without returning credentials.
- SQLite busy-timeout/WAL and auth provisioning retry hardening were retained and regression-tested.
- URL source ingestion now has an explicit fetchWebsite contract. The webpage extractor validates public URLs, blocks private/loopback targets, bounds response/image sizes, extracts readable text/metadata/tables/images, and stores bounded notebook assets with stable anchors.
- arXiv /abs/... references are normalized to the PDF export path for extraction.
- Notebook source metrics expose pages, blocks, visuals, and selected anchors. Generated slide imagery uses the Next image component with unoptimized for source-backed assets.
- The learning UI now preserves source scope, shows provider provenance, handles remediation/retry, and records evidence separately from generated answers.
- React hook/image lint issues found during hardening were fixed; the final production build emitted no lint warnings.

## 3. Runtime and provider configuration

Services were launched locally with:

- Backend: python manage.py runserver 127.0.0.1:8000
- Frontend: npm.cmd run dev -- --hostname 127.0.0.1

Fresh browser request to http://127.0.0.1:8000/api/v1/providers returned HTTP 200. The response reported:

- default provider: qwen
- Qwen model: qwen3p7-plus
- Qwen transport: Fireworks-compatible
- Fireworks key configured: true
- OpenAI key configured: false
- Mistral key configured: true

No secret values appeared in the provider response.

## 4. Automated verification

All final checks passed:

- python manage.py check — 0 issues.
- python manage.py makemigrations --check --dry-run — no changes detected.
- python -m compileall -q teachback — passed.
- python -m pytest -q — 151 passed, one environment dependency warning.
- npm.cmd test — 58 passed in 11 files.
- npm.cmd run typecheck — passed.
- npm.cmd run build — passed; Next.js 14.2.20 production build completed with no lint warnings.
- git diff --check — passed; only normal LF/CRLF normalization warnings were emitted.

The requests character-detection warning and the pytest-asyncio loop-scope deprecation warning are environment/configuration warnings, not test failures.

## 5. Browser routes and viewports

Fresh desktop route sweep covered /, /onboarding (redirected to /login), /home, /goals/new, /evidence, /sources, /courses, /settings/privacy, a notebook route, a goal learning route, and an invalid route. The invalid route rendered the intentional Next 404 rather than a blank page.

Fresh auth/mobile coverage included /login, /signup, /sources, /goals/new, /evidence, /settings/privacy, and the authenticated goal/notebook routes.

Viewport evidence:

- Normal desktop browser viewport (route sweep captured at approximately 1265–1280 CSS px wide).
- Mobile: explicit 390x844 override; public route sweep showed no horizontal overflow.
- Tablet: explicit 1024x768 override; authenticated notebook source desk rendered with its source and tool panels.
- The temporary viewport overrides were reset before finishing.

## 6. Authentication and session boundaries

- The login form rendered stable email/password controls and accepted the authorized QA account.
- Successful sign-in reached /home, showed the learner navigation, and survived a browser reload.
- Sign-out was exercised earlier in the same isolated profile; unauthenticated /home rendered a clear “Sign in to continue” boundary with Retry and Sign in actions instead of a blank/error page.
- Signup validation reached the Clerk boundary and surfaced an email-taken validation state.
- After sign-in, protected goal, source, notebook, evidence, and privacy routes all rendered.

## 7. Goal creation and learning loop

Fresh goal route ID: e6f41f3a-02be-49b7-82a6-99ef0cf6e910.

The browser flow:

1. Started a goal for “Understand operating-system scheduling”.
2. Selected the “Operating systems” category.
3. Reached the learner-editable contract review screen.
4. Confirmed the contract and generated an eight-task route.
5. Opened the active practice guide with an interactive round-robin scheduler trace and an accessible process-completion table.
6. Submitted a short attempt. The system recorded the observable attempt and moved to a remediation task rather than treating the short answer as mastery.
7. Submitted a longer structured attempt. With no citation anchor selected, the server returned explicit “Feedback needs selected source context”.
8. Selected a durable source anchor and resubmitted. Qwen feedback first rejected the mismatched HTML source and explained the mismatch; the retry action was then exercised.
9. Retry feedback returned verified provider feedback: the trace accurately described ready/running transitions and the responsiveness/context-switch trade-off. The evidence rail showed 2 verified, 4 observable attempts, provider qwen, model accounts/fireworks/models/qwen3p7-plus, 1 source anchor, and next action advance.

This is fresh proof of the intended prediction → attempt → remediation → source verification → retry loop.

## 8. Source Desk flow

Fresh notebook ID: b7e3afb1-b002-42f5-9c44-e252586a2c2d.

- Created a notebook through the real Source Desk form attached to the new goal.
- Added a normal public webpage containing tables: W3C tables tutorial.
- Added an arXiv reference: https://arxiv.org/abs/1706.03762.
- Both sources became ready and selectable. The notebook showed 2 of 2 sources active.
- The source panel exposed page/block counts and durable page/image anchors.
- Source-scoped chat was exercised with one source selected. The answer was source-grounded and carried the page anchor 704e7bd5dc51:p1.
- Deselecting the only source changed the desk to 0 of 1 sources active, removed the proof task, and disabled source tools. Reselecting restored the task. This confirms source scope is enforced.
- Clicking Remove opened the explicit “Remove source?” confirmation. Cancel was selected; the source was not destructively deleted.

## 9. Web, arXiv, PDF, and visual extraction

Observed notebook extraction metrics:

- W3C webpage: 1 pages / 6 blocks / 5 visuals.
- arXiv paper: 15 pages / 156 blocks / 6 visuals.

The notebook exposed visual anchors such as 704e7bd5dc51:web:img1 through web:img5 and the arXiv page/block anchors. The extracted webpage answer cited a durable page anchor rather than returning an unscoped response.

The public URL path exercised the bounded web extractor, metadata/table/image handling, and notebook asset persistence. Local PDF selection was not completed because the isolated in-app browser did not expose a usable file chooser; this remains a limitation rather than an unverified success claim.

## 10. Qwen, Fireworks, OpenAI, and Codex status

The live browser route generated a curriculum, source answer, artifact outputs, evidence evaluation, and retry feedback through Qwen via the configured Fireworks-compatible transport. UI status explicitly reported qwen · accounts/fireworks/models/qwen3p7-plus.

The OpenAI provider is implemented as an optional first-party Responses API adapter, but the current local environment has no OpenAI key configured and it was not called. There is no Codex desktop-authentication bridge in the repository provider path; the code explicitly keeps Codex authentication separate. This pass therefore verifies Qwen/Fireworks live behavior, not OpenAI/Codex live behavior.

## 11. Provider failure, malformed, and retry behavior

- Missing source context produced a visible server-side evaluation state with no fabricated provider feedback.
- A mismatched source produced an explicit mismatch explanation and uncertainty state.
- The visible Retry feedback action was clicked and returned a successful verified response with advance.
- Backend provider/error-path tests are included in the 151-test pass.

## 12. Artifact generation

On the real notebook, each source tool was activated and returned a saved output:

- Study guide
- Quiz
- Slide deck
- Flashcards
- Formula sheet
- Source table
- Mind map
- Narrated lesson

The Notebook notes tool was also exercised. A cited note titled “Tables accessibility takeaway” was saved successfully; the notebook then reported Notes 1. The artifact inventory and the generated output UI were inspected after the requests.

## 13. Source scoping, stale behavior, and deletion boundary

Source selection is explicit and visible in both the notebook and goal Source Dock. Deselecting all sources removes the proof task and disables source tools. Selecting a page anchor adds 1 anchor included with the attempt, and the provider response reports the anchor count.

The removal confirmation dialog was tested and cancelled. Final source deletion was not performed without an explicit destructive-action confirmation, so deletion persistence remains unverified.

## 14. Tables, diagrams, and media

- The learning route rendered a semantic scheduler table with caption, column headers, row headers, and completion cells.
- The webpage notebook exposed extracted visuals and stable image anchors.
- Slide deck, source table, mind map, narrated lesson, formula sheet, and other artifact cards were generated and saved.
- The notebook source desk displayed page/block/visual metrics rather than raw HTML or unbounded remote image URLs.

## 15. Responsive acceptance

The public mobile sweep at 390x844 reported no horizontal overflow on the tested routes. Authenticated mobile screenshots were captured for the goal learning route and notebook source desk. A 1024x768 tablet screenshot showed the authenticated source desk with its panels and tools.

Representative responsive evidence:

- E:/newOpenAI/openX-hackathon/outputs/final-qa-goal-mobile-authenticated.png
- E:/newOpenAI/openX-hackathon/outputs/final-qa-source-mobile-authenticated.png
- E:/newOpenAI/openX-hackathon/outputs/final-qa-source-tablet-1024.png

## 16. Console and network observations

Application console errors were zero after filtering known third-party noise on the authenticated home/goal routes. Observed non-application noise:

- Statsig requests from the Codex harness frequently reported nodeRepl.fetch response is too large.
- Clerk emitted a development-key warning.
- Cloudflare Turnstile emitted a third-party console message during auth.

These did not prevent the tested application flows. No application request exposed credentials in the browser UI or provider response.

## 17. Screenshot evidence

Fresh representative screenshots:

- [Landing desktop](/E:/newOpenAI/openX-hackathon/outputs/final-qa-landing-desktop.png)
- [Authenticated home](/E:/newOpenAI/openX-hackathon/outputs/final-qa-home-authenticated.png)
- [Goal contract review](/E:/newOpenAI/openX-hackathon/outputs/final-qa-goal-review.png)
- [Generated goal overview](/E:/newOpenAI/openX-hackathon/outputs/final-qa-goal-overview.png)
- [Initial learning workspace](/E:/newOpenAI/openX-hackathon/outputs/final-qa-learning-initial.png)
- [Remediation state](/E:/newOpenAI/openX-hackathon/outputs/final-qa-learning-remediation.png)
- [Successful Qwen feedback](/E:/newOpenAI/openX-hackathon/outputs/final-qa-qwen-feedback-success.png)
- [Webpage notebook](/E:/newOpenAI/openX-hackathon/outputs/final-qa-webpage-notebook.png)
- [Generated artifact output](/E:/newOpenAI/openX-hackathon/outputs/final-qa-artifact-output.png)
- [Authenticated mobile goal](/E:/newOpenAI/openX-hackathon/outputs/final-qa-goal-mobile-authenticated.png)
- [Authenticated mobile source desk](/E:/newOpenAI/openX-hackathon/outputs/final-qa-source-mobile-authenticated.png)
- [Tablet source desk](/E:/newOpenAI/openX-hackathon/outputs/final-qa-source-tablet-1024.png)

The complete route-sweep screenshots remain in E:/newOpenAI/openX-hackathon/outputs/ with the final-qa-route- prefix.

## 18. Remaining issues by priority

### P0

None found in the exercised local critical path.

### P1

- Local PDF upload still needs a real file-chooser/browser test.
- Final source deletion persistence is intentionally unverified because the destructive confirmation was cancelled.
- OpenAI live-provider acceptance remains pending until an OpenAI key is supplied.

### P2

- Replace or configure the environment-level requests character-detection and pytest-asyncio warnings.
- Reduce third-party Statsig/Turnstile console noise in the QA harness where possible.
- Add a browser-level assertion for each individual artifact’s rendered body, not only its saved-output inventory.

## 19. Final handoff

The local application is ready for the next integration step with the supplied Qwen/Fireworks configuration. The final automated checks pass, and fresh browser evidence covers the core authenticated learning, source, provider, artifact, evidence, and responsive workflows. The correct release label for this run is PASS WITH LIMITATIONS, with the P1 items above carried forward before claiming full production acceptance.
