/**
 * Pregnancy / Lactation display rule (brief section 16).
 *
 * For a male patient the Pregnancy / Lactation field must read NOT APPLICABLE.
 * For a female patient the existing value and behaviour are left exactly as
 * app.js rendered them.
 *
 * This is deliberately implemented as an observer rather than an edit to
 * app.js's selectPatient(). Keeping app.js byte-identical to the original is
 * what guarantees the prescription -> analysis -> override flow is unchanged,
 * and a display rule is not worth weakening that guarantee for.
 *
 * IMPORTANT: this is presentational only. The patient record sent to the backend
 * is untouched, so the server-side vulnerable-population rules still evaluate
 * against the real pregnancy_status. Nothing here can suppress a safety warning.
 */

const NOT_APPLICABLE = "NOT APPLICABLE";

function sexOfSelectedPatient(): string | null {
  const ageSex = document.getElementById("patAgeSex");
  if (!ageSex || !ageSex.textContent) return null;
  // app.js renders: "45 yrs (ADULT) • MALE"
  const parts = ageSex.textContent.split("•");
  return parts.length > 1 ? parts[parts.length - 1].trim().toUpperCase() : null;
}

function apply(): void {
  const preg = document.getElementById("patPregnancy");
  if (!preg) return;

  if (sexOfSelectedPatient() !== "MALE") {
    // Female or unknown: leave whatever app.js rendered untouched.
    return;
  }
  // Guard against re-entering the observer with our own write.
  if (preg.textContent && preg.textContent.trim() === NOT_APPLICABLE) return;

  const span = document.createElement("span");
  span.className = "val-mono";
  span.textContent = NOT_APPLICABLE;
  preg.replaceChildren(span);
}

let observer: MutationObserver | null = null;

/** Starts watching the patient summary card. Safe to call more than once. */
export function installPregnancyDisplayRule(): void {
  if (observer) return;

  const card = document.getElementById("patientDetailsCard");
  if (!card) return;

  observer = new MutationObserver(() => apply());
  observer.observe(card, { childList: true, subtree: true, characterData: true });
  apply();
}
