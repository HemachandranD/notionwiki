"""Wiki graph UI: FastAPI app serving the force-directed graph at localhost:7777
(docs/design.md §9). No dependency on Notion, state.db, or the ingestion daemon —
works purely off wiki/graph.json. Read-only; bound to 127.0.0.1 only.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from notion_wiki.paths import wiki_graph_json_path

_GRAPH_HTML = """<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<title>notion-wiki graph</title>
<style>
  body { margin: 0; background: #0b0d12; color: #e6e6e6; font-family: system-ui, sans-serif; }
  svg { width: 100vw; height: 100vh; display: block; }
  circle { fill: #6ea8fe; stroke: #1b2735; stroke-width: 1px; }
  line { stroke: #3a4256; stroke-width: 1px; }
  text { fill: #cbd5e1; font-size: 11px; pointer-events: none; }
</style>
</head>
<body>
<svg id="graph"></svg>
<script>
async function main() {
  const res = await fetch("/graph.json");
  const data = await res.json();
  const svg = document.getElementById("graph");
  const width = window.innerWidth, height = window.innerHeight;

  const nodes = data.nodes.map((n, i) => ({
    ...n, x: width / 2 + Math.cos(i) * 100, y: height / 2 + Math.sin(i) * 100, vx: 0, vy: 0,
  }));
  const index = Object.fromEntries(nodes.map((n) => [n.id, n]));
  const edges = data.edges.filter((e) => index[e.source] && index[e.target]);

  function tick() {
    for (const n of nodes) {
      n.vx += (width / 2 - n.x) * 0.001;
      n.vy += (height / 2 - n.y) * 0.001;
      for (const other of nodes) {
        if (other === n) continue;
        const dx = n.x - other.x, dy = n.y - other.y;
        const distSq = Math.max(dx * dx + dy * dy, 1);
        const force = 400 / distSq;
        n.vx += dx * force;
        n.vy += dy * force;
      }
    }
    for (const e of edges) {
      const a = index[e.source], b = index[e.target];
      const dx = b.x - a.x, dy = b.y - a.y;
      a.vx += dx * 0.01; a.vy += dy * 0.01;
      b.vx -= dx * 0.01; b.vy -= dy * 0.01;
    }
    for (const n of nodes) {
      n.vx *= 0.85; n.vy *= 0.85;
      n.x += n.vx; n.y += n.vy;
    }
  }

  function render() {
    const lines = edges
      .map((e) => {
        const a = index[e.source], b = index[e.target];
        return `<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" />`;
      })
      .join("");
    const circles = nodes
      .map(
        (n) =>
          `<circle cx="${n.x}" cy="${n.y}" r="${4 + Math.sqrt(n.backlinks || 0) * 2}" />` +
          `<text x="${n.x + 8}" y="${n.y + 4}">${n.id}</text>`
      )
      .join("");
    svg.innerHTML = lines + circles;
  }

  function loop() {
    tick();
    render();
    requestAnimationFrame(loop);
  }
  loop();
}
main();
</script>
</body>
</html>
"""


def create_app(wiki_root: Path) -> FastAPI:
    fastapi_app = FastAPI(title="notion-wiki graph")

    @fastapi_app.get("/graph", response_class=HTMLResponse)
    def graph_page() -> str:
        return _GRAPH_HTML

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
