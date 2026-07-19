"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import katex from "katex";
import "katex/dist/katex.min.css";
import { askNotebook, createNotebookArtifact, createNotebookLesson, getNotebook } from "@/lib/notebookApi";
import type { Notebook, NotebookArtifact, NotebookArtifactType, NotebookSection } from "@/lib/notebookTypes";

const outputOptions: Array<{ type: NotebookArtifactType; label: string; description: string; icon: string }> = [
  { type: "summary", label: "Study guide", description: "A calm, section-by-section overview.", icon: "✦" },
  { type: "mcq", label: "MCQ test", description: "Check recall, then reveal the explanation.", icon: "◉" },
  { type: "slides", label: "Slide lesson", description: "Turn the source into a visual sequence.", icon: "▤" },
  { type: "formula_sheet", label: "Formula sheet", description: "Collect equations with source references.", icon: "∑" },
  { type: "important_questions", label: "Important questions", description: "Prepare explanations and applications.", icon: "?" },
  { type: "flashcards", label: "Flashcards", description: "Quick retrieval practice from every section.", icon: "▣" },
];

outputOptions.push({ type: "openmaic_lesson", label: "Narrated lesson", description: "OpenMAIC-style slides with actions, visuals, and voice.", icon: "▶" });

function blockText(section: NotebookSection) { return section.blocks.filter((block) => block.type.toLowerCase() !== "image").map((block) => block.markdown).filter(Boolean).join(" "); }
function formatCount(value: number | undefined) { return String(value ?? 0).padStart(2, "0"); }

export default function NotebookWorkspace({ notebookId }: { notebookId: string }) {
  const [notebook, setNotebook] = useState<Notebook | null>(null);
  const [view, setView] = useState<"overview" | "sources" | "ask">("overview");
  const [activeArtifact, setActiveArtifact] = useState<NotebookArtifact | null>(null);
  const [generating, setGenerating] = useState<NotebookArtifactType | null>(null);
  const [question, setQuestion] = useState("");
  const [lessonComposerOpen, setLessonComposerOpen] = useState(false);
  const [lessonDuration, setLessonDuration] = useState(120);
  const [answer, setAnswer] = useState<{ text: string; sourceIds: string[]; groundedIn?: string; webSources?: Array<{ title: string; url: string; snippet?: string }> } | null>(null);
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => { try { setNotebook(await getNotebook(notebookId)); } catch (caught) { setError(caught instanceof Error ? caught.message : "Notebook could not be loaded."); } }, [notebookId]);
  useEffect(() => { void load(); }, [load]);

  const pack = notebook?.knowledgePack;
  const sourceCount = notebook?.stats.sourceCount || notebook?.sources.length || 0;
  const readyCount = notebook?.sources.filter((source) => source.status === "ready").length || 0;
  const selectedArtifact = activeArtifact || notebook?.artifacts.find((artifact) => artifact.status === "ready") || null;

  async function makeArtifact(type: NotebookArtifactType) {
    if (type === "openmaic_lesson") {
      setView("ask");
      setLessonComposerOpen(true);
      setQuestion("");
      setAnswer(null);
      setError("");
      return;
    }
    setError(""); setGenerating(type);
    try {
      const artifact = await createNotebookArtifact(notebookId, type);
      setActiveArtifact(artifact); await load();
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Could not create this output."); } finally { setGenerating(null); }
  }

  async function makeLesson() {
    if (!question.trim()) return;
    setError(""); setGenerating("openmaic_lesson");
    try { const artifact = await createNotebookLesson(notebookId, question.trim(), lessonDuration); setActiveArtifact(artifact); await load(); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "The narrated lesson could not be created."); }
    finally { setGenerating(null); }
  }

  async function ask() {
    if (!question.trim()) return;
    setAsking(true); setError("");
    try { const result = await askNotebook(notebookId, question.trim()); setAnswer({ text: result.answer, sourceIds: result.sourceIds, groundedIn: result.groundedIn, webSources: result.webSources }); } catch (caught) { setError(caught instanceof Error ? caught.message : "The notebook could not answer."); } finally { setAsking(false); }
  }

  if (!notebook && !error) return <main className="notebook-loading"><span className="notebook-spinner" /><p>Opening your notebook…</p></main>;
  if (!notebook) return <main className="notebook-loading"><strong>{error}</strong><Link href="/study/new">Back to notebooks</Link></main>;

  return <main className="notebook-workspace-shell">
    <header className="notebook-header notebook-workspace-header"><Link href="/" className="notebook-brand">feynman<span>.ai</span></Link><div className="notebook-breadcrumb"><span>NOTEBOOK</span><b>/</b><strong>{notebook.title}</strong></div><Link href="/study/new" className="notebook-new-link">＋ New notebook</Link></header>
    <div className="notebook-workspace-grid">
      <aside className="notebook-sidebar"><div className="notebook-side-intro"><span className="notebook-eyebrow">YOUR NOTEBOOK</span><h1>{notebook.title}</h1><p>{notebook.description || "A source-grounded workspace for learning, testing, and making ideas stick."}</p><div className="notebook-side-status"><span className="notebook-status-dot" /> {notebook.status === "ready" ? "Knowledge pack ready" : notebook.status}</div></div><nav className="notebook-side-nav" aria-label="Notebook sections"><button className={view === "overview" ? "active" : ""} onClick={() => { setView("overview"); setLessonComposerOpen(false); }}>⌂ <span>Overview</span><small>your source map</small></button><button className={view === "sources" ? "active" : ""} onClick={() => { setView("sources"); setLessonComposerOpen(false); }}>▤ <span>Sources</span><small>{readyCount} of {sourceCount} processed</small></button><button className={view === "ask" ? "active" : ""} onClick={() => setView("ask")}>◌ <span>Ask notebook</span><small>search your material</small></button></nav><div className="notebook-sidebar-footer"><span>EXTRACTION</span><strong>{notebook.ocrProvider === "mistral-ocr-4-0" ? "Mistral OCR 4" : "Local source reader"}</strong><small>Every output stays linked to source pages.</small></div></aside>

      <section className="notebook-main">
        <div className="notebook-main-top"><div><span className="notebook-eyebrow">{view === "overview" ? "SOURCE DESK" : view === "sources" ? "SOURCE LIBRARY" : "NOTEBOOK COPILOT"}</span><h2>{view === "overview" ? "What would you like to make?" : view === "sources" ? "Your material, kept in order" : "Ask questions grounded in your sources"}</h2><p>{view === "overview" ? "The source pack is the foundation. Choose an output and Feynman will build it from the same structured content." : view === "sources" ? "Text, visual assets, page references, and extraction status stay visible so you can trust the pack." : "Answers are retrieved from the extracted notebook, with the source IDs that informed them."}</p></div><div className="notebook-stat-strip"><span><b>{formatCount(sourceCount)}</b> sources</span><span><b>{formatCount(pack?.sections.length)}</b> sections</span><span><b>{formatCount(pack?.assets.length)}</b> visuals</span></div></div>

        {error && <p className="notebook-error" role="alert">{error}</p>}
        {view === "overview" && <>
          <div className="notebook-output-grid">{outputOptions.map((option) => <button className="notebook-output-card" key={option.type} type="button" onClick={() => void makeArtifact(option.type)} disabled={Boolean(generating)}><span className="notebook-output-icon">{option.icon}</span><span><strong>{option.label}</strong><small>{option.description}</small></span><i>{generating === option.type ? "Building…" : "Create →"}</i></button>)}</div>
          {selectedArtifact ? <ArtifactPanel artifact={selectedArtifact} /> : <section className="notebook-empty-panel"><span className="notebook-empty-orbit">✦</span><h3>Your first study tool is one click away.</h3><p>Start with a study guide for orientation, an MCQ test for recall, or slides when you want the big picture.</p></section>}
          <section className="notebook-pack-preview"><div className="notebook-section-heading"><div><span className="notebook-eyebrow">STRUCTURED KNOWLEDGE PACK</span><h3>What Feynman found</h3></div><button type="button" onClick={() => setView("sources")}>Open source library →</button></div><div className="notebook-section-list">{(pack?.sections || []).slice(0, 6).map((section) => <SectionPreview key={section.sectionId} section={section} />)}</div></section>
          {pack?.assets.length ? <section className="notebook-asset-strip"><div className="notebook-section-heading"><div><span className="notebook-eyebrow">VISUAL SOURCE ASSETS</span><h3>Images kept with their page context</h3></div><span>{pack.assets.length} assets</span></div><div className="notebook-asset-grid">{pack.assets.slice(0, 8).map((asset) => asset.dataUrl ? <figure key={asset.assetId}><img src={asset.dataUrl} alt={asset.alt || "Extracted source visual"} /><figcaption>{asset.alt || "Source visual"}{asset.page ? ` · p. ${asset.page}` : ""}</figcaption></figure> : <div className="notebook-asset-placeholder" key={asset.assetId}><span>VISUAL</span><strong>{asset.alt || "Extracted source visual"}</strong><small>{asset.page ? `page ${asset.page}` : "page context retained"}</small></div>)}</div></section> : null}
        </>}
        {view === "sources" && <SourceLibrary notebook={notebook} />}
        {view === "ask" && <section className={`notebook-ask-panel ${lessonComposerOpen ? "notebook-lesson-composer-open" : ""}`}>
          {lessonComposerOpen && <div className="notebook-lesson-composer-heading"><span className="notebook-eyebrow">OPENMAIC STUDY STUDIO</span><h3>What do you want to learn?</h3><p>Describe the exact idea, question, process, formula, or diagram you want taught. Feynman will build a source-grounded handwritten lesson around it.</p></div>}
          <div className="notebook-ask-examples"><span>{lessonComposerOpen ? "LESSON IDEAS" : "TRY ASKING"}</span>{["Explain the main idea step by step", "Show the important formula and when to use it", "Teach this with a worked example and diagram"].map((item) => <button key={item} type="button" onClick={() => setQuestion(item)}>{item} ↗</button>)}</div>
          <textarea value={question} onChange={(event) => setQuestion(event.target.value)} placeholder={lessonComposerOpen ? "For example: Teach me how a digital instrumentation system works, including its block diagram and one practical example…" : "Ask anything about the material in this notebook…"} rows={lessonComposerOpen ? 7 : 5} />
          <div className="notebook-ask-actions"><small>{answer ? `${answer.sourceIds.length} source${answer.sourceIds.length === 1 ? "" : "s"} used` : "Uploaded sources first · web context when needed"}</small><div className="notebook-ask-action-buttons"><button type="button" className="notebook-secondary-button" onClick={() => void ask()} disabled={asking || !question.trim()}>{asking ? "Searching…" : "Ask for a text answer"}</button><button type="button" className="notebook-primary-button" onClick={() => void makeLesson()} disabled={Boolean(generating) || !question.trim()}>{generating === "openmaic_lesson" ? "Building lesson…" : "Generate narrated lesson →"}</button></div><label className="notebook-duration-picker">Lesson length<select value={lessonDuration} onChange={(event) => setLessonDuration(Number(event.target.value))}><option value={60}>1 minute</option><option value={120}>2 minutes</option><option value={180}>3 minutes</option><option value={300}>5 minutes</option></select></label></div>
          {answer && <div className="notebook-answer"><span className="notebook-eyebrow">NOTEBOOK ANSWER</span>{answer.text.split("\n\n").map((paragraph) => <p key={paragraph}>{paragraph}</p>)}<small>Sources: {answer.sourceIds.join(", ") || "none"}{answer.groundedIn ? ` · grounded in ${answer.groundedIn}` : ""}</small>{answer.webSources?.length ? <div className="notebook-web-sources">{answer.webSources.map((source) => <a key={source.url} href={source.url} target="_blank" rel="noreferrer">{source.title}</a>)}</div> : null}</div>}
        </section>}
        {view === "ask" && answer && <section className="notebook-ask-lesson-cta"><div><span className="notebook-eyebrow">OPENMAIC STUDY STUDIO</span><strong>Turn this answer into a narrated visual lesson</strong><small>OpenMAIC-style slides with guided actions, source visuals, diagrams, and optional voice.</small></div><button type="button" className="notebook-primary-button" onClick={() => void makeLesson()} disabled={Boolean(generating)}>{generating === "openmaic_lesson" ? "Building lesson…" : "Create narrated lesson →"}</button></section>}
        {view === "ask" && selectedArtifact?.payload.kind === "openmaic_lesson" && <ArtifactPanel artifact={selectedArtifact} pack={notebook.knowledgePack} />}
      </section>
    </div>
  </main>;
}

function SectionPreview({ section }: { section: NotebookSection }) { return <article className="notebook-section-preview"><span>{String(section.order).padStart(2, "0")}</span><div><strong>{section.title}</strong><p>{blockText(section).slice(0, 210)}{blockText(section).length > 210 ? "…" : ""}</p></div><small>{section.pages.length ? `p. ${section.pages.join(", ")}` : "source"}</small></article>; }

function SourceLibrary({ notebook }: { notebook: Notebook }) { return <section className="notebook-source-library"><div className="notebook-library-note"><span className="notebook-library-icon">✓</span><div><strong>Extraction is complete and reviewable</strong><p>Each file is processed independently before it contributes to the shared knowledge pack.</p></div></div><div className="notebook-source-library-list">{notebook.sources.map((source) => <article key={source.sourceId}><div className="notebook-source-status"><span className={source.status === "ready" ? "ready" : source.status === "failed" ? "failed" : "pending"}>{source.status === "ready" ? "✓" : source.status === "failed" ? "!" : "…"}</span><div><strong>{source.title}</strong><small>{source.filename || source.sourceKind} · {source.extractionMethod}</small></div></div><div className="notebook-source-metrics"><span>{String(source.extraction.pageCount || 0).padStart(2, "0")} pages</span><span>{String(source.extraction.blockCount || 0).padStart(2, "0")} blocks</span><span>{String(source.extraction.assetCount || 0).padStart(2, "0")} visuals</span></div></article>)}</div>{notebook.knowledgePackMarkdown && <details className="notebook-markdown"><summary>View compact Markdown knowledge pack</summary><pre>{notebook.knowledgePackMarkdown}</pre></details>}</section>; }

function VisualSlidesLegacy({ artifact, pack }: { artifact: NotebookArtifact; pack?: Notebook["knowledgePack"] }) {
  const payload = artifact.payload;
  const slides = payload.slides || [];
  const [slideIndex, setSlideIndex] = useState(0);
  if (!slides.length) return <section className="notebook-artifact-panel notebook-empty-artifact"><span className="notebook-eyebrow">SLIDE LESSON</span><h3>No learner-ready slides yet</h3><p>The source pack did not contain enough structured teaching sections for a reliable slide lesson.</p></section>;
  const slide = slides[slideIndex] || {};
  const sourceAssets = payload.assets || pack?.assets || [];
  const assets = (slide.assetIds || []).map((id: string) => sourceAssets.find((asset: any) => asset.assetId === id)).filter(Boolean);
  return <section className="notebook-artifact-panel"><div className="notebook-artifact-heading"><div><span className="notebook-eyebrow">GENERATED OUTPUT · SLIDE LESSON</span><h3>{artifact.title}</h3></div><span>{slideIndex + 1} / {slides.length}</span></div><div className="notebook-slide"><span className="notebook-slide-number">SLIDE {String(slideIndex + 1).padStart(2, "0")}</span><h4>{slide.title}</h4><p>{slide.body}</p><ul>{(slide.bullets || []).map((bullet: string) => <li key={bullet}>{bullet}</li>)}</ul>{assets.length ? <div className="notebook-slide-assets">{assets.map((asset: any) => <figure key={asset.assetId}><img src={asset.dataUrl || asset.url} alt={asset.alt || "Source visual"} /><figcaption>{asset.alt || "Source visual"}{asset.page ? ` · p. ${asset.page}` : ""}</figcaption></figure>)}</div> : null}<NotebookDiagram diagram={slide.diagram} /><div className="notebook-visual-placeholder"><span>SOURCE-GROUNDED VISUAL</span><strong>{slide.visualHint}</strong><small>Labels are teaching aids; the accompanying text remains anchored to the extracted source.</small></div></div><div className="notebook-artifact-controls"><button type="button" onClick={() => setSlideIndex((index) => Math.max(0, index - 1))} disabled={slideIndex === 0}>← Previous</button><button type="button" onClick={() => setSlideIndex((index) => Math.min(slides.length - 1, index + 1))} disabled={slideIndex >= slides.length - 1}>Next slide →</button></div></section>;
}

function VisualSlides({ artifact, pack }: { artifact: NotebookArtifact; pack?: Notebook["knowledgePack"] }) {
  const payload = artifact.payload;
  const slides = (payload.slides || []) as Array<any>;
  const [slideIndex, setSlideIndex] = useState(0);
  if (!slides.length) return <section className="notebook-artifact-panel notebook-empty-artifact"><span className="notebook-eyebrow">SLIDE LESSON</span><h3>No learner-ready slides yet</h3><p>The source pack did not contain enough structured teaching sections for a reliable visual lesson.</p></section>;
  const slide = slides[slideIndex] || {};
  const sourceAssets = payload.assets || pack?.assets || [];
  const assets = (slide.assetIds || []).map((id: string) => sourceAssets.find((asset: any) => asset.assetId === id)).filter(Boolean);
  return <section className="notebook-artifact-panel notebook-handwritten-output">
    <div className="notebook-artifact-heading"><div><span className="notebook-eyebrow">GENERATED OUTPUT · HANDWRITTEN SLIDE LESSON</span><h3>{artifact.title}</h3><p className="notebook-artifact-subtitle">Read the note, follow the figure, then explain the highlighted relationship.</p></div><span>{slideIndex + 1} / {slides.length}</span></div>
    <div className="openmaic-lesson-stage notebook-slide-stage"><div className="openmaic-lesson-topline"><span>SLIDE {String(slideIndex + 1).padStart(2, "0")}</span><span>{slide.visualKind === "source-figure" ? "SOURCE FIGURE" : slide.visualKind === "teaching-diagram" ? "TEACHING DIAGRAM" : "SOURCE NOTE"}</span></div>
      <div className="openmaic-slide-canvas notebook-standard-slide"><div className="openmaic-slide-title"><span className="openmaic-slide-kicker">{slide.slideLabel || "SOURCE NOTE"}</span><h4>{slide.title}</h4></div><p className="openmaic-lesson-body">{slide.body}</p>{slide.bullets?.length ? <ul className="openmaic-lesson-bullets">{slide.bullets.map((bullet: string, index: number) => <li key={`${bullet}-${index}`}>{bullet}</li>)}</ul> : null}{assets.length ? <div className="notebook-slide-assets">{assets.map((asset: any) => <figure key={asset.assetId}><img src={asset.dataUrl || asset.url} alt={asset.alt || "Source figure"} /><figcaption>{asset.alt || "Source figure"}{asset.page ? ` · p. ${asset.page}` : ""}</figcaption></figure>)}</div> : null}{slide.diagram?.nodes?.length ? <HanddrawnDiagram diagram={slide.diagram} /> : null}<div className="openmaic-focus"><span className="notebook-eyebrow">TEACHING NOTE</span><strong>{slide.teachingNote || slide.visualHint || "Connect the highlighted terms to the source explanation."}</strong></div></div>
    </div>
    <div className="notebook-artifact-controls"><button type="button" onClick={() => setSlideIndex((index) => Math.max(0, index - 1))} disabled={slideIndex === 0}>← Previous slide</button><button type="button" className="notebook-primary-button" onClick={() => setSlideIndex((index) => Math.min(slides.length - 1, index + 1))} disabled={slideIndex >= slides.length - 1}>Next slide →</button></div>
  </section>;
}

function VisualSlidesModern({ artifact, pack }: { artifact: NotebookArtifact; pack?: Notebook["knowledgePack"] }) {
  const slides = (artifact.payload.slides || []) as Array<any>;
  const [slideIndex, setSlideIndex] = useState(0);
  if (!slides.length) return <section className="notebook-artifact-panel notebook-empty-artifact"><span className="notebook-eyebrow">SLIDE LESSON</span><h3>No learner-ready slides yet</h3><p>The source pack did not contain enough structured teaching sections for a reliable visual lesson.</p></section>;
  const slide = slides[slideIndex] || {};
  const sourceAssets = artifact.payload.assets || pack?.assets || [];
  const assets = (slide.assetIds || []).map((id: string) => sourceAssets.find((asset: any) => asset.assetId === id)).filter(Boolean);
  const hasVisual = Boolean(assets.length || slide.diagram?.nodes?.length);
  return <section className="notebook-artifact-panel notebook-handwritten-output">
    <div className="notebook-artifact-heading"><div><span className="notebook-eyebrow">GENERATED OUTPUT · SLIDE LESSON</span><h3>{artifact.title}</h3><p className="notebook-artifact-subtitle">A concise teaching note with a source figure or a process diagram where it clarifies the idea.</p></div><span>{slideIndex + 1} / {slides.length}</span></div>
    <div className="openmaic-lesson-stage notebook-slide-stage"><div className="openmaic-lesson-topline"><span>SLIDE {String(slideIndex + 1).padStart(2, "0")}</span><span>{slide.visualKind === "source-figure" ? "SOURCE FIGURE" : slide.visualKind === "teaching-diagram" ? "TEACHING DIAGRAM" : "SOURCE NOTE"}</span></div>
      <div className={`openmaic-slide-canvas notebook-standard-slide ${hasVisual ? "has-visual" : "text-only"}`}>
        <div className="notebook-slide-copy"><div className="openmaic-slide-title"><span className="openmaic-slide-kicker">{slide.slideLabel || "KEY IDEA"}</span><h4>{slide.title}</h4></div><p className="openmaic-lesson-body">{slide.body}</p>{slide.bullets?.length ? <ul className="openmaic-lesson-bullets">{slide.bullets.map((bullet: string, index: number) => <li key={`${bullet}-${index}`}>{bullet}</li>)}</ul> : null}</div>
        {hasVisual ? <aside className="notebook-slide-visual" aria-label="Source-grounded visual">{assets.length ? <div className="notebook-slide-assets">{assets.map((asset: any) => <figure key={asset.assetId}><img src={asset.dataUrl || asset.url} alt={asset.alt || "Source figure"} /><figcaption>{asset.alt || "Source figure"}{asset.page ? ` · p. ${asset.page}` : ""}</figcaption></figure>)}</div> : null}{slide.diagram?.nodes?.length ? <HanddrawnDiagram diagram={slide.diagram} /> : null}</aside> : null}
        <div className="openmaic-focus"><span className="notebook-eyebrow">TEACHING NOTE</span><strong>{slide.teachingNote || "Connect the highlighted terms to the source explanation."}</strong></div>
      </div>
    </div>
    <div className="notebook-artifact-controls"><button type="button" onClick={() => setSlideIndex((index) => Math.max(0, index - 1))} disabled={slideIndex === 0}>Previous slide</button><button type="button" className="notebook-primary-button" onClick={() => setSlideIndex((index) => Math.min(slides.length - 1, index + 1))} disabled={slideIndex >= slides.length - 1}>Next slide</button></div>
  </section>;
}

function NotebookDiagram({ diagram }: { diagram?: { nodes?: Array<{ id: string; label: string }>; edges?: Array<{ from: string; to: string }> } }) {
  const nodes = diagram?.nodes || [];
  if (!nodes.length) return null;
  const width = Math.max(720, nodes.length * 175);
  const nodeWidth = Math.min(150, Math.max(112, (width - 80) / nodes.length - 18));
  const xFor = (index: number) => 28 + index * ((width - nodeWidth - 56) / Math.max(1, nodes.length - 1));
  return <div className="notebook-diagram"><span className="notebook-diagram-label">CONCEPT MAP</span><svg viewBox={`0 0 ${width} 150`} role="img" aria-label="Source-grounded concept map">{(diagram?.edges || []).map((edge) => { const from = nodes.findIndex((node) => node.id === edge.from); const to = nodes.findIndex((node) => node.id === edge.to); return <line key={`${edge.from}-${edge.to}`} x1={xFor(from) + nodeWidth} y1="75" x2={xFor(to)} y2="75" stroke="#b8c1ec" strokeWidth="3" markerEnd="url(#notebook-arrow)" />; })}<defs><marker id="notebook-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#8995d4" /></marker></defs>{nodes.map((node, index) => <g key={node.id}><rect x={xFor(index)} y="43" width={nodeWidth} height="64" rx="12" fill={index === 0 || index === nodes.length - 1 ? "#fff1df" : "#f7f8ff"} stroke={index === 0 || index === nodes.length - 1 ? "#e9a24d" : "#b9c2ea"} strokeWidth="2" /><text x={xFor(index) + nodeWidth / 2} y="70" textAnchor="middle" fill="#252a4b" fontSize="12" fontWeight="700"><tspan x={xFor(index) + nodeWidth / 2} dy="0">{node.label.length > 22 ? `${node.label.slice(0, 21)}…` : node.label}</tspan></text></g>)}</svg></div>;
}

function normalizeFormulaText(raw: string) {
  return String(raw || "")
    .replace(/\*\*/g, "")
    .replace(/\\\\/g, "\\")
    .replace(/\\\s+/g, " ")
    .replace(/\\_/g, "_")
    .trim();
}

function FormulaParts({ raw }: { raw: string }) {
  const text = normalizeFormulaText(raw);
  const match = text.match(/\$\$([\s\S]*?)\$\$|\$([\s\S]*?)\$/);
  const math = (match?.[1] || match?.[2] || (/[\\^_=]|\\frac|\\sqrt|\\times|\\Delta/.test(text) ? text : "")).trim();
  const explanation = match ? `${text.slice(0, match.index).trim()} ${text.slice((match.index || 0) + match[0].length).trim()}`.trim() : "";
  if (!math) return <p className="notebook-formula-prose">{text}</p>;
  const html = katex.renderToString(math, { displayMode: true, throwOnError: false, strict: "ignore" });
  return <><div className="notebook-formula-math" dangerouslySetInnerHTML={{ __html: html }} />{explanation ? <p className="notebook-formula-prose">{explanation}</p> : null}</>;
}

function FormulaSheet({ artifact }: { artifact: NotebookArtifact }) {
  const formulas = artifact.payload.formulas || [];
  return <section className="notebook-artifact-panel"><div className="notebook-artifact-heading"><div><span className="notebook-eyebrow">GENERATED OUTPUT · QUICK REFERENCE</span><h3>{artifact.title}</h3><p className="notebook-artifact-subtitle">Readable equations with the original source page retained.</p></div><span>{formulas.length} formulas</span></div><div className="notebook-formula-list">{formulas.length ? formulas.map((formula: any) => <article key={formula.formulaId}><FormulaParts raw={formula.text} /><small>{formula.sourceId}{formula.page ? ` · page ${formula.page}` : ""}</small></article>) : <p>No equation-like lines were detected yet.</p>}</div></section>;
}

function OpenMAICLesson({ artifact }: { artifact: NotebookArtifact }) {
  const payload = artifact.payload;
  const slides = (payload.slides || []) as Array<any>;
  const [slideIndex, setSlideIndex] = useState(0);
  const [actionIndex, setActionIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const audioRef = useRef<HTMLAudioElement>(null);
  const slide = slides[slideIndex] || {};
  const assets = (slide.assetIds || []).map((id: string) => (payload.assets || []).find((asset: any) => asset.assetId === id)).filter(Boolean);
  const actions = slide.actions || [];

  useEffect(() => { setActionIndex(0); }, [slideIndex]);
  useEffect(() => {
    if (!playing || !slides.length) return;
    const narration = String(slide.narration || slide.body || "");
    const audioUrl = slide.audio?.dataUrl;
    if (audioUrl && audioRef.current) {
      audioRef.current.src = audioUrl;
      audioRef.current.currentTime = 0;
      void audioRef.current.play().catch(() => setPlaying(false));
      return () => { audioRef.current?.pause(); };
    }
    if (typeof window !== "undefined" && "speechSynthesis" in window && narration) {
      window.speechSynthesis.cancel();
      const speech = new SpeechSynthesisUtterance(narration);
      speech.rate = 0.94;
      speech.onend = () => setSlideIndex((index) => index >= slides.length - 1 ? (setPlaying(false), index) : index + 1);
      window.speechSynthesis.speak(speech);
      return () => window.speechSynthesis.cancel();
    }
    const timer = window.setTimeout(() => setSlideIndex((index) => index >= slides.length - 1 ? (setPlaying(false), index) : index + 1), Math.max(8, Number(slide.durationSeconds || 12)) * 1000);
    return () => window.clearTimeout(timer);
  }, [playing, slide, slides.length]);
  useEffect(() => {
    if (!playing || actions.length < 2) return;
    const timer = window.setInterval(() => setActionIndex((index) => Math.min(actions.length - 1, index + 1)), Math.max(1200, (Number(slide.durationSeconds || 12) * 1000) / actions.length));
    return () => window.clearInterval(timer);
  }, [playing, slide.durationSeconds, actions.length]);

  function next() { setSlideIndex((index) => Math.min(slides.length - 1, index + 1)); }
  function previous() { setSlideIndex((index) => Math.max(0, index - 1)); }
  return <section className="notebook-artifact-panel openmaic-lesson"><div className="notebook-artifact-heading"><div><span className="notebook-eyebrow">OPENMAIC STUDY STUDIO · NARRATED SLIDES</span><h3>{payload.title || artifact.title}</h3><p className="notebook-artifact-subtitle">A source-grounded visual lesson with guided actions and automatic progression.</p></div><span>{slideIndex + 1} / {slides.length}</span></div><div className="openmaic-lesson-stage"><div className="openmaic-lesson-topline"><span>SCENE {String(slideIndex + 1).padStart(2, "0")}</span><span>{payload.groundedIn || "notebook"} · {payload.voiceProviderId ? "voice ready" : "browser narration"}</span></div><h4>{slide.title}</h4><p className="openmaic-lesson-body">{slide.body}</p>{slide.bullets?.length ? <ul className="openmaic-lesson-bullets">{slide.bullets.map((bullet: string) => <li key={bullet}>{bullet}</li>)}</ul> : null}{assets.length ? <div className="notebook-slide-assets">{assets.map((asset: any) => <figure key={asset.assetId}><img src={asset.dataUrl || asset.url} alt={asset.alt || "Source visual"} /><figcaption>{asset.alt || "Source visual"}{asset.page ? ` · p. ${asset.page}` : ""}</figcaption></figure>)}</div> : null}<NotebookDiagram diagram={slide.diagram} /><div className="openmaic-action-rail"><span className="notebook-eyebrow">TEACHING ACTIONS</span>{actions.map((action: any, index: number) => <button key={`${action.kind}-${index}`} type="button" className={index === actionIndex ? "active" : ""} onClick={() => setActionIndex(index)}><small>{action.kind}</small><strong>{action.label}</strong></button>)}</div><div className="openmaic-focus"><span className="notebook-eyebrow">TEACHING FOCUS</span><strong>{actions[actionIndex]?.label || "Follow the explanation and connect it to the visual."}</strong></div></div><audio ref={audioRef} controls className="openmaic-audio" onEnded={next} /><div className="notebook-artifact-controls"><button type="button" onClick={previous} disabled={slideIndex === 0}>← Previous scene</button><button type="button" className="notebook-primary-button" onClick={() => setPlaying((value) => !value)}>{playing ? "Pause lesson" : "Play narrated lesson"}</button><button type="button" onClick={next} disabled={slideIndex >= slides.length - 1}>Next scene →</button></div></section>;
}

type LessonSpotlight = { kind: "title" | "body" | "bullet" | "diagram" | "asset" | "canvas"; index?: number };

function lessonSpotlight(action: any, slide: any, actionIndex: number): LessonSpotlight | null {
  const allowed = ["title", "body", "bullet", "diagram", "asset", "canvas"];
  let kind = allowed.includes(action?.target) ? action.target as LessonSpotlight["kind"] : action?.kind === "draw" ? "diagram" : action?.kind === "write" ? "title" : action?.kind === "highlight" ? "bullet" : "body";
  const bullets = Array.isArray(slide.bullets) ? slide.bullets : [];
  const assets = Array.isArray(slide.assetIds) ? slide.assetIds : [];
  const nodes = Array.isArray(slide.diagram?.nodes) ? slide.diagram.nodes : [];
  if (kind === "bullet" && !bullets.length) kind = "body";
  if (kind === "asset" && !assets.length) kind = nodes.length ? "diagram" : "body";
  if (kind === "diagram" && !nodes.length) kind = "body";
  if (kind === "canvas") return { kind };
  const size = kind === "bullet" ? bullets.length : kind === "asset" ? assets.length : kind === "diagram" ? nodes.length : 1;
  const index = ["bullet", "asset", "diagram"].includes(kind) ? Math.min(Math.max(0, Number(action?.targetIndex ?? actionIndex)), Math.max(0, size - 1)) : undefined;
  return { kind, index };
}

function OpenMAICSpotlightLesson({ artifact }: { artifact: NotebookArtifact }) {
  const payload = artifact.payload;
  const slides = (payload.slides || []) as Array<any>;
  const [slideIndex, setSlideIndex] = useState(0);
  const [actionIndex, setActionIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const audioRef = useRef<HTMLAudioElement>(null);
  const slide = slides[slideIndex] || {};
  const actions = slide.actions || [];
  const spotlight = lessonSpotlight(actions[actionIndex], slide, actionIndex);
  const hasSpotlight = Boolean(spotlight && spotlight.kind !== "canvas");
  const itemClass = (kind: LessonSpotlight["kind"], index?: number) => !hasSpotlight ? "" : spotlight?.kind === kind && spotlight.index === index ? "is-focused" : "is-dimmed";
  const assets = (slide.assetIds || []).map((id: string) => (payload.assets || []).find((asset: any) => asset.assetId === id)).filter(Boolean);

  useEffect(() => { setActionIndex(0); }, [slideIndex]);
  useEffect(() => {
    if (!playing || !slides.length) return;
    const narration = String(slide.narration || slide.body || "");
    const audio = audioRef.current;
    if (slide.audio?.dataUrl && audio) {
      audio.src = slide.audio.dataUrl;
      audio.currentTime = 0;
      void audio.play().catch(() => setPlaying(false));
      return () => audio.pause();
    }
    if (typeof window !== "undefined" && "speechSynthesis" in window && narration) {
      window.speechSynthesis.cancel();
      const speech = new SpeechSynthesisUtterance(narration);
      speech.rate = 0.94;
      speech.onend = () => setSlideIndex((index) => index >= slides.length - 1 ? (setPlaying(false), index) : index + 1);
      window.speechSynthesis.speak(speech);
      return () => window.speechSynthesis.cancel();
    }
    const timer = window.setTimeout(() => setSlideIndex((index) => index >= slides.length - 1 ? (setPlaying(false), index) : index + 1), Math.max(8, Number(slide.durationSeconds || 12)) * 1000);
    return () => window.clearTimeout(timer);
  }, [playing, slideIndex, slide.narration, slide.body, slide.audio?.dataUrl, slide.durationSeconds, slides.length]);
  useEffect(() => {
    if (!playing || actions.length < 2) return;
    const timer = window.setInterval(() => setActionIndex((index) => Math.min(actions.length - 1, index + 1)), Math.max(1200, (Number(slide.durationSeconds || 12) * 1000) / actions.length));
    return () => window.clearInterval(timer);
  }, [playing, slide.durationSeconds, actions.length]);

  function next() { setSlideIndex((index) => Math.min(slides.length - 1, index + 1)); }
  function previous() { setSlideIndex((index) => Math.max(0, index - 1)); }
  return <section className="notebook-artifact-panel openmaic-lesson"><div className="notebook-artifact-heading"><div><span className="notebook-eyebrow">OPENMAIC STUDY STUDIO · NARRATED SLIDES</span><h3>{payload.title || artifact.title}</h3><p className="notebook-artifact-subtitle">Handwritten-style teaching slides with source visuals, diagrams, and guided focus.</p></div><span>{slideIndex + 1} / {slides.length}</span></div><div className={`openmaic-lesson-stage ${hasSpotlight ? "has-spotlight" : ""}`}><div className="openmaic-lesson-topline"><span>SCENE {String(slideIndex + 1).padStart(2, "0")}</span><span>{payload.groundedIn || "notebook"} · {payload.voiceProviderId ? "voice ready" : "browser narration"}</span></div><div className={`openmaic-slide-canvas ${hasSpotlight ? "has-spotlight" : ""}`}><div className={`openmaic-spotlight-item openmaic-slide-title ${itemClass("title")}`}><span className="openmaic-slide-kicker">{slide.slideLabel || "KEY IDEA"}</span><h4>{slide.title}</h4></div><div className={`openmaic-spotlight-item ${itemClass("body")}`}><p className="openmaic-lesson-body">{slide.body}</p></div>{slide.bullets?.length ? <ul className="openmaic-lesson-bullets">{slide.bullets.map((bullet: string, index: number) => <li key={`${bullet}-${index}`} className={`openmaic-spotlight-item ${itemClass("bullet", index)}`}>{bullet}</li>)}</ul> : null}{assets.length ? <div className={`notebook-slide-assets openmaic-spotlight-item ${itemClass("asset", 0)}`}>{assets.map((asset: any) => <figure key={asset.assetId}><img src={asset.dataUrl || asset.url} alt={asset.alt || "Source visual"} /><figcaption>{asset.alt || "Source visual"}{asset.page ? ` · p. ${asset.page}` : ""}</figcaption></figure>)}</div> : null}{slide.diagram?.nodes?.length ? <div className={`openmaic-spotlight-item ${itemClass("diagram")}`}><HanddrawnDiagram diagram={slide.diagram} focusNodeIndex={spotlight?.kind === "diagram" ? spotlight.index : undefined} /></div> : null}</div><div className="openmaic-action-rail"><span className="notebook-eyebrow">TEACHING ACTIONS · click a point to replay its focus</span>{actions.map((action: any, index: number) => <button key={`${action.kind}-${index}`} type="button" className={index === actionIndex ? "active" : ""} onClick={() => setActionIndex(index)}><small>{action.kind}{action.target ? ` · ${action.target}` : ""}</small><strong>{action.label}</strong></button>)}</div><div className="openmaic-focus"><span className="notebook-eyebrow">NOW TEACHING</span><strong>{actions[actionIndex]?.label || "Follow the explanation and connect it to the visual."}</strong><small>The white rectangle is the current focus. Everything else is softened so one important point stays clear.</small></div></div><audio ref={audioRef} controls className="openmaic-audio" onEnded={next} /><div className="notebook-artifact-controls"><button type="button" onClick={previous} disabled={slideIndex === 0}>← Previous scene</button><button type="button" className="notebook-primary-button" onClick={() => setPlaying((value) => !value)}>{playing ? "Pause lesson" : "Play narrated lesson"}</button><button type="button" onClick={next} disabled={slideIndex >= slides.length - 1}>Next scene →</button></div></section>;
}

function HanddrawnDiagram({ diagram, focusNodeIndex }: { diagram?: { nodes?: Array<{ id: string; label: string }>; edges?: Array<{ from: string; to: string }> }; focusNodeIndex?: number }) {
  const nodes = diagram?.nodes || [];
  if (!nodes.length) return null;
  const width = Math.max(760, nodes.length * 200);
  const nodeWidth = Math.min(174, Math.max(138, (width - 96) / nodes.length - 18));
  const xFor = (index: number) => 28 + index * ((width - nodeWidth - 56) / Math.max(1, nodes.length - 1));
  const linesFor = (label: string) => { const lines: string[] = []; let current = ""; for (const word of String(label || "").split(/\s+/)) { if ((current + " " + word).trim().length > 18 && current) { lines.push(current); current = word; } else current = `${current} ${word}`.trim(); } if (current) lines.push(current); return lines.slice(0, 3); };
  return <div className="notebook-diagram notebook-diagram-handdrawn"><span className="notebook-diagram-label">HAND-DRAWN VISUAL MODEL · FOLLOW THE FOCUS</span><svg viewBox={`0 0 ${width} 184`} role="img" aria-label="Hand-drawn source-grounded concept map">{(diagram?.edges || []).map((edge) => { const from = nodes.findIndex((node) => node.id === edge.from); const to = nodes.findIndex((node) => node.id === edge.to); if (from < 0 || to < 0) return null; return <line key={`${edge.from}-${edge.to}`} x1={xFor(from) + nodeWidth} y1="92" x2={xFor(to)} y2="92" stroke="#8995d4" strokeWidth="3" strokeLinecap="round" markerEnd="url(#handdrawn-arrow)" />; })}<defs><marker id="handdrawn-arrow" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="#7784ca" /></marker></defs>{nodes.map((node, index) => { const lines = linesFor(node.label); const focused = focusNodeIndex === index; return <g key={node.id} className={focused ? "notebook-diagram-node-focused" : ""} transform={`rotate(${index % 2 ? 0.7 : -0.7} ${xFor(index) + nodeWidth / 2} 92)`}><rect x={xFor(index)} y="52" width={nodeWidth} height="80" rx="15" fill={focused ? "#fff3d5" : "#fbfbff"} stroke={focused ? "#e69a39" : "#aeb9e8"} strokeWidth={focused ? "3" : "2"} strokeDasharray="2 1" /><text x={xFor(index) + nodeWidth / 2} y={92 - (lines.length - 1) * 7} textAnchor="middle" fill="#252a4b" fontSize="12" fontWeight="700" fontFamily="Segoe Print, Bradley Hand, cursive">{lines.map((line, lineIndex) => <tspan key={line} x={xFor(index) + nodeWidth / 2} dy={lineIndex === 0 ? 0 : 15}>{line}</tspan>)}</text></g>; })}</svg></div>;
}

function FlashcardDeck({ artifact }: { artifact: NotebookArtifact }) {
  const cards = (artifact.payload.cards || []) as Array<any>;
  const [index, setIndex] = useState(0);
  const [revealed, setRevealed] = useState(false);
  const card = cards[index] || {};
  if (!cards.length) return <section className="notebook-artifact-panel notebook-empty-artifact"><span className="notebook-eyebrow">RETRIEVAL PRACTICE</span><h3>No defensible flashcards yet</h3><p>Feynman needs a readable definition, relationship, parameter, correction, or formula before it creates a card.</p></section>;
  function move(step: number) { setIndex((value) => Math.min(cards.length - 1, Math.max(0, value + step))); setRevealed(false); }
  return <section className="notebook-artifact-panel notebook-flashcard-deck"><div className="notebook-artifact-heading"><div><span className="notebook-eyebrow">GENERATED OUTPUT · RETRIEVAL PRACTICE</span><h3>{artifact.title}</h3><p className="notebook-artifact-subtitle">Answer aloud first. Reveal only after you commit, then connect the explanation to the source.</p></div><span>{index + 1} / {cards.length}</span></div><button type="button" className={`notebook-flashcard ${revealed ? "revealed" : ""}`} onClick={() => setRevealed((value) => !value)} aria-label={revealed ? "Hide flashcard answer" : "Reveal flashcard answer"}><span className="notebook-flashcard-kicker">{revealed ? "SOURCE-BACKED ANSWER" : card.tag || "CHECK YOUR RECALL"}</span><strong>{revealed ? card.back : card.front}</strong><small>{revealed ? "Click to hide the answer" : "Click to reveal · say your answer first"}</small></button><div className="notebook-flashcard-meta"><span>Source-grounded</span>{card.sourceAnchors?.[0] ? <span>{card.sourceAnchors[0]}</span> : null}</div><div className="notebook-artifact-controls"><button type="button" onClick={() => move(-1)} disabled={index === 0}>← Previous card</button><button type="button" className="notebook-primary-button" onClick={() => setRevealed((value) => !value)}>{revealed ? "Hide answer" : "Reveal answer"}</button><button type="button" onClick={() => move(1)} disabled={index >= cards.length - 1}>Next card →</button></div></section>;
}

function ImportantQuestions({ artifact }: { artifact: NotebookArtifact }) {
  const questions = (artifact.payload.questions || []) as Array<any>;
  if (!questions.length) return <section className="notebook-artifact-panel notebook-empty-artifact"><span className="notebook-eyebrow">EXAM PREP</span><h3>No source-grounded questions yet</h3><p>Add a clearer source section or a past question paper to build meaningful practice.</p></section>;
  return <section className="notebook-artifact-panel"><div className="notebook-artifact-heading"><div><span className="notebook-eyebrow">GENERATED OUTPUT · SOURCE-GROUNDED PRACTICE</span><h3>{artifact.title}</h3><p className="notebook-artifact-subtitle">Every prompt names the idea, the situation, and what a strong answer must demonstrate.</p></div><span>{questions.length} prompts</span></div><div className="notebook-question-list notebook-question-list-rich">{questions.map((item, index) => <article key={item.id}><span>{String(index + 1).padStart(2, "0")}</span><div><small>{item.kind === "apply" ? "APPLY THE IDEA" : "EXPLAIN THE IDEA"}</small><strong>{item.question}</strong><details><summary>What a strong answer should contain</summary><p>{item.answerFocus || "Use the source definition, identify the relevant relationship, and justify your conclusion."}</p>{item.sourceAnchors?.length ? <small>Source anchor: {item.sourceAnchors[0]}</small> : null}</details></div></article>)}</div></section>;
}

function MCQPractice({ artifact }: { artifact: NotebookArtifact }) {
  const questions = (artifact.payload.questions || []) as Array<any>;
  const [mcqIndex, setMcqIndex] = useState(0);
  const [selected, setSelected] = useState<number | null>(null);
  const question = questions[mcqIndex] || {};
  const answered = selected !== null;
  return <section className="notebook-artifact-panel"><div className="notebook-artifact-heading"><div><span className="notebook-eyebrow">GENERATED OUTPUT · TOPIC PRACTICE</span><h3>{artifact.title}</h3><p className="notebook-artifact-subtitle">Each question identifies its topic; the correct choice is anchored to the same source section.</p></div><span>{mcqIndex + 1} / {questions.length}</span></div><div className="notebook-mcq"><span className="notebook-practice-topic">TOPIC · {question.topicTitle || "Source section"}</span><h4>{question.question}</h4>{(question.options || []).map((option: string, index: number) => <button key={`${index}-${option}`} type="button" className={answered && index === question.answerIndex ? "correct" : answered && index === selected ? "incorrect" : ""} onClick={() => setSelected(index)}>{String.fromCharCode(65 + index)} <span>{option}</span></button>)}{answered ? <div className="notebook-mcq-feedback"><strong>{selected === question.answerIndex ? "Correct - keep going." : "Review this idea before moving on."}</strong><p>{question.explanation}</p>{question.sourceAnchors?.[0] ? <small>Source anchor: {question.sourceAnchors[0]}</small> : null}</div> : null}</div><div className="notebook-artifact-controls"><button type="button" onClick={() => { setSelected(null); setMcqIndex((index) => Math.max(0, index - 1)); }} disabled={mcqIndex === 0}>Previous question</button><button type="button" className="notebook-primary-button" onClick={() => { setSelected(null); setMcqIndex((index) => Math.min(questions.length - 1, index + 1)); }} disabled={!answered || mcqIndex >= questions.length - 1}>Next question</button></div></section>;
}

function ArtifactPanel({ artifact, pack }: { artifact: NotebookArtifact; pack?: Notebook["knowledgePack"] }) {
  const payload = artifact.payload;
  const [slideIndex, setSlideIndex] = useState(0);
  const [mcqIndex, setMcqIndex] = useState(0);
  const [selected, setSelected] = useState<number | null>(null);
  if (payload.kind === "slides") return <VisualSlidesModern artifact={artifact} pack={pack} />;
  if (payload.kind === "openmaic_lesson") return <OpenMAICSpotlightLesson artifact={artifact} />;
  if (payload.kind === "formula_sheet") return <FormulaSheet artifact={artifact} />;
  if (payload.kind === "important_questions") return <ImportantQuestions artifact={artifact} />;
  if (payload.kind === "flashcards") return <FlashcardDeck artifact={artifact} />;
  if (payload.kind === "mcq" && !(payload.questions || []).length) return <section className="notebook-artifact-panel notebook-empty-artifact"><span className="notebook-eyebrow">MCQ PRACTICE</span><h3>No defensible MCQs yet</h3><p>Feynman only publishes a question when its answer can be supported by an extracted source section.</p></section>;
  if (payload.kind === "mcq") return <MCQPractice artifact={artifact} />;
  if (payload.kind === "slides") { const slides = payload.slides || []; const slide = slides[slideIndex] || {}; return <section className="notebook-artifact-panel"><div className="notebook-artifact-heading"><div><span className="notebook-eyebrow">GENERATED OUTPUT · SLIDE LESSON</span><h3>{artifact.title}</h3></div><span>{slideIndex + 1} / {slides.length}</span></div><div className="notebook-slide"><span className="notebook-slide-number">SLIDE {String(slideIndex + 1).padStart(2, "0")}</span><h4>{slide.title}</h4><p>{slide.body}</p><ul>{(slide.bullets || []).map((bullet: string) => <li key={bullet}>{bullet}</li>)}</ul><div className="notebook-visual-placeholder"><span>VISUAL LEARNING PROMPT</span><strong>{slide.visualHint}</strong><small>Source-linked visuals can be added to this slide without changing the source text.</small></div></div><div className="notebook-artifact-controls"><button type="button" onClick={() => setSlideIndex((index) => Math.max(0, index - 1))} disabled={slideIndex === 0}>← Previous</button><button type="button" onClick={() => setSlideIndex((index) => Math.min(slides.length - 1, index + 1))} disabled={slideIndex >= slides.length - 1}>Next slide →</button></div></section>; }
  if (payload.kind === "mcq") { const questions = payload.questions || []; const question = questions[mcqIndex] || {}; const answered = selected !== null; return <section className="notebook-artifact-panel"><div className="notebook-artifact-heading"><div><span className="notebook-eyebrow">GENERATED OUTPUT · PRACTICE</span><h3>{artifact.title}</h3></div><span>{mcqIndex + 1} / {questions.length}</span></div><div className="notebook-mcq"><h4>{question.question}</h4>{(question.options || []).map((option: string, index: number) => <button key={option} type="button" className={answered && index === question.answerIndex ? "correct" : answered && index === selected ? "incorrect" : ""} onClick={() => setSelected(index)}>{String.fromCharCode(65 + index)} <span>{option}</span></button>)}{answered && <div className="notebook-mcq-feedback"><strong>{selected === question.answerIndex ? "Correct — keep going." : "Review this idea before moving on."}</strong><p>{question.explanation}</p></div>}</div><div className="notebook-artifact-controls"><button type="button" onClick={() => { setSelected(null); setMcqIndex((index) => Math.max(0, index - 1)); }} disabled={mcqIndex === 0}>← Previous</button><button type="button" onClick={() => { setSelected(null); setMcqIndex((index) => Math.min(questions.length - 1, index + 1)); }} disabled={!answered || mcqIndex >= questions.length - 1}>Next question →</button></div></section>; }
  if (payload.kind === "formula_sheet") return <section className="notebook-artifact-panel"><div className="notebook-artifact-heading"><div><span className="notebook-eyebrow">GENERATED OUTPUT · QUICK REFERENCE</span><h3>{artifact.title}</h3></div><span>{(payload.formulas || []).length} formulas</span></div><div className="notebook-formula-list">{(payload.formulas || []).length ? payload.formulas.map((formula: any) => <article key={formula.formulaId}><strong>{formula.text}</strong><small>{formula.sourceId}{formula.page ? ` · page ${formula.page}` : ""}</small></article>) : <p>No equation-like lines were detected yet. Connect Mistral OCR for deeper scan and equation extraction.</p>}</div></section>;
  if (payload.kind === "important_questions") return <section className="notebook-artifact-panel"><div className="notebook-artifact-heading"><div><span className="notebook-eyebrow">GENERATED OUTPUT · EXAM PREP</span><h3>{artifact.title}</h3></div><span>{(payload.questions || []).length} prompts</span></div><div className="notebook-question-list">{(payload.questions || []).map((item: any, index: number) => <article key={item.id}><span>{String(index + 1).padStart(2, "0")}</span><div><small>{item.kind}</small><strong>{item.question}</strong></div></article>)}</div></section>;
  if (payload.kind === "flashcards") return <section className="notebook-artifact-panel"><div className="notebook-artifact-heading"><div><span className="notebook-eyebrow">GENERATED OUTPUT · RETRIEVAL</span><h3>{artifact.title}</h3></div><span>{(payload.cards || []).length} cards</span></div><div className="notebook-card-list">{(payload.cards || []).map((card: any) => <details key={card.front}><summary>{card.front}</summary><p>{card.back}</p></details>)}</div></section>;
  return <section className="notebook-artifact-panel"><div className="notebook-artifact-heading"><div><span className="notebook-eyebrow">GENERATED OUTPUT · ORIENTATION</span><h3>{artifact.title}</h3></div><span>{(payload.sections || []).length} sections</span></div><div className="notebook-summary-list">{(payload.sections || []).map((section: any) => <article key={section.title}><strong>{section.title}</strong><p>{section.summary}</p></article>)}</div></section>;
}
