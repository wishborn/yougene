import { useQuery } from "@tanstack/react-query";
import { Badge, Callout, Skeleton } from "@particle-academy/react-fancy";
import { pgxApi, type PgxGene } from "../api";

const POSITION_STATUS: Record<string, string> = {
  not_tested: "not in this file",
  no_call: "not read",
  conflicting: "probes disagree",
  unexpected: "unexpected letters",
};

function GeneCard({ g }: { g: PgxGene }) {
  return (
    <li className="space-y-2 rounded-lg border border-zinc-200 bg-white p-4 text-sm dark:border-zinc-800 dark:bg-zinc-900"
      data-testid="pgx-gene">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold">{g.gene}</span>
        {g.status === "ok"
          ? <Badge variant="soft" color="blue">{g.phenotype}</Badge>
          : <Badge variant="soft" color="zinc">Not determined</Badge>}
        {g.detail && <span className="text-xs text-zinc-500">{g.detail}</span>}
      </div>
      {g.status !== "ok" && (
        <p>Not every position needed for this gene was read in this file, so no result is given.</p>
      )}
      <p className="text-zinc-600 dark:text-zinc-300">Guidelines use this gene for: {g.drugs.join("; ")}.</p>
      <table className="w-full text-xs">
        <thead className="text-left text-zinc-500">
          <tr><th className="py-1 font-normal">Variant</th><th className="font-normal">Effect</th><th className="font-normal">Your call</th></tr>
        </thead>
        <tbody>
          {g.positions.map(p => (
            <tr key={p.rsid} className="border-t border-zinc-100 dark:border-zinc-800">
              <td className="py-1">
                <a className="underline" href={`https://www.ncbi.nlm.nih.gov/clinvar/variation/${p.clinvar_vcv}/`}
                  target="_blank" rel="noreferrer noopener">{p.star}</a> · {p.rsid}
              </td>
              <td>{p.function === "no" ? "no function" : p.function === "sensitivity" ? "higher sensitivity" : `${p.function} function`}</td>
              <td>{p.status === "ok" ? p.genotype : POSITION_STATUS[p.status]}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {g.note && <p className="text-xs text-zinc-500">{g.note}</p>}
      {g.untested_alleles.length > 0 && (
        <p className="text-xs text-zinc-500">Not tested by arrays: {g.untested_alleles.join(", ")}.</p>
      )}
    </li>
  );
}

export function MedicinesPanel({ sampleId }: { sampleId: string }) {
  const genes = useQuery({ queryKey: ["pgx", sampleId], queryFn: () => pgxApi.list(sampleId) });
  return (
    <section className="space-y-4" aria-labelledby="medicines-title">
      <h2 id="medicines-title" className="sr-only">Medicines</h2>
      <Callout color="amber">
        How your genes may affect some medicines, from the few positions a consumer DNA array can read. Results are
        partial: arrays test only some known variants and can't detect gene copies or deletions (so CYP2D6, an
        important drug gene, isn't reported). Never start, stop or change a medicine because of this. Share it with
        your doctor or pharmacist, who can order a clinical test.
      </Callout>
      {!genes.data ? <Skeleton height={240} /> : (
        <ul className="grid gap-3 lg:grid-cols-2">{genes.data.map(g => <GeneCard key={g.gene} g={g} />)}</ul>
      )}
    </section>
  );
}
