# notionwiki

A one-way bridge that pulls your Notion workspace into the immutable Raw Sources layer of an LLM Wiki, so an assistant can build and maintain a compounding knowledge base on top. Inspired by [LLM Wiki](llm_wiki.md).

Notion stays the source of truth — you author from anywhere. A scheduled job polls the workspace, converts pages to markdown, and files them as raw source material under `raw/notion/`. There is no write-back: no push, no conflict resolution, no file watcher.

## Install

```bash
npm install -g notionwiki
```

<sub>Also works with `pnpm add -g notionwiki` or `bun install -g notionwiki`.</sub>

The npm package is a thin wrapper: on first run it provisions a self-contained Python runtime (via [`uv`](https://docs.astral.sh/uv/) if present, otherwise your system Python ≥ 3.11) and installs the CLI into it. You get a global `notionwiki` command (alias `nw`) with no manual Python setup.

<details>
<summary>Prefer to install straight from Python?</summary>

```bash
uv tool install notionwiki      # or: pipx install notionwiki
```

Both give you the same global `notionwiki` / `nw` commands.
</details>

## Quickstart

```bash
notionwiki init     # interactive setup: Notion token, database scope, wiki path
notionwiki pull     # one-shot ingestion run
notionwiki status   # summary of the last run
```

Then schedule it so the wiki stays fresh:

```bash
notionwiki service install   # registers `pull` with your OS scheduler (~60s cadence)
```

## Commands

`notionwiki` (alias `nw`):

| Command | What it does |
| --- | --- |
| `init` | Interactive setup wizard (Notion token, database scope, wiki path). |
| `pull` | One-shot ingestion run. `--full` forces a full reconciliation sweep; `--json` for machine-readable output. |
| `status` | Summary of the last run (`--json`). |
| `open <query>` | Look up a raw page by filename, slug, or title substring. |
| `graph` | Generate `wiki/index.md` / `wiki/graph.json`. `--serve` hosts the force-directed graph UI at `127.0.0.1:7777` — pan/zoom/drag nodes, and click one to open a drawer with the rendered wiki page plus "Open in Notion" links back to its raw sources. |
| `lint` | Lint pass over the wiki pages. |
| `service install \| uninstall \| status` | Register/remove `pull` with the OS scheduler (Task Scheduler / launchd / systemd timer). |
| `daemon` | Optional long-lived loop instead of OS scheduling (`--interval-seconds`, `--serve-graph`). |

There is intentionally no `sync` or `push` — ingestion is one-directional.

## Configuration

Environment variables the npm wrapper understands:

| Variable | Effect |
| --- | --- |
| `NOTION_WIKI_HOME` | Where the managed Python runtime lives (default `~/.notionwiki`). |
| `NOTION_WIKI_PYTHON` | Path to an existing `notionwiki` executable; skips runtime provisioning entirely. |
| `NOTION_WIKI_SKIP_BOOTSTRAP` | Skip provisioning during `npm install` (it will run on first use instead). |

## Development

Work on the Python package directly with `uv`:

```bash
uv sync --extra graph --extra daemon --group dev
uv run pytest                 # full test suite (HTTP mocked via respx; no live Notion workspace needed)
uv run pytest tests/test_convert_blocks.py -q
uv run ruff check src tests
uv run notionwiki --help     # run the CLI in place
```

See [docs/design.md](docs/design.md) for the full architecture, and [CLAUDE.md](CLAUDE.md) for implementation status and deviations from the design doc.
