import { useEffect, useRef, useState } from "react";
import {
  Activity,
  ArrowRight,
  BookOpenCheck,
  Check,
  CheckCircle2,
  ClipboardCheck,
  FileCheck2,
  LockKeyhole,
  Network,
  Pill,
  ShieldCheck,
  Sparkles,
  Stethoscope,
  UserCheck,
} from "lucide-react";
import { LazyMotion, MotionConfig, domAnimation, m, useMotionValue, useReducedMotion, useScroll, useSpring, useTransform } from "motion/react";
import { Link } from "wouter";
import logoSrc from "@/assets/antibiotix-logo.jpg";
import "@/styles/landing.css";

const features = [
  {
    icon: ClipboardCheck,
    index: "01",
    title: "Prescription safety review",
    text: "Patient-specific context stays beside the prescription, so each concern is visible before taking action.",
  },
  {
    icon: ShieldCheck,
    index: "02",
    title: "Risk-aware checks",
    text: "Surface allergy cross-reactivity, renal (CKD-EPI 2021), hepatic, pregnancy, and DDI considerations.",
  },
  {
    icon: BookOpenCheck,
    index: "03",
    title: "Guideline precedence",
    text: "Keep local hospital guidance, national ICMR 2022-23 recommendations, and WHO AWaRe in a 3-tier precedence hierarchy.",
  },
  {
    icon: FileCheck2,
    index: "04",
    title: "Evidence-linked warnings",
    text: "Trace each warning back to the specific rule ID, guideline version, and exact verbatim passage.",
  },
  {
    icon: LockKeyhole,
    index: "05",
    title: "Clinician control",
    text: "Professional judgment stays in the loop, with deliberate clinical rationale captured in the audit trail.",
  },
  {
    icon: Activity,
    index: "06",
    title: "Stewardship visibility",
    text: "Turn review activity into clear metrics tracking priority tiers and alert recalibration targets.",
  },
];

const workflow = [
  {
    number: "01",
    title: "Context",
    text: "Select a returning patient or register a new record with demographics, allergies, and organ function.",
    icon: UserCheck,
  },
  {
    number: "02",
    title: "Prescription",
    text: "Enter medication orders with structured dose, route, frequency, and indication parsing.",
    icon: Pill,
  },
  {
    number: "03",
    title: "Evidence",
    text: "Evaluate against 24 deterministic safety rules, ICMR guidelines, and WHO AWaRe classifications.",
    icon: BookOpenCheck,
  },
  {
    number: "04",
    title: "Action",
    text: "Decide, document overrides with substantive clinical rationale, and export official prescription PDFs.",
    icon: CheckCircle2,
  },
];

/**
 * One easing curve for the whole page. Independent animations only read as a
 * single system if they share a curve - mixing eases is what makes a page feel
 * assembled out of unrelated parts.
 */
const EASE: [number, number, number, number] = [0.16, 1, 0.3, 1];

const fadeUp = {
  hidden: { opacity: 0, y: 28 },
  show: { opacity: 1, y: 0, transition: { duration: 0.7, ease: EASE } },
};

const fadeIn = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { duration: 0.7, ease: EASE } },
};

/** A parent that releases its children one after another. */
const group = (staggerChildren: number, delayChildren = 0) => ({
  hidden: {},
  show: { transition: { staggerChildren, delayChildren } },
});

/**
 * Reveal-on-scroll defaults. `once` matters: without it every section
 * re-animates each time it scrolls back into view, which reads as a glitch
 * rather than a flourish.
 */
const reveal = {
  initial: "hidden",
  whileInView: "show",
  viewport: { once: true, amount: 0.25 },
} as const;

/** Short and springy - this is feedback on a pointer, not a page transition. */
const press = { type: "spring", stiffness: 400, damping: 26 } as const;

/**
 * wouter's Link forwards its ref to the underlying anchor, so it can be animated
 * directly rather than wrapped in an extra element. Its own props are generic
 * over the location hook, which leaves TypeScript unable to see `className`
 * through the motion wrapper - narrowing to the props actually used here keeps
 * the call site type-checked instead of reaching for `any`.
 */
type AnchorLinkProps = {
  href: string;
  className?: string;
  children?: React.ReactNode;
  style?: React.CSSProperties;
  "aria-label"?: string;
};

const MotionLink = m.create(
  Link as React.ForwardRefExoticComponent<AnchorLinkProps & React.RefAttributes<HTMLAnchorElement>>
);

export default function Landing() {
  const heroVisualRef = useRef<HTMLDivElement>(null);

  /**
   * Motion animates against the wall clock, so an entrance started at mount runs
   * *through* the bundle-parse and hydration stall that follows it. Measured on
   * this page, ~70% of the fade elapsed during a 153ms frame gap and the first
   * painted frame already showed it 77% complete - which reads as "nothing
   * animated". Waiting for two frames means the browser has painted once and the
   * main thread is clear before the clock starts.
   */
  const [ready, setReady] = useState(false);
  useEffect(() => {
    let second = 0;
    let idle: number | undefined;
    // Two frames gets us past the first paint; the idle callback then waits for
    // the remaining parse/hydration work to drain, because that is where the
    // frame gaps were. The timeout is the guarantee - on a busy page idle may
    // never arrive, and a late entrance is better than none.
    const start = () => {
      const ric = (window as unknown as {
        requestIdleCallback?: (cb: () => void, opts?: { timeout: number }) => number;
      }).requestIdleCallback;
      if (ric) {
        idle = ric(() => setReady(true), { timeout: 250 });
      } else {
        idle = window.setTimeout(() => setReady(true), 120);
      }
    };
    const first = requestAnimationFrame(() => {
      second = requestAnimationFrame(start);
    });
    return () => {
      cancelAnimationFrame(first);
      cancelAnimationFrame(second);
      if (idle !== undefined) {
        const cic = (window as unknown as {
          cancelIdleCallback?: (h: number) => void;
        }).cancelIdleCallback;
        cic ? cic(idle) : clearTimeout(idle);
      }
    };
  }, []);

  // Reading indicator across the top of the page. The spring keeps the bar from
  // twitching on every wheel tick while still tracking the scroll closely.
  const { scrollY, scrollYProgress } = useScroll();
  const progressScaleX = useSpring(scrollYProgress, {
    stiffness: 120,
    damping: 30,
    restDelta: 0.001,
  });

  // MotionConfig's reducedMotion setting only filters animations - a motion
  // value wired straight to scroll or pointer position keeps moving. Parallax
  // and tilt are exactly the sustained movement that triggers vestibular
  // symptoms, so gate them on the same preference by hand.
  const prefersReducedMotion = useReducedMotion();

  // The hero stage drifts upward slightly as the page scrolls past it.
  const heroDriftRaw = useTransform(scrollY, [0, 700], [0, -48]);
  const heroDrift = prefersReducedMotion ? 0 : heroDriftRaw;

  // Pointer tilt, held in motion values so it never touches React's render
  // path - routing a mousemove through useState would re-render the whole page
  // sixty times a second.
  const tiltY = useMotionValue(0);
  const tiltX = useMotionValue(0);
  const rotateYRaw = useSpring(tiltY, { stiffness: 140, damping: 18, mass: 0.6 });
  const rotateXRaw = useSpring(tiltX, { stiffness: 140, damping: 18, mass: 0.6 });
  const rotateY = prefersReducedMotion ? 0 : rotateYRaw;
  const rotateX = prefersReducedMotion ? 0 : rotateXRaw;

  const handleHeroMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (prefersReducedMotion || !heroVisualRef.current) return;
    const { left, top, width, height } = heroVisualRef.current.getBoundingClientRect();
    tiltY.set((e.clientX - left - width / 2) / 30);
    tiltX.set(-(e.clientY - top - height / 2) / 30);
  };

  const handleHeroMouseLeave = () => {
    tiltY.set(0);
    tiltX.set(0);
  };

  return (
    // "user" honours prefers-reduced-motion: transform and layout animations are
    // dropped while opacity still resolves, so the page stays legible and
    // nothing vanishes for people who get motion sick.
    <MotionConfig reducedMotion="user">
      <LazyMotion features={domAnimation}>
      <main className="landing-page">
        <m.div className="landing-scroll-progress" style={{ scaleX: progressScaleX }} />

        {/* 1. TOP BRANDING & NAVIGATION HEADER */}
        <m.header
          className="landing-nav"
          initial={{ y: -22, opacity: 0 }}
          animate={ready ? { y: 0, opacity: 1 } : { y: -22, opacity: 0 }}
          transition={{ duration: 0.6, ease: EASE }}
        >
          <Link href="/" className="landing-brand" aria-label="AntiBioTix home">
            <span className="landing-brand-mark">
              <img src={logoSrc} alt="AntiBioTix logo" />
            </span>
            <span>
              <strong>AntiBioTix</strong>
              <small>Clinical decision support</small>
            </span>
          </Link>
          <nav aria-label="Primary navigation">
            <a href="#capabilities">Safety signals</a>
            <a href="#workflow">Review path</a>
            <Link href="/clinical-tools" className="landing-secondary-cta" style={{ fontSize: "0.82rem", marginRight: "6px" }}>
              Clinical Tools
            </Link>
            <MotionLink
              href="/patient-type"
              className="landing-nav-cta"
              whileHover={{ y: -2, transition: press }}
              whileTap={{ scale: 0.97, transition: press }}
            >
              Start Patient Visit <ArrowRight size={15} />
            </MotionLink>
          </nav>
        </m.header>

        {/* 2. HERO SECTION */}
        <section className="landing-hero" aria-labelledby="landing-title">
          <m.div
            className="landing-hero-copy"
            variants={group(0.13, 0.08)}
            initial="hidden"
            animate={ready ? "show" : "hidden"}
          >
            <m.div className="hero-signal" variants={fadeUp}>
              <span className="signal-pulse" /> Evidence-linked antimicrobial review
            </m.div>
            <m.h1 id="landing-title" variants={fadeUp}>
              Clinical decisions,<br />
              <em>supported by evidence.</em>
            </m.h1>
            <m.p className="landing-lede" variants={fadeUp}>
              Review prescriptions against patient-specific risks, antimicrobial guidelines, and resistance patterns &mdash; while keeping the clinician firmly in control.
            </m.p>
            <m.div className="landing-actions" variants={fadeUp}>
              <MotionLink
                href="/patient-type"
                className="landing-primary-cta"
                whileHover={{ y: -2, transition: press }}
                whileTap={{ scale: 0.97, transition: press }}
              >
                Start Patient Visit <ArrowRight size={17} />
              </MotionLink>
            </m.div>
            <m.div className="hero-proof" variants={fadeUp}>
              <Check size={14} />
              <span>Clinical decision support only &mdash; never an autonomous prescribing system.</span>
            </m.div>
          </m.div>

          {/* HERO 3D VISUAL STAGE */}
          <m.div
            ref={heroVisualRef}
            className="hero-visual"
            aria-label="Evidence and prescription review visualization"
            onMouseMove={handleHeroMouseMove}
            onMouseLeave={handleHeroMouseLeave}
            initial={{ opacity: 0, scale: 0.94 }}
            animate={ready ? { opacity: 1, scale: 1 } : { opacity: 0, scale: 0.94 }}
            transition={{ duration: 0.9, delay: 0.1, ease: EASE }}
            // The orbit scene, chips and console card inside carry their own CSS
            // keyframe transforms, so Motion only drives this container.
            style={{ rotateX, rotateY, y: heroDrift, transformStyle: "preserve-3d" }}
          >
            <div className="visual-caption visual-caption-top">
              <span>LIVE EVIDENCE LAYER</span>
              <b>01</b>
            </div>

            <div className="orbit-scene">
              <div className="orbit orbit-one" />
              <div className="orbit orbit-two" />
              <div className="orbit orbit-three" />

              <div className="evidence-core">
                <div className="core-halo" />
                <div className="core-mark">
                  <img src={logoSrc} alt="AntiBioTix Core" />
                </div>
                <span className="core-label">ANTIBIOTIX</span>
                <strong>
                  Evidence
                  <br />
                  in context.
                </strong>
              </div>

              <div className="orbit-node node-guideline">
                <BookOpenCheck size={15} />
                <span>Guideline</span>
              </div>

              <div className="orbit-node node-patient">
                <Stethoscope size={15} />
                <span>Patient</span>
              </div>

              <div className="orbit-node node-audit">
                <Network size={15} />
                <span>24-Rule Engine</span>
              </div>

              <div className="floating-chip chip-warning">
                <span className="chip-dot" /> 1 attention item
              </div>

              <div className="floating-chip chip-status">
                <Sparkles size={13} /> traceable
              </div>
            </div>

            <m.div
              className="visual-console-card"
              initial={{ opacity: 0, y: 34 }}
              animate={ready ? { opacity: 1, y: 0 } : { opacity: 0, y: 34 }}
              transition={{ duration: 0.75, delay: 0.55, ease: EASE }}
            >
              <div className="console-card-top">
                <span>
                  <i /> Clinical Safety Review
                </span>
                <small>READY</small>
              </div>
              <div className="console-card-body">
                <div className="console-rail">
                  <span className="active" />
                  <span />
                  <span />
                  <span />
                </div>
                <div className="console-content">
                  <small className="console-kicker">CURRENT PRESCRIPTION ORDER</small>
                  <div className="console-drug">
                    <div>
                      <strong>Amoxicillin 500 mg</strong>
                      <span>PO &middot; three times daily &middot; 7 days</span>
                    </div>
                    <b>REVIEWING</b>
                  </div>
                  <div className="console-meta">
                    <span>
                      <small>PATIENT CONTEXT</small>
                      <strong>PATIENT-001 &middot; 45 yrs (Male)</strong>
                    </span>
                    <span>
                      <small>RULE EVALUATION</small>
                      <strong className="attention">1 Penicillin Allergy Alert</strong>
                    </span>
                  </div>
                  <div className="console-source">
                    <FileCheck2 size={14} />
                    <span>
                      <small>EVIDENCE SOURCE</small>
                      <strong>ICMR National Guidelines &middot; 2022-23</strong>
                    </span>
                    <em>VIEW RULE</em>
                  </div>
                </div>
              </div>
            </m.div>
          </m.div>
        </section>

        {/* 3. VALUE PROPOSITION STRIP */}
        <m.section className="landing-intro-strip" variants={fadeIn} {...reveal}>
          <span>CLINICAL DECISION SUPPORT</span>
          <p>
            Patient context, prescription details, 24 deterministic safety rules, ICMR/WHO evidence sources, and clinician override rationale in one unified flow.
          </p>
          <span>IST TIMEZONE INTEGRATED</span>
        </m.section>

        {/* 5. 4-STEP WORKFLOW REVIEW PATH */}
        <section className="landing-workflow" id="workflow">
          <m.div className="section-heading" variants={fadeUp} {...reveal}>
            <div>
              <p className="eyebrow">A VISIBLE PATH FROM INPUT TO ACTION</p>
              <h2>
                Every check.<br />
                <em>In the review.</em>
              </h2>
            </div>
            <p>
              Patient context, prescription text, 24 deterministic rules, and guideline evidence remain visible before a clinician takes action.
            </p>
          </m.div>

          <m.div className="workflow-line" variants={group(0.09)} {...reveal}>
            {workflow.map((step, index) => {
              const Icon = step.icon;
              return (
                <m.div className="workflow-step" key={step.number} variants={fadeUp}>
                  <span className="workflow-number">{step.number}</span>
                  <div className="workflow-icon">
                    <Icon size={17} />
                  </div>
                  <h3>{step.title}</h3>
                  <p>{step.text}</p>
                  {index < workflow.length - 1 && <ArrowRight className="workflow-arrow" size={16} />}
                </m.div>
              );
            })}
          </m.div>
        </section>

        {/* 6. CAPABILITIES & SAFETY SIGNALS GRID */}
        <section className="landing-capabilities" id="capabilities">
          <m.div className="section-heading capability-heading" variants={fadeUp} {...reveal}>
            <div>
              <p className="eyebrow">A CLEAR REASON BEHIND EVERY RECOMMENDATION</p>
              <h2>
                Built for decisions<br />
                <em>that deserve more context.</em>
              </h2>
            </div>
            <p>
              Precision without noise. A calm, evidence-grounded interface for patient details, prescription checks, evidence sources, and deliberate clinician action.
            </p>
          </m.div>

          <m.div className="feature-grid" variants={group(0.06)} {...reveal}>
            {features.map(({ icon: Icon, index, title, text }) => (
              <m.article
                className="feature-item"
                key={title}
                variants={fadeUp}
                whileHover={{ y: -4, transition: press }}
              >
                <div className="feature-top">
                  <Icon size={18} strokeWidth={1.7} />
                  <span>{index}</span>
                </div>
                <h3>{title}</h3>
                <p>{text}</p>
                <ArrowRight className="feature-arrow" size={15} />
              </m.article>
            ))}
          </m.div>
        </section>

        {/* 7. FINAL CALL TO ACTION */}
        <m.section
          className="landing-final-cta"
          variants={{
            hidden: { opacity: 0, y: 26, scale: 0.985 },
            show: { opacity: 1, y: 0, scale: 1, transition: { duration: 0.6, ease: EASE } },
          }}
          {...reveal}
        >
          <div className="final-orb">
            <div />
            <div />
            <div />
          </div>
          <div>
            <p className="eyebrow">Authorized clinical workspace</p>
            <h2>
              Review the signal.<br />
              <em>Document the decision.</em>
            </h2>
          </div>
          <MotionLink
            href="/patient-type"
            className="landing-primary-cta"
            whileHover={{ y: -2, transition: press }}
            whileTap={{ scale: 0.97, transition: press }}
          >
            Start Patient Visit <ArrowRight size={17} />
          </MotionLink>
        </m.section>

        {/* 8. FOOTER */}
        <m.footer className="landing-footer" variants={fadeIn} {...reveal}>
          <span>AntiBioTix v1.4.0</span>
          <span>Reliable. Precise. Traceable.</span>
          <span>Clinical decision support only.</span>
        </m.footer>
      </main>
      </LazyMotion>
    </MotionConfig>
  );
}
