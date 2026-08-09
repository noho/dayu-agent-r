# PR Review: wu-cli-interactive-02

## Scope

- Mode: PR Review
- PR: [#190](https://github.com/noho/dayu-agent-r/pull/190)
- Title: fix(cli): close interactive conformance gaps
- Author: noho
- Head branch: codex/interactive-oracle (head: a4ff05db)
- Base branch: main (merge base: 113ea34d)
- State: OPEN / Draft
- Commits: 16
- Changed files: 181 (31210 insertions, 4816 deletions)
- Output file: docs/reviews/pr-review-wu-cli-interactive-02-mimo-20260802.md

## PR Facts Verification

| 检查项 | 结果 |
|---|---|
| ae6bb96f 在 PR commit chain 中 | ✅ 确认 |
| cc5c9d57 在 PR commit chain 中 | ✅ 确认 |
| Base drift (main 113ea34d == merge base) | ✅ 无 drift |
| Draft status | ✅ 是 draft PR |
| CI checks | 无 checks（draft PR 不触发） |
| Secret/credential scan | ✅ 无敏感字段泄漏；test "secret" 是测试数据；production code 显式剥离 endpoint/credential/header |
| F01-F13 frozen semantics 覆盖 | ✅ 全部 13 项均有实现 |
| Gateflow artifacts 在 PR 中 | ✅ plan、slice、aggregate review 均已包含 |

## Findings

未发现实质性问题。

## Evidence Summary

### F01: prompt/interactive 无 `--config`

- `dayu/cli/arg_parsing.py`: `_register_prompt_command` 和 `_register_interactive_command` 改用 `command_common_parent`（不含 `--config`）。
- `_reject_disallowed_explicit_config()` 在 `parse_cli_args()` 中对 `prompt`、`interactive`、`session resume` 命令做 command-aware 拒绝。
- `prepare_prompt_session_execution()` 和 `prepare_interactive_session_execution()` 不再调用 `resolve_explicit_config_dir()`。
- 测试覆盖：`test_arg_parsing.py`、`test_prompt_command.py`、`test_interactive_command.py` 均有 parser-level 不可达测试。

### F02: interactive 无 `--ticker`

- `_register_interactive_command()` 删除 `--ticker` 参数。
- `build_interactive_context_slot_values()` 改为无参数接口，固定 `ticker=None, fmp_api_key=None`。
- `session resume --mode interactive` 携带 ticker 时由 `_reject_interactive_resume_ticker()` 显式拒绝。
- 测试覆盖：`test_interactive_command.py`、`test_session_command.py` 均有 negative 测试。

### F03/F04: 统一 label owner

- `dayu/cli/host_context.py`: 用 `CLI_AGENT_SESSION_SCOPE = "cli.agent"` 和 `cli_label_slot_key()` 替代旧的 prompt/interactive 双套常量和 helper。
- `dayu/cli/session_identity.py`: 删除 `CliSessionLabelKind`，`slot_ref_for_cli_label()` 只接受 label 参数，映射到共享 scope。
- `session` 命令删除 `--kind` 参数，`--label` selector 不再需要 kind。
- 测试覆盖：`test_session_command.py` 有共享 slot 双向测试。

### F05-F09: composer、non-TTY、Escape、Ctrl+C、type-ahead

- `dayu/cli/composer.py`: 完整重写。引入 `InteractiveComposerPhase`（IDLE/RUNNING/CANCELLING）、`InteractiveComposerEvent`（typed event）、`InteractiveCancelSource`（ESCAPE/CTRL_C）。prompt_toolkit key bindings 按 phase 分发行为。
- `dayu/cli/session_execution.py`: TTY 路径由 `_drive_interactive_tty_repl()` 驱动，non-TTY 路径由 `_run_interactive_non_tty_batch()` 处理。type-ahead 通过 composer 的 `_pending_submit` 和 `_draft` 机制实现，单 QUEUE follow-up 在 Run 终态后执行。
- `Ctrl+J` 插入换行，xterm Shift+Enter 序列精确匹配后插入换行，其它 Enter 提交。
- `Escape` 只在 `active_phase` filter 下绑定，CSI/Alt/bracketed paste 不误触发。
- non-TTY 读取整个 binary stdin，UTF-8 校验失败为稳定用法错误，空白流不提交。
- 测试覆盖：`test_interactive_composer.py`（588 行变更）、`test_interactive_command.py`（2311 行变更）覆盖 PTY/pipe/async barrier。

### F10: fresh RW delayed orphan recovery

- `dayu/host/recovery.py`: `SessionAttachmentRecoveryAction` 增加 `retry_not_before` 字段，`SessionAttachmentRecoveryScanResult` 增加 `next_reconcile_at`。
- `dayu/host/recovery_process.py`: `classify_orphan_candidate()` 在 heartbeat 仍 recent 时（`now - heartbeat < stale_after`，严格小于）返回 `retry_not_before = heartbeat + stale_after`。
- `dayu/host/open_host.py`: `_PublicHostHandle.attach_session()` 在 initial scan 返回 `next_reconcile_at` 时，调度 `_run_delayed_attachment_recovery()` 单次任务。`_ManagedHostSessionAttachment` 包装 public attachment，在 `aclose()` 时取消并 join delayed task。
- Host close 时 `_cancel_and_join_all_delayed_attachment_recoveries()` 清理所有 delayed tasks。
- 测试覆盖：`test_recovery_scan.py`、`test_recovery_dispatch.py`、`test_recovery_multiprocess.py` 增加了 deadline 和 delayed recovery 测试。

### F11: all-trigger unique compaction terminal

- `dayu/host/compaction_terminal.py`（新文件，291 行）：`begin_compaction_terminal_commit_in_transaction()` 在同一 write transaction 内读取 request 和 terminal rows，返回 `CompactionTerminalCommitPermit`（OPEN）或 `CompactionTerminalClosed`。严格校验 request payload、trigger source 和 terminal canonical identity。
- `dayu/host/dispatch.py`: proactive 路径的 4 个 compaction 入口（governance、execution、resume、missing compactor）均在写 artifact/event 前调用 `begin_compaction_terminal_commit_in_transaction()`，CLOSED 时 warn+noop 或 fail closed（INVALID_MULTIPLE）。
- `dayu/host/engine_ingest.py`: reactive 路径 `_execute_reactive_compaction()` 在 outcome transaction 内同样调用该函数，CLOSED 时返回 `pending.result_prefix`。
- `dayu/host/proactive_compaction.py`: `_project_state()` 使用 terminal owner 的 fresh 结果校验 terminal rows 的一致性。
- 测试覆盖：`test_compaction_terminal.py`（1065 行新文件）覆盖 OPEN、COMPACTED、FAILED、INVALID_MULTIPLE、payload corruption、trigger mismatch、concurrent competition 等场景。

### F12: per-Session pre-start single-flight

- `dayu/host/dispatch.py`: `_PreStartGovernanceFlight` 数据类持有 `task` 和 `rerun_requested`。`_signal_pre_start_governance()` 合并 signal 到已有 flight 或创建新 flight。`_run_pre_start_governance_flight()` 串行执行 coalesced passes，每个 pass 前清除 level bit 并取得 fresh lease。`_promotion_pending_session_ids` set 防止重复投递。
- `_enqueue_requeued_promotion()` 在 transient backoff 后按同一 level-bit 规则重新投递。
- `_suppress_task_cancel()` 类型扩展为 `Task[None] | Task[bool]`。
- 测试覆盖：`test_dispatch_scheduler.py`（1320 行变更）覆盖 single-flight、coalesced signal、promotion dedup。

### F13: durable compactor response identity

- `dayu/engine/contracts/runner_identity.py`: 新增 `ProviderRequestIdAvailability` 枚举和 `SuccessfulRunnerResponseIdentity` 数据类，严格校验 provider/model/request identity/availability 一致性。
- `dayu/engine/agent.py`: `_FinalDecision` 增加 `response_identity` 字段，`_successful_response_identity()` 从 `AgentRunRequest`、`_IterationState`、`RunnerDoneData` 构造。identity 贯穿 degraded/filter 路径。
- `dayu/host/compaction.py`: 新增 `CompactorProposal`（candidate + response identity 配对）和 `CompactorProposalError`（携带可选 identity）。`ContextCompactor` 协议返回类型改为 `CompactorProposal`。
- `dayu/host/llm_compaction.py`: `LLMContextCompactor.compact()` 和 `run_prepared_compactor_proposal()` 返回 `CompactorProposal`。`_validated_prepared_response_identity()` 校验 Engine run/attempt/provider/model 同源。
- `dayu/host/context_events.py`: `CompactorProposalManifestReference` 从 `compaction_operation.py` 迁移至此（context events 是 durable payload schema owner），增加 `compaction_operation_id`、`compaction_attempt_number`、`compactor_engine_run_id` 绑定字段。`build_context_compacted_payload()` 和 `build_context_compaction_attempt_rejected_payload()` 必须携带 `successful_response_identity`。`_validate_successful_response_manifest_binding()` 校验 operation/attempt/run 同源。`_parse_successful_response_identity()` 严格反序列化并校验 compactor identity 不使用 ordinary attempt/execution。
- `dayu/host/engine_ingest.py` 和 `dayu/host/dispatch.py`: accepted/rejected 路径均携带并验证 `successful_response_identity` 和 `CompactorProposalManifestReference`。
- 测试覆盖：`test_runner_identity.py`、`test_engine_event_contract.py`、`test_compaction_operation.py`、`test_compaction_terminal.py` 覆盖 present/unavailable、success/failure/repair、identity mismatch。

## Merge Correctness

- PR diff 与 `git diff main...a4ff05db` 一致（181 文件）。
- 所有新增生产文件（`compaction_terminal.py`、`CompactorProposal`、`SuccessfulRunnerResponseIdentity` 等）均在 `__all__` 中正确导出。
- 旧符号（`CliSessionLabelKind`、`InputReaderComposer`、`prompt_slot_key`、`interactive_slot_key`、`PROMPT_SESSION_SCOPE`、`INTERACTIVE_SESSION_SCOPE` 等）已从 `__all__` 和 import 中移除，无兼容 re-export。
- `CompactorProposalManifestReference` 从 `compaction_operation.py` 迁移到 `context_events.py`，`compaction_operation.py` 改为 import 新位置，无断裂。

## Architecture Alignment

- 分层边界严格：CLI 不读取 Host internals，Service API 不增加 UI 状态，Host 只依赖 Engine 安全 typed identity，Engine 不理解 Host compaction operation。
- `dayu.runtime` 未被触及。
- 新类型从 Engine contracts 流向 Host，不反向依赖。
- compaction_terminal 是窄专用 guard，不建立通用 event terminal framework。
- pre-start flight 是 scheduler-local dict + coalesced bit，不引入通用 scheduler。

## Open Questions

无。

## Residual Risk

1. **G01-G07 未裁决**：PR body 明确声明这些留待后续 CLI calibration campaign。这是 scope 内的已知 non-goal，不构成本 PR 的阻塞风险。
2. **phase5 scheduler/test race failures**：PR body 记录 6 个 race failures 已在 clean base 上复现并分类为 non-regressions。这些是已有技术债务。
3. **Provider identity evidence**：PR body 说明 provider identity 验证证据是 raw validation evidence，尚未成为 accepted formal interactive scenario。这是 G01-G07 范围。
4. **Draft PR 状态**：当前为 draft，CI checks 未触发。合并前需确认 pyright、full test suite 在 CI 环境通过。

## Conclusion

**PASS。** PR 实现了 F01-F13 全部冻结语义，架构分层正确，semantic ownership 清晰，无 secret 泄漏，base 无 drift，原始 calibration commits 已包含。未发现实质性问题。Draft 状态下的 residual risk 均为已知 scope 边界或已有技术债务，不阻塞 PR 从 draft 转为 ready。
