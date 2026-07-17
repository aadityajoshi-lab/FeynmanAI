"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { studyModes } from "@/lib/learningModes";
import { chatWithStudyPlan, interactWithStudyPlan, StudyChatMessage, StudyChatResponse, StudyInteractionResponse, StudyPlanResponse, StudyScene } from "@/lib/studyApi";
import type { StudyAsset } from "@/lib/studyTypes";

type StudyDraft = {
  subjectId?: string;
  subjectTitle?: string;
  moduleId?: string;
  chapterTitle?: string;
  provider?: "fireworks" | "openai" | "fixture";
  providerMode?: string;
  sourceIds?: string[];
  assets?: StudyAsset[];
  learningMode?: string;
  plan?: StudyPlanResponse;
};

type ChatUiMessage = StudyChatMessage & { response?: StudyChatResponse };

function displayValue(value: unknown): ReactNode {
  if (value === null || value === undefined) return null;
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return value.map((item, index) => <li key={index}>{displayValue(item)}</li>);
  return <pre className="study-payload-pre">{JSON.stringify(value, null, 2)}</pre>;
}

function PayloadView({ payload }: { payload: Record<string, unknown> }) {
  const entries = Object.entries(payload || {});
  if (!entries.length) return null;
  return <dl className="study-payload-list">{entries.map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{Array.isArray(value) ? <ul>{displayValue(value)}</ul> : displayValue(value)}</dd></div>)}</dl>;
}

function GeneratedVisual({ config }: { config?: Record<string, unknown> }) {
  const source = config || {};
  const rawPoints = Array.isArray(source.points) ? source.points : [];
  const points = rawPoints.map((point) => {
    if (!point || typeof point !== "object") return null;
    const candidate = point as Record<string, unknown>;
    const x = Number(candidate.x);
    const y = Number(candidate.y);
    return Number.isFinite(x) && Number.isFinite(y) ? { x, y } : null;
  }).filter((point): point is { x: number; y: number } => Boolean(point));
  const minX = points.length ? Math.min(...points.map((point) => point.x)) : 0;
  const maxX = points.length ? Math.max(...points.map((point) => point.x)) : 1;
  const minY = points.length ? Math.min(...points.map((point) => point.y)) : 0;
  const maxY = points.length ? Math.max(...points.map((point) => point.y)) : 1;
  const rangeX = maxX - minX || 1;
  const rangeY = maxY - minY || 1;
  const polyline = points.map((point) => `${24 + ((point.x - minX) / rangeX) * 452},${142 - ((point.y - minY) / rangeY) * 112}`).join(" ");
  const title = typeof source.title === "string" ? source.title : typeof source.kind === "string" ? source.kind : "Generated visualization";

  return <div className="study-generated-visual" aria-label={title}>
    <div className="study-board-head"><div><span className="study-board-label">{typeof source.dimension === "string" ? source.dimension : "GENERATED VISUAL"}</span><strong>{title}</strong></div><span className="study-status">model manifest</span></div>
    {points.length >= 2 ? <svg viewBox="0 0 500 170" className="study-signal-svg" role="img" aria-label={title}><line x1="24" y1="142" x2="476" y2="142" className="study-axis" /><line x1="24" y1="30" x2="24" y2="142" className="study-axis" /><polyline points={polyline} className="study-sampled-line" />{points.map((point, index) => <circle key={`${point.x}-${point.y}-${index}`} cx={24 + ((point.x - minX) / rangeX) * 452} cy={142 - ((point.y - minY) / rangeY) * 112} r="3" className="study-sample-point" />)}</svg> : <PayloadView payload={source} />}
  </div>;
}

function sceneInteractionKind(scene: StudyScene): "predict" | "retrieval" | "teach_back" | "exam_bridge" | null {
  if (scene.checkpoint?.kind) return scene.checkpoint.kind;
  if (scene.type === "predict_checkpoint") return "predict";
  if (scene.type === "retrieval") return "retrieval";
  if (scene.type === "teach_back") return "teach_back";
  if (scene.type === "exam_bridge") return "exam_bridge";
  return null;
}

export default function StudyWorkspace() {
  const [draft, setDraft] = useState<StudyDraft | null>(null);
  const [activeSceneIndex, setActiveSceneIndex] = useState(0);
  const [visibleActions, setVisibleActions] = useState<Record<string, number>>({});
  const [responses, setResponses] = useState<Record<string, string>>({});
  const [interactionResults, setInteractionResults] = useState<Record<string, StudyInteractionResponse>>({});
  const [loadingInteractions, setLoadingInteractions] = useState<Record<string, boolean>>({});
  const [visualizationOpen, setVisualizationOpen] = useState<Record<string, boolean>>({});
  const [chatMessages, setChatMessages] = useState<ChatUiMessage[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const saved = window.localStorage.getItem("feynman.studyDraft");
    if (!saved) return;
    try {
      setDraft(JSON.parse(saved) as StudyDraft);
    } catch {
      setError("The saved module could not be read. Build it again from the study setup.");
    }
  }, []);

  const scenes = draft?.plan?.scenes ?? [];
  const activeScene = scenes[activeSceneIndex] as StudyScene | undefined;
  const activeOutline = draft?.plan?.outline?.find((item) => item.conceptId === activeScene?.conceptId);
  const learningMode = draft?.learningMode ?? studyModes[0].id;
  const mode = useMemo(() => studyModes.find((item) => item.id === learningMode) ?? studyModes[0], [learningMode]);

  function setMode(value: string) {
    setDraft((current) => {
      if (!current) return current;
      const updated = { ...current, learningMode: value };
      window.localStorage.setItem("feynman.studyDraft", JSON.stringify(updated));
      return updated;
    });
  }

  function revealNext(scene: StudyScene) {
    setVisibleActions((current) => ({ ...current, [scene.sceneId]: Math.min((current[scene.sceneId] ?? 0) + 1, scene.actions?.length ?? 0) }));
  }

  async function submitInteraction(scene: StudyScene) {
    if (!draft?.plan?.sourceIds?.length) return;
    const kind = sceneInteractionKind(scene);
    const response = responses[scene.sceneId]?.trim();
    if (!kind || !response) return;
    setLoadingInteractions((current) => ({ ...current, [scene.sceneId]: true }));
    setError("");
    try {
      const checkpoint = scene.checkpoint;
      const result = await interactWithStudyPlan({
        sourceIds: draft.plan.sourceIds,
        provider: draft.provider ?? "fireworks",
        kind,
        response,
        scene: {
          sceneId: scene.sceneId,
          prompt: checkpoint?.prompt ?? scene.explanation ?? scene.title,
          explanation: scene.explanation,
          responseType: checkpoint?.responseType ?? "long_text",
          sourceAnchorIds: scene.sourceAnchorIds,
        },
      });
      setInteractionResults((current) => ({ ...current, [scene.sceneId]: result }));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The live checkpoint could not be evaluated.");
    } finally {
      setLoadingInteractions((current) => ({ ...current, [scene.sceneId]: false }));
    }
  }

  function applyChatAction(action: StudyChatResponse["action"]) {
    if (!action) return;
    const targetIndex = action.sceneId ? scenes.findIndex((scene) => scene.sceneId === action.sceneId) : -1;
    if (action.kind === "next_scene") setActiveSceneIndex((current) => Math.min(Math.max(scenes.length - 1, 0), targetIndex >= 0 ? targetIndex : current + 1));
    if (action.kind === "previous_scene") setActiveSceneIndex((current) => Math.max(0, targetIndex >= 0 ? targetIndex : current - 1));
    if (["open_scene", "focus_checkpoint", "show_visualization", "repeat_explanation"].includes(action.kind) && targetIndex >= 0) setActiveSceneIndex(targetIndex);
    if (action.kind === "show_visualization" && targetIndex >= 0) setVisualizationOpen((current) => ({ ...current, [scenes[targetIndex].sceneId]: true }));
    if (action.kind === "repeat_explanation" && targetIndex >= 0) setVisibleActions((current) => ({ ...current, [scenes[targetIndex].sceneId]: Math.max(current[scenes[targetIndex].sceneId] ?? 0, 1) }));
    if (action.kind === "set_learning_mode" && action.modeId) setMode(action.modeId);
    if (action.kind === "focus_checkpoint" && targetIndex >= 0) window.setTimeout(() => document.getElementById(`checkpoint-${scenes[targetIndex].sceneId}`)?.scrollIntoView({ behavior: "smooth", block: "center" }), 0);
  }

  async function submitChat(forcedMessage?: string) {
    if (!draft?.plan?.sourceIds?.length || chatLoading) return;
    const message = (forcedMessage ?? chatInput).trim();
    if (!message) return;
    const userMessage: ChatUiMessage = { role: "user", content: message };
    const history = chatMessages.map(({ role, content }) => ({ role, content }));
    setChatMessages((current) => [...current, userMessage]);
    setChatInput("");
    setChatLoading(true);
    setError("");
    try {
      const result = await chatWithStudyPlan({
        subjectId: draft.subjectId || "study",
        subjectTitle: draft.subjectTitle,
        moduleId: draft.moduleId,
        sourceIds: draft.plan.sourceIds,
        provider: draft.provider ?? "fireworks",
        message,
        history,
        activeSceneId: activeScene?.sceneId,
        activeSceneIndex,
        learningMode,
        scenes: scenes.map((scene) => ({
          sceneId: scene.sceneId,
          title: scene.title,
          type: scene.type,
          hasVisualization: Boolean(scene.config && Object.keys(scene.config).length > 0),
          hasCheckpoint: Boolean(scene.checkpoint),
        })),
      });
      setChatMessages((current) => [...current, { role: "assistant", content: result.reply, response: result }]);
      applyChatAction(result.action);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The module copilot could not respond.");
    } finally {
      setChatLoading(false);
    }
  }

  if (!draft) {
    return <main className="study-empty-state"><p className="study-kicker">STUDY DESK</p><h1>No generated module loaded.</h1><p>Build a module from the study setup before opening this workspace.</p><Link href="/study/new" className="study-solid-button">Build a module -&gt;</Link></main>;
  }

  return <main className="study-desk-shell">
    <a className="study-skip-link" href="#study-desk-main">Skip to study desk</a>
    <header className="study-desk-header">
      <Link href="/study/new" className="study-wordmark" aria-label="Back to study setup">feynman<span>.ai</span></Link>
      <div className="study-desk-context"><span>{draft.subjectTitle || "Study module"} / {draft.chapterTitle || draft.moduleId || "selected scope"}</span><span className="study-runtime-label">{draft.plan?.providerMode || draft.providerMode || "provider unknown"} / {draft.plan?.sourcePackVersion || "source pack"}</span></div>
      <Link href="/subjects" className="study-quiet-link">Subject atlas</Link>
    </header>

    <div className="study-desk-grid" id="study-desk-main">
      <aside className="study-outline" aria-label="Generated module outline">
        <p className="study-kicker">GENERATED MODULE</p>
        <h1>{draft.chapterTitle || "Learning path"}</h1>
        <p className="study-outline-note">Every step below comes from the generated manifest. Open one scene, act on it, then explain what changed.</p>
        <ol className="study-step-list">
          {scenes.map((scene, index) => <li key={scene.sceneId} className={activeSceneIndex === index ? "active" : ""}><button type="button" onClick={() => setActiveSceneIndex(index)}><span>{String(index + 1).padStart(2, "0")}</span><strong>{scene.title}</strong></button></li>)}
        </ol>
        <div className="study-material-note"><span className="study-kicker">SOURCE MATERIAL</span><ul>{(draft.assets ?? []).map((asset) => <li key={asset.id}>{asset.name}</li>)}</ul><small>Source anchors are server-owned. Uploaded content remains reviewable until approval.</small></div>
      </aside>

      <section className="study-desk-main" aria-label="Generated interactive lesson">
        {draft.plan?.reviewRequired && <div className="study-review-banner" role="status"><strong>Draft source pack.</strong><span>The live provider used extracted candidates, but the source spans still need instructor approval before this lesson can be treated as authoritative evidence.</span></div>}
        {error && <div className="study-form-error" role="alert">{error}</div>}
        {!activeScene && <section className="study-generated-module"><h2>The provider returned no learner scenes.</h2><p>Retry the module build so the source pack can produce a complete manifest.</p></section>}
        {activeScene && <>
          <div className="study-desk-title-row"><div><p className="study-kicker">SCENE {activeSceneIndex + 1} / {activeScene.type}</p><h2>{activeScene.title}</h2><p>{activeScene.explanation || activeOutline?.objective || "This scene did not return an explanation body."}</p></div><span className="study-step-count">{activeSceneIndex + 1} of {scenes.length}</span></div>

          {activeOutline && <section className="study-generated-module" aria-label="Concept objective"><div className="study-generated-heading"><div><span className="study-board-label">CONCEPT OBJECTIVE</span><h2>{activeOutline.title}</h2><p>{activeOutline.objective}</p></div><span className="study-runtime-label">{activeScene.sourceAnchorIds.length} source anchors</span></div></section>}

          {visualizationOpen[activeScene.sceneId] && activeScene.config && Object.keys(activeScene.config).length > 0 && <GeneratedVisual config={activeScene.config} />}

          <section className="study-board" aria-label="Generated whiteboard actions"><div className="study-board-head"><div><span className="study-board-label">WHITEBOARD EXPLAINER</span><strong>Reveal the model-authored steps in order.</strong></div><span className="study-status">{activeScene.actions?.length ?? 0} actions</span></div><div className="study-action-list">{(activeScene.actions ?? []).slice(0, visibleActions[activeScene.sceneId] ?? 0).map((action) => <article key={action.actionId} className="study-action-card"><span className="study-board-label">{action.kind}</span><h3>{action.label}</h3><PayloadView payload={action.payload} /></article>)}</div>{(activeScene.actions?.length ?? 0) > (visibleActions[activeScene.sceneId] ?? 0) && <button className="study-solid-button" type="button" onClick={() => revealNext(activeScene)}>Reveal next action -&gt;</button>}{(activeScene.actions?.length ?? 0) === 0 && <p className="study-muted">No whiteboard actions were returned for this scene.</p>}</section>

          {sceneInteractionKind(activeScene) && <section className="study-checkpoint" id={`checkpoint-${activeScene.sceneId}`}><div className="study-checkpoint-heading"><div><span className="study-board-label">{activeScene.checkpoint?.kind?.replace("_", " ") || activeScene.type}</span><h3>{activeScene.checkpoint?.prompt || activeScene.explanation || activeScene.title}</h3></div><span className="study-question-label">source-bounded checkpoint</span></div>{activeScene.checkpoint?.options?.length ? <div className="study-predictions" role="radiogroup" aria-label={activeScene.checkpoint.prompt}>{activeScene.checkpoint.options.map((option) => <label key={option} className={responses[activeScene.sceneId] === option ? "selected" : ""}><input type="radio" name={`response-${activeScene.sceneId}`} value={option} checked={responses[activeScene.sceneId] === option} onChange={() => setResponses((current) => ({ ...current, [activeScene.sceneId]: option }))} />{option}</label>)}</div> : <textarea className="study-interaction-textarea" value={responses[activeScene.sceneId] ?? ""} onChange={(event) => setResponses((current) => ({ ...current, [activeScene.sceneId]: event.target.value }))} placeholder="Write your response before asking the live provider to inspect it." aria-label={activeScene.checkpoint?.prompt || activeScene.title} maxLength={12000} />}
            <div className="study-checkpoint-footer"><button className="study-solid-button" type="button" onClick={() => submitInteraction(activeScene)} disabled={!responses[activeScene.sceneId]?.trim() || loadingInteractions[activeScene.sceneId]}>{loadingInteractions[activeScene.sceneId] ? "Evaluating..." : "Check with the live provider"}</button>{interactionResults[activeScene.sceneId] && <InteractionResult result={interactionResults[activeScene.sceneId]} />}</div></section>}
        </>}
      </section>

      <aside className="study-next-panel" aria-label="Module controls">
        <section className="study-chat-card" aria-label="Module copilot">
          <div className="study-chat-heading"><div><span className="study-kicker">MODULE COPILOT</span><h2>Ask, then steer the desk.</h2></div><span className="study-chat-status">{draft.plan?.providerMode || "live provider"}</span></div>
          <p className="study-chat-note">Ask about the current concept or say “next scene”, “show the visualization”, “make it simpler”, or “use a worked example”.</p>
          <div className="study-chat-messages" role="log" aria-live="polite" aria-label="Module copilot messages">
            {!chatMessages.length && <p className="study-chat-empty">Your questions stay scoped to this module and its approved source pack.</p>}
            {chatMessages.map((message, index) => <article key={`${message.role}-${index}`} className={`study-chat-message ${message.role}`}><span>{message.role === "user" ? "YOU" : "COPILOT"}</span><p>{message.content}</p>{message.response && <small>{message.response.state} · {message.response.sourceAnchorIds.length} source anchors{message.response.action.kind !== "none" ? ` · ${message.response.action.kind.replaceAll("_", " ")}` : ""}</small>}</article>)}
          </div>
          <div className="study-chat-prompts" aria-label="Suggested module commands">
            <button type="button" onClick={() => void submitChat("Make this concept simpler.")} disabled={chatLoading}>Simpler</button>
            <button type="button" onClick={() => void submitChat("Show the visualization for this concept if one is available.")} disabled={chatLoading}>Open visual</button>
            <button type="button" onClick={() => void submitChat("Take me to the next scene.")} disabled={chatLoading}>Next scene</button>
          </div>
          <form className="study-chat-form" onSubmit={(event) => { event.preventDefault(); void submitChat(); }}>
            <label className="study-sr-only" htmlFor="module-chat-input">Ask the module copilot</label>
            <textarea id="module-chat-input" value={chatInput} onChange={(event) => setChatInput(event.target.value)} placeholder="Ask about this concept or control the module…" maxLength={4000} rows={3} disabled={chatLoading} />
            <button className="study-solid-button" type="submit" disabled={chatLoading || !chatInput.trim()}>{chatLoading ? "Thinking…" : "Send"}</button>
          </form>
        </section>
        <div className="study-next-card"><span className="study-kicker">YOUR METHOD</span><label htmlFor="workspace-mode">Change anytime</label><select id="workspace-mode" className="study-select" value={learningMode} onChange={(event) => setMode(event.target.value)}>{studyModes.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select><p>{mode.description}</p></div>
        <div className="study-next-card"><span className="study-kicker">PROGRESS</span><h3>{activeSceneIndex + 1} / {scenes.length || 0} scenes</h3><p>{activeScene ? `${activeScene.sourceAnchorIds.length} source anchors are attached to this scene.` : "No scene is active."}</p><div className="study-step-actions"><button className="study-outline-button" type="button" onClick={() => setActiveSceneIndex((current) => Math.max(0, current - 1))} disabled={activeSceneIndex === 0}>Previous</button><button className="study-solid-button" type="button" onClick={() => setActiveSceneIndex((current) => Math.min(Math.max(0, scenes.length - 1), current + 1))} disabled={activeSceneIndex >= scenes.length - 1}>Next -&gt;</button></div></div>
        <div className="study-next-card study-source-note"><span className="study-kicker">SOURCE ANCHORS</span>{activeScene?.sourceAnchorIds.length ? <ul>{activeScene.sourceAnchorIds.map((anchor) => <li key={anchor}>{anchor}</li>)}</ul> : <p>No server-owned anchors were returned for this scene.</p>}<small>Quotes are rendered only from the server source pack, never from model prose.</small></div>
      </aside>
    </div>
  </main>;
}

function InteractionResult({ result }: { result: StudyInteractionResponse }) {
  const message = result.answer || result.explanation || result.reasonCode || result.state || "The provider returned a result.";
  return <div className="study-interaction-result" role="status"><strong>{result.state || "complete"}</strong><p>{message}</p><small>{result.providerMode} / record v{result.recordVersion} / {result.sourceAnchorIds.length} anchors</small></div>;
}
