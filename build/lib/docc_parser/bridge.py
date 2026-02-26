"""C ABI Bridge to libswiftdocc."""

import ctypes
import json
import os
from pathlib import Path
from typing import List, Dict, Any

CALLBACK_FUNC = ctypes.CFUNCTYPE(None, ctypes.c_int32, ctypes.c_char_p)

class DocCBridgeError(Exception):
    """Raised when the Swift DocC bridge encounters an error."""
    pass

def get_dylib_path() -> Path:
    """Find the libDocCBridge dynamic library.
    For now, we assume it is in the current working directory.
    """
    path = Path.cwd() / "libDocCBridge.dylib"
    if not path.exists():
        # Fallback for linux extensions
        path = Path.cwd() / "libDocCBridge.so"
    if not path.exists():
        raise FileNotFoundError(f"Could not find libDocCBridge.dylib or .so in {Path.cwd()}")
    return path

def parse_catalog(catalog_path: str | Path) -> List[Dict[str, Any]]:
    """Parse a .docc catalog into a list of RenderNode JSON dictionaries."""
    dylib_path = get_dylib_path()
    lib = ctypes.CDLL(str(dylib_path))
    
    lib.parse_docc_catalog.argtypes = [ctypes.c_char_p, CALLBACK_FUNC]
    lib.parse_docc_catalog.restype = None

    nodes: List[Dict[str, Any]] = []
    errors: List[str] = []

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
