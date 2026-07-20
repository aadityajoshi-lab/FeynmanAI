import { SharedGoalView } from "@/components/LearningViews";

export default function SharedGoalPage({ params }: { params: { token: string } }) {
  return <SharedGoalView token={params.token} />;
}
