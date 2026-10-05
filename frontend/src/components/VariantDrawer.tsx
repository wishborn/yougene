import { useQuery } from "@tanstack/react-query";
import { Badge, Callout, Drawer, Skeleton } from "@particle-academy/react-fancy";
import { variantApi } from "../api";

type Props = { sampleId: string; target: { chrom: string; pos: number } | null; onClose: () => void };

export function VariantDrawer({ sampleId, target, onClose }: Props) {
  const detail = useQuery({
    queryKey: ["variant", sampleId, target?.chrom, target?.pos],
    queryFn: () => variantApi.get(sampleId, target!.chrom, target!.pos),
    enabled: target !== null,
  });
  const d = detail.data;
  return (
    <Drawer open={target !== null} onClose={onClose} side="right" size="lg">
      <Drawer.Header closable>
        {target ? `Chromosome ${target.chrom} · ${target.pos.toLocaleString()} (GRCh37)` : ""}
      </Drawer.Header>
      <Drawer.Body>
        {!d ? <Skeleton height={200} /> : (
          <div className="space-y-5 text-sm" data-testid="variant-detail">
            <section className="space-y-1">
              <h3 className="font-semibold">Your call{d.calls.length > 1 ? "s" : ""}</h3>
              {d.calls.map(c => (
                <p key={c.probe_id}>
                  {c.probe_id}: {c.call_type === "nocall" ? "not read" : c.alleles}
                  {c.call_type === "indel_code" && " (insertion/deletion probe: letters, not sequence)"}
                  {c.ploidy === 1 && " (single copy)"}
                </p>
              ))}
              {d.calls.some(c => c.dup_conflict) && (
                <Callout color="amber">Probes at this position disagree, so this call is unreliable.</Callout>
              )}
            </section>
            {d.curated.length > 0 && (
              <section className="space-y-1">
                <h3 className="font-semibold">Used by</h3>
                {d.curated.map(c => <Badge key={c.kind + c.id} variant="soft" color="zinc" className="mr-1">{c.title}</Badge>)}
              </section>
            )}
            <section className="space-y-2">
              <h3 className="font-semibold">ClinVar</h3>
              {d.clinvar.length === 0 && d.clinvar_hidden === 0 && <p className="text-zinc-500">No ClinVar records at this position.</p>}
              {d.clinvar_hidden > 0 && (
                <p className="text-zinc-500">
                  {d.clinvar_hidden} health record{d.clinvar_hidden > 1 ? "s are" : " is"} hidden. Opt in on the Health tab to see them.
                </p>
              )}
              {d.clinvar.map(r => (
                <div key={r.vcv_id} className="rounded-md border border-zinc-200 p-2 dark:border-zinc-800">
                  <p className="font-medium">{(r.conditions ?? []).filter(c => !/^not (provided|specified)$/i.test(c)).join(" · ") || "Condition not named"}</p>
                  <p className="text-xs text-zinc-500">
                    {r.ref}&gt;{r.alt} · {r.sig_cat.replace(/_/g, " ")} · {r.stars} of 4 stars · {(r.genes ?? []).join(", ")}
                    {" · "}{r.your_copies === null ? "copies not determined" : `you carry ${r.your_copies} cop${r.your_copies === 1 ? "y" : "ies"}`}
                    {" · "}<a className="underline" href={`https://www.ncbi.nlm.nih.gov/clinvar/variation/${r.vcv_id}/`} target="_blank" rel="noreferrer noopener">VCV{r.vcv_id}</a>
                  </p>
                </div>
              ))}
            </section>
            {d.snpedia.length > 0 && (
              <section className="space-y-2" data-testid="snpedia-note">
                <h3 className="font-semibold">SNPedia</h3>
                {d.snpedia.map(n => (
                  <div key={n.rsid} className="space-y-1">
                    <p>
                      Your call is {n.snpedia_genotype} as SNPedia writes it.{" "}
                      {n.genotype_summary ? `SNPedia: “${n.genotype_summary}”` : "SNPedia has no note for this genotype."}
                    </p>
                    {n.about && <p className="text-xs text-zinc-500">{n.about}</p>}
                    <p className="text-xs text-zinc-500">
                      Community-written, not reviewed by YouGene. <a className="underline" href={n.url} target="_blank"
                        rel="noreferrer noopener">SNPedia page</a> · {n.license}
                    </p>
                  </div>
                ))}
              </section>
            )}
            <section className="space-y-2">
              <h3 className="font-semibold">Trait associations</h3>
              {d.traits.length === 0 && <p className="text-zinc-500">No GWAS Catalog associations for this SNP (or the sample isn't matched yet).</p>}
              {d.traits.map((t, i) => (
                <p key={i}>
                  {t.mapped_trait || t.reported_trait}: risk allele {t.risk_allele}, you have{" "}
                  {t.dosage === null ? "an undetermined number of" : t.dosage} cop{t.dosage === 1 ? "y" : "ies"}
                  <span className="text-xs text-zinc-500"> · p {t.p_value} · {t.first_author} {t.published?.slice(0, 4)}</span>
                </p>
              ))}
            </section>
          </div>
        )}
      </Drawer.Body>
    </Drawer>
  );
}
