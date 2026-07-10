from notion_wiki.notion.models import Block, DatabaseRow, Page, RichText, extract_title


def test_rich_text_annotations():
    rt = RichText.from_api(
        {
            "plain_text": "hello",
            "href": "https://example.com",
            "annotations": {"bold": True, "italic": False, "strikethrough": False, "code": False},
            "type": "text",
        }
    )
    assert rt.plain_text == "hello"
    assert rt.bold is True
    assert rt.mention_page_id is None


def test_rich_text_page_mention():
    rt = RichText.from_api(
        {
            "plain_text": "Some Page",
            "type": "mention",
            "mention": {"type": "page", "page": {"id": "page-123"}},
            "annotations": {},
        }
    )
    assert rt.mention_page_id == "page-123"


def test_block_from_api():
    block = Block.from_api(
        {
            "id": "b1",
            "type": "paragraph",
            "has_children": False,
            "paragraph": {"rich_text": [{"plain_text": "hi", "annotations": {}}]},
        }
    )
    assert block.type == "paragraph"
    assert block.data["rich_text"][0]["plain_text"] == "hi"


def test_extract_title_finds_title_property():
    props = {
        "Tags": {"type": "multi_select", "multi_select": []},
        "Name": {"type": "title", "title": [{"plain_text": "My Page"}]},
    }
    assert extract_title(props) == "My Page"


def test_extract_title_defaults_to_untitled():
    assert extract_title({}) == "Untitled"


def test_page_from_api_parses_parent_and_title():
    raw = {
        "id": "page-1",
        "url": "https://notion.so/page-1",
        "parent": {"type": "page_id", "page_id": "parent-1"},
        "last_edited_time": "2026-07-09T14:01:00.000Z",
        "created_time": "2026-07-01T00:00:00.000Z",
        "properties": {"title": {"type": "title", "title": [{"plain_text": "Bridge Design"}]}},
        "archived": False,
    }
    page = Page.from_api(raw)
    assert page.title == "Bridge Design"
    assert page.parent_type == "page_id"
    assert page.parent_id == "parent-1"


def test_page_from_api_workspace_parent_has_no_parent_id():
    raw = {
        "id": "page-1",
        "url": "https://notion.so/page-1",
        "parent": {"type": "workspace", "workspace": True},
        "last_edited_time": "2026-07-09T14:01:00.000Z",
        "created_time": "2026-07-01T00:00:00.000Z",
        "properties": {},
    }
    page = Page.from_api(raw)
    assert page.parent_id is None


def test_database_row_from_api_carries_database_context():
    raw = {
        "id": "row-1",
        "url": "https://notion.so/row-1",
        "parent": {"type": "database_id", "database_id": "db-1"},
        "last_edited_time": "2026-07-09T14:01:00.000Z",
        "created_time": "2026-07-01T00:00:00.000Z",
        "properties": {"Name": {"type": "title", "title": [{"plain_text": "Row 4"}]}},
    }
    row = DatabaseRow.from_api(raw, database_id="db-1", database_name="Reading Notes")
    assert row.title == "Row 4"
    assert row.database_name == "Reading Notes"
    assert row.database_id == "db-1"
