import { redirect } from "next/navigation";

export default function NewStudyPage({ searchParams }: { searchParams: { goal?: string } }) {
  const goal = searchParams.goal;
  redirect(goal ? `/sources?goal=${encodeURIComponent(goal)}` : "/sources");
}
