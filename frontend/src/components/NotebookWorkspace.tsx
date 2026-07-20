"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  askNotebook,
  createNotebookArtifact,
  createNotebookLesson,
  createNotebookNote,
  deleteNotebookNote,
  deleteNotebookSource,
  getNotebook,
  retryNotebookSource,
  updateNotebookNote,
  uploadNotebookSource,
} from "@/lib/notebookApi";
import { learningOsApi } from "@/lib/learningOsApi";
import type { LearningActivity, LearningGoal } from "@/lib/learningOsTypes";
import type { Notebook, NotebookArtifact, NotebookArtifactType, NotebookChatMessage, NotebookNote, NotebookSection, NotebookSource } from "@/lib/notebookTypes";

type CenterView = "proof" | "chat" | "artifact" | "notes";
type Drawer = "sources" | "studio" | null;
type StudioArtifactType = Exclude<NotebookArtifactType, "openmaic_lesson">;
type ProviderGenerationRetry = { kind: "artifact"; type: StudioArtifactType } | { kind: "lesson" } | null;

const studioCards: Array<{ type: StudioArtifactType | "notes" | "openmaic_lesson"; label: string; description: string; icon: IconName; accent: string }> = [
  { type: "summary", label: "Study guide", description: "A concise map of every saved topic.", icon: "spark", accent: "#111111" },
  { type: "mcq", label: "Quiz", description: "Recall checks with source-backed answers.", icon: "quiz", accent: "#111111" },
  { type: "slides", label: "Slide deck", description: "Turn the source into a visual sequence.", icon: "slides", accent: "#111111" },
  { type: "flashcards", label: "Flashcards", description: "Practice retrieval from your material.", icon: "cards", accent: "#111111" },
  { type: "formula_sheet", label: "Formula sheet", description: "Keep equations linked to their pages.", icon: "formula", accent: "#111111" },
  { type: "data_table", label: "Source table", description: "Browse topics, pages, ideas, and formulas.", icon: "table", accent: "#111111" },
  { type: "mind_map", label: "Mind map", description: "See the source structure at a glance.", icon: "mind", accent: "#111111" },
  { type: "openmaic_lesson", label: "Narrated lesson", description: "A guided source-grounded explanation.", icon: "audio", accent: "#111111" },
  { type: "notes", label: "Notebook notes", description: "Save your own thinking with citations.", icon: "note", accent: "#111111" },
];

const prompts = [
  "Give me the big idea in plain language",
  "What should I remember for an exam?",
  "Explain one difficult concept step by step",
];

function firstProofAnchor(notebook: Notebook) {
  const block = notebook.knowledgePack.sections.flatMap((section) => section.blocks).find((item) => item.sourceAnchor || item.blockId);
  return block?.sourceAnchor || block?.blockId || "";
}

function proofConcept(notebook: Notebook) {
  const concept = notebook.knowledgePack.concepts[0];
  if (concept && typeof concept.title === "string" && concept.title.trim()) return concept.title;
  const section = notebook.knowledgePack.sections[0]?.title;
  return section || notebook.title;
}

const ACCEPTED_FILES = "application/pdf,image/*,.txt,.md,.markdown,.csv,.docx,.pptx";

type IconName = "add" | "audio" | "back" | "cards" | "check" | "chevron" | "close" | "delete" | "file" | "formula" | "guide" | "mind" | "more" | "note" | "panel" | "quiz" | "search" | "send" | "slides" | "spark" | "table" | "upload";

function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  const common = { width: size, height: size, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.9, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true };
  switch (name) {
    case "add": return <svg {...common}><path d="M12 5v14M5 12h14" /></svg>;
    case "audio": return <svg {...common}><path d="M4 12h2l2-6 4 12 2-6h2" /><path d="M18 8c1.5 1 1.5 7 0 8" /></svg>;
    case "back": return <svg {...common}><path d="m15 18-6-6 6-6" /></svg>;
    case "cards": return <svg {...common}><rect x="5" y="4" width="14" height="16" rx="2" /><path d="M8 8h8M8 12h6" /></svg>;
    case "check": return <svg {...common}><path d="m5 12 4 4L19 6" /></svg>;
    case "chevron": return <svg {...common}><path d="m9 18 6-6-6-6" /></svg>;
    case "close": return <svg {...common}><path d="m6 6 12 12M18 6 6 18" /></svg>;
    case "delete": return <svg {...common}><path d="M4 7h16M10 11v5M14 11v5M9 7l1-2h4l1 2M6 7l1 13h10l1-13" /></svg>;
    case "file": return <svg {...common}><path d="M6 3h8l4 4v14H6z" /><path d="M14 3v5h5M9 13h6M9 17h4" /></svg>;
    case "formula": return <svg {...common}><path d="M18 5H8l6 7-6 7h10" /><path d="M4 5h2M4 19h2" /></svg>;
    case "guide": return <svg {...common}><path d="M5 4h14v16H5z" /><path d="M8 8h8M8 12h8M8 16h5" /></svg>;
    case "mind": return <svg {...common}><circle cx="12" cy="12" r="2.5" /><circle cx="5" cy="6" r="2" /><circle cx="19" cy="6" r="2" /><circle cx="5" cy="18" r="2" /><circle cx="19" cy="18" r="2" /><path d="m10 10-3.5-3M14 10l3.5-3M10 14l-3.5 3M14 14l3.5 3" /></svg>;
    case "more": return <svg {...common}><circle cx="5" cy="12" r="1" fill="currentColor" /><circle cx="12" cy="12" r="1" fill="currentColor" /><circle cx="19" cy="12" r="1" fill="currentColor" /></svg>;
    case "note": return <svg {...common}><path d="M6 3h12v18H6z" /><path d="M9 8h6M9 12h6M9 16h4" /></svg>;
    case "panel": return <svg {...common}><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M9 4v16" /></svg>;
    case "quiz": return <svg {...common}><circle cx="12" cy="12" r="8" /><path d="M9.5 9a2.6 2.6 0 1 1 4.3 2c-.9.7-1.8 1.2-1.8 2.5M12 17h.01" /></svg>;
    case "search": return <svg {...common}><circle cx="10.5" cy="10.5" r="5.5" /><path d="m15 15 4 4" /></svg>;
    case "send": return <svg {...common}><path d="m4 4 16 8-16 8 3-8z" /><path d="M7 12h13" /></svg>;
    case "slides": return <svg {...common}><rect x="4" y="5" width="16" height="14" rx="2" /><path d="M8 9h8M8 13h5" /></svg>;
    case "spark": return <svg {...common}><path d="m12 3 1.7 5.3L19 10l-5.3 1.7L12 17l-1.7-5.3L5 10l5.3-1.7z" /></svg>;
    case "table": return <svg {...common}><rect x="4" y="5" width="16" height="14" rx="1" /><path d="M4 10h16M10 5v14" /></svg>;
    case "upload": return <svg {...common}><path d="M12 16V4M8 8l4-4 4 4" /><path d="M5 15v4h14v-4" /></svg>;
    default: return null;
  }
}

function sourceMetric(source: NotebookSource, key: "pageCount" | "blockCount" | "assetCount") {
  return Number(source.extraction?.[key] || 0);
}

function shortDate(value: string) {
  try { return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(new Date(value)); } catch { return "saved"; }
}

function titleFromArtifact(type: NotebookArtifactType) {
  return studioCards.find((card) => card.type === type)?.label || "Saved output";
}

export default function NotebookWorkspace({ notebookId }: { notebookId: string }) {
  const [notebook, setNotebook] = useState<Notebook | null>(null);
  const [selectedSourceIds, setSelectedSourceIds] = useState<string[]>([]);
  const [centerView, setCenterView] = useState<CenterView>("proof");
  const [activeArtifact, setActiveArtifact] = useState<NotebookArtifact | null>(null);
  const [drawer, setDrawer] = useState<Drawer>(null);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [providerNotice, setProviderNotice] = useState("");
  const [retryQuestion, setRetryQuestion] = useState("");
  const [retryableQuestionError, setRetryableQuestionError] = useState("");
  const [retryGeneration, setRetryGeneration] = useState<ProviderGenerationRetry>(null);
  const [retrySource, setRetrySource] = useState<NotebookSource | null>(null);
  const [noteDraft, setNoteDraft] = useState({ title: "", content: "", sourceIds: [] as string[], sourceAnchorIds: [] as string[] });
  const [editingNote, setEditingNote] = useState<NotebookNote | null>(null);
  const [proofGoal, setProofGoal] = useState<LearningGoal | null>(null);
  const [proofResponse, setProofResponse] = useState("");
  const [proofConclusion, setProofConclusion] = useState("");
  const [proofConfidence, setProofConfidence] = useState<1 | 2 | 3 | 4 | 5>(3);
  const [proofBusy, setProofBusy] = useState(false);
  const [proofFeedback, setProofFeedback] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const retryFileInputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      const data = await getNotebook(notebookId);
      setNotebook(data);
      setSelectedSourceIds((current) => {
        const ready = data.sources.filter((source) => source.status === "ready" && source.groundingEnabled !== false).map((source) => source.sourceId);
        const retained = current.filter((sourceId) => ready.includes(sourceId));
        return retained.length || !ready.length ? retained : ready;
      });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Notebook could not be loaded.");
    }
  }, [notebookId]);

  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    let live = true;
    if (!notebook?.goalId) { setProofGoal(null); return () => { live = false; }; }
    void learningOsApi.goal(notebook.goalId).then((goal) => { if (live) setProofGoal(goal); }).catch(() => { if (live) setProofGoal(null); });
    return () => { live = false; };
  }, [notebook?.goalId]);

  const readySources = useMemo(() => notebook?.sources.filter((source) => source.status === "ready") || [], [notebook]);
  const groundingReadySources = useMemo(() => readySources.filter((source) => source.groundingEnabled !== false), [readySources]);
  const activeSources = useMemo(() => groundingReadySources.filter((source) => selectedSourceIds.includes(source.sourceId)), [groundingReadySources, selectedSourceIds]);
  const canUseSources = activeSources.length > 0;
  const messages = useMemo(() => notebook?.chatMessages || [], [notebook]);
  const notes = notebook?.notes || [];
  const proofActivity = proofGoal?.activities?.find((activity) => activity.status !== "completed") || proofGoal?.activities?.[0] || null;

  useEffect(() => {
    const fallback = [...messages].reverse().find((item) => item.role === "assistant" && (item.degraded || item.providerUnavailable || item.status === "provider_unavailable"));
    if (fallback) setProviderNotice(fallback.providerMessage || "A saved answer used the source-bounded fallback because the answer provider was temporarily unavailable. Citations still point only to selected sources; retry the question later for a generated explanation.");
    else setProviderNotice("");
  }, [messages]);

  function closeDrawer() { setDrawer(null); }

  function toggleSource(sourceId: string) {
    const source = notebook?.sources.find((item) => item.sourceId === sourceId);
    if (!source || source.status !== "ready" || source.groundingEnabled === false) return;
    setSelectedSourceIds((current) => current.includes(sourceId) ? current.filter((id) => id !== sourceId) : [...current, sourceId]);
  }

  function selectAllSources() { setSelectedSourceIds(groundingReadySources.map((source) => source.sourceId)); }

  async function uploadFiles(files: FileList | null) {
    if (!files?.length || !notebook) return;
    setBusy("upload"); setError("");
    try {
      let current = notebook;
      for (const file of Array.from(files)) {
        current = await uploadNotebookSource(notebookId, file, { sourceKind: "reference", ocrProvider: current.ocrProvider === "mistral-ocr-4-0" ? "mistral" : "auto" });
      }
      setNotebook(current);
      setSelectedSourceIds(current.sources.filter((source) => source.status === "ready" && source.groundingEnabled !== false).map((source) => source.sourceId));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The source could not be added.");
    } finally {
      setBusy(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  function openSourcePicker() {
    setRetrySource(null);
    fileInputRef.current?.click();
  }

  function openSourceRetry(source: NotebookSource) {
    setRetrySource(source);
    retryFileInputRef.current?.click();
  }

  async function retrySourceExtraction(source: NotebookSource, files: FileList | null) {
    const file = files?.[0];
    if (!file || !notebook) return;
    setBusy(`retry-${source.sourceId}`); setError("");
    try {
      const next = await retryNotebookSource(notebookId, source.sourceId, file, {
        sourceKind: source.sourceKind,
        ocrProvider: notebook.ocrProvider === "mistral-ocr-4-0" ? "mistral" : "auto",
        title: source.title,
        useForGrounding: source.groundingEnabled,
      });
      setNotebook(next);
      setSelectedSourceIds((current) => {
        const ready = next.sources.filter((item) => item.status === "ready" && item.groundingEnabled !== false).map((item) => item.sourceId);
        const retained = current.filter((sourceId) => ready.includes(sourceId));
        return retained.length || !ready.length ? retained : ready;
      });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The source could not be extracted. Select the file again to retry.");
    } finally {
      setBusy(null);
      setRetrySource(null);
      if (retryFileInputRef.current) retryFileInputRef.current.value = "";
    }
  }

  function handleRetryFileSelection(files: FileList | null) {
    const retry = retrySource;
    if (retry) void retrySourceExtraction(retry, files);
  }

  async function removeSource(source: NotebookSource) {
    if (!notebook || !window.confirm(`Remove ${source.title}? Its extracted context will be removed from this notebook.`)) return;
    setBusy(`source-${source.sourceId}`); setError("");
    try {
      const next = await deleteNotebookSource(notebookId, source.sourceId);
      setNotebook(next);
      setSelectedSourceIds((current) => current.filter((id) => id !== source.sourceId));
      if (activeArtifact?.sourceIds.includes(source.sourceId)) setActiveArtifact(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The source could not be removed.");
    } finally { setBusy(null); }
  }

  async function submitQuestion(event?: FormEvent, questionOverride?: string) {
    event?.preventDefault();
    const asked = (questionOverride ?? question).trim();
    if (!asked || !canUseSources || !notebook) return;
    setBusy("ask"); setError(""); setProviderNotice(""); setRetryableQuestionError("");
    setRetryQuestion(asked);
    try {
      const result = await askNotebook(notebookId, asked, selectedSourceIds);
      setNotebook((current) => current ? { ...current, chatMessages: [...current.chatMessages, result.messages.user, result.messages.assistant] } : current);
      if (result.degraded || result.providerUnavailable) setProviderNotice(result.providerMessage || "Feynman used a source-bounded fallback because the answer provider is temporarily unavailable. Citations still point only to your selected sources; retry the question later for a generated explanation.");
      else setRetryQuestion("");
      setQuestion("");
      setCenterView("chat");
    } catch (caught) {
      const failure = caught instanceof Error ? caught.message : "The notebook could not answer that question.";
      setError(failure); setRetryableQuestionError(failure);
    } finally { setBusy(null); }
  }

  async function makeArtifact(type: StudioArtifactType) {
    if (!canUseSources || !notebook) return;
    setBusy(type); setError(""); setRetryGeneration(null);
    try {
      const artifact = await createNotebookArtifact(notebookId, type, selectedSourceIds);
      setActiveArtifact(artifact);
      setNotebook((current) => current ? { ...current, artifacts: [artifact, ...current.artifacts] } : current);
      setCenterView("artifact"); closeDrawer();
    } catch (caught) {
      const failure = caught instanceof Error ? caught.message : "That studio tool could not be created.";
      setError(failure);
      if (/fireworks.*(?:unavailable|invalid)|configured fireworks provider/i.test(failure)) setRetryGeneration({ kind: "artifact", type });
    } finally { setBusy(null); }
  }

  async function makeLesson() {
    if (!canUseSources || !notebook) return;
    setBusy("openmaic_lesson"); setError(""); setRetryGeneration(null);
    try {
      const artifact = await createNotebookLesson(notebookId, question.trim() || "Create a guided lesson from this notebook.", 120, selectedSourceIds);
      setActiveArtifact(artifact);
      setNotebook((current) => current ? { ...current, artifacts: [artifact, ...current.artifacts] } : current);
      setQuestion(""); setCenterView("artifact"); closeDrawer();
    } catch (caught) {
      const failure = caught instanceof Error ? caught.message : "The narrated lesson could not be created.";
      setError(failure);
      if (/fireworks.*(?:unavailable|invalid)|configured fireworks provider/i.test(failure)) setRetryGeneration({ kind: "lesson" });
    } finally { setBusy(null); }
  }

  async function submitProof(event: FormEvent) {
    event.preventDefault();
    if (!notebook || !proofGoal || !proofActivity || !proofResponse.trim()) return;
    setProofBusy(true); setProofFeedback(""); setError("");
    const anchor = firstProofAnchor(notebook);
    try {
      const result = await learningOsApi.submitAttempt(proofGoal.goalId, {
        activityId: proofActivity.activityId,
        response: proofResponse.trim(),
        writtenExplanation: proofResponse.trim(),
        learnerConclusion: proofConclusion.trim(),
        confidence: proofConfidence,
        interactionState: { mode: "source_proof", concept: proofConcept(notebook), selectedSourceCount: activeSources.length },
        sourceIds: activeSources.map((source) => source.sourceId),
        sourceAnchorIds: anchor ? [anchor] : [],
      });
      setProofGoal(result.goal);
      setProofFeedback(result.feedback?.evaluation?.feedback || result.evidence.summary || "Attempt recorded. Open the learning route for the next best task.");
      setProofResponse(""); setProofConclusion("");
    } catch (caught) {
      setProofFeedback(caught instanceof Error ? caught.message : "The proof attempt could not be recorded.");
    } finally { setProofBusy(false); }
  }

  function openNewNote(message?: NotebookChatMessage) {
    setEditingNote(null);
    setNoteDraft({
      title: message ? "Notebook chat note" : "",
      content: message?.content || "",
      sourceIds: message?.sourceIds || selectedSourceIds,
      sourceAnchorIds: message?.sourceAnchorIds || [],
    });
    setCenterView("notes"); closeDrawer();
  }

  function openExistingNote(note: NotebookNote) {
    setEditingNote(note);
    setNoteDraft({ title: note.title, content: note.content, sourceIds: note.sourceIds, sourceAnchorIds: note.sourceAnchorIds });
    setCenterView("notes"); closeDrawer();
  }

  async function saveNote() {
    if (!notebook || !noteDraft.content.trim()) return;
    setBusy("note"); setError("");
    try {
      if (editingNote) {
        const updated = await updateNotebookNote(notebookId, editingNote.noteId, { title: noteDraft.title || "Untitled note", content: noteDraft.content });
        setNotebook((current) => current ? { ...current, notes: current.notes.map((note) => note.noteId === updated.noteId ? updated : note) } : current);
        setEditingNote(updated);
      } else {
        const created = await createNotebookNote(notebookId, noteDraft);
        setNotebook((current) => current ? { ...current, notes: [created, ...current.notes] } : current);
        setEditingNote(created);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The note could not be saved.");
    } finally { setBusy(null); }
  }

  async function removeNote(note: NotebookNote) {
    if (!window.confirm(`Delete “${note.title}”?`)) return;
    setBusy(`note-${note.noteId}`); setError("");
    try {
      await deleteNotebookNote(notebookId, note.noteId);
      setNotebook((current) => current ? { ...current, notes: current.notes.filter((item) => item.noteId !== note.noteId) } : current);
      if (editingNote?.noteId === note.noteId) openNewNote();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The note could not be deleted.");
    } finally { setBusy(null); }
  }

  if (!notebook && !error) return <main className="nlm-loading"><span className="nlm-loader" /><p>Opening your notebook…</p></main>;
  if (!notebook) return <main className="nlm-loading"><strong>{error}</strong><Link href="/sources">Back to Source Desk</Link></main>;

  return <main className="nlm-shell">
    <header className="nlm-topbar">
      <Link href="/home" className="nlm-brand" aria-label="Feynman home">feynman<span>.ai</span></Link>
        <div className="nlm-title"><strong>{notebook.title}</strong><span>{activeSources.length} of {groundingReadySources.length || 0} sources active · SOURCE → PROOF → EVIDENCE</span></div>
      <div className="nlm-top-actions">
        <button type="button" className="nlm-top-quiet" onClick={() => openNewNote()}><Icon name="note" size={15} /> Notes</button>
        <Link href="/sources" className="nlm-create-button"><Icon name="add" size={16} /> Add source</Link>
      </div>
      <div className="nlm-mobile-actions"><button type="button" onClick={() => setDrawer(drawer === "sources" ? null : "sources")} aria-expanded={drawer === "sources"}><Icon name="panel" /></button><button type="button" onClick={() => setDrawer(drawer === "studio" ? null : "studio")} aria-expanded={drawer === "studio"}><Icon name="spark" /></button></div>
    </header>

    {drawer && <button type="button" className="nlm-drawer-scrim" aria-label="Close panel" onClick={closeDrawer} />}
    <div className="nlm-workspace">
      <aside className="nlm-panel nlm-sources" data-open={drawer === "sources"}>
        <PanelHeading title="Sources" icon="file" onClose={closeDrawer} />
        <div className="nlm-sources-body">
          <input ref={fileInputRef} type="file" accept={ACCEPTED_FILES} multiple hidden onChange={(event) => void uploadFiles(event.target.files)} />
          <input ref={retryFileInputRef} type="file" accept={ACCEPTED_FILES} hidden onChange={(event) => handleRetryFileSelection(event.target.files)} />
          <button type="button" className="nlm-add-source" onClick={() => fileInputRef.current?.click()} disabled={busy === "upload"}><Icon name={busy === "upload" ? "more" : "add"} /> {busy === "upload" ? "Processing source…" : "Add sources"}</button>
          <div className="nlm-source-context"><span><span className="nlm-memory-dot" /> Notebook memory</span><p>PDF text, visuals, and page anchors are stored with this notebook. Original files are not retained.</p></div>
          {groundingReadySources.length > 1 && <div className="nlm-select-all"><button type="button" onClick={selectAllSources}>Select all</button><span>{selectedSourceIds.length} active</span></div>}
          <div className="nlm-source-list">
            {notebook.sources.length ? notebook.sources.map((source) => <GroundingSourceRow key={source.sourceId} source={source} selected={selectedSourceIds.includes(source.sourceId)} busy={busy === `source-${source.sourceId}` || busy === `retry-${source.sourceId}`} onToggle={() => toggleSource(source.sourceId)} onDelete={() => void removeSource(source)} onRetry={() => openSourceRetry(source)} />) : <EmptySources onAdd={openSourcePicker} />}
          </div>
        </div>
      </aside>

      <section className="nlm-panel nlm-center">
        <div className="nlm-center-header">
          <div className="nlm-center-tabs" role="tablist" aria-label="Notebook workspace views">
            <button type="button" role="tab" aria-selected={centerView === "proof"} className={centerView === "proof" ? "active" : ""} onClick={() => setCenterView("proof")}>Proof task</button>
            <button type="button" role="tab" aria-selected={centerView === "chat"} className={centerView === "chat" ? "active" : ""} onClick={() => setCenterView("chat")}>Ask source</button>
            {centerView === "artifact" && <button type="button" role="tab" aria-selected className="active artifact-tab" onClick={() => setCenterView("artifact")}>{activeArtifact?.title || "Output"}</button>}
            {centerView === "notes" && <button type="button" role="tab" aria-selected className="active artifact-tab" onClick={() => setCenterView("notes")}>Notes</button>}
          </div>
          {centerView !== "proof" && <button type="button" className="nlm-icon-button" aria-label="Return to proof task" onClick={() => setCenterView("proof")}><Icon name="back" /></button>}
        </div>
        {error && <div className="nlm-error" role="alert"><span>{error}</span><div className="nlm-error-actions">{retryQuestion && retryableQuestionError === error ? <button type="button" onClick={() => void submitQuestion(undefined, retryQuestion)} disabled={busy === "ask"}>Retry question</button> : null}{retryGeneration ? <button type="button" onClick={() => { if (retryGeneration.kind === "artifact") void makeArtifact(retryGeneration.type); else void makeLesson(); }} disabled={busy !== null}>Retry provider</button> : null}<button type="button" onClick={() => { setError(""); setRetryGeneration(null); }} aria-label="Dismiss error"><Icon name="close" size={14} /></button></div></div>}
        {providerNotice ? <div className="nlm-provider-notice" role="alert"><div><strong>Answer provider unavailable</strong><p>{providerNotice}</p></div><div className="nlm-provider-actions">{retryQuestion ? <button type="button" onClick={() => void submitQuestion(undefined, retryQuestion)} disabled={busy === "ask"}>Retry provider</button> : null}<button type="button" onClick={() => setProviderNotice("")}>Dismiss</button></div></div> : null}
        {centerView === "proof" && <ProofTaskCanvas notebook={notebook} activeSources={activeSources} goal={proofGoal} activity={proofActivity} response={proofResponse} conclusion={proofConclusion} confidence={proofConfidence} busy={proofBusy} feedback={proofFeedback} onResponse={setProofResponse} onConclusion={setProofConclusion} onConfidence={setProofConfidence} onSubmit={submitProof} />}
        {centerView === "chat" && <ChatCanvas messages={messages} activeSources={activeSources} question={question} busy={busy === "ask"} canUseSources={canUseSources} onQuestion={onQuestion => setQuestion(onQuestion)} onSubmit={submitQuestion} onPrompt={setQuestion} onSaveMessage={openNewNote} />}
        {centerView === "artifact" && activeArtifact && <ArtifactCanvas artifact={activeArtifact} pack={notebook.knowledgePack} onBack={() => setCenterView("proof")} />}
        {centerView === "artifact" && !activeArtifact && <EmptyArtifact onBack={() => setCenterView("proof")} />}
        {centerView === "notes" && <NotesCanvas notes={notes} draft={noteDraft} editing={editingNote} busy={busy === "note"} onDraft={setNoteDraft} onSave={() => void saveNote()} onNew={() => openNewNote()} onOpen={openExistingNote} onDelete={(note) => void removeNote(note)} />}
      </section>

      <aside className="nlm-panel nlm-studio" data-open={drawer === "studio"}>
        <PanelHeading title="Source tools" icon="spark" onClose={closeDrawer} />
        <div className="nlm-studio-body">
          <div className="nlm-studio-grid">
            {studioCards.map((card) => <button key={card.type} type="button" className="nlm-studio-card" style={{ borderColor: card.accent }} disabled={!canUseSources && card.type !== "notes"} onClick={() => {
              if (card.type === "notes") openNewNote();
              else if (card.type === "openmaic_lesson") void makeLesson();
              else void makeArtifact(card.type);
            }}>
              <span className="nlm-studio-icon" style={{ color: card.accent, backgroundColor: `${card.accent}17` }}><Icon name={card.icon} /></span>
              <span><strong>{busy === card.type ? "Creating…" : card.label}</strong><small>{card.description}</small></span><Icon name="chevron" size={16} />
            </button>)}
          </div>
          <div className="nlm-saved-heading"><span>Saved outputs</span><button type="button" onClick={() => openNewNote()}>Notes {notes.length}</button></div>
          <div className="nlm-saved-list">
            {notebook.artifacts.filter((artifact) => artifact.status === "ready").slice(0, 5).map((artifact) => <button type="button" key={artifact.artifactId} onClick={() => { setActiveArtifact(artifact); setCenterView("artifact"); closeDrawer(); }}><span className="nlm-saved-icon"><Icon name="file" size={15} /></span><span><strong>{artifact.title}</strong><small>{titleFromArtifact(artifact.type)} · {shortDate(artifact.createdAt)}</small></span><Icon name="chevron" size={15} /></button>)}
            {!notebook.artifacts.some((artifact) => artifact.status === "ready") && <p className="nlm-empty-saved">Your generated study tools will appear here.</p>}
          </div>
          {notebook.artifacts.some((artifact) => artifact.status === "stale") && <p className="nlm-stale-note">Some saved outputs use a removed source and are safely marked stale.</p>}
        </div>
      </aside>
    </div>
  </main>;
}

function PanelHeading({ title, icon, onClose }: { title: string; icon: IconName; onClose: () => void }) {
  return <header className="nlm-panel-heading"><span><Icon name={icon} size={17} /> {title}</span><button type="button" className="nlm-panel-close" onClick={onClose} aria-label={`Close ${title} panel`}><Icon name="close" size={16} /></button></header>;
}

function EmptySources({ onAdd }: { onAdd: () => void }) {
  return <div className="nlm-empty-sources"><span><Icon name="upload" size={25} /></span><strong>Add your first source</strong><p>Upload a PDF, note, or slide deck to create this notebook’s saved context.</p><button type="button" onClick={onAdd}>Choose a file</button></div>;
}

function GroundingSourceRow({ source, selected, busy, onToggle, onDelete, onRetry }: { source: NotebookSource; selected: boolean; busy: boolean; onToggle: () => void; onDelete: () => void; onRetry: () => void }) {
  const ready = source.status === "ready";
  const failed = source.status === "failed";
  const selectable = ready && source.groundingEnabled !== false;
  return <article className={`nlm-source-row ${selected ? "selected" : ""} ${!ready ? "pending" : ""} ${!selectable && ready ? "view-only" : ""}`}>
    <label><input type="checkbox" checked={selected} disabled={!selectable} onChange={onToggle} aria-label={selectable ? `Use ${source.title} as context` : `${source.title} is view-only and excluded from grounded answers`} /><span className="nlm-source-file"><Icon name="file" size={17} /></span><span className="nlm-source-copy"><strong>{source.title}</strong><small>{!ready ? failed ? "Extraction failed. Choose the file again to retry." : "Extracting..." : !selectable ? "View-only - excluded from grounded answers" : `${sourceMetric(source, "pageCount")} pages / ${sourceMetric(source, "blockCount")} blocks`}</small></span></label>
    <div className="nlm-source-row-actions">{failed && source.retryAvailable !== false ? <button type="button" className="nlm-source-retry" disabled={busy} onClick={onRetry}>{busy ? "Retrying..." : "Retry extraction"}</button> : null}<button type="button" className="nlm-source-delete" disabled={busy} aria-label={`Remove ${source.title}`} onClick={onDelete}>{busy ? <Icon name="more" size={15} /> : <Icon name="delete" size={15} />}</button></div>
  </article>;
}

function SourceRow({ source, selected, busy, onToggle, onDelete }: { source: NotebookSource; selected: boolean; busy: boolean; onToggle: () => void; onDelete: () => void }) {
  const ready = source.status === "ready";
  const groundingExcluded = ready && source.groundingEnabled === false;
  return <article className={`nlm-source-row ${selected ? "selected" : ""} ${!ready ? "pending" : ""} ${groundingExcluded ? "view-only" : ""}`}>
    <label><input type="checkbox" checked={selected} disabled={!ready} onChange={onToggle} aria-label={`Use ${source.title} as context`} /><span className="nlm-source-file"><Icon name="file" size={17} /></span><span className="nlm-source-copy"><strong>{source.title}</strong><small>{ready ? `${sourceMetric(source, "pageCount")} pages · ${sourceMetric(source, "blockCount")} blocks` : source.status === "failed" ? "Extraction failed" : "Extracting…"}</small></span></label>
    <button type="button" className="nlm-source-delete" disabled={busy} aria-label={`Remove ${source.title}`} onClick={onDelete}>{busy ? <Icon name="more" size={15} /> : <Icon name="delete" size={15} />}</button>
  </article>;
}

function ProofTaskCanvas({ notebook, activeSources, goal, activity, response, conclusion, confidence, busy, feedback, onResponse, onConclusion, onConfidence, onSubmit }: { notebook: Notebook; activeSources: NotebookSource[]; goal: LearningGoal | null; activity: LearningActivity | null; response: string; conclusion: string; confidence: 1 | 2 | 3 | 4 | 5; busy: boolean; feedback: string; onResponse: (value: string) => void; onConclusion: (value: string) => void; onConfidence: (value: 1 | 2 | 3 | 4 | 5) => void; onSubmit: (event: FormEvent) => void }) {
  const concept = proofConcept(notebook);
  const anchor = firstProofAnchor(notebook);
  return <div className="nlm-proof-canvas">
    <div className="nlm-proof-intro"><span className="nlm-kicker">THE FEYNMAN LOOP</span><h1>Turn this source into demonstrated understanding.</h1><p>Reading and generated answers stay in the desk. Only your prediction, explanation, or derivation can change learner evidence.</p><div className="nlm-proof-loop"><span>SOURCE</span><i>→</i><strong>ATTEMPT</strong><i>→</i><span>FEEDBACK</span><i>→</i><span>NEXT TASK</span></div></div>
  {!activeSources.length ? <div className="nlm-proof-empty"><Icon name="file" size={25} /><h2>Select a ready source first</h2><p>The proof task is source-scoped. Choose a processed source in the left panel so the evaluator can cite a durable page or block anchor.</p></div> : !goal || !activity ? <div className="nlm-proof-empty"><Icon name="spark" size={25} /><h2>Build a goal before recording evidence</h2><p><strong>{concept}</strong> is ready to become a challenge, but this notebook is context memory only until it is attached to a learning goal.</p><Link href={`/?sourceNotebook=${encodeURIComponent(notebook.notebookId)}`} className="nlm-proof-cta">Start a learning goal from this source <Icon name="chevron" size={15} /></Link></div> : <form className="nlm-proof-form" onSubmit={onSubmit}><div className="nlm-proof-task-meta"><span>ACTIVE TASK</span><strong>{activity.type} · {activity.difficulty ? `difficulty ${activity.difficulty}` : "adaptive"}</strong></div><h2>{activity.prompt || `Explain ${concept} in a concrete case.`}</h2><p className="nlm-proof-boundary">Predict first. Use the selected source only to verify your reasoning after you commit.</p><div className="nlm-proof-source"><span>SELECTED SOURCE SIGNAL</span><strong>{concept}</strong><small>{anchor ? `Anchor ${anchor}` : "No durable anchor was extracted yet"}</small></div><label className="nlm-proof-field"><span>Your attempt</span><textarea value={response} onChange={(event) => onResponse(event.target.value)} placeholder="State a prediction, show the mechanism, and name what would falsify it…" rows={7} minLength={24} required /></label><label className="nlm-proof-field"><span>Learner conclusion</span><textarea value={conclusion} onChange={(event) => onConclusion(event.target.value)} placeholder="What did the evidence change in your understanding?" rows={3} /></label><label className="nlm-proof-field"><span>Confidence before feedback: {confidence}/5</span><input type="range" min={1} max={5} value={confidence} onChange={(event) => onConfidence(Number(event.target.value) as 1 | 2 | 3 | 4 | 5)} /></label><div className="nlm-proof-submit"><span>{activeSources.length} source selected · {anchor ? "citation anchor ready" : "citation pending"}</span><button type="submit" disabled={busy || response.trim().length < 24}>{busy ? "Evaluating…" : "Submit proof attempt"}<Icon name="send" size={16} /></button></div>{feedback ? <div className="nlm-proof-feedback" role="status"><strong>Route feedback</strong><p>{feedback}</p></div> : null}</form>}
  </div>;
}

function ChatCanvas({ messages, activeSources, question, busy, canUseSources, onQuestion, onSubmit, onPrompt, onSaveMessage }: { messages: NotebookChatMessage[]; activeSources: NotebookSource[]; question: string; busy: boolean; canUseSources: boolean; onQuestion: (value: string) => void; onSubmit: (event?: FormEvent) => void; onPrompt: (value: string) => void; onSaveMessage: (message: NotebookChatMessage) => void }) {
  return <div className="nlm-chat-canvas">
    <div className="nlm-chat-scroll">
      {!messages.length && <div className="nlm-chat-welcome"><div className="nlm-welcome-orb"><Icon name="spark" size={26} /></div><h1>What would you like to understand?</h1><p>Ask about your selected sources. Every answer stays tied to the page-aware memory saved in this notebook.</p><div className="nlm-prompt-grid">{prompts.map((prompt) => <button type="button" key={prompt} onClick={() => onPrompt(prompt)}>{prompt}<Icon name="chevron" size={15} /></button>)}</div></div>}
      {messages.map((message) => <article className={`nlm-message ${message.role} ${message.status === "stale" ? "stale" : ""}`} key={message.messageId}><div className="nlm-message-avatar">{message.role === "assistant" ? <Icon name="spark" size={15} /> : "You"}</div><div className="nlm-message-content"><p>{message.content}</p>{message.status === "stale" ? <small className="nlm-stale-chip">A cited source was removed</small> : null}{message.role === "assistant" && <><CitationChips anchors={message.sourceAnchorIds} sourceIds={message.sourceIds} /><div className="nlm-message-actions"><button type="button" onClick={() => onSaveMessage(message)}><Icon name="note" size={14} /> Save to note</button><span>{message.groundedIn === "notebook" || !message.groundedIn ? "Source-grounded" : message.groundedIn}</span></div></>}</div></article>)}
      {busy && <article className="nlm-message assistant thinking"><div className="nlm-message-avatar"><Icon name="spark" size={15} /></div><div className="nlm-typing"><i /><i /><i /></div></article>}
    </div>
    <form className="nlm-composer" onSubmit={onSubmit}><textarea value={question} onChange={(event) => onQuestion(event.target.value)} placeholder={canUseSources ? "Start typing…" : "Select at least one processed source first"} rows={2} disabled={!canUseSources || busy} /><div><span>{activeSources.length} source{activeSources.length === 1 ? "" : "s"} selected</span><button type="submit" disabled={!question.trim() || !canUseSources || busy} aria-label="Send question"><Icon name="send" size={19} /></button></div></form>
  </div>;
}

function CitationChips({ anchors, sourceIds }: { anchors: string[]; sourceIds: string[] }) {
  const items = (anchors.length ? anchors : sourceIds).filter((item, index, values) => values.indexOf(item) === index).slice(0, anchors.length ? 4 : 3);
  if (!items.length) return null;
  return <div className="nlm-citations">{items.map((item) => <span key={item}><Icon name="file" size={12} /> {item.length > 28 ? `${item.slice(0, 27)}…` : item}</span>)}</div>;
}

function EmptyArtifact({ onBack }: { onBack: () => void }) {
  return <div className="nlm-empty-output"><span><Icon name="spark" size={28} /></span><h2>Create a source-grounded tool</h2><p>Select a Studio card to build a guide, quiz, slide deck, map, or other output from your saved source memory.</p><button type="button" onClick={onBack}>Back to chat</button></div>;
}

function ArtifactCanvas({ artifact, pack, onBack }: { artifact: NotebookArtifact; pack: Notebook["knowledgePack"]; onBack: () => void }) {
  if (artifact.status !== "ready") return <div className="nlm-empty-output"><span><Icon name="file" size={28} /></span><h2>This output is stale</h2><p>One of its selected sources was removed. Generate it again from the current notebook memory.</p><button type="button" onClick={onBack}>Back to chat</button></div>;
  const payload = artifact.payload;
  const providerLabel = artifact.provider === "fireworks" ? `Fireworks${artifact.model ? ` · ${artifact.model}` : ""}` : artifact.provider === "local_deterministic" ? "Local deterministic source structure" : null;
  return <div className="nlm-artifact-canvas"><div className="nlm-artifact-top"><div><span className="nlm-kicker">SOURCE-GROUNDED OUTPUT</span><h1>{artifact.title}</h1><p>{artifact.sourceIds.length} selected source{artifact.sourceIds.length === 1 ? "" : "s"} · created {shortDate(artifact.createdAt)}{providerLabel ? ` · ${providerLabel}` : ""}</p></div><button type="button" onClick={onBack}><Icon name="back" size={16} /> Chat</button></div>
    {payload.kind === "summary" && <SummaryArtifact payload={payload} />}
    {payload.kind === "mcq" && <QuizArtifact payload={payload} />}
    {payload.kind === "slides" && <SlidesArtifact payload={payload} pack={pack} />}
    {payload.kind === "formula_sheet" && <FormulaArtifact payload={payload} />}
    {payload.kind === "data_table" && <TableArtifact payload={payload} />}
    {payload.kind === "mind_map" && <MindMapArtifact payload={payload} />}
    {payload.kind === "flashcards" && <FlashcardsArtifact payload={payload} />}
    {payload.kind === "important_questions" && <QuestionsArtifact payload={payload} />}
    {payload.kind === "openmaic_lesson" && <LessonArtifact payload={payload} />}
    {!payload.kind && <SummaryArtifact payload={payload} />}
  </div>;
}

function SummaryArtifact({ payload }: { payload: Record<string, any> }) {
  const sections = payload.sections || [];
  return <div className="nlm-summary-list">{sections.length ? sections.map((section: any, index: number) => <article key={`${section.title}-${index}`}><span>{String(index + 1).padStart(2, "0")}</span><div><h3>{section.title}</h3><p>{section.summary}</p><CitationChips anchors={section.sourceAnchors || []} sourceIds={section.sourceIds || []} /></div></article>) : <p className="nlm-artifact-empty">No readable source sections were available for this output.</p>}</div>;
}

function QuizArtifact({ payload }: { payload: Record<string, any> }) {
  const questions = payload.questions || [];
  const [index, setIndex] = useState(0);
  const [answer, setAnswer] = useState<number | null>(null);
  const question = questions[index];
  if (!question) return <p className="nlm-artifact-empty">No defensible quiz question could be built from the selected sources.</p>;
  const reveal = answer !== null;
  return <div className="nlm-quiz"><div className="nlm-quiz-meta"><span>QUESTION {index + 1} OF {questions.length}</span><span>{question.topicTitle || "Source topic"}</span></div><h2>{question.question}</h2><div className="nlm-quiz-options">{(question.options || []).map((option: string, optionIndex: number) => <button type="button" key={`${option}-${optionIndex}`} disabled={reveal} className={reveal && optionIndex === question.answerIndex ? "correct" : reveal && optionIndex === answer ? "incorrect" : ""} onClick={() => setAnswer(optionIndex)}><b>{String.fromCharCode(65 + optionIndex)}</b><span>{option}</span></button>)}</div>{reveal && <div className="nlm-quiz-answer"><strong>{answer === question.answerIndex ? "Correct" : "Review this one"}</strong><p>{question.explanation}</p><CitationChips anchors={question.sourceAnchors || []} sourceIds={question.sourceIds || []} /></div>}<div className="nlm-artifact-nav"><button type="button" onClick={() => { setIndex((value) => Math.max(0, value - 1)); setAnswer(null); }} disabled={index === 0}>Previous</button><button type="button" onClick={() => { setIndex((value) => Math.min(questions.length - 1, value + 1)); setAnswer(null); }} disabled={!reveal || index === questions.length - 1}>Next question</button></div></div>;
}

function SlidesArtifact({ payload, pack }: { payload: Record<string, any>; pack: Notebook["knowledgePack"] }) {
  const slides = payload.slides || [];
  const [index, setIndex] = useState(0);
  const slide = slides[index];
  if (!slide) return <p className="nlm-artifact-empty">No slide sequence could be created from the selected sources.</p>;
  const assets = (slide.assetIds || []).map((id: string) => (payload.assets || pack.assets || []).find((asset: any) => asset.assetId === id)).filter(Boolean);
  return <div className="nlm-slide"><span className="nlm-slide-count">SLIDE {String(index + 1).padStart(2, "0")} / {String(slides.length).padStart(2, "0")}</span><div className="nlm-slide-layout"><div><span className="nlm-kicker">{slide.slideLabel || "KEY IDEA"}</span><h2>{slide.title}</h2><p>{slide.body}</p>{slide.bullets?.length ? <ul>{slide.bullets.map((bullet: string) => <li key={bullet}>{bullet}</li>)}</ul> : null}<CitationChips anchors={slide.sourceAnchors || []} sourceIds={slide.sourceIds || []} /></div>{assets.length ? <div className="nlm-slide-visual">{assets.slice(0, 1).map((asset: any) => <figure key={asset.assetId}><img src={asset.dataUrl || asset.url} alt={asset.alt || "Source visual"} /><figcaption>{asset.alt || "Source visual"}{asset.page ? ` · p. ${asset.page}` : ""}</figcaption></figure>)}</div> : slide.diagram?.nodes?.length ? <MiniDiagram diagram={slide.diagram} /> : <div className="nlm-slide-placeholder"><Icon name="mind" size={30} /><span>{slide.visualHint || "Source-backed idea"}</span></div>}</div><div className="nlm-artifact-nav"><button type="button" onClick={() => setIndex((value) => Math.max(0, value - 1))} disabled={index === 0}>Previous slide</button><button type="button" onClick={() => setIndex((value) => Math.min(slides.length - 1, value + 1))} disabled={index === slides.length - 1}>Next slide</button></div></div>;
}

function FormulaArtifact({ payload }: { payload: Record<string, any> }) {
  const formulas = payload.formulas || [];
  return <div className="nlm-formula-list">{formulas.length ? formulas.map((formula: any) => <article key={formula.formulaId || formula.text}><strong>{formula.text}</strong><span>{formula.sourceId}{formula.page ? ` · page ${formula.page}` : ""}</span></article>) : <p className="nlm-artifact-empty">No equation-like source text was detected in the selected sources.</p>}</div>;
}

function TableArtifact({ payload }: { payload: Record<string, any> }) {
  const rows = payload.rows || [];
  return <div className="nlm-data-table-wrap"><p className="nlm-table-note">{payload.note}</p><div className="nlm-data-table"><table><thead><tr><th>Topic</th><th>Pages</th><th>Key idea</th><th>Formulas</th></tr></thead><tbody>{rows.map((row: any) => <tr key={row.topic}><td><strong>{row.topic}</strong></td><td>{(row.pages || []).join(", ") || "—"}</td><td>{row.keyIdea}</td><td>{(row.formulas || []).join(" · ") || "—"}</td></tr>)}</tbody></table></div></div>;
}

function MindMapArtifact({ payload }: { payload: Record<string, any> }) {
  const nodes = payload.nodes || [];
  const root = nodes.find((node: any) => node.kind === "root") || nodes[0];
  const topics = nodes.filter((node: any) => node.id !== root?.id);
  if (!root) return <p className="nlm-artifact-empty">No source topics are available for a mind map.</p>;
  return <div className="nlm-mind-map"><p>{payload.note}</p><div className="nlm-mind-root"><Icon name="mind" size={20} /><strong>{root.label}</strong></div><div className="nlm-mind-branches">{topics.map((topic: any) => <article key={topic.id}><span className="nlm-mind-line" /><h3>{topic.label}</h3><p>{topic.detail}</p><CitationChips anchors={topic.sourceAnchors || []} sourceIds={topic.sourceIds || []} /></article>)}</div></div>;
}

function MiniDiagram({ diagram }: { diagram: { nodes?: Array<{ id: string; label: string }>; edges?: Array<{ from: string; to: string }> } }) {
  const nodes = diagram.nodes || [];
  return <div className="nlm-mini-diagram">{nodes.map((node) => <span key={node.id}>{node.label}</span>)}</div>;
}

function FlashcardsArtifact({ payload }: { payload: Record<string, any> }) {
  const cards = payload.cards || [];
  const [index, setIndex] = useState(0);
  const [revealed, setRevealed] = useState(false);
  const card = cards[index];
  if (!card) return <p className="nlm-artifact-empty">No source-backed flashcards could be created.</p>;
  return <div className="nlm-flashcards"><button type="button" className={`nlm-flashcard ${revealed ? "revealed" : ""}`} onClick={() => setRevealed((value) => !value)}><span>{revealed ? "SOURCE-BACKED ANSWER" : card.tag || "RECALL"}</span><strong>{revealed ? card.back : card.front}</strong><small>Click to {revealed ? "hide" : "reveal"} the answer</small></button><CitationChips anchors={card.sourceAnchors || []} sourceIds={card.sourceIds || []} /><div className="nlm-artifact-nav"><button type="button" onClick={() => { setIndex((value) => Math.max(0, value - 1)); setRevealed(false); }} disabled={index === 0}>Previous</button><span>{index + 1} / {cards.length}</span><button type="button" onClick={() => { setIndex((value) => Math.min(cards.length - 1, value + 1)); setRevealed(false); }} disabled={index === cards.length - 1}>Next</button></div></div>;
}

function QuestionsArtifact({ payload }: { payload: Record<string, any> }) {
  const questions = payload.questions || [];
  return <div className="nlm-question-list">{questions.map((question: any, index: number) => <article key={question.id || index}><span>{String(index + 1).padStart(2, "0")}</span><div><small>{question.kind === "apply" ? "APPLY" : "EXPLAIN"}</small><h3>{question.question}</h3><details><summary>What a strong answer should contain</summary><p>{question.answerFocus}</p></details><CitationChips anchors={question.sourceAnchors || []} sourceIds={question.sourceIds || []} /></div></article>)}</div>;
}

function LessonArtifact({ payload }: { payload: Record<string, any> }) {
  const slides = payload.slides || [];
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const slide = slides[index];
  useEffect(() => () => window.speechSynthesis?.cancel(), []);
  if (!slide) return <p className="nlm-artifact-empty">This narrated lesson has no readable scenes.</p>;
  function toggleNarration() {
    if (!window.speechSynthesis) return;
    if (playing) { window.speechSynthesis.cancel(); setPlaying(false); return; }
    window.speechSynthesis.cancel();
    const speech = new SpeechSynthesisUtterance(slide.narration || slide.body || slide.title);
    speech.rate = 0.94;
    speech.onend = () => setPlaying(false);
    window.speechSynthesis.speak(speech); setPlaying(true);
  }
  return <div className="nlm-lesson"><div className="nlm-lesson-stage"><span className="nlm-kicker">SCENE {index + 1} · NARRATED LESSON</span><h2>{slide.title}</h2><p>{slide.body}</p>{slide.bullets?.length ? <ul>{slide.bullets.map((bullet: string) => <li key={bullet}>{bullet}</li>)}</ul> : null}<CitationChips anchors={slide.sourceAnchorIds || slide.sourceAnchors || []} sourceIds={payload.sourceIds || []} /></div><div className="nlm-artifact-nav"><button type="button" onClick={() => setIndex((value) => Math.max(0, value - 1))} disabled={index === 0}>Previous scene</button><button type="button" className="nlm-play" onClick={toggleNarration}><Icon name="audio" size={16} /> {playing ? "Pause narration" : "Play narration"}</button><button type="button" onClick={() => setIndex((value) => Math.min(slides.length - 1, value + 1))} disabled={index === slides.length - 1}>Next scene</button></div></div>;
}

function NotesCanvas({ notes, draft, editing, busy, onDraft, onSave, onNew, onOpen, onDelete }: { notes: NotebookNote[]; draft: { title: string; content: string; sourceIds: string[]; sourceAnchorIds: string[] }; editing: NotebookNote | null; busy: boolean; onDraft: (value: { title: string; content: string; sourceIds: string[]; sourceAnchorIds: string[] }) => void; onSave: () => void; onNew: () => void; onOpen: (note: NotebookNote) => void; onDelete: (note: NotebookNote) => void }) {
  return <div className="nlm-notes-canvas"><aside><div><span className="nlm-kicker">YOUR NOTES</span><button type="button" onClick={onNew}><Icon name="add" size={15} /> New note</button></div><div className="nlm-note-list">{notes.length ? notes.map((note) => <article className={editing?.noteId === note.noteId ? "active" : ""} key={note.noteId}><button type="button" onClick={() => onOpen(note)}><strong>{note.title}</strong><small>{shortDate(note.updatedAt)} · {note.sourceIds.length ? `${note.sourceIds.length} sources` : "personal"}</small></button><button type="button" aria-label={`Delete ${note.title}`} onClick={() => onDelete(note)}><Icon name="delete" size={14} /></button></article>) : <p>No saved notes yet.</p>}</div></aside><section><span className="nlm-kicker">{editing ? "EDIT NOTE" : "NEW NOTE"}</span><input value={draft.title} onChange={(event) => onDraft({ ...draft, title: event.target.value })} placeholder="Note title" maxLength={240} /><textarea value={draft.content} onChange={(event) => onDraft({ ...draft, content: event.target.value })} placeholder="Write what you want to remember…" rows={12} maxLength={12000} /><div className="nlm-note-footer"><CitationChips anchors={draft.sourceAnchorIds} sourceIds={draft.sourceIds} /><button type="button" onClick={onSave} disabled={!draft.content.trim() || busy}>{busy ? "Saving…" : editing ? "Save changes" : "Save note"}</button></div></section></div>;
}
