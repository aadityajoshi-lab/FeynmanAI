import type { Notebook, NotebookArtifact, NotebookArtifactType } from "./notebookTypes";

const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1").replace(/\/$/, "");

async function parseError(response: Response, fallback: string) {
  try {
    const body = await response.json() as { error?: { message?: string } | string; message?: string };
    return (typeof body.error === "string" ? body.error : body.error?.message) || body.message || fallback;
  } catch { return fallback; }
}

export async function createNotebook(input: { title: string; subject?: string; description?: string; learningGoal: string; ocrProvider: "auto" | "local" | "mistral" }): Promise<Notebook> {
  const response = await fetch(`${API_BASE}/notebooks`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input) });
  if (!response.ok) throw new Error(await parseError(response, `Notebook creation failed (${response.status})`));
  return response.json() as Promise<Notebook>;
}

export async function uploadNotebookSource(notebookId: string, file: File, input: { sourceKind: "reference" | "past_questions"; ocrProvider: "auto" | "local" | "mistral" }): Promise<Notebook> {
  const body = new FormData();
  body.append("file", file);
  body.append("sourceKind", input.sourceKind);
  body.append("ocrProvider", input.ocrProvider);
  const response = await fetch(`${API_BASE}/notebooks/${notebookId}/sources`, { method: "POST", body });
  if (!response.ok) throw new Error(await parseError(response, `Source processing failed (${response.status})`));
  return response.json() as Promise<Notebook>;
}

export async function getNotebook(notebookId: string): Promise<Notebook> {
  const response = await fetch(`${API_BASE}/notebooks/${notebookId}`, { cache: "no-store" });
  if (!response.ok) throw new Error(await parseError(response, `Notebook could not be loaded (${response.status})`));
  return response.json() as Promise<Notebook>;
}

export async function createNotebookArtifact(notebookId: string, type: NotebookArtifactType): Promise<NotebookArtifact> {
  const response = await fetch(`${API_BASE}/notebooks/${notebookId}/artifacts`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ type }) });
  if (!response.ok) throw new Error(await parseError(response, `Output generation failed (${response.status})`));
  return response.json() as Promise<NotebookArtifact>;
}

export async function askNotebook(notebookId: string, question: string): Promise<{ answer: string; sourceIds: string[]; sourceAnchorIds?: string[]; sectionIds?: string[]; groundedIn?: string; webSources?: Array<{ title: string; url: string; snippet?: string }> }> {
  const response = await fetch(`${API_BASE}/notebooks/${notebookId}/ask`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question, allowWebSearch: true }) });
  if (!response.ok) throw new Error(await parseError(response, `Notebook question failed (${response.status})`));
  return response.json();
}

export async function createNotebookLesson(notebookId: string, question: string, requestedDurationSeconds = 120): Promise<NotebookArtifact> {
  const response = await fetch(`${API_BASE}/notebooks/${notebookId}/lessons`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, allowWebSearch: true, requestedDurationSeconds }),
  });
  if (!response.ok) throw new Error(await parseError(response, `Narrated lesson failed (${response.status})`));
  return response.json() as Promise<NotebookArtifact>;
}
