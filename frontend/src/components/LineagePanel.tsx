import { useQuery } from "@tanstack/react-query";
import { Accordion, Badge, Callout, Skeleton } from "@particle-academy/react-fancy";
import { haplogroupApi, type LineageStep, type MaternalLine, type PaternalLine } from "../api";

const MARKER_LABEL = {
  present: "seen in your file",
  absent: "not seen",
  untested: "not tested",
  reverted: "changed back later in this line",
} as const;

const MARKER_COLOR = { present: "green", absent: "red", untested: "zinc", reverted: "zinc" } as const;

function percent(p: number) {
  return p >= 0.999 ? ">99.9%" : `${(p * 100).toFixed(1)}%`;
}

function Path({ steps }: { steps: LineageStep[] }) {
  return (
    <ol className="flex flex-wrap items-center gap-x-1 gap-y-1 text-sm" aria-label="Line of descent">
      {steps.map((s, i) => (
        <li key={s.haplogroup} className="flex items-center gap-1">
          {i > 0 && <span aria-hidden className="text-zinc-400">→</span>}
          <span className={i === steps.length - 1 ? "font-semibold" : "text-zinc-600 dark:text-zinc-300"}>
            {s.haplogroup}
          </span>
        </li>
      ))}
    </ol>
  );
}

function Evidence({ steps }: { steps: LineageStep[] }) {
  return (
    <Accordion type="multiple">
      <Accordion.Item value="evidence">
        <Accordion.Trigger>How this was worked out</Accordion.Trigger>
        <Accordion.Content>
          <table className="w-full text-xs">
            <thead className="text-left text-zinc-500">
              <tr><th className="py-1 font-normal">Branch</th><th className="font-normal">Defining mutations</th></tr>
            </thead>
            <tbody>
              {steps.map(s => (
                <tr key={s.haplogroup} className="border-t border-zinc-100 align-top dark:border-zinc-800">
                  <td className="py-1 pr-3 font-medium">{s.haplogroup}</td>
                  <td className="py-1">
                    <span className="flex flex-wrap gap-1">
                      {s.markers.length === 0 && <span className="text-zinc-500">top of the tree</span>}
                      {s.markers.map(m => (
                        <Badge key={m.mutation + (m.name ?? "")} variant="soft" color={MARKER_COLOR[m.status]}
                          title={MARKER_LABEL[m.status]}>
                          {m.name ? `${m.name} ` : ""}{m.mutation}
                        </Badge>
                      ))}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-2 text-xs text-zinc-500">
            Green: seen in your file. Red: not seen. Grey: not tested, or changed back further down the line.
          </p>
        </Accordion.Content>
      </Accordion.Item>
    </Accordion>
  );
}

function Maternal({ line }: { line: MaternalLine }) {
  if (line.status !== "ok") {
    const message = {
      no_data: "This file has no mitochondrial calls.",
      insufficient: `This file tests too few of the positions that tell maternal lines apart (${line.informative ?? 0}) to place it.`,
      reference_mismatch: "This file's mitochondrial positions don't follow the standard reference (rCRS), so they can't be compared with the tree.",
      unresolved: "The tested positions don't settle even the oldest split in the tree, so no maternal line is given.",
    }[line.status as string] ?? "No maternal line could be worked out.";
    return <p className="text-sm" data-testid="maternal-status">{message}</p>;
  }
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-baseline gap-3">
        <span className="text-3xl font-semibold" data-testid="maternal-haplogroup">{line.haplogroup}</span>
        <Badge variant="soft" color="green">{percent(line.probability!)} likely</Badge>
      </div>
      {line.possibly && (
        <p className="text-sm text-zinc-600 dark:text-zinc-300">
          Possibly more specifically <span className="font-medium">{line.possibly.haplogroup}</span>
          {" "}({percent(line.possibly.probability)}): not certain enough to state.
        </p>
      )}
      <Path steps={line.lineage!} />
      <p className="text-xs text-zinc-500">
        Based on {line.informative!.toLocaleString()} tested positions that tell lines apart
        ({line.tested!.toLocaleString()} mitochondrial positions in all).
        {line.assumed_reference && " This VCF lists only differences, so positions it doesn't list were taken to match the reference, as is standard for sequencing data."}
      </p>
      <Evidence steps={line.lineage!} />
    </div>
  );
}

function Paternal({ line }: { line: PaternalLine }) {
  if (line.status !== "ok") {
    const message = {
      no_y: "This sample has no Y chromosome, so it has no paternal (Y) line. A father's, brother's or paternal uncle's sample would show it.",
      sex_unknown: "YouGene couldn't tell whether this sample has a Y chromosome, so no paternal line is given.",
      no_data: "This file has no Y-chromosome calls.",
      insufficient: `This file tests too few Y-chromosome positions in the tree (${line.informative ?? 0}) to place it.`,
      unresolved: "No branch-defining Y mutations were seen, so no paternal line is given.",
    }[line.status as string] ?? "No paternal line could be worked out.";
    return <p className="text-sm" data-testid="paternal-status">{message}</p>;
  }
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-baseline gap-3">
        <span className="text-3xl font-semibold" data-testid="paternal-haplogroup">{line.short_name}</span>
        <span className="text-sm text-zinc-500">{line.haplogroup}</span>
      </div>
      <Path steps={line.lineage!} />
      <p className="text-xs text-zinc-500">
        {line.derived!.toLocaleString()} branch-defining mutations seen along this line, out of{" "}
        {line.informative!.toLocaleString()} tested Y positions in the tree.
      </p>
      <Evidence steps={line.lineage!} />
    </div>
  );
}

export function LineagePanel({ sampleId }: { sampleId: string }) {
  const result = useQuery({ queryKey: ["haplogroups", sampleId], queryFn: () => haplogroupApi.get(sampleId) });
  const data = result.data;
  return (
    <section className="space-y-4" aria-labelledby="lineage-title">
      <h2 id="lineage-title" className="sr-only">Lineage</h2>
      <Callout color="blue">
        Your maternal line follows your mother's mother's mother, and so on; your paternal line follows your father's
        father's father. Each is one line among thousands of ancestors, so it says where those two lines branched
        from, not your ancestry or ethnicity as a whole. Names come from PhyloTree 17 and the 2016 ISOGG tree; newer
        trees may name some branches differently.
      </Callout>
      {result.isError && <Callout color="red">The lineage couldn't be worked out for this sample.</Callout>}
      {!data ? !result.isError && <Skeleton height={240} /> : (
        <>
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="space-y-3 rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900"
              data-testid="maternal-line">
              <h3 className="font-semibold">Maternal line (mtDNA)</h3>
              <Maternal line={data.maternal} />
            </div>
            <div className="space-y-3 rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900"
              data-testid="paternal-line">
              <h3 className="font-semibold">Paternal line (Y chromosome)</h3>
              <Paternal line={data.paternal} />
            </div>
          </div>
          <p className="text-xs text-zinc-500">
            Maternal: {data.sources.maternal.tree.name} ({data.sources.maternal.tree.licence}).{" "}
            {data.sources.maternal.method} Paternal: {data.sources.paternal.tool}, {data.sources.paternal.tree}.{" "}
            {data.sources.paternal.licence}
          </p>
        </>
      )}
    </section>
  );
}
