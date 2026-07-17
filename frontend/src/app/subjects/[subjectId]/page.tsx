import Link from "next/link";
import { notFound } from "next/navigation";
import { getSubjectCatalog } from "@/lib/catalog";

export default async function SubjectPage({ params }: { params: { subjectId: string } }) {
  const subjects = await getSubjectCatalog();
  const subject = subjects.find((item) => item.id === params.subjectId);
  if (!subject) notFound();

  return (
    <main className="landing subject-index">
      <nav className="site-nav"><Link className="brand" href="/subjects"><span className="brand-mark">f</span><span>feynman<span style={{ color: "var(--blue)" }}>.</span>ai</span></Link><Link className="button button-ghost" href="/subjects">All subjects</Link></nav>
      <section className="subject-index-hero"><span className="eyebrow">{subject.shortName} / SUBJECT PACK</span><h1>{subject.name}<br /><em>one module at a time.</em></h1><p>{subject.description}</p></section>
      <section className="subject-grid" aria-label={`${subject.name} modules`}>
        {subject.modules.map((module) => <article className="subject-card" key={module.id} style={{ borderTopColor: subject.color }}><span className="eyebrow" style={{ color: subject.color }}>{module.eyebrow}</span><h2>{module.title}</h2><p>{module.objective}</p><div className="subject-modules"><Link className="module-link" href="/study/new"><span><strong>Build a fresh source-backed module</strong><small>Choose your own material and scope</small></span><span aria-hidden="true">-&gt;</span></Link></div></article>)}
      </section>
    </main>
  );
}
