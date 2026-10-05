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
