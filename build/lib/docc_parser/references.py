"""Resolve RenderNode reference identifiers to URLs, titles, and metadata."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ResolvedReference:
    """A resolved reference with URL and display information."""

    url: str
    title: str
    kind: str  # "topic", "image", "video", "file"
    abstract: str = ""


class ReferenceResolver:
    """Resolves reference identifiers from a RenderNode's `references` dict.

    Each RenderNode JSON has a top-level ``references`` object mapping
    identifier strings (e.g. ``"doc://com.apple.swift/..."`` ) to reference
    objects that contain the resolved URL, title, and type information.
    """

    def __init__(self, references: dict) -> None:
        self._refs = references

    def resolve(self, identifier: str) -> ResolvedReference | None:
        """Look up *identifier* and return a `ResolvedReference`, or ``None``."""
        ref = self._refs.get(identifier)
        if ref is None:
            return None

        kind = ref.get("type", "")
        if kind == "topic":
            return self._resolve_topic(ref)
        if kind == "image":
            return self._resolve_image(ref)
        if kind == "video":
            return self._resolve_video(ref)
        if kind == "file":
            return self._resolve_file(ref)

        # Unknown reference type — return best‐effort.
        return ResolvedReference(
            url=ref.get("url", identifier),
            title=ref.get("title", identifier),
            kind=kind,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_topic(ref: dict) -> ResolvedReference:
        title = ref.get("title", "")
        url = ref.get("url", "")
        abstract_parts = ref.get("abstract", [])
        abstract = "".join(
            part.get("text", "") for part in abstract_parts if isinstance(part, dict)
        )
        return ResolvedReference(url=url, title=title, kind="topic", abstract=abstract)

    @staticmethod
    def _resolve_image(ref: dict) -> ResolvedReference:
        variants = ref.get("variants", [])
        # Pick the first variant URL (usually there's a 1× and 2×).
        url = variants[0]["url"] if variants else ""
        # Sanitize @2x → -2x to avoid texinfo @command collision.
        url = url.replace("@", "-")
        alt = ref.get("alt", "")
        return ResolvedReference(url=url, title=alt, kind="image")

    @staticmethod
    def _resolve_video(ref: dict) -> ResolvedReference:
        variants = ref.get("variants", [])
        url = variants[0]["url"] if variants else ""
        return ResolvedReference(url=url, title="", kind="video")

    @staticmethod
    def _resolve_file(ref: dict) -> ResolvedReference:
        url = ref.get("url", "")
        title = ref.get("title", ref.get("identifier", ""))
        return ResolvedReference(url=url, title=title, kind="file")
