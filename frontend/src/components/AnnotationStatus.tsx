import { useEffect, useState } from "react";
import { Link } from "@inertiajs/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Callout, Progress } from "@particle-academy/react-fancy";
import { api, findingsApi } from "../api";

export function AnnotationStatus({ sampleId }: { sampleId: string }) {
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
    return (
      <Callout color="zinc">
        Download the reference data in <Link href="/settings" className="underline">Settings</Link> to see traits and
        health results for this sample.
      </Callout>
    );
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
