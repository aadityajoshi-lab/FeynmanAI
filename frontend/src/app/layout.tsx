import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Feynman AI · Teach-Back Lab",
  description: "Build a source-bounded explanation, then verify it claim by claim.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
