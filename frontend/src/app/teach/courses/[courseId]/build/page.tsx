import { CourseBuilderView } from "@/components/LearningViews";

export default function CourseBuilderPage({ params }: { params: { courseId: string } }) {
  return <CourseBuilderView courseId={params.courseId} />;
}
