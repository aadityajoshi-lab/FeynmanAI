# OpenMAIC integration boundary

OpenMAIC is a useful reference implementation for interactive learning, not a drop-in replacement for Feynman. The repository was audited at commit `34448beb6ce764ec2bc8ceb1d6ed519c37fa6184` (2026-07-17). Its current main branch is MIT-licensed, but the repository contains separately packaged artifacts with their own package metadata; any future copied file must retain its notice and be rechecked at the pinned commit.

Reference: [THU-MAIC/OpenMAIC](https://github.com/THU-MAIC/OpenMAIC).

## What we are carrying forward

| OpenMAIC element | Feynman adaptation | Boundary |
|---|---|---|
| Two-stage outline -> scene generation | Upload material -> editable `StudyPlan` -> approved scene manifest | GPT proposes typed JSON; the server validates it before publication. |
| SVG whiteboard with pan/zoom, reset/fit, reveal, and history | `WhiteboardManifest` and a small Feynman whiteboard surface | No OpenMAIC stage store or arbitrary action execution is imported. |
| Interactive HTML scene renderer | Optional reviewed 2D/3D scene configuration, opened by the module copilot | No model-generated HTML/JS is executed in the learner page; a visualization is never a build requirement. |
| Deep Interactive 3D/simulation scenes | Optional reviewed `three_d` scene manifest | 3D is not required for the DSAP MVP; sandboxing and a review gate are mandatory. |
| Quiz and question scene types | Approved past-question bank with source/concept IDs | Runtime samples approved questions; it does not generate unlimited exam content on click. |
| AI teacher drawing and spotlight actions | Finite actions: `reveal`, `spotlight`, `draw`, `write`, `equation` | Each action is bounded by count, size, and scene version. |
| PDF/media authoring pipeline | Private source upload -> extraction candidates -> review -> immutable source pack | Raw uploads never become runtime evidence automatically. |

## What we are not importing

- OpenMAIC's full Next.js/LangGraph/provider stack; Django remains the source and policy authority.
- Multi-agent classroom theatre, TTS/ASR, OpenClaw, PBL, export, or hosted retrieval in the first study slice.
- Arbitrary generated HTML, scripts, iframes, or network-enabled visualizations.
- An unbounded generic chat surface. Feynman's copilot is contextual, source-bounded, and limited to typed module controls; it complements the concept objective, checkpoint, and teach-back.

## Required provenance for copied code

If an isolated MIT-licensed file is copied rather than reimplemented, preserve the original copyright/license notice and add a nearby `NOTICE` comment containing:

```text
Adapted from THU-MAIC/OpenMAIC, commit 34448beb6ce764ec2bc8ceb1d6ed519c37fa6184, MIT License.
```

The first implementation uses the interaction ideas and typed manifest boundary rather than copying the repository wholesale. This keeps the learner surface minimalist and avoids pulling in incompatible stores, renderers, or nested package terms.
