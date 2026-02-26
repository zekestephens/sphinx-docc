"""CLI entry point for docc2docutils."""

import argparse
import sys
from pathlib import Path

from docutils.core import publish_from_doctree

from .converter import convert_file


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="docc2docutils",
        description="Convert DocC RenderNode JSON to docutils XML.",
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Path to a .doccarchive directory or a single RenderNode JSON file.",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        help="Output file (single) or directory (archive). Defaults to stdout.",
    )
    parser.add_argument(
        "-f", "--format",
        choices=["xml", "html", "pseudoxml"],
        default="xml",
        help="Output format (default: xml).",
    )

    args = parser.parse_args(argv)
    input_path: Path = args.input
    output_path: Path | None = args.output

    if input_path.is_file():
        _convert_single(input_path, output_path, args.format)
    elif input_path.is_dir():
        _convert_archive(input_path, output_path, args.format)
    else:
        print(f"error: {input_path} is not a file or directory", file=sys.stderr)
        sys.exit(1)


def _render(doc, fmt: str) -> str:
    """Render a docutils document to a string in the given format."""
    return publish_from_doctree(doc, writer_name=fmt).decode("utf-8")


def _convert_single(json_path: Path, output_path: Path | None, fmt: str) -> None:
    doc = convert_file(json_path)
    result = _render(doc, fmt)

    if output_path is None:
        sys.stdout.write(result)
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(result, encoding="utf-8")


def _convert_archive(archive_path: Path, output_dir: Path | None, fmt: str) -> None:
    data_dir = archive_path / "data"
    if not data_dir.is_dir():
        print(f"error: {archive_path} does not contain a data/ directory", file=sys.stderr)
        sys.exit(1)

    if output_dir is None:
        output_dir = Path("output")

    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = ".html" if fmt == "html" else ".xml"

    json_files = sorted(data_dir.rglob("*.json"))
    if not json_files:
        print(f"warning: no JSON files found in {data_dir}", file=sys.stderr)
        return

    converted = 0
    for json_file in json_files:
        rel = json_file.relative_to(data_dir)
        out_file = output_dir / rel.with_suffix(suffix)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            doc = convert_file(json_file)
            result = _render(doc, fmt)
            out_file.write_text(result, encoding="utf-8")
            converted += 1
        except Exception as exc:
            print(f"warning: failed to convert {rel}: {exc}", file=sys.stderr)

    print(f"Converted {converted}/{len(json_files)} files to {output_dir}")


if __name__ == "__main__":
    main()
