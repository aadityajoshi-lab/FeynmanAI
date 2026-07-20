import { LearningWorkspaceView } from "@/components/LearningViews";

export default function GoalLearningPage({ params }: { params: { goalId: string } }) {
  return <LearningWorkspaceView goalId={params.goalId} />;
}
