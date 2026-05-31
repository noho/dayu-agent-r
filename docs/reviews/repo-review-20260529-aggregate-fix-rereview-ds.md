# AgentDS Re-review: repo-review-fix 修复验证

## 输入

- MiMo review: `docs/reviews/repo-review-20260529-220422.md` (13 findings)
- DS review: `docs/reviews/repo-review-20260529-215815.md` (18 findings)
- 修复说明: `docs/reviews/repo-review-20260529-aggregate-fix-codex.md`

## 验证方法

基于当前 workspace diff 逐项核验修复说明中声明的 11 项已修复 + 低风险小修，并对 6 项未修项裁定做合理性判断。

## 已修复项核验

### 1. purge RunStatus 同源 — PASS

- `state.py`: `TERMINAL_RUN_STATUSES` 和 `NON_TERMINAL_RUN_STATUSES` 提升为模块级公开常量，由 `RunStatus` enum 派生。
- `purge.py`: 删除了 9 个重复的 `_RUN_STATUS_*` 字符串常量，改为从 `state` 导入并派生 `_TERMINAL_RUN_STATUS_VALUES` / `_NON_TERMINAL_RUN_STATUS_VALUES` frozenset。
- 验证: `test_purge_session.py` 6 种非终态 status 参数化测试全部通过。

### 2. schema v15 active Run CHECK — PASS

- `HOST_SCHEMA_VERSION` 从 14 bump 到 15。
- 新增 CHECK 约束: `status NOT IN ('running', 'waiting', 'cancelling', 'recovering') OR (started_event_id IS NOT NULL AND started_event_sequence IS NOT NULL)`。
- 错误消息改为 `"expected fresh schema ..., got ...; recreate the durable database for this version"`。
- 验证: `test_durable_schema.py` 全量通过。Schema 按项目 fresh schema 规则处理，无旧库兼容逻辑。

### 3. _NoToolBundle unsafe cast — PASS

- `tools_discovery.py`: 删除 `_NoToolBundle` sentinel 类及其 `cast(ToolBundle, ...)` 强转。
- `tool_declaration.py`: `ToolBundle` 增加 `_allow_empty: InitVar[bool] = False` 参数。`__post_init__` 仅在 `not self.definitions and not _allow_empty` 时拒绝空集合。
- 公共默认构造 `ToolBundle(definitions=...)` 行为不变（拒绝空）。内部 no-tool 路径使用 `ToolBundle(definitions=(), _allow_empty=True)`。
- `_allow_empty` 是 `InitVar`，不存储为实例字段，不污染 `ToolBundle` 公共接口。
- 验证: `test_tool_declaration.py`, `test_tools_discovery.py`, `test_host_assembly.py` 全部通过。

### 4. compaction merge-level reject — PASS

- `compaction_operation.py:255-264`: merge quality check 失败时，追加一个 `_attempt_rejected(..., failure_category=_FAILURE_QUALITY_CHECK_REJECTED, repairable=False, ...)` 到 `rejected` 列表。
- 验证: `test_multi_pass_merge_quality_reject_records_rejected_attempt` 专项测试通过。

### 5. budget_after_compact overhead — PASS

- 导入 `DEFAULT_ESTIMATOR_MESSAGE_OVERHEAD_TOKENS` 和 `DEFAULT_ESTIMATOR_TOOL_SCHEMA_OVERHEAD_TOKENS`。
- `_budget_after_compact`: 每个 structured fragment 叠加 message overhead；增加 `tool_schema_overhead` 项。
- `_estimate_preserved_context_tokens`: typed fragments 叠加 message overhead；增加 base message count 的 framing。
- 验证: `test_llm_context_compactor_budget_counts_preserved_context` 通过。仍为保守估算而非精确 tokenization，但口径已补齐。

### 6. dispatch drain loop fail-close — PASS

- `_drain_loop` 中新增独立的 `except HostTransactionRetryExhaustedError` 分支（在通用 `except Exception` 之前）。
- 该分支: 记录 ERROR 日志 → 设置 `self._closed = True` → 调用 `_best_effort_mark_host_instance_stopped("drain_loop_durable_retry_exhausted")`。
- 通用异常分支行为不变: WARNING + sleep + continue。
- `__init__` 新增 `_close_cleanup_done = False` 字段，`close()` 方法中使用 `if self._closed and self._close_cleanup_done: return` 防止重复清理。
- 验证: `test_drain_loop_fail_closes_on_durable_retry_exhausted` 和 `test_drain_loop_logs_unexpected_exception` 通过。

### 7. session lifecycle projection catch-up — PASS

- `command.py` 导入 `catch_up_projection_best_effort`。
- `ensure_session`, `create_session`, `close_session` 在 durable write 提交后调用 `catch_up_projection_best_effort(host._admission_service.projection_catchup_port)`。
- 与 `start_run` (admission.py:548) 和 `submit_followup_queue` (admission.py:590) 的 catch-up 模式一致。
- 验证: `test_session_lifecycle_commands_trigger_projection_catchup` 通过。

### 8. WAL autocheckpoint — PASS

- `transaction.py`: `configure_connection_pragmas` 中增加 `PRAGMA wal_autocheckpoint=256`。
- 验证: `test_configure_connection_pragmas_sets_wal_autocheckpoint` 通过。

### 9. ToolCallAggregator id remap — PASS

- 新增 `_remap_partial_index(source_index, target_index)` 方法: 合并旧 synthetic partial 到 provider 原生 index，包括 name/arguments_buffer/provider_state 迁移，以及 `_index_by_id` 和 `_index_by_position` 的指针更新。
- `feed()` 方法: `setdefault` 改为直接赋值 `self._index_by_id[delta_id] = index`；若 `delta_id` 已有映射且 index 不同，先调用 `_remap_partial_index` 合并。
- 验证: `test_later_native_index_remaps_existing_id_partial` 通过。

### 10. sqlite_errorcode getattr — PASS

- `transaction.py:_sqlite_errorcode`: 从 `getattr(error, "sqlite_errorcode", None)` 改为 `try: code = error.sqlite_errorcode  # type: ignore[attr-defined] / except AttributeError: return None`。
- 行为等价，符合项目 "禁止用 getattr 逃避类型设计" 约束。

### 11. 低风险小修 — 全部 PASS

- `sse_parser.py:161`: `_byte_buffer` 字段已删除。
- `compaction.py:1566-1569`: `preserved_canonical_evidence_refs` 校验改为 `_require_unique_string_tuple`。
- `compact_material.py:1008-1020`: `_evidence_provenance` 删除未使用的 `blocks` 参数，调用方同步修改。
- `scene_prepare.py`: `SceneFragmentRef` 加入 `__all__`。
- `scene_prepare.py:_require_json_object`: 新增 key 为字符串的校验。
- `open_host.py:741`: `del exc_type, exc_value, traceback` 已删除。
- 验证: 各自对应测试通过。

## 重点风险专项审查

### R1: ToolBundle 内部空构造入口泄漏风险

`_allow_empty: InitVar[bool] = False` 设计正确：
- `InitVar` 确保参数仅在 `__init__` 和 `__post_init__` 中可用，不存储为实例字段。
- 下划线前缀 `_allow_empty` 向调用方传达内部使用语义。
- 公共默认构造行为不变（拒绝空集合）。
- 外部调用方需显式传 `_allow_empty=True` 才能绕过——非误用风险。
- **结论: 无泄漏风险。**

### R2: Schema bump fresh schema 合规性

- Version 14→15，无 ALTER TABLE 迁移逻辑。
- 错误消息明确引导 "recreate the durable database"。
- 与项目 "按全新 schema 起库处理，禁止旧库兼容" 的规则一致。
- **结论: 合规。**

### R3: Dispatch fail-close 误杀可恢复异常

- 仅 `HostTransactionRetryExhaustedError` 触发 fail-close。该类仅在 transaction runner 耗尽所有 write retry 后抛出，语义是"持久层已不可用"。
- 其他 `Exception`（含 `RuntimeError`）仍按原行为：WARNING + sleep + continue。
- `close()` 方法的 `_close_cleanup_done` 防护防止 fail-close 路径与调用方 `close()` 重复清理。
- **结论: 不会误杀可恢复异常，fail-close 触发条件正确。**

### R4: 大 diff 格式化 vs 行为漂移

逐文件审计结论：
- `state.py` (695→? lines): 大量 `_require_*` 调用从多行展开为单行，以及函数签名单行化。零行为变更。
- `compaction.py`, `compaction_operation.py`, `llm_compaction.py`, `dispatch.py`, `compact_material.py`: 同模式——行宽约束放宽导致的格式化归一，辅以少量实质性修复。
- `purge.py`: 格式化 + 状态常量同源修复（实质变更）。
- `schema.py`: 格式化 + CHECK 约束新增（实质变更）。
- `sse_parser.py`: 格式化 + `_byte_buffer` 删除（实质变更）。
- `tool_call_aggregator.py`: 格式化 + `_remap_partial_index` 新增（实质变更）。
- `tools_discovery.py`: 格式化 + `_NoToolBundle` 删除（实质变更）。
- **结论: 无行为漂移。实质变更与格式化变更可清晰分离。**

## 未修项裁定合理性判断

| 未修项 | 裁定 | 判断 |
|--------|------|------|
| schema 迁移机制 | 不实施，强化 mismatch 消息 | 合理。项目规则明确 fresh schema 策略 |
| command-handle-only Noop wakeup | 不实施，需单独设计 | 合理。涉及 composition boundary 重构 |
| `_promote_after_release` RuntimeError | 不实施，startup recovery 可恢复 | 合理。可观测性增强留后续 |
| dispatch `ingest_async` LOST 异常归类 | 不实施 | 合理。影响面大，需独立设计 |
| EventLogStore 纯委托 | 不实施 | 合理。架构演进，非 bugfix |
| contracts/runtime 重复 helper | 不实施 | 合理。需统一抽取设计 |
| active cancel hook race | 不实施 | 合理。并发时序复现困难 |
| major 测试空白 | 不实施 | 合理。持续补齐，非本轮阻塞 |
| SSE 多 choice finish_reason | 不实施 | 合理。实际触发概率极低 |
| resolve_wait service 实例化一致性 | 不实施 | 合理。无功能影响 |
| dead code (scene_prepare 不可达分支等) | 未提及 | 注意：`scene_prepare.py:1027-1029` 不可达分支本轮未清理，但不在修复说明未修列表。影响极低。 |

所有未修项裁定均有充分理由，无直接证据表明当前 diff 引入新 bug。

## 测试与类型检查

- `pytest`: 120 passed, 0 failed
- `pyright`: 0 errors, 0 warnings, 0 informations

## 残余风险

1. **ToolBundle `_allow_empty`**: 虽然 `InitVar` + 下划线前缀大幅降低误用风险，但 Python 运行时不强制阻止外部传参。若后续 contracts 层重构，建议将空 bundle 构造入口收口到 factory 函数，完全隐藏 `_allow_empty`。
2. **compact 后预算估算**: 仍为保守估算而非 provider tokenizer 精确值。当前版本已将 Host 端估算器常数的口径补齐，但不同 provider 的实际 token 消耗可能偏差较大。
3. **dispatch fail-close 后恢复**: `_drain_loop` fail-close 后 scheduler 停止接收新 wakeup。调用方需按现有 Host lifecycle 重开 scheduler 或走 startup recovery。
4. **scene_prepare 不可达分支**: `_load_fragment_contents:1027-1029` 的死代码分支本轮未清理。无功能影响，但遗留了认知负担。

## 结论

**PASS** — 所有已修复项经直接代码证据和测试验证确认正确修复；未修项裁定合理；重点风险审查未发现 blocker；测试 120 passed，pyright 零错误。

输出 artifact: `docs/reviews/repo-review-20260529-aggregate-fix-rereview-ds.md`
