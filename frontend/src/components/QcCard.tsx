import { useMemo } from "react";
import { Stat } from "@particle-academy/react-fancy";
import { EChart, type EChartsOption } from "@particle-academy/fancy-echarts";
import type { Sample } from "../api";
import { CHROMS, percent, sexLabel } from "../format";

type Props = { sample: Sample; dark: boolean };

export function QcCard({ sample, dark }: Props) {
  const qc = sample.qc;
  const option = useMemo<EChartsOption>(() => ({
    backgroundColor: "transparent",
    animation: false,
    tooltip: { trigger: "axis" },
    legend: { data: ["Called", "No-call"], top: 0 },
    grid: { left: 55, right: 15, top: 30, bottom: 30 },
    xAxis: { type: "category", data: CHROMS },
    yAxis: { type: "value" },
    series: [
      { name: "Called", type: "bar", stack: "probes", barMaxWidth: 22,
        data: CHROMS.map(c => qc.per_chromosome[c].probes - qc.per_chromosome[c].nocalls),
        itemStyle: { color: dark ? "#8fa2ef" : "#5266bd" } },
      { name: "No-call", type: "bar", stack: "probes", barMaxWidth: 22,
        data: CHROMS.map(c => qc.per_chromosome[c].nocalls),
        itemStyle: { color: dark ? "#52525b" : "#d4d4d8" } },
    ],
  }), [qc, dark]);

  const sex = qc.sex;
  return (
    <section aria-labelledby="qc-title" className="space-y-4 rounded-lg border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
      <div>
        <h2 id="qc-title" className="font-semibold">{sample.display_name}: file quality</h2>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          {sample.vendor} · {sample.build} (confirmed by {qc.build_evidence.anchors_matching_grch37} of{" "}
          {qc.build_evidence.anchors_checked} reference SNPs{qc.build_evidence.header ? " and the file header" : ""})
        </p>
      </div>
      <Stat.Band columns={4}>
        <Stat value={qc.rows.toLocaleString()} label="Probes" />
        <Stat value={percent(qc.call_rate)} label="Call rate" />
        <Stat value={percent(qc.autosomal_heterozygosity)} label="Autosomal heterozygosity" />
        <Stat value={sexLabel(sex.inferred)} label="Inferred chromosomes" data-testid="qc-sex" />
      </Stat.Band>
      <EChart option={option} theme={dark ? "dark" : undefined} renderer="svg" style={{ height: 260 }} data-testid="qc-chart" />
      <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
        <dt className="text-zinc-500">Inferred from</dt>
        <dd>
          {sex.reason}: X heterozygosity outside the shared X/Y regions {percent(sex.x_non_par_heterozygosity as number | null)},
          Y call rate {percent(sex.y_call_rate as number | null)}
        </dd>
        <dt className="text-zinc-500">Insertion/deletion probes</dt>
        <dd>{qc.indel_codes.toLocaleString()} (shown, but not interpretable from array letters)</dd>
        <dt className="text-zinc-500">Positions tested by more than one probe</dt>
        <dd>{qc.duplicate_position_groups.toLocaleString()} ({qc.duplicate_position_conflicts.toLocaleString()} disagree)</dd>
        <dt className="text-zinc-500">23andMe internal ids</dt>
        <dd>{qc.vendor_ids.toLocaleString()}</dd>
      </dl>
    </section>
  );
}
