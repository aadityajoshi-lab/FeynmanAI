"use client";

import { useEffect, useId, useMemo, useState } from "react";
import type { ActivityConfiguration } from "@/lib/learningOsTypes";
import styles from "./DomainActivityWorkbench.module.css";

export type WorkbenchActivityType =
  | "predict"
  | "explain"
  | "derive"
  | "debug"
  | "simulate"
  | "apply"
  | "build"
  | "transfer"
  | (string & {});

export type DomainActivityWorkbenchProps = {
  domain: string;
  goalTitle: string;
  activityType: WorkbenchActivityType;
  configuration?: ActivityConfiguration;
  onInteractionChange?: (state: Record<string, unknown>) => void;
};

type WorkbenchInteractionProps = {
  onInteractionChange?: (state: Record<string, unknown>) => void;
};

type WorkbenchDomain =
  | "dsp"
  | "history"
  | "operating_systems"
  | "graphics"
  | "machine_learning"
  | "medicine"
  | "finance"
  | "general";

type TaskCopy = {
  action: string;
  instruction: string;
};

type SamplingState = {
  signalFrequency: number;
  sampleRate: number;
  nyquistFrequency: number;
  aliasFrequency: number;
  samplesPerCycle: number;
  isAliased: boolean;
};

type SchedulerProcess = {
  id: "P1" | "P2" | "P3";
  arrival: number;
  burst: number;
};

export type SchedulerSlice = {
  processId: SchedulerProcess["id"];
  start: number;
  end: number;
  remaining: number;
};

export type SchedulerTrace = {
  slices: SchedulerSlice[];
  completionTimes: Record<SchedulerProcess["id"], number>;
  averageWaitingTime: number;
};

type SchedulerPolicy = "fcfs" | "round_robin" | "priority";
type OperatingSystemsTopic = "scheduling" | "memory" | "deadlock" | "system_call";

const SCHEDULER_PROCESSES: SchedulerProcess[] = [
  { id: "P1", arrival: 0, burst: 5 },
  { id: "P2", arrival: 1, burst: 3 },
  { id: "P3", arrival: 2, burst: 4 },
];

const PAGE_REFERENCE_STRING = [7, 0, 1, 2, 0, 3, 0, 4];

const ML_EXAMPLES = [
  { id: "A01", actual: "positive", confidence: 0.96, slice: "clear" },
  { id: "A02", actual: "negative", confidence: 0.73, slice: "clear" },
  { id: "B03", actual: "positive", confidence: 0.42, slice: "low_light" },
  { id: "B04", actual: "negative", confidence: 0.84, slice: "low_light" },
  { id: "C05", actual: "positive", confidence: 0.61, slice: "occluded" },
  { id: "C06", actual: "negative", confidence: 0.58, slice: "occluded" },
  { id: "D07", actual: "positive", confidence: 0.37, slice: "rare_class" },
  { id: "D08", actual: "negative", confidence: 0.68, slice: "rare_class" },
] as const;

type MlSlice = "all" | (typeof ML_EXAMPLES)[number]["slice"];

function normalizedText(value: string) {
  return value.toLowerCase().replace(/[\-_]+/g, " ");
}

export function resolveWorkbenchDomain(domain: string, goalTitle = ""): WorkbenchDomain {
  const cues = normalizedText(`${domain} ${goalTitle}`);

  if (/(medical|medicine|clinical|health|patient|diagnos|treat|pharmac|disease)/.test(cues)) {
    return "medicine";
  }
  if (/(finance|financial|invest|trading|portfolio|market|balance sheet|valuation)/.test(cues)) {
    return "finance";
  }
  if (/(dsp|signal processing|sampling|aliasing|reconstruction|waveform|fourier)/.test(cues)) {
    return "dsp";
  }
  if (/(history|historical|primary source|archive|institution|chronology|causal timeline)/.test(cues)) {
    return "history";
  }
  if (/(operating system|scheduler|scheduling|round robin|process|thread|memory management)/.test(cues)) {
    return "operating_systems";
  }
  if (/(computer graphics|graphics|render|rendering|camera|transform|transformation|shader|lighting)/.test(cues)) {
    return "graphics";
  }
  if (/(machine learning|\bml\b|\bai\b|dataset|classification|model|neural|error analysis)/.test(cues)) {
    return "machine_learning";
  }

  return "general";
}

function activityCopy(activityType: WorkbenchActivityType): TaskCopy {
  const normalized = normalizedText(activityType || "apply");
  if (normalized.includes("predict")) {
    return { action: "Predict before reveal", instruction: "Set the controls, state what you expect, then use the calculated state to check your reasoning." };
  }
  if (normalized.includes("derive")) {
    return { action: "Derive the relationship", instruction: "Use the visible state to justify each step instead of relying on an answer alone." };
  }
  if (normalized.includes("debug")) {
    return { action: "Find the failure mode", instruction: "Change one variable at a time and identify the condition that produces the failure." };
  }
  if (normalized.includes("simulate")) {
    return { action: "Run a bounded simulation", instruction: "Manipulate the system and explain the trade-off exposed by the trace." };
  }
  if (normalized.includes("build")) {
    return { action: "Build an interpretation", instruction: "Make a concrete configuration, then defend why it meets the task boundary." };
  }
  if (normalized.includes("transfer")) {
    return { action: "Transfer to a nearby case", instruction: "Apply the same principle to the changed conditions and name what no longer holds." };
  }
  if (normalized.includes("explain")) {
    return { action: "Explain the mechanism", instruction: "Use the changed state as evidence for a short causal explanation in your own words." };
  }
  return { action: "Apply the concept", instruction: "Make an observable attempt in the activity, then explain the result in your evidence response." };
}

function humanizeActivityType(activityType: WorkbenchActivityType) {
  const value = normalizedText(activityType || "apply").trim();
  return value ? value.replace(/\b\w/g, (letter) => letter.toUpperCase()) : "Apply";
}

function formatNumber(value: number, digits = 1) {
  return Number.isInteger(value) ? String(value) : value.toFixed(digits);
}

export function clampRangeValue(value: number, min: number, max: number, step = 1) {
  const stepped = min + Math.round((value - min) / step) * step;
  return Math.min(max, Math.max(min, Number(stepped.toFixed(6))));
}

export function calculateSamplingState(signalFrequency: number, sampleRate: number): SamplingState {
  const nyquistFrequency = sampleRate / 2;
  const wrappedFrequency = ((signalFrequency + nyquistFrequency) % sampleRate + sampleRate) % sampleRate - nyquistFrequency;
  const aliasFrequency = Math.abs(wrappedFrequency);

  return {
    signalFrequency,
    sampleRate,
    nyquistFrequency,
    aliasFrequency,
    samplesPerCycle: sampleRate / signalFrequency,
    isAliased: signalFrequency > nyquistFrequency,
  };
}

export function buildRoundRobinTrace(quantum: number, processes: SchedulerProcess[] = SCHEDULER_PROCESSES): SchedulerTrace {
  const pending = [...processes]
    .sort((left, right) => left.arrival - right.arrival)
    .map((process) => ({ ...process, remaining: process.burst }));
  const queue: Array<(SchedulerProcess & { remaining: number })> = [];
  const slices: SchedulerSlice[] = [];
  const completionTimes = {} as Record<SchedulerProcess["id"], number>;
  let nextPending = 0;
  let time = 0;

  while (nextPending < pending.length || queue.length) {
    if (!queue.length && nextPending < pending.length && time < pending[nextPending].arrival) {
      time = pending[nextPending].arrival;
    }

    while (nextPending < pending.length && pending[nextPending].arrival <= time) {
      queue.push(pending[nextPending]);
      nextPending += 1;
    }

    const current = queue.shift();
    if (!current) continue;

    const start = time;
    const runFor = Math.min(current.remaining, Math.max(1, quantum));
    time += runFor;
    current.remaining -= runFor;
    slices.push({ processId: current.id, start, end: time, remaining: current.remaining });

    while (nextPending < pending.length && pending[nextPending].arrival <= time) {
      queue.push(pending[nextPending]);
      nextPending += 1;
    }

    if (current.remaining > 0) {
      queue.push(current);
    } else {
      completionTimes[current.id] = time;
    }
  }

  const totalWaitingTime = processes.reduce((total, process) => total + completionTimes[process.id] - process.arrival - process.burst, 0);
  return { slices, completionTimes, averageWaitingTime: totalWaitingTime / processes.length };
}

export function buildPolicyTrace(policy: SchedulerPolicy, quantum: number, processes: SchedulerProcess[] = SCHEDULER_PROCESSES): SchedulerTrace {
  if (policy === "round_robin") return buildRoundRobinTrace(quantum, processes);
  const pending = [...processes].sort((left, right) => left.arrival - right.arrival);
  const order = policy === "priority" ? [...pending].sort((left, right) => (left.burst - right.burst) || (left.arrival - right.arrival)) : pending;
  const slices: SchedulerSlice[] = [];
  const completionTimes = {} as Record<SchedulerProcess["id"], number>;
  let time = 0;
  for (const process of order) {
    time = Math.max(time, process.arrival);
    slices.push({ processId: process.id, start: time, end: time + process.burst, remaining: 0 });
    time += process.burst;
    completionTimes[process.id] = time;
  }
  const totalWaitingTime = processes.reduce((total, process) => total + completionTimes[process.id] - process.arrival - process.burst, 0);
  return { slices, completionTimes, averageWaitingTime: totalWaitingTime / processes.length };
}

function RangeControl({
  id,
  label,
  value,
  min,
  max,
  step = 1,
  output,
  help,
  onChange,
}: {
  id: string;
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  output: string;
  help?: string;
  onChange: (value: number) => void;
}) {
  const helpId = `${id}-help`;
  const decreaseLabel = `Decrease ${label}`;
  const increaseLabel = `Increase ${label}`;
  return <div className={styles.rangeControl}>
    <div className={styles.controlHeading}>
      <label htmlFor={id}>{label}</label>
      <output htmlFor={id}>{output}</output>
    </div>
    <div className={styles.rangeInputRow}>
      <button type="button" className={styles.stepButton} aria-label={decreaseLabel} disabled={value <= min} onClick={() => onChange(clampRangeValue(value - step, min, max, step))}>−</button>
      <input id={id} type="range" min={min} max={max} step={step} value={value} aria-describedby={help ? helpId : undefined} onChange={(event) => onChange(Number(event.currentTarget.value))} />
      <button type="button" className={styles.stepButton} aria-label={increaseLabel} disabled={value >= max} onClick={() => onChange(clampRangeValue(value + step, min, max, step))}>+</button>
    </div>
    {help ? <small id={helpId}>{help}</small> : null}
  </div>;
}

function Metrics({ items }: { items: Array<{ label: string; value: string; emphasis?: boolean }> }) {
  return <dl className={styles.metrics}>
    {items.map((item) => <div key={item.label} className={item.emphasis ? styles.metricEmphasis : undefined}>
      <dt>{item.label}</dt>
      <dd>{item.value}</dd>
    </div>)}
  </dl>;
}

function DspActivity({ task, onInteractionChange }: { task: TaskCopy } & WorkbenchInteractionProps) {
  const id = useId();
  const [signalFrequency, setSignalFrequency] = useState(7);
  const [sampleRate, setSampleRate] = useState(8);
  const [predictionChecked, setPredictionChecked] = useState(false);
  const state = useMemo(() => calculateSamplingState(signalFrequency, sampleRate), [signalFrequency, sampleRate]);
  const waveformPath = useMemo(() => {
    const points = Array.from({ length: 161 }, (_, index) => {
      const time = index / 160;
      const x = 18 + time * 524;
      const y = 88 - Math.sin(Math.PI * 2 * signalFrequency * time) * 58;
      return `${index ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`;
    });
    return points.join(" ");
  }, [signalFrequency]);
  const samplePoints = useMemo(() => {
    const count = Math.max(2, Math.min(37, sampleRate + 1));
    return Array.from({ length: count }, (_, index) => {
      const time = index / (count - 1);
      return {
        x: 18 + time * 524,
        y: 88 - Math.sin(Math.PI * 2 * signalFrequency * time) * 58,
      };
    });
  }, [sampleRate, signalFrequency]);
  const pointString = samplePoints.map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(" ");
  const waveformTitleId = `${id}-waveform-title`;
  const interpretation = state.isAliased
    ? `${formatNumber(state.signalFrequency)} Hz is above the ${formatNumber(state.nyquistFrequency)} Hz Nyquist limit, so these samples can look like a ${formatNumber(state.aliasFrequency)} Hz signal.`
    : `${formatNumber(state.signalFrequency)} Hz is within the ${formatNumber(state.nyquistFrequency)} Hz Nyquist limit. The samples retain a unique frequency interpretation.`;

  useEffect(() => {
    onInteractionChange?.({
      kind: "sampling",
      signalFrequency,
      sampleRate,
      nyquistFrequency: state.nyquistFrequency,
      aliasFrequency: state.aliasFrequency,
      samplesPerCycle: state.samplesPerCycle,
      isAliased: state.isAliased,
      predictionChecked,
      trace: samplePoints,
    });
  }, [onInteractionChange, predictionChecked, samplePoints, sampleRate, signalFrequency, state.aliasFrequency, state.isAliased, state.nyquistFrequency, state.samplesPerCycle]);

  return <div className={styles.activityBody}>
    <div className={styles.activityIntro}>
      <p>{task.instruction}</p>
      <span className={styles.taskHint}>Change the signal or sampling rate and use the trace as evidence.</span>
    </div>
    <div className={styles.twoColumn}>
      <div className={styles.controls}>
        <RangeControl id={`${id}-signal-frequency`} label="Signal frequency" value={signalFrequency} min={1} max={18} output={`${signalFrequency} Hz`} help="Frequency of the original continuous signal." onChange={(value) => { setSignalFrequency(value); setPredictionChecked(false); }} />
        <RangeControl id={`${id}-sample-rate`} label="Sample rate" value={sampleRate} min={2} max={36} output={`${sampleRate} samples/s`} help="Samples taken during one second of the signal." onChange={(value) => { setSampleRate(value); setPredictionChecked(false); }} />
        <Metrics items={[
          { label: "Nyquist limit", value: `${formatNumber(state.nyquistFrequency)} Hz` },
          { label: "Apparent frequency", value: `${formatNumber(state.aliasFrequency)} Hz`, emphasis: state.isAliased },
          { label: "Samples per cycle", value: formatNumber(state.samplesPerCycle, 2) },
        ]} />
        <button type="button" className={styles.secondaryButton} onClick={() => setPredictionChecked(true)}>
          {predictionChecked ? "Prediction checkpoint noted" : "Check my prediction"}
        </button>
        <p className={styles.checkpoint} aria-live="polite">{predictionChecked ? "Checkpoint noted locally. Explain why this state occurs when you submit evidence." : "Make a prediction before checking the calculated interpretation."}</p>
      </div>
      <figure className={styles.visualFigure}>
        <svg viewBox="0 0 560 176" role="img" aria-labelledby={waveformTitleId} className={styles.waveform}>
          <title id={waveformTitleId}>Continuous {signalFrequency} hertz waveform with samples taken at {sampleRate} samples per second</title>
          <line x1="18" y1="88" x2="542" y2="88" className={styles.axisLine} />
          <path d={waveformPath} className={styles.signalPath} />
          <polyline points={pointString} className={styles.sampleLine} />
          {samplePoints.map((point, index) => <circle key={`${point.x}-${index}`} cx={point.x} cy={point.y} r="4.5" className={styles.sampleDot} />)}
        </svg>
        <figcaption>Continuous signal — solid line. Captured samples — connected points.</figcaption>
      </figure>
    </div>
    <p className={state.isAliased ? styles.warning : styles.calculation} aria-live="polite"><strong>{state.isAliased ? "Aliasing detected." : "Sampling condition met."}</strong> {interpretation}</p>
  </div>;
}

function SchedulerActivity({ task, onInteractionChange }: { task: TaskCopy } & WorkbenchInteractionProps) {
  const id = useId();
  const [policy, setPolicy] = useState<SchedulerPolicy>("round_robin");
  const [quantum, setQuantum] = useState(2);
  const [predictionChecked, setPredictionChecked] = useState(false);
  const trace = useMemo(() => buildPolicyTrace(policy, quantum), [policy, quantum]);
  const traceText = trace.slices.map((slice) => `${slice.processId} ${slice.start}–${slice.end}`).join(" → ");
  const tradeoff = quantum === 1
    ? "Every process gets a quick turn, but the trace contains the most context switches."
    : quantum >= 4
      ? "The trace has fewer context switches, but later arrivals wait longer before their next turn."
      : "The trace balances interactivity with fewer context switches than a one-tick quantum.";

  useEffect(() => {
    onInteractionChange?.({
      kind: "scheduler_trace",
      policy,
      quantum,
      predictionChecked,
      contextSwitches: Math.max(0, trace.slices.length - 1),
      averageWaitingTime: trace.averageWaitingTime,
      completionTimes: trace.completionTimes,
      trace: trace.slices,
    });
  }, [onInteractionChange, policy, predictionChecked, quantum, trace]);

  return <div className={styles.activityBody}>
    <div className={styles.activityIntro}>
      <p>{task.instruction}</p>
      <span className={styles.taskHint}>Processes arrive at time 0, 1, and 2 with bursts of 5, 3, and 4 ticks.</span>
    </div>
    <div className={styles.twoColumn}>
      <div className={styles.controls}>
        <div className={styles.selectControl}>
          <label htmlFor={`${id}-policy`}>Scheduling policy</label>
          <select id={`${id}-policy`} value={policy} onChange={(event) => { setPolicy(event.currentTarget.value as SchedulerPolicy); setPredictionChecked(false); }}>
            <option value="fcfs">FCFS</option>
            <option value="round_robin">Round Robin</option>
            <option value="priority">Shortest-job priority</option>
          </select>
        </div>
        <RangeControl id={`${id}-time-quantum`} label="Round-robin time quantum" value={quantum} min={1} max={5} output={`${quantum} tick${quantum === 1 ? "" : "s"}`} help="How long a runnable process can execute before it returns to the ready queue." onChange={(value) => { setQuantum(value); setPredictionChecked(false); }} />
        <Metrics items={[
          { label: "Context switches", value: String(Math.max(0, trace.slices.length - 1)) },
          { label: "Average waiting time", value: `${formatNumber(trace.averageWaitingTime, 1)} ticks` },
          { label: "Final completion", value: `t = ${Math.max(...Object.values(trace.completionTimes))}` },
        ]} />
        <button type="button" className={styles.secondaryButton} onClick={() => setPredictionChecked(true)}>{predictionChecked ? "Trade-off checkpoint noted" : "Check the trade-off"}</button>
        <p className={styles.checkpoint} aria-live="polite">{predictionChecked ? "Checkpoint noted locally. State which process benefits and which cost rises." : "Predict which quantity changes when the quantum becomes smaller."}</p>
      </div>
      <div className={styles.schedulerVisual}>
        <div className={styles.timeline} role="list" aria-label={`Round-robin schedule: ${traceText}`}>
          {trace.slices.map((slice, index) => <div key={`${slice.processId}-${slice.start}`} role="listitem" className={`${styles.timelineSlice} ${styles[`process${slice.processId}`]}`} style={{ flexGrow: slice.end - slice.start }} aria-label={`${slice.processId}, time ${slice.start} through ${slice.end}, ${slice.remaining} ticks remaining`}>
            <strong>{slice.processId}</strong><span>{slice.start}–{slice.end}</span>
          </div>)}
        </div>
        <p className={styles.timelineCaption}>Execution order: {traceText}</p>
        <div className={styles.traceTableWrap}>
          <table className={styles.traceTable}>
            <caption>Process completion times for the current round-robin trace</caption>
            <thead><tr><th scope="col">Process</th><th scope="col">Arrival</th><th scope="col">Burst</th><th scope="col">Complete</th></tr></thead>
            <tbody>{SCHEDULER_PROCESSES.map((process) => <tr key={process.id}><th scope="row">{process.id}</th><td>{process.arrival}</td><td>{process.burst}</td><td>{trace.completionTimes[process.id]}</td></tr>)}</tbody>
          </table>
        </div>
      </div>
    </div>
    <p className={styles.calculation} aria-live="polite"><strong>Observed trade-off.</strong> {tradeoff}</p>
  </div>;
}

export function resolveOperatingSystemsTopic(value: string): OperatingSystemsTopic {
  const cues = normalizedText(value);
  if (/(virtual memory|page replacement|page fault|working set|paging)/.test(cues)) return "memory";
  if (/(deadlock|resource allocation|wait for graph)/.test(cues)) return "deadlock";
  if (/(system call|instruction trace|kernel transition|syscall)/.test(cues)) return "system_call";
  return "scheduling";
}

type PagePolicy = "fifo" | "lru";

function pageReplacementTrace(referenceString: number[], capacity: number, policy: PagePolicy) {
  const frames: number[] = [];
  const lastSeen = new Map<number, number>();
  let faults = 0;
  const trace = referenceString.map((page, index) => {
    const hit = frames.includes(page);
    if (!hit) {
      faults += 1;
      if (frames.length < capacity) frames.push(page);
      else if (policy === "fifo") frames.shift(), frames.push(page);
      else {
        const victim = frames.reduce((oldest, candidate) => (lastSeen.get(candidate) ?? -1) < (lastSeen.get(oldest) ?? -1) ? candidate : oldest, frames[0]);
        frames[frames.indexOf(victim)] = page;
      }
    }
    lastSeen.set(page, index);
    return { step: index + 1, page, hit, fault: !hit, frames: [...frames] };
  });
  return { faults, trace };
}

function MemoryActivity({ task, onInteractionChange }: { task: TaskCopy } & WorkbenchInteractionProps) {
  const id = useId();
  const [capacity, setCapacity] = useState(3);
  const [policy, setPolicy] = useState<PagePolicy>("lru");
  const [predictionChecked, setPredictionChecked] = useState(false);
  const result = useMemo(() => pageReplacementTrace(PAGE_REFERENCE_STRING, capacity, policy), [capacity, policy]);
  useEffect(() => {
    onInteractionChange?.({ kind: "page_replacement", policy, frameCapacity: capacity, referenceString: PAGE_REFERENCE_STRING, pageFaults: result.faults, predictionChecked, trace: result.trace });
  }, [capacity, onInteractionChange, policy, predictionChecked, result]);
  return <div className={styles.activityBody}>
    <div className={styles.activityIntro}><p>{task.instruction}</p><span className={styles.taskHint}>Reference string: {PAGE_REFERENCE_STRING.join(" , ")}. Predict the fault pattern before revealing the trace.</span></div>
    <div className={styles.twoColumn}><div className={styles.controls}>
      <RangeControl id={`${id}-frame-capacity`} label="Frame capacity" value={capacity} min={2} max={5} output={`${capacity} frames`} onChange={(value) => { setCapacity(value); setPredictionChecked(false); }} />
      <div className={styles.selectControl}><label htmlFor={`${id}-page-policy`}>Replacement policy</label><select id={`${id}-page-policy`} value={policy} onChange={(event) => { setPolicy(event.currentTarget.value as PagePolicy); setPredictionChecked(false); }}><option value="fifo">FIFO</option><option value="lru">LRU</option></select></div>
      <Metrics items={[{ label: "Page faults", value: String(result.faults), emphasis: true }, { label: "Hits", value: String(PAGE_REFERENCE_STRING.length - result.faults) }, { label: "Working set", value: `${new Set(PAGE_REFERENCE_STRING).size} pages` }]} />
      <button type="button" className={styles.secondaryButton} onClick={() => setPredictionChecked(true)}>{predictionChecked ? "Fault prediction noted" : "Check fault prediction"}</button>
      <p className={styles.checkpoint} aria-live="polite">{predictionChecked ? "Checkpoint noted. Explain why the policy changes which page is evicted." : "Predict the first eviction before checking the trace."}</p>
    </div><div className={styles.traceTableWrap}><table className={styles.traceTable}><caption>{policy.toUpperCase()} page replacement trace</caption><thead><tr><th>Step</th><th>Page</th><th>Frames</th><th>Result</th></tr></thead><tbody>{result.trace.map((row) => <tr key={row.step}><th scope="row">{row.step}</th><td>{row.page}</td><td>{row.frames.join(" | ")}</td><td>{row.fault ? "page fault" : "hit"}</td></tr>)}</tbody></table></div></div>
    <p className={styles.calculation}><strong>Observed memory behavior.</strong> {result.faults} faults occur for this bounded reference string; relate each fault to the working set and replacement policy.</p>
  </div>;
}

function DeadlockActivity({ task, onInteractionChange }: { task: TaskCopy } & WorkbenchInteractionProps) {
  const id = useId();
  const [request, setRequest] = useState("P1-R2");
  const [predictionChecked, setPredictionChecked] = useState(false);
  const safe = request === "P1-R2";
  const trace = useMemo(() => safe ? ["P1 holds R1", "P1 requests R2", "R2 is available", "P1 completes and releases R1/R2"] : ["P1 holds R1", "P2 holds R2", "P1 requests R2", "P2 requests R1", "cycle detected: unsafe allocation"], [safe]);
  useEffect(() => { onInteractionChange?.({ kind: "deadlock_resource_graph", request, safe, predictionChecked, trace }); }, [onInteractionChange, predictionChecked, request, safe, trace]);
  return <div className={styles.activityBody}><div className={styles.activityIntro}><p>{task.instruction}</p><span className={styles.taskHint}>Two processes and two single-instance resources form a bounded allocation graph.</span></div><div className={styles.twoColumn}><div className={styles.controls}><div className={styles.selectControl}><label htmlFor={`${id}-request`}>Next resource request</label><select id={`${id}-request`} value={request} onChange={(event) => { setRequest(event.currentTarget.value); setPredictionChecked(false); }}><option value="P1-R2">P1 requests R2</option><option value="P2-R1">P2 requests R1</option></select></div><button type="button" className={styles.secondaryButton} onClick={() => setPredictionChecked(true)}>{predictionChecked ? "Safety prediction noted" : "Check safety prediction"}</button><p className={styles.checkpoint} aria-live="polite">{predictionChecked ? safe ? "No cycle is formed in this bounded graph." : "The wait-for cycle is a deadlock candidate." : "Predict whether the request creates a cycle."}</p></div><div className={styles.traceTableWrap}><table className={styles.traceTable}><caption>Resource-allocation trace</caption><tbody>{trace.map((step, index) => <tr key={`${index}-${step}`}><th scope="row">{index + 1}</th><td>{step}</td></tr>)}</tbody></table></div></div><p className={safe ? styles.calculation : styles.warning}><strong>{safe ? "Safe allocation." : "Deadlock risk."}</strong> {safe ? "The available resource breaks the cycle." : "A wait-for cycle means neither process can make progress without intervention."}</p></div>;
}

function HistoryEvidenceActivity({ task, onInteractionChange }: { task: TaskCopy } & WorkbenchInteractionProps) {
  const [timeline, setTimeline] = useState<string[]>(["Fiscal pressure", "Popular mobilization", "Institutional change"]);
  const [sourceStance, setSourceStance] = useState("secondary");
  const [checked, setChecked] = useState(false);
  useEffect(() => {
    onInteractionChange?.({ kind: "historical_evidence_map", timeline, actors: { pressure: "institutions", mobilization: "public", change: "authority" }, sourceStance, predictionChecked: checked });
  }, [checked, onInteractionChange, sourceStance, timeline]);
  function move(index: number, direction: -1 | 1) {
    const next = [...timeline];
    const target = index + direction;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    setTimeline(next);
    setChecked(false);
  }
  return <div className={styles.activityBody}>
    <div className={styles.activityIntro}><p>{task.instruction}</p><span className={styles.taskHint}>Separate what happened, who acted, and what the selected source can actually support.</span></div>
    <div className={styles.twoColumn}>
      <div className={styles.controls}>
        <div className={styles.selectControl}><label htmlFor="history-source-stance">Source stance</label><select id="history-source-stance" value={sourceStance} onChange={(event) => { setSourceStance(event.currentTarget.value); setChecked(false); }}><option value="primary">Primary source</option><option value="secondary">Secondary source</option><option value="uncertain">Stance uncertain</option></select></div>
        <button type="button" className={styles.secondaryButton} onClick={() => setChecked(true)}>{checked ? "Evidence map checkpoint noted" : "Check the evidence map"}</button>
        <p className={styles.checkpoint} aria-live="polite">{checked ? "Checkpoint noted. Explain which link is evidence and which link is your interpretation." : "Reorder the timeline, then predict which relationship the source can support."}</p>
      </div>
      <div className={styles.traceTableWrap}><table className={styles.traceTable}><caption>Bounded historical sequence</caption><thead><tr><th scope="col">Order</th><th scope="col">Event</th><th scope="col">Move</th></tr></thead><tbody>{timeline.map((event, index) => <tr key={event}><th scope="row">{index + 1}</th><td>{event}</td><td><button type="button" className={styles.secondaryButton} onClick={() => move(index, -1)} disabled={index === 0} aria-label={`Move ${event} earlier`}>↑</button><button type="button" className={styles.secondaryButton} onClick={() => move(index, 1)} disabled={index === timeline.length - 1} aria-label={`Move ${event} later`}>↓</button></td></tr>)}</tbody></table></div>
    </div>
    <p className={styles.calculation}><strong>Interpretation boundary.</strong> This map records a chronology and source stance; it does not prove that one event alone caused the next.</p>
  </div>;
}

function SystemCallActivity({ task, onInteractionChange }: { task: TaskCopy } & WorkbenchInteractionProps) {
  const id = useId();
  const [call, setCall] = useState("read");
  const [pageFault, setPageFault] = useState(false);
  const [predictionChecked, setPredictionChecked] = useState(false);
  const trace = useMemo(() => ["user instruction", `trap: ${call}()`, ...(pageFault ? ["page fault", "kernel resolves page"] : []), "kernel validates arguments", "return to user mode"], [call, pageFault]);
  useEffect(() => { onInteractionChange?.({ kind: "system_call_trace", systemCall: call, pageFault, predictionChecked, trace }); }, [call, onInteractionChange, pageFault, predictionChecked, trace]);
  return <div className={styles.activityBody}><div className={styles.activityIntro}><p>{task.instruction}</p><span className={styles.taskHint}>Follow the user-to-kernel transition and identify where a fault changes the trace.</span></div><div className={styles.twoColumn}><div className={styles.controls}><div className={styles.selectControl}><label htmlFor={`${id}-syscall`}>System call</label><select id={`${id}-syscall`} value={call} onChange={(event) => { setCall(event.currentTarget.value); setPredictionChecked(false); }}><option value="read">read</option><option value="write">write</option><option value="fork">fork</option></select></div><label className={styles.checkboxControl}><input type="checkbox" checked={pageFault} onChange={(event) => { setPageFault(event.currentTarget.checked); setPredictionChecked(false); }} /> Inject a page fault</label><button type="button" className={styles.secondaryButton} onClick={() => setPredictionChecked(true)}>{predictionChecked ? "Trace prediction noted" : "Check trace prediction"}</button></div><div className={styles.traceTableWrap}><table className={styles.traceTable}><caption>System-call instruction trace</caption><tbody>{trace.map((step, index) => <tr key={`${index}-${step}`}><th scope="row">{index + 1}</th><td>{step}</td></tr>)}</tbody></table></div></div><p className={styles.calculation}><strong>Observable boundary.</strong> A system call crosses privilege levels; a page fault inserts a kernel-managed recovery step.</p></div>;
}

type GraphicsTopic = "transform" | "rasterization" | "lighting" | "depth" | "sampling";

export function resolveGraphicsTopic(value: string): GraphicsTopic {
  const cues = normalizedText(value);
  if (/(lighting|shading|light)/.test(cues)) return "lighting";
  if (/(depth|z buffer|z-buffer)/.test(cues)) return "depth";
  if (/(clip|raster)/.test(cues)) return "rasterization";
  if (/(texture|sampling|alias)/.test(cues)) return "sampling";
  return "transform";
}

function RenderingActivity({ task, topic, onInteractionChange }: { task: TaskCopy; topic: Exclude<GraphicsTopic, "transform"> } & WorkbenchInteractionProps) {
  const id = useId();
  const [light, setLight] = useState(0.7);
  const [depth, setDepth] = useState(0.45);
  const [clip, setClip] = useState(0.5);
  const [samples, setSamples] = useState(2);
  const [predictionChecked, setPredictionChecked] = useState(false);
  const result = topic === "lighting" ? `diffuse response ${Math.round(light * (1 - depth) * 100)}%` : topic === "depth" ? (depth < 0.5 ? "front object wins depth test" : "far object is occluded") : topic === "rasterization" ? `${Math.round(clip * 100)}% of the triangle remains after clipping` : `${samples} samples/pixel; ${samples < 4 ? "aliasing remains visible" : "edges are more stable"}`;
  useEffect(() => { onInteractionChange?.({ kind: `graphics_${topic}`, topic, lightIntensity: light, objectDepth: depth, clipPlane: clip, samplesPerPixel: samples, predictionChecked, result }); }, [clip, depth, light, onInteractionChange, predictionChecked, result, samples, topic]);
  return <div className={styles.activityBody}><div className={styles.activityIntro}><p>{task.instruction}</p><span className={styles.taskHint}>Change one rendering variable, predict the visible consequence, then inspect the bounded calculation.</span></div><div className={styles.twoColumn}><div className={styles.controls}>{topic === "lighting" ? <RangeControl id={`${id}-light`} label="Light intensity" value={light} min={0} max={1} step={0.1} output={light.toFixed(1)} onChange={(value) => { setLight(value); setPredictionChecked(false); }} /> : null}{topic === "depth" ? <RangeControl id={`${id}-depth`} label="Object depth" value={depth} min={0} max={1} step={0.05} output={depth.toFixed(2)} onChange={(value) => { setDepth(value); setPredictionChecked(false); }} /> : null}{topic === "rasterization" ? <RangeControl id={`${id}-clip`} label="Clip plane" value={clip} min={0} max={1} step={0.05} output={`${Math.round(clip * 100)}%`} onChange={(value) => { setClip(value); setPredictionChecked(false); }} /> : null}{topic === "sampling" ? <RangeControl id={`${id}-samples`} label="Samples per pixel" value={samples} min={1} max={8} output={String(samples)} onChange={(value) => { setSamples(value); setPredictionChecked(false); }} /> : null}<button type="button" className={styles.secondaryButton} onClick={() => setPredictionChecked(true)}>{predictionChecked ? "Rendering prediction noted" : "Check rendering prediction"}</button><p className={styles.checkpoint} aria-live="polite">{predictionChecked ? `Observed result: ${result}. Explain the causal change.` : "Predict the visible result before checking."}</p></div><div className={styles.visualFigure}><div className={styles.calculation}><strong>{topic.replace("_", " ")}</strong><p>{result}</p><small>Bounded local renderer model; use the observed parameter and result in your explanation.</small></div></div></div></div>;
}

function SceneGrid() {
  return <g aria-hidden="true">
    {Array.from({ length: 9 }, (_, index) => <line key={`vertical-${index}`} x1={40 + index * 40} y1="24" x2={40 + index * 40} y2="216" className={styles.gridLine} />)}
    {Array.from({ length: 5 }, (_, index) => <line key={`horizontal-${index}`} x1="24" y1={40 + index * 40} x2="376" y2={40 + index * 40} className={styles.gridLine} />)}
    <line x1="24" y1="120" x2="376" y2="120" className={styles.axisLine} />
    <line x1="200" y1="24" x2="200" y2="216" className={styles.axisLine} />
  </g>;
}

function SceneObject({ translateX, rotation, scale }: { translateX: number; rotation: number; scale: number }) {
  return <g transform={`translate(${translateX} 0) rotate(${rotation} 200 120) scale(${scale} ${scale})`}>
    <rect x="166" y="84" width="68" height="68" rx="4" className={styles.sceneObject} />
    <circle cx="215" cy="103" r="8" className={styles.sceneDetail} />
    <line x1="180" y1="138" x2="220" y2="98" className={styles.sceneDetailLine} />
  </g>;
}

function GraphicsActivity({ task, onInteractionChange }: { task: TaskCopy } & WorkbenchInteractionProps) {
  const id = useId();
  const [translateX, setTranslateX] = useState(24);
  const [rotation, setRotation] = useState(18);
  const [scale, setScale] = useState(1);
  const [cameraZoom, setCameraZoom] = useState(1.2);
  const [predictionChecked, setPredictionChecked] = useState(false);
  const cameraWidth = 300 / cameraZoom;
  const cameraHeight = 180 / cameraZoom;
  const cameraX = 200 - cameraWidth / 2;
  const cameraY = 120 - cameraHeight / 2;
  useEffect(() => {
    onInteractionChange?.({
      kind: "transform_camera",
      translation: { x: translateX, y: 0 },
      rotation,
      scale,
      cameraZoom,
      predictionChecked,
      cameraFrame: { width: cameraWidth, height: cameraHeight, x: cameraX, y: cameraY },
    });
  }, [cameraHeight, cameraWidth, cameraX, cameraY, cameraZoom, onInteractionChange, predictionChecked, rotation, scale, translateX]);
  const objectState = `x ${translateX >= 0 ? "+" : ""}${translateX}, ${rotation >= 0 ? "+" : ""}${rotation}°, scale ${formatNumber(scale, 2)}`;

  return <div className={styles.activityBody}>
    <div className={styles.activityIntro}>
      <p>{task.instruction}</p>
      <span className={styles.taskHint}>The left scene is world space. The right frame is what the camera sees.</span>
    </div>
    <div className={styles.graphicsLayout}>
      <div className={styles.controls}>
        <RangeControl id={`${id}-translate-x`} label="Object translation, x" value={translateX} min={-80} max={80} output={`${translateX}px`} onChange={(value) => { setTranslateX(value); setPredictionChecked(false); }} />
        <RangeControl id={`${id}-rotation`} label="Object rotation" value={rotation} min={-90} max={90} output={`${rotation}°`} onChange={(value) => { setRotation(value); setPredictionChecked(false); }} />
        <RangeControl id={`${id}-scale`} label="Object scale" value={scale} min={0.5} max={1.6} step={0.1} output={`${formatNumber(scale, 1)}×`} onChange={(value) => { setScale(value); setPredictionChecked(false); }} />
        <RangeControl id={`${id}-camera-zoom`} label="Camera zoom" value={cameraZoom} min={0.7} max={2.4} step={0.1} output={`${formatNumber(cameraZoom, 1)}×`} onChange={(value) => { setCameraZoom(value); setPredictionChecked(false); }} />
        <button type="button" className={styles.secondaryButton} onClick={() => setPredictionChecked(true)}>{predictionChecked ? "Viewpoint checkpoint noted" : "Check the viewpoint"}</button>
        <p className={styles.checkpoint} aria-live="polite">{predictionChecked ? "Checkpoint noted locally. Explain whether the change came from the object, camera, or both." : "Predict what changes in camera space before moving a control."}</p>
      </div>
      <div className={styles.scenePair}>
        <figure className={styles.sceneFigure}>
          <svg viewBox="0 0 400 240" role="img" aria-label={`World space with an object at ${objectState}; the dashed rectangle is the camera frame.`}>
            <SceneGrid />
            <SceneObject translateX={translateX} rotation={rotation} scale={scale} />
            <rect x={cameraX} y={cameraY} width={cameraWidth} height={cameraHeight} className={styles.cameraFrame} />
          </svg>
          <figcaption>World space</figcaption>
        </figure>
        <figure className={styles.sceneFigure}>
          <svg viewBox={`${cameraX} ${cameraY} ${cameraWidth} ${cameraHeight}`} role="img" aria-label={`Camera view at ${formatNumber(cameraZoom, 1)} times zoom of the transformed object.`}>
            <SceneGrid />
            <SceneObject translateX={translateX} rotation={rotation} scale={scale} />
          </svg>
          <figcaption>Camera view · {formatNumber(cameraZoom, 1)}×</figcaption>
        </figure>
      </div>
    </div>
    <p className={styles.calculation} aria-live="polite"><strong>Current transform.</strong> Object: {objectState}. Camera framing: {formatNumber(cameraWidth, 0)} × {formatNumber(cameraHeight, 0)} world units.</p>
  </div>;
}

function classifyExample(example: (typeof ML_EXAMPLES)[number], threshold: number) {
  const predicted = example.confidence >= threshold ? "positive" : "negative";
  if (predicted === "positive" && example.actual === "positive") return { ...example, predicted, result: "true positive" };
  if (predicted === "positive") return { ...example, predicted, result: "false positive" };
  if (example.actual === "positive") return { ...example, predicted, result: "false negative" };
  return { ...example, predicted, result: "true negative" };
}

function MachineLearningActivity({ task, onInteractionChange }: { task: TaskCopy } & WorkbenchInteractionProps) {
  const id = useId();
  const [threshold, setThreshold] = useState(0.65);
  const [slice, setSlice] = useState<MlSlice>("all");
  const [split, setSplit] = useState("stratified");
  const [regularization, setRegularization] = useState(0.2);
  const [errorsOnly, setErrorsOnly] = useState(false);
  const reviewed = ML_EXAMPLES.filter((example) => slice === "all" || example.slice === slice).map((example) => classifyExample(example, threshold));
  const visibleRows = errorsOnly ? reviewed.filter((example) => example.result.startsWith("false")) : reviewed;
  const matrix = reviewed.reduce((totals, example) => {
    if (example.result === "true positive") totals.truePositive += 1;
    if (example.result === "false positive") totals.falsePositive += 1;
    if (example.result === "false negative") totals.falseNegative += 1;
    if (example.result === "true negative") totals.trueNegative += 1;
    return totals;
  }, { truePositive: 0, falsePositive: 0, falseNegative: 0, trueNegative: 0 });
  const precision = matrix.truePositive + matrix.falsePositive ? matrix.truePositive / (matrix.truePositive + matrix.falsePositive) : 0;
  const recall = matrix.truePositive + matrix.falseNegative ? matrix.truePositive / (matrix.truePositive + matrix.falseNegative) : 0;
  const errors = matrix.falsePositive + matrix.falseNegative;
  const leakage = split === "leaky";
  const reportedPrecision = Math.min(1, precision + (leakage ? 0.12 : 0));
  const reportedRecall = Math.min(1, recall + (leakage ? 0.08 : 0));
  useEffect(() => {
    onInteractionChange?.({
      kind: "classification_threshold",
      threshold,
      slice,
      split,
      regularization,
      leakage,
      errorsOnly,
      confusionMatrix: matrix,
      precision: reportedPrecision,
      recall: reportedRecall,
      errors,
      inspectedExampleIds: visibleRows.map((example) => example.id),
    });
  }, [errors, errorsOnly, leakage, matrix, onInteractionChange, regularization, reportedPrecision, reportedRecall, slice, split, threshold, visibleRows]);

  return <div className={styles.activityBody}>
    <div className={styles.activityIntro}>
      <p>{task.instruction}</p>
      <span className={styles.taskHint}>This compact synthetic set is for inspecting decisions, not for scoring a learner.</span>
    </div>
    <div className={styles.twoColumn}>
      <div className={styles.controls}>
        <RangeControl id={`${id}-threshold`} label="Positive-decision threshold" value={threshold} min={0.2} max={0.9} step={0.05} output={threshold.toFixed(2)} help="Scores at or above this threshold are labelled positive." onChange={setThreshold} />
        <div className={styles.selectControl}><label htmlFor={`${id}-split`}>Dataset split</label><select id={`${id}-split`} value={split} onChange={(event) => setSplit(event.currentTarget.value)}><option value="stratified">Stratified holdout</option><option value="random">Random holdout</option><option value="leaky">Leaky split (inspect this)</option></select></div>
        <RangeControl id={`${id}-regularization`} label="Regularization" value={regularization} min={0} max={1} step={0.1} output={regularization.toFixed(1)} onChange={setRegularization} />
        <div className={styles.selectControl}>
          <label htmlFor={`${id}-slice`}>Review data slice</label>
          <select id={`${id}-slice`} value={slice} onChange={(event) => setSlice(event.currentTarget.value as MlSlice)}>
            <option value="all">All examples</option>
            <option value="clear">Clear inputs</option>
            <option value="low_light">Low-light inputs</option>
            <option value="occluded">Occluded inputs</option>
            <option value="rare_class">Rare-class inputs</option>
          </select>
        </div>
        <fieldset className={styles.radioGroup}>
          <legend>Rows to inspect</legend>
          <label><input type="radio" name={`${id}-rows`} checked={!errorsOnly} onChange={() => setErrorsOnly(false)} /> All selected decisions</label>
          <label><input type="radio" name={`${id}-rows`} checked={errorsOnly} onChange={() => setErrorsOnly(true)} /> Errors only</label>
        </fieldset>
        <Metrics items={[
          { label: "Precision", value: `${Math.round(reportedPrecision * 100)}%` },
          { label: "Recall", value: `${Math.round(reportedRecall * 100)}%` },
          { label: "Errors in slice", value: `${errors} of ${reviewed.length}`, emphasis: errors > 0 },
        ]} />
      </div>
      <div className={styles.mlVisual}>
        <div className={styles.matrix} aria-label={`Confusion matrix: ${matrix.truePositive} true positives, ${matrix.falsePositive} false positives, ${matrix.falseNegative} false negatives, and ${matrix.trueNegative} true negatives`}>
          <span>Actual / predicted</span><strong>Positive</strong><strong>Negative</strong>
          <strong>Positive</strong><span><b>{matrix.truePositive}</b><small>True positive</small></span><span><b>{matrix.falseNegative}</b><small>False negative</small></span>
          <strong>Negative</strong><span><b>{matrix.falsePositive}</b><small>False positive</small></span><span><b>{matrix.trueNegative}</b><small>True negative</small></span>
        </div>
        <div className={styles.traceTableWrap}>
          <table className={styles.traceTable}>
            <caption>Model decisions for the selected review slice</caption>
            <thead><tr><th scope="col">Item</th><th scope="col">Score</th><th scope="col">Decision</th><th scope="col">Analysis</th></tr></thead>
            <tbody>{visibleRows.length ? visibleRows.map((example) => <tr key={example.id}><th scope="row">{example.id}</th><td>{example.confidence.toFixed(2)}</td><td>{example.predicted}</td><td>{example.result}</td></tr>) : <tr><td colSpan={4}>No errors occur in this slice at the selected threshold.</td></tr>}</tbody>
          </table>
        </div>
      </div>
    </div>
    <p className={errors || leakage ? styles.warning : styles.calculation} aria-live="polite"><strong>{leakage ? "Leakage detected." : errors ? "Error pattern to inspect." : "No decision errors in this slice."}</strong> {leakage ? "The apparent metric gain is not valid evidence; rebuild the split before claiming generalization." : errors ? "Compare the false decisions by input slice before changing the model or threshold." : "Change the threshold, regularization, or review slice to test whether this holds elsewhere."}</p>
  </div>;
}

function CaseAnalysisActivity({ task, kind, onInteractionChange }: { task: TaskCopy; kind: "medicine" | "finance" } & WorkbenchInteractionProps) {
  const id = useId();
  const [claim, setClaim] = useState("");
  const [anchor, setAnchor] = useState("");
  const [limitation, setLimitation] = useState("");
  const [stance, setStance] = useState("uncertain");
  const [reviewed, setReviewed] = useState(false);
  const medicine = kind === "medicine";
  const scenario = medicine
    ? "A paper reports a change in an outcome for its studied population. Identify what the study supports, its source anchor, and a limitation before discussing transfer." 
    : "A company report describes a change in a financial metric. Identify what the report supports, its source anchor, and a limitation before discussing an interpretation.";
  const disclaimer = medicine
    ? "Academic, source-cited case analysis only. This workbench cannot diagnose, treat, or guide a personal health decision."
    : "Academic, source-cited case analysis only. This workbench cannot recommend a trade, investment, or other personal financial decision.";
  const complete = claim.trim().length > 12 && anchor.trim().length > 3 && limitation.trim().length > 12;
  useEffect(() => {
    onInteractionChange?.({
      kind: medicine ? "medical_case_analysis" : "finance_case_analysis",
      boundedClaim: claim,
      sourceAnchor: anchor,
      limitation,
      stance,
      reviewed,
      complete,
      requiresSourceVerification: medicine,
    });
  }, [anchor, claim, complete, limitation, medicine, onInteractionChange, reviewed, stance]);

  return <div className={styles.activityBody}>
    <div className={styles.disclaimer} role="note">
      <strong>{medicine ? "Medical education boundary" : "Finance education boundary"}</strong>
      <p>{disclaimer}</p>
    </div>
    <div className={styles.activityIntro}>
      <p>{task.instruction}</p>
      <span className={styles.taskHint}>{scenario}</span>
    </div>
    <div className={styles.caseGrid}>
      <div className={styles.casePrompt}>
        <span className={styles.kicker}>Case-analysis sequence</span>
        <ol>
          <li>State only the bounded claim made by the source.</li>
          <li>Point to the page, table, or block that supports it.</li>
          <li>Name a limitation or condition that blocks a broader conclusion.</li>
        </ol>
        <label htmlFor={`${id}-stance`}>Current academic reading</label>
        <select id={`${id}-stance`} value={stance} onChange={(event) => setStance(event.currentTarget.value)}>
          <option value="supported">Supported within the stated source boundary</option>
          <option value="uncertain">Uncertain — needs more source review</option>
          <option value="insufficient">Insufficient support for the stated claim</option>
        </select>
      </div>
      <div className={styles.caseFields}>
        <label htmlFor={`${id}-claim`}>Bounded source claim</label>
        <textarea id={`${id}-claim`} value={claim} onChange={(event) => { setClaim(event.currentTarget.value); setReviewed(false); }} placeholder="Write what the source says, without extending it to an individual decision." />
        <label htmlFor={`${id}-anchor`}>Source anchor</label>
        <input id={`${id}-anchor`} value={anchor} onChange={(event) => { setAnchor(event.currentTarget.value); setReviewed(false); }} placeholder="e.g. p. 6, Table 2, or block 14" />
        <label htmlFor={`${id}-limitation`}>Limitation or missing condition</label>
        <textarea id={`${id}-limitation`} value={limitation} onChange={(event) => { setLimitation(event.currentTarget.value); setReviewed(false); }} placeholder="Name what the evidence does not establish." />
        <button type="button" className={styles.secondaryButton} onClick={() => setReviewed(true)}>Check analysis structure</button>
        <p className={styles.checkpoint} aria-live="polite">{reviewed ? complete ? `Structure complete: ${stance.replace("_", " ")}. Keep the conclusion inside the cited academic boundary.` : "Add a bounded claim, source anchor, and limitation before treating the analysis as ready for review." : "This local check does not create evidence or advice."}</p>
      </div>
    </div>
  </div>;
}

function GeneralActivity({ task, goalTitle, onInteractionChange }: { task: TaskCopy; goalTitle: string } & WorkbenchInteractionProps) {
  const id = useId();
  const [attempt, setAttempt] = useState("");
  const [checked, setChecked] = useState(false);
  useEffect(() => {
    onInteractionChange?.({ kind: "general_observable_attempt", draft: attempt, checked, substantive: attempt.trim().length >= 40 });
  }, [attempt, checked, onInteractionChange]);
  return <div className={styles.activityBody}>
    <div className={styles.activityIntro}>
      <p>{task.instruction}</p>
      <span className={styles.taskHint}>Use a concrete example, a changed condition, and a causal explanation.</span>
    </div>
    <div className={styles.generalPrompt}>
      <span className={styles.kicker}>Observable attempt</span>
      <h3>{goalTitle || "Your learning goal"}</h3>
      <p>Describe what you predict or can now do, then name the observation that would prove or disprove it.</p>
      <label htmlFor={`${id}-attempt`}>Working explanation</label>
      <textarea id={`${id}-attempt`} value={attempt} onChange={(event) => { setAttempt(event.currentTarget.value); setChecked(false); }} placeholder="Write an explanation or a plan for a testable attempt." />
      <button type="button" className={styles.secondaryButton} onClick={() => setChecked(true)}>Check attempt structure</button>
      <p className={styles.checkpoint} aria-live="polite">{checked ? attempt.trim().length >= 40 ? "This is a substantive local draft. Submit the observable result separately to record evidence." : "Add a concrete prediction, action, or observation before treating this as an attempt." : "A draft is not evidence until an observable attempt is submitted."}</p>
    </div>
  </div>;
}

export function DomainActivityWorkbench({ domain, goalTitle, activityType, configuration, onInteractionChange }: DomainActivityWorkbenchProps) {
  const workbenchDomain = resolveWorkbenchDomain(domain, goalTitle);
  const operatingSystemsTopic = resolveOperatingSystemsTopic(configuration?.concept || goalTitle);
  const graphicsTopic = resolveGraphicsTopic(configuration?.concept || goalTitle);
  const task = { ...activityCopy(activityType), instruction: configuration?.taskPrompt || activityCopy(activityType).instruction };
  const activityTitleId = useId();
  const domainLabel: Record<WorkbenchDomain, string> = {
    dsp: "Signal sampling lab",
    history: "Historical evidence map",
    operating_systems: "Scheduler trace",
    graphics: "Transform and camera lab",
    machine_learning: "Error-analysis lab",
    medicine: "Academic case analysis",
    finance: "Academic case analysis",
    general: "Active practice workbench",
  };

  return <section className={styles.workbench} aria-labelledby={activityTitleId}>
    <header className={styles.header}>
      <div>
        <span className={styles.kicker}>{domainLabel[workbenchDomain]}</span>
        <h2 id={activityTitleId}>{task.action}</h2>
      </div>
      <span className={styles.activityType}>{humanizeActivityType(activityType)}</span>
    </header>
    {workbenchDomain === "dsp" ? <DspActivity task={task} onInteractionChange={onInteractionChange} /> : null}
    {workbenchDomain === "history" ? <HistoryEvidenceActivity task={task} onInteractionChange={onInteractionChange} /> : null}
    {workbenchDomain === "operating_systems" && operatingSystemsTopic === "scheduling" ? <SchedulerActivity task={task} onInteractionChange={onInteractionChange} /> : null}
    {workbenchDomain === "operating_systems" && operatingSystemsTopic === "memory" ? <MemoryActivity task={task} onInteractionChange={onInteractionChange} /> : null}
    {workbenchDomain === "operating_systems" && operatingSystemsTopic === "deadlock" ? <DeadlockActivity task={task} onInteractionChange={onInteractionChange} /> : null}
    {workbenchDomain === "operating_systems" && operatingSystemsTopic === "system_call" ? <SystemCallActivity task={task} onInteractionChange={onInteractionChange} /> : null}
    {workbenchDomain === "graphics" && graphicsTopic === "transform" ? <GraphicsActivity task={task} onInteractionChange={onInteractionChange} /> : null}
    {workbenchDomain === "graphics" && graphicsTopic !== "transform" ? <RenderingActivity task={task} topic={graphicsTopic} onInteractionChange={onInteractionChange} /> : null}
    {workbenchDomain === "machine_learning" ? <MachineLearningActivity task={task} onInteractionChange={onInteractionChange} /> : null}
    {workbenchDomain === "medicine" ? <CaseAnalysisActivity task={task} kind="medicine" onInteractionChange={onInteractionChange} /> : null}
    {workbenchDomain === "finance" ? <CaseAnalysisActivity task={task} kind="finance" onInteractionChange={onInteractionChange} /> : null}
    {workbenchDomain === "general" ? <GeneralActivity task={task} goalTitle={goalTitle} onInteractionChange={onInteractionChange} /> : null}
  </section>;
}
