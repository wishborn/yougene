import { useMemo, useSyncExternalStore } from "react";

// Consent is kept on this computer and can be withdrawn at any time.
const KEY = "yougene.consent";
const listeners = new Set<() => void>();
export function readConsent(): Record<string, boolean> {
  try { return JSON.parse(localStorage.getItem(KEY) ?? "{}"); } catch { return {}; }
}
export function setConsent(name: string, value: boolean) {
  localStorage.setItem(KEY, JSON.stringify({ ...readConsent(), [name]: value }));
  listeners.forEach(l => l());
}
export function useConsent(): Record<string, boolean> {
  const raw = useSyncExternalStore(
    l => { listeners.add(l); return () => listeners.delete(l); },
    () => localStorage.getItem(KEY) ?? "{}",
  );
  return useMemo(() => { try { return JSON.parse(raw); } catch { return {}; } }, [raw]);
}

