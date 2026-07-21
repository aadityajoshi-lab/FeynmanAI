"use client";

import Link from "next/link";
import { ChangeEvent, DragEvent, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { studyModes } from "@/lib/learningModes";
import type { AssessmentFocus, LearningGoal, SkillLevel, StudyAsset } from "@/lib/studyTypes";
import { generateStudyPlan, getProviderStatus, getRemediationVideoConfig, ingestStudySource, ingestStudyUrl, ProviderStatus, StudySourceIngestResponse, StudyRemediationVideoConfig } from "@/lib/studyApi";

const acceptedTypes = new Set(["application/pdf", "image/png", "image/jpeg", "image/webp", "video/mp4", "video/webm", "video/quicktime", "audio/mpeg", "audio/wav", "audio/x-wav", "audio/ogg", "audio/webm"]);
type LiveProvider = "qwen" | "fireworks" | "openai";
type SetupStep = 1 | 2 | 3;

const goals: Array<{ id: LearningGoal; eyebrow: string; label: string; description: string; examples: string; focus: AssessmentFocus; icon: string }> = [
  { id: "course", eyebrow: "SUBJECTS", label: "Understand a subject", description: "Turn notes, chapters, and lectures into a structured learning path.", examples: "Engineering · biology · economics", focus: "mastery", icon: "01" },
  { id: "skill", eyebrow: "SKILLS", label: "Build a skill", description: "Practice a skill from first principles to confident real-world use.", examples: "English · Python · public speaking", focus: "mastery", icon: "02" },
  { id: "interview", eyebrow: "CAREER", label: "Prepare for an interview", description: "Run adaptive mock questions with follow-ups, feedback, and pressure practice.", examples: "System design · HR · language interview", focus: "mock_test", icon: "03" },
  { id: "viva", eyebrow: "LAB + ORAL", label: "Practice a viva or lab exam", description: "Explain procedures, defend decisions, and rehearse the questions an examiner will ask next.", examples: "Electronics lab · medicine · research defense", focus: "viva", icon: "04" },
];

const focusOptions: Array<{ id: AssessmentFocus; label: string; description: string; icon: string }> = [
  { id: "mastery", label: "Deep understanding", description: "Definition → practice → explain it back.", icon: "↗" },
  { id: "mock_test", label: "Mock test", description: "Timed questions with exam-style feedback.", icon: "◷" },
  { id: "conversation", label: "Conversation practice", description: "Answer aloud, handle follow-ups, improve clarity.", icon: "◌" },
  { id: "viva", label: "Viva mode", description: "Defend your reasoning under an examiner's probe.", icon: "◇" },
];

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
  const [step, setStep] = useState<SetupStep>(1);
  const [learningGoal, setLearningGoal] = useState<LearningGoal>("course");
  const [subjectTitle, setSubjectTitle] = useState("");
  const [moduleFocus, setModuleFocus] = useState("");
  const [goalBrief, setGoalBrief] = useState("");
  const [skillLevel, setSkillLevel] = useState<SkillLevel>("beginner");
  const [assessmentFocus, setAssessmentFocus] = useState<AssessmentFocus>("mastery");
  const [chapterSelection, setChapterSelection] = useState<"chapter_1" | "all">("chapter_1");
  const [learningMode, setLearningMode] = useState<string>(studyModes[0].id);
  const [provider, setProvider] = useState<LiveProvider>("qwen");
  const [providers, setProviders] = useState<ProviderStatus[]>([]);
  const [videoConfig, setVideoConfig] = useState<StudyRemediationVideoConfig | null>(null);
  const [videoDurationSeconds, setVideoDurationSeconds] = useState(120);
  const [assets, setAssets] = useState<StudyAsset[]>([]);
  const [files, setFiles] = useState<File[]>([]);
  const [pastQuestionAssets, setPastQuestionAssets] = useState<StudyAsset[]>([]);
  const [pastQuestionFiles, setPastQuestionFiles] = useState<File[]>([]);
  const [sourceUrl, setSourceUrl] = useState("");
  const [resourcesOpen, setResourcesOpen] = useState(false);
  const [pastQuestionsOpen, setPastQuestionsOpen] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState("");
  const [starting, setStarting] = useState(false);
  const [buildStage, setBuildStage] = useState<"idle" | "uploading" | "authoring" | "validating">("idle");

  const goal = useMemo(() => goals.find((item) => item.id === learningGoal) ?? goals[0], [learningGoal]);
  const mode = useMemo(() => studyModes.find((item) => item.id === learningMode) ?? studyModes[0], [learningMode]);
  const liveProviders = providers.filter((item): item is ProviderStatus & { id: LiveProvider } => item.id === "qwen" || item.id === "fireworks" || item.id === "openai");
  const selectedProvider = liveProviders.find((item) => item.id === provider);
  const totalResources = assets.length + pastQuestionAssets.length + (sourceUrl.trim() ? 1 : 0);
  const canBuild = Boolean(subjectTitle.trim() && selectedProvider?.available && !starting);

  useEffect(() => {
    getProviderStatus().then((status) => {
      setProviders(status.providers);
      const preferred = status.providers.find((item) => item.id === "qwen" && item.available) ?? status.providers.find((item) => item.id === "fireworks" && item.available) ?? status.providers.find((item) => item.id === "openai" && item.available);
      if (preferred && (preferred.id === "qwen" || preferred.id === "fireworks" || preferred.id === "openai")) setProvider(preferred.id);
    }).catch(() => setError("The live builder could not be reached. Check that Django is running."));
    getRemediationVideoConfig().then(setVideoConfig).catch(() => setVideoConfig(null));
  }, []);

  useEffect(() => {
    setAssessmentFocus(goal.focus);
  }, [goal.focus]);

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
    if (!next.length) return;
    if (target === "past_questions") {
      setPastQuestionAssets((current) => [...current, ...next]);
      setPastQuestionFiles((current) => [...current, ...acceptedFiles]);
    } else {
      setAssets((current) => [...current, ...next]);
      setFiles((current) => [...current, ...acceptedFiles]);
    }
    setError("");
  }

  function removeAsset(id: string, target: "notes" | "past_questions") {
    if (target === "past_questions") {
      const index = pastQuestionAssets.findIndex((asset) => asset.id === id);
      setPastQuestionAssets((current) => current.filter((asset) => asset.id !== id));
      setPastQuestionFiles((current) => current.filter((_, fileIndex) => fileIndex !== index));
      return;
    }
    const index = assets.findIndex((asset) => asset.id === id);
    setAssets((current) => current.filter((asset) => asset.id !== id));
    setFiles((current) => current.filter((_, fileIndex) => fileIndex !== index));
  }

  function handleDrop(event: DragEvent<HTMLDivElement>, target: "notes" | "past_questions" = "notes") {
    event.preventDefault();
    setDragging(false);
    addFiles(event.dataTransfer.files, target);
  }

  function nextStep() {
    setError("");
    if (step === 1 && !subjectTitle.trim()) {
      setError(learningGoal === "course" ? "Give this subject a name so we can build its learning path." : "Name the skill or scenario you want to practice.");
      return;
    }
    setStep((current) => Math.min(3, current + 1) as SetupStep);
  }

  async function startStudy() {
    setStarting(true);
    setError("");
    try {
      if (!subjectTitle.trim()) throw new Error("Name your subject or skill before opening the study desk.");
      if (!selectedProvider?.available) throw new Error("The selected live provider is not configured on the server.");
      const subjectId = slugify(subjectTitle);
      const moduleId = slugify(moduleFocus) || slugify(subjectTitle);
      setBuildStage("uploading");
      const uploadedNotes: StudySourceIngestResponse[] = await Promise.all(files.map((file) => ingestStudySource(file, { subjectId, moduleId, sourceKind: "notes" })));
      const uploadedPastQuestions: StudySourceIngestResponse[] = await Promise.all(pastQuestionFiles.map((file) => ingestStudySource(file, { subjectId, moduleId, sourceKind: "past_questions" })));
      const uploaded: StudySourceIngestResponse[] = [...uploadedNotes, ...uploadedPastQuestions];
      if (sourceUrl.trim()) uploaded.push(await ingestStudyUrl(sourceUrl.trim(), { subjectId, moduleId, sourceKind: "website" }));
      setBuildStage("authoring");
      const sourceIds = uploaded.map((item) => item.sourceId);
      const plan = await generateStudyPlan({ subjectId, subjectTitle: subjectTitle.trim(), moduleId, sourceIds, pastQuestionSourceIds: uploadedPastQuestions.map((item) => item.sourceId), chapterSelection, provider, learningGoal, assessmentFocus, skillLevel, goalBrief: goalBrief.trim() });
      setBuildStage("validating");
      const draft = {
        version: "study-draft-v3",
        subjectId,
        subjectTitle: subjectTitle.trim(),
        moduleId,
        chapterTitle: moduleFocus.trim() || (learningGoal === "course" && chapterSelection === "all" ? "Complete source pack" : moduleFocus.trim() || "First learning sprint"),
        provider,
        providerMode: plan.providerMode,
        sourceIds: plan.sourceIds ?? sourceIds,
        assets: [...assets, ...pastQuestionAssets],
        pastQuestionSourceIds: uploadedPastQuestions.map((item) => item.sourceId),
        learningGoal,
        goalBrief: goalBrief.trim(),
        assessmentFocus,
        skillLevel,
        learningMode,
        remediationVideoDurationSeconds: videoDurationSeconds,
        remediationVideoConfig: videoConfig,
        plan,
        uploadReview: uploaded.map((item) => ({ sourceId: item.sourceId, filename: item.filename, approvalStatus: item.approvalStatus, extraction: item.extraction })),
      };
      window.localStorage.setItem("feynman.studyDraft", JSON.stringify(draft));
      router.push("/study/workspace");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The study desk could not be opened.");
    } finally {
      setStarting(false);
      setBuildStage("idle");
    }
  }

  const buildStageLabel = buildStage === "uploading" ? "Preparing your context" : buildStage === "authoring" ? "Designing your learning path" : "Checking assessments and feedback loops";
  const resourceDescription = totalResources ? `${totalResources} resource${totalResources === 1 ? "" : "s"} added` : "Optional — start from the skill name alone";

  return <main className="study-intake-shell study-new-shell">
    <a className="study-skip-link" href="#study-intake-main">Skip to study setup</a>
    <header className="study-minimal-header study-new-header"><Link href="/" className="study-wordmark" aria-label="Feynman AI home">feynman<span>.ai</span></Link><div className="study-header-right"><span className="study-header-pill"><i /> live learning desk</span><span className="study-header-step">setup {step} of 3</span></div></header>

    <section className="study-new-hero"><div><span className="study-kicker">A PERSONAL LEARNING SYSTEM</span><h1>Learn the idea.<br /><em>Handle the pressure.</em></h1><p>One calm workspace for subjects, skills, interviews, and oral exams. Feynman turns your goal into a sequence of explanations, practice, feedback, and proof.</p></div><div className="study-hero-trust"><span className="study-hero-orbit">✦</span><strong>Built around your next right step</strong><small>Every session adapts to what you can explain—not just what you can recognize.</small></div></section>

    <div className="study-setup-progress" aria-label="Study setup progress">{(["Choose your goal", "Add context", "Tune the experience"] as const).map((label, index) => { const itemStep = (index + 1) as SetupStep; return <button key={label} type="button" className={step === itemStep ? "active" : step > itemStep ? "done" : ""} onClick={() => itemStep < step ? setStep(itemStep) : undefined} aria-current={step === itemStep ? "step" : undefined}><span>{step > itemStep ? "✓" : `0${itemStep}`}</span><strong>{label}</strong></button>; })}</div>

    <section className="study-new-layout" id="study-intake-main">
      <div className="study-new-form">
        {step === 1 && <section className="study-new-card study-goal-card"><div className="study-new-card-heading"><div><span className="study-kicker">STEP 01 · START WITH INTENT</span><h2>What are you here to get better at?</h2><p>Choose the experience, not the file type. You can change the details later.</p></div><span className="study-card-count">4 paths</span></div><div className="study-goal-grid">{goals.map((item) => <button key={item.id} type="button" className={`study-goal-option ${learningGoal === item.id ? "selected" : ""}`} onClick={() => { setLearningGoal(item.id); setAssessmentFocus(item.focus); }}><span className="study-goal-icon">{item.icon}</span><span className="study-goal-copy"><small>{item.eyebrow}</small><strong>{item.label}</strong><span>{item.description}</span><em>{item.examples}</em></span><span className="study-goal-check" aria-hidden="true">{learningGoal === item.id ? "✓" : ""}</span></button>)}</div><div className="study-field-block study-goal-name"><label htmlFor="subject-title">Name the subject, skill, or scenario</label><input id="subject-title" className="study-new-input" value={subjectTitle} onChange={(event) => setSubjectTitle(event.target.value)} placeholder={learningGoal === "course" ? "Digital Instrumentation" : learningGoal === "interview" ? "Backend engineering interview" : learningGoal === "viva" ? "Electronics measurement lab viva" : "Spoken English for work"} maxLength={160} /><small>{learningGoal === "course" ? "This becomes your study desk title." : "Be specific—the more focused the goal, the better the practice."}</small></div><div className="study-inline-note"><span>✦</span><p><strong>Why this matters:</strong> the goal changes the question style, feedback tone, and the way the next challenge is chosen.</p></div></section>}

        {step === 2 && <section className="study-new-card"><div className="study-new-card-heading"><div><span className="study-kicker">STEP 02 · GIVE IT CONTEXT</span><h2>What should the desk know?</h2><p>Resources are optional. Add notes when you want the experience grounded to a curriculum; leave them out for general skill practice.</p></div><span className="study-card-count">optional context</span></div><div className="study-field-block"><label htmlFor="goal-brief">Your target outcome <span>(optional)</span></label><textarea id="goal-brief" className="study-new-textarea" value={goalBrief} onChange={(event) => setGoalBrief(event.target.value)} placeholder={learningGoal === "interview" ? "e.g. I want to explain trade-offs clearly and handle follow-up questions." : learningGoal === "viva" ? "e.g. I need to defend my circuit choices and answer safety questions." : "e.g. I want to confidently solve numerical problems from this unit."} maxLength={500} rows={3} /><small>{goalBrief.length}/500 · This gives the coach a useful definition of success.</small></div><div className={`study-resource-toggle ${resourcesOpen ? "open" : ""}`}><button type="button" onClick={() => setResourcesOpen((current) => !current)} aria-expanded={resourcesOpen}><span className="study-resource-toggle-icon">{resourcesOpen ? "−" : "+"}</span><span><strong>Add notes, slides, or reference material</strong><small>{resourceDescription}</small></span><em>{resourcesOpen ? "hide" : "optional"}</em></button>{resourcesOpen && <div className="study-resource-panel"><div className={`study-new-dropzone ${dragging ? "is-dragging" : ""}`} onDragEnter={(event) => { event.preventDefault(); setDragging(true); }} onDragOver={(event) => event.preventDefault()} onDragLeave={() => setDragging(false)} onDrop={(event) => handleDrop(event)}><input id="study-files" type="file" accept=".pdf,image/png,image/jpeg,image/webp,video/mp4,video/webm,video/quicktime,audio/mpeg,audio/wav,audio/ogg,audio/webm" multiple onChange={(event: ChangeEvent<HTMLInputElement>) => { if (event.target.files) addFiles(event.target.files); }} /><label htmlFor="study-files"><span className="study-upload-glyph">↑</span><strong>Drop resources here or browse</strong><small>PDF, image, audio, or video · up to 50 MB each · multiple files supported</small></label></div>{assets.length > 0 && <ul className="study-new-file-list" aria-label="Selected resources">{assets.map((asset) => <li key={asset.id}><span className="study-file-kind">{asset.kind}</span><span>{asset.name}</span><button type="button" onClick={() => removeAsset(asset.id, "notes")} aria-label={`Remove ${asset.name}`}>×</button></li>)}</ul>}<label className="study-field-label" htmlFor="study-source-url">Or add a website or paper URL</label><input id="study-source-url" className="study-new-input" value={sourceUrl} onChange={(event) => setSourceUrl(event.target.value)} placeholder="https://..." inputMode="url" />{sourceUrl.trim() && <div className="study-url-preview"><span>url</span><strong>{sourceUrl.trim()}</strong><button type="button" onClick={() => setSourceUrl("")} aria-label="Remove URL">×</button></div>}<p className="study-resource-footnote">Uploaded material remains reviewable and is used to keep explanations, visuals, and assessments close to your source.</p></div>}</div><div className={`study-resource-toggle ${pastQuestionsOpen ? "open" : ""}`}><button type="button" onClick={() => setPastQuestionsOpen((current) => !current)} aria-expanded={pastQuestionsOpen}><span className="study-resource-toggle-icon">{pastQuestionsOpen ? "−" : "+"}</span><span><strong>Analyze past questions</strong><small>{pastQuestionAssets.length ? `${pastQuestionAssets.length} question set${pastQuestionAssets.length === 1 ? "" : "s"} added` : "Optional · exams, assignments, question banks"}</small></span><em>{pastQuestionsOpen ? "hide" : "optional"}</em></button>{pastQuestionsOpen && <div className="study-resource-panel"><div className="study-new-dropzone compact" onDrop={(event) => handleDrop(event, "past_questions")} onDragOver={(event) => event.preventDefault()}><input id="study-past-question-files" type="file" accept=".pdf,image/png,image/jpeg,image/webp" multiple onChange={(event) => { if (event.target.files) addFiles(event.target.files, "past_questions"); }} /><label htmlFor="study-past-question-files"><span className="study-upload-glyph">+</span><strong>Add exam or interview question sets</strong><small>We use patterns to shape application checks; answer keys stay hidden.</small></label></div>{pastQuestionAssets.length > 0 && <ul className="study-new-file-list">{pastQuestionAssets.map((asset) => <li key={asset.id}><span className="study-file-kind">past</span><span>{asset.name}</span><button type="button" onClick={() => removeAsset(asset.id, "past_questions")} aria-label={`Remove ${asset.name}`}>×</button></li>)}</ul>}</div>}</div></section>}

        {step === 3 && <section className="study-new-card"><div className="study-new-card-heading"><div><span className="study-kicker">STEP 03 · MAKE IT YOURS</span><h2>How should it challenge you?</h2><p>Feynman will still adapt after every answer. These choices set the starting rhythm.</p></div><span className="study-card-count">personalized</span></div><div className="study-field-block"><label>Current level</label><div className="study-segmented" role="radiogroup" aria-label="Current level">{(["beginner", "intermediate", "advanced"] as SkillLevel[]).map((item) => <button key={item} type="button" className={skillLevel === item ? "selected" : ""} onClick={() => setSkillLevel(item)}>{item[0].toUpperCase() + item.slice(1)}<small>{item === "beginner" ? "Build the base" : item === "intermediate" ? "Sharpen what I know" : "Perform under pressure"}</small></button>)}</div></div><div className="study-field-block"><label>Primary experience</label><div className="study-focus-grid">{focusOptions.filter((item) => learningGoal === "interview" ? ["mock_test", "conversation"].includes(item.id) : learningGoal === "viva" ? ["viva", "mastery"].includes(item.id) : true).map((item) => <button key={item.id} type="button" className={`study-focus-option ${assessmentFocus === item.id ? "selected" : ""}`} onClick={() => setAssessmentFocus(item.id)}><span>{item.icon}</span><strong>{item.label}</strong><small>{item.description}</small></button>)}</div></div><div className="study-field-block study-scope-block"><label htmlFor="module-focus">First sprint scope <span>(optional)</span></label><input id="module-focus" className="study-new-input" value={moduleFocus} onChange={(event) => setModuleFocus(event.target.value)} placeholder={learningGoal === "course" ? "e.g. Chapter 1 · Analog instrumentation" : "e.g. Speaking clearly in technical interviews"} maxLength={160} /><div className="study-scope-options"><label className={chapterSelection === "chapter_1" ? "selected" : ""}><input type="radio" name="scope" checked={chapterSelection === "chapter_1"} onChange={() => setChapterSelection("chapter_1")} /><span><strong>First sprint</strong><small>Start focused and unlock the next topic when ready.</small></span></label><label className={chapterSelection === "all" ? "selected" : ""}><input type="radio" name="scope" checked={chapterSelection === "all"} onChange={() => setChapterSelection("all")} /><span><strong>Map the full journey</strong><small>Let the coach outline everything up front.</small></span></label></div></div><details className="study-advanced"><summary>Advanced settings <span>provider, remediation video, learning approach</span></summary><div className="study-advanced-body"><div><label className="study-field-label">Live builder</label><div className="study-provider-list study-provider-list-new" role="radiogroup" aria-label="Live module builder provider">{liveProviders.map((item) => <label key={item.id} className={`study-provider-row ${provider === item.id ? "selected" : ""} ${item.available ? "" : "disabled"}`}><input type="radio" name="provider" value={item.id} checked={provider === item.id} disabled={!item.available} onChange={() => setProvider(item.id)} /><span><strong>{item.label}</strong><small>{item.model}</small></span><em>{item.available ? "ready" : "unavailable"}</em></label>)}</div></div><div className="study-advanced-grid"><label><span>Remediation video length</span><select className="study-new-select" value={videoDurationSeconds} onChange={(event) => setVideoDurationSeconds(Number(event.target.value))}><option value={60}>1 minute · focused</option><option value={120}>2 minutes · explain + apply</option><option value={180}>3 minutes · full review</option><option value={300}>5 minutes · deep review</option></select><small>{videoConfig?.configured ? "Ready when a mistake needs another explanation." : "Generated slides are available; server voice is optional."}</small></label><label><span>Starting rhythm</span><select className="study-new-select" value={learningMode} onChange={(event) => setLearningMode(event.target.value)}>{studyModes.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select><small>{mode.description}</small></label></div></div></details></section>}

        {error && <p className="study-form-error study-new-error" role="alert">{error}</p>}
        <div className="study-new-actions">{step > 1 ? <button type="button" className="study-new-ghost-button" onClick={() => { setError(""); setStep((current) => Math.max(1, current - 1) as SetupStep); }}>← Back</button> : <span />}{step < 3 ? <button type="button" className="study-new-primary-button" onClick={nextStep}>Continue <span>→</span></button> : <button type="button" className="study-new-primary-button" onClick={() => void startStudy()} disabled={!canBuild}>{starting ? "Building your desk…" : selectedProvider ? "Open my study desk" : "Connecting to live builder…"}<span>→</span></button>}</div>
      </div>

      <aside className="study-new-preview" aria-label="Study desk preview"><div className="study-preview-sticky"><div className="study-preview-label"><span>YOUR STUDY DESK</span><i>live preview</i></div><div className="study-preview-card"><div className="study-preview-top"><span className="study-preview-spark">✦</span><span>{goal.eyebrow.toLowerCase()} / {assessmentFocus.replace("_", " ")}</span></div><h3>{subjectTitle.trim() || "Your next learning goal"}</h3><p>{goalBrief.trim() || goal.description}</p><div className="study-preview-loop"><div className="complete"><span>01</span><strong>Learn</strong><small>clear explanation</small></div><div><span>02</span><strong>Try</strong><small>adaptive check</small></div><div><span>03</span><strong>Prove</strong><small>teach it back</small></div></div><div className="study-preview-footer"><span><i /> {skillLevel}</span><span>{totalResources ? `${totalResources} context item${totalResources === 1 ? "" : "s"}` : "general practice"}</span></div></div><div className="study-preview-promise"><span>WHAT HAPPENS NEXT</span><p>Miss something? You get the correction, a similar retry, and a clear path forward—not a dead end.</p></div></div></aside>
    </section>

    {starting && <div className="study-build-overlay" role="status" aria-live="polite" aria-busy="true"><div className="study-build-card study-new-build-card"><span className="study-build-spinner" aria-hidden="true" /><p className="study-kicker">SETTING UP YOUR DESK</p><h2>{buildStageLabel}</h2><p>We are preparing the context, topic sequence, assessment ladder, and feedback loop for {subjectTitle.trim() || "your goal"}.</p><ol className="study-build-steps"><li className={buildStage === "uploading" ? "current" : buildStage === "idle" ? "" : "done"}>Context</li><li className={buildStage === "authoring" ? "current" : buildStage === "validating" ? "done" : ""}>Learning path</li><li className={buildStage === "validating" ? "current" : ""}>Quality check</li></ol></div></div>}
  </main>;
}
