import { Suspense } from "react";
import { AuthView } from "@/components/GoalEntry";

export default function LoginPage() {
  return <Suspense fallback={null}><AuthView initialMode="login" /></Suspense>;
}
