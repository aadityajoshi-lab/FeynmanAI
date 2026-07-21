# Feynman Learning OS

## Submission metadata

- **Category:** Education
- **Project name:** Feynman Learning OS
- **Tagline:** AI should not make students feel fluent. It should help them prove they can think.
- **Recommended hero story:** A computer-science student learns to *reason about* operating-system scheduling, not merely define it.
- **Repository:** `[ADD PUBLIC REPOSITORY URL]`
- **Live demo:** `[ADD DEPLOYED DEMO URL OR JUDGE INSTRUCTIONS]`
- **Demo video:** `[ADD PUBLIC YOUTUBE URL]`
- **Codex feedback session:** `[ADD /feedback SESSION ID]`

> **Why this story:** Operating-system scheduling is visual, technical, and easy to test in a three-minute demo. It lets a judge see a learner make a prediction, get a wrong answer, inspect a trace, explain the trade-off, and earn evidence. Transformers, medical education, and research-paper learning remain proof of generality - not competing stories in the first minute.

---

## One-line pitch

**Feynman turns a learning goal and trusted sources into an adaptive practice loop that records what a learner can actually explain, apply, and transfer - instead of mistaking a good chat response for understanding.**

## The problem

Students are surrounded by explanations and still leave uncertain about what they can do alone.

A student can watch a lecture on Round Robin scheduling, read a polished AI summary, and even repeat the definition of a time quantum. Then put them in front of three processes with different arrival times and ask: *Which scheduler is appropriate here, what trade-off are you making, and how would the trace change?* Many cannot defend an answer.

That gap is the problem Feynman is built for.

Most AI learning products optimize for an immediate answer, a summary, or a conversation. They make learning feel fast, but they rarely distinguish between:

- seeing an explanation;
- repeating an explanation;
- applying it to a concrete case; and
- transferring it to a changed situation.

Chat history is not learner state. A fluent model response is not learner evidence. A completed video is not proof that the learner can reason independently.

This is especially costly in technical subjects, where students need to make choices, trace systems, debug mistakes, and explain trade-offs. It is also why a single generic chatbot is a poor fit for serious learning across engineering, AI/ML, research papers, and academic medical education.

## The solution

Feynman is an adaptive Learning OS built around one rule:

> **Reading, chat, and generated answers do not change learner state. Observable attempts do.**

A learner starts with one plain-language goal:

> *What do you want to become able to do?*

Feynman turns that into an editable learning contract, a source-grounded route, an active task, and an evidence-backed next action.

```text
Goal
  -> Learning contract
  -> Source-grounded route
  -> Active task
  -> Observable attempt
  -> Evidence and feedback
  -> Next best action
```

The system can advance a learner, ask for a retry, simplify the task, repair a prerequisite, show a worked example, require source verification, or ask for transfer to a new case. It does not silently label someone as having mastered a topic because they read an answer.

## The demo story: from "I know Round Robin" to "I can defend a scheduling decision"

Our demo follows a second-year CS student preparing for an operating-systems exam and interview.

They begin with a familiar but weak goal: **“Understand operating-system scheduling.”** Feynman asks them to make the goal concrete: explain FCFS, SJF, and Round Robin; trace ready, running, and waiting states; and defend the waiting-time versus response-time trade-off.

The learner then:

1. reviews and edits a learning contract instead of accepting an AI-generated plan blindly;
2. opens an interactive scheduler trace with processes arriving at different times;
3. makes a prediction before seeing the answer;
4. submits an explanation of the trace and its trade-offs;
5. receives evidence-aware feedback when their reasoning is incomplete or conflicts with the selected source;
6. retries with a grounded explanation; and
7. sees an evidence record and the next task update only after the observable attempt.

The emotional turn is simple: the student stops asking, *“Did I finish the material?”* and starts asking, *“Can I defend this decision?”*

## What makes Feynman different

Feynman is not another AI tutor, PDF chatbot, course generator, or quiz wrapper. Its core primitive is an **evidence-backed learner model**.

| Typical AI learning flow | Feynman flow |
| --- | --- |
| Ask a question | State a capability to build |
| Receive an answer | Make an observable attempt |
| Continue chatting | Get source-bounded feedback |
| Track completion | Record evidence and uncertainty |
| Show more content | Select the next best activity |

The product keeps two kinds of memory deliberately separate:

- **Notebook/source memory:** extracted source text, page/block anchors, visuals, citations, and source-grounded artifacts.
- **Learner memory:** the learner's goal, observable attempts, evidence state, misconceptions, and next action.

That separation matters. A PDF should not become an unrestricted personal-memory dump, and a course should not receive private learner data unless the learner explicitly shares selected evidence.

## Built for one learner, designed to generalize

The hero demo is Operating Systems because it makes active reasoning visible. The runtime is not hardcoded to one subject.

- **Operating Systems:** scheduling traces, process states, memory and debugging tasks.
- **Computer Graphics:** transformations, camera-space reasoning, rendering and sampling experiments.
- **Machine Learning:** data leakage, class imbalance, confusion matrices, error analysis, and model evaluation.
- **Research papers:** arXiv/web/PDF extraction, source anchors, diagrams/visuals, paper-grounded questions, and study artifacts.
- **Academic medical education:** source-cited mechanisms and bounded educational cases, with personal diagnosis and treatment advice blocked.

The promise is not “AI can certify mastery of anything.” The promise is that one evidence runtime can adapt the **practice mode** to the domain while keeping the same honest loop: goal, attempt, evidence, next action.

## Why this methodology

Feynman turns established learning-science ideas into product behavior rather than a list of study features.

1. **Retrieval and reconstruction, not passive review.** Karpicke and Blunt found retrieval practice supported meaningful learning better than elaborative concept mapping in their study. Feynman therefore asks the learner to predict, explain, derive, or trace before it reveals or validates the answer. [Karpicke & Blunt, 2011](https://pubmed.ncbi.nlm.nih.gov/21252317/)

2. **Self-explanation as an observable signal.** Chi and colleagues showed that prompting self-explanations can improve understanding and transfer. Feynman captures the learner's reasoning, conclusion, confidence, and uncertainty rather than scoring a single final answer. [Chi et al., 1994](https://onlinelibrary.wiley.com/doi/10.1207/s15516709cog1803_3)

3. **Transfer is a stronger test than recognition.** Barnett and Ceci's taxonomy makes clear that transfer varies with how much the context changes. Feynman includes changed-case and transfer tasks so it can distinguish a memorized example from a defensible idea. [Barnett & Ceci, 2002](https://pubmed.ncbi.nlm.nih.gov/12081085/)

4. **Adaptive support must be bounded and inspectable.** Research on intelligent tutoring motivates timely feedback and adaptation, but it does not justify letting a model make opaque mastery claims. Feynman uses structured activity contracts, rubrics, source anchors, explicit state transitions, and visible provider failures. [VanLehn, 2011](https://doi.org/10.1080/00461520.2011.611369)

These papers motivate the design; they do **not** prove that Feynman itself improves outcomes yet. That requires a future learner study with retention, transfer, calibration, and comparison measures.

## How it works technically

Feynman is a working full-stack adaptive-learning runtime:

- **Frontend:** Next.js and TypeScript with a responsive AppShell, Source Dock, Activity Canvas, Evidence Rail, and mobile drawers.
- **Backend:** Django and Django REST Framework with durable goals, learning contracts, curricula, activities, attempts, evidence records, notebooks, notes, and source models.
- **Source Desk:** PDFs, pasted text, webpages, and arXiv references become bounded, durable source packs with page/block/visual anchors. Raw source files are not reused as global learner memory.
- **Adaptive engine:** structured activity contracts and deterministic route decisions for retry, remediation, worked examples, advance, source verification, transfer, difficulty increase, and human review.
- **Model boundary:** provider output is schema-checked, provenance is visible, and provider failure cannot become verified evidence. The current local live path uses Qwen through a Fireworks-compatible transport; Mistral is available for OCR/extraction. The provider boundary is server-side and replaceable.
- **Trust boundary:** selected-ready sources scope chat and artifact generation. Deleting or changing a source can invalidate dependent context instead of silently preserving stale claims.
- **Privacy boundary:** learner evidence is owned by the learner; sharing is explicit and revocable.

## What we validated

This is not a slide deck pretending to be a product. The local alpha has been exercised end to end with authenticated browser testing.

- 151 backend tests passed.
- 58 frontend tests passed.
- Type checking, production build, Django checks, migration checks, and compile checks passed.
- Live browser flows covered sign-in/session persistence, goal creation, learning-contract confirmation, curriculum compilation, interactive attempts, remediation, source-anchored feedback, artifact generation, notebook notes, responsive layouts, and safety boundaries.
- A live Qwen/Fireworks run generated a curriculum, source-grounded feedback, and saved source artifacts.
- Webpage and arXiv ingestion were exercised with durable source metrics and page/visual anchors.

Representative visual evidence already captured in this repository:

| What it proves | Screenshot |
| --- | --- |
| Evidence-first home experience | `outputs/final-qa-landing-desktop.png` |
| Learner-editable contract | `outputs/final-qa-goal-review.png` |
| Source/evidence-aware retry feedback | `outputs/final-qa-learning-verified-feedback.png` |
| Three-pane Source Desk with source tools | `outputs/final-qa-webpage-notebook.png` |
| Saved, source-grounded artifact | `outputs/final-qa-artifact-output.png` |
| Responsive learning workspace | `outputs/final-qa-goal-mobile-authenticated.png` |

The current release label is **alpha**. Two final browser-validation gaps are recorded honestly: native local PDF file selection could not be driven by the isolated in-app browser, and destructive source deletion was not completed in that pass. The existing API/test coverage remains in place, but those two UI actions should be re-run in a browser with a native file chooser before a production claim.

## How Codex and GPT-5.6 were used

Codex was used as the engineering and verification partner for the project: architecture and data-contract work across the Next.js/Django application, migration and API work, test creation, production-build checks, browser-driven visual QA, responsive fixes, and final hardening.

The project is intentionally honest about the distinction between **how it was built** and **which runtime provider currently serves learner-generation requests**. The local verified runtime uses Qwen/Fireworks today; it does not claim that GPT-5.6 is secretly serving end-user requests. The provider layer keeps model calls server-side and swappable.

Before final submission, attach the `/feedback` session ID that documents the main Codex/GPT-5.6 build work and ensure the README identifies the exact Codex/GPT-5.6 contributions. This is important because the OpenAI Build Week submission asks for a working project built with Codex and GPT-5.6, a public demo video that explains that use, a repository with setup instructions, and the relevant `/feedback` session ID.

## What comes after the hackathon

The next question is not “Can we add more subjects?” It is: **Does this loop make a learner more capable than ordinary AI chat or passive study?**

Our post-hackathon validation plan is deliberately narrow:

1. run a small learner study in Operating Systems or DSP;
2. compare Feynman against the same sources plus ordinary chat/study workflow;
3. measure delayed retention, changed-case transfer, explanation quality, confidence calibration, and time-to-independent solution;
4. audit the evidence rubric against instructor review; and
5. expand domain adapters only when the practice interaction is genuinely useful.

That is how Feynman earns the right to scale from one compelling learning transformation to many subjects.

## Closing

The future of learning should not be a more persuasive answer box.

It should be a system that helps a learner encounter an idea, struggle with it safely, explain it in their own words, apply it to a changed situation, and leave with evidence they can inspect.

**Feynman turns “I studied it” into “I can show you.”**

---

## Internal pre-submission truth check - remove before publishing

- [ ] Replace all bracketed links and the `/feedback` session ID.
- [ ] Confirm the submitted Codex session actually used GPT-5.6; do not imply an end-user GPT-5.6 API path unless one is implemented and live-tested.
- [ ] Keep **Education** as the category.
- [ ] Record a public video under three minutes with voiceover that explains the concrete Codex/GPT-5.6 development contribution.
- [ ] Ensure the repo README contains setup, sample source data, a no-secret test path, and a short Codex/GPT-5.6 contribution section.
- [ ] Use the OS scheduler as the main narrative. Mention ML, graphics, research papers, and medicine only after the core before/after proof lands.
- [ ] Do not claim improved learning outcomes, mastery certification, clinical diagnosis, or personalized financial advice.
