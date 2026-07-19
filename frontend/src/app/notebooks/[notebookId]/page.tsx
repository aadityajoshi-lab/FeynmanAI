import NotebookWorkspace from "@/components/NotebookWorkspace";

export default function NotebookPage({ params }: { params: { notebookId: string } }) {
  return <NotebookWorkspace notebookId={params.notebookId} />;
}
