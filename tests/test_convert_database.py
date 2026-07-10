from notion_wiki.convert.database import render_property_table, render_property_value


def test_title_property_skipped_by_default():
    props = {
        "Name": {"type": "title", "title": [{"plain_text": "Row 4"}]},
        "Tags": {"type": "multi_select", "multi_select": [{"name": "a"}, {"name": "b"}]},
    }
    table = render_property_table(props)
    assert "Name" not in table
    assert "| Tags | a, b |" in table


def test_render_property_table_empty_when_only_title():
    props = {"Name": {"type": "title", "title": [{"plain_text": "Row"}]}}
    assert render_property_table(props) == ""


def test_checkbox_value():
    assert render_property_value({"type": "checkbox", "checkbox": True}) == "x"
    assert render_property_value({"type": "checkbox", "checkbox": False}) == " "


def test_select_value():
    assert render_property_value({"type": "select", "select": {"name": "Done"}}) == "Done"
    assert render_property_value({"type": "select", "select": None}) == ""


def test_date_value_with_and_without_end():
    assert render_property_value({"type": "date", "date": {"start": "2026-07-09"}}) == "2026-07-09"
    assert (
        render_property_value(
            {"type": "date", "date": {"start": "2026-07-09", "end": "2026-07-10"}}
        )
        == "2026-07-09 → 2026-07-10"
    )


def test_number_value():
    assert render_property_value({"type": "number", "number": 42}) == "42"
    assert render_property_value({"type": "number", "number": None}) == ""


def test_people_value():
    props = {"type": "people", "people": [{"name": "Hema"}, {"id": "u2"}]}
    assert render_property_value(props) == "Hema, u2"


def test_url_value():
    assert render_property_value({"type": "url", "url": "https://x.com"}) == "https://x.com"
