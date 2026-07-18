import { describe, expect, it } from "vitest";
import { normalizeRemediationVideoRequest } from "./remediationVideo";

describe("self-contained remediation video contract", () => {
  it("requires a bounded 1–5 minute duration", () => {
    const result = normalizeRemediationVideoRequest({
      topicTitle: "Digital instrumentation",
      stageKind: "diagram",
      mistake: "The ADC was placed after the display.",
      correctAnswer: "The ADC converts the conditioned signal before display.",
      correction: "Follow the signal path in order.",
      sourceContext: "[anchor-1] Digital instruments convert signals for display.",
      requestedDurationSeconds: 30,
    });
    expect(result.error).toContain("60 to 300");
  });

  it("accepts source-grounded remediation input", () => {
    const result = normalizeRemediationVideoRequest({
      topicTitle: "Digital instrumentation",
      stageKind: "diagram",
      mistake: "The ADC was placed after the display.",
      correctAnswer: "The ADC converts the conditioned signal before display.",
      correction: "Follow the signal path in order.",
      sourceContext: "[anchor-1] Digital instruments convert signals for display.",
      requestedDurationSeconds: 60,
    });
    expect(result.request?.topicTitle).toBe("Digital instrumentation");
    expect(result.request?.requestedDurationSeconds).toBe(60);
  });
});
