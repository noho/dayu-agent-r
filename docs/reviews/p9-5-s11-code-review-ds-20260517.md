# P9.5 S11 ToolRuntime Boundary Cleanup — Code Review

## Gate

- **Work unit**: P9.5 Pre-P10 Cross-Repository Hardening
- **Slice**: S11 ToolRuntime Boundary Cleanup
- **Approved plan**: `docs/host/p9-5-pre-p10-hardening-plan.md` S11 (lines 272-288)
- **Design truth**: `docs/host/design.md` §2, §18.2
- **Implementation artifact**: `docs/reviews/p9-5-s11-toolruntime-boundary-cleanup-implementation-20260517.md`
- **Reviewer**: AgentDS (code review agent, not controller)
- **Review target**: uncommitted diff for `dayu/host/tool_runtime.py`, `dayu/host/tool_runtime_schema_projection.py`, `tests/host/test_import_boundary.py`, `tests/engine/test_import_boundary.py`

## Review Scope And Methodology

### Scope

仅审查 S11 diff 触及的四个文件及其边界一致性。不审查未改动代码、不设计新方案、不改代码、不 commit/push/PR。

### Methodology

1. 逐行 diff 核对：确认移除的私有函数与新模块中的对应函数行为一致、签名一致。
2. 调用点审查：确认所有调用点使用正确的导入别名，无遗漏、无重名冲突。
3. 导入边界验证：AST 扫描 + 人工核实新模块的所有 import 是否违反架构边界。
4. 测试审查：检查 import-boundary 测试的正负覆盖、假阳性风险、断言强度。
5. 禁止项逐一核对：对照 S11 plan 的 9 项 stop condition 逐条验证。

### Key Review Decisions From Implementation Artifact

- Extraction decision: accept — 只抽取纯 schema projection / digest helper。public ToolRuntime 类型不迁移，避免 compatibility re-export。
- Docs decision: accept — `dayu/host/README.md` 中 ToolRuntime boundary、public import、accept barrier、truncation、duplicate 与 diagnostics 描述仍与当前代码一致。`tests/README.md` 职责未变。
- Validations: accept — 45 tests passed, pyright 0 errors.

## Finding 1 — LOW: Import-boundary test 未覆盖 `from X import *` 模式

- **入口/函数**: `test_engine_does_not_import_toolruntime_or_tool_declaration_owners` (tests/engine/test_import_boundary.py:140-150)
- **文件行号**: tests/engine/test_import_boundary.py:69-83 (`_imported_symbol_refs`), tests/host/test_import_boundary.py:249-261 (Host 侧同理)
- **输入场景**: 若 Engine 中未来出现 `from dayu.contracts.tool_declaration import *`，`_imported_symbol_refs()` 会提取到 `("*",)` 的 alias name，不会命中 `ENGINE_TOOL_OWNERSHIP_FORBIDDEN_SYMBOLS`。
- **实际**: 当前代码库中无任何 `import *`，此场景为理论缺口。
- **预期**: 在生产代码实际出现 `import *` 之前无需处理；S16 Contract Ownership audit 可统一加固。
- **直接证据**: `_imported_symbol_refs()` 只处理 `alias.name`，star import 的 `alias.name == "*"` 不会命中任何禁止符号。
- **影响**: 当前无实际影响。理论风险为 Engine 可通过 star import 获取 `ToolDefinition` / `ToolBundle`（二者均在 `dayu.contracts.tool_declaration` 中，是 Engine 合法可导入的 contracts 模块）。
- **建议验证点**: S16 可将 `import *` 检测加入 import-boundary 测试基础设施。
- **严重程度**: LOW — 理论缺口，无当前利用可能，不影响通过。

## Finding 2 — INFO: `__all__` in `tool_runtime.py` 未反映新的私有模块

- **入口/函数**: `tool_runtime.py` 模块级 `__all__` (dayu/host/tool_runtime.py:4958-4998)
- **文件行号**: dayu/host/tool_runtime.py:4958
- **输入场景**: `__all__` 列表不含 `tool_runtime_schema_projection` 中的任何符号。
- **实际**: `__all__` 未变更，正确——新模块是私有实现细节，其符号通过 `from X import Y as _Y` 在 tool_runtime.py 中作为私有别名存在，不应进入 `__all__`。
- **预期**: 与当前行为一致。
- **直接证据**: diff 未触及 `__all__` 段；新模块未被任何外部模块导入。
- **影响**: 无。
- **严重程度**: INFO — 确认性发现，非缺陷。

## Stop Condition Verification

逐条对照 S11 plan stop condition (lines 287-288)：

| # | Stop Condition | 状态 | 证据 |
|---|---|---|---|
| 1 | extraction requires public compatibility wrappers | **未触发** | 无新增 wrapper/facade；5 个导入使用 `as _` 私有别名 |
| 2 | test-only private re-export | **未触发** | 无测试导入 `tool_runtime_schema_projection`；所有测试通过 `dayu.host.tool_runtime` 公共模块 |
| 3 | semantic changes | **未触发** | 45 个既有测试全绿；函数体逐行一致 |
| 4 | moving ToolRuntime into contracts/runtime | **未触发** | ToolRuntime 仍在 `dayu/host/tool_runtime.py`；新模块在 `dayu/host/` 下 |

## Behavior Preservation Verification

逐项验证以下行为路径不变：

| 行为路径 | 验证方式 | 结果 |
|---|---|---|
| ToolRuntimeHandle 构造 | diff 未触及该 class | 不变 |
| factory (EffectiveToolBundleBuilder.build) | diff 显示 `build()` 方法仅调用点改用导入别名 | 不变 |
| accept barrier | 11 accept-barrier tests pass | 不变 |
| diagnostics | 5 diagnostics tests pass | 不变 |
| duplicate governance | accept-barrier tests 覆盖 duplicate path | 不变 |
| truncation / fetch_more | executor tests cover truncation path | 不变 |
| EventLog facts | accept-barrier tests 验证 canonical facts 不重复 | 不变 |
| `_tool_schema_json` at line 4611 | 导入别名 `tool_schema_json as _tool_schema_json` 保持原名 | 不变 |

## Import Boundary Test Coverage Analysis

### Engine side (`tests/engine/test_import_boundary.py`)

| 测试 | 覆盖模型 | 假阳性风险 | 结论 |
|---|---|---|---|
| `test_engine_does_not_import_phase0_forbidden_modules` | `requests`/`httpx`/`aiohttp` 全局扫描 | 低 — 精确前缀匹配 | 通过 |
| `test_engine_does_not_import_engine_core_forbidden_modules` | `dayu.host`/`dayu.service`/`dayu.ui`/`dayu.fins`/`dayu.engine.tools`/`dayu.engine.processors`/`*tool_trace*` 扫描 | 低 — 精确前缀+子串匹配 | 通过 |
| `test_engine_does_not_import_toolruntime_or_tool_declaration_owners` (新增) | `from X import ToolRuntime/ToolBundle/ToolDefinition` 符号级扫描 | 低 — Engine 当前不导入这些符号 | 通过 |

新增测试断言强度：符号级扫描，覆盖 `from module import Symbol` 和 `from module import Symbol as Alias`（alias.name 仍为原始符号名）。

### Host side (`tests/host/test_import_boundary.py`)

| 测试 | 覆盖模型 | 假阳性风险 | 结论 |
|---|---|---|---|
| `test_host_root_does_not_export_toolruntime_or_tool_declaration_owners` (新增) | `__all__` + `vars(host)` 双重检查 | 低 — `__all__` 不应含这些符号 | 通过 |
| `test_toolruntime_schema_projection_stays_private_host_owner` (新增) | 新模块 AST import 扫描，禁止 `dayu.engine`/`dayu.service`/`dayu.ui`/`dayu.fins`/Host mutator owners | 低 — 精确前缀匹配 | 通过 |

`TOOL_RUNTIME_SCHEMA_PROJECTION_FORBIDDEN_PREFIXES` 覆盖范围合理：禁止了 Engine、上层业务层、以及 Host 内部 mutator owner（dispatch、engine_ingest、projection、waiting）。未禁止 `dayu.host.admission`、`dayu.host.api`、`dayu.host.command` 是合理的——schema projection helper 理论上不应依赖这些，但当前未触犯，S16 可补充。

## New Module Architecture Boundary Check

`dayu/host/tool_runtime_schema_projection.py` 的 import 分析：

```
dayu.contracts.json_value          → layer-neutral contract ✓
dayu.contracts.tool_declaration    → layer-neutral contract ✓
dayu.contracts.tool_schema         → layer-neutral contract ✓
dayu.host.durable.codec            → Host internal utility (sha256_digest_json) ✓
dayu.host.tooling                  → Host tooling (FrameworkToolPolicyView) ✓
```

- 无 `dayu.engine` import ✓
- 无 `dayu.service` / `dayu.ui` / `dayu.fins` import ✓
- 无 `dayu.host.dispatch` / `dayu.host.engine_ingest` / `dayu.host.projection` / `dayu.host.waiting` import ✓
- `sha256_digest_json` 是纯计算函数，无业务语义 ✓
- `FrameworkToolPolicyView` 是 Host tooling 类型，符合 Host 内依赖 ✓

## Docs Decision Verification

实现 artifact 声称不更新 README。验证：

- `dayu/host/README.md`: ToolRuntime boundary、public import、accept barrier、truncation、duplicate 与 diagnostics 描述仍与当前代码一致。新模块是私有实现细节，不影响 README 描述的公开边界。
- `tests/README.md`: 测试分层与运行方式未变化。新增 import-boundary test 属于现有 `test_import_boundary.py` 文件扩展，不改变测试约定。
- 决策正确。

## Validation Reproduction

```text
$ source .venv/bin/activate && pytest tests/host/test_toolruntime_effective_bundle.py \
    tests/host/test_toolruntime_executor.py tests/host/test_toolruntime_accept_barrier.py \
    tests/host/test_toolruntime_diagnostics.py tests/host/test_import_boundary.py \
    tests/engine/test_import_boundary.py -v
45 passed in 0.61s

$ source .venv/bin/activate && python -m pyright dayu/host/tool_runtime.py \
    dayu/host/tool_runtime_schema_projection.py tests/host/test_import_boundary.py \
    tests/engine/test_import_boundary.py
0 errors, 0 warnings, 0 informations
```

## Residual Risks

1. **tool_runtime.py 仍然 ~5150 行**：accept barrier、truncation、duplicate、diagnostics 与 executor 仍在同一公开模块内。这是 S11 的明确设计决策——避免 public type 迁移触发 compatibility re-export 或 public API 变化。S12/S16 若需进一步拆分，必须先重新裁决公开导入路径。

2. **新私有模块依赖 `sha256_digest_json`**：digest helper 仍属于 `dayu.host.durable.codec`，未下沉到 `dayu.runtime` 或 `dayu.contracts`。S11 实现 artifact 已说明这是为避免扩大架构变更。若后续需要跨层共享 digest 语义，属于 P10+ 契约审计范围。

3. **Import-boundary 测试的 star import 缺口**：见 Finding 1。当前无实际影响，S16 可统一加固。

4. **S12 truncation/duplicate 测试与 S16 contract audit 的交互**：新私有模块让 S12/S16 可以局部检查 schema projection boundary，但目前 `tool_runtime_schema_projection.py` 无独立单元测试。其正确性由 `tool_runtime.py` 的集成测试间接覆盖。若 S12 修改 truncation/duplicate 逻辑时触及 schema projection 路径，建议为其补充独立单元测试。

## Conclusion

**建议**: 通过。无 blocking finding。

**Finding 数量**: 2（1 LOW + 1 INFO），均非阻塞。

**Artifact 路径**: `docs/reviews/p9-5-s11-code-review-ds-20260517.md`

**关键确认**:
- 5 个抽取函数体与原始实现逐行一致
- ToolRuntimeHandle、factory、accept barrier、duplicate governance、truncation/fetch_more、diagnostics、EventLog facts 行为路径全不变
- 公共 API 不变，`dayu/host/__init__.py` 未修改，`tool_runtime.py.__all__` 未修改
- 无 compatibility re-export、test-only private re-export、facade、lazy import seam
- 新模块不依赖 Engine 或 Host mutator owner
- 45 targeted tests + pyright 0 errors
- README 不更新决策正确
