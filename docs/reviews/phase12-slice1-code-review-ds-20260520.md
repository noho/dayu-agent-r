# Phase 12 Slice 1 Code Review — AgentDS

## Verdict: PASS

无阻塞性 finding。Slice 1 实现符合 accepted plan 范围、架构硬约束与编码硬约束。

## Scope

- **Mode**: current changes (unstaged workspace + untracked files)
- **Branch**: `docs/phase12-design-discussion`
- **Base**: `HEAD` (e45f251)
- **Output file**: `docs/reviews/phase12-slice1-code-review-ds-20260520.md`
- **Included scope**:
  - `dayu/contracts/tool_source.py` (新) — canonical `ToolBundleSourceKind` / `ToolBundleSourceRef`
  - `dayu/contracts/__init__.py` (改) — 新增 source ref 契约导出
  - `dayu/host/tooling.py` (改) — 删除旧类型定义，改用 canonical 契约
  - `dayu/host/__init__.py` — 不变（仅 import 源不变）
  - `dayu/runtime/tools_discovery.py` (新) — `ToolsDiscovery`、provider protocol、import/entry point 解析
  - `dayu/runtime/__init__.py` (改) — runtime docstring 更新
  - `dayu/README.md` (改) — runtime/contracts 稳定边界说明同步
  - `tests/runtime/test_tools_discovery.py` (新) — 8 个测试
  - `tests/host/test_tooling_options.py` (改) — 新增 canonical identity 测试
  - `docs/host/implementation-control.md` (改) — controller status update
- **Excluded scope**: Slice 2 digest/reserved-name、Slice 3 ConfigLoader、Slice 4 ScenePrepare、Slice 5 资产迁移、旧 `dayu-agent` 仓库
- **Parallel review coverage**: 无（单 reviewer 全量走读）

## Findings

未发现实质性问题。

## Accepted-Scope / Non-Blocking Notes

1. **`_require_non_empty_text` / `_require_optional_non_empty_text` 重复定义** (`dayu/contracts/tool_source.py:58-81`, `dayu/runtime/tools_discovery.py:431-454`): 两个模块各自定义了完全相同的私有校验辅助函数。当前是两层独立的私有 helper，若将来校验规则扩展（例如 Python 标识符合法性）需要同步双写。可待 Slice 2 或后续 cleanup slice 考虑是否抽取共享 helper，当前不构成正确性或架构问题。

2. **`entry_points(group=...)` Python 3.11 兼容性已确认** (`dayu/runtime/tools_discovery.py:324`): 经验证，当前 venv Python 3.11.9 中 `importlib.metadata.entry_points(group=...)` 可用（返回 `EntryPoints` 类型，支持 `group` 关键字参数）。不存在 claimed 的 Python 3.11 不兼容问题。

3. **`_resolve_import_path` 异常传播** (`dayu/runtime/tools_discovery.py:305`): `importlib.import_module()` 的 `ModuleNotFoundError` 直接向上传播，不包裹为 `ToolsDiscoveryError`。docstring 声称 `:raises ToolsDiscoveryError` 但实际上 `ModuleNotFoundError` 也可能抛出。这不是设计缺陷——模块不存在与 import path 格式非法是不同错误类别，当前行为合理但 docstring 不够精确。

4. **测试 gap** (`tests/runtime/test_tools_discovery.py`): 未覆盖以下边界场景：import path 格式非法（无冒号、空模块名）、属性路径含空 segment、entry point 解析为非 callable、模块不存在时的异常类型。这些是边界防御性校验的测试缺口，但核心 happy path 与关键 error path 均已覆盖。

5. **Slice 1 vs Slice 2 边界确认**: 本 slice 未实现 digest 计算、content_digest 字段填充、framework reserved name 运行时校验。`HostToolingOptions.__post_init__` 中已有的 `fetch_more` 保留名校验保持不变。digest 字段在 `ToolBundleSourceRef` 中声明为可选，当前始终为 `None`，后续 Slice 2 填充。符合 plan 分 slice 约定。

## Validation Commands/Results

| 命令 | 结果 |
|---|---|
| `pytest tests/runtime/test_tools_discovery.py tests/host/test_tooling_options.py tests/host/test_package_exports.py -q` | 26 passed in 0.61s |
| `python -m pyright dayu/contracts dayu/runtime dayu/host tests/runtime tests/host` | 0 errors, 0 warnings, 0 informations |
| `pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q` | 6 passed in 0.62s |
| Python 3.11 `importlib.metadata.entry_points(group=...)` 兼容性 | `entry_points(group=...)` works in Python 3.11.9 |
| `ToolBundleSourceKind is ContractToolBundleSourceKind` 身份校验 | PASS |
| `host.tooling` 无旧 class 定义（`class ToolBundleSourceKind`/`class ToolBundleSourceRef`） | PASS |
| `host/__init__.py` 通过 `host.tooling` 导入（非直接 `contracts`） | PASS |
| `tools_discovery.py` import boundary（无 host/engine/service/ui/fins） | PASS |
| `tool_source.py` import boundary | PASS |
| `ToolsDiscoveryProviderSpec.config` default_factory 可变安全 | PASS |
| empty specs `discover_tools(())` | PASS |

## Architecture Boundary Checks

- **`dayu.runtime.tools_discovery`**: 只 import `__future__`, `importlib`, `importlib.metadata`, `collections.abc`, `dataclasses`, `types`, `typing`, `dayu.contracts`. 无 host/engine/service/ui/fins 或业务工具包。
- **`dayu.contracts.tool_source`**: 只 import `__future__`, `dataclasses`, `enum`. 无任何业务层依赖。
- **`dayu.host.tooling`**: 从 `dayu.contracts` 导入 canonical 类型，无新类定义、无包装语义。
- **`dayu.host.__init__`**: 从 `dayu.host.tooling` 导入（间接获得 canonical 类型），无直接 `contracts` 导入路径。
- **Export surface**: `HostToolingOptions` 字段不变，`ToolBundleSourceKind`/`ToolBundleSourceRef` 仍出现在 `dayu.host.__all__` 中且身份等于 `dayu.contracts` 的 canonical 类型。
- **无反向依赖、无跨层穿透、无 God object/builder、无 `Any`/`object`/无类型签名、无魔法字符串**（除测试中 schema-like 字面量外）。

## Final Blocking Findings Count: 0
