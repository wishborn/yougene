import { useQuery } from "@tanstack/react-query";
import { Badge, Skeleton } from "@particle-academy/react-fancy";
import { knownTraitsApi, type KnownTrait } from "../api";

const STATUS: Record<Exclude<KnownTrait["status"], "ok">, string> = {
  not_tested: "This file doesn't include this SNP.",
  no_call: "This SNP wasn't read successfully in this file.",
  conflicting: "Probes in this file disagree at this SNP, so it isn't interpreted.",
  unexpected: "The letters in this file don't match this SNP's known alleles, so it isn't interpreted.",
};

export function KnownTraits({ sampleId }: { sampleId: string }) {
  const traits = useQuery({ queryKey: ["known-traits", sampleId], queryFn: () => knownTraitsApi.list(sampleId) });
  if (!traits.data) return <Skeleton height={160} />;
  return (
    <section aria-labelledby="known-title" className="space-y-3">
      <h3 id="known-title" className="font-semibold">Well-known traits</h3>
      <ul className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {traits.data.map(t => (
          <li key={t.id} className="space-y-2 rounded-lg border border-zinc-200 bg-white p-4 text-sm dark:border-zinc-800 dark:bg-zinc-900"
            data-testid="known-trait">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{t.title}</span>
              {t.status === "ok" && <Badge size="sm" variant="soft" color="zinc">{t.genotype}</Badge>}
            </div>
            <p>{t.status === "ok" ? t.summary : STATUS[t.status]}</p>
            <p className="text-xs text-zinc-500">{t.caveat}</p>
            <p className="text-xs text-zinc-500">
              {t.gene} · {t.rsid} · allele {t.effect_allele} ·{" "}
              <a className="underline" href={`https://www.ncbi.nlm.nih.gov/clinvar/variation/${t.clinvar_vcv}/`}
                target="_blank" rel="noreferrer noopener">ClinVar</a>
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}
