import { CohortView } from "@/components/LearningViews";

export default function CohortPage({ params }: { params: { courseId: string } }) {
  return <CohortView courseId={params.courseId} />;
}
