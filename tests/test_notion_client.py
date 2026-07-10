import httpx
import pytest
import respx

from notion_wiki.notion.client import BASE_URL, NotionAPIError, NotionClient
from notion_wiki.notion.rate_limit import TokenBucket

FAST_LIMITER = lambda: TokenBucket(rate=1000, capacity=1000)  # noqa: E731


@respx.mock
def test_search_paginates():
    page1 = {
        "results": [{"id": "p1"}, {"id": "p2"}],
        "has_more": True,
        "next_cursor": "cursor-2",
    }
    page2 = {"results": [{"id": "p3"}], "has_more": False, "next_cursor": None}
    route = respx.post(f"{BASE_URL}/search")
    route.side_effect = [
        httpx.Response(200, json=page1),
        httpx.Response(200, json=page2),
    ]

    client = NotionClient("secret-token", rate_limiter=FAST_LIMITER())
    results = list(client.search())

    assert [r["id"] for r in results] == ["p1", "p2", "p3"]
    assert route.call_count == 2
    first_request_body = route.calls[0].request.content
    assert b'"value":"page"' in first_request_body


@respx.mock
def test_list_block_children_paginates():
    page1 = {"results": [{"id": "b1"}], "has_more": True, "next_cursor": "c2"}
    page2 = {"results": [{"id": "b2"}], "has_more": False, "next_cursor": None}
    route = respx.get(f"{BASE_URL}/blocks/abc/children")
    route.side_effect = [
        httpx.Response(200, json=page1),
        httpx.Response(200, json=page2),
    ]

    client = NotionClient("secret-token", rate_limiter=FAST_LIMITER())
    results = list(client.list_block_children("abc"))

    assert [r["id"] for r in results] == ["b1", "b2"]


@respx.mock
def test_retrieve_page():
    respx.get(f"{BASE_URL}/pages/xyz").mock(return_value=httpx.Response(200, json={"id": "xyz"}))
    client = NotionClient("secret-token", rate_limiter=FAST_LIMITER())
    assert client.retrieve_page("xyz") == {"id": "xyz"}


@respx.mock
def test_search_databases_filters_by_database_object():
    body = {"results": [{"id": "db1", "title": []}], "has_more": False, "next_cursor": None}
    route = respx.post(f"{BASE_URL}/search")
    route.mock(return_value=httpx.Response(200, json=body))
    client = NotionClient("secret-token", rate_limiter=FAST_LIMITER())

    results = list(client.search_databases())

    assert [r["id"] for r in results] == ["db1"]
    assert b'"value":"database"' in route.calls[0].request.content


@respx.mock
def test_query_database():
    body = {"results": [{"id": "row1"}], "has_more": False, "next_cursor": None}
    respx.post(f"{BASE_URL}/databases/db1/query").mock(return_value=httpx.Response(200, json=body))
    client = NotionClient("secret-token", rate_limiter=FAST_LIMITER())
    assert [r["id"] for r in client.query_database("db1")] == ["row1"]


@respx.mock
def test_retries_on_429_then_succeeds():
    route = respx.get(f"{BASE_URL}/pages/xyz")
    route.side_effect = [
        httpx.Response(429, headers={"Retry-After": "0"}, json={"message": "rate limited"}),
        httpx.Response(200, json={"id": "xyz"}),
    ]
    client = NotionClient("secret-token", rate_limiter=FAST_LIMITER())
    assert client.retrieve_page("xyz") == {"id": "xyz"}
    assert route.call_count == 2


@respx.mock
def test_exhausts_retries_raises(monkeypatch):
    monkeypatch.setattr("notion_wiki.notion.client.time.sleep", lambda *_: None)
    respx.get(f"{BASE_URL}/pages/xyz").mock(
        return_value=httpx.Response(500, json={"message": "server error"})
    )
    client = NotionClient("secret-token", rate_limiter=FAST_LIMITER(), max_retries=2)
    with pytest.raises(NotionAPIError):
        client.retrieve_page("xyz")


@respx.mock
def test_client_error_raises_immediately():
    respx.get(f"{BASE_URL}/pages/missing").mock(return_value=httpx.Response(404, json={}))
    client = NotionClient("secret-token", rate_limiter=FAST_LIMITER())
    with pytest.raises(httpx.HTTPStatusError):
        client.retrieve_page("missing")
