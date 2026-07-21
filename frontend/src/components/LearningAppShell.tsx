"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { signOutCurrentAuth } from "@/lib/learningOsApi";

type NavItem = { href: string; label: string; icon: string; match?: string[] };

const courseNav: NavItem = { href: "/courses", label: "Courses", icon: "course", match: ["/courses"] };

const learnerNav: NavItem[] = [
  { href: "/home", label: "Home", icon: "home" },
  { href: "/goals", label: "Goals", icon: "spark", match: ["/goals"] },
  { href: "/sources", label: "Sources", icon: "source", match: ["/sources", "/notebooks", "/study"] },
  { href: "/evidence", label: "Evidence", icon: "proof" },
  courseNav,
];

const mobilePrimaryNav = learnerNav.filter((item) => item !== courseNav);
const mobileMoreNav: NavItem[] = [
  courseNav,
  { href: "/settings/privacy", label: "Privacy", icon: "settings", match: ["/settings"] },
];

export function FeynmanIcon({ name, size = 18 }: { name: string; size?: number }) {
  const symbols: Record<string, string> = {
    home: "⌂", spark: "✦", source: "▤", proof: "✓", course: "▱", teach: "⌁", org: "◫",
    plus: "+", arrow: "→", lock: "⌾", shield: "◈", chart: "⌁", people: "◌", book: "▥",
    play: "▶", check: "✓", dot: "•", panel: "▯", note: "▣", settings: "⚙", close: "×",
  };
  return <span className="fos-icon" style={{ fontSize: size, width: size, height: size }} aria-hidden="true">{symbols[name] || "•"}</span>;
}

function isNavItemActive(item: NavItem, pathname: string) {
  const matches = item.match || [item.href];
  return matches.some((match) => pathname === match || pathname.startsWith(`${match}/`));
}

function NavLink({ item, pathname }: { item: NavItem; pathname: string }) {
  const active = isNavItemActive(item, pathname);
  return <Link href={item.href as never} className={`fos-nav-link ${active ? "active" : ""}`} aria-current={active ? "page" : undefined}><FeynmanIcon name={item.icon} /><span>{item.label}</span></Link>;
}

export function LearningAppShell({ children, title, eyebrow, actions, mobileActions, compact = false }: { children: ReactNode; title?: string; eyebrow?: string; actions?: ReactNode; mobileActions?: ReactNode; compact?: boolean }) {
  const pathname = usePathname();
  const [signingOut, setSigningOut] = useState(false);
  const [isSignedIn, setIsSignedIn] = useState<boolean | null>(null);
  useEffect(() => {
    const sync = (event?: Event) => {
      const detail = (event as CustomEvent<{ isSignedIn?: boolean }> | undefined)?.detail;
      if (typeof detail?.isSignedIn === "boolean") {
        setIsSignedIn(detail.isSignedIn);
        return;
      }
      // A Clerk-backed page starts with an unknown auth marker. Do not flash
      // a misleading "Sign in" action while Clerk is still hydrating; the
      // bridge dispatches the authoritative state once `isLoaded` is true.
      const marker = document.documentElement.dataset.feynmanAuth;
      if (marker === "signed-in") setIsSignedIn(true);
      if (marker === "signed-out") setIsSignedIn(false);
    };
    sync();
    window.addEventListener("feynman-auth-state", sync);
    return () => window.removeEventListener("feynman-auth-state", sync);
  }, []);
  const mobileMoreActive = mobileMoreNav.some((item) => isNavItemActive(item, pathname));
  async function signOut() {
    if (signingOut) return;
    setSigningOut(true);
    try { await signOutCurrentAuth(); } finally { window.location.assign("/"); }
  }
  return <div className={`fos-shell ${compact ? "fos-shell-compact" : ""}`}>
    <a className="skip-link" href="#feynman-main">Skip to content</a>
    <aside className="fos-sidebar" aria-label="Feynman navigation">
      <Link className="fos-brand" href="/home" aria-label="Feynman home"><span className="fos-brand-mark">f</span><span>feynman<span>.</span>ai</span></Link>
      <div className="fos-workspace-chip"><span className="fos-workspace-orb">A</span><span><small>ACTIVE WORKSPACE</small><strong>Personal lab</strong></span><FeynmanIcon name="arrow" size={14} /></div>
      <nav className="fos-nav-list" aria-label="Learner navigation">{learnerNav.map((item) => <NavLink item={item} pathname={pathname} key={item.label} />)}</nav>
      <div className="fos-sidebar-bottom"><Link href="/settings/privacy" className="fos-nav-link"><FeynmanIcon name="settings" /><span>Privacy</span></Link><p><span className="fos-live-dot" /> learner-owned data</p></div>
    </aside>
    <div className="fos-app-frame">
      <header className="fos-topbar">
        <div className="fos-breadcrumb"><span>{eyebrow || "LEARNING OS"}</span>{title ? <><i>/</i><strong>{title}</strong></> : null}</div>
        <div className="fos-top-actions">{actions}<Link href="/goals/new" className="fos-primary-action fos-top-goal-action"><FeynmanIcon name="plus" size={15} /> New goal</Link>{isSignedIn === true ? <><Link href="/settings/privacy" className="fos-avatar" aria-label="Open account settings">A</Link><button type="button" className="fos-signout-action" onClick={() => void signOut()} disabled={signingOut} aria-label="Sign out">{signingOut ? "Signing out…" : "Sign out"}</button></> : isSignedIn === false ? <Link href={"/login" as never} className="fos-signin-action">Sign in</Link> : null}</div>
      </header>
      <main id="feynman-main" className="fos-main">{children}</main>
    </div>
    <nav className="fos-mobile-nav" aria-label="Mobile navigation">
      {mobilePrimaryNav.map((item) => <NavLink item={item} pathname={pathname} key={item.label} />)}
      <details key={pathname} className={`fos-mobile-more ${mobileMoreActive ? "active" : ""}`}>
        <summary className="fos-mobile-more-toggle" aria-label="Open course and role navigation"><FeynmanIcon name="panel" /><span>More</span></summary>
        <div className="fos-mobile-more-menu" aria-label="Course and role navigation">
          {mobileActions ? <div className="fos-mobile-action-slot">{mobileActions}</div> : null}
          {mobileMoreNav.map((item) => {
            const active = isNavItemActive(item, pathname);
            return <Link href={item.href as never} className={`fos-mobile-more-link ${active ? "active" : ""}`} aria-current={active ? "page" : undefined} key={item.label}><FeynmanIcon name={item.icon} /><span>{item.label}</span></Link>;
          })}
        </div>
      </details>
    </nav>
  </div>;
}

export function SectionHeading({ eyebrow, title, copy, action }: { eyebrow: string; title: string; copy?: string; action?: ReactNode }) {
  return <div className="fos-section-heading"><div><span className="fos-eyebrow">{eyebrow}</span><h1>{title}</h1>{copy ? <p>{copy}</p> : null}</div>{action ? <div className="fos-heading-action">{action}</div> : null}</div>;
}

export function StatusPill({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "danger" }) {
  return <span className={`fos-status fos-status-${tone}`}>{children}</span>;
}
