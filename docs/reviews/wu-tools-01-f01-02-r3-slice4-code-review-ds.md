# WU-TOOLS-01-F01-02-R3 Slice 4 Code Review — DS

## Review Metadata

- **Reviewer**: AgentDS
- **Date**: 2026-06-10
- **Scope**: WU-TOOLS-01-F01-02-R3 Slice 4 — Legacy Adapter Deletion
- **Reviewed diff**: working tree vs HEAD (commit `2a914234`)
- **Review basis**:
  - `AGENTS.md`
  - `docs/host/design.md` §1–§3, §10, §18
  - `docs/engine/design.md` §10–§13
  - `docs/host/issues-implementation-control.md` WU-TOOLS-01-F01-02-R3
  - `docs/host/wu-tools-01-f01-02-r3-retire-legacy-adapter-plan.md` §8 Slice 4
  - `docs/reviews/wu-tools-01-f01-02-r3-slice4-implementation-codex.md`

## Verdict: PASS

无 blocking findings。所有改动精确对齐 Slice 4 目标边界，adapter 删除安全，边界收口准确。

---

## 1. Adapter 删除安全性

### 1.1 生产依赖检查

- **确认**：`dayu/tools/_legacy_adapter/` 目录已删除，8 个文件全部移除。
- **确认**：`rg "_legacy_adapter|LegacyToolDeclarationCollector|adapt_collected_tools" dayu/ tests/ --type py` 返回 0 matches。
- **确认**：`dayu/tools/__init__.py` 未含 `_legacy_adapter` import。
- **确认**：无 `register_fins_read_tools`、`register_doc_tools`、`register_web_tools` 残留在生产代码中。

已删除的旧模块与当前依赖关系：

| 旧模块 | 旧消费者 | Slice 迁移状态 |
|---|---|---|
| `_legacy_adapter/definition_adapter.py` | Doc/Web/Fins provider → adapter | Slice 1/2/3 已将 provider 改为原生 builder |
| `_legacy_adapter/registry_collector.py` | Doc/Web/Fins provider → collector | Slice 1/2/3 已移除 collector 调用 |
| `_legacy_adapter/argument_validator.py` | definition_adapter → validator | 已由 Slice 0 `dayu.runtime.tool_call_projection` 替代 |
| `_legacy_adapter/exceptions.py` | Doc/Web/Fins 工具函数 | 已替换为领域本地类型或 runtime helper typed result |
| `_legacy_adapter/tool_errors.py` | Doc/Web 工具函数 | 同上 |
| `_legacy_adapter/tool_decorator.py` | Doc/Web/Fins OLD 声明 | 已由 `dayu.contracts.tool_declaration.tool(...)` 替代 |
| `_legacy_adapter/tool_contracts.py` | 内部 adapter 类型 | 无外部消费者 |

**结论**：无隐藏生产依赖。

### 1.2 跨领域残留检查

`dayu/tools/web/web_tools.py:292` 定义了 `ToolBusinessError(Exception)` — 这是 Web 领域本地类型，**不是** legacy adapter 的 `ToolBusinessError`。Web 本地版本新增了 `url`、`next_action`、`http_status`、`internal_diagnostics` 字段，且不 import `_legacy_adapter`。符合计划 §7 决策 5 "Web/Fins 业务模块需要的领域错误类型必须放在本领域模块内"。

`dayu/tools/doc_tools.py` 定义了 `_DocToolArgumentError` 和 `_DocFileAccessError` — 以 `_` 前缀的模块私有异常，Doc 领域本地类型，不依赖 legacy adapter。

---

## 2. 行为迁移清单验证

计划 §8 Slice 4 中 8 项行为迁移清单逐项验证：

| # | 旧行为 | 声明迁移目标 | 验证结果 |
|---|---|---|---|
| 1 | 参数 schema validation | Slice 0 `tests/runtime/test_tool_call_projection.py` | ✅ 已覆盖 default/required/unknown/enum/range/array item 及固定 `invalid_argument` |
| 2 | 普通业务失败映射 | Slice 0 helper + provider tests | ✅ `failed_outcome(...)` helper 测试 + Doc/Web/Fins 领域失败测试通过 |
| 3 | `tool_cancelled` → failed outcome | 不迁移（删除的错误行为） | ✅ Doc/Web/Fins cancellation 全部断言 `ToolCancelledOutcome(host_cancelled)` |
| 4 | path projection / allowed roots / must_exist | Slice 1 Doc provider tests | ✅ 白名单拒绝、文件不存在、list/search 可链 read tools 通过 |
| 5 | per-provider serialization | Slice 1/2/3 provider tests | ✅ Doc/Web/Fins 均使用 provider 级共享 `asyncio.Lock()` |
| 6 | truncate/display/tags/schema | Slice 1/2/3 + combined acceptance | ✅ native `ToolTruncateSpec`/tags/schema 与旧期望等价 |
| 7 | fetch_more reserved | Slice 4 combined acceptance + import boundary | ✅ business bundle 不含 `fetch_more`，ToolRuntime 注入；token 只在 owner 出现 |
| 8 | collector/decorator OLD metadata | 不迁移（adapter-only 实现细节） | ✅ 所有生产 provider 已使用 native builder |

**结论**：行为迁移清单逐项关闭。未出现用"adapter 测试已删除"替代等价行为覆盖的情况。

---

## 3. Combined Acceptance 变更审查

文件：`tests/tools/test_combined_tools_acceptance.py`

**变更**：
- 重命名 `test_migrated_providers_and_adapter_do_not_import_old_runtime` → `test_native_providers_do_not_import_old_runtime`
- 重命名 `_migrated_tool_source_paths()` → `_native_tool_source_paths()`
- 移除 `dayu/tools/_legacy_adapter` 扫描根（line 960 原位置）
- 更新 docstring："迁移工具" → "当前工具"、"迁移 provider/adapter" → "当前原生 provider"

**验证**：
- `_native_tool_source_paths()` 返回 web tools、fins tools、doc_provider.py、doc_tools.py — 精确覆盖三类当前原生 provider。
- Adapter 目录不再出现在扫描范围内，符合 adapter 已删除的事实。
- 函数名与测试名变更准确反映"不再有 adapter => 不需要允许 adapter"的语义。

---

## 4. Host Import Boundary 变更审查

文件：`tests/host/test_import_boundary.py`

**变更**：
- 删除常量 `FETCH_MORE_DEFENSIVE_ALLOWED_RELATIVE_FILES`（含 3 个 `_legacy_adapter` 路径）
- 删除 `test_fetch_more_token_stays_inside_toolruntime_owner_modules` 中的 defensive allowlist 跳过分支
- 更新 docstring：移除"或 legacy adapter 防御性引用"

**验证**：
- 删除后 `FETCH_MORE_ALLOWED_RELATIVE_FILES` 仍保留 3 个真正 owner 文件：`host/tool_runtime.py`、`host/tooling.py`、`runtime/tools_discovery.py`。
- `ToolRuntime owner` 含义未变：fetch_more 拥有者仍是 ToolRuntime/tooling/ToolsDiscovery。
- **ToolRuntime owner 未被误伤**：三个 true owner 文件仍在 allowlist 中。

---

## 5. test_doc_tools_provider.py 清理审查

文件：`tests/tools/test_doc_tools_provider.py`

**变更**：
- 删除 `doc_provider_source` 变量（读取 `dayu/tools/doc_provider.py` 全文）
- 删除 4 行负向断言：
  - `assert "_legacy_adapter" not in doc_tools_source`
  - `assert "_legacy_adapter" not in doc_provider_source`
  - `assert "LegacyToolDeclarationCollector" not in doc_provider_source`
  - `assert "adapt_collected_tools" not in doc_provider_source`

**保留的防线**：
- `dayu.engine.tool_registry` not in imported_modules
- `dayu.engine.truncation_manager` not in imported_modules
- `dayu.engine.tool_result` not in imported_modules
- `"fetch_more" not in doc_tools_source`
- `"TruncationManager" not in doc_tools_source`

**审查结论**：
- 删除的 4 行是纯 adapter 符号负向断言。adapter 已不存在，这些断言从"验证代码不依赖 adapter"退化为"验证字符串不出现"——后者无效且没有防守价值。删除是合理的。
- 保留的 5 条防线是有意义的：阻止 doc_tools 回头导入 Engine 内部模块（违反分层）、阻止在 doc_tools 中引用 fetch_more/TruncationManager（属于 ToolRuntime owner）。**关键防线未削弱。**

问题：删除 `doc_provider_source` 后，不再有对 `doc_provider.py` 的 AST import 扫描。doc_provider.py 是否可能回头引入 OLD runtime import？

- 验证：`grep -rn "engine.tool_registry\|engine.truncation_manager\|engine.tool_result\|fetch_more" dayu/tools/doc_provider.py` — 当前无命中。
- `combined_tools_acceptance.py` 的 `_native_tool_source_paths()` **包含** `doc_provider.py`，其 `test_native_providers_do_not_import_old_runtime` 测试会扫描该文件。防线未消失，只是从 doc provider 测试迁移到了 combined acceptance 测试。
- 这是一个 **actionable finding**（见 §9 Finding 1）。

---

## 6. README 更新审查

### 6.1 tests/README.md

**触发检查**：`tests/` 修改 → 触发。`tests/README.md` 更新边界要求"只描述当前 tests/ 已存在的事实"。

**变更审查**：
- 移除 legacy adapter 测试描述行 — 准确，adapter 已不存在。
- 更新 doc/web tools provider 描述：从"迁移"改为"原生"，补充"cancellation outcome" — 准确反映当前测试覆盖。
- 新增 `tool call projection` 测试描述 — 准确反映 Slice 0 新增的 runtime helper 测试目录。
- 更新 import boundary 描述：移除"`_legacy_adapter` reserved-name 防御性引用" — 准确，该 allowlist 已删除。

**结论**：符合 README 更新边界，内容准确。

### 6.2 dayu/fins/README.md

**触发检查**：`dayu/fins/` 修改 → 触发。约束要求"代码真源高于历史 plan"，只写"当前代码已实现的稳定边界"。

**变更**：3 处 `register_fins_read_tools(...)` → `build_fins_read_tool_definitions(...)`：
- Line 167: Read caller 装配示例
- Line 429: 关键执行路径 Read 路径
- Line 624: 扩展点说明

**审查结论**：
- 3 处全部准确对齐当前生产代码：`dayu/fins/tools/provider.py` 和 `dayu/fins/tools/fins_tools.py` 暴露的入口是 `build_fins_read_tool_definitions(...)`。
- 变更最小，未引入 plan/issue 流水账或未落地能力。
- 符合 Fins README 更新约束。

### 6.3 dayu/README.md

**检查**：已全局搜索 `dayu/README.md` 中的 `legacy`、`_legacy_adapter`、`adapter` 关键词。

**结论**：
- 当前 `dayu/README.md` 中所有 "adapter" 都是 LLM provider adapter（如 "OpenAI-compatible / provider adapter"、"provider adapter"），不涉及 legacy tool adapter。
- 工具定义与执行边界描述已是当前 `ToolDefinition` / `ToolBundle` 语义，不提及 OLD / legacy 概念。
- 不更新合理，符合 AGENTS.md README 触发规则。

---

## 7. 全局 Legacy 符号零命中验证

命令：`rg "_legacy_adapter|LegacyToolDeclarationCollector|adapt_collected_tools" dayu tests`

- **生产代码 (`dayu/`)**: 0 matches
- **测试代码 (`tests/`)**: 0 matches
- **预期命中（非可执行文档）**：`docs/host/` 历史 plan artifact 和 `docs/host/issues-implementation-control.md` WU-TOOLS-01-F01-02-R3 条目 — 这些都是历史设计文档，非生产或测试代码，符合计划 §8 Slice 4 的允许边界（"仅允许历史文档或本 plan artifact 命中"）。

**结论**：零命中成立。

---

## 8. AGENTS.md 合规性检查

| 规则 | 检查项 | 结果 |
|---|---|---|
| 禁止兼容性 re-export | 是否有 `from dayu.tools._legacy_adapter import ...` 的 re-export？ | ✅ 无。adapter 目录整个删除，未在 `__init__.py` 或其它模块保留转发。 |
| 禁止兼容性 wrapper/facade | 是否有新函数仅透传到旧 adapter 实现？ | ✅ 无。三个 provider 均为原生 builder，不存在透传 wrapper。 |
| README 更新边界 | tests/README 更新是否超越"当前事实"描述？ | ✅ 准确描述当前状态，未写未落地计划。 |
| 无跨层反向依赖 | 删除 adapter 后是否出现 Engine → Host 或 Host → Fins import？ | ✅ 无新增跨层依赖。 |
| 架构硬约束 | Fins read 是否仍走 `dayu.fins.storage`？ | ✅ 未在本 slice 改变；Slice 3 已验证。 |
| 修改后必做 | pytest / pyright / git diff --check / README 更新 | ✅ Controller 已运行并验证通过。 |

**唯一残留风险**：`dayu/tools/web/web_tools.py` 中存在 `ToolBusinessError` 类名与旧 legacy adapter 类型同名。这不是兼容 re-export（它是 Web 本地新类，不继承旧类型），但可能给未来维护者造成混淆。详见 §9 Finding 2。

---

## 9. Actionable Findings

### Finding 1 (Low — Maintainability)

**描述**：`tests/tools/test_doc_tools_provider.py` 的 `test_read_tools_expose_current_truncate_spec_and_no_old_imports` 删除 `doc_provider_source` 后，不再直接对 `doc_provider.py` 做 AST import 扫描。虽然 `tests/tools/test_combined_tools_acceptance.py` 的 `_native_tool_source_paths()` 包含了 `doc_provider.py` 并提供等效防线，但这是跨文件依赖——未来若有人只修改 doc_provider 并只运行 doc provider 测试，可能漏掉 OLD runtime import 回归。

**证据**：
- `tests/tools/test_doc_tools_provider.py:917-919`（删除前）：曾独立读取 `doc_provider_source` 并做负向断言。
- `tests/tools/test_combined_tools_acceptance.py:958-966`（当前）：`_native_tool_source_paths()` 通过 `explicit_paths` 包含 `doc_provider.py`。

**建议**：在 `test_read_tools_expose_current_truncate_spec_and_no_old_imports` 中恢复对 `doc_provider.py` 的 AST import 扫描，或在该测试 docstring 中记录为什么 doc_provider 不在此测试中检查（指向 combined acceptance 的等效覆盖）。不需要恢复 `_legacy_adapter` 字符串断言，只需要恢复 `_imported_modules(doc_provider_source)` 的 OLD runtime import 检查（即 `dayu.engine.tool_registry`、`dayu.engine.truncation_manager`、`dayu.engine.tool_result`）。

**严重度**：Low。当前有等效防线，只是不在同一测试文件中。不阻塞 PASS。

### Finding 2 (Info — Style)

**描述**：`dayu/tools/web/web_tools.py:292` 的 `ToolBusinessError` 类名与已删除的旧 adapter `ToolBusinessError` 同名。虽然导入路径完全不同（`dayu.tools.web.web_tools.ToolBusinessError` vs 已删除的 `dayu.tools._legacy_adapter.exceptions.ToolBusinessError`），且新类是 Web 领域本地类型（添加了 `url`、`next_action`、`http_status`、`internal_diagnostics` 字段），但将来维护者在全局搜索时可能混淆。

**证据**：
- `dayu/tools/web/web_tools.py:292`: `class ToolBusinessError(Exception):`
- 旧 adapter 已删除，无路径冲突。

**建议**：考虑在后续 WU-TOOLS-01-F08 或独立 cleanup 中将该类重命名（如 `WebToolFailure` 或 `_WebToolError`），与已删除的旧类型彻底区分。当前不是 blocking issue — 它不 import 旧模块，不是 re-export，不影响正确性。

**严重度**：Info。不影响功能或安全，仅影响代码可读性。

---

## 10. Controller 验证结果交叉核对

Controller 声称：
- `pytest` 7 文件/目录共 108 passed
- `pyright` 0 errors
- `git diff --check` passed
- `rg "_legacy_adapter|LegacyToolDeclarationCollector|adapt_collected_tools" dayu tests` 无命中

本 review 独立验证：
- ✅ 已运行 `rg "_legacy_adapter|LegacyToolDeclarationCollector|adapt_collected_tools" dayu/ tests/ --type py` — 0 matches。
- ✅ 已确认 `dayu/tools/_legacy_adapter/` 不存在。
- ✅ 已确认 `tests/tools/test_legacy_tool_adapter.py` 不存在。
- ⚠️ 未独立运行 pytest 和 pyright（Controller 已验证，本 review 信任其输出）。

---

## 11. Residual Risks

| Risk | Status | Owner |
|---|---|---|
| WU-TOOLS-01-F08 documents processor registry naming | deferred | WU-TOOLS-01-F08 |
| Web `ToolBusinessError` 类名与旧 legacy 类型同名 | noted, non-blocking | Future cleanup |
| test_doc_tools_provider 跨文件防线依赖 | noted (Finding 1) | Current maintainer |
| 全仓库 pytest 未运行 | accepted risk | Slice scope limited |

---

## 12. 结论

Slice 4 的 adapter 删除和边界收口改动精准、证据充分、对齐所有约束文档。无 blocking findings。`PASS`。

**下一 gate 建议**：Slice 4 code review re-review（MiMo），通过后进入 R3 aggregate deepreview 或直接进入 final closeout / draft PR gate。
