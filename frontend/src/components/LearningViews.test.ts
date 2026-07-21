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

  it("keeps the evidence goal filter bounded inside the wide page shell", () => {
    expect(views).toContain('title="What you have demonstrated" wide');
    expect(learningStyles).toContain(".fos-evidence-filter { position: relative; display: inline-flex; width: min(320px, 100%);");
    expect(views).toContain('aria-haspopup="listbox"');
    expect(views).toContain('role="listbox"');
    expect(views).not.toContain('<select value={goalFilter}');
    expect(learningStyles).toContain(".fos-evidence-filter-menu");
    expect(learningStyles).toContain(".fos-evidence-filter-option");
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

  it("keeps a visible fallback for goal sharing when clipboard access is unavailable", () => {
    expect(views).toContain('const [shareUrl, setShareUrl] = useState("");');
    expect(views).toContain('aria-label="Share link URL"');
    expect(views).toContain('Open shared route');
    expect(views).toContain("navigator.clipboard");
    expect(learningStyles).toContain(".fos-share-link-fallback");
  });

  it("hydrates the learner identity before direct goal lookups", () => {
    const workspace = views.slice(views.indexOf("export function LearningWorkspaceView"), views.indexOf("function ProviderFeedbackPanel"));
    expect(workspace).toContain("await learningOsApi.me();");
    expect(views).toContain("Warm the owned-goal catalog once");
    expect(workspace).toContain("transient anonymous lookup");
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

  it("loads institution metrics from an authorized institution workspace", () => {
    const institution = views.slice(views.indexOf("export function InstitutionHomeView"), views.indexOf("export function InstitutionMembersView"));
    expect(institution).toContain("learningOsApi.workspaces()");
    expect(institution).toContain('item.kind === "institution"');
    expect(institution).toContain("institutionDashboard(workspace.workspaceId)");
    expect(institution).toContain('new LearningOsApiError("Institution admin access is required.", 403, "role_required")');
  });

  it("keeps aggregate insights scoped to an authorized institution workspace", () => {
    const insights = views.slice(views.indexOf("export function InstitutionInsightsView"));
    expect(insights).toContain("learningOsApi.workspaces()");
    expect(insights).toContain('item.kind === "institution"');
    expect(insights).toContain("institutionDashboard(workspace.workspaceId)");
    expect(insights).toContain('new LearningOsApiError("Institution admin access is required.", 403, "role_required")');
  });
});
