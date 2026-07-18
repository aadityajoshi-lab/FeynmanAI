export type StudyAssetKind = "pdf" | "image" | "video" | "audio";

export type LearningGoal = "course" | "skill" | "interview" | "viva";
export type AssessmentFocus = "mastery" | "mock_test" | "conversation" | "viva";
export type SkillLevel = "beginner" | "intermediate" | "advanced";

export interface StudyAsset {
  id: string;
  name: string;
  kind: StudyAssetKind;
  status: "review_required";
}
