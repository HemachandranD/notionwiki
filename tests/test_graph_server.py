from pathlib import Path

from fastapi.testclient import TestClient

from notion_wiki.graph.graph_gen import generate_graph
from notion_wiki.graph.server import create_app
from tests.test_graph_gen import write_page


def test_graph_json_endpoint_serves_generated_graph(tmp_path: Path):
    write_page(tmp_path, "wiki/concepts/a.md", frontmatter={"type": "concept", "description": "d"})
    generate_graph(tmp_path)

    client = TestClient(create_app(tmp_path))
    response = client.get("/graph.json")

    assert response.status_code == 200
    assert response.json()["nodes"][0]["id"] == "wiki/concepts/a"


def test_graph_json_endpoint_empty_when_not_generated(tmp_path: Path):
    client = TestClient(create_app(tmp_path))
    response = client.get("/graph.json")
    assert response.json() == {"nodes": [], "edges": []}


def test_graph_page_serves_html(tmp_path: Path):
    client = TestClient(create_app(tmp_path))
    response = client.get("/graph")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "graph.json" in response.text
    # The UI is driven by the vendored force-graph renderer, not the old inline SVG sim.
    assert "ForceGraph" in response.text


def test_root_redirects_to_graph(tmp_path: Path):
    client = TestClient(create_app(tmp_path), follow_redirects=False)
    response = client.get("/")
    assert response.status_code in (307, 308)
    assert response.headers["location"] == "/graph"


def test_vendored_force_graph_js_is_served(tmp_path: Path):
    client = TestClient(create_app(tmp_path))
    response = client.get("/force-graph.min.js")
    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]
    assert "force-graph" in response.text  # the bundle's banner comment
