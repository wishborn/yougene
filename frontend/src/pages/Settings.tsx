import { useState } from "react";
import { router } from "@inertiajs/react";
import { useQueryClient } from "@tanstack/react-query";
import { Button, Callout, Input, Modal } from "@particle-academy/react-fancy";
import { ReferencePanel } from "../components/ReferencePanel";
import { useConsent, useSetConsent } from "../consent";
import { AppLayout, PageHeader } from "../layout/AppLayout";

const CONSENTS: [string, string][] = [
  ["health", "Health results"],
  ["topic.apoe", "APOE (Alzheimer's disease risk)"],
  ["topic.hereditary_cancer", "Hereditary cancer genes"],
  ["topic.parkinsons", "Parkinson's disease genes"],
  ["topic.huntington", "Huntington's disease (HTT)"],
];

export default function Settings() {
  const consent = useConsent();
  const setConsent = useSetConsent();
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState(false);
  const [phrase, setPhrase] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function deleteAll() {
    const response = await fetch("/api/data", {
      method: "DELETE",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ confirm: phrase }),
    });
    if (!response.ok) {
      setError((await response.json().catch(() => ({}))).detail ?? "Couldn't delete the data.");
      return;
    }
    setConfirming(false);
    queryClient.clear();
    router.visit("/");
  }

  return (
    <AppLayout title="Settings">
      <PageHeader eyebrow="YouGene" title="Settings" />
      <ReferencePanel />
      <section className="space-y-3 rounded-lg border border-zinc-200 bg-white p-5 text-sm dark:border-zinc-800 dark:bg-zinc-900"
        aria-labelledby="consent-title">
        <h2 id="consent-title" className="font-semibold">What you've chosen to see</h2>
        <ul className="space-y-1">
          {CONSENTS.map(([name, label]) => (
            <li key={name} className="flex items-center gap-3">
              <span className="w-72">{label}</span>
              <span className="text-zinc-500">{consent[name] ? "shown" : "hidden"}</span>
              {consent[name] && <Button size="sm" variant="ghost" onClick={() => void setConsent(name, false)}>Hide</Button>}
            </li>
          ))}
        </ul>
        <p className="text-zinc-500">To show a topic, open a sample's Health page; each topic explains itself before you choose.</p>
      </section>
      <section className="space-y-3 rounded-lg border border-red-200 bg-white p-5 text-sm dark:border-red-900 dark:bg-zinc-900"
        aria-labelledby="delete-title">
        <h2 id="delete-title" className="font-semibold">Delete all data</h2>
        <p>Removes every imported sample and your choices from this computer. Downloaded public reference data is kept.</p>
        <Button color="red" onClick={() => { setPhrase(""); setError(null); setConfirming(true); }}>Delete all data…</Button>
      </section>
      <Modal open={confirming} onClose={() => setConfirming(false)} size="sm">
        <Modal.Header>Delete all data?</Modal.Header>
        <Modal.Body>
          <div className="space-y-3 text-sm">
            <p>This can't be undone. Type <strong>DELETE ALL</strong> to confirm.</p>
            <Input aria-label="Confirmation" value={phrase} onValueChange={setPhrase} />
            {error && <Callout color="red">{error}</Callout>}
          </div>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="ghost" onClick={() => setConfirming(false)}>Cancel</Button>
          <Button color="red" disabled={phrase !== "DELETE ALL"} onClick={() => void deleteAll()}>Delete everything</Button>
        </Modal.Footer>
      </Modal>
    </AppLayout>
  );
}
