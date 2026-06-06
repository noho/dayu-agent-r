# WU-TOOLS-01 Slice S6 Code Review

Gate: code-review
Work unit: WU-TOOLS-01
Slice: S6 - Combined Discovery / ToolRuntime Acceptance / Docs Closure
Reviewer: AgentMiMo
Status: PASS-WITH-EXTERNAL-BLOCKER

## Review Scope

- `tests/tools/test_combined_tools_acceptance.py` (new, 996 lines)
- `tests/README.md` (1 line addition)
- `docs/reviews/wu-tools-01-slice6-implementation-codex.md` (implementation artifact, not production)

S6 未修改任何 `dayu/` 生产代码。`git diff HEAD -- dayu/host/ dayu/engine/ dayu/runtime/ dayu/service/ dayu/contracts/` 为空。

## Findings

按严重性排序。无 blocking finding。

### F1 [INFO] Wildcard import 不在 AST 扫描范围内

- 文件: `tests/tools/test_combined_tools_acceptance.py:962-966`
- `_module_imports` 跳过 `from X import *` 节点（`alias.name != "*"` 条件）。若迁移 provider 使用 wildcard import 引入旧 runtime 符号，AST 扫描不会捕获。
- 影响: 低。迁移 provider 实际未使用 wildcard import，且 pyright 会报错。但扫描器的完整性声明应注明此限制。
- 建议: 无需修改，但若未来扩展扫描器，应处理 wildcard import。

### F2 [INFO] `_AcceptingPort` 中硬编码的 digest 值

- 文件: `tests/tools/test_combined_tools_acceptance.py:180`
- `result_digest=f"sha256:{'6' * 64}"` 是测试桩中的魔法字符串。不影响测试正确性，因为测试不验证 digest 内容。
- 影响: 无。测试桩内部实现细节。

### F3 [INFO] 实现 artifact 的 broad command 失败分类需要独立确认

- 实现 artifact 声称 13 个 Host 失败为 "pre-existing Host suites outside S6 allowed production modules"。
- 本 review 已独立验证：`git stash` 后在 S6 前状态运行同一组测试，得到完全相同的 13 个失败。确认为 S6 外部已存在回归。
- 失败根因:
  - `test_dispatch_scheduler.py` (7 项): proactive compaction 测试期望 `proposal manifest ref`，当前 `dispatch.py` 在 `_execute_proactive_compaction` 中抛出 `RuntimeError`。
  - `test_effective_execution_config.py` (2 项): 测试期望 raw system prompt，当前 `RunInputBuilder` 已改为 one-system-message envelope。
  - `test_import_boundary.py` (2 项): 测试禁止的 token/import 在当前已接受代码中已存在（`_legacy_adapter` 引用 reserved `fetch_more`；`compaction_operation` 导入 Engine 合约模块）。
  - `test_phase7_waiting_integration.py` + `test_resolve_wait_command.py` (2 项): 测试期望 `"Accepted wait result fact:"` 文本，当前 resume request 消息已改写。
- 影响: 这些是 Host 层已知回归，非 S6 引入，不阻塞 S6 合并。但应作为独立 Host work unit 跟踪修复。

## S6 Exact Requirements 覆盖验证

| # | Requirement | Test | Verdict |
|---|---|---|---|
| 1 | Combined discovery 单一 bundle | `test_combined_discovery_returns_single_bundle_without_reserved_names` | PASS |
| 2 | 无重复工具名 | 同上 `len(names) == len(set(names))` | PASS |
| 3 | Reserved `fetch_more` 不在业务 bundle | 同上 `FETCH_MORE.value not in names` | PASS |
| 4 | 所有迁移工具使用 current `ToolTruncateSpec` | `test_combined_truncate_specs_and_fetch_more_owner` `type(definition.truncate) is ToolTruncateSpec` | PASS |
| 5 | `FETCH_MORE` 由 ToolRuntime 注入并拥有 | 同上 `isinstance(fetch_more.callable, FetchMoreToolCallable)` | PASS |
| 6 | Service assembly 传 effective bundle 给 Host | `test_compose_open_host_options_passes_effective_bundle_to_host` `business_tool_bundle is result.effective_tool_bundle` | PASS |
| 7 | ToolRuntime 执行三类 provider 代表工具 | `test_toolruntime_executes_representative_provider_tools_and_accepts_facts` | PASS |
| 8 | Host accept barrier 记录 accepted facts | 同上 `len(accept_port.candidates) == 3` | PASS |
| 9 | Input projection (路径投影 + 数值 coercion) | 同上 `doc_value["file_path"] == str(doc_file.resolve())` + `recency_days == 7` | PASS |
| 10 | Response projection (无 OLD ok envelope) | 同上 `"ok" not in doc_value/fins_value/web_value` | PASS |
| 11 | 代表性失败投影为 current `ToolFailedOutcome` | `test_representative_failures_project_to_current_failed_outcomes` | PASS |
| 12 | ScenePrepare tags 选择 doc/fins/web | `test_scene_prepare_tags_select_doc_fins_and_web_tools` | PASS |
| 13 | Web SERIAL_PER_PROVIDER 并发策略 | `test_web_provider_serial_policy_holds_under_concurrent_calls` `max_active_calls == 1` | PASS |
| 14 | 无 OLD runtime import | `test_migrated_providers_and_adapter_do_not_import_old_runtime` AST 扫描 | PASS |

## OLD Runtime 依赖检查

- `test_migrated_providers_and_adapter_do_not_import_old_runtime` 扫描 `_legacy_adapter/`、`dayu/tools/web/`、`dayu/fins/tools/`、`doc_provider.py`、`doc_tools.py`。
- 禁止 import: `dayu.engine.tool_registry`、`dayu.engine.truncation_manager`、`dayu.engine.tools.fetch_more`。
- 禁止 projection token: `project_for_llm`、`fetch_more_args`、`continuation_hint`。
- 结果: 0 个违规。

## 编码约束检查

| 约束 | 状态 |
|---|---|
| 中文 docstring | PASS - 所有类/函数/方法均有中文 docstring |
| 无 `Any` / `object` / 无类型参数 | PASS |
| 无 `hasattr` / `getattr` | PASS |
| 无魔法数字/字符串（schema 例外） | PASS - 唯一的硬编码字符串在测试桩和常量定义中 |
| 无兼容性 re-export / wrapper | PASS |
| pyright | PASS - 0 errors |

## 测试质量检查

| 检查项 | 状态 |
|---|---|
| Deterministic（无 live network） | PASS - Web 调用通过 monkeypatch 替换为 fake |
| Deterministic（无 live browser） | PASS - 无 Playwright 调用 |
| Deterministic（无 live model） | PASS - 无 LLM 调用 |
| 使用 tmp_path 隔离 | PASS - 所有涉及文件系统的测试使用 pytest tmp_path |
| 无硬编码路径 | PASS - 所有路径通过 tmp_path 派生 |

## Residual Closure 验证

| Residual | Claimed Status | Evidence | Verdict |
|---|---|---|---|
| R1 path safety | closed | S3 path whitelist + S6 combined `read_file` 路径投影为绝对路径 | PASS |
| R2 typed config | closed | S6 workspace `tool_discovery.json` fixture 传入 typed config | PASS |
| R3 ToolDiscovery/ToolRuntime | closed | S6 三 provider 聚合 + ToolRuntime 执行 + accept barrier | PASS |
| R4 truncation/fetch_more | closed | S6 `ToolTruncateSpec` 类型检查 + `FetchMoreToolCallable` 注入检查 | PASS |
| R5 query/response projection | closed | S6 路径投影、数值 coercion、成功/失败 outcome 投影 | PASS |
| S3-R1 response projector | closed | S6 combined outcome 未扩散为 OLD projection | PASS |
| S4-R1 Fins ingestion | deferred | 合理 - S6 只覆盖 read tools | PASS |
| S5-R1 Web concurrency | closed | S6 并发 callable 测试 `max_active_calls == 1` | PASS |
| S5-R2 Web live coverage | deferred | 合理 - 用户硬约束 deterministic | PASS |
| S1-R1 documents coverage | partially closed | 合理 - 已消费路径已覆盖 | PASS |

## README / Docs 同步

- `tests/README.md`: 新增 combined tools acceptance 描述，与测试实际覆盖范围一致。触发规则 `tests/` 修改 -> 更新 `tests/README.md`。PASS。
- 其他 README: 实现 artifact 声称无变化，与 S6 未修改生产代码一致。PASS。

## Conclusion

**PASS-WITH-EXTERNAL-BLOCKER**

S6 实现完整覆盖全部 14 项 exact requirements。测试 deterministic、typing 合规、无 OLD runtime 依赖。Residual closure 证据充分。

Broad command 的 13 个 Host 失败经独立验证为 S6 前已存在的 Host 层回归，非 S6 引入：
- 7 项 `test_dispatch_scheduler.py`: proactive compaction `proposal manifest ref` 缺失
- 2 项 `test_effective_execution_config.py`: system prompt envelope 期望不匹配
- 2 项 `test_import_boundary.py`: import boundary 期望与当前代码不一致
- 2 项 `test_phase7_waiting_integration.py` + `test_resolve_wait_command.py`: wait resume 文本不匹配

这些 Host 回归应作为独立 Host work unit 跟踪，不阻塞 S6 合并。
