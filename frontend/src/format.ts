export const CHROMS = [...Array.from({ length: 22 }, (_, i) => String(i + 1)), "X", "Y", "MT"];

export function percent(value: number | null | undefined, digits = 1): string {
  return value === null || value === undefined ? "unknown" : `${(value * 100).toFixed(digits)}%`;
}

export function sexLabel(inferred: string): string {
  return inferred === "XX" ? "XX" : inferred === "XY" ? "XY" : "Sex unknown";
}
