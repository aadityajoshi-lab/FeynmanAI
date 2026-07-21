import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const desk = readFileSync(fileURLToPath(new URL("./UniversalSourceDesk.tsx", import.meta.url)), "utf8");

describe("universal source desk grounding inputs", () => {
  it("offers durable pasted source notes in addition to file and URL references", () => {
    expect(desk).toContain('type SourceKind = "file" | "url" | "text";');
    expect(desk).toContain('"Paste notes"');
    expect(desk).toContain('Source excerpt or notes');
    expect(desk).toContain('sourceKind: "pasted_notes"');
  });

  it("requests bounded extraction instead of saving a URL as metadata-only context", () => {
    expect(desk).toContain("fetchWebsite: true");
    expect(desk).toContain("Extract readable text, metadata, and available visuals");
  });

  it("appends text and URL sources to an existing notebook when requested", () => {
    expect(desk).toContain('const requestedNotebookId = searchParams.get("notebook") || "";');
    expect(desk).toContain('const notebookResult = await getNotebook(requestedNotebookId);');
    expect(desk).toContain('const notebook = targetNotebook || await createNotebook');
    expect(desk).toContain('Add context to ${targetNotebook.title}');
  });

  it("does not silently create a new notebook for an unavailable notebook query", () => {
    expect(desk).toContain('if (requestedNotebookId && !targetNotebook)');
    expect(desk).toContain('Notebook unavailable');
    expect(desk).toContain('Return to Source Desk and choose another notebook.');
  });
});
