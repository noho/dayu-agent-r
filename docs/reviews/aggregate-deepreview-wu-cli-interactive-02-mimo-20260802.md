# Aggregate Deep Review: wu-cli-interactive-02-conformance-fixes

## Scope

- Mode: current changes
- Branch: `codex/interactive-oracle`
- Base: `main`
- Output file: `docs/reviews/aggregate-deepreview-wu-cli-interactive-02-mimo-20260802.md`
- Included scope: 171 files changed (+28658/-4813)，覆盖 CLI (session_execution, composer, commands, identity)、Host (compaction_terminal, dispatch, open_host, recovery, context_events, llm_compaction, proactive_compaction)、Engine (contracts, agent)、Tests (50+ 文件)、Docs (cli_ci, oracles, scenarios, design, README)。
- Excluded scope: AgentDS review artifacts（按用户要求不读取）、generated/vendor/build files。
- Parallel review coverage: 4 个 subagent 并行审查：
  - CLI session execution（session_execution.py, composer.py, commands, identity）
  - Host state machines（compaction_terminal, dispatch, open_host, recovery, context_events）
  - Engine contracts & identity（runner_identity, agent_run, engine_events, agent）
  - Tests/docs/scenarios（oracles.json, scenarios.json, design docs, README, tests）

## 门控历史

本 review 覆盖的提交链：

```
ae6bb96f docs(cli): complete interactive calibration matrix
cc5c9d57 docs(cli): adjudicate interactive oracle
34127db4 gateflow: accept plan for wu-cli-interactive-02-conformance-fixes
d210444f gateflow: accept wu-cli-interactive-02 S1
057b5b9b gateflow: accept wu-cli-interactive-02 S2
eadee409 gateflow: accept wu-cli-interactive-02 S3
331d38dc gateflow: accept wu-cli-interactive-02 S4
ec9342ed gateflow: amend S5 plan for required identity closure
e7f578dc gateflow: close S5 durable builder plan closure
ce7ef846 gateflow: close S5 utils identity closure
9ad45cf7 host: preserve compactor response identity
cf041c2c gateflow: accept wu-cli-interactive-02 S6
```

## Findings

### 01-未修复-高-interactive oracle 已 accepted 但 scenarios registry 零覆盖

- **入口/函数**: `docs/cli_ci_oracles.json` → `cli.interactive.core-execution` oracle，`docs/cli_ci_scenarios.json` → scenarios list
- **文件(行号)**: `docs/cli_ci_oracles.json`（oracle `cli.interactive.core-execution` status=accepted），`docs/cli_ci_scenarios.json`（442 scenarios，0 个 interactive）
- **输入场景**: 任何基于 scenarios registry 判断 interactive readiness 的自动化或人工审计
- **实际分支**: oracle status=`accepted`，`scenario_refs=[]`（空数组）；scenarios.json 中无任何 interactive 前缀条目
- **预期行为**: `cli_ci.md` 第 4.6 节 readiness condition #2 要求 "scenario registry 对每个 mandatory obligation 都有 accepted coverage claim"。oracle accepted 意味着 predicates 已冻结，对应 scenarios 应已写入 registry
- **实际行为**: oracle 已 accepted 但 scenarios registry 中零 interactive 条目。`readiness_proof` 无 interactive section，`ready_command_scopes` 只含 `["init", "prompt"]`，`calibration_command_scopes` 包含 `"interactive"` 但无对应 proof
- **直接证据**: `python3 -c "import json; d=json.load(open('docs/cli_ci_oracles.json')); o=[x for x in d['oracles'] if x.get('oracle_id')=='cli.interactive.core-execution'][0]; print(o['status'], o.get('observed_behavior',{}).get('scenario_refs',[]))"` → `accepted []`；`python3 -c "import json; d=json.load(open('docs/cli_ci_scenarios.json')); print(len([s for s in d['scenarios'] if 'interactive' in str(s.get('id',''))]))"` → `0`
- **影响**: oracle 声称的 predicates 无法被 scenarios 验证；readiness proof 无法覆盖 interactive scope；任何基于 scenarios registry 判断 interactive readiness 的自动化都会误判为"未开始"
- **建议改法和验证点**: 在 `cli_ci_scenarios.json` 中为 `cli.interactive.core-execution` oracle 的每个 predicate 写入对应 scenario entry；或明确记录 interactive scenarios 写入 registry 的时间点和 WU 归属
- **修复风险（低/中/高）**: 中（需要决定 scenarios 写入时机，可能需要单独 WU）
- **严重程度（低/中/高/严重）**: 高

### 02-未修复-中-terminal guard INVALID_MULTIPLE fail-closed 散落在调用方而非 guard 自身

- **入口/函数**: `dayu/host/dispatch.py` 中 4 个 governance path 的 terminal guard 检查
- **文件(行号)**: `dayu/host/dispatch.py`（行 2206-2220、2424-2436、3195-3209、3268-3280），`dayu/host/compaction_terminal.py`（行 164-176）
- **输入场景**: 新增 compaction governance 路径时
- **实际分支**: `begin_compaction_terminal_commit_in_transaction` 返回 `CompactionTerminalClosed(disposition=INVALID_MULTIPLE)`，调用方必须显式检查 disposition 并 raise
- **预期行为**: fail-closed 语义应收拢到 guard owner 模块，`INVALID_MULTIPLE` 时直接 raise 而非返回可忽略的 disposition
- **实际行为**: 4 个调用方各自重复相同的 `if disposition is INVALID_MULTIPLE: raise HostDurableError(...)` 模式
- **直接证据**: `grep -n 'INVALID_MULTIPLE' dayu/host/dispatch.py` → 4 处 `is CompactionOperationTerminalDisposition.INVALID_MULTIPLE` 检查；`dayu/host/compaction_terminal.py` 行 164-176 返回 `CompactionTerminalClosed` 而非 raise
- **影响**: 当前所有调用点均正确处理。但如果新增调用点忘记检查 `INVALID_MULTIPLE`，guard 会静默返回"已关闭"而非抛出异常，导致多 terminal 历史被掩盖
- **建议改法和验证点**: 将 `INVALID_MULTIPLE` 的 raise 收拢到 `begin_compaction_terminal_commit_in_transaction` 内部，或提供 `require_compaction_terminal_commit_in_transaction` wrapper
- **修复风险（低/中/高）**: 低（纯重构，不改变运行时行为）
- **严重程度（低/中/高/严重）**: 中

### 03-未修复-中-readiness_proof mandatory/covered counts 为 None

- **入口/函数**: `docs/cli_ci_scenarios.json` → `readiness_proof`
- **文件(行号)**: `docs/cli_ci_scenarios.json`（readiness_proof.prompt/init 段）
- **输入场景**: 人工或自动化审计 readiness proof 完整性
- **实际分支**: `prompt.mandatory_count = None`，`prompt.covered_count = None`，`init.mandatory_count = None`，`init.covered_count = None`
- **预期行为**: `cli_ci.md` 第 4.6 节要求 readiness proof 记录 mandatory/covered/gap counts
- **实际行为**: proof 只有 `gap_count=0` 和 `validation_result=ready`，mandatory 和 covered 数量为 None，无法独立审计
- **直接证据**: `python3 -c "import json; d=json.load(open('docs/cli_ci_scenarios.json')); rp=d['readiness_proof']; print(rp['prompt']['mandatory_count'], rp['prompt']['covered_count'])"` → `None None`
- **影响**: readiness proof 不可独立审计；无法从 proof 中复核实际 mandatory obligation 总数和 covered 数量
- **建议改法和验证点**: 补齐 mandatory_count 和 covered_count 字段值
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 04-未修复-中-I0554 oracle-scenario refs 不可双向解析

- **入口/函数**: `docs/cli_ci_oracles.json` → `interactive.27-success-requires-final-answer` predicate
- **文件(行号)**: `docs/cli_ci_oracles.json`（interactive.27 predicate），`docs/cli_ci_scenarios.json`（无 I0554 scenario）
- **输入场景**: 自动化 scenario-oracle 交叉引用验证
- **实际分支**: predicate 声称 "I0554 证明 public contract 无法产生 succeeded/no-final"，接受 "owner-level static proof closure"
- **预期行为**: oracle 的 `scenario_refs` 应可双向解析到 scenarios registry 中的对应条目
- **实际行为**: `scenario_refs=[]`，scenarios registry 中无 I0554 相关条目。用户已接受 static closure 方式，但 refs 不可双向解析
- **直接证据**: oracle `interactive.27` 的 `scenario_refs` 为空；scenarios registry 中无 I0554/succeeded/no-final 条目
- **影响**: 不阻塞（用户已明确接受 static closure），但 oracle-scenario 双向引用完整性条件不满足
- **建议改法和验证点**: 在 scenarios registry 中为 static proof closure 添加对应 entry（标记为 `static_proof` 类型），或在 oracle 中明确标注 "scenario_refs intentionally empty for static closure"
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 05-未修复-中-_validate_non_empty_text 错误消息误标 owner

- **入口/函数**: `dayu/engine/contracts/runner_identity.py` → `_validate_non_empty_text`
- **文件(行号)**: `dayu/engine/contracts/runner_identity.py`（行 240-250）
- **输入场景**: `SuccessfulRunnerResponseIdentity` 构造时 `effective_provider` 或 `effective_model` 为空
- **实际分支**: `raise ValueError(f"RunnerRequestIdentity.{field_name} must be non-empty")`
- **预期行为**: 错误消息应标注实际调用方类型名（`SuccessfulRunnerResponseIdentity.effective_provider`）
- **实际行为**: 错误消息硬编码 `RunnerRequestIdentity` 前缀，但该函数同时被 `SuccessfulRunnerResponseIdentity.__post_init__`（行 119-120）调用
- **直接证据**: 行 250: `raise ValueError(f"RunnerRequestIdentity.{field_name} must be non-empty")`；行 119: `_validate_non_empty_text("effective_provider", self.effective_provider)`（在 `SuccessfulRunnerResponseIdentity.__post_init__` 中）
- **影响**: 调试时错误消息误导开发者认为问题出在 `RunnerRequestIdentity` 而非 `SuccessfulRunnerResponseIdentity`
- **建议改法和验证点**: 将 `_validate_non_empty_text` 改为接受 `owner_name` 参数，或在各 `__post_init__` 中使用独立的校验函数
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 06-未修复-低-中-_TerminalPostCommitCoordinator.close() drain barrier 可能丢失最后几个 terminal notice

- **入口/函数**: `dayu/host/open_host.py` → `_TerminalPostCommitCoordinator.close()`
- **文件(行号)**: `dayu/host/open_host.py`（行 465-481）
- **输入场景**: close 期间通过 `call_soon_threadsafe` 排入的 `notify_terminal_post_commit` callback
- **实际分支**: `call_soon(barrier.set_result)` + `await barrier` 只保证 barrier 在下一个 event loop iteration 被 resolve
- **预期行为**: close 前所有已排队的 terminal notice callback 应被执行
- **实际行为**: `call_soon` 不能保证 `call_soon_threadsafe` 排入的 callback 都已执行；`_closing` 标志位设置后，后续 notice 被静默丢弃
- **直接证据**: 行 467-470: `self._loop.call_soon(barrier.set_result, None); await barrier`；行 480: `if self._closing or self._closed: return`
- **影响**: close 期间最后几个 terminal notice 可能丢失，导致 Session Event Delivery 瞬态 watermark 不完整。durable reconciliation 在下次 watch 时会补偿
- **建议改法和验证点**: 添加注释说明 close 期间 notice 丢失的恢复路径；或在 close 中增加 drain loop 等待所有 pending callback
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低-中

### 07-未修复-低-dead code：resolve_explicit_config_dir 仍被导出

- **入口/函数**: `dayu/cli/agent_entrypoint.py` → `resolve_explicit_config_dir`
- **文件(行号)**: `dayu/cli/agent_entrypoint.py`（行 201-233, 325-333）
- **输入场景**: CLI 命令调用
- **实际分支**: prompt/interactive 已改为 `command_common_parent`（不含 `--config`），`resolve_explicit_config_dir` 不再被任何 CLI 命令调用
- **预期行为**: F01 清理应移除所有 prompt/interactive 对 `--config` 的引用路径
- **实际行为**: `resolve_explicit_config_dir` 仍导出在 `__all__` 中，未被 CLI 层调用
- **直接证据**: `__all__` 中包含 `resolve_explicit_config_dir`；grep 确认无 CLI 命令调用
- **影响**: 零运行时影响。可能属于 F01 清理不完整
- **建议改法和验证点**: 确认是否为其他调用方保留；如无，从 `__all__` 移除
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 08-未修复-低-dead code：InteractiveComposerCompletionResult 类型别名

- **入口/函数**: `dayu/cli/session_execution.py` → 模块级类型别名
- **文件(行号)**: `dayu/cli/session_execution.py`（行 1480）
- **输入场景**: 无
- **实际分支**: 类型别名定义但未在任何函数签名或类型标注中引用
- **预期行为**: 无主类型别名应被清理
- **实际行为**: `InteractiveComposerCompletionResult` 定义但未使用
- **直接证据**: 行 1480 定义；grep 确认无引用
- **影响**: 零运行时影响
- **建议改法和验证点**: 移除未使用的类型别名
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

1. **interactive scenarios 写入 registry 的时间点**: oracle 已 accepted，observed_behavior 中有真实运行记录，但 scenarios registry 中零 interactive 条目。按 `cli_ci.md` 第 4.6 节，第一轮 campaign 不能在 registry 仍为空时结束。interactive scenarios 写入是否需要单独 WU？
2. **Escape cancel 的 prompt_toolkit 序列解析 timeout**: standalone Escape 依赖 prompt_toolkit 内部 key sequence resolution timeout。极端场景（慢速 SSH 连接）下用户可能感觉到 Escape cancel 响应延迟。
3. **queued follow-up 退出后 Host 侧行为**: finally 块对非正常退出取消 queued.submit_task，但如果 queued follow-up 已被 Host durable accepted，本地取消不会取消 Host 侧 Run。G01 需要覆盖此路径。

## Residual Risk

1. **calibration 行为项 29 (compactor identity)**: F13 未修复前，compactor 成功 response 的实际 provider identity 无法从 durable evidence 证明。当前 CLI 变更不涉及此项，但它是 wu-cli-interactive-01 整体裁决的剩余阻塞项。
2. **G01-G07 覆盖缺口**: queued Run 退出/重连恢复（G01）、RUNNING crash/SIGKILL 恢复（G02）、durable steer 恢复（G03）等动态场景需要真实 Host 运行覆盖。
3. **prompt registry 中的 legacy config scenarios**: calibration C01 提到正式 prompt registry 有 17 条携带 `--config` 的 invocation 和 21 条 scenario 声明 config coverage。这些在当前 CLI 变更后会因 parse-time 拒绝而无法执行。
4. **`_pre_start_flights` 并发正确性依赖 asyncio 单线程模型**: 如果未来引入 multi-loop 或 threading 模型，dict 的并发访问需要额外同步。

## Positive Confirmations

以下关键设计和实现经审查确认正确：

1. **F06 (non-TTY pipe batch)**: `_run_interactive_non_tty_batch` 一次读取整个 stdin，只创建一个 Run，CRLF/CR 规范化正确。
2. **F07 (Escape cancel)**: Escape 通过 `active_phase` Condition filter 限制在 RUNNING/CANCELLING phase，CSI/Alt/bracketed-paste 不会触发误取消。测试 `test_complete_csi_alt_and_bracketed_paste_do_not_emit_cancel` 覆盖。
3. **F08 (Ctrl+C lifecycle)**: 第一次取消、第二次登记 exit-after-cancel、等待 canonical terminal 后 exit 130。Idle 双 Ctrl+C 使用 `input_revision` 防误退出。
4. **F09 (QUEUE 语义)**: composer 在 RUNNING phase 继续接受输入，Enter 提交创建 queued follow-up，sole queued slot 已占用时拒绝。
5. **F10 (recovery reclassification)**: `SessionAttachmentRecoveryScanner` 新增 `terminal_post_commit_port` 和 `recovery_owner_host_instance_id`，recovery 产生的 terminal 现在会推进 delivery watermark。
6. **F12 (per-Session single-flight)**: `_PreStartGovernanceFlight` + `_promotion_pending_session_ids` 正确实现 wake/reconcile signal 合并到唯一 governance single-flight。asyncio 单线程协作模型保证无 data race。
7. **F13 (identity taxonomy)**: `RunnerRequestIdentity` → `SuccessfulRunnerResponseIdentity` → `FinalAnswerData` → Host durable event 全链路贯通。compactor 路径 `attempt_id/execution_id` 必须为 None 的约束在三层均有校验。
8. **label 跨入口 alias**: `host_context.py` 统一为 `CLI_AGENT_SESSION_SCOPE="cli.agent"` + `cli_label_slot_key(label)`，prompt ↔ interactive 共享同一 Session。
9. **`--config` 清理**: prompt/interactive parser 已移除 `--config`，`_reject_disallowed_explicit_config` 在 parse-time 拒绝。
10. **CompactorProposalManifestReference**: frozen dataclass 将 proposal manifest 的 event id、payload ref、digest、operation id、attempt number、engine run id 绑定为不可变值对象，是正确的 schema 改进。
11. **无 secret 泄露**: oracles.json 和 scenarios.json 中未发现 API key、credential 等敏感信息。
12. **README 变更符合触发规则**: 所有 README 变更均符合 CLAUDE.md 定义的触发规则。
13. **测试覆盖**: compaction_terminal (829 行新文件)、runner_identity (104 行新文件)、dispatch_scheduler (+1320 行)、interactive_command (+2109 行) 等关键测试到位。
