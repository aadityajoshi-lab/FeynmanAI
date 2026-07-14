# Feynman AI: The Protégé Effect Engine

### AI shouldn't replace thinking. AI should force thinking.

---

## 1. The Problem

Modern AI tutors explain concepts, summarize notes, solve homework, and generate polished lessons on demand.

This creates a dangerous educational phenomenon:

> **The Illusion of Explanatory Depth** — students feel they understand because the explanation *sounded* clear, but when asked to explain the idea themselves, the understanding collapses.

AI performed the cognitive work. The student consumed the output. Learning never happened.

## 2. Our Thesis

We don't need AI that teaches students better. We need AI that forces students to think harder.

**Feynman AI** leverages the **Protégé Effect** — the well-established cognitive phenomenon that teaching others is one of the most effective ways to learn. Instead of tutoring the student, Feynman AI creates a classroom of AI students that the human user must teach. The classroom refuses to "understand" until the explanation is complete, logically consistent, transferable, and robust against misconceptions.

**Traditional AI:** AI thinks → Human consumes.
**Feynman AI:** Human thinks → AI verifies.

> **One-sentence pitch:** Most AI education products answer questions for students. Feynman AI creates a classroom of AI students that users must teach — exposing misconceptions, measuring overconfidence, predicting forgetting, and intervening (up to and including a short AI-generated video) only when productive struggle turns unproductive.

---

## 3. Core Learning Loop

```
Upload Material
      |
      v
AI Builds Concept Dependency Graph
      |
      v
Pre-Assessment Confidence Gauge
      |
      v
Student Teaches AI Classroom  <------------------+
      |                                          |
      v                                          |
AI Challenges Explanation (Novice/Skeptic/Extrapolator)
      |                                          |
      v                                          |
Misconception Detected? --No--> Node Marked Mastered
      |                                          |
     Yes                                         |
      v                                          |
Adaptive Intervention Engine                     |
(Hint -> Analogy -> Diagram -> Worked Example     |
        -> AI-Generated Micro-Video)              |
      |                                          |
      +---------- Student Re-Teaches -------------+
      |
      v
All Nodes Mastered --> Domain-Transfer Challenge
      |
      v
Confidence-Mastery Gap Analysis + Forgetting Curve
```

---

## 4. End-to-End Architecture

```
       +---------------------------------------------+
       |   Universal Ingestion (PDF / PPT / Notes)   |
       +----------------------+----------------------+
                              |
                              v
       +---------------------------------------------+
       |     AI Concept Graph Generation (JSON)      |
       +----------------------+----------------------+
                              |
                              v
       +---------------------------------------------+
       |   Pre-Assessment Self-Confidence Measure    |
       +----------------------+----------------------+
                              |
                              v
       +---------------------------------------------+
       |    Multi-Agent Swarm (Interactive Class)    |
       |  - The Novice (Jargon Trap)                 |
       |  - The Skeptic (Logic Gaps)                 |
       |  - The Extrapolator (Boundary Limits)       |
       +----------------------+----------------------+
                              |
                              v
       +---------------------------------------------+
       |       Interactive Whiteboard (Canvas)       |
       +----------------------+----------------------+
                              |
                              v
       +---------------------------------------------+
       |       Hidden Rubric Progress Evaluator      |
       +----------------------+----------------------+
                              |
                              v
       +---------------------------------------------+
       |   Adaptive Intervention Engine (escalating) |
       |   Hint > Analogy > Diagram > Worked Example |
       |            > AI Micro-Video (30s)           |
       +----------------------+----------------------+
                              |
                              v
       +---------------------------------------------+
       |          Domain-Transfer Challenge          |
       +----------------------+----------------------+
                              |
                              v
       +---------------------------------------------+
       |  Confidence-Mastery Gap & Forgetting Curve  |
       +---------------------------------------------+
```

---

## 5. Feature Set

### Feature 1 — Universal Learning Ingestion & Concept Dependency Graph
Accepts PDFs, PPT/PPTX, DOC/DOCX, research papers, lecture notes, handwritten notes, photos of textbooks, and syllabus documents. The system extracts concepts, formulas, examples, diagrams, and references, then structures them as a **directed acyclic graph (DAG)** where nodes are sub-concepts and edges are prerequisite relationships.

Example:
```
Differential Equations → Laplace Transform → Transfer Function → Root Locus
```

This graph becomes the hidden mastery model the student must teach back to the classroom.

### Feature 2 — Pre-Assessment Self-Confidence Gauge
Before entering the classroom, the student is shown the generated syllabus and asked:
*"On a scale of 0–100%, how well do you understand this topic?"*
This establishes the baseline used later to measure the **illusion of competence**.

### Feature 3 — The Multi-Agent Swarm (AI Classroom)
Three AI students with distinct cognitive profiles:

| Agent | Emoji | Behavior |
|---|---|---|
| **The Novice** | 👦 Timmy | Hates jargon, needs simple analogies, gets confused by complex equations unless simplified |
| **The Skeptic** | 👧 Sasha | Aggressively probes logical loops, loose connections, and weak evidence |
| **The Extrapolator** | 🧑‍🦱 Mr. Bright | Stretches the student's explanation to absurd logical extremes to test boundary conditions |

### Feature 4 — Interactive Multimodal Whiteboard
A shared canvas (powered by Excalidraw) where the student can sketch structures, write equations, or drag in photos of handwritten work. Agents "read" the drawing via vision APIs and base their follow-up questions on both the spoken/typed transcript and the canvas layout.

### Feature 5 — Hidden Mastery Rubric
The student sees a visual board of required concepts, each in one of three states:

- `Unexplained` (Gray)
- `Partially Explained` (Amber)
- `Mastered` (Green)

A node is only marked **mastered** once the student defines it, illustrates it, applies it in context, and defeats its associated misconception.

### Feature 6 — Adaptive Intervention Engine *(includes new video feature)*
Feynman AI never hands over the answer. When a student is stuck or triggers a misconception, the platform escalates through a strict hierarchy — intervening only as much as necessary before demanding the student teach again:

```
Hint → Analogy → Diagram → Worked Example → 30-second AI-Generated Micro-Video
```

- Each level is tried first; the system only escalates if the student is still stuck after re-attempting the explanation.
- The **micro-video** is the final, highest-support intervention: a short (~30s) AI-generated visual explanation targeted precisely at the failed concept and the specific misconception triggered — not a generic lesson.
- Example trigger:
  - Understanding: 34%
  - Stuck concept: *Laplace differentiation property*
  - Recommended intervention: *30-second visual explanation*
- After any intervention (including the video), the loop does not end — the student must immediately re-teach the concept to the classroom. Mastery is only ever demonstrated through explanation, never by watching.

### Feature 7 — Domain-Transfer Challenge
Once all rubric nodes are mastered, the Extrapolator issues a transfer problem that applies the concept to a novel context:

> *"You explained how a PID controller works in cruise control. Now, how would the proportional and integral values change if we applied this system to keep a drone stable in turbulent crosswinds?"*

Successful transfer is used as evidence of genuine (non-illusory) understanding.

### Feature 8 — Confidence Calibration Engine / Illusion of Competence Analysis
The final dashboard compares the student's initial confidence score against actual rubric mastery:

```
Confidence: 92%
Mastery:    61%
Calibration Score: 66%
```

This exposes the gap and pinpoints the exact misconceptions surfaced during the session.

### Feature 9 — Ebbinghaus Forgetting Curve Prediction
The system tracks teaching efficacy (hesitations, wrong statements, misconceptions triggered, and how much intervention support — including video — was required) and predicts retention decay:

$$R(t) = e^{-\frac{t}{S}}$$

Where $S$ is a memory strength score computed from session dynamics (see §7). The platform automatically schedules review sessions once predicted retention drops below 50%.

---

## 6. Data Schemas

### Zustand Store (`src/store/useStore.ts`)

```typescript
export type InterventionLevel =
  | "hint"
  | "analogy"
  | "diagram"
  | "worked_example"
  | "micro_video";

export interface InterventionRecord {
  nodeId: string;
  level: InterventionLevel;
  videoUrl?: string;        // populated only when level === "micro_video"
  videoDurationSeconds?: number;
  triggeredAt: string;      // ISO timestamp
}

export interface ConceptNode {
  id: string;
  title: string;
  description: string;
  status: "unexplained" | "partially_explained" | "mastered";
  misconception: string;
  prerequisites: string[];
  interventionsUsed: InterventionRecord[];
  highestInterventionLevel: InterventionLevel | null;
}

export interface Agent {
  id: "novice" | "skeptic" | "extrapolator";
  name: string;
  emoji: string;
  color: string;
  dialogue: string;
  status: "idle" | "thinking" | "speaking";
}

export interface SessionProfile {
  topic: string;
  initialConfidence: number;
  finalScore: number;
  misconceptionsTriggered: string[];
  interventionsUsed: InterventionRecord[];
  microVideosGenerated: number;
  durationSeconds: number;
  decayRate: number; // S value for Ebbinghaus equation
}

export interface AppState {
  nodes: ConceptNode[];
  agents: Agent[];
  profile: SessionProfile | null;
  stage: "upload" | "confidence" | "classroom" | "intervention" | "transfer" | "analytics";
  whiteboardBase64: string | null;
  activeIntervention: InterventionRecord | null;
}
```

---

## 7. API Spec & Prompt Engineering

### `POST /api/ingest`
**Payload:** form data containing file upload (PDF/PPTX/PNG).

**Response:**
```json
{
  "topic": "State Space Control",
  "nodes": [
    {
      "id": "matrix_representation",
      "title": "State Vector Matrix Form",
      "description": "Representing linear differential equations in modern state-space vectors.",
      "misconception": "Thinking state variables must always represent physical components.",
      "prerequisites": []
    },
    {
      "id": "eigenvalues",
      "title": "Eigenvalues & System Stability",
      "description": "Analyzing pole locations using matrix eigenvalues.",
      "misconception": "Confusing eigenvalues with eigenvectors regarding scale factors.",
      "prerequisites": ["matrix_representation"]
    }
  ]
}
```

### `POST /api/orchestrate`
**Payload:**
```json
{
  "transcript": "Let's look at the eigenvalues of matrix A. If they lie in the left half plane...",
  "whiteboardBase64": "data:image/png;base64,...",
  "nodes": [...]
}
```

**System Prompt for the Orchestrator:**
```text
You are the Cognitive Orchestrator for Feynman AI.
Review the human teacher's transcript and their whiteboard image (which contains diagrams/equations).

Compare their input to the concept nodes:
1. Did they explain a node correctly? If so, mark it 'mastered' or 'partially_explained'.
2. Did they use excessive jargon without explaining it? If so, set nextAgent to 'novice'.
3. Did they make a logical leap or write a conflicting equation? If so, set nextAgent to 'skeptic'.
4. Is the student stuck or repeatedly failing the same node? If so, set nextAction to 'intervene'
   and recommend an interventionLevel following the hierarchy: hint -> analogy -> diagram ->
   worked_example -> micro_video. Only recommend 'micro_video' if lower levels have already
   been tried for this node in this session.
5. Have they explained all core concepts? If so, set nextAgent to 'extrapolator' and transition
   to the Transfer Test.

Output ONLY JSON:
{
  "updatedNodes": [{ "id": "eigenvalues", "status": "mastered" }],
  "nextAgent": "novice" | "skeptic" | "extrapolator",
  "nextAction": "continue" | "intervene",
  "interventionLevel": "hint" | "analogy" | "diagram" | "worked_example" | "micro_video" | null,
  "speech": "The question or comment the student will say."
}
```

### `POST /api/intervention`  — *new endpoint powering the video feature*
Called whenever the orchestrator returns `"nextAction": "intervene"`. Generates the appropriate support asset for the stuck concept, escalating to a short AI-generated video only at the top of the hierarchy.

**Payload:**
```json
{
  "nodeId": "eigenvalues",
  "misconception": "Confusing eigenvalues with eigenvectors regarding scale factors.",
  "interventionLevel": "micro_video",
  "priorInterventions": ["hint", "analogy", "diagram", "worked_example"]
}
```

**Response:**
```json
{
  "nodeId": "eigenvalues",
  "level": "micro_video",
  "content": {
    "script": "A tight 30-second script targeted at the exact misconception.",
    "videoUrl": "https://cdn.feynman.ai/interventions/eigenvalues-scale-factors.mp4",
    "durationSeconds": 30
  },
  "reteachPrompt": "Now explain eigenvalues and system stability back to the class, in your own words."
}
```

**System prompt for the video-generation step:**
```text
You are the Intervention Content Generator for Feynman AI.
You have been called because the student has already tried a hint, an analogy, a diagram,
and a worked example for this node and is still stuck on the specific misconception provided.

Generate a script for a 30-second micro-video that:
1. Targets ONLY the specific misconception — do not re-teach the whole concept.
2. Uses one concrete visual analogy or example.
3. Ends with a direct callback prompting the student to re-explain the concept themselves.

This is the highest-support intervention in the hierarchy. After this, the student must
immediately re-teach the concept — the video is a bridge back to teaching, not a replacement for it.

Output ONLY JSON:
{
  "script": "...",
  "visualDirections": "...",
  "reteachPrompt": "..."
}
```

---

## 8. Ebbinghaus Memory Retention Math

Memory strength $S$ is calculated dynamically from student errors and how much intervention support was required (including whether a micro-video was needed):

$$S = \text{base\_strength} \times \left(1 - \frac{\text{misconceptions\_triggered}}{\text{total\_nodes}}\right) \times \left(\frac{\text{final\_score}}{100}\right) \times \left(1 - \frac{\text{micro\_videos\_used}}{\text{total\_nodes}} \times 0.5\right)$$

Concepts that required a micro-video intervention are weighted as more fragile, since reaching the top of the intervention hierarchy indicates the student needed the most external support before re-teaching successfully. This value feeds the decay model to predict how many days the student has before forgetting the topic, plotted as a visual decay curve on the dashboard.

---

## 9. Implementation Plan Checkpoints

- **Checkpoint 1:** PDF/Image upload parsing to generate JSON dependency graphs.
- **Checkpoint 2:** Excalidraw integration and Base64 whiteboard change tracking.
- **Checkpoint 3:** Realtime agent state changes (Zustand) triggered by backend orchestration logic.
- **Checkpoint 4:** Adaptive Intervention Engine — hint/analogy/diagram/worked-example tiers, with escalation logic and re-teach enforcement.
- **Checkpoint 5:** AI-generated micro-video intervention — `/api/intervention` video pipeline, storage/CDN delivery, and mandatory re-teach step after playback.
- **Checkpoint 6:** Transfer test phase transitions and visual confidence-mastery gap analytics.
- **Checkpoint 7:** Ebbinghaus forgetting-curve dashboard and automated review scheduling.

---

## 10. Tech Stack Summary

- **Frontend:** React + Zustand for state, Excalidraw for the whiteboard canvas.
- **Ingestion:** PDF/PPTX/image parsing → LLM concept-graph extraction.
- **Orchestration:** LLM-driven cognitive orchestrator (multimodal: transcript + whiteboard image).
- **Intervention media:** Escalating text/diagram generation, culminating in short AI-generated video clips for the highest-support tier.
- **Analytics:** Confidence-mastery gap scoring, Ebbinghaus-based forgetting curve, automated review scheduling.
#   F e y n m a n - A I  
 