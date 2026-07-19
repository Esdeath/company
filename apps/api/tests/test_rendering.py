from pathlib import Path

import pytest

from company_api.rendering import extract_html_title, render_markdown

EXAMPLE_ROOT = Path(__file__).parents[3] / "doc" / "templates" / "markdown" / "examples"


@pytest.mark.parametrize(
    ("fixture_name", "expected"),
    [
        ("financial-snapshot.md", "<table>"),
        ("ceo-interview.md", "<blockquote>"),
        ("public-speech.md", "<ul>"),
    ],
)
def test_examples_share_one_template(fixture_name: str, expected: str) -> None:
    source = (EXAMPLE_ROOT / fixture_name).read_text()

    result = render_markdown(source, fixture_name.removesuffix(".md"))

    assert result.title
    assert expected in result.html
    assert "<style>" in result.html
    assert "{{" not in result.html


def test_first_h1_becomes_title_and_is_not_duplicated() -> None:
    result = render_markdown("导语\n\n# CEO 访谈\n\n正文", "fallback")

    assert result.title == "CEO 访谈"
    assert "<title>CEO 访谈</title>" in result.html
    assert result.html.count("<h1>CEO 访谈</h1>") == 1
    assert result.html.count("<h1>") == 1


def test_extended_markdown_elements_use_the_same_page() -> None:
    source = (
        "- [x] 已核对\n\n脚注[^1]\n\n[^1]: 来源\n\n"
        "![图](https://example.com/a.png)\n\n"
        "[视频](https://example.com/video)\n\n```text\ncode\n```"
    )

    html = render_markdown(source, "资料").html

    for fragment in ("task-list-item", "footnote", "<img", "<a href=", "<pre>"):
        assert fragment in html


def test_html_title_falls_back_without_changing_source() -> None:
    source = b"<!doctype html><p>plain</p>"

    assert extract_html_title(source, "plain") == "plain"
    assert source == b"<!doctype html><p>plain</p>"


def test_html_title_uses_only_the_first_title() -> None:
    source = b"<title>Primary &amp; trusted</title><title>Ignored</title>"

    assert extract_html_title(source, "fallback") == "Primary & trusted"


def test_raw_html_is_preserved_in_rendered_document() -> None:
    result = render_markdown("<aside>Trusted administrator content</aside>", "资料")

    assert "<aside>Trusted administrator content</aside>" in result.html


@pytest.mark.parametrize(
    "marker",
    [
        "{{ document_title }}",
        "{{ document_meta }}",
        "{{ document_styles }}",
        "{{ document_content }}",
    ],
)
def test_template_markers_in_title_and_metadata_are_not_reprocessed(marker: str) -> None:
    raw_body = '<aside data-content="trusted">Raw body</aside>'

    page = render_markdown(raw_body, marker, document_meta=marker).html

    assert f"<title>{marker}</title>" in page
    assert f"<h1>{marker}</h1>" in page
    assert f'<p class="document-meta">{marker}</p>' in page
    assert page.count(raw_body) == 1
    assert f"<title>{raw_body}</title>" not in page
    assert f"<h1>{raw_body}</h1>" not in page
    assert f'<p class="document-meta">{raw_body}</p>' not in page
    assert raw_body in page.split('<article class="markdown-body">', 1)[1].split("</article>", 1)[0]


def test_only_the_first_h1_is_removed_after_leading_content() -> None:
    result = render_markdown("引言\n\n# 首个标题\n\n# 保留标题", "fallback")

    assert result.title == "首个标题"
    assert "<p>引言</p>" in result.html
    assert "<h1>保留标题</h1>" in result.html
