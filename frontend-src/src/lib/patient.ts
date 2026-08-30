/**
 * Patient records are stored as "PATIENT-021 (Meera Krishnan)" - the synthetic
 * id the server issues at registration, plus the name the clinician typed. The
 * id is what the audit chain and every API path key on, but it is not what a
 * clinician recognises a patient by, so screens lead with the name and keep the
 * id alongside as the record reference.
 */
export function patientName(
  displayName?: string | null,
  patientId?: string | null,
): string {
  const fallback = patientId?.trim() || "Unknown patient";
  if (!displayName) return fallback;

  // "PATIENT-021 (Meera Krishnan)" -> "Meera Krishnan"; anything without the
  // parenthesised part is already a bare name or a bare id.
  const parenthesised = displayName.match(/^(.*?)\s*\((.+)\)\s*$/);
  const name = (parenthesised ? parenthesised[2] : displayName).trim();

  // Registrations submitted with no name are stored with this placeholder, and
  // a record whose "name" is just its own id tells the clinician nothing.
  if (!name || name === "Patient Record" || name === patientId?.trim()) {
    return fallback;
  }
  return name;
}
