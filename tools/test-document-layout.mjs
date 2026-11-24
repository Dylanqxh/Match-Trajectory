import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const stylesheet = path.join(root, "web", "src", "styles.css");
const markup = `
  <div class="app-shell workbench-open">
    <aside class="sidebar"></aside>
    <main class="main-area">
      <div class="canvas">
        <div class="editor-grid document-view-split">
          <section class="document-left-pane">
            <aside class="document-workspace-controls">视图控制</aside>
            <section class="editor-panel">
              <div class="resume-editor-workspace">
                <nav class="editor-section-nav"><button>基本信息</button></nav>
                <div class="editor-section-content"><label>姓名<input value="林然"></label></div>
              </div>
            </section>
          </section>
          <section class="preview-panel"><div class="preview-sheet"></div></section>
        </div>
      </div>
    </main>
    <aside class="agent-rail collapsed"></aside>
  </div>`;

async function metrics(page) {
  return page.evaluate(() => {
    const rect = (selector) => {
      const element = document.querySelector(selector);
      if (!element) throw new Error(`Missing ${selector}`);
      const box = element.getBoundingClientRect();
      return { x: box.x, y: box.y, width: box.width, height: box.height };
    };
    const grid = document.querySelector(".editor-grid");
    return {
      grid: rect(".editor-grid"),
      left: rect(".document-left-pane"),
      editor: rect(".editor-panel"),
      preview: rect(".preview-panel"),
      editorDisplay: getComputedStyle(document.querySelector(".editor-panel")).display,
      previewDisplay: getComputedStyle(document.querySelector(".preview-panel")).display,
      overflow: grid.scrollWidth - grid.clientWidth,
    };
  });
}

const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1234, height: 923 } });
  await page.setContent(markup);
  await page.addStyleTag({ path: stylesheet });

  const desktop = await metrics(page);
  assert.ok(desktop.left.width >= 400, `split editor width ${desktop.left.width}px is below 400px`);
  assert.ok(desktop.preview.width >= 430, `split preview width ${desktop.preview.width}px is below 430px`);
  assert.equal(desktop.editorDisplay, "block");
  assert.equal(desktop.previewDisplay, "flex");

  await page.locator(".editor-grid").evaluate(element => {
    element.className = "editor-grid document-view-preview";
  });
  const focusedPreview = await metrics(page);
  assert.equal(focusedPreview.editorDisplay, "none");
  assert.equal(focusedPreview.previewDisplay, "flex");

  await page.locator(".editor-grid").evaluate(element => {
    element.className = "editor-grid document-view-edit";
  });
  const focusedEdit = await metrics(page);
  assert.equal(focusedEdit.editorDisplay, "block");
  assert.equal(focusedEdit.previewDisplay, "none");

  await page.locator(".editor-grid").evaluate(element => {
    element.className = "editor-grid document-view-split";
  });
  await page.setViewportSize({ width: 1180, height: 923 });
  const constrained = await metrics(page);
  assert.ok(constrained.preview.y >= constrained.left.y + constrained.left.height - 1,
    `1180px viewport still overlaps split columns at y=${constrained.preview.y}`);
  assert.ok(constrained.overflow <= 1, `single-column workspace overflows by ${constrained.overflow}px`);

  console.log("document layout checks passed");
} finally {
  await browser.close();
}
