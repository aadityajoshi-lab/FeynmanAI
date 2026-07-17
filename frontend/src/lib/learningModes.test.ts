import { describe, expect, it } from "vitest";
import { studyModes } from "./learningModes";

describe("learning mode catalog", () => {
  it("keeps strategy choices explicit without classifying the learner", () => {
    expect(studyModes.map((mode) => mode.id)).toContain("retrieval");
    expect(studyModes.map((mode) => mode.id)).toContain("representation_switch");
    expect(studyModes.every((mode) => mode.description.length > 20)).toBe(true);
  });
});
