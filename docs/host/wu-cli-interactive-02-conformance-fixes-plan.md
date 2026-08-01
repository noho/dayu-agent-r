# `wu-cli-interactive-02-conformance-fixes` 实现计划

## 0. Artifact 与 Gate 元数据

- Gate：`plan`
- Work unit：`wu-cli-interactive-02-conformance-fixes`
- Goal confirmation：用户已确认；本 artifact 不重新打开 goal 语义。
- 当前分支：`codex/interactive-oracle`
- 后续单一 PR base：`main`
- 当前分支前置提交：
  - `ae6bb96f docs(cli): complete interactive calibration matrix`
  - `cc5c9d57 docs(cli): adjudicate interactive oracle`
- 本次 accepted-finding fix preflight：目标 plan 与两份 review artifact 均为未跟踪文件，三者所有权由用户明确；本次只修改目标 plan。
- Plan review artifacts：
  - `docs/reviews/plan-review-20260801-143257.md`
  - `docs/reviews/plan-review-20260801-143623.md`
- 本计划 review target：Gateflow controller 的 re-review；re-review 通过前不得进入 accepted plan commit 或 implementation gate。
- 本计划范围：冻结修改项 F01-F13，按 S1-S6 在一个 PR 内完成；不得删减 F 项、改变 accepted oracle 语义或拆 PR。
- 本计划状态：`code-generation-ready / accepted-finding-fix-applied / awaiting-re-review`。
- Artifact path：`docs/host/wu-cli-interactive-02-conformance-fixes-plan.md`
- 当前 gate 的修改权限：只允许新增/修改本 plan artifact；不得修改生产代码、测试、其它文档，不得 commit、push 或创建 PR。
- 当前 Gateflow entry：`plan review -> fix` 中的 accepted-finding fix。
- Next entry point：`re-review`；本 Agent 子任务在 fix 与验证完成后把控制权交回 controller，由 controller 立即派发独立 re-review；整个 Gateflow 继续按固定 Gate Order 自动推进，不在普通 gate 停止。

## 1. Goal、动机与成功信号

### 1.1 Goal

让 `dayu-cli prompt`、`dayu-cli interactive` 及其直接 Host/Engine 治理链符合已经冻结的 `cli.prompt.core-execution@1` 与 `cli.interactive.core-execution@1` 语义，并修复 calibration 直接证明的 F01-F13：参数与 label 公共契约、TTY/non-TTY 输入、取消/type-ahead、fresh writer orphan recovery、compaction terminal/single-flight，以及成功 compactor response identity 的 durable 绑定。

### 1.2 动机是否成立

动机成立，且严重性没有被高估。根因证据均来自同源代码或 durable evidence，不是从 UI 现象反推：

1. F01/F02/F03/F04 是公开 parser/slot 真源与冻结 contract 直接不一致：prompt/interactive 共用含 `--config` 的 runtime parent，interactive 显式注册并消费 `--ticker`，同一 label 被写入 `cli.prompt.*` 与 `cli.interactive.*` 两个 durable slot namespace；`prompt.P37` 却声明了并未执行的 cross-command reuse。
2. F05-F09 的根因是 stdin 所有权分裂：输入态由 prompt_toolkit composer 读取，Run 中由 `TtyRunningKeyMonitor` 以单字节读取；后者看到首个 `0x1b` 就取消，无法区分 standalone Escape、CSI、Alt 或 bracketed paste，且 Run 中没有活跃 composer，因此 type-ahead 必然丢失。当前 non-TTY `input()` 又把普通换行误当多轮边界。
3. F10 的 scanner 已有 positive orphan proof、fixed watermark、bounded page、CAS 和 recovery dispatch limit；缺口只在 fresh RW attachment 于 30 秒阈值前完成一次固定 `now` scan 后，没有 attachment-owned delayed reclassification。
4. F11 的同 operation 双 terminal 由同源 EventLog 证明，且 invariant 必须覆盖所有 trigger：当前全仓仅 `dayu/host/dispatch.py` 的 proactive writer 与 `dayu/host/engine_ingest.py` 的 reactive writer 会追加 `CONTEXT_COMPACTED` / `CONTEXT_COMPACTION_FAILED`。proactive 已有“首次 invalid/exhausted failed 提交后，事务外 late result 再追加 `stale_compaction_result`”的直接证据；reactive `_execute_reactive_compaction()` 同样在 `await run_compaction_operation(...)` 后开新 write transaction，只校验 Run/input 状态就直接写 terminal，accepted 路径还会先写 compact artifact/descriptor。
5. reactive 的并发/幂等重入反例也来自同源代码：`_duplicate_engine_terminal_result()` 只能在初始 Engine candidate ingest transaction 对已提交 prefix/outcome 去重，不能保护两个已经取得同一 `_ReactiveCompactPending` 并在事务外运行的 outcome executor。若幂等 retry/crash-resume 或 callback 重入使两个 executor 分别得到 accepted/failed，它们可在第一个 outcome transaction 提交后、recovery start transaction 前都看到 `RECOVERING` + terminal source Attempt；当前没有 operation-terminal reread，第二个仍可写另一 terminal。SQLite write transaction 只会串行这两次提交，不会自动把第二次变成 loser；必须有同一 transaction-local terminal guard。
6. F12 的 wake promotion 与 periodic owned-session reconciliation 都直接取得 `SessionWorkLease` 后调用 `_run_queue_promotion_with_lease`；lease 是生命周期计数器而非互斥锁，所以同一 live RW Session 可以并发进入 pre-start governance。
7. F13 的 Engine `_IterationState` 同时持有 `RunnerRequestIdentity` 与 `RunnerDoneData.provider_request_id`，但 `_FinalDecision`、`FinalAnswerData`、`EngineRunOutcomeFinalAnswer` 逐层丢弃；Host compactor只能得到 candidate，无法将实际成功 response 与 operation/attempt/manifest/output 同源绑定。代码同时证明每个 Host `compaction_attempt_number` 都会重新调用 `prepare_compactor_proposal_run_input()` 构造一个新 `AgentRunRequest`；其 `run_id` 是该 attempt 的 `compactor_engine_run_id`，`attempt_id/execution_id` 为 `None`。只有同一 Engine request 内的 length continuation 递增 `runner_call_index`，且 Host compactor 对最终 `finish_reason=LENGTH` 明确 fail closed。Service 的配置 family 校验和调用前 manifest 都不能替代 response evidence。

### 1.3 成功信号

- F01-F13 每项均有 owner-level contract test；所有新增/修改生产文件单文件覆盖率不低于 80%。
- prompt/interactive help、parser inventory、typed command consumption 中不存在各自已移除参数；任何参数位置都不能让这些参数进入对应 Agent 执行。
- 相同 workspace+label 的 prompt/interactive 只解析到一个新 durable slot；旧 namespace 不读取、不迁移、不兼容。
- TTY 只有 composer 读取 stdin；non-TTY 从首 byte 到真实 EOF 只形成一个 draft、最多一个 Run。
- active Run 的 standalone Escape/Ctrl+C/Enter 行为分别稳定为 graceful cancel、cancel/exit-after-cancel、单个 `QUEUE` follow-up；完整 ESC-prefixed 输入不误取消，draft 跨 terminal 保留。
- fresh RW attach 在旧 owner heartbeat 变 stale 后自行重扫；只有 positive proof 才推进同一 Run 的 `ATTEMPT_LOST -> RUN_RECOVERING -> RUN_STARTED(recovery)`，最多一个 recovery Attempt/execution。
- 每个 compaction operation 无论 proactive/reactive trigger 都精确一个 canonical terminal；同一 live RW Session 精确一个 pre-start flight；wake/periodic 只形成合并信号。
- accepted 和有成功 provider response 的 rejected compactor attempt 均持久化安全 response identity；provider request id 缺失显式记为 `unavailable`，且无 endpoint、credential、header、secret。
- 受影响测试、集成测试、smoke、完整 pyright、JSON registry 校验和 secret/canary 检查通过。

## 2. Non-goals 与冻结边界

以下全部是硬边界，不得以“顺手修复”扩大：

- 不裁决或实现 G01-G07；尤其不以本 WU 宣称完成真实 queued reconnect、完整 crash matrix、steer recovery、真实财报 refresh、真实成功 compaction continuity campaign。
- 不新增 interactive 内 `resume`、`/clear`、`/new`、`/resume`；不新增隐藏 STEER gesture。现有 `session resume --mode interactive` 只随共享 label/removed parameter contract 做必要收敛，不扩展能力。
- 不改变 prompt 的 `--ticker`；不改变独立 download/upload/preprocess/process 命令的 ticker、输入、oracle 或业务流程。
- 不为 removed `--config`、removed interactive `--ticker`、旧 label namespace 或旧 compaction payload/schema 增加 accepted/compatibility scenario。
- 不读取、迁移或 re-export `cli.prompt.*` / `cli.interactive.*`；不兼容旧参数、旧 namespace、旧 schema、旧测试偶然行为。
- 不删除 periodic owned-session reconciliation；不把 `SessionWorkLease` 改造成 mutex；不引入 runtime/global/per-workspace 通用锁。
- 不引入通用 scheduler、通用 delayed-job、通用 recovery 或通用 event terminal framework；只实现本 work unit 的 Session pre-start flight、attachment delayed rescan 和一个 compaction-operation 专用、trigger-aware transaction-local terminal guard。
- 不重写 reactive compaction 的 request/Attempt closeout/recovery state machine；只将其 terminal outcome commit 收敛到与 proactive 相同的 Host terminal/CAS owner。
- 不从 CLI、Tool Trace、report、workspace config 或 manifest 反推实际 provider response identity。
- 不在动态 smoke 伪造 `succeeded/no-final`。行为项 30 继续只由 I0554 对应的 Engine/Host/public-contract owner-level 静态证明关闭。
- 不创建 issue；不拆 PR。

## 3. Design alignment 与第一性原理决策

### 3.1 分层与 semantic owner

| 语义 | 唯一 owner | 消费者规则 |
|---|---|---|
| prompt/interactive 参数可达性 | `dayu.cli.arg_parsing` | command 不读取未注册/已拒绝字段；Service 不解释 CLI argv |
| CLI label -> durable slot | `dayu.cli.host_context` + `dayu.cli.session_identity` 的单一 public mapping | prompt、interactive、session selector 机械复用，不自行拼 prefix |
| TTY draft/key sequence | `dayu.cli.composer` | `session_execution` 只消费 typed composer event；Run 中不再有第二 stdin reader |
| interactive Run/queue/cancel/exit-after 状态 | `dayu.cli.session_execution` | Service 只执行已有 typed submit/cancel/wait；Host 仍拥有 durable Run truth |
| whole-stdin draft | CLI binary stdin reader | 真实 stream exhaustion 是唯一 EOF；文本换行不被 REPL 重解释 |
| orphan proof 与 recovery CAS | `dayu.host.recovery_process` / `dayu.host.recovery` | open_host 只调度目标重扫，不凭 RW mutex 推断 orphan |
| delayed recovery 生命周期 | `_PublicHostHandle` 的 attachment-local task owner | attachment/Host close 取消未开始 task；scanner仍是唯一 durable mutator |
| compaction operation terminal | `dayu.host.compaction_terminal` 的专用 trigger-aware transaction-local guard | `dispatch` / `engine_ingest` 只在同一 write transaction 取得 OPEN permit 后写 artifact/event/fallback/start；`proactive_compaction` 复用该 terminal projection，memory/read/UI 不去重掩盖 canonical duplicate |
| pre-start single-flight | 每个 `HostDispatchScheduler` 对 live RW attachment 的 per-Session flight registry | wake 与 periodic 只是 signal；`SessionWorkLease` 仍只做 close/drain 生命周期计数 |
| 成功 Runner response identity | Engine success terminal/outcome contract | Host compactor只机械携带和验证，不从配置重算 |
| compactor accepted/rejected durable evidence | Host compaction operation/result + context event schema | accepted/rejected event 与 operation、attempt、manifest、output 同一 payload/event 绑定 |

该划分保持 `UI -> Service -> Host -> Engine`：CLI 不读取 Host internals，Service API 不增加 UI 状态，Host 只依赖 Engine 的安全 typed identity，Engine 不理解 Host compaction operation。

### 3.2 为什么不是过度设计

- S1 只收敛现有 parser、slot helper 和 session registry，不新建 alias service或迁移层。
- S2 复用 prompt_toolkit 的 VT100 sequence 解析、现有 Service `FollowupBehavior.QUEUE` 与 cancel/wait helper；新增的是小型 typed composer event 和 REPL-local状态，不建立第二套终端库。
- S3 复用现有 target scanner、orphan classifier、actor、CAS 与 dispatch limit；只增加由首次 scan 派生的一次 deadline task，不增加 polling supervisor。
- S4 使用 scheduler 内一个 `dict[session_id, flight]` 与一个 coalesced bit，并用一个只识别 compaction request/terminal 的窄 Host owner 同时服务 proactive/reactive writer；不用 database lock、新表、distributed lease、通用 event terminal framework 或通用工作队列。
- S5 扩展已经存在的 `RunnerRequestIdentity`、Engine final contract、compactor result 与 context payload；不暴露整个 `RunnerSpec`，也不建立第二份 provider tracing 系统。
- 六个 slice 有直接编译/调用依赖且必须最终联合验证，拆 PR 会制造中间不一致 schema 或暂时兼容层，因此一个 PR 是最小可维护交付单位。

## 4. Slice 总览与依赖

| Slice | 冻结项 | prerequisite | completion signal |
|---|---|---|---|
| S1 | F01-F04 parser/public contract/统一 label owner/registry | 当前 calibration/adjudication 两提交 | parser/help/typed consumption、slot 与 session registry owner tests 全绿；无旧 namespace读取 |
| S2 | F05-F09 composer、whole stdin、Escape、Ctrl+C、type-ahead+单 QUEUE | S1 的 interactive public args/context 已稳定 | PTY/pipe/async barrier tests 证明单 stdin owner、一次提交、canonical cancel、draft/queue race |
| S3 | F10 fresh RW delayed orphan recovery | S1 共享 label 使真实重连命中同 Session | immediate fresh attach 无提前恢复；threshold 后同 Run仅一个 recovery Attempt并终态 |
| S4 | F11 all-trigger unique terminal + F12 per-Session pre-start single-flight | S3 的 fresh-owner边界与 attachment access truth已稳定 | proactive/reactive barrier 下一个 live execution、一个 operation terminal；fresh owner才恢复 durable pending op |
| S5 | F13 Engine success identity -> Host accepted/rejected durable projection | S4 先保证 operation/attempt/terminal不串行性错误 | present/unavailable、success/failure/repair/multiattempt全覆盖且无敏感字段 |
| S6 | 集成、docs、oracle/scenario、一致性与 smoke | S1-S5 全部 owner tests 通过 | focused/full affected suite、pyright、coverage、docs/registry/secret检查和允许的 smoke 完成 |

依赖只用于实施顺序，不拆 PR；每个 slice 完成后先跑该 slice focused tests，再进入下一 slice。

## 5. S1 — F01-F04：parser、public contract、统一 label owner 与 registry

### 5.1 Allowed files/modules

生产代码只允许触及：

- `dayu/cli/arg_parsing.py`
- `dayu/cli/host_context.py`
- `dayu/cli/session_identity.py`
- `dayu/cli/session_execution.py`
- `dayu/cli/commands/prompt.py`
- `dayu/cli/commands/interactive.py`
- `dayu/cli/commands/session.py`

owner tests只允许触及：

- `tests/cli/test_arg_parsing.py`
- `tests/cli/test_prompt_command.py`
- `tests/cli/test_interactive_command.py`
- `tests/cli/test_session_command.py`
- `tests/service/test_entrypoint_runtime_prompt_path.py`
- `tests/service/test_entrypoint_runtime_interactive_path.py`

registry/docs 修改统一留到 S6。不得修改 `dayu.runtime`、Service assembly、Host slot schema或 Fins 命令。

### 5.2 Exact changes

#### F01：prompt/interactive 彻底无 `--config`

1. `build_parser()` 让 `_register_prompt_command`、`_register_interactive_command` 使用不含 `--config` 的 `command_common_parent`；其它 runtime commands 保持现有 parent，避免改变独立 Fins 命令的 command-local参数。
2. root parser 为其它 runtime commands 保留的前置 `--config` 必须在 `parse_cli_args()` 的单一 command-aware validation 中 fail closed：当最终 leaf 是 `prompt`、`interactive`，或现有 `session resume` 路由到这两个 Agent surface 时，只要 `config_dir` 非 `None` 就调用 parser usage error。这样 `dayu-cli --config X prompt ...` 也不可达，而 `prompt --config X` 继续由 argparse unknown option拒绝；该校验不是兼容路径，不进入 command runner。
3. `prepare_prompt_session_execution()`、`prepare_interactive_session_execution()` 删除 `resolve_explicit_config_dir(args.config_dir, ...)`；`_prepare_session_runtime()` 删除 `explicit_config_dir` 参数，并对 `EntrypointRuntimeRequest.explicit_config_dir` 固定传 `None`。workspace `<base>/config` / package fallback继续由现有 runtime location/config loader owner决定。
4. 删除 prompt/interactive 的显式 config错误测试，改成 parser-level不可达测试；不得保留 command-level config fallback。
5. 现有 `session list/purge` 仍可使用自己的 runtime config公共行为；`session resume` 走 Agent surface时拒绝显式 config，避免“parser接受但执行忽略”。

#### F02：interactive 彻底无 `--ticker`

1. `_register_interactive_command()` 删除 `--ticker`；prompt与独立财报命令的 ticker不变。
2. 删除 `_interactive_ticker()`；`_run_interactive_command_async()` 创建 `CliInvocation` 时传 `ticker=None`。
3. `build_interactive_context_slot_values()` 改成无 ticker/FMP参数的直接接口，只构造 interactive scene当前必需的默认财报主体与当前时间；删除 interactive command对 `FMP_API_KEY_ENV` 的读取。
4. `prepare_interactive_session_execution()` 删除 ticker参数；调用路径不再把 ticker作为 invocation identity或 context输入。
5. `session resume --mode prompt` 继续允许共享 parser上的 `--ticker`；`--mode interactive` 若携带 ticker，在 `_run_session_resume()` 进入 runtime前由明确 validation拒绝，删除 `_resume_interactive_ticker()`。这只是现有入口的 frozen parameter收敛，不新增 interactive resume能力。

#### F03/F04：一个 label owner、一个新 namespace

1. 在 `host_context.py` 用唯一 `CLI_AGENT_SESSION_SCOPE = "cli.agent"`、`CLI_AGENT_SLOT_KEY_PREFIX = "cli.agent."` 和 `cli_label_slot_key(label)` 取代 prompt/interactive 两套常量/helper。旧名字直接删除，不 re-export。
2. `_ensure_prompt_session()` 与 `_ensure_interactive_session()` 对有 label路径传同一 scope/slot helper；无 label路径不变：prompt `create_new=True/bind_slot=False` 且进程完成后退出，interactive 每次 invocation创建 anonymous fresh Session。
3. 不查找、不回退、不迁移 `cli.prompt.*` 或 `cli.interactive.*`；旧 slot在新代码中只会作为 `other` durable slot显示。
4. `session_identity.py` 删除 `CliSessionLabelKind` 与 kind参数；`slot_ref_for_cli_label(label)` 只构造 shared slot。`CliSessionDisplayKind` 用单一 `LABELED`（用户可读文本“labeled”）表示 shared alias，`ANONYMOUS/OTHER` 保留。
5. `session` 的 `--label` selector不再要求 `--kind`；parser删除 `--kind` 与 choices，resolver/purge/resume直接复用 `slot_ref_for_cli_label(label)`。`--mode prompt|interactive` 仍只选择已有输入模式，不再参与 durable alias身份。
6. 删除旧 namespace定向测试；新增同一临时 workspace中 prompt→interactive、interactive→prompt、prompt→prompt、interactive→interactive 都取得相同 `session_id` 的 public Host slot tests，并分别断言无 label两次 invocation的 `session_id` 不同。

### 5.3 Call path 与 data flow

```text
argv
  -> build_parser / parse_cli_args command-aware removed-option validation
  -> prompt|interactive command (不读取 config；interactive 不读取 ticker)
  -> resolve_workspace_root
  -> prepare_entrypoint_runtime(explicit_config_dir=None)
  -> cli_label_slot_key(label?)
       labeled: ensure_session(scope="cli.agent", slot_key="cli.agent.<label>")
       unlabeled: create fresh unbound Session
  -> attach -> execute existing-session path
```

### 5.4 Error handling 与 invariants

- removed参数在 runtime、Host open、Session create/ensure前失败；错误不回显 config路径之外的敏感内容，不输出 traceback。
- label strip/非空校验只在 `cli_label_slot_key`；consumer不再次 trim或拼 prefix。
- workspace 是 slot数据库边界的一部分；相同文本 label跨不同 workspace不构成同一 Session。
- `--kind`、旧 slot constants与旧 helpers必须从 exports/tests/docs中消失，不保留 wrapper。
- interactive context中不存在 ticker伪业务事实；用户若要分析某主体，必须在真实用户文本中表达。

### 5.5 Owner-level tests 与受影响测试

- parser inventory/help：prompt/interactive无 config，interactive无 ticker；root前置 config也不可达；session label selector无 kind；session resume mode-specific ticker/config拒绝；其它 runtime commands的 config正向用例不回归。
- command conversion：prompt仍传 ticker；interactive invocation/context明确 `None`/默认 subject；Service request `explicit_config_dir is None`。
- label：单 helper的Unicode/点号/空白；session list display；shared slot双向；旧 namespace为 OTHER且不复用。
- 删除迫使生产代码保留旧行为的 fake/fixture；fake按新 contract构造，不用默认字段掩盖缺参。

### 5.6 明确 non-goals

- 不改变 Host `SessionSlotRef` schema、ensure/create语义或 workspace DB路径。
- 不新增旧 slot migration、冲突合并或 label rename。
- 不修改 Fins ticker与配置行为。

### 5.7 Completion signal

S1 focused tests全绿；从 parser inventory、help、command DTO和 public slot状态四个 surface均无法观察旧参数/旧 namespace；跨 command同 label的 exact `session_id` 相同，无 label exact `session_id` 不同。

## 6. S2 — F05-F09：单一 composer、whole stdin、取消与单个 QUEUE follow-up

### 6.1 Allowed files/modules

生产代码只允许触及：

- `dayu/cli/composer.py`
- `dayu/cli/session_execution.py`
- `dayu/cli/commands/interactive.py`
- `dayu/cli/run_keys.py`（只收窄为 prompt one-shot 运行态用途；不重写 prompt行为）
- `dayu/cli/agent_entrypoint.py`（只在现有 `CliSigintMonitor` 缺少 composer并发等待所需的计数通知时做最小调整）

测试只允许触及：

- `tests/cli/test_interactive_composer.py`
- `tests/cli/test_interactive_command.py`
- `tests/cli/test_run_keys.py`
- `tests/cli/test_runtime_display.py`
- `tests/cli/test_interactive_run_view.py`
- `tests/cli/test_session_command.py`（现有 interactive mode调用签名）
- `tests/service/test_entrypoint_runtime_interactive_path.py`（只验证复用现有 QUEUE/cancel public request，不改 Service语义）

不得把终端解析下沉到 Service/Host/Engine；不得新增第二 stdin reader。

### 6.2 Composer public/private contract

1. 删除 `InputReaderComposer` 这条按行兼容 seam；非TTY走独立 whole-stream reader，TTY只使用 `PromptToolkitInteractiveComposer`。
2. 用小型严格类型替换 `InteractiveComposer.read() -> str`：
   - `InteractiveComposerPhase`: `IDLE`、`RUNNING`、`CANCELLING`；
   - `InteractiveComposerEventKind`: `SUBMIT`、`CANCEL_ACTIVE`、`TOGGLE_ACTIVITY`、`IDLE_INTERRUPT`、`EOF`；
   - `InteractiveComposerEvent` 只在 `SUBMIT` 携带非空/可空原始 draft，其它 event不得携带 submit文本；构造期验证封闭组合；
   - `InteractiveComposer.set_phase(phase)` 更新 key policy；`read_event(prompt)` 返回下一 typed event；draft/cursor/history由 composer自己拥有。
3. control key使 prompt_toolkit app返回 typed event时，composer先保存 exact buffer与 cursor；下一次 `prompt_async` 用同一 draft/cursor恢复。提交成功才把 exact text写入同一 `InMemoryHistory` 并清空 draft。
4. REPL只读取 typed event，不访问 prompt_toolkit buffer/key types。

### 6.3 F05：Shift+Enter exact sequence

1. 保留 Ctrl+J插入 `\n`。
2. 为 prompt_toolkit当前已证实映射成 `Keys.ControlM` 的 xterm modifyOtherKeys Shift+Enter exact bytes `\x1b[27;2;13~` 定义命名常量。`c-m` binding必须检查 `KeyPressEvent.key_sequence` 保存的原始 data：只有该完整 sequence插入换行；普通 `\r`/Enter提交。
3. 不把未知 CSI-u、普通 Enter或终端无法区分的同 bytes猜成 Shift+Enter；不修改 prompt_toolkit全局 `ANSI_SEQUENCES`。
4. PTY test保存 exact bytes、prompt_toolkit版本/capability和提交前 exact buffer；另有不可区分终端用普通 Enter bytes证明仍提交且报告“不支持区分”，不能伪报换行。

### 6.4 F06：non-TTY whole stdin

1. `_run_interactive_command_async`/`execute_interactive_on_session` 在 `stdin.isatty()==False` 时进入 `_run_interactive_non_tty_batch`，不创建 prompt_toolkit session、不打印 `dayu> `、不进入循环。
2. 使用显式注入的 `BinaryIO`（生产默认是已验证的 `sys.stdin` TextIOWrapper `.buffer`）一次 `read()` 到真实 exhaustion；测试用 `BytesIO`，不使用 `getattr/hasattr`。
3. bytes按 strict UTF-8解码；`UnicodeDecodeError` 转成稳定 `CliInteractiveUsageError("interactive stdin is not valid UTF-8")`，不得包含byte内容、codec repr、surrogate或 traceback。
4. 先 `\r\n -> \n`，再剩余 `\r -> \n`，然后按TTY冻结规则对整个字符串做一次外层 trim；内部换行、Unicode和 literal `0x04` 保留。
5. blank/whitespace batch不 submit、exit 0；非空 batch构造一个 `FollowupBehavior.QUEUE,target_run_id=None` 的 turn，等待该 Run canonical terminal、render/cursor/cleanup后按 terminal mapping退出。无第二 prompt、无第二 Run。

### 6.5 F07/F08/F09：TTY REPL state machine

在 `session_execution.py` 用几个职责单一的私有类型/函数重写现有串行 `_run_interactive_repl`；删除 `_wait_for_run_id_or_local_exit`、`_cancel_run_waiting_for_terminal_or_second_sigint` 等会在第二次SIGINT取消canonical waiter的旧分支，不留 wrapper。建议边界：

- `_InteractiveActiveTurn`：当前 submit/wait task、accepted run id generation、turn index、cancel task/原因；不持 composer或全局 renderer。
- `_InteractiveQueuedFollowup`：唯一已提交的下一 turn task与 turn index。
- `_InteractiveExitIntent`：封闭为 `continue` / `idle_exit_pending` / `exit_after_cancel`，只是 REPL-local intent，不是 Host 状态。任何正常编辑或非 Ctrl+C composer event 都会清除 `idle_exit_pending`，防止非连续 Ctrl+C 误退出。
- `_drive_interactive_tty_repl`：唯一竞态裁决者；等待 composer event、OS SIGINT count、current terminal与queued terminal。
- `_start_interactive_turn`、`_request_interactive_cancel`、`_finish_interactive_terminal`：分别拥有 submit、single cancel、render+cursor收口。

状态与确定性转移：

| 当前状态 | 输入/完成 | 唯一转移 |
|---|---|---|
| idle + 空 draft | Enter | no-op，清除 `idle_exit_pending`，仍 idle |
| idle + 非空 draft | Enter | 创建 current `QUEUE` turn，清除 `idle_exit_pending`，phase=`RUNNING` |
| idle + 非空或纯空白 draft | Ctrl+C | 清空整个 draft 并重绘；不设置 `idle_exit_pending`，仍 idle |
| idle + 空 draft，`idle_exit_pending=false` | Ctrl+C | 登记 `idle_exit_pending=true` 并重绘；不退出 |
| idle + 空 draft，`idle_exit_pending=true` | Ctrl+C | 若两次之间无正常输入，完成 display/composer/attachment cleanup 后 exit 130 |
| active pre-accept/accepted | standalone Escape | 合并一次 graceful cancel intent；若未 accepted，继续跨 acceptance barrier 等 run id；不退出 |
| active | 首次 Ctrl+C（composer byte 或 OS SIGINT） | 与 Escape 共用 single cancel 入口，但 reason 为 `cli_sigint`；不取消 submit 直到 run id/明确未接受事实成立 |
| cancelling，`exit_after_cancel=false` | Ctrl+C | 只设 `exit_after_cancel=true`；不取消 cancel task、canonical waiter、watcher、Host或attachment |
| cancelling/exit-after-cancel，`exit_after_cancel=true` | Ctrl+C | 第三次及之后一律 no-op；绝不再次发 cancel、`Task.cancel()` canonical waiter 或强关 Host/attachment |
| active | Ctrl+T | 通过现有 `RuntimeDisplayController.toggle_activity_display`；不改 draft/Run |
| active，尚无 queued follow-up | 第一份非空 Enter | 提交恰好一个 `QUEUE,target=None` follow-up，保存为 sole queued task；不 STEER |
| active，已有 queued follow-up | Enter | 不创建第二个 Run；保留当前新 draft 并给出有界中性提示 |
| active | printable/Unicode/paste/edit/navigation | 只改变可见 draft；current terminal 后仍保留 |
| active/cancelling | current terminal | 固定先 render、advance cursor、finish display，再把已存在 queued task 提升为 current；无 queued 则 phase 回 idle |
| active/cancelling | terminal 与 composer event 同一 wait 批次完成 | 先按 generation 处理 terminal，再处理仍匹配的新 composer event；stale generation control 丢弃，不重复 submit/cancel |
| exit-after-cancel | current/queued completion | 停止接收新输入；先等当前 cancel target canonical terminal，再对本 invocation 的 sole queued submit 等待明确 acceptance 结果；若已 durable accepted，必须使同一 queued Run 恰好执行一次并等其 canonical terminal；只有明确未 accepted 时才可无 queued terminal 继续，最后完成 display/composer/attachment cleanup 并 exit 130 |

关键实现要求：

1. TTY整个 invocation始终只有 prompt_toolkit input owner；interactive不再创建 `RunningKeyMonitor`。`run_keys.py` 继续服务 prompt one-shot的 Esc/Ctrl+T，不与 interactive composer竞争。
2. Escape binding采用 prompt_toolkit的非 eager sequence resolution：只有 parser timeout/flush后得到的 standalone `Keys.Escape` 发 `CANCEL_ACTIVE`；Up/Down/Home/Delete CSI、Alt序列和 bracketed paste由完整 sequence/paste event进入默认编辑或 draft语义。
3. `Ctrl+D` phase-aware：idle空 buffer为 `EOF`；非空按 prompt_toolkit删除光标下字符/末尾no-op；active/cancelling无论一次或连续都不 cancel、不登记exit。
4. cancel intent以 current turn generation去重；Escape和Ctrl+C race最多调用一次 `cancel_entrypoint_run_and_wait`。若submit先terminal，terminal truth赢，不对终态再cancel。
5. F08 + F09 的组合语义是 durable accepted sole `QUEUE` 必须恰好执行一次；第二次 Ctrl+C 只登记 exit-after-cancel，不撤销、取消或改写 queued Run。当前 invocation 必须先收口当前 cancel terminal，然后把已 accepted sole queued follow-up 提升为 current 并等待其 terminal；这是对现有 plan 语义的精确化，不改变 frozen oracle。特别是无 label fresh Session，不得在进程退出时留下永久 `QUEUED` Run 等待一个不会到来的 fresh invocation。
6. 第二次以及之后的 Ctrl+C 不能 `Task.cancel()` canonical cancel/terminal waiter；`exit_after_cancel=true` 后所有后续 Ctrl+C 都 no-op。outer task cancellation仍按正常 Python cancellation/cleanup传播，不伪装用户 Ctrl+C。
7. queued follow-up使用新的稳定 `interactive_submit_client_request_id(turn_index)`；Host幂等与admission保证durable exactly-once，CLI本地 sole slot保证不会发第二个并行queue。exit intent 不取消已发出的 sole submit task，而是等其返回“accepted + exact run id”或“明确未 accepted”，禁止从 task cancellation 推断 Host acceptance。
8. run view/thinking/activity仍通过现有单线程 `RuntimeDisplayController` 串行，不把composer buffer投影到Service或日志。

### 6.6 Error handling 与 invariants

- composer、signal、submit、cancel、renderer、cursor、attachment各自错误沿现有 primary-vs-cleanup cause规则收口；不得吞掉首个业务错误。
- `Host LOST`仍fatal exit 1；FAILED/CANCELLED是否回composer遵守 frozen interactive oracle；nonTTY任何terminal都结束进程。
- active draft永不进入log、trace、EventLog，直到用户Enter；取消不提交draft。
- 同一时刻一个TTY stdin reader、一个current turn、至多一个queued follow-up、至多一个cancel waiter。
- QUEUE不带 `target_run_id`；代码和测试禁止 `STEER`。

### 6.7 Owner-level tests

- composer纯测试：Ctrl+J、exact Shift+Enter、ordinary Enter、CSI、Alt、paste、Escape timeout、Ctrl+D phase matrix、draft/cursor/history恢复、Ctrl+C phase matrix、editor failure脱敏。
- real POSIX PTY：按bytes写入 standalone `\x1b`、`\x1b[A`、代表性Alt、`\x1b[200~...\x1b[201~`、`\x1b[27;2;13~`；断言screen、buffer、terminal mode/echo恢复。非POSIX明确skip并由Windows CI保留非TTY owner boundary。
- pipe：empty、whitespace、single line、multiline、CRLF、CR、无末尾LF、literal `0x04`、invalid UTF-8；断言0/1 Run、无prompt、exact user message、稳定错误。
- Ctrl+C deterministic matrix：idle 非空、纯空白 draft 首次只清空且不设 pending；之后空 draft 第一次只登记 exit intent，第二次 cleanup+130；中间穿插正常输入会重置 intent。
- async barrier：pre-accept/provider/tool/closeout各阶段 Escape和Ctrl+C；active 第一次 Ctrl+C 只建立 single cancel，第二次只设 exit flag，第三次及更多次均 no-op；cancel/canonical terminal task 均未被 cancel，且 terminal/cursor/cleanup 完成。
- type-ahead：printable/Unicode/paste/edit在terminal前后保留；Enter只创建一个 QUEUE，current terminal后执行一次；terminal/Enter race双序测试；明确零STEER。
- exit-after-cancel + sole QUEUE 确定性测试：分别在 queued submit acceptance barrier 之前/之后连续 Ctrl+C，断言当前 Run 精确一个 cancel terminal、已 accepted queued Run 精确启动/终态一次、两者收口后才 exit 130；无 label fresh Session 退出后查询不存在永久 queued Run。
- 更新旧tests/README描述所依赖的旧断言，不能让 fake强迫“第二次Ctrl+C立即退出且无terminal”或“Run中single-byte monitor”继续存在。

### 6.8 明确 non-goals

- 不支持多个并行queued follow-up，不增加framing pipe多轮协议。
- 不改变 prompt one-shot运行态按键语义。
- 不实现 TUI、命令模式、STEER、interactive resume命令。

### 6.9 Completion signal

PTY与pipe owner tests、CLI integration tests全绿；检查任何 active阶段都只有composer读取stdin；Escape/CSI/Alt/paste、Ctrl+C、Ctrl+D、type-ahead和terminal race的exact状态/次数符合表格。

## 7. S3 — F10：fresh RW attachment delayed orphan recovery

### 7.1 Allowed files/modules

生产代码只允许触及：

- `dayu/host/recovery_process.py`
- `dayu/host/recovery.py`
- `dayu/host/open_host.py`
- `dayu/host/session_attachment.py`（仅当内部attachment资源需要窄lifecycle接口；优先由open_host managed wrapper完成，不改变public DTO）

测试只允许触及：

- `tests/host/test_recovery_orphan_classifier.py`
- `tests/host/test_recovery_scan.py`
- `tests/host/test_public_session_attachment.py`
- `tests/host/test_session_attachment_registry.py`
- `tests/host/test_open_host_runtime.py`
- `tests/host/test_recovery_multiprocess.py`

### 7.2 Exact changes

1. `classify_orphan_candidate()` 将stale边界定义为 elapsed `< stale_after` 才 recent，elapsed `>= stale_after` 进入stale分类；避免deadline相等时被迫轮询。
2. `SessionAttachmentRecoveryAction` 增加 `retry_not_before: datetime | None`；只有 heartbeat可解析且原因是 `owner_heartbeat_recent` 时，由 classifier同源 `heartbeat_at + stale_after` 产生。missing row、parse failure、probe error、identity matched等不猜deadline。
3. `SessionAttachmentRecoveryScanResult` 增加全部action中最早的 `next_reconcile_at` typed aggregate；scanner每次仍使用固定 `policy.now`、fixed upper watermark、bounded pages，并只返回schedule建议，不在scanner里sleep或建task。
4. `_SessionAttachmentRecoveryActorOperation` 保持 target-only scanner owner；首次 attach传初始fixed now，delayed执行时必须创建新operation并传 `datetime.now(UTC)`，禁止复用旧now。
5. `_PublicHostHandle` 增加仅针对当前live RW attachment的 `_delayed_attachment_recovery_tasks: dict[str, Task[None]]`：
   - 首次scan返回deadline且allocation成功activate后，创建至多一个target task；
   - task按UTC deadline换算一次monotonic delay，唤醒后先从registry取得新的new-work lifecycle lease，再向现有durable actor提交同一target scanner；
   - actor future与lease绑定，caller/task cancellation不越过已开始transaction；
   - 第二次scan使用fresh now，不循环poll；positive proof、CAS miss、owner live/inconclusive均由原classifier决定。
6. public attachment用一个增加真实生命周期语义的内部managed resource返回：`aclose()`先取消并join尚未开始的target delayed task，再关闭底层attachment。Host close在actor stop前批量取消/join全部delayed tasks；未开始task不写EventLog或状态。
7. delayed task异常记录安全type并通过现有 `HostExecutionHealthGate.report_fatal` 使new-work fail closed；不静默丢失obligation。正常完成不是scheduler fatal。

### 7.3 Deterministic recovery/CAS data flow

```text
fresh writer取得native RW mutex
  -> initial target scan(now=t0, fixed watermark)
  -> recent heartbeat => action.retry_not_before = heartbeat + stale_after
  -> activate attachment并登记一个target task
  -> deadline到达，以fresh now=t1取得new-work lifecycle lease
  -> same target scanner / fresh fixed watermark / bounded pages
  -> positive orphan proof only
  -> close_startup_orphan_attempt_in_transaction(expected run/attempt/execution/
     dispatch owner/heartbeat) CAS
  -> ATTEMPT_LOST -> RUN_RECOVERING
  -> same frozen prepared source创建new Attempt/execution/dispatch
  -> RUN_STARTED(start_reason=recovery)
  -> commit后wake scheduler
```

### 7.4 Invariants 与错误处理

- RW mutex只授予mutation资格，不是orphan proof；deadline前绝不恢复。
- 每个live attachment/Session最多一个delayed task；每个task最多一次delayed scan；每Run既有 `recovery_dispatch_limit=1` 保持。
- CAS校验旧 owner id/heartbeat与全部Run/Attempt/dispatch identity；deadline等待期间terminal或owner状态变化使CAS/no-op赢，不写补偿fact。
- attachment close取消未开始sleep不写事实；已进入actor的scan必须shield收口再释放attachment mutex。
- scanner不扫描其它Session，不takeover旧Attempt，不重发CLI prompt。

### 7.5 Owner-level tests

- classifier：threshold前、等于threshold、之后；deadline只来自recent heartbeat。
- scanner：aggregate earliest deadline、多个Run固定watermark、无schedule类别、CAS loser。
- fake clock/barrier：initial scan recent，deadline前零mutation，fresh now后positive proof，exact event顺序与一个new Attempt/execution。
- attachment close：sleep前close取消task零fact；actor已提交时close等待future；Host close无task泄漏/无mutex提前释放。
- multiprocess：owner建立active RUNNING后 `SIGKILL`，fresh same-label interactive立即RW attach；无需第二次重启，stale后同Run恢复且最终terminal，旧/new attempt与execution不同，provider/worker执行次数不超过允许值。
- live owner/probe inconclusive反例：不恢复、不写lost/recovering；RO attachment不schedule。

### 7.6 明确 non-goals

- 不实现 G02完整normal close/crash/SIGKILL矩阵；本slice只关闭F10已证实的SIGKILL immediate fresh reconnect。
- 不增加后台永久recovery polling或全库startup scan。
- 不改变accepted cancel watchdog owner。

### 7.7 Completion signal

F10复现场景从“180秒仍RUNNING”变成无需用户二次重启的bounded recovery；所有反例仍无提前/错误恢复；task/lease/mutex close tests全绿。

## 8. S4 — F11/F12：唯一 compaction terminal 与 per-Session pre-start single-flight

### 8.1 Allowed files/modules

生产代码只允许触及：

- `dayu/host/compaction_terminal.py`（新增的精确 compaction-operation terminal/CAS owner）
- `dayu/host/proactive_compaction.py`
- `dayu/host/dispatch.py`
- `dayu/host/engine_ingest.py`（只收敛 reactive terminal outcome commit，不重写其余 recovery state machine）
- `dayu/host/session_attachment.py`（只保持/测试lease生命周期接口，不增加mutex语义）

测试只允许触及：

- `tests/host/test_compaction_terminal.py`（新增 shared owner 的 trigger/race contract tests）
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_compaction_operation.py`
- `tests/host/test_context_compact_events.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_public_session_attachment.py`
- `tests/host/test_session_attachment_registry.py`
- `tests/host/test_open_host_runtime.py`

F12设计文档更新在S6统一落地。两路 writer 的已核实代码证据要求在 S4 直接新增一个精确命名的 `compaction_terminal.py`；它只理解 compaction request/trigger/terminal，不接受任意 event type，不演化为通用 terminal framework。不再保留“implementation 自行决定是否新增 owner”的设计空白。

### 8.2 F11：所有 compaction operation 的唯一 terminal/CAS owner

#### 8.2.1 代码证据与必须修复的反例

1. 全仓 terminal writer 核验只有两路：`dispatch.py` 追加 proactive `CONTEXT_COMPACTED` / `CONTEXT_COMPACTION_FAILED`，`engine_ingest.py` 追加 reactive 同名 terminal。F11 是“每个 compaction operation 精确一个 canonical terminal”的通用 invariant，不以 trigger source 为边界。
2. reactive `_execute_reactive_compaction()` 先在事务外 `await run_compaction_operation(...)`，再进入新 write transaction。结果 transaction 当前只校验 `_validate_durable_context()`、`RunStatus.RECOVERING`、source Attempt terminal 与 input cursor，没有读取该 `operation_id` 的已有 terminal。`sequence_stale` 分支直接写 `stale_compaction_result` failed，普通分支直接写 rejected events 后 failed 或 accepted。
3. `_duplicate_engine_terminal_result()` 只保护“重新 ingest 同一 Engine candidate”的 prefix/outcome 读取，并不是 outcome commit guard。两个已取得同一 `_ReactiveCompactPending` 的并发/幂等重入 executor 可在事务外分别得到 accepted 与 failed；第一个 outcome transaction 提交后、后续 recovery-start transaction 之前，第二个仍可通过上述 Run/Attempt 校验并写另一 terminal。这是必须以 transaction-local reread 关闭的 reactive 反例，不得以“当前常规入口大概只会发出一个 pending”代替 idempotency contract。
4. reactive `_append_reactive_compacted_event()` 当前先写 artifact bytes 和 payload descriptor，再 append `CONTEXT_COMPACTED`。因此 late loser 必须在 artifact/descriptor、rejected/terminal event、fallback/fail-close/recovery start 之前就返回 no-op/diagnostic，不能只在 event append 处去重。

#### 8.2.2 专用 trigger-aware transaction-local guard

1. 新增 `dayu.host.compaction_terminal`，定义封闭 `CompactionOperationTerminalDisposition`：`OPEN`、`COMPACTED`、`FAILED`、`INVALID_MULTIPLE`，以及 `CompactionTerminalCommitPermit` / `CompactionTerminalClosed` 两个封闭结果类型。permit 只表示 `OPEN`，带 `operation_id`、已验证 `trigger_source`、request event sequence；closed 只表示 `COMPACTED/FAILED/INVALID_MULTIPLE`，保留 first terminal sequence/type 供安全 diagnostic。
2. 唯一入口 `begin_compaction_terminal_commit_in_transaction(transaction, event_log_store, *, operation_id, expected_trigger_source) -> CompactionTerminalCommitPermit | CompactionTerminalClosed` 使用 strict `CONTEXT_COMPACTION_REQUESTED` / terminal payload parser 读取该 operation，校验 request 与 expected proactive/reactive trigger 一致，并返回 permit 或 loser result。两路 writer 不得各自实现 terminal count、fallback check 或 loose parsing。
3. `proactive_compaction.py` 的完整 operation projection 继续拥有 proactive snapshot/attempt/decision，但 terminal disposition 必须机械复用 `compaction_terminal` 的 strict 结果，不保留第二套 terminal guard/source of truth。
4. `dispatch.py` 的 invalid/exhausted pre-start、stale run/input、session no longer allows、operation failure/fallback 与 accepted 分支，以及 `engine_ingest.py` 的 sequence-stale、operation failure/fallback/fail-close 与 accepted recovery 分支，都必须在各自现有 write transaction 中首先调用这一入口。
5. 只有 `OPEN` permit 持有者可在同一 transaction 继续：
   - accepted：先校验 candidate/quality/manifest，再写 compact artifact/descriptor 与唯一 compacted event；
   - failed：先写当次 winner 所有 rejected evidence 与唯一 failed event，仅该 winner 可继续 fallback dispatch、reactive recovery start 或 fail-close；
   - `COMPACTED/FAILED` late loser：只写有界安全 log/health diagnostic 并返回 no-op，不写 artifact、descriptor、rejected/terminal/canonical event、fallback、Run/Attempt start/closeout；
   - `INVALID_MULTIPLE`：fail closed 并保持已有 truth，不追加第三 terminal 或尝试修复旧库。
6. SQLite write transaction 串行 + transaction 内 fresh operation projection read 是 CAS 线性化点；permit 不持久化、不跨 await/事务传递。不新增 event 删除、projection 去重、DB unique index/新表或迁移。
7. S4 guard 的 request/permit 不预埋 optional `successful_response_identity`。S5 依赖 accepted S4 guard 后，再在两路 winner writer 的 typed accepted/rejected payload 上做 required identity 扩展；guard 只决定“能否提交 terminal”，不拥有“terminal payload 写什么”，因而 S5 无需重构或扩展 guard 签名。

### 8.3 F12：scheduler-local per-Session flight

新增精确的私有 `_PreStartGovernanceFlight`：只含 `task: Task[bool]` 与 `rerun_requested: bool`。`HostDispatchScheduler` 增加 `_pre_start_flights: dict[str, _PreStartGovernanceFlight]` 和 `_promotion_pending_session_ids: set[str]`，不得加入锁对象。

信号算法：

1. `wake_queue_promotion(session_id)` 先检查attachment new-work资格：
   - 已有flight：只把 `rerun_requested=True`；
   - 尚在promotion queue pending set：不重复入队；
   - 否则加入pending set和现有promotion queue。
2. `_promotion_drain_loop` 取出Session后移除pending marker，调用 `_signal_pre_start_governance(session_id)`；该函数复用existing flight或创建sole flight并await。现有transient retry/backoff仍由drain loop拥有。
3. `run_queue_promotion()` 与 `reconcile_owned_sessions_once()` 不再自行取得lease并直接调用 `_run_queue_promotion_with_lease`；两者都调用同一signal-and-await入口。periodic loop保留。
4. sole flight loop每一pass：
   - 在无await区间清空当前coalesced bit；
   - 从 `SessionNewWorkAccessPort` 取得一个 `SessionWorkLease`，只覆盖本pass durable/pre-start/compactor await与stable dispatch commit；
   - 调用 `_run_queue_promotion_with_lease`，finally释放lease；
   - 完成后若bit为true，恰好再从fresh durable truth执行下一pass；若false，在无await区间按task identity删除dict entry并退出。
5. signal在“检查bit -> 删除entry”之间不能丢失：该区间无await，event loop原子；删除后到达的新signal创建new flight。重复signals只合并成一个level bit，不按次数消耗compaction attempt。
6. flight task进入scheduler现有critical-task/close tracking；异常对所有awaiter一致并沿现有health fatal/requeue policy，close取消并await，不留compactor task。
7. live flight已在事务外执行compactor时，periodic/repeated wake只置bit，不读取durable request为“crash resume”。flight完成后的fresh pass看到terminal/dispatch后no-op或推进一次。
8. opener停止/crash使in-memory flight消失；fresh RW attachment的target recovery/wake由新scheduler从durable `CONTEXT_COMPACTION_REQUESTED`、prepared/rejected manifests、冻结snapshot/max budget恢复同一个operation。不得创建新operation或重置attempt number。

### 8.4 Concurrency/cancellation/recovery invariants

- 每个scheduler、每个live RW Session至多一个pre-start invocation；不同Session仍可各自推进，不增加global mutex。
- `SessionWorkLease`只保证attachment/Host close等待真实work，不决定互斥；docstring/tests明确这一点。
- compactor cancellation/Host close留下已提交request与manifests，由fresh owner恢复；live重复signal不恢复。
- first terminal commit wins；late provider/repair/result不能改变fallback、accepted output或Run start次数。
- periodic interval不删除、不禁用；它仍保障cross-opener accepted/queued liveness。

### 8.5 Owner-level tests

- shared owner direct tests：proactive/reactive request 都可得到 `OPEN` permit，trigger mismatch fail closed，first compacted/failed 投影出 exact first sequence/type，multiple terminals 为 `INVALID_MULTIPLE`；不允许任意非 compaction event。
- proactive F11 复现 I0543 顺序：先 invalid/exhausted failed，再释放 late compactor；EventLog exact 一个 terminal 且 reason 保持 first，fallback/start 次数不变。
- proactive first compacted 后 late failed、first failed 后 late accepted、两个 terminal contender barrier；exact 一个 terminal、无 loser artifact/event/fallback/start。
- reactive 并发/幂等重入确定性反例：将同一 operation/pending 的两个 outcome executor 阻塞在事务外 compactor barrier，分别按“failed winner -> late accepted”与“accepted winner -> late failed/sequence-stale”释放；每次均 exact 一个 terminal，loser 无 artifact/descriptor/rejected event/fallback/recovery start/fail-close，first reason/output/start count 不变。
- writer inventory test/静态检查：`dispatch.py` 与 `engine_ingest.py` 的全部 `CONTEXT_COMPACTED` / `CONTEXT_COMPACTION_FAILED` append 路径均在同一 transaction 使用 shared owner，不存在第二 guard。
- F12真实async barrier冻结compactor await，同时注入多个wake与periodic one-shot；provider/compactor执行一次、一个request、attempt budget只记真实attempt。
- barrier释放后coalesced pass至少fresh reread一次且no-op；在exit边界到达的新signal不丢失。
- 不同Session可并行；RO/closing无flight；scheduler close取消flight并保持lease/mutex顺序。
- fresh scheduler基于同一DB恢复同operation id、snapshot、max budget和next attempt；live scheduler不走resume。
- 保留现有periodic reconciliation test，修改其断言为“signal source”而非“独立owner”。

### 8.6 明确 non-goals

- 不重写 reactive compaction 的 request/Attempt closeout/recovery 状态机；只收敛 terminal outcome commit。不新增数据库 unique index 或 operation 表。
- 不在 S4 guard 中预埋 optional identity/payload bag，不让 terminal owner 演化为通用 event commit framework。
- 不承诺公平性/FIFO，不让single-flight跨Host opener共享内存。
- 不把promotion queue替换成通用task scheduler。

### 8.7 Completion signal

barrier/race tests在固定顺序与反向顺序均稳定：同 Session 一个 live flight，proactive/reactive 每个 operation 都只有一个 canonical terminal，late loser 在任何 artifact/event/fallback/start 前 no-op/diagnostic，periodic 仍可推进，fresh owner 才恢复。

## 9. S5 — F13：Engine success response identity 到 Host accepted/rejected durable evidence

S5 严格依赖 accepted S4 terminal guard：S4 只决定当前 transaction 是否是 terminal winner，不预埋 optional identity。S5 在 winner 路径上一次性把 accepted/rejected identity 改为 required typed payload；不向 S4 加 nullable 参数、payload bag 或兼容分支。

### 9.1 Allowed files/modules

Engine生产代码：

- `dayu/engine/contracts/runner_identity.py`
- `dayu/engine/contracts/engine_events.py`
- `dayu/engine/contracts/agent_run.py`
- `dayu/engine/contracts/__init__.py`
- `dayu/engine/agent.py`
- `dayu/engine/__init__.py`

Host生产代码：

- `dayu/host/compaction.py`
- `dayu/host/llm_compaction.py`
- `dayu/host/compaction_operation.py`
- `dayu/host/context_events.py`
- `dayu/host/dispatch.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/compact_pipeline.py`（只更新typed payload input的直接字段）
- 对应package export文件（仅真实public contract，不做兼容re-export）

S5 owner-level / behavior tests 只允许触及：

- `tests/engine/contracts/test_runner_identity.py`
- `tests/engine/test_engine_event_contract.py`
- `tests/engine/contracts/test_agent_run.py`
- `tests/engine/test_agent_phase2.py`
- `tests/engine/test_agent_phase3_tool_call.py`
- `tests/engine/test_package_exports.py`
- `tests/host/test_llm_compaction.py`
- `tests/host/test_compaction_operation.py`
- `tests/host/test_context_compact_events.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_compact_pipeline.py`
- `tests/host/test_package_exports.py`
- `tests/host/test_import_boundary.py`

此外，required success identity 与 `ContextCompactor` typed return 会让既有
test/test-support 直接构造点发生必然类型错误。以下是基于
HEAD `331d38dcaeebe3a929b7fa52d4e161a1c6504c55` 的完整机械闭包，也属于
S5 allowed files；这只允许补齐 required typed value、解包/保留同一个 proposal
identity 和随 contract 迁移类型标注，不允许借机改变测试场景、Host/Engine 行为或
断言语义。

表中 `FA(n)` 表示该文件有 `n` 个 `FinalAnswerData(...)` 直接构造，`OA(n)`
表示有 `n` 个 `EngineRunOutcomeFinalAnswer(...)` 直接构造，`CR` 表示直接实现、
override、delegate 或消费 `ContextCompactor` / prepared-compactor typed return。

| 文件 | HEAD 直接证据 |
|---|---|
| `tests/engine/test_engine_event_contract.py` | `FA(2)` |
| `tests/engine/test_smoke_async_agent_providers.py` | `FA(1)` |
| `tests/service/test_entrypoint_runtime_interactive_path.py` | `FA(1)` |
| `tests/host/fake_compaction.py` | `CR`；`FakeContextCompactor` 是测试 double owner |
| `tests/host/public_smoke_support.py` | `FA(1)` |
| `tests/host/recovery_support.py` | `FA(2)` |
| `tests/host/stress_support.py` | `FA(1)` |
| `tests/host/transient_stream_support.py` | `FA(1)` |
| `tests/host/test_active_cancel_dispatch.py` | `FA(2)` |
| `tests/host/test_compact_artifact_store.py` | `CR` |
| `tests/host/test_compaction_cancellation_scope.py` | `OA(1)` |
| `tests/host/test_compaction_contract.py` | `CR` |
| `tests/host/test_compaction_operation.py` | `CR` |
| `tests/host/test_dispatch_scheduler.py` | `FA(3) + CR` |
| `tests/host/test_effective_execution_config.py` | `FA(1)` |
| `tests/host/test_engine_ingest_mapping.py` | `FA(10) + CR` |
| `tests/host/test_llm_compaction.py` | `OA(1) + CR` |
| `tests/host/test_open_host_runtime.py` | `FA(3)` |
| `tests/host/test_per_run_tool_selection.py` | `FA(1)` |
| `tests/host/test_phase5_local_execution_integration.py` | `FA(1)` |
| `tests/host/test_public_compact_smoke.py` | `FA(1) + OA(2)` |
| `tests/host/test_public_retry_replay.py` | `FA(1)` |
| `tests/host/test_recovery_dispatch.py` | `FA(1)` |
| `tests/host/test_submit_followup_public_contract.py` | `FA(1)` |
| `tests/host/test_watch_session_events.py` | `FA(1)` |

上述第一 amendment 的 tests/test-support 机械闭包总计 25 个去重文件：35 个
`FinalAnswerData(...)` 直接构造、4 个 `EngineRunOutcomeFinalAnswer(...)` 直接构造，以及
7 个 `ContextCompactor` typed-return 相关文件；其中 5 个已在上方 owner-level 清单，
当时新增 allowed-file 缺口为 20 个。

第三次 accepted-plan premise invalidation 在 accepted HEAD
`e7f578dc7bdfafb51a859be2db584300e08f81fb` 证明第一 amendment 只枚举 `tests/`，遗漏了
全量 `python -m pyright dayu/ tests/ utils/` 必然覆盖的两个既有 smoke consumer。二者与
上述 25-file tests closure 无重叠，且 `utils/` 没有 `ContextCompactor` typed-return hit：

| 文件 | accepted HEAD 精确调用行证据 | S5 boundary 状态 |
|---|---|---|
| `utils/smoke_host_public_awaiting_entrypoint.py` | `FinalAnswerData(...)`：2010 | 第三次 amendment 新增；只允许 required identity 机械迁移 |
| `utils/smoke_host_public_conversation_memory_scenarios.py` | `EngineRunOutcomeFinalAnswer(...)`：1748、1794；`FinalAnswerData(...)`：1843 | 第三次 amendment 新增；只允许 required identity 机械迁移 |

完整 tests+utils identity/typed-return closure 因此精确为：`FinalAnswerData(...)` 37 calls /
21 files、`EngineRunOutcomeFinalAnswer(...)` 6 calls / 4 files、`ContextCompactor`
typed-return 7 files，三类去重 union 27 files。S5 实现前必须在 `tests/` 与 `utils/` 上重跑
同一 inventory；若 accepted HEAD 之后出现新直接构造点或 typed-return file，先退回
controller 修订 allowed files，不得在未列文件中补 default/fallback。

所有 tests 与 utils 机械调用点必须从该 fake/event/outcome 的同一次 typed invocation/input 构造
`SuccessfulRunnerResponseIdentity`：run、iteration、attempt/execution、provider/model
与 provider request id availability 必须同源。没有 provider request id 的 fixture/smoke 明确使用
`UNAVAILABLE + None`；不得复用相邻 Run/iteration/compactor attempt 的 identity，不得
增加 optional default、兼容构造签名、全局万能 identity fixture 或下游补值。

两个 utils 文件的唯一 allowed delta 冻结如下；它们是 smoke fixture consumer，不获得
Engine identity 业务规则所有权：

1. 每个文件只可增加构造 required `SuccessfulRunnerResponseIdentity` 所需的精确 imports、
   module-level private smoke identity 常量/窄 helper，以及 4 个 direct constructors 的 required
   `response_identity` 实参。两个文件分别定义 file-local
   `_unavailable_smoke_response_identity(*, request, iteration_id, iteration_index, runner_call_index)`；
   所有参数 required 且无 default。不得新增跨文件共享 helper或通用
   identity builder。
2. `utils/smoke_host_public_awaiting_entrypoint.py::_AnswerHandle.events()` 必须从已持有的
   `self._request` 构造 identity：`run_id/attempt_id/execution_id` 直接取该 request，
   provider/model 直接取 `self._request.runner_spec.provider/model`；该 synthetic smoke request
   只模拟一个成功 Runner call，所以由调用点显式传
   `_ANSWER_RESPONSE_ITERATION_ID = "awaiting-smoke-answer-iteration"`、
   `_SMOKE_RESPONSE_ITERATION_INDEX = 0`、`_SMOKE_RESPONSE_RUNNER_CALL_INDEX = 1`，provider request id 使用
   `UNAVAILABLE + None`。
3. `utils/smoke_host_public_conversation_memory_scenarios.py` 中
   `_DeterministicCompactWorker.accept()` 已同时持有 `AttemptDispatchSnapshot` 与同一次
   `AgentRunRequest`；它必须从该 request 构造 identity，并把 required typed value 显式传给
   `_final_answer_event(...)`，后者新增无 default 的 required typed 参数并只机械写入
   `FinalAnswerData.response_identity`。`_AcceptingSmokeCompactorRunner.__call__()` 与
   `_RejectingSmokeCompactorRunner.__call__()` 分别从各自收到的 compactor
   `AgentRunRequest` 构造并写入 outcome identity。三处均直接使用 request 的
   `run_id/attempt_id/execution_id` 与 `runner_spec.provider/model`；ordinary final、accepting
   compactor、rejecting compactor 的调用点分别显式传
   `"smoke-final-answer-iteration"`、`"smoke-accepting-compactor-iteration"`、
   `"smoke-rejecting-compactor-iteration"` 三个 module-level private 常量，并共同显式传
   `_SMOKE_RESPONSE_ITERATION_INDEX = 0`、`_SMOKE_RESPONSE_RUNNER_CALL_INDEX = 1`。provider request id
   使用 `UNAVAILABLE + None`；不同 Host compactor attempt 依靠各自 request.run_id 保持身份
   分离。
4. identity 不得从 runtime/workspace config、manifest、CLI 参数、相邻 event、输出文本、
   provider family 或 smoke 全局状态反推。迁移不得改变调用次数、scene/suite、worker/compactor
   分支、provider 配置、输出文本/marker、CLI oracle、artifact/EventLog 断言或异常语义；不得为
   identity 增加新的输出。

S5 另有一个独立的 strict durable builder 调用闭包。§9.4 将
`CONTEXT_COMPACTED.successful_response_identity` 固定为 required mapping，并将
`CONTEXT_COMPACTION_ATTEMPT_REJECTED.successful_response_identity` 固定为 required
field（值按对应 event 语义为 mapping 或 `null`）。S5 必须先由
`dayu/host/context_events.py` owner 给 `build_context_compacted_payload(...)` 增加
required typed `successful_response_identity: SuccessfulRunnerResponseIdentity` 参数，并给
`build_context_compaction_attempt_rejected_payload(...)` 增加 required typed
`successful_response_identity: SuccessfulRunnerResponseIdentity | None` 参数；两者都不得有
default、optional call seam 或兼容 overload。owner signature 收紧后，再机械迁移全部
8 个 consumer files 的 15 个 direct calls。后述 5-file delta 只表示新增 allowed-file
boundary，不是完整调用迁移范围；原已允许的 3 个文件同样必须迁移。

基于 HEAD `ec9342ed9e5584123618f6b5c5eba8e93e2aed94`，`CB(n)` 表示
`build_context_compacted_payload(...)` 的 `n` 个 test calls，`RB(n)` 表示
`build_context_compaction_attempt_rejected_payload(...)` 的 `n` 个 test calls：

| 文件 | HEAD 直接证据 | S5 boundary 状态 |
|---|---|---|
| `tests/host/test_context_compact_events.py` | `CB(3) + RB(4)` | 已允许 |
| `tests/host/test_compaction_operation.py` | `RB(1)` | 已允许 |
| `tests/host/test_dispatch_scheduler.py` | `CB(1) + RB(1)` | 已允许 |
| `tests/host/test_memory_projection.py` | `CB(1)` | 本 amendment 新增 |
| `tests/host/test_compaction_terminal.py` | `CB(1)` | 本 amendment 新增 |
| `tests/host/test_run_input_builder.py` | `CB(1)` | 本 amendment 新增 |
| `tests/host/test_compact_material.py` | `CB(1)` | 本 amendment 新增 |
| `tests/host/test_proactive_compaction_operation.py` | `RB(1)` | 本 amendment 新增 |

该 inventory 精确为 accepted builder `8 calls / 6 files`、rejected builder
`7 calls / 4 files`、去重 `8 files`；其中 3 个文件此前已在 S5 owner-level / behavior
test 清单，新增 allowed-file 缺口精确为后 5 个文件。第一 amendment 的 25-file tests
identity/typed-return closure 原样保留；第三次 amendment 加入与其无重叠的 2 个 utils 后，
完整 tests+utils identity/typed-return closure 为 27 files。该 27-file closure 与完整 8-file
builder closure 的 overlap 精确为 2 files：`tests/host/test_compaction_operation.py`、
`tests/host/test_dispatch_scheduler.py`。因此 builder closure 相对 27-file closure 的 set
difference 精确为 6 files：`tests/host/test_context_compact_events.py`、
`tests/host/test_memory_projection.py`、`tests/host/test_compaction_terminal.py`、
`tests/host/test_run_input_builder.py`、`tests/host/test_compact_material.py`、
`tests/host/test_proactive_compaction_operation.py`。其中
`tests/host/test_context_compact_events.py` 在第二次 amendment 前已经属于 S5 allowed owner
tests，但没有 FA/OA/CR hit；其余 5 files 才是第二次 amendment 新增的 allowed-file delta。
完整 S5 枚举 mechanical union 必须按全集去重为
`27 identity/typed-return + 8 builder - 2 overlap = 33 files`；不得把 5-file allowed-file delta
误当作 builder closure 相对 identity closure 的完整 set difference。

Base HEAD 的 15 个 call 都尚未携带该参数，因为 owner signature 也尚未扩展；不得暗示
这些测试已经拥有可直接复用的 runtime response identity。这 15 个 direct call sites 的
durable-builder 迁移只允许补齐新增 required typed 参数或同步 exact payload fixture；5 个
新增文件只是本次 allowed-file delta，整文件内也仅放行该机械变更，原已允许 3 个文件的
其它 S5 owner-level 改动仍以本节既有清单为准。contract、projection、material、run-input
等未执行真实 Engine 的测试，若 helper 没有 run context，每个受影响文件可在自己的 fixture
owner 内定义 private typed identity factory。test/case caller 必须使用当前 helper/call site
实际已有的显式、非敏感且足以区分 event 的上下文（例如 case label、`operation_id`、
attempt/run id 或显式 ordinal），由该 factory 构造 deterministic 且对该 event 唯一的
`SuccessfulRunnerResponseIdentity`；具体输入维度与参数名以现有 helper/call site 为准，不要求
为统一形状虚构不存在的维度。caller 再把返回的 identity 作为 required 参数显式传给 payload
helper。已有 proposal manifest / compactor Engine run context 时，caller 必须显式传入对应
`compactor_engine_run_id` 给 factory。identity 必须与同一 event 的 sibling
run/operation/attempt/manifest 语义一致，但 factory / payload helper 不得从 manifest 或其它
sibling field 反推。它只证明 strict event contract fixture 自洽，不是 provider continuity
evidence。factory / payload helper 内不得提供 default 或硬编码跨 event 共享 singleton；不得
新增跨文件万能 helper、复用相邻 event/operation/attempt identity、依赖偶然 fixture 顺序，或
用 loose dict patch 补字段。

mapping / `null` 按 durable event 自身语义冻结，不按测试是否真的运行 Engine 选择：

- `CONTEXT_COMPACTED` 始终为 mapping；
- rejected attempt 的 parse/schema/semantic/quality/budget post-success category 为 mapping；
- 只有 transport/timeout/cancel/Engine failed 且没有 successful final 时才为 `null`；
- `tests/host/test_proactive_compaction_operation.py::_rejected_payload()` 的 orphan、incomplete、
  exhausted 三个调用都通过该 helper 生成
  `failure_category="quality_check_rejected"` event，因此三者的
  `successful_response_identity` 都必须传 file-local typed mapping，不能因 projection 场景未
  运行真实 Engine 而改为 `null`。

原场景、状态转移、failure category 和行为断言不得改变。不得增加
optional/default/compatibility path，不得从 manifest、config、provider family、相邻
operation/attempt 或字符串反推 identity，不得接受 missing/extra/renamed field 或 loose
payload。若机械迁移需要超出上述改动，必须停止并退回 controller 修订 plan。

### 9.2 Engine contract/schema changes

1. 在 `runner_identity.py` 新增：
   - `ProviderRequestIdAvailability`: `PRESENT` / `UNAVAILABLE`；
   - `SuccessfulRunnerResponseIdentity`：`effective_provider`、`effective_model`、完整 `RunnerRequestIdentity`、availability、`provider_request_id: str | None`。
2. `SuccessfulRunnerResponseIdentity.__post_init__`：provider/model非空；availability与request id严格成对；request identity必须是typed instance。字段集刻意不包含endpoint、api key/ref、headers、provider request payload或response body。
3. `_FinalDecision` 增加required `response_identity`；`_classify_iteration()` 只能从同一个 `_IterationState.request_identity`、同一个 `runner_done.provider_request_id` 与本次 `AgentRunRequest.runner_spec.provider/model` 构造。normal final、content-filter final、length continuation 的最终 Runner call、force-answer final 都必须携带实际产出该 Engine terminal decision 的成功 call identity。`_handle_final_decision()` 合并 length 片段时只保留最后一次使 run 终结的 current decision identity，不得沿用首个 LENGTH call 或相邻 iteration identity。
4. `FinalAnswerData` 与 `EngineRunOutcomeFinalAnswer` 增加required `response_identity`；`_make_final_after_close()`、`run_agent_and_wait()`机械透传。不得从最后一个普通diagnostic、tool call或相邻iteration补默认。
5. failed/cancelled/suspended contract不伪造success identity；现有failure provider/client correlation字段保持其失败语义。

### 9.3 Identity taxonomy 与 Host compactor typed flow

以下 identity 不得混用、代换或从字符串反推：

| Identity | Semantic owner | 精确语义/绑定 |
|---|---|---|
| `compaction_operation_id` | Host compaction request/event | 一次 proactive 或 reactive durable operation；跨 proposal attempts 不变 |
| `compaction_attempt_number` | Host `compaction_operation` | operation 内全局 proposal 序号；每个 number 都构造并执行一个新 `AgentRunRequest` |
| `compactor_engine_run_id` | Host `LLMContextCompactor` prepared input/manifest | 根据 operation id + request digest + Host attempt number 派生，并作为该 `AgentRunRequest.run_id`；相邻 Host attempts 必须不同 |
| `RunnerRequestIdentity.attempt_id` / `execution_id` | Engine request identity | 表示 ordinary Host Run/Attempt/Execution 注入 Engine 的成对 identity；compactor 不是 ordinary Host Attempt 路径，两字段必须显式为 `None`，绝不得填 Host `compaction_attempt_number` |
| `RunnerRequestIdentity.runner_call_index` | Engine `_AsyncAgent` | 单个 `AgentRunRequest`/Engine run 内从 1 递增；新 Host proposal attempt 创建新 Engine run 并从 1 重新计数，只有同 request 内 length continuation 等真实 Runner 再调用才递增 |
| `client_correlation_id` | Engine `RunnerRequestIdentity` | 由完整 request identity canonical tuple 派生，定位一次逻辑 Runner call；不是 Host operation/attempt id |
| `provider_request_id` | provider/Runner success terminal | vendor 返回的可选 request id；缺失时只记 `unavailable`，不从 client correlation 或 manifest 伪造 |

代码已证明 `run_compaction_operation()` 在每个 Host proposal attempt 重新调用 `prepare_compactor_proposal_run_input()`；`_agent_request_vnext()` 用 `run_id=compactor_engine_run_id`、`attempt_id=None`、`execution_id=None` 构造新 request。Engine 内 `_runner_call_index` 从 0 开始且每次 Runner call 加 1。`LLMContextCompactor` 对最终 `EngineRunOutcomeFinalAnswer.finish_reason=LENGTH` 已明确 fail closed；若 Engine 在同 request 内 length continuation 后以非 LENGTH final 结束，只最后 call identity 可绑定该 accepted/rejected proposal。

1. `compaction.py` 定义 `CompactorProposal`：`candidate` + required `SuccessfulRunnerResponseIdentity`。`ContextCompactor.compact()` 返回该类型。`tests/host/fake_compaction.py` 的外层 `FakeContextCompactor` 必须在 fake owner 内显式构造安全的完整 identity 并返回 `CompactorProposal`：使用非敏感 test-only provider/model、canonical `build_runner_request_identity()`、与该次 synthetic compactor invocation 同源的 run/iteration/call identity，`attempt_id/execution_id` 显式为 `None`，且无真实 provider id 时严格使用 `UNAVAILABLE + None`。不得给 proposal/identity 字段增加 optional default、不得保留旧 return signature 或 compatibility overload；candidate-only 的 `FakeConversationCompactorVNext` 仍只拥有 vNext candidate，不伪造 Engine identity。其它 custom compactor test double 若只是变换 candidate，必须机械保留同一个 proposal identity；若模拟另一成功 Runner call，则显式构造该次 call 自己的同源 identity。
2. `LLMContextCompactor.run_prepared_compactor_proposal()`：
   - 只接受 `EngineRunOutcomeFinalAnswer`；
   - 校验 response identity 的 `request_identity.run_id == prepared_input.compactor_engine_run_id`、`request_identity.attempt_id is None`、`request_identity.execution_id is None`、effective provider/model 等于该 prepared `AgentRunRequest.runner_spec`；这两个 `None` 是 compactor Engine request contract，不表示 Host `compaction_attempt_number` 缺失；
   - parse成功返回 `CompactorProposal`；
   - Engine 成功但最终 finish reason 仍为 LENGTH、JSON parse/schema 失败时，`LLMCompactionProposalError` 都携带同一个安全 response identity，使 rejected Host attempt 不会丢失实际 success call 证据；错误消息仍走现有脱敏/截断。
3. `_CompactorProposalAttempt`、`CompactionAttemptRejected`、`CompactionOperationResult` 分别携带当前attempt或accepted attempt的response identity：
   - semantic/quality/budget/parse rejection在确有successful response时保存identity；
   - transport/timeout/cancel/Engine failed在没有成功final时为None；
   - accepted result的identity required且必须与accepted candidate、accepted attempt number、accepted manifest同一次assignment写入，禁止分别选“最后一个非空值”。
4. Host repair/multi-pass 循环的每个 `compaction_attempt_number` 都创建新 prepared input / manifest / `AgentRunRequest`，不在 Host attempt 间复用 Engine run-local identity。accepted/rejected identity 必须来自“对应 Host proposal attempt 实际成功的 Engine final”：第二 Host attempt accepted 只能带第二 request 的 identity，ordinary Run、第一 rejected attempt、相邻 compactor operation/attempt 或 LENGTH 之前的 Runner call identity 均不得泄漏。

### 9.4 Host durable payload contract

`context_events.py` 为 accepted/rejected schema使用一个strict serializer/parser，nested field命名为 `successful_response_identity`，exact shape：

```json
{
  "effective_provider": "provider-id",
  "effective_model": "provider-model-id",
  "runner_request_identity": {
    "run_id": "context-compactor-...",
    "attempt_id": null,
    "execution_id": null,
    "iteration_id": "...",
    "iteration_index": 0,
    "runner_call_index": 1,
    "client_correlation_id": "dayu-<64 lowercase hex>"
  },
  "provider_request_id_availability": "present",
  "provider_request_id": "vendor-request-id"
}
```

规则：

- `CONTEXT_COMPACTED.successful_response_identity` required 且始终为 mapping；同一event已有 `operation_id`、`accepted_attempt_number`、accepted proposal manifest ref/digest、candidate digest、compact artifact ref/digest、quality与budget，因此一次canonical event完成operation/attempt/manifest/output/response绑定。
- `CONTEXT_COMPACTION_ATTEMPT_REJECTED.successful_response_identity` 为required field但value可为mapping或null；成功final后的parse/schema/semantic/quality/budget rejection必须为mapping，只有transport/timeout/cancel/Engine failed且没有successful final时才可为null。rejected event现有 attempt number与manifest ref/digest完成同源绑定。fixture 是否执行真实 Engine 不改变该分类。
- availability=`unavailable` 时 `provider_request_id` 必须为 null；`present` 时必须非空。`runner_request_identity` 是 exact required object，`attempt_id` / `execution_id` 字段不得省略；compactor payload 中二者均必须为 null。client correlation 始终 required 并由该完整 `RunnerRequestIdentity` canonical 校验。
- Host builder 在写 event 前校验 `runner_request_identity.run_id == manifest.compactor_identity.compactor_engine_run_id`，同时校验该 manifest 的 `compaction_operation_id` / `compaction_attempt_number` 等于当前 accepted/rejected Host attempt。strict durable parser 从 exact nested object 重建 typed identity，consumer 不得从 Host attempt number 补齐 Engine `attempt_id`、从 manifest 反推 client/provider id 或 loose parse。
- payload exact-field validation拒绝endpoint、credential、api key/ref、headers、authorization、cookie、secret、完整request/response body等extra字段；fresh schema直接起库，不兼容旧payload。

### 9.5 Data flow

```text
RunnerSpec(provider/model only selected as effective call identity)
  + RunnerRequestIdentity(client correlation, iteration/call)
  + RunnerDoneData(provider request id optional)
    -> SuccessfulRunnerResponseIdentity
    -> FinalAnswerData
    -> EngineRunOutcomeFinalAnswer
    -> LLMContextCompactor CompactorProposal / typed parse failure
    -> CompactionOperationResult or CompactionAttemptRejected
    -> CONTEXT_COMPACTED / CONTEXT_COMPACTION_ATTEMPT_REJECTED
       (same operation + attempt + proposal manifest + candidate/artifact linkage)
```

### 9.6 Tests 与安全检查

- Engine contract exact fields、present/unavailable pair、完整 `RunnerRequestIdentity` canonical client id、empty provider/model 拒绝；attempt/execution 成对校验不因 compactor 语义放松。
- normal final、filtered、force-answer：identity 来自实际终结 Engine run 的当前成功 call；tool-call、ordinary/相邻 iteration 中间 identity 不能串到 final。
- Engine length continuation exact test：同一 `AgentRunRequest.run_id/attempt_id/execution_id` 不变，第一个 LENGTH call 的 `runner_call_index=1`，continuation final 的 index=2 且 client/provider id 不同；成功非 LENGTH terminal 只携带 index=2 identity。continuation 预算耗尽仍以 LENGTH 结束时，final 携带最后 call identity，由 compactor 层 fail closed，不把 index=1 当 accepted evidence。
- LLM compactor：每个 Host proposal attempt 构造新 `AgentRunRequest`、新 `compactor_engine_run_id`、runner call index 从 1 开始，且 Engine request `attempt_id/execution_id` 显式为 `None`；present/absent provider id，effective provider/model mismatch、engine run mismatch fail closed；最终 LENGTH 与 parse/schema error 都携带该 exact successful identity 进入 rejected attempt；endpoint/api ref/header canary 不出现在返回对象或异常。
- operation exact A/B/C 串线反例：ordinary Run final 身份 A；同 Session compactor Host attempt 1 实际成功 final 身份 B 后 semantic/parse/quality/budget rejected；Host attempt 2 实际成功 final 身份 C 后 accepted。断言 A/B/C 的 engine run/client correlation/provider request id 按设定不同，rejected event 只携 B 且绑定 attempt-1 manifest，accepted event 只携 C 且绑定 attempt-2 manifest，A/B 绝不出现在 accepted，A/C 绝不出现在 rejected。再以相邻 compactor operation 交换顺序重复断言。
- operation 其余 exact cases：first success accepted、provider failure、timeout/cancel、multi-pass；只有对应 Host attempt 确有 successful Engine final 的 rejected/accepted event 才携带 mapping，每个 event 都指向同 attempt manifest 和 compactor engine run。
- proactive与reactive writers都传required accepted identity；缺失时transaction失败且不写artifact/event。
- durable payload round-trip 重建 exact nested `runner_request_identity`，显式验证 null attempt/execution 与 Host `compaction_attempt_number` 不是同一字段；missing/extra/loose/renamed field 均拒绝。canary 分别放入 endpoint、credential value/ref、Authorization/header、secret 与 ordinary RunnerSpec，扫描 EventLog payload、artifact metadata、Host public diagnostic 确保不存在。
- required-contract 机械闭包：HEAD inventory 中 35 个 `FinalAnswerData(...)`、4 个 `EngineRunOutcomeFinalAnswer(...)` 与 7 个 `ContextCompactor` typed-return 文件全部通过 pytest 与 pyright；每个 direct constructor 都显式提供同源 typed identity，candidate-transforming fake 保留 paired identity。不得用 dataclass/default factory、optional field、兼容 helper signature 或 loose test fixture 让遗漏调用点继续通过。
- strict durable builder 机械闭包：先断言两个 owner signatures 的 required typed 参数无 default，再断言 8 files / 15 calls 全部显式迁移；5-file 仅参与 allowed-file delta 检查。file-local contract fixture identity 必须 deterministic、非敏感且与 sibling run/operation/attempt/manifest 语义一致；accepted 与 post-success rejection 的 mapping 不得因测试未运行真实 Engine 而降为 `null`。

### 9.7 明确 non-goals

- 不把endpoint、credential ref/value、headers或secret加入evidence，即使它们已存在于配置family校验。
- 不要求所有provider返回vendor request id；`unavailable`是合法且可审计状态。
- 不修改ordinary final answer的Host terminal payload为provider trace，不扩展CLI屏幕或Tool Trace analyzer去展示identity。
- 不执行/裁决G06真实成功compaction continuity；本slice只建立使后续真实证据可采集的owner contract。

### 9.8 Completion signal

Engine成功outcome必有安全identity；Host accepted/rejected strict payload能逐跳反查同一compactor engine run、attempt和manifest；present/unavailable及multiattempt tests全绿，secret canary零命中。

## 10. S6 — 集成、文档、CLI registry/oracle一致性与 smoke

### 10.1 Allowed files

在S1-S5生产/测试文件之外，只允许按职责触及：

- `README.md`
- `dayu/README.md`
- `dayu/host/README.md`
- `dayu/engine/README.md`
- `tests/README.md`
- `docs/host/design.md`
- `docs/engine/design.md`
- `docs/cli_ci.md`
- `docs/cli_ci_scenarios.json`
- `docs/cli_ci_oracles.json`（只允许proof/ref/适用性机械一致性；不得改accepted predicate语义）

明确不修改 `docs/reviews/wu-cli-interactive-01-calibration-adjudication-controller.md`（冻结review artifact）、`dayu/config/README.md`、`dayu/service/README.md`、`dayu/fins/README.md`，除非实际代码最终越过本计划边界；若越界必须先退回controller，不得机械扩写。

### 10.2 Docs responsibility decision

| 文档 | 决策 | 原因/内容边界 |
|---|---|---|
| 根 `README.md` | 必须更新 | 用户可见CLI参数、shared label、session selector、interactive输入/取消/pipe行为变化；只写已实现操作，不写Host内部状态机 |
| `dayu/README.md` | 必须更新 | Engine成功identity到Host compactor、Host attachment/pre-start治理是跨包稳定边界；只写当前实现摘要 |
| `dayu/host/README.md` | 必须更新 | delayed recovery、one terminal、single-flight、accepted/rejected response evidence属于Host关键机制 |
| `dayu/engine/README.md` | 必须更新 | `FinalAnswerData`/`EngineRunOutcomeFinalAnswer`新增成功response identity public contract |
| `tests/README.md` | 必须更新 | 当前文本明确记载interactive ticker/config、single-byte monitor、第二次Ctrl+C提前退出等旧测试事实；需改为新suite事实与命令 |
| `docs/host/design.md` | 必须更新 | F12用户明确要求；同时把F11/F13 owner不变量写入对应compaction章节。F10 delayed条款已在前置提交，implementation后只核对准确性，不重复写第二套 |
| `docs/engine/design.md` | 必须更新 | 成功terminal/outcome identity是Engine contract变化 |
| `docs/cli_ci.md` | 必须核对并按需更新 | accepted交互语义已大体写入；只修parser inventory、scenario/proof和实际capability描述，不改oracle |
| `dayu/config/README.md` | 不更新 | 无配置schema/default asset/overlay规则变化；只是两个CLI surface不接受explicit config |
| `dayu/service/README.md` | 不更新 | Service typed assembly与entrypoint API未变；F13由Engine和Host owner闭环 |
| `dayu/fins/README.md` | 不更新 | 不改财报存取或Fins命令 |

所有README更新前再次读取各自 `Agent更新约束`，只写代码已经实现的现状。

### 10.3 Scenario registry exact cleanup

1. 从 `docs/cli_ci_scenarios.json` 删除17条真实argv含 prompt `--config` 的accepted scenario，不改写成unknown-option oracle：
   - `prompt.P25-config-missing`
   - `prompt.P26-config-outside`
   - `prompt.P35-explicit-config-unicode-multiline`
   - `prompt.P35R-explicit-config-positive`
   - `prompt.PC-PW-R2-01`
   - `prompt.PC-PW-R2-02`
   - `prompt.PC-PW-R2-05`
   - `prompt.PC-PW-R2-07`
   - `prompt.PC-PW-R2-09`
   - `prompt.PC-PW-R2-11`
   - `prompt.PC-PW-R2-12`
   - `prompt.PC-PW-R2-13`
   - `prompt.PC-PW-R2-14`
   - `prompt.PC-PW-R2-15`
   - `prompt.PC-PW-R2-16`
   - `prompt.PC-PW-R2-17`
   - `prompt.PC-PW-R2-18`
2. 保留 `prompt.P29R-config-not-directory`、`prompt.P30-default-no-init`、`prompt.P32-existing-dayu-no-config` 这类 workspace/package 配置 precondition 场景；它们不是 removed option coverage。精确保留以下五条不带 `--config` argv 的 pairwise rows：
   - `prompt.PC-PW-R2-03`
   - `prompt.PC-PW-R2-04`
   - `prompt.PC-PW-R2-06`
   - `prompt.PC-PW-R2-08`
   - `prompt.PC-PW-R2-10`
3. 对上述五条保留 row，从 `coverage_claims.command_parameter_ids` 和 `coverage_claims.raw_stable_claims` 各删除唯一 `parameter:config:default`；不新增、改名或发明任何替代 parameter claim。每条已有的 `coverage_claims.precondition_state_ids=["init-deepseek-config-explicit"]` 与 `precondition.state_id="init-deepseek-config-explicit"` 保持不变，由 precondition 继续表达 workspace runtime config source evidence；不把系统配置来源伪装为 prompt command parameter。
4. 保留 `prompt.P11-empty-label`、`prompt.P36-label-first-tool-call`；`prompt.P37-label-followup` 把错误的 `cross-command:label-session-reuse` 改为准确的 `same-command:prompt-label-session-reuse`，保留其真实 memory/prior-turn 证据。
5. S1-S5 implementation完成后，按 `docs/cli_ci.md` 先生成/执行候选、冻结真实 evidence，再写入 shared label 双向、no-label fresh、Shift+Enter capability、whole stdin、Escape sequence、Ctrl+C、type-ahead/sole QUEUE、F10 immediate reconnect 等 F 项 scenario。不得先填 success outcome 或在无 evidence 时标 accepted。
6. F11-F13 主要由 owner-level deterministic tests 关闭 implementation finding；行为项 29 仍需后续真实 provider successful compaction evidence。由于 G06 不在本 WU，不得用 fake/deterministic smoke 把 registry 写成“实际 provider 已证明”。
7. 重新从 `build_parser()` 派生 prompt/interactive inventory、version/digest 和 mandatory counts；重算 scenario/oracle refs 与 readiness proof。`registry_status` 只能由 validation result 投影；若真实 provider/PTY evidence 环境缺失，保持 `calibration` 并在 completion report 列 external validation gap，不手工改 `ready`。

### 10.4 Oracle consistency

- `docs/cli_ci_oracles.json` 的F01-F13 accepted predicate语义保持不变。
- 只校验scope、applicable_from、scenario refs、proof counts/digest；没有直接schema要求时不修改该文件。
- I0554的三条静态owner proof继续存在：Engine blank final -> failure、Host ingest保持failed、Host public SUCCEEDED要求final answer；不新增动态fake scenario。
- G01-G07保持coverage/adjudication gap，不在本WU写accepted replacement predicate。

### 10.5 Validation plan

每次代码修改后先激活Python 3.11 venv：

```bash
source .venv/bin/activate
```

按slice运行：

```bash
pytest tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py \
  tests/cli/test_interactive_command.py tests/cli/test_interactive_composer.py \
  tests/cli/test_run_keys.py tests/cli/test_session_command.py -q

pytest tests/service/test_entrypoint_runtime_prompt_path.py \
  tests/service/test_entrypoint_runtime_interactive_path.py -q

pytest tests/host/test_recovery_orphan_classifier.py tests/host/test_recovery_scan.py \
  tests/host/test_recovery_multiprocess.py \
  tests/host/test_session_attachment_registry.py \
  tests/host/test_public_session_attachment.py \
  tests/host/test_open_host_runtime.py -q

pytest tests/host/test_compaction_terminal.py \
  tests/host/test_dispatch_scheduler.py \
  tests/host/test_compaction_operation.py \
  tests/host/test_context_compact_events.py \
  tests/host/test_engine_ingest_mapping.py -q

pytest tests/engine/contracts/test_runner_identity.py \
  tests/engine/contracts/test_agent_run.py \
  tests/engine/test_engine_event_contract.py \
  tests/engine/test_agent_phase2.py \
  tests/engine/test_agent_phase3_tool_call.py \
  tests/engine/test_package_exports.py \
  tests/engine/test_smoke_async_agent_providers.py -q

pytest tests/host/test_llm_compaction.py \
  tests/host/test_compaction_contract.py \
  tests/host/test_compact_artifact_store.py \
  tests/host/test_compaction_operation.py \
  tests/host/test_context_compact_events.py \
  tests/host/test_memory_projection.py \
  tests/host/test_compaction_terminal.py \
  tests/host/test_run_input_builder.py \
  tests/host/test_compact_material.py \
  tests/host/test_proactive_compaction_operation.py \
  tests/host/test_dispatch_scheduler.py \
  tests/host/test_engine_ingest_mapping.py \
  tests/host/test_compact_pipeline.py \
  tests/host/test_compaction_cancellation_scope.py \
  tests/host/test_active_cancel_dispatch.py \
  tests/host/test_effective_execution_config.py \
  tests/host/test_open_host_runtime.py \
  tests/host/test_per_run_tool_selection.py \
  tests/host/test_phase5_local_execution_integration.py \
  tests/host/test_public_compact_smoke.py \
  tests/host/test_public_retry_replay.py \
  tests/host/test_recovery_dispatch.py \
  tests/host/test_submit_followup_public_contract.py \
  tests/host/test_watch_session_events.py \
  tests/host/test_package_exports.py \
  tests/host/test_import_boundary.py -q

pytest tests/service/test_entrypoint_runtime_interactive_path.py -q
```

`tests/host/public_smoke_support.py`、`recovery_support.py`、`stress_support.py`
与 `transient_stream_support.py` 是 test-support module，不把“pytest 对无 test module
返回 no-tests”当验证。它们由下方完整 `tests/host` 回归和全量 pyright 关闭；回归必须
实际收集其消费者，包括 recovery multiprocess、host production stress 与 transient
delta/watch paths，不能只做 import smoke。

`tests/host/fake_compaction.py` 同样是不可由 pytest 直接收集的 test-support module；
其行为由上方已列消费者测试覆盖，typed return 由全量 pyright 关闭。
`FakeContextCompactor` 的 identity 构造 owner 与 candidate-transforming fake 的 paired
identity 保留规则以 §9.3 为唯一真源，本 validation 层不得重算或扩展这些规则。

集成/回归：

```bash
pytest tests/cli tests/service/test_entrypoint_runtime.py \
  tests/service/test_entrypoint_runtime_prompt_path.py \
  tests/service/test_entrypoint_runtime_interactive_path.py -q

pytest tests/host/test_context_anchor.py tests/host/test_context_budget.py \
  tests/host/test_context_compact_events.py tests/host/test_memory_projection.py \
  tests/host/test_compaction_terminal.py tests/host/test_run_input_builder.py \
  tests/host/test_compact_material.py \
  tests/host/test_proactive_compaction_operation.py \
  tests/host/test_compaction_operation.py \
  tests/host/test_dispatch_scheduler.py tests/host/test_recovery_scan.py \
  tests/host/test_recovery_multiprocess.py \
  tests/host/test_public_session_attachment.py \
  tests/host/test_open_host_runtime.py tests/host/test_engine_ingest_mapping.py -q

pytest tests/engine tests/host -q
```

上述 S5 focused Host 命令与 full affected Host/Engine 回归都必须实际收集完整 8-file / 15-call
builder closure；不得把 5-file allowed delta 误当完整迁移范围，也不得只以 full suite 的
间接通过替代 focused failure 定位。8 个文件的改动只验证 owner required typed argument、
exact payload fixture 与 frozen mapping/null 分类是否闭合，不改变原测试断言所代表的业务
场景。无 run context helper 的 caller 必须使用当前 helper/call site 实际已有的显式、非敏感且
足以区分 event 的上下文（例如 case label、`operation_id`、attempt/run id 或显式 ordinal），
由所在文件的 private typed factory 构造 deterministic、event-unique identity，再作为 required
参数显式传给 payload helper；具体输入维度与参数名以现有 helper/call site 为准，不要求虚构
不存在的维度。已有 manifest / compactor Engine run 时 caller 必须显式传对应 run id 给 factory。
focused tests
还必须证明 helper 内无 default、无硬编码共享 singleton、无跨文件万能 helper或从
manifest/sibling fields 反推，并断言 identity 与 sibling run/operation/attempt/manifest
一致。`test_proactive_compaction_operation.py` 的 orphan/incomplete/exhausted 三个调用都必须
产生 `quality_check_rejected` event，且 `successful_response_identity` 全部为 mapping，不接受
`null`。

Smoke分三层，不能互相冒充：

1. deterministic public-path pytest smoke：shared label双向、pipe one-shot、Host delayed recovery、single-flight、identity payload round-trip。
2. POSIX PTY smoke：真实PTY exact bytes与terminal restore；非POSIX记录capability/skip，不拿pipe代替。
3. 按 `docs/cli_ci.md` 执行有授权的真实CLI scenario并冻结evidence；本WU不创建新通用harness。真实provider successful compaction若未执行，只报告行为项29/G06外部证据未关闭，不用fake替代。

第三次 amendment 放行的两个既有 utils smoke 不新增测试，也不承担 coverage 指标；required
identity 迁移必须由全量 pyright、post-inventory、后续 code review 与以下既有 smoke 验证共同
关闭。命令不得改变 suite、provider 配置或输出 oracle：

```bash
python utils/smoke_host_public_awaiting_entrypoint.py \
  --workspace-root workspace/tmp/wu-cli-interactive-02-s5-awaiting-identity

DEEPSEEK_API_KEY=test-provider-key \
python utils/smoke_host_public_conversation_memory_scenarios.py \
  --suite memory-reactive-compact \
  --log-level CRITICAL

DEEPSEEK_API_KEY=test-provider-key \
python utils/smoke_host_public_conversation_memory_scenarios.py \
  --suite memory-compact-fallback \
  --pressure-mode auto \
  --log-level CRITICAL
```

awaiting smoke 必须保持既有 11-phase public Host/Service path 与最终 pass marker；
`memory-reactive-compact` 必须覆盖 accepting compactor outcome 与 ordinary final event，
`memory-compact-fallback` 必须覆盖 rejecting compactor outcome 与 ordinary final event。三条命令的
既有场景、stdout marker、CLI oracle 和 provider assembly 断言不得改变；本次迁移只让它们在
required typed contract 下继续成立。

完整类型检查：

```bash
python -m pyright dayu/ tests/ utils/
```

S5 implementation 前后都重跑 required-constructor / typed-return inventory：

```bash
rg -n --glob '*.py' '\bFinalAnswerData\s*\(' tests utils
rg -n --glob '*.py' '\bEngineRunOutcomeFinalAnswer\s*\(' tests utils
rg -n --glob '*.py' \
  '\b(ContextCompactor|FakeContextCompactor|prepare_compactor_proposal_run_input|run_prepared_compactor_proposal)\b' \
  tests utils
rg -n --glob '*.py' '\bbuild_context_compacted_payload\s*\(' tests/host
rg -n --glob '*.py' \
  '\bbuild_context_compaction_attempt_rejected_payload\s*\(' tests/host
```

除逐类核对 calls/files 外，pre/post 都必须执行以下完整五类 pattern 去重检查；该检查直接构造
27-file identity/typed-return closure 与 8-file builder closure，验证 exact overlap、builder-only
set difference 和 33-file union，不得只把 allowed-file delta 相加：

```bash
identity_files="$(
  {
    rg -l --glob '*.py' '\bFinalAnswerData\s*\(' tests utils
    rg -l --glob '*.py' '\bEngineRunOutcomeFinalAnswer\s*\(' tests utils
    rg -l --glob '*.py' \
      '\b(ContextCompactor|FakeContextCompactor|prepare_compactor_proposal_run_input|run_prepared_compactor_proposal)\b' \
      tests utils
  } | sort -u
)"
builder_files="$(
  {
    rg -l --glob '*.py' '\bbuild_context_compacted_payload\s*\(' tests/host
    rg -l --glob '*.py' \
      '\bbuild_context_compaction_attempt_rejected_payload\s*\(' tests/host
  } | sort -u
)"
overlap_files="$(
  comm -12 \
    <(printf '%s\n' "$identity_files") \
    <(printf '%s\n' "$builder_files")
)"
builder_only_files="$(
  comm -13 \
    <(printf '%s\n' "$identity_files") \
    <(printf '%s\n' "$builder_files")
)"
mechanical_files="$(
  {
    printf '%s\n' "$identity_files"
    printf '%s\n' "$builder_files"
  } | sort -u
)"

test "$(printf '%s\n' "$identity_files" | wc -l | tr -d ' ')" -eq 27
test "$(printf '%s\n' "$builder_files" | wc -l | tr -d ' ')" -eq 8
test "$(printf '%s\n' "$overlap_files" | wc -l | tr -d ' ')" -eq 2
test "$(printf '%s\n' "$builder_only_files" | wc -l | tr -d ' ')" -eq 6
test "$(printf '%s\n' "$mechanical_files" | wc -l | tr -d ' ')" -eq 33
diff -u \
  <(printf '%s\n' \
    tests/host/test_compaction_operation.py \
    tests/host/test_dispatch_scheduler.py) \
  <(printf '%s\n' "$overlap_files")
diff -u \
  <(printf '%s\n' \
    tests/host/test_compact_material.py \
    tests/host/test_compaction_terminal.py \
    tests/host/test_context_compact_events.py \
    tests/host/test_memory_projection.py \
    tests/host/test_proactive_compaction_operation.py \
    tests/host/test_run_input_builder.py) \
  <(printf '%s\n' "$builder_only_files")
```

以 §9.1 的三组 HEAD 基线为 closure 起点：第一 amendment 的 25-file tests
identity/typed-return inventory 与第三次 amendment 的 2-file utils delta 必须合并重现
`FA 37 calls / 21 files`、`OA 6 calls / 4 files`、`CR 7 files`、union `27 files`；两个 utils
文件必须仍与既有 25-file tests closure 无重叠，且 utils 仍无 CR hit。durable builder
pre-inventory 必须重现 accepted
`8 calls / 6 files`、rejected `7 calls / 4 files`、union `8 files` 与表中 exact paths。
两组闭包的 overlap 必须精确为 `test_compaction_operation.py` 与
`test_dispatch_scheduler.py`，builder-only set difference 必须为上述 6 files，完整 S5 枚举
mechanical union 必须重现 `27 + 8 - 2 = 33 files`。第二次 amendment 新增 allowed-file delta
仍是 5 files；`test_context_compact_events.py` 是早已允许但不在 27-file identity closure 的第六个
builder-only file，allowed delta 不得改称 6。implementation 后重跑完全相同的 inventory；新增
identity/typed-return hit 只能位于 S5 allowed tests/utils，新增 builder hit 只能位于 S5 allowed owner tests，
任何新文件 hit、遗漏的 8-file / 15-call 迁移或无法按 exact payload contract 迁移的调用点
都必须停止并退回 controller，不得在范围外修改。2-file utils delta 与 5-file builder delta
都只参与对应 allowed-file scope 检查。pyright 必须证明不存在漏传 required field、
旧 `ConversationCompactOutputVNext` return annotation 或 candidate/proposal 混用；不得用
`type: ignore`、仅为掩盖不匹配的 cast、optional/default、manifest/config 反推、loose
payload 或兼容 overload 消音。

覆盖率：对所有S1-S5新增/修改生产文件运行branch coverage，使用coverage JSON逐文件检查 `percent_covered >= 80`，不能只看aggregate；未达到则补owner/反例/race tests，不加pragma或排除。两个既有 `utils/` smoke 文件按项目规则不新增测试、无 coverage 要求，但必须通过上述全量 pyright、post-inventory、相关既有 smoke 与后续 code review；该豁免不得扩散到 production/tests。

Registry/docs检查：

- `python -m json.tool docs/cli_ci_scenarios.json` 与 `docs/cli_ci_oracles.json`；
- 精确查询五条保留 pairwise row，断言它们全部存在，`command_parameter_ids` / `raw_stable_claims` 都不含 `parameter:config:default`，且两处 `init-deepseek-config-explicit` precondition 仍存在；查询返回数不是 5 或任一断言不满足即失败，不用替代 parameter claim 凑 count；
- 从 `build_parser()` 重新生成并比对inventory，检查无dangling oracle/scenario refs；
- `rg` 确认prompt/interactive生产/帮助/README/registry无removed参数声称，旧 `cli.prompt.`/`cli.interactive.` 不在新owner/测试期望中；
- `git diff --check`；检查最终diff只包含本WU allowed files。

Secret/provider payload检查：

- owner tests用不同canary注入endpoint、credential value/ref、Authorization、headers、cookie、secret和ordinary/neighbor identity；
- 扫描 EventLog hot/cold payload、compact artifact descriptor、error/log、Host public event与smoke artifact；
- 允许字段仅为effective provider/model、client correlation、provider request present/unavailable及operation/attempt/manifest/output linkage；任一endpoint/credential/header/secret命中即失败；
- 不打印环境变量值，不运行会上传workspace内容的工具。

### 10.6 Completion signal

S1-S5 focused与整合回归全绿，pyright零新增/扩散错误，所有modified production files覆盖率>=80，JSON/proof/ref/secret检查通过，README/design准确描述已实现现状；真实环境未覆盖项被明确分类而未伪造。

## 11. Contract、schema 与 public interface 变更汇总

### 11.1 CLI public contract

- 删除 prompt/interactive `--config`；interactive删除 `--ticker`；session resume Agent mode也不能借共享parser绕过。
- prompt `--ticker`保留。
- `--label`成为prompt/interactive共享alias；session label selector删除`--kind`，仍用`--mode`选择现有输入方式。
- nonTTY interactive变为one batch/one Run/one process terminal。
- TTY active Run保持composer，Enter产生单个QUEUE，Escape/Ctrl+C行为按S2状态机。

### 11.2 Host internal/public durable contract

- recovery scan result增加typed `retry_not_before/next_reconcile_at`，不是durable schema。
- scheduler增加private per-Session pre-start flight，不改变Host public API。
- 新增一个 compaction-operation 专用 trigger-aware transaction-local terminal/CAS owner；proactive/reactive writer 共享，不增加 DB schema。
- `CONTEXT_COMPACTED` fresh payload schema required `successful_response_identity`。
- `CONTEXT_COMPACTION_ATTEMPT_REJECTED` fresh payload schema required nullable `successful_response_identity` field。
- `successful_response_identity.runner_request_identity` 显式持久 `run_id/attempt_id/execution_id/iteration_id/iteration_index/runner_call_index/client_correlation_id`；compactor 的 attempt/execution 必须为 null，Host `compaction_attempt_number` 继续由外层 event/manifest 独立表达。
- 不做旧库/旧event兼容读取；按AGENTS schema规则全新起库测试。

### 11.3 Engine public contract

- 新增 `ProviderRequestIdAvailability`、`SuccessfulRunnerResponseIdentity`。
- `FinalAnswerData.response_identity` 与 `EngineRunOutcomeFinalAnswer.response_identity` required。
- package root只导出真实新public types；不保留旧构造签名compatibility defaults。

## 12. Risk、反例与无阻塞 open questions

### 12.1 Residual risk 分类

| 类别 | 风险 | 计划内控制 | 完成后残余 |
|---|---|---|---|
| terminal capability | 不同终端无法区分Shift+Enter/Enter | 只支持证实的exact sequence并记录bytes/capability | 未知终端sequence不宣称支持，属于允许variant |
| input race | terminal、Enter、Escape、SIGINT同批完成 | generation + 固定terminal-first裁决 + sole tasks | OS/terminal实现差异由PTY/Windows证据继续观察 |
| queue lifecycle | exit-after-cancel时已有durable queued follow-up | 停止新输入，不取消sole submit/queued Run，等待当前cancel terminal与本invocation已accepted sole queue terminal收口 | G01跨进程queued reconnect仍不裁决；本 invocation 不留无 label fresh Session 永久 queued |
| recovery clock | wall clock/heartbeat临界点 | `<`/`>=`清晰边界、UTC deadline、fresh now、CAS | 极端系统时钟回拨只会保守不恢复，不允许提前takeover |
| process proof | pid存在但无identity | 继续inconclusive，不恢复 | G02完整矩阵仍是gap |
| compaction concurrency | proactive/reactive late result与first terminal竞争 | 同一 trigger-aware Host owner 在同 write transaction 做 fresh projection guard，loser 在 artifact/event/fallback/start 前 no-op | 已损坏旧DB不兼容；fresh schema fail closed |
| live/fresh owner | in-memory flight在crash时消失 | durable request/manifests + fresh RW recovery | 不提供跨opener共享single-flight |
| provider evidence | provider不返回request id | explicit unavailable + effective identity + canonical client correlation | 实际provider成功证据仍需G06/行为29后续run |
| secrets | RunnerSpec含endpoint/credential/header | 窄identity type、exact payload、canary扫描 | provider/model本身必须继续由配置schema保证为安全identity字符串 |
| coverage/platform | POSIX PTY与Windows差异 | POSIX真实PTY + Windows既有CI owner boundary | 本地无法替代真实Windows runner证据 |

### 12.2 Open questions

无阻塞open question。以下决策已经在本计划固定，implementation不得自行改向：

- shared slot使用全新 `cli.agent.<label>`，不兼容旧namespace；
- session `--kind`随双namespace一起删除；
- exact Shift+Enter只识别当前依赖已证明保留raw data的 `\x1b[27;2;13~`；
- active Run默认只允许一个pending QUEUE follow-up；
- idle 非空/纯空白 draft 的首次 Ctrl+C 只清空，不登记 exit；空 draft 后再以连续两次 Ctrl+C 完成 exit intent 与 cleanup+130；
- active exit-after-cancel 已为 true 后的第三次及更多 Ctrl+C 均 no-op，已 accepted sole QUEUE 必须恰好执行一次并收口后才退出；
- delayed recovery是每attachment一次target task，不是poller；
- pre-start single-flight是scheduler内event-loop flight，不是lease/mutex；
- F11 两路 terminal writer 已由代码确认为 `dispatch.py` 与 `engine_ingest.py`，两者必须复用同一 compaction terminal/CAS owner；
- `session resume --mode interactive` 的 `_resume_interactive_ticker()` 与调用路径已在当前代码确认存在，S1 按已定计划删除，无 OQ。
- S5 按 S4 -> S5 依赖顺序做 required typed identity payload 扩展，S4 不预埋 optional identity；
- Host compaction attempt、Engine request attempt/execution、Engine runner call、compactor engine run/client/provider identity 按 §9.3 精确区分；
- compactor success evidence不包含endpoint、credential或headers。

PTY 环境依赖已按 §12.1 分类为 allowed platform/capability variant：POSIX 执行真实 PTY，非 POSIX 明确 skip/capability 并保留 Windows non-TTY owner boundary；它不是 blocking open question，也不得用 pipe 伪装 PTY 证据。

若implementation直接证据否定其中任一前提，必须停止该slice并回到controller review；不能用fallback/兼容shim继续。

## 13. Slice completion checklist

### S1

- [ ] F01-F04 exact changes完成，无旧参数/namespace兼容。
- [ ] parser/help/command/slot/session registry owner tests通过。
- [ ] prompt/interactive shared label与unlabeled fresh identity通过。

### S2

- [ ] F05-F09 exact changes完成，TTY单stdin owner。
- [ ] whole stdin、invalid UTF-8、literal `0x04`通过。
- [ ] Escape/CSI/Alt/paste、idle nonblank/blank Ctrl+C、active Ctrl+C third+-no-op、Ctrl+D 与 type-ahead race 通过。
- [ ] sole QUEUE durable accepted exactly once，exit-after-cancel 等待 current cancel + queued terminal，无 label fresh Session 无永久 queued，零 STEER 通过。

### S3

- [ ] F10 deadline由recovery owner同源产生。
- [ ] close/cancel/task/lease tests通过。
- [ ] immediate fresh SIGKILL复现最终同Run恢复且只有一个new Attempt。

### S4

- [ ] F11 proactive/reactive 每 operation 一个 terminal，两路 writer 复用同一 trigger-aware transaction-local owner，late result 在 artifact/event/fallback/start 前 diagnostic-only/no-op。
- [ ] F12每live RW Session一个flight，signals coalesce，periodic保留。
- [ ] fresh owner同operation恢复、live owner不resume。

### S5

- [ ] Engine final/outcome required success identity。
- [ ] `dayu/host/context_events.py` owner 先给两个 strict builder 增加无 default 的 required typed `successful_response_identity` 参数，再机械迁移全部 8 files / 15 calls；5-file delta 只表示新增 allowed-file boundary。
- [ ] §9.1 第一 amendment 的 25-file tests identity/typed-return closure 完整保留；第三次 amendment 的 2-file utils delta 闭合后，完整 tests+utils inventory 重现 FA 37 calls / 21 files、OA 6 calls / 4 files、CR 7 files、27-file union，utils 无 CR hit且与既有 25-file tests closure 无重叠。
- [ ] durable builder inventory 重现 8 accepted calls / 6 files、7 rejected calls / 4 files、8-file union；它与 27-file identity/typed-return closure 的 overlap 精确为 `test_compaction_operation.py`、`test_dispatch_scheduler.py`，builder-only set difference 精确为 6 files，其中 `test_context_compact_events.py` 早已属于 S5 allowed owner tests，其余 5 files 才是第二次 amendment 新增 allowed-file delta；完整五类 pattern 去重重现 `27 + 8 - 2 = 33` files。
- [ ] `utils/smoke_host_public_awaiting_entrypoint.py` 精确迁移 1 个 `FinalAnswerData(...)`，`utils/smoke_host_public_conversation_memory_scenarios.py` 精确迁移 1 个 `FinalAnswerData(...)` 与 2 个 `EngineRunOutcomeFinalAnswer(...)`；每个 identity 都从该 smoke invocation 已有的 `AgentRunRequest` 直接取得 run/attempt/execution 与 `runner_spec.provider/model`，显式使用该 synthetic 单调用的 deterministic iteration id、index 0/call 1 和 `UNAVAILABLE + None`，不从 config/manifest/相邻 event 推断。
- [ ] 两个 utils 只增加精确 imports、file-local private 常量/窄 helper、required identity 参数构造/透传；零跨文件万能 helper，零 default/optional/compatibility，且 smoke scene/suite、分支、provider 配置、输出/marker、CLI oracle、artifact/EventLog 断言与异常语义零变化。
- [ ] 两个 utils 不新增测试且不计 coverage；全量 `python -m pyright dayu/ tests/ utils/`、post-inventory、public awaiting smoke、`memory-reactive-compact`、`memory-compact-fallback` 与后续 code review 全部通过。
- [ ] contract/projection/material/run-input 等未执行真实 Engine 且 helper 无 run context 时，caller 使用当前 helper/call site 实际已有的显式、非敏感且足以区分 event 的上下文（例如 case label、`operation_id`、attempt/run id 或显式 ordinal），由该文件 private typed factory 生成 deterministic、event-unique typed identity，再作为 required 参数显式传给 payload helper；具体输入维度与参数名以现有 helper/call site 为准，不要求虚构不存在的维度；已有 manifest / compactor Engine run 时 caller 显式传对应 run id 给 factory。
- [ ] file-local identity factory / payload helper 内零 default、零硬编码共享 singleton、零跨文件万能 helper、零 manifest/sibling 反推；identity 与同 event 的 sibling run/operation/attempt/manifest 语义一致，且不冒充 provider continuity evidence。
- [ ] mapping/null 分类按 event 语义冻结：`CONTEXT_COMPACTED` 恒为 mapping；post-success parse/schema/semantic/quality/budget rejected 为 mapping；仅 transport/timeout/cancel/Engine failed no-final 为 `null`；proactive orphan/incomplete/exhausted 三个调用均生成 `quality_check_rejected` event，三者 `successful_response_identity` 均为 mapping。
- [ ] `FakeContextCompactor` 显式构造安全 required identity，其它 direct constructor/typed-return 调用点只做同源机械迁移，零 optional default/兼容 signature。
- [ ] Host accepted/rejected payload 按 operation id + Host attempt number + manifest + exact compactor Engine final identity 同源绑定。
- [ ] RunnerRequestIdentity attempt/execution、runner_call_index、Host operation/attempt、compactor engine run/client/provider id 区分测试通过。
- [ ] present/unavailable、final LENGTH fail-closed、failure/repair/multiattempt/ordinary+neighbor A/B/C 串线反例通过。
- [ ] endpoint/credential/header/secret canary零泄漏。

### S6

- [ ] focused/full affected tests、pyright、per-file coverage>=80。
- [ ] README/design职责更新完成。
- [ ] 17条 prompt config argv scenarios 移除；五条指定 pairwise row 保留且仅删除两处 `parameter:config:default`，`init-deepseek-config-explicit` precondition 保留；P37 claim 纠正，新 scenario 只在真实 evidence 后登记。
- [ ] oracle语义未改变；I0554保持静态证明；G01-G07未裁决。
- [ ] JSON/proof/ref/diff/secret checks通过。

## 14. Implementation completion report 格式

implementation gate完成时，Agent必须按以下格式报告；不得只说“tests passed”：

```text
Gate: implementation complete / ready for implementation review
Work unit: wu-cli-interactive-02-conformance-fixes
Branch / PR base: <branch> / main

Scope delivered:
- S1 / F01-F04: <owner contract与可观察结果>
- S2 / F05-F09: <composer/input/cancel/queue结果>
- S3 / F10: <recovery deadline/CAS/result>
- S4 / F11-F12: <terminal/single-flight结果>
- S5 / F13: <Engine->Host identity与payload结果>
- S6: <docs/registry/smoke结果>

Contract/schema changes:
- CLI: <removed/changed interfaces>
- Engine: <required types/fields>
- Host durable: <fresh payload fields与no-compat声明>

Files changed:
- Production: <按层列出>
- Tests: <按owner列出>
- Docs/registry: <按职责列出>

Validation:
- Focused tests: <命令、pass/fail/count>
- Integration/smoke: <命令、真实/PTY/deterministic分类与结果>
- Pyright: <命令与结果>
- Coverage: <每个modified production file百分比，全部>=80>
- Registry/JSON/ref proof: <结果>
- Secret/provider payload canary: <结果>

Docs decision:
- Updated: <文件与职责>
- Checked/no update: <文件与理由>

Residual risks / not covered:
- correctness: <none或具体项>
- concurrency/recovery: <none或具体项>
- platform/external provider evidence: <具体项>
- explicitly out of scope: G01-G07、interactive resume/commands、独立Fins oracles等

Compatibility statement:
- no old args / namespace / schema compatibility

Commit / push / PR:
- 仅在后续对应gate获授权后报告；plan gate不得执行
```

## 15. Plan review controller 裁决与 fix trace

本节只记录 controller 给定的唯一修订范围与本 plan 的 fix 状态；不修改两份 review artifact，不代替后续独立 re-review。

| Review item | Controller decision | Fix status | Plan 落点/理由 |
|---|---|---|---|
| MiMo-001 | `accepted` | 已修复 | §1.2、§3.1、§8.1-§8.7：F11 改为 all-trigger invariant，纳入 `engine_ingest.py`，列全两路 writer，用一个 Host compaction terminal/CAS owner 在 artifact/event/fallback/start 前裁决，并加 reactive 并发/幂等重入反例与 exact tests；不扩成通用 framework |
| MiMo-002 / MiMo-004 | `accepted` | 已修复 | §6.5-§6.7：idle 非空/纯空白首次 Ctrl+C 只清 draft，空 draft 再以两次 Ctrl+C 登记/执行 exit；`exit_after_cancel=true` 后第三次及以后 no-op |
| DS F-01 | `accepted-clarification-only` | 已修复 | §6.5-§6.7：保持现有“等待 accepted sole QUEUE terminal”语义，明确 F08+F09 exactly-once、second Ctrl+C 不 cancel queued Run，并加无 label fresh Session 确定性反例；不改为 review 建议的“留 queued 给 fresh writer” |
| DS F-02 / MiMo-005 | `accepted` | 已修复 | §9.2-§9.6、§11.2：分开 Engine request attempt/execution、runner call index、Host operation/attempt、compactor engine run/client/provider identity；每 Host proposal attempt 是新 Engine request，同 request 的 LENGTH continuation 才递增 call index，最终 LENGTH fail closed，并加 ordinary/rejected/accepted A/B/C exact tests |
| DS F-03 | `accepted` | 已修复 | §10.3：精确保留 `prompt.PC-PW-R2-03/-04/-06/-08/-10`，仅从两个 claim 数组删除 `parameter:config:default`，不发明替代 claim，保留 `init-deepseek-config-explicit` precondition |
| MiMo-003 | `rejected-with-reason` | 不适用 | §8.2.2、§8.6、§9 开头：禁止 S4 预埋 optional identity；S5 按依赖顺序在 terminal winner writer 上做 required typed payload 扩展，guard 签名无需变更 |
| DS F-04 | `non-finding` | 证据失效 | 两路 review 已确认原 plan 的全部测试路径存在；§10.5 删除“若路径不存在”的多余注释，不新增 fallback mapping |
| OQ-01 | `closed-by-code-evidence` | 已修复 | 当前 `dayu/cli/commands/session.py` 确认 `_resume_interactive_ticker()` 及调用存在；§5.2.5 继续精确要求删除 |
| OQ-02 | `closed-by-MiMo-001` | 已修复 | reactive writer 已纳入同一 F11 guard 和 S4 allowed files/tests |
| PTY / OQ-03 | `allowed-variant` | 已分类 | §10.5、§12.1-§12.2：POSIX 真实 PTY，非 POSIX 记录 capability/skip，不用 pipe 替代；不阻塞 plan re-review |

第二次 S5/F13 durable-builder amendment review 裁决与 accepted-finding fix：

| Review item | Controller decision | Fix status | Plan 落点/理由 |
|---|---|---|---|
| MiMo-001 | `accepted-medium-clarification` | 已修复 | §9.1、§10.5、§13：先由 `context_events.py` owner 增加两个 required typed builder 参数，再迁移完整 8 files / 15 calls；5-file 仅是 allowed-file delta |
| MiMo-002 | `accepted-concern / rejected-null-conclusion` | 已修复 | §9.1、§9.4、§10.5、§13：按 event semantic 冻结 mapping/null；proactive `quality_check_rejected` 必须 mapping，明确拒绝 reviewer 的三场景 `null` 建议 |
| DS finding 2 | `accepted-medium-with-owner-correction` | 已修复 | §9.1、§10.5、§13：未运行真实 Engine 时由 file-local fixture owner 构造 deterministic、非敏感、typed identity，并保持 sibling 语义一致；不冒充 provider continuity evidence |
| DS finding 1 | `rejected-historical-trace` | 不适用 | §16 `planned-new` 是 accepted original plan gate 的历史 validation trace，保持原文，不改写为当前工作树状态 |
| MiMo re-review finding 001 | `accepted-low` | 已修复 | Proposal §6 已将当前 amendment 冻结的 file-local identity/fixture 风险分类改为 `fixed in current amendment`；plan §9.1/§10.5/§13 是对应规则真源 |
| MiMo re-review finding 002 | `accepted-low` | 已修复 | §9.1、§10.5、§13 明确 orphan/incomplete/exhausted 三个调用均生成 `quality_check_rejected` event，三者 identity 均为 mapping |
| AgentDS re-review finding 001 | `accepted-low-with-strategy` | 已修复 | §9.1、§10.5、§13 冻结 caller 的实际显式上下文 → file-local private typed factory → required identity 参数的数据流；已有 run context 显式传对应 run id，禁止 helper default、共享 singleton、跨文件万能 helper与反推 |
| MiMo final finding 001 | `rejected-duplicate-inventory` | 不适用 | §9.1 已保留第一 amendment 的完整 25-file closure、本 amendment 的 8-file builder inventory 与 5-file delta，§10.5 要求重跑去重 inventory；不复制第三份 30-file 全清单 |
| MiMo final finding 002 | `rejected-already-covered` | 不适用 | §9.1、§10.5、§13 已冻结 event uniqueness、sibling consistency、required argument 及 default/共享 singleton/反推禁止项；无需新增抽象 |
| AgentDS final finding 001 | `accepted-low-clarification` | 已修复 | §9.1、§10.5、§13 将写死的 `case_label` / `operation_label` / `attempt_label` 改为 caller 使用当前 helper/call site 实际已有的显式、非敏感、足以区分 event 的上下文；不要求虚构不存在的维度，仍保持 deterministic、event-unique、sibling-consistent，并继续禁止 default、共享 singleton、跨文件万能 helper及 manifest/sibling 反推 |

Controller adjudication §3、§6 与 §7 的 accepted findings 在 plan artifact 层面均已修复，没有
unclassified residual risk。第二次 amendment 是否通过 review loop 必须由 MiMo 与 AgentDS
后续 simultaneous independent final dual re-review durable artifacts 裁决；本次不生成
re-review artifact，不创建 accepted plan amendment commit，也不进入 implementation。

上述段落与既有表格是第二次 amendment 的 accepted 历史 trace，保持原文，不重写已有 review
artifact。第三次 S5/F13 tests+utils identity closure premise invalidation 由 Controller 在 accepted
HEAD `e7f578dc7bdfafb51a859be2db584300e08f81fb` 直接复核，本轮只追加以下 amendment trace：

| Review item | Controller decision | Fix status | Plan 落点/理由 |
|---|---|---|---|
| utils required-identity closure omission | `accepted-plan premise invalidation` | 已修复 | §9.1：补入 `utils/smoke_host_public_awaiting_entrypoint.py` 的 `FA(1)` 与 `utils/smoke_host_public_conversation_memory_scenarios.py` 的 `FA(1)+OA(2)`；冻结完整 tests+utils `FA 37/21`、`OA 6/4`、`CR 7 files`、union 27，utils 无 CR hit且两文件与既有 25-file tests closure 无重叠 |
| S5 mechanical total union | `accepted arithmetic correction / superseded by full-set recomputation` | 已修复 | §9.1、§10.5、§13：完整集合按 27-file identity/typed-return closure 与 8-file builder closure、2-file overlap 去重为 `27 + 8 - 2 = 33`；第二次 amendment 的 5-file allowed-file delta 原样保留，不再误用于 union 算术 |
| utils semantic owner / exact delta | `accepted owner-preserving expansion` | 已修复 | §9.1、§13：Engine success terminal identity contract 仍是 owner；两个 smoke consumer 只从各自 `AgentRunRequest` 的显式 run/attempt/execution 与 `runner_spec.provider/model` 构造/透传 required typed identity，provider id 用 `UNAVAILABLE + None`；禁止 config/manifest 推断、共享万能 helper与场景/输出/oracle/provider 配置变化 |
| utils validation closure | `accepted validation correction` | 已修复 | §10.5、§13：pre/post inventory 扩至 `tests utils`，全量 pyright 保持 `dayu/ tests/ utils/`；两个 utils 按项目规则不新增测试/coverage，但必须通过相关既有 smoke 与后续 code review |

第三次 amendment initial dual review 与 Controller 算术裁决只追加以下 fix trace；MiMo/AgentDS
review 和 Controller adjudication artifacts 均保留原文，不把 AgentDS 的错误 pass 当作 acceptance：

| Review item | Controller decision | Fix status | Plan 落点/理由 |
|---|---|---|---|
| MiMo finding 001 | `accepted-medium-with-terminology-correction` | 已修复（`accepted-fixed`） | §9.1、§10.5、§13、§15：total union 修为 33，显式冻结 27/8/2 overlap、6-file builder-only set difference 与 5-file allowed-file delta 的术语边界；§10.5 用完整五类 pattern 直接去重验证 33 |
| AgentDS A5 / final pass | `rejected-set-arithmetic` | 不适用 | AgentDS 将 5-file 新增 allowed-file delta 当成完整 builder-only set difference，未验证 27-file 与 8-file closure 的实际 2-file overlap，因此该 arithmetic conclusion 被拒绝；其关于 exact 2-file/4-call、semantic owner、identity source、cardinality、`UNAVAILABLE + None`、scope 与 validation 的其它直接证据继续接受 |

本轮裁决与两路 review 的历史 artifacts 保持不变：

- `docs/reviews/gateflow-wu-cli-interactive-02-s5-utils-closure-amendment-review-adjudication-20260802.md`
- `docs/reviews/plan-review-20260802-000526.md`
- `docs/reviews/plan-review-20260802-000107.md`

本轮 amendment proposal 路径为
`docs/reviews/wu-cli-interactive-02-s5-f13-utils-closure-plan-amendment-proposal-codex.md`。
本轮不生成 plan review/re-review artifact，不执行 implementation，不创建 accepted plan amendment
commit，也不 push/PR。当前唯一 next gate 是 MiMo 与 AgentDS simultaneous independent
re-review；两路独立 durable re-review artifacts 与 Controller 最终裁决完成前不得恢复 S5
implementation。

## 16. Plan gate closeout

- Goal：已按用户确认的F01-F13冻结语义转译为code-generation-ready slices。
- Scope：一个work unit、一个后续PR，不增删F项，不纳入G01-G07。
- Review target：Gateflow controller re-review。
- Validation plan：owner tests、race/barrier、PTY/pipe、multiprocess、集成、pyright、逐文件coverage、registry与secret检查均已明确。
- Docs decision：已逐README职责判定。
- Residual risks：已按correctness、concurrency/recovery、platform/external evidence、security分类；均不阻塞plan review。
- Finding status：controller accepted findings 已在 plan 中修复；MiMo-003 已 rejected-with-reason；DS F-04 为证据失效的 non-finding；OQ-01/OQ-02 已关闭，PTY 已分类 allowed variant。
- Validation：`git diff --check` exit 0；未跟踪 plan 的 `git diff --no-index --check` 无 whitespace error；path inventory 共 77 条，75 条已存在，2 条为 S4 明确 planned-new (`dayu/host/compaction_terminal.py`、`tests/host/test_compaction_terminal.py`)，0 条意外缺失；F01-F13 均至少出现一次且在 S1-S5 有显式 heading/combined heading 覆盖。
- Completion status：`accepted-finding fix complete; awaiting re-review`。
- Next entry point：`re-review`；不进入 accepted plan commit 或 implementation。
- Artifact：`docs/host/wu-cli-interactive-02-conformance-fixes-plan.md`。
