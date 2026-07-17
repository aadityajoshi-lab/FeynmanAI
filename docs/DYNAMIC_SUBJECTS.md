# Dynamic subjects and learning modes

Feynman is a learning engine, not a DSAP-specific application. A subject is a versioned `SubjectPack` containing modules, concepts, approved source spans, media manifests, checkpoints, evaluation cases, and the learning modes allowed for each concept.

The first published pack is `dsap-v1`, with a complete `sampling-aliasing` module. New subjects should be added as data packs and reviewed by a domain instructor; the frontend and provider contract must not be forked per subject.

## Learner evidence

The product records observable evidence for a concept: prediction accuracy, explanation rubric results, transfer attempts, confidence calibration, retries, and selected learning modes. It reports interpretable states (`unseen`, `emerging`, `practiced`, `transfer_ready`, `needs_review`, `insufficient_evidence`). It does not infer IQ, personality, disability, or a fixed learning style.

## Learning mode policy

Learners can choose a mode. The server can recommend a mode after a failed attempt, but the recommendation is always overridable and explains the observed reason. The available modes are defined in the subject pack so an instructor can remove a mode that does not fit a discipline.

## Source and media boundary

Source processing is an authoring workflow:

```text
PDF/image/video -> validate -> extract candidates -> instructor review -> atomic spans -> SubjectPack publish
```

Published runtime requests receive only the approved spans selected by the module. Model-generated text cannot become evidence automatically. Retrieval is intentionally absent for small packs; an optional retriever can be added when a pack grows beyond the direct-context budget.

## Memory boundary

Global preferences are separate from subject-specific skill evidence and short-lived session state. Demo memory is keyed by an anonymous learner ID, opt-in, and deletable. Cross-subject memories never merge source evidence or skill states between domains.
