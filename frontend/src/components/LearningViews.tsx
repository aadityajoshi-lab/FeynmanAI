"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { DomainActivityWorkbench } from "./DomainActivityWorkbench";
import { GoalSourceDock } from "./GoalSourceDock";
import { FeynmanIcon, LearningAppShell, SectionHeading, StatusPill } from "./LearningAppShell";
import { isAuthenticationError, LearningOsApiError, learningOsApi } from "@/lib/learningOsApi";
import { listNotebooks } from "@/lib/notebookApi";
import type { ActivityProviderFeedback, Course, CurriculumSummary, EvidenceRecord, GoalSourceContext, LearningActivity, LearningGoal, LearningWorkspace, ShareGrant, StructuredActivityAttempt } from "@/lib/learningOsTypes";
import type { NotebookListItem } from "@/lib/notebookTypes";

type InstitutionMetrics = {
  memberCounts: Record<string, number>;
  courseCount: number;
  activeEnrollmentCount: number;
  verifiedEvidenceCount: number;
  sourceGovernance: { approved: number; needsReview: number };
};

type Member = { membershipId: string; email: string; name: string; role: string; status: string };
type CohortLearner = { name: string; sharedEvidence: EvidenceRecord[] };
type RetryableAttempt = StructuredActivityAttempt;

function message(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

function stateCopy(error: unknown, resource: string) {
  if (error instanceof LearningOsApiError) {
    if (error.status === 0) return { title: "Learning service unavailable", copy: "Feynman cannot reach the local learning service. Start it on 127.0.0.1:8000 and try again." };
    if (error.status === 401) return { title: "Sign in to continue", copy: `Your ${resource} stays private until you sign in to its workspace.` };
    if (error.status === 403) return { title: "You do not have access", copy: `This ${resource} is outside your current role or sharing scope.` };
    if (error.status === 404) return { title: "This item is unavailable", copy: `The requested ${resource} no longer exists or is not shared with you.` };
  }
  return { title: `Could not load ${resource}`, copy: message(error, "Try again in a moment.") };
}

function RouteState({ title, state, error, onRetry, action }: { title: string; state: "loading" | "empty" | "error"; error?: unknown; onRetry?: () => void; action?: React.ReactNode }) {
  const detail = state === "error" ? stateCopy(error, title.toLowerCase()) : null;
  return <section className={`fos-route-state ${state}`} role={state === "loading" ? "status" : state === "error" ? "alert" : undefined}>
    {state === "loading" ? <><span className="fos-loading-orb" /><h2>Loading {title.toLowerCase()}...</h2><p>Retrieving the current workspace state.</p></> : null}
    {state === "empty" ? <><FeynmanIcon name="spark" size={28} /><h2>No {title.toLowerCase()} yet</h2><p>Nothing is assumed or filled with sample content.</p>{action}</> : null}
    {state === "error" && detail ? <><FeynmanIcon name="close" size={24} /><h2>{detail.title}</h2><p>{detail.copy}</p><div className="fos-state-actions">{onRetry ? <button type="button" className="fos-primary-action" onClick={onRetry}>Retry</button> : null}{error instanceof LearningOsApiError && error.status === 401 ? <Link className="fos-quiet-action" href={"/login" as never}>Sign in</Link> : null}</div></> : null}
  </section>;
}

function stateTone(status: string): "neutral" | "danger" {
  return status === "rejected" ? "danger" : "neutral";
}

function activityIcon(type: string) {
  if (type === "predict") return "spark";
  if (type === "simulate" || type === "apply") return "play";
  if (type === "debug") return "settings";
  if (type === "transfer") return "arrow";
  return "proof";
}

function formatStatus(value: string) {
  return value.replaceAll("_", " ");
}

async function managedCourse(courseId: string) {
  const course = await learningOsApi.course(courseId);
  if (!course.canManage) {
    throw new LearningOsApiError("This course is visible to you, but teaching controls require an instructor, owner, or institution-admin role.", 403, "role_required");
  }
  return course;
}

async function reviewableCourse(courseId: string) {
  const course = await managedCourse(courseId);
  if (!course.canReviewCohort) {
    throw new LearningOsApiError("Cohort evidence is available only to the assigned instructor.", 403, "cohort_review_required");
  }
  return course;
}

export function HomeDashboard() {
  const [dataState, setData] = useState<{ goals: LearningGoal[]; evidence: EvidenceRecord[]; courses: Course[]; notebooks: NotebookListItem[] } | null>(null);
  const [error, setError] = useState<unknown>(null);
  const load = useCallback(async () => {
    setError(null); setData(null);
    try {
      const [goals, evidence, courses, notebooks] = await Promise.all([learningOsApi.goals(), learningOsApi.evidence(), learningOsApi.courses(), listNotebooks()]);
      setData({ goals: goals.goals, evidence: evidence.evidence, courses: courses.courses, notebooks });
    } catch (caught) { setError(caught); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  if (!dataState) return <LearningAppShell eyebrow="PERSONAL LAB" title="Now"><RouteState title="workspace" state={error ? "error" : "loading"} error={error} onRetry={() => void load()} /></LearningAppShell>;
  const data = dataState;
  const activeGoal = data.goals.find((goal) => goal.status === "active") || data.goals[0];
  const readyDesks = data.notebooks.filter((notebook) => notebook.status === "ready").length;
  const totalSources = data.notebooks.reduce((total, notebook) => total + notebook.sourceCount, 0);
  const routeLength = activeGoal?.activities?.length || 0;
  const completedTasks = activeGoal?.activities?.filter((activity) => activity.status === "completed").length || 0;
  return <LearningAppShell eyebrow="PERSONAL LAB" title="Now">
    <section className="fos-home-hero">
      <div className="fos-home-hero-copy"><span className="fos-eyebrow">LEARNING ENGINE / NEXT PROOF</span><h1>{activeGoal ? "Turn today's question into proof." : "Build a capability, one proof at a time."}</h1><p>{activeGoal ? `Your route is waiting on one observable move: ${activeGoal.nextAction}` : "Feynman does not count reading as mastery. Start with a capability and we will shape the first task you can demonstrate."}</p><div className="fos-home-hero-actions">{activeGoal ? <Link href={`/goals/${activeGoal.goalId}/learn`} className="fos-primary-action">Open next proof <FeynmanIcon name="arrow" /></Link> : <Link href="/goals/new" className="fos-primary-action">Define a capability <FeynmanIcon name="arrow" /></Link>}<Link href="/evidence" className="fos-quiet-action">View evidence</Link></div></div>
      <div className="fos-home-loop" aria-label="Feynman learning loop"><span className="fos-home-loop-label">THE LOOP</span><ol><li className="active"><b>01</b><span>Goal</span></li><li className={activeGoal ? "active" : ""}><b>02</b><span>Route</span></li><li className={activeGoal && completedTasks ? "active" : ""}><b>03</b><span>Attempt</span></li><li className={activeGoal && data.evidence.length ? "active" : ""}><b>04</b><span>Evidence</span></li></ol><p>Every next action is earned by what you can show, not by how much you read.</p></div>
    </section>
    {!activeGoal ? <RouteState title="active goal" state="empty" action={<Link href="/goals/new" className="fos-primary-action">Create learning goal</Link>} /> : null}
    <section className="fos-home-metrics" aria-label="Current learning state"><div><span>ACTIVE GOAL</span><strong>{data.goals.length}</strong><small>{data.goals.length === 1 ? "one route in motion" : "routes in your lab"}</small></div><div><span>ROUTE PROGRESS</span><strong>{completedTasks}/{routeLength || 0}</strong><small>observable tasks completed</small></div><div><span>PROOF RECORDS</span><strong>{data.evidence.length}</strong><small>attempts in your evidence trail</small></div><div><span>SOURCES READY</span><strong>{readyDesks}</strong><small>{totalSources} source{totalSources === 1 ? "" : "s"} available</small></div></section>
    <section className="fos-home-quick-grid">
      <article className="fos-panel fos-home-route-card"><div className="fos-panel-title"><span><FeynmanIcon name="spark" /> Your route</span><Link href="/goals/new">New goal</Link></div>{data.goals.length ? <div className="fos-goal-list">{data.goals.slice(0, 3).map((goal) => <Link href={`/goals/${goal.goalId}`} key={goal.goalId} className="fos-goal-row"><span><strong>{goal.title}</strong><small>{goal.nextAction}</small></span><StatusPill>{goal.evidenceCount} proof{goal.evidenceCount === 1 ? "" : "s"}</StatusPill></Link>)}</div> : <p className="fos-empty-copy">A route appears after you confirm a learning contract.</p>}</article>
      <article className="fos-panel fos-home-proof-card"><div className="fos-panel-title"><span><FeynmanIcon name="proof" /> Recent proof</span><Link href="/evidence">Open evidence</Link></div>{data.evidence.length ? <div className="fos-evidence-stack">{data.evidence.slice(0, 3).map((item) => <div className="fos-evidence-line" key={item.evidenceId}><div><strong>{item.capability}</strong><p>{item.summary}</p></div><StatusPill tone={stateTone(item.status)}>{formatStatus(item.status)}</StatusPill></div>)}</div> : <p className="fos-empty-copy">Evidence starts after your first observable attempt.</p>}</article>
      <article className="fos-panel fos-home-source-card"><div className="fos-panel-title"><span><FeynmanIcon name="source" /> Source extraction</span><Link href="/sources">Source Desk</Link></div><div className="fos-source-status-summary"><strong>{readyDesks} of {data.notebooks.length} desks ready</strong><small>{totalSources} saved source{totalSources === 1 ? "" : "s"} across your account</small></div>{data.notebooks.length ? <div className="fos-source-status-list">{data.notebooks.slice(0, 3).map((notebook) => <Link href={`/notebooks/${notebook.notebookId}`} key={notebook.notebookId}><span><strong>{notebook.title}</strong><small>{notebook.sourceCount} source{notebook.sourceCount === 1 ? "" : "s"}</small></span><StatusPill>{formatStatus(notebook.status)}</StatusPill></Link>)}</div> : <p className="fos-empty-copy">Add context when a source should ground an answer or verification.</p>}</article>
      <article className="fos-panel fos-home-course-card"><div className="fos-panel-title"><span><FeynmanIcon name="course" /> Courses</span><Link href="/courses">All courses</Link></div>{data.courses.length ? data.courses.slice(0, 3).map((course) => <Link href={`/courses/${course.courseId}`} className="fos-course-row" key={course.courseId}><span><strong>{course.title}</strong><small>{course.learnerCount} learners · {course.sourcePackCount} source packs</small></span><FeynmanIcon name="arrow" /></Link>) : <p className="fos-empty-copy">Join a course when shared structure will help your route.</p>}</article>
    </section>
  </LearningAppShell>;
  return <LearningAppShell eyebrow="PERSONAL LAB" title="Now">
    <SectionHeading eyebrow="ONE PRIMARY NEXT ACTION" title={activeGoal ? activeGoal.nextAction : "Start with a capability."} copy={activeGoal ? activeGoal.title : "Describe what you want to become able to do. Your route begins with an observable task."} action={activeGoal ? <Link href={`/goals/${activeGoal.goalId}/learn`} className="fos-primary-action">Continue <FeynmanIcon name="arrow" /></Link> : null} />
    {!activeGoal ? <RouteState title="active goal" state="empty" action={<Link href="/goals/new" className="fos-primary-action">Create learning goal</Link>} /> : null}
    <section className="fos-home-grid">
      <article className="fos-panel"><div className="fos-panel-title"><span><FeynmanIcon name="spark" /> Active goals</span><Link href="/goals/new">New goal</Link></div>{data.goals.length ? <div className="fos-goal-list">{data.goals.map((goal) => <Link href={`/goals/${goal.goalId}`} key={goal.goalId} className="fos-goal-row"><span><strong>{goal.title}</strong><small>{goal.nextAction}</small></span><StatusPill>{goal.evidenceCount} evidence</StatusPill></Link>)}</div> : <p className="fos-empty-copy">A goal appears after you confirm a learning contract.</p>}</article>
      <article className="fos-panel"><div className="fos-panel-title"><span><FeynmanIcon name="proof" /> Recent evidence</span><Link href="/evidence">Open evidence</Link></div>{data.evidence.length ? <div className="fos-evidence-stack">{data.evidence.slice(0, 3).map((item) => <div className="fos-evidence-line" key={item.evidenceId}><div><strong>{item.capability}</strong><p>{item.summary}</p></div><StatusPill tone={stateTone(item.status)}>{formatStatus(item.status)}</StatusPill></div>)}</div> : <p className="fos-empty-copy">Evidence only appears after you submit an active attempt.</p>}</article>
      <article className="fos-panel"><div className="fos-panel-title"><span><FeynmanIcon name="source" /> Source extraction</span><Link href="/sources">Source Desk</Link></div><div className="fos-source-status-summary"><strong>{readyDesks} of {data.notebooks.length} desks ready</strong><small>{totalSources} saved source{totalSources === 1 ? "" : "s"} across your account</small></div>{data.notebooks.length ? <div className="fos-source-status-list">{data.notebooks.slice(0, 3).map((notebook) => <Link href={`/notebooks/${notebook.notebookId}`} key={notebook.notebookId}><span><strong>{notebook.title}</strong><small>{notebook.sourceCount} source{notebook.sourceCount === 1 ? "" : "s"}</small></span><StatusPill>{formatStatus(notebook.status)}</StatusPill></Link>)}</div> : <p className="fos-empty-copy">Add context when a source should ground an answer or verification.</p>}</article>
      <article className="fos-panel"><div className="fos-panel-title"><span><FeynmanIcon name="course" /> Courses</span><Link href="/courses">All courses</Link></div>{data.courses.length ? data.courses.slice(0, 3).map((course) => <Link href={`/courses/${course.courseId}`} className="fos-course-row" key={course.courseId}><span><strong>{course.title}</strong><small>{course.learnerCount} learners · {course.sourcePackCount} source packs</small></span><FeynmanIcon name="arrow" /></Link>) : <p className="fos-empty-copy">Join a course to see its shared learning structure.</p>}</article>
    </section>
  </LearningAppShell>;
  return <LearningAppShell eyebrow="PERSONAL LAB" title="Now">
    <SectionHeading eyebrow="ONE PRIMARY NEXT ACTION" title={activeGoal ? activeGoal.nextAction : "Start with a capability."} copy={activeGoal ? activeGoal.title : "Describe what you want to become able to do. Your route begins with an observable task."} action={activeGoal ? <Link href={`/goals/${activeGoal.goalId}/learn`} className="fos-primary-action">Continue <FeynmanIcon name="arrow" /></Link> : null} />
    {!activeGoal ? <RouteState title="active goal" state="empty" action={<Link href="/goals/new" className="fos-primary-action">Create learning goal</Link>} /> : null}
    <section className="fos-home-grid">
      <article className="fos-panel"><div className="fos-panel-title"><span><FeynmanIcon name="spark" /> Active goals</span><Link href="/goals/new">New goal</Link></div>{data.goals.length ? <div className="fos-goal-list">{data.goals.map((goal) => <Link href={`/goals/${goal.goalId}`} key={goal.goalId} className="fos-goal-row"><span><strong>{goal.title}</strong><small>{goal.nextAction}</small></span><StatusPill>{goal.evidenceCount} evidence</StatusPill></Link>)}</div> : <p className="fos-empty-copy">A goal appears after you confirm a learning contract.</p>}</article>
      <article className="fos-panel"><div className="fos-panel-title"><span><FeynmanIcon name="proof" /> Recent evidence</span><Link href="/evidence">Open evidence</Link></div>{data.evidence.length ? <div className="fos-evidence-stack">{data.evidence.slice(0, 3).map((item) => <div className="fos-evidence-line" key={item.evidenceId}><div><strong>{item.capability}</strong><p>{item.summary}</p></div><StatusPill tone={stateTone(item.status)}>{formatStatus(item.status)}</StatusPill></div>)}</div> : <p className="fos-empty-copy">Evidence only appears after you submit an active attempt.</p>}</article>
      <article className="fos-panel"><div className="fos-panel-title"><span><FeynmanIcon name="course" /> Courses</span><Link href={"/courses" as never}>All courses</Link></div>{data.courses.length ? data.courses.slice(0, 3).map((course) => <Link href={`/courses/${course.courseId}`} className="fos-course-row" key={course.courseId}><span><strong>{course.title}</strong><small>{course.learnerCount} learners · {course.sourcePackCount} source packs</small></span><FeynmanIcon name="arrow" /></Link>) : <p className="fos-empty-copy">Join a course to see its shared learning structure.</p>}</article>
    </section>
  </LearningAppShell>;
}

export function GoalsIndexView() {
  const [goals, setGoals] = useState<LearningGoal[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const load = useCallback(async () => {
    setError(null); setGoals(null);
    try {
      const result = await learningOsApi.goals();
      const detailed = await Promise.all(result.goals.map(async (goal) => {
        try { return await learningOsApi.goal(goal.goalId); } catch { return goal; }
      }));
      setGoals(detailed);
    } catch (caught) { setError(caught); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  if (!goals) return <LearningAppShell eyebrow="GOALS" title="Your learning routes"><RouteState title="goals" state={error ? "error" : "loading"} error={error} onRetry={() => void load()} /></LearningAppShell>;
  const grouped = goals.reduce<Record<string, LearningGoal[]>>((acc, goal) => { (acc[goal.domain || "general"] ||= []).push(goal); return acc; }, {});
  return <LearningAppShell eyebrow="GOALS" title="Your learning routes">
    <SectionHeading eyebrow="PERSISTENT LEARNER STATE" title="See every route you started." copy="Goals are durable capabilities, grouped by category. Progress only moves when you submit observable work." />
    {!goals.length ? <RouteState title="learning goal" state="empty" action={<Link href="/goals/new" className="fos-primary-action">Create your first goal</Link>} /> : <div className="fos-goal-catalog">{Object.entries(grouped).map(([domain, items]) => <section key={domain} className="fos-goal-category"><div className="fos-goal-category-head"><span className="fos-eyebrow">{formatStatus(domain)}</span><span>{items.length} route{items.length === 1 ? "" : "s"}</span></div><div className="fos-goal-category-grid">{items.map((goal) => { const activities = goal.activities || []; const completed = activities.filter((activity) => activity.status === "completed").length; const progress = activities.length ? Math.round((completed / activities.length) * 100) : 0; return <article className="fos-goal-catalog-card fos-panel" key={goal.goalId}><div className="fos-goal-catalog-top"><StatusPill>{formatStatus(goal.status)}</StatusPill><span>{goal.currentLevel}</span></div><h2>{goal.title}</h2><p>{goal.outcome || goal.description || goal.nextAction}</p><div className="fos-goal-progress" aria-label={`${progress}% route progress`}><span style={{ width: `${progress}%` }} /></div><div className="fos-goal-progress-meta"><strong>{completed}/{activities.length || "—"} tasks</strong><span>{goal.evidenceCount} proof record{goal.evidenceCount === 1 ? "" : "s"}</span></div><p className="fos-goal-next"><strong>Next</strong> {goal.nextAction}</p><div className="fos-goal-catalog-actions"><Link href={`/goals/${goal.goalId}`} className="fos-quiet-action">Open overview</Link><Link href={`/goals/${goal.goalId}/learn`} className="fos-primary-action">Start guide <FeynmanIcon name="arrow" /></Link></div></article>; })}</div></section>)}</div>}
  </LearningAppShell>;
}

function CurriculumPreview({ goal, curriculum, onUpdated }: { goal: LearningGoal; curriculum: CurriculumSummary; onUpdated: (result: { curriculum: CurriculumSummary; goal: LearningGoal }) => void }) {
  const initialOrder = (goal.activities || []).map((activity) => activity.activityId);
  const [activityOrder, setActivityOrder] = useState(initialOrder);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [messageText, setMessageText] = useState("");
  const activitiesById = new Map((goal.activities || []).map((activity) => [activity.activityId, activity]));
  const orderedActivities = activityOrder.map((activityId) => activitiesById.get(activityId)).filter((activity): activity is LearningActivity => Boolean(activity));
  const quality = curriculum.quality || {};
  const move = (index: number, direction: -1 | 1) => {
    const next = index + direction;
    if (next < 0 || next >= activityOrder.length) return;
    const reordered = [...activityOrder];
    [reordered[index], reordered[next]] = [reordered[next], reordered[index]];
    setActivityOrder(reordered);
    setDirty(true);
  };
  async function save(changes: { activityOrder?: string[]; approvalState?: "pending" | "approved" }) {
    setBusy(true); setMessageText("");
    try { onUpdated(await learningOsApi.updateCurriculum(goal.goalId, changes)); setDirty(false); setMessageText(changes.approvalState === "approved" ? "Curriculum approved for this course." : "Route correction saved."); }
    catch (caught) { setMessageText(message(caught, "The route correction could not be saved.")); }
    finally { setBusy(false); }
  }
  return <section className="fos-curriculum-preview fos-panel" aria-label="Curriculum preview">
    <header className="fos-curriculum-preview-head"><div><span className="fos-eyebrow">CURRICULUM PREVIEW</span><h2>What you will learn</h2><p>Review the cited concepts and observable route before you invest a session. Provider output is provisional, not proof of mastery.</p></div><StatusPill>{`v${curriculum.version}`}</StatusPill></header>
    <div className="fos-quality-strip">
      <div><span>Source coverage</span><strong>{quality.coveragePercent ?? 0}%</strong><small>{quality.citedConceptCount ?? 0}/{quality.conceptCount ?? 0} concepts cited · {quality.citedActivityCount ?? 0}/{quality.activityCount ?? 0} activities cited</small></div>
      <div><span>Difficulty</span><strong>{goal.currentLevel}</strong><small>{curriculum.difficultyExplanation || "Bounded practice increases toward transfer."}</small></div>
      <div><span>Trust state</span><strong>{String(curriculum.provenance?.providerMode || "deterministic_fallback").replaceAll("_", " ")}</strong><small>{curriculum.sourceFingerprint ? `Fingerprint ${curriculum.sourceFingerprint.slice(0, 12)}…` : "Source fingerprint unavailable"}</small></div>
    </div>
    <div className="fos-preview-grid">
      <div className="fos-preview-block"><div className="fos-preview-title"><span>CONCEPTS</span><small>{curriculum.concepts?.length || 0} cited</small></div>{curriculum.concepts?.map((concept) => <article className="fos-concept-preview" key={concept.key}><strong>{concept.title}</strong><p>{concept.description || "A bounded source concept to inspect and explain."}</p><div>{concept.sourceAnchorIds.map((anchor) => <span className="fos-citation-chip" key={anchor}>{anchor}</span>)}<span className="fos-uncertainty-chip">{String(concept.uncertainty?.level || "provisional")}</span></div></article>)}</div>
      <div className="fos-preview-block"><div className="fos-preview-title"><span>PREREQUISITE CHAIN</span><small>{curriculum.prerequisites?.length || 0} links</small></div>{curriculum.prerequisites?.length ? <ol className="fos-prereq-list">{curriculum.prerequisites.map((edge) => <li key={`${edge.prerequisite}-${edge.dependent}`}><strong>{edge.prerequisite}</strong><span>before</span><strong>{edge.dependent}</strong></li>)}</ol> : <p className="fos-empty-copy">No prerequisite link was inferred. The first activity will establish the boundary.</p>}<div className="fos-preview-safety"><span>SAFETY BOUNDARY</span><p>{curriculum.safetyBoundary || "Bounded learning only."}</p></div></div>
    </div>
    <div className="fos-preview-route"><div className="fos-preview-title"><span>ACTIVITY ROUTE · EDITABLE</span><small>{orderedActivities.length} observable tasks</small></div>{orderedActivities.length ? <ol>{orderedActivities.map((activity, index) => <li key={activity.activityId} className={activity.status === "completed" ? "completed" : ""}><span>{String(index + 1).padStart(2, "0")}</span><div><strong>{activity.title}</strong><small>{activity.type} · difficulty {activity.difficulty || 1}{activity.sourceAnchorIds?.length ? ` · ${activity.sourceAnchorIds.length} citation${activity.sourceAnchorIds.length === 1 ? "" : "s"}` : ""}</small></div><div className="fos-route-edit-actions"><button type="button" aria-label={`Move ${activity.title} up`} onClick={() => move(index, -1)} disabled={index === 0 || busy}>↑</button><button type="button" aria-label={`Move ${activity.title} down`} onClick={() => move(index, 1)} disabled={index === orderedActivities.length - 1 || busy}>↓</button></div></li>)}</ol> : <p className="fos-empty-copy">Compile a route to preview observable activities.</p>}</div>
    <div className="fos-preview-footer"><div><span className="fos-eyebrow">UNCERTAINTY</span><p>{String(curriculum.uncertainty?.reason || "This route is a provisional source-grounded proposal. Learner evidence must update confidence.")}</p>{quality.warnings?.map((warning) => <small key={warning}>{warning}</small>)}</div><div className="fos-preview-actions">{dirty ? <button type="button" className="fos-primary-action" onClick={() => void save({ activityOrder })} disabled={busy}>{busy ? "Saving route…" : "Save route correction"}</button> : null}{curriculum.preview?.approvalRequired && curriculum.preview.approvalState !== "approved" ? <button type="button" className="fos-quiet-action" onClick={() => void save({ approvalState: "approved" })} disabled={busy}>Approve curriculum</button> : null}{messageText ? <span role="status">{messageText}</span> : null}</div></div>
  </section>;
}

export function GoalOverviewView({ goalId }: { goalId: string }) {
  const [goalState, setGoal] = useState<LearningGoal | null>(null);
  const [curriculumState, setCurriculum] = useState<CurriculumSummary | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [sourceContexts, setSourceContexts] = useState<GoalSourceContext[]>([]);
  const [sourceError, setSourceError] = useState<unknown>(null);
  const [confirming, setConfirming] = useState(false);
  const [compiling, setCompiling] = useState(false);
  const [curriculumError, setCurriculumError] = useState<string | null>(null);
  const [shareMessage, setShareMessage] = useState("");
  const load = useCallback(async () => {
    setError(null); setSourceError(null); setGoal(null); setSourceContexts([]);
    try {
      const current = await learningOsApi.goal(goalId);
      setGoal(current);
      if (current.curriculum?.status === "ready") {
        try { setCurriculum((await learningOsApi.curriculum(goalId)).curriculum); } catch { setCurriculum(null); }
      } else {
        setCurriculum(null);
      }
      try { setSourceContexts((await learningOsApi.goalSources(goalId)).notebooks); } catch (caught) { setSourceError(caught); }
    } catch (caught) { setError(caught); }
  }, [goalId]);
  useEffect(() => { void load(); }, [load]);
  async function confirmContract() {
    if (!goalState) return;
    setConfirming(true);
    try { setGoal(await learningOsApi.updateGoal(goalState.goalId, { confirmContract: true })); } catch (caught) { setError(caught); } finally { setConfirming(false); }
  }
  async function compileCurriculum() {
    if (!goalState) return;
    const selectedSourceIds = sourceContexts.flatMap((context) => context.sources).filter((source) => source.status === "ready" && source.groundingEnabled !== false).map((source) => source.sourceId);
    if (!selectedSourceIds.length) { setCurriculumError("Attach at least one ready source before compiling a curriculum."); return; }
    setCompiling(true); setCurriculumError(null);
    try { const result = await learningOsApi.compileCurriculum(goalState.goalId, { sourceIds: selectedSourceIds, learnerLevel: goalState.currentLevel }); setCurriculum(result.curriculum); setGoal(result.goal); } catch (caught) { setCurriculumError(message(caught, "The curriculum could not be compiled.")); } finally { setCompiling(false); }
  }
  async function shareGoal() {
    if (!goalState) return;
    try {
      const result = await learningOsApi.createGoalShare(goalState.goalId);
      const shareUrl = `${window.location.origin}/share/goals/${result.token}`;
      await navigator.clipboard?.writeText(shareUrl);
      setShareMessage("Template link copied. It includes the route and source metadata, never private evidence.");
    } catch (caught) { setShareMessage(message(caught, "The learning route could not be shared.")); }
  }
  if (!goalState) return <LearningAppShell eyebrow="LEARNING GOAL" title="Goal"><RouteState title="learning goal" state={error ? "error" : "loading"} error={error} onRetry={() => void load()} /></LearningAppShell>;
  const goal = goalState;
  const activities = goal.activities || [];
  const evidence = goal.evidence || [];
  const sources = sourceContexts.flatMap((context) => context.sources);
  const readySources = sources.filter((source) => source.status === "ready" && source.groundingEnabled !== false);
  const failedSources = sources.filter((source) => source.status === "failed");
  const artifacts = sourceContexts.flatMap((context) => context.artifacts || []);
  const sourceDeskHref = `/sources?goal=${encodeURIComponent(goal.goalId)}` as never;
  return <LearningAppShell eyebrow="LEARNING GOAL" title={goal.title} actions={<><Link href={sourceDeskHref} className="fos-quiet-action">Edit sources</Link><button type="button" className="fos-quiet-action" onClick={() => void shareGoal()}>Share route</button><Link href={`/goals/${goal.goalId}/learn`} className="fos-primary-action">Start guide <FeynmanIcon name="arrow" /></Link></>}>
    <section className="fos-goal-header"><div><span className="fos-eyebrow">{formatStatus(goal.domain)} · {goal.currentLevel}</span><h1>{goal.title}</h1><p>{goal.description || goal.outcome}</p><div className="fos-goal-status-row"><StatusPill>{formatStatus(goal.status)}</StatusPill><span>{goal.timeBudget || "Flexible schedule"}</span><span>{goal.sourceMode === "required" ? "Source-backed verification required" : "Sources optional until verification"}</span><span>Category: {formatStatus(goal.category || goal.domain)}</span></div></div><div className="fos-goal-header-score"><span>EVIDENCE</span><strong>{goal.evidenceCount}</strong><small>observable attempts</small></div></section>
    {error ? <p className="fos-form-error">{message(error, "The contract could not be updated.")}</p> : null}
    {shareMessage ? <p className="fos-share-message" role="status">{shareMessage}</p> : null}
    {readySources.length ? <div className="fos-curriculum-action"><div><span className="fos-eyebrow">SOURCE-GROUNDED CURRICULUM</span><strong>{goal.curriculum?.status === "ready" ? `Curriculum v${goal.curriculum.version} · ${goal.curriculum.sourceAnchorIds.length} cited anchors` : "Compile a route from the selected ready sources."}</strong>{curriculumError ? <p className="fos-form-error">{curriculumError}</p> : null}</div><button type="button" className="fos-text-button" onClick={() => void compileCurriculum()} disabled={compiling}>{compiling ? "Compiling..." : goal.curriculum?.status === "ready" ? "Recompile" : "Compile curriculum"}</button></div> : null}
    {curriculumState?.status === "ready" ? <CurriculumPreview goal={goal} curriculum={curriculumState} onUpdated={(result) => { setCurriculum(result.curriculum); setGoal(result.goal); }} /> : null}
    <section className="fos-goal-overview-grid">
      <article className="fos-panel fos-contract-panel"><div className="fos-panel-title"><span><FeynmanIcon name="book" /> Learning contract</span>{goal.status === "contract_ready" ? <button type="button" className="fos-text-button" onClick={() => void confirmContract()} disabled={confirming}>{confirming ? "Confirming..." : "Confirm route"}</button> : <StatusPill>Confirmed</StatusPill>}</div><h2>{goal.contract.intendedCapability}</h2><p>{goal.contract.firstTask}</p><dl className="fos-contract-list"><div><dt>Starting point</dt><dd>{goal.contract.learnerStartingPoint}</dd></div><div><dt>Verification</dt><dd>{goal.contract.sourceRequirements}</dd></div><div><dt>Safety</dt><dd>{goal.contract.safetyMode}</dd></div></dl></article>
      <article className="fos-panel fos-path-panel"><div className="fos-panel-title"><span><FeynmanIcon name="spark" /> Route and prerequisites</span><span>{activities.length} tasks</span></div><div className="fos-missing-prereqs"><span>MISSING / TO PRACTICE</span>{goal.contract.prerequisites.length ? goal.contract.prerequisites.map((item) => <p key={item}><FeynmanIcon name="check" /> {item}</p>) : <p>No prerequisite has been recorded.</p>}</div>{activities.length ? <ol className="fos-capability-path">{activities.map((activity, index) => <li key={activity.activityId} className={activity.status === "completed" ? "completed" : index === 0 ? "current" : ""}><span>{String(index + 1).padStart(2, "0")}</span><div><strong>{activity.title}</strong><p>{activity.type} · {formatStatus(activity.status)}</p></div></li>)}</ol> : <p className="fos-empty-copy">Confirm this contract to retrieve its activity route.</p>}</article>
      <article className="fos-panel fos-source-coverage-panel"><div className="fos-panel-title"><span><FeynmanIcon name="source" /> Source coverage</span><Link href={sourceDeskHref}>Open Source Desk</Link></div>{sourceError ? <p className="fos-subtle-error">{message(sourceError, "Source coverage is unavailable. Retry from the Source Desk.")}</p> : <><div className="fos-source-coverage-summary"><strong>{readySources.length} ready for grounding</strong><small>{sources.length} attached source{sources.length === 1 ? "" : "s"}{failedSources.length ? ` · ${failedSources.length} need attention` : ""}</small></div>{sourceContexts.length ? <div className="fos-source-status-list">{sourceContexts.map((context) => <Link href={`/notebooks/${context.notebookId}`} key={context.notebookId}><span><strong>{context.title}</strong><small>{context.sources.length} source{context.sources.length === 1 ? "" : "s"} · {context.status.replaceAll("_", " ")}</small></span><StatusPill>{context.artifacts?.filter((artifact) => artifact.status === "ready").length || 0} outputs</StatusPill></Link>)}</div> : <p className="fos-empty-copy">Attach context before you need source-grounded answers or verified evidence.</p>}</>}</article>
      <article className="fos-panel fos-proof-panel"><div className="fos-panel-title"><span><FeynmanIcon name="proof" /> Evidence and next proof</span><Link href="/evidence">Evidence</Link></div><p className="fos-next-proof"><strong>Next best action</strong>{goal.nextAction}</p>{evidence.length ? evidence.slice(0, 2).map((item) => <div className="fos-proof-row" key={item.evidenceId}><div><strong>{item.capability}</strong><p>{item.summary}</p></div><StatusPill tone={stateTone(item.status)}>{formatStatus(item.status)}</StatusPill></div>) : <p className="fos-empty-copy">No learner state changes until you submit an observable attempt.</p>}{artifacts.length ? <small className="fos-artifact-count">{artifacts.filter((artifact) => artifact.status === "ready").length} current saved output{artifacts.filter((artifact) => artifact.status === "ready").length === 1 ? "" : "s"} in attached desks</small> : null}</article>
    </section>
  </LearningAppShell>;
  return <LearningAppShell eyebrow="LEARNING GOAL" title={goal.title} actions={<Link href={`/goals/${goal.goalId}/learn`} className="fos-primary-action">Continue <FeynmanIcon name="arrow" /></Link>}>
    <section className="fos-goal-header"><div><span className="fos-eyebrow">{formatStatus(goal.domain)} · {goal.currentLevel}</span><h1>{goal.title}</h1><p>{goal.description || goal.outcome}</p><div className="fos-goal-status-row"><StatusPill>{formatStatus(goal.status)}</StatusPill><span>{goal.timeBudget || "Flexible schedule"}</span><span>{goal.sourceMode === "required" ? "Source-backed verification required" : "Sources optional until verification"}</span></div></div><div className="fos-goal-header-score"><span>EVIDENCE</span><strong>{goal.evidenceCount}</strong><small>observable attempts</small></div></section>
    {error ? <p className="fos-form-error">{message(error, "The contract could not be updated.")}</p> : null}
    <section className="fos-goal-overview-grid"><article className="fos-panel fos-contract-panel"><div className="fos-panel-title"><span><FeynmanIcon name="book" /> Learning contract</span>{goal.status === "contract_ready" ? <button type="button" className="fos-text-button" onClick={() => void confirmContract()} disabled={confirming}>{confirming ? "Confirming..." : "Confirm route"}</button> : <StatusPill>Confirmed</StatusPill>}</div><h2>{goal.contract.intendedCapability}</h2><p>{goal.contract.firstTask}</p><dl className="fos-contract-list"><div><dt>Starting point</dt><dd>{goal.contract.learnerStartingPoint}</dd></div><div><dt>Prerequisites</dt><dd>{goal.contract.prerequisites.join(" · ")}</dd></div><div><dt>Verification</dt><dd>{goal.contract.sourceRequirements}</dd></div><div><dt>Safety</dt><dd>{goal.contract.safetyMode}</dd></div></dl></article>
      <article className="fos-panel fos-path-panel"><div className="fos-panel-title"><span><FeynmanIcon name="spark" /> Capability route</span><span>{activities.length} tasks</span></div>{activities.length ? <ol className="fos-capability-path">{activities.map((activity, index) => <li key={activity.activityId} className={activity.status === "completed" ? "completed" : index === 0 ? "current" : ""}><span>{String(index + 1).padStart(2, "0")}</span><div><strong>{activity.title}</strong><p>{activity.type} · {formatStatus(activity.status)}</p></div></li>)}</ol> : <p className="fos-empty-copy">Confirm this contract to retrieve its activity route.</p>}</article>
      <article className="fos-panel fos-proof-panel"><div className="fos-panel-title"><span><FeynmanIcon name="proof" /> Evidence state</span><Link href="/evidence">Evidence</Link></div>{evidence.length ? evidence.slice(0, 3).map((item) => <div className="fos-proof-row" key={item.evidenceId}><div><strong>{item.capability}</strong><p>{item.summary}</p></div><StatusPill tone={stateTone(item.status)}>{formatStatus(item.status)}</StatusPill></div>) : <p className="fos-empty-copy">No learner state changes until you submit an observable attempt.</p>}</article></section>
  </LearningAppShell>;
}

export function SharedGoalView({ token }: { token: string }) {
  const router = useRouter();
  const [share, setShare] = useState<import("@/lib/learningOsTypes").GoalShare | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { learningOsApi.sharedGoal(token).then(setShare).catch(setError); }, [token]);
  async function start() {
    setBusy(true); setError(null);
    try { const goal = await learningOsApi.cloneSharedGoal(token); router.replace(`/goals/${goal.goalId}`); }
    catch (caught) { if (isAuthenticationError(caught)) { router.push(`/login?next=${encodeURIComponent(`/share/goals/${token}`)}` as never); } else setError(caught); }
    finally { setBusy(false); }
  }
  if (!share) return <LearningAppShell eyebrow="SHARED ROUTE" title="Start guide"><RouteState title="shared route" state={error ? "error" : "loading"} error={error} onRetry={() => { setError(null); learningOsApi.sharedGoal(token).then(setShare).catch(setError); }} /></LearningAppShell>;
  return <LearningAppShell eyebrow="SHARED ROUTE" title="Start guide" compact><section className="fos-shared-goal-card fos-panel"><span className="fos-eyebrow">FRESH LEARNER COPY</span><h1>{share.title}</h1><p>{share.outcome || "A shared capability route ready for a fresh learner."}</p><div className="fos-goal-status-row"><StatusPill>{formatStatus(share.domain || "general")}</StatusPill><span>{share.currentLevel || "beginner"}</span><span>{share.activityCount || 0} observable tasks</span><span>{share.sourceCount || 0} source items attached</span></div>{share.sourceTitles?.length ? <div className="fos-shared-source-list"><strong>Included source desks</strong>{share.sourceTitles.map((title) => <span key={title}>{title}</span>)}</div> : null}<p>This creates your own goal, route, and source context. The original learner’s evidence and private memory stay private.</p><button type="button" className="fos-goal-submit" onClick={() => void start()} disabled={busy}>{busy ? "Preparing your guide…" : "Start this guide"}<FeynmanIcon name="arrow" /></button></section></LearningAppShell>;
}

export function LearningWorkspaceView({ goalId }: { goalId: string }) {
  const [goalState, setGoal] = useState<LearningGoal | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [activeIndex, setActiveIndex] = useState(0);
  const [response, setResponse] = useState("");
  const [learnerConclusion, setLearnerConclusion] = useState("");
  const [confidence, setConfidence] = useState<1 | 2 | 3 | 4 | 5>(3);
  const [anchorText, setAnchorText] = useState("");
  const [sourceSelection, setSourceSelection] = useState<{ sourceIds: string[]; sourceAnchorIds: string[] }>({ sourceIds: [], sourceAnchorIds: [] });
  const [sourceContexts, setSourceContexts] = useState<GoalSourceContext[]>([]);
  const [busy, setBusy] = useState(false);
  const [mobilePane, setMobilePane] = useState<"sources" | "evidence" | null>(null);
  const [providerFeedback, setProviderFeedback] = useState<ActivityProviderFeedback | null>(null);
  const [retryAttempt, setRetryAttempt] = useState<RetryableAttempt | null>(null);
  const [interactionState, setInteractionState] = useState<Record<string, unknown>>({});
  const routeActivityId = goalState?.route?.activeActivityId as string | undefined;
  const routeActivities = goalState?.activities;
  const activeActivityId = routeActivities?.[activeIndex]?.activityId;
  const load = useCallback(async () => { setError(null); setGoal(null); try { setGoal(await learningOsApi.goal(goalId)); } catch (caught) { setError(caught); } }, [goalId]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (!routeActivityId || !routeActivities) return;
    const routeIndex = routeActivities.findIndex((activity) => activity.activityId === routeActivityId);
    if (routeIndex >= 0) setActiveIndex(routeIndex);
  }, [routeActivityId, routeActivities]);
  useEffect(() => { setInteractionState({}); }, [activeActivityId]);
  if (!goalState) return <LearningAppShell eyebrow="ACTIVE PRACTICE" title="Learning workspace"><RouteState title="learning workspace" state={error ? "error" : "loading"} error={error} onRetry={() => void load()} /></LearningAppShell>;
  const goal = goalState;
  const currentGoal = goal;
  const activities = goal.activities || [];
  const activeActivity = activities[Math.min(activeIndex, Math.max(0, activities.length - 1))];
  const evidence = goal.evidence || [];
  const verifiedEvidence = evidence.filter((item) => item.status === "verified");
  const latestEvidence = evidence[0];
  const savedArtifacts = sourceContexts.flatMap((context) => (context.artifacts || []).map((artifact) => ({ ...artifact, notebookId: context.notebookId, notebookTitle: context.title }))).filter((artifact) => artifact.status === "ready");
  async function submit(event?: FormEvent, retry?: RetryableAttempt) {
    event?.preventDefault();
    if (!retry && (!activeActivity || (response.trim().length < 24 && Object.keys(interactionState).length === 0))) { setError(new Error("Make a concrete attempt or interact with the activity before submitting evidence.")); return; }
    setBusy(true); setError(null);
    try {
      const typedAnchorIds = anchorText.split(/[,\n]/).map((value) => value.trim()).filter(Boolean);
      const sourceAnchorIds = [...new Set([...sourceSelection.sourceAnchorIds, ...typedAnchorIds])];
      const attempt = retry || {
        activityId: activeActivity!.activityId,
        response: response.trim(),
        writtenExplanation: response.trim(),
        learnerConclusion: learnerConclusion.trim() || undefined,
        confidence,
        interactionState: Object.keys(interactionState).length ? interactionState : undefined,
        simulationParameters: Object.keys(interactionState).length ? interactionState : undefined,
        ...(Array.isArray(interactionState.trace) ? { trace: interactionState.trace } : {}),
        ...(sourceSelection.sourceIds.length ? { sourceIds: sourceSelection.sourceIds } : {}),
        ...(sourceAnchorIds.length ? { sourceAnchorIds } : {}),
      } satisfies StructuredActivityAttempt;
      const result = await learningOsApi.submitAttempt(currentGoal.goalId, attempt);
      setGoal(result.goal); setResponse(""); setLearnerConclusion(""); setConfidence(3); setAnchorText("");
      setProviderFeedback(result.feedback || null);
      setRetryAttempt(result.feedback?.retryAvailable ? attempt : null);
      const nextActivityId = result.adaptiveRoute?.activeActivityId || (result.goal.route?.activeActivityId as string | undefined);
      setActiveIndex((current) => {
        const nextIndex = nextActivityId ? (result.goal.activities || []).findIndex((item) => item.activityId === nextActivityId) : -1;
        if (nextIndex >= 0) return nextIndex;
        return !result.feedback?.retryAvailable && current < (result.goal.activities || []).length - 1 ? current + 1 : current;
      });
    } catch (caught) { setError(caught); } finally { setBusy(false); }
  }
  return <LearningAppShell eyebrow="ACTIVE PRACTICE" title={goal.title} actions={<><button type="button" className="fos-quiet-action fos-pane-toggle" onClick={() => setMobilePane("sources")}><FeynmanIcon name="source" /> Sources</button><button type="button" className="fos-quiet-action fos-pane-toggle" onClick={() => setMobilePane("evidence")}><FeynmanIcon name="proof" /> Evidence</button></>}>
    <section className="fos-learning-workspace">
      <GoalSourceDock goal={goal} mobileOpen={mobilePane === "sources"} onClose={() => setMobilePane(null)} onEvidenceSelectionChange={setSourceSelection} onSourceContextsChange={setSourceContexts} />
      <section className="fos-activity-canvas"><header className="fos-activity-head"><div><span className="fos-eyebrow">TASK {String(Math.min(activeIndex + 1, Math.max(1, activities.length))).padStart(2, "0")} / {String(activities.length).padStart(2, "0")}</span><h1>{activeActivity?.title || "No task is ready yet"}</h1></div>{activeActivity ? <StatusPill>{activeActivity.type}</StatusPill> : null}</header>{activities.length ? <div className="fos-activity-progress">{activities.map((activity, index) => <button key={activity.activityId} type="button" className={`${index === activeIndex ? "active" : ""} ${activity.status === "completed" ? "complete" : ""}`} onClick={() => setActiveIndex(index)} aria-label={`Open task ${index + 1}: ${activity.title}`}><span>{activity.status === "completed" ? <FeynmanIcon name="check" size={12} /> : index + 1}</span><i /></button>)}</div> : null}{activeActivity ? <form className="fos-activity-card" onSubmit={(event) => void submit(event)}><div className="fos-activity-type"><FeynmanIcon name={activityIcon(activeActivity.type)} size={20} /><span>{activeActivity.type} before answer</span></div><h2>{activeActivity.prompt}</h2><p>State a concrete case, show your reasoning, and name uncertainty. A fluent generated answer is not evidence.</p><DomainActivityWorkbench domain={goal.domain} goalTitle={goal.title} activityType={activeActivity.type} configuration={activeActivity.configuration} onInteractionChange={setInteractionState} /><label className="fos-field"><span>Your observable attempt</span><textarea value={response} onChange={(event) => setResponse(event.target.value)} rows={8} maxLength={12000} placeholder="Write the reasoning you could defend to a peer..." /></label><label className="fos-field"><span>Learner conclusion</span><textarea value={learnerConclusion} onChange={(event) => setLearnerConclusion(event.target.value)} rows={3} maxLength={4000} placeholder="State what the observed result means and what remains uncertain..." /></label><label className="fos-field"><span>Confidence before feedback</span><select value={confidence} onChange={(event) => setConfidence(Number(event.target.value) as 1 | 2 | 3 | 4 | 5)}><option value={1}>1 — guessing</option><option value={2}>2 — tentative</option><option value={3}>3 — mixed</option><option value={4}>4 — confident</option><option value={5}>5 — very confident</option></select></label>{activeActivity.evaluator.requiresSource ? <label className="fos-field"><span>Source anchors required for verification</span><input value={anchorText} onChange={(event) => setAnchorText(event.target.value)} placeholder="Select durable page or block anchors from the Source Dock" /></label> : null}{error ? <p className="fos-form-error" role="alert">{message(error, "The attempt could not be recorded.")}</p> : null}<div className="fos-activity-actions"><span>{activeActivity.evaluator.requiresSource ? "Verified evidence needs a selected ready source, a durable anchor, and a meaningful response." : "A meaningful response becomes observed evidence; it is not a mastery score."}</span><button type="submit" className="fos-goal-submit" disabled={busy}>{busy ? "Saving attempt..." : "Submit evidence"}<FeynmanIcon name="arrow" /></button></div></form> : <RouteState title="active task" state="empty" action={<Link href={`/goals/${goal.goalId}`} className="fos-primary-action">Return to contract</Link>} />}</section>
      <aside className={`fos-evidence-rail ${mobilePane === "evidence" ? "mobile-open" : ""}`} aria-label="Evidence rail"><div className="fos-workspace-panel-head"><span>Evidence</span><button type="button" onClick={() => setMobilePane(null)} aria-label="Close evidence rail"><FeynmanIcon name="close" /></button></div><div className="fos-evidence-rail-body"><div className="fos-evidence-summary"><span>LEARNER STATE</span><strong>{verifiedEvidence.length} verified</strong><p>{evidence.length} observable attempt{evidence.length === 1 ? "" : "s"}</p></div><div className="fos-next-action"><span>NEXT BEST ACTION</span><p>{goal.nextAction}</p></div><div className="fos-evaluator-summary"><span>EVALUATOR / RUBRIC</span>{activeActivity ? <><strong>{activeActivity.evaluator.mode?.replaceAll("_", " ") || "Observed response"}</strong><small>{activeActivity.evaluator.requiresSource ? "Requires a selected ready source and durable anchor." : "Records a meaningful response before changing learner state."}</small><small>Minimum response: {activeActivity.evaluator.minimumResponseCharacters || 24} characters</small></> : <small>No active evaluator is available until the contract has a task.</small>}</div><div className="fos-source-verification"><span>SOURCE VERIFICATION</span>{latestEvidence ? <><StatusPill tone={stateTone(latestEvidence.status)}>{formatStatus(latestEvidence.status)}</StatusPill><small>{latestEvidence.sourceAnchorIds.length ? `${latestEvidence.sourceAnchorIds.length} durable anchor${latestEvidence.sourceAnchorIds.length === 1 ? "" : "s"} recorded` : "Observed only; no source anchors recorded."}</small></> : <small>No submitted evidence yet.</small>}</div><div className="fos-evidence-rail-list">{evidence.length ? evidence.slice(0, 3).map((item) => <div className="fos-evidence-rail-item" key={item.evidenceId}><StatusPill tone={stateTone(item.status)}>{formatStatus(item.status)}</StatusPill><strong>{item.capability}</strong><small>{item.summary}</small></div>) : <div className="fos-source-empty"><FeynmanIcon name="proof" /><strong>No evidence yet</strong><small>Submit the active task to record the first attempt.</small></div>}</div><div className="fos-saved-artifacts"><span>SAVED ARTIFACTS</span>{savedArtifacts.length ? savedArtifacts.slice(0, 3).map((artifact) => <Link href={`/notebooks/${artifact.notebookId}`} key={artifact.artifactId}><strong>{artifact.title}</strong><small>{artifact.notebookTitle} · {artifact.type.replaceAll("_", " ")}</small></Link>) : <small>Studio outputs from attached contexts will appear here.</small>}</div><Link href="/evidence" className="fos-rail-link">Open evidence timeline <FeynmanIcon name="arrow" /></Link></div></aside>
    </section>
    {providerFeedback ? <ProviderFeedbackPanel feedback={providerFeedback} retryAttempt={retryAttempt} busy={busy} nextAction={goal.nextAction} onRetry={() => void submit(undefined, retryAttempt || undefined)} /> : null}
  </LearningAppShell>;
  return <LearningAppShell eyebrow="ACTIVE PRACTICE" title={goal.title} actions={<><button type="button" className="fos-quiet-action fos-pane-toggle" onClick={() => setMobilePane("sources")}><FeynmanIcon name="source" /> Sources</button><button type="button" className="fos-quiet-action fos-pane-toggle" onClick={() => setMobilePane("evidence")}><FeynmanIcon name="proof" /> Evidence</button></>}>
    <section className="fos-learning-workspace">
      <GoalSourceDock goal={goal} mobileOpen={mobilePane === "sources"} onClose={() => setMobilePane(null)} onEvidenceSelectionChange={setSourceSelection} />
      <section className="fos-activity-canvas"><header className="fos-activity-head"><div><span className="fos-eyebrow">TASK {String(Math.min(activeIndex + 1, Math.max(1, activities.length))).padStart(2, "0")} / {String(activities.length).padStart(2, "0")}</span><h1>{activeActivity?.title || "No task is ready yet"}</h1></div>{activeActivity ? <StatusPill>{activeActivity.type}</StatusPill> : null}</header>{activities.length ? <div className="fos-activity-progress">{activities.map((activity, index) => <button key={activity.activityId} type="button" className={`${index === activeIndex ? "active" : ""} ${activity.status === "completed" ? "complete" : ""}`} onClick={() => setActiveIndex(index)} aria-label={`Open task ${index + 1}: ${activity.title}`}><span>{activity.status === "completed" ? <FeynmanIcon name="check" size={12} /> : index + 1}</span><i /></button>)}</div> : null}{activeActivity ? <form className="fos-activity-card" onSubmit={(event) => void submit(event)}><div className="fos-activity-type"><FeynmanIcon name={activityIcon(activeActivity.type)} size={20} /><span>{activeActivity.type} before answer</span></div><h2>{activeActivity.prompt}</h2><p>State a concrete case, show your reasoning, and name uncertainty. A fluent generated answer is not evidence.</p><DomainActivityWorkbench domain={goal.domain} goalTitle={goal.title} activityType={activeActivity.type} /><label className="fos-field"><span>Your observable attempt</span><textarea value={response} onChange={(event) => setResponse(event.target.value)} rows={8} maxLength={12000} placeholder="Write the reasoning you could defend to a peer..." /></label>{activeActivity.evaluator.requiresSource ? <label className="fos-field"><span>Source anchors required for verification</span><input value={anchorText} onChange={(event) => setAnchorText(event.target.value)} placeholder="Paste page or block anchor IDs from the attached Source Desk" /></label> : null}{error ? <p className="fos-form-error" role="alert">{message(error, "The attempt could not be recorded.")}</p> : null}<div className="fos-activity-actions"><span>{activeActivity.evaluator.requiresSource ? "Verified evidence needs a supported source anchor and meaningful response." : "A meaningful response becomes observed evidence; it is not a mastery score."}</span><button type="submit" className="fos-goal-submit" disabled={busy}>{busy ? "Saving attempt..." : "Submit evidence"}<FeynmanIcon name="arrow" /></button></div></form> : <RouteState title="active task" state="empty" action={<Link href={`/goals/${goal.goalId}`} className="fos-primary-action">Return to contract</Link>} />}</section>
      <aside className={`fos-evidence-rail ${mobilePane === "evidence" ? "mobile-open" : ""}`} aria-label="Evidence rail"><div className="fos-workspace-panel-head"><span>Evidence</span><button type="button" onClick={() => setMobilePane(null)} aria-label="Close evidence rail"><FeynmanIcon name="close" /></button></div><div className="fos-evidence-rail-body"><div className="fos-evidence-summary"><span>LEARNER STATE</span><strong>{evidence.filter((item) => item.status === "verified").length} verified</strong><p>{evidence.length} observable attempt{evidence.length === 1 ? "" : "s"}</p></div><div className="fos-next-action"><span>NEXT BEST ACTION</span><p>{goal.nextAction}</p></div><div className="fos-evidence-rail-list">{evidence.length ? evidence.slice(0, 4).map((item) => <div className="fos-evidence-rail-item" key={item.evidenceId}><StatusPill tone={stateTone(item.status)}>{formatStatus(item.status)}</StatusPill><strong>{item.capability}</strong><small>{item.summary}</small></div>) : <div className="fos-source-empty"><FeynmanIcon name="proof" /><strong>No evidence yet</strong><small>Submit the active task to record the first attempt.</small></div>}</div><Link href="/evidence" className="fos-rail-link">Open evidence timeline <FeynmanIcon name="arrow" /></Link></div></aside>
    </section>
    {providerFeedback ? <ProviderFeedbackPanel feedback={providerFeedback!} retryAttempt={retryAttempt} busy={busy} nextAction={goal.nextAction} onRetry={() => void submit(undefined, retryAttempt || undefined)} /> : null}
  </LearningAppShell>;
}

function ProviderFeedbackPanel({ feedback, retryAttempt, busy, nextAction, onRetry }: { feedback: ActivityProviderFeedback; retryAttempt: RetryableAttempt | null; busy: boolean; nextAction: string; onRetry: () => void }) {
  const evaluation = feedback.evaluation;
  const completed = feedback.providerAttempt === "completed";
  const needsSource = feedback.providerAttempt === "skipped_no_selected_source";
  const title = completed ? "Provider feedback" : needsSource ? "Feedback needs selected source context" : feedback.providerAttempt === "not_configured" ? "Feedback provider not configured" : "Feedback provider unavailable";
  const body = completed
    ? evaluation?.feedback || evaluation?.remediation || "The provider evaluated this observable response."
    : "Your observable attempt was recorded, but this provider attempt did not verify it. No provider-generated feedback is being substituted.";
  const anchors = feedback.sourceAnchorIds.length || evaluation?.sourceAnchorIds?.length || 0;
  return <section className={`fos-provider-feedback ${completed ? "completed" : "unavailable"}`} role={completed ? "status" : "alert"}>
    <div><span className="fos-eyebrow">SERVER-SIDE EVALUATION</span><h2>{title}</h2><p>{body}</p><small>{feedback.provider}{feedback.model ? ` · ${feedback.model}` : ""} · {anchors} source anchor{anchors === 1 ? "" : "s"}{feedback.uncertainty ? ` · ${feedback.uncertainty} uncertainty` : ""}</small>{feedback.providerErrorCategory ? <small>Failure category: {feedback.providerErrorCategory}</small> : null}</div>
    <div className="fos-provider-feedback-actions">{feedback.retryAvailable && retryAttempt ? <button type="button" className="fos-primary-action" onClick={onRetry} disabled={busy}>{busy ? "Retrying feedback..." : "Retry feedback"}</button> : null}<p><strong>Next best action</strong>{evaluation?.nextAction || nextAction}</p></div>
  </section>;
}

export function EvidenceView() {
  const searchParams = useSearchParams();
  const [data, setData] = useState<{ evidence: EvidenceRecord[]; courses: Course[]; shares: ShareGrant[]; goals: LearningGoal[] } | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [courseId, setCourseId] = useState("");
  const [messageText, setMessageText] = useState("");
  const [goalFilter, setGoalFilter] = useState(searchParams.get("goalId") || "all");
  const load = useCallback(async () => { setData(null); setError(null); try { const [evidence, courses, shares, goals] = await Promise.all([learningOsApi.evidence(), learningOsApi.courses(), learningOsApi.shares(), learningOsApi.goals()]); setData({ evidence: evidence.evidence, courses: courses.courses, shares: shares.shares, goals: goals.goals }); } catch (caught) { setError(caught); } }, []);
  useEffect(() => { void load(); }, [load]);
  async function share() { if (!data || !courseId || !selected.length) { setMessageText("Choose a course and at least one evidence record."); return; } try { const grant = await learningOsApi.createShare({ courseId, evidenceIds: selected }); setData({ ...data, shares: [grant, ...data.shares] }); setSelected([]); setMessageText("The selected evidence is shared. You can revoke access immediately in Privacy."); } catch (caught) { setMessageText(message(caught, "The evidence could not be shared.")); } }
  if (!data) return <LearningAppShell eyebrow="LEARNER EVIDENCE" title="Evidence"><RouteState title="evidence" state={error ? "error" : "loading"} error={error} onRetry={() => void load()} /></LearningAppShell>;
  const visibleEvidence = goalFilter === "all" ? data.evidence : data.evidence.filter((item) => item.goalId === goalFilter);
  return <LearningAppShell eyebrow="LEARNER EVIDENCE" title="What you have demonstrated"><SectionHeading eyebrow="NOT A GRADEBOOK" title="Keep the trail; own the meaning." copy="Evidence is grouped by the goal and category that produced it. Courses only see records you explicitly share." action={<label className="fos-evidence-filter"><span>Goal</span><select value={goalFilter} onChange={(event) => setGoalFilter(event.target.value)}><option value="all">All goals</option>{data.goals.map((goal) => <option key={goal.goalId} value={goal.goalId}>{goal.title}</option>)}</select></label>} /><section className="fos-evidence-page-grid"><article className="fos-panel fos-evidence-timeline"><div className="fos-panel-title"><span><FeynmanIcon name="proof" /> Evidence timeline</span><span>{visibleEvidence.length} records</span></div>{visibleEvidence.length ? visibleEvidence.map((item) => <label key={item.evidenceId} className={`fos-evidence-card ${selected.includes(item.evidenceId) ? "selected" : ""}`}><input type="checkbox" checked={selected.includes(item.evidenceId)} onChange={() => setSelected((current) => current.includes(item.evidenceId) ? current.filter((id) => id !== item.evidenceId) : [...current, item.evidenceId])} /><div><div className="fos-evidence-card-top"><strong>{item.capability}</strong><StatusPill tone={stateTone(item.status)}>{formatStatus(item.status)}</StatusPill></div><p>{item.goalTitle ? `${item.goalTitle} · ${formatStatus(item.goalCategory || "general")}` : "Goal evidence"}</p><p>{item.summary}</p><small>{item.sourceAnchorIds.length ? `${item.sourceAnchorIds.length} source anchors` : "Observed only - no source anchors"}</small></div></label>) : <p className="fos-empty-copy">No evidence matches this goal yet.</p>}</article><aside className="fos-share-panel"><span className="fos-eyebrow">EXPLICIT COURSE SHARING</span><h2>Share selected evidence</h2><p>Instructors cannot browse private notebooks, raw chats, or unrelated learner memory.</p><label className="fos-field"><span>Course</span><select value={courseId} onChange={(event) => setCourseId(event.target.value)}><option value="">Choose a course</option>{data.courses.map((course) => <option key={course.courseId} value={course.courseId}>{course.title}</option>)}</select></label><button type="button" className="fos-goal-submit" onClick={() => void share()}>Share selected evidence <FeynmanIcon name="arrow" /></button>{messageText ? <p className="fos-share-message">{messageText}</p> : null}<div className="fos-share-history"><span>ACTIVE SHARES</span>{data.shares.filter((share) => share.active).length ? data.shares.filter((share) => share.active).map((share) => <div key={share.shareId}><strong>{share.courseTitle || "Course"}</strong><small>{share.evidenceIds.length} evidence record{share.evidenceIds.length === 1 ? "" : "s"}</small></div>) : <p>No active evidence shares.</p>}</div></aside></section></LearningAppShell>;
}

export function PrivacyView() {
  const [data, setData] = useState<{ memoryEnabled: boolean; courseSharingEnabled: boolean; retention: string; shares: ShareGrant[] } | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [messageText, setMessageText] = useState("");
  const load = useCallback(async () => { setData(null); setError(null); try { const [privacy, shares] = await Promise.all([learningOsApi.privacy(), learningOsApi.shares()]); setData({ memoryEnabled: privacy.learnerMemoryEnabled, courseSharingEnabled: privacy.courseSharingEnabled, retention: privacy.notebookSourceRetention, shares: shares.shares }); } catch (caught) { setError(caught); } }, []);
  useEffect(() => { void load(); }, [load]);
  async function toggleMemory() { if (!data) return; const next = !data.memoryEnabled; setData({ ...data, memoryEnabled: next }); try { await learningOsApi.updatePrivacy({ learnerMemoryEnabled: next }); setMessageText(next ? "Learner memory enabled." : "Learner memory disabled."); } catch (caught) { setData({ ...data, memoryEnabled: !next }); setMessageText(message(caught, "The privacy setting could not be updated.")); } }
  async function toggleCourseSharing() { if (!data) return; const next = !data.courseSharingEnabled; const previousShares = data.shares; setData({ ...data, courseSharingEnabled: next, shares: next ? data.shares : data.shares.map((share) => ({ ...share, active: false })) }); try { const updated = await learningOsApi.updatePrivacy({ courseSharingEnabled: next }); setData((current) => current ? { ...current, courseSharingEnabled: updated.courseSharingEnabled } : current); setMessageText(next ? "Course sharing is enabled. You still choose every evidence grant." : "Course sharing is disabled and every active instructor grant was revoked."); } catch (caught) { setData({ ...data, shares: previousShares }); setMessageText(message(caught, "The course sharing setting could not be updated.")); } }
  async function revoke(shareId: string) { if (!data) return; try { await learningOsApi.revokeShare(shareId); setData({ ...data, shares: data.shares.map((share) => share.shareId === shareId ? { ...share, active: false } : share) }); setMessageText("Access was revoked immediately."); } catch (caught) { setMessageText(message(caught, "The evidence share could not be revoked.")); } }
  if (!data) return <LearningAppShell eyebrow="PRIVACY" title="Your learning data"><RouteState title="privacy controls" state={error ? "error" : "loading"} error={error} onRetry={() => void load()} /></LearningAppShell>;
  return <LearningAppShell eyebrow="PRIVACY" title="Your learning data">
    <SectionHeading eyebrow="LEARNER-OWNED CONTROL" title="Separate what you know from what you share." copy="Notebook source context, learner evidence, and course sharing are separate stores." />
    <section className="fos-privacy-grid">
      <article className="fos-panel fos-privacy-card"><span className="fos-eyebrow">NOTEBOOK SOURCE MEMORY</span><h2>Source-bounded and removable</h2><p>{data.retention}</p><Link href="/sources" className="fos-quiet-action">Open Source Desk <FeynmanIcon name="arrow" /></Link></article>
      <article className="fos-panel fos-privacy-card"><span className="fos-eyebrow">LEARNER MEMORY</span><h2>Use observable state across goals</h2><p>Only learner state and evidence can influence a next action. Raw notebook text is not copied into learner memory.</p><label className="fos-switch"><input type="checkbox" checked={data.memoryEnabled} onChange={() => void toggleMemory()} /><span /><strong>{data.memoryEnabled ? "Enabled with consent" : "Disabled"}</strong></label></article>
      <article className="fos-panel fos-privacy-card"><span className="fos-eyebrow">COURSE / INSTRUCTOR SHARING</span><h2>Grant by grant, never by default</h2><p>When disabled, Feynman revokes every active course evidence grant immediately. Private notebooks and raw chats are never shared either way.</p><label className="fos-switch"><input type="checkbox" checked={data.courseSharingEnabled} onChange={() => void toggleCourseSharing()} /><span /><strong>{data.courseSharingEnabled ? "Ready for explicit grants" : "All course sharing disabled"}</strong></label></article>
      <article className="fos-panel fos-privacy-card fos-privacy-wide"><div className="fos-panel-title"><span><FeynmanIcon name="people" /> Course evidence shares</span><StatusPill>{data.courseSharingEnabled ? "Revocable" : "Sharing disabled"}</StatusPill></div>{data.shares.length ? data.shares.map((share) => <div key={share.shareId} className="fos-share-row"><div><strong>{share.courseTitle || "Course evidence"}</strong><p>{share.evidenceIds.length} selected record{share.evidenceIds.length === 1 ? "" : "s"} · {formatStatus(share.scope)}</p></div>{share.active ? <button type="button" className="fos-danger-link" onClick={() => void revoke(share.shareId)}>Revoke access</button> : <StatusPill>Revoked</StatusPill>}</div>) : <p className="fos-empty-copy">You have not shared evidence with a course.</p>}</article>
    </section>
    {messageText ? <p className="fos-share-message">{messageText}</p> : null}
  </LearningAppShell>;
}

function CoursesListViewLegacy() {
  const [courses, setCourses] = useState<Course[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const load = useCallback(async () => { setCourses(null); setError(null); try { setCourses((await learningOsApi.courses()).courses); } catch (caught) { setError(caught); } }, []);
  useEffect(() => { void load(); }, [load]);
  if (!courses) return <LearningAppShell eyebrow="COURSES" title="Courses"><RouteState title="courses" state={error ? "error" : "loading"} error={error} onRetry={() => void load()} /></LearningAppShell>;
  return <LearningAppShell eyebrow="COURSES" title="Course spaces"><SectionHeading eyebrow="SHARED STRUCTURE" title="Courses preserve learner boundaries." copy="Course staff can only see evidence a learner shares to that course." />{courses.length ? <section className="fos-course-list">{courses.map((course) => <Link href={`/courses/${course.courseId}`} key={course.courseId} className="fos-panel fos-course-list-item"><div><span className="fos-eyebrow">{formatStatus(course.status)}</span><h2>{course.title}</h2><p>{course.description}</p><small>{course.learnerCount} learners · {course.sourcePackCount} source packs</small></div><FeynmanIcon name="arrow" /></Link>)}</section> : <RouteState title="courses" state="empty" action={<Link href="/institution/courses" className="fos-primary-action">Create or join a course</Link>} />}</LearningAppShell>;
}

function JoinCourseForm({ className = "" }: { className?: string }) {
  const router = useRouter();
  const [joinCode, setJoinCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [messageText, setMessageText] = useState("");

  async function join(event: FormEvent) {
    event.preventDefault();
    if (!joinCode.trim()) { setMessageText("Enter the course join code."); return; }
    setBusy(true);
    setMessageText("");
    try {
      const result = await learningOsApi.joinCourse(joinCode.trim());
      router.push(`/courses/${result.course.courseId}`);
    } catch (caught) {
      setMessageText(message(caught, "The course could not be joined."));
    } finally {
      setBusy(false);
    }
  }

  return <form className={`fos-course-join ${className}`} onSubmit={(event) => void join(event)}>
    <span>JOIN A COURSE</span>
    <input value={joinCode} onChange={(event) => setJoinCode(event.target.value.toUpperCase())} placeholder="Join code" maxLength={24} autoComplete="off" />
    <button type="submit" disabled={busy}>{busy ? "Joining..." : "Join"}</button>
    {messageText ? <p className="fos-share-message" role="alert">{messageText}</p> : null}
  </form>;
}

export function CoursesListView() {
  const [courses, setCourses] = useState<Course[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const load = useCallback(async () => {
    setCourses(null);
    setError(null);
    try { setCourses((await learningOsApi.courses()).courses); } catch (caught) { setError(caught); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  return <LearningAppShell eyebrow="COURSES" title="Course spaces">
    <SectionHeading eyebrow="SHARED STRUCTURE" title="Courses preserve learner boundaries." copy="Course staff can only see evidence a learner shares to that course." />
    <section className="fos-course-directory">
      <JoinCourseForm className="fos-course-join-standalone" />
      {!courses ? <RouteState title="courses" state={error ? "error" : "loading"} error={error} onRetry={() => void load()} /> : courses.length ? <section className="fos-course-list">{courses.map((course) => <Link href={`/courses/${course.courseId}`} key={course.courseId} className="fos-panel fos-course-list-item"><div><span className="fos-eyebrow">{formatStatus(course.status)}</span><h2>{course.title}</h2><p>{course.description}</p><small>{course.learnerCount} learners / {course.sourcePackCount} source packs</small></div><FeynmanIcon name="arrow" /></Link>)}</section> : <RouteState title="courses" state="empty" action={<Link href="/institution/courses" className="fos-primary-action">Create an institution workspace or course</Link>} />}
    </section>
  </LearningAppShell>;
}

export function CourseHubView({ courseId }: { courseId: string }) {
  const [course, setCourse] = useState<Course | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [joinCode, setJoinCode] = useState("");
  const [messageText, setMessageText] = useState("");
  const load = useCallback(async () => { setCourse(null); setError(null); try { setCourse(await learningOsApi.course(courseId)); } catch (caught) { setError(caught); } }, [courseId]);
  useEffect(() => { void load(); }, [load]);
  async function join() { try { const result = await learningOsApi.joinCourse(joinCode); setCourse(result.course); setError(null); setMessageText("You are enrolled. Your private context remains private."); } catch (caught) { setMessageText(message(caught, "The course could not be joined.")); } }
  if (!course && error instanceof LearningOsApiError && error.status === 403) return <LearningAppShell eyebrow="COURSE SPACE" title="Course access"><SectionHeading eyebrow="JOIN REQUIRED" title="Enter the course code to continue." copy="Course details stay private until you enroll. Your private notebooks and learner state remain outside the course." /><JoinCourseForm className="fos-course-join-standalone" /></LearningAppShell>;
  if (!course) return <LearningAppShell eyebrow="COURSE SPACE" title="Course"><RouteState title="course" state={error ? "error" : "loading"} error={error} onRetry={() => void load()} /></LearningAppShell>;
  const stages = Array.isArray(course.route?.stages) ? course.route.stages as string[] : [];
  return <LearningAppShell eyebrow="COURSE SPACE" title={course.title} actions={<Link href={`/goals/new?course=${course.courseId}`} className="fos-primary-action">Add personal goal <FeynmanIcon name="plus" /></Link>}><section className="fos-course-hero"><div><span className="fos-eyebrow">INSTRUCTOR · {course.instructor}</span><h1>{course.title}</h1><p>{course.description}</p><div><StatusPill>{course.enrollmentStatus || formatStatus(course.status)}</StatusPill><span>{course.learnerCount} learners</span><span>{course.sourcePackCount} source packs</span></div></div><div className="fos-course-join"><span>JOIN A COURSE</span><input value={joinCode} onChange={(event) => setJoinCode(event.target.value.toUpperCase())} placeholder="Join code" maxLength={24} /><button type="button" onClick={() => void join()}>Join</button></div></section>{messageText ? <p className="fos-share-message">{messageText}</p> : null}<section className="fos-course-grid"><article className="fos-panel"><div className="fos-panel-title"><span><FeynmanIcon name="spark" /> Course route</span></div>{stages.length ? <ol className="fos-course-route">{stages.map((stage, index) => <li key={`${stage}-${index}`}><span>{String(index + 1).padStart(2, "0")}</span><strong>{stage}</strong><small>{index === 0 ? "Make an independent prediction" : "Create learner-owned evidence"}</small></li>)}</ol> : <p className="fos-empty-copy">This course has not published a learning route.</p>}</article><article className="fos-panel"><div className="fos-panel-title"><span><FeynmanIcon name="source" /> Approved materials</span><Link href="/sources">Source Desk</Link></div>{course.sourcePacks?.length ? <div className="fos-course-materials">{course.sourcePacks.map((source) => <div key={source.sourcePackId}><span><strong>{source.title}</strong><small>{source.description || "Approved course material"}</small></span><StatusPill>{source.approved ? "approved" : "review"}</StatusPill></div>)}</div> : <p className="fos-empty-copy">No approved course source packs yet.</p>}</article><article className="fos-panel"><h2>Private by default</h2><p>Course staff only see selected evidence you share. They never see private notebook sources or raw chat.</p><Link href="/settings/privacy" className="fos-quiet-action">Manage sharing <FeynmanIcon name="arrow" /></Link></article></section></LearningAppShell>;
}

export function TeachHomeView() {
  const [data, setData] = useState<{ courses: Course[]; pendingReviews: number; sourceApprovalNeeded: number } | null>(null);
  const [error, setError] = useState<unknown>(null);
  const load = useCallback(async () => { setData(null); setError(null); try { setData(await learningOsApi.teachDashboard()); } catch (caught) { setError(caught); } }, []);
  useEffect(() => { void load(); }, [load]);
  if (!data) return <LearningAppShell eyebrow="TEACHING SPACE" title="Instructor home"><RouteState title="teaching workspace" state={error ? "error" : "loading"} error={error} onRetry={() => void load()} /></LearningAppShell>;
  return <LearningAppShell eyebrow="TEACHING SPACE" title="Instructor home" actions={<Link href="/institution/courses" className="fos-primary-action">New course <FeynmanIcon name="plus" /></Link>}><SectionHeading eyebrow="INSTRUCTOR VIEW" title="Teach from shared evidence, not surveillance." copy="Only course-scoped, learner-shared evidence appears in a cohort." /><section className="fos-teach-metrics"><article><span>COURSES</span><strong>{data.courses.length}</strong><small>you can manage</small></article><article><span>HUMAN REVIEW</span><strong>{data.pendingReviews}</strong><small>shared attempts needing review</small></article><article><span>SOURCE GOVERNANCE</span><strong>{data.sourceApprovalNeeded}</strong><small>packs needing review</small></article></section><section className="fos-panel fos-teach-course-list"><div className="fos-panel-title"><span><FeynmanIcon name="course" /> Your courses</span><Link href="/institution/courses">All courses</Link></div>{data.courses.length ? data.courses.map((course) => <Link href={`/teach/courses/${course.courseId}`} className="fos-teach-course-row" key={course.courseId}><div><strong>{course.title}</strong><p>{course.learnerCount} learners · {course.sourcePackCount} source packs</p></div><StatusPill>{formatStatus(course.status)}</StatusPill></Link>) : <p className="fos-empty-copy">No instructor courses are available in this workspace.</p>}</section></LearningAppShell>;
}

export function CourseCommandView({ courseId }: { courseId: string }) {
  const [course, setCourse] = useState<Course | null>(null);
  const [error, setError] = useState<unknown>(null);
  const load = useCallback(async () => { setCourse(null); setError(null); try { setCourse(await managedCourse(courseId)); } catch (caught) { setError(caught); } }, [courseId]);
  useEffect(() => { void load(); }, [load]);
  if (!course) return <LearningAppShell eyebrow="COURSE COMMAND" title="Course"><RouteState title="course" state={error ? "error" : "loading"} error={error} onRetry={() => void load()} /></LearningAppShell>;
  const stages = Array.isArray(course.route?.stages) ? course.route.stages as string[] : [];
  if (!course.canReviewCohort) return <LearningAppShell eyebrow="COURSE COMMAND" title={course.title} actions={<Link href={`/teach/courses/${course.courseId}/build`} className="fos-primary-action">Build course <FeynmanIcon name="arrow" /></Link>}><SectionHeading eyebrow="COURSE MANAGEMENT" title="Manage the shared learning route." copy="Institution administrators can govern course structure and source policy. Cohort evidence remains restricted to the assigned instructor." /><section className="fos-command-grid"><article className="fos-panel"><div className="fos-panel-title"><span><FeynmanIcon name="spark" /> Teaching route</span></div>{stages.length ? <div className="fos-command-route">{stages.map((stage, index) => <div key={`${stage}-${index}`}><span>{String(index + 1).padStart(2, "0")}</span><strong>{stage}</strong><small>{index === 0 ? "Elicit a prediction" : "Capture an observable attempt"}</small></div>)}</div> : <p className="fos-empty-copy">Build a route before publishing this course.</p>}</article><article className="fos-panel"><div className="fos-panel-title"><span><FeynmanIcon name="source" /> Source governance</span></div><p>Verified course evidence uses only approved source packs. Cohort evidence is not available to your role.</p><Link href={`/teach/courses/${course.courseId}/build`} className="fos-quiet-action">Manage sources <FeynmanIcon name="arrow" /></Link></article></section></LearningAppShell>;
  return <LearningAppShell eyebrow="COURSE COMMAND" title={course.title} actions={<><Link href={`/teach/courses/${course.courseId}/build`} className="fos-quiet-action">Build course</Link><Link href={`/teach/courses/${course.courseId}/learners`} className="fos-primary-action">Cohort <FeynmanIcon name="people" /></Link></>}><section className="fos-command-hero"><div><span className="fos-eyebrow">{formatStatus(course.status)} · {course.learnerCount} learners</span><h1>{course.title}</h1><p>{course.description}</p></div><div className="fos-command-code"><span>JOIN CODE</span><strong>{course.joinCode || "-"}</strong><small>Share this with invited learners.</small></div></section><section className="fos-command-grid"><article className="fos-panel"><div className="fos-panel-title"><span><FeynmanIcon name="spark" /> Teaching route</span><Link href={`/teach/courses/${course.courseId}/build`}>Edit</Link></div>{stages.length ? <div className="fos-command-route">{stages.map((stage, index) => <div key={`${stage}-${index}`}><span>{String(index + 1).padStart(2, "0")}</span><strong>{stage}</strong><small>{index === 0 ? "Elicit a prediction" : "Capture an observable attempt"}</small></div>)}</div> : <p className="fos-empty-copy">Build a route before publishing this course.</p>}</article><article className="fos-panel"><div className="fos-panel-title"><span><FeynmanIcon name="source" /> Source governance</span></div><p>Verified course evidence uses only approved source packs. Private learner notebooks are not imported.</p><Link href={`/teach/courses/${course.courseId}/build`} className="fos-quiet-action">Manage sources <FeynmanIcon name="arrow" /></Link></article></section></LearningAppShell>;
}

function CourseBuilderViewLegacy({ courseId }: { courseId: string }) {
  const [course, setCourse] = useState<Course | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [title, setTitle] = useState("");
  const [routeText, setRouteText] = useState("");
  const [sourceIds, setSourceIds] = useState("");
  const [messageText, setMessageText] = useState("");
  const load = useCallback(async () => { setCourse(null); setError(null); try { const current = await managedCourse(courseId); setCourse(current); setTitle(current.title); setRouteText(Array.isArray(current.route?.stages) ? (current.route.stages as string[]).join("\n") : ""); setSourceIds((current.sourcePacks || []).map((source) => source.sourcePackId).join(", ")); } catch (caught) { setError(caught); } }, [courseId]);
  useEffect(() => { void load(); }, [load]);
  async function save(event: FormEvent) { event.preventDefault(); if (!course) return; try { const stages = routeText.split("\n").map((item) => item.trim()).filter(Boolean); const updated = await learningOsApi.updateCourse(course.courseId, { title, route: { stages }, sourcePolicy: { approvedSourcesOnly: true } }); const ids = sourceIds.split(",").map((item) => item.trim()).filter(Boolean); await learningOsApi.updateCourseSources(course.courseId, ids); setCourse(updated); setMessageText("Course route and approved source policy saved."); } catch (caught) { setMessageText(message(caught, "The course could not be saved.")); } }
  if (!course) return <LearningAppShell eyebrow="COURSE BUILDER" title="Course builder"><RouteState title="course builder" state={error ? "error" : "loading"} error={error} onRetry={() => void load()} /></LearningAppShell>;
  return <LearningAppShell eyebrow="COURSE BUILDER" title={course.title} actions={<Link href={`/teach/courses/${course.courseId}`} className="fos-quiet-action">Back to course</Link>}><SectionHeading eyebrow="BUILD THE EXPERIENCE" title="Author tasks, not a pile of content." copy="A learning route should ask learners to predict, explain, apply, or transfer." /><form className="fos-builder-grid" onSubmit={(event) => void save(event)}><article className="fos-panel fos-builder-main"><label className="fos-field"><span>Course title</span><input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={240} /></label><label className="fos-field"><span>Capability route <em>one active stage per line</em></span><textarea value={routeText} onChange={(event) => setRouteText(event.target.value)} rows={8} /></label></article><aside className="fos-panel fos-builder-side"><div className="fos-panel-title"><span><FeynmanIcon name="source" /> Source policy</span></div><p>Only approved packs support verified course evidence.</p><label className="fos-field"><span>Approved source pack IDs</span><textarea value={sourceIds} onChange={(event) => setSourceIds(event.target.value)} rows={4} placeholder="one-pack, another-pack" /></label><button className="fos-goal-submit" type="submit">Save teaching route <FeynmanIcon name="arrow" /></button>{messageText ? <p className="fos-share-message">{messageText}</p> : null}</aside></form></LearningAppShell>;
}

export function CourseBuilderView({ courseId }: { courseId: string }) {
  const [course, setCourse] = useState<Course | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [title, setTitle] = useState("");
  const [routeText, setRouteText] = useState("");
  const [sourceIds, setSourceIds] = useState("");
  const [status, setStatus] = useState<"draft" | "published">("draft");
  const [busy, setBusy] = useState(false);
  const [messageText, setMessageText] = useState("");
  const load = useCallback(async () => {
    setCourse(null);
    setError(null);
    try {
      const current = await managedCourse(courseId);
      setCourse(current);
      setTitle(current.title);
      setRouteText(Array.isArray(current.route?.stages) ? (current.route.stages as string[]).join("\n") : "");
      setSourceIds((current.sourcePacks || []).map((source) => source.sourcePackId).join(", "));
      setStatus(current.status === "published" ? "published" : "draft");
    } catch (caught) { setError(caught); }
  }, [courseId]);
  useEffect(() => { void load(); }, [load]);

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!course) return;
    setBusy(true);
    setMessageText("");
    try {
      const stages = routeText.split("\n").map((item) => item.trim()).filter(Boolean);
      const updated = await learningOsApi.updateCourse(course.courseId, { title: title.trim(), status, route: { stages }, sourcePolicy: { approvedSourcesOnly: true } });
      const ids = sourceIds.split(",").map((item) => item.trim()).filter(Boolean);
      await learningOsApi.updateCourseSources(course.courseId, ids);
      setCourse(updated);
      setMessageText(status === "published" ? "Course published. Learners can now join with its code." : "Draft course saved. Publish it when the route is ready.");
    } catch (caught) { setMessageText(message(caught, "The course could not be saved.")); }
    finally { setBusy(false); }
  }

  if (!course) return <LearningAppShell eyebrow="COURSE BUILDER" title="Course builder"><RouteState title="course builder" state={error ? "error" : "loading"} error={error} onRetry={() => void load()} /></LearningAppShell>;
  return <LearningAppShell eyebrow="COURSE BUILDER" title={course.title} actions={<Link href={`/teach/courses/${course.courseId}`} className="fos-quiet-action">Back to course</Link>}>
    <SectionHeading eyebrow="BUILD THE EXPERIENCE" title="Author tasks, not a pile of content." copy="A learning route should ask learners to predict, explain, apply, or transfer." />
    <form className="fos-builder-grid" onSubmit={(event) => void save(event)}>
      <article className="fos-panel fos-builder-main"><label className="fos-field"><span>Course title</span><input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={240} required /></label><label className="fos-field"><span>Capability route <em>one active stage per line</em></span><textarea value={routeText} onChange={(event) => setRouteText(event.target.value)} rows={8} /></label></article>
      <aside className="fos-panel fos-builder-side"><div className="fos-panel-title"><span><FeynmanIcon name="source" /> Source policy</span></div><p>Only approved packs support verified course evidence.</p><label className="fos-field"><span>Approved source pack IDs</span><textarea value={sourceIds} onChange={(event) => setSourceIds(event.target.value)} rows={4} placeholder="one-pack, another-pack" /></label><label className="fos-field"><span>Availability</span><select value={status} onChange={(event) => setStatus(event.target.value as "draft" | "published")}><option value="draft">Draft - instructors only</option><option value="published">Published - learners can join</option></select></label><button className="fos-goal-submit" type="submit" disabled={busy}>{busy ? "Saving..." : status === "published" ? "Save and publish" : "Save draft"} <FeynmanIcon name="arrow" /></button>{messageText ? <p className="fos-share-message">{messageText}</p> : null}</aside>
    </form>
  </LearningAppShell>;
}

export function CohortView({ courseId }: { courseId: string }) {
  const [data, setData] = useState<{ course: Course; learners: CohortLearner[] } | null>(null);
  const [error, setError] = useState<unknown>(null);
  const load = useCallback(async () => { setData(null); setError(null); try { const course = await reviewableCourse(courseId); const cohort = await learningOsApi.cohort(courseId); setData({ course, learners: cohort.learners }); } catch (caught) { setError(caught); } }, [courseId]);
  useEffect(() => { void load(); }, [load]);
  if (!data) return <LearningAppShell eyebrow="COHORT EVIDENCE" title="Cohort"><RouteState title="cohort evidence" state={error ? "error" : "loading"} error={error} onRetry={() => void load()} /></LearningAppShell>;
  return <LearningAppShell eyebrow="COHORT EVIDENCE" title={data.course.title} actions={<Link href={`/teach/courses/${data.course.courseId}`} className="fos-quiet-action">Course command</Link>}><SectionHeading eyebrow="SHARED EVIDENCE ONLY" title="See only the reasoning learners chose to show." copy="No raw chats, private notebooks, or unrelated learner state." /><section className="fos-cohort-table"><div className="fos-cohort-table-head"><span>Learner</span><span>Shared evidence</span><span>Review state</span></div>{data.learners.length ? data.learners.map((learner, index) => { const latest = learner.sharedEvidence[0]; return <article key={`${learner.name}-${index}`}><strong>{learner.name}</strong><div>{latest ? <><strong>{latest.capability}</strong><p>{latest.summary}</p></> : <p>No evidence shared.</p>}</div>{latest ? <StatusPill tone={stateTone(latest.status)}>{formatStatus(latest.status)}</StatusPill> : <StatusPill>Private</StatusPill>}</article>; }) : <p className="fos-empty-copy">No enrolled learner has shared evidence to this course.</p>}</section></LearningAppShell>;
}

export function InstitutionHomeView() {
  const [data, setData] = useState<{ workspace: LearningWorkspace; metrics: InstitutionMetrics } | null>(null);
  const [error, setError] = useState<unknown>(null);
  const load = useCallback(async () => { setData(null); setError(null); try { const result = await learningOsApi.institutionDashboard(); setData({ workspace: result.workspace, metrics: result }); } catch (caught) { setError(caught); } }, []);
  useEffect(() => { void load(); }, [load]);
  if (!data && error instanceof LearningOsApiError && error.status === 404) return <LearningAppShell eyebrow="INSTITUTION" title="Institution"><RouteState title="institution workspace" state="empty" action={<Link href="/institution/courses" className="fos-primary-action">Create institution workspace</Link>} /></LearningAppShell>;
  if (!data) return <LearningAppShell eyebrow="INSTITUTION" title="Institution"><RouteState title="institution workspace" state={error ? "error" : "loading"} error={error} onRetry={() => void load()} /></LearningAppShell>;
  const { metrics } = data;
  return <LearningAppShell eyebrow="INSTITUTION" title={data.workspace.name} actions={<Link href="/institution/members" className="fos-primary-action">Manage members <FeynmanIcon name="people" /></Link>}><SectionHeading eyebrow="GOVERNANCE WITHOUT SURVEILLANCE" title="Keep the system trustworthy at scale." copy="Institution views are aggregate by default and do not expose private learner context." /><section className="fos-institution-metrics"><article><span>ACTIVE LEARNERS</span><strong>{metrics.memberCounts.learner || 0}</strong></article><article><span>ACTIVE ENROLLMENTS</span><strong>{metrics.activeEnrollmentCount}</strong></article><article><span>VERIFIED EVIDENCE</span><strong>{metrics.verifiedEvidenceCount}</strong></article><article><span>SOURCE REVIEW</span><strong>{metrics.sourceGovernance.needsReview}</strong></article></section><section className="fos-institution-grid"><Link href="/institution/members" className="fos-panel fos-institution-link"><span><h2>Members and invitations</h2><p>Set roles without exposing learner memory.</p></span><FeynmanIcon name="arrow" /></Link><Link href="/institution/courses" className="fos-panel fos-institution-link"><span><h2>Course ownership</h2><p>See course routes and source policies.</p></span><FeynmanIcon name="arrow" /></Link><Link href="/institution/insights" className="fos-panel fos-institution-link"><span><h2>Aggregate insights</h2><p>Notice friction without learner ranking.</p></span><FeynmanIcon name="arrow" /></Link></section></LearningAppShell>;
}

export function InstitutionMembersView() {
  const [data, setData] = useState<{ workspace: LearningWorkspace | null; members: Member[] } | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("instructor");
  const [messageText, setMessageText] = useState("");
  const load = useCallback(async () => { setData(null); setError(null); try { const workspaces = await learningOsApi.workspaces(); const workspace = workspaces.workspaces.find((item) => item.kind === "institution" && ["owner", "institution_admin"].includes(item.role || "")) || null; if (!workspace) { setData({ workspace: null, members: [] }); return; } const roster = await learningOsApi.members(workspace.workspaceId); setData({ workspace, members: roster.members }); } catch (caught) { setError(caught); } }, []);
  useEffect(() => { void load(); }, [load]);
  async function invite(event: FormEvent) { event.preventDefault(); if (!data?.workspace) return; try { const result = await learningOsApi.inviteMember(data.workspace.workspaceId, { email, role }); setMessageText(`Invitation created for ${result.email}. Share ${result.joinPath} through an approved channel.`); setEmail(""); } catch (caught) { setMessageText(message(caught, "The invitation could not be created.")); } }
  if (!data) return <LearningAppShell eyebrow="INSTITUTION" title="Members"><RouteState title="members" state={error ? "error" : "loading"} error={error} onRetry={() => void load()} /></LearningAppShell>;
  if (!data.workspace) return <LearningAppShell eyebrow="INSTITUTION" title="Members"><RouteState title="institution admin workspace" state="empty" action={<Link href="/home" className="fos-primary-action">Return home</Link>} /></LearningAppShell>;
  return <LearningAppShell eyebrow="INSTITUTION" title="Members and invitations"><SectionHeading eyebrow="ROLE-BASED ACCESS" title="Give people only the access they need." copy="Owners and admins govern workspaces; learners retain their personal data." /><section className="fos-members-grid"><article className="fos-panel"><div className="fos-panel-title"><span><FeynmanIcon name="people" /> {data.workspace.name}</span><span>{data.members.length} active</span></div><div className="fos-members-list">{data.members.length ? data.members.map((member) => <div key={member.membershipId}><span><strong>{member.name}</strong><small>{member.email}</small></span><StatusPill>{formatStatus(member.role)}</StatusPill></div>) : <p className="fos-empty-copy">No active members yet.</p>}</div></article><form className="fos-panel fos-invite-form" onSubmit={(event) => void invite(event)}><span className="fos-eyebrow">INVITE A MEMBER</span><h2>Create an access link</h2><label className="fos-field"><span>Email</span><input value={email} onChange={(event) => setEmail(event.target.value)} type="email" required /></label><label className="fos-field"><span>Role</span><select value={role} onChange={(event) => setRole(event.target.value)}><option value="instructor">Instructor</option><option value="institution_admin">Institution admin</option><option value="learner">Learner</option></select></label><button className="fos-goal-submit" type="submit">Create invitation <FeynmanIcon name="arrow" /></button>{messageText ? <p className="fos-share-message">{messageText}</p> : null}</form></section></LearningAppShell>;
}

function InstitutionCoursesViewLegacy() {
  const [data, setData] = useState<{ courses: Course[]; workspaces: LearningWorkspace[] } | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [title, setTitle] = useState("");
  const [messageText, setMessageText] = useState("");
  const load = useCallback(async () => { setData(null); setError(null); try { const [courses, workspaces] = await Promise.all([learningOsApi.courses(), learningOsApi.workspaces()]); setData({ courses: courses.courses, workspaces: workspaces.workspaces }); } catch (caught) { setError(caught); } }, []);
  useEffect(() => { void load(); }, [load]);
  async function create(event: FormEvent) { event.preventDefault(); if (!data) return; const workspace = data.workspaces.find((item) => item.kind === "institution" && ["owner", "institution_admin", "instructor"].includes(item.role || "")); if (!workspace) { setMessageText("Create or join an institution workspace before creating a course."); return; } try { const course = await learningOsApi.createCourse({ workspaceId: workspace.workspaceId, title, status: "draft" }); setData({ ...data, courses: [...data.courses, course] }); setTitle(""); setMessageText("Draft course created. Build its route before publishing."); } catch (caught) { setMessageText(message(caught, "The course could not be created.")); } }
  if (!data) return <LearningAppShell eyebrow="INSTITUTION" title="Courses"><RouteState title="institution courses" state={error ? "error" : "loading"} error={error} onRetry={() => void load()} /></LearningAppShell>;
  return <LearningAppShell eyebrow="INSTITUTION" title="Course ownership"><SectionHeading eyebrow="COURSE GOVERNANCE" title="Give each course a clear owner and route." copy="Courses do not inherit private notebooks or learner memory." /><section className="fos-members-grid"><article className="fos-panel"><div className="fos-panel-title"><span><FeynmanIcon name="course" /> Courses</span><span>{data.courses.length} total</span></div>{data.courses.length ? data.courses.map((course) => <Link href={`/teach/courses/${course.courseId}`} key={course.courseId} className="fos-teach-course-row"><div><strong>{course.title}</strong><p>{course.instructor} · {course.learnerCount} learners · {course.sourcePackCount} source packs</p></div><StatusPill>{formatStatus(course.status)}</StatusPill></Link>) : <p className="fos-empty-copy">No courses have been created in this workspace.</p>}</article><form className="fos-panel fos-invite-form" onSubmit={(event) => void create(event)}><span className="fos-eyebrow">NEW COURSE</span><h2>Start a course route</h2><label className="fos-field"><span>Course title</span><input value={title} onChange={(event) => setTitle(event.target.value)} required /></label><button className="fos-goal-submit" type="submit">Create draft <FeynmanIcon name="arrow" /></button>{messageText ? <p className="fos-share-message">{messageText}</p> : null}</form></section></LearningAppShell>;
}

export function InstitutionCoursesView() {
  const [data, setData] = useState<{ courses: Course[]; workspaces: LearningWorkspace[] } | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [title, setTitle] = useState("");
  const [workspaceName, setWorkspaceName] = useState("");
  const [busy, setBusy] = useState(false);
  const [messageText, setMessageText] = useState("");
  const load = useCallback(async () => {
    setData(null);
    setError(null);
    try {
      const [courses, workspaces] = await Promise.all([learningOsApi.courses(), learningOsApi.workspaces()]);
      setData({ courses: courses.courses, workspaces: workspaces.workspaces });
    } catch (caught) { setError(caught); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const courseWorkspace = data?.workspaces.find((item) => item.kind === "institution" && ["owner", "institution_admin", "instructor"].includes(item.role || ""));

  async function createWorkspace(event: FormEvent) {
    event.preventDefault();
    if (!workspaceName.trim()) return;
    setBusy(true);
    setMessageText("");
    try {
      const workspace = await learningOsApi.createWorkspace({ name: workspaceName.trim(), kind: "institution" });
      setData((current) => current ? { ...current, workspaces: [...current.workspaces, workspace] } : current);
      setWorkspaceName("");
      setMessageText("Institution workspace created. You can now create a draft course.");
    } catch (caught) { setMessageText(message(caught, "The institution workspace could not be created.")); }
    finally { setBusy(false); }
  }

  async function createCourse(event: FormEvent) {
    event.preventDefault();
    if (!courseWorkspace || !title.trim()) return;
    setBusy(true);
    setMessageText("");
    try {
      const course = await learningOsApi.createCourse({ workspaceId: courseWorkspace.workspaceId, title: title.trim(), status: "draft" });
      setData((current) => current ? { ...current, courses: [...current.courses, course] } : current);
      setTitle("");
      setMessageText("Draft course created. Build its route before publishing.");
    } catch (caught) { setMessageText(message(caught, "The course could not be created.")); }
    finally { setBusy(false); }
  }

  if (!data) return <LearningAppShell eyebrow="INSTITUTION" title="Courses"><RouteState title="institution courses" state={error ? "error" : "loading"} error={error} onRetry={() => void load()} /></LearningAppShell>;
  return <LearningAppShell eyebrow="INSTITUTION" title="Course ownership">
    <SectionHeading eyebrow="COURSE GOVERNANCE" title="Give each course a clear owner and route." copy="Courses do not inherit private notebooks or learner memory." />
    <section className="fos-members-grid">
      <article className="fos-panel"><div className="fos-panel-title"><span><FeynmanIcon name="course" /> Courses</span><span>{data.courses.length} total</span></div>{data.courses.length ? data.courses.map((course) => <Link href={`/teach/courses/${course.courseId}`} key={course.courseId} className="fos-teach-course-row"><div><strong>{course.title}</strong><p>{course.instructor} / {course.learnerCount} learners / {course.sourcePackCount} source packs</p></div><StatusPill>{formatStatus(course.status)}</StatusPill></Link>) : <p className="fos-empty-copy">No courses have been created in this workspace.</p>}</article>
      {courseWorkspace ? <form className="fos-panel fos-invite-form" onSubmit={(event) => void createCourse(event)}><span className="fos-eyebrow">NEW COURSE</span><h2>Start a course route</h2><label className="fos-field"><span>Course title</span><input value={title} onChange={(event) => setTitle(event.target.value)} required /></label><button className="fos-goal-submit" type="submit" disabled={busy}>{busy ? "Creating..." : "Create draft"} <FeynmanIcon name="arrow" /></button>{messageText ? <p className="fos-share-message">{messageText}</p> : null}</form> : <form className="fos-panel fos-invite-form" onSubmit={(event) => void createWorkspace(event)}><span className="fos-eyebrow">INSTITUTION SETUP</span><h2>Create your teaching workspace</h2><p className="fos-empty-copy">A course needs an institution workspace with a clear owner. This does not expose learner notebooks or private evidence.</p><label className="fos-field"><span>Workspace name</span><input value={workspaceName} onChange={(event) => setWorkspaceName(event.target.value)} required placeholder="For example: Physics teaching team" /></label><button className="fos-goal-submit" type="submit" disabled={busy}>{busy ? "Creating..." : "Create institution workspace"} <FeynmanIcon name="arrow" /></button>{messageText ? <p className="fos-share-message">{messageText}</p> : null}</form>}
    </section>
  </LearningAppShell>;
}

export function InstitutionInsightsView() {
  const [metrics, setMetrics] = useState<InstitutionMetrics | null>(null);
  const [error, setError] = useState<unknown>(null);
  const load = useCallback(async () => { setMetrics(null); setError(null); try { setMetrics(await learningOsApi.institutionDashboard()); } catch (caught) { setError(caught); } }, []);
  useEffect(() => { void load(); }, [load]);
  if (!metrics) return <LearningAppShell eyebrow="INSTITUTION" title="Aggregate insights"><RouteState title="aggregate insights" state={error ? "error" : "loading"} error={error} onRetry={() => void load()} /></LearningAppShell>;
  return <LearningAppShell eyebrow="INSTITUTION" title="Aggregate insights"><SectionHeading eyebrow="USEFUL, NOT INTRUSIVE" title="Find learning friction without profiling people." copy="Indicators describe course conditions and shared evidence volume, not private learner activity." /><section className="fos-insight-grid"><article className="fos-panel fos-insight-feature"><span className="fos-eyebrow">SOURCE READINESS</span><h2>{metrics.sourceGovernance.approved} approved packs</h2><p>{metrics.sourceGovernance.needsReview} pack{metrics.sourceGovernance.needsReview === 1 ? "" : "s"} need review before they support verified learning claims.</p></article><article className="fos-panel"><span className="fos-eyebrow">ACTIVE LEARNING</span><strong className="fos-insight-number">{metrics.activeEnrollmentCount}</strong><p>active course enrollments</p></article><article className="fos-panel"><span className="fos-eyebrow">VERIFIED OUTPUT</span><strong className="fos-insight-number">{metrics.verifiedEvidenceCount}</strong><p>source-backed records across courses</p></article><article className="fos-panel fos-insight-callout"><FeynmanIcon name="shield" size={25} /><h2>What this view never shows</h2><p>Private chats, raw notebooks, unshared learner state, or learner ranking.</p></article></section></LearningAppShell>;
}
