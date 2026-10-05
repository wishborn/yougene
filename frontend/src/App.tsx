import { useCallback, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Navbar, Sidebar, useTheme, type ThemePreference } from "@particle-academy/react-fancy";
import { api } from "./api";
import { CallsGrid } from "./components/CallsGrid";
import { ImportPanel } from "./components/ImportPanel";
import { QcCard } from "./components/QcCard";
import { ReferencePanel } from "./components/ReferencePanel";
import { SampleList } from "./components/SampleList";

export function App() {
  const theme = useTheme();
  const health = useQuery({ queryKey: ["health"], queryFn: api.health, retry: 1 });
  const samples = useQuery({ queryKey: ["samples"], queryFn: api.samples });
  const [chosen, setChosen] = useState<string | null>(null);
  const onImported = useCallback((id: string) => setChosen(id), []);

  const list = samples.data ?? [];
  const selected = list.find(s => s.id === chosen) ?? list[0] ?? null;

  return (
    <div className="min-h-screen bg-zinc-50 text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100">
      <Navbar className="px-6">
        <Navbar.Brand><span className="font-semibold tracking-tight">YouGene</span></Navbar.Brand>
        <div className="flex items-center gap-3">
          <span className="hidden text-sm text-zinc-500 sm:inline">Your files stay on this computer</span>
          <label className="flex items-center gap-2 text-sm">Theme
            <select aria-label="Theme" value={theme.preference}
              onChange={e => theme.setPreference(e.target.value as ThemePreference)}
              className="rounded-md border border-zinc-300 bg-white px-3 py-2 dark:border-zinc-700 dark:bg-zinc-900">
              <option value="light">Light</option><option value="dark">Dark</option><option value="system">System</option>
            </select>
          </label>
        </div>
      </Navbar>
      <div className="flex">
        <Sidebar className="hidden min-h-[calc(100vh-65px)] shrink-0 md:flex">
          <Sidebar.Group label="Development">
            <Sidebar.Item active>Samples</Sidebar.Item>
          </Sidebar.Group>
          <p className="px-4 py-6 text-xs text-zinc-500">Temporary workspace. Proper pages arrive with routing.</p>
        </Sidebar>
        <main className="mx-auto min-w-0 max-w-6xl flex-1 space-y-6 p-5 lg:p-9">
          <header>
            <p className="text-xs font-semibold uppercase tracking-widest text-brand">Development workspace</p>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight">Samples</h1>
            <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400" data-testid="health-status">
              {health.isPending ? "Connecting to the local server…" : health.isError
                ? "The local server isn't responding. Check the site logs."
                : `Local server ${health.data.status} · v${health.data.version}`}
            </p>
          </header>

          <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
            <ImportPanel onImported={onImported} />
            <section aria-labelledby="samples-title" className="space-y-3">
              <h2 id="samples-title" className="font-semibold">Samples on this computer</h2>
              {samples.isPending ? <p className="text-sm text-zinc-500">Loading…</p>
                : <SampleList samples={list} selected={selected?.id ?? null} onSelect={setChosen} />}
            </section>
          </div>

          <ReferencePanel />

          {selected && <QcCard sample={selected} dark={theme.resolved === "dark"} />}
          {selected && <CallsGrid key={selected.id} sampleId={selected.id} />}

          <footer className="text-xs text-zinc-500">
            YouGene is not a diagnosis. Consumer DNA arrays are not clinical grade; confirm anything
            important with a clinical lab and a genetics professional.
          </footer>
        </main>
      </div>
    </div>
  );
}
