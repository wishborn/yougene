import { useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

// Opt-ins for sensitive results are stored by the local server for this
// install (every sample) and enforced there too. Withdrawing "health"
// withdraws every topic. "Delete all data" clears them.
type Consent = Record<string, boolean>;

async function fetchConsent(): Promise<Consent> {
  const response = await fetch("/api/consent");
  if (!response.ok) throw new Error(`The local server returned ${response.status}.`);
  return response.json();
}

export function useConsent(): Consent {
  const consent = useQuery({ queryKey: ["consent"], queryFn: fetchConsent });
  return consent.data ?? {};
}

export function useSetConsent(): (name: string, granted: boolean) => Promise<void> {
  const queryClient = useQueryClient();
  return useCallback(async (name: string, granted: boolean) => {
    const response = await fetch("/api/consent", {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ name, granted }),
    });
    if (!response.ok) throw new Error(`The local server returned ${response.status}.`);
    const next: Consent = await response.json();
    if (!granted) {
      // Withdrawn: drop cached health results from memory rather than refetch.
      queryClient.removeQueries({ queryKey: ["clinvar"] });
      queryClient.removeQueries({ queryKey: ["coverage"] });
    }
    queryClient.setQueryData(["consent"], next);
    // Views whose cache key doesn't include consent.
    void queryClient.invalidateQueries({ queryKey: ["variant"] });
  }, [queryClient]);
}
