import { useMemo, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Badge, Callout, Input, Pagination, Switch } from "@particle-academy/react-fancy";
import { FancyDataGrid, type FancyGridColumn, type FancyGridState } from "@particle-academy/fancy-grid";
import { findingsApi, type TraitFinding } from "../api";
import { KnownTraits } from "./KnownTraits";

const PAGE_SIZE = 25;
const INITIAL: FancyGridState = { sorting: [], filters: [], rowSelection: {}, pagination: { pageIndex: 0, pageSize: PAGE_SIZE } };

function effect(row: TraitFinding): string {
  if (row.effect === null || row.effect_type === "none") return "not reported";
  if (row.effect_type === "or") return `odds ratio ${row.effect.toFixed(2)}`;
  const direction = row.beta_direction ? ` ${row.beta_direction}` : "";
  return `${row.effect.toPrecision(2)}${direction} per copy`;
}

function copies(row: TraitFinding): string {
  if (row.dosage === null) return "can't tell";
  const of = row.ploidy === 1 ? "1" : "2";
  return `${row.dosage} of ${of}`;
}

export function TraitsPanel({ sampleId }: { sampleId: string }) {
  const [state, setState] = useState<FancyGridState>(INITIAL);
  const [query, setQuery] = useState("");
  const [allStrengths, setAllStrengths] = useState(false);
  const page = state.pagination?.pageIndex ?? 0;

  const params = useMemo(() => {
    const p = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
    if (query.trim()) p.set("q", query.trim());
    if (allStrengths) p.set("min_p_mlog", "5");
    return p;
  }, [page, query, allStrengths]);

  const traits = useQuery({
    queryKey: ["traits", sampleId, params.toString()],
    queryFn: () => findingsApi.traits(sampleId, params),
    placeholderData: keepPreviousData,
  });

  const columns = useMemo<FancyGridColumn<TraitFinding>[]>(() => [
    { id: "mapped_trait", header: "Trait (as studied)",
      cell: (_, row) => (
        <span>
          <span className="block font-medium">{row.mapped_trait || row.reported_trait}</span>
          {row.reported_trait && row.reported_trait !== row.mapped_trait &&
            <span className="block text-xs text-zinc-500">{row.reported_trait}</span>}
        </span>
      ) },
    { id: "probe_id", header: "SNP · risk allele",
      cell: (_, row) => (
        <span>
          {row.probe_id} · {row.risk_allele}
          {row.strand === "flipped" && <span className="block text-xs text-zinc-500">reported on the other strand</span>}
          {row.strand === "assumed" && <span className="block text-xs text-zinc-500">strand assumed, not confirmed</span>}
        </span>
      ) },
    { id: "dosage", header: "Your copies", cell: (_, row) => copies(row) },
    { id: "effect", header: "Effect in the study", cell: (_, row) => effect(row) },
    { id: "risk_af", header: "Risk allele frequency",
      cell: value => value === null ? "unknown" : `${Math.round((value as number) * 100)}% of people` },
    { id: "p_mlog", header: "Strength (p)", align: "end",
      cell: (_, row) => row.p_value || (row.p_mlog ? `1e-${row.p_mlog.toFixed(0)}` : "?") },
    { id: "study", header: "Study",
      cell: (_, row) => (
        <span className="text-xs">
          {row.first_author} {row.published?.slice(0, 4)}
          {row.pmid && <> · <a className="text-brand underline" href={`https://pubmed.ncbi.nlm.nih.gov/${row.pmid}/`}
            target="_blank" rel="noreferrer noopener">PubMed</a></>}
          <span className="block text-zinc-500">{row.initial_sample}</span>
        </span>
      ) },
  ], []);

  const rows = useMemo(() => traits.data?.rows ?? [], [traits.data]);
  const total = traits.data?.total ?? 0;

  return (
    <section className="space-y-3" aria-labelledby="traits-title">
      <h2 id="traits-title" className="sr-only">Traits</h2>
      <KnownTraits sampleId={sampleId} />
      <h3 className="pt-2 font-semibold">Published trait associations</h3>
      <Callout color="zinc">
        These are published associations where you carry at least one copy of the allele the study linked to the trait.
        Most risk alleles are common and each changes the odds only slightly, so a match here is not a prediction.
        Studies were mostly in people of European ancestry and may not apply equally to everyone.
      </Callout>
      <div className="flex flex-wrap items-center gap-4">
        <div className="w-72">
          <Input aria-label="Search traits" placeholder="Search traits (e.g. height, lactose)" value={query}
            onValueChange={value => { setQuery(value); setState(INITIAL); }} size="sm" />
        </div>
        <Switch label="Include weaker associations (p < 1e-5)" checked={allStrengths}
          onCheckedChange={value => { setAllStrengths(value); setState(INITIAL); }} />
        <Badge variant="soft" color="zinc" data-testid="traits-total">{total.toLocaleString()} associations</Badge>
      </div>
      <div className="max-h-[36rem] overflow-auto rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
        <FancyDataGrid gridId={`traits-${sampleId}`} rows={rows} columns={columns} state={state} onStateChange={setState}
          serverSide rowCount={total} getRowId={row => `${row.assoc_id}-${row.probe_id}`}
          emptyMessage={traits.isPending ? "Loading…" : "No associations match."} />
      </div>
      <Pagination page={page + 1} totalPages={Math.max(1, Math.ceil(total / PAGE_SIZE))}
        onPageChange={next => setState(s => ({ ...s, pagination: { pageIndex: next - 1, pageSize: PAGE_SIZE } }))} />
    </section>
  );
}
