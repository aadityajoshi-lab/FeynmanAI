export type StudyMode = "learn" | "build" | "check";

export interface ModuleCheckpoint {
  id: string;
  prompt: string;
  options: string[];
  answer: number;
  explanation: string;
}

export interface SubjectModule {
  id: string;
  title: string;
  eyebrow: string;
  description: string;
  objective: string;
  estimatedMinutes: number;
  accent: "teal" | "blue" | "coral" | "lime";
  steps: string[];
  checkpoints: ModuleCheckpoint[];
  learningModes?: { id: string; title: string; description: string }[];
}

export interface Subject {
  id: string;
  name: string;
  shortName: string;
  description: string;
  color: string;
  modules: SubjectModule[];
}
