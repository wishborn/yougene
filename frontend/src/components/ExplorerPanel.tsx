import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Badge, Button, Callout, Skeleton } from "@particle-academy/react-fancy";
import { EChart, type EChartsOption } from "@particle-academy/fancy-echarts";
import { genomeApi, type Marker } from "../api";
import { useConsent } from "../consent";
import { Ideogram } from "./Ideogram";

const KARYOTYPE = [...Array.from({ length: 22 }, (_, i) => String(i + 1)), "X", "Y"];

function byChrom(markers: Marker[] | undefined, chrom: string) {
  return (markers ?? []).filter(m => m.chrom === chrom);
}

export function ExplorerPanel({ sampleId, dark }: { sampleId: string; dark: boolean }) {
  const consent = useConsent();
  const showHealth = Boolean(consent.health);
  const [chrom, setChrom] = useState<string | null>(null);
  const bands = useQuery({ queryKey: ["cytobands"], queryFn: genomeApi.cytobands, staleTime: Infinity });
  const roh = useQuery({ queryKey: ["roh", sampleId], queryFn: () => genomeApi.roh(sampleId) });
  const markers = useQuery({
    queryKey: ["markers", sampleId, showHealth],
    queryFn: () => genomeApi.markers(sampleId, showHealth),
  });

  if (bands.isError) {
    return <Callout color="zinc">Download the reference data to see chromosome bands.</Callout>;
  }
  if (!bands.data) return <Skeleton height={320} />;
  const longest = bands.data.lengths["1"] || 1;

  return (
    <section className="space-y-4" aria-labelledby="explorer-title">
      <h2 id="explorer-title" className="sr-only">Chromosome explorer</h2>
      <div className="flex flex-wrap items-center gap-3 text-sm text-zinc-600 dark:text-zinc-300">
        <span className="inline-flex items-center gap-1"><span className="inline-block h-1.5 w-4 rounded bg-amber-600 dark:bg-amber-400" /> runs of homozygosity</span>
        <span className="inline-flex items-center gap-1"><span className="inline-block h-3 w-0.5 bg-brand" /> trait associations you carry</span>
        {showHealth && <span className="inline-flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-full bg-pink-700 dark:bg-pink-400" /> health findings (well reviewed)</span>}
        {roh.data && (
          <Badge variant="soft" color="zinc" data-testid="roh-total">
            {roh.data.segments.length} runs of homozygosity · {roh.data.total_mb} Mb
          </Badge>
        )}
      </div>

      {chrom === null ? (
        <div className="grid grid-cols-1 gap-x-8 gap-y-3 md:grid-cols-2" data-testid="karyotype">
          {KARYOTYPE.map(c => {
            const width = Math.max(40, Math.round((bands.data.lengths[c] / longest) * 460));
            return (
              <button key={c} type="button" onClick={() => setChrom(c)}
                className="flex items-center gap-3 rounded-md px-2 py-1 text-left hover:bg-zinc-100 dark:hover:bg-zinc-800"
                aria-label={`Chromosome ${c}`}>
                <span className="w-6 text-right text-xs font-medium text-zinc-500">{c}</span>
                <Ideogram bands={bands.data.bands[c]} length={bands.data.lengths[c]} width={width} dark={dark}
                  roh={(roh.data?.segments ?? []).filter(s => s.chrom === c)}
                  traitMarkers={byChrom(markers.data?.traits, c)} healthMarkers={byChrom(markers.data?.health, c)}
                  title={`chr${c}`} />
              </button>
            );
          })}
        </div>
      ) : (
        <ChromosomeDetail sampleId={sampleId} chrom={chrom} dark={dark} onBack={() => setChrom(null)}
          bands={bands.data.bands[chrom]} length={bands.data.lengths[chrom]}
          roh={(roh.data?.segments ?? []).filter(s => s.chrom === chrom)}
          traits={byChrom(markers.data?.traits, chrom)} health={byChrom(markers.data?.health, chrom)} />
      )}
      <p className="text-xs text-zinc-500">
        Runs of homozygosity are long stretches where both copies match. Short runs are common in everyone; long or
        many runs can reflect shared ancestry between parents. They aren't a diagnosis.
      </p>
    </section>
  );
}

type DetailProps = {
  sampleId: string; chrom: string; dark: boolean; onBack: () => void;
  bands: import("../api").Band[]; length: number;
  roh: { start: number; end: number; snps: number }[]; traits: Marker[]; health: Marker[];
};

function ChromosomeDetail({ sampleId, chrom, dark, onBack, bands, length, roh, traits, health }: DetailProps) {
  const bins = useQuery({ queryKey: ["bins", sampleId, 500], queryFn: () => genomeApi.bins(sampleId, 500) });
  const rows = bins.data?.chroms[chrom] ?? [];
  const option = useMemo<EChartsOption>(() => ({
    backgroundColor: "transparent",
    animation: false,
    tooltip: { trigger: "axis" },
    legend: { data: ["Probes", "Heterozygosity"], top: 0 },
    grid: { left: 55, right: 55, top: 30, bottom: 60 },
    xAxis: { type: "value", min: 0, max: Math.ceil(length / 1e6), name: "Mb",
      axisLabel: { formatter: (value: number) => String(Math.round(value)) } },
    yAxis: [{ type: "value", name: "Probes" }, { type: "value", name: "Het", min: 0, max: 1, position: "right" }],
    dataZoom: [{ type: "inside" }, { type: "slider", height: 18, bottom: 10 }],
    series: [
      { name: "Probes", type: "bar", barWidth: "90%", data: rows.map(b => [b.start / 1e6 + 0.25, b.probes]),
        itemStyle: { color: dark ? "#8fa2ef" : "#5266bd" },
        markArea: { silent: true, itemStyle: { color: dark ? "rgba(251,191,36,0.15)" : "rgba(217,119,6,0.12)" },
          data: roh.map(s => [{ xAxis: s.start / 1e6 }, { xAxis: s.end / 1e6 }]) } },
      { name: "Heterozygosity", type: "line", yAxisIndex: 1, showSymbol: false, connectNulls: false,
        data: rows.map(b => [b.start / 1e6 + 0.25, b.het_rate]), lineStyle: { width: 1.5 },
        itemStyle: { color: dark ? "#fbbf24" : "#b45309" } },
    ],
  }), [rows, roh, length, dark]);

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <Button size="sm" variant="ghost" onClick={onBack}>All chromosomes</Button>
        <h3 className="font-semibold">Chromosome {chrom}</h3>
        <span className="text-sm text-zinc-500" data-testid="chromosome-summary">
          {(length / 1e6).toFixed(0)} Mb{bins.data ? ` · ${rows.reduce((sum, b) => sum + b.probes, 0).toLocaleString()} probes` : ""}
        </span>
      </div>
      <Ideogram bands={bands} length={length} width={1000} height={20} dark={dark} roh={roh}
        traitMarkers={traits} healthMarkers={health} title={`chr${chrom} detail`} />
      {bins.isPending
        ? <Skeleton height={320} />
        : <EChart option={option} theme={dark ? "dark" : undefined} style={{ height: 320 }} data-testid="chromosome-chart" />}
      {roh.length > 0 && (
        <p className="text-sm text-zinc-600 dark:text-zinc-300">
          Runs of homozygosity: {roh.map(s => `${(s.start / 1e6).toFixed(1)}–${(s.end / 1e6).toFixed(1)} Mb`).join(", ")}
        </p>
      )}
    </div>
  );
}
