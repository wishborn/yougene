import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Badge, Button, Input, Modal } from "@particle-academy/react-fancy";
import { api, type Sample } from "../api";
import { percent, sexLabel } from "../format";

type Props = { samples: Sample[]; selected: string | null; onSelect: (id: string | null) => void };

export function SampleList({ samples, selected, onSelect }: Props) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<Sample | null>(null);
  const [deleting, setDeleting] = useState<Sample | null>(null);
  const [name, setName] = useState("");
  const [relationship, setRelationship] = useState("");

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["samples"] });
  const rename = useMutation({
    mutationFn: () => api.rename(editing!.id, { display_name: name.trim(), relationship: relationship.trim() || null }),
    onSuccess: () => { setEditing(null); void refresh(); },
  });
  const remove = useMutation({
    mutationFn: () => api.remove(deleting!.id),
    onSuccess: () => {
      if (deleting?.id === selected) onSelect(null);
      setDeleting(null);
      void refresh();
    },
  });

  if (samples.length === 0) {
    return <p className="text-sm text-zinc-500">No samples yet. Import a file to get started.</p>;
  }

  return (
    <>
      <ul className="space-y-2" aria-label="Samples">
        {samples.map(sample => (
          <li key={sample.id}>
            <div className={`flex flex-wrap items-center gap-3 rounded-lg border p-3 ${sample.id === selected
              ? "border-brand bg-brand/5" : "border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900"}`}>
              <button type="button" className="min-w-0 flex-1 text-left" onClick={() => onSelect(sample.id)}
                aria-pressed={sample.id === selected}>
                <span className="block truncate font-medium">{sample.display_name}</span>
                <span className="block text-xs text-zinc-500">
                  {[sample.relationship, sample.vendor, `${sample.qc.rows.toLocaleString()} probes`,
                    `call rate ${percent(sample.qc.call_rate)}`].filter(Boolean).join(" · ")}
                </span>
              </button>
              <Badge variant="soft" color="zinc">{sexLabel(sample.qc.sex.inferred)}</Badge>
              <Button size="sm" variant="ghost" onClick={() => {
                setEditing(sample); setName(sample.display_name); setRelationship(sample.relationship ?? "");
              }}>Rename</Button>
              <Button size="sm" variant="ghost" onClick={() => setDeleting(sample)}>Delete</Button>
            </div>
          </li>
        ))}
      </ul>

      <Modal open={editing !== null} onClose={() => setEditing(null)} size="sm">
        <Modal.Header>Rename sample</Modal.Header>
        <Modal.Body>
          <div className="space-y-3">
            <Input label="Name" value={name} onValueChange={setName} maxLength={120} />
            <Input label="Relationship (optional)" value={relationship} onValueChange={setRelationship} maxLength={60} />
          </div>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="ghost" onClick={() => setEditing(null)}>Cancel</Button>
          <Button color="brand" disabled={!name.trim() || rename.isPending} onClick={() => rename.mutate()}>Save</Button>
        </Modal.Footer>
      </Modal>

      <Modal open={deleting !== null} onClose={() => setDeleting(null)} size="sm">
        <Modal.Header>Delete {deleting?.display_name}?</Modal.Header>
        <Modal.Body>
          <p className="text-sm">This removes the sample and everything YouGene stored for it from this computer. Your original file isn't affected.</p>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="ghost" onClick={() => setDeleting(null)}>Cancel</Button>
          <Button color="red" disabled={remove.isPending} onClick={() => remove.mutate()}>Delete</Button>
        </Modal.Footer>
      </Modal>
    </>
  );
}
