// Browser smoke test of the app, using synthetic fixtures only.
// Run it against servers started with a throwaway data dir and spare ports,
// never your real data (see README):
//   YOUGENE_DATA_DIR=<tmp> YOUGENE_API_PORT=8799 PORT=5190 python scripts/dev.py
//   YOUGENE_SMOKE_URL=http://127.0.0.1:5190 npm run smoke
// With invented reference data installed in that dir (synth_reference), the
// traits, medicines, chromosomes and health pages are exercised too.
import { chromium } from "@playwright/test";
import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const fixtures = join(here, "../../backend/tests/fixtures/synthetic");
const artifacts = join(tmpdir(), "yougene-smoke");
const origin = process.env.YOUGENE_SMOKE_URL || "http://127.0.0.1:5190";
await mkdir(artifacts, { recursive: true });

const browser = await chromium.launch();
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1100 }, colorScheme: "light" });
  const page = await context.newPage();
  const errors = [];
  const external = [];
  const failed = [];
  page.on("pageerror", error => errors.push(error.message));
  page.on("console", message => {
    // The duplicate-import check answers 409 on purpose; Chrome logs every 4xx.
    if (message.type() === "error" && !/status of 409/.test(message.text())) errors.push(message.text());
  });
  page.on("response", response => {
    if (response.status() >= 400 && response.status() !== 409) failed.push(`${response.status()} ${response.request().method()} ${response.url()}`);
  });
  page.on("request", request => {
    const url = new URL(request.url());
    if (!["yougene.gen", "127.0.0.1", "localhost"].includes(url.hostname) && ["http:", "https:"].includes(url.protocol)) {
      external.push(request.url());
    }
  });
  const sidebar = page.locator("[data-react-fancy-sidebar]").first();
  const nav = async name => {
    await sidebar.getByRole("link", { name, exact: true }).first().click();
    await page.waitForLoadState("networkidle");
  };

  // Home: empty, then import two samples (each lands on its overview page).
  await page.goto(origin);
  await page.getByText("No samples yet").waitFor({ timeout: 15_000 }); // needs an empty data dir
  const reference = await (await page.request.get(`${origin}/api/refdata`)).json();
  const withReference = reference.ready === true;

  async function importFixture(sex, name) {
    await page.goto(origin);
    await page.locator('input[type="file"]').setInputFiles(join(fixtures, `${sex}.txt`));
    await page.getByLabel("Name", { exact: true }).first().fill(name);
    await page.getByRole("button", { name: "Import", exact: true }).click();
    await page.waitForURL(/\/samples\/[0-9a-f]+$/, { timeout: 30_000 });
    await page.getByRole("heading", { name, level: 1 }).waitFor();
  }
  await importFixture("female", "Synthetic female");
  await page.getByTestId("qc-sex").filter({ hasText: "XX" }).waitFor();
  await importFixture("male", "Synthetic male");
  await page.getByTestId("qc-sex").filter({ hasText: "XY" }).waitFor();
  await page.getByTestId("qc-chart").locator("svg").waitFor();

  // Re-importing the same file offers a replacement instead of duplicating.
  await page.goto(origin);
  await page.locator('input[type="file"]').setInputFiles(join(fixtures, "female.txt"));
  await page.getByRole("button", { name: "Import", exact: true }).click();
  await page.getByText("This file has already been imported.").waitFor();

  // Calls page via the sidebar (client-side Inertia navigation).
  await page.goto(origin);
  await sidebar.getByRole("link", { name: "Open" }).last().click();
  await page.getByRole("heading", { name: "Synthetic male", level: 1 }).waitFor();
  await nav("All calls");
  await page.getByTestId("calls-total").filter({ hasText: "5,000 matching" }).waitFor();
  assert.equal(await page.locator("[data-fancy-grid-row]").count(), 50);
  const header = page.getByRole("columnheader", { name: /Position/ });
  await header.click();
  await header.click();
  await page.getByLabel("Chromosome").selectOption("X");
  await page.waitForFunction(() =>
    [...document.querySelectorAll("[data-fancy-grid-row]")].every(row => row.textContent?.includes("X")));
  await page.getByLabel("Chromosome").selectOption("");
  await page.getByLabel("Call type").selectOption("nocall");
  await page.waitForFunction(() =>
    [...document.querySelectorAll("[data-fancy-grid-row]")].every(row => row.textContent?.includes("no call")));
  await page.getByLabel("Call type").selectOption("");
  await page.locator("[data-fancy-grid-row] button").first().click();
  await page.getByTestId("variant-detail").waitFor();
  await page.keyboard.press("Escape");
  await page.getByTestId("variant-detail").waitFor({ state: "detached" });
  await page.getByRole("button", { name: "2", exact: true }).first().click();
  await page.waitForTimeout(300);

  if (withReference) {
    await nav("Traits");
    await page.getByTestId("known-trait").nth(5).waitFor();
    await page.getByTestId("traits-total").filter({ hasText: /^[1-9][\d,]* associations$/ }).waitFor();
    await nav("Medicines");
    await page.getByTestId("pgx-gene").nth(7).waitFor();
    await nav("Chromosomes");
    await page.getByTestId("karyotype").waitFor();
    assert.equal(await page.getByTestId("karyotype").locator("svg").count(), 24);
    await page.getByTestId("roh-total").waitFor();
    await page.getByRole("button", { name: "Chromosome 1", exact: true }).click();
    await page.getByTestId("chromosome-summary").filter({ hasText: /[1-9][\d,]* probes/ }).waitFor();
    await page.getByRole("button", { name: "All chromosomes" }).click();
    await nav("Health");
    assert.equal(await page.getByTestId("health-finding").count(), 0, "health shown before opt-in");
    await page.getByRole("button", { name: "Show health results" }).click();
    await page.getByRole("dialog").getByText("I understand and want to see these results").click();
    await page.getByRole("dialog").getByRole("button", { name: "Show results" }).click();
    await page.getByTestId("health-total").waitFor();
    await page.getByTestId("coverage-note").first().waitFor();
    await page.getByLabel("Gene symbol").fill("GENE2");
    await page.getByRole("button", { name: "Look up" }).click();
    await page.getByTestId("gene-view").waitFor();
    await page.getByRole("button", { name: /Show APOE/ }).click();
    await page.getByRole("dialog").getByText("I understand and want to see these results").click();
    await page.getByRole("dialog").getByRole("button", { name: "Show results" }).click();
    await page.getByRole("button", { name: /Hide APOE/ }).waitFor();
    // Consent is listed (and can be withdrawn) in Settings.
    await nav("Settings");
    await page.getByRole("heading", { name: "What you've chosen to see" }).waitFor();
    await page.getByRole("button", { name: "Hide" }).first().click();
    // Withdrawing health withdraws every topic, so no "Hide" buttons remain.
    await page.waitForFunction(() => ![...document.querySelectorAll("button")].some(b => b.textContent === "Hide"));
  }

  for (const mode of ["light", "dark"]) {
    await page.getByLabel("Theme", { exact: true }).selectOption(mode);
    await page.waitForFunction(dark => document.documentElement.classList.contains("dark") === dark, mode === "dark");
    await page.screenshot({ path: join(artifacts, `${mode}.png`), fullPage: true });
  }

  // Rename, then delete both samples on Home so the data dir ends empty.
  await page.goto(origin);
  await page.getByRole("button", { name: "Rename" }).first().click();
  await page.getByRole("dialog").getByLabel("Name", { exact: true }).fill("Renamed synthetic");
  await page.getByRole("dialog").getByRole("button", { name: "Save" }).click();
  await page.getByRole("button", { name: /Renamed synthetic/ }).waitFor();
  await sidebar.getByText("Renamed synthetic").waitFor(); // shared props reloaded
  for (let i = 0; i < 2; i++) {
    await page.getByRole("button", { name: "Delete", exact: true }).first().click();
    await page.getByRole("dialog").getByRole("button", { name: "Delete", exact: true }).click();
    await page.getByRole("dialog").waitFor({ state: "detached" });
  }
  await page.getByText("No samples yet").waitFor();

  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true,
    "horizontal overflow on mobile");
  await page.screenshot({ path: join(artifacts, "mobile.png"), fullPage: true });

  assert.deepEqual(external, [], "external requests");
  assert.deepEqual(failed, [], "failed requests");
  assert.deepEqual(errors, [], "browser errors");
  console.log(JSON.stringify({ result: "PASS", origin, withReference, artifacts }, null, 2));
} finally {
  await browser.close();
}
