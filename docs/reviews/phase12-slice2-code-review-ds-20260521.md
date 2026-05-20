# Code Review

## Scope

- Mode: current changes (Phase 12 Slice 2 workspace)
- Branch: `docs/phase12-design-discussion`
- Base: `main`
- Output file: `docs/reviews/phase12-slice2-code-review-ds-20260521.md`
- Included scope:
  - `dayu/runtime/tools_discovery.py` — digest helpers, source ref normalization, reserved framework tool name validation (unstaged additions on top of Slice 1 commit)
  - `tests/runtime/test_tools_discovery.py` — narrow source-ref assertion updates
  - `tests/runtime/test_tools_discovery_digest.py` — digest/source-ref/reserved-name coverage
  - `dayu/contracts/tool_source.py` — canonical `ToolBundleSourceRef` contract (committed Slice 1)
  - `docs/host/implementation-control.md` — status update (evidence only)
  - `docs/host/phase12-runtime-assembly-plan.md` — accepted plan (truth reference)
- Excluded scope: Host durable state, ToolRuntime accept barrier, Engine, ConfigLoader, ScenePrepare, prompt assets, config schema, business tools, committed-only Slice 1 code paths
- Parallel review coverage: 无

## Findings

### 1-未修复-低-`_normalize_json_value` Mapping 分支对非字符串键 silently 转换为字符串

- **入口/函数**: `_normalize_json_value` → `_canonical_json_digest` → `_tool_definitions_digest`
- **文件(行号)**: `dayu/runtime/tools_discovery.py:566-569`
- **输入场景**: 若未来某 `ToolParametersSchema.properties` 或 `ToolTruncateSpec.limits` 的实现返回 `Mapping` 但键不是 `str`（违反 `JsonValue` 类型约定但 Python 运行时不会阻止）
- **实际分支**: `isinstance(value, Mapping)` 命中，`for key, item in value.items()` 直接使用非字符串键作为 dict key
- **预期行为**: 应 fail fast 或确保键为字符串再继续
- **实际行为**: `json.dumps` 会将非字符串键转为字符串，例如 `{1: "x"}` → `{"1": "x"}` — 虽然 digest 仍稳定，但类型契约被静默绕过
- **直接证据**: 行 566 的 `isinstance(value, Mapping)` 匹配任何 Mapping，不检查键类型；行 569 的 `result[key]` 假设 key 已是 str
- **影响**: 静默绕过类型契约，不会导致 digest 不稳定，但削弱防御性；当前所有已知输入（`Mapping[str, JsonValue]`、`Mapping[str, int]`）均不会触发
- **建议改法和验证点**: 在 Mapping 分支内对 key 做 `isinstance(key, str)` 断言，或在递归前先显式 cast 为 `Mapping[str, JsonValue]`；当前风险极低，可在后续 slice 统一处理
- **修复风险（低）**: 仅增加一层防御性校验，不改变 digest 结果
- **严重程度（低）**: 无法被当前合法输入触发，属于防御性缺失而非功能缺陷

## Open Questions

1. `_RESERVED_FRAMEWORK_TOOL_NAMES` 当前只有 `"fetch_more"` 一个值。未来若新增 framework tool（如 `"retry"`、`"continue"`），这个 frozenset 的维护归属尚不明确——是放在 contracts 层作为公共常量，还是由 `dayu.runtime` 私有？建议在 Slice 3/4 或 Phase 13 讨论时明确。
2. Digest 当前是 provider 级（一个 provider 的多个 source refs 共享同一 digest）。Slice 2 实现 artifact 的 Residual Risks 已经指出："如果后续需要 per-tool source refs，需要在后续 slice 或 phase 明确契约。"本 review 确认当前实现与计划一致，此项属于已记录的 open design question，不重复计为 finding。

## Residual Risk

- `_normalize_json_value` 的 raise TypeError 分支（行 571）没有被测试覆盖。当前 `JsonValue` 类型保证该分支不可达，但若类型别名被放宽，缺少测试会让回归更晚被发现。建议后续 slice 在 `test_tools_discovery_digest.py` 中增补一个阴性测试。
- 空 provider 输出（`allow_empty=True`）产出的 digest `sha256:...` 基于 `{"tools": []}`。该行为在当前的测试中被隐式验证（`test_empty_provider_with_allow_empty_succeeds` 断言 `content_digest is not None`），但测试未固定期望的 hex 值。若 canonical JSON helper 的 `sort_keys` 或 encoding 行为在未来调整，空集合摘要会静默变化。建议在 digest 测试中固定一个已知输入的金标准 hex 值（例如 `sha256:<expected_hex>`），作为 canonical 算法的回归哨兵。此项属于测试加固建议，不阻塞当前 slice。

## Validation Commands and Results

```bash
# Tests
source .venv/bin/activate && pytest tests/runtime/test_tools_discovery.py \
  tests/runtime/test_tools_discovery_digest.py \
  tests/runtime/test_import_boundary.py -v
# Result: 22 passed in 0.66s
```

```bash
# Pyright
source .venv/bin/activate && python -m pyright dayu/contracts dayu/runtime \
  tests/runtime
# Result: 0 errors, 0 warnings, 0 informations
```

```bash
# Import boundary verification (manual confirmation)
source .venv/bin/activate && python -c "
import ast, pathlib
root = pathlib.Path('dayu/runtime')
for f in sorted(root.rglob('*.py')):
    if '__pycache__' in f.parts:
        continue
    tree = ast.parse(f.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith('dayu.host'):
                    print(f'VIOLATION: {f} imports {alias.name}')
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith('dayu.host'):
                print(f'VIOLATION: {f} imports {node.module}')
print('Import boundary check: PASS (no violations)')
"
# Result: Import boundary check: PASS (no violations)
```

## Verdict

**PASS** — 0 blocking findings.

实施正确满足 Phase 12 Slice 2 的所有设计和计划要求：

- `dayu.runtime.tools_discovery` 不 import `dayu.host` 或 Host durable codec，只使用 stdlib `json` + `hashlib` 做 canonical digest
- Digest 只覆盖工具声明内容（name、LLM-facing schema、truncate spec、tags、display metadata），明确排除 callable 引用、provider identity、模块路径对象身份、权限、lease、fencing、Host truth 或 owner
- Source ref 规范化正确保留 `source_kind`、`source_id`、`version_ref`，替换 `content_digest` 为 discovery 计算的声明摘要
- 保留名校验至少拒绝 `fetch_more`，未导入 `FrameworkToolName`，未改变 ToolRuntime 注入或 accept barrier
- 无弱类型逃逸（`Any`/`object`）、无 Slice 3/4 范围蔓延、无架构边界违规
- 所有相关测试通过，pyright 零报错，import boundary 测试通过
