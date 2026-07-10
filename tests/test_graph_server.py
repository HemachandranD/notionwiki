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
