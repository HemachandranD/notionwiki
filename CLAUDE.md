# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

notion-wiki is a **one-way ingestion bridge** that pulls a Notion workspace into the immutable Raw Sources layer of an LLM Wiki, inspired by Karpathy's LLM Wiki (`llm_wiki.md`). Notion is the source (authored from anywhere); a background daemon pulls it, converts pages to markdown, and files them as raw source material an assistant then builds a wiki on top of. The repository is currently greenfield — it contains only the README, LICENSE, docs, and a Python-oriented .gitignore. No source code, dependency manifest, or tooling configuration exists yet.

## Design

The architecture is specified in `docs/design.md` (**v2 — one-way redesign**; the earlier bidirectional design is superseded). Three layers: **Notion** (source you edit), the **daemon** (poll → convert → write → log), and the **LLM Wiki** (a Notion-fed `Sources/` raw layer plus the agent-built wiki). Key decisions:

- **Pull-only.** Notion → local markdown, one direction. No write-back, so there is **no push, no conflict resolution, no block-level patching, no file watcher** (v1's `watchdog` dependency is dropped). The reconciliation model is entirely poll + content-hash change detection.
- **Raw layer:** pulled pages land as **flat files** in `Sources/` (Notion hierarchy kept in frontmatter, not folders); **database rows become individual source pages**; on re-pull the daemon **overwrites in place and archives the prior version** to `archive/`; deletions in Notion move the file to `archive/`. `Sources/` is **read-only to agents by convention** (stated in the generated `AGENTS.md`/`CLAUDE.md`), not daemon-enforced.
- **Logging:** `daemon_log.md` is a machine-parseable ingestion ledger (owned by the daemon), kept **separate** from the wiki's agent-owned `_log.md`.
- **Wiki layer:** follows the LLM Wiki pattern — a `_schema.md` conventions page rendered into `AGENTS.md`/`CLAUDE.md`, a generated `_index.md` (and optional `_graph.json`), and an agent-run lint pass over the wiki pages.
- **Layer separation:** the ingestion daemon does Notion→`Sources/` and nothing else. Wiki-layer bookkeeping (`_index.md`/`_graph.json` generation + the localhost:7777 force-directed graph UI) is a **separate `notion-wiki graph` command**, decoupled from Notion — not part of the ingestion daemon.
- **Ingestion runs on a schedule, not a resident process.** `notion-wiki pull` is a one-shot command; `notion-wiki service install` registers it with the OS scheduler (Task Scheduler / launchd `StartInterval` / systemd timer), default ~60 s. Each run reads its baseline from `state.db` and exits — crash-resilient by construction. A long-lived `notion-wiki daemon` mode exists only as an option (sub-minute cadence, or co-hosting the graph UI).
- **Stack & interface:** Python (uv-managed); assistants work directly on the mirror files and run the `notion-wiki` CLI (alias `nw`; subcommands `init`/`pull`/`status`/`graph`/`service`/`open` — note **no `sync`/`push`**). Importable Python module is `notion_wiki` (`src/notion_wiki/`).

Consult the design doc before adding code and keep it updated as implementation diverges.

## Current State

- The .gitignore is the standard Python template, so this is intended to be a Python project. No package manager (pip/uv/poetry/pdm) has been chosen yet.
- There are no build, lint, or test commands to run. Once project scaffolding is added (e.g., pyproject.toml, source layout, test framework), update this file with the actual commands.

## When Adding Initial Code

- Update this file with the chosen package manager, how to install dependencies, and how to run the app and tests (including a single test).
- Document the bridge architecture (Notion API integration, the pull/convert/write ingestion loop, overwrite+archive semantics) here once it takes shape, since that is the core of this project.
