import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const surface = readFileSync(
  fileURLToPath(new URL("../components/StudyWorkspace.tsx", import.meta.url)),
  "utf8",
);

describe("generated study workspace accessibility contract", () => {
  it("exposes skip navigation and named landmarks", () => {
    expect(surface).toContain('className="study-skip-link"');
    expect(surface).toContain('href="#study-desk-main"');
    expect(surface).toContain('aria-label="Generated interactive lesson"');
  });

  it("keeps generated checkpoint controls keyboard and screen-reader addressable", () => {
    expect(surface).toContain('role="radiogroup"');
    expect(surface).toContain('aria-label={activeScene.checkpoint.prompt}');
    expect(surface).toContain('role="status"');
    expect(surface).toContain('aria-label={activeScene.checkpoint?.prompt || activeScene.title}');
  });
});
