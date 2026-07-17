import Link from "next/link";
import { getSubjectCatalog } from "@/lib/catalog";

export default async function SubjectsPage() {
  const subjects = await getSubjectCatalog();
  return (
    <main className="landing subject-index">
      <nav className="site-nav">
        <Link className="brand" href="/" aria-label="Feynman AI home"><span className="brand-mark">f</span><span>feynman<span style={{ color: "var(--blue)" }}>.</span>ai</span></Link>
        <Link className="button button-primary" href="/study/new">Add a subject -&gt;</Link>
      </nav>
      <section className="subject-index-hero"><span className="eyebrow">YOUR BUILD SPACE</span><h1>Choose a subject<br /><em>to make legible.</em></h1><p>Each module is a small, inspectable loop: learn the idea, build a model, then explain what your evidence shows.</p></section>
      <section className="subject-grid" aria-label="Subjects">
        {subjects.map((subject) => <article className="subject-card" key={subject.id} style={{ borderTopColor: subject.color }}><span className="eyebrow" style={{ color: subject.color }}>{subject.shortName}</span><h2>{subject.name}</h2><p>{subject.description}</p><div className="subject-modules">{subject.modules.map((module) => <Link className="module-link" href="/study/new" key={module.id}><span><strong>{module.title}</strong><small>Build a fresh source-backed module</small></span><span aria-hidden="true">-&gt;</span></Link>)}</div></article>)}
      </section>
      <footer className="landing-footer"><span>Feynman AI / subject atlas</span><span>Source-bounded by design.</span></footer>
    </main>
  );
}
