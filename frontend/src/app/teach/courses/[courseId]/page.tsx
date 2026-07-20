import { CourseCommandView } from "@/components/LearningViews";

export default function TeachCoursePage({ params }: { params: { courseId: string } }) {
  return <CourseCommandView courseId={params.courseId} />;
}
