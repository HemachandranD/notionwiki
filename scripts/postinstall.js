#!/usr/bin/env node
// Runs on `npm install`. Best-effort: provision the Python runtime up front so the
// first `notionwiki` call is instant. If it fails (offline, no Python/uv yet), we
// stay silent-ish and let the bin shim retry on first run with a clear error —
// a failed postinstall must not abort the whole `npm install`.

"use strict";

// Honor the usual opt-outs for CI / air-gapped installs.
if (process.env.NOTION_WIKI_SKIP_BOOTSTRAP || process.env.NOTION_WIKI_PYTHON) {
  process.exit(0);
}

try {
  const { ensureRuntime } = require("./bootstrap.js");
  ensureRuntime({ quiet: false });
} catch (err) {
  process.stderr.write(
    `notionwiki: runtime will be provisioned on first run (${err.message})\n`
  );
}
process.exit(0);
