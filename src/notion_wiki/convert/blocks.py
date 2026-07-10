"""Block tree -> markdown (docs/design.md §5.2). The critical suite (§12).

Pure and network-free: callers first build the tree via
`NotionClient.fetch_block_tree` (which sets `.truncated` on read-only islands
and over-deep toggles per §5.2), then hand it to `render_blocks`. This keeps
conversion unit-testable without mocking HTTP.
"""

from __future__ import annotations

from collections.abc import Callable

from notion_wiki.notion.models import Block, RichText

ResolveMention = Callable[[str], "str | None"]
DownloadAsset = Callable[[str], "str | None"]

_HEADING_PREFIX = {"heading_1": "#", "heading_2": "##", "heading_3": "###"}


def _render_run(raw: dict, resolve_mention: ResolveMention | None) -> str:
    rt = RichText.from_api(raw)
    text = rt.plain_text
    if rt.code:
        text = f"`{text}`"
    if rt.bold:
        text = f"**{text}**"
    if rt.italic:
        text = f"*{text}*"
    if rt.strikethrough:
        text = f"~~{text}~~"

    if rt.mention_page_id:
        target = resolve_mention(rt.mention_page_id) if resolve_mention else None
        if target:
            return f"[[{target}]]"
        if rt.href:
            return f"[{text}]({rt.href})"
        return text

    if rt.href:
        return f"[{text}]({rt.href})"
    return text


def _render_rich_text(runs: list[dict], resolve_mention: ResolveMention | None) -> str:
    return "".join(_render_run(raw, resolve_mention) for raw in runs)


def _indent(text: str, prefix: str = "  ") -> str:
    return "\n".join((prefix + line if line else line) for line in text.splitlines())


def _placeholder(block: Block) -> str:
    label = block.type.replace("_", " ")
    return f"```notion-block id={block.id} type={block.type}\n🔗 {label} — view in Notion\n```"


def _render_children(
    block: Block, resolve_mention: ResolveMention | None, download_asset: DownloadAsset | None
) -> str:
    if not block.children:
        return ""
    return render_blocks(
        block.children, resolve_mention=resolve_mention, download_asset=download_asset
    )


def _render_image(block: Block, download_asset: DownloadAsset | None) -> str:
    file_info = block.data.get("file") or block.data.get("external") or {}
    url = file_info.get("url", "")
    caption = "".join(rt.get("plain_text", "") for rt in block.data.get("caption", [])) or "image"
    path = download_asset(url) if (download_asset and url) else url
    return f"![{caption}]({path})"


def _render_child_page(block: Block, resolve_mention: ResolveMention | None) -> str:
    title = block.data.get("title", "")
    target = resolve_mention(block.id) if resolve_mention else None
    return f"📄 [[{target}]]" if target else f"📄 {title}"


def _render_simple(
    block: Block, resolve_mention: ResolveMention | None, download_asset: DownloadAsset | None
) -> str:
    """Dispatch for block types that don't need sibling context (numbering)."""
    if block.type == "paragraph":
        return _render_rich_text(block.data.get("rich_text", []), resolve_mention)

    if block.type in _HEADING_PREFIX:
        prefix = _HEADING_PREFIX[block.type]
        return f"{prefix} {_render_rich_text(block.data.get('rich_text', []), resolve_mention)}"

    if block.type == "bulleted_list_item":
        text = f"- {_render_rich_text(block.data.get('rich_text', []), resolve_mention)}"
        nested = _render_children(block, resolve_mention, download_asset)
        return f"{text}\n{_indent(nested)}" if nested else text

    if block.type == "to_do":
        mark = "x" if block.data.get("checked") else " "
        text = f"- [{mark}] {_render_rich_text(block.data.get('rich_text', []), resolve_mention)}"
        nested = _render_children(block, resolve_mention, download_asset)
        return f"{text}\n{_indent(nested)}" if nested else text

    if block.type == "code":
        language = block.data.get("language") or ""
        code_text = "".join(rt.get("plain_text", "") for rt in block.data.get("rich_text", []))
        return f"```{language}\n{code_text}\n```"

    if block.type == "quote":
        text = _render_rich_text(block.data.get("rich_text", []), resolve_mention)
        quoted = "\n".join(f"> {line}" for line in text.splitlines()) or "> "
        nested = _render_children(block, resolve_mention, download_asset)
        return f"{quoted}\n{_indent(nested, '> ')}" if nested else quoted

    if block.type == "divider":
        return "---"

    if block.type == "image":
        return _render_image(block, download_asset)

    if block.type == "child_page":
        return _render_child_page(block, resolve_mention)

    if block.type == "toggle":
        summary = _render_rich_text(block.data.get("rich_text", []), resolve_mention)
        nested = _render_children(block, resolve_mention, download_asset)
        body = f"\n\n{nested}\n\n" if nested else "\n\n"
        return f"<details>\n<summary>{summary}</summary>{body}</details>"

    return _placeholder(block)


_LIST_TYPES = frozenset({"bulleted_list_item", "numbered_list_item", "to_do"})


def render_blocks(
    blocks: list[Block],
    *,
    resolve_mention: ResolveMention | None = None,
    download_asset: DownloadAsset | None = None,
) -> str:
    """Render an already-fetched block tree to markdown.

    Consecutive list items (bulleted/numbered/to-do) are joined with a single
    newline so they render as one continuous markdown list; every other
    block-to-block transition gets a blank line, matching normal prose flow.
    """
    parts: list[str] = []
    previous_was_list = False
    numbered_counter = 0

    for block in blocks:
        if block.type != "numbered_list_item":
            numbered_counter = 0

        if block.truncated:
            rendered = _placeholder(block)
            is_list_item = False
        elif block.type == "numbered_list_item":
            numbered_counter += 1
            rich_text = _render_rich_text(block.data.get("rich_text", []), resolve_mention)
            text = f"{numbered_counter}. {rich_text}"
            nested = _render_children(block, resolve_mention, download_asset)
            rendered = f"{text}\n{_indent(nested)}" if nested else text
            is_list_item = True
        else:
            rendered = _render_simple(block, resolve_mention, download_asset)
            is_list_item = block.type in _LIST_TYPES

        if previous_was_list and is_list_item:
            parts[-1] = f"{parts[-1]}\n{rendered}"
        else:
            parts.append(rendered)
        previous_was_list = is_list_item

    return "\n\n".join(parts)
