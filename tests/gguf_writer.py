"""Writes a GGUF header (no tensor) for the tests: `write_gguf(path, metadata)`.

Integers are uint32 (a negative one int32), floats float32, booleans bool, strings UTF-8,
lists arrays of uint32 (or of strings). Enough for `wavestack.models.gguf_meta`.
"""

from __future__ import annotations

import struct
import sys
import warnings
from pathlib import Path
from typing import Any


def make_sparse(path: Path, size: int) -> None:
    """Extends (or creates) the file to `size` bytes without writing them.

    On NTFS a file is only sparse with the sparse flag: without it `truncate` writes the
    zeros (seconds per GB). The flag needs no admin rights. Elsewhere `truncate` is enough.
    The size stays real: the code under test reads it with a plain `stat`.
    """
    path = Path(path)
    path.touch()  # keeps an existing header: callers write the GGUF header first
    with open(path, "r+b") as f:
        if sys.platform == "win32":
            import ctypes
            import msvcrt
            from ctypes import wintypes

            fsctl_set_sparse = 0x900C4
            returned = wintypes.DWORD(0)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.DeviceIoControl.argtypes = [
                wintypes.HANDLE,
                wintypes.DWORD,
                wintypes.LPVOID,
                wintypes.DWORD,
                wintypes.LPVOID,
                wintypes.DWORD,
                ctypes.POINTER(wintypes.DWORD),
                wintypes.LPVOID,
            ]
            # Best effort: without the flag the file is still correct, only slower.
            if not kernel32.DeviceIoControl(
                msvcrt.get_osfhandle(f.fileno()),
                fsctl_set_sparse,
                None,
                0,
                None,
                0,
                ctypes.byref(returned),
                None,
            ):
                warnings.warn("sparse flag refused: the file will be written in full", stacklevel=2)
        if sys.platform == "win32" and size > path.stat().st_size:
            # `truncate` (SetEndOfFile) still takes ~1 s/GB on NTFS, even flagged sparse;
            # writing the last byte extends the file at once (measured: 5 GiB in < 10 ms).
            f.seek(size - 1)
            f.write(b"\0")
        else:
            f.truncate(size)


def _string(text: str) -> bytes:
    data = text.encode("utf-8")
    return struct.pack("<Q", len(data)) + data


def _typed(value: Any) -> tuple[int, bytes]:
    if isinstance(value, bool):
        return 7, struct.pack("<?", value)
    if isinstance(value, int):
        return (5, struct.pack("<i", value)) if value < 0 else (4, struct.pack("<I", value))
    if isinstance(value, float):
        return 6, struct.pack("<f", value)
    if isinstance(value, str):
        return 8, _string(value)
    if isinstance(value, list):
        inner = 8 if value and isinstance(value[0], str) else 4
        items = b"".join(_typed(v)[1] for v in value)
        return 9, struct.pack("<IQ", inner, len(value)) + items
    raise TypeError(value)


def write_gguf(path: Path, metadata: dict[str, Any], version: int = 3) -> Path:
    body = b""
    for key, value in metadata.items():
        kind, data = _typed(value)
        body += _string(key) + struct.pack("<I", kind) + data
    path.write_bytes(b"GGUF" + struct.pack("<IQQ", version, 0, len(metadata)) + body)
    return path
