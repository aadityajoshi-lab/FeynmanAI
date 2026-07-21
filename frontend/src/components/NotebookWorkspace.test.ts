import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const workspace = readFileSync(fileURLToPath(new URL("./NotebookWorkspace.tsx", import.meta.url)), "utf8");

describe("Notebook notes source scope", () => {
  it("initializes notes opened from the header and saved-output count with the active source selection", () => {
    expect(workspace).toContain('className="nlm-top-quiet" onClick={() => openNewNote()}');
    expect(workspace).toContain('onClick={() => openNewNote()}>Notes {notes.length}</button>');
  });

  it("makes the proof task the primary source desk view", () => {
    expect(workspace).toContain('useState<CenterView>("proof")');
    expect(workspace).toContain("Turn this source into demonstrated understanding.");
    expect(workspace).toContain("learningOsApi.submitAttempt");
    expect(workspace).toContain("SOURCE → PROOF → EVIDENCE");
    expect(workspace).toContain("sourceNotebook=");
    expect(workspace).toContain("values.indexOf(item) === index");
  });

  it("uses an accessible in-app confirmation before source deletion", () => {
    expect(workspace).not.toContain("window.confirm");
    expect(workspace).toContain("Confirm remove ${source.title}");
    expect(workspace).toContain("onCancelDelete={() => setConfirmingDeleteSource(null)}");
  });

  it("keeps OpenAI provider failures retryable and visible on generated outputs", () => {
    expect(workspace).toContain("function isRetryableGenerationFailure");
    expect(workspace).toContain("isRetryableGenerationFailure(failure)");
    expect(workspace).toContain("OpenAI${normalizedModel");
    expect(workspace).toContain('replace(/^cx\\//i, "")');
  });
});
