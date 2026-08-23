/*
 * AntiBioTix — landing page.
 *
 * Ported from the Manus redesign. The visual system, copy, and structure are the
 * Manus design; the only changes are that the logo now resolves to a local asset
 * instead of Manus storage, and the calls to action route to the ORIGINAL
 * application's console rather than to a Manus route.
 */
import {
  Activity,
  ArrowRight,
  BookOpenCheck,
  Check,
  ClipboardCheck,
  FileCheck2,
  LockKeyhole,
  Network,
  ShieldCheck,
  Sparkles,
  Stethoscope,
} from "lucide-react";
import { Link } from "wouter";
import logoSrc from "@/assets/antibiotix-logo.jpg";
import "@/styles/landing.css";

const features = [
  { icon: ClipboardCheck, index: "01", title: "Prescription safety review", text: "Patient-specific context stays beside the prescription, so each concern is visible before action." },
  { icon: ShieldCheck, index: "02", title: "Risk-aware checks", text: "Surface allergy, renal, hepatic, pregnancy, and interaction considerations with clear status." },
  { icon: BookOpenCheck, index: "03", title: "Guideline precedence", text: "Keep local guidance, national recommendations, and global references in a readable hierarchy." },
  { icon: FileCheck2, index: "04", title: "Evidence-linked warnings", text: "Trace each warning back to the rule, source, version, and supporting passage." },
  { icon: LockKeyhole, index: "05", title: "Clinician control", text: "Professional judgment stays in the loop, with deliberate override rationale captured." },
  { icon: Activity, index: "06", title: "Stewardship visibility", text: "Turn review activity into a clearer view of where clinical attention is needed." },
];

const workflow = [
  { number: "01", title: "Context", text: "Select the synthetic or connected patient profile." },
  { number: "02", title: "Prescription", text: "Enter the medication and intended treatment plan." },
  { number: "03", title: "Evidence", text: "Review checks against patient context and guidance." },
  { number: "04", title: "Action", text: "Decide, document, and keep the reasoning traceable." },
];

const workflowIcons = [Stethoscope, ClipboardCheck, BookOpenCheck, Check];

export default function Landing() {
  return (
    <main className="landing-page">
      <header className="landing-nav">
        <Link href="/" className="landing-brand" aria-label="AntiBioTix home">
          <span className="landing-brand-mark"><img src={logoSrc} alt="" /></span>
          <span><strong>AntiBioTix</strong><small>Clinical decision support</small></span>
        </Link>
        <nav aria-label="Primary navigation">
          <a href="#capabilities">Safety signals</a>
          <a href="#workflow">Review path</a>
          <Link href="/review" className="landing-nav-cta">Open review <ArrowRight size={15} /></Link>
        </nav>
      </header>

      <section className="landing-hero" aria-labelledby="landing-title">
        <div className="landing-hero-copy">
          <div className="hero-signal"><span className="signal-pulse" /> Evidence-linked antimicrobial review</div>
          <h1 id="landing-title">Clinical decisions,<br /><em>supported by evidence.</em></h1>
          <p className="landing-lede">Review prescriptions against patient-specific risks, antimicrobial guidelines, and resistance patterns &mdash; while keeping the clinician firmly in control.</p>
          <div className="landing-actions">
            <Link href="/review" className="landing-primary-cta">Open Clinical Review <ArrowRight size={17} /></Link>
            <a href="#workflow" className="landing-secondary-cta">Explore how it works <span>&#8600;</span></a>
          </div>
          <div className="hero-proof"><Check size={14} /><span>Clinical decision support only &mdash; never a prescribing system.</span></div>
        </div>

        <div className="hero-visual" aria-label="Evidence and prescription review visualization">
          <div className="visual-caption visual-caption-top"><span>LIVE EVIDENCE LAYER</span><b>01</b></div>
          <div className="orbit-scene">
            <div className="orbit orbit-one" /><div className="orbit orbit-two" /><div className="orbit orbit-three" />
            <div className="evidence-core">
              <div className="core-halo" />
              <div className="core-mark"><img src={logoSrc} alt="" /></div>
              <span className="core-label">ANTIBIOTIX</span>
              <strong>Evidence<br />in context.</strong>
            </div>
            <div className="orbit-node node-guideline"><BookOpenCheck size={15} /><span>Guideline</span></div>
            <div className="orbit-node node-patient"><Stethoscope size={15} /><span>Patient</span></div>
            <div className="orbit-node node-audit"><Network size={15} /><span>Audit trail</span></div>
            <div className="floating-chip chip-warning"><span className="chip-dot" /> 1 attention item</div>
            <div className="floating-chip chip-status"><Sparkles size={13} /> traceable</div>
          </div>
          <div className="visual-console-card">
            <div className="console-card-top"><span><i /> Clinical Review</span><small>READY</small></div>
            <div className="console-card-body">
              <div className="console-rail"><span className="active" /><span /><span /><span /></div>
              <div className="console-content">
                <small className="console-kicker">CURRENT PRESCRIPTION</small>
                <div className="console-drug"><div><strong>Amoxicillin 500 mg</strong><span>PO &middot; three times daily &middot; 7 days</span></div><b>REVIEWING</b></div>
                <div className="console-meta"><span><small>PATIENT CONTEXT</small><strong>PT-0421 &middot; 58 yrs</strong></span><span><small>RULE EVALUATION</small><strong className="attention">1 attention item</strong></span></div>
                <div className="console-source"><FileCheck2 size={14} /><span><small>EVIDENCE SOURCE</small><strong>Local Hospital Guideline &middot; 2026</strong></span><em>VIEW RULE</em></div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="landing-intro-strip"><span>CLINICAL REVIEW CONSOLE</span><p>Patient context, prescription details, deterministic checks, evidence sources, and override rationale in one traceable flow.</p><span>AUTHORIZED TEAM WORKSPACE</span></section>

      <section className="landing-workflow" id="workflow">
        <div className="section-heading"><div><p className="eyebrow">A visible path from input to action</p><h2>Every check.<br /><em>In the review.</em></h2></div><p>Patient context, prescription text, deterministic rules, and evidence remain visible before a clinician takes action.</p></div>
        <div className="workflow-line">{workflow.map((step, index) => {
          const Icon = workflowIcons[index];
          return (
            <div className="workflow-step" key={step.number}>
              <span className="workflow-number">{step.number}</span>
              <div className="workflow-icon"><span><Icon size={17} /></span></div>
              <h3>{step.title}</h3>
              <p>{step.text}</p>
              {index < workflow.length - 1 && <ArrowRight className="workflow-arrow" size={16} />}
            </div>
          );
        })}</div>
      </section>

      <section className="landing-capabilities" id="capabilities">
        <div className="section-heading capability-heading"><div><p className="eyebrow">A clear reason behind every recommendation</p><h2>Built for decisions<br /><em>that deserve more context.</em></h2></div><p>Precision without noise. A calm interface for patient details, prescription checks, evidence sources, and deliberate clinician action.</p></div>
        <div className="feature-grid">{features.map(({ icon: Icon, index, title, text }) => <article className="feature-item" key={title}><div className="feature-top"><Icon size={18} strokeWidth={1.7} /><span>{index}</span></div><h3>{title}</h3><p>{text}</p><ArrowRight className="feature-arrow" size={15} /></article>)}</div>
      </section>

      <section className="landing-final-cta"><div className="final-orb"><div /><div /><div /></div><div><p className="eyebrow">Authorized clinical workspace</p><h2>Review the signal.<br /><em>Document the decision.</em></h2></div><Link href="/review" className="landing-primary-cta">Open Clinical Review <ArrowRight size={17} /></Link></section>

      <footer className="landing-footer"><span>AntiBioTix</span><span>Reliable. Precise. Traceable.</span><span>Clinical decision support only.</span></footer>
    </main>
  );
}
