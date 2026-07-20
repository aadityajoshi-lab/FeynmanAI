import { Suspense } from "react";
import { AuthView } from "@/components/GoalEntry";

export default function SignupPage() {
  return <Suspense fallback={null}><AuthView initialMode="register" /></Suspense>;
}
