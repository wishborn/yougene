import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Navbar, Sidebar, Stat, useTheme, type ThemePreference } from "@particle-academy/react-fancy";
import { EChart, type EChartsOption } from "@particle-academy/fancy-echarts";
import { FancyDataGrid, type FancyGridColumn, type FancyGridState } from "@particle-academy/fancy-grid";

type SmokeRow = { id: string; chromosome: number; position: number; genotype: string };
type Health = { status: string; version: string };

async function fetchHealth(): Promise<Health> {
  const response = await fetch("/api/health");
  if (!response.ok) throw new Error(`Backend returned ${response.status}`);
  const value: unknown = await response.json();
  if (typeof value !== "object" || value === null || !("status" in value) ||
      !("version" in value) || typeof value.status !== "string" || typeof value.version !== "string") {
    throw new Error("Unexpected health response");
  }
  return { status: value.status, version: value.version };
}

export function App() {
  const theme = useTheme();
  const health = useQuery({ queryKey: ["health"], queryFn: fetchHealth, retry: 1 });
  const [gridState, setGridState] = useState<FancyGridState>({
    sorting: [],
    filters: [],
    rowSelection: {},
    pagination: { pageIndex: 0, pageSize: 50 },
  });
  const rows = useMemo<SmokeRow[]>(() => Array.from({ length: 50 }, (_, i) => ({
    id: `demo-${String(i + 1).padStart(2, "0")}`,
    chromosome: (i % 5) + 1,
    position: 1_000_000 + i * 25_000,
    genotype: ["AA", "AG", "CC", "CT", "--"][i % 5],
  })), []);
  const columns = useMemo<FancyGridColumn<SmokeRow>[]>(() => [
    { id: "id", header: "Synthetic probe", sortable: true },
    { id: "chromosome", header: "Chromosome", sortable: true },
    { id: "position", header: "Position", sortable: true, align: "end" },
    { id: "genotype", header: "Call", sortable: true },
  ], []);
  const option = useMemo<EChartsOption>(() => ({
    backgroundColor: "transparent",
    animation: false,
    tooltip: { trigger: "axis" },
    grid: { left: 45, right: 20, top: 20, bottom: 35 },
    xAxis: { type: "category", data: ["1", "2", "3", "4", "5"], name: "Chr" },
    yAxis: { type: "value", minInterval: 1 },
    series: [{ type: "bar", data: [10, 10, 10, 10, 10], barMaxWidth: 45,
      itemStyle: { color: theme.resolved === "dark" ? "#a7b8ff" : "#5266bd", borderRadius: [4, 4, 0, 0] } }],
  }), [theme.resolved]);

  return (
    <div className="min-h-screen bg-zinc-50 text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100">
      <Navbar className="px-6">
        <Navbar.Brand><span className="font-semibold tracking-tight">YouGene</span></Navbar.Brand>
        <div className="flex items-center gap-3">
          <span className="hidden text-sm text-zinc-500 sm:inline">Local · synthetic data only</span>
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
            <Sidebar.Item active>Kit smoke page</Sidebar.Item>
          </Sidebar.Group>
          <p className="px-4 py-6 text-xs text-zinc-500">Temporary scaffold. Routing pending fancy-inertia-server.</p>
        </Sidebar>
        <main className="mx-auto min-w-0 max-w-6xl flex-1 space-y-6 p-5 lg:p-9">
          <header>
            <p className="text-xs font-semibold uppercase tracking-widest text-brand dark:text-brand-contrast">P0 · component check</p>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight">Kit smoke page</h1>
            <p className="mt-2 text-zinc-500 dark:text-zinc-400">Temporary page with invented calls. Replaced by application pages when routing is available.</p>
          </header>
          <Stat.Band columns={3} className="rounded-lg border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
            <Stat value="50" label="Synthetic probes" />
            <Stat value="5" label="Demo chromosomes" />
            <Stat value="0" label="Personal samples" />
          </Stat.Band>
          <section aria-label="Backend connection" className="rounded-lg border border-zinc-200 bg-white px-5 py-4 text-sm dark:border-zinc-800 dark:bg-zinc-900">
            <span className="font-medium">Backend: </span>
            <span data-testid="health-status">{health.isPending ? "Connecting…" : health.isError
              ? "Backend unavailable. Check the site logs." : `${health.data.status} · v${health.data.version}`}</span>
          </section>
          <section className="rounded-lg border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900" aria-labelledby="chart-title">
            <h2 id="chart-title" className="font-semibold">Synthetic probe counts</h2>
            <p className="mt-1 text-sm text-zinc-500">Static demonstration of chart styling. No genetic conclusions.</p>
            <EChart option={option} theme={theme.resolved} renderer="svg" style={{ height: 240 }} data-testid="probe-chart" />
          </section>
          <section aria-labelledby="grid-title">
            <h2 id="grid-title" className="mb-3 font-semibold">Invented calls <span className="font-normal text-zinc-500">· select a column header to sort</span></h2>
            <div className="max-h-80 overflow-auto rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
              <FancyDataGrid gridId="synthetic-smoke" rows={rows} columns={columns} state={gridState} onStateChange={setGridState} />
            </div>
          </section>
          <footer className="text-xs text-zinc-500">YouGene is not a diagnosis. Confirm actionable findings with a clinical lab and a genetics professional.</footer>
        </main>
      </div>
    </div>
  );
}
