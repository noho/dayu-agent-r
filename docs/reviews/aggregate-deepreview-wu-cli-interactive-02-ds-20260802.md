# 聚合深度审查 — wu-cli-interactive-02-conformance-fixes

## Scope

- **Mode**: Current changes aggregate deepreview
- **Branch**: `codex/interactive-oracle`
- **Base**: `main`
- **Output file**: `docs/reviews/aggregate-deepreview-wu-cli-interactive-02-ds-20260802.md`
- **Review date**: 2026-08-02
- **Included scope**: 全部 12 个提交（两个 calibration 提交 + accepted plan + S1-S6），F01-F13 冻结语义
- **Excluded scope**: AgentMiMo review artifacts（未读取）；既有 controller 结论（独立验证，不直接接受）
- **Parallel review coverage**:
  - CLI 层（session_execution, composer, arg_parsing, commands）：agent `a76a1227f4521aaaa` 覆盖，详细状态机走读
  - Host 层（compaction_terminal, dispatch, engine_ingest, context_events, recovery, open_host）：agent `a1156dc9914d70f1f` 覆盖
  - Engine 层（agent, runner_identity, agent_run, engine_events）：agent `a93a7292d89533296` 覆盖
  - 测试与验证（tests, scenarios, oracles）：agent `aafb3603a9ed26224` 覆盖
  - 主 reviewer 独立补充：compaction_terminal.py, runner_identity.py, session_execution.py, composer.py, arg_parsing.py, host_context.py, context_events.py, dispatch.py, engine_ingest.py, open_host.py 完整走读
- **Verification**: pyright 全量 0 errors；受影响测试通过；主 reviewer 独立走读全部关键路径
- **Commit timeline**:
  - `cc5c9d57` docs(cli): adjudicate interactive oracle
  - `ae6bb96f` docs(cli): complete interactive calibration matrix
  - `34127db4` gateflow: accept plan for wu-cli-interactive-02-conformance-fixes
  - `d210444f` gateflow: accept wu-cli-interactive-02 S1
  - `057b5b9b` gateflow: accept wu-cli-interactive-02 S2
  - `eadee409` gateflow: accept wu-cli-interactive-02 S3
  - `331d38dc` gateflow: accept wu-cli-interactive-02 S4
  - `ec9342ed` gateflow: amend S5 plan for required identity closure
  - `e7f578dc` gateflow: close S5 durable builder plan closure
  - `ce7ef846` gateflow: close S5 utils identity closure
  - `9ad45cf7` host: preserve compactor response identity
  - `cf041c2c` gateflow: accept wu-cli-interactive-02 S6

---

## F01-F13 逐项结论

以下是对每项 frozen fix 的独立验证结论。每一项均基于生产代码直接走读、测试断言和 pyright 结果，不依赖 AgentMiMo 或既有 controller 裁决。

| F 项 | 描述 | 结论 | 证据摘要 |
|------|------|------|----------|
| F01 | prompt/interactive 彻底无 `--config` | **通过** | `arg_parsing.py:249-250` 两个命令用 `command_common_parent`（无 `--config`）；`_reject_disallowed_explicit_config` 拒绝 root 级别 `--config`；`test_agent_surfaces_reject_config_in_every_parser_position` 覆盖前中后三位置 |
| F02 | interactive 彻底无 `--ticker` | **通过** | `arg_parsing.py:621-641` interactive 只注册 `--label` 和执行参数；`test_interactive_rejects_removed_ticker_and_session_kind` 断言 `EXIT_USAGE_ERROR` |
| F03/F04 | 统一 label owner，单一 `cli.agent.<label>` namespace | **通过** | `host_context.py:26-27` `CLI_AGENT_SLOT_KEY_PREFIX = "cli.agent."`；旧 `cli.prompt.*`/`cli.interactive.*` 无残留；`session_identity.py` 单一 `slot_ref_for_cli_label(label)` |
| F05 | 单一 stdin owner（composer） | **通过** | `composer.py` 是唯一 stdin reader；旧 `InputReaderComposer` 已删除；`session_execution.py:1498` 仅调 `composer.read_event()` |
| F06 | non-TTY whole-stdin batch | **通过** | `session_execution.py:1104-1123` 从首 byte 到真实 EOF 读为单个 draft；内部换行不拆多 Run |
| F07 | Escape/CSI/Alt 不误取消 | **通过** | `composer.py:429-443` Escape 绑定用 `filter=active_phase` 且 prompt_toolkit 的 VT100 解析器区分 standalone Escape 与 CSI 序列 |
| F08 | Enter = QUEUE，不 STEER | **通过** | `session_execution.py:1360-1374` active Run 中 Enter 创建 `FollowupBehavior.QUEUE` 且 `target_run_id=None` |
| F09 | 连续 Ctrl+C 优雅退出 + sole QUEUE 终端等待 | **通过** | 状态机 `exit_intent=EXIT_AFTER_CANCEL` → 等待 `current=None`（含 promoted queued）→ exit 130；`finally` 块取消所有未完成 task |
| F10 | fresh RW delayed orphan recovery | **通过** | `open_host.py:1242-1337` `_schedule_delayed_attachment_recovery`；`_run_delayed_attachment_recovery` 用 `asyncio.shield` 保护 actor future |
| F11 | all-trigger unique terminal（compaction_terminal guard） | **通过** | `compaction_terminal.py:98-177` SQLite write transaction 串行 CAS；dispatch.py 4 处 + engine_ingest.py 1 处调用；AST 测试验证所有 writer 经同一 owner |
| F12 | per-Session pre-start single-flight | **通过** | `dispatch.py:1368-1386` `_pre_start_flights` dict + `rerun_requested` coalesced bit；flight loop 每 pass 获取 fresh work_lease |
| F13 | Engine success identity → Host durable projection | **通过** | `RunnerRequestIdentity` → `_successful_response_identity()` → `_FinalDecision.response_identity` → `FinalAnswerData`/`EngineRunOutcomeFinalAnswer`；identity payload 无 secret |

---

## Findings

### AG-001-中-OS SIGINT idle 路径 `idle_interrupt_revision=None` 导致非对称双 Ctrl+C 行为

- **入口/函数**: `_drive_interactive_tty_repl` 中的 `sigint_task` 完成处理分支
- **文件(行号)**: `dayu/cli/session_execution.py:1427`
- **输入场景**: 用户在 idle 状态下通过 `kill -INT` 或外部工具发送 SIGINT，然后通过终端按两次 Ctrl+C
- **实际分支**: OS SIGINT 路径设置 `idle_interrupt_revision = None`（行 1427）；composer Ctrl+C 路径设置 `idle_interrupt_revision = event.input_revision`（行 1409）
- **预期行为**: 两次 Ctrl+C（无论来源）行为一致，均按"第一次登记 pending，第二次匹配 revision 退出"
- **实际行为**: OS SIGINT 先触发 → `idle_interrupt_revision=None` → 第一次 composer Ctrl+C 检查 `None == event.input_revision` 必然为 `False` → 仅更新 revision 不退出 → 需要第二次 composer Ctrl+C 才退出。总计 3 次输入事件 vs 正常 2 次
- **直接证据**: `session_execution.py:1403-1405` 比较 `idle_interrupt_revision == event.input_revision`；`session_execution.py:1427` OS SIGINT 路径设 `idle_interrupt_revision = None`，无法匹配任何 composer revision
- **影响**: idle 退出行为不一致；用户感知可能需要额外一次 Ctrl+C
- **建议改法和验证点**: OS SIGINT 在 idle 状态不应独立设置 `IDLE_EXIT_PENDING`，或应将 revision 比较逻辑改为"`idle_interrupt_revision is None` 时视为匹配任何 revision"。需要验证：OS SIGINT + 2 次 Ctrl+C 行为与纯 2 次 Ctrl+C 行为一致
- **修复风险（低）**: 只影响 idle 退出路径的边缘时序；不涉及 active Run 取消语义
- **严重程度（中）**: 状态机行为不一致，但在实践中触发概率低（外部 SIGINT 在 idle 时罕见）

### AG-002-中-`_require_exact_fields` 收紧拒绝含旧字段集的 legacy `CONTEXT_COMPACTED` 事件

- **入口/函数**: `validate_context_compacted_payload` / `validate_context_compaction_attempt_rejected_payload`
- **文件(行号)**: `dayu/host/context_events.py:1276-1294`（compacted）；`dayu/host/context_events.py:1591`（attempt rejected）
- **输入场景**: 存在含旧字段集（不含 `accepted_proposal_manifest_ref`、`accepted_proposal_manifest_digest`、`successful_response_identity`）的 legacy `CONTEXT_COMPACTED` 事件的 durable store
- **实际分支**: `_require_exact_fields`（从 `_require_fields` 升级）验证 payload 恰好只含指定字段集。legacy 事件缺少新字段 → `HostDurableError("compaction terminal payload is invalid")`
- **预期行为**: 按项目"全新 schema 起库"策略，旧 schema 事件不应存在于生产库。但如果存在（如 schema 迁移未执行），terminal guard 应给出可行动诊断而非 fail-closed
- **实际行为**: terminal guard 的 `_strict_terminal_payload` 抛出 `HostDurableError`，阻止该 Session 后续所有 compaction。错误消息为通用 "compaction terminal payload is invalid"，未说明具体缺失字段
- **直接证据**: `context_events.py:1276` `_reject_old_compacted_fields(payload)` + `_require_exact_fields(payload, _COMPACTED_REQUIRED_FIELDS)`；`compaction_terminal.py:258-266` `_strict_terminal_payload` 将校验失败转换为 `HostDurableError`
- **影响**: 如果旧 durable store 与新代码共存，compaction 功能静默退化（terminal guard fail-closed）
- **建议改法和验证点**: 在 compaction terminal guard 的 CLOSED disposition 中，对 legacy field mismatch 给出明确诊断日志（包含缺失字段名），并考虑是否允许 legacy event 在 guard 只读投影中被接受
- **修复风险（低）**: 仅影响有旧 schema 遗留的 workspace；全新 workspace 不受影响
- **严重程度（中）**: 部署兼容性风险，但项目策略明确禁止兼容旧 schema

### AG-003-中-`_promotion_pending_session_ids` 在 scheduler close 时未排空

- **入口/函数**: `HostDispatchScheduler.close()` / `_run_promotion_loop`
- **文件(行号)**: `dayu/host/dispatch.py:1579-1584`（add）；`dayu/host/dispatch.py:4457-4459`（discard）；scheduler close 路径
- **输入场景**: scheduler 正常关闭，`_promotion_queue` 中仍有待处理 session id
- **实际分支**: close 路径调用 `_promotion_queue.get_nowait()` 排空队列，但不调用 `_promotion_pending_session_ids.discard()`
- **预期行为**: queue 和 set 同步清空
- **实际行为**: set 中遗留 session id 字符串；如果 scheduler 对象因引用循环未 GC，字符串累积
- **直接证据**: `dispatch.py` 中 `_promotion_pending_session_ids.add()` 和 `.discard()` 的对应关系；close 路径只排空 queue 不清 set
- **影响**: scheduler 未 GC 时的内存泄漏（bouunded by unique session count）
- **建议改法和验证点**: 在 scheduler close 的 queue drain 后追加 `self._promotion_pending_session_ids.clear()`
- **修复风险（低）**: 纯 cleanup 操作
- **严重程度（中）**: 泄漏量 bounded，但显式清空是正确资源管理实践

### AG-004-中-Engine `_handle_final_decision` continuation merge 仅保留最后一次 Runner 调用的 identity

- **入口/函数**: `Agent._handle_final_decision`
- **文件(行号)**: `dayu/engine/agent.py:1109-1148`
- **输入场景**: LENGTH continuation 后 Runner 返回非 LENGTH finish_reason，内容由多个 Runner 调用的输出累积而成
- **实际分支**: `continuation_content_parts` 非空时，merge 后的 `_FinalDecision.response_identity = decision.response_identity`（仅最后一次调用的 identity）
- **预期行为**: 应记录所有参与 continuation 的 Runner 调用的 identity，或至少文档化"仅代表最后一次调用"
- **实际行为**: 前 N-1 次 continuation Runner 调用的 identity 丢失，无法追溯哪部分内容来自哪个 provider response
- **直接证据**: `agent.py:1137-1144` 合并 `decision.response_identity` 不保留历史 identity 列表
- **影响**: continuation 路径的审计可追溯性降低；`continuation_active=True` + `degraded=True` 信号表明这是合并结果，但未说明 identity 只代表最后一次调用
- **建议改法和验证点**: 至少应在 `FinalAnswerData` 或 Engine EventLog 的 docstring 中明确："`response_identity` 在 continuation merge 时仅代表最后一次 Runner 调用"。未来可考虑扩展为 `response_identity_chain`
- **修复风险（低）**: 文档级修复
- **严重程度（中）**: 审计可追溯性 gap；相比之前无任何 identity 已是大改进

### AG-005-中-Recovery `<=` 到 `<` 边界变更在精确 stale 时刻改变孤儿重分类时机

- **入口/函数**: `classify_orphan_candidate`
- **文件(行号)**: `dayu/host/recovery_process.py:272`
- **输入场景**: `policy.now - heartbeat_at == policy.stale_after`（精确边界时刻）
- **实际分支**: 旧代码 `<=` → `OwnerStillLive(retry_not_before=heartbeat_at + stale_after)`；新代码 `<` → 进入 `_classify_stale_owner`，若 identity 匹配成功 → `OwnerStillLive(retry_not_before=None)`，若失败 → `OrphanProofInconclusive`（无 `retry_not_before`）
- **预期行为**: 精确边界时刻的行为应确定性定义
- **实际行为**: `retry_not_before` 从有值变为 `None`（identity 匹配时），或完全不设置 delayed reclass（identity 匹配失败时），导致该边界时刻的 Run 在下一次 periodic reconciliation 前不被重扫
- **直接证据**: `recovery_process.py:272` diff `<=` → `<`；`recovery_process.py:353-355` `_classify_stale_owner` 路径 `retry_not_before=None`
- **影响**: 精确边界微秒的 Run 在下一次 periodic reconciliation 前不被重扫；实际触发概率极低
- **建议改法和验证点**: 在 `retry_not_before=None` 的路径增设保守默认值（如 `now + stale_after`），确保不依赖 periodic reconciliation 作为唯一恢复路径
- **修复风险（低）**: 变更一行
- **严重程度（中）**: 理论上可能导致 Run 在下一次 periodic 前停留 running；实际触发条件苛刻

### AG-006-中-测试覆盖 — 无 compaction_terminal guard 并发写入者竞争测试

- **入口/函数**: `test_compaction_terminal_writer_inventory_uses_only_shared_owner`
- **文件(行号)**: `tests/host/test_compaction_terminal.py:452`
- **输入场景**: 两个并发 write transaction 同时尝试为同一 `operation_id` 写入 terminal
- **实际分支**: 当前测试使用 AST 分析验证所有 writer 都经过 guard，但未真实执行并发写入
- **预期行为**: 两个并发 writer 中仅第一个获得 OPEN permit，第二个获得 `CompactionTerminalClosed`
- **实际行为**: guard 的线性化依赖 SQLite write serialization，语义正确，但未由测试直接证明
- **直接证据**: `test_compaction_terminal.py` 共 7 个测试，无 `asyncio.gather` 或多线程并发测试
- **影响**: 对 SQLite serialization 的依赖未在测试中显式证明
- **建议改法和验证点**: 增加并发测试：两个 writer 在同一 `HostTransaction` 边界内（通过 fake/mock 模拟）竞争同一 operation_id，断言一个 OPEN 一个 CLOSED
- **修复风险（低）**: 纯测试补充
- **严重程度（中）**: SQLite serialization 是成熟保证，但测试应显式证明

### AG-007-中-测试覆盖 — recovery 无 `stale_after` 阈值边界边缘测试

- **入口/函数**: `classify_orphan_candidate` 的 stale 判定
- **文件(行号)**: `dayu/host/recovery_process.py:272`
- **输入场景**: `policy.now - heartbeat_at` 恰好等于 `stale_after` 或差 1 微秒
- **实际分支**: 当前测试使用固定 `_NOW` 验证两侧（"inside stale threshold" → `OWNER_STILL_LIVE`；"stale heartbeat without identity" → `ORPHAN_INCONCLUSIVE`），但无 `stale_after - 1s` vs `stale_after + 1s` 的精确边界测试
- **预期行为**: 边界两侧行为确定性
- **实际行为**: 测试未显式验证 `<` 边界语义
- **直接证据**: `test_recovery_scan.py` 中 stale 相关测试使用 `timedelta(seconds=30)` 但无边界微调
- **影响**: 差一错误无法被测试捕获
- **建议改法和验证点**: 增加 `timedelta(seconds=30) - timedelta(microseconds=1)` 和 `timedelta(seconds=30) + timedelta(microseconds=1)` 两个边界的参数化测试
- **修复风险（低）**: 纯测试补充
- **严重程度（低→中）**: 低触发概率但高影响（孤儿 Run 可能不被正确分类）

### AG-008-低-Engine `_successful_response_identity()` ValueError 未捕获

- **入口/函数**: `Agent._classify_iteration` → `_successful_response_identity`
- **文件(行号)**: `dayu/engine/agent.py:1922-1931`
- **输入场景**: `runner_spec.provider` 或 `runner_spec.model` 为空字符串（绕过 `RunnerSpec` 构造校验）
- **实际分支**: `SuccessfulRunnerResponseIdentity.__post_init__` 抛出 `ValueError`，未被 `_classify_iteration` 捕获
- **预期行为**: 应产生 `RunFailedData` 并 fail closed，而非抛出未捕获异常
- **实际行为**: 异常透传到 `run_messages()` 调用者；runner 在 `finally` 中被正确关闭，但调用者收到异常而非终端事件
- **直接证据**: `agent.py:1922-1931` 直接构造不 try/except；`SuccessfulRunnerResponseIdentity.__post_init__` 的 `_validate_non_empty_text` 校验
- **影响**: 防御深度不足；在 `RunnerSpec` 构造校验有效的前提下不可达
- **建议改法和验证点**: 在 `_classify_iteration` 中将 `ValueError` 捕获并转为 `RunFailedData(error_code=_ERROR_RUNNER_EXCEPTION)`
- **修复风险（低）**: 纯防御性修改
- **严重程度（低）**: `RunnerSpec` 构造已校验，实际不可达

### AG-009-低-Engine force-answer empty content 路径丢弃 `provider_request_id`

- **入口/函数**: `Agent._run_force_answer` 或 `_make_iteration_failure_terminal`
- **文件(行号)**: `dayu/engine/agent.py:2469-2481`
- **输入场景**: force-answer Runner 完成但返回空内容
- **实际分支**: `provider_request_id=None` 硬编码；对比正常 `_classify_iteration(reject_empty_final_content=True)` 路径保留 `runner_done.provider_request_id`
- **预期行为**: 两个空内容检查路径行为一致
- **实际行为**: force-answer 路径丢失 provider 侧 request id
- **直接证据**: `agent.py:2477` `provider_request_id=None` vs `agent.py:1917` `provider_request_id=runner_done.provider_request_id`
- **影响**: `FORCE_ANSWER_EMPTY` 失败时降低了与 provider 侧关联的可追溯性；`client_correlation_id` 仍保留
- **建议改法和验证点**: 将 `provider_request_id=None` 改为 `state.runner_done.provider_request_id`
- **修复风险（低）**: 单行修改
- **严重程度（低）**: 错误码已区分（`FORCE_ANSWER_EMPTY` vs `RUNNER_EMPTY_FINAL_CONTENT`），operator 可区分

### AG-010-低-`_enqueue_requeued_promotion` 与 `_wake_queue_promotion` 逻辑重复

- **入口/函数**: `_enqueue_requeued_promotion` / `_wake_queue_promotion`
- **文件(行号)**: `dayu/host/dispatch.py:4570-4588` / `dispatch.py:1576-1584`
- **输入场景**: 两个函数共享相同的 flight check + pending set + queue put 逻辑
- **实际分支**: `_enqueue_requeued_promotion` 多了 `_closed` 前置检查
- **预期行为**: 公共逻辑抽取为单一 helper
- **实际行为**: 两处重复实现；如果逻辑需要变更，两处都必须更新
- **直接证据**: 两段代码逐行比对，除 `_closed` 检查外完全一致
- **影响**: 维护负担轻微增加
- **建议改法和验证点**: 抽取 `_enqueue_promotion_signal(session_id, *, allow_closed=False)` 公共 helper
- **修复风险（低）**: 纯重构
- **严重程度（低）**: 当前行为正确

### AG-012-中-`TOGGLE_ACTIVITY` 在 CANCELLING 阶段静默重置 `EXIT_AFTER_CANCEL`

- **入口/函数**: `_drive_interactive_tty_repl` 的 TOGGLE_ACTIVITY 处理分支
- **文件(行号)**: `dayu/cli/session_execution.py:1395-1399`
- **输入场景**: 用户已触发 EXIT_AFTER_CANCEL（第二次 Ctrl+C），在 CANCELLING 阶段按 Ctrl+T
- **实际分支**: `TOGGLE_ACTIVITY` 事件处理将 `exit_intent = CONTINUE`（行 1396），清除 EXIT_AFTER_CANCEL
- **预期行为**: Ctrl+T 只切换 activity 显示，不应改变退出意图
- **实际行为**: Ctrl+T 将两个语义上不同的操作混在一起：切换 activity 显示 和 取消退出计划。cancel 完成后 REPL 继续运行而非退出
- **直接证据**: `session_execution.py:1396` `exit_intent = _InteractiveExitIntent.CONTINUE`；`composer.py:445` TOGGLE_ACTIVITY 绑定的 `filter=active_phase` 在 RUNNING 和 CANCELLING 阶段均为 True
- **影响**: 用户取消并表达退出意图后，按 Ctrl+T 查看 activity 会导致 REPL 意外继续；用户困惑"为什么没退出"
- **建议改法和验证点**: TOGGLE_ACTIVITY 事件处理应只切换 display，不重置 `exit_intent`。或将 `exit_intent = CONTINUE` 的行移至 RUNNING 专属分支
- **修复风险（低）**: 删除一行 + 改条件分支
- **严重程度（中）**: 用户可见行为意外

### AG-013-中-`idle_interrupt_revision` 计数所有文本变更，退格/删除也触发，需要额外 Ctrl+C

- **入口/函数**: `PromptToolkitInteractiveComposer._record_text_change`
- **文件(行号)**: `dayu/cli/composer.py:308-317`；`dayu/cli/session_execution.py:1403-1405`
- **输入场景**: 用户在第一次 Ctrl+C 后、第二次 Ctrl+C 前对 draft 进行任何编辑（包括打一个字再删除）
- **实际分支**: `_record_text_change` 在每次 `on_text_changed` 时递增 `_input_revision`；'x' + Backspace = 2 次递增；`idle_interrupt_revision == event.input_revision` 严格比较失败
- **预期行为**: "两次 idle Ctrl+C 之间没有实质编辑"应只计实质性内容变更（非空 buffer 变为不同非空内容）
- **实际行为**: 打一个字再删除需要第三次 Ctrl+C 才退出，因为 revision 从 N 变为 N+2
- **直接证据**: `composer.py:316` `self._input_revision += 1` 无条件递增；`session_execution.py:1404` 严格相等比较
- **影响**: 用户误触后需要额外一次 Ctrl+C；体验摩擦
- **建议改法和验证点**: 改为跟踪 buffer 内容的 digest 而非递增计数器，只在 buffer 内容从"非空变为空、空变为非空、或从一个非空值变为另一个非空值"时才使 pending exit 失效
- **修复风险（中）**: 需要修改 composer 的 revision 跟踪逻辑和 session_execution 的比较逻辑
- **严重程度（中）**: 用户体验问题，非数据正确性问题

### AG-014-低-non-TTY batch 路径无显式 SIGINT 保护

- **入口/函数**: `_run_interactive_non_tty_batch`
- **文件(行号)**: `dayu/cli/session_execution.py:1163-1183`
- **输入场景**: non-TTY 管道输入期间收到 OS SIGINT
- **实际分支**: `await active.submit_task` 阻塞，无并发 `sigint_task` 观察；SIGINT 通过 `CancelledError` 传播到外层 `except BaseException`
- **预期行为**: 有显式的 SIGINT → exit 130 收口
- **实际行为**: SIGINT 的取消语义依赖外层异常处理，错误消息通用
- **直接证据**: `session_execution.py:1163-1183` 无 `sigint_monitor.wait_next` 调用
- **影响**: non-TTY batch 中 SIGINT 的错误消息不够精确
- **建议改法和验证点**: 在 batch await 前增加 `sigint_monitor.wait_next` 并发等待
- **修复风险（低）**: 增加一个并发 task
- **严重程度（低）**: non-TTY batch 中 SIGINT 罕见

### AG-015-低-`effective_binary_stdin is None` 防御性死代码

- **入口/函数**: `execute_interactive_on_session` 的 non-TTY 分支
- **文件(行号)**: `dayu/cli/session_execution.py:501-503, 533-536`
- **输入场景**: 无——`_resolve_interactive_binary_stdin` 总是返回有效值或 raise
- **实际分支**: `if effective_binary_stdin is None: raise RuntimeError(...)` 在当前代码路径中永远不可达
- **预期行为**: 防御性代码应可证明有用或应删除
- **实际行为**: 两处相同检查，造成"有两种错误模式"的假象
- **直接证据**: `session_execution.py:1084-1101` `_resolve_interactive_binary_stdin` 签名返回 `BinaryIO`（非 `BinaryIO | None`）
- **影响**: 维护者困惑
- **建议改法和验证点**: 删除死代码或改为 `assert effective_binary_stdin is not None`
- **修复风险（低）**: 纯清理
- **严重程度（低）**: 无行为影响

### AG-011-低-场景注册表无 interactive 命令场景

- **入口/函数**: `docs/cli_ci_scenarios.json`
- **文件(行号)**: `docs/cli_ci_scenarios.json`（全文）
- **输入场景**: 885 个注册场景中 interactive 命令场景数为 0
- **实际分支**: 仅有 `init.INIT-042R-reset-workspace-real-interactive`（跨命令验证），无 `interactive.I*` 场景
- **预期行为**: interactive 应有一套 mandatory scenario registry
- **实际行为**: interactive 需要真实 TTY 输入流，CI 编排器支持有限，因此场景未生成
- **直接证据**: `grep -c "interactive" cli_ci_scenarios.json` → 仅匹配 init 跨命令场景
- **影响**: interactive 命令无 formal CI readiness proof
- **建议改法和验证点**: 这是计划内的 G01-G07 future work，非本 WU scope
- **修复风险（N/A）**: future work
- **严重程度（低）**: 已知 gap，有显式 future work 计划

---

## Cross-cutting 验证

### 架构分层

CLI → Service → Host → Engine 分层未被违反：
- CLI 不读取 Host internals，只通过 `Host` public API (`ensure_session`, `attach`, `submit_followup`, `cancel_run`)
- Service 不增加 UI 状态
- Host 只依赖 Engine 的 typed identity (`SuccessfulRunnerResponseIdentity`)，不解构 `RunnerSpec`
- Engine 不理解 Host compaction operation

### 语义所有权

- compaction terminal 的 owner 是 `dayu.host.compaction_terminal`：proactive（dispatch.py）+ reactive（engine_ingest.py）均通过同一 `begin_compaction_terminal_commit_in_transaction` 入口
- label→slot 的 owner 是 `dayu.cli.host_context.cli_label_slot_key`：prompt 和 interactive 机械复用
- stdin 的 owner 是 `dayu.cli.composer`：session_execution 只消费 typed event
- Runner response identity 的 owner 是 `dayu.engine.contracts.runner_identity`：Host 只机械携带和验证

### Secret 泄露检查

**通过**。`SuccessfulRunnerResponseIdentity` 的 JSON 序列化（`_successful_response_identity_json`）只包含：
- `effective_provider`、`effective_model`
- `runner_request_identity`（run_id, attempt_id, execution_id, iteration_id, iteration_index, runner_call_index, client_correlation_id — SHA-256 hex hash）
- `provider_request_id_availability`、`provider_request_id`

无 API key、bearer token、endpoint、header 或 provider response body。

`arg_parsing.py` 中的 `_require_valid_utf8_invocation` 在 argparse 消费前拒绝非法 UTF-8 argv，防止 surrogate 文本泄漏。

### 并发安全

- **compaction_terminal guard**: SQLite write transaction 串行 + 事务内 fresh read 作为线性化点。两个并发 writer 不可能同时获得 OPEN permit。✅
- **pre-start single-flight**: `_pre_start_flights` dict + `asyncio.shield` + `rerun_requested` coalesced bit。同一 Session 最多一个 in-flight governance。✅
- **delayed recovery**: 每个 attachment/Session 至多一个 delayed task；取消时 `asyncio.shield` 保护已提交 actor future。✅
- **ManagedHostSessionAttachment.aclose**: `_close_task` 的 lazy init 无 `await` 之间，asyncio 协作式并发模型下安全。✅

### 类型安全

**通过**。pyright 全量 0 errors, 0 warnings, 0 informations。全域搜索无 `hasattr`/`getattr` 滥用、无 `Any`/`object` 类型泄漏、无 `# type: ignore` 新增。

### 向后兼容性

按项目"全新 schema 起库"策略，不保留旧 namespace（`cli.prompt.*`/`cli.interactive.*`）、旧参数（`--kind`、`--new-session`、`--model-name`）、旧 schema（legacy compaction payload）。所有 callers（生产代码、测试 fixture、smoke support）已同步更新。

---

## Open Questions

1. **行为项 29（G06 — 真实 provider successful compaction identity evidence）**: 已在 S6 的 supplementary evidence 中完成？S6 controller adjudication 提到 `interactive.S6-compaction-provider-identity-attempt-02` 的 raw evidence。本 review 未独立验证该 evidence 的内容，因为其位于 workspace 外部的 `.dayu-cli-ci` 目录。应确认该 evidence 的 digest 和 resolved provider identity 与 frozen oracle 一致。

2. **G01-G07 剩余项**: 本 WU 的 plan 明确将 G01-G07（真实 queued reconnect、完整 crash matrix、steer recovery、真实财报 refresh、真实成功 compaction continuity campaign）列为 future work。当前分支未覆盖这些 gap。

---

## Residual Risk

| 类别 | 风险 | 控制 | 残余 |
|------|------|------|------|
| legacy durable store | `_require_exact_fields` 拒绝旧 schema compaction 事件 | 全新 schema 起库策略 | 如有旧 workspace 存在，compaction 可能 fail-closed |
| 并发写入者证明 | compaction_terminal guard 依赖 SQLite serialization | AST 测试验证 writer inventory | 无真实并发 race 测试 |
| recovery 边界 | `<=` → `<` 在精确 stale 时刻改变行为 | periodic reconciliation 作为 fallback | 极端边界下 Run 可能多等一个周期 |
| interactive CI scenarios | 无 formal scenario registry | 已知 gap，列在 future work | interactive 缺少 CI readiness proof |
| continuation identity | 多次 Runner 调用只保留最后一次 identity | `degraded=True` + `continuation_active=True` flag | 前 N-1 次调用的 provider 关联丢失 |
| OS SIGINT idle | `idle_interrupt_revision=None` 导致不对称行为 | composer Ctrl+C 是主要 idle 输入路径 | 外部 SIGINT + 2 Ctrl+C 需要 3 次事件 |
| scheduler close set leak | `_promotion_pending_session_ids` 未 clear | bounded by unique session count | scheduler 未 GC 时微量泄漏 |
| 真实 compaction identity evidence | 行为项 29 raw evidence 未独立验证 | S6 controller 已裁决 | evidence 在外部 `.dayu-cli-ci` 目录 |
| TOGGLE_ACTIVITY 重置退出 | Ctrl+T 在 CANCELLING 阶段清除 EXIT_AFTER_CANCEL | 可修复为只在 RUNNING 阶段重置 | 用户可能在 cancel 后意外继续 REPL |
| idle_int_revision 过度计数 | 退格/删除也递增 revision 计数器 | 改为 digest-based 比较 | 误触后需额外 Ctrl+C |
| non-TTY batch SIGINT | batch 路径无并发 sigint_task | 外层 except BaseException 兜底 | 错误消息不够精确 |
| binary_stdin 死代码 | 两处 `is None` 检查不可达 | 可删除或改为 assert | 维护者困惑 |

---

## 最终结论

**PASS** — 无 critical 或 high 严重度 finding。

13 项 frozen fix（F01-F13）全部通过独立验证。每条均有生产代码直接证据、测试断言和 pyright 结果支撑。

发现 15 条 finding：
- **中严重度**: 9 条（AG-001 至 AG-007, AG-012, AG-013）— 主要包括 OS SIGINT idle 行为不对称、legacy schema 兼容性、scheduler close 资源泄漏、continuation identity 审计 gap、recovery 边界语义、两个测试覆盖 gap、TOGGLE_ACTIVITY 重置退出意图、以及 idle_interrupt_revision 过度计数
- **低严重度**: 6 条（AG-008 至 AG-011, AG-014, AG-015）— 防御深度、易维护性、non-TTY SIGINT gap 和已知 future work gap

全部 medium finding 均为已知设计 trade-off 或边缘路径问题，不构成 merge blocker。low finding 均为防御深度或文档级改进。

建议在 merge 前优先修复：AG-003（scheduler close set leak，一条 `clear()` 调用）、AG-005（recovery 边界 `retry_not_before` 保守默认值）、AG-012（TOGGLE_ACTIVITY 不应重置 EXIT_AFTER_CANCEL）。
