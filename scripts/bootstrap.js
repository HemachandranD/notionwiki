// Shared runtime bootstrap for the notionwiki npm wrapper.
//
// The npm package ships the Python source (src/, pyproject.toml, uv.lock). On first
// use we materialize a dedicated virtual environment and install the bundled Python
// package into it, then hand every invocation off to that env's `notionwiki`
// console script. `uv` is used when present (fast, can fetch a Python for you);
// otherwise we fall back to the system Python's `venv` + `pip`.
//
// No third-party Node dependencies — this must run during `npm install`.

"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");

const PACKAGE_ROOT = path.resolve(__dirname, "..");
const PKG = require(path.join(PACKAGE_ROOT, "package.json"));
const IS_WINDOWS = process.platform === "win32";

// Where the managed runtime lives. Overridable so CI / multi-user boxes can pin it.
function runtimeHome() {
  if (process.env.NOTION_WIKI_HOME) return path.resolve(process.env.NOTION_WIKI_HOME);
  return path.join(os.homedir(), ".notionwiki");
}

function venvDir() {
  return path.join(runtimeHome(), "venv");
}

// Marker records which package version + interpreter strategy provisioned the venv,
// so we reinstall automatically on upgrade instead of running stale code.
function markerFile() {
  return path.join(venvDir(), ".notionwiki-install");
}

function consoleScript(venv) {
  return IS_WINDOWS
    ? path.join(venv, "Scripts", "notionwiki.exe")
    : path.join(venv, "bin", "notionwiki");
}

function venvPython(venv) {
  return IS_WINDOWS
    ? path.join(venv, "Scripts", "python.exe")
    : path.join(venv, "bin", "python");
}

function run(cmd, args, opts = {}) {
  return spawnSync(cmd, args, { encoding: "utf8", ...opts });
}

function onPath(cmd) {
  const probe = IS_WINDOWS ? run("where", [cmd]) : run("command", ["-v", cmd], { shell: true });
  return probe.status === 0 && String(probe.stdout).trim().length > 0;
}

// Find a CPython >= 3.11 the plain-venv path can use. Tries the specific minors
// first so we don't accidentally grab a too-old default `python`.
function findSystemPython() {
  const candidates = IS_WINDOWS
    ? ["python", "python3", "py"]
    : ["python3.13", "python3.12", "python3.11", "python3", "python"];
  for (const cand of candidates) {
    if (!onPath(cand.split(" ")[0])) continue;
    const args = cand === "py" ? ["-3", "-c"] : ["-c"];
    const probe = run(cand.split(" ")[0], [
      ...(cand === "py" ? ["-3"] : []),
      "-c",
      "import sys;print('.'.join(map(str,sys.version_info[:2])))",
    ]);
    if (probe.status !== 0) continue;
    const [maj, min] = String(probe.stdout).trim().split(".").map(Number);
    if (maj === 3 && min >= 11) return cand.split(" ")[0];
    void args;
  }
  return null;
}

function alreadyInstalled(strategy) {
  try {
    const marker = JSON.parse(fs.readFileSync(markerFile(), "utf8"));
    return (
      marker.version === PKG.version &&
      marker.strategy === strategy &&
      fs.existsSync(consoleScript(venvDir()))
    );
  } catch {
    return false;
  }
}

function writeMarker(strategy) {
  fs.writeFileSync(
    markerFile(),
    JSON.stringify({ version: PKG.version, strategy, provisionedAt: new Date().toISOString() }, null, 2)
  );
}

function installWithUv(venv, log) {
  log("Provisioning Python runtime with uv…");
  const mkvenv = run("uv", ["venv", "--python", ">=3.11", venv], { stdio: "inherit" });
  if (mkvenv.status !== 0) return false;
  const install = run("uv", ["pip", "install", "--python", venvPython(venv), PACKAGE_ROOT], {
    stdio: "inherit",
  });
  return install.status === 0;
}

function installWithVenv(venv, python, log) {
  log(`Provisioning Python runtime with ${python} -m venv…`);
  const mkvenv = run(python, ["-m", "venv", venv], { stdio: "inherit" });
  if (mkvenv.status !== 0) return false;
  const py = venvPython(venv);
  run(py, ["-m", "pip", "install", "--quiet", "--upgrade", "pip"], { stdio: "inherit" });
  const install = run(py, ["-m", "pip", "install", PACKAGE_ROOT], { stdio: "inherit" });
  return install.status === 0;
}

// Ensure the managed venv exists and is current; return the console-script path.
// `quiet` suppresses progress chatter (used by postinstall so a clean install stays quiet).
function ensureRuntime({ quiet = false } = {}) {
  // Escape hatch: user points us at an existing notionwiki install.
  if (process.env.NOTION_WIKI_PYTHON) {
    return process.env.NOTION_WIKI_PYTHON;
  }

  const log = quiet ? () => {} : (msg) => process.stderr.write(`notionwiki: ${msg}\n`);
  const strategy = onPath("uv") ? "uv" : "venv";

  if (alreadyInstalled(strategy)) {
    return consoleScript(venvDir());
  }

  fs.mkdirSync(runtimeHome(), { recursive: true });
  // Rebuild from scratch on version/strategy change to avoid half-upgraded envs.
  fs.rmSync(venvDir(), { recursive: true, force: true });

  let ok = false;
  if (strategy === "uv") {
    ok = installWithUv(venvDir(), log);
  } else {
    const python = findSystemPython();
    if (!python) {
      throw new Error(
        "No Python 3.11+ found and `uv` is not installed.\n" +
          "Install uv (https://docs.astral.sh/uv/) or Python 3.11+ and re-run, " +
          "or set NOTION_WIKI_PYTHON to an existing notionwiki executable."
      );
    }
    ok = installWithVenv(venvDir(), python, log);
  }

  if (!ok || !fs.existsSync(consoleScript(venvDir()))) {
    throw new Error("Failed to provision the notionwiki Python runtime (see output above).");
  }

  writeMarker(strategy);
  log("Runtime ready.");
  return consoleScript(venvDir());
}

module.exports = { ensureRuntime, consoleScript, venvDir, runtimeHome };
