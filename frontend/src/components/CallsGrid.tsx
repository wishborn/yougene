import { useMemo, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Badge, Input, Pagination, Select } from "@particle-academy/react-fancy";
import { FancyDataGrid, type FancyGridColumn, type FancyGridState } from "@particle-academy/fancy-grid";
import { api, type Call } from "../api";
import { CHROMS } from "../format";
import { VariantDrawer } from "./VariantDrawer";

const PAGE_SIZE = 50;
const CALL_TYPES = [
  { value: "", label: "All call types" },
  { value: "snp", label: "SNP calls" },
  { value: "nocall", label: "No-calls" },
  { value: "indel_code", label: "Insertion/deletion probes" },
];
const CHROM_OPTIONS = [{ value: "", label: "All chromosomes" }, ...CHROMS.map(c => ({ value: c, label: `Chr ${c}` }))];
// Every slice is supplied, from one stable initial object (see the P0 grid hang notes).
const INITIAL_STATE: FancyGridState = {
  sorting: [],
  filters: [],
  rowSelection: {},
  pagination: { pageIndex: 0, pageSize: PAGE_SIZE },
};

type Filters = { chrom: string; callType: string; probe: string; alleles: string };

export function CallsGrid({ sampleId }: { sampleId: string }) {
  const [state, setState] = useState<FancyGridState>(INITIAL_STATE);
  const [target, setTarget] = useState<{ chrom: string; pos: number } | null>(null);
  const [filters, setFilters] = useState<Filters>({ chrom: "", callType: "", probe: "", alleles: "" });
  const page = state.pagination?.pageIndex ?? 0;

  const params = useMemo(() => {
    const p = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
    const sort = (state.sorting ?? []).map(s => (s.desc ? "-" : "") + s.id).join(",");
    if (sort) p.set("sort", sort);
    if (filters.chrom) p.set("chrom", filters.chrom);
    if (filters.callType) p.set("call_type", filters.callType);
    if (/^[A-Za-z0-9_]+$/.test(filters.probe)) p.set("probe", filters.probe);
    if (/^([ACGTDIacgtdi]{1,2}|--)$/.test(filters.alleles)) p.set("alleles", filters.alleles);
    return p;
  }, [page, state.sorting, filters]);

  const calls = useQuery({
    queryKey: ["calls", sampleId, params.toString()],
    queryFn: () => api.calls(sampleId, params),
    placeholderData: keepPreviousData,
  });

  const columns = useMemo<FancyGridColumn<Call>[]>(() => [
    { id: "probe_id", header: "Probe", sortable: true,
      cell: (value, row) => (
        <button type="button" className="text-left text-brand underline-offset-2 hover:underline"
          onClick={() => setTarget({ chrom: row.chrom, pos: row.pos })} aria-label={`Details for ${String(value)}`}>
          {String(value)}
        </button>
      ) },
    { id: "chrom", header: "Chr", sortable: true },
    { id: "pos", header: "Position (GRCh37)", sortable: true, align: "end",
      cell: value => (value as number).toLocaleString() },
    { id: "alleles", header: "Call", sortable: true,
      cell: (value, row) => row.call_type === "nocall" ? <span className="text-zinc-400">no call</span> : String(value) },
    { id: "call_type", header: "Type", sortable: true,
      cell: (_, row) => row.call_type === "indel_code" ? <Badge size="sm" variant="soft" color="zinc">indel probe</Badge>
        : row.call_type === "nocall" ? "" : row.ploidy === 1 ? "single copy" : "" },
    { id: "dup_group", header: "Notes",
      cell: (_, row) => row.dup_conflict ? <Badge size="sm" variant="soft" color="amber">probes disagree</Badge>
        : row.dup_group !== null ? <Badge size="sm" variant="soft" color="zinc">shared position</Badge> : null },
  ], []);

  const rows = useMemo(() => calls.data?.rows ?? [], [calls.data]);
  const total = calls.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const onStateChange = (next: FancyGridState) => {
    const sortChanged = JSON.stringify(next.sorting ?? []) !== JSON.stringify(state.sorting ?? []);
    setState(sortChanged ? { ...next, pagination: { pageIndex: 0, pageSize: PAGE_SIZE } } : next);
  };

  const update = (patch: Partial<Filters>) => {
    setFilters(f => ({ ...f, ...patch }));
    setState(s => ({ ...s, pagination: { pageIndex: 0, pageSize: PAGE_SIZE } }));
  };

  return (
    <section aria-labelledby="calls-title" className="space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h2 id="calls-title" className="font-semibold">
          Calls <span className="font-normal text-zinc-500" data-testid="calls-total">· {total.toLocaleString()} matching</span>
        </h2>
        <div className="grid w-full grid-cols-2 gap-2 sm:w-auto sm:grid-cols-[10rem_12rem_11rem_7rem]">
          <Select aria-label="Chromosome" list={CHROM_OPTIONS} value={filters.chrom}
            onValueChange={value => update({ chrom: value })} size="sm" />
          <Select aria-label="Call type" list={CALL_TYPES} value={filters.callType}
            onValueChange={value => update({ callType: value })} size="sm" />
          <Input aria-label="Probe id starts with" placeholder="Probe id (rs123)" value={filters.probe}
            onValueChange={value => update({ probe: value.trim() })} size="sm" />
          <Input aria-label="Genotype" placeholder="Call (AG)" value={filters.alleles}
            onValueChange={value => update({ alleles: value.trim() })} size="sm" maxLength={2} />
        </div>
      </div>
      <div className="max-h-[32rem] overflow-auto rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
        <FancyDataGrid gridId={`calls-${sampleId}`} rows={rows} columns={columns} state={state}
          onStateChange={onStateChange} serverSide rowCount={total} getRowId={row => row.probe_id}
          emptyMessage={calls.isPending ? "Loading…" : "No calls match these filters."} />
      </div>
      <VariantDrawer sampleId={sampleId} target={target} onClose={() => setTarget(null)} />
      <Pagination page={page + 1} totalPages={totalPages}
        onPageChange={next => setState(s => ({ ...s, pagination: { pageIndex: next - 1, pageSize: PAGE_SIZE } }))} />
    </section>
  );
}
