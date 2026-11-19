"""Layering rules checked on the import graph (AST, no execution)."""

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _imports(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield node.module.split(".")[0]


def _modules(package):
    return sorted((ROOT / package).rglob("*.py"))


def test_core_is_framework_free():
    banned = {"fastapi", "starlette", "pydantic", "jwt", "sqlalchemy", "tkinter", "app", "gui",
              "random", "numpy", "sympy"}
    for path in _modules("pcss"):
        assert not banned & set(_imports(path)), path


def test_services_security_storage_do_not_depend_on_http():
    for package in ("app/services", "app/security", "app/storage"):
        for path in _modules(package):
            assert not {"fastapi", "starlette"} & set(_imports(path)), path


def test_gui_does_not_depend_on_app_layer():
    for path in _modules("gui"):
        assert not {"app", "fastapi", "sqlalchemy", "jwt"} & set(_imports(path)), path


def test_api_does_not_do_field_arithmetic():
    """Routers call services; they must not import the algorithm modules directly."""
    for path in _modules("app/api"):
        imported = {n.module for n in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
                    if isinstance(n, ast.ImportFrom) and n.module}
        assert not {m for m in imported if m.startswith("pcss.") and m != "pcss.errors"}, path
