# WU-SEMANTIC-OWNERSHIP-01 / P2-E Implementation Review - AgentMiMo

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: uncommitted diff only (no production code changed)
- Output file: `docs/reviews/wu-semantic-ownership-01-p2-e-implementation-review-mimo.md`
- Included scope: 6 test/fixture files changed by P2-E implementation
- Excluded scope: production code, docs, README
- Parallel review coverage: 无

## Findings

未发现实质性问题。

### 详细走读

#### 1. Stream heartbeat 正向 / 负向断言

- **正向测试** `test_idle_heartbeat_emits_debug_log_and_does_not_drop_bytes`：使用 `STREAM_DEBUG_LOG_LEVEL`（值 9）捕获 heartbeat。`_heartbeat_runner()` 构造 `stream_idle_heartbeat_seconds=0.02`、`delay_seconds=0.06` 的 runner，保证至少 2 次 heartbeat 在 0.06s 延迟期间产生。断言 heartbeat 可见、无 HTTP_ERROR、最终 DONE。✅
- **负向测试** `test_idle_heartbeat_is_not_captured_at_normal_debug`：使用 `logging.DEBUG`（值 10）捕获。同一 `_heartbeat_runner()` helper 保证 heartbeat 确实产生；因 `STREAM_DEBUG_LOG_LEVEL=9 < logging.DEBUG=10`，caplog 不捕获 level 9 日志。断言无 heartbeat 记录、无 HTTP_ERROR、最终 DONE。✅
- **假通过风险**：负向测试不依赖"heartbeat 从未产生"的假设。`_heartbeat_runner()` 的 timing 保证 heartbeat 在两种 capture level 下都会触发；区别仅在于 caplog threshold 是否过滤。不是假通过。✅
- **变更边界**：只改测试导入和 caplog level；未修改 `runner.py` 生产日志级别。✅

#### 2. Engine event / export snapshot

- `test_iteration_started_runner_input_signal_fields_are_locked`：字段快照新增 `input_projection`。直接证据：`docs/engine/design.md` 明确 `iteration_started` 携带 `input_projection`；`dayu/engine/contracts/engine_events.py` 生产代码 `IterationStartedData` 包含该字段。✅
- `test_engine_all_matches_expected_set`：`EXPECTED_EXPORTS` 新增 `RunnerInputMessageProjection` / `RunnerInputToolCallProjection`。直接证据：`dayu/engine/__init__.py` `__all__` 导出这两个类型；`docs/engine/design.md` 列为公共包根导出。✅
- 变更边界：只更新测试快照，未修改生产导出或契约。✅

#### 3. Host export snapshot

- `test_host_all_matches_current_public_contracts`：`EXPECTED_HOST_EXPORTS` 新增 `HostThinkingView`。直接证据：`dayu/host/__init__.py` `__all__` 导出；`docs/host/design.md` 明确 `HostThinkingView` 是 `HostEvent.thinking` 的 typed view。✅
- `test_api_all_stays_request_snapshot_boundary`：`EXPECTED_API_EXPORTS` 新增 `HostThinkingView`。直接证据：`dayu/host/api.py` 导出。✅
- 变更边界：只更新测试快照，未修改生产导出。✅

#### 4. Wait-resume protocol replay

- 旧断言：检查 `resume_request.messages` 中是否存在英文 fallback guidance 字符串 `"A previous interrupted step..."`。
- 新断言：取 `messages[-3:]`，逐一断言 `UserMessage -> AssistantMessage(tool_call) -> ToolMessage`。
- **SystemMessage 前缀处理**：`messages[-3:]` 跳过 `SystemMessage`（implementation codex 诊断确认 messages[0] 是 SystemMessage）。这是合理的：SystemMessage 是 Host/Engine 内部上下文治理，不属于 LLM-facing 协议 replay 闭环。测试断言的是协议层 `user -> assistant(tool_call) -> tool` 的身份和语义一致性。✅
- **tool_call_id identity closure**：`assistant_tool_call.id == batch.calls[0].tool_call_id` 且 `tool_message.tool_call_id == assistant_tool_call.id`。确认请求和响应通过同一 id 闭合。✅
- **业务结果断言**：`json.loads(tool_message.content)["answer"] == 42`。直接验证 tool result JSON 中的业务语义。✅
- **诊断结论**：implementation codex 记录实际 `resume_request.messages` 已是正常协议链（SystemMessage + UserMessage + AssistantMessage(tool_call) + ToolMessage），无旧英文 guidance。无需修改生产代码或 fixture。✅
- **导入检查**：`json`、`AssistantMessage`、`ToolMessage`、`UserMessage` 均已在文件顶部导入。✅

#### 5. Purge fixture cancel_request_event_id

- `_insert_cancel_request_event_if_needed`：只在 `status in (cancelling, cancelled)` 时生成 dedicated `CANCEL_REQUESTED` EventLog row，event id 格式为 `event-{run_id}-cancel-requested`（不复用已有 event）。其它状态返回 `None`。✅
- `_insert_run_row`：始终调用 `_insert_cancel_request_event_if_needed`，结果写入 `cancel_request_event_id` 列。`TEXT NULL` 列允许 `None`。✅
- **succeeded matrix 不被污染**：`_SeedClosedSessionMatrixOperation` 默认 `run_status=_RUN_STATUS_SUCCEEDED`，此时 `_insert_cancel_request_event_if_needed` 返回 `None`，不额外写入 EventLog row。succeeded matrix 的 event 计数不变。✅
- **cancelled 覆盖**：`_NON_TERMINAL_RUN_STATUSES` 不含 `cancelled`（cancelled 是 terminal），所以 `test_purge_session_durable_rejects_non_terminal_runs` 的 parametrize 不覆盖 `cancelled`。但 helper 已同时处理 `cancelled`，如果未来其它测试路径用 `_insert_run_row` 创建 cancelled Run，也能满足 durable CHECK constraint。✅
- **durable schema 对齐**：生产 schema CHECK constraint 要求 `status IN ('cancelling', 'cancelled')` 时 `cancel_request_event_id IS NOT NULL`。fixture 的 dedicated EventLog row 满足 FOREIGN KEY + CHECK 双重约束。未放宽 schema。✅
- **event_type 使用**：`_EVENT_TYPE_CANCEL_REQUESTED = "CANCEL_REQUESTED"` 作为新常量引入，只用于 dedicated cancel event；旧 `_EVENT_TYPE_TEST = "TEST_EVENT"` 保持不变，不被 cancel 逻辑污染。✅

#### 6. README / doc trigger

- 无生产代码变更。6 个文件均为测试/fixture。
- `docs/engine/design.md` 已记录 `input_projection` 和 projection exports。
- `dayu/host/README.md` 已记录 `HostThinkingView`。
- `tests/README.md` 未引入新测试类别或命令约定。
- 无需更新任何 README。✅

#### 7. AGENTS.md 合规

- `_heartbeat_runner()`、`_insert_cancel_request_event_if_needed()` 均有完整中文 docstring（参数、返回值、异常）。✅
- 无 `Any`、`object` 签名回归。✅
- 无 downstream masking、兼容性 re-export 或 fallback 分支。✅

## Open Questions

无。

## Residual Risk

- **Real-provider wait-resume**：P2-E 只验证了本地 integration path 的 protocol replay，未单独在真实 provider 环境验证 wait-resume 行为。Classification：归属已有 broader smoke / real-environment validation owners，不阻塞 P2-E。
- **Broad suite edgar warnings**：broad matrix 仍有 edgar dependency deprecation warnings。Classification：与 P2-E 无关，已在外部分 track。
- **cancelled parametrize gap**：`_NON_TERMINAL_RUN_STATUSES` 不含 `cancelled`，purge rejection test 不覆盖 cancelled 状态的 fixture 校验。但 `cancelled` 是 terminal 状态，purge helper 对 terminal 状态是正常处理路径而非 rejection 路径，所以这不是测试缺口。
