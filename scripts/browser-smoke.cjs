/* Optional developer check. Run the Python app first, then `node scripts/browser-smoke.cjs`. */
"use strict";
const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const path = require("node:path");
const fs = require("node:fs/promises");
const { existsSync } = require("node:fs");
const { execFileSync } = require("node:child_process");

(async () => {
  const root = path.resolve(__dirname, "..");
  const output = path.join(root, "test-results");
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.BROWSER_EXECUTABLE
      ? { executablePath: process.env.BROWSER_EXECUTABLE }
      : {}),
  });
  try {
    const context = await browser.newContext({
      viewport: { width: 1440, height: 1100 },
      locale: "en-US",
      reducedMotion: "reduce",
    });
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    const base = process.env.BASE_URL || "http://127.0.0.1:8000";
    await page.goto(base);
    assert.equal(await page.locator("#export-button").isDisabled(), true);
    await page.screenshot({
      path: path.join(output, "upload.png"),
      fullPage: true,
    });
    await page
      .locator("#file-input")
      .setInputFiles(path.join(root, "sales_dashboard/data/sample_sales.csv"));
    await page.waitForFunction(
      () => document.querySelector("#m-orders").textContent === "576",
    );
    assert.equal(await page.locator("#m-revenue").textContent(), "$166,917.00");
    assert.equal(await page.locator("#q-clean").textContent(), "576");
    assert.equal(await page.locator("#q-invalid").textContent(), "8");
    await page.locator("#quality-toggle").click();
    assert.equal(await page.locator("#quality-details").isVisible(), true);
    await page.locator("#quality-toggle").click();
    await page.locator("#next-page").click();
    assert.equal(await page.locator("#page-number").textContent(), "2 / 10");
    await page.locator("#previous-page").click();
    await page.locator("#start-date").fill("2026-03-01");
    await page.locator("#end-date").fill("2026-03-31");
    await page.locator("#region-filter").selectOption("Europe");
    await page.getByRole("button", { name: "Apply", exact: true }).click();
    await page.waitForFunction(
      () => document.querySelector("#m-revenue").textContent === "$7,487.00",
    );
    // Unapplied form edits must not change the PDF's applied selection.
    await page.locator("#start-date").fill("2027-01-01");
    const downloadWait = page.waitForEvent("download");
    await page.locator("#export-button").click();
    const download = await downloadWait;
    await download.saveAs(path.join(output, "filtered-report.pdf"));
    assert.equal(
      (await fs.readFile(path.join(output, "filtered-report.pdf")))
        .subarray(0, 5)
        .toString(),
      "%PDF-",
    );
    const venvPython = path.join(
      root,
      process.platform === "win32"
        ? ".venv/Scripts/python.exe"
        : ".venv/bin/python",
    );
    const python =
      process.env.PYTHON_EXECUTABLE ||
      (existsSync(venvPython) ? venvPython : "python");
    const reportText = execFileSync(
      python,
      [
        "-c",
        'import sys; from pypdf import PdfReader; print("\\n".join(p.extract_text() for p in PdfReader(sys.argv[1]).pages))',
        path.join(output, "filtered-report.pdf"),
      ],
      { encoding: "utf8", env: { ...process.env, PYTHONIOENCODING: "utf-8" } },
    );
    assert.ok(
      reportText.includes("USD 7,487.00"),
      "Downloaded PDF must match the filtered metric",
    );
    assert.ok(
      reportText.includes("2026-03-01"),
      "Downloaded PDF must include the applied March start date",
    );
    assert.ok(
      !reportText.includes("2027-01-01"),
      "Downloaded PDF must exclude the unapplied date",
    );
    await page.locator("#end-date").fill("2027-12-31");
    await page.getByRole("button", { name: "Apply", exact: true }).click();
    await page.locator("#no-results").waitFor({ state: "visible" });
    assert.equal(await page.locator("#export-button").isDisabled(), true);
    await page.locator("#reset-filters").click();
    await page.waitForFunction(
      () => document.querySelector("#m-orders").textContent === "576",
    );
    // Failed replacement preserves the previous valid dataset.
    await page
      .locator("#file-input")
      .setInputFiles({
        name: "broken.csv",
        mimeType: "text/csv",
        buffer: Buffer.from("bad,headers\n1,2"),
      });
    await page.locator("#alert").waitFor({ state: "visible" });
    assert.match(
      await page.locator("#alert").textContent(),
      /Missing required/,
    );
    assert.equal(await page.locator("#m-orders").textContent(), "576");
    // User-provided cells are rendered as text, not HTML.
    const xss =
      "date,product,quantity,unit_price\n2026-01-01,<img src=x onerror=alert(1)>,1,1";
    await page
      .locator("#file-input")
      .setInputFiles({
        name: "text.csv",
        mimeType: "text/csv",
        buffer: Buffer.from(xss),
      });
    await page.waitForFunction(
      () => document.querySelector("#m-orders").textContent === "1",
    );
    assert.equal(await page.locator("#preview-body img").count(), 0);
    assert.match(await page.locator("#preview-body").textContent(), /<img/);
    await page.reload();
    await page.locator("#sample-button").click();
    await page.waitForFunction(
      () => document.querySelector("#m-orders").textContent === "576",
    );
    await page.locator("#toast").waitFor({ state: "hidden" });
    await page.screenshot({
      path: path.join(output, "dashboard.png"),
      fullPage: true,
    });
    for (const width of [375, 768, 1024, 1440]) {
      await page.setViewportSize({ width, height: 900 });
      assert.equal(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
        true,
        `overflow at ${width}px`,
      );
    }
    await page.setViewportSize({ width: 375, height: 812 });
    await page.screenshot({
      path: path.join(output, "mobile.png"),
      fullPage: true,
    });
    await page
      .locator(".guide-button")
      .first()
      .click({ force: true })
      .catch(async () => {
        await page.setViewportSize({ width: 1440, height: 1100 });
        await page.locator(".guide-button").first().click();
      });
    assert.equal(await page.locator("#help-dialog").isVisible(), true);
    await page.keyboard.press("Escape");
    assert.equal(await page.locator("#help-dialog").isVisible(), false);
    assert.deepEqual(errors, []);
    console.log(
      "PASS: upload, sample, cleaning, metrics, pagination, filters, PDF download, empty state, recovery, HTML escaping, responsive layout and keyboard dialog.",
    );
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
