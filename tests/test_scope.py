from notion_wiki.ingest.scope import ScopeResolver
from notion_wiki.notion.models import Page
from tests.fakes import make_raw_page

TS = "2026-07-09T00:00:00.000Z"


class ScopeFakeClient:
    """Serves ancestor pages for the resolver's walk; records what it fetched."""

    def __init__(self, raws: dict[str, dict]):
        self._raws = raws
        self.fetched: list[str] = []

    def retrieve_page(self, page_id: str) -> dict:
        self.fetched.append(page_id)
        return self._raws[page_id]


def _page(pid: str, parent_id: str | None = None) -> Page:
    parent = (
        {"type": "page_id", "page_id": parent_id}
        if parent_id
        else {"type": "workspace", "workspace": True}
    )
    return Page.from_api(make_raw_page(pid, pid, last_edited_time=TS, parent=parent))


def test_empty_roots_is_unrestricted_and_never_hits_network():
    resolver = ScopeResolver(client=None, root_ids=[])
    assert resolver.unrestricted
    assert resolver.in_scope(_page("anything"))


def test_selected_root_itself_in_scope():
    resolver = ScopeResolver(ScopeFakeClient({}), ["root"])
    assert resolver.in_scope(_page("root"))


def test_descendant_in_scope_without_fetch_when_chain_noted():
    client = ScopeFakeClient({})
    resolver = ScopeResolver(client, ["root"])
    resolver.note(_page("root"))
    resolver.note(_page("child", parent_id="root"))
    assert resolver.in_scope(_page("grand", parent_id="child"))
    assert client.fetched == []  # ancestry proven from noted links alone


def test_page_outside_the_subtree_excluded():
    resolver = ScopeResolver(ScopeFakeClient({}), ["root"])
    assert not resolver.in_scope(_page("elsewhere"))


def test_ancestor_is_fetched_once_when_not_already_known():
    raws = {
        "child": make_raw_page(
            "child", "child", last_edited_time=TS, parent={"type": "page_id", "page_id": "root"}
        ),
    }
    client = ScopeFakeClient(raws)
    resolver = ScopeResolver(client, ["root"])
    assert resolver.in_scope(_page("grand", parent_id="child"))
    # Only `child` is fetched — its parent "root" matches the root set directly,
    # so the walk stops without a redundant fetch of root itself.
    assert client.fetched == ["child"]
    # A second query reuses the cache — no more fetches.
    assert resolver.in_scope(_page("grand2", parent_id="child"))
    assert client.fetched == ["child"]


def test_id_matching_ignores_dashes_and_case():
    resolver = ScopeResolver(ScopeFakeClient({}), ["AB-CD-ef"])
    assert resolver.in_scope(_page("abcdef"))
