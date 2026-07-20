import { GoalOverviewView } from "@/components/LearningViews";

export default function GoalPage({ params }: { params: { goalId: string } }) {
  return <GoalOverviewView goalId={params.goalId} />;
}
