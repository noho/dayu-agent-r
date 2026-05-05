"""弱类型守卫测试。

通过 AST 扫描 ``dayu/engine/`` 下所有源码文件，禁止以下弱
类型签名：

- ``Any`` / ``object`` 出现在注解中。
- 函数 / 方法参数无注解（除 ``self`` / ``cls``）。
- 函数 / 方法返回值无注解。
- 注解中出现裸 ``dict`` / ``list`` / ``tuple`` / ``set``（必须参数化）。

测试守的是「公开契约」层，对私有 helper 同样适用。
"""

from __future__ import annotations

import ast
from pathlib import Path

import dayu.engine as engine


def _engine_root() -> Path:
    """返回 ``dayu/engine/`` 源码根目录。"""

    package_file = engine.__file__
    assert package_file is not None
    return Path(package_file).resolve().parent


def _iter_contract_files() -> list[Path]:
    """递归收集 engine 包中所有 ``.py`` 文件。"""

    root = _engine_root()
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


_BARE_BUILTIN_GENERICS: frozenset[str] = frozenset(
    {"dict", "list", "tuple", "set", "frozenset"}
)


def _annotation_violations(node: ast.expr | None, *, location: str) -> list[str]:
    """检查单个注解节点是否违规。

    返回违规说明列表（多个违规分开记录）。
    """

    if node is None:
        return [f"{location}: missing annotation"]
    violations: list[str] = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name):
            if sub.id in {"Any", "object"}:
                violations.append(f"{location}: annotation uses {sub.id}")
            elif sub.id in _BARE_BUILTIN_GENERICS:
                # 仅当裸 Name 出现在注解位置（即非 Subscript 的 value）才视为违规。
                # ast.walk 同时会访问 Subscript 中的 value，需要单独判断父节点。
                pass
        elif isinstance(sub, ast.Attribute):
            if isinstance(sub.value, ast.Name) and sub.value.id == "typing" and sub.attr in {"Any"}:
                violations.append(f"{location}: annotation uses typing.{sub.attr}")
    # 单独扫描裸 builtin generics（不在 Subscript 内时违规）。
    violations.extend(_bare_builtin_generic_violations(node, location=location))
    return violations


def _bare_builtin_generic_violations(
    node: ast.expr, *, location: str
) -> list[str]:
    """检查注解中是否包含未参数化的裸 builtin 容器。"""

    violations: list[str] = []

    class _Scanner(ast.NodeVisitor):
        def __init__(self) -> None:
            self._inside_subscript_value: int = 0

        def visit_Subscript(self, node: ast.Subscript) -> None:  # noqa: N802
            self._inside_subscript_value += 1
            self.visit(node.value)
            self._inside_subscript_value -= 1
            self.visit(node.slice)

        def visit_Name(self, node: ast.Name) -> None:  # noqa: N802
            if (
                node.id in _BARE_BUILTIN_GENERICS
                and self._inside_subscript_value == 0
            ):
                violations.append(
                    f"{location}: bare builtin generic {node.id}"
                )

    _Scanner().visit(node)
    return violations


def _check_function_def(
    func: ast.FunctionDef | ast.AsyncFunctionDef, *, file: str
) -> list[str]:
    """检查函数 / 方法签名的注解完整性与弱类型违规。"""

    violations: list[str] = []
    location_prefix = f"{file}:{func.name}"

    args = func.args
    pos_args = list(args.posonlyargs) + list(args.args)
    for index, arg in enumerate(pos_args):
        if index == 0 and arg.arg in {"self", "cls"}:
            continue
        violations.extend(
            _annotation_violations(
                arg.annotation, location=f"{location_prefix}({arg.arg})"
            )
        )
    for arg in args.kwonlyargs:
        violations.extend(
            _annotation_violations(
                arg.annotation, location=f"{location_prefix}({arg.arg})"
            )
        )
    if args.vararg is not None:
        violations.extend(
            _annotation_violations(
                args.vararg.annotation,
                location=f"{location_prefix}(*{args.vararg.arg})",
            )
        )
    if args.kwarg is not None:
        violations.extend(
            _annotation_violations(
                args.kwarg.annotation,
                location=f"{location_prefix}(**{args.kwarg.arg})",
            )
        )

    if func.returns is None:
        # 允许 ``__init__`` 等魔术方法省略返回注解。
        if func.name not in {"__init__"}:
            violations.append(f"{location_prefix}: missing return annotation")
    else:
        violations.extend(
            _annotation_violations(
                func.returns, location=f"{location_prefix}->return"
            )
        )

    return violations


def _check_class_field_annotations(cls: ast.ClassDef, *, file: str) -> list[str]:
    """检查 dataclass 字段 / 类变量注解完整性与弱类型违规。"""

    violations: list[str] = []
    for body_node in cls.body:
        if isinstance(body_node, ast.AnnAssign) and isinstance(
            body_node.target, ast.Name
        ):
            location = f"{file}:{cls.name}.{body_node.target.id}"
            violations.extend(
                _annotation_violations(body_node.annotation, location=location)
            )
    return violations


def test_contracts_disallow_weak_typing() -> None:
    """``dayu.engine`` 不得出现 ``Any`` / ``object`` / 未注解 / 裸容器。"""

    violations: list[str] = []
    for file_path in _iter_contract_files():
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        rel = str(file_path)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                violations.extend(_check_function_def(node, file=rel))
            elif isinstance(node, ast.ClassDef):
                violations.extend(_check_class_field_annotations(node, file=rel))
    assert not violations, "weak typing violations:\n" + "\n".join(violations)


def test_engine_event_metadata_annotation_is_mapping_jsonvalue() -> None:
    """``EngineEvent.metadata`` 注解必须为 ``Mapping[str, JsonValue] | None``。"""

    file_path = _engine_root() / "contracts" / "engine_events.py"
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "EngineEvent":
            for body_node in node.body:
                if (
                    isinstance(body_node, ast.AnnAssign)
                    and isinstance(body_node.target, ast.Name)
                    and body_node.target.id == "metadata"
                ):
                    found.append(ast.unparse(body_node.annotation))
    assert found == ["Mapping[str, JsonValue] | None"], (
        f"EngineEvent.metadata annotation unexpected: {found}"
    )
