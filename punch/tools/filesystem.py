from __future__ import annotations

import os
from pathlib import Path


async def list_dir(path: str, pattern: str = "*") -> list[dict]:
    p = Path(path)
    items = []
    for entry in sorted(p.glob(pattern)):
        stat = entry.stat()
        items.append({
            "name": entry.name,
            "path": str(entry),
            "is_dir": entry.is_dir(),
            "size": stat.st_size,
            "modified": stat.st_mtime,
        })
    return items


async def read_file(path: str) -> str:
    return Path(path).read_text(encoding="utf-8", errors="replace")


async def write_file(path: str, content: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(content, encoding="utf-8")


async def search_files(directory: str, query: str, extensions: list[str] | None = None) -> list[dict]:
    results = []
    for root, dirs, files in os.walk(directory):
        for fname in files:
            if extensions and not any(fname.endswith(ext) for ext in extensions):
                continue
            fpath = os.path.join(root, fname)
            try:
                content = Path(fpath).read_text(encoding="utf-8", errors="replace")
                if query.lower() in content.lower():
                    # Find the line containing the match
                    for i, line in enumerate(content.split("\n")):
                        if query.lower() in line.lower():
                            results.append({
                                "path": fpath,
                                "line": i + 1,
                                "content": line.strip()[:200],
                            })
                            break
            except (PermissionError, UnicodeDecodeError):
                continue
    return results


async def file_info(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {"exists": False}
    stat = p.stat()
    return {
        "exists": True,
        "path": str(p.resolve()),
        "is_dir": p.is_dir(),
        "size": stat.st_size,
        "modified": stat.st_mtime,
    }
