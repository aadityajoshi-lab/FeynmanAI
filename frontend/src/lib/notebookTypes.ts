export type NotebookGoal = "understand" | "exam" | "interview" | "viva" | "language";
export type NotebookArtifactType = "summary" | "mcq" | "slides" | "formula_sheet" | "important_questions" | "flashcards" | "mind_map" | "data_table" | "openmaic_lesson";

export type NotebookBlock = { blockId: string; type: string; markdown: string; page?: number; section?: string; sourceAnchor?: string; assetId?: string; bbox?: unknown };
export type NotebookSection = { sectionId: string; title: string; order: number; kind?: string; sourceIds: string[]; pages: number[]; blocks: NotebookBlock[] };
export type NotebookPack = {
  version: string;
  notebookId: string;
  title: string;
  sources: string[];
  sections: NotebookSection[];
  supplementarySections?: NotebookSection[];
  concepts: Array<Record<string, unknown>>;
  formulas: Array<{ formulaId: string; text: string; sectionId: string; sourceId: string; page?: number }>;
  assets: Array<{ assetId: string; type: string; mimeType?: string; page?: number; alt?: string; dataUrl?: string; url?: string; sourceId?: string }>;
};
export type NotebookSource = {
  sourceId: string;
  title: string;
  filename?: string;
  sourceKind: string;
  mimeType?: string;
  status: string;
  extractionMethod: string;
  groundingEnabled?: boolean;
  /** A failed extraction can be retried only by selecting the source file again.
   * The browser never retains or re-sends a raw file without a new selection. */
  retryAvailable?: boolean;
  retryRequiresReupload?: boolean;
  retryAction?: string | null;
  extraction: Record<string, any>;
  assets: Array<Record<string, unknown>>;
};
export type NotebookArtifact = {
  artifactId: string;
  type: NotebookArtifactType;
  title: string;
  status: string;
  payload: Record<string, any>;
  sourceIds: string[];
  provider?: string | null;
  model?: string | null;
  providerStatus?: string | null;
  citationValidation?: string | null;
  createdAt: string;
};
export type NotebookChatMessage = {
  messageId: string;
  role: "user" | "assistant";
  content: string;
  sourceIds: string[];
  sourceAnchorIds: string[];
  groundedIn?: "notebook" | "web" | "mixed" | "insufficient" | null;
  degraded?: boolean;
  providerUnavailable?: boolean;
  providerMessage?: string;
  /** Non-secret provenance emitted by the server after a real provider attempt. */
  provider?: string | null;
  model?: string | null;
  providerStatus?: string | null;
  providerErrorCategory?: string | null;
  status: "ready" | "stale" | string;
  createdAt: string;
};
export type NotebookNote = {
  noteId: string;
  title: string;
  content: string;
  sourceIds: string[];
  sourceAnchorIds: string[];
  createdAt: string;
  updatedAt: string;
};
export type Notebook = {
  notebookId: string;
  title: string;
  subject: string;
  description: string;
  learningGoal: NotebookGoal;
  workspaceId?: string | null;
  goalId?: string | null;
  courseId?: string | null;
  owned?: boolean;
  status: string;
  ocrProvider: string;
  stats: { sourceCount?: number; sectionCount?: number; assetCount?: number; formulaCount?: number };
  sources: NotebookSource[];
  knowledgePack: NotebookPack;
  knowledgePackMarkdown: string;
  artifacts: NotebookArtifact[];
  chatMessages: NotebookChatMessage[];
  notes: NotebookNote[];
};

/** The intentionally small, account-owned response returned by GET /notebooks.
 * It is safe to use in the universal context picker because it never includes
 * raw source text, chat content, or artifacts. */
export type NotebookListItem = {
  notebookId: string;
  title: string;
  status: string;
  goalId?: string | null;
  courseId?: string | null;
  sourceCount: number;
  updatedAt: string;
};
