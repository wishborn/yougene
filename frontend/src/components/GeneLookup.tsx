import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button, Callout, Input } from "@particle-academy/react-fancy";
import { geneApi } from "../api";

export function GeneLookup({ sampleId }: { sampleId: string }) {
  const [text, setText] = useState("");
  const [gene, setGene] = useState<string | null>(null);
  const view = useQuery({
    queryKey: ["gene", sampleId, gene],
    queryFn: () => geneApi.get(sampleId, gene!),
    enabled: gene !== null,
    retry: false,
  });
  const v = view.data;
  return (
    <section className="space-y-3 rounded-lg border border-zinc-200 bg-white p-4 text-sm dark:border-zinc-800 dark:bg-zinc-900"
      aria-labelledby="gene-title">
      <h3 id="gene-title" className="font-semibold">Look up a gene</h3>
      <form className="flex items-end gap-2" onSubmit={e => { e.preventDefault(); if (text.trim()) setGene(text.trim().toUpperCase()); }}>
        <div className="w-56"><Input aria-label="Gene symbol" placeholder="Gene symbol, e.g. CFTR" value={text} onValueChange={setText} size="sm" /></div>
        <Button size="sm" type="submit">Look up</Button>
      </form>
      {view.error && <Callout color="amber">{view.error.message}</Callout>}
      {v && (
        <div className="space-y-2" data-testid="gene-view">
          <p>
            <span className="font-medium">{v.gene}</span>: ClinVar lists {v.known_pathogenic_snvs.toLocaleString()} single-letter
            variants it classes as pathogenic or likely pathogenic. This file read {v.tested.toLocaleString()} of them
            {v.known_pathogenic_snvs > 0 && ` (${Math.round((v.tested / v.known_pathogenic_snvs) * 100)}%)`}, and you carry{" "}
            {v.carried.length === 0 ? "none of those" : `${v.carried.length}`}.
          </p>
          <p className="text-zinc-500">
            Variants this file doesn't read, and other kinds of change (insertions, deletions, copy-number changes), can't be
            ruled out, so a clear result here isn't a clear result for the gene.
          </p>
          {v.carried.length > 0 && (
            <Callout color="amber">
              Carried here: {v.carried.map(c => `${c.chrom}:${c.pos.toLocaleString()} ${c.ref}>${c.alt} (${c.stars}★)`).join(", ")}.
              See the findings list above for details and caveats.
            </Callout>
          )}
          {v.tested_positions.length > 0 && (
            <details>
              <summary className="cursor-pointer text-zinc-600 dark:text-zinc-300">Positions read ({v.tested_positions.length})</summary>
              <table className="mt-2 w-full text-xs">
                <thead className="text-left text-zinc-500"><tr><th className="font-normal">Position</th><th className="font-normal">Variant</th><th className="font-normal">Your call</th><th className="font-normal">ClinVar</th></tr></thead>
                <tbody>
                  {v.tested_positions.map(p => (
                    <tr key={`${p.vcv_id}-${p.probe_id}`} className="border-t border-zinc-100 dark:border-zinc-800">
                      <td className="py-0.5">{p.chrom}:{p.pos.toLocaleString()}</td>
                      <td>{p.ref}&gt;{p.alt}</td>
                      <td>{p.alleles}</td>
                      <td><a className="underline" href={`https://www.ncbi.nlm.nih.gov/clinvar/variation/${p.vcv_id}/`} target="_blank" rel="noreferrer noopener">{p.stars}★</a></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          )}
        </div>
      )}
    </section>
  );
}
