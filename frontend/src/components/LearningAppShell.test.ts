import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const shell = readFileSync(fileURLToPath(new URL("./LearningAppShell.tsx", import.meta.url)), "utf8");
const styles = readFileSync(fileURLToPath(new URL("../app/learning-os.css", import.meta.url)), "utf8");

describe("LearningAppShell mobile navigation", () => {
  it("keeps learner course and privacy surfaces reachable below the desktop breakpoint", () => {
    expect(shell).toContain("const mobileMoreNav");
    expect(shell).not.toContain('href: "/teach"');
    expect(shell).not.toContain('href: "/institution"');
    expect(shell).toContain('href: "/settings/privacy"');
    expect(shell).toContain('aria-label="Course and role navigation"');
    expect(styles).toContain(".fos-mobile-more-menu");
    expect(styles).toContain("max-height: calc(100dvh - 100px)");
  });

  it("keeps the top-level New goal action readable on the monochrome header", () => {
    expect(shell).toContain('className="fos-primary-action fos-top-goal-action"');
    expect(styles).toContain(".fos-top-actions .fos-top-goal-action");
    expect(styles).toContain("color: var(--fos-ink);");
    expect(styles).toContain("background: #ffffff;");
  });

  it("exposes a real sign-out action for the authenticated workspace", () => {
    expect(shell).toContain('aria-label="Sign out"');
    expect(shell).toContain("signOutCurrentAuth");
    expect(shell).toContain('window.location.assign("/")');
    expect(styles).toContain(".fos-signout-action");
  });
});
