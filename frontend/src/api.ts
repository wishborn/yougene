// Typed client for the local YouGene API. Everything stays on this machine.

export type Sex = { inferred: "XX" | "XY" | "unknown"; reason: string } & Record<string, number | string | null>;

export type Qc = {
  rows: number;
  rs_ids: number;
  vendor_ids: number;
  nocalls: number;
  call_rate: number | null;
  snp_calls: number;
  indel_codes: number;
  duplicate_position_groups: number;
  duplicate_position_conflicts: number;
  autosomal_heterozygosity: number | null;
  per_chromosome: Record<string, { probes: number; nocalls: number }>;
  sex: Sex;
  build_evidence: { build: string; header: string | null; anchors_checked: number; anchors_matching_grch37: number };
};

export type Sample = {
  id: string;
  display_name: string;
  relationship: string | null;
  vendor: string;
  format: string;
  build: string;
  qc: Qc;
  created_at: string;
  updated_at: string;
};

export type Job = {
  id: string;
  state: "queued" | "running" | "done" | "failed";
  progress: number;
  message: string;
  sample_id: string | null;
  error_code: string | null;
};

export type Call = {
  probe_id: string;
  id_kind: "rs" | "vendor";
  chrom: string;
  pos: number;
  alleles: string;
  ploidy: number | null;
  call_type: "snp" | "indel_code" | "nocall";
  dup_group: number | null;
  dup_conflict: boolean;
};

export type CallsPage = { total: number; page: number; page_size: number; rows: Call[] };

export class ApiError extends Error {
  constructor(public status: number, message: string, public body?: unknown) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (response.status === 204) return undefined as T;
  const body: unknown = await response.json().catch(() => undefined);
  if (!response.ok) {
    const detail =
      body && typeof body === "object" && "detail" in body && typeof body.detail === "string"
        ? body.detail
        : `The local server returned ${response.status}.`;
    throw new ApiError(response.status, detail, body);
  }
  return body as T;
}

export const api = {
  health: () => request<{ status: string; version: string }>("/api/health"),
  samples: () => request<{ samples: Sample[] }>("/api/samples").then(r => r.samples),
  upload: (file: File, options: { name?: string; relationship?: string; replace?: boolean }) => {
    const params = new URLSearchParams();
    if (options.name) params.set("name", options.name);
    if (options.relationship) params.set("relationship", options.relationship);
    if (options.replace) params.set("on_duplicate", "replace");
    return request<{ job_id: string }>(`/api/samples?${params}`, {
      method: "POST",
      headers: { "content-type": "application/octet-stream" },
      body: file,
    });
  },
  job: (id: string) => request<Job>(`/api/jobs/${id}`),
  rename: (id: string, changes: { display_name?: string; relationship?: string | null }) =>
    request<Sample>(`/api/samples/${id}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(changes),
    }),
  remove: (id: string) => request<void>(`/api/samples/${id}`, { method: "DELETE" }),
  calls: (id: string, params: URLSearchParams) => request<CallsPage>(`/api/samples/${id}/calls?${params}`),
};

export type RefSource = {
  id: string;
  title: string;
  purpose: string;
  license: string;
  attribution: string;
  approx_mb: number;
  url: string;
  installed: null | {
    released: string | null;
    built_at: string;
    bytes?: number;
    stats: Record<string, number>;
  };
};

export const refdataApi = {
  status: () => request<{ sources: RefSource[]; ready: boolean }>("/api/refdata"),
  install: (sources?: string[]) =>
    request<{ job_id: string }>("/api/refdata/install", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(sources ? { sources } : {}),
    }),
};

export type AnnotationState = {
  state: "none" | "no_reference" | "stale" | "current";
  reference: Record<string, { built_at: string; released: string | null }> | null;
  stats?: {
    clinvar: { records_at_tested_positions: number; carried: number; allele_mismatch: number };
    gwas: { associations_at_tested_snps: number; carrying_risk_allele: number; by_strand: Record<string, number> };
  };
};

export type ClinvarFinding = {
  probe_id: string; chrom: string; pos: number; alleles: string; ploidy: number;
  dup_conflict: boolean; vcv_id: number; rsid: string | null; ref: string; alt: string;
  sig_cat: string; sig_raw: string | null; stars: number; revstat: string | null;
  conditions: string[] | null; genes: string[] | null; consequences: string[] | null;
  low_penetrance: boolean | null; max_af: number; match_via: "rsid" | "pos";
  sensitive_topic: string | null; status: string; zygosity: string | null; dosage: number;
  tier: "established" | "moderate" | "limited" | "research"; rare_guard: boolean;
};

export type TraitFinding = {
  assoc_id: number; probe_id: string; chrom: string; pos: number; alleles: string;
  ploidy: number; risk_allele: string; dosage: number | null; strand: string;
  study_acc: string; pmid: number | null; first_author: string; published: string | null;
  study: string; reported_trait: string; mapped_trait: string; initial_sample: string;
  risk_af: number | null; p_mlog: number | null; p_value: string; effect: number | null;
  effect_type: "or" | "beta" | "none"; beta_direction: string | null; ci_text: string;
  mapped_gene: string; context: string;
};

export type Page<T> = { total: number; page: number; page_size: number; rows: T[] };

export const findingsApi = {
  state: (id: string) => request<AnnotationState>(`/api/samples/${id}/annotation`),
  annotate: (id: string) => request<{ job_id: string }>(`/api/samples/${id}/annotate`, { method: "POST" }),
  clinvarSummary: (id: string) =>
    request<{ counts: { sig_cat: string; tier: string; topic: string | null; rare_guard: boolean; count: number }[] }>(
      `/api/samples/${id}/clinvar/summary`),
  clinvar: (id: string, params: URLSearchParams) =>
    request<Page<ClinvarFinding>>(`/api/samples/${id}/clinvar?${params}`),
  traits: (id: string, params: URLSearchParams) =>
    request<Page<TraitFinding>>(`/api/samples/${id}/traits?${params}`),
};

export type Band = { start: number; end: number; band: string; stain: string };
export type Bin = { start: number; probes: number; nocalls: number; het_rate: number | null };
export type Roh = { segments: { chrom: string; start: number; end: number; snps: number }[]; total_mb: number; fraction_of_autosomes: number };
export type Marker = { chrom: string; pos: number; probe_id: string };

export const genomeApi = {
  cytobands: () => request<{ bands: Record<string, Band[]>; lengths: Record<string, number> }>("/api/reference/cytobands"),
  bins: (id: string, binKb = 1000) =>
    request<{ bin_bp: number; chroms: Record<string, Bin[]> }>(`/api/samples/${id}/genome/bins?bin_kb=${binKb}`),
  roh: (id: string) => request<Roh>(`/api/samples/${id}/genome/roh`),
  markers: (id: string, health: boolean) =>
    request<{ traits: Marker[]; health: Marker[] }>(`/api/samples/${id}/genome/markers?health=${health}`),
  coverage: (id: string, genes: string[]) => {
    const p = new URLSearchParams();
    genes.forEach(g => p.append("gene", g));
    return request<{ genes: Record<string, { known_pathogenic_snvs: number; tested: number }> }>(
      `/api/samples/${id}/coverage?${p}`);
  },
};

export type KnownTrait = {
  id: string; title: string; rsid: string; gene: string; effect_allele: string; other_allele: string;
  caveat: string; clinvar_vcv: number;
  status: "ok" | "not_tested" | "no_call" | "conflicting" | "unexpected";
  genotype?: string; copies?: number; summary: string | null;
};

export const knownTraitsApi = {
  list: (id: string) => request<{ traits: KnownTrait[] }>(`/api/samples/${id}/known-traits`).then(r => r.traits),
};

export type PgxGene = {
  gene: string; drugs: string[]; note: string; untested_alleles: string[];
  status: "ok" | "not_determined"; phenotype: string | null; detail: string | null;
  positions: { rsid: string; star: string; function: string; clinvar_vcv: number; genotype: string | null;
    status: "ok" | "not_tested" | "no_call" | "conflicting" | "unexpected" }[];
};

export const pgxApi = {
  list: (id: string) => request<{ genes: PgxGene[] }>(`/api/samples/${id}/pgx`).then(r => r.genes),
};
