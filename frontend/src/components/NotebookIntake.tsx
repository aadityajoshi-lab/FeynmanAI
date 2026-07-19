"use client";

import Link from "next/link";
import { ChangeEvent, DragEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { createNotebook, uploadNotebookSource } from "@/lib/notebookApi";
import type { NotebookGoal } from "@/lib/notebookTypes";

type QueuedFile = { id: string; file: File; kind: "reference" | "past_questions" };
const MAX_BYTES = 50 * 1024 * 1024;
const ACCEPT = ".pdf,.md,.txt,.csv,.docx,.pptx,.png,.jpg,.jpeg,.webp";

const goals: Array<{ id: NotebookGoal; label: string; description: string; icon: string }> = [
  { id: "understand", label: "Learn a subject", description: "Build a clear map from your books, notes, and lectures.", icon: "01" },
  { id: "exam", label: "Prepare for an exam", description: "Turn material and past papers into targeted practice.", icon: "02" },
  { id: "interview", label: "Prepare for an interview", description: "Rehearse important questions with follow-up prompts.", icon: "03" },
  { id: "viva", label: "Practice a viva or lab", description: "Explain procedures, diagrams, and decisions under pressure.", icon: "04" },
  { id: "language", label: "Build a language skill", description: "Start with a goal; add resources only when useful.", icon: "05" },
];

function fileKey(file: File) { return `${file.name}-${file.size}-${file.lastModified}`; }

export default function NotebookIntake() {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [subject, setSubject] = useState("");
  const [description, setDescription] = useState("");
  const [goal, setGoal] = useState<NotebookGoal>("understand");
  const [ocrProvider, setOcrProvider] = useState<"auto" | "local" | "mistral">("auto");
  const [files, setFiles] = useState<QueuedFile[]>([]);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState("");
  const [error, setError] = useState("");

  function addFiles(selected: FileList | File[], kind: "reference" | "past_questions" = "reference") {
    const incoming: QueuedFile[] = [];
    for (const file of Array.from(selected)) {
      const extension = file.name.toLowerCase().split(".").pop() || "";
      if (!ACCEPT.includes(extension) && !file.type.startsWith("image/")) { setError(`${file.name} is not supported. Add a PDF, note, slide, image, or CSV.`); continue; }
      if (file.size > MAX_BYTES) { setError(`${file.name} is larger than 50 MB.`); continue; }
      if (!files.some((item) => item.file.name === file.name && item.file.size === file.size)) incoming.push({ id: `${kind}-${fileKey(file)}`, file, kind });
    }
    if (incoming.length) { setFiles((current) => [...current, ...incoming]); setError(""); }
  }

  function drop(event: DragEvent<HTMLDivElement>, kind: "reference" | "past_questions" = "reference") { event.preventDefault(); setDragging(false); addFiles(event.dataTransfer.files, kind); }

  async function openNotebook() {
    setError("");
    if (!title.trim()) { setError("Name your notebook first — for example, Digital Instrumentation."); return; }
    setBusy(true);
    try {
      const notebook = await createNotebook({ title: title.trim(), subject: subject.trim() || title.trim(), description: description.trim(), learningGoal: goal, ocrProvider });
      for (let index = 0; index < files.length; index += 1) {
        const item = files[index];
        setProgress(`Reading source ${index + 1} of ${files.length} · ${item.file.name}`);
        await uploadNotebookSource(notebook.notebookId, item.file, { sourceKind: item.kind, ocrProvider });
      }
      setProgress("Opening your notebook…");
      router.push(`/notebooks/${notebook.notebookId}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The notebook could not be prepared.");
    } finally { setBusy(false); setProgress(""); }
  }

  return <main className="notebook-intake-shell">
    <header className="notebook-header"><Link href="/" className="notebook-brand">feynman<span>.ai</span></Link><div className="notebook-header-meta"><span className="notebook-status-dot" /> private study workspace <span>·</span> source-first</div></header>
    <section className="notebook-intake-hero"><div><span className="notebook-eyebrow">YOUR KNOWLEDGE WORKSPACE</span><h1>Bring the material.<br /><em>Keep the understanding.</em></h1><p>Upload your books, notes, scans, or question papers. Feynman builds one structured knowledge pack, then lets you turn it into the exact study tool you need.</p></div><div className="notebook-hero-note"><strong>One notebook. Many ways to learn.</strong><span>Ask questions · make a quiz · study slides · find formulas · rehearse important questions</span></div></section>

    <div className="notebook-intake-layout">
      <section className="notebook-intake-card">
        <div className="notebook-card-heading"><div><span className="notebook-eyebrow">01 · SET THE NORTH STAR</span><h2>What are you building this notebook for?</h2><p>This only sets the default tone. You can create any output later.</p></div><span className="notebook-card-count">{files.length} source{files.length === 1 ? "" : "s"}</span></div>
        <div className="notebook-goal-grid">{goals.map((item) => <button key={item.id} type="button" className={`notebook-goal ${goal === item.id ? "selected" : ""}`} onClick={() => setGoal(item.id)}><span className="notebook-goal-number">{item.icon}</span><span><strong>{item.label}</strong><small>{item.description}</small></span><i>{goal === item.id ? "✓" : ""}</i></button>)}</div>
        <div className="notebook-field-grid"><label><span>Notebook name</span><input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Digital Instrumentation" maxLength={160} /></label><label><span>Subject or skill <em>optional</em></span><input value={subject} onChange={(event) => setSubject(event.target.value)} placeholder="Instrumentation systems" maxLength={160} /></label></div>
        <label className="notebook-field notebook-description"><span>What do you want to be able to do?</span><textarea value={description} onChange={(event) => setDescription(event.target.value)} placeholder="For example: understand every section, solve numerical problems, and explain block diagrams in a viva." rows={3} maxLength={500} /></label>
      </section>

      <section className="notebook-intake-card notebook-source-card">
        <div className="notebook-card-heading"><div><span className="notebook-eyebrow">02 · ADD YOUR SOURCES</span><h2>Everything starts here</h2><p>Upload multiple sources. The extractor keeps text, tables, equations, page references, and visual assets together.</p></div><span className="notebook-card-count">up to 50 MB each</span></div>
        <div className={`notebook-dropzone ${dragging ? "dragging" : ""}`} onDragEnter={(event) => { event.preventDefault(); setDragging(true); }} onDragOver={(event) => event.preventDefault()} onDragLeave={() => setDragging(false)} onDrop={(event) => drop(event)}><input id="notebook-files" type="file" accept={ACCEPT} multiple onChange={(event: ChangeEvent<HTMLInputElement>) => event.target.files && addFiles(event.target.files)} /><label htmlFor="notebook-files"><span className="notebook-upload-icon">＋</span><strong>Drop notes, books, or scans here</strong><small>PDF · DOCX · PPTX · Markdown · images · CSV</small><b>Browse files</b></label></div>
        <div className="notebook-source-rows">{files.filter((item) => item.kind === "reference").map((item) => <div className="notebook-source-row" key={item.id}><span className="notebook-file-icon">{item.file.name.toLowerCase().endsWith(".pdf") ? "PDF" : "DOC"}</span><span><strong>{item.file.name}</strong><small>{(item.file.size / 1024 / 1024).toFixed(1)} MB · ready to extract</small></span><button type="button" onClick={() => setFiles((current) => current.filter((entry) => entry.id !== item.id))} aria-label={`Remove ${item.file.name}`}>×</button></div>)}</div>
        <div className="notebook-past-row"><div><span className="notebook-mini-icon">?</span><span><strong>Past questions or question banks</strong><small>Optional · they shape important questions and exam practice.</small></span></div><label className="notebook-add-small" htmlFor="notebook-past-files">Add files<input id="notebook-past-files" type="file" accept={ACCEPT} multiple onChange={(event: ChangeEvent<HTMLInputElement>) => event.target.files && addFiles(event.target.files, "past_questions")} /></label></div>
        {files.filter((item) => item.kind === "past_questions").length > 0 && <div className="notebook-past-list">{files.filter((item) => item.kind === "past_questions").map((item) => <span key={item.id}>{item.file.name}<button type="button" onClick={() => setFiles((current) => current.filter((entry) => entry.id !== item.id))}>×</button></span>)}</div>}
      </section>

      <section className="notebook-intake-card notebook-pipeline-card"><div className="notebook-card-heading"><div><span className="notebook-eyebrow">03 · CHOOSE THE EXTRACTOR</span><h2>Make the source pack trustworthy</h2><p>Use Mistral OCR 4 for complex scans, tables, handwriting, equations, and page-level visual blocks.</p></div></div><div className="notebook-ocr-options" role="radiogroup" aria-label="OCR provider"><button type="button" className={ocrProvider === "auto" ? "selected" : ""} onClick={() => setOcrProvider("auto")}><span>✦</span><strong>Automatic</strong><small>Use Mistral when configured; otherwise stay offline.</small></button><button type="button" className={ocrProvider === "mistral" ? "selected" : ""} onClick={() => setOcrProvider("mistral")}><span>◎</span><strong>Mistral OCR 4</strong><small>Best for scanned pages, equations, and visual blocks.</small></button><button type="button" className={ocrProvider === "local" ? "selected" : ""} onClick={() => setOcrProvider("local")}><span>⌁</span><strong>Offline extraction</strong><small>Fast local PDF and text extraction for private drafts.</small></button></div><div className="notebook-pipeline"><span className="done">1 <b>Upload</b></span><i>→</i><span>2 <b>Extract</b></span><i>→</i><span>3 <b>Structure</b></span><i>→</i><span>4 <b>Create</b></span></div></section>

      {error && <p className="notebook-error" role="alert">{error}</p>}
      <div className="notebook-intake-actions"><span>Sources remain organized inside this notebook.</span><button type="button" className="notebook-primary-button" onClick={() => void openNotebook()} disabled={busy}>{busy ? progress || "Preparing notebook…" : files.length ? "Build my source workspace →" : "Open an empty notebook →"}</button></div>
    </div>
    {busy && <div className="notebook-busy" role="status" aria-live="polite"><div><span className="notebook-spinner" /><span className="notebook-eyebrow">BUILDING YOUR NOTEBOOK</span><h2>{progress || "Preparing your source workspace…"}</h2><p>Each source is extracted separately, then merged into one page-aware knowledge pack.</p></div></div>}
  </main>;
}
