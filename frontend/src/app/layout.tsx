import type { Metadata } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import { ClerkAuthBridge } from "@/components/ClerkAuthBridge";
import "./globals.css";
import "./learning-os.css";
import "./source-desk.css";

export const metadata: Metadata = {
  title: "Feynman AI · Teach-Back Lab",
  description: "Build a source-bounded explanation, then verify it claim by claim.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const clerkKey = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;
  const content = clerkKey ? <ClerkProvider publishableKey={clerkKey}><ClerkAuthBridge />{children}</ClerkProvider> : children;
  return <html lang="en" data-feynman-auth={clerkKey ? undefined : "signed-out"}><body>{content}</body></html>;
}
