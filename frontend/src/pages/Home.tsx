import { useCallback } from "react";
import { Link, router } from "@inertiajs/react";
import { useQuery } from "@tanstack/react-query";
import { Callout } from "@particle-academy/react-fancy";
import { api, refdataApi } from "../api";
import { ImportPanel } from "../components/ImportPanel";
import { SampleList } from "../components/SampleList";
import { AppLayout, PageHeader } from "../layout/AppLayout";

export default function Home() {
  const samples = useQuery({ queryKey: ["samples"], queryFn: api.samples });
  const reference = useQuery({ queryKey: ["refdata"], queryFn: refdataApi.status });
  const onImported = useCallback((id: string) => {
    router.visit(`/samples/${id}`);
  }, []);
  return (
    <AppLayout title="Samples">
      <PageHeader eyebrow="YouGene" title="Samples">
        Import raw DNA files and explore them. Everything stays on this computer.
      </PageHeader>
      {reference.data && !reference.data.ready && (
        <Callout color="zinc">
          Traits, medicines and health results need the public reference data.{" "}
          <Link href="/settings" className="underline">Download it in Settings</Link>.
        </Callout>
      )}
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <ImportPanel onImported={onImported} />
        <section aria-labelledby="samples-title" className="space-y-3">
          <h2 id="samples-title" className="font-semibold">Samples on this computer</h2>
          {samples.isPending ? <p className="text-sm text-zinc-500">Loading…</p>
            : <SampleList samples={samples.data ?? []} selected={null} onSelect={id => id && router.visit(`/samples/${id}`)} />}
        </section>
      </div>
    </AppLayout>
  );
}
