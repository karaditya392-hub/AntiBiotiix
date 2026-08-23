export type ClassValue = string | number | null | undefined | false;

/** Minimal class-name joiner. */
export function cn(...inputs: ClassValue[]): string {
  return inputs.filter(Boolean).join(" ");
}
