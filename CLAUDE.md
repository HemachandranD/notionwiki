# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

notionwiki is a **one-way ingestion bridge** that pulls a Notion workspace into the immutable Raw Sources layer of an LLM Wiki, inspired by Karpathy's LLM Wiki (`llm_wiki.md`). Notion is the source (authored from anywhere); a background daemon pulls it, converts pages to markdown, and files them as raw source material an assistant then builds a wiki on top of. The repository is currently greenfield — it contains only the README, LICENSE, docs, and a Python-oriented .gitignore. No source code, dependency manifest, or tooling configuration exists yet.

## Design

The architecture is specified in `docs/design.md` (**v2 — one-way redesign**; the earlier bidirectional design is superseded). Three layers: **Notion** (source you edit), the **daemon** (poll → convert → write → log), and the **LLM Wiki** (a per-feeder `raw/` layer plus the agent-built `wiki/` and `outputs/`). Key decisions:

- **Pull-only.** Notion → local markdown, one direction. No write-back, so there is **no push, no conflict resolution, no block-level patching, no file watcher** (v1's `watchdog` dependency is dropped). The reconciliation model is an incremental poll (content-hash change detection) plus a periodic full reconciliation sweep (the only place deletions are detectable).
- **Wiki layout:** `raw/` (Layer 1 — one subfolder per feeder; the bridge owns `raw/notion/`, other material lands in siblings like `raw/articles/`), `wiki/` (Layer 2 — agent-built: `index.md`, `log.md`, `overview.md`, `concepts/`, `entities/`, `sources/`), `outputs/` (generated reports/answers), and root `CLAUDE.md`/`AGENTS.md` (Layer 3 — the schema configuration, agent-maintained).
- **Raw layer:** pulled pages land as **flat files** in `raw/notion/` (Notion hierarchy kept in frontmatter, not folders); **database rows become individual source pages**; on re-pull the daemon **overwrites in place and archives the prior version** to `archive/`; deletions in Notion move the file to `archive/`. All of `raw/` is **read-only to agents by convention** (stated in `AGENTS.md`/`CLAUDE.md` at the wiki root), not daemon-enforced.
- **Logging:** `raw/notion/daemon_log.md` is a machine-parseable ingestion ledger (owned by the daemon), kept **separate** from the wiki's agent-owned `wiki/log.md`.
- **Wiki layer:** follows the LLM Wiki pattern — the schema lives directly in the wiki root's `CLAUDE.md`/`AGENTS.md` (identical twins the agent maintains), a generated `wiki/index.md` (and `wiki/graph.json`), and an agent-run lint pass over the wiki pages.
- **Layer separation:** the ingestion daemon does Notion→`raw/notion/` and nothing else. Wiki-layer bookkeeping (`wiki/index.md`/`wiki/graph.json` generation + the localhost:7777 force-directed graph UI) is a **separate `notionwiki graph` command**, decoupled from Notion — not part of the ingestion daemon.
- **Ingestion runs on a schedule, not a resident process.** `notionwiki pull` is a one-shot command; `notionwiki service install` registers it with the OS scheduler (Task Scheduler / launchd `StartInterval` / systemd timer), default ~60 s. Each run reads its baseline from `state.db` and exits — crash-resilient by construction. A long-lived `notionwiki daemon` mode exists only as an option (sub-minute cadence, or co-hosting the graph UI).
- **Stack & interface:** Python (uv-managed); assistants work directly on the mirror files and run the `notionwiki` CLI (alias `nw`; subcommands `init`/`pull`/`status`/`graph`/`service`/`open` — note **no `sync`/`push`**). Importable Python module is `notion_wiki` (`src/notion_wiki/`).
- **Distribution:** two front doors to the same Python CLI — `uv tool install`/`pipx install` from PyPI, and an npm wrapper (`npm install -g notionwiki`, the README's headline install) that bootstraps a managed Python venv and execs the console script. The npm layer is `package.json` + `bin/notionwiki.js` + `scripts/bootstrap.js` + `scripts/postinstall.js`; it adds no Python behavior, only packaging.

Consult the design doc before adding code and keep it updated as implementation diverges.

## Current State

Roadmap 0.1–0.5 implemented: `src/notion_wiki/` (Notion API client, block→markdown converter,
SQLite state store, ingestion pull loop, CLI, OS scheduling, wiki graph tooling, optional daemon)
plus a full `tests/` suite (all HTTP mocked via `respx`; no live Notion workspace required).

**Package manager:** `uv`, Python ≥3.11. An npm wrapper (`package.json`, `bin/`, `scripts/`) also
ships for `npm install -g notionwiki`; it provisions a managed Python venv and execs the CLI —
edit Python for behavior, the Node shim only for packaging/bootstrap logic.

```bash
uv sync --extra graph --extra daemon   # install with optional extras (graph UI, long-lived daemon)
uv run pytest                          # run the full test suite
uv run pytest tests/test_convert_blocks.py -q          # a single test file
uv run pytest tests/test_convert_blocks.py::test_plain_paragraph  # a single test
uv run ruff check src tests            # lint
uv run notionwiki --help              # run the CLI in place (alias: `uv run nw`)
```

**Architecture (matches `docs/design.md` §12):**

- `notion/` — `NotionClient` (httpx, token-bucket rate limit + 429/5xx backoff), dataclass models
  (`Page`, `Block`, `RichText`, `DatabaseRow`), `fetch_block_tree` (recursion gated per §5.2:
  read-only islands and toggles past depth 3 are marked `truncated`, never fetched further).
- `convert/` — `blocks.py` (pure block-tree → markdown, no network; the "critical suite"),
  `assets.py` (content-hash-named downloads), `database.py` (row property tables).
- `store/` — `db.py` (SQLite `pages`/`runs`/`meta`), `lock.py` (cross-platform single-instance
  file lock: `msvcrt`/`fcntl`), `archive.py` (timestamped copy-before-overwrite).
- `ingest/` — `poller.py` (incremental search + full sweep), `writer.py` (content hashing,
  outcome decision incl. the settle window, frontmatter rendering), `daemon_log.py`
  (`daemon_log.md` ledger, parse/format/rotate), `scope.py` (`ScopeResolver` — ancestry-walk
  filter that restricts ingestion to the operator-selected `root_page_ids` and their sub-pages;
  empty selection = pull everything shared, unchanged behavior), `pull.py` (`PullRunner`
  orchestration; applies the scope filter to the page stream).
- `cli.py` — Typer app: `init` (interactive wizard), `pull`, `status`, `open`, `graph`, `lint`,
  `service install|uninstall|status`, `daemon`. Welcome banner suppressed on `--json`/`--quiet`/
  non-TTY output (§8.2). `init` uses `questionary` for real-TTY selection (masked-token feedback,
  checkbox multi-select of pages/databases with an "All" option), probing prompt_toolkit once and
  falling back to line prompts on unsupported terminals (Git Bash/mintty) and piped input.
- `schedule/` — one `Scheduler` implementation per OS (`windows.py` schtasks, `macos.py` launchd,
  `linux.py` systemd user timer + headless Secret Service detection), dispatched by
  `detect_scheduler()`.
- `graph/` — `scanner.py`/`index_gen.py`/`graph_gen.py`/`lint.py` (pure wiki-layer tooling, no
  Notion dependency) + `server.py` (FastAPI, vendored force-directed UI, `127.0.0.1:7777` only).
- `daemon.py` — optional long-lived loop (APScheduler), lazy-imported behind the `[daemon]` extra.

**Deviations from `docs/design.md` filled in during implementation** (see the plan file for full
reasoning): Notion API pinned to version `2022-06-28`; `tomli-w` added for writing `config.toml`
(§12 names `pyyaml`, which is actually for raw-file frontmatter, not config); `respx` added as a
dev-only test dependency; `questionary` added for the interactive `init` TUI; database scope
(§14.2) is resolved once at `init` time into an explicit `[[notion.databases]]` list rather than a
live "all"; **page scope** works the same way — `init` snapshots the chosen pages into
`[notion].root_page_ids` (a list; empty = all), and `ScopeResolver` enforces it at pull time via
parent-chain ancestry (the design-doc §5.1/§5.2 "page-tree walk from the root", implemented as an
ancestry filter over Search results rather than a top-down traversal). The pre-multi-select
singular `root_page_id` key is still read for back-compat.

## When Adding Code

- Keep `docs/design.md` and this file in sync as implementation diverges further (e.g. a real
  page-tree traversal for the full sweep instead of exhaustive Search, embeddings/hybrid search
  per §14.3, daemon-enforced `raw/` immutability).
- No live Notion workspace has been used against this codebase yet — `notionwiki init` and a
  first `notionwiki pull` against a real integration token are the natural next manual test.
