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


def _repo_root() -> Path:
    """返回仓库根目录。"""

    return _engine_root().parent.parent


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


def _find_field_annotation(
    file_path: Path, class_name: str, field_name: str
) -> str | None:
    """返回指定 dataclass 字段的注解源代码。

    :param file_path: 源码路径。
    :param class_name: 类名。
    :param field_name: 字段名。
    :returns: 注解源码字符串，找不到则返回 ``None``。
    """

    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for body_node in node.body:
                if (
                    isinstance(body_node, ast.AnnAssign)
                    and isinstance(body_node.target, ast.Name)
                    and body_node.target.id == field_name
                ):
                    return ast.unparse(body_node.annotation)
    return None


def _contains_error_code_attribute(node: ast.expr) -> bool:
    """判断表达式是否读取 ``error_code`` 属性。

    :param node: 待检查的表达式语法树节点。
    :returns: 表达式内部包含 ``.error_code`` 读取时返回 ``True``。
    """

    return any(
        isinstance(child, ast.Attribute) and child.attr == "error_code"
        for child in ast.walk(node)
    )


def test_assistant_tool_call_provider_state_annotation_is_typed_union() -> None:
    """``AssistantToolCall.provider_state`` 必须为 ``ToolCallProviderState | None``。

    严禁退化为 ``dict[str, Any]`` / ``Mapping[str, Any]`` / ``object``。
    """

    file_path = _engine_root() / "contracts" / "messages.py"
    annotation = _find_field_annotation(
        file_path, "AssistantToolCall", "provider_state"
    )
    assert annotation == "ToolCallProviderState | None", (
        f"AssistantToolCall.provider_state annotation unexpected: {annotation}"
    )


def test_runner_http_error_data_error_code_annotation_is_enum() -> None:
    """``RunnerHTTPErrorData.error_code`` 必须为 ``RunnerHTTPErrorCode`` 枚举。

    严禁退化为裸 ``str``。
    """

    file_path = _engine_root() / "contracts" / "runner_events.py"
    annotation = _find_field_annotation(
        file_path, "RunnerHTTPErrorData", "error_code"
    )
    assert annotation == "RunnerHTTPErrorCode", (
        f"RunnerHTTPErrorData.error_code annotation unexpected: {annotation}"
    )


def test_engine_run_error_code_annotations_are_typed() -> None:
    """Engine run failure code 字段不得退化为裸 ``str``。"""

    contracts_root = _engine_root() / "contracts"
    expected = {
        (contracts_root / "engine_events.py", "RunFailedData"): (
            "EngineErrorCode"
        ),
        (contracts_root / "engine_events.py", "ProviderProtocolErrorData"): (
            "EngineErrorCode"
        ),
        (contracts_root / "agent_run.py", "EngineRunOutcomeFailed"): (
            "EngineErrorCode"
        ),
        (contracts_root / "runner_events.py", "RunnerProtocolErrorData"): (
            "RunnerSpecificErrorCode"
        ),
    }
    mismatches: list[str] = []
    for (file_path, class_name), expected_annotation in expected.items():
        annotation = _find_field_annotation(file_path, class_name, "error_code")
        if annotation != expected_annotation:
            mismatches.append(
                f"{file_path}:{class_name}.error_code -> {annotation}"
            )
    assert not mismatches, "typed error-code annotations drifted:\n" + "\n".join(
        mismatches
    )


def test_engine_error_code_constructors_do_not_use_literal_strings() -> None:
    """关键错误码 contract 构造点不得传入字符串字面量。"""

    scanned_roots = (
        _engine_root(),
        _repo_root() / "tests" / "engine",
    )
    target_names = frozenset(
        {
            "RunFailedData",
            "EngineRunOutcomeFailed",
            "ProviderProtocolErrorData",
            "RunnerProtocolErrorData",
        }
    )
    violations: list[str] = []
    for root in scanned_roots:
        for file_path in sorted(root.rglob("*.py")):
            source = file_path.read_text(encoding="utf-8")
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if not isinstance(func, ast.Name) or func.id not in target_names:
                    continue
                for keyword in node.keywords:
                    if (
                        keyword.arg == "error_code"
                        and isinstance(keyword.value, ast.Constant)
                        and isinstance(keyword.value.value, str)
                    ):
                        violations.append(f"{file_path}:{node.lineno}:{func.id}")
    assert not violations, (
        "literal string error_code constructors found:\n" + "\n".join(violations)
    )


def test_agent_tests_do_not_compare_typed_error_codes_to_literal_strings() -> None:
    """Agent 行为测试不得用字符串字面量直接比较 typed ``error_code``。"""

    file_path = _repo_root() / "tests" / "engine" / "test_agent_phase2.py"
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        if not any(
            isinstance(operator, (ast.Eq, ast.NotEq)) for operator in node.ops
        ):
            continue
        expressions: tuple[ast.expr, ...] = (node.left, *node.comparators)
        if not any(_contains_error_code_attribute(expr) for expr in expressions):
            continue
        if not any(
            isinstance(expr, ast.Constant) and isinstance(expr.value, str)
            for expr in expressions
        ):
            continue
        violations.append(f"{file_path}:{node.lineno}")
    assert not violations, (
        "typed error_code compared directly with string literals:\n"
        + "\n".join(violations)
    )


def test_host_typed_error_code_boundary_uses_serializer() -> None:
    """Host ingest 读取 typed Engine 错误码时必须经过统一 serializer。"""

    file_path = _repo_root() / "dayu" / "host" / "engine_ingest.py"
    violations: list[str] = []
    for line_number, line in enumerate(
        file_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if ".error_code" not in line:
            continue
        if "data.error_code" not in line and "event.data.error_code" not in line:
            continue
        if "serialize_engine_error_code" in line:
            continue
        violations.append(f"{file_path}:{line_number}:{line.strip()}")
    assert not violations, (
        "Host typed Engine error_code access bypassed serializer:\n"
        + "\n".join(violations)
    )
