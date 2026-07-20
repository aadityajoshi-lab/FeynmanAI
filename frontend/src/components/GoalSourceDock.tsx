"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { FeynmanIcon } from "./LearningAppShell";
import { LearningOsApiError, learningOsApi } from "@/lib/learningOsApi";
import { createNotebook } from "@/lib/notebookApi";
import type { GoalSourceContext, LearningGoal } from "@/lib/learningOsTypes";

type EvidenceSelection = { sourceIds: string[]; sourceAnchorIds: string[] };

type GoalSourceDockProps = {
  goal: LearningGoal;
  mobileOpen: boolean;
  onClose: () => void;
  onEvidenceSelectionChange?: (selection: EvidenceSelection) => void;
  onSourceContextsChange?: (contexts: GoalSourceContext[]) => void;
};

function sourceMessage(error: unknown) {
  if (error instanceof LearningOsApiError && error.status === 0) {
    return "Source context is temporarily unavailable. Start the local learning service, then retry.";
  }
  return error instanceof Error ? error.message : "Source context could not be loaded.";
}

function sourceCount(context: GoalSourceContext) {
  return context.sources.filter((source) => source.status === "ready").length;
}

function failedSourceCount(context: GoalSourceContext) {
  return context.sources.filter((source) => source.status === "failed").length;
}

function canGround(source: GoalSourceContext["sources"][number]) {
  return source.status === "ready" && source.groundingEnabled !== false;
}

export function GoalSourceDock({ goal, mobileOpen, onClose, onEvidenceSelectionChange, onSourceContextsChange }: GoalSourceDockProps) {
  const [contexts, setContexts] = useState<GoalSourceContext[] | null>(null);
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const [selectedSourceIds, setSelectedSourceIds] = useState<string[]>([]);
  const [selectedAnchorIds, setSelectedAnchorIds] = useState<string[]>([]);

  const applyEvidenceSelection = useCallback((sourceIds: string[], sourceAnchorIds: string[]) => {
    setSelectedSourceIds(sourceIds);
    setSelectedAnchorIds(sourceAnchorIds);
    onEvidenceSelectionChange?.({ sourceIds, sourceAnchorIds });
  }, [onEvidenceSelectionChange]);

  const clearEvidenceSelection = useCallback(() => applyEvidenceSelection([], []), [applyEvidenceSelection]);

  const load = useCallback(async () => {
    setError("");
    setContexts(null);
    try {
      const result = await learningOsApi.goalSources(goal.goalId);
      setContexts(result.notebooks);
      onSourceContextsChange?.(result.notebooks);
      clearEvidenceSelection();
    } catch (caught) {
      setError(sourceMessage(caught));
      setContexts([]);
      onSourceContextsChange?.([]);
      clearEvidenceSelection();
    }
  }, [clearEvidenceSelection, goal.goalId, onSourceContextsChange]);

  useEffect(() => { void load(); }, [load]);

  async function createBlankDesk() {
    setCreating(true);
    setError("");
    try {
      const notebook = await createNotebook({
        title: `${goal.title} sources`.slice(0, 160),
        subject: goal.domain.replaceAll("_", " "),
        description: `Source context for the learning goal: ${goal.title}`,
        learningGoal: "understand",
        ocrProvider: "auto",
        goalId: goal.goalId,
      });
      const attached = await learningOsApi.attachGoalNotebook(goal.goalId, notebook.notebookId);
      setContexts(attached.notebooks);
      onSourceContextsChange?.(attached.notebooks);
      clearEvidenceSelection();
    } catch (caught) {
      setError(sourceMessage(caught));
    } finally {
      setCreating(false);
    }
  }

  function toggleSource(context: GoalSourceContext, source: GoalSourceContext["sources"][number]) {
    if (!canGround(source)) return;
    const selected = selectedSourceIds.includes(source.sourceId);
    const sourceIds = selected ? selectedSourceIds.filter((id) => id !== source.sourceId) : [...selectedSourceIds, source.sourceId];
    const sourceAnchorIds = selected ? selectedAnchorIds.filter((id) => !(source.anchorIds || []).includes(id)) : selectedAnchorIds;
    applyEvidenceSelection(sourceIds, sourceAnchorIds);
  }

  function toggleAnchor(source: GoalSourceContext["sources"][number], anchorId: string) {
    if (!canGround(source)) return;
    const sourceIds = selectedSourceIds.includes(source.sourceId) ? selectedSourceIds : [...selectedSourceIds, source.sourceId];
    const sourceAnchorIds = selectedAnchorIds.includes(anchorId) ? selectedAnchorIds.filter((id) => id !== anchorId) : [...selectedAnchorIds, anchorId];
    applyEvidenceSelection(sourceIds, sourceAnchorIds);
  }

  const firstNotebook = contexts?.[0];

  return <aside className={`fos-source-dock ${mobileOpen ? "mobile-open" : ""}`} aria-label="Goal source context">
    <div className="fos-workspace-panel-head"><span>Source Dock</span><button type="button" onClick={onClose} aria-label="Close source dock"><FeynmanIcon name="close" /></button></div>
    <div className="fos-source-dock-body">
      <div className="fos-source-dock-intro">
        <span className="fos-source-orb"><FeynmanIcon name="source" size={20} /></span>
        <strong>{goal.sourceMode === "required" ? "Verification needs sources" : "Sources improve precision"}</strong>
        <p>{goal.sourceMode === "required" ? "Select a grounded source and an anchor before recording verified evidence." : "Select source context when you want grounded answers or verification."}</p>
      </div>

      <div className="fos-source-dock-actions">
        <Link href={`/sources?goal=${encodeURIComponent(goal.goalId)}`} className="fos-source-dock-add"><FeynmanIcon name="plus" /> Add context</Link>
        {!contexts?.length ? <button type="button" className="fos-text-button" onClick={() => void createBlankDesk()} disabled={creating}>{creating ? "Creating desk..." : "Start blank desk"}</button> : null}
      </div>

      {selectedSourceIds.length || selectedAnchorIds.length ? <div className="fos-source-selection" role="status"><strong>{selectedSourceIds.length} source{selectedSourceIds.length === 1 ? "" : "s"} selected</strong><span>{selectedAnchorIds.length} anchor{selectedAnchorIds.length === 1 ? "" : "s"} included with the attempt</span></div> : null}
      {contexts === null ? <div className="fos-source-loading" role="status"><span className="fos-loading-orb" /> Loading attached contexts...</div> : null}
      {error ? <div className="fos-source-error" role="alert"><p>{error}</p><button type="button" onClick={() => void load()}>Retry</button></div> : null}

      {contexts?.length ? <div className="fos-source-dock-list">
        {contexts.map((context) => <article className="fos-goal-source-context" key={context.notebookId}>
          <div className="fos-goal-source-context-head"><span><FeynmanIcon name="book" /> {context.title}</span><Link href={`/notebooks/${context.notebookId}`}>Open</Link></div>
          <p>{sourceCount(context)} ready of {context.sources.length} source{context.sources.length === 1 ? "" : "s"} / {failedSourceCount(context) ? `${failedSourceCount(context)} need attention / ` : ""}{context.status.replaceAll("_", " ")}</p>
          <div className="fos-goal-source-list">{context.sources.length ? context.sources.slice(0, 8).map((source) => {
            const selectable = canGround(source);
            const sourceSelected = selectedSourceIds.includes(source.sourceId);
            return <div className={`fos-goal-source-item ${sourceSelected ? "selected" : ""} ${!selectable ? "view-only" : ""}`} key={source.sourceId}>
              <button type="button" className="fos-goal-source-toggle" onClick={() => toggleSource(context, source)} disabled={!selectable} aria-pressed={sourceSelected}>
                <FeynmanIcon name="source" size={13} /><span><strong>{source.title}</strong><small>{!selectable && source.status === "ready" ? "View-only / excluded from grounded answers" : source.status === "ready" ? `${source.pageCount || 0} pages / ${source.blockCount || 0} blocks` : source.status.replaceAll("_", " ")}</small></span>
              </button>
              {selectable && source.anchorIds?.length ? <div className="fos-source-anchor-list" aria-label={`Anchors for ${source.title}`}>{source.anchorIds.slice(0, 6).map((anchorId) => <button type="button" key={anchorId} className={selectedAnchorIds.includes(anchorId) ? "selected" : ""} onClick={() => toggleAnchor(source, anchorId)} aria-pressed={selectedAnchorIds.includes(anchorId)} title={`Use ${anchorId} with this attempt`}>{anchorId}</button>)}</div> : null}
            </div>;
          }) : <small>No source has been added yet.</small>}</div>
        </article>)}
      </div> : !error ? <div className="fos-source-empty"><FeynmanIcon name="book" /><strong>No context attached yet</strong><small>Add a PDF, notes, a reference URL, typed source text, or begin with a blank personal note.</small></div> : null}

      <div className="fos-source-boundary"><FeynmanIcon name="lock" /><span>{firstNotebook ? <Link href={`/notebooks/${firstNotebook.notebookId}`}>Open source-grounded chat and Studio</Link> : "Source chat becomes available inside a context desk."}</span></div>
    </div>
  </aside>;
}
