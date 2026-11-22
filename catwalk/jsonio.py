"""Reading and writing the JSON and SVG files the automation owns.

Two rules keep the repository history clean and the data safe:
* Writes are atomic (temporary file + rename), so a crash never leaves half a file behind.
* A file is only rewritten when its content actually changes, so an unchanged run commits nothing.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

# Long lists of numbers (the 366 calendar days) are kept on one line: readable diffs, small files.
_NUMBER_LIST = re.compile(r"\[\n\s+((?:-?\d+(?:\.\d+)?,\n\s+)*-?\d+(?:\.\d+)?)\n\s+\]")


def dumps(data: Any) -> str:
    text = json.dumps(data, indent=2, ensure_ascii=False)
    text = _NUMBER_LIST.sub(lambda m: "[" + re.sub(r",\n\s+", ", ", m.group(1)) + "]", text)
    return text + "\n"


def read_json(path: Path) -> Any:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def read_json_or(path: Path, default: Any) -> Any:
    """Read a JSON file, or return `default` when it does not exist. A corrupt file still raises."""
    try:
        return read_json(path)
    except FileNotFoundError:
        return default


def write_text(path: Path, text: str) -> bool:
    """Write `text` atomically. Returns True when the file changed, False when it was already identical."""
    path = Path(path)
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise
    return True


def write_json(path: Path, data: Any) -> bool:
    return write_text(path, dumps(data))
