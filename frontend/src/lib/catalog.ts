import { Subject, SubjectModule, ModuleCheckpoint } from "./subjectTypes";

const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1").replace(/\/$/, "");

function normalizeCheckpoint(raw: any): ModuleCheckpoint {
  const answer = Number.isInteger(raw?.answer) ? raw.answer : 0;
  return {
    id: raw?.checkpointId || raw?.id || "checkpoint",
    prompt: raw?.prompt || "Explain what changed and why.",
    options: Array.isArray(raw?.options) && raw.options.length ? raw.options : ["I need a worked example.", "I can explain the evidence."],
    answer,
    explanation: raw?.explanation || "Use the approved source evidence to justify the next step.",
  };
}

function normalizeSubject(raw: any): Subject {
  const modules = Array.isArray(raw?.modules) ? raw.modules : [];
  return {
    id: raw?.subjectId || raw?.id,
    name: raw?.title || raw?.name || "Subject",
    shortName: raw?.shortName || String(raw?.subjectId || raw?.id || "SUB").toUpperCase(),
    description: raw?.summary || raw?.description || "A source-bounded subject pack.",
    color: raw?.color || "var(--teal)",
    modules: modules.map((module: any): SubjectModule => ({
      id: module.moduleId || module.id,
      title: module.title,
      eyebrow: `${String(raw?.subjectId || raw?.id || "SUB").toUpperCase()} · MODULE`,
      description: module.summary || module.description || "Learn, build, and explain one concept.",
      objective: module.objective || module.learningGoal || module.summary || "Build an evidence-backed explanation.",
      estimatedMinutes: module.estimatedMinutes || 16,
      accent: module.accent || "teal",
      steps: Array.isArray(module.steps) && module.steps.length ? module.steps : ["Learn the idea", "Build a model", "Explain the evidence"],
      checkpoints: (module.checkpoints || []).map(normalizeCheckpoint),
      learningModes: Array.isArray(module.learningModes || raw?.learningModes) ? (module.learningModes || raw.learningModes).map((mode: any) => ({ id: mode.modeId || mode.id, title: mode.title, description: mode.description || mode.useWhen || "Try this learning strategy." })) : undefined,
    })),
  };
}

async function getJson(path: string) {
  const response = await fetch(`${API_BASE}${path}`, { next: { revalidate: 15 } });
  if (!response.ok) throw new Error(`catalog API ${response.status}`);
  return response.json();
}

export async function getSubjectCatalog(): Promise<Subject[]> {
  try {
    const payload = await getJson("/subjects");
    const rows = Array.isArray(payload?.subjects) ? payload.subjects : [];
    return rows.map(normalizeSubject);
  } catch {
    return [];
  }
}

export async function getSubjectModule(subjectId: string, moduleId: string): Promise<{ subject: Subject; module: SubjectModule } | null> {
  try {
    const raw = await getJson(`/subjects/${subjectId}/modules/${moduleId}`);
    const subjectRaw = await getJson(`/subjects/${subjectId}`);
    const subject = normalizeSubject({ ...subjectRaw, modules: [{ ...raw, moduleId }] });
    const subjectModule = subject.modules[0];
    return subjectModule ? { subject, module: subjectModule } : null;
  } catch { return null; }
}
