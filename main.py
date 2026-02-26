import os
import sys
from pathlib import Path

# Add src to python path so we can import docc_parser
sys.path.insert(0, str(Path(__file__).parent / "src"))

from docc_parser.bridge import parse_catalog
from docc_parser.converter import convert

def main():
    print("Finding a .docc catalog to parse...")
    
    # Use the SwiftDocC test catalog from earlier
    catalog_path = Path("/Users/zeke/docc-to-docutils/vendor/swift-docc/Sources/SwiftDocC/SwiftDocC.docc")
    
    if not catalog_path.exists():
        print(f"Catalog not found at {catalog_path}")
        return

    print("Parsing catalog in-memory via SwiftDocC C-ABI bridge...")
    try:
        nodes = parse_catalog(catalog_path)
    except Exception as e:
        print(f"Error parsing catalog: {e}")
        return
        
    print(f"Successfully received {len(nodes)} RenderNodes from the bridge!")
    
    # Let's try converting the first one to a docutils document
    for node in nodes[:1]:
        print(f"\nProcessing node title: {node.get('metadata', {}).get('title')}")
        doc = convert(node, source="<in-memory-docc>")
        print("Generated docutils document:")
        print(doc.pformat())

if __name__ == "__main__":
    main()
