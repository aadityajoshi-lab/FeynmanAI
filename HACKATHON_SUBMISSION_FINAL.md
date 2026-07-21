# FEYNMAN

## The Evidence-First Learning Runtime

**Category:** Education
**Tagline:** AI should not make students feel fluent. It should help them prove they can think.
**Built with:** Codex + GPT-5.6 for the engineering and verification workflow; provider-neutral learner runtime.

---

## The moment we are building for

Picture a student at 11:48 p.m. They finish an operating-systems lecture, read a clean AI summary, and feel ready.

The next morning, they are given three processes, a time quantum, and one question:

> Which scheduler would you choose here - and can you defend the trade-off?

They freeze.

They did not fail because the explanation was missing. They failed because nobody asked them to make a prediction, trace the system, explain the result, or apply the idea when the numbers changed.

That is the quiet failure of modern learning: **we confuse exposure with capability.**

AI has made exposure nearly frictionless. It can summarize a chapter, answer a question, generate flashcards, and write a perfect explanation in seconds. But a beautiful answer on screen is not evidence that the learner can reason alone when the answer is no longer there.

Feynman exists to close that gap.

## Evidence before answers

Feynman is not a chatbot with a study-plan skin. It is an **evidence-first learning runtime** built around one rule:

> **Reading, chat, and generated answers do not change learner state. Observable attempts do.**

The learner begins with a human goal:

> *What do you want to become able to do?*

Feynman turns that into an editable learning contract, a source-grounded route, an active task, and an evidence-backed next action.

```text
Goal -> Learning contract -> Active task -> Observable attempt -> Evidence -> Next best action
```

Instead of rewarding time spent, Feynman asks for proof:

- predict what will happen;
- explain why it happened;
- trace a system or derive a result;
- debug a misconception;
- apply the idea to a changed case; or
- admit uncertainty and repair a prerequisite.

The system can advance, retry, remediate, show a worked example, increase difficulty, require source verification, or ask for transfer. It cannot silently call a learner "mastered" because they read an answer.

## The live demo: from "I know Round Robin" to "I can defend a scheduling decision"

Our three-minute story follows a computer-science learner who says, "I understand operating-system scheduling."

Feynman does not accept that sentence as progress. It asks the learner to define a capability: trace ready, running, and waiting states; compare FCFS, SJF, and Round Robin; and defend the responsiveness versus context-switch trade-off.

The learner then:

1. **Edits the learning contract.** The route is proposed by AI, but the learner controls the goal, starting point, prerequisites, and first proof.
2. **Makes a prediction.** Before seeing the answer, they work through an interactive scheduler trace.
3. **Submits reasoning, not just a final choice.** Feynman captures their explanation, conclusion, confidence, and uncertainty.
4. **Receives bounded feedback.** If the trace is incomplete or the source does not support the claim, the system says so and routes them to a repair step.
5. **Retries with evidence.** A stronger, source-anchored explanation becomes an observable record, and only then does the route advance.

The emotional shift is the product:

> The student stops asking, "Did I finish the chapter?" and starts asking, "Can I defend this decision?"

## What a judge can verify in one minute

1. Create the goal **"Understand operating-system scheduling."**
2. Edit the learner-owned contract instead of accepting a black-box plan.
3. Open the scheduler task and make a trace-based prediction.
4. Submit a weak explanation and watch Feynman route it to remediation rather than award a completion badge.
5. Select a source anchor, submit a stronger explanation, and see the evidence record and next task update.

That one loop is the whole thesis made visible: **AI output is not the achievement; the learner's observable action is.**

## Why Feynman is different

| Most AI learning flows | Feynman |
| --- | --- |
| Ask for an answer | Commit to an attempt first |
| Produce more content | Select the smallest useful next activity |
| Save chat history | Save evidence of learner actions |
| Measure completion | Surface uncertainty, reasoning, and transfer |
| Treat sources as context | Preserve source anchors and citation boundaries |

The core product object is not a conversation. It is a **learner-owned evidence record**:

```text
What did the learner attempt?
What did they explain or apply?
What source supports the feedback?
What remains uncertain?
What should happen next?
```

That is why Feynman is not another summary tool, static course generator, or quiz collection. It is a system for moving a learner from curiosity to independent performance - visibly and honestly.

Under the hood, that makes Feynman an evidence state machine rather than an answer generator: every route change must be justified by an attempt, a rubric, source context, or an explicit uncertainty state.

## Learning science translated into product behavior

Feynman does not claim to have solved learning. It turns well-established learning-science principles into product constraints.

- **Retrieval before review.** Delayed testing can improve later retention even when repeated study feels more familiar. That is why Feynman asks for a prediction, trace, or explanation before revealing a polished answer. [Roediger & Karpicke, 2006](https://pubmed.ncbi.nlm.nih.gov/16507066/)

- **Self-explanation over answer imitation.** Prompted self-explanation has been shown to support deeper understanding. That is why a Feynman attempt records reasoning and uncertainty, not only a final answer. [Chi et al., 1994](https://onlinelibrary.wiley.com/doi/10.1207/s15516709cog1803_3)

- **Useful struggle, not manufactured frustration.** Productive-failure research motivates letting learners grapple with a meaningful problem before targeted instruction. Feynman turns a weak attempt into a specific remediation path instead of a generic "incorrect." [Kapur, 2008](https://doi.org/10.1080/07370000802212669)

- **Transfer as the stress test.** Recognition is not enough. Feynman changes the numbers, scenario, or context to ask whether the learner can use the same idea again. [Barnett & Ceci, 2002](https://pubmed.ncbi.nlm.nih.gov/12081085/)

These studies motivate the design. They do **not** prove that Feynman improves learning outcomes yet. That claim belongs to a future controlled learner study - and we say so plainly.

## What is actually built

Feynman is a working full-stack application, not a concept video.

- **Next.js + TypeScript** frontend with a focused learning workspace: Source Dock, one active Activity Canvas, and an Evidence Rail.
- **Django + Django REST Framework** backend with durable goals, contracts, activities, attempts, evidence records, notebooks, source packs, notes, and permissions.
- **Adaptive route engine** with explicit decisions: retry, remediate, show a worked example, verify against sources, advance, increase difficulty, transfer, or request human review.
- **Source Desk** for PDFs, pasted text, webpages, and arXiv references. Extracted content retains page/block/visual anchors; selected sources scope chat and generated artifacts.
- **Trust boundaries:** source memory and learner memory stay separate; provider failures cannot create verified evidence; stale/deleted sources do not silently support new claims; evidence sharing is explicit and revocable.
- **Safety boundaries:** medical learning remains source-cited and educational. Personal diagnosis, treatment, and prescription behavior are blocked.

The current local alpha has passed 151 backend tests, 58 frontend tests, type checking, production build, Django checks, migration checks, and authenticated browser acceptance. The browser flow exercised sign-in, goal creation, contract confirmation, curriculum compilation, interactive attempts, remediation, source-anchored feedback, notebook artifacts, responsive layouts, and safety boundaries.

The live local model path uses Qwen through a Fireworks-compatible transport, with server-side model selection and visible provider provenance. That is intentional: the learning runtime is provider-neutral, while its evidence rules remain explicit and inspectable.

## What Feynman refuses to fake

Feynman does not issue degrees. It does not turn a fluent response into "mastery." It does not present personal medical or financial advice as education. And it does not hide a provider failure behind a confident-looking answer.

Those boundaries are not disclaimers added at the end. They are part of the runtime: verified evidence requires an observable attempt, source-backed feedback stays within the selected source scope, and uncertainty remains visible when the system cannot defend a claim.

## One runtime, different ways to practice

Feynman should not present every subject as the same chat screen. It keeps one evidence loop but changes the *practice*.

- **Operating Systems:** scheduler traces, process-state reasoning, and debugging.
- **Computer Graphics:** transformations, camera-space reasoning, and rendering experiments.
- **Machine Learning:** data leakage, class imbalance, confusion matrices, and error analysis.
- **Research papers:** arXiv/web/PDF source extraction, cited questions, visuals, and source-grounded study artifacts.
- **Academic medical education:** mechanisms and bounded educational cases, never personal clinical advice.

This is how Feynman can grow without making a false "learn anything" promise. We expand only when the domain has a meaningful active task and a defensible way to evaluate it.

## Built with Codex and GPT-5.6

Codex was used as the engineering and verification partner for Feynman: shaping the application architecture and contracts, implementing backend and frontend changes, creating migrations and tests, running production-build checks, driving browser-based visual QA, and iterating on failures until the critical learner journey worked end to end.

We are deliberate about a distinction that many AI demos blur:

- **Codex + GPT-5.6** accelerated the building, testing, and hardening of Feynman.
- **Qwen/Fireworks** is the verified local runtime provider for learner-generation requests today.

We do not claim that GPT-5.6 is secretly serving end-user requests when it is not. The `/feedback` session ID and repository history document how Codex and GPT-5.6 were used to build the project.

## What comes next

The next milestone is not adding more AI features. It is asking one hard question:

> **Does a learner using Feynman solve a changed task better, later, than a learner using the same sources with ordinary chat or passive study?**

We will test that first in a demanding technical domain such as Operating Systems or DSP, measuring delayed retention, changed-case transfer, explanation quality, confidence calibration, and time to independent solution. We will audit the evidence rubric against instructor review before expanding into more domains.

If the answer is no, we should not scale. If the answer is yes, Feynman has a credible primitive for a new category of AI learning: one that does not merely explain, but helps people become demonstrably capable.

## Closing

The future of education is not a more persuasive answer box.

It is a system that lets a learner struggle safely, explain in their own words, apply an idea when the situation changes, and leave with evidence they can inspect.

**Feynman turns "I studied it" into "I can show you."**

---

## Submission fields to complete before publishing

- **Repository URL:** `[ADD URL]`
- **Live demo / judge instructions:** `[ADD URL OR INSTRUCTIONS]`
- **Public YouTube demo:** `[ADD URL]`
- **Codex `/feedback` session ID:** `[ADD SESSION ID]`

## Internal truth guardrails - remove before pasting into Devpost

- Do not say GPT-5.6 serves learner requests unless that path is live and tested.
- Do not claim measured learning gains, mastery certification, clinical diagnosis, or personalized financial advice.
- Keep **Education** as the selected category.
- Use the Operating Systems story as the main video narrative; show other domains only as proof that the runtime generalizes.
- In the video voiceover, name concrete Codex/GPT-5.6 work: architecture, implementation, tests, browser QA, and iterative fixes.
