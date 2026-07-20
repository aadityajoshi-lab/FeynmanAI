import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const goalEntry = readFileSync(fileURLToPath(new URL("./GoalEntry.tsx", import.meta.url)), "utf8");

describe("Universal goal contract payload", () => {
  it("does not send an empty contract brief when optional intent context is blank", () => {
    expect(goalEntry).toContain("const brief = pending.description.trim() || pending.outcome.trim() || intendedCapability;");
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
});
