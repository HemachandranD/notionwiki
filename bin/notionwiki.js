#!/usr/bin/env node
// npm `bin` shim for both `notionwiki` and `nw`.
//
// Ensures the managed Python runtime exists (bootstrapping on first run if the
// postinstall step was skipped, e.g. `--ignore-scripts`), then execs the real
// Python CLI with every argument passed straight through.

"use strict";

const { spawnSync } = require("child_process");
const { ensureRuntime } = require("../scripts/bootstrap.js");

let executable;
try {
  executable = ensureRuntime();
} catch (err) {
  process.stderr.write(`notionwiki: ${err.message}\n`);
  process.exit(1);
}

const result = spawnSync(executable, process.argv.slice(2), { stdio: "inherit" });

if (result.error) {
  process.stderr.write(`notionwiki: failed to launch runtime: ${result.error.message}\n`);
  process.exit(1);
}
process.exit(result.status === null ? 1 : result.status);
