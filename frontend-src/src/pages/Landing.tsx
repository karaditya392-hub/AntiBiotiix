import { useRef, useState } from "react";
import {
  Activity,
  AlertTriangle,
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
import { Link } from "wouter";
import logoSrc from "@/assets/antibiotix-logo.jpg";
import { WebcamPixelGrid } from "@/components/ui/webcam-pixel-grid";
import MacbookScrollDemo from "@/components/macbook-scroll-demo";
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

const demoScenarios = [
  {
    id: "cap-penicillin",
    title: "Community-Acquired Pneumonia",
    patientName: "PATIENT-001 (Rajesh Sharma)",
    ageSex: "45 yrs · Male",
    drug: "Amoxicillin 500mg PO TID x 7 days",
    warning: "ALLERGY-001: Severe Penicillin Anaphylaxis",
    recommendation: "Switch to Macrolide (Azithromycin 500mg PO QD) or Respiratory Fluoroquinolone per ICMR STG 2022.",
    evidence: "ICMR Treatment Guidelines 2022: Beta-lactams contraindicated in documented IgE-mediated anaphylaxis.",
    priority: "HIGH SEVERITY",
  },
  {
    id: "uti-ckd",
    title: "Acute Cystitis in CKD Stage 4",
    patientName: "PATIENT-002 (Sunita Devi)",
    ageSex: "68 yrs · Female",
    drug: "Nitrofurantoin 100mg PO BID x 5 days",
    warning: "RENAL-001: Contraindicated in severe renal impairment (eGFR <30 mL/min)",
    recommendation: "Avoid Nitrofurantoin (eGFR 22 mL/min). Recommend Fosfomycin 3g PO single dose or Ceftriaxone IV.",
    evidence: "ICMR STG 2022 / FDA DailyMed: Inadequate urinary concentration and neurotoxicity risk when eGFR <30 mL/min.",
    priority: "CRITICAL SEVERITY",
  },
  {
    id: "cirrhosis-metronidazole",
    title: "Intra-abdominal Infection in Cirrhosis",
    patientName: "PATIENT-003 (Amitabh Verma)",
    ageSex: "54 yrs · Male",
    drug: "Metronidazole 500mg IV TID x 10 days",
    warning: "HEPATIC-002: Hepatic clearance impaired in Child-Pugh Class C",
    recommendation: "Reduce dose by 50% (500mg IV Q12H-Q24H) to prevent systemic drug accumulation and encephalopathy.",
    evidence: "WHO AWaRe 2023 / DailyMed: Severe hepatic impairment impairs drug metabolism; plasma clearance reduced by 65%.",
    priority: "HIGH SEVERITY",
  },
  {
    id: "pregnancy-cipro",
    title: "Pyelonephritis in 2nd Trimester",
    patientName: "PATIENT-004 (Priya Patel)",
    ageSex: "28 yrs · Female (Pregnant 24 wks)",
    drug: "Ciprofloxacin 500mg PO BID x 7 days",
    warning: "TERATOGEN-001: Fluoroquinolones carry cartilage toxicity risk in pregnancy",
    recommendation: "Avoid Ciprofloxacin in 2nd trimester. Recommend Ceftriaxone 1g IV QD or Cephalexin 500mg PO QID.",
    evidence: "ICMR STG 2022 / FDA Pregnancy Category C: Quinolones cause arthropathy in immature animal models.",
    priority: "CRITICAL SEVERITY",
  },
];

export default function Landing() {
  const [selectedScenario, setSelectedScenario] = useState(demoScenarios[0]);
  const heroVisualRef = useRef<HTMLDivElement>(null);

  const handleHeroMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!heroVisualRef.current) return;
    const { left, top, width, height } = heroVisualRef.current.getBoundingClientRect();
    const x = (e.clientX - left - width / 2) / 30;
    const y = (e.clientY - top - height / 2) / 30;
    heroVisualRef.current.style.transform = `rotateY(${x}deg) rotateX(${-y}deg)`;
  };

  const handleHeroMouseLeave = () => {
    if (!heroVisualRef.current) return;
    heroVisualRef.current.style.transform = "rotateY(0deg) rotateX(0deg)";
  };

  return (
    <main className="landing-page" style={{ position: "relative" }}>
      {/* FULL BACKGROUND WEBCAM PIXEL GRID */}
      <div className="absolute inset-0 opacity-20 pointer-events-none overflow-hidden" style={{ zIndex: 0 }}>
        <WebcamPixelGrid
          gridCols={64}
          gridRows={48}
          maxElevation={40}
          motionSensitivity={0.3}
          elevationSmoothing={0.15}
          colorMode="monochrome"
          monochromeColor="#328b70"
          backgroundColor="transparent"
          mirror={true}
          gapRatio={0.06}
          darken={0.5}
          borderColor="#97e2d3"
          borderOpacity={0.1}
          className="w-full h-full"
        />
      </div>
      {/* 1. TOP BRANDING & NAVIGATION HEADER */}
      <header className="landing-nav">
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
          <a href="#scenarios">Live Scenarios</a>
          <Link href="/clinical-tools" className="landing-secondary-cta" style={{ fontSize: "0.82rem", marginRight: "6px" }}>
            Clinical Tools
          </Link>
          <Link href="/patient-type" className="landing-nav-cta">
            Start Patient Visit <ArrowRight size={15} />
          </Link>
        </nav>
      </header>

      {/* 2. HERO SECTION */}
      <section className="landing-hero" aria-labelledby="landing-title">
        <div className="landing-hero-copy">
          <div className="hero-signal">
            <span className="signal-pulse" /> Evidence-linked antimicrobial review
          </div>
          <h1 id="landing-title">
            Clinical decisions,<br />
            <em>supported by evidence.</em>
          </h1>
          <p className="landing-lede">
            Review prescriptions against patient-specific risks, antimicrobial guidelines, and resistance patterns &mdash; while keeping the clinician firmly in control.
          </p>
          <div className="landing-actions">
            <Link href="/patient-type" className="landing-primary-cta">
              Start Patient Visit <ArrowRight size={17} />
            </Link>
            <a href="#scenarios" className="landing-secondary-cta">
              Explore Live Scenarios <span>&#8600;</span>
            </a>
          </div>
          <div className="hero-proof">
            <Check size={14} />
            <span>Clinical decision support only &mdash; never an autonomous prescribing system.</span>
          </div>
        </div>

        {/* HERO 3D VISUAL STAGE */}
        <div
          ref={heroVisualRef}
          className="hero-visual"
          aria-label="Evidence and prescription review visualization"
          onMouseMove={handleHeroMouseMove}
          onMouseLeave={handleHeroMouseLeave}
          style={{ transition: "transform 0.15s ease-out", transformStyle: "preserve-3d" }}
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

          <div className="visual-console-card">
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
          </div>
        </div>
      </section>

      {/* 3. VALUE PROPOSITION STRIP */}
      <section className="landing-intro-strip">
        <span>CLINICAL DECISION SUPPORT</span>
        <p>
          Patient context, prescription details, 24 deterministic safety rules, ICMR/WHO evidence sources, and clinician override rationale in one unified flow.
        </p>
        <span>IST TIMEZONE INTEGRATED</span>
      </section>

      {/* 4. INTERACTIVE CLINICAL SCENARIOS SHOWCASE */}
      <section className="landing-workflow" id="scenarios" style={{ paddingBottom: "3rem" }}>
        <div className="section-heading">
          <div>
            <p className="eyebrow">INTERACTIVE SAFETY DEMONSTRATION</p>
            <h2>
              Test Real Clinical Scenarios.<br />
              <em>Before Starting a Visit.</em>
            </h2>
          </div>
          <p>
            Select any teaching scenario below to inspect how the 24-rule safety engine evaluates allergies, organ impairment, and guideline recommendations in real time.
          </p>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1.3fr", gap: "24px", alignItems: "start" }}>
          {/* SCENARIO SELECTOR BUTTONS */}
          <div style={{ display: "grid", gap: "10px" }}>
            {demoScenarios.map((sc) => (
              <button
                key={sc.id}
                type="button"
                onClick={() => setSelectedScenario(sc)}
                style={{
                  background: selectedScenario.id === sc.id ? "rgba(15,119,116,0.3)" : "rgba(9,44,46,0.66)",
                  border: `1.5px solid ${selectedScenario.id === sc.id ? "#8ed2c2" : "rgba(160,221,208,0.2)"}`,
                  borderRadius: "8px",
                  padding: "16px",
                  textAlign: "left",
                  color: "#e5f1ee",
                  cursor: "pointer",
                  transition: "all 0.18s ease",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <strong style={{ fontSize: "0.95rem", color: "#f2f9f7" }}>{sc.title}</strong>
                  <span style={{ fontSize: "0.68rem", fontWeight: 700, color: sc.priority.includes("CRITICAL") ? "#e2bd72" : "#8ed2c2" }}>
                    {sc.priority}
                  </span>
                </div>
                <p style={{ margin: "4px 0 0", fontSize: "0.78rem", color: "#98b0ab" }}>
                  {sc.patientName} · {sc.ageSex}
                </p>
              </button>
            ))}
          </div>

          {/* LIVE SCENARIO EVALUATION CARD */}
          <div
            style={{
              background: "#0c3537",
              border: "1.5px solid rgba(143,218,202,0.3)",
              borderRadius: "10px",
              padding: "24px",
              boxShadow: "0 16px 36px rgba(0,0,0,0.3)",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
              <span style={{ fontSize: "0.7rem", fontWeight: 700, color: "#8ed2c2", letterSpacing: "0.08em" }}>
                SAFETY ENGINE ANALYSIS
              </span>
              <span style={{ background: "rgba(226,189,114,0.18)", color: "#e2bd72", padding: "3px 8px", borderRadius: "4px", fontSize: "0.72rem", fontWeight: 700 }}>
                {selectedScenario.priority}
              </span>
            </div>

            <h3 style={{ margin: "0 0 4px", fontSize: "1.1rem", color: "#f2f9f7" }}>{selectedScenario.title}</h3>
            <p style={{ margin: "0 0 16px", fontSize: "0.82rem", color: "#9eb5b1" }}>
              Patient: <strong>{selectedScenario.patientName}</strong> ({selectedScenario.ageSex})
            </p>

            <div style={{ background: "#082425", border: "1px solid rgba(143,218,202,0.2)", padding: "12px", borderRadius: "6px", marginBottom: "14px" }}>
              <small style={{ color: "#789894", fontSize: "0.68rem", fontWeight: 700 }}>PRESCRIBED ORDER</small>
              <p style={{ margin: "4px 0 0", fontWeight: 700, color: "#96d7c7", fontSize: "0.9rem" }}>{selectedScenario.drug}</p>
            </div>

            <div style={{ background: "rgba(163,61,49,0.15)", border: "1px solid rgba(224,180,172,0.3)", padding: "12px", borderRadius: "6px", marginBottom: "14px" }}>
              <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                <AlertTriangle size={16} color="#e2bd72" />
                <strong style={{ color: "#e2bd72", fontSize: "0.88rem" }}>{selectedScenario.warning}</strong>
              </div>
              <p style={{ margin: "6px 0 0", color: "#e5f1ee", fontSize: "0.82rem" }}>
                <b>Clinical Recommendation:</b> {selectedScenario.recommendation}
              </p>
            </div>

            <div style={{ background: "#082425", border: "1px solid rgba(143,218,202,0.2)", padding: "12px", borderRadius: "6px", fontSize: "0.78rem", color: "#98b0ab" }}>
              <b>Guideline Provenance:</b> {selectedScenario.evidence}
            </div>

            <div style={{ marginTop: "16px", display: "flex", justifyContent: "flex-end" }}>
              <Link href="/patient-type" className="landing-primary-cta" style={{ padding: "8px 16px", fontSize: "0.8rem" }}>
                Start Patient Visit <ArrowRight size={15} />
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* 5. 4-STEP WORKFLOW REVIEW PATH */}
      <section className="landing-workflow" id="workflow">
        <div className="section-heading">
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
        </div>

        <div className="workflow-line">
          {workflow.map((step, index) => {
            const Icon = step.icon;
            return (
              <div className="workflow-step" key={step.number}>
                <span className="workflow-number">{step.number}</span>
                <div className="workflow-icon">
                  <Icon size={17} />
                </div>
                <h3>{step.title}</h3>
                <p>{step.text}</p>
                {index < workflow.length - 1 && <ArrowRight className="workflow-arrow" size={16} />}
              </div>
            );
          })}
        </div>
      </section>

      {/* 6. CAPABILITIES & SAFETY SIGNALS GRID */}
      <section className="landing-capabilities" id="capabilities">
        <div className="section-heading capability-heading">
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
        </div>

        <div className="feature-grid">
          {features.map(({ icon: Icon, index, title, text }) => (
            <article className="feature-item" key={title}>
              <div className="feature-top">
                <Icon size={18} strokeWidth={1.7} />
                <span>{index}</span>
              </div>
              <h3>{title}</h3>
              <p>{text}</p>
              <ArrowRight className="feature-arrow" size={15} />
            </article>
          ))}
        </div>
      </section>

      {/* 6.5 INTERACTIVE MACBOOK SCROLL FEATURE */}
      <section style={{ position: "relative", zIndex: 1, overflow: "hidden" }}>
        <MacbookScrollDemo />
      </section>

      {/* 7. FINAL CALL TO ACTION */}
      <section className="landing-final-cta">
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
        <Link href="/patient-type" className="landing-primary-cta">
          Start Patient Visit <ArrowRight size={17} />
        </Link>
      </section>

      {/* 8. FOOTER */}
      <footer className="landing-footer">
        <span>AntiBioTix v1.4.0</span>
        <span>Reliable. Precise. Traceable.</span>
        <span>Clinical decision support only.</span>
      </footer>
    </main>
  );
}