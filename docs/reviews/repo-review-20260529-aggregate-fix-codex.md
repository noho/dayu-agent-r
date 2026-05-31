# repo-review-fix Codex 修复说明

## 输入

- MiMo review: `docs/reviews/repo-review-20260529-220422.md`
- DS review: `docs/reviews/repo-review-20260529-215815.md`

## 已修复项

1. purge 状态集合不同源：成立。`purge.py` 原先维护重复字符串集合，已改为从 `dayu.host.durable.state` 中由 `RunStatus` 派生的 `TERMINAL_RUN_STATUSES` / `NON_TERMINAL_RUN_STATUSES` 获取 schema value。
2. active Run schema CHECK 缺口：成立。`host_runs` 现要求 `running` / `waiting` / `cancelling` / `recovering` 必须有 `started_event_id` 与 `started_event_sequence`，`HOST_SCHEMA_VERSION` bump 到 15；按项目规则只支持 fresh schema，不做旧库迁移兼容。
3. `_NoToolBundle` unsafe cast：成立。删除 runtime sentinel cast，改为 contracts 层提供 `_allow_empty=True` 的类型真实空 `ToolBundle`，公共默认构造仍拒绝空 bundle。
4. compaction merge-level quality reject 未记录：成立。multi-pass merge 后被质量闸门拒绝时，会追加一次不可修复的 `quality_check_rejected` rejected attempt。
5. compact 后预算估算低估 framing / tool schema envelope：部分成立。`LLMContextCompactor` 预算估算已纳入 message overhead 与工具 schema envelope overhead；真实 provider tokenizer 差异仍由保守估算而非精确 tokenization 处理。
6. dispatch drain loop catch-all：成立但严重度需收敛。普通 `RuntimeError` 仍只记录并继续，避免把临时 worker / 调度异常误判为 fatal；`HostTransactionRetryExhaustedError` 代表 durable 重试耗尽，现 fail-close scheduler 并写 error 诊断。
7. session lifecycle projection catch-up：成立。`ensure_session` / `create_session` / `close_session` 提交 durable 写入后统一走 best-effort projection catch-up。
8. WAL checkpoint 管理：成立。SQLite connection 初始化显式设置 `wal_autocheckpoint=256`。
9. ToolCallAggregator id remap：成立。后续 delta 携带同一 `id` 的 provider 原生 `index` 时，会把旧 synthetic partial 合并到新 index。
10. durable `getattr`：成立。`sqlite_errorcode` 改为直接属性读取并用 `AttributeError` 收口。
11. 低风险小修：删除 SSE parser 未使用 `_byte_buffer`；`CompactionCandidate.preserved_canonical_evidence_refs` 改为唯一性校验；移除 `_evidence_provenance` 未使用参数；`SceneFragmentRef` 加入 `__all__`；`scene_prepare._require_json_object` 校验 key 为字符串；删除 `open_host.__aexit__` 的无效 `del`。

## 未修项与理由

- schema 迁移机制：不实施。项目规则明确按全新 schema 起库；本轮只强化 mismatch 错误消息与 README。
- command-handle-only `resolve_wait` Noop wakeup：不实施生产改动。该路径没有 scheduler 装配，硬塞 scheduler 会越过当前 composition 边界；需要单独设计可选 wakeup port。
- `_promote_after_release` 吞 `RuntimeError`：不实施。本轮证据显示 startup recovery 可恢复 queued Run；适合后续增强可观测诊断，不做队列重构。
- dispatch `ingest_async` 异常统一 LOST、EventLogStore 纯委托、contracts/runtime 重复 helper、active cancel hook race、major 测试空白：影响面较大或属于架构演进，未在本轮 bugfix 扩大生产改动。
- SSE 多 choice `finish_reason` warning、resolve_wait service 实例化一致性、其它 dead code：不影响本轮共同高信号问题，未继续扩大范围。

## 测试与验证

- `source .venv/bin/activate && pytest tests/contracts/test_tool_declaration.py tests/runtime/test_tools_discovery.py tests/service/test_host_assembly.py tests/host/test_durable_schema.py tests/host/test_state_schema.py tests/host/test_durable_connection.py tests/host/test_dispatch_scheduler.py::test_drain_loop_logs_unexpected_exception tests/host/test_dispatch_scheduler.py::test_drain_loop_fail_closes_on_durable_retry_exhausted tests/engine/runners/openai/test_sse_tool_call_index_fallback_to_id.py tests/host/test_compaction_contract.py::test_candidate_rejects_duplicate_preserved_canonical_evidence_refs tests/host/test_compaction_operation.py::test_multi_pass_merge_quality_reject_records_rejected_attempt tests/host/test_llm_compaction.py::test_llm_context_compactor_budget_counts_preserved_context tests/runtime/test_scene_prepare.py::test_scene_fragment_ref_is_public_export tests/runtime/test_scene_prepare.py::test_require_json_object_rejects_non_string_keys tests/host/test_public_session_api.py::test_session_lifecycle_commands_trigger_projection_catchup tests/host/test_purge_session.py`
  - 结果：120 passed
- `source .venv/bin/activate && pyright`
  - 结果：0 errors, 0 warnings, 0 informations

## README 同步

- `dayu/README.md`：同步 runtime tools discovery 的 no-tool 表达。
- `dayu/host/README.md`：同步 fresh schema / WAL auto-checkpoint、compact 后预算 overhead 与 merge-level reject 诊断。
- `tests/README.md`：同步 ToolBundle 空 bundle 测试边界。

## 剩余风险

- `ToolBundle(_allow_empty=True)` 是框架内部 no-tool 构造入口，调用方默认构造仍拒绝空集合；后续如要完全隐藏该入口，需要更大规模 contracts factory 设计。
- compact 后预算仍不是 provider tokenizer 精确值；本轮只把估算口径补齐到 Host 现有 conservative estimator 常数。
- dispatch durable retry exhausted fail-close 会停止 scheduler 接收新 wakeup；调用方仍需按现有 Host lifecycle 重开 scheduler 或走 startup recovery。
