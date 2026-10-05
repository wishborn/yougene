import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Callout, FileUpload, Input, Progress } from "@particle-academy/react-fancy";
import { api, ApiError } from "../api";

type Props = { onImported: (sampleId: string) => void };

export function ImportPanel({ onImported }: Props) {
  const queryClient = useQueryClient();
  const [files, setFiles] = useState<File[]>([]);
  const [name, setName] = useState("");
  const [relationship, setRelationship] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const [duplicateOf, setDuplicateOf] = useState<string | null>(null);
  // Remounting FileUpload clears its hidden <input>, so choosing the same file
  // again still registers (the browser fires no change event otherwise).
  const [pickerKey, setPickerKey] = useState(0);
  const resetPicker = () => { setFiles([]); setPickerKey(k => k + 1); };

  const upload = useMutation({
    mutationFn: (replace: boolean) =>
      api.upload(files[0], { name: name.trim(), relationship: relationship.trim(), replace }),
    onSuccess: ({ job_id }) => {
      setDuplicateOf(null);
      setJobId(job_id);
    },
    onError: error => {
      if (error instanceof ApiError && error.status === 409) {
        const body = error.body as { sample_id?: string } | undefined;
        setDuplicateOf(body?.sample_id ?? "");
      }
    },
  });

  const job = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => api.job(jobId!),
    enabled: jobId !== null,
    refetchInterval: query => {
      const state = query.state.data?.state;
      return state === "done" || state === "failed" ? false : 400;
    },
  });

  const finished = job.data?.state === "done" ? job.data.sample_id : null;
  useEffect(() => {
    if (!finished) return;
    void queryClient.invalidateQueries({ queryKey: ["samples"] });
    onImported(finished);
    resetPicker();
    setName("");
    setRelationship("");
  }, [finished, onImported, queryClient]);

  const running = upload.isPending || job.data?.state === "queued" || job.data?.state === "running";
  const failed = job.data?.state === "failed" ? job.data.message : null;
  const uploadError = upload.error && !(upload.error instanceof ApiError && upload.error.status === 409)
    ? upload.error.message : null;

  return (
    <section aria-labelledby="import-title" className="space-y-4 rounded-lg border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
      <div>
        <h2 id="import-title" className="font-semibold">Import a raw data file</h2>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          23andMe raw data, as the .txt file or the .zip you downloaded. The file stays on this computer.
        </p>
      </div>
      <FileUpload key={pickerKey} value={files}
        onChange={next => { setFiles(next.slice(-1)); setJobId(null); setDuplicateOf(null); }}
        accept=".txt,.zip" multiple={false} disabled={running}>
        <FileUpload.Dropzone className="text-sm">Drop the file here, or click to choose it</FileUpload.Dropzone>
        <FileUpload.List />
        {files.length > 0 && !running && (
          <Button size="sm" variant="ghost" onClick={resetPicker}>Choose a different file</Button>
        )}
      </FileUpload>
      <div className="grid gap-3 sm:grid-cols-2">
        <Input label="Name" placeholder="e.g. Me, Mum, Sam" value={name} onValueChange={setName} maxLength={120} disabled={running} />
        <Input label="Relationship (optional)" placeholder="e.g. me, mother" value={relationship}
          onValueChange={setRelationship} maxLength={60} disabled={running} />
      </div>
      <div className="flex items-center gap-3">
        <Button color="brand" disabled={files.length === 0 || running} onClick={() => upload.mutate(false)}>
          Import
        </Button>
        {running && job.data && <span className="text-sm text-zinc-500" data-testid="import-status">{job.data.message}…</span>}
      </div>
      {running && <Progress value={Math.round((job.data?.progress ?? 0) * 100)} max={100} indeterminate={!job.data} />}
      {duplicateOf !== null && (
        <Callout color="amber">
          This file has already been imported.{" "}
          <Button size="sm" color="brand" onClick={() => upload.mutate(true)}>Replace the existing copy</Button>
        </Callout>
      )}
      {failed && <Callout color="red" data-testid="import-error">{failed}</Callout>}
      {uploadError && <Callout color="red">{uploadError}</Callout>}
    </section>
  );
}
