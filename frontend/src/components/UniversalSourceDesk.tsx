"use client";

import Link from "next/link";
import { ChangeEvent, FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { FeynmanIcon, LearningAppShell, SectionHeading } from "./LearningAppShell";
import { isAuthenticationError, learningOsApi } from "@/lib/learningOsApi";
import { addNotebookTextSource, createNotebook, getNotebook, uploadNotebookSource } from "@/lib/notebookApi";
import type { Course, LearningGoal } from "@/lib/learningOsTypes";
import type { Notebook } from "@/lib/notebookTypes";

type SourceKind = "file" | "url" | "text";
type SourceDeskAccess = "checking" | "ready" | "sign-in" | "error";
const FILE_ACCEPT = ".pdf,.md,.txt,.csv,.docx,.pptx,.png,.jpg,.jpeg,.webp";

function readableError(error: unknown, fallback: string) { return error instanceof Error ? error.message : fallback; }
function formatStatus(value: string) { return value.replaceAll("_", " "); }

export function UniversalSourceDesk() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const requestedGoalId = searchParams.get("goal") || "";
  const requestedCourseId = searchParams.get("course") || "";
  const requestedNotebookId = searchParams.get("notebook") || "";
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [goals, setGoals] = useState<LearningGoal[]>([]);
  const [courses, setCourses] = useState<Course[]>([]);
  const [targetNotebook, setTargetNotebook] = useState<Notebook | null>(null);
  const [notebookLoadError, setNotebookLoadError] = useState("");
  const [access, setAccess] = useState<SourceDeskAccess>("checking");
  const [accessError, setAccessError] = useState("");
  const [goalId, setGoalId] = useState(requestedGoalId);
  const [courseId, setCourseId] = useState(requestedCourseId);
  const [goalLoadError, setGoalLoadError] = useState("");
  const [title, setTitle] = useState("");
  const [purpose, setPurpose] = useState("");
  const [grounded, setGrounded] = useState(true);
  const [kind, setKind] = useState<SourceKind>("file");
  const [file, setFile] = useState<File | null>(null);
  const [url, setUrl] = useState("");
  const [sourceText, setSourceText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let live = true;
    async function loadAccount() {
      try {
        await learningOsApi.me();
        if (!live) return;
        setAccess("ready");
        try {
          const [goalResult, courseResult] = await Promise.all([learningOsApi.goals(), learningOsApi.courses()]);
          if (!live) return;
          setGoals(goalResult.goals);
          setCourses(courseResult.courses);
          if (requestedNotebookId) {
            try {
              const notebookResult = await getNotebook(requestedNotebookId);
              if (!live) return;
              setTargetNotebook(notebookResult);
              setGoalId(requestedGoalId || notebookResult.goalId || "");
              setCourseId(requestedCourseId || notebookResult.courseId || "");
            } catch (caught) {
              if (!live) return;
              if (isAuthenticationError(caught)) { setAccess("sign-in"); return; }
              setNotebookLoadError(readableError(caught, "This notebook could not be loaded."));
            }
          }
        } catch (caught) {
          if (!live) return;
          if (isAuthenticationError(caught)) { setAccess("sign-in"); return; }
          setGoalLoadError(readableError(caught, "Your goals could not be loaded."));
        }
      } catch (caught) {
        if (!live) return;
        if (isAuthenticationError(caught)) { setAccess("sign-in"); return; }
        setAccessError(readableError(caught, "We could not confirm your account."));
        setAccess("error");
      }
    }
    void loadAccount();
    return () => { live = false; };
  }, [requestedCourseId, requestedGoalId, requestedNotebookId]);

  useEffect(() => {
    setGoalId(requestedGoalId || targetNotebook?.goalId || "");
    setCourseId(requestedCourseId || targetNotebook?.courseId || "");
  }, [requestedCourseId, requestedGoalId, targetNotebook?.courseId, targetNotebook?.goalId]);
  const selectedGoal = useMemo(() => goals.find((goal) => goal.goalId === goalId), [goals, goalId]);
  const selectedCourse = useMemo(() => courses.find((course) => course.courseId === courseId), [courseId, courses]);
  const courseChoices = useMemo(() => selectedGoal?.courseId ? courses.filter((course) => course.courseId === selectedGoal.courseId) : courses, [courses, selectedGoal?.courseId]);
  const defaultTitle = targetNotebook?.title || (selectedGoal ? `${selectedGoal.title} sources` : "Source desk");
  const goalIsLocked = Boolean(requestedGoalId || targetNotebook);

  useEffect(() => { if (selectedGoal?.courseId) setCourseId(selectedGoal.courseId); }, [selectedGoal?.courseId]);
  function chooseFile(event: ChangeEvent<HTMLInputElement>) { const next = event.target.files?.[0] || null; setFile(next); if (next) setError(""); }

  async function createDesk(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (access !== "ready") return;
    if (kind === "file" && !file) { setError("Choose a PDF, image, document, slide, or other supported source file."); return; }
    if (kind === "url" && !url.trim()) { setError("Add a webpage URL before creating this source."); return; }
    if (kind === "text" && !sourceText.trim()) { setError("Paste a source excerpt or notes before creating this source."); return; }
    if (requestedNotebookId && !targetNotebook) { setError("This notebook is unavailable. Return to Source Desk and choose another notebook."); return; }
    setBusy(true);
    try {
      const notebook = targetNotebook || await createNotebook({
          title: (title.trim() || defaultTitle).slice(0, 160),
          subject: selectedGoal?.domain.replaceAll("_", " ") || "Source context",
          description: [purpose.trim(), grounded ? "Use this source for grounded answers and verification." : "Keep this source separate from grounded verification."].filter(Boolean).join(" "),
          learningGoal: "understand",
          ocrProvider: "auto",
          ...(goalId ? { goalId } : {}),
          ...(courseId ? { courseId } : {}),
        });
      if (!targetNotebook && goalId) await learningOsApi.attachGoalNotebook(goalId, notebook.notebookId);
      if (kind === "file" && file) await uploadNotebookSource(notebook.notebookId, file, { sourceKind: "reference", ocrProvider: "auto", useForGrounding: grounded });
      if (kind === "url") await addNotebookTextSource(notebook.notebookId, { url: url.trim(), title: title.trim() || "Webpage source", sourceKind: "url_reference", useForGrounding: grounded, fetchWebsite: true, ocrProvider: "auto" });
      if (kind === "text") await addNotebookTextSource(notebook.notebookId, { text: sourceText.trim(), title: title.trim() || "Pasted source notes", sourceKind: "pasted_notes", useForGrounding: grounded });
      router.push(`/notebooks/${notebook.notebookId}`);
    } catch (caught) {
      if (isAuthenticationError(caught)) { router.push(`/login?next=${encodeURIComponent("/sources")}` as never); return; }
      setError(readableError(caught, "The source could not be created."));
    } finally { setBusy(false); }
  }

  const query = new URLSearchParams({ ...(requestedGoalId ? { goal: requestedGoalId } : {}), ...(requestedCourseId ? { course: requestedCourseId } : {}), ...(requestedNotebookId ? { notebook: requestedNotebookId } : {}) });
  const nextPath = query.toString() ? `/sources?${query.toString()}` : "/sources";
  if (access === "checking") return <LearningAppShell eyebrow="SOURCE DESK" title="Add source"><section className="fos-route-state loading" role="status"><span className="fos-loading-orb" /><h2>Checking your workspace…</h2><p>Sources always belong to an account-owned workspace.</p></section></LearningAppShell>;
  if (access === "sign-in") return <LearningAppShell eyebrow="SOURCE DESK" title="Sign in required"><section className="fos-route-state empty"><FeynmanIcon name="lock" size={28} /><h2>Sign in before adding a source</h2><p>Source files, webpages, extracted text, and anchors belong to your account.</p><Link href={`/login?next=${encodeURIComponent(nextPath)}` as never} className="fos-primary-action">Sign in to continue <FeynmanIcon name="arrow" /></Link></section></LearningAppShell>;
  if (access === "error") return <LearningAppShell eyebrow="SOURCE DESK" title="Add source"><section className="fos-route-state error" role="alert"><FeynmanIcon name="close" size={24} /><h2>Account check unavailable</h2><p>{accessError}</p><Link href={"/login" as never} className="fos-quiet-action">Go to sign in</Link></section></LearningAppShell>;
  if (requestedNotebookId && notebookLoadError) return <LearningAppShell eyebrow="SOURCE DESK" title="Notebook unavailable"><section className="fos-route-state error" role="alert"><FeynmanIcon name="close" size={24} /><h2>Notebook unavailable</h2><p>{notebookLoadError}</p><Link href="/sources" className="fos-quiet-action">Back to Source Desk</Link></section></LearningAppShell>;

  return <LearningAppShell eyebrow="SOURCE DESK" title="Add source">
    <SectionHeading eyebrow="SOURCE DESK" title={targetNotebook ? `Add context to ${targetNotebook.title}` : selectedGoal ? `Sources for ${selectedGoal.title}` : "Bring the sources you want to learn from."} copy="Add or edit context here after a goal exists. Feynman keeps source context separate from your demonstrated learner evidence." />
    <section className="fos-source-entry-layout">
      <form className="fos-source-entry-form" onSubmit={(event) => void createDesk(event)}>
        <div className="fos-source-entry-head"><div><span className="fos-eyebrow">SOURCE INPUT</span><h2>{targetNotebook ? "Add another source." : "Choose a source."}</h2></div><span>PDFs, images, documents, or webpages</span></div>
        <div className="fos-context-kind-grid" role="radiogroup" aria-label="Source type">
          {([["file", "Upload a file", "PDF, image, document, slide, or table"], ["text", "Paste notes", "Keep a source excerpt with durable text anchors"], ["url", "Add a webpage", "Extract readable text, metadata, and available visuals"]] as Array<[SourceKind, string, string]>).map(([value, label, copy]) => <button key={value} type="button" className={kind === value ? "selected" : ""} role="radio" aria-checked={kind === value} onClick={() => setKind(value)}><strong>{label}</strong><small>{copy}</small></button>)}
        </div>
        {kind === "file" ? <div className="fos-context-input"><input ref={fileInputRef} type="file" accept={FILE_ACCEPT} hidden onChange={chooseFile} /><button type="button" className="fos-drop-target" onClick={() => fileInputRef.current?.click()}><FeynmanIcon name="source" size={22} /><span><strong>{file ? file.name : "Choose a source file"}</strong><small>{file ? `${Math.max(1, Math.round(file.size / 1024))} KB selected` : "PDF, text, Markdown, CSV, Word, slides, or image"}</small></span></button></div> : null}
        {kind === "url" ? <label className="fos-field"><span>Webpage URL</span><input type="url" value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://…" inputMode="url" /></label> : null}
        {kind === "text" ? <label className="fos-field"><span>Source excerpt or notes</span><textarea value={sourceText} onChange={(event) => setSourceText(event.target.value)} placeholder="Paste the bounded source passage you want Feynman to cite…" rows={8} maxLength={120000} /></label> : null}
        <div className="fos-source-entry-meta">{goalIsLocked && selectedGoal ? <div className="fos-field"><span>Attached goal</span><strong>{selectedGoal.title}</strong><small>{formatStatus(selectedGoal.domain)} · sources can be edited later from this goal.</small></div> : <label className="fos-field"><span>Attach to a goal <em>optional</em></span><select value={goalId} onChange={(event) => setGoalId(event.target.value)}><option value="">Keep this source independent</option>{goals.map((goal) => <option key={goal.goalId} value={goal.goalId}>{goal.title}</option>)}</select></label>}<label className="fos-field"><span>Attach to a course <em>optional</em></span><select value={courseId} onChange={(event) => setCourseId(event.target.value)} disabled={Boolean(selectedGoal?.courseId)}><option value="">Keep this source outside a course</option>{courseChoices.map((course) => <option key={course.courseId} value={course.courseId}>{course.title}</option>)}</select><small>{selectedGoal?.courseId ? "This goal already has a fixed course scope." : selectedCourse ? "Course scope never exposes raw source text." : "A course scope keeps this source inside that workspace."}</small></label><label className="fos-field"><span>Source label <em>optional</em></span><input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={160} placeholder="For example: Chapter 7 notes" /></label></div>
        <label className="fos-source-toggle"><input type="checkbox" checked={grounded} onChange={(event) => setGrounded(event.target.checked)} /><span><FeynmanIcon name="shield" /><strong>Use this source for grounded answers</strong><small>Only selected, ready sources are sent to chat or generated lessons.</small></span></label>
        {goalLoadError ? <p className="fos-subtle-error">{goalLoadError}</p> : null}{error ? <p className="fos-form-error" role="alert">{error}</p> : null}
        <div className="fos-source-entry-actions"><Link href="/home" className="fos-quiet-action">Cancel</Link><button type="submit" className="fos-goal-submit" disabled={busy}>{busy ? "Creating source…" : kind === "url" ? "Add webpage source" : kind === "text" ? "Save source notes" : "Upload source"}<FeynmanIcon name="arrow" /></button></div>
      </form>
      <aside className="fos-source-entry-aside"><span className="fos-eyebrow">SOURCE BOUNDARY</span><h2>Context is not learner state.</h2><p>OCR, source blocks, page anchors, chat, and generated lessons stay with this source desk. Only an observable learner attempt can change evidence.</p><dl><div><dt>Selected sources</dt><dd>Scope every answer and output</dd></div><div><dt>Stale sources</dt><dd>Excluded from new grounded work</dd></div><div><dt>Evidence</dt><dd>Requires an actual learner response</dd></div></dl></aside>
    </section>
  </LearningAppShell>;
}
