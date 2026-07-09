# notion_wiki_bridge — Design Document

**Status:** Draft v2 (one-way redesign) · 2026-07-09
**Goal:** A **one-way ingestion bridge** that pulls a Notion workspace into the immutable Raw Sources layer of an LLM Wiki. Notion is where you author and update content from anywhere; a background daemon periodically pulls it, converts it to markdown, and files it as raw source material. An assistant then builds and maintains the wiki layer on top — the "LLM Wiki" pattern (`../llm_wiki.md`), with Notion as the feeder for the raw layer.

> **v1 → v2 change.** The earlier design was a *bidirectional* mirror where Notion **was** the wiki (two-way sync, conflict resolution, block-level push, last-write-wins + backup). This redesign makes the bridge **pull-only**: Notion → markdown, one direction. That removes the entire write-back path — no push, no conflict resolution, no block-level patching, no `conflicts/`. The daemon becomes a simple *poll → convert → write → log* loop.

---

## 1. The three layers

Per `prompt.md`, the system is three layers, each with a clear owner and mutability:

| Layer | What it is | Owner | Mutability |
|---|---|---|---|
| **Notion** (source) | Where you keep and update data — articles, pages, database rows — authored from anywhere remotely | You | You edit freely in Notion |
| **Bridge Daemon** | Periodically pulls Notion, converts to markdown, files into the Raw Sources layer, records each pull in `daemon_log.md` | The bridge | — |
| **LLM Wiki** | The Raw Sources folder (Notion-fed, immutable) + the agent-built wiki (summaries, entity/concept pages, syntheses) | Daemon writes `Sources/`; agent owns the rest | See §4 |

The key reframe: **Notion is not the wiki — Notion feeds the wiki's raw-source layer.** The wiki itself is built locally by an assistant reading those raw sources, exactly as in the LLM Wiki pattern.

## 2. Decisions (settled)

| Question | Decision |
|---|---|
| Direction | **One-way pull only** (Notion → local markdown). No write-back to Notion. |
| Notion's role | **One feeder among many** — `Sources/` also accepts non-Notion raw material (clipped articles, PDFs, transcripts) dropped in by you or an agent. |
| Re-pull on Notion edit/delete | **Overwrite + archive prior** — `Sources/` stays a clean mirror of current Notion state; each replaced/removed version is archived, never silently lost. |
| Hierarchy mapping | **Flat files + frontmatter breadcrumb** — no nested folders; Notion's tree is recorded in frontmatter, not the filesystem. |
| Databases | **Rows as pages** — each database row (itself a Notion page) becomes its own source `.md` file. |
| Raw-layer immutability | **Convention only** — `CLAUDE.md`/`AGENTS.md` instructs agents never to edit `Sources/`; not daemon-enforced. |
| Logging | **Separate logs** — `daemon_log.md` (ingestion events) is distinct from the wiki's `_log.md` (agent operations). |
| Stack | **Python** (httpx, APScheduler; optional FastAPI for the graph UI). uv-managed, Python ≥3.11. |
| Agent interface | **Plain files + a small CLI** — assistants read the mirror directly; no MCP server. |

## 3. Architecture

```mermaid
flowchart LR
    NOTION[(Notion API)]

    subgraph Daemon["nwb daemon — ingestion only (always running)"]
        POLL[Poller<br/>APScheduler]
        CONV[Converter<br/>blocks → markdown]
        WRITE[Writer<br/>overwrite + archive]
        LOG[daemon_log.md]
    end

    subgraph Wiki["LLM Wiki (local folder)"]
        SRC[Sources/ — raw layer<br/>immutable to agents]
        WK[wiki pages<br/>agent-owned]
        IDX[_index.md · _graph.json]
    end

    subgraph WikiTooling["nwb graph — wiki layer (on demand)"]
        GEN[Index / graph generator<br/>scans wiki *.md]
        API[Graph UI<br/>localhost:7777]
    end

    subgraph Assistants
        CC[Claude Code]
        CU[Cursor]
        CX[Codex]
    end

    NOTION -->|poll last_edited_time| POLL
    POLL --> CONV --> WRITE --> SRC
    WRITE --> LOG
    WRITE -->|ingestion state| DBSTATE[(state.db)]
    SRC -.read-only.-> CC & CU & CX
    CC & CU & CX -->|read / grep / write| WK
    WK --> GEN --> IDX
    GEN --> API
```

**Two independent concerns, deliberately separated:**

1. **The ingestion daemon** owns exactly one direction — Notion → `Sources/` — and nothing else. It never reads agent edits, never touches the wiki pages, and knows nothing about the graph. Its only state is `state.db` (ingestion bookkeeping: `notion_id`, hashes, pull timestamps) and `daemon_log.md`.
2. **The wiki tooling** (`nwb graph`, §9) is a **wiki-layer** concern: it scans the agent-built wiki `*.md`, generates `_index.md`/`_graph.json`, and serves the force-directed graph at localhost:7777. It has no dependency on Notion — you could feed `Sources/` from something other than Notion and the wiki tooling would work unchanged.

Assistants read `Sources/` (by convention, never write it) and build/maintain the wiki layer beside it with their native file tools. Conventions load automatically via `AGENTS.md`/`CLAUDE.md` at the wiki root.

Because there is no write-back, there is **no watcher, no write queue, no conflict path** — the agent's edits to the wiki layer are simply local files the daemon does not touch.

## 4. Local layout

```
~/.notion-wiki-bridge/           (configurable, XDG-aware)
├── config.toml
├── wiki/                        ← the LLM Wiki root
│   ├── _schema.md               ← conventions page (rendered to AGENTS.md/CLAUDE.md, §7)
│   ├── AGENTS.md / CLAUDE.md    ← generated from _schema.md; auto-loaded by assistants
│   ├── _index.md                ← generated catalog of wiki pages (nwb graph, §7)
│   ├── _graph.json              ← generated link graph (nwb graph, §9)
│   ├── daemon_log.md            ← ingestion ledger (ingestion daemon, §6)
│   ├── _log.md                  ← wiki operations timeline (agent-owned narrative)
│   ├── Sources/                 ← RAW LAYER — Notion-fed, immutable to agents (§5)
│   │   ├── bridge-design.md
│   │   ├── karpathy-llm-wiki.md
│   │   └── ...                  ← flat; hierarchy lives in frontmatter
│   ├── Home.md                  ← agent-built wiki pages
│   ├── Concepts/
│   └── ...
├── state.db                     ← SQLite index
└── archive/                     ← replaced/removed raw versions, timestamped (§5.3)
    └── 2026-07-09T14-03_bridge-design.md
```

- **`Sources/` is flat.** Every pulled Notion page — regular page, subpage, or database row — becomes one `.md` file directly under `Sources/`. Notion's nesting is preserved in frontmatter (`parent`, `breadcrumb`), not as folders, so a Notion move/rename never churns the filesystem.
- **Filenames** come from page titles (slugified, deduplicated with a short Notion-ID suffix on collision). The stable identity is `notion_id` in frontmatter, not the filename.
- Names starting with `_` and the `daemon_log.md` file are reserved for the bridge. The `Sources/` folder is reserved for the raw layer.

### File format (a pulled source)

```markdown
---
notion_id: 1a2b3c4d-....
notion_url: https://notion.so/...
source: notion                    # feeder tag; other raw sources use their own value
kind: page                        # page | database_row
database: Reading Notes           # present only for database rows
parent: 9f8e7d6c-....             # Notion parent id (breadcrumb reconstruction)
breadcrumb: ["Home", "Projects"]  # human-readable path in Notion
last_pulled: 2026-07-09T14:03:11Z
remote_edited_at: 2026-07-09T14:01:00Z
content_hash: sha256:...          # of normalized markdown; drives change detection
---

# Bridge Design

Raw content converted from Notion. Agents read this; they never edit it.
```

All frontmatter here is **bridge-owned** — agents don't touch source files at all. The agent-owned LLM-Wiki metadata (`type`, `description`, `tags`, `sources:`) lives on the *wiki* pages the agent creates, which cite these raw files via `sources: ["[[Sources/bridge-design]]"]`.

## 5. Ingestion engine

### 5.1 Change detection (pull)

- Poll the Notion **Search API** scoped to the shared wiki root, sorted by `last_edited_time`; for each page compare `remote_edited_at` against the stored value, then compare `content_hash` of the freshly converted markdown to decide whether anything actually changed.
- Default interval **60 s**, configurable. `nwb pull` forces an immediate cycle.
- Respect Notion's ~3 req/s average rate limit with a token-bucket limiter and exponential backoff on 429.

> ⚠ **Known constraint:** Notion's `last_edited_time` has **minute granularity**. The engine never trusts timestamps alone for "did it change" — it compares `content_hash`. Timestamps only order confirmed changes.

Because the bridge is pull-only, this is the *entire* reconciliation model — there is no local-change detection and no merge.

### 5.2 Content conversion

Notion pages are block trees; the raw layer is markdown. The converter is bridge-owned (existing libraries like `notion2md` don't convert reliably enough):

- **Converted cleanly:** paragraphs, headings, bulleted/numbered/todo lists, code blocks, quotes, dividers, images (downloaded to an `assets/` sibling), bold/italic/strikethrough/inline code, links, page mentions.
- **Read-only islands** (synced blocks, embeds, columns, deeply nested toggles) render as a labeled fenced placeholder so the agent knows something exists but isn't fully captured:

  ````markdown
  ```notion-block id=abc123 type=embed
  🔗 Figma embed — view in Notion
  ```
  ````

  Since nothing is pushed back, placeholders are purely informational — there is no round-trip requirement to preserve.

**Databases → rows as pages.** For each database in scope, the daemon enumerates its rows (each a Notion page), converts each row to its own `Sources/*.md` with `kind: database_row` and `database: <name>`, and includes the row's properties as a small frontmatter/property table plus the page body. A database with 40 rows yields 40 source files, each independently citable by the wiki layer.

### 5.3 Re-pull, overwrite + archive, deletions

On each tick, for every in-scope Notion page:

- **New** (unknown `notion_id`) → write a fresh `Sources/*.md`; log `new`.
- **Updated** (`content_hash` changed) → **archive the current file** to `archive/<timestamp>_<slug>.md` (with its frontmatter intact), then overwrite `Sources/*.md` with the new content; log `updated`.
- **Unchanged** → no write; not logged (or logged at debug level only).
- **Deleted/trashed in Notion** → move the local file to `archive/<timestamp>_<slug>.md` and remove it from `Sources/`; log `archived`. The bridge never hard-deletes.

`Sources/` therefore always reflects **current** Notion state, while `archive/` preserves every prior version for provenance and recovery.

## 6. `daemon_log.md` — the ingestion ledger

Distinct from the wiki's `_log.md` (a human-narrative timeline the agent maintains), `daemon_log.md` is a **machine-parseable, append-only ledger** the daemon owns. Following the `llm_wiki.md` tip about consistent prefixes, every line starts with `## [ISO-8601]` so simple tooling works without parsing prose:

```
## [2026-07-09T14:03:11Z] pull  | 1a2b3c4d | Bridge Design        | updated  | 12 blocks | archived→2026-07-09T14-03_bridge-design.md
## [2026-07-09T14:03:12Z] pull  | 5e6f7a8b | Reading Notes / Row 4 | new      | 6 blocks
## [2026-07-09T14:03:12Z] pull  | 9c0d1e2f | Old Draft            | archived | deleted in Notion
## [2026-07-09T14:03:13Z] error | 3a4b5c6d | Weekly Sync          | convert  | unsupported block: unsupported_type
```

- Fixed columns: `timestamp | action | notion_id | title | outcome | detail`.
- Actions: `pull` (with outcome `new|updated|archived|unchanged`) and `error` (outcome names the failing stage: `fetch|convert|write`).
- Greppable: `grep "^## \[" daemon_log.md | tail -20` for recent activity; `grep "| error " daemon_log.md` for failures — the same data `nwb status` reads.

**Suggested improvement over a plain `log.md`:** because errors are first-class rows (not buried in prose), `nwb status` can surface "3 pages failed to convert since last clean run" deterministically, and a failed pull never blocks the rest of the batch.

## 7. Knowledge conventions (the LLM Wiki layer)

The bridge feeds the raw layer; an assistant builds the wiki. Conventions come from the LLM Wiki pattern (`../llm_wiki.md`), unchanged in spirit — **deterministic bookkeeping to scripts, judgment to the LLM.**

- **`_schema.md`** — a normal wiki page defining page types (`concept`, `entity`, `source-summary`, `comparison`), new-page-vs-edit-in-place rules, and the compression rule (a wiki page larger than its source has negative value). On each tick the daemon renders it into **`AGENTS.md` and `CLAUDE.md`** at the wiki root, with a preamble covering: the mirror layout, the reserved `_` files, **the rule that `Sources/` is read-only**, and the `nwb` CLI. Codex/Cursor auto-load `AGENTS.md`; Claude Code auto-loads `CLAUDE.md`.
- **`_index.md`** — generated catalog of the *wiki* pages (grouped by `type`, one `description` line each), regenerated by `nwb graph` (§9) by scanning the wiki `*.md` — **not** by the ingestion daemon. The agent's first read on any query: index → drill into ~10 pages → answer. Keeps retrieval cheap without embeddings at moderate scale (grep covers keyword search).
- **`_graph.json`** — the wiki link graph as plain nodes/edges/backlink-counts, generated by the same `nwb graph` pass, for topology reasoning and the graph UI.

Both are **wiki-layer** artifacts derived from the agent's pages; the Notion ingestion daemon never generates or reads them.
- **`_log.md`** — the agent's narrative wiki timeline (ingest/query/lint), separate from `daemon_log.md`.

**Immutability of `Sources/` is by convention:** the generated `AGENTS.md`/`CLAUDE.md` state plainly that agents read `Sources/` and cite it via `sources:` frontmatter but never edit it. Not enforced by the daemon (accepted for v1).

**Lint (agent-run).** Since the bridge no longer generates a sync-drift report, wiki health is the agent's `nwb lint`-style pass over the *wiki* layer: orphan pages, dangling `[[links]]`, pages missing `description`/`type`, compression violations. Detection can be scripted; fixing is judgment.

## 8. Agent interface: files + CLI

No agent-facing server. The contract is the wiki directory plus a small CLI.

**Files**

| Agent need | How it's met |
|---|---|
| Read raw material | Read `Sources/*.md` (read-only); cite via `sources: [[Sources/...]]` |
| Orient / retrieve | Read `_index.md`, drill into ~10 wiki pages; grep/glob for keywords |
| Write / create | Ordinary file edits under the schema's rules — **outside `Sources/`** |
| Ingestion history | `daemon_log.md` (what was pulled, when, errors) |
| Conventions | `AGENTS.md` / `CLAUDE.md` at the wiki root |

**CLI**

| Command | Purpose |
|---|---|
| `nwb init` | Scaffold the wiki root, seed `_schema.md`, store the Notion token |
| `nwb pull` | Force an immediate pull/convert/write cycle (background ticks handle it otherwise) — *ingestion* |
| `nwb status` | Ingestion health, last pull time, recent errors (reads `daemon_log.md`) — *ingestion* |
| `nwb graph` | Regenerate `_index.md`/`_graph.json` from the wiki pages and serve the graph UI at localhost:7777 — *wiki layer* (§9) |
| `nwb open <page>` | Print the Notion URL / local path for a source |

Two intentional omissions: **no `nwb sync`/`push`** (the bridge never writes to Notion), and the graph/index generation lives under `nwb graph`, **not** the ingestion daemon (§3).

## 9. Wiki tooling: index + graph UI (`nwb graph`)

This is a **wiki-layer** concern, fully decoupled from Notion ingestion (§3). `nwb graph`:

1. Scans the agent-built wiki `*.md` (everything under the wiki root except `Sources/` and reserved `_` files), parsing `[[links]]` and frontmatter (`type`, `description`).
2. Regenerates `_index.md` (catalog) and `_graph.json` (nodes/edges/backlink counts).
3. Serves `http://localhost:7777/graph` — FastAPI + a vendored force-directed library (no CDN, works offline), a *read-only* view sized by backlink count and colored by section/tag. Bound to `127.0.0.1` only.

It has **no dependency on Notion, `state.db`, or the ingestion daemon** — it works purely off the local wiki files, so it functions identically for non-Notion sources. It can run on demand, or as a long-lived server that regenerates on a timer or when the wiki files change. Optional and can ship after the ingestion path is solid.

## 10. Always-running service (Windows / macOS / Linux)

`nwb service install|uninstall|status` — one long-lived daemon per OS:

| OS | Mechanism |
|---|---|
| Windows | **Task Scheduler** task, trigger *At log on*, run `pythonw -m nwb daemon`, restart on failure (no admin needed) |
| macOS | **launchd** user LaunchAgent, `KeepAlive=true` |
| Linux | **systemd user unit**, `Restart=on-failure` |

Crash-only design: all state is in SQLite + files, so restart is always safe; startup runs one reconciliation pull.

## 11. Security

- Notion **internal integration token**, stored in the OS keychain via `keyring` (env-var override for headless setups); never in `config.toml`.
- The integration is shared **only with the wiki root page** — Notion's permission model enforces the pull scope.
- The only HTTP surface is the optional graph UI, bound to localhost.

## 12. Project structure & tooling

```
notion_wiki_bridge/
├── pyproject.toml              # uv-managed; Python ≥3.11
├── src/nwb/
│   ├── cli.py                  # nwb init | daemon | pull | status | service ...
│   ├── daemon.py               # poll loop composition
│   ├── notion/                 # API client (httpx), rate limiter, models
│   ├── convert/                # blocks → markdown, database rows → pages
│   ├── ingest/                 # poller, change detection, overwrite+archive writer
│   ├── store/                  # SQLite state, source file I/O, archive
│   └── web/                    # optional FastAPI graph UI
└── tests/                      # pytest; block→markdown conversion is the critical suite
```

Key dependencies: `httpx`, `apscheduler`, `keyring`, `pyyaml`, `typer`; `fastapi`+`uvicorn` only if the graph UI ships. Tooling: `uv`, `ruff`, `pytest`. Note the dropped v1 dependency on `watchdog` — there is no file watcher.

## 13. Roadmap

| Phase | Deliverable | Proves |
|---|---|---|
| **0.1** | `nwb init` + one-way pull of Notion pages/subpages → flat `Sources/*.md` + `daemon_log.md` | Auth, traversal, block→markdown conversion |
| **0.2** | Database rows → source pages; overwrite + archive on re-pull; deletion → archive | Full raw-layer fidelity to current Notion state |
| **0.3** | `_schema.md` → `AGENTS.md`/`CLAUDE.md` rendering; `_index.md`; assistants pointed at the folder | The agent-builds-the-wiki experience |
| **0.4** | `nwb service install` on all three OSes; `nwb status`; hardening, backoff | Always-running reliability |
| **0.5** | Optional graph UI + `_graph.json`; agent-run lint over the wiki layer | The visible graph + wiki health |
| v2 ideas | Webhook-mode pulls via tunnel (near-instant), embeddings/hybrid search, daemon-enforced `Sources/` immutability, **optional write-back** if bidirectionality is ever wanted again | — |

## 14. Open questions (non-blocking)

1. **Attachment churn** — re-downloading images on every content change is wasteful; mitigate with a content-hash asset cache keyed on the Notion file URL.
2. **Database scope selection** — which databases to pull (all shared, or an allowlist in `config.toml`)? Large databases could flood `Sources/`; consider a per-database row cap or filter.
3. **Search at scale** — agent grep + `_index.md` should carry a personal wiki far; revisit hybrid search (BM25 + embeddings) if it outgrows that.
4. **Slug stability** — title-derived slugs change when a Notion page is renamed; the `notion_id` is the stable key, but citing `[[Sources/<slug>]]` links could break. Options: keep filenames stable after first pull, or rewrite inbound citations on rename (agent-side).
