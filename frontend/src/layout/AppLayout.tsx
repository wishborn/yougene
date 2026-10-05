import type { ReactNode } from "react";
import { Link, usePage } from "@inertiajs/react";
import { Navbar, Sidebar, useTheme, type ThemePreference } from "@particle-academy/react-fancy";

export type SharedProps = { samples: { id: string; display_name: string; relationship: string | null }[] };

const SAMPLE_PAGES = [
  ["", "Overview"],
  ["calls", "All calls"],
  ["chromosomes", "Chromosomes"],
  ["traits", "Traits"],
  ["medicines", "Medicines"],
  ["lineage", "Lineage"],
  ["health", "Health"],
] as const;

export function AppLayout({ title, children }: { title: string; children: ReactNode }) {
  const theme = useTheme();
  const { url, props } = usePage<SharedProps>();
  const path = url.split("?")[0];
  const current = path.match(/^\/samples\/([0-9a-f]+)/)?.[1] ?? null;

  return (
    <div className="min-h-screen bg-zinc-50 text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100">
      <title>{`${title} · YouGene`}</title>
      <Navbar className="px-6">
        <Navbar.Brand><Link href="/" className="font-semibold tracking-tight">YouGene</Link></Navbar.Brand>
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
        <Sidebar className="hidden min-h-[calc(100vh-65px)] w-60 shrink-0 md:flex">
          <Sidebar.Group label="YouGene">
            <Sidebar.Item as={Link} href="/" active={path === "/"}>Samples</Sidebar.Item>
            <Sidebar.Item as={Link} href="/settings" active={path === "/settings"}>Settings</Sidebar.Item>
          </Sidebar.Group>
          {props.samples.map(sample => (
            <Sidebar.Group key={sample.id} label={sample.display_name}>
              {sample.id === current
                ? SAMPLE_PAGES.map(([slug, label]) => {
                    const href = `/samples/${sample.id}${slug ? `/${slug}` : ""}`;
                    return <Sidebar.Item key={slug} as={Link} href={href} active={path === href}>{label}</Sidebar.Item>;
                  })
                : <Sidebar.Item as={Link} href={`/samples/${sample.id}`}>Open</Sidebar.Item>}
            </Sidebar.Group>
          ))}
        </Sidebar>
        <main className="mx-auto min-w-0 max-w-6xl flex-1 space-y-6 p-5 lg:p-9">
          {current && (
            <nav aria-label="Sample sections" className="flex flex-wrap gap-2 md:hidden">
              {SAMPLE_PAGES.map(([slug, label]) => (
                <Link key={slug} href={`/samples/${current}${slug ? `/${slug}` : ""}`}
                  className="rounded-md border border-zinc-300 px-2 py-1 text-sm dark:border-zinc-700">{label}</Link>
              ))}
            </nav>
          )}
          {children}
          <footer className="text-xs text-zinc-500">
            YouGene is not a diagnosis. Consumer DNA arrays are not clinical grade; confirm anything important with a
            clinical lab and a genetics professional.
          </footer>
        </main>
      </div>
    </div>
  );
}

export function PageHeader({ eyebrow, title, children }: { eyebrow?: string; title: string; children?: ReactNode }) {
  return (
    <header>
      {eyebrow && <p className="text-xs font-semibold uppercase tracking-widest text-brand">{eyebrow}</p>}
      <h1 className="mt-2 text-3xl font-semibold tracking-tight">{title}</h1>
      {children && <div className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">{children}</div>}
    </header>
  );
}
