from notion_wiki.convert.blocks import render_blocks
from notion_wiki.notion.models import Block


def rt(text, **annotations):
    return {"plain_text": text, "type": "text", "annotations": annotations, "href": None}


def link_rt(text, href):
    return {"plain_text": text, "type": "text", "annotations": {}, "href": href}


def mention_rt(text, page_id):
    return {
        "plain_text": text,
        "type": "mention",
        "mention": {"type": "page", "page": {"id": page_id}},
        "annotations": {},
        "href": None,
    }


def para(text_runs, block_id="p1"):
    return Block(id=block_id, type="paragraph", has_children=False, data={"rich_text": text_runs})


def test_plain_paragraph():
    out = render_blocks([para([rt("hello world")])])
    assert out == "hello world"


def test_bold_italic_strike_code_combine():
    runs = [
        rt("bold", bold=True),
        rt(" "),
        rt("italic", italic=True),
        rt(" "),
        rt("strike", strikethrough=True),
        rt(" "),
        rt("code", code=True),
    ]
    out = render_blocks([para(runs)])
    assert out == "**bold** *italic* ~~strike~~ `code`"


def test_link_rendered():
    out = render_blocks([para([link_rt("site", "https://example.com")])])
    assert out == "[site](https://example.com)"


def test_page_mention_resolved_to_wiki_link():
    blocks = [para([mention_rt("Other Page", "page-id-1")])]
    out = render_blocks(blocks, resolve_mention=lambda pid: "raw/notion/other-page")
    assert out == "[[raw/notion/other-page]]"


def test_page_mention_unresolved_falls_back_to_plain_text():
    blocks = [para([mention_rt("Other Page", "page-id-1")])]
    out = render_blocks(blocks, resolve_mention=lambda pid: None)
    assert out == "Other Page"


def test_headings():
    blocks = [
        Block(id="h1", type="heading_1", has_children=False, data={"rich_text": [rt("H1")]}),
        Block(id="h2", type="heading_2", has_children=False, data={"rich_text": [rt("H2")]}),
        Block(id="h3", type="heading_3", has_children=False, data={"rich_text": [rt("H3")]}),
    ]
    out = render_blocks(blocks)
    assert out == "# H1\n\n## H2\n\n### H3"


def test_bulleted_list_joined_without_blank_lines():
    blocks = [
        Block(
            id="b1", type="bulleted_list_item", has_children=False, data={"rich_text": [rt("one")]}
        ),
        Block(
            id="b2", type="bulleted_list_item", has_children=False, data={"rich_text": [rt("two")]}
        ),
    ]
    out = render_blocks(blocks)
    assert out == "- one\n- two"


def test_numbered_list_numbering_and_reset():
    blocks = [
        Block(
            id="n1",
            type="numbered_list_item",
            has_children=False,
            data={"rich_text": [rt("first")]},
        ),
        Block(
            id="n2",
            type="numbered_list_item",
            has_children=False,
            data={"rich_text": [rt("second")]},
        ),
        Block(id="p", type="paragraph", has_children=False, data={"rich_text": [rt("break")]}),
        Block(
            id="n3",
            type="numbered_list_item",
            has_children=False,
            data={"rich_text": [rt("restart")]},
        ),
    ]
    out = render_blocks(blocks)
    assert out == "1. first\n2. second\n\nbreak\n\n1. restart"


def test_todo_checked_and_unchecked():
    blocks = [
        Block(
            id="t1",
            type="to_do",
            has_children=False,
            data={"rich_text": [rt("done")], "checked": True},
        ),
        Block(
            id="t2",
            type="to_do",
            has_children=False,
            data={"rich_text": [rt("todo")], "checked": False},
        ),
    ]
    out = render_blocks(blocks)
    assert out == "- [x] done\n- [ ] todo"


def test_nested_bulleted_list_indented():
    child = Block(
        id="c1", type="bulleted_list_item", has_children=False, data={"rich_text": [rt("child")]}
    )
    parent = Block(
        id="p1",
        type="bulleted_list_item",
        has_children=True,
        data={"rich_text": [rt("parent")]},
        children=[child],
    )
    out = render_blocks([parent])
    assert out == "- parent\n  - child"


def test_code_block_with_language():
    block = Block(
        id="cd1",
        type="code",
        has_children=False,
        data={"rich_text": [rt("x = 1")], "language": "python"},
    )
    out = render_blocks([block])
    assert out == "```python\nx = 1\n```"


def test_quote_block():
    block = Block(id="q1", type="quote", has_children=False, data={"rich_text": [rt("wise words")]})
    out = render_blocks([block])
    assert out == "> wise words"


def test_divider():
    block = Block(id="d1", type="divider", has_children=False, data={})
    out = render_blocks([block])
    assert out == "---"


def test_image_with_download_asset():
    block = Block(
        id="i1",
        type="image",
        has_children=False,
        data={
            "file": {"url": "https://s3.amazonaws.com/signed/foo.png"},
            "caption": [rt("a diagram")],
        },
    )
    out = render_blocks([block], download_asset=lambda url: "assets/sha256-deadbeef.png")
    assert out == "![a diagram](assets/sha256-deadbeef.png)"


def test_image_without_download_asset_falls_back_to_url():
    block = Block(
        id="i1",
        type="image",
        has_children=False,
        data={"external": {"url": "https://x.com/y.png"}, "caption": []},
    )
    out = render_blocks([block])
    assert out == "![image](https://x.com/y.png)"


def test_toggle_shallow_renders_details():
    child = para([rt("hidden content")], "c1")
    toggle = Block(
        id="tg1",
        type="toggle",
        has_children=True,
        data={"rich_text": [rt("Click me")]},
        children=[child],
    )
    out = render_blocks([toggle])
    assert out == "<details>\n<summary>Click me</summary>\n\nhidden content\n\n</details>"


def test_truncated_toggle_renders_placeholder():
    toggle = Block(
        id="tg-deep",
        type="toggle",
        has_children=True,
        data={"rich_text": [rt("deep")]},
        truncated=True,
    )
    out = render_blocks([toggle])
    assert out == ("```notion-block id=tg-deep type=toggle\n🔗 toggle — view in Notion\n```")


def test_unsupported_block_renders_placeholder():
    block = Block(id="e1", type="embed", has_children=False, data={}, truncated=True)
    out = render_blocks([block])
    assert "```notion-block id=e1 type=embed" in out
    assert "view in Notion" in out


def test_child_page_resolved_link():
    block = Block(id="child-1", type="child_page", has_children=False, data={"title": "Sub Page"})
    out = render_blocks([block], resolve_mention=lambda pid: "raw/notion/sub-page")
    assert out == "📄 [[raw/notion/sub-page]]"


def test_child_page_unresolved_shows_title():
    block = Block(id="child-1", type="child_page", has_children=False, data={"title": "Sub Page"})
    out = render_blocks([block])
    assert out == "📄 Sub Page"


def test_mixed_paragraph_and_list_spacing():
    blocks = [
        para([rt("intro")], "p1"),
        Block(
            id="b1", type="bulleted_list_item", has_children=False, data={"rich_text": [rt("item")]}
        ),
        para([rt("outro")], "p2"),
    ]
    out = render_blocks(blocks)
    assert out == "intro\n\n- item\n\noutro"
