import { afterEach, describe, expect, it, vi } from "vitest";
import { addNotebookTextSource, askNotebook, createNotebookArtifact, createNotebook, deleteNotebookSource, listNotebooks, retryNotebookSource } from "./notebookApi";
import { setAuthTokenGetter } from "./learningOsApi";

const fetchMock = vi.fn();

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), { status, headers: { "Content-Type": "application/json" } });
}

afterEach(() => {
  fetchMock.mockReset();
  vi.unstubAllGlobals();
  setAuthTokenGetter(null);
});

describe("notebook API source scope", () => {
  it("attaches a fresh Clerk bearer token to source-desk reads", async () => {
    setAuthTokenGetter(async () => "clerk-session-token");
    vi.stubGlobal("fetch", fetchMock.mockResolvedValue(jsonResponse({ notebooks: [] })));

    await listNotebooks();

    const [, init] = fetchMock.mock.calls[0];
    expect(new Headers(init.headers).get("Authorization")).toBe("Bearer clerk-session-token");
  });

  it("lists only compact account-owned desk summaries for the universal context picker", async () => {
    vi.stubGlobal("fetch", fetchMock.mockResolvedValue(jsonResponse({ notebooks: [{ notebookId: "notebook-1", title: "Signals", status: "ready", sourceCount: 2, updatedAt: "2026-07-19T00:00:00Z" }] })));

    const notebooks = await listNotebooks();

    expect(notebooks).toEqual([expect.objectContaining({ notebookId: "notebook-1", sourceCount: 2 })]);
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/notebooks"), expect.objectContaining({ cache: "no-store", credentials: "include" }));
  });

  it("keeps course scope explicit when a new source desk is created", async () => {
    vi.stubGlobal("document", { cookie: "csrftoken=local-csrf-token" });
    vi.stubGlobal("fetch", fetchMock.mockResolvedValue(jsonResponse({ notebookId: "notebook-1" }, 201)));

    await createNotebook({ title: "Course reading", learningGoal: "understand", ocrProvider: "auto", courseId: "course-1" });

    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(init.body)).toMatchObject({ title: "Course reading", courseId: "course-1" });
  });

  it("sends selected source IDs with a notebook question and does not opt into web context", async () => {
    vi.stubGlobal("fetch", fetchMock.mockResolvedValue(jsonResponse({
      answer: "A grounded answer", sourceIds: ["source-a"], sourceAnchorIds: ["anchor-a"], groundedIn: "notebook",
      messages: { user: {}, assistant: {} },
    })));

    await askNotebook("notebook-1", "What is this?", ["source-a"]);

    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(init.body)).toEqual({ question: "What is this?", sourceIds: ["source-a"] });
  });

  it("uses the selected source IDs for Studio artifacts", async () => {
    vi.stubGlobal("fetch", fetchMock.mockResolvedValue(jsonResponse({ artifactId: "artifact-1", type: "mind_map", title: "Mind map", status: "ready", payload: {}, sourceIds: ["source-a"], createdAt: "2026-01-01T00:00:00Z" }, 201)));

    await createNotebookArtifact("notebook-1", "mind_map", ["source-a"]);

    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(init.body)).toEqual({ type: "mind_map", sourceIds: ["source-a"] });
  });

  it("calls the notebook-scoped source removal endpoint", async () => {
    vi.stubGlobal("fetch", fetchMock.mockResolvedValue(jsonResponse({ notebookId: "notebook-1" })));

    await deleteNotebookSource("notebook-1", "source-a");

    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/notebooks/notebook-1/sources/source-a"), expect.objectContaining({ method: "DELETE", credentials: "include" }));
  });

  it("retries a failed extraction only with a newly supplied file", async () => {
    vi.stubGlobal("document", { cookie: "csrftoken=local-csrf-token" });
    vi.stubGlobal("fetch", fetchMock.mockResolvedValue(jsonResponse({ notebookId: "notebook-1" }, 201)));
    const retryFile = new File(["fresh source bytes"], "retry.pdf", { type: "application/pdf" });

    await retryNotebookSource("notebook-1", "source-a", retryFile, { ocrProvider: "mistral", useForGrounding: true });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain("/notebooks/notebook-1/sources/source-a/retry");
    expect(init).toMatchObject({ method: "POST", credentials: "include" });
    expect((init.body as FormData).get("file")).toBe(retryFile);
    expect((init.body as FormData).get("ocrProvider")).toBe("mistral");
    expect((init.body as FormData).get("useForGrounding")).toBe("true");
  });

  it("keeps pasted text source-scoped and sends its grounding choice", async () => {
    vi.stubGlobal("fetch", fetchMock.mockResolvedValue(jsonResponse({ notebookId: "notebook-1" })));

    await addNotebookTextSource("notebook-1", { title: "Lecture notes", text: "A bounded source excerpt.", sourceKind: "pasted_notes", useForGrounding: false });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain("/notebooks/notebook-1/sources/text");
    expect(JSON.parse(init.body)).toMatchObject({ sourceKind: "pasted_notes", useForGrounding: false });
  });
});
