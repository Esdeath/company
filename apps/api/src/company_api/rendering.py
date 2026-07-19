"""Render trusted Markdown documents with the shared editorial template."""

import html
from dataclasses import dataclass
from html.parser import HTMLParser
from importlib.resources import files

from markdown_it import MarkdownIt
from mdit_py_plugins.footnote import footnote_plugin
from mdit_py_plugins.tasklists import tasklists_plugin

markdown = (
    MarkdownIt("commonmark", {"html": True})
    .enable("table")
    .use(footnote_plugin)
    .use(tasklists_plugin)
)


@dataclass(frozen=True)
class RenderedMarkdown:
    title: str
    html: str


class _FirstTitleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._capturing_title = False
        self._has_seen_title = False
        self._title_parts: list[str] = []

    @property
    def title(self) -> str:
        return "".join(self._title_parts).strip()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag.lower() == "title" and not self._has_seen_title:
            self._has_seen_title = True
            self._capturing_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title" and self._capturing_title:
            self._capturing_title = False

    def handle_data(self, data: str) -> None:
        if self._capturing_title:
            self._title_parts.append(data)


def extract_html_title(source: bytes, fallback_title: str) -> str:
    """Return the first HTML title without changing the original source bytes."""
    parser = _FirstTitleParser()
    parser.feed(source.decode("utf-8", errors="replace"))
    parser.close()
    return parser.title or fallback_title


def _load_template() -> str:
    return (
        files("company_api")
        .joinpath("templates", "markdown", "template.html")
        .read_text(encoding="utf-8")
    )


def _load_styles() -> str:
    return (
        files("company_api")
        .joinpath("templates", "markdown", "template.css")
        .read_text(encoding="utf-8")
    )


def render_markdown(
    source: str,
    fallback_title: str,
    document_meta: str = "",
) -> RenderedMarkdown:
    """Render trusted Markdown into the standalone editorial document page."""
    tokens = markdown.parse(source)
    title = fallback_title
    title_index = next(
        (
            index
            for index, token in enumerate(tokens)
            if token.type == "heading_open" and token.tag == "h1"
        ),
        None,
    )
    if title_index is not None:
        title = tokens[title_index + 1].content.strip() or fallback_title
        tokens = tokens[:title_index] + tokens[title_index + 3 :]

    body = markdown.renderer.render(tokens, markdown.options, {})
    page = _load_template().replace("{{ document_title }}", html.escape(title))
    page = page.replace("{{ document_meta }}", html.escape(document_meta))
    page = page.replace("{{ document_styles }}", _load_styles())
    page = page.replace("{{ document_content }}", body)
    return RenderedMarkdown(title=title, html=page)
