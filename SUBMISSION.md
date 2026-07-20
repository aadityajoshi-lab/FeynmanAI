# Feynman Learning OS

## One-line pitch

Feynman turns any learning goal and source material into an adaptive, evidence-based learning journey—not just an AI chat that gives answers.

## The problem

Most AI learning tools optimize for immediate answers. Students can read a summary, ask follow-up questions, and feel productive without actually being able to explain, apply, debug, derive, or transfer the idea.

Learning is also fragmented:

- PDFs live separately from practice.
- Courses are fixed instead of adapting to learner evidence.
- Chat history is mistaken for understanding.
- Generic AI answers rarely show what the learner can actually do.
- Medical and financial topics require stronger source and safety boundaries.

The missing layer is a system that continuously connects goals, sources, active practice, evidence, and the next best learning action.

## Our solution

Feynman is a general adaptive Learning OS.

A learner starts with:

> What do you want to become able to do?

Feynman creates an editable learning contract, then compiles a source-grounded curriculum with:

- concepts
- prerequisites
- activities
- difficulty
- evaluator rubrics
- source citations
- remediation paths
- transfer tasks

The learner does not simply read an answer. They interact with a simulation, make a prediction, explain a mechanism, calculate a result, debug a misconception, or analyze a bounded case.

Feynman then evaluates the observable attempt and chooses what should happen next:

- advance
- retry
- simplify
- remediate a prerequisite
- review a worked example
- increase difficulty
- verify against sources
- transfer to a new case
- request human review

## How it works

```text
Learning goal
    ↓
Editable learning contract
    ↓
Source-grounded curriculum compiler
    ↓
Interactive activity
    ↓
Observable learner attempt
    ↓
Evidence and evaluator feedback
    ↓
Adaptive next action
```

## Multi-domain support

Feynman uses one shared runtime with domain adapters.

### Operating Systems

Learners can explore process scheduling, context switching, virtual memory, deadlocks, system calls, and trace-based debugging.

### Computer Graphics

Learners can manipulate transformations, camera and coordinate spaces, rasterization, lighting, depth testing, and sampling behavior.

### Machine Learning

Learners can investigate thresholds, confusion matrices, class imbalance, data leakage, distribution shift, and model error analysis.

### Medical education

Learners can study anatomy, physiology, academic mechanisms, bounded educational cases, source-supported reasoning, uncertainty, and limitations.

Medical learning is strictly educational and source-cited. Feynman does not provide personal diagnosis, treatment, or prescriptions.

### Unseen domains

The system also supports generic source-grounded curriculum generation. During validation, it generated and resumed a History curriculum about the French Revolution without requiring a dedicated History application.

## Source Desk

Feynman includes a source workspace where learners can:

- upload and extract PDFs
- preserve page and block anchors
- select sources for a goal
- ask source-scoped questions
- generate study artifacts
- save notes
- track stale or deleted source context

Citations are validated against selected sources. Deleted or replaced source context invalidates dependent curriculum and artifacts.

## Why this is different

Feynman is not another chatbot, a collection of subject-specific apps, a static course generator, or a PDF summarizer. It does not declare mastery from fluent text.

The core primitive is **observable learning evidence**.

The system asks:

> What did the learner actually demonstrate, and what should they do next?

That makes the product extensible across subjects while preserving a consistent learning model.

## Technical architecture

- Next.js and TypeScript frontend
- Django and Django REST Framework backend
- Persistent learner, curriculum, activity, evidence, notebook, and source models
- Structured JSON activity contracts
- Deterministic adaptive route engine
- Mistral for source extraction and OCR
- Fireworks for structured curriculum and evaluator feedback
- Source fingerprints and stale-context invalidation
- Strict provider schemas and visible failure states
- Responsive AppShell with Source Dock, Activity Canvas, and Evidence Rail

LLMs propose and enrich structured learning content, but they do not silently decide mastery. Evidence transitions are governed by explicit runtime rules and validated learner state.

## Safety and trust

Feynman is designed to fail honestly:

- provider failures never become verified evidence
- malformed outputs are rejected
- citations must match selected sources
- medical learning remains source-bound
- personal clinical and financial advice is blocked
- raw PDFs are not stored as unrestricted learner memory
- learner evidence sharing is explicit and revocable

## Validation

The current implementation has been validated with:

- 133 backend tests
- 35 frontend tests
- TypeScript typecheck
- production build
- Django checks
- migration checks
- live API smoke tests
- isolated browser acceptance

Browser validation covered goal creation, curriculum compilation, route editing, interactive domain activities, weak-attempt remediation, verified evidence, source citations, refresh persistence, mobile layouts, medical safety boundaries, notebook chat, notes, artifacts, course states, teaching states, institution states, and privacy states.

## Current status

Feynman is an adaptive Learning OS alpha.

The core runtime and multi-domain architecture are implemented. The next stage is real-learner validation: measuring whether students improve, retain concepts, transfer knowledge, and become better calibrated about what they do and do not understand.

## Closing statement

AI should not only explain more quickly.

It should help people become capable of explaining, applying, testing, and defending what they learned.

Feynman is built around that principle.
