# Feynman Learning OS browser QA and hardening report

**Date:** 2026-07-21
**Repository:** `E:\newOpenAI\openX-hackathon`
**Browser:** Codex in-app browser, isolated tabs only; the original user tab was left unchanged.
**Overall decision:** **Pass for the exercised learner/source/safety flows; not a claim of full matrix acceptance.** The remaining limitations are listed below.

## Browser evidence

- The live learner session rendered the existing History workspace plus newly created Transformer, ML, Operating Systems, Computer Graphics, Medical, Finance, and unseen-earthquake goals.
- Transformer goal `5d2e6710-6596-43e2-9c77-1779c434d6af`; notebook `9366c7bf-0121-4643-8b0c-9bb8c78631ad`.
- Medical goal `aca45f96-88da-4694-8a54-2132a77d1c48`; notebook `e81eb797-8a41-4c69-b059-4e2a843ae018`.
- Medical source `Renal physiology academic case` was created through the browser Paste notes flow, selected, cited at `ee5513dc00be:p1`, deselected (proof and tools correctly became unavailable), then reselected.
- Personal clinical request was blocked in the notebook chat with an educational-boundary message and was not saved as learner evidence.
- Academic renal physiology question was answered from the selected source with the page anchor `ee5513dc00be:p1` and an honest statement of source limits.
- Medical proof submission advanced from `predict · difficulty 1` to `explain · difficulty 2`; refresh preserved that route position.
- ML goal `0a4e4417-5224-4d05-9136-2ed87a0cb47f`: the `Error-analysis lab` exposed dataset-split, slice, error-filter, threshold, confusion-matrix, and metric state. Selecting a leaky split surfaced an explicit warning; structured attempts advanced the route while provider-unavailable feedback stayed unverified. The category-aware contract now displays `Machine learning / AI`.
- Operating-systems goal `09d4c67b-076f-450b-a35e-e2675e37c33c`: the scheduler lab switched FCFS to round-robin, used the accessible `Increase Round-robin time quantum` control to change the quantum to 3 ticks, reset the trace, and recorded the trade-off checkpoint before an observable scheduling explanation advanced the route to `TASK 03 / 08`.
- Graphics goal `4131aa24-8fb2-4b8e-9ca4-9af433cdc390`: the transform/camera lab rendered object translation, rotation, scale, and camera zoom controls; the accessible `Increase Object translation, x` control changed the value to 25, recorded a viewpoint checkpoint, and persisted an observable explanation.
- Finance goal `0c59abb3-3093-416a-b91d-025112c5f6b5`: source notes were attached through the browser, an academic order-type question returned a citation (`dd82c51563a3:p1`), a personal buy/sell question returned an explicit educational boundary, and a case-analysis proof recorded educational reasoning without personal trading advice.
- Unseen-earthquake goal `bfb85751-3375-402a-8bb1-54df65b352d2`: the compiler produced exactly four generic tasks (`predict`, `explain`, `apply`, `transfer`) rather than inventing a specialized adapter. A weak/no-source attempt became observed but not verified, the next action became retry with source context, and refresh preserved `TASK 02 / 04` plus two attempts.
- Transformer flow covered weak evidence, remediation, strong structured evidence, adaptive transfer, source-scoped chat, study guide, quiz, flashcards, slides, source table, provider failure/retry states, and note create/edit/delete.
- The isolated continuation created a real arXiv URL reference (`https://arxiv.org/abs/1706.03762`) through the Source Desk. The resulting source-bound study guide visibly disclosed that URL references are retained without web fetching and require notes or excerpts before grounded claims; no unsupported paper content was presented as fact. Source selection was toggled off and back on, disabling and re-enabling source tools as expected.
- The Source Desk now supports appending text/URL context to an existing notebook through `/sources?notebook=...`. In the isolated disposable notebook, a second excerpt source was added and persisted; source A was deselected, source-B-only chat returned citation `4e344b55f8f4:p1`, then source B was deselected and source-A-only chat returned the metadata-bound citation `55f04bcb271b:p1`. Neither answer cited the unselected source.
- After the final production build and dev-cache restart, `/sources?notebook=00000000-0000-0000-0000-000000000000` rendered an explicit `Notebook unavailable` alert with `Back to Source Desk`; it did not expose the source form or create a replacement notebook. The valid disposable notebook query still rendered `Add another source.` and the existing notebook title.
- The isolated tab was reloaded while Django was intentionally stopped: `/home` moved from a clear loading state to `Learning service unavailable` with a Retry action. After Django was restored, clicking Retry returned to the persisted home workspace. Screenshot: `outputs/qa-backend-unavailable.png`; recovery screenshot: `outputs/qa-backend-restored.png`.
- The institution member UI created a disposable learner invitation in-browser. Opening the resulting join page rendered the invited role, email-bound privacy copy, and `Accept invitation`; attempting acceptance with the currently signed-in account correctly produced `This invitation needs attention` because the emails did not match. The tab was returned to `/home` without exposing the invitation token. Screenshots: `outputs/qa-invitation-join.png` and `outputs/qa-invitation-accepted.png`.
- The goal overview `Share route` control was exercised in-browser and displayed `Template link copied. It includes the route and source metadata, never private evidence.` The new visible fallback rendered a read-only share URL and `Open shared route`; the valid shared-goal preview opened with `FRESH LEARNER COPY`, eight observable tasks, and the explicit private-memory boundary. `Start this guide` cloned a fresh goal with zero evidence and the full route, proving shared material does not carry learner state. Screenshots: `outputs/qa-goal-share-fallback.png`, `outputs/qa-goal-share-preview.png`, and `outputs/qa-goal-share-cloned.png`.
- At the explicit 390x844 viewport, the goal overview’s mobile More menu exposed `Share route`; the fallback rendered with one `Open shared route` link, `bodyScrollWidth=375`, `clientWidth=375`, no horizontal overflow, and zero application console errors. Screenshot: `outputs/qa-goal-share-mobile.png`. The viewport override was reset after the check.
- The disposable notebook source-delete flow opened the accessible `Remove source?` confirmation with one Cancel and one Confirm remove action. Cancel was clicked in-browser; the prompt closed, the source remained present, and the tab reported zero application errors. Screenshots: `outputs/qa-source-delete-cancel-dialog.png` and `outputs/qa-source-delete-cancelled.png`.
- A cited notebook note was created and edited in-browser; its source anchor remained attached, and the note was separate from learner evidence. The evidence timeline showed verified, observed, and needs-review records, source-anchor counts, next-action reasons, and the explicit course-sharing boundary without raw chat text.
- Privacy controls were toggled and refreshed: learner memory persisted across reload, course sharing disabled/re-enabled with the expected revocation message, and the original settings were restored. The isolated tab also rendered the safe unavailable-notebook error state with a Source Desk recovery link.
- Authentication flow was exercised in an isolated tab: valid login reached `/home`, refresh preserved the session, sign-out redirected to `/`, protected `/home` and `/goals` showed `Sign in to continue`, invalid credentials showed `Identifier is invalid`, signup required fields remained blocking, and a short/invalid signup submission stayed on the form without creating an account. The supplied valid account was restored before leaving the tab available.
- Mobile notebook screenshot at `390x844`: `bodyScrollWidth=375`, `clientWidth=375`; no horizontal overflow. The generic unseen-domain learning workspace also measured `bodyScrollWidth=375`, `clientWidth=375` at the same viewport. The final OS learning workspace and Source Desk were rechecked at the explicit `390x844` viewport with no horizontal overflow and no application console errors.
- Captured screenshots in the QA session: login/auth surface, Transformer/medical proof canvas, medical safety chat with citation, finance safety chat, ML/OS/graphics/DSP workbenches, generic unseen-domain workspace, direct OS route, and mobile OS learning view. The clean isolated tab is left on the exact post-build OS workspace for inspection.
- Persisted screenshot checkpoints: `outputs/qa-finance-safety.png`, `outputs/qa-unseen-workspace.png`, `outputs/qa-os-step-controls.png`, `outputs/qa-graphics-step-controls.png`, `outputs/qa-ml-step-controls.png`, `outputs/qa-dsp-step-controls.png`, `outputs/qa-os-direct-route.png`, and `outputs/qa-os-mobile.png`.
- Authentication screenshot: `outputs/qa-login.png`.
- Research-paper URL/study-guide screenshot: `outputs/qa-research-study-guide.png`.
- Evidence timeline screenshot: `outputs/qa-evidence.png`.
- Privacy controls screenshot: `outputs/qa-privacy.png`.
- Mobile OS and Source Desk screenshots: `outputs/qa-mobile-os-final.png` and `outputs/qa-mobile-sources.png`.
- Safe notebook error screenshot: `outputs/qa-notebook-error.png`.
- Source A/B selection and citation screenshot: `outputs/qa-source-ab-citations.png`.
- Final post-build OS workspace screenshot: `outputs/qa-final-os-postbuild.png`.
- Final post-build OS workspace screenshot: `outputs/qa-final-os-postbuild-final.png` (fresh after the dev-cache restart; `TASK 03 / 08`, `bodyScrollWidth=1265`, `clientWidth=1265`, `window.__qaErrors=[]`).
- Final post-build OS workspace screenshot: `outputs/qa-final-os-postbuild-final2.png` (fresh after the append-source production build and second dev-cache restart; `TASK 03 / 08`, `bodyScrollWidth=1554`, `clientWidth=1554`, `window.__qaErrors=[]`).
- Final post-build OS workspace screenshot: `outputs/qa-final-os-postbuild-final3.png` (fresh after the final notebook-query safety patch and cache restart; `TASK 03 / 08`, `bodyScrollWidth=1265`, `clientWidth=1265`, no application console errors).
- Source deletion confirmation screenshot: `outputs/qa-source-delete-confirmation.png`; the destructive action now opens a labelled in-app confirmation group with Cancel and Confirm remove actions.
- Invalid notebook-query recovery screenshot: `outputs/qa-source-notebook-error.png`.
- Existing-notebook append form screenshot: `outputs/qa-source-append-postbuild.png`.
- Backend-unavailable recovery screenshot: `outputs/qa-backend-unavailable.png`.
- Backend-restored Retry screenshot: `outputs/qa-backend-restored.png`.
- Invitation join screenshot: `outputs/qa-invitation-join.png`.
- Invitation email-mismatch boundary screenshot: `outputs/qa-invitation-accepted.png`.
- Goal share status screenshot: `outputs/qa-goal-share-status.png`.
- Goal share fallback screenshot: `outputs/qa-goal-share-fallback.png`.
- Valid shared-goal preview screenshot: `outputs/qa-goal-share-preview.png`.
- Fresh cloned shared-goal screenshot: `outputs/qa-goal-share-cloned.png`.
- Mobile goal-share screenshot: `outputs/qa-goal-share-mobile.png`.
- Source-delete cancel dialog screenshot: `outputs/qa-source-delete-cancel-dialog.png`.
- Source-delete cancelled/preserved screenshot: `outputs/qa-source-delete-cancelled.png`.
- Course permission screenshot: `outputs/qa-course-learner.png` and restricted institution state `outputs/qa-institution-permission.png`.
- Course command-center screenshot: `outputs/qa-course-command.png`.
- Existing published course `Evidence Systems Studio` (`db0debca-7aba-4ead-be1f-7f71ecf08e2d`) was joined in-browser with its real join code. The learner course hub rendered the route and private-by-default boundary; direct teaching access returned `You do not have access` without exposing cohort controls.
- Direct `/institution` access from the learner account now returns the explicit `You do not have access` state. `/institution/members` remains an empty admin state, and the learner navigation still contains no Teach or Institution links.
- In the same isolated local account, a labeled `Feynman QA Teaching Lab` institution workspace and `Feynman Adaptive Proof Lab` course were created through the UI. The course builder saved four stages (`Predict`, `Explain`, `Apply`, `Transfer`), published the course, reopened the command center, inspected the empty cohort state, created a disposable invitation, and reloaded to confirm the published route persisted.
- The owner view then loaded `/institution` and `/institution/insights` from the authorized institution workspace; the metrics and aggregate-insights surfaces rendered with no application errors. The insights screenshot is `outputs/qa-institution-insights.png`.

## Route matrix

| Route | Result |
| --- | --- |
| `/`, `/onboarding`, `/login`, `/signup` | Rendered; `/onboarding` correctly reaches the auth surface; no blank page |
| `/home`, `/goals`, `/goals/new`, `/goals/new?review=1` | Rendered; goal entry, category, contract review, and navigation exercised |
| `/goals/[goalId]`, `/goals/[goalId]/learn` | Exact app-generated goal URLs rendered directly and after navigation; interacted with real History, Transformer, ML, OS, Graphics, Medical, Finance, and unseen-domain goals; refresh preserved route state |
| `/sources`, `/sources?goal=...`, `/notebooks/[notebookId]` | Rendered; source creation, selection, chat, artifacts, notes, and proof exercised |
| `/sources?notebook=...`, unknown `/notebooks/[notebookId]` | URL-reference form rendered and created a clearly marked arXiv reference; valid notebook append and invalid notebook recovery rendered without silent notebook creation |
| `/evidence`, `/settings/privacy` | Rendered; evidence states, anchors, privacy boundaries inspected |
| `/teach`, `/institution`, `/institution/members`, `/institution/courses`, `/institution/insights` | Rendered safe learner/permission/empty states; owner institution workspace rendered aggregate metrics and insights; learner navigation omits Teach and Institution; direct course teaching access is denied |
| `/courses`, `/courses/[courseId]`, `/teach/courses/[courseId]` | Joined the published course hub; private course boundary rendered; direct learner teaching route denied |
| `/teach/courses/[courseId]/build`, `/teach/courses/[courseId]/learners` | Created and published a real QA course route in-browser; refresh preserved four stages; empty cohort state rendered without private data |
| `/courses`, unknown `/courses/[courseId]` | Rendered empty course state and safe unavailable state |
| Unknown `/teach/courses/[courseId]`, `/build`, `/learners` | Safe “This item is unavailable” state after dev-cache repair |
| `/join/[invite]`, `/share/goals/[token]` | A real disposable invitation rendered the join page and correctly blocked an email-mismatched acceptance; a valid goal share opened through the visible fallback, showed the private-memory boundary, and cloned a fresh zero-evidence route |
| `/study/new`, `/study/workspace` | Compatibility behavior rendered (`/study/new` redirects to Source Desk; workspace renders selected-module state) |
| `/subjects` | 404 as intended after legacy page removal |

The final post-build isolated-tab sweep rechecked **23 explicit route URLs** with no application errors or missing chunks. Earlier sweeps covered **34** and **28** URLs. The only expected 404 was the removed `/subjects` legacy route; `/onboarding` redirected to the authenticated workspace, the valid notebook rendered after its extraction state settled, the learner course hub rendered, direct teaching access was denied, and the valid OS workspace loaded at `TASK 03 / 08`.

## Feature matrix

| Feature | Result | Browser evidence / limitation |
| --- | --- | --- |
| Authentication, logout, refresh, protected routes | Pass | Login, invalid credentials, logout, refresh persistence, 401 boundary, and backend-unavailable recovery/retry exercised; OTP and expired-session paths remain untested |
| Universal goal, contract, curriculum preview, route persistence | Pass | Manual and example goals, editable contract, prerequisite/warning/source coverage, route save, refresh/reopen exercised |
| Adaptive evidence and next action | Pass | Weak, strong, remediation, transfer, difficulty, source-anchor, and observed-vs-verified states exercised across goals |
| Operating Systems, DSP, Graphics, ML, Transformer, History, unseen domain | Pass | Domain workbenches and generic predict/explain/apply/transfer fallback interacted with structured controls |
| Research-paper source flow | Pass with boundary | arXiv URL reference and source-bound study guide exercised; URL references honestly disclose that web content is not fetched |
| Medical and finance safety | Pass | Academic source-grounded answers allowed; personal diagnosis/treatment and buy/sell requests redirected; no unsafe evidence stored |
| Source Desk text/URL intake and selection | Pass | Paste notes, URL intake, append-to-existing-notebook, select/deselect gating, source-A/source-B citation filtering, citation anchors, and refresh persistence exercised |
| PDF/file upload and OCR retry | Partial | IAB does not expose a safe local file chooser; backend and UI retry paths are covered by tests and visible states |
| Source-scoped two-source citation filtering and destructive deletion | Pass with deletion boundary | Two-source A/B selection and citations, confirmation, and safe Cancel preservation were exercised in-browser; the destructive Confirm remove action was intentionally not activated without a fresh user confirmation |
| Study guide, quiz, flashcards, slides, tables, mind map, narrated lesson | Pass with provider boundary | Existing Transformer notebook generated/inspected tools and provider retry/failure states; URL-only study guide remained explicitly metadata-only |
| Notebook notes | Pass | Create/edit/delete flow was exercised in the learner notebook; continuation rechecked create/edit with source anchors |
| Evidence timeline and privacy | Pass | Timeline, anchors, next action, sharing boundary, privacy toggles, refresh persistence, and revocation messaging exercised |
| Courses, teaching, institution, role gates | Pass with account boundary | Learner denial, institution owner workspace, course builder/publish, cohort empty state, invitation creation/join, email-mismatch protection, goal-share preview/clone, and refresh persistence exercised |
| Mobile and accessibility | Pass for exercised surfaces | 390x844 OS, Source Desk, and goal-share fallback had no horizontal overflow; mobile More menu exposed Share route; labels, focusable controls, loading/error/empty states inspected |
| Provider failure and recovery | Pass | Honest unavailable/malformed output messages, backend-unavailable loading/error/retry, and provider retry controls observed; no provider failure became verified evidence |

## Defects fixed

1. **Medical contract copy mismatch (P1).** The editor displayed “Sources optional” for a manually categorized medical goal even though the backend required academic source-bound verification. Category-aware inference now shows “Source-backed required,” automatically enables source context for medical intent, and explains the educational/personal-advice boundary.
2. **Generated source artifact text corruption (P1).** Duplicate glyphs, repeated punctuation, split words, and `Ooverview`-style provider text are repaired conservatively before persistence. New quiz, study guide, slide deck, and source-table outputs were regenerated and inspected as clean. Older malformed rows remain historical saved outputs and are noted as a P2 cleanup opportunity.
3. **Literal `{concept}` in new adaptive route prompts (P1).** Activity contracts now interpolate the goal capability before persistence; regression coverage added.
4. **Note deletion browser dead-end (P2).** Native `window.confirm` was replaced with an accessible in-app confirmation group; create/edit/delete was completed in the browser.
5. **Stale Next.js development cache (P1, operational).** Running production build while `next dev` was active left missing `@clerk` vendor chunks for course/role pages. The generated `.next` directory was validated as inside the frontend workspace, moved to `.next.qa-stale-20260721-final7`, and the dev server was restarted. All affected routes then rendered normally. The backup is generated cache only and can be removed later during routine cleanup.
6. **Category label drift in contract review (P2).** Explicit `ai_ml`, `medical`, graphics, DSP, OS, and history categories now map to human-readable domain labels before review, so the contract no longer falls back to the generic `Adaptive study` label for categorized goals.
7. **Signed-in first-load hardening (P2).** The API now waits briefly for a fresh Clerk token when a signed-in marker is present, and a transient owned-goal 404 warms the goal catalog before retrying the exact detail request. This keeps direct hard-refresh requests on the same learner profile without weakening ownership checks.
8. **Protected notebook boundary (P2).** Notebook API 401/0 responses now preserve the shared API error status, so Home and other protected routes render the same sign-in/recovery boundary instead of a misleading generic workspace error.
9. **Personal workspace exposed institution metrics (P1).** The institution dashboard accepted the learner’s personal workspace because personal owners satisfy the generic organization-owner check. Institution metrics now require `workspace.kind == "institution"`; a backend regression test and an isolated browser permission-state screenshot cover the boundary.
10. **Institution insights ignored the authorized workspace (P1).** The insights page called the dashboard without a workspace identifier, so an institution owner could still be denied after the dashboard boundary was tightened. The frontend now resolves an owned institution workspace before requesting aggregate insights, with a static regression test and owner-browser screenshot.
11. **Notebook add-source isolation (P2).** The notebook Source Desk action previously always created a new notebook, preventing a learner from adding a second source to the same grounding scope. The notebook now links to `/sources?notebook=...`; text and URL intake append to that notebook, with regression coverage and browser-verified A/B source citation filtering.
12. **Invalid notebook query could create an unrelated desk (P2).** The new append flow initially fell back to `createNotebook` when a requested notebook failed to load. The Source Desk now surfaces a recoverable `Notebook unavailable` state and blocks creation when a notebook query is invalid; the behavior is covered by a static regression test and a final isolated-browser screenshot.
13. **Clipboard-only goal sharing (P2).** Goal sharing previously exposed only a copy status, leaving no usable path when clipboard permissions were unavailable. The overview now renders a read-only share URL and `Open shared route` fallback; regression coverage and valid preview/clone browser evidence were added.
14. **Goal actions disappeared on mobile (P2).** Responsive CSS hid top actions without exposing route-specific actions elsewhere. `LearningAppShell` now accepts `mobileActions`, and the goal Share route is available in the mobile More menu with responsive fallback styling and browser coverage.

## Console and provider results

- Clean isolated-tab console after the final cache repair: **0 application errors**; only the expected Clerk development-key warning. A historical missing `./510.js` error was captured during the build/dev-cache collision, then disappeared after moving the generated cache and restarting `next dev`; the fresh post-repair tab has no such error. The latest restart moved the generated cache to `.next.qa-stale-20260721-final10`.
- A direct unauthenticated `GET http://127.0.0.1:8000/api/v1/me` returned **401** with the expected authentication-required error. Authenticated isolated tabs rendered the private workspace, goals, sources, and evidence, but no bearer token or network secret was captured or printed.
- Statsig `nodeRepl.fetch response is too large` messages are Codex bridge noise from `ab.chatgpt.com`, not application console errors.
- Mind map and narrated lesson provider failures were visible, honest, retryable, and did not save invalid artifacts.
- No password, Clerk token, API key, or OTP was printed or rendered by the tested flows.
- Invalid Clerk attempts emitted third-party Cloudflare Turnstile `font-size ... NaN` messages in the auth tab; these were not application errors and the clean post-build learner tab remained at zero application errors. The controlled backend outage produced no application console errors; the UI surfaced the recovery state as designed.

## Automated validation

| Check | Result |
| --- | --- |
| `python manage.py check` | Pass — 0 issues |
| `python manage.py makemigrations --check --dry-run` | Pass — no changes |
| Backend `pytest -q` | **141 passed**, 1 environment warning |
| Frontend `npm.cmd test` | **57 passed** in 11 files |
| Frontend typecheck | Pass |
| Frontend production build | Pass; existing non-fatal Next.js lint warnings for one `<img>` and three hook dependency/cleanup cases |

## Files changed

- `backend/teachback/adaptive_runtime.py`
- `backend/teachback/notebook_media.py`
- `backend/teachback/tests/test_adaptive_runtime.py`
- `backend/teachback/tests/test_notebook_api.py`
- `frontend/src/app/globals.css`
- `frontend/src/app/learning-os.css`
- `frontend/src/components/GoalEntry.tsx`
- `frontend/src/components/GoalEntry.test.ts`
- `frontend/src/components/LearningAppShell.tsx`
- `frontend/src/components/LearningAppShell.test.ts`
- `frontend/src/components/NotebookWorkspace.tsx`
- `frontend/src/components/NotebookWorkspace.test.ts`
- `frontend/src/components/UniversalSourceDesk.tsx`
- `frontend/src/components/UniversalSourceDesk.test.ts`
- `frontend/src/components/DomainActivityWorkbench.tsx`
- `frontend/src/components/DomainActivityWorkbench.module.css`
- `frontend/src/components/DomainActivityWorkbench.test.ts`
- `frontend/src/components/LearningViews.tsx`
- `frontend/src/components/LearningViews.test.ts`
- `frontend/src/lib/learningOsApi.ts`
- `frontend/src/lib/learningOsApi.test.ts`
- `frontend/src/lib/notebookApi.ts`
- `frontend/src/lib/notebookApi.test.ts`
- `backend/teachback/learning_os_views.py`
- `backend/teachback/tests/test_learning_os_api.py`
- `outputs/qa-finance-safety.png`
- `outputs/qa-unseen-workspace.png`
- `outputs/qa-os-step-controls.png`
- `outputs/qa-graphics-step-controls.png`
- `outputs/qa-ml-step-controls.png`
- `outputs/qa-dsp-step-controls.png`
- `outputs/qa-os-direct-route.png`
- `outputs/qa-os-mobile.png`
- `outputs/qa-login.png`
- `outputs/qa-course-learner.png`
- `outputs/qa-institution-permission.png`
- `outputs/qa-course-command.png`
- `outputs/qa-institution-owner.png`
- `outputs/qa-institution-insights.png`
- `outputs/qa-research-study-guide.png`
- `outputs/qa-evidence.png`
- `outputs/qa-privacy.png`
- `outputs/qa-mobile-os-final.png`
- `outputs/qa-mobile-sources.png`
- `outputs/qa-notebook-error.png`
- `outputs/qa-final-os-postbuild.png`
- `outputs/qa-final-os-postbuild-final.png`
- `outputs/qa-final-os-postbuild-final2.png`
- `outputs/qa-final-os-postbuild-final3.png`
- `outputs/qa-source-delete-confirmation.png`
- `outputs/qa-source-ab-citations.png`
- `outputs/qa-source-notebook-error.png`
- `outputs/qa-source-append-postbuild.png`

## Known limitations / not claimed

- Codex IAB does not support native local file upload; the supplied PDF upload path therefore could not be exercised in-browser. Paste notes and URL-reference flows were exercised instead.
- Actual source deletion could not be completed in the IAB because the final Confirm remove action is destructive and requires an explicit action-time confirmation. The accessible confirmation and Cancel preservation were exercised, and stale/deletion semantics are covered by backend tests. No source was deleted in this continuation. Two-source A/B citation filtering is now browser-verified.
- No disposable signup/OTP was created or guessed. Login, invalid credentials, signup validation, full logout, protected-route recovery, session refresh, and backend-unavailable recovery were exercised; email verification and expired-session paths remain untested.
- Existing provider-backed artifacts created before the text repair can still appear in Saved outputs; regenerations are clean.
- A published learner course fixture was joined and inspected. Course-builder mutation, publishing, invitation creation, join-page rendering, and email-mismatch protection were exercised from a self-owned teaching workspace. Successful invitation acceptance and a second-account learner-sharing/revocation flow remain untested because they require a matching disposable account.
- The goal-share clipboard bridge itself returned no readable text in the first pass, but the visible fallback now makes the share route directly testable and the valid preview/clone flow passed after the patch.
- Native range dragging is not reliable through the IAB bridge; bounded adjacent step controls are now available and were verified for OS, graphics, ML, and DSP, so the underlying interaction state and backend submission are covered without relying on bridge-specific drag behavior.
- Authenticated `/api/v1/me` was proven indirectly by the private workspace and bearer-backed browser calls; the read-only browser evaluator could not expose the response body for a separate authenticated network assertion. No password, token, or OTP was printed.
