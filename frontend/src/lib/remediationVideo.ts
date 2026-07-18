/*
 * Adapted from THU-MAIC/OpenMAIC, commit 34448beb6ce764ec2bc8ceb1d6ed519c37fa6184, MIT License.
 * This is the server-side remediation-video slice used by Feynman-AI.
 * It follows OpenMAIC's provider -> normalize -> submit -> poll -> sequence
 * pipeline without exposing provider credentials to the browser.
 */

export type RemediationVideoRequest = {
  topicTitle: string;
  stageKind: string;
  mistake: string;
  correctAnswer: string;
  correction: string;
  remediation?: string;
  sourceContext: string;
  requestedDurationSeconds?: number;
};

export type RemediationVideoClip = {
  index: number;
  title: string;
  url: string;
  duration: number;
  width: number;
  height: number;
  poster?: string;
  narration?: {
    dataUrl: string;
    format: string;
    providerId: string;
    text: string;
  };
};

export type RemediationVideoLesson = {
  mode: "sequenced_clips";
  title: string;
  requestedDurationSeconds: number;
  actualDurationSeconds: number;
  providerId: string;
  clips: RemediationVideoClip[];
};

type VideoProviderId = "seedance";
type VideoAspectRatio = "16:9" | "4:3" | "1:1" | "9:16" | "3:4" | "21:9";
type VideoResolution = "480p" | "720p" | "1080p";

type VideoProviderConfig = {
  id: VideoProviderId;
  name: string;
  defaultBaseUrl: string;
  models: string[];
  supportedAspectRatios: VideoAspectRatio[];
  supportedDurations: number[];
  supportedResolutions: VideoResolution[];
  maxDuration: number;
};

type VideoGenerationConfig = {
  providerId: VideoProviderId;
  apiKey: string;
  baseUrl?: string;
  model?: string;
};

type VideoGenerationOptions = {
  prompt: string;
  duration?: number;
  aspectRatio?: VideoAspectRatio;
  resolution?: VideoResolution;
};

type VideoGenerationResult = {
  url: string;
  duration: number;
  width: number;
  height: number;
  poster?: string;
};

const VIDEO_PROVIDERS: Record<VideoProviderId, VideoProviderConfig> = {
  seedance: {
    id: "seedance",
    name: "Seedance",
    defaultBaseUrl: "https://ark.cn-beijing.volces.com",
    models: [
      "doubao-seedance-2-0-260128",
      "doubao-seedance-2-0-fast-260128",
      "doubao-seedance-2-0-mini-260615",
      "doubao-seedance-1-5-pro-251215",
      "doubao-seedance-1-0-pro-250528",
      "doubao-seedance-1-0-pro-fast-251015",
      "doubao-seedance-1-0-lite-t2v-250428",
    ],
    supportedAspectRatios: ["16:9", "4:3", "1:1", "9:16", "3:4", "21:9"],
    supportedDurations: [5, 10],
    supportedResolutions: ["480p", "720p", "1080p"],
    maxDuration: 10,
  },
};

const MIN_REMEDIATION_DURATION_SECONDS = 60;
const MAX_REMEDIATION_DURATION_SECONDS = 300;
const MAX_REMEDIATION_SEGMENTS = 20;
const SEGMENT_TITLES = [
  "Orient to the idea",
  "Explain the core principle",
  "Build the visual model",
  "Apply it to an example",
  "Correct the misconception",
  "Recap and transfer",
];

function text(value: unknown, maxLength: number): string {
  return typeof value === "string" ? value.trim().slice(0, maxLength) : "";
}

export function normalizeRemediationVideoRequest(input: unknown): { request?: RemediationVideoRequest; error?: string } {
  if (!input || typeof input !== "object") return { error: "Request body must be an object" };
  const body = input as Record<string, unknown>;
  const request: RemediationVideoRequest = {
    topicTitle: text(body.topicTitle, 240),
    stageKind: text(body.stageKind, 80),
    mistake: text(body.mistake, 2400),
    correctAnswer: text(body.correctAnswer, 4000),
    correction: text(body.correction, 2400),
    remediation: text(body.remediation, 2400),
    sourceContext: text(body.sourceContext, 12000),
    requestedDurationSeconds: typeof body.requestedDurationSeconds === "number" ? body.requestedDurationSeconds : MIN_REMEDIATION_DURATION_SECONDS,
  };
  if (!request.topicTitle || !request.mistake || !request.correctAnswer || !request.correction) return { error: "topicTitle, mistake, correctAnswer, and correction are required" };
  if (!request.sourceContext) return { error: "Approved source context is required" };
  const duration = request.requestedDurationSeconds ?? MIN_REMEDIATION_DURATION_SECONDS;
  if (!Number.isInteger(duration) || duration < MIN_REMEDIATION_DURATION_SECONDS || duration > MAX_REMEDIATION_DURATION_SECONDS) return { error: `requestedDurationSeconds must be an integer from ${MIN_REMEDIATION_DURATION_SECONDS} to ${MAX_REMEDIATION_DURATION_SECONDS}` };
  return { request };
}

function buildRemediationSegments(request: RemediationVideoRequest, provider: VideoProviderConfig) {
  const clipDuration = Math.max(...provider.supportedDurations);
  const count = Math.min(MAX_REMEDIATION_SEGMENTS, Math.max(1, Math.ceil((request.requestedDurationSeconds || MIN_REMEDIATION_DURATION_SECONDS) / clipDuration)));
  return Array.from({ length: count }, (_, index) => {
    const title = SEGMENT_TITLES[index] || `Practice segment ${index + 1}`;
    return {
      index,
      title,
      prompt: [
        `Create segment ${index + 1} of ${count} in a source-grounded educational remediation lesson about "${request.topicTitle}".`,
        `This segment is titled "${title}". Teach the learner who made this mistake: ${request.mistake}`,
        `The correct idea is: ${request.correctAnswer}`,
        `The repair is: ${request.correction}`,
        request.remediation ? `Review focus: ${request.remediation}` : "",
        `Stage being repaired: ${request.stageKind}`,
        `Use this approved source context only:\n${request.sourceContext}`,
        "Use a clean engineering classroom visual style with labeled block diagrams, arrows, symbols, and one concrete example. Do not invent values, citations, people, or claims outside the supplied source context.",
        "Do not show a multiple-choice answer key or refer to this as an AI-generated video. Keep labels short enough to read and make the visual sequence understandable on its own.",
      ].filter(Boolean).join("\n\n"),
    };
  });
}

function buildNarration(request: RemediationVideoRequest, index: number): string {
  const segmentSpecific = [
    "Start by naming the quantity, system, or principle being tested.",
    "Connect the definition to the approved source explanation.",
    "Read the visual from left to right and identify what each block does.",
    "Apply the idea to one concrete engineering example before calculating anything.",
    "Compare the original answer with the correction and locate the exact mistaken step.",
    "Say the idea back in your own words, then transfer it to a new example.",
  ][index] || "Summarize the idea and apply it to a new example.";
  return [
    `We are repairing the idea of ${request.topicTitle}.`,
    `The mistake to avoid is: ${request.mistake}.`,
    `The correct idea is: ${request.correctAnswer}.`,
    `Use this correction: ${request.correction}.`,
    request.remediation ? `Keep this review point in mind: ${request.remediation}.` : "",
    segmentSpecific,
  ].filter(Boolean).join(" ");
}

function audioFormat(contentType: string): string {
  if (contentType.includes("audio/mpeg") || contentType.includes("audio/mp3")) return "mp3";
  if (contentType.includes("audio/flac")) return "flac";
  if (contentType.includes("audio/ogg")) return "ogg";
  if (contentType.includes("audio/webm")) return "webm";
  return "wav";
}

async function generateVoxCPMPythonNarration(textValue: string): Promise<RemediationVideoClip["narration"] | undefined> {
  const baseUrl = (process.env.REMEDIATION_VOICE_BASE_URL?.trim() || process.env.TTS_VOXCPM_BASE_URL?.trim() || "").replace(/\/$/, "");
  if (!baseUrl) return undefined;
  const voicePrompt = process.env.REMEDIATION_VOICE_PROMPT?.trim();
  const formData = new FormData();
  formData.set("text", voicePrompt ? `(${voicePrompt})${textValue}` : textValue);
  formData.set("cfg_value", process.env.REMEDIATION_VOICE_CFG_VALUE?.trim() || "2.0");
  formData.set("inference_timesteps", process.env.REMEDIATION_VOICE_INFERENCE_TIMESTEPS?.trim() || "10");
  formData.set("normalize", process.env.REMEDIATION_VOICE_NORMALIZE?.trim() || "false");
  formData.set("denoise", process.env.REMEDIATION_VOICE_DENOISE?.trim() || "false");
  const apiKey = process.env.REMEDIATION_VOICE_API_KEY?.trim();
  const response = await fetch(`${baseUrl}/tts/upload`, { method: "POST", headers: apiKey ? { Authorization: `Bearer ${apiKey}` } : undefined, body: formData });
  if (!response.ok) throw new Error(`VoxCPM Python voice generation failed (${response.status}): ${(await response.text()).slice(0, 500)}`);
  const contentType = response.headers.get("content-type") || "audio/wav";
  const base64 = Buffer.from(await response.arrayBuffer()).toString("base64");
  return { dataUrl: `data:${contentType};base64,${base64}`, format: audioFormat(contentType), providerId: "voxcpm-python", text: textValue };
}

function arkRoot(baseUrl: string): string {
  const trimmed = baseUrl.replace(/\/+$/, "");
  return /\/api\//.test(trimmed) ? trimmed : `${trimmed}/api/v3`;
}

function estimateDimensions(ratio = "16:9", resolution = "720p") {
  const height = resolution === "1080p" ? 1080 : resolution === "480p" ? 480 : 720;
  const [widthRatio, heightRatio] = ratio.split(":").map(Number);
  if (!widthRatio || !heightRatio) return { width: Math.round(height * 16 / 9), height };
  return { width: Math.round(height * widthRatio / heightRatio), height };
}

function normalizeVideoOptions(provider: VideoProviderConfig, options: VideoGenerationOptions): VideoGenerationOptions {
  return {
    ...options,
    duration: provider.supportedDurations.includes(options.duration || 0) ? options.duration : provider.supportedDurations[0],
    aspectRatio: provider.supportedAspectRatios.includes(options.aspectRatio || "" as VideoAspectRatio) ? options.aspectRatio : provider.supportedAspectRatios[0],
    resolution: provider.supportedResolutions.includes(options.resolution || "" as VideoResolution) ? options.resolution : provider.supportedResolutions[0],
  };
}

type SubmitResult<T> = { status: "submitted"; taskId: string } | { status: "done"; result: T } | { status: "failed"; message: string };
type PollResult<T> = { status: "pending"; detail?: string } | { status: "done"; result: T } | { status: "failed"; message: string };

async function runPolledTask<T>(options: {
  submit: () => Promise<SubmitResult<T>>;
  poll: (taskId: string) => Promise<PollResult<T>>;
  intervalMs: number;
  maxAttempts: number;
  label: string;
}): Promise<T> {
  const submitted = await options.submit();
  if (submitted.status === "done") return submitted.result;
  if (submitted.status === "failed") throw new Error(submitted.message);
  let lastPendingDetail = "";
  for (let attempt = 0; attempt < options.maxAttempts; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, options.intervalMs));
    const polled = await options.poll(submitted.taskId);
    if (polled.status === "done") return polled.result;
    if (polled.status === "failed") throw new Error(polled.message);
    lastPendingDetail = polled.detail || lastPendingDetail;
  }
  throw new Error(`${options.label} timed out after ${options.maxAttempts * options.intervalMs / 1000}s${lastPendingDetail ? ` (${lastPendingDetail})` : ""}`);
}

async function generateSeedanceVideo(config: VideoGenerationConfig, options: VideoGenerationOptions): Promise<VideoGenerationResult> {
  const root = arkRoot(config.baseUrl || VIDEO_PROVIDERS.seedance.defaultBaseUrl);
  const body = {
    model: config.model || VIDEO_PROVIDERS.seedance.models[0],
    content: [{ type: "text", text: options.prompt }],
    watermark: false,
    ratio: options.aspectRatio,
    duration: options.duration,
    resolution: options.resolution,
  };
  return runPolledTask<VideoGenerationResult>({
    submit: async () => {
      const response = await fetch(`${root}/contents/generations/tasks`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${config.apiKey}` }, body: JSON.stringify(body) });
      if (!response.ok) return { status: "failed", message: `Seedance task submission failed (${response.status}): ${(await response.text()).slice(0, 500)}` };
      const data = await response.json() as { id?: string };
      return data.id ? { status: "submitted", taskId: data.id } : { status: "failed", message: "Seedance returned no task ID" };
    },
    poll: async (taskId) => {
      const response = await fetch(`${root}/contents/generations/tasks/${taskId}`, { headers: { Authorization: `Bearer ${config.apiKey}` } });
      if (!response.ok) return { status: "failed", message: `Seedance task polling failed (${response.status}): ${(await response.text()).slice(0, 500)}` };
      const data = await response.json() as { status?: string; duration?: number; ratio?: string; resolution?: string; content?: { video_url?: string }; error?: { message?: string } };
      if (data.status === "succeeded") {
        if (!data.content?.video_url) return { status: "failed", message: "Seedance completed without a video URL" };
        return { status: "done", result: { url: data.content.video_url, duration: data.duration || options.duration || 5, ...estimateDimensions(data.ratio || options.aspectRatio, data.resolution || options.resolution) } };
      }
      if (data.status === "failed") return { status: "failed", message: `Seedance video generation failed: ${data.error?.message || "Unknown provider error"}` };
      return { status: "pending", detail: data.status || "queued" };
    },
    intervalMs: 5000,
    maxAttempts: 60,
    label: "Seedance video generation",
  });
}

async function generateVideo(config: VideoGenerationConfig, options: VideoGenerationOptions): Promise<VideoGenerationResult> {
  if (config.providerId === "seedance") return generateSeedanceVideo(config, options);
  throw new Error(`Unsupported remediation video provider: ${config.providerId}`);
}

export async function generateRemediationLesson(request: RemediationVideoRequest): Promise<RemediationVideoLesson> {
  const providerId = (process.env.VIDEO_PROVIDER?.trim() || "seedance") as VideoProviderId;
  const provider = VIDEO_PROVIDERS[providerId];
  if (!provider) throw new Error(`Unsupported remediation video provider: ${providerId}`);
  const apiKey = process.env.VIDEO_SEEDANCE_API_KEY?.trim();
  if (!apiKey) throw new Error(`Configure VIDEO_SEEDANCE_API_KEY for ${provider.name} in the server environment to generate rendered remediation clips.`);
  const config: VideoGenerationConfig = {
    providerId,
    apiKey,
    baseUrl: process.env.VIDEO_SEEDANCE_BASE_URL?.trim() || provider.defaultBaseUrl,
    model: process.env.VIDEO_SEEDANCE_MODEL?.trim() || provider.models[0],
  };
  const segments = buildRemediationSegments(request, provider);
  const clips: RemediationVideoClip[] = [];
  const options = normalizeVideoOptions(provider, { prompt: "", duration: provider.maxDuration, aspectRatio: "16:9", resolution: "720p" });
  for (let offset = 0; offset < segments.length; offset += 2) {
    const batch = segments.slice(offset, offset + 2);
    const generated = await Promise.all(batch.map(async (segment) => {
      const narrationText = buildNarration(request, segment.index);
      const [video, narration] = await Promise.all([
        generateVideo(config, { ...options, prompt: segment.prompt }),
        generateVoxCPMPythonNarration(narrationText),
      ]);
      return { index: segment.index, title: segment.title, ...video, ...(narration ? { narration } : {}) };
    }));
    clips.push(...generated);
  }
  clips.sort((left, right) => left.index - right.index);
  return { mode: "sequenced_clips", title: `${request.topicTitle} — guided correction`, requestedDurationSeconds: request.requestedDurationSeconds || MIN_REMEDIATION_DURATION_SECONDS, actualDurationSeconds: clips.reduce((total, clip) => total + clip.duration, 0), providerId, clips };
}
