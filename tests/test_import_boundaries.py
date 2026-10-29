"""ADR-0001 test 1: the module allow-list, enforced on the source with `ast`.

Each module may import EXACTLY the volbt modules on its row of the ADR-0001 table, and no
others. The table below is that table. The checker parses every file under src/volbt/ (it
imports nothing), and it fails if:

- a module imports a volbt module that is not on its row;
- a module breaks its third-party limit (pricing: numpy, scipy, stdlib; config, contract and
  view: stdlib only; illustrative: numpy);
- a file belongs to no row;
- anywhere in volbt: importlib is imported; `__import__` appears as a name, an attribute or a
  string (`builtins.__import__`, `getattr(b, '__import__')`); sys.modules is referenced, under
  any name `sys` was imported or assigned as (`S = sys`) or as an attribute (`os.sys.modules`);
  or getattr/setattr/delattr is given an attribute name that is not a string literal
  (`getattr(b, '__imp' + 'ort__')` builds the name the string test looks for);
- in strategies and signals, an ALLOW-LIST (round 2 of the M1 review: a list of banned modules
  kept leaking, through `os.sys.modules`, `typing.get_type_hints`, `timeit`, `subprocess`...):
  - an import that is not the row's volbt modules, `__future__`, the stdlib modules math,
    statistics, dataclasses, enum, collections, itertools, functools, datetime and abc, or
    numpy. typing only as `from typing import <name>` for the names in TYPING_NAMES. No star
    import, and no import of a file reader by name (`from numpy import load`);
  - getattr/setattr/delattr, vars/globals/locals, exec/eval/compile is named at all, as a name
    or as an attribute (`g = getattr` is the same back door, and `enum.bltns.exec` is builtins'
    exec); `__builtins__`, `__loader__` or `__spec__` is named;
  - an attribute named in BANNED_ATTRIBUTES is used, on any object, `self` included: `sys`,
    `modules`, the dunders that reach a namespace, a class or a frame, `load_module`, and the
    modules that allowed modules carry as attributes (`dataclasses.inspect`, `enum.bltns`);
  - a file is opened: `open`, `read_parquet`, `read_csv`, `connect`, or a numpy file reader
    (`np.load`, `np.fromfile`...) on an imported name;
  - anything is written through an imported name, or a name assigned from one: an assignment,
    augmented assignment or `del` of an attribute or item of `vv` after `import volbt.view as vv`
    (the reviewer's `vv.exact_date = ...` and `vv.SPLITS[...] = ...`);
  - an annotation holds a string: typing.get_type_hints and functools.singledispatch evaluate it
    as code, out of this checker's sight (`from __future__ import annotations` keeps every
    annotation an expression the checker reads);
  - a private attribute (a name starting with "_") is read, except on a method's first
    parameter inside that method (self or cls, whatever it is called), and only if the method
    never rebinds that name, has no decorator but property, classmethod, abstractmethod,
    cached_property or a property's setter/getter/deleter (`sm = staticmethod; @sm` gets no
    exemption), and the name is not a dunder (`self.__closure__` is reflection, not state).
    A class pattern (`case object(_read=r)`) reads the attribute too and gets no exemption;
  - a method that uses that exemption is reached through its class (`S.peek(view)`,
    `M.r(view)`): called that way its first parameter can be any object, the view included;
  Each is a way round the allow-list;
- the table itself has a cycle.

THE THREAT MODEL (ADR-0001 test 1). This is a tripwire for accidental and casual misuse in our
own strategy and signal code, not a sandbox: deliberate subversion of Python cannot be stopped
by reading the source. The behavioural guard is the perturb-the-future test (ADR-0001 test 6),
which strategies get in M4. ADR-0001 lists the paths known to be still open.

Then each required mutant (ADR-0001, "Required mutants") is written into a copy of the source,
and the checker must report it, and so must every probe of the M1 review's two rounds.
"""

from __future__ import annotations

import ast
import graphlib
import shutil
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src" / "volbt"

# ADR-0001 §4, "May import (volbt)". The package root volbt/__init__.py is not a row of the
# ADR table; it may import nothing.
ALLOWED: dict[str, set[str]] = {
    "config": set(),
    "contract": set(),
    "illustrative": set(),
    "view": set(),
    "data": {"config", "view"},
    "pricing": set(),
    "build": {"config", "data", "pricing"},
    "signals": {"pricing", "view"},
    "strategies": {"pricing", "signals", "view"},
    "risk": {"pricing"},
    "engine": {"config", "data", "pricing", "signals", "strategies", "risk", "view"},
    "analytics": {"config", "pricing"},
    "export": {"analytics", "contract"},
}
ROOT = "__root__"
# ADR-0001 §4, "Third-party limit". A row not listed here has no limit.
THIRD_PARTY: dict[str, set[str]] = {
    "config": set(), "contract": set(), "view": set(), ROOT: set(),
    "illustrative": {"numpy"},
    "pricing": {"numpy", "scipy"},
}
GUARDED = {"strategies", "signals"}
# ADR-0001 §4, strategies and signals: everything else they may import, besides their volbt row.
# No pandas: the view hands them DataFrames, whose methods need no import, and pandas would bring
# read_parquet with it. typing is listed apart, because only some of its names are safe.
GUARDED_IMPORTS = {"__future__", "math", "statistics", "dataclasses", "enum", "collections", "itertools",
                   "functools", "datetime", "abc", "numpy"}
# `from typing import X` for these X only. Not get_type_hints (it evaluates a string annotation as
# code) and not ForwardRef; `import typing` is refused, since typing.sys.modules is one attribute away.
TYPING_NAMES = {"TYPE_CHECKING", "Any", "Callable", "ClassVar", "Final", "Generic", "Iterable", "Iterator",
                "Literal", "Mapping", "MutableMapping", "NamedTuple", "Optional", "Protocol", "Sequence",
                "Tuple", "TypeVar", "TypedDict", "Union", "cast", "overload"}
DYNAMIC_CALLS = {"getattr", "setattr", "delattr", "vars", "globals", "locals"}
# Each runs code from a string, which this checker never sees.
CODE_FROM_TEXT = {"exec", "eval", "compile"}
# Module globals that hand over a loader, a module spec or the builtins.
BANNED_NAMES = {"__builtins__", "__loader__", "__spec__"}
# Attribute names refused on ANY object in strategies and signals, a method's own first parameter
# included. sys and modules: sys.modules under any route (`os.sys`, `typing.sys`, `S = sys`). The
# dunders reach a namespace, a class, its subclasses or a loader; f_back and f_globals walk the
# frames; load_module imports a file. The last line: modules that the allowed modules carry as
# attributes (dataclasses.inspect, dataclasses.types, enum.bltns is builtins) and builtins'
# own names reached as attributes (`enum.bltns.exec`).
BANNED_ATTRIBUTES = {"sys", "modules", "__loader__", "__spec__", "__builtins__", "__globals__", "__dict__",
                     "__class__", "__subclasses__", "f_back", "f_globals", "f_locals", "load_module",
                     "inspect", "types", "bltns", "builtins", "__import__", *DYNAMIC_CALLS, *CODE_FROM_TEXT}
# Reading a file reaches the store's parquet with no view in between.
FILE_READERS = {"open", "read_parquet", "read_csv", "connect"}
# numpy's file readers, refused as an attribute of an imported name (`np.load`) or by name in an import.
NUMPY_FILE_READERS = {"load", "loadtxt", "genfromtxt", "fromfile", "fromregex", "memmap", "read_array",
                      "open_memmap", "ctypeslib"}
# Method decorators that keep a method's first parameter the instance (or, for classmethod, the class).
EXEMPTING_DECORATORS = {"property", "classmethod", "abstractmethod", "cached_property"}
PROPERTY_PARTS = {"setter", "getter", "deleter"}


def row_and_package(path: Path, src: Path) -> tuple[str | None, str]:
    """(table row, the package a relative import starts from) for one file."""
    parts = path.relative_to(src).with_suffix("").parts
    if parts == ("__init__",):
        return ROOT, "volbt"
    module = ".".join(("volbt", *parts))
    is_package = parts[-1] == "__init__"
    if is_package:
        module = module.rsplit(".", 1)[0]
    package = module if is_package else module.rsplit(".", 1)[0]
    row = parts[0]
    return (row if row in ALLOWED else None), package


def imported_modules(tree: ast.AST, package: str) -> list[tuple[int, str]]:
    """(line, absolute dotted name) for every import, relative ones resolved against `package`."""
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [(node.lineno, alias.name) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.split(".")
                base = base[: len(base) - (node.level - 1)]
                prefix = ".".join(base)
                module = f"{prefix}.{node.module}" if node.module else prefix
            else:
                module = node.module or ""
            if module == "volbt":
                # `from volbt import data` imports the submodule volbt.data.
                found += [(node.lineno, f"volbt.{alias.name}") for alias in node.names]
            else:
                found.append((node.lineno, module))
    return found


def binds(node: ast.AST, name: str) -> bool:
    """True if `node` (re)binds `name` in any way: assignment, parameter, import, except, match, global."""
    if isinstance(node, ast.Name):
        return node.id == name and isinstance(node.ctx, (ast.Store, ast.Del))
    if isinstance(node, ast.arg):
        return node.arg == name
    if isinstance(node, ast.alias):
        return (node.asname or node.name.split(".")[0]) == name
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return node.name == name
    if isinstance(node, ast.ExceptHandler):
        return node.name == name
    if isinstance(node, (ast.MatchAs, ast.MatchStar)):
        return node.name == name
    if isinstance(node, ast.MatchMapping):
        return node.rest == name
    if isinstance(node, (ast.Global, ast.Nonlocal)):
        return name in node.names
    return False


def is_dunder(name: str) -> bool:
    return name.startswith("__") and name.endswith("__")


def exempting(decorator: ast.expr) -> bool:
    """True for @property, @classmethod, @abstractmethod, @cached_property (bare or as `abc.`/`functools.`), @x.setter."""
    if isinstance(decorator, ast.Name):
        return decorator.id in EXEMPTING_DECORATORS
    if isinstance(decorator, ast.Attribute):
        return decorator.attr in PROPERTY_PARTS or (
            decorator.attr in EXEMPTING_DECORATORS and isinstance(decorator.value, ast.Name)
            and decorator.value.id in {"abc", "functools"})
    return False


def exempt_methods(tree: ast.AST) -> list[tuple[ast.FunctionDef, bool, set[int]]]:
    """(method, is a classmethod, id() of each exempt `p._x` node) for every method with an exemption.

    A method is a def directly in a class body, with at least one positional parameter and no
    decorator but the exempting ones (a staticmethod, or any decorator the checker cannot read,
    gets none). Its first parameter's private, non-dunder attributes are exempt only inside that
    method, and only if nothing in the method rebinds the name (an assignment, a nested def or
    lambda taking it as a parameter, a comprehension variable...).
    """
    found = []
    for cls in (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)):
        for method in cls.body:
            if not isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not all(exempting(d) for d in method.decorator_list):
                continue
            positional = [*method.args.posonlyargs, *method.args.args]
            if not positional:
                continue
            first = positional[0].arg
            inside = [n for statement in method.body for n in ast.walk(statement)]
            if any(binds(n, first) for n in inside):
                continue
            exempt = {id(n) for n in inside if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
                      and n.value.id == first and not is_dunder(n.attr)}
            is_classmethod = any(isinstance(d, ast.Name) and d.id == "classmethod" for d in method.decorator_list)
            found.append((method, is_classmethod, exempt))
    return found


def own_attribute_reads(tree: ast.AST) -> set[int]:
    """id() of every `p._x` node where p is the first parameter of the method the node sits in (exempt_methods)."""
    return {node_id for _, _, exempt in exempt_methods(tree) for node_id in exempt}


def chain_root(node: ast.AST, through_items: bool) -> str | None:
    """The name at the bottom of `a.b.c` (and of `a[i].b` when through_items), else None."""
    while isinstance(node, ast.Attribute) or (through_items and isinstance(node, ast.Subscript)):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def with_aliases(tree: ast.AST, names: set[str]) -> set[str]:
    """`names` plus every name assigned one of them, or an attribute of one (`S = sys`, `m = vv.sub`).

    A value that is a call or an item (`np.zeros(3)`, `vv.SPLITS["x"]`) is a new object, not an alias.
    """
    names = set(names)
    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                targets, value = node.targets, node.value
            elif isinstance(node, (ast.NamedExpr, ast.AnnAssign)) and node.value is not None:
                targets, value = [node.target], node.value
            else:
                continue
            if chain_root(value, through_items=False) in names:
                for target in targets:
                    if isinstance(target, ast.Name) and target.id not in names:
                        names.add(target.id)
                        changed = True
    return names


def annotations(tree: ast.AST) -> list[ast.expr]:
    """Every annotation: of parameters, of return values, and of annotated assignments."""
    found = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            arguments = node.args
            params = [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs,
                      *(a for a in (arguments.vararg, arguments.kwarg) if a is not None)]
            found += [a.annotation for a in params if a.annotation is not None]
            if not isinstance(node, ast.Lambda) and node.returns is not None:
                found.append(node.returns)
        elif isinstance(node, ast.AnnAssign):
            found.append(node.annotation)
    return found


def guarded_import_problems(tree: ast.AST, package: str, where: str, row: str) -> list[str]:
    """The allow-list of strategies and signals, applied to every import statement."""
    problems = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        names = [alias.name for alias in node.names]
        if isinstance(node, ast.ImportFrom):
            if "*" in names:
                problems.append(f"{where}:{node.lineno}: star import is banned in {row}: name what you use")
            module = node.module or ""
            if node.level == 0 and module == "typing":
                problems += [f"{where}:{node.lineno}: {row} may not import {name} from typing" for name in names
                             if name not in TYPING_NAMES and name != "*"]
            problems += [f"{where}:{node.lineno}: {row} may not import the file reader {name}" for name in names
                         if name in NUMPY_FILE_READERS | FILE_READERS]
            problems += [f"{where}:{node.lineno}: {row} may not import {name}" for name in names
                         if name in BANNED_ATTRIBUTES | BANNED_NAMES]
        resolved = imported_modules(ast.Module(body=[node], type_ignores=[]), package)
        for line, name in resolved:
            top = name.split(".")[0]
            if top in ("volbt", "importlib"):
                continue                      # the checks every row gets
            if top == "typing" and isinstance(node, ast.Import):
                problems.append(f"{where}:{line}: {row} may not import typing itself (typing.sys, "
                                f"typing.get_type_hints); write `from typing import <name>`")
            elif top != "typing" and top not in GUARDED_IMPORTS:
                problems.append(f"{where}:{line}: {row} may not import {top}: not on its allow-list "
                                f"(ADR-0001 test 1)")
    return problems


def violations(src: Path = SRC) -> list[str]:
    problems = []
    for path in sorted(src.rglob("*.py")):
        where = path.relative_to(src).as_posix()
        row, package = row_and_package(path, src)
        if row is None:
            problems.append(f"{where}: belongs to no row of the ADR-0001 table")
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=where)
        allowed = ALLOWED.get(row, set())
        for line, name in imported_modules(tree, package):
            top = name.split(".")[0]
            if top == "importlib":
                problems.append(f"{where}:{line}: importlib is banned in volbt")
            elif top == "volbt":
                parts = name.split(".")
                if len(parts) == 1:
                    problems.append(f"{where}:{line}: bare `import volbt` reaches every submodule; import what you need")
                    continue
                target = parts[1]
                if target not in ALLOWED:
                    problems.append(f"{where}:{line}: imports volbt.{target}, which is not a table row")
                elif target != row and target not in allowed:
                    problems.append(f"{where}:{line}: {row} may not import {target}")
            elif row not in GUARDED and top not in sys.stdlib_module_names and row in THIRD_PARTY \
                    and top not in THIRD_PARTY[row]:
                problems.append(f"{where}:{line}: {row} may not import third-party {top}")
        if row in GUARDED:
            problems += guarded_import_problems(tree, package, where, row)
        # Every name `sys` was imported as (`import sys as s`, `from os import sys`), and every name
        # assigned one of those (`S = sys`), so `S.modules` is caught too.
        sys_names = with_aliases(tree, {alias.asname or alias.name for node in ast.walk(tree)
                                        if isinstance(node, (ast.Import, ast.ImportFrom))
                                        for alias in node.names if alias.name == "sys"})
        for node in ast.walk(tree):
            # Everywhere in volbt: __import__ by name, by attribute or by string, and sys.modules.
            if (isinstance(node, ast.Name) and node.id == "__import__") or \
                    (isinstance(node, ast.Attribute) and node.attr == "__import__") or \
                    (isinstance(node, ast.Constant) and node.value == "__import__"):
                problems.append(f"{where}:{node.lineno}: __import__ is banned in volbt")
            if (isinstance(node, ast.Attribute) and node.attr == "modules"
                    and ((isinstance(node.value, ast.Name) and node.value.id in sys_names)
                         or (isinstance(node.value, ast.Attribute) and node.value.attr == "sys"))) or \
                    (isinstance(node, ast.ImportFrom) and node.module == "sys"
                     and any(alias.name == "modules" for alias in node.names)):
                problems.append(f"{where}:{node.lineno}: sys.modules is banned in {row}")
            # `getattr(b, '__imp' + 'ort__')` builds the name the string test above looks for.
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                    and node.func.id in {"getattr", "setattr", "delattr"} \
                    and not (len(node.args) >= 2 and isinstance(node.args[1], ast.Constant)
                             and isinstance(node.args[1].value, str)):
                problems.append(f"{where}:{node.lineno}: {node.func.id}() with a computed attribute name is banned in volbt")
        if row in GUARDED:
            problems += guarded_problems(tree, where, row)
    return problems


def guarded_problems(tree: ast.AST, where: str, row: str) -> list[str]:
    """Every rule of strategies and signals beyond the imports (the module docstring lists them)."""
    problems = []
    methods = exempt_methods(tree)
    own_reads = {node_id for _, _, exempt in methods for node_id in exempt}
    imported = with_aliases(tree, {alias.asname or alias.name.split(".")[0] for node in ast.walk(tree)
                                   if isinstance(node, (ast.Import, ast.ImportFrom))
                                   for alias in node.names if alias.name != "*"})
    classes = with_aliases(tree, {n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)})
    # Methods that read their first parameter's private attributes. Reached through the class,
    # that parameter can be handed any object; a classmethod binds its class whatever the route.
    risky = {method.name for method, is_classmethod, exempt in methods if exempt and not is_classmethod}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in DYNAMIC_CALLS | CODE_FROM_TEXT:
            problems.append(f"{where}:{node.lineno}: {node.id}() is banned in {row}")
        if isinstance(node, ast.Name) and node.id in BANNED_NAMES:
            problems.append(f"{where}:{node.lineno}: {node.id} is banned in {row}")
        if isinstance(node, ast.Name) and node.id in FILE_READERS:
            problems.append(f"{where}:{node.lineno}: {node.id}() reads a file; it is banned in {row}")
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("_") and id(node) not in own_reads:
                problems.append(f"{where}:{node.lineno}: private attribute .{node.attr} read in {row}")
            if node.attr in BANNED_ATTRIBUTES:
                problems.append(f"{where}:{node.lineno}: attribute .{node.attr} is banned in {row}")
            if node.attr in FILE_READERS or (node.attr in NUMPY_FILE_READERS
                                             and chain_root(node.value, through_items=True) in imported):
                problems.append(f"{where}:{node.lineno}: .{node.attr} reads a file; it is banned in {row}")
            if isinstance(node.ctx, ast.Load) and isinstance(node.value, ast.Name) and node.value.id in classes \
                    and node.attr in risky:
                problems.append(f"{where}:{node.lineno}: {node.value.id}.{node.attr} reads private attributes of "
                                f"its first parameter; reached through the class, that parameter can be any "
                                f"object (call it on an instance) in {row}")
        if isinstance(node, (ast.Attribute, ast.Subscript)) and isinstance(node.ctx, (ast.Store, ast.Del)):
            root = chain_root(node, through_items=True)
            if root in imported:
                problems.append(f"{where}:{node.lineno}: {row} may not write through an imported name ({root})")
        if isinstance(node, ast.MatchClass):
            for attr in (a for a in node.kwd_attrs if a.startswith("_")):
                problems.append(f"{where}:{node.lineno}: private attribute .{attr} read in {row} (class pattern)")
    for annotation in annotations(tree):
        for node in ast.walk(annotation):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                problems.append(f"{where}:{node.lineno}: a quoted annotation is code that typing.get_type_hints "
                                f"evaluates; it is banned in {row} (use `from __future__ import annotations`)")
    return problems


def test_the_real_source_has_no_violations():
    assert violations() == []


def test_every_row_has_a_module():
    rows = {row_and_package(p, SRC)[0] for p in SRC.rglob("*.py")}
    assert set(ALLOWED) <= rows


def test_the_table_has_no_cycle():
    graphlib.TopologicalSorter(ALLOWED).prepare()


def test_a_cycle_in_the_table_is_detected():
    cyclic = {**ALLOWED, "pricing": {"build"}}   # build -> pricing -> build
    with pytest.raises(graphlib.CycleError):
        graphlib.TopologicalSorter(cyclic).prepare()


def test_strategies_and_signals_cannot_reach_data_through_their_allowed_imports():
    # The transitive closure of what strategies and signals may import must not contain data.
    def reach(row, seen=None):
        seen = set() if seen is None else seen
        for target in ALLOWED[row]:
            if target not in seen:
                seen.add(target)
                reach(target, seen)
        return seen

    assert "data" not in reach("strategies")
    assert "data" not in reach("signals")


@pytest.fixture
def mutable_src(tmp_path):
    copy = tmp_path / "volbt"
    shutil.copytree(SRC, copy, ignore=shutil.ignore_patterns("__pycache__"))
    return copy


def mutate(src: Path, relative: str, line: str) -> None:
    path = src / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    path.write_text(existing + "\n" + line + "\n", encoding="utf-8")


# ADR-0001's required mutants first, then more ways round the rules.
@pytest.mark.parametrize("relative, line, expected", [
    ("strategies/__init__.py", "import volbt.data", "strategies may not import data"),
    ("risk/__init__.py", "import volbt.strategies", "risk may not import strategies"),
    ("pricing/__init__.py", "import volbt.engine", "pricing may not import engine"),
    ("signals/__init__.py", "from ..data import store", "signals may not import data"),
    ("pricing/__init__.py", "import duckdb", "pricing may not import third-party duckdb"),
    ("strategies/__init__.py", "import sys\nx = sys.modules['volbt.data']", "sys.modules is banned in strategies"),
    ("signals/__init__.py", "x = getattr(view, '_store')", "getattr() is banned in signals"),
    # beyond the required list
    ("strategies/__init__.py", "from volbt import data", "strategies may not import data"),
    ("strategies/__init__.py", "from volbt.data.store import view", "strategies may not import data"),
    ("signals/__init__.py", "from .. import data", "signals may not import data"),
    ("strategies/__init__.py", "import volbt", "bare `import volbt`"),
    ("strategies/__init__.py", "x = view._read", "private attribute ._read read in strategies"),
    ("signals/__init__.py", "x = view.__class__", "private attribute .__class__ read in signals"),
    ("signals/__init__.py", "from sys import modules", "sys.modules is banned in signals"),
    ("strategies/__init__.py", "x = vars(view)", "vars() is banned in strategies"),
    ("engine/__init__.py", "m = __import__('volbt.data')", "__import__ is banned"),
    ("data/store.py", "import importlib", "importlib is banned"),
    ("config.py", "import numpy", "config may not import third-party numpy"),
    ("view.py", "import pandas", "view may not import third-party pandas"),
    ("data/calendar.py", "from volbt import engine", "data may not import engine"),
    ("build.py", "import volbt.strategies", "build may not import strategies"),
    ("export/__init__.py", "import volbt.data", "export may not import data"),
    ("stray.py", "x = 1", "stray.py: belongs to no row"),
])
def test_each_mutant_is_caught(mutable_src, relative, line, expected):
    assert violations(mutable_src) == []          # the copy starts clean
    mutate(mutable_src, relative, line)
    found = violations(mutable_src)
    assert any(expected in problem for problem in found), found


# The M1 reviewer's 15 probe cases (ast_bypass.py), each as it was written, then variants of the
# same back doors. Every one was missed before the R3 fix except cls_param and from_dot_star.
@pytest.mark.parametrize("relative, line, expected", [
    ("strategies/__init__.py", "exec('import volbt.data as d')", "exec() is banned in strategies"),
    ("signals/__init__.py", "d = eval(\"__builtins__['__im' + 'port__']('volbt.data')\")", "eval() is banned in signals"),
    ("strategies/__init__.py", "import pkgutil\nd = pkgutil.resolve_name('volbt.data.store:Store')",
     "strategies may not import pkgutil"),
    ("strategies/__init__.py", "import pydoc\nd = pydoc.locate('volbt.data.store.Store')", "strategies may not import pydoc"),
    ("strategies/__init__.py", "import pickle\nS = pickle.loads(b'cvolbt.data.store\\nStore\\n.')",
     "strategies may not import pickle"),
    ("signals/__init__.py", "import operator\ndef f(view): return operator.attrgetter('_read')(view)",
     "signals may not import operator"),
    ("strategies/__init__.py", "def peek(self):\n    return self._read\n", "private attribute ._read read in strategies"),
    ("signals/__init__.py", "def peek(cls):\n    return cls._read.__closure__[0].cell_contents\n",
     "private attribute ._read read in signals"),
    ("strategies/__init__.py", "import inspect\ndef f(view):\n    r = dict(inspect.getmembers(view))['_read']\n"
     "    return inspect.getclosurevars(r).nonlocals['source']", "strategies may not import inspect"),
    ("signals/__init__.py", "import gc\ndef f(view): return gc.get_referents(view)", "signals may not import gc"),
    ("pricing/__init__.py", "import builtins\nm = builtins.__import__('volbt.engine')", "__import__ is banned in volbt"),
    ("risk/__init__.py", "import builtins as b\nm = getattr(b, '__import__')('volbt.strategies')", "__import__ is banned in volbt"),
    ("strategies/__init__.py", "import runpy\ng = runpy.run_module('volbt.data.store')", "strategies may not import runpy"),
    ("engine/__init__.py", "import sys\nm = sys.modules['volbt.data']", "sys.modules is banned in engine"),
    ("strategies/__init__.py", "from ..data.store import *", "strategies may not import data"),
    # variants
    ("strategies/__init__.py", "e = compile('import volbt.data', 'x', 'exec')", "compile() is banned in strategies"),
    ("strategies/__init__.py", "g = getattr\nr = g(view, '_read')", "getattr() is banned in strategies"),
    ("signals/__init__.py", "run = exec", "exec() is banned in signals"),
    ("signals/__init__.py", "e = __builtins__['eval']", "__builtins__ is banned in signals"),
    ("strategies/__init__.py", "from operator import attrgetter", "strategies may not import operator"),
    ("strategies/__init__.py", "import _operator", "strategies may not import _operator"),
    ("signals/__init__.py", "import _pickle", "signals may not import _pickle"),
    ("strategies/__init__.py", "import builtins", "strategies may not import builtins"),
    ("signals/__init__.py", "from importlib import import_module", "importlib is banned in volbt"),
    ("strategies/__init__.py", "import sys as s\nm = s.modules['volbt.data']", "sys.modules is banned in strategies"),
    ("export/__init__.py", "x = getattr(object, '__import__')", "__import__ is banned in volbt"),
    ("strategies/__init__.py", "def f(view):\n    match view:\n        case object(_read=r):\n            return r",
     "private attribute ._read read in strategies (class pattern)"),
    ("strategies/__init__.py", "class S:\n    @staticmethod\n    def peek(self):\n        return self._read",
     "private attribute ._read read in strategies"),
    ("strategies/__init__.py", "class S:\n    def peek(self, view):\n        self = view\n        return self._read",
     "private attribute ._read read in strategies"),
    ("strategies/__init__.py", "class S:\n    def peek(self, views):\n        return [self._read for self in views]",
     "private attribute ._read read in strategies"),
    ("strategies/__init__.py", "class S:\n    def peek(self, view):\n        return (lambda self: self._read)(view)",
     "private attribute ._read read in strategies"),
    ("signals/__init__.py", "class S:\n    def peek(self, view):\n        return view._read", "private attribute ._read read in signals"),
])
def test_each_review_probe_is_caught(mutable_src, relative, line, expected):
    assert violations(mutable_src) == []
    mutate(mutable_src, relative, line)
    found = violations(mutable_src)
    assert any(expected in problem for problem in found), found


def test_self_attributes_are_allowed_in_strategies(mutable_src):
    mutate(mutable_src, "strategies/__init__.py",
           "class S:\n    def __init__(self):\n        self._n = 1\n    def n(self):\n        return self._n")
    assert violations(mutable_src) == []


def test_a_method_s_first_parameter_is_exempt_whatever_its_name(mutable_src):
    # cls in a classmethod, `me` in a plain method, and a closure inside a method that uses it.
    mutate(mutable_src, "signals/__init__.py",
           "class S:\n    _k = 2\n    @classmethod\n    def k(cls):\n        return cls._k\n"
           "    def m(me):\n        return me._k\n    def later(self):\n        return lambda: self._k")
    assert violations(mutable_src) == []


def test_from_future_imports_stay_allowed_in_strategies(mutable_src):
    # __future__ starts with "_" but is not a private module.
    mutate(mutable_src, "strategies/__init__.py", "from __future__ import annotations")
    assert violations(mutable_src) == []


def test_imports_inside_a_package_are_allowed(mutable_src):
    # data.store importing data.schema is one row importing itself.
    mutate(mutable_src, "data/store.py", "from volbt.data import schema\nfrom . import flags")
    assert violations(mutable_src) == []


# Round 2 of the M1 review: every case of the reviewer's ast3.py, as it was written (20 of the 23
# were missed by the ban list), then variants of the rules that replaced it.
@pytest.mark.parametrize("relative, line, expected", [
    # sys.modules under any alias of sys
    ("strategies/__init__.py", "import os\nm = os.sys.modules['volbt.data.store']", "strategies may not import os"),
    ("strategies/__init__.py", "from os import sys\nm = sys.modules['volbt.data.store']", "strategies may not import os"),
    ("signals/__init__.py", "import typing\nm = typing.sys.modules['volbt.data.store']", "signals may not import typing itself"),
    ("strategies/__init__.py", "import sys\nS = sys\nm = S.modules['volbt.data.store']", "strategies may not import sys"),
    # monkeypatch an allowed module
    ("strategies/__init__.py", "import volbt.view as vv\nfrom datetime import date, timedelta\n"
     "_orig = vv.exact_date\nvv.exact_date = lambda v, w: date(v.year, v.month, v.day) + timedelta(days=1)",
     "strategies may not write through an imported name (vv)"),
    ("strategies/__init__.py", "import volbt.view as vv\nfrom datetime import date\n"
     "vv.SPLITS['development'] = (date(2010,1,4), date(2026,10,26))", "strategies may not write through an imported name (vv)"),
    # import without an import statement
    ("strategies/__init__.py", "L = type(__loader__)('volbt.data.store', __file__.replace('strategies/__init__.py', "
     "'data/store.py'))\nm = L.load_module()", "__loader__ is banned in strategies"),
    ("strategies/__init__.py", "import typing\ndef f(x: \"__import__('volbt.data.store', fromlist=['S']).Store\"): pass\n"
     "S = typing.get_type_hints(f)['x']", "strategies may not import typing itself"),
    ("signals/__init__.py", "import timeit\ntimeit.timeit('import volbt.data.store as s; print(s.Store)', number=1)",
     "signals may not import timeit"),
    ("risk/__init__.py", "import builtins as b\nm = getattr(b, '__imp' + 'ort__')('volbt.strategies')",
     "getattr() with a computed attribute name is banned in volbt"),
    # the reviewer's control cases, which ADR-0001 listed as open before this round
    ("strategies/__init__.py", "class S:\n    def peek(self):\n        return self._read\n    def cl(self):\n"
     "        return self.__closure__\ndef leak(view):\n    return S.cl(S.peek(view))",
     "S.peek reads private attributes of its first parameter"),
    ("strategies/__init__.py", "import string\ndef leak(view):\n    return string.Formatter().get_field('0._read.__closure__', "
     "[view], {})[0]", "strategies may not import string"),
    ("signals/__init__.py", "import traceback\ndef leak():\n    return [f.f_globals for f, _ in traceback.walk_stack(None)]",
     "signals may not import traceback"),
    ("strategies/__init__.py", "import pandas as pd\ndef leak():\n    return pd.read_parquet('data/store/option_quotes')",
     "strategies may not import pandas"),
    ("signals/__init__.py", "import duckdb\ndef leak():\n    return duckdb.sql(\"select * from "
     "'data/store/option_quotes/**/*.parquet'\").df()", "signals may not import duckdb"),
    ("strategies/__init__.py", "import subprocess\nsubprocess.run(['python', '-c', 'import volbt.data'])",
     "strategies may not import subprocess"),
    ("strategies/__init__.py", "import ctypes", "strategies may not import ctypes"),
    ("strategies/__init__.py", "import code\ncode.InteractiveInterpreter().runsource('import volbt.data')",
     "strategies may not import code"),
    ("strategies/__init__.py", "class M(type):\n    def r(cls):\n        return cls._read\ndef leak(view):\n    return M.r(view)",
     "M.r reads private attributes of its first parameter"),
    ("strategies/__init__.py", "sm = staticmethod\nclass S:\n    @sm\n    def peek(self):\n        return self._read",
     "private attribute ._read read in strategies"),
    ("strategies/__init__.py", "class S:\n    def peek(self):\n        return super()._read", "private attribute ._read read in strategies"),
    ("strategies/__init__.py", "def f(view):\n    return type(view).__dict__", "private attribute .__dict__ read in strategies"),
    ("strategies/__init__.py", "import functools\ndef f(view):\n    return functools.reduce(lambda o, n: "
     "type(o).__getattribute__(o, n), ['_read'], view)", "private attribute .__getattribute__ read in strategies"),
])
def test_each_round_2_probe_is_caught(mutable_src, relative, line, expected):
    assert violations(mutable_src) == []
    mutate(mutable_src, relative, line)
    found = violations(mutable_src)
    assert any(expected in problem for problem in found), found


@pytest.mark.parametrize("relative, line, expected", [
    # the allow-list, one rule at a time
    ("signals/__init__.py", "from typing import get_type_hints", "signals may not import get_type_hints from typing"),
    ("strategies/__init__.py", "from typing import Any, ForwardRef", "strategies may not import ForwardRef from typing"),
    ("strategies/__init__.py", "from math import *", "star import is banned in strategies"),
    ("strategies/__init__.py", "import numpy as np\nx = np.load('data/x.npy')", ".load reads a file"),
    ("signals/__init__.py", "import numpy\nx = numpy.lib.format.read_array", ".read_array reads a file"),
    ("strategies/__init__.py", "from numpy import fromfile", "strategies may not import the file reader fromfile"),
    ("strategies/__init__.py", "x = open('data/store/spy_bars/part-0.parquet', 'rb').read()", "open() reads a file"),
    ("signals/__init__.py", "def f(con):\n    return con.connect()", ".connect reads a file"),
    ("strategies/__init__.py", "def f(frame):\n    return frame.read_csv", ".read_csv reads a file"),
    ("strategies/__init__.py", "import dataclasses\nx = dataclasses.inspect", "attribute .inspect is banned in strategies"),
    ("strategies/__init__.py", "import enum\nenum.bltns.exec('import volbt.data')", "attribute .bltns is banned in strategies"),
    ("signals/__init__.py", "import enum\nx = enum.bltns", "attribute .bltns is banned in signals"),
    ("strategies/__init__.py", "import dataclasses\nm = dataclasses.sys.modules", "sys.modules is banned in strategies"),
    ("strategies/__init__.py", "x = __spec__", "__spec__ is banned in strategies"),
    ("strategies/__init__.py", "def f(frame):\n    return frame.f_back.f_globals", "attribute .f_back is banned in strategies"),
    # a method's own dunders are reflection, not state
    ("strategies/__init__.py", "class S:\n    def m(self):\n        return self.__dict__", "attribute .__dict__ is banned in strategies"),
    ("strategies/__init__.py", "class S:\n    def m(self):\n        return self.__closure__",
     "private attribute .__closure__ read in strategies"),
    # an unknown decorator gives no exemption
    ("signals/__init__.py", "import functools\nclass S:\n    @functools.cache\n    def m(self):\n        return self._k",
     "private attribute ._k read in signals"),
    # a method reached through its class, an alias of it, or a subclass
    ("strategies/__init__.py", "class S:\n    def peek(self):\n        return self._read\nK = S\ndef f(view):\n    return K.peek(view)",
     "K.peek reads private attributes"),
    ("strategies/__init__.py", "class S:\n    @property\n    def p(self):\n        return self._read\nclass T(S):\n    pass\n"
     "def f(view):\n    return T.p.fget(view)", "T.p reads private attributes"),
    # writes through an imported name: every kind of store
    ("strategies/__init__.py", "import datetime\ndatetime.date = None", "may not write through an imported name (datetime)"),
    ("strategies/__init__.py", "import volbt.view as vv\nm = vv\nm.exact_date = None", "may not write through an imported name (m)"),
    ("strategies/__init__.py", "from volbt.view import SPLITS\ndel SPLITS['holdout']", "may not write through an imported name (SPLITS)"),
    ("signals/__init__.py", "import volbt.view\nvolbt.view.SPLITS = {}", "may not write through an imported name (volbt)"),
    ("signals/__init__.py", "from volbt import view as v\nv.x += 1", "may not write through an imported name (v)"),
    ("strategies/__init__.py", "import numpy as np\ndef f():\n    for np.e in range(3):\n        pass",
     "may not write through an imported name (np)"),
    # a quoted annotation, even without typing
    ("strategies/__init__.py", "import functools\n@functools.singledispatch\ndef f(x):\n    pass\n@f.register\n"
     "def _(x: \"open('data/x').read()\"):\n    pass", "a quoted annotation is code"),
    ("signals/__init__.py", "from typing import Optional\nx: Optional['Thing'] = None", "a quoted annotation is code"),
    # every row: a computed getattr name, and sys.modules under any alias
    ("data/store.py", "name = '__imp' + 'ort__'\nx = getattr(object, name)", "getattr() with a computed attribute name"),
    ("engine/__init__.py", "import sys\nS = sys\nm = S.modules['volbt.data']", "sys.modules is banned in engine"),
    ("engine/__init__.py", "import os\nm = os.sys.modules['volbt.data']", "sys.modules is banned in engine"),
])
def test_each_rule_of_the_allow_list_is_enforced(mutable_src, relative, line, expected):
    assert violations(mutable_src) == []
    mutate(mutable_src, relative, line)
    found = violations(mutable_src)
    assert any(expected in problem for problem in found), found


def test_what_a_strategy_may_write_is_still_allowed(mutable_src):
    # The allow-list in use: the stdlib modules on it, numpy, typing's safe names, the row's volbt
    # modules, a numpy array written in place, an object's own state, and a classmethod through its class.
    mutate(mutable_src, "strategies/__init__.py", "\n".join([
        "from __future__ import annotations",
        "import math, statistics, dataclasses, enum, itertools, functools, datetime, abc",
        "import collections.abc",
        "from collections import deque",
        "from typing import Any, Protocol, TYPE_CHECKING",
        "import numpy as np",
        "from volbt.view import MarketView, LookAheadError, SPLITS",
        "import volbt.signals",
        "class Straddle:",
        "    _count = 0",
        "    def __init__(self, legs: list[int]) -> None:",
        "        self._legs = legs",
        "    @property",
        "    def legs(self) -> list[int]:",
        "        return self._legs",
        "    @classmethod",
        "    def count(cls) -> int:",
        "        return cls._count",
        "def weights(n: int) -> Any:",
        "    w = np.zeros(n)",
        "    w[0] = 1.0",
        "    w += math.sqrt(2)",
        "    return w, Straddle.count(), Straddle([1]).legs, SPLITS['holdout'], datetime.date(2024, 1, 2)",
    ]))
    assert violations(mutable_src) == []
