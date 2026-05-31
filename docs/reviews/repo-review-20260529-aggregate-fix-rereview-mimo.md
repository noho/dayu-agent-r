# repo-review-fix Re-Review (MiMo)

## 输入

- 原始 MiMo review: `docs/reviews/repo-review-20260529-220422.md`
- 原始 DS review: `docs/reviews/repo-review-20260529-215815.md`
- 修复说明: `docs/reviews/repo-review-20260529-aggregate-fix-codex.md`

## 核验方法

逐项读取当前 workspace diff 中的生产代码与测试，基于直接代码证据判断修复是否到位。

---

## 逐项核验

### 1. purge RunStatus 同源 — PASS

- `purge.py:58` 导入 `from dayu.host.durable.state import NON_TERMINAL_RUN_STATUSES, TERMINAL_RUN_STATUSES`
- `state.py:56-59` 由 `RunStatus` enum 派生两个 `frozenset`，是唯一真源
- `purge.py:108-109` 用 `_NON_TERMINAL_RUN_STATUS_VALUES = frozenset(status.value for status in NON_TERMINAL_RUN_STATUSES)` 转为字符串值集合
- 新增 `RunStatus` 值时自动同步，不再存在手动维护的重复字符串集合

### 2. schema v15 active Run CHECK — PASS

- `schema.py:26`: `HOST_SCHEMA_VERSION = 15`
- `schema.py:387-392`: CHECK 约束 `status NOT IN ('running', 'waiting', 'cancelling', 'recovering') OR (started_event_id IS NOT NULL AND started_event_sequence IS NOT NULL)`
- 覆盖了所有 active 非终态，确保 `started_event_id/sequence` 必须存在
- fresh schema 规则下不做旧库迁移，符合项目约束

### 3. 空工具发现类型真实表达 — PASS

- `tool_declaration.py:122-148`: `ToolBundle` 使用 `InitVar[bool] _allow_empty=False`
- `__post_init__` 中 `if not self.definitions and not _allow_empty: raise ValueError`
- `tools_discovery.py:260-263`: 空工具时 `ToolBundle(definitions=(), _allow_empty=True)` — 真实 `ToolBundle` 实例，不再是 `_NoToolBundle` unsafe cast
- 公共默认构造仍拒绝空 bundle，`_allow_empty` 仅框架内部 no-tool 路径可用
- `isinstance(result.tool_bundle, ToolBundle)` 在空工具场景下现在返回 `True`

### 4. compaction merge-level rejected attempt — PASS

- `compaction_operation.py:249-268`: merge 后 `check_compaction_candidate` 返回 `accepted=False` 时，先 `rejected.append(_attempt_rejected(...))` 再 return
- `rejected_attempts` 包含 merge-level 条目，调用方可区分"各 pass 通过但 merge 质量不足"与"某 pass 质量不足"

### 5. budget_after_compact overhead — PASS

- `llm_compaction.py:1239-1244`: `structured_output_tokens` 已包含 `DEFAULT_ESTIMATOR_MESSAGE_OVERHEAD_TOKENS`（per message）
- `llm_compaction.py:1243`: `tool_schema_overhead = DEFAULT_ESTIMATOR_TOOL_SCHEMA_OVERHEAD_TOKENS * _POST_COMPACT_TOOL_SCHEMA_OVERHEAD_COUNT`
- `llm_compaction.py:1244`: 返回值 = `structured_output_tokens + preserved_tokens + tool_schema_overhead`
- 预算估算现在包含 message framing 和 tool schema 开销

### 6. dispatch durable retry exhausted fail-close — PASS

- `dispatch.py:1839-1847`: `except HostTransactionRetryExhaustedError` 分支：
  - 记录 `_LOG_DRAIN_LOOP_DURABLE_RETRY_EXHAUSTED` ERROR 日志
  - `self._closed = True` — fail-close scheduler
  - `_best_effort_mark_host_instance_stopped("drain_loop_durable_retry_exhausted")`
- 普通 `Exception` 仍只 WARNING + sleep 继续（避免临时 worker/调度异常误杀 scheduler）
- `HostTransactionRetryExhaustedError` 代表 durable 写入重试耗尽，是不可恢复信号，fail-close 合理
- 不会误杀可恢复异常：只有显式 `HostTransactionRetryExhaustedError`（busy/locked 重试耗尽）才触发

### 7. session lifecycle projection catch-up — PASS

- `command.py:353`: `ensure_session` 写入后 `catch_up_projection_best_effort(host._admission_service.projection_catchup_port)`
- `command.py:380`: `create_session` 写入后同样调用
- `command.py:408`: `close_session` 写入后同样调用
- 与 `admission.py` 中 `start_run`/`submit_followup_queue` 的 catch-up 模式一致

### 8. wal_autocheckpoint — PASS

- `transaction.py:33`: `_SQLITE_WAL_AUTOCHECKPOINT_PAGES = 256`
- `transaction.py:370`: `connection.execute(f"PRAGMA wal_autocheckpoint={_SQLITE_WAL_AUTOCHECKPOINT_PAGES}")`
- 在 `configure_connection_pragmas` 中与 `busy_timeout`、`foreign_keys`、`journal_mode=WAL` 一同设置
- 256 pages (~1MB) 是合理的 checkpoint 频率，防止 WAL 无界增长

### 9. ToolCallAggregator id remap — PASS

- `tool_call_aggregator.py:260-268`: `feed()` 中检测 `existing_index is not None and existing_index != index` 时调用 `_remap_partial_index`
- `_remap_partial_index` (L197-225): 合并旧 partial 到新 index（name 拼接、arguments buffer 迁移、provider_state 合并），更新 `_index_by_id` 和 `_index_by_position` 映射
- 修复了"第一个 delta 无 index 分配合成 -1，后续 delta 带 index=0 时 setdefault 不更新"的 bug

### 10. sqlite_errorcode 读取 — PASS

- `transaction.py:472-478`: `try: code = error.sqlite_errorcode  # type: ignore[attr-defined]` + `except AttributeError: return None`
- 不再使用 `getattr`，改用直接属性访问 + `try/except AttributeError` 收口
- 符合项目编码硬约束"使用 getattr 必须有充分理由"

### 11. 低风险小修 — PASS（有一项遗留）

- `sse_parser.py`: `_byte_buffer` 字段已删除 ✓
- `compaction.py:1437-1440`: `preserved_canonical_evidence_refs` 改用 `_require_unique_string_tuple` ✓
- `compact_material.py:985-987`: `_evidence_provenance` 签名已移除 `blocks` 参数 ✓
- `scene_prepare.py:1716`: `SceneFragmentRef` 已加入 `__all__` ✓
- `scene_prepare.py:1448-1451`: `_require_json_object` 已校验 key 为字符串 ✓
- `open_host.py:710-712`: `__aexit__` 中 `del exc_type, exc_value, traceback` 已删除 ✓
- **遗留**: `scene_prepare.py:1001-1003` 的不可达分支（`_parse_defaults` 强制 `fail_closed`，但 `_load_fragment_contents` 仍有 `else` raise）未删除。严重性低，不构成 blocker。

---

## 风险审查

### ToolBundle `_allow_empty` 是否泄漏为公共空构造？

- `tool_declaration.py:131`: `_allow_empty: InitVar[bool] = False` — `InitVar` 不成为实例属性
- 公共构造 `ToolBundle(definitions=())` 触发 `__post_init__` 中 `raise ValueError`
- 只有显式传 `_allow_empty=True` 才能构造空 bundle，且该参数不出现在 `__all__` 导出中
- **结论**: 不泄漏。`_allow_empty` 是 framework-only 构造入口。

### schema bump 是否符合 fresh schema 规则？

- `schema.py:26`: `HOST_SCHEMA_VERSION = 15`（从 14 bump）
- `schema.py:1240-1245`: `if current_version not in (0, HOST_SCHEMA_VERSION): raise HostSchemaMismatchError`
- 只接受 fresh DB (version=0) 或当前版本 (version=15)
- **结论**: 符合 fresh schema 规则，不做旧库兼容读取。

### dispatch fail-close 是否会误杀可恢复异常？

- `dispatch.py:1839-1847`: 只有 `HostTransactionRetryExhaustedError` 触发 fail-close
- `HostTransactionRetryExhaustedError` 由 `transaction.py:285-288` 在 `sqlite3.Error` busy/locked 重试耗尽时抛出
- 普通 `RuntimeError`、`OSError` 等仍走 WARNING + sleep 继续路径
- **结论**: 不会误杀。`HostTransactionRetryExhaustedError` 是 durable 层明确的不可恢复信号。

### 大 diff 是否只是格式化还是有行为漂移？

- diff stats: 34 files changed, 1686 insertions(+), 3459 deletions(-)
- 净减少 1773 行，主要来自 `state.py`（-695 行简化）、`compaction.py`（-399 行简化）、`dispatch.py`（-463 行简化）
- 逐项核验确认行为变更与修复说明一致，未发现格式化掩盖的行为漂移

---

## 测试验证

- 120 passed（修复说明中列出的全部测试用例）
- pyright: 0 errors, 0 warnings, 0 informations
- 关键新增测试：
  - `test_drain_loop_fail_closes_on_durable_retry_exhausted` — 验证 fail-close 行为
  - `test_multi_pass_merge_quality_reject_records_rejected_attempt` — 验证 merge-level reject 记录
  - `test_llm_context_compactor_budget_counts_preserved_context` — 验证预算 overhead
  - `test_session_lifecycle_commands_trigger_projection_catchup` — 验证 projection catch-up
  - `test_candidate_rejects_duplicate_preserved_canonical_evidence_refs` — 验证唯一性校验
  - `test_synthetic_index_does_not_collide_with_later_native_index` + `test_later_native_index_remaps_existing_id_partial` — 验证 id remap

---

## 未修项裁定合理性

修复说明中明确列出的未修项，裁定均合理：

- **schema 迁移机制**: 项目规则明确 fresh schema，不做迁移 ✓
- **command-handle-only wakeup**: 需要独立设计可选 wakeup port，不应在 bugfix 中硬塞 scheduler ✓
- **`_promote_after_release` 吞 RuntimeError**: startup recovery 已覆盖，适合后续增强 ✓
- **dispatch `ingest_async` 异常统一 LOST / EventLogStore 纯委托 / contracts/runtime 重复 helper / active cancel hook race / 测试空白**: 影响面大或属架构演进，不在本轮 bugfix 范围 ✓

---

## 结论

**PASS**

所有 11 项修复均已基于直接代码证据验证到位。测试 120 passed，pyright 0 errors。修复说明中未修项裁定合理，未发现本轮 diff 引入的新 bug。

唯一遗留：`scene_prepare.py:1001-1003` 的不可达分支未删除（严重性低，不构成 blocker）。
