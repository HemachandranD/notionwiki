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

from notion_wiki.paths import wiki_graph_json_path


def _vendored_force_graph_js() -> str:
    return (
        files("notion_wiki.graph")
        .joinpath("static", "force-graph.min.js")
        .read_text(encoding="utf-8")
    )


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
</style>
</head>
<body>
<div id="graph"></div>
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
      const panel = {
        title: document.getElementById("p-title"),
        meta: document.getElementById("p-meta"),
        desc: document.getElementById("p-desc"),
      };
      if (node) {
        panel.title.textContent = shortName(node.id);
        panel.meta.textContent = `${node.type} · ${node.backlinks || 0} backlinks · ${node.id}`;
        panel.desc.textContent = node.description || "";
      }
    })
    .onNodeClick((node) => {
      Graph.centerAt(node.x, node.y, 600);
      Graph.zoom(4, 600);
    });

  // Spread things out a bit and stop cleanly, then frame the whole graph.
  Graph.d3Force("charge").strength(-140);
  Graph.d3Force("link").distance(46);
  Graph.onEngineStop(() => Graph.zoomToFit(400, 60));

  window.addEventListener("resize", () => {
    Graph.width(window.innerWidth).height(window.innerHeight);
  });
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

    return fastapi_app


def serve(wiki_root: Path, *, port: int = 7777) -> None:
    import uvicorn

    uvicorn.run(create_app(wiki_root), host="127.0.0.1", port=port)
