import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Callout, Progress, Tabs } from "@particle-academy/react-fancy";
import { api, findingsApi, type Sample } from "../api";
import { CallsGrid } from "./CallsGrid";
import { ExplorerPanel } from "./ExplorerPanel";
import { HealthPanel } from "./HealthPanel";
import { MedicinesPanel } from "./MedicinesPanel";
import { QcCard } from "./QcCard";
import { TraitsPanel } from "./TraitsPanel";

function AnnotationStatus({ sampleId }: { sampleId: string }) {
  const queryClient = useQueryClient();
  const state = useQuery({ queryKey: ["annotation", sampleId], queryFn: () => findingsApi.state(sampleId) });
  const [jobId, setJobId] = useState<string | null>(null);
  const run = useMutation({ mutationFn: () => findingsApi.annotate(sampleId), onSuccess: r => setJobId(r.job_id) });
  const job = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => api.job(jobId!),
    enabled: jobId !== null,
    refetchInterval: q => (q.state.data?.state === "done" || q.state.data?.state === "failed" ? false : 500),
  });
  const finished = job.data?.state === "done";
  useEffect(() => {
    if (!finished) return;
    void queryClient.invalidateQueries({ queryKey: ["annotation", sampleId] });
    void queryClient.invalidateQueries({ queryKey: ["traits", sampleId] });
    void queryClient.invalidateQueries({ queryKey: ["clinvar", sampleId] });
  }, [finished, queryClient, sampleId]);

  const s = state.data?.state;
  const running = run.isPending || job.data?.state === "running" || job.data?.state === "queued";
  if (running) return <Progress indeterminate />;
  if (s === "no_reference") {
    return <Callout color="zinc">Download the reference data above to see traits and health results for this sample.</Callout>;
  }
  if (s === "none" || s === "stale") {
    return (
      <Callout color="amber">
        {s === "none" ? "This sample hasn't been matched against the reference data yet." :
          "The reference data has been updated since this sample was matched."}{" "}
        <Button size="sm" color="brand" onClick={() => run.mutate()}>Match now</Button>
      </Callout>
    );
  }
  return null;
}

export function SampleView({ sample, dark }: { sample: Sample; dark: boolean }) {
  const [tab, setTab] = useState("calls");
  return (
    <div className="space-y-4">
      <QcCard sample={sample} dark={dark} />
      <AnnotationStatus sampleId={sample.id} />
      <Tabs activeTab={tab} onTabChange={setTab} variant="underline">
        <Tabs.List>
          <Tabs.Tab value="calls">All calls</Tabs.Tab>
          <Tabs.Tab value="chromosomes">Chromosomes</Tabs.Tab>
          <Tabs.Tab value="traits">Traits</Tabs.Tab>
          <Tabs.Tab value="medicines">Medicines</Tabs.Tab>
          <Tabs.Tab value="health">Health</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panels className="pt-4">
          <Tabs.Panel value="calls"><CallsGrid sampleId={sample.id} /></Tabs.Panel>
          <Tabs.Panel value="chromosomes"><ExplorerPanel sampleId={sample.id} dark={dark} /></Tabs.Panel>
          <Tabs.Panel value="traits"><TraitsPanel sampleId={sample.id} /></Tabs.Panel>
          <Tabs.Panel value="medicines"><MedicinesPanel sampleId={sample.id} /></Tabs.Panel>
          <Tabs.Panel value="health"><HealthPanel sampleId={sample.id} /></Tabs.Panel>
        </Tabs.Panels>
      </Tabs>
    </div>
  );
}
