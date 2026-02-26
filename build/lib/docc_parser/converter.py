"""Convert DocC RenderNode JSON to a docutils node tree.

This module walks the structured JSON emitted by ``docc convert`` and
produces a ``docutils.nodes.document`` tree that can be rendered by any
docutils writer (HTML, LaTeX, XML, …) or consumed directly by Sphinx.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from docutils import nodes
from docutils.utils import new_document
from docutils.frontend import get_default_settings
from docutils.parsers.rst import Parser as RSTParser

from .references import ReferenceResolver


# ======================================================================
# Public API
# ======================================================================


def convert_file(json_path: Path) -> nodes.document:
    """Read a RenderNode JSON file and return a ``docutils.nodes.document``."""
    with open(json_path) as fh:
        data = json.load(fh)
    return convert(data, source=str(json_path))


def convert(data: dict, *, source: str = "<docc>") -> nodes.document:
    """Convert a RenderNode dict to a ``docutils.nodes.document``."""
    settings = get_default_settings(RSTParser)
    doc = new_document(source, settings)
    ctx = _Context(data)

    # Title — from metadata.
    title_text = data.get("metadata", {}).get("title", "")

    # Wrap everything in a top-level section so Sphinx toctree finds the title.
    if title_text:
        sec_id = _make_id(title_text)
        top_section = nodes.section(ids=[sec_id], names=[sec_id])
        top_section += nodes.title(title_text, title_text)
        doc += top_section
        body = top_section
    else:
        body = doc

    # Abstract.
    abstract = data.get("abstract", [])
    if abstract:
        p = nodes.paragraph()
        _emit_inline_content(p, abstract, ctx)
        body += p

    # Primary content sections.
    for section in data.get("primaryContentSections", []):
        kind = section.get("kind", "")
        if kind == "content":
            _emit_block_content(body, section.get("content", []), ctx)


    return doc


# ======================================================================
# Helpers
# ======================================================================


def _make_id(text: str) -> str:
    """Convert text to a valid docutils id (lowercase, no special chars)."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


class _Context:
    """Carries state needed during conversion."""

    def __init__(self, data: dict) -> None:
        self.resolver = ReferenceResolver(data.get("references", {}))


# ======================================================================
# Block content
# ======================================================================

_BLOCK_HANDLERS: dict[str, Any] = {}


def _block_handler(type_name: str):
    """Register a handler for RenderNode block *type_name*."""
    def decorator(fn):
        _BLOCK_HANDLERS[type_name] = fn
        return fn
    return decorator


def _emit_block_content(
    parent: nodes.Element, content: list[dict], ctx: _Context
) -> None:
    """Emit block content, reconstructing section hierarchy from headings."""
    section_stack: list[tuple[int, nodes.Element]] = [(0, parent)]

    for block in content:
        block_type = block.get("type", "")

        if block_type == "heading":
            level = block.get("level", 1)
            text = block.get("text", "")
            anchor = block.get("anchor", "")

            while section_stack and section_stack[-1][0] >= level:
                section_stack.pop()

            attach_to = section_stack[-1][1] if section_stack else parent
            sec_id = _make_id(anchor) if anchor else _make_id(text)
            section = nodes.section(ids=[sec_id], names=[sec_id])
            section += nodes.title(text, text)
            attach_to += section
            section_stack.append((level, section))
        else:
            target = section_stack[-1][1] if section_stack else parent
            handler = _BLOCK_HANDLERS.get(block_type)
            if handler:
                handler(target, block, ctx)
            else:
                target += nodes.comment("", f"unhandled block type: {block_type}")


# ------------------------------------------------------------------
# Block handlers
# ------------------------------------------------------------------


@_block_handler("paragraph")
def _handle_paragraph(parent: nodes.Element, block: dict, ctx: _Context) -> None:
    p = nodes.paragraph()
    _emit_inline_content(p, block.get("inlineContent", []), ctx)
    parent += p


@_block_handler("codeListing")
def _handle_code_listing(parent: nodes.Element, block: dict, ctx: _Context) -> None:
    code_text = "\n".join(block.get("code", []))
    syntax = block.get("syntax", "")
    lb = nodes.literal_block(code_text, code_text)
    if syntax:
        lb["language"] = syntax
        lb["classes"].append(syntax)
    lb["xml:space"] = "preserve"
    parent += lb


@_block_handler("aside")
def _handle_aside(parent: nodes.Element, block: dict, ctx: _Context) -> None:
    style = block.get("style", "note")
    content = block.get("content", [])

    builtin = {
        "note": nodes.note,
        "warning": nodes.warning,
        "tip": nodes.tip,
        "important": nodes.important,
    }
    if style in builtin:
        aside_node = builtin[style]()
    else:
        aside_node = nodes.admonition(classes=[style])
        aside_node += nodes.title(style.title(), block.get("name", style.title()))

    _emit_block_content(aside_node, content, ctx)
    parent += aside_node


@_block_handler("unorderedList")
def _handle_unordered_list(parent: nodes.Element, block: dict, ctx: _Context) -> None:
    ul = nodes.bullet_list(bullet="-")
    for item in block.get("items", []):
        li = nodes.list_item()
        _emit_block_content(li, item.get("content", []), ctx)
        ul += li
    parent += ul


@_block_handler("orderedList")
def _handle_ordered_list(parent: nodes.Element, block: dict, ctx: _Context) -> None:
    ol = nodes.enumerated_list()
    start = block.get("start", 1)
    if start != 1:
        ol["start"] = start
    for item in block.get("items", []):
        li = nodes.list_item()
        _emit_block_content(li, item.get("content", []), ctx)
        ol += li
    parent += ol


@_block_handler("table")
def _handle_table(parent: nodes.Element, block: dict, ctx: _Context) -> None:
    raw_rows = block.get("rows", [])
    if not raw_rows:
        return
    ncols = len(raw_rows[0])
    table = nodes.table()
    tgroup = nodes.tgroup(cols=ncols)
    table += tgroup
    for _ in range(ncols):
        tgroup += nodes.colspec(colwidth=100 // ncols)

    header = block.get("header", "none")
    body_start = 0

    if header in ("row", "both") and raw_rows:
        thead = nodes.thead()
        thead += _build_table_row(raw_rows[0], ctx)
        tgroup += thead
        body_start = 1

    tbody = nodes.tbody()
    for row_data in raw_rows[body_start:]:
        tbody += _build_table_row(row_data, ctx)
    tgroup += tbody
    parent += table


def _build_table_row(cells: list, ctx: _Context) -> nodes.row:
    row = nodes.row()
    for cell_content in cells:
        entry = nodes.entry()
        if isinstance(cell_content, list):
            _emit_block_content(entry, cell_content, ctx)
        row += entry
    return row


@_block_handler("termList")
def _handle_term_list(parent: nodes.Element, block: dict, ctx: _Context) -> None:
    dl = nodes.definition_list()
    for item in block.get("items", []):
        dli = nodes.definition_list_item()

        term_node = nodes.term()
        term_data = item.get("term", {})
        _emit_inline_content(term_node, term_data.get("inlineContent", []), ctx)
        dli += term_node

        defn_node = nodes.definition()
        defn_data = item.get("definition", {})
        _emit_block_content(defn_node, defn_data.get("content", []), ctx)
        dli += defn_node

        dl += dli
    parent += dl


@_block_handler("thematicBreak")
def _handle_thematic_break(parent: nodes.Element, block: dict, ctx: _Context) -> None:
    parent += nodes.transition()


@_block_handler("row")
def _handle_row(parent: nodes.Element, block: dict, ctx: _Context) -> None:
    container = nodes.container(classes=["row"])
    for col in block.get("columns", []):
        col_node = nodes.container(classes=["column"])
        _emit_block_content(col_node, col.get("content", []), ctx)
        container += col_node
    parent += container


@_block_handler("small")
def _handle_small(parent: nodes.Element, block: dict, ctx: _Context) -> None:
    p = nodes.paragraph(classes=["small"])
    _emit_inline_content(p, block.get("inlineContent", []), ctx)
    parent += p


@_block_handler("links")
def _handle_links(parent: nodes.Element, block: dict, ctx: _Context) -> None:
    ul = nodes.bullet_list(classes=["links"])
    for ref_id in block.get("items", []):
        li = nodes.list_item()
        p = nodes.paragraph()
        resolved = ctx.resolver.resolve(ref_id)
        if resolved:
            ref_node = nodes.reference("", resolved.title or ref_id, refuri=resolved.url)
        else:
            ref_node = nodes.reference("", ref_id)
        p += ref_node
        li += p
        ul += li
    parent += ul


@_block_handler("tabNavigator")
def _handle_tab_navigator(parent: nodes.Element, block: dict, ctx: _Context) -> None:
    container = nodes.container(classes=["tab-navigator"])
    for tab in block.get("tabs", []):
        tab_node = nodes.container(classes=["tab"])
        tab_node += nodes.title(tab.get("title", ""), tab.get("title", ""))
        _emit_block_content(tab_node, tab.get("content", []), ctx)
        container += tab_node
    parent += container


@_block_handler("video")
def _handle_video(parent: nodes.Element, block: dict, ctx: _Context) -> None:
    identifier = block.get("identifier", "")
    resolved = ctx.resolver.resolve(identifier)
    url = resolved.url if resolved else identifier
    ref_node = nodes.reference("", identifier, refuri=url, classes=["video"])
    parent += ref_node


# ======================================================================
# Inline content
# ======================================================================

_INLINE_HANDLERS: dict[str, Any] = {}


def _inline_handler(type_name: str):
    def decorator(fn):
        _INLINE_HANDLERS[type_name] = fn
        return fn
    return decorator


def _emit_inline_content(
    parent: nodes.Element, content: list[dict], ctx: _Context
) -> None:
    for item in content:
        item_type = item.get("type", "")
        handler = _INLINE_HANDLERS.get(item_type)
        if handler:
            handler(parent, item, ctx)
        else:
            parent += nodes.Text(f"[{item_type}?]")


# ------------------------------------------------------------------
# Inline handlers
# ------------------------------------------------------------------


@_inline_handler("text")
def _handle_text(parent: nodes.Element, item: dict, ctx: _Context) -> None:
    parent += nodes.Text(item.get("text", ""))


@_inline_handler("emphasis")
@_inline_handler("italic")
def _handle_emphasis(parent: nodes.Element, item: dict, ctx: _Context) -> None:
    em = nodes.emphasis()
    _emit_inline_content(em, item.get("inlineContent", []), ctx)
    parent += em


@_inline_handler("strong")
def _handle_strong(parent: nodes.Element, item: dict, ctx: _Context) -> None:
    strong = nodes.strong()
    _emit_inline_content(strong, item.get("inlineContent", []), ctx)
    parent += strong


@_inline_handler("codeVoice")
def _handle_code_voice(parent: nodes.Element, item: dict, ctx: _Context) -> None:
    code = item.get("code", "")
    parent += nodes.literal(code, code)


@_inline_handler("reference")
def _handle_reference(parent: nodes.Element, item: dict, ctx: _Context) -> None:
    identifier = item.get("identifier", "")
    resolved = ctx.resolver.resolve(identifier)
    if resolved:
        title = item.get("overridingTitle") or resolved.title or identifier
        ref_node = nodes.reference("", title, refuri=resolved.url)
    else:
        title = item.get("overridingTitle", identifier)
        ref_node = nodes.reference("", title, refuri=identifier)

    if not item.get("isActive", True):
        ref_node["classes"].append("inactive")
    parent += ref_node


@_inline_handler("image")
def _handle_image(parent: nodes.Element, item: dict, ctx: _Context) -> None:
    identifier = item.get("identifier", "")
    resolved = ctx.resolver.resolve(identifier)
    if resolved:
        img = nodes.image(uri=resolved.url)
        if resolved.title:
            img["alt"] = resolved.title
    else:
        img = nodes.image(uri=identifier)
    parent += img


@_inline_handler("link")
def _handle_link(parent: nodes.Element, item: dict, ctx: _Context) -> None:
    title = item.get("title", "")
    ref_node = nodes.reference("", title, refuri=item.get("destination", ""))
    parent += ref_node


@_inline_handler("newTerm")
def _handle_new_term(parent: nodes.Element, item: dict, ctx: _Context) -> None:
    em = nodes.emphasis(classes=["new-term"])
    _emit_inline_content(em, item.get("inlineContent", []), ctx)
    parent += em


@_inline_handler("inlineHead")
def _handle_inline_head(parent: nodes.Element, item: dict, ctx: _Context) -> None:
    strong = nodes.strong()
    _emit_inline_content(strong, item.get("inlineContent", []), ctx)
    parent += strong


@_inline_handler("superscript")
def _handle_superscript(parent: nodes.Element, item: dict, ctx: _Context) -> None:
    sup = nodes.superscript()
    _emit_inline_content(sup, item.get("inlineContent", []), ctx)
    parent += sup


@_inline_handler("subscript")
def _handle_subscript_inline(parent: nodes.Element, item: dict, ctx: _Context) -> None:
    sub = nodes.subscript()
    _emit_inline_content(sub, item.get("inlineContent", []), ctx)
    parent += sub


@_inline_handler("strikethrough")
def _handle_strikethrough(parent: nodes.Element, item: dict, ctx: _Context) -> None:
    el = nodes.inline(classes=["strikethrough"])
    _emit_inline_content(el, item.get("inlineContent", []), ctx)
    parent += el
