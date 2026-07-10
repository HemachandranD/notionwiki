"""Database rows -> source pages (docs/design.md §5.2).

Each database row is itself a Notion page; the raw source file for a row
gets a small markdown property table ahead of the converted page body.
"""

from __future__ import annotations

from typing import Any


def render_property_value(prop: dict[str, Any]) -> str:
    prop_type = prop.get("type")
    value = prop.get(prop_type)

    if prop_type in ("title", "rich_text"):
        return "".join(rt.get("plain_text", "") for rt in (value or []))
    if prop_type in ("select", "status"):
        return value.get("name", "") if value else ""
    if prop_type == "multi_select":
        return ", ".join(opt.get("name", "") for opt in (value or []))
    if prop_type == "checkbox":
        return "x" if value else " "
    if prop_type == "number":
        return "" if value is None else str(value)
    if prop_type == "date":
        if not value:
            return ""
        start = value.get("start", "")
        end = value.get("end")
        return f"{start} → {end}" if end else start
    if prop_type in ("url", "email", "phone_number"):
        return value or ""
    if prop_type == "people":
        return ", ".join(p.get("name") or p.get("id", "") for p in (value or []))
    if prop_type in ("created_time", "last_edited_time"):
        return value or ""
    if prop_type in ("created_by", "last_edited_by"):
        return (value or {}).get("name", "")
    if prop_type == "files":
        return ", ".join(f.get("name", "") for f in (value or []))
    if prop_type == "relation":
        return ", ".join(r.get("id", "") for r in (value or []))
    if prop_type == "formula":
        inner = (value or {}).get("type")
        return str((value or {}).get(inner, "")) if value else ""
    if prop_type == "rollup":
        return str(value) if value else ""
    return str(value) if value is not None else ""


def render_property_table(properties: dict[str, Any], *, skip_title: bool = True) -> str:
    """Render a row's Notion properties as a markdown table, title column skipped
    by default since it becomes the page's H1 instead."""
    rows = []
    for name, prop in properties.items():
        if skip_title and prop.get("type") == "title":
            continue
        rows.append(f"| {name} | {render_property_value(prop)} |")
    if not rows:
        return ""
    return "\n".join(["| Property | Value |", "| --- | --- |", *rows])
