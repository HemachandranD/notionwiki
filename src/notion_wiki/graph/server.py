"""Wiki graph UI: FastAPI app serving the force-directed graph at localhost:7777
(docs/design.md §9). No dependency on Notion, state.db, or the ingestion daemon —
works purely off wiki/graph.json. Read-only; bound to 127.0.0.1 only.

The renderer is `force-graph` (vasturiano, canvas + d3-force), vendored under
`static/force-graph.min.js` so the UI works fully offline. It provides pan/zoom/
drag, hover tooltips, and click-to-focus out of the box — replacing the earlier
hand-rolled SVG simulation that had no zoom/pan and scattered nodes off-screen.
"""

from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from notion_wiki.graph.scanner import _parse_frontmatter_and_body
from notion_wiki.paths import wiki_graph_json_path


def _vendored_force_graph_js() -> str:
    return (
        files("notion_wiki.graph")
        .joinpath("static", "force-graph.min.js")
        .read_text(encoding="utf-8")
    )


def _resolve_node_file(wiki_root: Path, node_id: str) -> Path | None:
    """Map a graph node id ("wiki/concepts/foo") back to its markdown file,
    refusing anything that escapes wiki_root or isn't a .md (path-traversal guard)."""
    if not node_id or node_id.startswith("/") or ".." in node_id.split("/"):
        return None
    candidate = (wiki_root / f"{node_id}.md").resolve()
    root = wiki_root.resolve()
    if root not in candidate.parents or candidate.suffix != ".md" or not candidate.is_file():
        return None
    return candidate


def _resolve_sources(wiki_root: Path, frontmatter: dict) -> list[dict]:
    """A wiki page lists its raw feeders as `sources: [[raw/notion/slug]]`; follow
    each to the raw file's frontmatter to recover the Notion title + URL so the UI
    can offer an "Open in Notion" jump."""
    out: list[dict] = []
    for entry in frontmatter.get("sources") or []:
        rel = str(entry).strip().lstrip("[").rstrip("]").split("|")[0].strip()
        if not rel:
            continue
        raw_file = _resolve_node_file(wiki_root, rel)
        if raw_file is None:
            continue
        raw_fm, _ = _parse_frontmatter_and_body(raw_file.read_text(encoding="utf-8"))
        url = raw_fm.get("notion_url")
        if url:
            out.append({"title": raw_fm.get("title") or rel.split("/")[-1], "url": url})
    return out


def _render_page(wiki_root: Path, node_id: str) -> dict | None:
    file = _resolve_node_file(wiki_root, node_id)
    if file is None:
        return None
    import markdown as md

    frontmatter, body = _parse_frontmatter_and_body(file.read_text(encoding="utf-8"))
    # Render [[wiki links]] as plain text (they aren't hyperlinks in this viewer).
    body = body.replace("[[", "").replace("]]", "")
    html = md.markdown(body, extensions=["fenced_code", "tables"])
    return {
        "id": node_id,
        "title": frontmatter.get("title") or node_id.split("/")[-1].replace("-", " "),
        "type": frontmatter.get("type") or "untyped",
        "path": str(file),
        "html": html,
        "sources": _resolve_sources(wiki_root, frontmatter),
    }


_GRAPH_HTML = """<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<title>notionwiki graph</title>
<style>
  html, body { margin: 0; height: 100%; background: #0b0d12; color: #e6e6e6;
    font-family: system-ui, -apple-system, sans-serif; overflow: hidden; }
  #graph { width: 100vw; height: 100vh; }
  #panel { position: fixed; top: 14px; left: 14px; max-width: 340px; padding: 12px 14px;
    background: rgba(17,20,28,.86); border: 1px solid #232838; border-radius: 10px;
    backdrop-filter: blur(6px); font-size: 13px; line-height: 1.45; pointer-events: none; }
  #panel h1 { margin: 0 0 4px; font-size: 14px; font-weight: 600; }
  #panel .meta { color: #8b93a7; font-size: 12px; }
  #panel .desc { margin-top: 8px; color: #c8d0de; }
  #legend { position: fixed; bottom: 14px; left: 14px; font-size: 12px; color: #9aa3b7;
    background: rgba(17,20,28,.8); border: 1px solid #232838; border-radius: 8px;
    padding: 8px 10px; }
  #legend span { display: inline-block; margin-right: 12px; }
  #legend i { display: inline-block; width: 9px; height: 9px; border-radius: 50%;
    margin-right: 5px; vertical-align: middle; }
  #hint { position: fixed; bottom: 14px; right: 14px; font-size: 11px; color: #6b7385; }
  #drawer { position: fixed; top: 0; right: 0; width: min(560px, 92vw); height: 100vh;
    background: #0e1117; border-left: 1px solid #232838; box-shadow: -8px 0 30px rgba(0,0,0,.4);
    transform: translateX(100%); transition: transform .22s ease; overflow-y: auto; z-index: 10; }
  #drawer.open { transform: translateX(0); }
  #drawer .bar { position: sticky; top: 0; display: flex; align-items: center; gap: 10px;
    padding: 12px 16px; background: #11151d; border-bottom: 1px solid #232838; }
  #drawer .bar h2 { margin: 0; font-size: 15px; flex: 1; }
  #drawer .bar .tag { font-size: 11px; color: #8b93a7; }
  #drawer .close { cursor: pointer; border: 1px solid #2a3040; background: #161b25;
    color: #cbd5e1; border-radius: 6px; padding: 3px 9px; font-size: 13px; }
  #drawer .sources { padding: 10px 16px; border-bottom: 1px solid #1c2130; }
  #drawer .sources a { display: inline-block; margin: 3px 6px 3px 0; padding: 3px 9px;
    font-size: 12px; color: #dbe4ff; background: #1b2233; border: 1px solid #2a3346;
    border-radius: 999px; text-decoration: none; }
  #drawer .sources a:hover { background: #223052; }
  #drawer .body { padding: 6px 20px 60px; font-size: 14px; line-height: 1.6; color: #d7dde8; }
  #drawer .body h1,#drawer .body h2,#drawer .body h3 { color: #eef2f8; line-height: 1.3; }
  #drawer .body code { background: #161b25; padding: 1px 5px; border-radius: 4px; font-size: 90%; }
  #drawer .body pre code { background: none; padding: 0; }
  #drawer .body pre { background: #0b0d12; border: 1px solid #1c2130; border-radius: 8px;
    padding: 12px; overflow-x: auto; }
  #drawer .body a { color: #6ea8fe; }
  #drawer .body table { border-collapse: collapse; }
  #drawer .body td,#drawer .body th { border: 1px solid #2a3040; padding: 4px 8px; }
  #drawer .path { font-size: 11px; color: #6b7385; padding: 0 20px 16px; word-break: break-all; }
</style>
</head>
<body>
<div id="graph"></div>
<div id="drawer">
  <div class="bar">
    <h2 id="d-title"></h2><span class="tag" id="d-type"></span>
    <button class="close" id="d-close">esc ✕</button>
  </div>
  <div class="sources" id="d-sources"></div>
  <div class="body" id="d-body"></div>
  <div class="path" id="d-path"></div>
</div>
<div id="panel">
  <h1 id="p-title">notionwiki graph</h1>
  <div class="meta" id="p-meta"></div>
  <div class="desc" id="p-desc">Hover a node for details · scroll to zoom · drag to pan.</div>
</div>
<div id="legend">
  <span><i style="background:#6ea8fe"></i>concept</span>
  <span><i style="background:#f0883e"></i>entity</span>
  <span><i style="background:#56d364"></i>source</span>
</div>
<div id="hint">force-graph · localhost:7777/graph</div>
<script src="/force-graph.min.js"></script>
<script>
const TYPE_COLOR = {
  "concept": "#6ea8fe", "entity": "#f0883e", "source-summary": "#56d364",
};
function colorFor(t) { return TYPE_COLOR[t] || "#8b93a7"; }
function shortName(id) { return String(id).split("/").pop().replace(/-/g, " "); }

const PANEL_DEFAULT_TITLE = "notionwiki graph";
const PANEL_DEFAULT_DESC = "Hover a node for details · scroll to zoom · drag to pan.";

// Single writer for the info panel so hover and click can never disagree, and so
// leaving a node resets it instead of stranding the previous node's summary.
function setPanel(node) {
  const title = document.getElementById("p-title");
  const meta = document.getElementById("p-meta");
  const desc = document.getElementById("p-desc");
  if (!node) {
    title.textContent = PANEL_DEFAULT_TITLE;
    meta.textContent = "";
    desc.textContent = PANEL_DEFAULT_DESC;
    return;
  }
  title.textContent = shortName(node.id);
  meta.textContent = `${node.type} · ${node.backlinks || 0} backlinks · ${node.id}`;
  desc.textContent = node.description || "No description — add one to this page's frontmatter.";
}

async function main() {
  const data = await (await fetch("/graph.json")).json();
  const el = document.getElementById("graph");

  if (!data.nodes || data.nodes.length === 0) {
    document.getElementById("p-title").textContent = "No wiki pages yet";
    document.getElementById("p-desc").textContent =
      "The graph maps the agent-built wiki/ layer, which is still empty. " +
      "Pull sources with `notionwiki pull`, then have your assistant build wiki pages.";
    return;
  }

  const neighbors = new Map();
  data.nodes.forEach((n) => neighbors.set(n.id, new Set()));
  data.edges.forEach((e) => {
    if (neighbors.has(e.source)) neighbors.get(e.source).add(e.target);
    if (neighbors.has(e.target)) neighbors.get(e.target).add(e.source);
  });

  let highlightNode = null;

  const Graph = ForceGraph()(el)
    .graphData({
      nodes: data.nodes.map((n) => ({ ...n })),
      links: data.edges.map((e) => ({ source: e.source, target: e.target })),
    })
    .backgroundColor("#0b0d12")
    .nodeRelSize(4)
    .nodeVal((n) => 1 + (n.backlinks || 0))
    .nodeColor((n) => colorFor(n.type))
    .linkColor(() => "rgba(120,132,160,0.28)")
    .linkWidth((l) => (highlightNode &&
      (l.source.id === highlightNode || l.target.id === highlightNode)) ? 1.6 : 0.5)
    .linkDirectionalParticles(0)
    .nodeCanvasObjectMode(() => "after")
    .nodeCanvasObject((node, ctx, scale) => {
      // Draw a label beside the node once zoomed in enough (Obsidian-style).
      if (scale < 1.2 && node.id !== highlightNode) return;
      const label = shortName(node.id);
      const fontSize = Math.max(10 / scale, 3);
      ctx.font = `${fontSize}px system-ui, sans-serif`;
      ctx.fillStyle = "#cbd5e1";
      ctx.textAlign = "left";
      ctx.textBaseline = "middle";
      const r = Math.sqrt(1 + (node.backlinks || 0)) * 4 / scale;
      ctx.fillText(label, node.x + r + 2 / scale, node.y);
    })
    .onNodeHover((node) => {
      highlightNode = node ? node.id : null;
      el.style.cursor = node ? "pointer" : "default";
      setPanel(node);
    })
    .onNodeClick((node) => {
      // Clicking zooms and re-centers, which moves the node out from under the
      // cursor, so onNodeHover cannot be relied on to fire afterwards. Update the
      // panel here too, otherwise the summary a click produces is down to luck.
      setPanel(node);
      Graph.centerAt(node.x, node.y, 600);
      Graph.zoom(4, 600);
      openDrawer(node.id);
    });

  // Spread things out a bit and stop cleanly, then frame the whole graph.
  Graph.d3Force("charge").strength(-140);
  Graph.d3Force("link").distance(46);
  Graph.onEngineStop(() => Graph.zoomToFit(400, 60));

  window.addEventListener("resize", () => {
    Graph.width(window.innerWidth).height(window.innerHeight);
  });

  // Deep link: /graph#node=<id> opens that page's drawer on load (shareable).
  const hash = new URLSearchParams(location.hash.slice(1));
  if (hash.get("node")) openDrawer(hash.get("node"));
}

const drawer = document.getElementById("drawer");
function closeDrawer() { drawer.classList.remove("open"); }
document.getElementById("d-close").addEventListener("click", closeDrawer);
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeDrawer(); });

async function openDrawer(id) {
  document.getElementById("d-title").textContent = shortName(id);
  document.getElementById("d-type").textContent = "";
  document.getElementById("d-sources").innerHTML = "";
  document.getElementById("d-body").innerHTML = "<p style='color:#8b93a7'>Loading…</p>";
  document.getElementById("d-path").textContent = "";
  drawer.classList.add("open");
  try {
    const res = await fetch("/page?id=" + encodeURIComponent(id));
    if (!res.ok) throw new Error("not found");
    const p = await res.json();
    document.getElementById("d-title").textContent = p.title;
    document.getElementById("d-type").textContent = p.type;
    document.getElementById("d-body").innerHTML = p.html;
    document.getElementById("d-path").textContent = p.path;
    const src = document.getElementById("d-sources");
    if (p.sources && p.sources.length) {
      src.innerHTML = "<span style='color:#8b93a7;font-size:12px;margin-right:6px'>"
        + "Open in Notion:</span>";
      for (const s of p.sources) {
        const a = document.createElement("a");
        a.href = s.url; a.target = "_blank"; a.rel = "noopener";
        a.textContent = "↗ " + s.title;
        src.appendChild(a);
      }
    }
  } catch (err) {
    document.getElementById("d-body").innerHTML =
      "<p style='color:#f0883e'>Could not load this page.</p>";
  }
}
main();
</script>
</body>
</html>
"""


def create_app(wiki_root: Path) -> FastAPI:
    fastapi_app = FastAPI(title="notionwiki graph")

    @fastapi_app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        # The UI lives at /graph; redirect the bare host so the printed link and a
        # manually-typed localhost:7777 both land on the graph instead of a 404.
        return RedirectResponse(url="/graph")

    @fastapi_app.get("/graph", response_class=HTMLResponse)
    def graph_page() -> str:
        return _GRAPH_HTML

    @fastapi_app.get("/force-graph.min.js")
    def force_graph_js() -> Response:
        return Response(
            content=_vendored_force_graph_js(),
            media_type="application/javascript",
            headers={"Cache-Control": "max-age=86400"},
        )

    @fastapi_app.get("/graph.json", response_class=JSONResponse)
    def graph_json() -> dict:
        path = wiki_graph_json_path(wiki_root)
        if not path.exists():
            return {"nodes": [], "edges": []}
        return json.loads(path.read_text(encoding="utf-8"))

    @fastapi_app.get("/page", response_class=JSONResponse)
    def page(id: str) -> JSONResponse:  # noqa: A002 - matches the query-param name
        rendered = _render_page(wiki_root, id)
        if rendered is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse(rendered)

    return fastapi_app


def serve(wiki_root: Path, *, port: int = 7777) -> None:
    import uvicorn

    uvicorn.run(create_app(wiki_root), host="127.0.0.1", port=port)
