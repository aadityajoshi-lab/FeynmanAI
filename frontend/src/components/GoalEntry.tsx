"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { useSignIn, useSignUp } from "@clerk/nextjs";
import { FeynmanIcon, LearningAppShell, StatusPill } from "./LearningAppShell";
import { isAuthenticationError, learningOsApi } from "@/lib/learningOsApi";
import type { PendingGoal } from "@/lib/learningOsTypes";

const PENDING_GOAL_KEY = "feynman.pendingGoal";

const examples = ["Understand operating-system scheduling", "Learn DSP well enough to design a filter", "Explain machine learning models clearly", "Study anatomy from my own notes"];

type StarterRoute = { key: string; domain: string; title: string; outcome: string; sourceRequired?: boolean };

const starterRoutes: StarterRoute[] = [
  { key: "os-process", domain: "Operating systems", title: "Trace process states and context switches", outcome: "Explain why a process moves between ready, running, and waiting." },
  { key: "os-scheduling", domain: "Operating systems", title: "Compare FCFS, Round Robin, and priority scheduling", outcome: "Calculate waiting time and defend a policy trade-off." },
  { key: "os-memory", domain: "Operating systems", title: "Simulate page faults and page replacement", outcome: "Predict how a working set changes under FIFO and LRU." },
  { key: "os-deadlock", domain: "Operating systems", title: "Diagnose a deadlock from a resource graph", outcome: "Find the cycle and propose a safe allocation change." },
  { key: "os-syscall", domain: "Operating systems", title: "Explain a system call and instruction trace", outcome: "Connect user code, kernel mode, registers, and return state." },
  { key: "gfx-transform", domain: "Computer graphics", title: "Apply 2D transforms in the correct order", outcome: "Predict how translation, rotation, and scale change an object." },
  { key: "gfx-spaces", domain: "Computer graphics", title: "Label world, view, and projection spaces", outcome: "Explain which matrix changes a point and why." },
  { key: "gfx-camera", domain: "Computer graphics", title: "Build a camera and projection matrix", outcome: "Manipulate the camera and explain the visible frame." },
  { key: "gfx-raster", domain: "Computer graphics", title: "Debug clipping, rasterization, and depth buffering", outcome: "Trace why a fragment is kept, clipped, or hidden." },
  { key: "gfx-light", domain: "Computer graphics", title: "Explain lighting, shading, and sampling artifacts", outcome: "Change a light or sample rate and defend the visual result." },
  { key: "dsp-sampling", domain: "Signal processing", title: "Predict aliasing from a sampling rate", outcome: "Use a waveform lab to connect sample rate and the Nyquist limit." },
  { key: "dsp-dft", domain: "Signal processing", title: "Derive the DFT from sampled sinusoids", outcome: "Explain magnitude, phase, and frequency-bin spacing." },
  { key: "dsp-leakage", domain: "Signal processing", title: "Diagnose spectral leakage and windowing", outcome: "Change a window and defend the resolution trade-off." },
  { key: "dsp-convolution", domain: "Signal processing", title: "Apply convolution in time and frequency", outcome: "Predict how filtering changes a bounded signal." },
  { key: "dsp-reconstruction", domain: "Signal processing", title: "Transfer sampling theory to reconstruction", outcome: "Explain what can and cannot be recovered from samples." },
  { key: "ml-split", domain: "Machine learning", title: "Detect dataset leakage in a train-test split", outcome: "Inspect a bounded split and explain why the metric is misleading." },
  { key: "ml-threshold", domain: "Machine learning", title: "Tune a classification threshold", outcome: "Predict how precision, recall, and the confusion matrix move." },
  { key: "ml-calibration", domain: "Machine learning", title: "Evaluate calibration and confidence", outcome: "Compare confidence with observed correctness on a slice." },
  { key: "ml-overfit", domain: "Machine learning", title: "Diagnose overfitting and regularization", outcome: "Change regularization and explain the train-validation trade-off." },
  { key: "ml-shift", domain: "Machine learning", title: "Analyze model errors under distribution shift", outcome: "Find the failing slice and design a follow-up evaluation." },
  { key: "med-anatomy", domain: "Medical education", title: "Explain an anatomy mechanism from an academic source", outcome: "Connect structure, relationship, and function with citations.", sourceRequired: true },
  { key: "med-physiology", domain: "Medical education", title: "Trace a bounded physiology feedback loop", outcome: "Explain the mechanism without extending it to personal advice.", sourceRequired: true },
  { key: "med-case", domain: "Medical education", title: "Interpret a bounded educational case", outcome: "Compare academic explanations and state uncertainty.", sourceRequired: true },
  { key: "med-evidence", domain: "Medical education", title: "Compare evidence quality in an academic question", outcome: "Separate what a source supports from what it cannot establish.", sourceRequired: true },
  { key: "med-limit", domain: "Medical education", title: "Communicate uncertainty and limitations", outcome: "Write a source-cited explanation that stays educational.", sourceRequired: true },
  { key: "history-cause", domain: "History", title: "Build a causal timeline for a historical change", outcome: "Distinguish chronology, mechanism, and interpretation.", sourceRequired: true },
  { key: "history-source", domain: "History", title: "Compare primary and secondary historical sources", outcome: "Track claims, provenance, and disagreement.", sourceRequired: true },
  { key: "history-institutions", domain: "History", title: "Explain how an institution changed over time", outcome: "Connect evidence to a bounded institutional claim.", sourceRequired: true },
  { key: "history-map", domain: "History", title: "Map actors, incentives, and consequences", outcome: "Use a relationship map to explain competing perspectives.", sourceRequired: true },
  { key: "history-transfer", domain: "History", title: "Transfer a historical pattern to a nearby case", outcome: "State what carries over and what the evidence does not support.", sourceRequired: true },
];

function savePendingGoal(goal: PendingGoal) {
  window.localStorage.setItem(PENDING_GOAL_KEY, JSON.stringify(goal));
}

function readPendingGoal(): PendingGoal | null {
  try {
    const raw = window.localStorage.getItem(PENDING_GOAL_KEY);
    return raw ? JSON.parse(raw) as PendingGoal : null;
  } catch {
    return null;
  }
}

function inferredContract(goal: PendingGoal) {
  const text = `${goal.title} ${goal.description}`.toLowerCase();
  const highStakes = /(medical|clinical|medicine|finance|stock|trading|invest)/.test(text);
  const engineering = /(operating system|dsp|signal|graphics|kernel|computer|engineering)/.test(text);
  return {
    domain: highStakes ? (/(finance|stock|trading|invest)/.test(text) ? "Finance education" : "Medical education") : engineering ? "Engineering" : "Adaptive study",
    safety: highStakes ? "Academic + source-cited" : "Guided learning",
    first: engineering ? "Predict the system behavior before inspecting the mechanism." : "Explain the first important idea in your own words before asking for an answer.",
  };
}

type ContractDraft = {
  intendedCapability: string;
  learnerStartingPoint: PendingGoal["currentLevel"];
  prerequisites: string;
  confidence: string;
  sourceRequirements: string;
  safetyMode: string;
  verificationMode: string;
  firstTask: string;
};

function contractDraftFor(goal: PendingGoal): ContractDraft {
  const inferred = inferredContract(goal);
  const academic = inferred.safety === "Academic + source-cited";
  return {
    intendedCapability: goal.title,
    learnerStartingPoint: goal.currentLevel,
    prerequisites: ["Name the core relationship", "Use one concrete example", "Transfer it to a nearby case"].join("\n"),
    confidence: "provisional",
    sourceRequirements: academic ? "Source-backed evidence is required before a claim can be verified." : "Sources are optional until you want source-backed verification.",
    safetyMode: academic ? "academic_source_bound" : "guided",
    verificationMode: academic ? "source_backed" : "guided",
    firstTask: inferred.first,
  };
}

export function UniversalGoalEntry() {
  const router = useRouter();
  const pathname = usePathname();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [outcome, setOutcome] = useState("");
  const [currentLevel, setCurrentLevel] = useState<PendingGoal["currentLevel"]>("beginner");
  const [timeBudget, setTimeBudget] = useState("A few focused sessions each week");
  const [hasSources, setHasSources] = useState(false);
  const [sourceNotebookId, setSourceNotebookId] = useState("");
  const [starterRoute, setStarterRoute] = useState("");
  const [category, setCategory] = useState("general");
  const [authState, setAuthState] = useState<boolean | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const syncAuth = (event?: Event) => {
      const detail = (event as CustomEvent<{ isSignedIn?: boolean }> | undefined)?.detail;
      const signedIn = typeof detail?.isSignedIn === "boolean" ? detail.isSignedIn : document.documentElement.dataset.feynmanAuth === "signed-in";
      setAuthState(signedIn);
      if (signedIn && pathname === "/") router.replace("/home");
    };
    syncAuth();
    window.addEventListener("feynman-auth-state", syncAuth);
    const requestedSourceNotebookId = new URLSearchParams(window.location.search).get("sourceNotebook") || "";
    setSourceNotebookId(requestedSourceNotebookId);
    if (requestedSourceNotebookId) setHasSources(true);
    return () => window.removeEventListener("feynman-auth-state", syncAuth);
  }, [pathname, router]);

  async function continueToContract(event: FormEvent) {
    event.preventDefault();
    if (!title.trim()) { setError("Start with the capability you want, not just a subject name."); return; }
    const courseId = new URLSearchParams(window.location.search).get("course") || "";
    const pending = { title: title.trim(), description: description.trim(), outcome: outcome.trim(), currentLevel, timeBudget, hasSources, category, ...(courseId ? { courseId } : {}), ...(sourceNotebookId ? { sourceNotebookId } : {}) };
    savePendingGoal(pending);
    try {
      await learningOsApi.me();
      router.push(courseId ? `/goals/new?course=${encodeURIComponent(courseId)}` : "/goals/new");
    } catch {
      const next = courseId ? `/goals/new?course=${encodeURIComponent(courseId)}` : "/goals/new";
      router.push(`/login?next=${encodeURIComponent(next)}` as never);
    }
  }

  function chooseStarterRoute(key: string) {
    setStarterRoute(key);
    const route = starterRoutes.find((item) => item.key === key);
    if (!route) return;
    setTitle(route.title);
    setOutcome(route.outcome);
    setCategory(route.domain.toLowerCase().replaceAll(" ", "_"));
    setHasSources(Boolean(route.sourceRequired));
  }

  return <main className="fos-entry-shell">
    <header className="fos-entry-top"><Link className="fos-brand" href={authState === true ? "/home" : "/"} aria-label="Feynman home"><span className="fos-brand-mark">f</span><span>feynman<span>.</span>ai</span></Link><nav aria-label="Landing page"><a href="#loop">The loop</a><a href="#boundary">Source boundary</a>{authState === true ? <><Link href="/goals">My goals</Link><Link href="/home" className="fos-entry-signin">Open workspace</Link></> : <><Link href={"/login" as never}>Sign in</Link><Link href={"/signup" as never} className="fos-entry-signin">Create a lab</Link></>}</nav></header>
    <section className="fos-entry-layout">
      <div className="fos-entry-copy"><span className="fos-eyebrow">THE ADAPTIVE LEARNING ENGINE</span><h1>AI can explain anything.<br /><em>Feynman shows what you can do.</em></h1><p>Most tutors optimize for a good answer. Feynman turns your goal into an observable task, watches the attempt, and chooses the next best move from evidence.</p><div className="fos-entry-proof"><span><i>01</i> Define a capability, not a subject</span><span><i>02</i> Predict, build, explain, or debug</span><span><i>03</i> Carry forward only what you demonstrated</span></div><div className="fos-entry-articulation" id="boundary"><span className="fos-eyebrow">THE DIFFERENCE</span><h2>Context is useful. <em>Evidence is the product.</em></h2><p>Sources ground the work; observable attempts change your learner state.</p></div></div>
      <form className="fos-goal-card" id="loop" onSubmit={(event) => void continueToContract(event)}>
        <div className="fos-goal-card-head"><span className="fos-eyebrow">START WITH A CAPABILITY</span><StatusPill><span className="fos-live-dot" /> private by default</StatusPill></div>
        <h2>What should you become able to do?</h2>
        <label className="fos-field"><span>Your capability</span><textarea value={title} onChange={(event) => setTitle(event.target.value)} placeholder="For example: trace a process scheduler and explain its trade-offs." rows={3} maxLength={240} autoFocus /></label>
        <label className="fos-field"><span>Why does this matter to you? <em>optional</em></span><input value={outcome} onChange={(event) => setOutcome(event.target.value)} placeholder="Pass a viva, build a project, teach a peer…" maxLength={500} /></label>
        <label className="fos-field"><span>Starting point</span><select value={currentLevel} onChange={(event) => setCurrentLevel(event.target.value as PendingGoal["currentLevel"])}><option value="beginner">I am new to it</option><option value="intermediate">I know some pieces</option><option value="advanced">I need depth and transfer</option></select></label>
        <label className="fos-field"><span>Learning category</span><select value={category} onChange={(event) => setCategory(event.target.value)}><option value="general">General learning</option><option value="operating_systems">Operating systems</option><option value="computer_graphics">Computer graphics</option><option value="dsp">Signal processing / DSP</option><option value="ai_ml">Machine learning / AI</option><option value="medical">Medical education</option><option value="history">History</option></select></label>
        <label className="fos-source-toggle"><input type="checkbox" checked={hasSources} onChange={(event) => setHasSources(event.target.checked)} /><span><FeynmanIcon name="source" /><strong>Add a source when it should ground the route</strong><small>PDFs, images, documents, and webpages stay in a separate Source Desk.</small></span></label>
        {error ? <p className="fos-form-error" role="alert">{error}</p> : null}
        <button className="fos-goal-submit" type="submit">Build my learning route <FeynmanIcon name="arrow" /></button>
        <div className="fos-goal-examples"><span>Start from a real capability</span>{examples.map((example) => <button key={example} type="button" onClick={() => setTitle(example)}>{example}</button>)}</div>
        <details className="fos-starter-routes"><summary>Browse 30 guided starter routes</summary><div>{Array.from(new Set(starterRoutes.map((route) => route.domain))).map((domain) => <section key={domain}><span>{domain}</span>{starterRoutes.filter((route) => route.domain === domain).map((route) => <button key={route.key} type="button" className={starterRoute === route.key ? "selected" : ""} onClick={() => chooseStarterRoute(route.key)}>{route.title}<small>{route.outcome}</small></button>)}</section>)}</div></details>
      </form>
    </section>
    <footer className="fos-entry-footer"><span>Feynman only records what you demonstrate.</span><span>Sources and learner memory are separate.</span></footer>
  </main>;
}

export function AuthView({ initialMode = "register" }: { initialMode?: "register" | "login" }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const signInState = useSignIn();
  const signUpState = useSignUp();
  const [mode] = useState<"register" | "login">(initialMode);
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [needsVerification, setNeedsVerification] = useState(false);
  const [verificationCode, setVerificationCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [redirecting, setRedirecting] = useState(false);
  const next = searchParams.get("next") || "/home";

  useEffect(() => {
    const syncAuth = (event?: Event) => {
      const detail = (event as CustomEvent<{ isSignedIn?: boolean }> | undefined)?.detail;
      const signedIn = typeof detail?.isSignedIn === "boolean" ? detail.isSignedIn : document.documentElement.dataset.feynmanAuth === "signed-in";
      if (signedIn) {
        setRedirecting(true);
        router.replace(next as never);
      }
    };
    syncAuth();
    window.addEventListener("feynman-auth-state", syncAuth);
    return () => window.removeEventListener("feynman-auth-state", syncAuth);
  }, [next, router]);

  function clerkErrorMessage(caught: unknown) {
    const errors = (caught as { errors?: Array<{ longMessage?: string; message?: string }> })?.errors;
    return errors?.[0]?.longMessage || errors?.[0]?.message || (caught instanceof Error ? caught.message : "We could not open your workspace.");
  }

  async function finishClerkSession(sessionId: string | null) {
    const setActive = mode === "register" ? signUpState.setActive : signInState.setActive;
    if (!sessionId || !setActive) throw new Error("Clerk did not create an active session. Try again.");
    await setActive({ session: sessionId });
    await learningOsApi.me();
    router.replace(next as never);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true); setError("");
    try {
      if (mode === "register" && signUpState.isLoaded) {
        const result = await signUpState.signUp.create({ emailAddress: email, password, firstName: displayName || undefined });
        if (result.status !== "complete") {
          await signUpState.signUp.prepareEmailAddressVerification({ strategy: "email_code" });
          setNeedsVerification(true);
          setError("We sent a verification code to your email. Enter it below to finish creating your workspace.");
        } else {
          await finishClerkSession(result.createdSessionId);
        }
      } else if (mode === "login" && signInState.isLoaded) {
        const result = await signInState.signIn.create({ strategy: "password", identifier: email, password });
        if (result.status !== "complete") throw new Error("This sign-in needs an additional verification step in Clerk.");
        await finishClerkSession(result.createdSessionId);
      } else {
        throw new Error("Authentication is still loading. Try again.");
      }
    } catch (caught) {
      setError(clerkErrorMessage(caught));
    } finally { setBusy(false); }
  }

  async function verifyEmail(event: FormEvent) {
    event.preventDefault();
    if (!signUpState.isLoaded) return;
    setBusy(true); setError("");
    try {
      const result = await signUpState.signUp.attemptEmailAddressVerification({ code: verificationCode.trim() });
      if (result.status !== "complete") throw new Error("That verification code is not complete. Check the email and try again.");
      await finishClerkSession(result.createdSessionId);
    } catch (caught) {
      setError(clerkErrorMessage(caught));
    } finally { setBusy(false); }
  }

  if (redirecting) return <main className="fos-entry-shell fos-route-state loading" role="status"><span className="fos-loading-orb" /><h2>Opening your workspace…</h2><p>Your active session is being restored.</p></main>;
  return <main className="fos-entry-shell fos-auth-shell">
    <header className="fos-entry-top"><Link className="fos-brand" href="/" aria-label="Feynman home"><span className="fos-brand-mark">f</span><span>feynman<span>.</span>ai</span></Link><nav aria-label="Authentication"><Link href={"/" as never}>Back to home</Link></nav></header>
    <section className="fos-onboarding-grid">
      <div className="fos-onboarding-copy"><span className="fos-eyebrow">LEARNER-OWNED BY DESIGN</span><h1>Your learning state is not a score.</h1><p>Feynman keeps source context in notebooks and learner evidence in your private workspace. You decide what a teacher or course can see.</p><div className="fos-trust-list"><div><FeynmanIcon name="source" /><span><strong>Notebook memory</strong><small>Extracted source text, citations, and outputs stay with that notebook.</small></span></div><div><FeynmanIcon name="proof" /><span><strong>Learner evidence</strong><small>Only visible attempts can change a capability state.</small></span></div><div><FeynmanIcon name="shield" /><span><strong>Revocable sharing</strong><small>Courses only receive the evidence you explicitly share.</small></span></div></div>
      </div>
      <form className="fos-auth-card" onSubmit={(event) => void (needsVerification ? verifyEmail(event) : submit(event))}>
        <div className="fos-auth-tabs"><span>{mode === "register" ? "CREATE YOUR LAB" : "WELCOME BACK"}</span><Link href={(mode === "register" ? "/login" : "/signup") as never}>{mode === "register" ? "Already have an account? Sign in" : "New here? Create a lab"}</Link></div>
        {needsVerification ? <><span className="fos-eyebrow">VERIFY EMAIL</span><h2>One last step</h2><p>Enter the code Clerk sent to {email}.</p><label className="fos-field"><span>Verification code</span><input value={verificationCode} onChange={(event) => setVerificationCode(event.target.value)} inputMode="numeric" autoComplete="one-time-code" required /></label>{error ? <p className="fos-form-error" role="alert">{error}</p> : null}<button type="submit" className="fos-goal-submit" disabled={busy}>{busy ? "Verifying…" : "Verify and enter"}<FeynmanIcon name="arrow" /></button><button type="button" className="fos-quiet-action" onClick={() => { setNeedsVerification(false); setVerificationCode(""); setError(""); }}>Use a different email</button></> : <><h2>{mode === "register" ? "Make your personal lab" : "Welcome back"}</h2>{mode === "register" ? <label className="fos-field"><span>Name</span><input value={displayName} onChange={(event) => setDisplayName(event.target.value)} placeholder="How should Feynman address you?" maxLength={120} /></label> : null}<label className="fos-field"><span>Email</span><input type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" required /></label><label className="fos-field"><span>Password</span><input type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="At least 8 characters" minLength={8} required /></label>{mode === "register" ? <div id="clerk-captcha" aria-hidden="true" /> : null}{error ? <p className="fos-form-error" role="alert">{error}</p> : null}<button type="submit" className="fos-goal-submit" disabled={busy}>{busy ? "Opening…" : mode === "register" ? "Create my workspace" : "Sign in"}<FeynmanIcon name="arrow" /></button><p className="fos-auth-note">Authentication is handled by Clerk. Feynman receives only a verified session identity; provider API keys stay server-side.</p></>}
      </form>
    </section>
  </main>;
}

/** Kept as a compatibility export for older imports; new entry points use /login and /signup. */
export function OnboardingView() {
  return <AuthView initialMode="login" />;
}

export function GoalSetupView() {
  const router = useRouter();
  const [pending, setPending] = useState<PendingGoal | null>(null);
  const [draft, setDraft] = useState<ContractDraft | null>(null);
  const [courseId, setCourseId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const nextPending = readPendingGoal();
    const requestedCourseId = new URLSearchParams(window.location.search).get("course") || "";
    if (!nextPending && requestedCourseId) {
      router.replace(`/?course=${encodeURIComponent(requestedCourseId)}`);
      return;
    }
    setPending(nextPending);
    setDraft(nextPending ? contractDraftFor(nextPending) : null);
    setCourseId(nextPending?.courseId || requestedCourseId);
  }, [router]);

  async function createGoal() {
    if (!pending || !draft) { router.replace("/"); return; }
    const intendedCapability = draft.intendedCapability.trim();
    const firstTask = draft.firstTask.trim();
    if (!intendedCapability || !firstTask) {
      setError("Set an intended capability and a first observable task before confirming the contract.");
      return;
    }
    setBusy(true); setError("");
    try {
      const brief = pending.description.trim() || pending.outcome.trim() || intendedCapability;
      const contract = {
        intendedCapability,
        learnerStartingPoint: draft.learnerStartingPoint,
        timeBudget: pending.timeBudget,
        prerequisites: draft.prerequisites.split(/[,\n]/).map((item) => item.trim()).filter(Boolean),
        confidence: "provisional",
        sourceRequirements: inferredContract(pending).safety === "Academic + source-cited" ? "Source-backed evidence is required before a claim can be verified." : "Sources are optional until source-backed verification is needed.",
        safetyMode: draft.safetyMode,
        verificationMode: draft.verificationMode,
        firstTask,
        learnerCorrection: "Reviewed and edited by the learner before confirmation.",
        brief,
      };
      const goal = await learningOsApi.createGoal({
        ...pending,
        title: intendedCapability,
        currentLevel: draft.learnerStartingPoint,
        category: pending.category,
        ...(courseId ? { courseId } : {}),
        contract,
      });
      if (pending.sourceNotebookId) await learningOsApi.attachGoalNotebook(goal.goalId, pending.sourceNotebookId);
      await learningOsApi.updateGoal(goal.goalId, { confirmContract: true });
      window.localStorage.removeItem(PENDING_GOAL_KEY);
      router.replace(`/goals/${goal.goalId}`);
    } catch (caught) {
      if (isAuthenticationError(caught)) { router.push(`/login?next=${encodeURIComponent(courseId ? `/goals/new?course=${courseId}` : "/goals/new")}` as never); return; }
      setError(caught instanceof Error ? caught.message : "The contract could not be saved.");
    } finally { setBusy(false); }
  }

  if (!pending || !draft) return <UniversalGoalEntry />;

  return <LearningAppShell eyebrow="NEW GOAL" title="Confirm your learning contract" actions={<Link href={courseId ? `/?course=${encodeURIComponent(courseId)}` : "/"} className="fos-quiet-action">Edit intent</Link>}>
    <section className="fos-contract-layout"><div className="fos-contract-intro"><span className="fos-eyebrow">LEARNER-EDITABLE AGREEMENT</span><h1>Make the route accurate before it starts.</h1><p>Feynman proposes a starting contract, but you control the capability, boundary, and first proof. Nothing is confirmed until you do.</p><div className="fos-contract-goal"><span>WHY THIS MATTERS</span><strong>{pending.outcome || "A capability worth demonstrating"}</strong>{courseId ? <p>This goal will stay inside its selected course without exposing private notebook text.</p> : null}</div></div><form className="fos-contract-card fos-contract-form" onSubmit={(event) => { event.preventDefault(); void createGoal(); }}><div className="fos-contract-card-top"><StatusPill>{inferredContract(pending).domain}</StatusPill><StatusPill>{pending.hasSources ? "Source desk available" : "Sources optional"}</StatusPill></div><h2>Learning contract</h2><p className="fos-contract-lede">Four decisions are enough: what you will do, where you are starting, what must come first, and the first observable proof.</p><label className="fos-field"><span>Intended capability</span><textarea value={draft.intendedCapability} onChange={(event) => setDraft({ ...draft, intendedCapability: event.target.value })} rows={3} maxLength={240} required /></label><label className="fos-field"><span>Learner starting point</span><select value={draft.learnerStartingPoint} onChange={(event) => setDraft({ ...draft, learnerStartingPoint: event.target.value as PendingGoal["currentLevel"] })}><option value="beginner">Beginner</option><option value="intermediate">Intermediate</option><option value="advanced">Advanced</option></select></label><label className="fos-field"><span>Prerequisites <em>one per line or comma-separated</em></span><textarea value={draft.prerequisites} onChange={(event) => setDraft({ ...draft, prerequisites: event.target.value })} rows={3} /></label><label className="fos-field"><span>First observable task</span><textarea value={draft.firstTask} onChange={(event) => setDraft({ ...draft, firstTask: event.target.value })} rows={3} maxLength={1000} required /></label><p className="fos-contract-boundary">Chat, reading, and generated answers do not confirm this contract. Your first learner state change requires an observable attempt.</p>{error ? <p className="fos-form-error" role="alert">{error}</p> : null}<button type="submit" className="fos-goal-submit" disabled={busy}>{busy ? "Saving contract…" : "Confirm and begin"}<FeynmanIcon name="arrow" /></button></form></section>
  </LearningAppShell>;
}

export function JoinInvitationView({ token }: { token: string }) {
  const router = useRouter();
  const [invite, setInvite] = useState<{ organization: string; email: string; role: string; status: string } | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { learningOsApi.invitation(token).then(setInvite).catch((caught) => setError(caught instanceof Error ? caught.message : "This invitation could not be opened.")); }, [token]);
  async function accept() {
    setBusy(true); setError("");
    try { await learningOsApi.acceptInvitation(token); router.replace("/home"); } catch (caught) { if (isAuthenticationError(caught)) { router.push(`/login?next=/join/${token}` as never); return; } setError(caught instanceof Error ? caught.message : "This invitation could not be accepted."); } finally { setBusy(false); }
  }
  return <LearningAppShell eyebrow="WORKSPACE INVITATION" title="Join safely" compact><section className="fos-invite-card">{error ? <><FeynmanIcon name="close" size={28} /><h1>This invitation needs attention</h1><p>{error}</p><Link href="/home" className="fos-quiet-action">Return home</Link></> : !invite ? <><span className="fos-loading-orb" /><p>Checking the invitation…</p></> : <><span className="fos-invite-seal"><FeynmanIcon name="people" size={28} /></span><span className="fos-eyebrow">INVITED AS {invite.role.replace("_", " ")}</span><h1>Join {invite.organization}</h1><p>This invite is for <strong>{invite.email}</strong>. Your private notebooks and unshared learner memory remain private.</p><div className="fos-invite-rules"><span><FeynmanIcon name="lock" /> Sources remain in your notebooks.</span><span><FeynmanIcon name="proof" /> You choose which evidence to share.</span></div><button className="fos-goal-submit" type="button" onClick={() => void accept()} disabled={busy}>{busy ? "Joining…" : "Accept invitation"}<FeynmanIcon name="arrow" /></button></>}</section></LearningAppShell>;
}
