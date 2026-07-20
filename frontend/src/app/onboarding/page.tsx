import { redirect } from "next/navigation";

export default function OnboardingPage({ searchParams }: { searchParams: { next?: string } }) {
  const next = searchParams.next ? `?next=${encodeURIComponent(searchParams.next)}` : "";
  redirect(`/login${next}`);
}
