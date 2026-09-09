import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";

test("renders the SnowTV application shell", async () => {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  const response = await worker.fetch(
    new Request("http://localhost/", {
      headers: { accept: "text/html" },
    }),
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );

  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);
  const html = await response.text();
  assert.match(html, /SnowTV/i);
  assert.doesNotMatch(html, /codex-preview/i);
});

test("ships rerender overrides and professional caption controls", async () => {
  const source = await readFile(new URL("../app/studio.tsx", import.meta.url), "utf8");
  assert.match(source, /const options = \{ \.\.\.processingOptions\(\), \.\.\.extraOptions \};/);
  assert.match(source, /clipOverrides: \[\{ index, start, end, title \}\]/);
  assert.match(source, /caption-live-preview/);
  assert.match(source, /snowtv_caption_presets/);
  assert.match(source, /\/cancel`/);
  assert.match(source, /\/resume`/);
});
