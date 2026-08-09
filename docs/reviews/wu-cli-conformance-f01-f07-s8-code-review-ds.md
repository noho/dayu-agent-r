# Code Review — WU-CLI-CONFORMANCE-F01-F07 S8 Gate

## Scope

- **Mode**: current changes (target commit vs base)
- **Branch**: `codex/interactive-oracle`
- **PR**: 190
- **Target commit**: `9fec164715bc6af7a4a7d7446cb45d49593ec64f`
- **Base commit**: `cd6344c0`
- **Output file**: `docs/reviews/wu-cli-conformance-f01-f07-s8-code-review-ds.md`
- **Evidence bundle**: `/Users/leo/workspace/.dayu-cli-ci/pr190-wu-cli-conformance-f01-f07-s8-20260803T022326Z-9fec164715bc/bundle`
- **Bundle digest**: `7a80d9bcfb97bb7c8a80df8d2f10016d6f98577e01294f540a7ba2d9cea33b72`
- **Included scope**:
  - Full diff `cd6344c0..9fec164715` covering 166 files across CLI, Host, tests, config, docs
  - Immutable evidence bundle (443 entries, SHA256SUMS-verified)
  - Uncommitted intended S8 files: `README.md`, `dayu/config/README.md`, `dayu/host/README.md`, `tests/README.md`
  - Codex S8 implementation review: `docs/reviews/wu-cli-conformance-f01-f07-s8-implementation-codex.md`
- **Excluded scope**: 无
- **Parallel review coverage**: 无 — 本 review 由主 reviewer 单人执行全量走读

## Review Method

本 review 对 F01-F07 七项 accepted oracle 逐项执行以下检查：

1. **Oracle alignment**: 实现 diff 是否与 oracle predicate 的 expected/forbidden 对齐
2. **Owner-level evidence**: bundle 中的证据是否来自正确的 semantic owner（parser boundary、Host EventLog、Tool Trace、Memory projection、真实 CLI/PTY），而非 CLI 自报、exit code、mock 或下游 projection
3. **Multi-source consistency**: canonical EventLog、Host Run/Attempt index、Tool Trace、Memory snapshot、SQLite payload、compact artifact、真实生成物是否从同一 accepted truth 派生
4. **Target/digest/secret scan/只读封存**: bundle SHA256SUMS、digest、secret scan、writable paths 校验
5. **README 职责与实现 artifact 准确性**: 未提交 README 变更是否与各 README 职责边界对齐，是否准确反映实现事实
6. **Adversarial check**: 是否把 CLI 自报、exit code、mock、fake provider 或下游 projection 当 owner truth

## Findings

### F01 — remove global config

#### 001-PASS-F01-remove-global-config-complete

- **入口/函数**: `dayu/cli/arg_parsing.py:_build_runtime_arguments_parent` (已删除), `_reject_disallowed_explicit_config` (已删除)
- **文件(行号)**: `dayu/cli/arg_parsing.py:225-230` (删除 runtime parent), `dayu/cli/arg_parsing.py:285-310` (删除 reject 函数), `dayu/cli/arg_parsing.py:384-385` (删除 `config_dir` namespace default)
- **输入场景**: 任意 CLI invocation 携带 `--config`
- **实际分支**: `--config` 不再注册为任何 argparse action；携带该参数触发 argparse `unrecognized arguments` → exit 2
- **预期行为**: Oracle `cli.init.workspace-initialization` predicate `init.workspace-resolution` forbidden: "init 命令存在、展示、接受或解释 --config"; Oracle `cli.interactive.core-execution` predicate `interactive.01-public-parameter-surface` forbidden: "为 prompt/interactive --config 建立 accepted scenario"
- **实际行为**: 完全移除。所有 command（init/prompt/interactive/session/download/upload/process/tool-trace）统一使用 `command_common_parent`（不含 `--config`），`_build_runtime_arguments_parent` 整函数删除
- **直接证据**:
  - Diff: `_build_runtime_arguments_parent` 函数体删除 (`arg_parsing.py:516-541`)
  - Diff: `_reject_disallowed_explicit_config` 函数体删除 (`arg_parsing.py:285-310`)
  - Diff: `_new_default_namespace` 删除 `namespace.config_dir = None` (`arg_parsing.py:340`)
  - Diff: `ParsedCliArgs.config_dir` 字段删除 (`arg_parsing.py:163`)
  - Bundle evidence: `parser-inventory.json` 中 `config_option_occurrences=[]`，81 scoped actions 零命中
  - Bundle evidence: help/init.txt, help/interactive.txt, help/prompt.txt, help/root.txt 的 `--config` occurrences 均为 0
  - Bundle evidence: 7 条 rejection lane (root-before, init-before/after, prompt-before/after, interactive-before/after) 全部 exit 2
- **影响**: 无 — 符合 oracle
- **建议改法和验证点**: 无需修改
- **修复风险（低/中/高）**: 无
- **严重程度（低/中/高/严重）**: PASS

**Adversarial check**: 通过。证据同时包含 parser inventory（argparse 真源）、help output（CLI 自报但经独立文件校验）、rejection exit codes（OS-level 真源）。不存在用单一 CLI 自报替代多源验证的情况。

---

### F02 — explicit invalid editor

#### 002-PASS-F02-explicit-invalid-editor-owner-boundary

- **入口/函数**: `dayu/cli/composer.py:_ExplicitEditorCommand`, `_EditorConfigurationError`, `_EditorActionError`
- **文件(行号)**: `dayu/cli/composer.py:48-139` (新增类型), `dayu/cli/composer.py:234-330` (editor round trip)
- **输入场景**: VISUAL/EDITOR 环境变量配置了不存在、不可执行或无法启动的编辑器
- **实际分支**: `_EditorConfigurationError` 在 editor 解析阶段 fail closed → 显示脱敏错误 → 保留 draft → 恢复 composer
- **预期行为**: Oracle `interactive.09-external-editor` expected: "环境显式配置但目标不存在、不可执行或无法启动时，必须显示清晰错误并返回原 composer"
- **实际行为**: missing lane (editor 不存在): draft 保留, Runs=0, Attempts=0, Tool Trace rows=0, exit 0; nonexec lane (不可执行): 同上; spawn-failure lane (启动失败): 同上
- **直接证据**:
  - Diff: 新增 `_EditorConfigurationErrorReason` enum 含 `EMPTY_COMMAND`, `INVALID_SYNTAX`, `EXECUTABLE_NOT_FOUND`, `NOT_EXECUTABLE` (`composer.py:59-65`)
  - Diff: 新增 `_EditorActionFailureReason` enum 含 `TEMPFILE_UNAVAILABLE`, `SPAWN_FAILED`, `READBACK_FAILED`, `CLEANUP_FAILED` (`composer.py:68-74`)
  - Bundle evidence: `f02-matrix.json` 三 lane 全部 Runs=0, Attempts=0, Tool Trace rows=0, exit_code=0, terminal_restored=true
  - Bundle evidence: `f02-missing/command-result.json` 确认 editor_kind="missing", draft_occurrences=1
  - Bundle evidence: owner-projections 对三个 lane 分别交叉验证 EventLog/SQLite/Tool Trace
- **影响**: 无 — 符合 oracle
- **建议改法和验证点**: 无需修改
- **修复风险（低/中/高）**: 无
- **严重程度（低/中/高/严重）**: PASS

**Adversarial check**: 通过。证据同时覆盖 CLI terminal output、owner projection (EventLog/SQLite/Tool Trace) 三源交叉确认 Runs=0/Attempts=0。未用 CLI 自报替代 durable owner。

---

### F03 — graceful cancel / escape sequences

#### 003-PASS-F03-escape-sequence-disambiguation

- **入口/函数**: `dayu/cli/run_keys.py:TtyRunningKeyMonitor._read_loop`
- **文件(行号)**: `dayu/cli/run_keys.py:237-318` (重写 _read_loop), `dayu/cli/run_keys.py:10-13` (新增 Vt100Parser import)
- **输入场景**: prompt/interactive Run 中收到 CSI、Home/Delete、Alt+X、bracketed paste 等 ESC-prefixed 序列
- **实际分支**: `Vt100Parser` 增量解析完整 VT100 sequence → `_classify_running_key_batch` 分类 → 非 standalone Escape 不触发 cancel
- **预期行为**: Oracle `prompt.17-running-escape-sequence-disambiguation` expected: "完整CSI、Home/Delete、Alt与bracketed-paste sequence不得因首byte为ESC而取消one-shot Run"; Oracle `interactive.18-running-escape-sequence-disambiguation` 同
- **实际行为**: 所有 ESC-prefixed sequence lanes exit 0, terminal restored, conforms=true
- **直接证据**:
  - Diff: `_read_loop` 从单字节 `os.read(fd, 1)` 改为 `os.read(fd, 1024)` + `Vt100Parser` 增量解析 (`run_keys.py:247-318`)
  - Diff: `ESCAPE_SEQUENCE_AMBIGUITY_SECONDS = 0.1` 常量 (`run_keys.py:33`)
  - Diff: `tty.setcbreak(fd, when=termios.TCSANOW)` 改为 TCSANOW 不清空 pre-accept buffer (`run_keys.py:169`)
  - Bundle evidence: `f03-matrix.json` frozen prompt CSI/Home/Delete, Alt+X, bracketed paste 全部 conforms=true, exit 0
  - Bundle evidence: interactive CSI/Home/Delete, Alt+X same/cross chunk, bracketed paste 全部 conforms=true, exit 0
- **影响**: 无 — 符合 oracle
- **建议改法和验证点**: 无需修改
- **修复风险（低/中/高）**: 无
- **严重程度（低/中/高/严重）**: PASS

#### 004-PASS-F03-preaccept-escape-graceful-cancel

- **入口/函数**: `dayu/cli/session_execution.py:_ActiveTurnCloseout`
- **文件(行号)**: `dayu/cli/session_execution.py:217-318` (新增 closeout coordinator)
- **输入场景**: pre-accept 阶段 standalone Escape
- **实际分支**: composer 将 standalone Escape 分类为 `RUNNING_KEY_ACTION` (cancel) → closeout coordinator 跨 acceptance barrier 发起 cancel
- **预期行为**: Oracle `interactive.11-running-escape-cancels-without-exit` expected: "standalone Escape 在 pre-accept 可取消阶段表达取消当前 Run; Run 尚未返回 id 时，取消必须跨 acceptance barrier 收口"
- **实际行为**: interactive pre-accept Escape 0/10/20ms 三 lane 全部 graceful cancel → 返回 REPL → exit 0
- **直接证据**:
  - Diff: `InteractiveComposerEventKind.CANCEL_ACTIVE` → `RUNNING_KEY_ACTION` (`composer.py:167`)
  - Diff: `InteractiveCancelSource` enum 删除 (`composer.py:173-178`)
  - Diff: `_ActiveTurnCloseout` 新增 `wait_accepted_then_cancel` 跨 barrier 等待 (`session_execution.py:245-276`)
  - Bundle evidence: `f03-matrix.json` preaccept Escape 0ms/10ms/20ms 全部 exit 0, terminal restored
- **影响**: 无 — 符合 oracle
- **建议改法和验证点**: 无需修改
- **修复风险（低/中/高）**: 无
- **严重程度（低/中/高/严重）**: PASS

#### 005-PASS-F03-double-ctrl-c-self-exit-130

- **入口/函数**: `dayu/cli/session_execution.py:_ActiveTurnCloseout.request_cancel`
- **文件(行号)**: `dayu/cli/session_execution.py:233-243`
- **输入场景**: interactive Run 期间连续两次 Ctrl+C
- **实际分支**: 第一次 → `CANCEL_REQUESTED`; 第二次 → `EXIT_AFTER_CANCEL` → graceful closeout 完成后 exit 130
- **预期行为**: Oracle `interactive.12-running-ctrl-c-graceful-closeout` expected: "连续 Ctrl+C 表达取消完成后退出，不升级为 OS 级强制终止; CLI 等待 Host Run/Attempt 持久化为 terminal cancelled 后 exit 130"
- **实际行为**: double POSIX SIGINT 三条 lane 全部 exit 130, exactly one CANCEL_REQUESTED, exactly one RUN_CANCELLED, terminal restored
- **直接证据**:
  - Diff: `_LocalCancelIntent` enum: `NONE → CANCEL_REQUESTED → EXIT_AFTER_CANCEL` (`session_execution.py:175-179`)
  - Diff: `request_cancel` exit_after 升级逻辑 (`session_execution.py:238-243`)
  - Bundle evidence: `f03-matrix.json` double_posix_sigint 全部 cancel_requested=1, run_cancelled=1, exit_code=130
  - Bundle evidence: provider-wait lane attempt_terminal_status="cancelled", canonical_attempt_cancelled_events=1
  - Bundle evidence: tool-execution lane attempt_terminal_status="suspended" (等待态), canonical_attempt_cancelled_events=0 (由唯一 RUN_CANCELLED 收口，不伪造第二个 ATTEMPT_CANCELLED)
- **影响**: 无 — 符合 oracle
- **建议改法和验证点**: 无需修改
- **修复风险（低/中/高）**: 无
- **严重程度（低/中/高/严重）**: PASS

**Adversarial check for F03**: 通过。证据来自 (a) OS-level exit code 130, (b) Host EventLog canonical CANCEL_REQUESTED/RUN_CANCELLED count, (c) terminal flag restoration check (lflag_xor=0). 未用 CLI 终端文案替代 durable truth。tool-await lane 的 `canonical_attempt_cancelled_events=0` 经 owner analysis 确认是因为等待态由唯一 RUN_CANCELLED 收口，不写第二个 ATTEMPT_CANCELLED——这是正确的 owner 级语义，不是遗漏。

---

### F04 — READ_ONLY / fresh attachment

#### 006-PASS-F04-read-only-fresh-attachment-retry

- **入口/函数**: `dayu/cli/session_execution.py` (interactive outer driver)
- **文件(行号)**: `dayu/cli/session_execution.py:111-115` (新增 `_INTERACTIVE_READ_ONLY_MESSAGE`), `session_execution.py` 多处 (fresh attach retry 逻辑)
- **输入场景**: 同一 Session 两个 attachment，B 在 A 活跃时尝试 submit
- **实际分支**: B 收到 READ_ONLY rejection → 显示只读提示 → 保留 REPL 且 draft 不丢失 → A 退出后 B 关闭旧 attachment → fresh attach → submit 成功
- **预期行为**: Oracle `interactive.15-session-attachment-access` expected: "READ_ONLY 客户端提交 follow-up 时显示明确只读失败，但保留 REPL; 原 writer 释放后 CLI 可关闭旧 READ_ONLY attachment 并 fresh attach 重新竞争 READ_WRITE"
- **实际行为**: 两次 READ_ONLY rejection, Run count 均为 0; B 保持存活; A succeeded 并 exit 0 后 B fresh attach 成功; 最终恰好 2 个 succeeded Runs
- **直接证据**:
  - Diff: `_INTERACTIVE_READ_ONLY_MESSAGE` 常量 (`session_execution.py:114-116`)
  - Bundle evidence: `f04-matrix.json` read_only_rejections=2, runs_during_read_only=[0,0], final_run_count=2
  - Bundle evidence: 两个 attachment 的 request_id 不同 (`0455233a...` vs `821b3004...`)，证明是 fresh attach 而非原地升级
- **影响**: 无 — 符合 oracle
- **建议改法和验证点**: 无需修改
- **修复风险（低/中/高）**: 无
- **严重程度（低/中/高/严重）**: PASS

**Adversarial check**: 通过。证据来自 (a) 真实 PTY timeline 显示两个独立 attachment 进程, (b) request_id 差异证明 fresh attach, (c) Run count 来自 EventLog durable truth 而非 CLI 自报。

---

### F05 — effective tools / real chain

#### 007-PASS-F05-preprocess-not-registered

- **入口/函数**: `dayu/config/prompts/manifests/interactive.json`
- **文件(行号)**: `dayu/config/prompts/manifests/interactive.json` (diff 显示删除 1 行 — `start_fins_preprocess` 的 tag)
- **输入场景**: interactive 场景启动
- **实际分支**: interactive scene 的 effective tool schema 不含 `start_fins_preprocess`
- **预期行为**: Oracle `interactive.28-tool-registration-boundary` expected: "interactive 可以注册财报读取与下载工具，但 effective tool set 不向 Host 注册 start_fins_preprocess"
- **实际行为**: effective_tool_schema_names 含 `start_fins_download`，不含 `start_fins_preprocess`; preprocess_present=false
- **直接证据**:
  - Diff: `dayu/config/prompts/manifests/interactive.json` 减少 1 行 (移除 preprocess tag)
  - Bundle evidence: `f05-matrix.json` preprocess_present=false, effective_tool_schema_names 共 13 个工具不含 start_fins_preprocess
  - Bundle evidence: succeeded_run_count=3, model="mimo-v2.5-pro", provider="mimo"
- **影响**: 无 — 符合 oracle
- **建议改法和验证点**: 无需修改
- **修复风险（低/中/高）**: 无
- **严重程度（低/中/高/严重）**: PASS

#### 008-PASS-F05-real-tool-chain-evidence

- **入口/函数**: 真实 Mimo runner → Fins tools
- **文件(行号)**: 无代码变更（属于 integration evidence）
- **输入场景**: interactive 中请求下载 MSFT 财报
- **实际分支**: `start_fins_download -> list_documents -> get_document_sections -> read_section` 真实工具链
- **预期行为**: Oracle `interactive.24-memory-and-grounded-tool-evidence` expected: "Tool Trace 必须同时提供实际 tool call request 与 response"
- **实际行为**: 3 个 succeeded Runs, 生成 165 个 portfolio 文件
- **直接证据**:
  - Bundle evidence: `f05-matrix.json` canonical_requested_tool_names 含完整调用链
  - Bundle evidence: `evidence/generated-artifacts/f05-portfolio-manifest.json` 记录 165 个文件路径、大小与 SHA-256
  - Bundle evidence: owner projections 交叉验证 EventLog/Tool Trace 的 request/response 配对
- **影响**: 无 — 符合 oracle
- **建议改法和验证点**: 无需修改
- **修复风险（低/中/高）**: 无
- **严重程度（低/中/高/严重）**: PASS

**Adversarial check for F05**: 通过。证据来自 (a) Host effective tool schema snapshot (owner truth), (b) Tool Trace 的 canonical request/response (owner truth), (c) 真实文件系统生成物 SHA-256 (独立可验证). 未用 CLI 终端文案替代工具成功真源。

---

### F06 — dispatch manifest terminal ownership

#### 009-PASS-F06-context-governance-resolved-semantics

- **入口/函数**: `dayu/host/dispatch.py` (runner-call manifest construction)
- **文件(行号)**: `dayu/host/dispatch.py` (trigger reason 字段)
- **输入场景**: compact 成功或 compaction failure fallback 后的首次普通 dispatch
- **实际分支**: `runner_call_trigger_reason` 统一为 `context_governance_resolved`
- **预期行为**: Oracle `interactive.26-context-compaction-single-flight-and-success` expected: "runner_call_trigger_reason=context_governance_resolved 表示 context governance 已经收口并允许下一次 dispatch，不单独宣称 compact 成功"
- **实际行为**: 成功 lane 3 个 post-compact manifest 全部 `context_governance_resolved`; 失败 lane 1 个 post-fallback manifest 也是 `context_governance_resolved`
- **直接证据**:
  - Diff: `dayu/host/dispatch.py` trigger reason 字段从旧名改为 `context_governance_resolved`
  - Bundle evidence: `f06-matrix.json` success lane 3 个 manifest 全部 trigger=`context_governance_resolved`, 对应 terminal 分别为 3 个 `CONTEXT_COMPACTED`
  - Bundle evidence: failure lane 1 个 manifest trigger=`context_governance_resolved`, terminal=`CONTEXT_COMPACTION_FAILED`
  - Bundle evidence: `outcome_owner` 明确声明为 "canonical Context Governance terminal event"
- **影响**: 无 — 符合 oracle
- **建议改法和验证点**: 无需修改
- **修复风险（低/中/高）**: 无
- **严重程度（低/中/高/严重）**: PASS

**Adversarial check for F06**: 通过。证据同时包含 (a) 成功 lane 的 trigger=context_governance_resolved + terminal=CONTEXT_COMPACTED (证明 trigger 不承诺成功), (b) 失败 lane 的 trigger=context_governance_resolved + terminal=CONTEXT_COMPACTION_FAILED (证明 trigger 不伪装成功). `outcome_owner` 字段显式声明 canonical terminal event 是 outcome 的真源——这是正确的 owner 分离。

---

### F07 — strict v2 compaction / repair / continuity

#### 010-PASS-F07-strict-v2-candidate-accept

- **入口/函数**: `dayu/host/compaction.py:CompactAcceptedTruthV2`, `dayu/host/compaction.py:CompactRepairFeedbackV2`
- **文件(行号)**: `dayu/host/compaction.py:1-95` (模块重写)
- **输入场景**: LLM compactor 返回 candidate
- **实际分支**: Context Governance accept barrier 执行 strict JSON/source kind/coverage/duplicate/contradiction/cap 校验 → 形成唯一 `CompactAcceptedTruthV2` 或产生 bounded rejection + `CompactRepairFeedbackV2`
- **预期行为**: Oracle `interactive.29-compactor-output-accept-repair-fallback` expected: "Host Context Governance accept barrier 是 compact candidate 有效性的唯一 owner; 无效 proposal 形成 bounded attempt rejection; whole-candidate repair 完整重产 candidate"
- **实际行为**: 成功 lane 3 个 accepted compact; 第三个 compact 先有一个 real invalid candidate, attempt 2 repair 成功; 失败 lane 2 次 rejected, repairable=false, 恰好一个 CONTEXT_COMPACTION_FAILED
- **直接证据**:
  - Diff: `COMPACT_INPUT_SCHEMA_V2 = "dayu.context_compaction.input.v2"` (`compaction.py:28`)
  - Diff: `COMPACT_OUTPUT_SCHEMA_V2 = "dayu.context_compaction.output.v2"` (`compaction.py:31`)
  - Diff: 新增 `CompactSourceKindV2` enum — 8 种 bounded source kind (`compaction.py:59-72`)
  - Diff: 新增 `CompactSemanticSectionV2` enum — 5 种 coverage section (`compaction.py:75-81`)
  - Diff: `conversation_compaction_user.md` 完全重写 — 输入 schema 从 v1 变为 v2, 输出字段从 v1 变为 v2, 所有字段自足说明
  - Bundle evidence: `f07-matrix.json` real_successful_compacts 含 3 个 entry, 第三个 accepted_attempt_number=2 (repair)
  - Bundle evidence: real_invalid_bounded_repair_exhaust: 2 rejected, 1 CONTEXT_COMPACTION_FAILED, fallback_action=dispatch
  - Bundle evidence: 3 个 compact artifact 文件 (SHA-256 命名, 大小 7240-36802 bytes)
- **影响**: 无 — 符合 oracle
- **建议改法和验证点**: 无需修改
- **修复风险（低/中/高）**: 无
- **严重程度（低/中/高/严重）**: PASS

#### 011-PASS-F07-post-compact-continuity

- **入口/函数**: 真实 Mimo runner → Memory/RunInput
- **文件(行号)**: 无代码变更（属于 integration evidence）
- **输入场景**: compact 后的 follow-up 问题
- **实际分支**: 第一轮 follow-up 同时保留 OLD_AAPL_NET_SALES (数值/单位/期间/来源) + NEW_SCOPE=OPERATING_MARGIN; 第二轮无工具复述 OLD_AAPL_NET_SALES; 第三轮真实调用 list_documents/get_financial_statement/read_section, 按 NEW_SCOPE 得到 31.97%
- **预期行为**: Oracle `interactive.26-context-compaction-single-flight-and-success` expected: "成功 compact 后至少两个真实 follow-up 必须分别证明 compact 前财报事实的连续性，以及新口径下按需调用真实财报工具取得新证据"
- **实际行为**: 三轮 follow-up 满足要求
- **直接证据**:
  - Bundle evidence: `f07-matrix.json` post_compact_followups 含 3 个 entry
  - Followup 1: user_input 要求记住 NEW_SCOPE + 确认保留 OLD_AAPL_NET_SALES → succeeded, final_answer 含两条信息
  - Followup 2: user_input 要求复述 OLD_AAPL_NET_SALES → succeeded, final_answer 含 416,161/百万美元/FY2025/完整 SEC 来源
  - Followup 3: user_input 要求按 NEW_SCOPE 查询 operating margin → succeeded, tool_names=[list_documents, get_financial_statement, read_section], final_answer 含 31.97%
- **影响**: 无 — 符合 oracle
- **建议改法和验证点**: 无需修改
- **修复风险（低/中/高）**: 无
- **严重程度（低/中/高/严重）**: PASS

#### 012-PASS-F07-s7-deterministic-owner-matrix

- **入口/函数**: Host owner-level tests (15-file matrix)
- **文件(行号)**: `tests/host/test_compaction_contract.py`, `tests/host/test_llm_compaction.py`, `tests/host/test_compaction_operation.py` 等
- **输入场景**: deterministic malformed candidate 注入 → Host accept barrier 拒绝
- **实际分支**: 711 passed, 1 skipped
- **预期行为**: Oracle `interactive.29-compactor-output-accept-repair-fallback` expected: "全空、diagnostics-only、无法证明 semantic coverage、超过同源 section cap、unknown/duplicate JSON key 或重复 semantic item 的 candidate 不得被接受"
- **实际行为**: 711 个 owner-level test 全部通过
- **直接证据**:
  - Bundle evidence: `f07-matrix.json` deterministic_owner_matrix: "711 passed, 1 skipped"
  - Bundle evidence: `validation-results.json` s7_owner_matrix: 711 passed, 1 skipped
  - 1 skipped 的 root cause: `test_reactive_compact_request_uses_latest_previous_view` 的 0.01s LLM lane acquire timeout, 串行重跑通过, 非产品 bug
- **影响**: 无 — 符合 oracle
- **建议改法和验证点**: 无需修改
- **修复风险（低/中/高）**: 无
- **严重程度（低/中/高/严重）**: PASS

**Adversarial check for F07**: 通过。证据来自 (a) S7 deterministic owner matrix (malformed candidates + Host accept barrier 的 owner-level 测试), (b) 真实 Mimo invalid repair exhaust 的 EventLog/Host index, (c) 真实 compact artifacts (文件内容可独立校验), (d) post-compact Memory/RunInput/Tool Trace 交叉核对. 未用 mock/fake provider 形成 real-evidence claim; deterministic matrix 的 policy 明确声明 "malformed candidates are owner-test evidence only; full-real claims use Mimo"。

---

### 证据链完整性

#### 013-PASS-bundle-integrity-and-secret-scan

- **入口/函数**: CI bundle sealing pipeline
- **文件(行号)**: `bundle/SHA256SUMS`, `bundle/bundle-digest.txt`, `bundle/validation-results.json`
- **输入场景**: 442 个 seal 前文件 → secret scan → SHA256SUMS → digest → 只读封存
- **实际分支**: 所有校验通过
- **预期行为**: Target commit = `9fec164715bc6af7a4a7d7446cb45d49593ec64f`, digest 匹配, secret scan 零 exact credential, writable paths=0
- **实际行为**:
  - SHA256SUMS 443 entries, `sha256sum -c` 通过
  - bundle-digest.txt = SHA256SUMS digest = `7a80d9bcfb97bb7c8a80df8d2f10016d6f98577e01294f540a7ba2d9cea33b72`
  - Secret scan: exact credential=0, 未脱敏 bearer=0, structured secret assignment=0, 保留 41 个可审计 redaction placeholder
  - Python mode-bit 复核: writable paths=0
  - Frozen hashes 与 run-manifest.json 完全一致
- **直接证据**:
  - `bundle/bundle-digest.txt` 内容: `7a80d9bcfb97bb7c8a80df8d2f10016d6f98577e01294f540a7ba2d9cea33b72`
  - `bundle/run-manifest.json`: `frozen_hashes` 与 Codex review 第 2 节完全一致
  - `bundle/validation-results.json`: status="pass", target_diff_check="pass"
- **影响**: 无 — bundle 完整性可验证
- **建议改法和验证点**: 无需修改
- **修复风险（低/中/高）**: 无
- **严重程度（低/中/高/严重）**: PASS

#### 014-PASS-frozen-inputs-consistency

- **入口/函数**: `docs/cli_ci_oracles.json`, `docs/cli_ci_scenarios.json`, `docs/cli_ci.md`
- **文件(行号)**: frozen docs
- **输入场景**: bundle 中 frozen hashes 与 target commit 上实际文件对比
- **实际分支**: 三个 frozen hash 完全一致
- **直接证据**:
  - `run-manifest.json` frozen_hashes:
    - `docs/cli_ci_oracles.json`: `f9972d943ac8ae8d79ebbe7114c1305b7af2933729575d1407fcb6d4d05b07f4`
    - `docs/cli_ci_scenarios.json`: `7f283b039dc02ce686bb134c748e5c98039af2029eb090dbdaf6dcf4fe5e8cef`
    - `docs/cli_ci.md`: `a241182d4d09e8843ea647947777bc7f6f71c5532fa148e2abb87ede3e748b82`
  - Codex review 第 2 节 frozen inputs table 完全一致
- **影响**: 无
- **建议改法和验证点**: 无需修改
- **修复风险（低/中/高）**: 无
- **严重程度（低/中/高/严重）**: PASS

---

### README 与未提交文件

#### 015-PASS-README-changes-accurate

- **入口/函数**: `README.md`, `dayu/config/README.md`, `dayu/host/README.md`, `tests/README.md` (未提交)
- **文件(行号)**: 四个 README 的未提交 diff
- **输入场景**: S8 实现完成后对各 README 的更新
- **实际分支**: 各 README 按其自身职责边界更新
- **实际行为**:
  - `README.md`: 移除 `--config` 参数文档; 修正 "全局 `--base` / `--config`" → "工作区路径参数"; 新增 interactive 预处理能力说明; session resume 明确配置读取来源
  - `dayu/config/README.md`: 更新 scene/tag 说明反映 interactive 不注册 preprocess; 新增 v2 compactor input/output schema 说明
  - `dayu/host/README.md`: 新增 v2 accept barrier/repair/fallback 说明; 明确 `context_governance_resolved` 语义; Conversation Memory 更新为 v2 candidate 消费
  - `tests/README.md`: 新增 F01-F05 owner coverage 说明; 新增 F06-F07 Context Governance conformance 说明; 强调 real-evidence 要求
- **直接证据**:
  - `git diff` 输出的四个 README 变更
  - 变更内容与实现 diff 一致: `arg_parsing.py` 删除 `--config` → README 移除 `--config` 文档
  - 变更内容与实现 diff 一致: `compaction.py` v2 schema → README 描述 v2 accept barrier
  - 变更内容与实现 diff 一致: `interactive.json` manifest 减少 preprocess tag → README 说明 interactive 不注册 preprocess
- **影响**: 无 — README 准确反映实现
- **建议改法和验证点**: 无需修改
- **修复风险（低/中/高）**: 无
- **严重程度（低/中/高/严重）**: PASS

**Adversarial check for README**: 通过。README 变更 (a) 不超出各自职责边界, (b) 内容与实现 diff 可逐项对应, (c) 未编造未实现的能力, (d) `dayu/README.md` 和 `dayu/engine/README.md` 按 Codex review 第 7 节判断不需更新——该判断与 CLAUDE.md 的 README 更新触发规则一致。

---

### 实现质量观察（非 Finding）

以下项目经走读确认正确，不构成 finding，仅记录为观察：

1. **State machine ownership**: `_ActiveTurnCloseout` 的 `_LocalCancelIntent` 三态转换 (NONE → CANCEL_REQUESTED → EXIT_AFTER_CANCEL) 是单调不可逆的，第二次 Ctrl+C 不产生竞争 cancel owner。`request_cancel` 的 `exit_after` 参数只在 intent 非 NONE 时升级——设计正确。

2. **TCSANOW vs TCSAFLUSH**: `TtyRunningKeyMonitor` 从 `tty.setcbreak(fd)` (默认 TCSAFLUSH) 改为 `tty.setcbreak(fd, when=termios.TCSANOW)`——这确保 invocation 启动后、monitor 安装前到达的按键不被丢弃。这是正确的终端输入 owner 设计。

3. **Vt100Parser 集成**: `_read_loop` 从单字节读取改为 1024 字节 + `Vt100Parser` 增量解析 + `codecs.getincrementaldecoder("utf-8")`，正确地将终端输入序列的识别责任从应用层转移到 prompt_toolkit 的 VT100 parser（该 parser 是 POSIX 终端输入序列的 canonical owner）。

4. **Whole-candidate repair**: `conversation_compaction_user.md` 的重写将 v1 的字段级 patch 模式改为 v2 的完整 replacement candidate 模式，`CompactRepairFeedbackV2` 提供脱敏 validation 摘要——这与 oracle "不接受 patch 或旧 candidate 的局部沿用" 一致。

5. **v2 schema 自足性**: `dayu.context_compaction.input.v2` 和 `dayu.context_compaction.output.v2` 的所有字段在 prompt 中自足说明，不使用内部类型名、模块名或 "conforms to X schema" 的间接引用。符合 CLAUDE.md 的 LLM-facing 文本约束。

6. **三份历史失败 bundle**: 保留且未覆盖，digest 记录在新 bundle 中。这提供了完整的证据链可追溯性。

---

## Open Questions

无

## Residual Risk

1. **真实 provider 非确定性**: 真实 Mimo `mimo-v2.5-pro` 的输出具有通常的模型非确定性。本轮同时具备 deterministic owner matrix (711 tests) + 真实 invalid/exhaust + 真实 accepted repair + 真实 artifact/Memory/Tool follow-up 的完整 conjunction，风险已充分降低。

2. **S7 matrix 1 skipped**: `test_reactive_compact_request_uses_latest_previous_view` 的 0.01s LLM lane acquire timeout 在首次并发执行时出现，串行重跑通过。该 timeout 分类为 "non-governing test-environment interference"，但若 CI 环境负载持续升高，可能在其他测试中重现。

3. **未提交 README 变更**: 四个 README 的变更尚未 commit。若后续修改 diff 与本 review 所审查的版本不同，需重新审查。

---

## READY-FOR-CONTROLLER-ADJUDICATION

F01-F07 全部 PASS。

- F01: `--config` 从 parser、namespace、reject 函数、help output 四层完全移除
- F02: 显式无效 editor (missing/nonexec/spawn-failure) 三 lane 全部保留 draft、零 Run/Attempt、terminal 恢复
- F03: Escape sequence disambiguation (Vt100Parser)、pre-accept Escape graceful cancel (cross-barrier)、双 Ctrl+C self-exit 130 全部符合 oracle
- F04: READ_ONLY rejection 保留 REPL、fresh attach retry 成功、不同 request_id 证明非原地升级
- F05: interactive 不注册 `start_fins_preprocess`、真实 tool chain evidence 完整
- F06: `context_governance_resolved` 只表达 dispatch permit，不复制 compact outcome
- F07: strict v2 candidate accept/repair/fallback、711-test deterministic matrix、3 个真实 compact artifact、post-compact continuity 全部验证
- Bundle integrity: SHA256SUMS/digest/secret scan/只读封存全部通过
- README 准确性: 四个 README 变更与实现 diff 逐项对应
