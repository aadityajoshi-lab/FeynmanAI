import type { Notebook, NotebookArtifact, NotebookArtifactType, NotebookChatMessage, NotebookListItem, NotebookNote } from "./notebookTypes";
import { getAuthToken, LearningOsApiError } from "./learningOsApi";

const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000/api/v1").replace(/\/$/, "");

function csrfToken() {
  if (typeof document === "undefined") return undefined;
  const cookie = document.cookie.split("; ").find((item) => item.startsWith("csrftoken="));
  return cookie ? decodeURIComponent(cookie.slice("csrftoken=".length)) : undefined;
}

let csrfBootstrap: Promise<void> | null = null;

async function ensureCsrfToken() {
  if (typeof document === "undefined" || csrfToken()) return;
  if (!csrfBootstrap) {
    csrfBootstrap = fetch(`${API_BASE}/auth/csrf`, { credentials: "include" }).then((response) => {
      if (!response.ok) throw new Error("CSRF initialization failed");
    }).finally(() => { csrfBootstrap = null; });
  }
  await csrfBootstrap;
}

async function notebookFetch(path: string, init: RequestInit = {}) {
  const headers = new Headers(init.headers);
  const method = (init.method || "GET").toUpperCase();
  const unsafe = !["GET", "HEAD", "OPTIONS"].includes(method);
  try {
    const authToken = await getAuthToken();
    if (authToken) headers.set("Authorization", `Bearer ${authToken}`);
    if (unsafe && !authToken) await ensureCsrfToken();
    const token = csrfToken();
    if (unsafe && !authToken && token && !headers.has("X-CSRFToken")) headers.set("X-CSRFToken", token);
    return await fetch(path, { ...init, headers, credentials: "include" });
  } catch {
    throw new LearningOsApiError("Feynman's local source service is unavailable. Start the backend on 127.0.0.1:8000, then refresh this page.", 0, "service_unavailable");
  }
}

async function parseError(response: Response, fallback: string) {
  try {
    const body = await response.json() as { error?: { message?: string } | string; message?: string };
    return (typeof body.error === "string" ? body.error : body.error?.message) || body.message || fallback;
  } catch { return fallback; }
}

async function json<T>(response: Response, fallback: string): Promise<T> {
  if (!response.ok) throw new LearningOsApiError(await parseError(response, fallback), response.status);
  return response.json() as Promise<T>;
}

export async function listNotebooks(): Promise<NotebookListItem[]> {
  const result = await json<{ notebooks: NotebookListItem[] }>(await notebookFetch(`${API_BASE}/notebooks`, { cache: "no-store" }), "Source desks could not be loaded");
  return result.notebooks;
}

export async function createNotebook(input: { title: string; subject?: string; description?: string; learningGoal: string; ocrProvider: "auto" | "local" | "mistral"; goalId?: string; courseId?: string }): Promise<Notebook> {
  return json<Notebook>(await notebookFetch(`${API_BASE}/notebooks`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input) }), "Notebook creation failed");
}

export async function uploadNotebookSource(notebookId: string, file: File, input: { sourceKind: "reference" | "past_questions"; ocrProvider: "auto" | "local" | "mistral"; useForGrounding?: boolean }): Promise<Notebook> {
  const body = new FormData();
  body.append("file", file);
  body.append("sourceKind", input.sourceKind);
  body.append("ocrProvider", input.ocrProvider);
  if (input.useForGrounding !== undefined) body.append("useForGrounding", String(input.useForGrounding));
  return json<Notebook>(await notebookFetch(`${API_BASE}/notebooks/${notebookId}/sources`, { method: "POST", body }), "Source processing failed");
}

/** Re-submit a user-selected file for a failed extraction. The original raw
 * bytes are intentionally not retained by the service, so callers must pass
 * a newly selected File rather than attempting a silent replay. */
export async function retryNotebookSource(notebookId: string, sourceId: string, file: File, input: { sourceKind?: string; ocrProvider?: "auto" | "local" | "mistral"; title?: string; useForGrounding?: boolean } = {}): Promise<Notebook> {
  const body = new FormData();
  body.append("file", file);
  if (input.sourceKind) body.append("sourceKind", input.sourceKind);
  if (input.ocrProvider) body.append("ocrProvider", input.ocrProvider);
  if (input.title) body.append("title", input.title);
  if (input.useForGrounding !== undefined) body.append("useForGrounding", String(input.useForGrounding));
  return json<Notebook>(await notebookFetch(`${API_BASE}/notebooks/${notebookId}/sources/${sourceId}/retry`, { method: "POST", body }), "Source extraction retry failed");
}

export async function addNotebookTextSource(notebookId: string, input: { text?: string; url?: string; title?: string; sourceKind?: "pasted_notes" | "typed_text" | "url_reference" | "reference"; useForGrounding?: boolean; fetchWebsite?: boolean; ocrProvider?: "auto" | "local" | "mistral" }): Promise<Notebook> {
  return json<Notebook>(await notebookFetch(`${API_BASE}/notebooks/${notebookId}/sources/text`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  }), "Source context could not be added");
}

export async function createBlankNotebookNote(notebookId: string, input: { title?: string }): Promise<NotebookNote> {
  return json<NotebookNote>(await notebookFetch(`${API_BASE}/notebooks/${notebookId}/notes/blank`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  }), "Blank personal note could not be created");
}

export async function deleteNotebookSource(notebookId: string, sourceId: string): Promise<Notebook> {
  return json<Notebook>(await notebookFetch(`${API_BASE}/notebooks/${notebookId}/sources/${sourceId}`, { method: "DELETE" }), "Source removal failed");
}

export async function getNotebook(notebookId: string): Promise<Notebook> {
  return json<Notebook>(await notebookFetch(`${API_BASE}/notebooks/${notebookId}`, { cache: "no-store" }), "Notebook could not be loaded");
}

export async function getNotebookChatHistory(notebookId: string): Promise<NotebookChatMessage[]> {
  const result = await json<{ messages: NotebookChatMessage[] }>(await notebookFetch(`${API_BASE}/notebooks/${notebookId}/chat`, { cache: "no-store" }), "Chat history could not be loaded");
  return result.messages;
}

export async function createNotebookArtifact(notebookId: string, type: Exclude<NotebookArtifactType, "openmaic_lesson">, sourceIds?: string[]): Promise<NotebookArtifact> {
  return json<NotebookArtifact>(await notebookFetch(`${API_BASE}/notebooks/${notebookId}/artifacts`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ type, ...(sourceIds ? { sourceIds } : {}) }),
  }), "Output generation failed");
}

export async function askNotebook(notebookId: string, question: string, sourceIds?: string[]): Promise<{ answer: string; sourceIds: string[]; sourceAnchorIds: string[]; groundedIn?: string; degraded?: boolean; providerUnavailable?: boolean; providerMessage?: string; messages: { user: NotebookChatMessage; assistant: NotebookChatMessage } }> {
  return json(await notebookFetch(`${API_BASE}/notebooks/${notebookId}/ask`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question, ...(sourceIds ? { sourceIds } : {}) }),
  }), "Notebook question failed");
}

export async function createNotebookLesson(notebookId: string, question: string, requestedDurationSeconds = 120, sourceIds?: string[]): Promise<NotebookArtifact> {
  return json<NotebookArtifact>(await notebookFetch(`${API_BASE}/notebooks/${notebookId}/lessons`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question, requestedDurationSeconds, ...(sourceIds ? { sourceIds } : {}) }),
  }), "Narrated lesson failed");
}

export async function createNotebookNote(notebookId: string, input: { title?: string; content: string; sourceIds?: string[]; sourceAnchorIds?: string[] }): Promise<NotebookNote> {
  return json<NotebookNote>(await notebookFetch(`${API_BASE}/notebooks/${notebookId}/notes`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input),
  }), "Note could not be saved");
}

export async function updateNotebookNote(notebookId: string, noteId: string, input: { title?: string; content?: string }): Promise<NotebookNote> {
  return json<NotebookNote>(await notebookFetch(`${API_BASE}/notebooks/${notebookId}/notes/${noteId}`, {
    method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input),
  }), "Note could not be updated");
}

export async function deleteNotebookNote(notebookId: string, noteId: string): Promise<void> {
  const response = await notebookFetch(`${API_BASE}/notebooks/${notebookId}/notes/${noteId}`, { method: "DELETE" });
  if (!response.ok) throw new Error(await parseError(response, "Note could not be removed"));
}
