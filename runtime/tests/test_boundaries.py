"""The runtime reaches persistence only through its ports: no DB drivers or W2 internals.

The one exception is `runtime/demo.py`, the demo's composition root, which wires W2's adapters in
(it never calls a database driver itself); tests may use the offline adapters too.
The same file is also the only one that may name W5's hidden truth files: its call simulator reads
contact truth and its scoring step hands the rest to W4. Runtime logic never sees them.
"""

import ast
from pathlib import Path

RUNTIME_DIR = Path(__file__).resolve().parents[1]
DRIVERS = ("surrealdb", "pymongo", "motor", "bson", "gridfs", "mongomock", "langgraph.checkpoint.mongodb")
W2_INTERNALS = ("db", "memory")
COMPOSITION_ROOTS = {Path("demo.py")}
TRUTH_MARKERS = ("_truth", "needles", "decoys", "personas")  # contact_truth, households_truth, event_truth, ...


def imported_modules(path: Path) -> set[str]:
    names = set()
    for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def _matches(name: str, roots: tuple[str, ...]) -> bool:
    return any(name == root or name.startswith(f"{root}.") for root in roots)


def test_no_direct_db_implementation_in_runtime():
    sources = sorted(RUNTIME_DIR.rglob("*.py"))
    assert len(sources) > 5  # the scan really sees the package
    offenders = []
    for path in sources:
        relative = path.relative_to(RUNTIME_DIR)
        wiring = relative in COMPOSITION_ROOTS or relative.parts[0] == "tests"
        for name in imported_modules(path):
            if _matches(name, DRIVERS) or (not wiring and _matches(name, W2_INTERNALS)):
                offenders.append(f"{relative}: {name}")
    assert not offenders, offenders


def string_literals(path: Path) -> list[str]:
    """Every string constant in the module except docstrings."""
    tree = ast.parse(path.read_text(), filename=str(path))
    docstrings = {id(node.body[0].value) for node in ast.walk(tree)
                  if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                  and node.body and isinstance(node.body[0], ast.Expr)}
    return [node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings]


def test_only_the_demo_composition_names_hidden_truth_files():
    offenders = []
    for path in sorted(RUNTIME_DIR.rglob("*.py")):
        relative = path.relative_to(RUNTIME_DIR)
        if relative in COMPOSITION_ROOTS or relative.parts[0] == "tests":
            continue
        offenders += [f"{relative}: {text!r}" for text in string_literals(path)
                      if any(marker in text for marker in TRUTH_MARKERS)]
    assert not offenders, offenders
