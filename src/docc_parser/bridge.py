"""C ABI Bridge to libswiftdocc."""

import ctypes
import json
from pathlib import Path
from typing import Any

CALLBACK_FUNC = ctypes.CFUNCTYPE(None, ctypes.c_int32, ctypes.c_char_p)

class DocCBridgeError(Exception):
    """Raised when the Swift DocC bridge encounters an error."""
    pass

def get_dylib_path() -> Path:
    """Find the libDocCBridge dynamic library.
    We look for it in the same directory as this file inside the python package.
    """
    pkg_dir = Path(__file__).parent
    path = pkg_dir / "libDocCBridge.dylib"
    if not path.exists():
        # Fallback for linux extensions
        path = pkg_dir / "libDocCBridge.so"
    if not path.exists():
        raise FileNotFoundError(f"Could not find libDocCBridge.dylib or .so in {pkg_dir}")
    return path

def parse_catalog(catalog_path: str | Path) -> list[dict[str, Any]]:
    """Parse a .docc catalog into a list of RenderNode JSON dictionaries."""
    dylib_path = get_dylib_path()
    lib = ctypes.CDLL(str(dylib_path))
    
    lib.parse_docc_catalog.argtypes = [ctypes.c_char_p, CALLBACK_FUNC]
    lib.parse_docc_catalog.restype = None

    nodes: list[dict[str, Any]] = []
    errors: list[str] = []

    def callback(status: int, c_string: bytes):
        if status == 0:
            if c_string:
                try:
                    nodes.append(json.loads(c_string.decode('utf-8')))
                except json.JSONDecodeError as e:
                    errors.append(f"Failed to decode JSON from RenderNode: {e}")
        elif status == 1:
            if c_string:
                errors.append(c_string.decode('utf-8'))
        elif status == 2:
            # Success completion
            pass
        else:
            errors.append(f"Unknown status code from bridge: {status}")

    c_callback = CALLBACK_FUNC(callback)
    lib.parse_docc_catalog(str(catalog_path).encode('utf-8'), c_callback)

    if errors:
        raise DocCBridgeError("\n".join(errors))
    
    return nodes
