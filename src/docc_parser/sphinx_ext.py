"""Sphinx extension for Swift DocC integration.

Usage in conf.py::
    extensions = ["docc_parser.sphinx_ext"]
    docc_catalog = "TSPL.docc"

In index.rst::
    .. swift-docc::
"""

import re
import shutil
from pathlib import Path
from typing import Any

from docutils import nodes
from sphinx import addnodes
from sphinx.application import Sphinx
from sphinx.util import logging
from docutils.parsers.rst import Directive

from .bridge import parse_catalog
from .converter import convert

logger = logging.getLogger(__name__)

STUBS_DIR = "docc_stubs"


def _safe_docname(identifier: str) -> str:
    """Turn a doc://TSPL/documentation/foo/bar identifier into foo/bar."""
    if identifier.startswith("doc://"):
        identifier = identifier[6:]
    parts = identifier.split("/")
    # Skip module-name/documentation prefix
    if len(parts) > 2 and parts[1] == "documentation":
        parts = parts[2:]
    name = "/".join(parts)
    # Sanitize for filesystem
    return re.sub(r"[^a-zA-Z0-9/_-]", "-", name).strip("-")

def _copy_docc_images(catalog: Path, srcdir: Path):
    """Copy images from TSPL.docc/Assets/ to srcdir/images/, renaming @ to -."""
    assets = catalog / "Assets"
    if not assets.exists():
        return

    dest = srcdir / "images"
    dest.mkdir(exist_ok=True)

    count = 0
    for img in assets.iterdir():
        if img.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".svg"):
            safe_name = img.name.replace("@", "-")
            target = dest / safe_name
            if not target.exists() or img.stat().st_mtime > target.stat().st_mtime:
                shutil.copy2(img, target)
                count += 1

    logger.info(f"DocC: copied {count} images to images/")


def process_catalog(app: Sphinx):
    """builder-inited: call dylib once, write stub files, stash page data."""
    catalog_name = app.config.docc_catalog
    if not catalog_name:
        return

    catalog = Path(app.srcdir) / catalog_name
    if not catalog.exists():
        logger.warning(f"DocC catalog not found: {catalog}")
        return

    _copy_docc_images(catalog, Path(app.srcdir))

    try:
        pages = parse_catalog(catalog)
    except Exception as e:
        logger.error(f"Failed to parse DocC catalog: {e}")
        return

    logger.info(f"DocC: parsed {len(pages)} pages from {catalog_name}")

    # Clean stubs dir
    stubs_path = Path(app.srcdir) / STUBS_DIR
    if stubs_path.exists():
        shutil.rmtree(stubs_path)
    stubs_path.mkdir(parents=True)

    app.docc_pages = {}
    all_docnames = set()
    child_docnames = set()

    # First pass: register all pages
    for page in pages:
        identifier = page.get("identifier", {}).get("url", "")
        if not identifier:
            continue
        docname = _safe_docname(identifier)
        all_docnames.add(docname)
        app.docc_pages[docname] = page

    # Second pass: write stubs with toctrees
    for docname, page in app.docc_pages.items():
        lines = [f".. docc-page:: {docname}", ""]

        for section in page.get("topicSections", []):
            title = section.get("title", "Topics")
            children = []
            for ident in section.get("identifiers", []):
                child = _safe_docname(ident)
                if child in all_docnames:
                    children.append(child)
                    child_docnames.add(child)

            if children:
                lines.append(".. toctree::")
                lines.append(f"   :caption: {title}")
                lines.append("   :maxdepth: 1")
                lines.append("")
                for child in children:
                    lines.append(f"   /{STUBS_DIR}/{child}")
                lines.append("")

        stub = stubs_path / f"{docname}.rst"
        stub.parent.mkdir(parents=True, exist_ok=True)
        stub.write_text("\n".join(lines), encoding="utf-8")

    app.docc_root_pages = sorted(all_docnames - child_docnames)
    logger.info(f"DocC: {len(app.docc_root_pages)} root pages, "
                f"{len(child_docnames)} child pages")


class SwiftDocCDirective(Directive):
    """
    .. swift-docc::

    Place in index.rst. Emits a toctree of root pages.
    """
    has_content = False
    required_arguments = 0

    def run(self):
        env = self.state.document.settings.env
        app = env.app
        root_pages = getattr(app, "docc_root_pages", [])
        pages = getattr(app, "docc_pages", {})

        if not root_pages:
            return [nodes.paragraph(text="No DocC pages found.")]

        toc = addnodes.toctree()
        toc["entries"] = []
        toc["includefiles"] = []
        toc["maxdepth"] = 2
        toc["glob"] = False
        toc["parent"] = env.docname

        for docname in root_pages:
            page = pages.get(docname, {})
            title = (page.get("metadata", {}).get("title")
                     or docname.rsplit("/", 1)[-1])
            ref = f"{STUBS_DIR}/{docname}"
            toc["entries"].append((title, ref))
            toc["includefiles"].append(ref)

        wrapper = nodes.compound()
        wrapper += toc
        return [wrapper]


class DocCPageDirective(Directive):
    """
    .. docc-page:: some/page/name

    In each stub. Builds docutils nodes from stashed page data.
    """
    has_content = False
    required_arguments = 1

    def run(self):
        env = self.state.document.settings.env
        app = env.app
        docname = self.arguments[0]

        pages = getattr(app, "docc_pages", {})
        page = pages.get(docname)

        if not page:
            logger.warning(f"docc-page: no data for '{docname}'")
            return [nodes.paragraph(text=f"Missing page: {docname}")]

        try:
            doc = convert(page, source=docname)
            return [child.deepcopy() for child in doc.children]
        except Exception as e:
            logger.error(f"docc-page conversion error for {docname}: {e}")
            return [nodes.error("", nodes.paragraph(text=str(e)))]


def setup(app: Sphinx) -> dict[str, Any]:
    app.add_config_value("docc_catalog", None, "env")
    app.add_directive("swift-docc", SwiftDocCDirective)
    app.add_directive("docc-page", DocCPageDirective)
    app.connect("builder-inited", process_catalog)

    return {"version": "0.1", "parallel_read_safe": True}
