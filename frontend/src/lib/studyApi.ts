export type StudySourceIngestResponse = {
  sourceId: string;
  filename?: string;
  title?: string;
  sourceKind?: string;
  status: string;
  approvalStatus: string;
  autoApproved: boolean;
  publishable: boolean;
  extraction: { status: string; method?: string; pageCandidateCount?: number };
  candidates: Array<{ candidateId: string; text: string; locator: Record<string, unknown>; status: string }>;
};

export type StudyPlanResponse = {
  state?: string;
  reasonCode?: string;
  studyPlanId?: string;
  sourceIds?: string[];
  chapterSelection?: "chapter_1" | "all";
  providerMode: "codex_fixture" | "live_openai" | "live_fireworks" | "human_review";
  sourcePackVersion: string;
  recordVersion: number;
  outline?: Array<{ conceptId: string; title: string; objective: string; sourceAnchorIds: string[] }>;
  scenes?: StudyScene[];
  pastQuestionAnalysis?: string[];
  reviewRequired?: boolean;
};

export type StudyAction = { actionId: string; kind: string; label: string; payload: Record<string, unknown>; durationMs?: number | null };
export type StudyCheckpoint = { kind: "predict" | "retrieval" | "teach_back" | "exam_bridge"; prompt: string; responseType: "single_choice" | "short_text" | "long_text"; options?: string[] | null; sourceAnchorIds: string[] };
export type StudyStage = { stageId: string; kind: "definition" | "mcq" | "formula" | "diagram" | "numerical" | "teach_back"; title: string; prompt: string; responseType: "none" | "single_choice" | "short_text" | "long_text" | "file"; options?: string[] | null; sourceAnchorIds: string[] };
export type StudyScene = { sceneId: string; conceptId: string; type: string; title: string; explanation?: string; keyPoints?: string[]; workedExample?: string | null; commonMistakes?: string[]; sourceAnchorIds: string[]; actions?: StudyAction[]; config?: Record<string, unknown>; checkpoint?: StudyCheckpoint | null; stages?: StudyStage[] };
export type StudyInteractionResponse = { state?: string; prediction?: string; explanation?: string; prompt?: string; answer?: string; reasonCode?: string; correct?: boolean; understandingScore?: number; confidenceScore?: number; overconfidence?: boolean; feedback?: string; remediation?: string; mistake?: string; correctAnswer?: string; correction?: string; nextAction?: "advance" | "retry" | "review"; retryPrompt?: string | null; retryOptions?: string[] | null; retryResponseType?: StudyStage["responseType"] | null; retrySourceAnchorIds?: string[]; sourceAnchorIds: string[]; providerMode: "codex_fixture" | "live_openai" | "live_fireworks" | "human_review"; sourcePackVersion: string; recordVersion: number; reviewRequired?: boolean };
export type StudyChatAction = { kind: "none" | "next_scene" | "previous_scene" | "open_scene" | "focus_checkpoint" | "show_visualization" | "repeat_explanation" | "set_learning_mode"; sceneId?: string | null; modeId?: string | null; reason?: string };
export type StudyChatMessage = { role: "user" | "assistant"; content: string };
export type StudyChatResponse = { state: "answered" | "abstained" | "needs_human_review" | "action_only"; reply: string; reasonCode?: string | null; sourceAnchorIds: string[]; action: StudyChatAction; providerMode: "codex_fixture" | "live_openai" | "live_fireworks" | "human_review"; sourcePackVersion: string; recordVersion: number; reviewRequired?: boolean };

export type ProviderStatus = { id: "fireworks" | "openai" | "fixture"; label: string; available: boolean; model: string };

const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1").replace(/\/$/, "");

async function parseError(response: Response, fallback: string) {
  try {
    const body = await response.json() as { error?: { message?: string } };
    return body.error?.message || fallback;
  } catch {
    return fallback;
  }
}

export async function ingestStudySource(file: File, metadata?: { subjectId?: string; moduleId?: string; sourceKind?: "notes" | "past_questions" }): Promise<StudySourceIngestResponse> {
  const body = new FormData();
  body.append("file", file);
  if (metadata?.subjectId) body.append("subjectId", metadata.subjectId);
  if (metadata?.moduleId) body.append("moduleId", metadata.moduleId);
  if (metadata?.sourceKind) body.append("sourceKind", metadata.sourceKind);
  const response = await fetch(`${API_BASE}/study-sources/ingest`, { method: "POST", body });
  if (!response.ok) throw new Error(await parseError(response, `Upload failed (${response.status})`));
  return response.json() as Promise<StudySourceIngestResponse>;
}

export async function ingestStudyUrl(url: string, metadata?: { subjectId?: string; moduleId?: string; title?: string; sourceKind?: string }): Promise<StudySourceIngestResponse> {
  const response = await fetch(`${API_BASE}/study-sources/ingest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, ...metadata }),
  });
  if (!response.ok) throw new Error(await parseError(response, `Source URL failed (${response.status})`));
  return response.json() as Promise<StudySourceIngestResponse>;
}

export async function generateStudyPlan(input: { subjectId: string; subjectTitle?: string; moduleId?: string; sourceIds: string[]; pastQuestionSourceIds?: string[]; chapterSelection: "chapter_1" | "all"; provider?: "fireworks" | "openai" | "fixture" }): Promise<StudyPlanResponse> {
  const response = await fetch(`${API_BASE}/study-plans`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!response.ok) throw new Error(await parseError(response, `Study plan failed (${response.status})`));
  return response.json() as Promise<StudyPlanResponse>;
}

export async function getProviderStatus(): Promise<{ providers: ProviderStatus[]; defaultProvider: string }> {
  const response = await fetch(`${API_BASE}/providers`, { cache: "no-store" });
  if (!response.ok) throw new Error(`Provider status failed (${response.status})`);
  return response.json() as Promise<{ providers: ProviderStatus[]; defaultProvider: string }>;
}

export async function interactWithStudyPlan(input: { sourceIds: string[]; provider: "fireworks" | "openai" | "fixture"; kind: "mcq" | "predict" | "retrieval" | "formula" | "diagram" | "numerical" | "teach_back" | "exam_bridge"; response: string; confidence: number; attachment?: { name: string; mimeType: string; dataUrl: string } | null; scene: { sceneId: string; prompt?: string; explanation?: string; responseType?: string; sourceAnchorIds: string[]; stage?: { stageId: string; kind: string; title: string; prompt: string; responseType: string; options?: string[] | null; sourceAnchorIds: string[] } } }): Promise<StudyInteractionResponse> {
  const response = await fetch(`${API_BASE}/study-plans/interactions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!response.ok) throw new Error(await parseError(response, `Checkpoint failed (${response.status})`));
  return response.json() as Promise<StudyInteractionResponse>;
}

export async function chatWithStudyPlan(input: {
  subjectId: string;
  subjectTitle?: string;
  moduleId?: string;
  sourceIds: string[];
  provider: "fireworks" | "openai" | "fixture";
  message: string;
  history: StudyChatMessage[];
  activeSceneId?: string | null;
  activeSceneIndex: number;
  learningMode: string;
  scenes: Array<{ sceneId: string; title: string; type: string; hasVisualization: boolean; hasCheckpoint: boolean }>;
}): Promise<StudyChatResponse> {
  const response = await fetch(`${API_BASE}/study-plans/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!response.ok) throw new Error(await parseError(response, `Module chat failed (${response.status})`));
  return response.json() as Promise<StudyChatResponse>;
}
