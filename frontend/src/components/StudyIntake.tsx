"use client";

import Link from "next/link";
import { ChangeEvent, DragEvent, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { studyModes } from "@/lib/learningModes";
import type { StudyAsset } from "@/lib/studyTypes";
import { generateStudyPlan, getProviderStatus, ingestStudySource, ingestStudyUrl, ProviderStatus, StudySourceIngestResponse } from "@/lib/studyApi";

const acceptedTypes = new Set(["application/pdf", "image/png", "image/jpeg", "image/webp", "video/mp4", "video/webm", "video/quicktime", "audio/mpeg", "audio/wav", "audio/x-wav", "audio/ogg", "audio/webm"]);
type LiveProvider = "fireworks" | "openai";

function assetKind(type: string): StudyAsset["kind"] {
  if (type === "application/pdf") return "pdf";
  if (type.startsWith("image/")) return "image";
  if (type.startsWith("audio/")) return "audio";
  return "video";
}

function slugify(value: string) {
  return value.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "-").slice(0, 90) || "selected-module";
}

export default function StudyIntake() {
  const router = useRouter();
  const [subjectTitle, setSubjectTitle] = useState("");
  const [moduleFocus, setModuleFocus] = useState("");
  const [chapterSelection, setChapterSelection] = useState<"chapter_1" | "all">("chapter_1");
  const [learningMode, setLearningMode] = useState<string>(studyModes[0].id);
  const [provider, setProvider] = useState<LiveProvider>("fireworks");
  const [providers, setProviders] = useState<ProviderStatus[]>([]);
  const [assets, setAssets] = useState<StudyAsset[]>([]);
  const [files, setFiles] = useState<File[]>([]);
  const [pastQuestionAssets, setPastQuestionAssets] = useState<StudyAsset[]>([]);
  const [pastQuestionFiles, setPastQuestionFiles] = useState<File[]>([]);
  const [sourceUrl, setSourceUrl] = useState("");
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState("");
  const [starting, setStarting] = useState(false);
  const [buildStage, setBuildStage] = useState<"idle" | "uploading" | "authoring" | "validating">("idle");

  const mode = useMemo(() => studyModes.find((item) => item.id === learningMode) ?? studyModes[0], [learningMode]);
  const liveProviders = providers.filter((item): item is ProviderStatus & { id: LiveProvider } => item.id === "fireworks" || item.id === "openai");
  const selectedProvider = liveProviders.find((item) => item.id === provider);

  useEffect(() => {
    getProviderStatus().then((status) => {
      setProviders(status.providers);
      const preferred = status.providers.find((item) => item.id === "fireworks" && item.available) ?? status.providers.find((item) => item.id === "openai" && item.available);
      if (preferred && (preferred.id === "fireworks" || preferred.id === "openai")) setProvider(preferred.id);
    }).catch(() => setError("The provider status could not be loaded. Check that Django is running."));
  }, []);

  function addFiles(selected: FileList | File[], target: "notes" | "past_questions" = "notes") {
    const next: StudyAsset[] = [];
    const acceptedFiles: File[] = [];
    for (const file of Array.from(selected)) {
      if (!acceptedTypes.has(file.type)) {
        setError(`${file.name} is not supported. Use a PDF, image, audio, or video file.`);
        continue;
      }
      if (file.size > 50 * 1024 * 1024) {
        setError(`${file.name} is larger than the 50 MB upload limit.`);
        continue;
      }
      next.push({ id: `${target}-${file.name}-${file.lastModified}`, name: file.name, kind: assetKind(file.type), status: "review_required" });
      acceptedFiles.push(file);
    }
    if (next.length) {
      if (target === "past_questions") {
        setPastQuestionAssets((current) => [...current, ...next]);
        setPastQuestionFiles((current) => [...current, ...acceptedFiles]);
      } else {
        setAssets((current) => [...current, ...next]);
        setFiles((current) => [...current, ...acceptedFiles]);
      }
      setError("");
    }
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    if (event.target.files) addFiles(event.target.files);
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    addFiles(event.dataTransfer.files);
  }

  async function startStudy() {
    setStarting(true);
    setError("");
    try {
      if (!subjectTitle.trim()) throw new Error("Name the subject before opening the study desk.");
      if (!files.length && !pastQuestionFiles.length && !sourceUrl.trim()) throw new Error("Add at least one note or source URL. Past questions are optional.");
      if (!selectedProvider?.available) throw new Error("The selected live provider is not configured on the server.");
      const subjectId = slugify(subjectTitle);
      const moduleId = slugify(moduleFocus) || (chapterSelection === "all" ? "full-source-pack" : "selected-module");
      setBuildStage("uploading");
      const uploadedNotes: StudySourceIngestResponse[] = await Promise.all(files.map((file) => ingestStudySource(file, { subjectId, moduleId, sourceKind: "notes" })));
      const uploadedPastQuestions: StudySourceIngestResponse[] = await Promise.all(pastQuestionFiles.map((file) => ingestStudySource(file, { subjectId, moduleId, sourceKind: "past_questions" })));
      const uploaded: StudySourceIngestResponse[] = [...uploadedNotes, ...uploadedPastQuestions];
      if (sourceUrl.trim()) uploaded.push(await ingestStudyUrl(sourceUrl.trim(), { subjectId, moduleId, sourceKind: "website" }));
      const sourceIds = uploaded.map((item) => item.sourceId);
      if (!sourceIds.length) throw new Error("No source was accepted by the authoring pipeline.");
      setBuildStage("authoring");
      const plan = await generateStudyPlan({ subjectId, subjectTitle: subjectTitle.trim(), moduleId, sourceIds, pastQuestionSourceIds: uploadedPastQuestions.map((item) => item.sourceId), chapterSelection, provider });
      setBuildStage("validating");
      const draft = {
        version: "study-draft-v2",
        subjectId,
        subjectTitle: subjectTitle.trim(),
        moduleId,
        chapterTitle: moduleFocus.trim() || (chapterSelection === "all" ? "Complete source pack" : "Selected module"),
        provider,
        providerMode: plan.providerMode,
        sourceIds,
        assets: [...assets, ...pastQuestionAssets],
        pastQuestionSourceIds: uploadedPastQuestions.map((item) => item.sourceId),
        learningMode,
        plan,
        uploadReview: uploaded.map((item) => ({ sourceId: item.sourceId, filename: item.filename, approvalStatus: item.approvalStatus, extraction: item.extraction })),
      };
      window.localStorage.setItem("feynman.studyDraft", JSON.stringify(draft));
      router.push("/study/workspace");
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "The study desk could not be opened.";
      setError(message);
    } finally {
      setStarting(false);
      setBuildStage("idle");
    }
  }

  const buildStageLabel = buildStage === "uploading"
    ? "Uploading and extracting your source"
    : buildStage === "authoring"
      ? "The live provider is authoring the learning path"
      : "Checking scenes, checkpoints, and source anchors";

  return (
    <main className="study-intake-shell">
      <a className="study-skip-link" href="#study-intake-main">Skip to study setup</a>
      <header className="study-minimal-header">
        <Link href="/" className="study-wordmark" aria-label="Feynman AI home">feynman<span>.ai</span></Link>
        <span className="study-mode-note">live provider / source-bounded</span>
      </header>

      <section className="study-intake-layout" id="study-intake-main">
        <div className="study-intake-intro">
          <p className="study-kicker">START A STUDY DESK</p>
          <h1>Bring the material.<br /><em>Build a way through it.</em></h1>
          <p className="study-intake-lede">Name a subject, choose the material, and define the chapter or scope. The configured model will author a real lesson manifest with explanations, whiteboard actions, checkpoints, and exam practice. Ask the module copilot to open a visualization when one is available.</p>
          <p className="study-trust-line">The server owns source extraction and anchors. Generated lesson content is labeled with its provider and remains reviewable.</p>
        </div>

        <div className="study-intake-form" aria-label="Study setup">
          <section className="study-intake-block">
            <div className="study-block-heading"><span>01</span><div><h2>Name the subject</h2><p>This becomes the reusable learning space for the uploaded material.</p></div></div>
            <label className="study-select-label" htmlFor="subject-title">Subject name</label>
            <input id="subject-title" className="study-text-input" value={subjectTitle} onChange={(event) => setSubjectTitle(event.target.value)} placeholder="Digital Signal Analysis and Processing" maxLength={160} />
          </section>

          <section className="study-intake-block">
            <div className="study-block-heading"><span>02</span><div><h2>Your material</h2><p>Upload the chapter or source collection the live provider should learn from.</p></div></div>
            <div className={`study-dropzone ${dragging ? "is-dragging" : ""}`} onDragEnter={(event) => { event.preventDefault(); setDragging(true); }} onDragOver={(event) => event.preventDefault()} onDragLeave={() => setDragging(false)} onDrop={handleDrop}>
              <input id="study-files" type="file" accept=".pdf,image/png,image/jpeg,image/webp,video/mp4,video/webm,video/quicktime,audio/mpeg,audio/wav,audio/ogg,audio/webm" multiple onChange={handleFileChange} />
              <label htmlFor="study-files"><strong>Drop your study material here</strong><span>or choose files from this device</span><small>PDF / PNG/JPG / MP4/MOV / audio / up to 50 MB each</small></label>
            </div>
            <ul className="study-asset-list" aria-label="Selected study material">
              {assets.map((asset) => <li key={asset.id}><span className="study-asset-type">{asset.kind}</span><span className="study-asset-name">{asset.name}</span><span className="study-asset-status review_required">review</span></li>)}
              {sourceUrl.trim() && <li><span className="study-asset-type">url</span><span className="study-asset-name">{sourceUrl.trim()}</span><span className="study-asset-status review_required">review</span></li>}
            </ul>
            <label className="study-select-label" htmlFor="study-source-url">Or add a website or paper URL</label>
            <input id="study-source-url" className="study-text-input" value={sourceUrl} onChange={(event) => setSourceUrl(event.target.value)} placeholder="https://..." inputMode="url" />
            <p className="study-mode-description">You can upload multiple notes/resources. Each file is extracted into server-owned candidate spans before lesson authoring.</p>
          </section>

          <section className="study-intake-block">
            <div className="study-block-heading"><span>03</span><div><h2>Past questions <span>(optional)</span></h2><p>Upload previous exams, assignments, or question banks so the module can identify recurring patterns and prepare application checks around them.</p></div></div>
            <div className="study-dropzone study-dropzone-secondary" onDragEnter={(event) => { event.preventDefault(); setDragging(true); }} onDragOver={(event) => event.preventDefault()} onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); addFiles(event.dataTransfer.files, "past_questions"); }}>
              <input id="study-past-question-files" type="file" accept=".pdf,image/png,image/jpeg,image/webp" multiple onChange={(event) => { if (event.target.files) addFiles(event.target.files, "past_questions"); }} />
              <label htmlFor="study-past-question-files"><strong>Add past questions for analysis</strong><span>Optional — PDF or image files</span><small>The learner will not see answer keys before attempting a question.</small></label>
            </div>
            <ul className="study-asset-list" aria-label="Selected past question resources">
              {pastQuestionAssets.map((asset) => <li key={asset.id}><span className="study-asset-type">past</span><span className="study-asset-name">{asset.name}</span><span className="study-asset-status review_required">analysis</span></li>)}
            </ul>
          </section>

          <section className="study-intake-block">
            <div className="study-block-heading"><span>04</span><div><h2>Where should we begin?</h2><p>Choose a scope, then optionally name the chapter, unit, or lesson focus.</p></div></div>
            <label className={`study-choice-row ${chapterSelection === "chapter_1" ? "selected" : ""}`}><input type="radio" name="scope" value="chapter_1" checked={chapterSelection === "chapter_1"} onChange={() => setChapterSelection("chapter_1")} /><span><strong>One chapter or module</strong><small>Build a focused first learning path from the selected material.</small></span><em>focused</em></label>
            <label className={`study-choice-row ${chapterSelection === "all" ? "selected" : ""}`}><input type="radio" name="scope" value="all" checked={chapterSelection === "all"} onChange={() => setChapterSelection("all")} /><span><strong>All selected material</strong><small>Let the provider map the full source collection into a sequence.</small></span><em>full pack</em></label>
            <label className="study-select-label" htmlFor="module-focus">Chapter or module focus <span>(optional)</span></label>
            <input id="module-focus" className="study-text-input" value={moduleFocus} onChange={(event) => setModuleFocus(event.target.value)} placeholder="e.g. Chapter 7 — Discrete Fourier Transform" maxLength={160} />
          </section>

          <section className="study-intake-block">
            <div className="study-block-heading"><span>05</span><div><h2>Which live model should build it?</h2><p>Keys stay on the server. Fixture output is not offered in the learner flow.</p></div></div>
            <div className="study-provider-list" role="radiogroup" aria-label="Live module builder provider">
              {liveProviders.map((item) => <label key={item.id} className={`study-provider-row ${provider === item.id ? "selected" : ""} ${item.available ? "" : "disabled"}`}><input type="radio" name="provider" value={item.id} checked={provider === item.id} disabled={!item.available} onChange={() => setProvider(item.id)} /><span><strong>{item.label}</strong><small>{item.model}</small></span><em>{item.available ? "available" : "key unavailable"}</em></label>)}
            </div>
          </section>

          <section className="study-intake-block">
            <div className="study-block-heading"><span>06</span><div><h2>How do you want to start?</h2><p>This is a learner preference, not a fixed learning-style label.</p></div></div>
            <label className="study-select-label" htmlFor="study-mode">Learning approach</label>
            <select id="study-mode" className="study-select" value={learningMode} onChange={(event) => setLearningMode(event.target.value)}>{studyModes.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select>
            <p className="study-mode-description">{mode.description}</p>
          </section>

          {error && <p className="study-form-error" role="alert">{error}</p>}
          <div className="study-intake-submit"><div><strong>{moduleFocus.trim() || (chapterSelection === "all" ? "Complete source pack" : "Selected module")}</strong><span>{assets.length + pastQuestionAssets.length} material item{assets.length + pastQuestionAssets.length === 1 ? "" : "s"} / {mode.label}</span></div><button className="study-solid-button" type="button" onClick={startStudy} disabled={starting || !selectedProvider?.available}>{starting ? "Building module..." : "Build my study module -&gt;"}</button></div>
        </div>
      </section>
      {starting && <div className="study-build-overlay" role="status" aria-live="polite" aria-busy="true">
        <div className="study-build-card">
          <span className="study-build-spinner" aria-hidden="true" />
          <p className="study-kicker">BUILDING YOUR STUDY DESK</p>
          <h2>{buildStageLabel}</h2>
          <p>This can take a minute while the source is processed and the live model returns a complete, source-bounded module. Visualizations are optional and can be opened later from the module copilot.</p>
          <ol className="study-build-steps">
            <li className={buildStage === "uploading" ? "current" : buildStage === "idle" ? "" : "done"}>Source extraction</li>
            <li className={buildStage === "authoring" ? "current" : buildStage === "validating" ? "done" : ""}>Lesson authoring</li>
            <li className={buildStage === "validating" ? "current" : ""}>Safety validation</li>
          </ol>
        </div>
      </div>}
    </main>
  );
}
