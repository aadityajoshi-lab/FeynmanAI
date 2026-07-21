export type WorkspaceRole = "owner" | "institution_admin" | "instructor" | "learner";

export type LearningWorkspace = {
  workspaceId: string;
  name: string;
  kind: "personal" | "institution" | string;
  role?: WorkspaceRole | null;
  memberCount?: number;
  createdAt?: string;
};

export type LearningProfile = {
  learnerId: string;
  profileId: string;
  displayName: string;
  memoryEnabled: boolean;
  workspaceId?: string | null;
};

export type CurrentUser = {
  user: { id: number; email: string; displayName: string };
  profile: LearningProfile;
  workspaces: LearningWorkspace[];
  roles: WorkspaceRole[];
};

export type LearningActivity = {
  activityId: string;
  type: "predict" | "explain" | "compare" | "derive" | "debug" | "analyze" | "simulate" | "apply" | "build" | "transfer" | string;
  title: string;
  prompt: string;
  position: number;
  status: string;
  configuration?: ActivityConfiguration;
  difficulty?: number;
  remediationTarget?: string;
  transferTarget?: string;
  prerequisites: string[];
  sourceIds: string[];
  sourceAnchorIds?: string[];
  citations?: Array<{ sourceId: string; sourceAnchorId: string }>;
  evaluator: { mode?: string; requiresSource?: boolean; minimumResponseCharacters?: number };
};

export type ActivityConfiguration = {
  schemaVersion?: string;
  activityType?: string;
  domain?: "operating_systems" | "computer_graphics" | "ai_ml" | "medical" | "general" | string;
  concept?: string;
  difficulty?: number;
  prerequisites?: string[];
  taskPrompt?: string;
  interactiveControls?: Array<Record<string, unknown>>;
  expectedLearnerObservations?: string[];
  evaluatorRubric?: string[];
  sourceRequirements?: { mode?: "optional" | "required" | string; requireSelectedAnchors?: boolean };
  allowedResponseTypes?: string[];
  remediationTarget?: string;
  transferTarget?: string;
  adaptiveAction?: string;
  sourceIds?: string[];
  sourceAnchorIds?: string[];
  citations?: Array<{ sourceId: string; sourceAnchorId: string }>;
  safetyPolicy?: Record<string, unknown>;
};

export type StructuredActivityAttempt = {
  activityId: string;
  response?: string;
  writtenExplanation?: string;
  learnerConclusion?: string;
  confidence?: 1 | 2 | 3 | 4 | 5;
  prediction?: Record<string, unknown>;
  interactionState?: Record<string, unknown>;
  simulationParameters?: Record<string, unknown>;
  selectedOptions?: unknown[];
  calculations?: Record<string, unknown>;
  trace?: unknown[];
  sourceIds?: string[];
  sourceAnchorIds?: string[];
};

export type ActivityProviderEvaluation = {
  state?: string;
  correct?: boolean | null;
  understandingScore?: number | null;
  overconfidence?: boolean;
  feedback?: string;
  remediation?: string;
  mistake?: string;
  correctAnswer?: string;
  correction?: string;
  nextAction?: string;
  retryPrompt?: string | null;
  retryOptions?: string[] | null;
  sourceAnchorIds?: string[];
};

/** Safe provenance for a server-side OpenAI evaluation. This deliberately
 * contains model identity and failure category, never credentials or prompts. */
export type ActivityProviderFeedback = {
  provider: string;
  model?: string | null;
  state: string;
  providerAttempt: "completed" | "failed" | "not_configured" | "skipped_no_selected_source" | string;
  providerMode?: string | null;
  providerErrorCategory?: string | null;
  retryAvailable: boolean;
  retryAction?: string | null;
  uncertainty?: string | null;
  sourceAnchorIds: string[];
  evaluation?: ActivityProviderEvaluation | null;
};

export type EvidenceRubric = Record<string, unknown> & {
  provider?: string | null;
  providerMode?: string | null;
  model?: string | null;
  providerAttempt?: string | null;
  providerFeedback?: ActivityProviderEvaluation | null;
  providerErrorCategory?: string | null;
  uncertainty?: string | null;
};

export type EvidenceRecord = {
  evidenceId: string;
  goalId: string;
  goalTitle?: string;
  goalCategory?: string;
  activityId?: string | null;
  capability: string;
  type: string;
  status: "observed" | "verified" | "needs_review" | "rejected" | string;
  score?: number | null;
  summary: string;
  rubric: EvidenceRubric;
  transitionReason?: string;
  sourceAnchorIds: string[];
  createdAt: string;
};

export type LearningContract = {
  intendedCapability: string;
  learnerStartingPoint: string;
  timeBudget: string;
  prerequisites: string[];
  confidence: string;
  sourceRequirements: string;
  safetyMode: string;
  verificationMode: string;
  firstTask: string;
  learnerCorrection: string;
  brief?: string;
};

export type LearningGoal = {
  goalId: string;
  workspaceId?: string | null;
  courseId?: string | null;
  title: string;
  description: string;
  domain: string;
  category?: string;
  outcome: string;
  currentLevel: "beginner" | "intermediate" | "advanced" | string;
  timeBudget: string;
  sourceMode: string;
  safetyMode: string;
  verificationMode: string;
  status: string;
  contract: LearningContract;
  route?: Record<string, unknown>;
  nextAction: string;
  evidenceCount: number;
  activities?: LearningActivity[];
  evidence?: EvidenceRecord[];
  curriculum?: CurriculumSummary;
  createdAt?: string;
  updatedAt?: string;
};

export type GoalShare = {
  shareId: string;
  token: string;
  title?: string;
  domain?: string;
  outcome?: string;
  currentLevel?: string;
  activityCount?: number;
  sourceCount?: number;
  sourceTitles?: string[];
  active?: boolean;
};

export type CurriculumConcept = {
  conceptId?: number;
  key: string;
  title: string;
  description?: string;
  sourceIds: string[];
  sourceAnchorIds: string[];
  uncertainty?: Record<string, unknown>;
};

export type CurriculumSummary = {
  packId: string;
  curriculumVersionId?: number;
  version: number;
  status: string;
  domain: string;
  learnerLevel?: string;
  safetyMode?: string;
  sourceIds: string[];
  sourceAnchorIds: string[];
  sourceFingerprint?: string;
  uncertainty?: Record<string, unknown>;
  provenance?: Record<string, unknown>;
  quality?: {
    conceptCount?: number;
    citedConceptCount?: number;
    activityCount?: number;
    citedActivityCount?: number;
    coveragePercent?: number;
    unsupportedClaims?: number;
    warnings?: string[];
  };
  safetyBoundary?: string;
  difficultyExplanation?: string;
  compilerStages?: Array<{ id: string; label: string; status: string }>;
  preview?: { editable?: boolean; approvalRequired?: boolean; approvalState?: string; routeEdited?: boolean };
  concepts?: CurriculumConcept[];
  prerequisites?: Array<{ prerequisite: string; dependent: string; sourceAnchorIds: string[] }>;
  activities?: LearningActivity[];
  route?: Record<string, unknown>;
};

export type Course = {
  courseId: string;
  workspaceId: string;
  title: string;
  description: string;
  joinCode?: string;
  status: string;
  instructor: string;
  enrollmentStatus?: string | null;
  canManage?: boolean;
  canReviewCohort?: boolean;
  learnerCount: number;
  sourcePackCount: number;
  route: Record<string, unknown>;
  sourcePolicy: Record<string, unknown>;
  sourcePacks?: Array<{ sourcePackId: string; title: string; description?: string; approved: boolean }>;
};

export type ShareGrant = {
  shareId: string;
  courseId: string;
  courseTitle?: string;
  evidenceIds: string[];
  scope: string;
  active: boolean;
  createdAt?: string;
};

export type GoalSourceSummary = {
  sourceId: string;
  title: string;
  filename?: string;
  sourceKind: string;
  mimeType?: string;
  status: string;
  extractionMethod?: string;
  pageCount?: number;
  blockCount?: number;
  groundingEnabled?: boolean;
  anchorIds: string[];
};

export type GoalSourceContext = {
  notebookId: string;
  title: string;
  status: string;
  sources: GoalSourceSummary[];
  artifacts?: Array<{
    artifactId: string;
    type: string;
    title: string;
    status: string;
    sourceIds: string[];
  }>;
};

export type PendingGoal = {
  title: string;
  description: string;
  outcome: string;
  currentLevel: "beginner" | "intermediate" | "advanced";
  timeBudget: string;
  hasSources: boolean;
  category?: string;
  courseId?: string;
  sourceNotebookId?: string;
};
