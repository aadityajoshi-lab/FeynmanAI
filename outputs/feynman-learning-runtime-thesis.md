# Feynman Learning Runtime

**Research thesis · 19 July 2026**

## Executive verdict

Feynman should not position itself as another AI tutor, course marketplace, PDF chatbot, or “learn anything” search box.

It should become an **adaptive learning runtime**: a system that turns a learner’s goal into a sequence of observable attempts, domain-specific practice environments, feedback, and evidence of independent capability.

> **The masterstroke:** Feynman does not believe that a learner understands something until it has observed them explain, apply, and transfer it to a changed situation.

That makes the core product object an **evidence-backed learner state**, not a chat history, a course-completion percentage, or a generated study guide.

The company is solving a real problem:

> People have abundant information and increasingly capable AI answers, but they lack a reliable system for turning intent and material into durable, independently usable skill.

This is necessary for hard, applied learning—operating systems, DSP, graphics, AI/ML, mathematics, professional skills, and eventually medical/financial education. It is not necessary for simple fact lookup, casual browsing, or a generic “ask anything” experience.

The decisive constraint is honesty: Feynman cannot promise that any person will learn anything merely by opening the app. It can promise a much better process for learning: a clear path, active work, feedback, and truthful evidence of what is and is not yet reliable.

## The underlying problem

### Content is no longer scarce; reliable capability is

The old education bottleneck was access to teachers and material. The modern bottleneck is different:

1. A learner does not know the prerequisite structure behind a new goal.
2. Passive reading, videos, summaries, and AI answers create an illusion of understanding.
3. Most learners do not receive immediate feedback while making a mistake.
4. A final quiz often measures recall of familiar phrasing, not transfer to a new problem.
5. Professors and mentors cannot watch every learner’s reasoning process.

The OECD’s 2025 review reaches the relevant high-level conclusion: access to digital technology alone does not guarantee educational gains; pedagogy matters, not just the tool. [OECD review](https://www.oecd.org/en/publications/the-impact-of-digital-technologies-on-students-learning_9997e7b3-en.html)

The more specific AI risk is serious. A large randomized controlled trial of high-school mathematics found that access to unguarded generative AI could harm unassisted learning. The implication is not “ban AI”; it is that an answer machine is not automatically a learning machine. [PNAS randomized trial](https://doi.org/10.1073/pnas.2422633122)

At the same time, the underlying opportunity is real. A meta-analysis covering 107 effect sizes and 14,321 participants found intelligent tutoring systems associated with higher achievement than teacher-led large-group instruction, conventional computer instruction, and textbooks/workbooks; it found no significant difference from individualized human tutoring in the included comparisons. This is historical ITS evidence, not proof that any modern LLM product works, but it supports the value of structured, individualized instruction. [Ma et al., 2014](https://eric.ed.gov/?id=EJ1049508)

Retrieval and active use also matter. A classic experiment showed that retrieval practice itself improves later learning and that learners can misjudge which study methods work best. [Karpicke & Roediger, *Science*](https://doi.org/10.1126/science.1152408)

### The precise job to be done

When a learner says, “I want to understand operating systems,” they are not asking for more explanations. They are asking the system to help them become able to:

- reason about process, memory, filesystem, and concurrency behavior;
- read a trace and identify the cause of a bug;
- modify a constrained kernel or systems program;
- explain a decision under changed conditions;
- retain and reuse the skill later.

Feynman’s job is to move a person from **curiosity or syllabus** to **independent performance**, while making the state of that journey legible.

## What already exists, and why it is not enough

The existing market establishes the baseline rather than invalidating the idea.

| Product category | What it already solves | What Feynman must solve beyond it |
|---|---|---|
| General AI study chat | Socratic prompts, step-by-step explanation, uploaded-material support, and some personalization | Persistent evidence of demonstrated capability; a domain lab; transfer validation |
| Source-grounded notebooks | Accurate answers and citations tied to selected sources | A learning path and action loop—not just source understanding |
| Curriculum tutor | Guided questions and trusted curricular material | Technical task environments and a cross-domain evidence engine |
| Vertical learning app | Authored progression and feedback within one domain | A reusable domain-runtime for difficult applied subjects |

ChatGPT Study Mode already asks questions, adapts to stated level, checks understanding, and works with uploaded course materials. [OpenAI Study Mode](https://help.openai.com/en/articles/11780217) NotebookLM already grounds answers exclusively in selected sources and produces source-based artifacts. [Google NotebookLM](https://support.google.com/notebooklm/answer/17003757?hl=en) Khanmigo explicitly guides rather than gives direct answers and is coupled to a trusted content library. [Khanmigo](https://www.khanmigo.ai/) Duolingo demonstrates the power of a constrained path plus real-world roleplay, with experts authoring the underlying scenarios. [Duolingo Max](https://blog.duolingo.com/duolingo-max/)

**Strategic inference:** “source-grounded chat,” “Socratic tutoring,” “quizzes,” “flashcards,” and “personalization” are now table stakes. They are not the thesis.

Feynman’s differentiated primitive must be:

> **A versioned learner-evidence graph connected to executable domain environments.**

The graph answers, with evidence: What can this learner do? What misconception is currently blocking them? What is the smallest next action that will change that state? What was the last independent transfer task they passed?

## The product thesis

### One platform, not many disconnected ecosystems

There is one Feynman identity, learner profile, activity history, consent model, and navigation system. Subjects are separate only where practice itself differs.

```text
Learner goal + syllabus + sources + prior evidence
                ↓
        domain compiler and safety policy
                ↓
      capability graph + current learner state
                ↓
      one clearly justified next activity
                ↓
         domain lab / project / simulator
                ↓
  evaluator + learner reflection + transfer test
                ↓
         updated evidence-backed state
```

The backbone is stable. The activity canvas changes with the subject.

- DSP needs waveforms, audio, Fourier views, filter design, and numerical tools.
- Operating systems needs runnable code, kernel traces, scheduler and memory visualizations, race replay, and test harnesses.
- Computer graphics needs a 3D scene, coordinate-space debugger, rasterizer/ray tracer, shaders, and image/performance checks.
- AI/ML needs data, notebooks, training/evaluation sandboxes, and error-analysis tools.

MIT’s operating-systems course uses xv6 and labs that extend a real small OS; its DSP materials combine theory, demonstrations, problem sets, and lab-like experimentation. Feynman should match the **mode of practice**, not merely summarize the course notes. [MIT 6.S081](https://pdos.csail.mit.edu/6.S081/2021/overview.html) · [MIT DSP](https://ocw.mit.edu/courses/res-6-008-digital-signal-processing-spring-2011/)

### The learner should never face an infinite AI surface

At any point, the learner sees only four things:

1. **Current capability:** what they are trying to become able to do.
2. **Next action:** one task, experiment, prediction, explanation, or build.
3. **Why now:** the prerequisite, observed misconception, or goal connection.
4. **Evidence:** what completion would demonstrate and what remains uncertain.

Free chat remains available as an escape hatch—“Why did this happen?” or “Show another explanation”—but it cannot be the primary loop.

## The masterstroke in technical terms

### 1. Evidence-backed learner state

The durable state is not “mastery = 74%.” It is a ledger of claims backed by observable events.

```text
Capability state
  unseen
  exposed
  explained
  applied
  transferred
  stale / needs refresh

Evidence record
  capability
  observed attempt
  tool output or artifact
  evaluator result
  learner explanation
  source / rubric version
  confidence and uncertainty
  timestamp
```

An LLM response is never evidence by itself. A student’s copied answer is not evidence. A passed simulation, a code test, an explanation under changed conditions, or a reviewed project can be evidence.

### 2. Domain packs, not separate products

A `DomainPack` is a versioned contract that defines:

- capability nodes and prerequisite edges;
- authoritative source packs and curriculum mappings;
- misconception patterns;
- permitted activity types;
- simulator/tool adapters;
- deterministic and human evaluation rules;
- safety rules and escalation policy.

The learner sees one Feynman. Internally, Feynman selects or composes domain packs. A DSP learner weak in complex numbers gets a narrow bridge; the system does not dump a whole mathematics degree into the workspace.

### 3. An activity runtime

Activities should be typed, not just model-generated prose:

- `predict_before_reveal`
- `manipulate_simulation`
- `derive_step`
- `trace_execution`
- `write_or_modify_code`
- `debug_fault`
- `explain_with_constraint`
- `compare_cases`
- `transfer_challenge`
- `human_review`

Each activity declares expected evidence, available tools, rubrics, source grounding, and what state transition it can support.

### 4. A truthful next-best-action policy

The policy chooses the next task using prerequisites, prior evidence, error patterns, spaced review, the learner’s goal, and confidence. It must explain its choice. It should not optimize merely for engagement, number of messages, or time in app.

## What to build

### Preserve the current source-first system

The current repository already has much of the domain-neutral foundation:

- `SubjectPack`, `Module`, and `Concept` model publishable subject structure.
- `LearnerProfile`, `SkillEvidence`, and `LearnerMemory` model an individual learner.
- `LearningAttempt` and `AttemptCheckpoint` capture versioned, append-only attempts.
- `Claim`, `Clarification`, and `Revision` already support misconception-oriented reasoning.
- The Notebook workspace persists extracted sources, source-scoped chat, artifacts, notes, citations, and stale-artifact handling.

This should not be discarded. It becomes Feynman’s **Source Desk and evidence context layer**.

### Add the learning runtime around it

The missing core is explicit capability orchestration.

| New object | Responsibility |
|---|---|
| `LearningGoal` | Goal statement, desired outcome, course/syllabus linkage, risk level |
| `CapabilityNode` + `PrerequisiteEdge` | The graph that a learner traverses |
| `LearnerCapabilityState` | State, confidence, error patterns, last verified transfer |
| `ActivitySpec` | Versioned definition of an action, tool, rubric, and valid evidence |
| `ActivityRun` | A learner’s concrete attempt, including tool events and feedback |
| `EvidenceRecord` | Immutable proof used to change learner state |
| `DomainPack` | Subject-specific graph, activities, tools, references, and safety policy |
| `NextActionDecision` | Explainable decision and its inputs |

The main workspace should become:

```text
Left:    Current route and capability map
Center:  One active activity or lab
Right:   Evidence, source grounding, “why this?”, and human help
Drawer:  Source Desk / Notebook / notes / previous artifacts
```

The current three-pane notebook remains useful, but it should be a supporting surface—not the home screen for every learner.

### LLMs: use them as a specialist, not the operating system

LLM calls earn their cost when they:

- transform a syllabus or goal into a proposed, reviewable domain mapping;
- diagnose a misconception from an observed explanation or code trace;
- choose a hint that preserves productive struggle;
- generate a semantically equivalent transfer task within a validated activity template;
- explain feedback in the learner’s language and level;
- summarize evidence for a human instructor.

LLMs are wasteful or unsafe when they are used for:

- waveform rendering, compilation, test execution, numerical calculation, or simulation;
- persistence of learner state;
- deterministic scheduling of review;
- source retrieval and citation lookup;
- declaring mastery without an observed attempt.

Use deterministic tools for deterministic work. Use a small/cheap model for classification and structured extraction; reserve stronger models for diagnostic reasoning and high-value feedback. Persist compact state, activity artifacts, and evidence rather than replaying the entire chat history on every call.

## Where to start building

Do **not** build a generic “learn any subject” dashboard first. That would recreate the same chat-and-content bundle that every incumbent already has.

Build the full learning runtime around one complete, highly observable capability loop:

> **DSP: Sampling → Aliasing → Reconstruction**

This is the correct foundation because it requires every important system primitive:

- prerequisites (sinusoids, frequency, sampling);
- visual and auditory simulation;
- prediction before reveal;
- mathematical explanation;
- source grounding;
- code or parameter manipulation;
- misconception diagnosis;
- a changed transfer task;
- measurable independent performance.

The existing Feynman codebase is already pointed at this content pack. The foundational implementation is therefore not a throwaway demo; it is the first production-quality `DomainPack` and the contract every later subject must satisfy.

The first complete loop should be:

1. Establish a goal and diagnose the learner’s prerequisites through small actions, not a self-rating form.
2. Ask the learner to predict what a sampled signal will become before changing any parameter.
3. Let them manipulate frequency, sample rate, and reconstruction filter in a live lab.
4. Capture the attempt, result, and explanation.
5. Use the evaluator to distinguish an arithmetic slip from an aliasing misconception.
6. Give only the smallest useful next intervention.
7. Issue a new signal/context where the original answer cannot be copied.
8. Update the capability state only if the transfer evidence supports it.

Once this contract is reliable, Operating Systems is a new domain pack with an xv6/trace adapter; AI/ML is a pack with a notebook/training adapter; Graphics is a pack with a WebGL adapter. The platform expands by adding **validated practice environments**, not by adding more chat prompts.

## Market and institutional thesis

The initial learner is an ambitious technical student or early-career professional facing a hard applied subject. The initial buyer is a technical department, university, bootcamp, or employer upskilling program that wants better independent capability—not merely higher usage of online content.

India is a credible initial institutional environment, not because it lacks courses, but because scale and practical learning are large concerns:

- The Ministry of Education’s latest published AISHE figure reports 4.33 crore higher-education enrolments in 2021–22. [AISHE release](https://www.education.gov.in/sites/upload_files/mhrd/files/PIB1999713.pdf)
- The AICTE Internship Portal explicitly connects students with verified employers and promotes learning by doing across 200+ domains. Feynman should complement that ecosystem by producing stronger evidence before and during project work, not try to replace it. [AICTE Internship Portal](https://internship.aicte-india.org/index.php/Internshala.php)
- UGC’s Academic Bank of Credits is the formal mechanism for academic credits. Feynman should not claim to issue official credits; it should provide a portable, inspectable evidence layer that an institution may choose to use. [UGC ABC regulations](https://www.ugc.gov.in/e-book/UGC_Regulation/files/basic-html/page556.html)

The enduring moat is not the model. It is:

1. The versioned domain-pack and evaluation library.
2. Consent-based sequences of `attempt → intervention → later transfer outcome`.
3. Trusted integrations with courses, labs, and instructors.
4. Tool telemetry that makes capability measurable.
5. A learner-owned evidence record that is useful across courses and work.

## Safety and trust boundaries

The platform may teach medicine and finance; it must not quietly turn into a clinical or investment advisor.

- **Medical learning:** source-cited academic cases, simulators, and curriculum mapping are in scope. Patient-specific diagnosis, treatment recommendations, or independent clinical decision support are out of scope without appropriately governed clinical workflows and human responsibility. WHO guidance stresses human autonomy, safety, transparency, accountability, equity, and continuous assessment for AI in health. [WHO guidance](https://www.who.int/publications/i/item/9789240029200) India’s NMC curriculum is competency-based, which reinforces the relevance of observed practice—but does not authorize an AI product to certify clinical competence on its own. [NMC undergraduate curriculum](https://www.nmc.org.in/information-desk/for-colleges/ug-curriculum/1000/)
- **Financial learning:** market simulation, accounting, economics, and risk education are in scope. Personalized securities advice, recommendations, guaranteed returns, or portfolio allocation are out of scope unless operating under the applicable regulated framework. SEBI describes registered investment-advisor requirements and suitability obligations for personalized advice. [SEBI investor guidance](https://investor.sebi.gov.in/investment_advisor.html)
- **Learner privacy:** learner memory must be consented, capability-scoped, inspectable, editable, and deletable. Uploaded sources belong to a goal/notebook unless a learner explicitly promotes a verified cross-domain skill.
- **Institutional trust:** the model should show source anchors, rubric version, tool result, and confidence for every state change. A teacher must be able to override or challenge the system.

## How to know whether this deserves to become a company

Do not measure messages sent, time in app, generated notes, or quiz completion as the primary outcome. Measure:

| Metric | Why it matters |
|---|---|
| Unassisted transfer score on a novel task | Tests capability rather than copied help |
| Delayed retention after time away | Tests whether learning lasted |
| Time to independent completion | Measures practical autonomy |
| Calibration | Does the learner’s confidence match performance? |
| Instructor review agreement | Tests whether the learner-state model is trustworthy |
| Cost per verified capability gain | Tests platform economics |
| Authoring time per additional domain pack | Tests scalability beyond DSP |

The right comparison is not “students like AI.” It is:

> Does a learner using Feynman independently solve a changed task better, later, than a learner using the same sources plus ordinary chat or a standard course workflow?

If the answer is no, do not expand the platform. If the answer is yes for a demanding domain, Feynman has a credible core primitive that can generalize through domain packs.

## Final thesis in one page

**Problem:** Abundant content and AI answers do not produce reliable independent capability. Learners lack a coherent path, active practice environment, precise feedback, and truthful evidence of understanding.

**Solution:** Feynman is an adaptive learning runtime. It keeps a consented, evidence-backed model of the learner; selects the next best activity; runs the appropriate domain environment; and updates state only after observed explanation, application, or transfer.

**Masterstroke:** Replace “AI remembers your chat” with “Feynman maintains a verifiable ledger of what you have independently demonstrated.”

**Product:** One platform with a shared learning kernel and many domain packs—not separate ecosystems. The sources notebook becomes a supporting Source Desk; the primary experience is an active learning workspace.

**Start:** Make DSP Sampling → Aliasing → Reconstruction the first complete domain-runtime contract. It must include diagnosis, simulation, prediction, explanation, feedback, transfer, and evidence-backed state updates. Then reuse the contract for OS, graphics, AI/ML, and other domains.

**Scale:** The software kernel and evidence model scale. High-quality domains scale through versioned domain packs, deterministic tools, evaluators, expert review, and institutional integrations—not through indiscriminately adding LLM calls.

**Boundary:** Feynman teaches and supports practice. It does not claim that a chat response proves mastery, replace universities, provide clinical decisions, or issue personalized investment advice.
