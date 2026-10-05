import { useMemo, useState, useSyncExternalStore } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Badge, Button, Callout, Checkbox, Modal, Pagination, Switch } from "@particle-academy/react-fancy";
import { findingsApi, type ClinvarFinding } from "../api";

// Consent is kept on this computer and can be withdrawn at any time.
const KEY = "yougene.consent";
const listeners = new Set<() => void>();
function readConsent(): Record<string, boolean> {
  try { return JSON.parse(localStorage.getItem(KEY) ?? "{}"); } catch { return {}; }
}
function setConsent(name: string, value: boolean) {
  localStorage.setItem(KEY, JSON.stringify({ ...readConsent(), [name]: value }));
  listeners.forEach(l => l());
}
function useConsent(): Record<string, boolean> {
  const raw = useSyncExternalStore(
    l => { listeners.add(l); return () => listeners.delete(l); },
    () => localStorage.getItem(KEY) ?? "{}",
  );
  return useMemo(() => { try { return JSON.parse(raw); } catch { return {}; } }, [raw]);
}

const TOPICS: Record<string, { title: string; explain: string }> = {
  apoe: {
    title: "APOE (Alzheimer's disease risk)",
    explain: "APOE variants change the average risk of late-onset Alzheimer's disease. They don't determine whether someone " +
      "will develop it, there is no proven prevention based on the result, and it can be upsetting to learn. Results " +
      "also hint at relatives' genotypes.",
  },
  hereditary_cancer: {
    title: "Hereditary cancer genes (BRCA1/2, Lynch syndrome)",
    explain: "These genes affect cancer risk. Consumer arrays test only a few of the thousands of known variants, so a " +
      "clear result doesn't rule anything out, and rare positive calls are frequently wrong (40–80% in published " +
      "re-testing). Any positive must be confirmed by a clinical test before acting on it.",
  },
  parkinsons: {
    title: "Parkinson's disease genes (LRRK2, GBA, SNCA)",
    explain: "Variants here raise the risk of Parkinson's disease but most carriers never develop it. There is no proven " +
      "way to change the outcome based on this result.",
  },
  huntington: {
    title: "Huntington's disease (HTT)",
    explain: "Huntington's is caused by a repeat expansion that DNA arrays can't measure. Anything shown here is not a " +
      "Huntington's test. Genetic counselling is strongly recommended before any testing for this condition.",
  },
};

const SIG_LABEL: Record<string, string> = {
  pathogenic: "Pathogenic",
  likely_pathogenic: "Likely pathogenic",
  pathogenic_likely: "Pathogenic / likely pathogenic",
  uncertain: "Uncertain significance",
  conflicting: "Conflicting reports",
  benign: "Benign",
  drug_response: "Drug response",
  risk_factor: "Risk factor",
  protective: "Protective",
  association: "Association",
  not_provided: "Not provided",
  other: "Other",
  none: "Not classified",
};
const TIER: Record<string, { label: string; color: "green" | "blue" | "amber" | "zinc" }> = {
  established: { label: "Established (expert-reviewed)", color: "green" },
  moderate: { label: "Moderate (several labs agree)", color: "blue" },
  limited: { label: "Limited (one lab)", color: "amber" },
  research: { label: "Research only (no review)", color: "zinc" },
};

const DISEASE = new Set(["pathogenic", "likely_pathogenic", "pathogenic_likely"]);

function zygosityText(row: ClinvarFinding): string {
  if (row.zygosity === "hemizygous") return "1 copy (you have one copy of this chromosome)";
  if (row.zygosity === "homozygous") return "2 copies";
  // Inheritance isn't in ClinVar's summary, so state the carrier point conditionally.
  return DISEASE.has(row.sig_cat)
    ? "1 copy. If this condition is recessive, one copy usually means being a carrier, not being affected"
    : "1 copy";
}

function Gate({ title, explain, onAccept }: { title: string; explain: string; onAccept: () => void }) {
  const [open, setOpen] = useState(false);
  const [understood, setUnderstood] = useState(false);
  return (
    <>
      <Button onClick={() => setOpen(true)}>{title}</Button>
      <Modal open={open} onClose={() => setOpen(false)} size="md">
        <Modal.Header>{title}</Modal.Header>
        <Modal.Body>
          <div className="space-y-3 text-sm">
            <p>{explain}</p>
            <Checkbox label="I understand and want to see these results" checked={understood} onCheckedChange={setUnderstood} />
          </div>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="ghost" onClick={() => setOpen(false)}>Not now</Button>
          <Button color="brand" disabled={!understood} onClick={() => { setOpen(false); onAccept(); }}>Show results</Button>
        </Modal.Footer>
      </Modal>
    </>
  );
}

function FindingCard({ row }: { row: ClinvarFinding }) {
  const tier = TIER[row.tier];
  const conditions = (row.conditions ?? []).filter(c => !/^not (provided|specified)$/i.test(c));
  return (
    <li className="space-y-2 rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900" data-testid="health-finding">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{conditions.length ? conditions.join(" · ") : "Condition not named"}</span>
        <Badge size="sm" variant="soft" color="zinc">{SIG_LABEL[row.sig_cat] ?? row.sig_cat}</Badge>
        <Badge size="sm" variant="soft" color={tier.color}>{tier.label}</Badge>
      </div>
      <p className="text-sm text-zinc-600 dark:text-zinc-300">
        {(row.genes ?? []).join(", ") || "Gene not named"} · {row.probe_id} ({row.chrom}:{row.pos.toLocaleString()}) ·
        your call {row.alleles}, variant allele {row.alt}: {zygosityText(row)}
      </p>
      {row.rare_guard && (
        <Callout color="amber">
          This variant is rare (or its frequency is unknown). Consumer arrays are often wrong about rare variants, so treat
          this as unconfirmed until a clinical-grade test repeats it.
        </Callout>
      )}
      {row.dup_conflict && <Callout color="amber">Two probes at this position disagree, so this call is unreliable.</Callout>}
      <p className="text-xs text-zinc-500">
        ClinVar <a className="underline" href={`https://www.ncbi.nlm.nih.gov/clinvar/variation/${row.vcv_id}/`}
          target="_blank" rel="noreferrer noopener">VCV{String(row.vcv_id).padStart(9, "0")}</a>
        {" · "}{row.stars} of 4 review stars{row.low_penetrance ? " · low penetrance" : ""}
        {row.match_via === "pos" ? " · matched by position (23andMe internal probe or renamed SNP)" : ""}
      </p>
    </li>
  );
}

export function HealthPanel({ sampleId }: { sampleId: string }) {
  const consent = useConsent();
  const [page, setPage] = useState(0);
  const [showWeak, setShowWeak] = useState(false);
  const [onlyActionable, setOnlyActionable] = useState(true);
  const topics = Object.keys(TOPICS).filter(t => consent[`topic.${t}`]);

  const params = useMemo(() => {
    const p = new URLSearchParams({ page: String(page), page_size: "20", min_stars: showWeak ? "0" : "2" });
    if (onlyActionable) ["pathogenic", "likely_pathogenic", "pathogenic_likely", "risk_factor", "drug_response"]
      .forEach(s => p.append("sig", s));
    topics.forEach(t => p.append("topic", t));
    return p;
  }, [page, showWeak, onlyActionable, topics]);

  const findings = useQuery({
    queryKey: ["clinvar", sampleId, params.toString()],
    queryFn: () => findingsApi.clinvar(sampleId, params),
    enabled: Boolean(consent.health),
    placeholderData: keepPreviousData,
  });

  if (!consent.health) {
    return (
      <section className="space-y-3">
        <Callout color="zinc">
          Health results are hidden until you choose to see them. They come from ClinVar, a public database of variant
          reports. Consumer DNA arrays are not clinical tests: rare results are often wrong, a clear result never rules a
          condition out, and nothing here is a diagnosis.
        </Callout>
        <Gate title="Show health results" onAccept={() => setConsent("health", true)}
          explain="You'll see variants in your file that ClinVar links to medical conditions, with how strong the evidence is and how reliable array calls are for each. Some results can be worrying; several topics (APOE, hereditary cancer, Parkinson's, Huntington's) stay hidden behind their own extra step. You can hide health results again at any time." />
      </section>
    );
  }

  const total = findings.data?.total ?? 0;
  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center gap-4">
        <Switch label="Only significant findings" checked={onlyActionable} onCheckedChange={v => { setOnlyActionable(v); setPage(0); }} />
        <Switch label="Include weakly reviewed reports" checked={showWeak} onCheckedChange={v => { setShowWeak(v); setPage(0); }} />
        <Button size="sm" variant="ghost" onClick={() => setConsent("health", false)}>Hide health results</Button>
      </div>
      <div className="flex flex-wrap gap-2">
        {Object.entries(TOPICS).map(([id, topic]) => consent[`topic.${id}`]
          ? <Button key={id} size="sm" variant="ghost" onClick={() => setConsent(`topic.${id}`, false)}>Hide {topic.title}</Button>
          : <Gate key={id} title={`Show ${topic.title}`} explain={topic.explain} onAccept={() => setConsent(`topic.${id}`, true)} />)}
      </div>
      <p className="text-sm text-zinc-500" data-testid="health-total">{total.toLocaleString()} findings</p>
      <ul className="space-y-3">{(findings.data?.rows ?? []).map(row => <FindingCard key={`${row.vcv_id}-${row.probe_id}`} row={row} />)}</ul>
      <Pagination page={page + 1} totalPages={Math.max(1, Math.ceil(total / 20))} onPageChange={p => setPage(p - 1)} />
      <Callout color="zinc">
        Confirm anything important with a clinical lab and a genetics professional before making decisions.
      </Callout>
    </section>
  );
}
