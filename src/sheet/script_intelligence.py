"""Dependency-free, conservative Python source analysis for the script workspace."""

from __future__ import annotations

import ast
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

MAX_SEARCH_RESULTS = 200


@dataclass(frozen=True, slots=True)
class Diagnostic:
    line: int
    column: int
    message: str


@dataclass(frozen=True, slots=True)
class OutlineItem:
    name: str
    kind: str
    line: int
    end_line: int
    depth: int


@dataclass(frozen=True, slots=True)
class SearchMatch:
    source_name: str
    line: int
    column: int
    preview: str


@dataclass(frozen=True, slots=True)
class TextEdit:
    start: int
    end: int
    replacement: str
    line: int


@dataclass(frozen=True, slots=True)
class RenamePlan:
    symbol: str
    replacement: str
    source_versions: Mapping[str, int]
    edits: Mapping[str, tuple[TextEdit, ...]]


class AnalysisSignals(QObject):
    diagnostics_ready = Signal(str, int, object)


class SyntaxTask(QRunnable):
    def __init__(self, source_name: str, source: str, version: int) -> None:
        super().__init__()
        self.source_name = source_name
        self.source = source
        self.version = version
        self.signals = AnalysisSignals()

    def run(self) -> None:
        self.signals.diagnostics_ready.emit(
            self.source_name, self.version, syntax_diagnostics(self.source, self.source_name)
        )


def request_syntax_diagnostics(
    source_name: str,
    source: str,
    version: int,
    callback: Callable[[str, int, tuple[Diagnostic, ...]], None],
) -> None:
    """Parse off the GUI thread; callers discard replies for obsolete versions."""
    task = SyntaxTask(source_name, source, version)
    task.signals.diagnostics_ready.connect(callback)
    QThreadPool.globalInstance().start(task)


def syntax_diagnostics(source: str, filename: str = "<script>") -> tuple[Diagnostic, ...]:
    try:
        ast.parse(source, filename=filename)
    except (SyntaxError, ValueError) as error:
        return (
            Diagnostic(
                max(1, getattr(error, "lineno", 1) or 1),
                max(1, getattr(error, "offset", 1) or 1),
                getattr(error, "msg", str(error)),
            ),
        )
    return ()


def outline(source: str) -> tuple[OutlineItem, ...]:
    try:
        tree = ast.parse(source)
    except SyntaxError, ValueError:
        return ()
    items: list[OutlineItem] = []

    def visit(body: list[ast.stmt], depth: int) -> None:
        for node in body:
            if isinstance(node, ast.ClassDef):
                items.append(
                    OutlineItem(
                        node.name, "class", node.lineno, node.end_lineno or node.lineno, depth
                    )
                )
                visit(node.body, depth + 1)
            elif isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef):
                items.append(
                    OutlineItem(
                        node.name, "function", node.lineno, node.end_lineno or node.lineno, depth
                    )
                )
                visit(node.body, depth + 1)

    visit(tree.body, 0)
    return tuple(items)


def folding_ranges(source: str) -> tuple[tuple[int, int], ...]:
    return tuple(
        (item.line, item.end_line) for item in outline(source) if item.end_line > item.line
    )


def search_sources(
    sources: Mapping[str, str],
    query: str,
    *,
    case_sensitive: bool = False,
    whole_word: bool = False,
    limit: int = MAX_SEARCH_RESULTS,
    cancelled: Callable[[], bool] | None = None,
) -> tuple[SearchMatch, ...]:
    if not query:
        return ()
    flags = 0 if case_sensitive else re.IGNORECASE
    expression = re.escape(query)
    if whole_word:
        expression = rf"\b{expression}\b"
    matcher = re.compile(expression, flags)
    matches: list[SearchMatch] = []
    for source_name, source in sources.items():
        if cancelled is not None and cancelled():
            break
        for line_number, line in enumerate(source.splitlines(), start=1):
            if cancelled is not None and cancelled():
                break
            for match in matcher.finditer(line):
                matches.append(
                    SearchMatch(source_name, line_number, match.start() + 1, line.strip())
                )
                if len(matches) >= limit:
                    return tuple(matches)
    return tuple(matches)


@dataclass(slots=True)
class _Occurrence:
    name: str
    line: int
    column: int
    end_column: int
    scope: _Scope


@dataclass(slots=True)
class _Scope:
    parent: _Scope | None
    kind: str
    bindings: dict[str, _Occurrence] = field(default_factory=dict)
    occurrences: list[_Occurrence] = field(default_factory=list)
    unsupported: set[str] = field(default_factory=set)
    children: list[_Scope] = field(default_factory=list)


class _ScopeIndex(ast.NodeVisitor):
    def __init__(self, source: str) -> None:
        self.source = source
        self.root = _Scope(None, "module")
        self.scope = self.root
        self.nodes: list[tuple[ast.Name, _Scope]] = []
        self.declarations: list[_Occurrence] = []
        self.child_scopes: dict[int, _Scope] = {}

    def build(self) -> None:
        tree = ast.parse(self.source)
        self._collect_scope(tree.body, self.root)
        self.visit(tree)
        for node, scope in self.nodes:
            occurrence = _Occurrence(
                node.id,
                node.lineno,
                node.col_offset,
                node.end_col_offset or node.col_offset + len(node.id),
                self._resolve(scope, node.id),
            )
            occurrence.scope.occurrences.append(occurrence)

    def _collect_scope(self, body: list[ast.stmt], scope: _Scope) -> None:
        for node in body:
            if isinstance(node, ast.Global | ast.Nonlocal):
                scope.unsupported.update(node.names)
            elif isinstance(node, ast.ClassDef | ast.AsyncFunctionDef | ast.FunctionDef):
                self._declare(scope, node.name, node.lineno, _declaration_column(self.source, node))
                parent = (
                    scope.parent
                    if scope.kind == "class" and not isinstance(node, ast.ClassDef)
                    else scope
                )
                child = _Scope(parent, "class" if isinstance(node, ast.ClassDef) else "function")
                scope.children.append(child)
                if not isinstance(node, ast.ClassDef):
                    for argument in (
                        *node.args.posonlyargs,
                        *node.args.args,
                        *node.args.kwonlyargs,
                    ):
                        self._declare(child, argument.arg, argument.lineno, argument.col_offset)
                    if node.args.vararg is not None:
                        self._declare(
                            child,
                            node.args.vararg.arg,
                            node.args.vararg.lineno,
                            node.args.vararg.col_offset,
                        )
                    if node.args.kwarg is not None:
                        self._declare(
                            child,
                            node.args.kwarg.arg,
                            node.args.kwarg.lineno,
                            node.args.kwarg.col_offset,
                        )
                self._collect_scope(node.body, child)
                self.child_scopes[id(node)] = child
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.asname or alias.name.partition(".")[0]
                    self._declare(scope, name, alias.lineno, alias.col_offset)
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    self._declare(scope, alias.asname or alias.name, alias.lineno, alias.col_offset)
            else:
                for name_node in _bound_names(node):
                    self._declare(scope, name_node.id, name_node.lineno, name_node.col_offset)

    def _declare(self, scope: _Scope, name: str, line: int, column: int) -> None:
        occurrence = _Occurrence(name, line, column, column + len(name), scope)
        scope.bindings.setdefault(name, occurrence)
        scope.occurrences.append(occurrence)
        self.declarations.append(occurrence)

    def _resolve(self, scope: _Scope, name: str) -> _Scope:
        current: _Scope | None = scope
        while current is not None:
            if name in current.bindings:
                return current
            current = current.parent
        return self.root

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_child_scope(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_child_scope(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._visit_child_scope(node)

    def _visit_child_scope(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
    ) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        if not isinstance(node, ast.ClassDef):
            for default in (*node.args.defaults, *node.args.kw_defaults):
                if default is not None:
                    self.visit(default)
        previous = self.scope
        self.scope = self.child_scopes[id(node)]
        for statement in node.body:
            self.visit(statement)
        self.scope = previous

    def visit_Name(self, node: ast.Name) -> None:
        self.nodes.append((node, self.scope))


def _bound_names(node: ast.AST) -> list[ast.Name]:
    target = node

    class Collector(ast.NodeVisitor):
        def __init__(self) -> None:
            self.names: list[ast.Name] = []

        def visit_Name(self, node: ast.Name) -> None:
            if isinstance(node.ctx, ast.Store):
                self.names.append(node)

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            if node is target:
                self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            if node is target:
                self.generic_visit(node)

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            if node is target:
                self.generic_visit(node)

    collector = Collector()
    collector.visit(node)
    return collector.names


def _declaration_column(
    source: str, node: ast.ClassDef | ast.AsyncFunctionDef | ast.FunctionDef
) -> int:
    line = source.splitlines()[node.lineno - 1]
    match = re.search(rf"\b{re.escape(node.name)}\b", line)
    return match.start() if match else node.col_offset


def rename_plan(
    sources: Mapping[str, str],
    versions: Mapping[str, int],
    source_name: str,
    line: int,
    column: int,
    replacement: str,
) -> RenamePlan | None:
    """Return only statically-resolved local/module edits for the selected identifier."""
    if not replacement.isidentifier() or not replacement:
        return None
    source = sources.get(source_name)
    if source is None:
        return None
    try:
        index = _ScopeIndex(source)
        index.build()
    except SyntaxError, ValueError:
        return None
    if any(
        isinstance(node, ast.Lambda | ast.ListComp | ast.SetComp | ast.DictComp | ast.GeneratorExp)
        for node in ast.walk(ast.parse(source))
    ):
        return None
    selected = next(
        (
            occurrence
            for scope in _walk_scopes(index.root)
            for occurrence in scope.occurrences
            if occurrence.line == line and occurrence.column <= column < occurrence.end_column
        ),
        None,
    )
    if selected is None or selected.name in selected.scope.unsupported:
        return None
    definition = selected.scope.bindings.get(selected.name)
    if definition is None:
        return None
    edits = tuple(
        TextEdit(
            _offset(source, occurrence.line, occurrence.column),
            _offset(source, occurrence.line, occurrence.end_column),
            replacement,
            occurrence.line,
        )
        for occurrence in selected.scope.occurrences
        if occurrence.name == selected.name
    )
    if not edits:
        return None
    unique_edits = tuple({(edit.start, edit.end): edit for edit in edits}.values())
    return RenamePlan(
        selected.name,
        replacement,
        {source_name: versions[source_name]},
        {source_name: unique_edits},
    )


def apply_rename_plan(sources: Mapping[str, str], plan: RenamePlan) -> dict[str, str]:
    updated = dict(sources)
    for source_name, edits in plan.edits.items():
        source = updated[source_name]
        for edit in sorted(edits, key=lambda item: item.start, reverse=True):
            source = source[: edit.start] + edit.replacement + source[edit.end :]
        updated[source_name] = source
    return updated


def _walk_scopes(scope: _Scope):
    yield scope
    for child in scope.children:
        yield from _walk_scopes(child)


def _offset(source: str, line: int, column: int) -> int:
    return sum(len(value) + 1 for value in source.splitlines()[: line - 1]) + column
