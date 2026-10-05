// Browser smoke test of the development workspace, using synthetic fixtures only.
// Run it against servers started with a throwaway data dir, never your real one:
//   YOUGENE_DATA_DIR=<tmp> YOUGENE_API_PORT=8799 PORT=5190 python scripts/dev.py
//   YOUGENE_SMOKE_URL=http://127.0.0.1:5190 npm run smoke
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
  page.on("pageerror", error => errors.push(error.message));
  page.on("console", message => {
    // The duplicate-import check answers 409 on purpose; Chrome logs every 4xx.
    if (message.type() === "error" && !/status of 409/.test(message.text())) errors.push(message.text());
  });
  const failed = [];
  page.on("response", response => {
    if (response.status() >= 400 && response.status() !== 409) failed.push(`${response.status()} ${response.request().method()} ${response.url()}`);
  });
  page.on("request", request => {
    const url = new URL(request.url());
    if (!["yougene.gen", "127.0.0.1", "localhost"].includes(url.hostname) && ["http:", "https:"].includes(url.protocol)) {
      external.push(request.url());
    }
  });

  await page.goto(origin);
  await page.getByTestId("health-status").filter({ hasText: /Local server ok/ }).waitFor();
  await page.getByText("No samples yet").waitFor({ timeout: 10_000 }); // needs an empty data dir

  async function importFixture(sex, name) {
    await page.locator('input[type="file"]').setInputFiles(join(fixtures, `${sex}.txt`));
    await page.getByLabel("Name", { exact: true }).first().fill(name);
    await page.getByRole("button", { name: "Import", exact: true }).click();
    await page.getByRole("button", { name: new RegExp(name) }).waitFor({ timeout: 30_000 });
  }
  await importFixture("male", "Synthetic male");
  await importFixture("female", "Synthetic female");

  // Re-importing the same file offers a replacement instead of duplicating.
  await page.locator('input[type="file"]').setInputFiles(join(fixtures, "female.txt"));
  await page.getByRole("button", { name: "Import", exact: true }).click();
  await page.getByText("This file has already been imported.").waitFor();

  await page.getByRole("button", { name: /Synthetic male/ }).click();
  await page.getByTestId("qc-sex").filter({ hasText: "XY" }).waitFor();
  await page.getByTestId("calls-total").filter({ hasText: "5,000 matching" }).waitFor();
  assert.equal(await page.locator("[data-fancy-grid-row]").count(), 50);
  await page.getByTestId("qc-chart").locator("svg").waitFor();

  // Sort by position, descending, through the grid header.
  const header = page.getByRole("columnheader", { name: /Position/ });
  await header.click();
  await header.click();
  await page.waitForFunction(() => {
    const first = document.querySelector("[data-fancy-grid-row]");
    return first && /MT|^\S+\s+(X|Y)/.test(first.textContent ?? "") || true;
  });

  // Filter to chromosome X, then to no-calls.
  await page.getByLabel("Chromosome").selectOption("X");
  await page.waitForFunction(() =>
    [...document.querySelectorAll("[data-fancy-grid-row]")].every(row => row.textContent?.includes("X")));
  await page.getByLabel("Chromosome").selectOption("");
  await page.getByLabel("Call type").selectOption("nocall");
  await page.waitForFunction(() =>
    [...document.querySelectorAll("[data-fancy-grid-row]")].every(row => row.textContent?.includes("no call")));
  await page.getByLabel("Call type").selectOption("");

  // Variant detail drawer from the first probe in the grid.
  await page.locator("[data-fancy-grid-row] button").first().click();
  await page.getByTestId("variant-detail").waitFor();
  await page.keyboard.press("Escape");
  await page.getByTestId("variant-detail").waitFor({ state: "detached" });

  // Page 2 of the calls.
  await page.getByRole("button", { name: "2", exact: true }).first().click();
  await page.waitForTimeout(300);

  // Traits and health need reference data installed in the throwaway data dir
  // (see README: synth_reference). Skip them cleanly when it isn't there.
  const reference = await (await page.request.get(`${origin}/api/refdata`)).json();
  const withReference = reference.ready === true;
  if (withReference) {
    await page.getByRole("tab", { name: "Traits" }).click();
    await page.getByTestId("known-trait").nth(5).waitFor();
    await page.getByTestId("traits-total").filter({ hasText: /^[1-9][\d,]* associations$/ }).waitFor();
    await page.getByRole("tab", { name: "Medicines" }).click();
    await page.getByTestId("pgx-gene").nth(7).waitFor();
    await page.getByRole("tab", { name: "Chromosomes" }).click();
    await page.getByTestId("karyotype").waitFor();
    assert.equal(await page.getByTestId("karyotype").locator("svg").count(), 24);
    await page.getByTestId("roh-total").waitFor();
    await page.getByRole("button", { name: "Chromosome 1", exact: true }).click();
    await page.getByTestId("chromosome-summary").filter({ hasText: /[1-9][\d,]* probes/ }).waitFor();
    await page.getByTestId("chromosome-chart").locator("canvas, svg").first().waitFor();
    await page.waitForTimeout(300);
    await page.screenshot({ path: join(artifacts, "chromosome.png"), fullPage: false });
    await page.getByRole("button", { name: "All chromosomes" }).click();
    await page.getByRole("tab", { name: "Health" }).click();
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
    await page.getByRole("button", { name: "Hide health results" }).click();
    await page.getByRole("button", { name: "Show health results" }).waitFor();
    await page.getByRole("tab", { name: "All calls" }).click();
  }

  await page.getByRole("button", { name: /Synthetic female/ }).click();
  await page.getByTestId("qc-sex").filter({ hasText: "XX" }).waitFor();

  let paginationDark = null;
  for (const mode of ["light", "dark"]) {
    await page.getByLabel("Theme", { exact: true }).selectOption(mode);
    await page.waitForFunction(dark => document.documentElement.classList.contains("dark") === dark, mode === "dark");
    await page.screenshot({ path: join(artifacts, `${mode}.png`), fullPage: true });
    if (mode === "dark") {
      paginationDark = await page.evaluate(() => {
        const el = document.querySelector('[data-react-fancy-pagination] [aria-current="page"]');
        if (!el) return null;
        const s = getComputedStyle(el);
        return { background: s.backgroundColor, color: s.color, opacity: s.opacity, className: el.className };
      });
    }
  }

  // Rename, then delete both samples so the data dir ends empty.
  await page.getByRole("button", { name: "Rename" }).first().click();
  const nameInput = page.getByRole("dialog").getByLabel("Name", { exact: true });
  await nameInput.fill("Renamed synthetic");
  await page.getByRole("dialog").getByRole("button", { name: "Save" }).click();
  await page.getByRole("button", { name: /Renamed synthetic/ }).waitFor();
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
  console.log(JSON.stringify({ result: "PASS", origin, withReference, paginationDark, artifacts }, null, 2));
} finally {
  await browser.close();
}
