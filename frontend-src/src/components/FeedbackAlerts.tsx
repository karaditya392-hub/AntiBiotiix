import { useEffect, useRef, useState } from "react";
import { useLocation } from "wouter";
import { X, MessageSquareHeart } from "lucide-react";
import { useAuth } from "@/context/AuthContext";

/**
 * Patient follow-up answers, announced to the clinician after they log in.
 *
 * Mounted in UnifiedHeader, so it is present on every signed-in page rather than
 * only on the dashboard: an answer that arrives while the clinician is mid-review
 * should still reach them.
 *
 * Three things this deliberately does:
 *
 *   It shows what THIS clinician has not opened. Acknowledgement is recorded per
 *   clinician on the server, not in this component and not as a shared flag on the
 *   answer: five people use this system, and one of them dismissing an alert says
 *   nothing about whether the others have read it. Because it is on the server,
 *   dismissing on one machine also does not bring it back at the next login.
 *
 *   It does not shout. A patient reporting they feel worse is coloured and worded
 *   differently from one reporting improvement, but neither is a modal that blocks
 *   the page: the clinician may be in the middle of a prescription review, and
 *   this is follow-up, not an emergency channel. The patient page says as much.
 *
 *   IT GETS OUT OF THE WAY OF A FORM. The stack is fixed to the bottom-right at
 *   z-index 9999, which is over the submit button of every form on the right-hand
 *   side of a page -- and it polls every twenty seconds, so a card can appear
 *   under the cursor between a clinician reading a field and clicking Save. A
 *   follow-up answer is not worth intercepting a click meant for a prescription.
 *   So while a form is being filled the stack is HELD, not dropped: nothing is
 *   marked seen, nothing is lost, and everything held reappears once the form is
 *   submitted or abandoned. See `useFormEngagement` below.
 *
 *   Clicking it navigates to that patient and marks the answer seen. Dismissing
 *   with the cross also marks it seen -- the alert has done its job either way,
 *   and an alert that reappears after being dismissed trains people to ignore it.
 */
type Feedback = {
  response_id: string;
  patient_id: string;
  patient_name: string;
  visit_id: string;
  feeling: string;
  medicines_helped: string;
  discomfort?: string | null;
};

const POLL_MS = 20000;

/**
 * Routes where these alerts stay silent entirely.
 *
 * The Agent Console is a run-and-read screen: the clinician fills a form, waits
 * for a pipeline, and reads what came back. A patient follow-up card arriving
 * over that result competes with the only thing the page exists to show, and the
 * cards sit exactly where the run's own output does. So on this route the ONLY
 * thing that surfaces is the result of the run the clinician just started.
 *
 * Silenced, not discarded — nothing is marked seen here, so every held answer is
 * waiting on the dashboard and on every other page the moment they navigate away.
 */
const QUIET_ROUTES = ["/clinical-tools/agents"];

// How long after the clinician stops touching a form before the held alerts are
// allowed back. Long enough to cover reading a field, checking a value or picking
// a file; short enough that a form abandoned mid-way does not silence follow-up
// answers for the rest of the session.
const RELEASE_AFTER_MS = 12000;

/**
 * Whether the clinician is currently filling in a form.
 *
 * Watched on the document rather than wired through every page: this component
 * is mounted once, globally, and it has no idea which form it is about to cover.
 * A page-by-page opt-out would have to be remembered on every form added later,
 * and the one that got forgotten would be the one where a click went to a
 * follow-up alert instead of a prescription.
 *
 * Engagement starts on focus or typing in any field, and ends on submit, on
 * reset, or after RELEASE_AFTER_MS of no interaction. Submit ends it immediately
 * because that is exactly the moment the clinician is done and the answers become
 * worth showing again.
 */
function useFormEngagement(): boolean {
  const [engaged, setEngaged] = useState(false);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => {
    function isField(target: EventTarget | null): boolean {
      const el = target as HTMLElement | null;
      if (!el || !el.tagName) return false;
      return (
        ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName) ||
        el.isContentEditable === true
      );
    }

    function hold() {
      setEngaged(true);
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => setEngaged(false), RELEASE_AFTER_MS);
    }

    function release() {
      window.clearTimeout(timer.current);
      setEngaged(false);
    }

    function onFocusIn(e: FocusEvent) {
      if (isField(e.target)) hold();
    }
    function onInput(e: Event) {
      if (isField(e.target)) hold();
    }

    document.addEventListener("focusin", onFocusIn, true);
    document.addEventListener("input", onInput, true);
    // Capture phase: the form's own handler may preventDefault and re-render, and
    // a bubbling listener on a re-rendered tree can miss the event entirely.
    document.addEventListener("submit", release, true);
    document.addEventListener("reset", release, true);

    return () => {
      document.removeEventListener("focusin", onFocusIn, true);
      document.removeEventListener("input", onInput, true);
      document.removeEventListener("submit", release, true);
      document.removeEventListener("reset", release, true);
      window.clearTimeout(timer.current);
    };
  }, []);

  return engaged;
}

export default function FeedbackAlerts() {
  // This app authenticates with a Bearer token held in AuthContext, not with
  // cookies. These calls originally sent credentials:"include" and no header,
  // so every one of them answered 401 and the alert silently never appeared.
  const { isAuthenticated, token } = useAuth();
  const [location, setLocation] = useLocation();
  const [items, setItems] = useState<Feedback[]>([]);
  const dismissed = useRef<Set<string>>(new Set());
  const fillingAForm = useFormEngagement();
  const onAQuietRoute = QUIET_ROUTES.some((r) => location.startsWith(r));

  useEffect(() => {
    if (!isAuthenticated) {
      setItems([]);
      return;
    }
    let stopped = false;

    async function poll() {
      try {
        const res = await fetch("/api/feedback/unseen", {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) {
          // Say something. This used to return silently, which is how two separate
          // faults -- the wrong auth scheme, and being mounted in a header that half
          // the pages do not render -- both presented identically as "no popup" with
          // nothing in the console to work from. A 401 here means the session has
          // expired: AuthContext signs the clinician out on the next verify, and an
          // alert that renders nothing is then correct rather than broken.
          console.warn(
            `[FeedbackAlerts] /api/feedback/unseen returned ${res.status}. `
            + (res.status === 401
              ? "The session is not valid — sign in again."
              : "Follow-up alerts are unavailable.")
          );
          return;
        }
        const body = await res.json();
        if (stopped) return;
        // Anything dismissed in this session stays gone even if the mark-seen
        // request has not landed yet, so it cannot flicker back on the next poll.
        setItems((body.responses || []).filter((r: Feedback) => !dismissed.current.has(r.response_id)));
      } catch {
        // A follow-up alert that cannot load must never break the page it sits on.
      }
    }

    void poll();
    const timer = setInterval(poll, POLL_MS);
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, [isAuthenticated, token]);

  async function markSeen(id: string) {
    dismissed.current.add(id);
    setItems((current) => current.filter((r) => r.response_id !== id));
    try {
      await fetch(`/api/feedback/${encodeURIComponent(id)}/seen`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
    } catch {
      // The row stays unseen and will be offered again next login, which is the
      // safer failure: an unacknowledged answer should not disappear silently.
    }
  }

  function open(item: Feedback) {
    void markSeen(item.response_id);
    // The patient's own record, with their answers on it.
    setLocation(`/patients/${encodeURIComponent(item.patient_id)}?feedback=${encodeURIComponent(item.response_id)}`);
  }

  // HELD, NOT DROPPED. Rendering nothing while a form is being filled — or while
  // the clinician is on a route that has asked for quiet — leaves the answers
  // unseen on the server, so they come back the moment they are done. Marking
  // them seen here instead would lose a patient's answer to nothing more than the
  // clinician having typed in a box.
  if (!isAuthenticated || items.length === 0 || fillingAForm || onAQuietRoute) return null;

  return (
    <div
      style={{
        position: "fixed", right: "18px", bottom: "18px", zIndex: 9999,
        display: "grid", gap: "8px", width: "min(360px, calc(100vw - 36px))",
      }}
      role="status"
      aria-live="polite"
    >
      {items.slice(0, 4).map((item) => {
        const worse = item.feeling === "WORSE";
        return (
          <div
            key={item.response_id}
            style={{
              background: "#ffffff",
              border: `1px solid ${worse ? "#e3b9b0" : "#cbd9d4"}`,
              borderLeft: `4px solid ${worse ? "#a33d31" : "#2d7064"}`,
              borderRadius: "8px",
              boxShadow: "0 6px 20px rgba(23, 60, 61, 0.16)",
              padding: "11px 12px",
              fontSize: "0.8rem",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "8px" }}>
              <button
                onClick={() => open(item)}
                style={{
                  background: "none", border: "none", padding: 0, textAlign: "left",
                  cursor: "pointer", font: "inherit", color: "inherit", flex: 1,
                }}
                title={`Open ${item.patient_name}'s record`}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                  <MessageSquareHeart size={14} color={worse ? "#a33d31" : "#2d7064"} />
                  <strong style={{ color: "#173c3d" }}>{item.patient_name}</strong>
                </div>
                <div style={{ marginTop: "3px", color: worse ? "#a33d31" : "#203236" }}>
                  {worse ? "Reports feeling worse" :
                   item.feeling === "SAME" ? "Reports no change" : "Reports feeling better"}
                  {item.medicines_helped === "NO" ? " · medicines did not help" : ""}
                </div>
                {item.discomfort && (
                  <div style={{ marginTop: "3px", color: "#526968", fontSize: "0.74rem" }}>
                    “{item.discomfort.length > 90 ? item.discomfort.slice(0, 90) + "..." : item.discomfort}”
                  </div>
                )}
                <div className="muted" style={{ marginTop: "4px", fontSize: "0.7rem" }}>
                  Click to open this patient's record
                </div>
              </button>
              <X
                size={14}
                style={{ cursor: "pointer", color: "#718281", flexShrink: 0 }}
                onClick={() => void markSeen(item.response_id)}
                aria-label="Dismiss"
              />
            </div>
          </div>
        );
      })}
      {items.length > 4 && (
        <div className="muted" style={{ fontSize: "0.72rem", textAlign: "right" }}>
          and {items.length - 4} more awaiting review
        </div>
      )}
    </div>
  );
}
