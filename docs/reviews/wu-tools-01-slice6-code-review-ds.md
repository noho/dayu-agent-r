# WU-TOOLS-01 Slice S6 Code Review (AgentDS)

Gate: code review
Work unit: WU-TOOLS-01
Slice: S6 - Combined Discovery / ToolRuntime Acceptance / Docs Closure
Reviewer: AgentDS
Verdict: **PASS-WITH-EXTERNAL-BLOCKER**

## Review Scope

审查对象：当前未提交 S6 变更。变更仅含两项：
- 新增 `tests/tools/test_combined_tools_acceptance.py`（996 行，8 个测试用例）
- 修改 `tests/README.md`（+1 行，描述新增 combined tools acceptance 测试套件）

未触碰任何 `dayu/` 生产代码。

## Evidence Basis

- 本地复核 `pytest tests/tools/test_combined_tools_acceptance.py`：8 passed，0 failed
- 本地复核 `pyright tests/tools/test_combined_tools_acceptance.py`：0 errors
- 本地复核 `pyright`（全量）：0 errors
- 本地复核 `git diff --check`：clean
- Codex artifact `docs/reviews/wu-tools-01-slice6-implementation-codex.md` 的 implementation evidence 经独立验证
- 13 个失败测试的根因通过直接运行和源码审查独立确认

## Requirement Coverage Matrix

| # | Plan Requirement | Test | Status |
|---|-----------------|------|--------|
| 1 | `ToolsDiscovery` returns one bundle, no duplicates, no reserved `fetch_more` | `test_combined_discovery_returns_single_bundle_without_reserved_names` | ✅ PASS |
| 2 | All truncating tools use current `ToolTruncateSpec`; `FrameworkToolName.FETCH_MORE` is ToolRuntime-owned | `test_combined_truncate_specs_and_fetch_more_owner` | ✅ PASS |
| 3 | No migrated provider/adapter imports OLD `ToolRegistry`/`TruncationManager`/`fetch_more` or OLD projection tokens | `test_migrated_providers_and_adapter_do_not_import_old_runtime` | ✅ PASS |
| 4 | `compose_open_host_options` passes effective bundle to Host | `test_compose_open_host_options_passes_effective_bundle_to_host` | ✅ PASS |
| 5 | ToolRuntime executes representative Doc/Fins/Web tools through accept barrier | `test_toolruntime_executes_representative_provider_tools_and_accepts_facts` | ✅ PASS |
| 6 | Representative failures project to current outcomes | `test_representative_failures_project_to_current_failed_outcomes` | ✅ PASS |
| 7 | `ScenePrepare` tags select `doc`/`fins`/`web` tools | `test_scene_prepare_tags_select_doc_fins_and_web_tools` | ✅ PASS |
| 8 | Web provider serial policy holds under concurrent calls | `test_web_provider_serial_policy_holds_under_concurrent_calls` | ✅ PASS |

所有 8 个 plan requirement 均有直接测试覆盖，且全部通过。

## Detailed Findings

### Finding 1: Input Projection / Coercion Verification (NON-BLOCKING, verified correct)

**文件**: `tests/tools/test_combined_tools_acceptance.py:361-369`, `394-395`

测试 `test_toolruntime_executes_representative_provider_tools_and_accepts_facts` 验证了 Web provider 的 `recency_days=7.0` 被 coercion 为整数 `7`，`max_results=3.0` 被 coercion 为整数 `3`（line 394-395）。同时验证了 Doc provider 的 `file_path` 被 adapter 投影为绝对路径（line 387）。

这与 plan requirement "Representative provider calls cover input projection/coercion where needed" 一致。

### Finding 2: Response Projection Verification (NON-BLOCKING, verified correct)

**文件**: `tests/tools/test_combined_tools_acceptance.py:383`, `391-393`, `444-447`

成功路径：三个 provider 返回值均为 `ToolCompletedOutcome`（line 383），且均不含 OLD `"ok"` key（line 391-393）。
失败路径：三个 provider 失败均为 `ToolFailedOutcome`（line 444），`read_file` 的 `start_line=8, end_line=1` 失败投影为 `result.ok is False`（line 445），`search_document` 和 `search_web` 参数冲突失败投影为 `result.error == "invalid_argument"`（line 446-447）。

与 plan requirement "representative provider success and failure responses project to current `ToolCompletedOutcome` / `ToolFailedOutcome` without OLD `ok/value` nesting" 一致。

### Finding 3: Fetch_more Injection Verification (NON-BLOCKING, verified correct)

**文件**: `tests/tools/test_combined_tools_acceptance.py:228-232`

测试验证 `FrameworkToolName.FETCH_MORE` 在 business bundle 中不存在（line 225-227），但出现在 `runtime.effective_bundle.injected_framework_tool_names` 中（line 228），且其 callable 为 `FetchMoreToolCallable` 实例（line 231），并且 `effective_bundle.fetch_more_callable` 指向同一实例（line 232）。

与 plan requirement "current ToolRuntime owns `FrameworkToolName.FETCH_MORE`" 一致。

### Finding 4: Service Assembly Verification (NON-BLOCKING, verified correct)

**文件**: `tests/tools/test_combined_tools_acceptance.py:295-300`

测试验证 `result.options.tooling_options.business_tool_bundle is result.effective_tool_bundle`（line 295），即 Host 收到的 `business_tool_bundle` 对象与 Service 构造的 `effective_tool_bundle` 是同一个对象。同时验证 `source_refs` 正确传递（line 296）和所有 truncating definitions 均为 `ToolTruncateSpec`（line 298-300）。

### Finding 5: AGENTS.md Compliance (NON-BLOCKING, verified correct)

对 `test_combined_tools_acceptance.py` 的合规检查：

| 约束 | 检查结果 |
|------|---------|
| 无 `Any` / `object` 类型签名 | ✅ 全文未使用 `Any` 或 `object` 作为类型注解 |
| 无 `hasattr` / `getattr` | ✅ 全文未使用 |
| 完整中文 docstring | ✅ 所有函数/类/模块均有中文 docstring，包含参数/返回值/异常 |
| 无魔法数字/字符串 | ✅ 所有常量在模块顶部声明为 `Final` |
| 无 OLD 模块导入 | ✅ 所有导入均为 current 路径（`dayu.host.tool_runtime`、`dayu.service.host_assembly` 等） |
| 确定性测试 | ✅ 无 live network/model/browser；Web 通过 `monkeypatch.setattr` 替换 |
| `tests/README.md` 更新 | ✅ 新增一行描述 combined tools acceptance 覆盖范围 |

`tests/README.md` 的修改正确触发：`tests/` 变更 → 更新 `tests/README.md`。变更内容准确描述新增测试套件的覆盖范围，不越界不重复。

### Finding 6: Residual Closure Evidence (NON-BLOCKING, verified)

| Residual | Claimed Status | S6 Evidence | Verdict |
|----------|---------------|-------------|---------|
| WU-TOOLS-01-R1 path safety | Closed | `read_file` 路径在组合执行中被投影为绝对路径（line 387） | ✅ 证据充分 |
| WU-TOOLS-01-R2 typed config | Closed | Fixture config 向三个 provider 传入 typed config（line 630-686） | ✅ 证据充分 |
| WU-TOOLS-01-R3 ToolDiscovery/ToolRuntime | Closed | Combined discovery + ToolRuntime 执行 + accept barrier（test 1, 2, 5） | ✅ 证据充分 |
| WU-TOOLS-01-R4 truncation/fetch_more | Closed | 业务 bundle 不含 fetch_more；ToolRuntime 注入 FetchMoreToolCallable（test 2） | ✅ 证据充分 |
| WU-TOOLS-01-R5 query/response projection | Closed | 三个 provider 的 input coercion 和 outcome projection（test 5, 6） | ✅ 证据充分 |
| WU-TOOLS-01-S3-R1 response projector placement | Closed | AST 扫描无 OLD import（test 3）；outcome 均为 current 类型（test 5, 6） | ✅ 证据充分 |
| WU-TOOLS-01-S4-R1 Fins ingestion waiting | Deferred | S6 只覆盖 read tools（`include_ingestion_tools=false`） | ✅ 按计划 defer |
| WU-TOOLS-01-S5-R1 Web concurrency | Closed | 并发 callable 测试证明 `SERIAL_PER_PROVIDER` 生效（test 8） | ✅ 证据充分 |
| WU-TOOLS-01-S5-R2 Web live network | Deferred | S6 继续 deterministic/no-live-network | ✅ 按计划 defer |
| WU-TOOLS-01-S1-R1 documents coverage/parity | Partially closed | Doc Markdown + Docling JSON + Fins Markdown + Web mocked paths covered | ✅ 按计划部分 close |

所有 residual 声明有对应的 S6 测试证据支持，deferred 项目有明确 owner/destination。

## 13 Failed Tests: Root Cause Analysis

以下 13 个测试在 `pytest tests/runtime tests/service tests/tools tests/fins tests/host` 中失败。经直接运行和源码审查，**全部为预存失败，非 S6 变更引入**。

### 证据：S6 变更不触碰任何生产代码

```
$ git diff HEAD --stat
 tests/README.md | 1 +
 1 file changed, 1 insertion(+)
```

新增文件 `tests/tools/test_combined_tools_acceptance.py` 在 `tests/` 目录下，不在 `dayu/` 源码范围内。S6 未修改任何 `dayu/` 下的生产代码。

### Group A: Proactive Compaction (7 failures)

| 测试 | 文件 | 根因 |
|------|------|------|
| `test_pre_start_governance_soft_threshold_compacts_before_attempt` | `tests/host/test_dispatch_scheduler.py:3613` | `RuntimeError: accepted compaction is missing proposal manifest ref` at `dayu/host/dispatch.py:3744` |
| `test_proactive_compaction_uses_selected_material_not_session_start_range` | `tests/host/test_dispatch_scheduler.py:3690` | 同上 |
| `test_proactive_material_pack_not_larger_than_ordinary_material_for_same_view` | `tests/host/test_dispatch_scheduler.py:3725` | 同上 |
| `test_wake_queue_promotion_uses_tracked_async_promotion_task` | `tests/host/test_dispatch_scheduler.py:3757` | 同上 |
| `test_proactive_compaction_calls_llm_outside_write_transaction` | `tests/host/test_dispatch_scheduler.py:3890` | 同上 |
| `test_proactive_compaction_retries_quality_rejection_before_accept` | `tests/host/test_dispatch_scheduler.py:3967` | 同上 |
| `test_multi_turn_proactive_compact_feeds_subsequent_run_input` | `tests/host/test_dispatch_scheduler.py:4257` | 同上 |

**分类**: 预存 Host compaction 实现问题。`_required_compactor_manifest_ref()` 在 `dayu/host/dispatch.py:3744` 抛出 RuntimeError，表明 proactive compaction 的 `CompactionOperationResult.accepted_proposal_manifest_ref` 为 None。该逻辑位于 S6 未触碰的 Host dispatch 模块内。

### Group B: Effective Execution Config (2 failures)

| 测试 | 文件 | 根因 |
|------|------|------|
| `test_field_level_partial_merge_uses_baseline_for_omitted_fields` | `tests/host/test_effective_execution_config.py:208` | 测试期望 `messages[0].content == "system slice3"`，但当前 RunInputBuilder 在系统提示后追加了 `"\n\n## Execution Guidance\nUse the available context and tools under the current run limits.\nTools are disabled for this runner call."` |
| `test_descriptor_payload_dispatch_uses_per_run_override` | `tests/host/test_effective_execution_config.py:371` | 同上系统提示不匹配；另有 `RuntimeError: HostDispatchScheduler is closed` 二次失败 |

**分类**: 预存 one-system-message envelope 变更导致的测试期望不同步。RunInputBuilder 的系统提示包装逻辑在 S6 之前的提交中变更，S6 未触碰相关代码。

### Group C: Import Boundary (2 failures)

| 测试 | 文件 | 违规文件 | 引入提交 |
|------|------|---------|---------|
| `test_fetch_more_token_stays_inside_toolruntime_owner_modules` | `tests/host/test_import_boundary.py:223` | `dayu/tools/_legacy_adapter/__init__.py`, `definition_adapter.py`, `registry_collector.py` | `0b4dcd81` (WU-TOOLS-01 slice 4) |
| `test_host_engine_imports_stay_on_allowed_boundary_modules` | `tests/host/test_import_boundary.py:242` | `dayu/host/compaction_operation.py` | `9f5061e3` (Host layer follow-up) |

**分类**: Import boundary allowlist 过期。这两个测试通过 AST 扫描源码检测分层违规，其 allowlist（`FETCH_MORE_ALLOWED_RELATIVE_FILES` 和 `HOST_ENGINE_CONTRACT_ALLOWED_MODULES`）在近期其他工作单元新增模块后未同步更新。

**test 10 详细分析**: `_legacy_adapter/` 中的 `fetch_more` 引用均为防御性使用——`_RESERVED_FETCH_MORE_TOOL_NAME = "fetch_more"`（`definition_adapter.py:42`）和 `raise ValueError("legacy adapter must not expose fetch_more as a business tool")`（line 435, 462）——语义上正确，但 import boundary 测试的简单字符串扫描无法区分合法防御性引用与违规导出。该 allowlist 缺失在 WU-TOOLS-01 slice 4 引入 `_legacy_adapter/` 目录时即已存在。

**test 11 详细分析**: `compaction_operation.py:23-24` 导入 `dayu.engine.contracts.agent_run` 和 `dayu.engine.contracts.engine_events`，属于 Host 合法依赖 Engine contracts 的边界，但 allowlist 未包含 `compaction_operation.py`。该文件在 Host layer follow-up（`9f5061e3`）中引入。

### Group D: Wait/Resume (2 failures)

| 测试 | 文件 | 根因 |
|------|------|------|
| `test_local_awaiting_tool_manual_resolve_resumes_run` | `tests/host/test_phase7_waiting_integration.py:277` | `"Accepted wait result fact:"` 文本不再出现在 resume request messages 中 |
| `test_resolve_wait_completed_resumes_run_and_wakes_dispatch` | `tests/host/test_resolve_wait_command.py:113` | 同上 |

**分类**: 预存 Host wait/resume 文本变更。resume request 的构造文本在 S6 之前的变更中修改，测试仍期望旧文本。

### 13 Failures: Classification Summary

| Group | Count | Root Cause | S6 Introduced? | Classification |
|-------|-------|-----------|----------------|----------------|
| A - Proactive compaction | 7 | `RuntimeError: missing proposal manifest ref` in `dayu/host/dispatch.py:3744` | **No** | Pre-existing Host compaction bug |
| B - Effective execution config | 2 | System prompt envelope mismatch | **No** | Pre-existing Host test/impl sync gap |
| C - Import boundary | 2 | Allowlist not updated for earlier work units | **No** | Pre-existing allowlist staleness |
| D - Wait/Resume | 2 | Resume request text change | **No** | Pre-existing Host text mismatch |

**裁决**: 全部 13 个失败均为 S6 外部预存问题。S6 变更（纯测试/文档）不可能引入这些 Host 层失败。这些失败作为 **external blocker** 记录，不影响 S6 自身的 PASS 判定。

## AGENTS.md 约束违规

无。S6 变更完全遵守 AGENTS.md 的所有约束。

## 未覆盖项与风险

1. **13 个预存 Host 测试失败（external blocker）**: 这些失败阻塞了 plan 要求的完整 `pytest tests/runtime tests/service tests/tools tests/fins tests/host` 命令。虽然非 S6 引入，但它们阻碍了 S6 之后的 gate 推进（如 deepreview 的全量验证）。
   - 建议：在 S6 accept 后，由 Controller 裁决是否在推进前修复这些预存失败，特别是 Group C 的 import boundary allowlist 更新（WU-TOOLS-01 内部 regression）。
2. **Web provider 并发策略的 future hardening**: S5-R1 已 close 但 S6 测试只验证了 `search_web` 的 `SERIAL_PER_PROVIDER`。如果未来放宽为并发，需要独立的 provider concurrency hardening。
3. **Live network/browser 覆盖**: S5-R2 deferred。S6 按设计约束继续跳过 live network 测试。这部分需要独立的 integration test work unit。

## Review Conclusion

S6 实现完整覆盖了 plan 规定的所有 8 个 exact requirement，全部 8 个测试通过，pyright 零错误，AGENTS.md 完全合规。13 个 broad command 失败全部确认为 S6 外部预存问题，不影响 S6 本身验收。

**Verdict: PASS-WITH-EXTERNAL-BLOCKER**

External blockers:
- `tests/host/` 下 13 个预存失败，根因分别为 Host proactive compaction 实现 bug（7）、one-system-message envelope 测试不同步（2）、import boundary allowlist 过期（2）、wait/resume 文本变更（2）
- 其中 import boundary test 10（`test_fetch_more_token_stays_inside_toolruntime_owner_modules`）是 WU-TOOLS-01 slice 4 引入的内部 regression，应在 WU-TOOLS-01 完结前修复
