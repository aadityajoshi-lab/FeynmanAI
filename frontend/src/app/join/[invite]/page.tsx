import { JoinInvitationView } from "@/components/GoalEntry";

export default function JoinPage({ params }: { params: { invite: string } }) {
  return <JoinInvitationView token={params.invite} />;
}
