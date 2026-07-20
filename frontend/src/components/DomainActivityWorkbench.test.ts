import { describe, expect, it } from "vitest";
import { buildPolicyTrace, buildRoundRobinTrace, calculateSamplingState, resolveGraphicsTopic, resolveOperatingSystemsTopic, resolveWorkbenchDomain } from "./DomainActivityWorkbench";

describe("DomainActivityWorkbench calculations", () => {
  it("chooses one adaptive workbench from a goal's domain cues", () => {
    expect(resolveWorkbenchDomain("Engineering", "Understand DSP sampling and aliasing")).toBe("dsp");
    expect(resolveWorkbenchDomain("Humanities", "Compare primary and secondary historical sources")).toBe("history");
    expect(resolveWorkbenchDomain("Computer science", "Trace an operating-system scheduler")).toBe("operating_systems");
    expect(resolveWorkbenchDomain("Medical education", "Read a clinical paper critically")).toBe("medicine");
    expect(resolveWorkbenchDomain("general", "Learn the causes of the French Revolution")).toBe("general");
  });

  it("calculates a visible DSP alias and a round-robin trace", () => {
    const sampling = calculateSamplingState(7, 8);
    const trace = buildRoundRobinTrace(2);

    expect(sampling).toMatchObject({ nyquistFrequency: 4, aliasFrequency: 1, isAliased: true });
    expect(trace.slices.slice(0, 4).map((slice) => slice.processId)).toEqual(["P1", "P2", "P3", "P1"]);
    expect(trace.averageWaitingTime).toBeCloseTo(5.7, 1);
  });

  it("keeps operating-system and graphics topics on the shared canvas", () => {
    expect(resolveOperatingSystemsTopic("Virtual memory page replacement")).toBe("memory");
    expect(resolveOperatingSystemsTopic("Deadlock resource allocation graph")).toBe("deadlock");
    expect(resolveOperatingSystemsTopic("System call instruction trace")).toBe("system_call");
    expect(resolveGraphicsTopic("Lighting and shading")).toBe("lighting");
    expect(resolveGraphicsTopic("Depth buffering")).toBe("depth");
    expect(resolveGraphicsTopic("Rasterization clipping")).toBe("rasterization");
    expect(buildPolicyTrace("fcfs", 2).slices.map((slice) => slice.processId)).toEqual(["P1", "P2", "P3"]);
  });
});
