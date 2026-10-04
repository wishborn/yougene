// Both dev servers must be running. Artifacts contain only invented smoke data.
import { chromium } from "@playwright/test";
import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

const artifacts = join(tmpdir(), "yougene-p0-smoke");
const offline = process.argv.includes("--offline");
const origin = process.env.YOUGENE_SMOKE_URL || "http://127.0.0.1:5180";
await mkdir(artifacts, { recursive: true });
// Automated checks use the site's localOrigin; .gen routing is owned by Genie.
const browser = await chromium.launch();
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1100 }, colorScheme: "light" });
  const page = await context.newPage();
  if (offline) {
    await page.route("**/api/health", route => route.fulfill({
      status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok", version: "0.1.0" }),
    }));
  }
  const errors = [];
  const external = [];
  page.on("pageerror", error => errors.push(error.message));
  page.on("console", message => { if (message.type() === "error") errors.push(message.text()); });
  page.on("request", request => {
    const url = new URL(request.url());
    if (!["yougene.gen", "127.0.0.1", "localhost"].includes(url.hostname) && ["http:", "https:"].includes(url.protocol)) {
      external.push(request.url());
    }
  });
  await page.goto(origin);
  await page.getByTestId("health-status").filter({ hasText: "ok · v0.1.0" }).waitFor();
  assert.equal(await page.getByRole("heading", { name: "Kit smoke page", exact: true }).count(), 1);
  assert.equal(await page.locator('[data-fancy-grid-row]').count(), 50);
  await page.getByTestId("probe-chart").locator("svg").waitFor();
  const header = page.getByRole("columnheader", { name: /Synthetic probe/ });
  await header.click();
  const firstAscending = await page.locator('[data-fancy-grid-row]').first().innerText();
  await header.click();
  const firstDescending = await page.locator('[data-fancy-grid-row]').first().innerText();
  assert.match(firstAscending, /demo-01/);
  assert.match(firstDescending, /demo-50/);

  const styles = [];
  for (const mode of ["light", "dark"]) {
    await page.getByLabel("Theme", { exact: true }).selectOption(mode);
    await page.waitForFunction(dark => document.documentElement.classList.contains("dark") === dark, mode === "dark");
    // The SVG is recreated when ECharts' theme changes.
    await page.getByTestId("probe-chart").locator("svg").waitFor();
    await page.waitForFunction(expected =>
      [...document.querySelectorAll('[data-testid="probe-chart"] svg path')]
        .some(path => path.getAttribute("fill") === expected), mode === "dark" ? "#a7b8ff" : "#5266bd");
    const computed = await page.locator("#root > div").evaluate(element => {
      const style = getComputedStyle(element);
      return { background: style.backgroundColor, color: style.color,
        brand: getComputedStyle(document.documentElement).getPropertyValue("--color-brand").trim() };
    });
    assert.equal(computed.brand, "#5266bd");
    assert.notEqual(computed.background, "rgba(0, 0, 0, 0)");
    styles.push({ mode, ...computed });
    await page.screenshot({ path: join(artifacts, `${mode}.png`), fullPage: true });
  }
  assert.notEqual(styles[0].background, styles[1].background);
  await page.getByLabel("Theme", { exact: true }).selectOption("system");
  await page.emulateMedia({ colorScheme: "dark" });
  await page.waitForFunction(() => document.documentElement.classList.contains("dark"));
  await page.emulateMedia({ colorScheme: "light" });
  await page.waitForFunction(() => !document.documentElement.classList.contains("dark"));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("heading", { name: "Kit smoke page", exact: true }).waitFor();
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
  await page.screenshot({ path: join(artifacts, "mobile.png"), fullPage: true });
  assert.deepEqual(external, [], "Smoke page requested external resources");
  assert.deepEqual(errors, [], "Browser errors");
  console.log(JSON.stringify({ result: "PASS", origin, health: offline ? "MOCKED (UI only)" : "LIVE proxy PASS", rows: 50, themes: styles, sorting: "PASS", systemTheme: "PASS", mobile: "PASS", externalRequests: external.length, browserErrors: errors.length, artifacts }, null, 2));
} finally {
  await browser.close();
}
