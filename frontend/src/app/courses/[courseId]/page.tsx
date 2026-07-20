import { CourseHubView } from "@/components/LearningViews";

export default function CoursePage({ params }: { params: { courseId: string } }) {
  return <CourseHubView courseId={params.courseId} />;
}
