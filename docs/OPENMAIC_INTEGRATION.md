# OpenMAIC integration boundary

OpenMAIC is the reference implementation for the remediation media pipeline.
Feynman uses the audited commit `34448beb6ce764ec2bc8ceb1d6ed519c37fa6184`
(MIT License) and keeps Django as the source/evidence policy authority.

Reference: [THU-MAIC/OpenMAIC](https://github.com/THU-MAIC/OpenMAIC).

## What is carried forward

| OpenMAIC element | Feynman adaptation | Boundary |
|---|---|---|
| Typed media provider registry | Server-selected remediation mode and safe capability status | Provider credentials never reach the browser. |
| Provider capability normalization | Rendered path normalizes duration, aspect ratio, and resolution | Unsupported options fall back to provider-supported values. |
| Async task pipeline | Submit, poll, timeout, and ordered clip metadata | Two rendered clips are generated concurrently at most. |
| Media generation section | Intake capability card and incorrect-answer video section | Video is optional and never blocks learning progress. |
| VoxCPM Python narration contract | Optional `/tts/upload` narration for slides or clips | Voice remains server-side and can be unavailable. |
| Source-bounded lesson generation | Django resolves approved source anchors before media generation | Video is a teaching aid, never authoritative evidence. |

## Remediation video flow

An incorrect checkpoint exposes two independent recovery paths: an immediate
text/visual correction and an optional guided video. Feynman calls
`POST /api/v1/study-plans/remediation-video`; Django validates the stage anchors
and then selects one of two modes:

- `fireworks-slides` (default): Fireworks Qwen returns a typed 4-8 slide
  storyboard. Feynman presents it with optional VoxCPM narration or browser
  speech fallback. This uses the existing Fireworks key only and is the normal
  local setup.
- rendered clips: the protected local Next route follows OpenMAIC's provider
  pipeline with short 5/10-second tasks, two-at-a-time generation, polling,
  ordered segment playback, dimensions, and optional narration.

The learner can choose a 1, 2, 3, or 5 minute target in the Video remediation
section. The app generates media only after an incorrect answer and keeps the
retry, similar-question, and continue controls available if media fails.

## Settings

```text
# backend/.env -- default Fireworks-only remediation
REMEDIATION_VIDEO_PROVIDER=fireworks-slides
TTS_VOXCPM_BASE_URL=http://127.0.0.1:8001

# backend/.env -- optional protected bridge for rendered clips
VIDEO_SERVICE_BASE_URL=http://127.0.0.1:3000
VIDEO_SERVICE_KEY=feynman-local-video
VIDEO_SERVICE_TIMEOUT_SECONDS=900

# frontend/.env.local -- server-only, required only for rendered clips
VIDEO_PROVIDER=seedance
VIDEO_SEEDANCE_API_KEY=your-server-side-provider-key
VIDEO_SEEDANCE_MODEL=doubao-seedance-2-0-260128
FEYNMAN_VIDEO_INTERNAL_KEY=feynman-local-video
```

The backend Fireworks key is used for Qwen authoring, evaluation, and the
default slide lesson. It is never exposed to the browser and is not treated as
a Seedance key.

## What is not imported

Feynman does not copy OpenMAIC's full classroom, settings store, arbitrary HTML
renderer, or unrelated providers. Any future isolated MIT-licensed copied file
must retain the notice:

```text
Adapted from THU-MAIC/OpenMAIC, commit 34448beb6ce764ec2bc8ceb1d6ed519c37fa6184, MIT License.
```
