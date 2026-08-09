# Code Review

## Scope

- **Mode**: PR Review
- **PR**: [#190 — fix(cli): close interactive conformance gaps](https://github.com/noho/dayu-agent-r/pull/190)
- **Author**: noho (Leo Liu)
- **Base**: `main` (`113ea34d`)
- **Head**: `a4ff05db` (`codex/interactive-oracle`)
- **State**: Draft
- **Review date**: 2026-08-02
- **Output file**: `docs/reviews/pr-review-wu-cli-interactive-02-ds-20260802.md`
- **CI**: 该分支上无已报告的 GitHub checks
- **Merge base**: `113ea34d47b95812d79aa31705949bbb46bc6061`
- **Mergeable**: MERGEABLE（无冲突）
- **Base drift**: 无——`main` 上没有落后于 merge base 的新提交
- **Included scope**:
  - 16 commits，含 ae6bb96f（calibration matrix）和 cc5c9d57（oracle adjudication）——均在 commit chain 中
  - 生产代码变更：CLI（8 文件）、Host（14 文件）、Engine（7 文件）
  - 文档变更：README.md、dayu/README.md、engine/README.md、host/README.md、docs/cli_ci.md、docs/cli_ci_oracles.json、docs/cli_ci_scenarios.json、docs/engine/design.md、docs/host/design.md、docs/host/wu-cli-interactive-02-conformance-fixes-plan.md
  - Gateflow artifacts：docs/reviews/ 中 40+ review/adjudication/fix 记录
  - 测试文件变更：47 个测试文件
- **Excluded scope**:
  - `docs/reviews/` 中 AgentMiMo review artifacts（按指令跳过）
  - 与 S1–S6 无关的 docs/reviews 历史记录仅作文档完整性确认，不深读
- **Parallel review coverage**: 无——本 review 由单人独立完成全部走读

## 走读方法

1. 从 GitHub API 读取 PR metadata、commit chain、file list 和 PR body，确认 ae6bb96f/cc5c9d57 在 chain 中，对比 merge base 为 `113ea34d`，验证无 base drift。
2. 按 S1–S6 逐 slice 走读生产代码 diff：arg_parsing → host_context / session_identity → composer → session_execution → run_keys / agent_entrypoint → recovery → compaction_terminal → dispatch proactive → engine_ingest reactive → proactive_compaction projection → engine agent → runner_identity → compaction / llm_compaction / context_events。
3. 对每条关键数据路径展开：参数来源 → 校验 → 覆盖优先级 → 最终消费 → 副作用（parser→command、composer event→REPL state machine、compaction request→terminal→artifact/fact、Engine success→response identity→Host durable payload）。
4. Adversarial failure pass：检查 cancel/并发/terminal race/idempotent re-entry/single-flight/SIGINT fallback/secret 泄漏/non-TTY 边界/空输入/非法 UTF-8/stale control/composer phase 一致性。
5. Semantic ownership drift pass：按 plan 3.1 节的 owner table 逐项验证语义归属。
6. 阅读 plan document（F01–F13 定义与 design alignment），交叉验证实现与冻结语义的一致性。
7. 检查 frozen oracle（cli_ci_oracles.json → 3 accepted oracles：init/prompt/interactive），确认 interactive oracle predicates 覆盖 F01–F13 行为项。
8. 检查测试文件清单和 PR body 中报告的测试通过数，验证测试覆盖关键变更路径。

**实际走读覆盖**：所有 27 个生产代码文件 diff 已逐文件、逐函数走读；关键测试文件 spot-check 验证 contract test 存在性。

## Findings

### 1-未修复-中-engine-success-outcome-public-contract-breaking-change

- **入口/函数**: `EngineRunOutcomeFinalAnswer` 与 `FinalAnswerData` — Engine public contract dataclass
- **文件(行号)**:
  - `dayu/engine/contracts/agent_run.py:154` — `EngineRunOutcomeFinalAnswer.response_identity`
  - `dayu/engine/contracts/engine_events.py:447` — `FinalAnswerData.response_identity`
- **输入场景**: Engine 正常完成一次 Runner call 后构造 success outcome
- **实际分支**: 两个 dataclass 的 `response_identity` 字段均为**必填**（无默认值），类型为 `SuccessfulRunnerResponseIdentity`
- **预期行为**: 若此 PR 承诺兼容旧 Engine consumer，contract 变更应标注为 breaking change 并有迁移说明
- **实际行为**: `response_identity` 从旧版本的**不存在**变为**必填**。任何在 PR scope 外构造 `EngineRunOutcomeFinalAnswer` 或 `FinalAnswerData` 的代码将在运行时因缺少必填参数而失败
- **直接证据**:
  - Base（`113ea34d`）: `EngineRunOutcomeFinalAnswer` 有 6 个字段（session_id, run_id, content, filtered, degraded, finish_reason）；`FinalAnswerData` 有 4 个字段（content, filtered, degraded, finish_reason）
  - Head（`a4ff05db`）: 各自新增第 7/5 个必填字段 `response_identity: SuccessfulRunnerResponseIdentity`
- **影响**: PR scope 内的构造点（`engine/agent.py` 的 `_build_final_decision`、`_finalize_with_decision`、`run_agent_and_wait`）均已更新；但该 contract 是 `dayu.engine` 的公共导出类型，任何外部 consumer（包括未来 Host adapter、测试 fixture、benchmark harness）若直接构造这两个 dataclass 将失败
- **建议改法和验证点**:
  1. 在 PR body 中显式标注此 contract 为 breaking change，说明所有构造点已在本 PR 中更新
  2. 验证 `EngineRunOutcomeFinalAnswer` 和 `FinalAnswerData` 的全部构造点（含测试 fixture）均已传递 `response_identity`
  3. 运行全量 Engine + Host 测试确认无遗漏的 fixture 构造点
- **修复风险（低）**: 不涉及代码修改，仅补充文档声明
- **严重程度（中）**: breaking change 已被 PR scope 完全覆盖，但缺少显式 contract 变更声明可能导致外部 consumer 静默失败

### 2-未修复-低-engine_ingest-dispatch-duplicate-required-identity-helpers

- **入口/函数**: `_required_successful_response_identity` 与 `_required_compactor_manifest_reference` — 在两个 Host 模块中重复定义的私有 helper
- **文件(行号)**:
  - `dayu/host/engine_ingest.py:8818-8842` 与 `dayu/host/engine_ingest.py:8845-8861`
  - `dayu/host/dispatch.py:6257-6274` 与 `dayu/host/dispatch.py:6277-6293`
- **输入场景**: 在 compaction operation 返回 accepted result 后，proactive（dispatch）或 reactive（engine_ingest）writer 需要提取成功响应身份和 manifest reference
- **实际分支**: 两个模块各自定义了完全相同的 `_required_successful_response_identity(result)` 和 `_required_compactor_manifest_reference(result)` 函数
- **预期行为**: 共享语义应有单一 owner 和单一实现；重复定义违反 semantic ownership 原则，任一处的单独修改可能导致 proactive/reactive 路径行为分歧
- **实际行为**: 两处实现目前完全一致，但缺少编译期或测试期的共享契约保证
- **直接证据**:
  - `engine_ingest.py:8818-8861` 定义了 `_required_successful_response_identity` 和 `_required_compactor_manifest_reference`
  - `dispatch.py:6257-6293` 定义了完全相同的两个函数
  - `compaction_operation.py` 定义了 `CompactionOperationResult`（共享的返回类型），是自然的共享位置
- **影响**: 当前无功能影响（两处实现一致）。风险在于未来维护中一处更新另一处遗漏，导致 proactive 与 reactive compaction 的 durable event payload 不一致
- **建议改法和验证点**:
  1. 将两个 helper 提取到 `compaction_operation.py` 并作为 public helper（或至少 shared private）导出
  2. `dispatch.py` 和 `engine_ingest.py` 改为 import 复用
  3. 验证 proactive 和 reactive 路径的 compacted event payload 结构一致
- **修复风险（低）**: 纯重构，不改变运行时行为
- **严重程度（低）**: 当前无功能缺陷，但增加未来维护风险

### 3-未修复-低-resolve-interactive-binary-stdin-dead-parameter

- **入口/函数**: `_resolve_interactive_binary_stdin`
- **文件(行号)**: `dayu/cli/session_execution.py:1086`
- **输入场景**: interactive non-TTY 路径需要获取二进制 stdin
- **实际分支**: 函数签名接受 `args: ParsedCliArgs` 参数但不使用
- **预期行为**: 不应接受未使用的参数；若为未来扩展预留，应在 docstring 中说明
- **实际行为**: 参数存在于签名中但函数体始终返回 `sys.stdin.buffer`，完全不依赖 `args`
- **直接证据**:
  ```python
  def _resolve_interactive_binary_stdin(args: ParsedCliArgs) -> BinaryIO:
      """解析并返回 interactive non-TTY 使用的二进制 stdin。"""
      return sys.stdin.buffer
  ```
- **影响**: 仅代码清洁度问题，无运行时影响
- **建议改法和验证点**: 删除 `args` 参数或补充 docstring 说明预留意图
- **修复风险（低）**: 调用处需同步更新
- **严重程度（低）**: 不影响正确性

### 4-未修复-低-non-tty-blank-stream-silent-success

- **入口/函数**: `_run_interactive_non_tty_batch`
- **文件(行号)**: `dayu/cli/session_execution.py:1128-1197`
- **输入场景**: 向 `dayu-cli interactive` pipe 一个空文件或立即 EOF 的流
- **实际分支**: `_read_interactive_non_tty_text` 返回空字符串 → `EXIT_SUCCESS` 直接返回
- **预期行为**: 符合 frozen oracle "空白流不提交"——行为正确
- **实际行为**: 无任何用户可见输出（无提示符、无诊断），与 TTY 路径的交互体验不一致（TTY 路径至少显示 `dayu> ` 提示符）
- **直接证据**:
  ```python
  user_prompt = _read_interactive_non_tty_text(binary_stdin=binary_stdin, ...)
  if user_prompt == "":
      return EXIT_SUCCESS
  ```
- **影响**: pipe 空流到 interactive 静默成功。用户可能误以为命令执行了操作。这不是功能性 bug（行为符合 oracle），但交互体验不一致
- **建议改法和验证点**: 可接受；oracle 已冻结 "空白流不提交"。若要改进，可在 stderr 输出一行提示
- **修复风险（低）**: 仅影响 non-TTY 空白流场景
- **严重程度（低）**: 行为符合 oracle，仅交互体验差异

## F01–F13 冻结语义验证摘要

| 冻结项 | 语义 | 实现位置 | 验证结果 |
|---|---|---|---|
| F01 | prompt/interactive 无 `--config` | `arg_parsing.py`（`command_common_parent` + `_reject_disallowed_explicit_config`） | **PASS** — parser 层面拒绝 + root `--config` 前置拒绝，双路径 fail-closed |
| F02 | interactive 无 `--ticker` | `arg_parsing.py`（`_register_interactive_command` 删除 `--ticker`） | **PASS** — 参数已从 parser 移除；invocation 固定传 `ticker=None` |
| F03 | 统一 label slot namespace | `host_context.py`（`CLI_AGENT_SESSION_SCOPE` / `cli_label_slot_key`） | **PASS** — 旧 `PROMPT_SESSION_SCOPE`/`INTERACTIVE_SESSION_SCOPE` 已删除，不 re-export；`session_identity.py` 删除 `CliSessionLabelKind` |
| F04 | `--kind` 已移除；session label selector 直接复用统一 slot | `arg_parsing.py`（删除 `--kind` 与 `SESSION_LABEL_KIND_CHOICES`）；`session_identity.py`（`slot_ref_for_cli_label(label)` 不接收 kind） | **PASS** |
| F05 | TTY 由 composer 独占 stdin | `composer.py`（`PromptToolkitInteractiveComposer` + typed `InteractiveComposerEvent`）；`run_keys.py` docstring 明确 "interactive 不使用本模块" | **PASS** |
| F06 | non-TTY 整个 UTF-8 stream 作为至多一个 Run | `session_execution.py`（`_run_interactive_non_tty_batch` + `_read_interactive_non_tty_text`） | **PASS** — 一次 `binary_stdin.read()` 读整个流，空白不提交，非法 UTF-8 报错退出 |
| F07 | standalone Escape/Ctrl+C 请求 graceful cancel | `composer.py`（`escape` binding → `CANCEL_ACTIVE` + `Escape` source；`c-c` binding → `CANCEL_ACTIVE` + `Ctrl_C` source） | **PASS** — ESC 只在 standalone 解析时触发（`filter=active_phase`）；Ctrl+C 在 idle phase 清空 draft，active phase 触发 cancel |
| F08 | Ctrl+C 取消收口期间再次 Ctrl+C 登记 exit-after-cancel | `session_execution.py`（`_drive_interactive_tty_repl` 中第二次 `CANCEL_ACTIVE` + `Ctrl_C` → `EXIT_AFTER_CANCEL`） | **PASS** — exit-after-cancel 仅在 current terminal 收口且 queued follow-up 完成后退出 |
| F09 | 运行期间键入 draft 保留到收口；Enter 最多排入一个后续问题 | `session_execution.py`（queued follow-up sole slot + `_INTERACTIVE_QUEUED_DRAFT_MESSAGE`）；`composer.py`（`read_event` 恢复 draft/cursor） | **PASS** — 一个 queued slot，第二次 Enter 打印警告保留 draft |
| F10 | fresh RW attachment delayed orphan recovery | `open_host.py`（`_ManagedHostSessionAttachment` + `_schedule_delayed_attachment_recovery`）；`recovery.py`（`OWNER_STILL_LIVE` + `retry_not_before`） | **PASS** — 首次 scan 的 `next_reconcile_at` 派生 deadline task；attachment/Host close 取消并 join |
| F11 | 每个 compaction operation 精确一个 canonical terminal | `compaction_terminal.py`（`begin_compaction_terminal_commit_in_transaction` + first-committer-wins）；`dispatch.py`（3 个 proactive writer 调用点）；`engine_ingest.py`（reactive writer 调用点）；`proactive_compaction.py`（projection 复用 terminal owner） | **PASS** — transaction-local fresh read 作线性化点；`INVALID_MULTIPLE` → fail-closed |
| F12 | per-Session pre-start single-flight | `dispatch.py`（`_PreStartGovernanceFlight` + `_run_pre_start_governance_flight` + `rerun_requested` coalesced bit） | **PASS** — wake/periodic 信号合并为同一 flight；多 pass 间 bit 检查与 dictionary delete 间无 `await` |
| F13 | Engine success identity → Host durable projection | `engine/agent.py`（`_successful_response_identity` → `_FinalDecision` → `FinalAnswerData` → `EngineRunOutcomeFinalAnswer`）；`llm_compaction.py`（`_validated_prepared_response_identity`）；`context_events.py`（`_successful_response_identity_json` + `_parse_successful_response_identity` + strict field validation） | **PASS** — 安全字段（effective provider/model、request identity、provider request id availability）；无 endpoint/credential/header/secret |

## Merge correctness 检查

- **Base drift**: 无。`git merge-base main a4ff05db` 返回 `113ea34d`，`main` 上无后续提交。
- **File coverage**: PR body 声称的 scope（F01–F13 覆盖的 CLI/Service/Host/Engine 变更）与 diff 中的实际文件一致。无遗漏。
- **Commit 完整性**: ae6bb96f（calibration matrix）和 cc5c9d57（oracle adjudication）均为 PR chain 前两个提交。
- **Draft status**: PR 为 draft，PR body 明确表示等待 PR-specific deep review。这是预期状态。

## Public contract / docs / scenario / oracle 真实性

- **cli_ci_oracles.json**: 3 个 accepted oracles（init/prompt/interactive），interactive oracle 含 28+ 行为项 predicates，覆盖 F01–F13 语义。
- **cli_ci_scenarios.json**: 大规模重写（+337/-2404），从旧 legacy scenario 迁移到新 frozen contract。
- **README.md**: 更新了 interactive 参数说明、label 行为、TTY 输入约定、Ctrl+C/Ctrl+D/Escape 语义——与实现一致。
- **dayu/README.md**: 更新了稳定边界、Session label slot、compaction 与 recovery 段落。
- **engine/README.md** / **host/README.md**: 小范围更新，与 Engine/Host 变更一致。

## Concurrency / cancel / recovery 验证

- **Compaction terminal first-committer-wins**: SQLite write transaction 串行化保证。`begin_compaction_terminal_commit_in_transaction` 在 write transaction 内 fresh read request + terminal rows，仅 OPEN 时返回 permit。第二个 writer 在另一个 write transaction 中会看到第一个的 terminal → CLOSED。
- **Reactive compaction 并发修复**: 原来 `_execute_reactive_compaction` 的 outcome executor 在事务外运行，两个 executor 可能分别拿到 accepted/failed。现在 terminal owner guard 在 write transaction 内做线性化检查，第二个 executor 会看到 CLOSED。
- **Pre-start single-flight**: `rerun_requested` bit 在 `_run_pre_start_governance_flight` 循环中被检查和清除，且 bit 检查与 `del self._pre_start_flights[session_id]` 之间无 `await`——不会漏信号。
- **SIGINT fallback**: `CliSigintMonitor` 新增 `_CliSigintInstallationMode.SYNCHRONOUS`。`_notify_from_synchronous_handler` 使用 `loop.call_soon_threadsafe(self.notify)`，从 signal handler 上下文安全投递到事件循环。
- **Attachment delayed recovery lifecycle**: `_ManagedHostSessionAttachment.aclose` 使用 `asyncio.shield` 防止 caller cancel 泄漏 orphan task；`_cancel_and_join_delayed_attachment_recovery` 在 Host close 时批量取消。

## Provider identity / secret 验证

- **序列化内容**: `_successful_response_identity_json` 仅包含 `effective_provider`、`effective_model`、`runner_request_identity`（含 `run_id`、`client_correlation_id`）、`provider_request_id_availability`、`provider_request_id`。
- **不含敏感字段**: 不含 endpoint URL、credential、header value、API key、bearer token、raw provider payload。
- **Provider request ID**: 当 `provider_request_id` 为 `None` 时，availability 显式记为 `unavailable`；不存在时序列化为 JSON `null`。
- **Client correlation ID canonical check**: `_parse_successful_response_identity` 从 durable 重建 identity 时，通过 `build_runner_request_identity` 重新计算 canonical `client_correlation_id`，并与存储值严格比较——防止 payload 篡改或序列化错误。

## Review completeness

本 review 覆盖了 PR 中全部 27 个生产代码文件的 diff，逐文件逐函数走读了关键数据路径。还读取了 plan document、frozen oracle 和 scenario registry。以下区域受限于 scope 做 spot check 而非 exhaustive read：

- 47 个测试文件未逐文件阅读——通过 PR body 的测试通过数（CLI/Service 1181 passed, Host 775 passed, Engine/Host 2957 passed）和关键 contract test 文件的 spot check 验证测试覆盖存在性
- `docs/reviews/` 下 40+ Gateflow artifact 仅做存在性确认，未深读（按指令跳过 AgentMiMo artifact，其余做完整性确认）
- `docs/cli_ci_scenarios.json` 因体量（2741 行变更）未逐条走读

## Open Questions

1. **CI 未运行**: PR 分支上无 GitHub checks 报告。PR body 声称本地测试全部通过（含 pyright 0 errors/warnings），但缺少 CI 自动化验证。需在 mark ready 前触发 CI。
2. **EngineRunOutcomeFinalAnswer.response_identity 对非 compactor Run 的影响**: 所有成功 Engine run 现在都在 EventLog 中携带 `response_identity`。当前 Host 只在 compaction event payload 中显式读取和存储该字段。对于非 compaction 的 regular Run completion event，`response_identity` 是否进入 EventLog payload 取决于 `FinalAnswerData` 到 EventLog row 的投影路径——本 review 未逐层追踪非 compaction Run completion 的完整投影链，以确认 `response_identity` 不会泄漏到不适当的 durable projection（如 user-facing conversation memory）。
3. **`docs/reviews/` 中 AgentMiMo aggregate deep review 发现**: 按指令未读取，但这些 finding 已通过 aggregate adjudication 处理并体现在 PR body 中。若有未被 adjudication 覆盖的 residual risk，本 review 无法确认。

## Residual Risk

1. **Compaction terminal `INVALID_MULTIPLE` 仅 fail-closed，不自动修复**: 若因 bug 或极端并发导致同一 operation 出现多个 terminal，系统会抛 `HostDurableError` 终止当前操作，但不自动清理或合并。长期运行后可能需要手动干预。PR body 和 plan 均将此列为 fail-closed 预期行为——可接受。
2. **POSIX SIGINT fallback 路径缺少集成测试**: `_CliSigintInstallationMode.SYNCHRONOUS` 路径仅在 `loop.add_signal_handler` 不可用的平台触发。在 macOS（支持 asyncio signal handler）上该路径仅在单元测试中可达，缺少真实平台的端到端验证。
3. **Non-TTY stdin blocking read**: `_read_interactive_non_tty_text` 使用 `binary_stdin.read()` 同步阻塞读取。对于非常大的 pipe 输入或慢速流，这会阻塞事件循环。当前仅支持 "整个流作为一个 draft"，对超大输入无 chunk 或流式保护。
4. **Engine contract breaking change 的影响面**: `EngineRunOutcomeFinalAnswer` 和 `FinalAnswerData` 的新增必填字段已在本 PR 中全覆盖。若存在 PR scope 外的构造点（如未纳入本 PR 的测试 harness、benchmark、外部集成），会在运行时失败。
5. **47 个测试文件的 exhaustive 覆盖验证未完成**: 本 review 通过 spot check 关键 contract test（`test_runner_identity.py`、`test_compaction_terminal.py`、`test_context_compact_events.py`、`test_compaction_operation.py`、`test_llm_compaction.py`、`test_interactive_command.py`、`test_interactive_composer.py`）确认测试存在且与实现对齐。但未逐文件走读全部 47 个测试文件的 diff。

## Conclusion

**PASS** — 未发现 blocking 或 critical severity 的缺陷。

本 PR 实现了 F01–F13 全部 13 个冻结项，实现质量高，语义归属清晰，架构边界保持良好。关键变更——参数收敛（F01–F04）、composer 独占 stdin（F05–F09）、delayed orphan recovery（F10）、compaction terminal first-committer-wins（F11）、pre-start single-flight（F12）、Engine success identity durable projection（F13）——均有正确的 owner 边界、transaction 安全性与 cancel/recovery 路径处理。

发现的 4 个 findings 均为中/低严重度：contract breaking change 缺少显式声明（中）、重复 helper 定义（低）、dead parameter（低）、non-TTY 空白流静默成功（低）。均不影响 merge correctness。

PR 当前为 **draft**，PR body 声明等待 PR-specific deep review（本 review）。建议在 mark ready 前：
1. 触发 CI 运行确认测试通过
2. 在 PR body 中标注 `EngineRunOutcomeFinalAnswer.response_identity` 为 breaking change
3. 将 `_required_successful_response_identity`/`_required_compactor_manifest_reference` 提取到 `compaction_operation.py` 消除重复

**Next gate**: 将本 finding 提交 controller adjudication，accept/reject/defer 后推进 draft PR final closeout。
