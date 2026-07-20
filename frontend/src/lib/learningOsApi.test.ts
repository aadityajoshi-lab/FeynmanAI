import { afterEach, describe, expect, it, vi } from "vitest";
import { LearningOsApiError, learningOsApi, setAuthSignOut, setAuthTokenGetter, signOutCurrentAuth } from "./learningOsApi";

const fetchMock = vi.fn();

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), { status, headers: { "Content-Type": "application/json" } });
}

afterEach(() => {
  fetchMock.mockReset();
  vi.unstubAllGlobals();
  setAuthTokenGetter(null);
  setAuthSignOut(null);
});

describe("Learning OS API contracts", () => {
  it("clears the legacy API session before the Clerk session", async () => {
    vi.stubGlobal("fetch", fetchMock.mockResolvedValue(jsonResponse({ signedOut: true })));
    const clerkSignOut = vi.fn().mockResolvedValue(undefined);
    setAuthSignOut(clerkSignOut);

    await signOutCurrentAuth();

    expect(fetchMock.mock.calls[0][0]).toContain("/auth/logout");
    expect(clerkSignOut).toHaveBeenCalledTimes(1);
  });

  it("sends a fresh Clerk bearer token and skips CSRF bootstrap", async () => {
    vi.stubGlobal("fetch", fetchMock.mockResolvedValue(jsonResponse({ user: {}, profile: {} })));
    setAuthTokenGetter(async () => "clerk-session-token");

    await learningOsApi.me();

    const [, init] = fetchMock.mock.calls[0];
    expect(new Headers(init.headers).get("Authorization")).toBe("Bearer clerk-session-token");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("creates a visible learning contract inside an authenticated workspace", async () => {
    vi.stubGlobal("document", { cookie: "csrftoken=local-csrf-token" });
    vi.stubGlobal("fetch", fetchMock.mockResolvedValue(jsonResponse({ goalId: "goal-1" }, 201)));

    await learningOsApi.createGoal({ title: "Learn DSP", description: "Sampling and aliasing", outcome: "Explain it", currentLevel: "beginner", timeBudget: "Flexible", contract: { confidence: "uncertain", prerequisites: ["Wave basics"], learnerCorrection: "Prioritize the conceptual gap." } });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain("/goals");
    expect(init.credentials).toBe("include");
    expect(new Headers(init.headers).get("X-CSRFToken")).toBe("local-csrf-token");
    expect(JSON.parse(init.body)).toMatchObject({ title: "Learn DSP", currentLevel: "beginner", contract: { confidence: "uncertain", prerequisites: ["Wave basics"], learnerCorrection: "Prioritize the conceptual gap." } });
  });

  it("bootstraps a CSRF cookie before an unsafe request when the browser has none", async () => {
    let cookie = "";
    vi.stubGlobal("document", { get cookie() { return cookie; } });
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockImplementationOnce(async () => {
      cookie = "csrftoken=bootstrapped-token";
      return jsonResponse({ csrf: true });
    }).mockResolvedValueOnce(jsonResponse({ goalId: "goal-2" }, 201));

    await learningOsApi.createGoal({ title: "Trace a scheduler", description: "", outcome: "", currentLevel: "beginner", timeBudget: "Flexible" });

    expect(fetchMock.mock.calls[0][0]).toContain("/auth/csrf");
    const [, init] = fetchMock.mock.calls[1];
    expect(new Headers(init.headers).get("X-CSRFToken")).toBe("bootstrapped-token");
  });

  it("uses goal-scoped source context endpoints", async () => {
    vi.stubGlobal("document", { cookie: "csrftoken=local-csrf-token" });
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockResolvedValueOnce(jsonResponse({ goalId: "goal-1", notebooks: [] })).mockResolvedValueOnce(jsonResponse({ goalId: "goal-1", notebooks: [] }));

    await learningOsApi.goalSources("goal-1");
    await learningOsApi.attachGoalNotebook("goal-1", "notebook-1");

    expect(fetchMock.mock.calls[0][0]).toContain("/goals/goal-1/sources");
    expect(fetchMock.mock.calls[1][0]).toContain("/goals/goal-1/sources");
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ notebookId: "notebook-1" });
  });

  it("compiles a source-grounded curriculum through the goal-scoped endpoint", async () => {
    vi.stubGlobal("document", { cookie: "csrftoken=local-csrf-token" });
    vi.stubGlobal("fetch", fetchMock.mockResolvedValue(jsonResponse({ curriculum: { packId: "pack-1", version: 1 }, goal: {} }, 201)));

    await learningOsApi.compileCurriculum("goal-1", { sourceIds: ["source-1"], learnerLevel: "beginner" });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain("/goals/goal-1/curriculum");
    expect(JSON.parse(init.body)).toEqual({ sourceIds: ["source-1"], learnerLevel: "beginner" });
  });

  it("persists a learner route correction through the curriculum preview endpoint", async () => {
    vi.stubGlobal("document", { cookie: "csrftoken=local-csrf-token" });
    vi.stubGlobal("fetch", fetchMock.mockResolvedValue(jsonResponse({ curriculum: { packId: "pack-1", version: 1 }, goal: {} })));

    await learningOsApi.updateCurriculum("goal-1", { activityOrder: ["activity-2", "activity-1"], learnerNote: "Start with the prerequisite." });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain("/goals/goal-1/curriculum");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body)).toEqual({ activityOrder: ["activity-2", "activity-1"], learnerNote: "Start with the prerequisite." });
  });

  it("submits an observable activity attempt rather than a generic chat message", async () => {
    vi.stubGlobal("fetch", fetchMock.mockResolvedValue(jsonResponse({ evidence: {}, goal: {} })));

    await learningOsApi.submitAttempt("goal-1", { activityId: "activity-1", response: "My predicted mechanism has a concrete case and an uncertainty." });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain("/goals/goal-1/attempts");
    expect(JSON.parse(init.body)).toEqual({ activityId: "activity-1", response: "My predicted mechanism has a concrete case and an uncertainty." });
  });

  it("preserves non-secret provider feedback from an activity attempt", async () => {
    vi.stubGlobal("fetch", fetchMock.mockResolvedValue(jsonResponse({
      evidence: { status: "observed" },
      feedback: { provider: "fireworks", model: "configured-model", providerAttempt: "failed", retryAvailable: true, retryAction: "resubmit_attempt", sourceAnchorIds: [], uncertainty: "high" },
      goal: {},
    })));

    const result = await learningOsApi.submitAttempt("goal-1", { activityId: "activity-1", response: "A concrete response that can be evaluated and retried." });

    expect(result.feedback).toMatchObject({ provider: "fireworks", providerAttempt: "failed", retryAvailable: true, retryAction: "resubmit_attempt" });
    expect(result.feedback).not.toHaveProperty("apiKey");
  });

  it("uses a revocable DELETE request for shared evidence", async () => {
    vi.stubGlobal("fetch", fetchMock.mockResolvedValue(jsonResponse({ shareId: "share-1", active: false })));

    await learningOsApi.revokeShare("share-1");

    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/shares/share-1"), expect.objectContaining({ method: "DELETE", credentials: "include" }));
  });

  it("keeps learner memory and course sharing as distinct privacy controls", async () => {
    vi.stubGlobal("document", { cookie: "csrftoken=local-csrf-token" });
    vi.stubGlobal("fetch", fetchMock.mockResolvedValue(jsonResponse({ learnerMemoryEnabled: true, courseSharingEnabled: false, activeShares: 0 })));

    await learningOsApi.updatePrivacy({ courseSharingEnabled: false });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain("/privacy");
    expect(JSON.parse(init.body)).toEqual({ courseSharingEnabled: false });
  });

  it("turns a local API transport failure into a recoverable service error", async () => {
    vi.stubGlobal("fetch", fetchMock.mockRejectedValue(new TypeError("Failed to fetch")));

    await expect(learningOsApi.me()).rejects.toMatchObject({
      name: "LearningOsApiError",
      status: 0,
      code: "service_unavailable",
    } satisfies Partial<LearningOsApiError>);
  });
});
