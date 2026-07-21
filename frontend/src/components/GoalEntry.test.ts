import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const goalEntry = readFileSync(fileURLToPath(new URL("./GoalEntry.tsx", import.meta.url)), "utf8");

describe("Universal goal contract payload", () => {
  it("does not send an empty contract brief when optional intent context is blank", () => {
    expect(goalEntry).toContain("const brief = draft.brief.trim() || pending.description.trim() || pending.outcome.trim() || intendedCapability;");
    expect(goalEntry).toContain("brief,");
    expect(goalEntry).not.toContain("brief: pending.description");
  });

  it("completes Clerk email verification before activating a workspace session", () => {
    expect(goalEntry).toContain("prepareEmailAddressVerification");
    expect(goalEntry).toContain("attemptEmailAddressVerification");
    expect(goalEntry).toContain("Verify and enter");
    expect(goalEntry).toContain('id="clerk-captcha"');
  });

  it("carries a source notebook into the created goal", () => {
    expect(goalEntry).toContain("sourceNotebookId");
    expect(goalEntry).toContain("learningOsApi.attachGoalNotebook(goal.goalId, pending.sourceNotebookId)");
  });

  it("changes the review URL so direct goal entry mounts the contract editor", () => {
    expect(goalEntry).toContain('const reviewQuery = courseId ? `?course=${encodeURIComponent(courseId)}&review=1` : "?review=1";');
    expect(goalEntry).toContain("router.push(`/goals/new${reviewQuery}`);");
    expect(goalEntry).toContain("const searchParams = useSearchParams();");
  });

  it("requests a goal-specific contract before showing the review form", () => {
    expect(goalEntry).toContain("learningOsApi.previewGoalContract");
    expect(goalEntry).toContain("contractDraftFromModel");
    expect(goalEntry).toContain('replace(/^cx\\//i, "")');
    expect(goalEntry).toContain("function parsePrerequisites(value: string)");
    expect(goalEntry).not.toContain("draft.prerequisites.split(/[,\\n]/)");
    expect(goalEntry).toContain("Making this route specific to your goal");
    expect(goalEntry).not.toContain('["Name the core relationship", "Use one concrete example", "Transfer it to a nearby case"]');
  });

  it("keeps medical contracts visibly source-bound", () => {
    expect(goalEntry).toContain('const text = `${goal.title} ${goal.description} ${category}`.toLowerCase();');
    expect(goalEntry).toContain('ai_ml: "Machine learning / AI"');
    expect(goalEntry).toContain('if (nextCategory === "medical") setHasSources(true);');
    expect(goalEntry).toContain('const sourceBound = draft.safetyMode === "academic_source_bound" || draft.verificationMode === "source_backed";');
    expect(goalEntry).toContain("Source-backed required");
    expect(goalEntry).toContain("approved source anchors");
  });
});
