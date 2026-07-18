# Remediation video and media pipeline

The study runtime supports an optional remediation lesson after an incorrect
checkpoint. It is deliberately separate from the evidence record: generated
media teaches the learner but is not a source citation.

```text
incorrect checkpoint
  -> immediate text correction + source-grounded visual
  -> learner chooses guided video
  -> Django validates source IDs and bounded correction fields
  -> Fireworks slide generator OR protected rendered-video adapter
  -> ordered 1-5 minute lesson with segment controls
```

## Fireworks slide mode

The default `REMEDIATION_VIDEO_PROVIDER=fireworks-slides` asks the existing
Fireworks Qwen provider for a typed storyboard containing definition, visual
model, application, misconception repair, and transfer content. The player
shows one slide at a time and includes a diagram when the model returned one.
VoxCPM narration is optional; browser speech is used as a fallback. This mode
does not claim that Qwen generated an MP4.

## OpenMAIC-style rendered mode

When configured, the rendered path follows OpenMAIC's actual design:

1. Normalize the requested lesson against provider capabilities.
2. Split 60-300 seconds into bounded short segments.
3. Submit asynchronous provider tasks.
4. Poll each task with a five-minute timeout.
5. Generate at most two segments concurrently.
6. Return ordered clips with duration and dimensions.
7. Play clips as one lesson, with an explicit segment list and optional synced
   VoxCPM narration.

The route currently ports the Seedance adapter used by OpenMAIC. Additional
providers can be added behind the same registry without changing the Feynman
endpoint or learner UI.

Provider credentials stay in server environments. Generated URLs are teaching
outputs only and never enter the approved source pack.
