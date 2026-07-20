import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const views = readFileSync(fileURLToPath(new URL("./LearningViews.tsx", import.meta.url)), "utf8");
const learningStyles = readFileSync(fileURLToPath(new URL("../app/learning-os.css", import.meta.url)), "utf8");

describe("Learning OS real-state surface", () => {
  it("does not retain demo fallback objects for real routes", () => {
    expect(views).not.toContain("demoGoal");
    expect(views).not.toContain("demoEvidence");
    expect(views).not.toContain("demoCourse");
    expect(views).toContain("RouteState");
  });

  it("keeps the active Learning OS skin monochrome with a restrained editorial signal", () => {
    expect(learningStyles).toContain("background-image: linear-gradient");
    expect(learningStyles).toContain("--fos-ink: #111111");
    expect(learningStyles).toContain("--fos-paper: #f5f5f2");
    expect(learningStyles).toContain("--fos-canvas: #eeeeeb");
    expect(learningStyles).toContain("--fos-accent: #315efb");
  });

  it("renders real source and evidence state in the goal flow", () => {
    expect(views).toContain("listNotebooks()");
    expect(views).toContain("Source extraction");
    expect(views).toContain("Source coverage");
    expect(views).toContain("MISSING / TO PRACTICE");
    expect(views).toContain("EVALUATOR / RUBRIC");
    expect(views).toContain("SOURCE VERIFICATION");
    expect(views).toContain("SAVED ARTIFACTS");
    expect(views).toContain("onSourceContextsChange={setSourceContexts}");
    expect(views).toContain("SERVER-SIDE EVALUATION");
    expect(views).toContain("Retry feedback");
    expect(views).toContain("No provider-generated feedback is being substituted.");
    expect(views).toContain("Curriculum preview");
    expect(views).toContain("Save route correction");
    expect(views).toContain("What you will learn");
  });

  it("mounts provider feedback in the active workspace instead of leaving it in a dead return path", () => {
    const workspace = views.slice(views.indexOf("export function LearningWorkspaceView"), views.indexOf("function ProviderFeedbackPanel"));
    expect(workspace).toContain("<ProviderFeedbackPanel feedback={providerFeedback}");
  });

  it("keeps learner course access separate from teaching and cohort role gates", () => {
    const courseHub = views.slice(views.indexOf("export function CourseHubView"), views.indexOf("export function TeachHomeView"));
    const courseCommand = views.slice(views.indexOf("export function CourseCommandView"), views.indexOf("function CourseBuilderViewLegacy"));
    const courseBuilder = views.slice(views.indexOf("export function CourseBuilderView"), views.indexOf("export function CohortView"));
    const cohort = views.slice(views.indexOf("export function CohortView"), views.indexOf("export function InstitutionHomeView"));

    expect(courseHub).toContain("learningOsApi.course(courseId)");
    expect(courseHub).not.toContain("managedCourse(courseId)");
    expect(courseCommand).toContain("managedCourse(courseId)");
    expect(courseBuilder).toContain("managedCourse(courseId)");
    expect(cohort).toContain("reviewableCourse(courseId)");
  });
});
