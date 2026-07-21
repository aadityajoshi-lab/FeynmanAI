import type { ActivityProviderFeedback, Course, CurrentUser, EvidenceRecord, GoalShare, GoalSourceContext, LearningContract, LearningGoal, LearningWorkspace, ShareGrant, StructuredActivityAttempt, CurriculumSummary } from "./learningOsTypes";

const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000/api/v1").replace(/\/$/, "");

type AuthTokenGetter = () => Promise<string | null>;
let authTokenGetter: AuthTokenGetter | null = null;
let authSignOut: (() => Promise<void>) | null = null;

export function setAuthTokenGetter(getter: AuthTokenGetter | null) {
  authTokenGetter = getter;
}

/** Return a fresh Clerk token for secondary API clients (for example the
 * notebook/source client). Never cache the token in learner state. */
export async function getAuthToken(): Promise<string | null> {
  return authTokenGetter ? authTokenGetter() : null;
}

export function setAuthSignOut(signOut: (() => Promise<void>) | null) {
  authSignOut = signOut;
}

export async function signOutCurrentAuth() {
  // Clear any legacy Django session as well as the Clerk session. The app
  // deliberately sends credentials with every request, so leaving the local
  // session alive would let a signed-out browser continue through workspace
  // APIs even after Clerk has revoked its session.
  try {
    await learningOsApi.logout();
  } finally {
    if (authSignOut) await authSignOut();
  }
}

export class LearningOsApiError extends Error {
  readonly status: number;
  readonly code?: string;

  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = "LearningOsApiError";
    this.status = status;
    this.code = code;
  }
}

function csrfToken() {
  if (typeof document === "undefined") return undefined;
  const cookie = document.cookie.split("; ").find((item) => item.startsWith("csrftoken="));
  return cookie ? decodeURIComponent(cookie.slice("csrftoken=".length)) : undefined;
}

let csrfBootstrap: Promise<void> | null = null;

let authBootstrapWait: Promise<void> | null = null;

async function waitForAuthBridge(timeoutMs = 3500) {
  if (typeof window === "undefined" || typeof document === "undefined" || document.documentElement?.dataset.feynmanAuth) return;
  if (!authBootstrapWait) {
    authBootstrapWait = new Promise<void>((resolve) => {
      let settled = false;
      const settle = () => {
        if (settled) return;
        settled = true;
        window.removeEventListener("feynman-auth-state", settle);
        resolve();
      };
      window.addEventListener("feynman-auth-state", settle, { once: true });
      window.setTimeout(settle, timeoutMs);
    }).finally(() => { authBootstrapWait = null; });
  }
  await authBootstrapWait;
}

/**
 * Clerk can publish its signed-in marker a few milliseconds before its first
 * session token is available on a brand-new tab.  Never let that transient
 * null token fall through to the legacy session: doing so can resolve /me for
 * one account and the following goal lookup for another account.  A short,
 * bounded retry keeps the stable Clerk subject on both requests without
 * delaying signed-out or legacy-session callers.
 */
async function freshAuthToken(): Promise<string | null> {
  let token = await getAuthToken();
  if (token || typeof document === "undefined" || document.documentElement?.dataset.feynmanAuth !== "signed-in") return token;
  for (const delayMs of [40, 80, 160, 320, 640, 1000]) {
    await new Promise((resolve) => setTimeout(resolve, delayMs));
    token = await getAuthToken();
    if (token) return token;
  }
  return token;
}

async function ensureCsrfToken() {
  if (typeof document === "undefined" || csrfToken()) return;
  if (!csrfBootstrap) {
    csrfBootstrap = fetch(`${API_BASE}/auth/csrf`, { credentials: "include" }).then((response) => {
      if (!response.ok) throw new Error("CSRF initialization failed");
    }).finally(() => { csrfBootstrap = null; });
  }
  await csrfBootstrap;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const method = (init.method || "GET").toUpperCase();
  const unsafe = !["GET", "HEAD", "OPTIONS"].includes(method);
  await waitForAuthBridge();
  const send = async (token: string | null) => {
    const requestHeaders = new Headers(headers);
    if (token) requestHeaders.set("Authorization", `Bearer ${token}`);
    else requestHeaders.delete("Authorization");
    const anonymousLearnerId = typeof window !== "undefined" ? window.localStorage.getItem("feynman.learnerId") : null;
    if (anonymousLearnerId) requestHeaders.set("X-Feynman-Anonymous-Learner", anonymousLearnerId);
    if (unsafe && !token) await ensureCsrfToken();
    if (init.body && !requestHeaders.has("Content-Type")) requestHeaders.set("Content-Type", "application/json");
    const csrf = csrfToken();
    if (unsafe && !token && csrf && !requestHeaders.has("X-CSRFToken")) requestHeaders.set("X-CSRFToken", csrf);
    return fetch(`${API_BASE}${path}`, { ...init, headers: requestHeaders, credentials: "include" });
  };
  let token = await freshAuthToken();
  let response: Response;
  try {
    response = await send(token);
    if (response.status === 401) {
      if (!token) await waitForAuthBridge(2500);
      const freshToken = await getAuthToken();
      if (freshToken && freshToken !== token) {
        token = freshToken;
        response = await send(token);
      }
    }
  } catch {
    throw new LearningOsApiError(
      "Feynman's local learning service is unavailable. Start the backend on 127.0.0.1:8000, then refresh this page.",
      0,
      "service_unavailable",
    );
  }
  const body = await response.json().catch(() => null) as { error?: { message?: string; code?: string }; message?: string } | T | null;
  if (!response.ok) {
    const error = body as { error?: { message?: string; code?: string }; message?: string } | null;
    throw new LearningOsApiError(error?.error?.message || error?.message || `Request failed (${response.status})`, response.status, error?.error?.code);
  }
  return body as T;
}

function json(method: string, body?: unknown): RequestInit {
  return { method, body: body === undefined ? undefined : JSON.stringify(body) };
}

export const learningOsApi = {
  register(input: { email: string; password: string; displayName: string; anonymousLearnerId?: string | null }) {
    return request<CurrentUser>("/auth/register", json("POST", input));
  },
  login(input: { email: string; password: string }) {
    return request<CurrentUser>("/auth/login", json("POST", input));
  },
  logout() {
    return request<{ signedOut: boolean }>("/auth/logout", json("POST"));
  },
  me() {
    return request<CurrentUser>("/me");
  },
  workspaces() {
    return request<{ workspaces: LearningWorkspace[]; personalWorkspaceId: string }>("/workspaces");
  },
  createWorkspace(input: { name: string; kind?: "institution" | "personal" }) {
    return request<LearningWorkspace>("/workspaces", json("POST", input));
  },
  inviteMember(workspaceId: string, input: { email: string; role: string }) {
    return request<{ inviteId: string; email: string; role: string; token: string; joinPath: string }>(`/organizations/${workspaceId}/members`, json("POST", input));
  },
  members(workspaceId: string) {
    return request<{ members: Array<{ membershipId: string; email: string; name: string; role: string; status: string }>; invitations: Array<{ inviteId: string; email: string; role: string; token: string; status: string }> }>(`/organizations/${workspaceId}/members`);
  },
  invitation(token: string) {
    return request<{ inviteId: string; organization: string; workspaceId: string; email: string; role: string; status: string }>(`/invites/${token}`);
  },
  acceptInvitation(token: string) {
    return request<{ accepted: boolean; workspace: LearningWorkspace }>(`/invites/${token}`, json("POST"));
  },
  courses() {
    return request<{ courses: Course[] }>("/courses");
  },
  course(courseId: string) {
    return request<Course>(`/courses/${courseId}`);
  },
  createCourse(input: { workspaceId: string; title: string; description?: string; status?: string; route?: Record<string, unknown>; sourcePolicy?: Record<string, unknown> }) {
    return request<Course>("/courses", json("POST", input));
  },
  updateCourse(courseId: string, input: Partial<Pick<Course, "title" | "description" | "status" | "route" | "sourcePolicy">>) {
    return request<Course>(`/courses/${courseId}`, json("PATCH", input));
  },
  joinCourse(joinCode: string) {
    return request<{ enrollmentId: string; course: Course }>("/courses/join", json("POST", { joinCode }));
  },
  courseSources(courseId: string) {
    return request<{ sourcePacks: NonNullable<Course["sourcePacks"]> }>(`/courses/${courseId}/sources`);
  },
  updateCourseSources(courseId: string, sourcePackIds: string[]) {
    return request<{ sourcePacks: NonNullable<Course["sourcePacks"]> }>(`/courses/${courseId}/sources`, json("POST", { sourcePackIds }));
  },
  cohort(courseId: string) {
    return request<{ courseId: string; learners: Array<{ name: string; sharedEvidence: EvidenceRecord[] }> }>(`/courses/${courseId}/cohort`);
  },
  goals() {
    return request<{ goals: LearningGoal[] }>("/goals");
  },
  previewGoalContract(input: { title: string; description?: string; outcome?: string; currentLevel: string; timeBudget?: string; category?: string }) {
    return request<{ contract: LearningContract; domain: string; provider: string; model?: string; providerMode?: string | null; generated: boolean; providerMessage?: string }>("/goals/contract-preview", json("POST", input));
  },
  createGoal(input: { title: string; description: string; outcome: string; currentLevel: string; timeBudget: string; category?: string; courseId?: string; contract?: Partial<LearningContract> }) {
    return request<LearningGoal>("/goals", json("POST", input));
  },
  goal(goalId: string) {
    return request<LearningGoal>(`/goals/${goalId}`);
  },
  createGoalShare(goalId: string) {
    return request<{ shareId: string; token: string; active: boolean }>(`/goals/${goalId}/share`, json("POST"));
  },
  sharedGoal(token: string) {
    return request<GoalShare>(`/shared-goals/${token}`);
  },
  cloneSharedGoal(token: string) {
    return request<LearningGoal>(`/shared-goals/${token}/clone`, json("POST"));
  },
  goalSources(goalId: string) {
    return request<{ goalId: string; notebooks: GoalSourceContext[] }>(`/goals/${goalId}/sources`);
  },
  compileCurriculum(goalId: string, input: { sourceIds?: string[]; learnerLevel?: string } = {}) {
    return request<{ curriculum: CurriculumSummary; goal: LearningGoal }>(`/goals/${goalId}/curriculum`, json("POST", input));
  },
  curriculum(goalId: string) {
    return request<{ curriculum: CurriculumSummary; goal: LearningGoal }>(`/goals/${goalId}/curriculum`);
  },
  updateCurriculum(goalId: string, input: { activityOrder?: string[]; approvalState?: "pending" | "approved"; learnerNote?: string }) {
    return request<{ curriculum: CurriculumSummary; goal: LearningGoal }>(`/goals/${goalId}/curriculum`, json("PATCH", input));
  },
  attachGoalNotebook(goalId: string, notebookId: string) {
    return request<{ goalId: string; notebooks: GoalSourceContext[] }>(`/goals/${goalId}/sources`, json("POST", { notebookId }));
  },
  updateGoal(goalId: string, input: Record<string, unknown>) {
    return request<LearningGoal>(`/goals/${goalId}`, json("PATCH", input));
  },
  submitAttempt(goalId: string, input: StructuredActivityAttempt) {
    return request<{ evidence: EvidenceRecord; feedback?: ActivityProviderFeedback | null; adaptiveRoute?: Record<string, unknown>; goal: LearningGoal }>(`/goals/${goalId}/attempts`, json("POST", input));
  },
  evidence(goalId?: string) {
    const query = goalId ? `?goalId=${encodeURIComponent(goalId)}` : "";
    return request<{ evidence: EvidenceRecord[] }>(`/evidence${query}`);
  },
  shares() {
    return request<{ shares: ShareGrant[] }>("/shares");
  },
  createShare(input: { courseId: string; evidenceIds: string[] }) {
    return request<ShareGrant>("/shares", json("POST", input));
  },
  revokeShare(shareId: string) {
    return request<{ shareId: string; active: boolean }>(`/shares/${shareId}`, { method: "DELETE" });
  },
  privacy() {
    return request<{ learnerMemoryEnabled: boolean; notebookSourceRetention: string; courseSharingEnabled: boolean; activeShares: number }>("/privacy");
  },
  updatePrivacy(input: { learnerMemoryEnabled?: boolean; courseSharingEnabled?: boolean }) {
    return request<{ learnerMemoryEnabled: boolean; notebookSourceRetention: string; courseSharingEnabled: boolean; activeShares: number }>("/privacy", json("PATCH", input));
  },
  teachDashboard() {
    return request<{ courses: Course[]; pendingReviews: number; sourceApprovalNeeded: number }>("/teach/dashboard");
  },
  institutionDashboard(workspaceId?: string) {
    const query = workspaceId ? `?workspaceId=${encodeURIComponent(workspaceId)}` : "";
    return request<{ workspace: LearningWorkspace; memberCounts: Record<string, number>; courseCount: number; activeEnrollmentCount: number; verifiedEvidenceCount: number; sourceGovernance: { approved: number; needsReview: number } }>(`/institution/dashboard${query}`);
  },
};

export function isAuthenticationError(error: unknown): boolean {
  return error instanceof LearningOsApiError && error.status === 401;
}
