"""Sphinx extension for native Swift DocC integration.

Provides the ``.. swift-docc::`` directive to parse and render a `.docc`
catalog natively in-memory using the Swift DocC C ABI bridge.

Usage in ``conf.py``::

    extensions = ["docc_parser.sphinx_ext"]

In an ``.rst`` file:

    .. swift-docc:: TSPL.docc
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from docutils import nodes
from sphinx.application import Sphinx
from sphinx.parsers import Parser
from sphinx.util import logging

from .bridge import parse_catalog
from .converter import convert

logger = logging.getLogger(__name__)

# To share loaded nodes between compilation phases, we store them globally in the sphinx env
# Sphinx normally parses files one by one (read phase).
# But our bridged parse_catalog() returns ALL nodes at once.
# For simplicity, if we get a `.docc` directory as a "source", we evaluate the whole thing,
# and insert the nodes.
# However, Sphinx is designed to map 1 source file -> 1 output file.
# We will intercept the build. But for now let's just make the parser read one node. Or wait.

# Actually, the user asked to make "a sphinx extension and it should not make assumptions about the content of the docc markup."
# A `.docc` is a *directory*. Sphinx doesn't normally process directories as sources.
# Let's map `.docc` directly. When Sphinx asks us to parse `something.docc`, we parse it,
# take the primary RenderNode (the one that matches the catalog name or is the "root"),
# and emit it? Or wait, `parse_catalog` returns a *list* of many RenderNodes.
# Sphinx wants us to populate `document` (a single docutils AST node) for the current `inputstring`.

# To integrate SwiftDocC cleanly without assuming file layouts:
# 1. We expose a Sphinx directive to inline docc catalogs: `.. docc:: path/to/catalog.docc`
# 2. Or, more natively, we don't use a standard `Parser` for `.docc` files because `.docc` is a directory.
# Let's just create an `env-updated` hook or a custom source reader?

# The simplest robust way for a Sphinx extension to ingest a whole directory of external ASTs
# is to use the `env-updated` event or a dedicated Directive.
# Wait, if we use a Sphinx Parser, Sphinx passes the contents of the file. But `.docc` is a dir.
# Let's provide a Directive `.. swift-docc:: path/to.docc` which parses the catalog,
# and inserts the resulting nodes into the current document.

from docutils.parsers.rst import Directive, directives

class DoccDirective(Directive):
    """A directive to include and render a SwiftDocC catalog.
    
    Usage:
    
        .. docc:: TSPL.docc
    """
    required_arguments = 1
    optional_arguments = 0
    final_argument_whitespace = True
    has_content = False

    def run(self):
        catalog_path = self.arguments[0]
        env = self.state.document.settings.env
        
        # Resolve path relative to current document
        doc_dir = Path(env.doc2path(env.docname)).parent
        abs_catalog_path = doc_dir / catalog_path
        
        env.note_dependency(str(abs_catalog_path))
        
        try:
            nodes_data = parse_catalog(abs_catalog_path)
        except Exception as e:
            logger.error(f"Failed to parse DocC catalog {catalog_path}: {e}")
            return [nodes.error('', nodes.paragraph(text=f"DocC parse error: {e}"))]
        
        # Convert all parsed nodes into docutils nodes
        # We wrap them in a container to avoid multiple top-level titles
        container = nodes.container(classes=["docc-catalog"])
        
        for json_data in nodes_data:
            doc = convert(json_data, source=str(abs_catalog_path))
            for child in doc.children:
                container += child.deepcopy()
                
        return [container]


def setup(app: Sphinx) -> dict[str, Any]:
    app.add_directive("swift-docc", DoccDirective)
    return {"version": "0.1", "parallel_read_safe": True}
