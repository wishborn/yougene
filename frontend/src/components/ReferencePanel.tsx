import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge, Button, Callout, Progress } from "@particle-academy/react-fancy";
import { api, refdataApi, snpediaApi } from "../api";

function date(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleDateString(undefined, { dateStyle: "medium" }) : "unknown";
}

export function ReferencePanel() {
  const queryClient = useQueryClient();
  const status = useQuery({ queryKey: ["refdata"], queryFn: refdataApi.status });
  const [jobId, setJobId] = useState<string | null>(null);
  const install = useMutation({ mutationFn: () => refdataApi.install(), onSuccess: r => setJobId(r.job_id) });
  const job = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => api.job(jobId!),
    enabled: jobId !== null,
    refetchInterval: q => (q.state.data?.state === "done" || q.state.data?.state === "failed" ? false : 500),
  });
  const done = job.data?.state === "done";
  useEffect(() => {
    if (done) void queryClient.invalidateQueries({ queryKey: ["refdata"] });
  }, [done, queryClient]);

  const snpedia = useQuery({ queryKey: ["snpedia"], queryFn: snpediaApi.status });
  const [snpediaJob, setSnpediaJob] = useState<string | null>(null);
  const startSnpedia = useMutation({ mutationFn: snpediaApi.install, onSuccess: r => setSnpediaJob(r.job_id) });
  const snpediaProgress = useQuery({
    queryKey: ["job", snpediaJob],
    queryFn: () => api.job(snpediaJob!),
    enabled: snpediaJob !== null,
    refetchInterval: q => (q.state.data?.state === "done" || q.state.data?.state === "failed" ? false : 2000),
  });
  const snpediaDone = snpediaProgress.data?.state === "done";
  useEffect(() => {
    if (snpediaDone) void queryClient.invalidateQueries({ queryKey: ["snpedia"] });
  }, [snpediaDone, queryClient]);
  const snpediaRunning = startSnpedia.isPending || ["queued", "running"].includes(snpediaProgress.data?.state ?? "");

  const sources = (status.data?.sources ?? []).filter(s => s.id !== "liftover" || s.installed);
  const totalMb = sources.reduce((sum, s) => sum + s.approx_mb, 0);
  const running = install.isPending || job.data?.state === "queued" || job.data?.state === "running";
  const ready = status.data?.ready ?? false;

  return (
    <section aria-labelledby="ref-title" className="space-y-4 rounded-lg border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="ref-title" className="font-semibold">Reference data</h2>
          <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
            Public databases YouGene compares your file against. Downloaded once to this computer;
            your genetic data is never sent anywhere.
          </p>
        </div>
        <Button color="brand" disabled={running} onClick={() => install.mutate()} data-testid="refdata-install">
          {ready ? "Update reference data" : `Download reference data (about ${totalMb} MB)`}
        </Button>
      </div>
      {running && (
        <div className="space-y-1">
          <Progress value={Math.round((job.data?.progress ?? 0) * 100)} max={100} indeterminate={!job.data} />
          <p className="text-sm text-zinc-500" data-testid="refdata-status">{job.data?.message ?? "Starting"}…</p>
        </div>
      )}
      {job.data?.state === "failed" && <Callout color="red">{job.data.message}</Callout>}
      {install.error && <Callout color="red">{install.error.message}</Callout>}
      <ul className="divide-y divide-zinc-200 dark:divide-zinc-800">
        {sources.map(source => (
          <li key={source.id} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 py-2 text-sm">
            <span className="font-medium">{source.title}</span>
            {source.installed
              ? <Badge size="sm" variant="soft" color="green">Release {date(source.installed.released)}</Badge>
              : <Badge size="sm" variant="soft" color="zinc">Not installed</Badge>}
            <span className="w-full text-zinc-500 dark:text-zinc-400">
              {source.purpose} <span className="italic">{source.license}</span>
            </span>
          </li>
        ))}
      </ul>
      <div className="space-y-2 border-t border-zinc-200 pt-3 text-sm dark:border-zinc-800">
        <div className="flex flex-wrap items-center gap-3">
          <span className="font-medium">SNPedia notes (optional)</span>
          {snpedia.data?.installed
            ? <Badge size="sm" variant="soft" color="green">{snpedia.data.snps?.toLocaleString()} SNPs</Badge>
            : <Badge size="sm" variant="soft" color="zinc">Not installed</Badge>}
          <Button size="sm" disabled={snpediaRunning} onClick={() => startSnpedia.mutate()} data-testid="snpedia-install">
            {snpedia.data?.installed ? "Update SNPedia notes" : "Get SNPedia notes"}
          </Button>
        </div>
        <p className="text-zinc-500 dark:text-zinc-400">
          Plain-language, community-written notes for the SNPs on your files. YouGene asks SNPedia for every SNP on the
          chip and every genotype page, never just yours, so your genotypes aren't revealed. Downloads slowly to be polite
          (often 30–60 minutes) and runs in the background. {snpedia.data?.license}
        </p>
        {snpediaRunning && <Progress value={Math.round((snpediaProgress.data?.progress ?? 0) * 100)} max={100} />}
        {snpediaRunning && <p className="text-xs text-zinc-500">{snpediaProgress.data?.message}</p>}
        {snpediaProgress.data?.state === "failed" && <Callout color="red">{snpediaProgress.data.message}</Callout>}
        {startSnpedia.error && <Callout color="red">{startSnpedia.error.message}</Callout>}
      </div>
    </section>
  );
}
