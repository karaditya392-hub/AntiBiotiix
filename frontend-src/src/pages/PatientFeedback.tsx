import { useState } from "react";
import { HeartPulse, ShieldAlert, CheckCircle2, ArrowRight } from "lucide-react";
import "@/styles/patient-dashboard.css";

/**
 * The patient-facing follow-up page. PUBLIC — a patient has no login here.
 *
 * Access is by the per-visit code printed on their visit summary, never by name.
 * A name box on a public page would hand anyone who guesses "Rajesh Sharma" that
 * patient's medications and diagnosis, which is not a trade this system should
 * make for one field of convenience.
 *
 * What this page does NOT do, and says so rather than implying otherwise: it does
 * not prompt the patient on a schedule, and it is not monitored continuously.
 */
export default function PatientFeedback() {
  const [code, setCode] = useState("");
  const [context, setContext] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const [feeling, setFeeling] = useState("");
  const [helped, setHelped] = useState("");
  const [doses, setDoses] = useState("");
  const [discomfort, setDiscomfort] = useState("");
  const [submitted, setSubmitted] = useState(false);

  async function lookup(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await fetch(`/api/feedback/${encodeURIComponent(code.trim())}`);
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || "That code was not recognised.");
      }
      setContext(await res.json());
    } catch (err: any) {
      setError(err.message || "Could not look up that code.");
    } finally {
      setLoading(false);
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (!feeling || !helped) {
      setError("Please answer the first two questions before sending.");
      return;
    }
    setLoading(true);
    try {
      const res = await fetch(`/api/feedback/${encodeURIComponent(code.trim())}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ feeling, medicines_helped: helped, doses_taken: doses, discomfort }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || "Could not send your answers.");
      }
      setSubmitted(true);
    } catch (err: any) {
      setError(err.message || "Could not send your answers.");
    } finally {
      setLoading(false);
    }
  }

  // Question hints. A follow-up form is read by someone who is unwell and may be
  // reading it in a second language, so each question says what to think about
  // rather than assuming the short version is obvious.
  const hintStyle: React.CSSProperties = {
    fontSize: "0.79rem",
    color: "#607371",
    margin: "4px 0 0",
    lineHeight: 1.5,
  };

  const choice = (value: string, current: string, set: (v: string) => void, label: string) => (
    <button
      type="button"
      key={value}
      onClick={() => set(value)}
      className={`dashboard-button ${current === value ? "primary" : "secondary"}`}
      style={{ justifyContent: "center", padding: "10px 14px", flex: "1 1 120px" }}
    >
      {label}
    </button>
  );

  return (
    <main className="dashboard-page" style={{ maxWidth: "720px", margin: "0 auto" }}>
      <div style={{ marginBottom: "18px" }}>
        <p className="dashboard-kicker">ANTIBIOTIX PATIENT FOLLOW-UP</p>
        <h1 style={{ fontFamily: "Space Grotesk, sans-serif", fontSize: "2rem", color: "#173c3d", margin: "4px 0" }}>
          How are you doing?
        </h1>
        <p className="dashboard-subtitle" style={{ fontSize: "0.92rem" }}>
          A few questions from your clinician about how your treatment is going.
        </p>
      </div>

      {/* Stated before anything else, not buried at the bottom. A patient who is
          seriously unwell must not be waiting on a form nobody is watching. */}
      <div style={{ background: "#fdf3e3", border: "1px solid #e0c9a0", borderLeft: "3px solid #c86d38",
                    borderRadius: "6px", padding: "10px 12px", marginBottom: "18px",
                    fontSize: "0.8rem", color: "#8a4b1f", display: "flex", gap: "8px" }}>
        <ShieldAlert size={16} style={{ flexShrink: 0, marginTop: "1px" }} />
        <span>
          This form is read by your clinician during working hours and is <b>not monitored
          continuously</b>. If you feel seriously unwell, contact your doctor or emergency
          services directly.
        </span>
      </div>

      {!context && (
        <section className="info-section" style={{ background: "#ffffff", padding: "20px" }}>
          <form onSubmit={lookup}>
            <label className="field-label">Your visit code</label>
            <p className="muted" style={{ fontSize: "0.78rem", margin: "2px 0 8px" }}>
              This is on the visit summary your clinician gave you. It is eight characters,
              for example <code>TWWQ9JRX</code>.
            </p>
            <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
              <input
                type="text"
                value={code}
                onChange={(e) => setCode(e.target.value.toUpperCase())}
                placeholder="Enter your code"
                className="dashboard-select"
                style={{ flex: "1 1 220px", letterSpacing: "0.14em", fontFamily: "IBM Plex Mono, monospace" }}
                autoFocus
              />
              <button type="submit" className="dashboard-button primary" disabled={loading || !code.trim()}>
                {loading ? "Checking..." : <>Continue <ArrowRight size={16} /></>}
              </button>
            </div>
          </form>
          {error && <p className="form-error" style={{ marginTop: "10px" }}>{error}</p>}
        </section>
      )}

      {context && context.can_submit && !submitted && (
        <section className="info-section" style={{ background: "#ffffff", padding: "20px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "4px" }}>
            <HeartPulse size={18} color="#2d7064" />
            <h2 style={{ margin: 0, fontSize: "1.1rem", color: "#173c3d" }}>
              Hello {context.patient_name}
            </h2>
          </div>
          <p className="muted" style={{ fontSize: "0.8rem", margin: "0 0 14px" }}>
            About your visit for <b>{context.diagnosis || "your recent consultation"}</b>.
          </p>

          {context.medications?.length > 0 && (
            <div style={{ background: "#f0f6f1", border: "1px solid #d0e2d8", borderRadius: "6px",
                          padding: "10px 12px", marginBottom: "16px", fontSize: "0.84rem" }}>
              <b style={{ color: "#173c3d" }}>You were prescribed</b>
              <ul style={{ margin: "6px 0 0", paddingLeft: "20px" }}>
                {context.medications.map((m: any, i: number) => (
                  <li key={i}>
                    {m.medication_name} {m.dose} {m.unit} {m.route} {m.frequency}
                    {m.duration_days ? ` for ${m.duration_days} days` : ""}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <form onSubmit={submit} style={{ display: "grid", gap: "16px" }}>
            <div>
              <label className="field-label">
                1. Compared with how you felt on the day of your visit, how are you now?
              </label>
              <p style={hintStyle}>
                Think about the symptoms that brought you in &mdash; fever, pain, cough,
                burning, swelling. Answer for those, not for how you feel in general.
              </p>
              <div style={{ display: "flex", gap: "8px", marginTop: "6px", flexWrap: "wrap" }}>
                {choice("BETTER", feeling, setFeeling, "Better than on the visit day")}
                {choice("SAME", feeling, setFeeling, "About the same")}
                {choice("WORSE", feeling, setFeeling, "Worse than on the visit day")}
              </div>
            </div>

            <div>
              <label className="field-label">
                2. Do you think the medicine your clinician prescribed has helped?
              </label>
              <p style={hintStyle}>
                Your honest impression is what matters here. &ldquo;Not sure&rdquo; is a real
                answer &mdash; it is often too early to tell, and saying so is more useful to
                your clinician than a guess.
              </p>
              <div style={{ display: "flex", gap: "8px", marginTop: "6px", flexWrap: "wrap" }}>
                {choice("YES", helped, setHelped, "Yes, I think it helped")}
                {choice("NO", helped, setHelped, "No, I do not think so")}
                {choice("UNSURE", helped, setHelped, "Too early to tell")}
              </div>
            </div>

            <div>
              <label className="field-label">
                3. Have you been able to take every dose as your clinician explained?
              </label>
              <p style={hintStyle}>
                Please answer honestly &mdash; nobody is checking up on you. Missed or stopped
                antibiotic doses change what your clinician should do next, and stopping early
                is one of the main reasons infections come back harder to treat.
              </p>
              <div style={{ display: "flex", gap: "8px", marginTop: "6px", flexWrap: "wrap" }}>
                {choice("ALL", doses, setDoses, "Yes, every dose")}
                {choice("MOST", doses, setDoses, "Most of them")}
                {choice("SOME", doses, setDoses, "Only some")}
                {choice("STOPPED", doses, setDoses, "I have stopped taking it")}
              </div>
            </div>

            <div>
              <label className="field-label">
                4. Have you noticed anything new since starting the medicine? (optional)
              </label>
              <p style={hintStyle}>
                For example a rash, loose motions, nausea, stomach pain, dizziness, or anything
                that began after you started. Write it in your own words, in any language you
                are comfortable with. Leave it blank if there is nothing.
              </p>
              <textarea
                rows={3}
                value={discomfort}
                onChange={(e) => setDiscomfort(e.target.value)}
                placeholder="e.g. Rash on both arms since Tuesday, or loose motions twice a day"
                className="dashboard-select"
              />
            </div>

            {error && <p className="form-error">{error}</p>}

            <button type="submit" className="dashboard-button primary" disabled={loading}
                    style={{ justifyContent: "center", padding: "12px" }}>
              {loading ? "Sending..." : "Send to my clinician"}
            </button>
          </form>
        </section>
      )}

      {/*
        ALREADY ANSWERED. Shown INSTEAD of the form, not as an error after it: a
        patient should not fill in four questions to be told the answer will not be
        taken. The escalation line is not boilerplate -- a cooldown that leaves
        someone deteriorating with no route is a worse design than no cooldown.
      */}
      {context && !context.can_submit && !submitted && (
        <section className="info-section" style={{ background: "#ffffff", padding: "24px" }}>
          <CheckCircle2 size={28} color="#2d7064" />
          <h2 style={{ color: "#173c3d", margin: "10px 0 6px", fontSize: "1.05rem" }}>
            Your clinician already has your update
          </h2>
          <p className="muted" style={{ fontSize: "0.86rem", margin: "0 0 10px" }}>
            You sent an update for this visit, and it has already reached your clinician.
            You can send another one after{" "}
            <b>
              {context.next_submission_allowed_at
                ? new Date(context.next_submission_allowed_at).toLocaleString()
                : `${context.resubmit_cooldown_hours || 24} hours`}
            </b>
            .
          </p>
          <p style={{ fontSize: "0.84rem", margin: 0, color: "#a33d31" }}>
            If you feel seriously unwell before then &mdash; trouble breathing, a spreading
            rash, a high fever that will not come down, or you cannot keep fluids down &mdash;
            do not wait for this form. Contact your clinician or emergency services.
          </p>
        </section>
      )}

      {submitted && (
        <section className="info-section" style={{ background: "#ffffff", padding: "24px", textAlign: "center" }}>
          <CheckCircle2 size={32} color="#2d7064" />
          <h2 style={{ color: "#173c3d", margin: "10px 0 6px" }}>Thank you</h2>
          <p className="muted" style={{ fontSize: "0.86rem", margin: 0 }}>
            Your answers have gone to your clinician now. You can close this page.
            To let them act on one clear update rather than several, this form accepts
            another answer for this visit after 24 hours &mdash; but if you feel seriously
            unwell before then, contact your clinician or emergency services directly.
          </p>
        </section>
      )}
    </main>
  );
}
