import { Suspense } from "react";
import { UniversalSourceDesk } from "@/components/UniversalSourceDesk";

export default function SourcesPage() {
  return <Suspense fallback={<main className="fos-entry-shell"><p>Opening Source Desk...</p></main>}><UniversalSourceDesk /></Suspense>;
}
