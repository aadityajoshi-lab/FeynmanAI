import Link from "next/link";

export default function HomePage() {
  return (
    <main className="landing">
      <a className="skip-link" href="#main">Skip to content</a>
      <nav className="site-nav" aria-label="Main navigation">
        <Link className="brand" href="/" aria-label="Feynman AI home"><span className="brand-mark">f</span><span>feynman<span style={{ color: "var(--blue)" }}>.</span>ai</span></Link>
        <div className="nav-links"><Link href="#how-it-works">How it works</Link><Link href="#why">Why this?</Link><Link href="/subjects">Explore subjects</Link></div>
        <Link className="button button-primary" href="/study/new">Start a study desk</Link>
      </nav>

      <section className="hero" id="main">
        <span className="eyebrow">A small lab for difficult concepts</span>
        <h1>Don&apos;t just learn it.<br /><em>Make it legible.</em></h1>
        <p className="hero-copy">Feynman AI gives you a whiteboard, a learning method you can choose, and a source-bounded checkpoint that turns confusion into the next useful attempt.</p>
        <div className="hero-actions"><Link className="button button-primary" href="/study/new">Start a study desk -&gt;</Link><Link className="button button-ghost" href="/subjects">Browse subjects</Link></div>
        <div className="hero-note"><div className="avatar-stack"><span className="avatar">A</span><span className="avatar">M</span><span className="avatar">R</span></div><span><b>One concept at a time.</b> No hidden ability score.</span></div>
      </section>

      <section className="landing-grid" id="how-it-works">
        <article className="feature-card large"><span className="feature-number">01 / CHOOSE</span><h2>Pick the way you need to learn.</h2><p>Use worked examples, predict and reveal, retrieval, self-explanation, representation switches, or an exam bridge. The recommendation is evidence-based and always overridable.</p><div className="mini-flow"><span>mode</span><i /><span>model</span><i /><span>explain</span></div></article>
        <article className="feature-card teal"><span className="feature-number">02 / BUILD</span><h2>Make the invisible visible.</h2><p>Bring a source pack, then work through a model-authored whiteboard, visualization, and checkpoint sequence for the concept you choose.</p><div style={{ marginTop: 26 }}><span className="source-badge">SOURCE PACK / GENERATED MODULE</span></div></article>
        <article className="feature-card lime" id="why"><span className="feature-number">03 / VERIFY</span><h2>Explain what your evidence shows.</h2><p>Each checkpoint is tied to an instructor-controlled source pack. If the evidence is not approved or sufficient, the system abstains and says why.</p><div style={{ marginTop: 24 }}><Link className="button button-primary" href="/subjects" style={{ display: "inline-block", fontSize: 12 }}>Open the subject atlas -&gt;</Link></div></article>
        <article className="feature-card"><span className="feature-number">FOR LEARNERS &amp; TEACHERS</span><h2>Inspect progress without labeling a person.</h2><p>Memory is separated into global preferences, subject-specific skill evidence, and short-lived session state. Learners can view, export, reset, or delete it.</p><div style={{ marginTop: 25, color: "var(--teal)", fontFamily: "'DM Mono',monospace", fontSize: 11 }}>SOURCE-BOUNDED / HUMAN-REVIEW READY</div></article>
      </section>
      <footer className="landing-footer"><span>© 2026 Feynman AI</span><span>Built for curious people who like to verify.</span></footer>
    </main>
  );
}
