export const studyModes = [
  { id: "predict_reveal", label: "Predict then reveal", description: "Commit to a prediction before the generated lesson reveals the consequence." },
  { id: "worked_example", label: "Worked example", description: "See the complete path, then take responsibility for one missing step." },
  { id: "self_explain", label: "Self-explain", description: "Put the reason behind each transformation into your own words." },
  { id: "retrieval", label: "Retrieval practice", description: "Recall the idea before the source-bounded explanation appears." },
  { id: "representation_switch", label: "Representation switch", description: "Move between prose, equations, diagrams, and examples." },
  { id: "exam_bridge", label: "Exam bridge", description: "Apply the concept to one bounded exam-style problem." },
] as const;

export type LearningModeId = (typeof studyModes)[number]["id"];
