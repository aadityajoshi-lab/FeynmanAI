"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { studyModes } from "@/lib/learningModes";
import { chatWithStudyPlan, generateRemediationVideo, interactWithStudyPlan, StudyChatMessage, StudyChatResponse, StudyInteractionResponse, StudyPlanResponse, StudyRemediationVideo, StudyScene, StudyStage } from "@/lib/studyApi";
import type { StudyAsset } from "@/lib/studyTypes";

type StudyDraft = {
  subjectId?: string;
  subjectTitle?: string;
  moduleId?: string;
  chapterTitle?: string;
  provider?: "openai" | "fixture";
  providerMode?: string;
  sourceIds?: string[];
  assets?: StudyAsset[];
  learningMode?: string;
  remediationVideoDurationSeconds?: number;
  remediationVideoConfig?: { mode: "openai_slides" | "sequenced_clips"; label: string; provider: string; configured: boolean; voiceConfigured: boolean };
  learningGoal?: "course" | "skill" | "interview" | "viva";
  goalBrief?: string;
  assessmentFocus?: "mastery" | "mock_test" | "conversation" | "viva";
  skillLevel?: "beginner" | "intermediate" | "advanced";
  plan?: StudyPlanResponse;
};

type ChatUiMessage = StudyChatMessage & { response?: StudyChatResponse };
type VideoUiState = { status: "idle" | "loading" | "ready" | "error"; video?: StudyRemediationVideo; error?: string };

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
  const container = config || {};
  const source = container.visual && typeof container.visual === "object" ? container.visual as Record<string, unknown> : container;
  const [focusIndex, setFocusIndex] = useState(0);
  const rawPoints = Array.isArray(source.points) ? source.points : [];
  const rawNodes = Array.isArray(source.nodes) ? source.nodes : [];
  const rawEdges = Array.isArray(source.edges) ? source.edges : [];
  const sourceNodes = rawNodes.map((node, index) => {
    if (!node || typeof node !== "object") return null;
    const item = node as Record<string, unknown>;
    const x = Number(item.x);
    const y = Number(item.y);
    return { id: String(item.id || `node-${index}`), label: String(item.label || item.title || item.id || `Step ${index + 1}`), description: item.description ? String(item.description) : "", x: Number.isFinite(x) ? x : null, y: Number.isFinite(y) ? y : null };
  }).filter((node): node is { id: string; label: string; description: string; x: number | null; y: number | null } => Boolean(node));
  const coordinateRangeX = sourceNodes.length ? Math.max(...sourceNodes.map((node) => node.x ?? 0)) - Math.min(...sourceNodes.map((node) => node.x ?? 0)) : 0;
  const coordinateRangeY = sourceNodes.length ? Math.max(...sourceNodes.map((node) => node.y ?? 0)) - Math.min(...sourceNodes.map((node) => node.y ?? 0)) : 0;
  // Keep the teaching diagram on a predictable learner-friendly grid. Model
  // coordinates often place a terminal node diagonally across the canvas,
  // which makes the reading order and arrow direction harder to follow.
  const useModelCoordinates = false;
  const nodes: Array<{ id: string; label: string; description: string; x: number; y: number }> = sourceNodes.map((node, index) => {
    if (useModelCoordinates && node.x !== null && node.y !== null) return { ...node, x: node.x, y: node.y };
    const columns = sourceNodes.length <= 6 ? Math.max(1, sourceNodes.length) : 4;
    return { ...node, x: 150 + (index % columns) * 300, y: 110 + Math.floor(index / columns) * 165 };
  });
  const nodeWidth = nodes.length > 4 ? 190 : 230;
  const nodeHeight = 92;
  const canvasWidth = nodes.length > 4 ? 1200 : 960;
  const layoutColumns = nodes.length <= 6 ? Math.max(1, nodes.length) : 4;
  const canvasHeight = Math.max(420, 205 + Math.ceil(nodes.length / layoutColumns) * 165);
  const nodeMinX = nodes.length ? Math.min(...nodes.map((node) => node.x)) : 0;
  const nodeMaxX = nodes.length ? Math.max(...nodes.map((node) => node.x)) : 1;
  const nodeMinY = nodes.length ? Math.min(...nodes.map((node) => node.y)) : 0;
  const nodeMaxY = nodes.length ? Math.max(...nodes.map((node) => node.y)) : 1;
  const nodeRangeX = nodeMaxX - nodeMinX || 1;
  const nodeRangeY = nodeMaxY - nodeMinY || 1;
  const diagramPosition = (node: { x: number; y: number }) => ({ x: 130 + ((node.x - nodeMinX) / nodeRangeX) * (canvasWidth - 260), y: 90 + ((node.y - nodeMinY) / nodeRangeY) * (canvasHeight - 180) });
  const wrapLabel = (label: string, maxLength = 19) => {
    const words = label.split(/\s+/);
    const lines: string[] = [];
    let line = "";
    words.forEach((word) => {
      if (line && `${line} ${word}`.length > maxLength) { lines.push(line); line = word; } else { line = line ? `${line} ${word}` : word; }
    });
    if (line) lines.push(line);
    return lines.slice(0, 3);
  };
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
  const diagram = nodes.length > 0 && rawEdges.length > 0;
  const activeNode = nodes[focusIndex] || nodes[0];
  const activeNodeLabel = activeNode?.label || title;
  const activeConnections = activeNode ? rawEdges.map((edge) => edge && typeof edge === "object" ? edge as Record<string, unknown> : {}).flatMap((edge) => {
    const from = String(edge.from || "");
    const to = String(edge.to || "");
    if (from === activeNode.id) return nodes.find((node) => node.id === to)?.label || [];
    if (to === activeNode.id) return nodes.find((node) => node.id === from)?.label || [];
    return [];
  }) : [];
  const activeNodeDescription = activeNode?.description || (activeConnections.length ? `${activeNodeLabel} connects to ${activeConnections.join(" and ")}. Follow this relationship before moving on.` : `This is the ${activeNodeLabel} step in the model. Identify its role before moving on.`);
  const visualDescription = typeof source.description === "string" ? source.description : typeof source.explanation === "string" ? source.explanation : typeof source.caption === "string" ? source.caption : diagram ? `This diagram shows how ${nodes.map((node) => node.label).join(", ")} fit together. Read the highlighted element first, then follow each connected arrow.` : points.length ? "Read the highlighted point first, then compare its value with the next change in the signal." : "Use the model-authored representation as a visual summary of this topic.";
  const visualTakeaways = Array.isArray(source.takeaways) ? source.takeaways.filter((item): item is string => typeof item === "string").slice(0, 4) : nodes.slice(0, 4).map((node) => node.description ? `${node.label}: ${node.description}` : `Identify the role of ${node.label}.`);
  const markerId = `study-arrow-${title.toLowerCase().replace(/[^a-z0-9]+/g, "-").slice(0, 24) || "visual"}`;
  useEffect(() => { setFocusIndex(0); }, [config]);

  return <div className="study-generated-visual" aria-label={title}>
    <div className="study-board-head"><div><span className="study-board-label">{typeof source.dimension === "string" ? source.dimension : "GENERATED VISUAL"}</span><strong>{title}</strong></div><span className="study-status">model manifest</span></div>
    <div className="study-visual-copy"><span className="study-board-label">HOW TO READ THIS</span><p>{visualDescription}</p>{visualTakeaways.length ? <ul>{visualTakeaways.map((takeaway) => <li key={takeaway}>{takeaway}</li>)}</ul> : null}</div>
    {points.length >= 2 ? <div className="study-visual-stage"><svg viewBox="0 0 960 360" className="study-signal-svg" role="img" aria-label={title}><line x1="72" y1="300" x2="900" y2="300" className="study-axis" /><line x1="72" y1="44" x2="72" y2="300" className="study-axis" /><polyline points={points.map((point) => `${72 + ((point.x - minX) / rangeX) * 828},${300 - ((point.y - minY) / rangeY) * 230}`).join(" ")} className="study-sampled-line" />{points.map((point, index) => <circle key={`${point.x}-${point.y}-${index}`} cx={72 + ((point.x - minX) / rangeX) * 828} cy={300 - ((point.y - minY) / rangeY) * 230} r={index === focusIndex ? "9" : "6"} className={index === focusIndex ? "study-sample-point active" : "study-sample-point"} onClick={() => setFocusIndex(index)} />)}</svg><div className="study-visual-focus"><span>TEACHING FOCUS {Math.min(focusIndex + 1, points.length)} / {points.length}</span><strong>Read the highlighted point, then compare it with the next change in the signal.</strong></div></div> : diagram ? <div className="study-visual-stage"><svg viewBox={`0 0 ${canvasWidth} ${canvasHeight}`} className="study-diagram-svg study-diagram-svg-large" role="img" aria-label={title}><defs><marker id={markerId} markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto"><path d="M0,0 L12,6 L0,12 z" className="study-diagram-arrow" /></marker></defs>{rawEdges.map((edge, index) => { const item = edge && typeof edge === "object" ? edge as Record<string, unknown> : {}; const fromIndex = nodes.findIndex((node) => node.id === String(item.from)); const toIndex = nodes.findIndex((node) => node.id === String(item.to)); const from = nodes[fromIndex]; const to = nodes[toIndex]; if (!from || !to) return null; const fromPoint = diagramPosition(from); const toPoint = diagramPosition(to); const activeEdge = fromIndex === focusIndex || toIndex === focusIndex; return <line key={`edge-${index}`} x1={fromPoint.x} y1={fromPoint.y} x2={toPoint.x} y2={toPoint.y} className={activeEdge ? "study-diagram-edge active" : "study-diagram-edge"} markerEnd={`url(#${markerId})`} />; })}{nodes.map((node, index) => { const point = diagramPosition(node); const lines = wrapLabel(node.label); const active = index === focusIndex; return <g key={node.id} className={active ? "study-diagram-node-svg active" : "study-diagram-node-svg"} onClick={() => setFocusIndex(index)} role="button" tabIndex={0} aria-label={`Teach ${node.label}`}><rect x={point.x - nodeWidth / 2} y={point.y - nodeHeight / 2} width={nodeWidth} height={nodeHeight} rx="12" className="study-diagram-box" />{lines.map((line, lineIndex) => <text key={line} x={point.x} y={point.y - 13 + lineIndex * 19} textAnchor="middle" className="study-diagram-label">{line}</text>)}{node.description && <text x={point.x} y={point.y + 32} textAnchor="middle" className="study-diagram-description">{node.description.slice(0, 32)}{node.description.length > 32 ? "…" : ""}</text>}</g>; })}</svg><div className="study-visual-focus"><span>TEACHING FOCUS {Math.min(focusIndex + 1, nodes.length)} / {nodes.length}</span><strong>{activeNodeLabel}</strong><p>{activeNodeDescription}</p></div><div className="study-visual-controls" aria-label="Visual teaching controls"><button type="button" className="study-outline-button" onClick={() => setFocusIndex((current) => Math.max(0, current - 1))} disabled={focusIndex === 0}>Previous element</button><button type="button" className="study-solid-button" onClick={() => setFocusIndex((current) => Math.min(nodes.length - 1, current + 1))} disabled={focusIndex >= nodes.length - 1}>Teach next element</button></div></div> : nodes.length ? <div className="study-diagram-flow">{nodes.map((node, index) => <button type="button" className={index === focusIndex ? "study-diagram-node active" : "study-diagram-node"} key={node.id} onClick={() => setFocusIndex(index)}><strong>{node.label}</strong>{node.description ? <span>{node.description}</span> : null}</button>)}</div> : <PayloadView payload={source} />}
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

function stagesForScene(scene: StudyScene): StudyStage[] {
  const cleanOptions = (options?: unknown): string[] | null => {
    if (options && !Array.isArray(options) && typeof options === "object") {
      const container = options as unknown as Record<string, unknown>;
      options = (container.items || container.choices || container.values) as unknown[] | null;
    }
    if (!Array.isArray(options)) return null;
    const values = options.map((option) => {
      if (option && typeof option === "object") {
        const item = option as Record<string, unknown>;
        return item.text ?? item.label ?? item.value ?? item.stem ?? item.option;
      }
      return option;
    }).filter((option): option is string | number => typeof option === "string" || typeof option === "number");
    return values.length ? values.map(String) : null;
  };
  if (scene.stages?.length) return scene.stages.map((rawStage) => {
    const stage = rawStage as StudyStage & Record<string, unknown>;
    const options = cleanOptions(stage.options || stage.choices);
    return {
      ...stage,
      stageId: String(stage.stageId || stage.id || `${scene.sceneId}-stage`),
      kind: (stage.kind || stage.stageKind || stage.type || "teach_back") as StudyStage["kind"],
      title: String(stage.title || stage.kind || "Check your understanding"),
      prompt: String(stage.prompt || stage.stem || stage.question || scene.explanation || scene.title),
      responseType: (stage.responseType || (options ? "single_choice" : "long_text")) as StudyStage["responseType"],
      options,
      sourceAnchorIds: (stage.sourceAnchorIds || stage.sourceAnchors || scene.sourceAnchorIds) as string[],
    };
  });
  if (!scene.checkpoint) return [];
  return [{
    stageId: `${scene.sceneId}-stage-1`,
    kind: scene.checkpoint.kind === "predict" ? "mcq" : "teach_back",
    title: scene.checkpoint.kind.replace("_", " "),
    prompt: scene.checkpoint.prompt,
    responseType: scene.checkpoint.responseType,
    options: cleanOptions(scene.checkpoint.options),
    sourceAnchorIds: scene.checkpoint.sourceAnchorIds,
  }];
}

function fileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new Error("The answer file could not be read."));
    reader.readAsDataURL(file);
  });
}

function sceneUnderstandingScore(scene: StudyScene, results: Record<string, StudyInteractionResponse>): number | null {
  const scores = stagesForScene(scene)
    .map((stage) => results[stage.stageId]?.understandingScore)
    .filter((score): score is number => typeof score === "number");
  return scores.length ? Math.round(scores.reduce((total, score) => total + score, 0) / scores.length) : null;
}

export default function StudyWorkspace() {
  const [draft, setDraft] = useState<StudyDraft | null>(null);
  const [activeSceneIndex, setActiveSceneIndex] = useState(0);
  const [activeStageIndex, setActiveStageIndex] = useState<Record<string, number>>({});
  const [visibleActions, setVisibleActions] = useState<Record<string, number>>({});
  const [responses, setResponses] = useState<Record<string, string>>({});
  const [confidence, setConfidence] = useState<Record<string, number>>({});
  const [attachments, setAttachments] = useState<Record<string, { name: string; mimeType: string; dataUrl: string }>>({});
  const [interactionResults, setInteractionResults] = useState<Record<string, StudyInteractionResponse>>({});
  const [retryStages, setRetryStages] = useState<Record<string, StudyStage>>({});
  const [reviewAccepted, setReviewAccepted] = useState<Record<string, boolean>>({});
  const [remediationVideos, setRemediationVideos] = useState<Record<string, VideoUiState>>({});
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
  const activeStages = activeScene ? stagesForScene(activeScene) : [];
  const currentStageIndex = activeScene ? Math.min(activeStageIndex[activeScene.sceneId] ?? 0, Math.max(activeStages.length - 1, 0)) : 0;
  const baseActiveStage = activeStages[currentStageIndex];
  const activeStage = baseActiveStage ? retryStages[baseActiveStage.stageId] ?? baseActiveStage : undefined;
  const activeOutline = draft?.plan?.outline?.find((item) => item.conceptId === activeScene?.conceptId);
  const learningMode = draft?.learningMode ?? studyModes[0].id;
  const mode = useMemo(() => studyModes.find((item) => item.id === learningMode) ?? studyModes[0], [learningMode]);
  const visibleActionCount = activeScene ? visibleActions[activeScene.sceneId] : undefined;

  useEffect(() => {
    if (!activeScene?.sceneId || visibleActionCount !== undefined) return;
    setVisibleActions((current) => ({ ...current, [activeScene.sceneId]: Math.min(1, activeScene.actions?.length ?? 0) }));
  }, [activeScene?.actions?.length, activeScene?.sceneId, visibleActionCount]);

  function topicUnlocked(index: number) {
    if (index === 0) return true;
    return scenes.slice(0, index).every((scene) => {
      const stages = stagesForScene(scene);
      const finalStage = stages[stages.length - 1];
      return !finalStage || interactionResults[finalStage.stageId]?.correct === true;
    });
  }

  const activeTopicComplete = !activeStages.length || interactionResults[activeStages[activeStages.length - 1].stageId]?.correct === true;

  function stageCleared(stageId: string) {
    return interactionResults[stageId]?.correct === true || reviewAccepted[stageId] === true;
  }

  function retryStage(stageId: string) {
    setInteractionResults((current) => {
      const next = { ...current };
      delete next[stageId];
      return next;
    });
    setResponses((current) => {
      const next = { ...current };
      delete next[stageId];
      return next;
    });
    setAttachments((current) => {
      const next = { ...current };
      delete next[stageId];
      return next;
    });
    setReviewAccepted((current) => {
      const next = { ...current };
      delete next[stageId];
      return next;
    });
    setRemediationVideos((current) => {
      const next = { ...current };
      delete next[stageId];
      return next;
    });
  }

  function startSimilarRetry(stage: StudyStage, result: StudyInteractionResponse) {
    if (!result.retryPrompt) {
      retryStage(stage.stageId);
      return;
    }
    const retryStageData: StudyStage = {
      ...stage,
      title: `Similar check: ${stage.title}`,
      prompt: result.retryPrompt,
      options: result.retryOptions ?? null,
      responseType: result.retryResponseType ?? stage.responseType,
      sourceAnchorIds: result.retrySourceAnchorIds?.length ? result.retrySourceAnchorIds : stage.sourceAnchorIds,
    };
    setRetryStages((current) => ({ ...current, [stage.stageId]: retryStageData }));
    retryStage(stage.stageId);
  }

  function continueAfterReview(scene: StudyScene, stage: StudyStage) {
    const stages = stagesForScene(scene);
    const stageIndex = stages.findIndex((candidate) => candidate.stageId === stage.stageId);
    if (stageIndex < 0 || stageIndex >= stages.length - 1) return;
    setReviewAccepted((current) => ({ ...current, [stage.stageId]: true }));
    setActiveStageIndex((current) => ({ ...current, [scene.sceneId]: stageIndex + 1 }));
    window.setTimeout(() => document.getElementById(`checkpoint-${scene.sceneId}`)?.scrollIntoView({ behavior: "smooth", block: "center" }), 0);
  }

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

  function startNextStage(scene: StudyScene, nextIndex: number) {
    setActiveStageIndex((current) => ({ ...current, [scene.sceneId]: nextIndex }));
    window.setTimeout(() => document.getElementById(`checkpoint-${scene.sceneId}`)?.scrollIntoView({ behavior: "smooth", block: "center" }), 0);
  }

  async function submitInteraction(scene: StudyScene) {
    if (!draft?.plan?.sourceIds?.length) return;
    const stages = stagesForScene(scene);
    const stageIndex = Math.min(activeStageIndex[scene.sceneId] ?? 0, Math.max(stages.length - 1, 0));
    const baseStage = stages[stageIndex];
    const stage = baseStage ? retryStages[baseStage.stageId] ?? baseStage : undefined;
    if (!stage || stage.kind === "definition") return;
    const kind = stage.kind === "mcq" ? "mcq" : stage.kind;
    const response = responses[stage.stageId]?.trim() || (attachments[stage.stageId] ? `Uploaded answer: ${attachments[stage.stageId].name}` : "");
    if (!response) return;
    setLoadingInteractions((current) => ({ ...current, [stage.stageId]: true }));
    setError("");
    try {
      const result = await interactWithStudyPlan({
        sourceIds: draft.plan.sourceIds,
        provider: draft.provider ?? "openai",
        kind,
        response,
        confidence: confidence[stage.stageId] ?? 3,
        attachment: attachments[stage.stageId] ?? null,
        scene: {
          sceneId: scene.sceneId,
          prompt: stage.prompt,
          explanation: scene.explanation,
          responseType: stage.responseType,
          sourceAnchorIds: stage.sourceAnchorIds,
          stage,
        },
      });
      setInteractionResults((current) => ({ ...current, [stage.stageId]: result }));
      if (result.nextAction === "advance" || result.correct === true) {
        const nextStageIndex = stageIndex + 1;
        if (nextStageIndex < stages.length) {
          setActiveStageIndex((current) => ({ ...current, [scene.sceneId]: nextStageIndex }));
        } else if (activeSceneIndex < scenes.length - 1) {
          setActiveSceneIndex((current) => current + 1);
        }
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The live checkpoint could not be evaluated.");
    } finally {
      setLoadingInteractions((current) => ({ ...current, [stage.stageId]: false }));
    }
  }

  async function startRemediationVideo(scene: StudyScene, stage: StudyStage, result: StudyInteractionResponse) {
    if (!draft?.plan?.sourceIds?.length || !result.mistake || !result.correctAnswer || !result.correction) return;
    setRemediationVideos((current) => ({ ...current, [stage.stageId]: { status: "loading" } }));
    try {
      const videoResponse = await generateRemediationVideo({
        sourceIds: draft.plan.sourceIds,
        requestedDurationSeconds: draft?.remediationVideoDurationSeconds || 60,
        mistake: result.mistake,
        correctAnswer: result.correctAnswer,
        correction: result.correction,
        remediation: result.remediation,
        scene: { sceneId: scene.sceneId, title: scene.title, stageKind: stage.kind, sourceAnchorIds: stage.sourceAnchorIds },
      });
      setRemediationVideos((current) => ({ ...current, [stage.stageId]: { status: "ready", video: videoResponse.remediationVideo } }));
    } catch (caught) {
      setRemediationVideos((current) => ({ ...current, [stage.stageId]: { status: "error", error: caught instanceof Error ? caught.message : "The remediation video could not be generated." } }));
    }
  }

  async function handleAttachment(stage: StudyStage, file: File | undefined) {
    if (!file) return;
    if (file.size > 4 * 1024 * 1024) {
      setError("Answer uploads must be smaller than 4 MB.");
      return;
    }
    try {
      const dataUrl = await fileAsDataUrl(file);
      setAttachments((current) => ({ ...current, [stage.stageId]: { name: file.name, mimeType: file.type, dataUrl } }));
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The answer file could not be read.");
    }
  }

  function applyChatAction(action: StudyChatResponse["action"]) {
    if (!action) return;
    const targetIndex = action.sceneId ? scenes.findIndex((scene) => scene.sceneId === action.sceneId) : -1;
    if (action.kind === "next_scene") setActiveSceneIndex((current) => {
      const nextIndex = Math.min(Math.max(scenes.length - 1, 0), targetIndex >= 0 ? targetIndex : current + 1);
      return topicUnlocked(nextIndex) ? nextIndex : current;
    });
    if (action.kind === "previous_scene") setActiveSceneIndex((current) => Math.max(0, targetIndex >= 0 ? targetIndex : current - 1));
    if (["open_scene", "focus_checkpoint", "show_visualization", "repeat_explanation"].includes(action.kind) && targetIndex >= 0) setActiveSceneIndex((current) => topicUnlocked(targetIndex) ? targetIndex : current);
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
        provider: draft.provider ?? "openai",
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
          hasCheckpoint: Boolean(scene.checkpoint || scene.stages?.length),
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
      <div className="study-desk-context"><span>{draft.subjectTitle || "Study module"} / {draft.chapterTitle || draft.moduleId || "selected scope"}</span><span className="study-runtime-label">{draft.learningGoal === "interview" ? "INTERVIEW PRACTICE" : draft.learningGoal === "viva" ? "VIVA PRACTICE" : draft.learningGoal === "skill" ? "SKILL BUILDING" : "SUBJECT MASTERY"} · {draft.skillLevel || "beginner"}</span></div>
      <div className="study-desk-header-actions"><span className="study-header-pill"><i /> session ready</span><Link href="/study/new" className="study-quiet-link">New desk</Link></div>
    </header>

    <div className="study-desk-grid" id="study-desk-main">
      <aside className="study-outline" aria-label="Generated module outline">
        <p className="study-kicker">GENERATED MODULE</p>
        <h1>{draft.chapterTitle || "Learning path"}</h1>
        <p className="study-outline-note">One topic at a time. Learn it, try it, prove it. The next topic unlocks when this one is secure.</p>
        <ol className="study-step-list">
          {scenes.map((scene, index) => { const score = sceneUnderstandingScore(scene, interactionResults); return <li key={scene.sceneId} className={activeSceneIndex === index ? "active" : ""}><button type="button" disabled={!topicUnlocked(index)} onClick={() => setActiveSceneIndex(index)}><span>{String(index + 1).padStart(2, "0")}</span><strong>{scene.title}</strong><small>{score === null ? "not started" : `understanding ${score}%`} · {stagesForScene(scene).length} stages</small></button></li>; })}
        </ol>
        <div className="study-material-note"><span className="study-kicker">CONTEXT</span>{draft.assets?.length ? <ul>{draft.assets.map((asset) => <li key={asset.id}>{asset.name}</li>)}</ul> : <p className="study-context-empty">General practice mode. No upload required.</p>}<small>{draft.assets?.length ? "Uploaded content stays reviewable and keeps the lesson close to your material." : "The coach is using the goal, level, and assessment focus to guide this desk."}</small></div>
      </aside>

      <section className="study-desk-main" aria-label="Generated interactive lesson">
        {draft.plan?.reviewRequired && <div className="study-review-banner" role="status"><strong>Draft source pack.</strong><span>The live provider used extracted candidates, but the source spans still need instructor approval before this lesson can be treated as authoritative evidence.</span></div>}
        {error && <div className="study-form-error" role="alert">{error}</div>}
        {!activeScene && <section className="study-generated-module"><h2>The provider returned no learner scenes.</h2><p>Retry the module build so the source pack can produce a complete manifest.</p></section>}
        {activeScene && <>
          <div className="study-desk-title-row"><div><p className="study-kicker">TOPIC {activeSceneIndex + 1} / {activeStage ? `STAGE ${currentStageIndex + 1} OF ${activeStages.length}` : activeScene.type}</p><h2>{activeScene.title}</h2><p>{activeStage?.kind === "definition" ? activeScene.explanation : activeStage?.prompt || activeScene.explanation || activeOutline?.objective || "This scene did not return an explanation body."}</p>{draft.goalBrief && <span className="study-goal-context">Goal: {draft.goalBrief}</span>}</div><span className="study-step-count">{activeSceneIndex + 1} of {scenes.length}</span></div>

          {activeOutline && <section className="study-generated-module" aria-label="Concept objective"><div className="study-generated-heading"><div><span className="study-board-label">CONCEPT OBJECTIVE</span><h2>{activeOutline.title}</h2><p>{activeOutline.objective}</p></div><span className="study-runtime-label">{activeScene.sourceAnchorIds.length} source anchors</span></div></section>}

          {(activeScene.keyPoints?.length || activeScene.workedExample || activeScene.commonMistakes?.length) ? <section className="study-content-pack" aria-label="Complete topic explanation">
            {activeScene.keyPoints?.length ? <div><span className="study-board-label">KEY IDEAS</span><ul>{activeScene.keyPoints.map((point) => <li key={point}>{point}</li>)}</ul></div> : null}
            {activeScene.workedExample ? <div className="study-worked-example"><span className="study-board-label">WORKED EXAMPLE</span><p>{activeScene.workedExample}</p></div> : null}
            {activeScene.commonMistakes?.length ? <div className="study-common-mistakes"><span className="study-board-label">COMMON MISTAKES</span><ul>{activeScene.commonMistakes.map((mistake) => <li key={mistake}>{mistake}</li>)}</ul></div> : null}
          </section> : null}

          {draft.plan?.pastQuestionAnalysis?.length ? <section className="study-past-analysis" aria-label="Past question analysis"><span className="study-board-label">PAST QUESTION PATTERNS</span><p>The module used your past questions to target these recurring demands:</p><ul>{draft.plan.pastQuestionAnalysis.map((pattern) => <li key={pattern}>{pattern}</li>)}</ul></section> : null}

          {activeStages.length > 0 && <nav className="study-stage-strip" aria-label="Topic understanding stages">{activeStages.map((stage, index) => <button key={stage.stageId} type="button" disabled={index > 0 && !stageCleared(activeStages[index - 1].stageId)} className={currentStageIndex === index ? "active" : ""} onClick={() => setActiveStageIndex((current) => ({ ...current, [activeScene.sceneId]: index }))}><span>{String(index + 1).padStart(2, "0")}</span><strong>{stage.title}</strong>{interactionResults[stage.stageId]?.correct && <em>passed</em>}{reviewAccepted[stage.stageId] && !interactionResults[stage.stageId]?.correct && <em>reviewed</em>}</button>)}</nav>}

          {activeScene.config && Object.keys(activeScene.config).length > 0 && <section className="study-source-visual" aria-label="Source-grounded visual"><div className="study-board-head"><div><span className="study-board-label">SOURCE-GROUNDED VISUAL</span><strong>Model-authored representation for this topic</strong></div><span className="study-status">available</span></div><GeneratedVisual config={activeScene.config} /></section>}

          <section className="study-board" aria-label="Generated whiteboard actions"><div className="study-board-head"><div><span className="study-board-label">WHITEBOARD EXPLAINER</span><strong>Reveal the model-authored steps in order.</strong></div><span className="study-status">{activeScene.actions?.length ?? 0} actions</span></div><div className="study-action-list">{(activeScene.actions ?? []).slice(0, visibleActions[activeScene.sceneId] ?? 0).map((action) => <article key={action.actionId} className="study-action-card"><span className="study-board-label">{action.kind}</span><h3>{action.label}</h3><PayloadView payload={action.payload} /></article>)}</div>{(activeScene.actions?.length ?? 0) > (visibleActions[activeScene.sceneId] ?? 0) && <button className="study-solid-button" type="button" onClick={() => revealNext(activeScene)}>Reveal next action -&gt;</button>}{(activeScene.actions?.length ?? 0) === 0 && <p className="study-muted">No whiteboard actions were returned for this scene.</p>}</section>

          {activeStage && activeStage.kind !== "definition" && <section className="study-checkpoint" id={`checkpoint-${activeScene.sceneId}`}>
            <div className="study-checkpoint-heading"><div><span className="study-board-label">{activeStage.kind.replace("_", " ")}</span><h3>{activeStage.prompt}</h3><p className="study-stage-help">{activeStage.kind === "mcq" ? "Select one option. The answer key stays hidden until your response is evaluated." : "Write your reasoning or upload your handwritten work. The next stage unlocks after a correct response or after you review the correction."}</p></div><span className="study-question-label">level {currentStageIndex + 1} / source-bounded check</span></div>
            {activeStage.options?.length ? <div className="study-predictions" role="radiogroup" aria-label={activeStage.prompt}>{activeStage.options.map((option) => <label key={option} className={responses[activeStage.stageId] === option ? "selected" : ""}><input type="radio" name={`response-${activeStage.stageId}`} value={option} checked={responses[activeStage.stageId] === option} onChange={() => setResponses((current) => ({ ...current, [activeStage.stageId]: option }))} />{option}</label>)}</div> : <textarea className="study-interaction-textarea" value={responses[activeStage.stageId] ?? ""} onChange={(event) => setResponses((current) => ({ ...current, [activeStage.stageId]: event.target.value }))} placeholder={activeStage.kind === "numerical" ? "Write the known values, formula, substitution, and final answer." : activeStage.kind === "formula" ? "Write the formula and define each symbol." : "Write your answer before asking the live provider to inspect it."} aria-label={activeStage.prompt} maxLength={12000} />}
            {(activeStage.responseType === "file" || ["diagram", "formula", "numerical"].includes(activeStage.kind)) && <div className="study-answer-upload"><label htmlFor={`answer-file-${activeStage.stageId}`}>Upload a handwritten formula, solution, or block diagram <small>(PNG, JPG, WebP, or PDF; max 4 MB)</small></label><input id={`answer-file-${activeStage.stageId}`} type="file" accept="image/png,image/jpeg,image/webp,application/pdf" onChange={(event) => void handleAttachment(activeStage, event.target.files?.[0])} />{attachments[activeStage.stageId] && <small>Attached: {attachments[activeStage.stageId].name}</small>}</div>}
            <div className="study-confidence-row"><label htmlFor={`confidence-${activeStage.stageId}`}>How confident are you?</label><select id={`confidence-${activeStage.stageId}`} value={confidence[activeStage.stageId] ?? 3} onChange={(event) => setConfidence((current) => ({ ...current, [activeStage.stageId]: Number(event.target.value) }))}><option value={1}>1 — guessing</option><option value={2}>2 — unsure</option><option value={3}>3 — somewhat sure</option><option value={4}>4 — confident</option><option value={5}>5 — very confident</option></select></div>
            <div className="study-checkpoint-footer"><button className="study-solid-button" type="button" onClick={() => submitInteraction(activeScene)} disabled={(!responses[activeStage.stageId]?.trim() && !attachments[activeStage.stageId]) || loadingInteractions[activeStage.stageId]}>{loadingInteractions[activeStage.stageId] ? "Evaluating..." : "Check my understanding"}</button>{interactionResults[activeStage.stageId] && <InteractionResult result={interactionResults[activeStage.stageId]} canContinue={currentStageIndex < activeStages.length - 1} videoConfig={draft?.remediationVideoConfig} videoState={remediationVideos[activeStage.stageId]} onGenerateVideo={() => void startRemediationVideo(activeScene, activeStage, interactionResults[activeStage.stageId])} onSimilarRetry={() => startSimilarRetry(activeStage, interactionResults[activeStage.stageId])} onRetry={() => retryStage(activeStage.stageId)} onContinue={() => continueAfterReview(activeScene, activeStage)} />}</div>
          </section>}
          {activeStage?.kind === "definition" && <section className="study-checkpoint study-definition-step"><div className="study-checkpoint-heading"><div><span className="study-board-label">TOPIC DEFINITION</span><h3>Read the explanation, then start the first check.</h3><p className="study-stage-help">Writing and upload controls appear in the application stage. This step establishes the idea before the MCQ.</p></div><span className="study-question-label">understanding ladder</span></div><div className="study-definition-copy"><span className="study-board-label">IN PLAIN LANGUAGE</span><p>{activeScene.explanation || activeOutline?.objective || "Build a clear mental model of this topic before you test it."}</p>{activeScene.keyPoints?.length ? <ul>{activeScene.keyPoints.slice(0, 5).map((point) => <li key={point}>{point}</li>)}</ul> : null}</div><div className="study-definition-actions"><div><span className="study-board-label">READY FOR CHECK 01</span><p>When this idea feels clear, continue to the multiple-choice check.</p></div><button className="study-solid-button study-definition-continue" type="button" onClick={() => startNextStage(activeScene, currentStageIndex + 1)}>I understand — start the MCQ</button></div></section>}
        </>}
      </section>

      <aside className="study-next-panel" aria-label="Lesson controls">
        <section className="study-chat-card" aria-label="Module copilot">
          <div className="study-chat-heading"><div><span className="study-kicker">LESSON COPILOT</span><h2>Need another angle?</h2></div><span className="study-chat-status">{draft.plan?.providerMode || "live provider"}</span></div>
          <p className="study-chat-note">Ask for a simpler explanation, a worked example, a visual, or the next topic. This panel changes the lesson; it does not replace the required checks.</p>
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
        <div className="study-next-card"><span className="study-kicker">LEARNING MODE</span><label htmlFor="workspace-mode">Change the teaching rhythm</label><select id="workspace-mode" className="study-select" value={learningMode} onChange={(event) => setMode(event.target.value)}>{studyModes.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select><p>{mode.description}</p></div>
        <div className="study-next-card study-progress-card"><span className="study-kicker">YOUR PROGRESS</span><div className="study-progress-heading"><h3>Topic {activeSceneIndex + 1} <span>of {scenes.length || 0}</span></h3><strong>{activeTopicComplete ? "ready to continue" : "in progress"}</strong></div><div className="study-progress-track"><span style={{ width: `${scenes.length ? ((activeSceneIndex + (activeTopicComplete ? 1 : 0)) / scenes.length) * 100 : 0}%` }} /></div><p>{activeScene ? "Complete the four stages to unlock the next topic." : "No scene is active."}</p><div className="study-step-actions"><button className="study-outline-button" type="button" onClick={() => setActiveSceneIndex((current) => Math.max(0, current - 1))} disabled={activeSceneIndex === 0}>Previous</button><button className="study-solid-button" type="button" onClick={() => setActiveSceneIndex((current) => Math.min(Math.max(0, scenes.length - 1), current + 1))} disabled={activeSceneIndex >= scenes.length - 1 || !activeTopicComplete}>Next -&gt;</button></div></div>
        <div className="study-next-card study-source-note"><span className="study-kicker">EVIDENCE</span><p className="study-evidence-intro">These IDs show which uploaded or guided context supports the current topic.</p>{activeScene?.sourceAnchorIds.length ? <ul>{activeScene.sourceAnchorIds.map((anchor) => <li key={anchor}>{anchor}</li>)}</ul> : <p>No server-owned anchors were returned for this scene.</p>}<small>Source anchors protect the lesson boundary; they are not extra tasks for you.</small></div>
      </aside>
    </div>
  </main>;
}

function RemediationVideoPlayer({ video }: { video: StudyRemediationVideo }) {
  if (video.mode === "openai_slides") return <OpenAISlidePlayer video={video} />;
  return <RemediationClipPlayer video={video} />;
}

function RemediationClipPlayer({ video }: { video: Extract<StudyRemediationVideo, { mode: "sequenced_clips" }> }) {
  const [clipIndex, setClipIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  useEffect(() => { setClipIndex(0); setPlaying(false); }, [video]);
  const clip = video.clips[clipIndex];
  useEffect(() => {
    if (!playing || !clip || !videoRef.current) return;
    void videoRef.current.play().catch(() => setPlaying(false));
  }, [clip, playing]);
  if (!clip) return null;
  function playNarration() {
    setPlaying(true);
    if (audioRef.current) {
      audioRef.current.currentTime = videoRef.current?.currentTime || 0;
      void audioRef.current.play().catch(() => undefined);
    }
  }
  function pauseNarration() {
    audioRef.current?.pause();
  }
  function syncNarration() {
    if (audioRef.current && videoRef.current) audioRef.current.currentTime = videoRef.current.currentTime;
  }
  function nextClip() {
    audioRef.current?.pause();
    if (clipIndex >= video.clips.length - 1) {
      setPlaying(false);
      return;
    }
    setClipIndex((current) => Math.min(current + 1, video.clips.length - 1));
  }
  return <div className="study-remediation-player"><video ref={videoRef} key={clip.url} controls playsInline preload="metadata" poster={clip.poster} src={clip.url} onPlay={playNarration} onPause={pauseNarration} onSeeking={syncNarration} onEnded={nextClip} />{clip.narration && <><audio ref={audioRef} key={clip.narration.dataUrl} controls preload="metadata" src={clip.narration.dataUrl} /><small className="study-narration-note">Narration generated with the configured VoxCPM Python voice.</small></>}<nav className="study-video-segments" aria-label="Remediation video segments">{video.clips.map((item, index) => <button key={item.index} type="button" className={index === clipIndex ? "active" : ""} onClick={() => { audioRef.current?.pause(); setClipIndex(index); }}>{index === clipIndex && playing ? "Playing · " : ""}<span>{String(index + 1).padStart(2, "0")}</span>{item.title}</button>)}</nav><div className="study-video-progress"><span>{video.title}</span><small>{video.providerId} · segment {clipIndex + 1} of {video.clips.length} · about {Math.round(video.actualDurationSeconds)} seconds total · {clip.width}×{clip.height}</small></div></div>;
}

function OpenAISlidePlayer({ video }: { video: Extract<StudyRemediationVideo, { mode: "openai_slides" }> }) {
  const [slideIndex, setSlideIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [browserVoiceAvailable, setBrowserVoiceAvailable] = useState(false);
  const [voiceMode, setVoiceMode] = useState<"server" | "browser" | "unavailable">(video.voiceProviderId ? "server" : "unavailable");
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const slide = video.slides[slideIndex];
  useEffect(() => {
    setSlideIndex(0);
    setPlaying(false);
    setVoiceMode(video.voiceProviderId ? "server" : "unavailable");
  }, [video, video.voiceProviderId]);
  useEffect(() => {
    setBrowserVoiceAvailable(typeof window !== "undefined" && "speechSynthesis" in window && "SpeechSynthesisUtterance" in window);
  }, []);
  useEffect(() => {
    if (!playing || !slide) return;
    let cancelled = false;
    const audioElement = audioRef.current;
    const timer = window.setTimeout(() => {
      if (cancelled) return;
      if (slideIndex >= video.slides.length - 1) setPlaying(false);
      else setSlideIndex((current) => Math.min(current + 1, video.slides.length - 1));
    }, Math.max(4, slide.durationSeconds) * 1000);
    const speakInBrowser = () => {
      if (!("speechSynthesis" in window) || !("SpeechSynthesisUtterance" in window)) {
        setVoiceMode("unavailable");
        return;
      }
      const utterance = new SpeechSynthesisUtterance(slide.narration || `${slide.title}. ${slide.body}`);
      utterance.rate = 0.9;
      utterance.pitch = 1;
      utterance.volume = 1;
      const voices = window.speechSynthesis.getVoices();
      utterance.voice = voices.find((voice) => /^en(-|_)/i.test(voice.lang)) || voices[0] || null;
      utterance.onerror = () => setVoiceMode("unavailable");
      setVoiceMode("browser");
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(utterance);
    };
    if (slide.audio?.dataUrl && audioRef.current) {
      setVoiceMode("server");
      audioRef.current.currentTime = 0;
      void audioRef.current.play().catch(() => speakInBrowser());
    } else {
      speakInBrowser();
    }
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      window.speechSynthesis?.cancel();
      audioElement?.pause();
    };
  }, [playing, slide, slideIndex, video.slides.length]);
  if (!slide) return null;
  const diagramConfig = slide.diagram && slide.diagram.nodes.length ? { title: slide.title, kind: "diagram", ...slide.diagram } : undefined;
  const voiceLabel = voiceMode === "server" ? "VoxCPM voice enabled" : voiceMode === "browser" ? "browser narration" : "voice unavailable";
  const voiceNote = voiceMode === "server" ? "Narration generated with the configured VoxCPM Python voice." : voiceMode === "browser" ? "Narration is being read by your browser while the lesson advances automatically." : browserVoiceAvailable ? "Click Play lesson to start browser narration, or configure TTS_VOXCPM_BASE_URL for generated voice." : "No voice service is configured. Configure TTS_VOXCPM_BASE_URL on the backend for generated narration.";
  return <div className="study-slide-player"><div className="study-slide-canvas"><span className="study-slide-counter">SLIDE {slideIndex + 1} / {video.slides.length}</span><h4>{slide.title}</h4><p>{slide.body}</p><ul>{slide.bullets.map((bullet) => <li key={bullet}>{bullet}</li>)}</ul>{diagramConfig && <GeneratedVisual config={diagramConfig} />}</div>{slide.audio?.dataUrl && <audio ref={audioRef} key={slide.audio.dataUrl} controls preload="metadata" src={slide.audio.dataUrl} />}<small className={`study-narration-note ${voiceMode === "unavailable" ? "study-narration-unavailable" : ""}`}>{voiceNote}</small><div className="study-slide-controls"><button className="study-outline-button" type="button" onClick={() => { setPlaying(false); setSlideIndex((current) => Math.max(0, current - 1)); }}>Previous</button><button className="study-solid-button" type="button" onClick={() => setPlaying((current) => !current)}>{playing ? "Pause lesson" : "Play narrated lesson"}</button><button className="study-outline-button" type="button" onClick={() => { setPlaying(false); setSlideIndex((current) => Math.min(video.slides.length - 1, current + 1)); }}>Next</button></div><div className="study-video-progress"><span>{video.title}</span><small>{video.providerId} · {voiceLabel} · slide {slideIndex + 1} of {video.slides.length} · about {Math.round(video.actualDurationSeconds)} seconds total</small></div></div>;
}

function InteractionResult({ result, canContinue, videoConfig, videoState, onGenerateVideo, onSimilarRetry, onRetry, onContinue }: { result: StudyInteractionResponse; canContinue: boolean; videoConfig?: StudyDraft["remediationVideoConfig"]; videoState?: VideoUiState; onGenerateVideo: () => void; onSimilarRetry: () => void; onRetry: () => void; onContinue: () => void }) {
  const message = result.feedback || result.answer || result.explanation || result.reasonCode || result.state || "The provider returned a result.";
  const videoLabel = videoConfig?.label || "Source-grounded remediation video";
  const videoDescription = videoConfig?.mode === "sequenced_clips" ? "OpenMAIC-style rendered clips are generated in short ordered segments, then presented as one correction lesson." : "OpenAI creates a source-grounded slide lesson; the configured local Python voice reads it aloud when available.";
  const [readOpen, setReadOpen] = useState(true);
  return <div className={`study-interaction-result ${result.correct === false ? "needs-review" : "passed"}`} role="status"><strong>{result.correct ? "Understanding confirmed" : result.correct === false ? "Review this idea before moving on" : result.state || "complete"}</strong><p>{message}</p>{result.correct === false && result.mistake && <p className="study-mistake"><strong>Where it went wrong:</strong> {result.mistake}</p>}{result.correct === false && result.correctAnswer && <p className="study-correction"><strong>Correct answer:</strong> {result.correctAnswer}</p>}{result.correct === false && result.correction && <p><strong>How to fix it:</strong> {result.correction}</p>}{result.remediation && <p><strong>Review next:</strong> {result.remediation}</p>}{typeof result.understandingScore === "number" && <span>Understanding: {result.understandingScore}%</span>}{result.overconfidence && <span className="study-overconfidence">Confidence was higher than the demonstrated understanding. Slow down and use the remediation below.</span>}{result.correct === false && <><div className="study-remediation-options"><article className="study-correction-guide"><div className="study-remediation-card-head"><div><strong>1 · Read yourself</strong><span>Text explanation</span></div><button type="button" className="study-text-toggle" onClick={() => setReadOpen((current) => !current)} aria-expanded={readOpen}>{readOpen ? "Hide" : "Read explanation"}</button></div>{readOpen && <div className="study-read-remediation"><p>Use this compact repair path before retrying the question.</p>{result.correctAnswer && <div><span>Correct answer</span><p>{result.correctAnswer}</p></div>}{result.correction && <div><span>What to change</span><p>{result.correction}</p></div>}{result.remediation && <div><span>Try this next</span><p>{result.remediation}</p></div>}</div>}</article><article className="study-video-section"><div className="study-video-section-head"><div><strong>2 · {videoLabel}</strong><span className="study-video-subtitle">Visual explanation with narration</span></div><span>{videoConfig?.configured === false ? "not configured" : videoConfig?.voiceConfigured ? "voice enabled" : "voice optional"}</span></div><p>{videoDescription}</p>{videoState?.status === "loading" && <div className="study-video-loading" role="status"><span className="study-build-spinner" />Preparing source-grounded segments, narration, and playback controls...</div>}{videoState?.status === "ready" && videoState.video ? <RemediationVideoPlayer video={videoState.video} /> : videoState?.status !== "loading" && <button className="study-outline-button" type="button" onClick={onGenerateVideo}>{videoConfig?.mode === "sequenced_clips" ? "Generate rendered video lesson" : "Generate narrated visual lesson"}</button>}{videoState?.status === "error" && <small className="study-video-error">{videoState.error}</small>}</article></div><div className="study-result-actions">{result.retryPrompt && <button className="study-solid-button" type="button" onClick={onSimilarRetry}>Try a similar question</button>}{canContinue && <button className="study-outline-button" type="button" onClick={onContinue}>Review answer and continue</button>}<button className="study-outline-button study-retry-button" type="button" onClick={onRetry}>{result.retryPrompt ? "Retry this question" : "Try this stage again"}</button></div></>}<small>{result.providerMode} / record v{result.recordVersion} / {result.sourceAnchorIds.length} anchors</small></div>;
}
