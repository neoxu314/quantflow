"""Identify the calculation implementation independently of presentation and comments."""

import ast
import hashlib
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=256)
def _module_digest(path, file_identity):
    # Metadata invalidates the parse cache; only syntax enters the calculation hash.
    tree = ast.parse(path.read_bytes())
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if ast.get_docstring(node, clean=False) is not None:
                node.body.pop(0)
    return hashlib.sha256(ast.dump(tree).encode()).digest()


def calculation_hash(root):
    modules = []
    for package in ("config", "data", "execution", "indicators", "orchestration", "strategies"):
        modules.extend((root / package).rglob("*.py"))
    digest = hashlib.sha256()
    for path in sorted(modules):
        stat = path.stat()
        key = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
        digest.update(path.relative_to(root).as_posix().encode() + b"\0")
        digest.update(_module_digest(path, key))
    return "calc-v2:" + digest.hexdigest()


_SOURCE_ROOT = Path(__file__).resolve().parents[1]
_LOADED_HASH = calculation_hash(_SOURCE_ROOT)


def execution_hash():
    if calculation_hash(_SOURCE_ROOT) != _LOADED_HASH:
        raise ValueError("Calculation code changed while running. Restart QuantFlow.")
    return _LOADED_HASH
