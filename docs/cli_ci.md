# Dayu CLI 真实环境行为 CI

## 1. 定位

本文定义 Dayu CLI 的真实环境行为验证方案。目标不是增加一组只验证参数解析的单元测试，而是把目前依赖人工运行、录屏、查日志和查数据库的验收过程，收敛为可重复执行、可关联证据、可自动发现覆盖遗漏的 CI 体系。

该体系需要同时回答三个问题：

1. CLI 的用户可见行为是否符合 Dayu 设计、用户已接受的 oracle 和适用的交互最佳实践。
2. Host 的 canonical truth、状态迁移、Tool Trace、Conversation Memory 和实际模型输入是否符合设计真源与最佳实践。
3. 实际进入 LLM 上下文的 prompt、tool schema、memory 和 evidence material 是否符合 `AGENTS.md` 的“LLM-facing 文本约束”。

本文是验证体系设计，不表示当前仓库已经实现完整覆盖。现有 CLI smoke、PTY 测试和真实环境验证可以作为后续实现的输入，但不能替代本文定义的完整场景矩阵。

本文定义的 CI 是真实环境验收 CI。任何 mock runner、fake provider、fake tool、内存替身 Host、伪造 EventLog 或手工拼接 memory snapshot 都不能作为场景通过证据。普通单元测试仍可按其测试边界使用 test double，但它们属于开发回归，不计入本文 CI 的 pass verdict。

首次执行不是依据现有实现替用户判断产品正确性，而是一次完整的 oracle calibration campaign：总控代替人工验收者在
不同前置状态下逐项操作所有 CLI 命令、参数和交互分支，冻结实际行为证据，由 Agent 提供裁决建议，最终由用户定义
正确行为。第一轮允许为了补齐新发现的交互分支或证据缺口执行多个 run，但只有 mandatory 场景矩阵全部执行、证据
充分、用户裁决闭环且 scenario/oracle registries 均通过 readiness 校验后才结束。当前产品可以仍然违反新接受的
oracle；产品 failure 不等于 calibration 未完成，coverage/evidence/adjudication gap 才会阻止 readiness。

## 2. 新会话执行契约

本文必须能够作为新总控会话的自包含执行入口。用户给出“按 `docs/cli_ci.md` 执行 CLI CI”、准备好 `ai` tmux session 中的四个 Agent（总控、AgentCodex、AgentMiMo、AgentDS），并提供第 2.2 节规定的机器环境与授权配置。CLI 被测环境由总控自动创建、运行、取证和清理。

### 2.1 默认输入

新会话未提供额外参数时，默认规则如下：

- repository：包含本文档的当前仓库。
- target ref：当前 `HEAD` 对应的 commit SHA。
- profile：场景与 oracle registries 都通过 readiness proof 校验并为 `ready` 时使用 `full-real`；否则自动使用
  `calibration-real`。`calibration-real` 必须以完成全量 mandatory 矩阵和建立 registry 为目标，不得降级为抽样 smoke，
  也不得伪装成 full pass。
- agent session：tmux session `ai`。
- execution mode：新建独立 detached tmux session，不占用用户现有 `console` pane。
- evidence policy：通过和失败场景均保留 evidence bundle；失败场景额外保留完整终端和运行目录定位。

正式 CI 只接受 commit 作为被测对象。默认 target 已解析为明确的 `HEAD` commit SHA 时，当前工作区的未提交修改不进入 detached validation worktree；总控必须报告这些改动被排除，但不因其存在阻塞对该 SHA 的只读验证。只有用户要求把未提交修改作为被测对象，或 target ref / ownership 无法唯一确定时，才停止并要求先提交或显式裁决；未提交改动只能形成 `preflight`，不能形成 release/full-real verdict。

可选调用参数包括 target ref、`full-real` / `focused-real` profile、场景 id、允许的 provider/model、最大运行成本/时间和外部副作用授权。`focused-real` 只用于问题复现或修复验证，不能单独替代完整 CI pass。

### 2.2 用户负责的机器级条件

用户负责保证以下条件在机器上可用：

- `ai` tmux session 中总控、AgentCodex、AgentMiMo、AgentDS 可通信。
- Python 3.11、git、tmux、asciinema、VT100/xterm cast 回放能力、项目系统依赖和 Docling 等外部运行依赖已经安装。
- 真实模型 provider、FMP 等 credential 已按项目既有 secret-ref / 环境配置方式提供。
- SEC、CNInfo、HKEX、模型 provider 和其它场景依赖的网络可访问。
- 机器具备足够的磁盘、内存和执行时间。
- 默认授权允许真实模型调用、公开财报源读取/下载，以及 CI-owned run root 内的写入、预处理和上传；禁止读取用户未授权文件、写入用户共享 workspace、外部破坏性操作和非 CI-owned 上传。扩大权限时，用户必须给出对应授权边界。
- 可选成本/时间/磁盘上限通过 invocation 或 `DAYU_CLI_CI_AUTH_PROFILE` 指向的 operator 配置提供。配置至少可表达
  `max_wall_time_seconds`、`max_model_calls`、`max_disk_bytes`、`allow_public_financial_download`、
  `allow_ci_owned_upload` 和 `allow_external_write`。未提供时不做自动模型重试或无 coverage obligation 支撑的额外高成本
  采样，但仍必须尝试全部 mandatory 场景；预算不足使未执行场景成为显式 gap，并阻止 calibration completion /
  registry readiness 或 full-real verdict，不能据此缩小矩阵。

用户不需要提前创建 validation worktree、venv、CLI tmux session、workspace、日志、cast 或 evidence 目录。总控不得要求用户手工执行本可自动完成的命令。

### 2.3 总控自动创建的环境

总控必须按以下顺序完成 bootstrap：

1. 阅读仓库 `AGENTS.md` 和本文档，在任何文件写入、Agent dispatch 或运行资源创建前执行 `git branch --show-current` 与 `git status --short`，记录只读 assessment preflight。
2. 阅读 `docs/host/design.md`、`docs/engine/design.md` 和当前项目总控文档；涉及 #80 时读取其当前 issue 内容。
3. 使用 `$init-agents` 约定发现并确认 `ai` session 中的 Agent 类型、pane 和空闲状态。
4. 解析 target ref 为不可变 commit SHA，记录 branch/ref、commit、dirty state、被排除的未提交改动和仓库 remote identity。
5. 读取稳定 scenario/oracle registries，重新计算并校验 readiness proof 后决定 `full-real` 或
   `calibration-real`；不得只信任文件中的 `registry_status` 字面值。
6. 创建唯一 run id 和 run manifest；CLI CI assessment 不创建 Phaseflow control_doc，也不把自身伪装成可进入 `plan` 的 work unit。
7. 在仓库外部的独立 run root 创建 detached git worktree，避免 CI 产物污染主工作树，也避免 Agent 正在进行的修改改变被测代码。
8. 在 run root 创建或复用可证明与 target commit/lock digest 一致的 Python 3.11 venv；安装 target worktree 对应项目。venv 不得继续引用控制仓库中的可变源码。
9. 创建独立场景 workspace、日志、cast、screen 和 evidence 目录。
10. 创建唯一 detached tmux session，至少包含 CLI execution pane 和 observer/evidence pane，并固定终端尺寸、UTF-8 locale 与 `TERM=xterm-256color`。
11. 通过现有 secret-ref / 环境配置向真实 runtime 提供 credential；不得复制、回显或写入 secret 明文。
12. 按本节定义的 Phaseflow-aligned goal-discovery流程执行 evidence acquisition；用户选择某个候选进入正式 goal confirmation 后，才为该稳定 WU identity 调用 `$phaseflow design_doc=<design-doc> control_doc=<project-control-doc>`。

run root 默认位于仓库父目录下的专用 `.dayu-cli-ci/<run-id>/`，或由 `DAYU_CLI_CI_ROOT` 显式覆盖。run root 至少包含 `repo/`、`.venv/`、`workspaces/`、`logs/`、`casts/` 和 `evidence/`。具体物理布局可以调整，但 execution identity 和 artifact location 必须写入 run manifest。

### 2.4 Preflight

总控必须自动检查并记录：

- 四个 Agent 可达，角色映射正确，当前没有需要等待完成的冲突任务。
- target commit 可读取，validation worktree 与 commit SHA 一致且干净。
- Python 与 CLI 可执行文件来自 validation run root，而不是主工作树的 editable install。
- tmux、asciinema、终端回放能力和必要系统依赖可用。
- provider/model 配置可解析；只验证 secret ref 可用性，不输出 secret 值。
- 外部网络和真实财报源满足当前 profile 的最低条件。
- evidence 目录可写，剩余磁盘与预计运行预算足够。
- 当前系统时间、时区、locale、终端尺寸和关键依赖版本已记录。
- parser inventory 与 interactive branch inventory 能生成并冻结，且每个 mandatory coverage obligation 都有场景
  owner 或明确 gap。

任何真实依赖缺失都必须产生 `blocked` preflight 结论。不得自动切换到 mock/fake、缓存模型答案或更低语义的替代路径。

### 2.5 Phaseflow-aligned Goal Discovery 与 Agent 路由

总控保持唯一裁决权，具体工作按以下角色路由：

- AgentCodex：Codex Agent，承担 goal-discovery evidence acquisition，生成 inventory/场景、操作 CLI tmux panes、收集 evidence、分析直接证据；候选 WU 完成正式 Phaseflow goal confirmation 后，再承担对应 `plan` / `implementation` / `fix` gate。
- AgentMiMo：Claude Code Agent，在 assessment 内独立审查 UI 行为、LLM-facing 文本、Conversation Memory 和财报分析证据充分性。
- AgentDS：Claude Code Agent，在 assessment 内独立审查 Host/EventLog/Tool Trace/RunInputBuilder 传播、财务 oracle 和架构/最佳实践。
- 总控：维护 oracle、监督 Agent、不轻易中断长任务、关联证据、裁决 findings、决定 rerun 范围并输出最终 verdict。

AgentMiMo / AgentDS 的独立审查是候选 WU goal confirmation 的输入证据，不是 Gateflow 的 `plan review`、`code review`、`aggregate deepreview` 或 `PR review` gate，不得因此跳过后续开发 WU 中的任何正式 review gate。

一次 CLI CI 是只读 assessment，不是 Phaseflow work unit。它复用 Phaseflow 的 preflight、Agent liveness、finding taxonomy 和 goal confirmation 输出要求，但不进入 Gate Order。Goal-discovery evidence acquisition 中不可跳过的主流程是：

```text
FREEZE PARSER + INTERACTIVE-BRANCH INVENTORIES
-> BUILD ALL MANDATORY STATE / OPTION / INPUT / COMBINATION / CROSS-COMMAND OBLIGATIONS
-> EXECUTE EVERY MANDATORY SCENARIO WITH BEFORE / INPUT / SCREEN / ARTIFACT / CROSS-LAYER / AFTER EVIDENCE
-> CORRELATE / CLASSIFY OBJECTIVE OR HARD-CONTRACT FACTS WITHOUT SHORT-CIRCUITING
-> FREEZE HUMAN-READABLE OBSERVED-BEHAVIOR REPORT
-> AGENTMIMO + AGENTDS INDEPENDENT REVIEW / FORMAL SUGGESTIONS
-> CONTROLLER SYNTHESIS
-> USER ADJUDICATION
-> EXPAND AND RERUN IF USER OR EXECUTION DISCOVERS A COVERAGE / EVIDENCE GAP
-> PERSIST ACCEPTED SCENARIOS + EXECUTABLE ORACLES
-> VALIDATE READINESS PROOF
-> ORACLE LIFECYCLE / GOAL-DISCOVERY OUTPUT
```

在 correlate/classify 阶段发现 objective fact 或 hard contract failure 时可以立即标注并突出显示；除非继续执行会越过
授权、造成安全风险或受到真实依赖阻塞，不得以此短路其余 mandatory observation，也不得自动进入修复。Finding 或
修复候选可以在运行中暂存事实定位，但只有相应 observed report 冻结后才允许正式 review、裁决或生成候选 WU。
`observed-behavior.md` 只承载已观察事实，Agent suggestions 与 user adjudication 只写入
`oracle-adjudication.md`，三者不得混写。

`AGENTMIMO + AGENTDS INDEPENDENT REVIEW / FORMAL SUGGESTIONS` 是两路 reviewer 对同一 frozen report 的正式独立输出。两路 review 只能在 report freeze 后开始，freeze 前不得读取或写入针对本次行为的产品期望，以免污染 observation；它们不是第三套 review，也不替代后续开发 WU 的 Gateflow `plan review`、`code review`、`aggregate deepreview` 或 `PR review`。

每个 goal-confirmation-ready artifact 只描述一个稳定候选 WU identity，并包含动机、直接证据、语义 owner、传播路径、严重性、成功信号、非目标、scope boundary、blocking questions 和建议优先级。`unadjudicated` oracle difference 只进入 oracle candidate 清单，用户裁决前不得伪装成实现 finding。若多个 findings 不属于同一语义闭环，必须生成多个独立 artifacts，不能为了减少 gate 数量硬塞进一个实现范围。

Agent 执行期间，总控应耐心等待其完成；只有确认任务失去进展、进入错误目标或可能造成未授权副作用时才可中断。长事务不得仅因短时间无终端输出而被判定卡死，应同时观察 debug log、EventLog、Tool Trace 和外部 operation 状态。

### 2.6 CI 与修复边界

CI runner 是只读验证者，不修改被冻结测 worktree。发现 failure 后仍先完成其余获授权的 mandatory observation；
相应 observed report 冻结后才按以下流程处理：

1. 总控先用直接证据定位语义 owner 和传播路径。
2. 两路独立审查对 finding、严重性和修复边界提供 goal confirmation evidence。
3. 总控裁决 findings，为每个语义闭环生成独立候选 WU artifact，并停在 `awaiting-user-candidate-selection`；用户完成正式 Phaseflow goal confirmation 前禁止进入 `plan`、修改产品代码、创建修复 commit 或开启 PR。
4. 用户选择某个候选 WU 后，总控以正确 design_doc 和既有项目 control_doc 启动新的 Phaseflow，重新执行 branch/status preflight；若已有未完成 active WU，先等待或请用户裁决，不能覆盖。Preflight 通过后，由 Phaseflow 把该稳定 WU identity 写入项目 control_doc，current gate / next entry point 均指向 `goal confirmation`。Phaseflow 直接引用 assessment evidence并向用户复述目标；用户确认后才进入 `plan`。此后必须完整遵循既有 Gate Order，一直推进到 `final closeout pass`，不得因为 CI 已经做过双路审查而省略 plan review、code review、aggregate deepreview 或 PR review。
5. 开发 Git 流程完全复用 Phaseflow：branch/status preflight、accepted local commits、push、draft PR、PR review 和 final closeout。CLI CI 不定义第二套 branch、commit 或 PR 规则。
6. 修复不得直接修改 validation worktree。修复提交后，为新 commit 创建新的 CI run id 和 validation worktree。
7. 先执行 focused-real regression，再执行受影响矩阵；focused-real 只产生局部结论，不更新全量 coverage、
   calibration readiness 或 full-real verdict。需要形成完整结论时必须重新执行整个 mandatory `full-real` 矩阵。

若 CI 未发现成立的问题且不存在待裁决 oracle，总控输出 `no-implementation-goal`，不创建开发 branch、commit 或 PR。
若存在 `unadjudicated` oracle candidate，则停在 `awaiting-user-candidate-selection` / `oracle-review-required`，不能用
`no-implementation-goal` 跳过用户裁决。若用户暂不选择候选 WU 或不裁决 oracle，当前 execution run 可以在保留
evidence 后安全结束且不启动任何 Phaseflow WU；第一轮 calibration campaign 必须保持
`incomplete/awaiting-user-adjudication`，next entry point 仍指向补证、裁决或 readiness closure，不得报告为第一轮结束。

旧 run 的 evidence 不得被新 commit 覆盖。跨 run 复用结论时，必须证明 target commit、场景定义、真实财报 corpus digest、provider/model policy 和 oracle 均未变化。

### 2.7 重复执行、收尾与最终输出

每次执行必须生成唯一 run manifest 和最终报告。报告至少包含：

- target commit、profile、run id、起止时间和 runtime identity。
- parser/interactive inventories 的 identity/digest、mandatory obligation 总数、逐维度 coverage 和缺失项。
- `observed-behavior.md` 的路径、report identity、exact UTF-8 bytes SHA-256 digest 和冻结状态。
- 当前 `calibration_stage`；parser leaf 总数和 in-scope / out-of-scope 数量。
- mandatory scenarios 的 planned / attempted / executed / not-run / blocked 数量，以及
  `success` / `error` / `timeout` / `cancel` 各 `execution_outcome` 数量。
- 按 precondition、option/interactive branch、input class、combination、cross-command 和 path kind 分离的 coverage /
  outcome 统计；任一维度都不能用其它维度抵扣。
- required evidence 完整率、各 `evidence_status` 和 `gap_kind` 的独立统计，以及 frozen report 上的
  `observation_completeness`。
- AgentMiMo / AgentDS formal suggestions 状态、总控 synthesis 状态和 user adjudication 状态。
- scenario/oracle registry readiness proof：inventory identity、mandatory/covered/gap counts、用户裁决 identity、
  frozen report digests、dangling refs、uncovered correctness surfaces 和最终校验结果。
- SQLite observation 的 `queried` / `not-queried` 汇总、查询边界、只读证明、脱敏结果和 public observability gaps。
- CLI/UI、Host、LLM-facing、Conversation Memory、财报分析五类 verdict。
- 每个失败或 limited-signal 场景的直接证据、语义 owner、严重性和建议 owner。
- 本次使用的 accepted oracle id/version，以及新增 `unadjudicated` / `needs-more-evidence` candidates。
- mock/fake absence proof 与敏感信息扫描结果。
- 两路 review 结论和总控裁决。
- evidence bundle 根目录及可复现命令。
- 是否满足 `full-real-pass`，以及哪些场景 blocked/not-run。
- 候选 WU 列表，或没有成立 implementation goal 的直接理由。
- assessment 状态；若用户已选择候选 WU，则记录对应项目 control_doc、WU id 和 Phaseflow next entry point。

上述 observation、suggestions、reference、SQLite 和 registry readiness 字段是相互正交的事实或流程投影。一个 run
必须仍只有一个 primary validation verdict；不得从 `calibration_stage`、`observation_completeness`、registry
readiness、单条 `execution_outcome` 或 evidence gap 派生第二套产品 verdict。相反，已证实产品 failure 不得阻止
其余 mandatory observation，也不自动阻止用户定义 accepted oracle 或 registry ready。

CI validation verdict 只允许：

- `full-real-pass`：完整 mandatory 矩阵都由 objective fact、hard/current-design contract 或 accepted oracle 覆盖并通过，且没有 fail、blocked、not-run、limited-signal 或 oracle-review-required 场景。
- `focused-real-pass`：指定场景满足同样的 coverage/pass 条件；只代表该范围，不代表全量通过。
- `fail`：存在已证实行为、设计、财报分析或安全错误。
- `blocked`：真实依赖或授权缺失，无法形成有效 verdict。
- `limited-signal`：证据不足，只能形成受限结论。
- `oracle-review-required`：真实行为已取证，但相关 oracle 尚未由用户裁决，不能形成正式 pass/fail。

一个 run 只能有一个 primary validation verdict，聚合优先级固定为：`fail > blocked > oracle-review-required > limited-signal > full-real-pass/focused-real-pass`。低优先级状态和其它 findings 仍写入报告，但不能覆盖更高优先级 verdict。

Goal-discovery 状态只允许：

- `awaiting-user-candidate-selection`：存在一个或多个证据充分的候选 WU或待裁决 oracle，等待用户选择下一项；选择 WU 后启动该 WU 的正式 Phaseflow goal confirmation，确认后才进入 `plan`。
- `no-implementation-goal`：没有成立的修复目标，不进入开发 Git 流程。
- `needs-more-evidence`：当前证据不足以确认候选 WU，继续停留在 goal confirmation。
- `blocked`：preflight、真实依赖或授权缺失，无法完成 goal confirmation。

用户确认候选 WU 后，正式项目 control_doc 记录该 WU 和 Phaseflow next entry point。CLI CI evidence bundle 作为该 WU goal confirmation 的直接证据被引用，但不替代任何后续 gate artifact。

总控在 evidence 落盘并确认 Agent 无未完成任务后，按第 2.8 节停止 CI detached tmux session并执行 bounded cleanup。不得删除用户工作树、用户共享 workspace、credential 或未归属于本 run 的 tmux session。

### 2.8 Retention 与 Cleanup

每个 run root 创建 CI-owned marker，记录 run id、target commit、canonical run-root path 和 manifest digest。任何自动删除必须同时满足：目标位于 canonical run root 内、CI-owned marker 校验通过、run manifest 明确列出该资源、没有 Agent/tmux/process 仍在使用。缺少任一证明时 fail closed，不删除。

默认策略如下：

- 永久保留 bounded run manifest、verdict、oracle/scenario candidates、review/adjudication，以及必要 EventLog/Tool
  Trace/memory/runner-input 的 bounded 摘要与 digest。第一轮 campaign 未完成时，任何被 unresolved adjudication、
  accepted scenario/oracle candidate、readiness proof 或未关闭 finding 引用的完整 logs、casts、screen snapshots 和
  受控 evidence artifacts 都必须保留；最新 baseline 不能自动取代这些 owner。
- 所有 Agent 完成且 evidence integrity 校验通过后，停止并删除本 run 的 detached tmux session，移除 detached validation worktree 和 run-local venv；重现必须创建新 run，不依赖旧可执行环境。
- `full-real-pass` / `focused-real-pass` 场景的 CI workspace、下载和处理中间产物在 evidence 固化后删除。
- `fail` / `oracle-review-required` / `limited-signal` 场景至少保留最新一份 CI workspace；旧 workspace 只有在用户完成
  相关裁决、更新 run 明确 supersede 旧 evidence、所有 registry/readiness refs 已迁移且不存在 active finding 后才可
  删除。
- Campaign readiness 完成后，可把 accepted oracle/scenario 实际依赖的关键 screen、literal diff、DB delta 和
  cross-layer evidence 固化为 immutable bounded retained projection；只有该 projection 足以独立支持全部 claim、
  digest 校验通过且 registry refs 已通过正式 supersession/update 指向 retained material 后，才可删除对应大
  logs/casts/screens/payload。新 baseline 或 finding 关闭本身不是删除 oracle authority evidence 的充分条件。
- 清理失败必须写入 run report；下一次 preflight 统计所有 CI-owned run roots。若预计执行会超过 operator auth profile 的磁盘上限，则在创建新 workspace 前 `blocked`，不得删除无法证明归属的目录来腾空间。

## 3. 第一性原理

CLI 验证不能只检查进程退出码或最终回答。Dayu 是宿主强约束下的 `LLM in the loop` 系统，一次 CLI 交互至少同时涉及以下事实层：

- 终端实际显示给用户的内容。
- CLI / Service 产生的请求及生效参数。
- Host 持久化的 canonical EventLog facts。
- Tool Trace、audit、memory 等派生 projection。
- RunInputBuilder 实际组装给模型的 messages 和 tool schemas。
- 模型产生的 tool call、thinking、final answer。

这些层次可能发生“最终显示正确但持久化错误”“EventLog 正确但 memory 错误”“memory snapshot 正确但 runner input 组装错误”等传播偏差。因此，CI 必须关联检查整条传播路径，不能把任一单层输出当作全链路正确性的替代证据。

## 4. 真源与证据职责

| 验证对象 | 主要证据 | 不应作为唯一证据 |
|---|---|---|
| CLI 最终可见行为 | asciinema 回放后的终端屏幕状态 | debug log、cast 原始文本 |
| 按键、取消、重试和多轮输入 | PTY / tmux 输入时间线 | 最终退出码 |
| 参数解析与 CLI 请求 | parser contract、CLI invocation record | help 文本 |
| 运行过程和故障诊断 | `--log-level debug` 日志 | 用户可见输出 |
| Host canonical truth | Host DB、EventLog | Tool Trace、memory snapshot |
| 工具调用业务语义 | Tool Trace 与对应 EventLog facts | activity 文本 |
| Conversation Memory | memory snapshot、source refs、projection diagnostics | 最终回答 |
| 实际 LLM 输入 | runner-call input reconstruction / manifest | prompt 源文件或 memory snapshot |
| LLM-facing tool surface | attempt-local effective tool schema snapshot | scene manifest 声明 |

Debug log 用于诊断，不是 durable truth。Tool Trace 表达一次业务工具调用的可读追踪，不应为了复现 EventLog 的治理粒度而生成重复 trace。EventLog 可以为治理和投影保留多个相关 facts，但这些 facts 不应直接泄漏为重复 UI activity 或 LLM-facing memory。

### 4.1 Oracle 不是默认真源

“对齐 Codex / Claude Code”“对齐最佳实践”“对齐设计真源”这样的抽象口号都不能直接作为可执行 oracle：

- Codex / Claude Code 只在用户主动询问或 Agent 解释最佳实践时提供可选参考；CI 不负责运行、冻结、比较或记录其
  行为，也不从参考产品派生 mandatory obligation、evidence gap、oracle 或 readiness gate。
- 参考产品的版本、终端状态和任务上下文与 Dayu 不同，其行为不天然适合 Dayu，也不能替代用户对 Dayu predicate
  的裁决。
- 最佳实践是 Agent 基于经验、直接证据、替代方案和失败模式提出的候选判断，不因由总控或 reviewer 提出就自动正确。
- 设计真源是当前规范，但允许真实 CI 发现设计本身不符合更高层目标、事实边界或最佳实践。实现与设计不一致和设计需要修正是两个不同 finding。
- Dayu 当前实现只说明“现在发生了什么”，不能反过来定义“本来就应该这样”。

因此，除具有客观真源的硬事实外，未由用户裁决的期望行为必须标记为 `unadjudicated`，不得直接用于产品 pass/fail。

### 4.2 Oracle 类型

总控必须先分类，再决定是否需要用户裁决：

| 类型 | 示例 | 初始权威 | 裁决方式 |
|---|---|---|---|
| objective fact | 财报原始数值、单位、期间、digest、实际 EventLog row | 原始财报或 durable canonical fact | 来源与完整性校验通过后可直接使用 |
| hard contract | secret 不得泄漏、非法状态迁移不得发生、分层反向依赖禁止 | `AGENTS.md` 与已接受架构硬约束 | 直接形成 finding；若硬约束本身被质疑，必须升级为设计裁决 |
| current design behavior | memory、wait、trace、projection 当前设计要求 | 当前有效设计真源 | 实现偏离构成 conformance failure；CI 同时允许提出 design-review candidate，修复方向待用户裁决 |
| reference behavior | 用户主动询问的其它产品终端或交互行为 | 非约束性的参考信息 | 只用于解释建议与取舍；不进入 Dayu CI observation、coverage、oracle 或 readiness |
| best-practice proposal | reviewer 建议的 memory、UI、tool 或分析行为 | 有理由但未裁决的建议 | 双路 review 后由用户裁决 |
| product-quality rubric | 买方分析深度、表达方式、交互体验 | 候选 rubric | 用户裁决范围、阈值和允许变体 |

财报事实等 objective fact 不需要用户逐项主观决定真假，但其来源选择、容差、可比口径和哪些事实构成产品验收标准仍可以成为待裁决 oracle。

### 4.3 Oracle 生命周期

Oracle 状态只允许：

- `unadjudicated`：已提出，但尚未由用户裁决。
- `needs-more-evidence`：需要更多真实运行、参考实现对比或设计分析。
- `accepted`：用户已确认，可从指定版本开始用于正式 CI 判定。
- `rejected`：明确不作为 Dayu 行为要求，并记录理由。
- `superseded`：曾被接受，但已被新版本替代。

首次或校准阶段运行中，未命中 accepted oracle 的主观产品行为差异必须输出 `oracle-review-required`，而不是 `fail`。违反 objective fact、hard contract、当前有效设计 contract 或 accepted oracle 时，可以形成正式 failure。若当前设计同时被质疑，conformance failure 仍保留，但候选 WU 必须先裁决“修改设计还是修改实现”，不能自动选择修复方向。

Accepted oracle 后续仍可被新证据挑战。修改时必须创建新版本并把旧版本标记为 `superseded`；不得原地改写旧 oracle，使历史 CI verdict 失去解释基础。

当前判定按稳定 `predicate_id` 解析版本，而不是把 scenario 冻结的 `accepted_oracle_refs` 当作永久 current owner。每个
`oracle_predicate_refs` 必须恰好连接到一个 `status=accepted` 且未被 supersede 的当前 oracle version；零命中是 dangling
ref，多于一个命中是 duplicate current owner，二者都必须 fail closed。`accepted_oracle_refs` 只记录 scenario 获裁决时
所依据的 oracle version，oracle lifecycle replacement 不得批量改写这些历史引用。旧 oracle version 标为
`superseded` 后只用于解释历史 verdict，不再执行其 predicate contract。

### 4.4 Oracle Record

每条候选或已接受 oracle 至少记录：

- `oracle_id` 与 `version`。
- category、适用 command/scene/surface 和前置状态。
- 可判定的 expected behavior / predicate，以及允许的有效变体。
- 明确禁止的行为。
- authority basis：objective source、hard contract、current design、best-practice proposal 或 user decision。
- Dayu 实际行为和对应 evidence refs。
- 用户明确把某项外部参考纳入裁决理由时，可以在 adjudication notes 中简述该理由；不得把它变成 Dayu observation 或
  独立 oracle。
- 设计依据及精确章节；若质疑设计，记录 design conflict。
- AgentMiMo / AgentDS 的独立意见、替代方案和 trade-off。
- 当前状态、用户裁决、裁决日期、适用起始版本和 `supersedes` / `superseded_by`。

Oracle predicate 应验证语义不变量，避免锁定真实模型的完整回答、固定措辞或唯一工具调用顺序。真实模型存在多个合理路径时，只约束必须满足的事实、证据、禁止事项和用户可见结果。

### 4.5 校准与用户裁决

第一轮 CI 是完整的 oracle calibration campaign，不是允许局部覆盖的预热 smoke。总控必须从 parser inventory、
dynamic interactive branch inventory 和第 5.1 节 coverage dimensions 建立全部 mandatory obligations，在各相关前置
状态下真实执行对应场景，完整关联实际进程、终端、文件系统和跨层证据；然后为每个 run 生成并冻结单一
`observed-behavior.md`。只有 report frozen 后，AgentMiMo / AgentDS 才能独立 review 并提出正式 suggestions，最后由
用户逐个 predicate 裁决。新发现 branch、用户要求补证或 rejected behavior 留下 correctness gap 时，campaign 必须扩展
矩阵并产生新 run/new report，直到第 4.6 节 readiness proof 通过。Accepted oracle 冻结版本，从后续指定 run 开始参与
正式 pass/fail。

校准运行仍必须完整保存 evidence。不得因为用户尚未裁决，就只给结论而丢弃后续建立 oracle 所需的输入、screen、
stdout/stderr、生成物 before/after、debug log、Host public reads、EventLog、Tool Trace、memory、runner input 或财报证据。

#### 4.5.1 Observation gate 与 ordering invariants

`calibration_stage` 是 run report 中的 handbook workflow 位置，不是 Host runtime state、durable schema、Phaseflow /
Gateflow gate 或新的 validation verdict。合法 stage 和转移前置条件如下：

| `calibration_stage` | Entry criterion | 允许动作 | 禁止动作 |
|---|---|---|---|
| `observation-not-started` | 当前 run 的 frozen inventories、mandatory obligations、scope 和授权已知，尚未执行场景 | 准备场景和 bounded before snapshot | suggestions、adjudication、oracle acceptance |
| `observation-in-progress` | 至少一个 mandatory 场景已开始真实执行 | 继续逐场景取证；立即标注 objective / hard-contract failure | 修复；根据不完整样本冻结全量结论 |
| `observed-report-generated` | 当前 run 的单一事实报告已生成，并首次计算 `observation_completeness` | 检查完整性、脱敏、raw refs 和 exact-byte digest 准备 | Agent review/suggestions、用户裁决、accepted oracle |
| `observed-report-frozen` | report、evidence refs、脱敏结果和 digest 已冻结，completeness 已确定 | 启动 AgentMiMo / AgentDS 对 frozen report 的独立 review | 回写或原地替换 frozen facts；用 reviewer 期望污染 observation |
| `agent-suggestions-ready` | 两路独立 review 都引用 frozen report digest，并形成带 authority basis 的正式 suggestions | 总控合并同义建议并保留分歧 | 将 reviewer 共识自动升级为 accepted oracle |
| `awaiting-user-adjudication` | frozen report、两路 suggestions 和总控 synthesis 均可供用户阅读 | 用户逐 predicate accept / reject / request more evidence | 自动修改 registry、finding 或产品 |
| `adjudicated` | 用户已对具体 predicate、scope 和 allowed variants 作出决定 | 进入第 4.3 节既有 oracle lifecycle；必要时另建后续 WU | 把未裁决项写成 accepted |

`observation_completeness` 只在 `observed-report-generated` 时依据当前报告计算，在
`observed-report-frozen` 时随 report 冻结；后续 stage 只引用该 immutable 值，不随 suggestions 或 adjudication
改写：

- `complete`：当前 run 声明的每个 mandatory scenario obligation 都已真实 attempted/executed，且 required
  evidence 足以复核实际行为；该值只证明当前 report 的 observation scope，不单独证明整个 campaign matrix 已闭合。
- `incomplete`：任一当前 run mandatory scenario 为 `not-run` / `blocked`，或 required evidence
  缺失、损坏或歧义到不足以复核实际行为。

合法场景实际得到 `error`、`timeout` 或 `cancel` 不会自动导致 observation incomplete；这些值只属于
`execution_outcome`，行为正确与否由适用的 validation/oracle contract 判断。help、单个 negative、parser acceptance、
exit 0、outcome `success` 或 CLI 自报 summary 都不能替代其它 mandatory state/option/input obligations 的真实
attempt/execution 与 required evidence。

以下 owner / 交互表是各章节解释状态维度的集中 anchor。不得建立平行 verdict、生命周期或全组合状态矩阵：

| 维度 | 唯一 owner / scope | 何时有值 | 允许影响 | 不允许替代 |
|---|---|---|---|---|
| `calibration_stage` | 当前 calibration run 的 handbook workflow | run 全程 | 下一步 observation/review/adjudication 动作 | completeness、validation verdict、Gateflow gate |
| `observation_completeness` | 当前 immutable observed report 的覆盖/证据 contract | report generated 时计算、frozen 后只读 | 是否可声称 observation coverage complete | 命令成败、行为正确性、run validation verdict |
| `execution_outcome` | per-scenario raw process observation | 每次真实执行后；`not-run/blocked` 时无值 | 记录 `success/error/timeout/cancel` 实际结果 | coverage、evidence status、gap、pass/fail |
| `evidence_status` / `gap_kind` | per-scenario evidence integrity record | 取证检查后 | 说明证据充分性、gap owner 和后续取证动作 | execution outcome、平行 verdict |
| registry readiness proof | scenario/oracle registries 的 coverage/adjudication closure contract | campaign 更新 registry 后重算 | 决定 registry 是否为 `ready`、是否可结束第一轮 | observation completeness、产品 pass/fail |
| primary validation verdict | 第 2.7 节既有 run 裁决 contract | 既有规则要求时 | 裁决整个 run | calibration stage、后续 WU 状态 |
| goal-discovery status | 第 2.7 节 Phaseflow-aligned 后续 WU 路由 | observation/adjudication 产生候选目标后 | 选择、等待或声明后续 work unit | 当前 observation 或 oracle 状态 |
| oracle lifecycle | 第 4.3 节每个 oracle predicate | 候选形成后 | `unadjudicated` / `needs-more-evidence` / `accepted` / `rejected` / `superseded` | run verdict、report completeness |

同一 run 可以 observation-complete 且实际包含 error/timeout/cancel，也可以同时存在 hard-contract `fail`；它们分别回答
“是否观察完整”“实际发生什么”和“行为是否正确”。必须遵守：

1. 先事实、后两路独立 review / 正式 suggestions；没有 frozen `observed-behavior.md`，两路 reviewer 不得开始。
2. 先建议、后用户裁决；用户必须能同时看到事实、authority basis、反例、替代方案和风险。
3. 先用户裁决、后 accepted oracle；reviewer 或总控共识不能替代用户。
4. 先 accepted oracle 或 confirmed hard-contract WU、后修复；validation run 不直接修改产品。用户裁决完成后，稳定
   scenario/oracle registry 必须在第一轮 campaign 结束前通过正式 work unit 更新并完成 readiness 校验。
5. 每个 mandatory state/option/interactive/input/combination/cross-command obligation 的真实 attempt/execution
   先于 coverage 完成；help、单个 positive/negative 和任一 outcome 值都不能抵扣其它 obligation。
6. hard failure 可立即分类，但除授权、安全或真实依赖 stop condition 外，不得短路其余 mandatory observation。
7. frozen facts 永不回写；补充证据必须进入新 run 和新的 immutable report。
8. SQLite private schema 只用于本次诊断，不升级为公共 contract、业务真源或唯一 oracle。
9. 外部产品参考不属于 CI observation 或 correctness authority；未查询、不可用或版本不明都不构成 coverage /
   evidence / correctness gap。
10. incomplete run 中证据充分的局部 predicate 可以由用户裁决，但不得因此声称第一轮 calibration campaign 完成或
    registry ready；它只能减少后续未决集合。
11. outcome、evidence 和 verdict 必须分离；不得把 exit 0 / success 当作 completeness 或 correctness，也不得把
    error/timeout/cancel 自动改写成 gap 或 fail。

#### 4.5.2 Observed-behavior report 与建议/裁决边界

`observed-behavior.md` 是当前 run 的人类可读事实投影，不是 Host、EventLog、Tool Trace、memory、runner input、
oracle 或 verdict 的新真源。它必须在主体中直接展示足以让用户裁决的 bounded 关键 screen/transcript、输入选择、
生成物内容/diff、durable state delta、日志/trace/memory/runner-input 摘要和跨命令加载结果，同时引用各 owner 的
raw evidence 供深入复核；digest、raw ref、exit code 或 CLI 自报 summary 不能替代关键事实展示。Report 先支持全局
扫读，再支持跳转到逐场景细节，schema 见第 11.1 节。主体只能陈述实际输入、实际输出、实际状态变化、证据完整性和有
明确 authority 的 objective / hard-contract fact，禁止写期望行为、Codex 模仿建议、产品取舍、修复方案或未裁决结论。

AgentMiMo / AgentDS 的正式 suggestions、总控 synthesis 和 user adjudication 统一写入既有
`oracle-adjudication.md`，且每条 suggestion 必须引用 frozen report digest、scenario/correctness surface 和 evidence
refs；leaf/path 只能作为导航或分组，不能替代 scenario identity。用户裁决的对象必须是具体可执行 predicate 及其
scope、precondition、trigger、expected observable、allowed variants、forbidden behavior 和 measurement，不能笼统
裁决“与 Codex 一致”或“当前行为正确”。

任一路 reviewer、总控或用户发现证据不足时，当前 predicate 的合法状态是第 4.3 节既有
`needs-more-evidence`。新证据只能通过新 run 获取，并生成新的 immutable `observed-behavior.md`；旧 frozen report
及其 digest 永久保留，新 report 显式引用旧 report identity/digest。禁止修订、覆盖或回写旧 frozen facts，也禁止把
新证据追加到旧 digest 所代表的报告中。

### 4.6 Oracle Registry 与 Phaseflow 衔接

稳定 scenario registry 为 `docs/cli_ci_scenarios.json`，稳定 accepted oracle registry 为
`docs/cli_ci_oracles.json`。两个 registry 都包含 `schema_version`、`registry_status` 和记录列表；
`registry_status` 只允许 `calibration` 或 `ready`，且只是 readiness validation 的投影。`calibration` 空占位文件可以
暂时没有 readiness proof；任何 `ready` registry 必须包含完整 proof。新总控必须重新计算并校验两个 registry 的 proof
后决定 profile，不得只信任 status 字面值。

第一轮 calibration 的首个 observation run 启动时，`docs/cli_ci_scenarios.json` 仍是空的 `calibration` registry
属于正常 bootstrap：该 run 用来发现、执行和冻结候选场景。该 run 可以独立收口并保留报告，但第一轮 campaign 不能
在 registry 仍为空时结束；用户裁决和缺口补跑完成后，必须把 accepted scenarios 写入稳定 registry，并满足下述全部
readiness conditions。不得把“首个 run 允许为空”误写成“第一轮结束时允许为空”。

每次 run 在 evidence bundle 中生成 `oracle-candidates.json` 和 `oracle-adjudication.md`。不存在 accepted oracle 的场景默认进入 calibration，不得根据当前实现猜测期望值。

用户确认候选 oracle 后：

- 纯 CI 行为标准通过正式 WU 写入版本化 oracle registry。
- 若裁决改变架构、Host/Engine/Memory 契约或产品设计，必须先在对应候选 WU 中更新设计真源，再修改实现和 registry。
- 若 accepted oracle 暴露实现 failure，则同一候选 WU 的 goal confirmation 已具备直接证据，用户确认后顺畅进入 Phaseflow `plan`。
- Oracle registry、设计更新和实现修复都复用现有 Phaseflow Git/gate 流程，不建立独立的 oracle commit/PR 流程。

`docs/cli_ci_oracles.json` 中每条 oracle 至少包含第 4.4 节要求的 identity、scope、predicate、authority、状态和版本字段；只有 `accepted` 记录参与正式 verdict。`rejected` / `superseded` 可以保留在 registry 用于历史解释，但不得参与当前判定。per-run candidate/adjudication artifact 不能伪装成跨 run 已冻结 registry。

当 accepted oracle 发生 replacement 时，registry 顶层状态仍由完整 readiness proof 决定，不能因新 oracle version 已
accepted 就手工切换为 `ready`。当前 registry 中 `cli.interactive.core-execution@2` 是稳定 predicate 的 current accepted
owner；611 条历史 scenario records 的 768 个 `oracle_predicate_refs` 继续各自按 stable predicate id 解析到唯一 current
accepted owner，其中 interactive predicates 解析到 `core-execution@2`，跨 command predicate 仍解析到其所属的 current
accepted oracle。冻结的 `accepted_oracle_refs` 不迁移。该 current-resolution 规则不把 replacement scenario 的 evidence
observation 自动裁决为 accepted scenario。

第一轮 campaign 只有同时满足以下 readiness conditions 才能结束：

1. parser 与 interactive branch inventories 已冻结，identity/version/digest 可复核，且没有未分类 leaf、parameter、
   branch 或 option；
2. scenario registry 对每个 mandatory obligation 都有 accepted coverage claim；claim 使用稳定 ID 表达
   command/parameter、precondition state、interactive branch/option、input class、combination policy/high-risk
   combination、cross-command assertion 和 required evidence；
3. 每个 mandatory scenario 都引用 sufficient frozen observation evidence；`not-run`、`blocked`、缺失/损坏/歧义
   evidence 均是 readiness gap；
4. 每个 mandatory scenario 的每个 correctness surface 都映射到适用的 accepted oracle，或明确适用的
   objective/hard contract；
5. rejected candidate 留下的 correctness gap 已由 replacement predicate 或用户明确的 out-of-scope 裁决关闭；
   不能因为没有 `unadjudicated` 字面状态就视为 correctness 已定义；
6. scenario/oracle refs 双向可解析，没有 dangling refs、uncovered correctness surface、未裁决 candidate 或
   unresolved evidence gap；
7. registry-level proof 记录 inventories/version/digest、mandatory/covered/gap counts、用户裁决 identity、引用的
   frozen report digests 和 validation result，且两个 registry 均由该 result 派生为 `ready`。

产品当前违反新 accepted oracle 时，第 2-7 项仍可成立；readiness proof 记录对应 implementation finding，但不得把
产品 failure 伪装为 coverage gap。反之，产品当前看似运行成功也不能填补 coverage、evidence 或 correctness gap。

### 4.7 总控 Oracle 裁决算法

总控只对 frozen `observed-behavior.md` 中有可复核 evidence refs 的 observed difference 执行以下算法：

1. 读取 frozen report identity/digest，核对 `calibration_stage=observed-report-frozen` 和 evidence integrity；不回写
   observed facts。
2. 判断实际行为是否违反 objective fact 或既有 hard contract。若是，可形成有 authority basis 的 fail 建议；若
   hard contract 本身受到有材料的质疑，另建 design-review candidate，但不能让当前实现静默改写硬约束。
3. 查找 scope 和 version 均适用的 accepted oracle。存在时按其 predicate 形成 pass/fail 建议并记录 oracle usage。
4. 没有 accepted oracle 时，检查当前有效设计真源。实现偏离可形成 current-design conformance 建议；设计本身被
   质疑时，另提 design-review candidate，并在用户裁决修复方向前禁止直接修实现。
5. 收集 best-practice proposal 和 product-quality rubric；用户主动询问时可以解释其它产品的做法，但该信息不进入
   Dayu observation 或独立候选。当前实现和外部产品行为都不能自证为 oracle。
6. AgentMiMo / AgentDS 分别基于同一 frozen report 给出带 authority basis 的 accept / reject /
   `needs-more-evidence` 建议、反例、替代方案和 trade-off。
7. 总控合并同义材料、保留分歧，把候选保持为第 4.3 节的 `unadjudicated` 或
   `needs-more-evidence`，提交用户逐 predicate 裁决。
8. 用户裁决 `accepted` 后冻结 oracle version，再判断本次 observation 是否构成候选 implementation WU。裁决
   `rejected` 后保留理由；若 mandatory correctness surface 因此没有 accepted replacement predicate，则保持
   correctness gap、补充候选并继续裁决，不得进入 ready。用户裁决前不得写 accepted oracle、修改 registry、生成实现
   计划、启动修复或更改 finding。

总控不得因为两路 reviewer 意见一致而代替用户完成产品 oracle 裁决；用户裁决的是具体 predicate、scope 和 allowed
variants，不是笼统的产品相似性。

## 5. 覆盖模型

### 5.1 Inventory、Mandatory Obligations 与场景 Registry

命令和参数 inventory 必须从 `dayu.cli.arg_parsing.build_parser()` 派生，不能手工维护另一份可能漂移的完整清单。
Parser 只拥有 command/parameter 的静态 identity；动态 prompt、条件选项和按前序选择出现的交互分支由独立
interactive branch inventory 拥有。Interactive inventory 必须综合命令拥有的交互声明、当前 help/提示和真实运行
发现，并冻结 identity/version/digest。任一新发现 branch 或 option 都必须获得 stable ID、扩展 mandatory
obligations，并使 registry 保持或回到 `calibration`，直到补跑和裁决闭环。

场景 registry 必须同时和 parser/interactive inventories 做覆盖比对。registry 为 `ready` 时，新增命令、参数、
正反开关、子命令、动态分支、交互选项或 mandatory precondition/input class 后没有对应 accepted scenario，CI 必须
判定 registry drift failure。registry 为 `calibration` 时，所有缺失 obligation 都进入 scenario candidates，当前
campaign 不得结束，当前 run 也不得形成 `full-real-pass`。

`docs/cli_ci_scenarios.json` 中每条 scenario 至少包含：

- scenario id/version/status、supersession identity 和引用的 frozen report digests；
- stable coverage claims：command/parameter IDs、precondition-state IDs、interactive branch/option IDs、
  input-class IDs、combination policy/high-risk combination IDs 和 cross-command assertion IDs；
- 真实 invocation、交互步骤、前置 workspace/Host/Fins/DB 状态、财报 corpus/live source；
- accepted oracle refs、correctness surfaces、authorization requirements、timeout/resource budget；
- required evidence、实际 evidence refs、evidence status 和用户裁决 identity。

只有用户已裁决并标记为 `accepted`、且 coverage/evidence/oracle refs 校验通过的 scenario 参与正式覆盖率。
Calibration run 生成的新场景先写入 per-run candidates；用户裁决后通过正式 work unit 写入稳定 registry，不能由
validation worktree 原地修改。

Superseded scenario 只保留历史 invocation、evidence 与裁决解释，不得再作为 current formal scenario 执行。已有完整真实
evidence、但尚待 Oracle controller 裁决的 replacement scenario 可以登记为 `unadjudicated` 并引用 immutable evidence；
它们只作为后续裁决输入，不参与正式覆盖率、不得投影成 registry ready。F11/F12 replacement 使用
`tool-trace-formal@2`、`rolling-correction-replacement@1` 与 `cap-constrained-memory-replacement@1`。其中
`rolling-correction-replacement@1` 已由用户在 2026-08-08 根据 F14/F15/F16 fresh production observation 裁决为
`accepted`。`tool-trace-formal@2` 也已由用户在 2026-08-08 根据 F18 fresh production MiMo evidence 裁决为
`accepted`；mandatory evidence 是 public Host Tool Trace resolver/analysis response identity、canonical terminal 六字段
6/6 exact match 与 secret scan。cold analyzer `compactor_responses=0` 与 provider-native request id unavailable 保留为
limitation，不是 mandatory gap。F18/F19 早期未触发compaction或publication不完整的runs继续作为历史
`needs-more-evidence`/`nonconforming`证据保留，不得重标PASS。后续fresh production cap campaign使用真实MiMo、production
interactive与真实AAPL corpus，实际观察到同一operation五次candidate rejection后的budget-exhausted deterministic fallback、
另一operation的invalid JSON后bounded repair accepted、真实output caps、represented/omitted精确分区、compact artifact、Memory、
RunInput与跨进程reconnect同源。该run还观察到fallback final answer使用实际RunnerInput之外的材料生成未经支持的风险，因此先冻结为
implementation finding；G06 root fix后的fresh production MiMo run再次触发同一fallback，实际RunnerInput明确只允许使用当前可见且
直接支持的材料，final answer在缺少研发费用证据时明确说明无法回答并请求检索/提供材料。用户于2026-08-09据此前后复合证据裁决
`cap-constrained-memory-replacement@1`为`accepted`。`summary-null@1`的F13既有production evidence证明已有非空摘要后接受null只清除
session summary，保留5条EvidenceFact与1条AnswerAnchor，post-compact Run和跨进程reconnect继续消费同一状态；用户于2026-08-09
裁决该行为正确。至此interactive replacement scenarios的真实观察和用户裁决全部闭合。

Registry-level readiness proof 至少记录 inventories identity/version/digest、mandatory obligation 总数、covered
数、gap 数、按 coverage dimension 的明细、用户裁决 identity、frozen report digests、dangling/uncovered 检查和最终
validation result。`registry_status=ready` 只能由该 result 派生，禁止手工翻转 status 绕过校验。

2026-08-09 的version 3 readiness proof以实现commit `473e66b972e7e7a3e028ca1e9f4b2798ecb2b100`为运行真源，
重新导出root/init/prompt/interactive parser inventory，并对1056条current accepted scenarios逐条复核oracle/predicate、
correctness surface、frozen report digest、evidence status与用户裁决identity。init为59/59、prompt为388/388、interactive为
609/609，三者gap、unadjudicated、unresolved evidence和dangling refs均为0；`registry_status=ready`只适用于这三个命令。
`download`、`upload_*`、`process*`、`session`与`tool_trace`仍在本proof scope之外，不得借此宣称它们已完成第一轮。
`readiness_proof_history_20260802`只保存早期校准历史，当前第二轮入口唯一使用顶层`readiness_proof`。

当前 Agent CLI capability inventory 还必须遵守这些 parser/source-of-truth 规则：`prompt` 与
`interactive` leaf 都不包含 `--config`，root 前置 `--config` 也不能绕过 command-aware
validation；`interactive` 不包含 `--ticker`，而 `prompt --ticker` 仍是 prompt 专属参数；有
label 的 prompt/interactive 使用同一个 `cli.agent` Session slot，`prompt.P37-label-followup`
只证明 prompt 同命令复用，不能标成 cross-command proof。workspace 中存在显式配置仍可作为
precondition evidence，但不得把它登记为 command parameter claim。parser inventory 必须直接从
`build_parser()` 导出完整 action 顺序、version 与 canonical digest；参数删除后，旧真实 argv 场景
必须删除，不能改写成另一条 expected unknown-option oracle来保留 coverage 数量。

interactive 的 parser inventory 与 dynamic branch inventory 是两份正交证据。当前实现的动态
owner boundary 包括：TTY invocation 全程只有 composer 读取 stdin；non-TTY 读取 whole UTF-8
stream 并至多提交一个 Run；standalone Escape 与 CSI/Alt/paste 分流；Ctrl+C cancel/exit-after-cancel；
type-ahead 与唯一 accepted `QUEUE` handoff；fresh read-write attachment delayed orphan recovery。
这些实现事实或 owner-level tests 不能直接变成 accepted scenario：仍须先实际执行 candidate、冻结
目标 commit 的 observation report，再完成 evidence/ref/readiness validation。compactor 的真实成功
response identity 同理必须由 live provider 与 durable accepted outcome 共同证明；fake/deterministic
smoke 只能关闭 implementation finding，不能替代 provider evidence。

本节的 parser leaf 指 parser inventory 中没有下级 subparser、可以执行 primary operation 或 read flow 的完整 command
path。每个 leaf 都必须先建立 coverage obligations，而不是只规划一条 happy path。Mandatory dimensions 至少包括：

- **Precondition state**：空 workspace、已有 workspace、部分完成、重复执行、目标已存在，以及与命令相关的
  冲突/损坏状态；
- **Option / interactive branch**：默认行为、每个合法枚举/交互选项、显式参数、布尔正反开关、互斥和依赖关系；
- **Input class**：合法最小输入、其它合法值、空值、非法值、边界值、重复值、EOF、取消和中断；
- **Combination**：所有单维 obligation 至少独立生效一次，参数组合使用 pairwise，另行覆盖人工识别或历史 failure
  证明的高风险组合；不执行无收益的全笛卡尔积；
- **Cross-command**：一个命令生成的配置、文件、Host/Fins/DB 状态必须由真实后续 CLI 命令加载、查询或消费，不能只
  相信创建命令的自报 summary；
- **Evidence**：对每个场景声明应观察的 screen、filesystem、log、Host/EventLog、Tool Trace、memory、runner input、
  Fins 和相关 SQLite before/after。

Help、positive、negative、timeout 和 cancellation 可以作为 `path_kind` 分类，但不能替代上述 coverage dimensions。
执行前只能声明输入有效性、触达目标和 required evidence，不预写 `success`、exit 0、输出内容、状态变化或其它
“正确结果”，也不得依据期望 outcome 倒推场景。每个 mandatory scenario 必须有真实 attempted/executed 证据；
合法调用实际为 `error`、`timeout` 或 `cancel` 仍可 observation-complete，正确性留给 oracle。

Scenario 为 `not-run` / `blocked` 时没有 `execution_outcome`，必须记录对应 `gap_kind`；required evidence
缺失、损坏或歧义到不足以复核实际行为时，也使 observation incomplete 并阻止 readiness。某场景得到
error/timeout/cancel 后仍继续其余已获授权场景；只有越过授权、造成安全风险或受到真实依赖阻塞时，才可停止相关范围并
逐项记录 gap。

#### 5.1.1 `dayu-cli init` 最低 Mandatory Matrix 示例

`init` 的场景 registry 至少必须覆盖：

- 空 workspace、已有完整 workspace、部分初始化 workspace 和与 init 目标冲突/损坏的 workspace；
- 默认路径及每个合法交互选项逐个输入，选项组合按 pairwise + 高风险组合覆盖；
- 空输入、错误选项、非法值、EOF、Ctrl+C/取消和中断后的实际终端/文件状态；
- 重复 init，以及 overwrite/reset/preserve 等真实可用策略的逐项行为；不存在的策略不得编造，必须从当前
  parser/interactive inventory 记录为不适用；
- 运行前后的文件 manifest、创建/修改/删除列表、每个关键配置文件的脱敏内容和 diff；
- secret 是明文、secret ref 还是未持久化的直接事实；
- debug log、Host public reads、EventLog/Tool Trace 和相关 SQLite schema/关键 rows 的 before/after；
- init 后由真实后续 CLI 命令加载配置并执行 primary read/operation flow，而不是只检查文件存在或 init 自报成功。

`WU-CLI-INIT-01` 的 15-choice live provider slice 使用：

```bash
python utils/smoke_cli_init_provider_matrix.py --oracle-version 1
```

该命令为每个 choice 创建 fresh workspace 与 fresh HOME；只使用调用进程中已有
credential，缺失 credential 或 custom endpoint 时以真实 EOF 拒绝且不得 publication。
成功 init 后执行一次最小真实 prompt，并由 production Service assembly、Host canonical
terminal 与 Tool Trace runner-call resolver 共同证明 effective ordinary/compactor identity、
request/response truth 及 no-fallback。报告在
`workspace/tmp/wu-cli-init-01/<run-id>/matrix-report.json`，只含脱敏 endpoint、bounded
文本摘要、digest/marker 和 credential ref；terminal preview 只对显式
project/run/workspace roots 做精确前缀替换，不使用泛化路径正则。每个 row 完成后，
harness 必须在该 CI-owned row root 内执行 typed、bounded、no-follow 的全普通文件
持久化扫描，至少覆盖 init-owned config、Host SQLite/WAL、report、trace、log 和
其它 durable artifact；symlink、特殊文件、I/O/竞态或扫描边界超限均 fail closed。
扫描只用当前进程已知 credential 值和 canary 作精确探针，输出只包含稳定 code、
相对 artifact class 和 count，不得回显值或具体路径。init-owned config 只能保存
secret ref，不能保存 resolved credential；report、config、log、trace 及其它非 Host
SQLite durable artifact 出现 exact credential value 均为 persistence violation。
secret canary 在任何位置出现都属于 violation。Host SQLite 及其 WAL 中出现 exact
credential value 是已裁决允许的 durable fact，只记录为 accepted observation，不计
violation，也不影响 row internal contract、availability 或 overall verdict。row
report 全文与最终 report 仍必须分别通过 credential/canary/authorization/request-id/
已知绝对 root scan 后才写入。持久化 violation 同时进入 row secret contract、
internal contract 和 overall verdict；accepted observation 不进入失败判定。外部不可用会继续其余 rows；credential missing、endpoint
unconfigured、transport unavailable、provider rejection 与 rate limit 只要真实
证据、脱敏和 no-fallback contract 完整即可通过总体 verdict。internal product bug、
未分类、secret leak、fallback 或证据矛盾仍使命令总体退出非零。

#### 5.1.2 `dayu-cli interactive` 第一轮 Mandatory Matrix

`interactive` 不是在 `prompt` 后增加一个输入循环。它同时拥有 invocation 级配置、TTY composer、单轮 Run 控制、
跨轮 Session/Memory、跨进程 label reconnect、terminal cursor 和 context compaction。第一轮运行前必须先生成并冻结
`interactive-inventory.json`、`interactive-mandatory-obligations.json` 和 `interactive-coverage-plan.json`；三者至少综合：

- `dayu.cli.arg_parsing.build_parser()` 产生的当前 help/参数 leaf；
- CLI 显式 composer bindings、运行态 key monitor actions、run view modes 和 terminal-result branches；
- session 创建/绑定、startup reconnect、terminal cursor、单轮 submit/cancel 与 REPL continuation 的公开状态；
- 当前 scene manifest、execution profile、tool selection、memory 与 compaction policy；
- 已冻结的 `prompt` scenario/oracle registry 中可复用的 coverage 维度、历史高风险组合和失败反例。

代码只能用于发现 branch、owner 和观测点，不能把当前分支的 outcome 写成 expected behavior。Inherited
`prompt_toolkit` 默认 key map 不要求穷举每个组合，但必须冻结库版本/模式，并覆盖下述用户可达的代表性编辑动作和所有
Dayu 显式 binding。运行前 coverage-plan validator 必须证明：parser leaf、显式参数、显式 key binding、运行态 key
action、terminal branch、precondition、input class、pairwise assignment 和高风险组合均有 stable obligation；
`unclassified_branch_count=0`、`missing_planned_scenario_count=0` 且无重复 claim。否则不得启动“全量”运行后再靠报告发现
本可在静态盘点阶段发现的 gap。

##### 5.1.2.1 从 `prompt` 复用的边界

`prompt` 已冻结的矩阵用于减少遗漏，不用于替代 `interactive` 的真实运行。复用规则如下：

| surface | 可以复用 | `interactive` 必须重新真实执行 |
|---|---|---|
| parser/help | 参数 identity、validator、互斥/依赖矩阵和已接受的通用 exit-code oracle | `interactive --help`、该 leaf 的合法/非法 invocation、无 positional prompt 与额外 positional 输入 |
| workspace/model | workspace/package config precedence、model id/credential 分类和 init-selected default 的 accepted predicate | package fallback、workspace config、init-selected default、`--model/-m` override 各自至少一次真实 interactive Run |
| logging | 第 5.1.3 节的 16-entry、冲突、debug-stream、log-file 和 append 矩阵定义 | interactive 长进程中的实际 ordinary/stream admission、每个入口的 primary Run、跨 turn 写入和进程 close 后落盘 |
| provider/tool/fallback | provider identity、原生 tool request/response 配对、failed-batch 与 fallback 的已接受语义 | interactive 单轮和跨轮的真实 provider、工具、失败/取消后 REPL 行为以及后续 turn 是否受污染 |
| signal/display | startup bootstrap、单次 Run 的取消和 Ctrl+T 维度 | composer idle、Run 各阶段、取消后恢复 REPL、第二 turn、label reconnect 和终端恢复 |
| 财报事实 | 已固定真实 corpus、source identity 和独立 financial oracle | 同一 interactive Session 内的真实读取、追问、证据复用/刷新、跨进程恢复和 compact 前后连续性 |

只有同时满足以下条件，既有 `prompt` evidence 才可作为 shared static owner 的 cross-command supporting evidence：执行在
进入 command runner 前结束；parser action/normalizer/validator identity 与 digest 相同；不存在 command-local
side effect；interactive 至少有一个同类 sentinel 真实执行；registry 明确引用 source scenario 和 shared owner claim。
第一轮 interactive calibration 中，所有 command-local primary operation、REPL、Session、screen、日志、Run、Tool
Trace、memory、SQLite 和 filesystem obligation 都必须重新执行。禁止机械复制 `prompt` scenario 后只替换 command
字符串，也禁止因 `prompt` 已通过而省略 interactive 的动态路径。

`prompt` 与 `interactive` 的公开参数中不存在 `--config`；二者只按 `--base/-b/--workspace` 解析 workspace config 或
package fallback。`interactive` 的公开参数中也不存在 `--ticker`。第一轮若从当前实现发现这些 legacy parser leaf，只能
记录为待删除 finding，并验证修复后 help、parser、inventory 与实现引用消失；不得为它们创建 accepted oracle/scenario，
也不得把 legacy 动态运行扩张成产品能力。

从 `prompt` 迁移矩阵时至少逐项处理：help/unknown/removed option、base/model/label、detail/thinking、
temperature/tool timeout/max iterations/fallback/failed-batch、日志入口与冲突、invalid UTF-8、credential/provider/network/
Host failure、startup/running/closeout cancellation、真实工具 request/response、真实财报读取和 fixed pairwise
assignments。`prompt` positional input、一次性进程终态和 prompt-only ticker 必须显式标记不适用，不能偷偷删除；
对应的 interactive composer 与 REPL continuation 必须建立新的 obligations。`--label` 是跨 CLI Agent 入口共享的
conversation alias，不得为 prompt 与 interactive 建立互不相通的 label namespace。

##### 5.1.2.2 Invocation、配置与运行参数

第一轮至少覆盖：

- 默认 `./workspace`、`--base/-b/--workspace`、空 workspace、已有 workspace、已有 `.dayu` 但缺 config、init 后
  workspace，以及 workspace config 缺失/普通文件/损坏/缺关键文件时的 package fallback 或 fail-closed 行为；
- 无 init 时 package default、init-selected default、显式 `--model` 和 `-m` 覆盖，以及语法有效但 catalog 不存在、
  credential 缺失和真实 provider rejection；
- `--label` 缺省、合法、空白、Unicode 和长文本；无 label 的每次 interactive invocation 必须证明创建 fresh Session，
  有 label 时必须证明该 alias 绑定到可由 prompt/interactive 共同恢复的同一 conversation；
- `--detail/--no-detail`、`--thinking/--no-thinking`、temperature、tool timeout、max iterations、fallback mode/prompt、
  max consecutive failed tool batches 的默认值、每个合法边界、非法格式/范围、互斥和 pairwise；
- 无 positional prompt 是合法 REPL invocation；额外 positional、unknown option、removed option、缺少 option value、
  invalid UTF-8 argv 和日志/参数错误必须在 primary operation 前观察；
- 全局参数位于 command 前/后、短别名和等价 spelling 的 accepted placement；重复参数按其 parser contract 全量观察，
  不假定“最后一个生效”。

高成本 provider matrix 不机械重复 init 的全部 provider choice；但 interactive 必须真实证明 package/workspace/explicit
三种 model resolution 路径、至少一个可用 provider 的多轮调用、至少一个真实不可用/rejection 路径，以及实际触发
compaction 时 ordinary scene 与 compactor 的 effective provider/model identity。已有 provider evidence 只能说明 adapter
可达，不能替代 interactive 的 scene assembly 和跨轮状态。

##### 5.1.2.3 Composer、输入与编辑状态

TTY 与 non-TTY 是不同 input class，必须分别执行。TTY composer 至少覆盖：

- 初次空 buffer、空白 buffer、普通单行、Unicode、长行、宽字符、组合字符和含前后空白输入；
- Enter 提交；Ctrl+J 与终端能够区分时的 Shift+Enter 均插入换行后继续编辑并提交；粘贴单行/多行；光标位于
  开头、中间、末尾时的插入。若终端把 Shift+Enter 编码为普通 Enter，必须记录 terminal capability 与 exact bytes，
  不得伪报已支持；
- Left/Right、Home/End、Backspace/Delete 的代表性编辑链，并记录提交前 exact buffer 和 cursor；
- 无历史时与至少两个已完成 turn 后的 Up/Down；Ctrl+R 无匹配、有唯一匹配和多匹配；选中历史后编辑再提交；
- Ctrl+X Ctrl+E 使用 CI-owned editor 成功修改 draft，以及 editor 缺失/非零/启动失败；记录临时文件是否残留、draft
  是否保留、stderr 和 REPL 是否继续，但不得读取或修改 CI-owned root 之外的用户 editor 配置；
- 非空 draft Ctrl+C、空白 draft Ctrl+C、空 draft 第一次 Ctrl+C、连续第二次 Ctrl+C，以及中间经过空输入、正常提交、
  已完成/失败/取消 turn 后 pending-exit 状态是否重置；
- composer 中单独 Escape、方向键产生的 CSI、Alt 组合和 bracketed paste；这些输入必须与 Run 中同 bytes 分开记录；
- Ctrl+Z suspend/SIGCONT 后的 buffer、screen、terminal mode 与 echo 恢复；
- 合法 UTF-8 与 raw invalid byte 的 TTY/non-TTY 输入边界；若终端/locale/文本解码层先拒绝，必须记录实际 owner，不能
  把 stdin decoding failure 与 argv parser failure 合并；
- non-TTY stdin 把从首 byte 到真实 EOF 的整个输入视为一个 draft：内部 LF/CRLF/CR 是 draft 内容，真实 EOF 是唯一提交
  边界，非空 batch 只创建一个 Run；覆盖空输入、单行、多行、最后一行无换行和流中的 literal `0x04`。禁止按普通换行
  拆成多个 turn；PTY raw key 不得归入本类。

non-TTY batch 必须把 CRLF/CR 规范化为 LF，沿用 TTY 已冻结的首尾空白规则并保留内部换行；空或纯空白 batch 不创建
Run、exit 0，非空 batch 在 EOF 后整体提交一次并在该 Run terminal 后结束进程，不恢复第二轮 REPL。真实 EOF 由 input
stream exhaustion 表达；流中的 literal `0x04` 是普通数据，不能冒充 EOF。non-TTY 屏幕不得输出 `dayu>` 等 TTY composer
提示符。非法 UTF-8 必须走稳定、脱敏的输入错误，不得暴露 Python codec exception 或 surrogate 文本。未来若要在一个
pipe 中表达多轮，必须新增显式 framing contract（例如独立的结构化输入模式）；不得把普通换行重新解释为 turn delimiter。

空白输入是否创建 Run、trim 后实际 user message、multi-line material、历史内容、屏幕重绘、stdout/stderr、terminal
echo/mode 和下一次 `dayu>` 都是 observation surface。Harness 需保存 key-by-key 时间线与关键虚拟屏幕，不能只保存最终
stdout；也不能从 EventLog 反推未被提交的 composer buffer。

##### 5.1.2.4 Ctrl+D Mandatory Matrix

Ctrl+D coverage 必须按实际 UI/Run 状态拆分，不能用一次 Run 中按键或 CLI 自报替代整个状态矩阵。第一轮
calibration 和以后每次适用的 `full-real` 至少真实运行：

- 初次进入 REPL、空 composer 时按 Ctrl+D；
- composer 非空且光标位于文本中间时按 Ctrl+D，并记录按键前后的完整 buffer、光标位置、屏幕和是否提交；
- composer 非空且光标位于文本末尾时按 Ctrl+D，并记录输入是否保留、进程是否继续；
- Run accepted 前、等待真实 provider response、真实 tool request/response loop 和 cancel/closeout 阶段分别按一次及
  连续多次 Ctrl+D；
- Run final、failed 或 cancelled 后 REPL 恢复 composer，在空 composer 和非空 composer 中分别按 Ctrl+D；
- non-TTY stdin EOF、关闭 PTY master、canonical-mode EOF 与 raw-mode `0x04` 分别作为独立 input class。

每个场景必须记录精确按键 bytes、发送时相对 UI/Run 状态、虚拟终端屏幕、composer buffer/光标、进程是否仍存活、
exit code/signal、Host Run terminal 状态、后续是否自动退出，以及日志和相关 SQLite/EventLog before/after。harness
不得用关闭 PTY、超时 kill 或 cleanup 冒充 Ctrl+D。只对 Dayu 的各状态建立 mandatory observation；用户主动询问其它
产品做法时可以另行回答，但该参考不进入场景 coverage，也不能替代任何 Dayu 状态的真实运行。

当 `cli.interactive.core-execution` oracle 适用时，conformance 还必须断言：空 composer 的 Ctrl+D 是正常 EOF、清理后
exit 0；非空 draft 中有光标下字符时删除该字符，光标在末尾时 no-op并保留draft；active Run 中一次或连续 Ctrl+D 均
不取消、不登记退出，只有 Run terminal 后回到空 composer 的新 Ctrl+D 才 exit 0。TTY Ctrl+D、non-TTY stream
exhaustion、literal `0x04`、canonical-mode EOF 和 PTY master close 始终分别取证。

`prompt` 是一次性命令，没有 composer 或 final 后 REPL。其 Ctrl+D obligation 只适用于命令仍在执行且终端按键监听
有效的阶段；interactive 的空/非空 composer、光标编辑和 final 后恢复场景对 `prompt` 必须标记为不适用，禁止为追求
矩阵对称而编造输入状态。

##### 5.1.2.5 Run 控制、type-ahead 与终端恢复

运行态至少区分 startup/pre-accept、accepted/provider wait、thinking/streaming、tool request、tool execution、tool
response continuation、fallback、terminal rendering 和 final-to-composer handoff。不是每种模型都会自然暴露全部阶段；
场景必须用真实 provider/工具和状态证据确认按键确实落在目标阶段，不能仅靠固定 sleep 命名场景。

每个可达阶段按风险组合覆盖：

- 单次 Escape、单次 Ctrl+C、连续 Ctrl+C，以及第一次取消后 closeout 中的后续 Ctrl+C；
- Ctrl+T 从初始 view 切换、再次切回、在无 activity/已有多条 activity/有 thinking 时切换、terminal 后第二 turn 再切换；
- `--detail`、`--no-detail`、默认 detail 与 thinking on/off 下 Ctrl+T 的屏幕和 Run 副作用；
- 一次/连续 Ctrl+D；普通 printable bytes、Enter 和完整 type-ahead 文本；
- Up/Down/Home/Delete 等 CSI sequences、Alt key 和 bracketed paste。运行态 monitor 若按字节解释输入，必须证明完整
  sequence 是被忽略、缓存、丢弃、进入下一 composer，还是因 ESC prefix 触发控制动作，不能只测试单字节 Escape；
- Ctrl+Z/SIGCONT、SIGWINCH/终端宽度变化、窄终端长 activity/thinking 和 Unicode 宽字符。

单次 Run succeeded/failed/cancelled 后都要观察是否回到 `dayu>`、下一 turn 能否真实提交、terminal mode/echo 是否恢复、
先前 type-ahead 是否意外提交。若进程退出，记录 exit code/signal 和是否完成 Host/attachment/display/key-monitor 清理；
若进程继续，不能把单轮 cancel 的 terminal status 冒充 process exit 130。重复 Ctrl+C 必须同时检查用户观感、process
生命周期和 Host canonical terminal，不能只检查其中一个。

当 `cli.interactive.core-execution` oracle 适用时，running-input conformance 必须同时断言：standalone Escape 在每个
active-turn 阶段取消当前 Run、等待 canonical cancelled 后恢复 composer且不退出；完整 CSI、Alt 与 bracketed-paste
sequence 进入 composer 编辑/导航/draft，不得因 ESC prefix 误取消。第一次 Ctrl+C 在所有 active-turn 阶段都登记同一
graceful cancel intent；连续第二次只登记 exit-after-cancel，必须等 Host terminal 与本地资源清理完成后 exit 130。

active Run 期间未按 Enter 的 composer draft 必须跨 terminal handoff 保留；按 Enter 默认提交一个 QUEUE follow-up，
不得丢弃或隐式 STEER，且在当前 Run terminal 后恰好执行一次。STEER 只能由明确、独立的 UI action 选择。startup 尚无
Run/composer 时一次 SIGINT 清理后 exit 130且无 traceback；Host `lost` 显示明确错误并 exit 1，不恢复可写 composer。

##### 5.1.2.6 Session、label、reconnect 与 cursor

至少建立以下相互独立的 state chains：

1. 无 label 的 fresh invocation：同一进程至少两个成功 turn，随后正常 EOF；新进程不应因测试 harness 假定而被当作
   同一 Session，实际 Session identity 由证据记录并交用户裁决。
2. label 首次绑定：第一 turn 前的 Session/slot/cursor 状态、多个 turn、正常退出；同 label 新进程 reconnect 后继续
   提交追问。
3. reconnect 去重：已展示 succeeded/failed/cancelled terminal 后重启，观察是否重复展示；terminal cursor 文件的
   before/after、EventLog terminal sequence 和新 turn cursor advance 必须一致。
4. 未完成 Run recovery：通过真实 CLI 启动有 label 的 Run，再以明确记录的进程崩溃/终端断开/受支持退出路径构造
   precondition；第二个真实 interactive 进程观察 running/cancelling/terminal promotion。Harness termination 只能作为
   recovery precondition，不能被报告为 Dayu 的取消或退出行为。
5. 相同 label 的两个并发 interactive 进程：空闲/一方 running/双方提交三种时序，记录 queue/rejection、每个客户端
   屏幕、唯一 Run identities、terminal cursor 和最终 Session 状态。
6. 同一文本 label 在 `prompt --label` 与 `interactive --label` 之间双向续问，必须解析为同一个 durable
   conversation/Session；分别以 prompt 创建后由 interactive 继续、interactive 创建后由 prompt 继续，并用 Session id、
   prior-turn runner input 与 memory continuity 证明，而不是从回答猜测。另用 `session` CLI 做只读查询；该查询只证明
   interactive 生成物可消费，不提前裁决 `session` 命令自身的 UI oracle。
7. 同 label 新 invocation 更改 model 或其它 run override，区分 durable Session/Memory 与 invocation-local
   scene inputs；不得从最终回答猜 effective 配置。
8. active Run 期间由 composer Enter 提交并进入 queue 的 follow-up，在当前 interactive 退出后，用同 label 重新运行时
   必须由 Host ordinary governance 自动 promotion/执行且恰好一次；记录 queued Run identity、退出前后状态、fresh
   read-write attachment recovery、provider 调用与terminal。不得用 harness 重发同一文本冒充 queued Run 自动恢复。

还必须覆盖空白/Unicode/长 label、cursor 文件不存在/损坏/路径冲突/不可写、Host DB 或 runtime DB 路径冲突，以及
startup reconnect 在任何 composer 输入前产生 terminal/error 的屏幕顺序。禁止写 SQLite 私有表伪造目标状态；若只能
通过 harness 构造异常，必须使用公开 CLI/文件系统前置动作并清楚标记 setup 与被测 observation 的边界。

unfinished recovery 与 cancel non-resurrection 必须建立独立矩阵。每一行都分别覆盖没有用户 cancel facts 的正常
opener/process close、可诊断 crash 与 SIGKILL，并通过同一 label取得fresh `READ_WRITE` attachment；另对相同状态在
accepted cancel和terminal cancelled后重复三类终止。无label invocation是fresh Session，不能用来判定旧Run恢复。

| durable precondition | 无 cancel facts 的同 Session 重连 | 已接受 cancel / terminal cancelled 后重连 |
|---|---|---|
| `RUNNING` | positive orphan proof 后，同一 Run 以 new Attempt/new execution id恢复并最终terminal | watchdog/closeout推进或保持`CANCELLED`，不恢复执行 |
| `QUEUED` | 保持同一 Run，按FIFO ordinary governance promotion并恰好执行一次 | 直接或保持`CANCELLED`，不创建Attempt |
| durable accepted steer | 保持同一 Run，按最新accepted steer candidate以new Attempt继续且恰好一次 | 按canonical commit order取消；已取消continuation不恢复 |

每个恢复场景必须保存旧/new Host instance、Run/Attempt/execution identity、accepted/cancel/recovery EventLog顺序、positive
orphan proof输入、provider/tool request、terminal、memory、cursor和重复执行检查。只有durable accepted input才可恢复；
acceptance前键盘输入不得猜测补回。恢复不得takeover旧Attempt，不得由CLI/harness重发输入或修改private SQLite伪造。
若recovery policy放弃、必要facts缺失或预算耗尽，必须进入明确`FAILED`/`LOST`，不能无限停留`running`。
若fresh writer在旧heartbeat达到stale threshold前立即attach，场景必须继续越过该threshold观察同一invocation是否执行
delayed reclassification/reconcile；产品不得要求用户在threshold后再次手工重启interactive。判定时记录真实policy threshold、
两端heartbeat/PID/start token和每次scan/reconcile时间，不能仅用固定sleep猜positive orphan proof。

accepted cancel facts是恢复分类的硬边界：`CANCELLING`先由accepted-cancel watchdog处理，不得按普通orphan创建recovery
Attempt；terminal `CANCELLED`不可改写，重连不得调用provider、再次执行queued/steer input或重复投影旧terminal。
正常close/crash/kill本身不是cancel；interactive双Ctrl+C因已表达显式cancel intent，必须先完成`CANCELLED`再exit 130，
随后重连适用non-resurrection而非unfinished recovery。

##### 5.1.2.7 多轮工具、Memory、财报与 Compaction

低成本 smoke 不能替代以下真实 Session 场景族；核心连续性场景必须在同一 Session chain 中完成：

- 普通问答后使用“继续”“刚才那个”“第二点”等指代追问；
- 对固定真实财报先 discovery/read，再追问数值、原因、来源和前一回答中的具体风险点；
- 已有证据足够时的复用，以及 ticker/期间/口径改变时的必要刷新；记录实际 tool call count 和 request/response；
- 用户纠正事实或切换主体后，后续回答、memory projection 和工具参数如何变化；
- tool not_found/error、handshake timeout、failed-batch threshold 的 raise_error/force_answer、provider failure、单轮
  cancelled 后，若屏幕仍提供 composer 则尝试再提交一个正常 turn；若进程已经退出则记录无法继续的直接事实，不能由
  harness 重启后伪装成同一 REPL continuation；
- 至少一个真实 web tool 和真实 Fins read路径。真实财报主体必须来自用户prompt或同一Session已接受的业务上下文，不能
  通过removed `interactive --ticker`注入；至少一次完整保存`list_documents`到最终read tool的request/response、accepted
  EventLog、memory、runner input、Host SQLite与final answer grounding；
- `dayu-cli download`与`dayu-cli preprocess/process`的UI、生成物、退出码和正确性只由各自command campaign裁决；
  interactive campaign可以把其已有真实corpus作为前置条件，但不得用interactive工具调用或准备步骤提前关闭这些命令的
  oracle；
- 同 label 跨进程延续上述财报追问，区分 Host/Memory continuity 与仅存在于当前进程的 composer history。

failure-continuation chain必须区分“已接受的失败工具结果”与“没有accepted response/final answer的Run失败”。not_found等已
accepted tool response可以作为上一轮可读结果支持后续解释；handshake timeout、provider failure或cancel不得被伪装成
成功工具事实或业务结论。每条chain都要在同一可写Session中提交下一Run，验证per-Run failed-batch预算重置、composer
恢复、下一Run真实provider调用与terminal；无label harness重启不能冒充同一REPL/Session连续性。

第一轮还必须覆盖accepted negative observation之后外部业务状态发生变化的链路，不能把“下一轮记得not_found”误当成
完整的temporal-update验证。至少在一个起初没有MSFT文档的独立workspace和同一interactive Session中真实执行：

1. 用户询问MSFT财报，保存`list_documents(MSFT)`的真实`not_found` request/response、`TOOL_RESULT_ACCEPTED`、memory和
   下一轮runner input；
2. 用户输入“下载微软财报”，由模型真实调用`start_fins_download`并等待accepted terminal result，同时记录Fins source
   repository、文件生成物、EventLog、Tool Trace、memory和SQLite前后变化；本链路没有预处理环节，不得插入
   `start_fins_preprocess`或独立`preprocess/process`命令改变前置条件；
3. 用户再次提出需要当前MSFT财报才能回答的问题，完整记录模型是否重新调用`list_documents(MSFT)`、随后实际read tool
   request/response、旧`not_found`与新下载证据在memory/runner input中的投影、最终回答及grounding；
4. 若模型没有刷新、下载后仍`not_found`、读取失败或直接使用模型记忆回答，照实记录为observed behavior并交用户裁决，
   不得由harness补发工具指令、删除旧memory、预先写入文档或把旧negative observation解释成永久事实。

该场景只裁决interactive中的跨轮memory、工具选择、freshness与最终回答；`dayu-cli download`及
`dayu-cli preprocess/process`独立命令的UI、生成物、退出码和正确性仍由各自command campaign裁决。

必须在 interactive 中真正触发至少一次 context compaction。场景在同一 REPL/Session 中用真实用户输入、真实
provider 和真实工具结果累积上下文，直到 EventLog/runner-call evidence 出现实际 compaction operation；仅出现
context budget evaluated、低剩余 token 估计或 compaction 配置不能算触发。报告至少对比 compact 前后：

- ordinary scene 与 compactor 的实际 provider/model/endpoint/credential ref、runner inputs 和 outputs；
- 被 compact 的 event/turn 范围、artifact identity/digest、memory snapshot/projection 与 RunInputBuilder material；
- 财务事实、单位、期间、source refs、answer anchors、open question 和用户纠正是否保留；
- tool request/response/evidence continuity、是否重复调用、是否把内部治理状态投影给 LLM；
- compact 后至少两个真实 follow-up turn，其中一个引用 compact 前财报事实，另一个改变口径或请求新证据。

可使用 CI-owned 合法 config 选择较小但真实受支持的 context profile以控制成本；必须保存完整 config diff、证明该
profile 经 production config loader/Service assembly 生效，且不得注入 memory、伪造 assistant/tool result、直接写
EventLog/SQLite 或调用内部 compactor API制造触发。

##### 5.1.2.8 Terminal outcome、屏幕与 evidence closure

真实可达的 succeeded、failed、cancelled、lost/startup-recovery terminal 分支必须逐项观察。无法在不破坏 private
state、伪造 Host response 或越过授权的情况下到达的 defensive branch，必须在 inventory 中给出 unreachable/out-of-
scope 证明和 owner-level test ref；不能静默漏掉，也不能为了“覆盖”写 SQLite 或 fake terminal result。

每个 stateful scenario 除第 11 节通用材料外还必须保存：

- asciinema/raw PTY transcript、按键时间线，以及 composer 前/后、每次 view 切换、terminal 渲染、恢复 `dayu>` 的
  VT-compatible screen snapshots；
- stdout、stderr、exit code/signal、process 存活时间线、termios/echo before/after 和子进程（editor）状态；
- workspace manifest/diff、config、log/append bytes、terminal cursor 和 compaction artifacts；
- Session/slot/attachment、每个 Run/Attempt terminal、EventLog、Tool Trace request+response、memory store/projection、
  runner input、runtime lane 和相关 SQLite bounded before/after；
- 每轮 user input、effective scene/model/provider/overrides/tool schema、final answer 与真实财报 source 的关联；
- failed/cancelled/reconnect/compaction 后下一轮行为，以及进程关闭后的 Host stopped、attachment 释放、runtime lane
  claim 清零和不应存在的后台进程/锁。

运行完成后先以 inventory 和 coverage plan 重新计算 obligation closure，再生成单一 frozen
`observed-behavior.md`。运行中发现真正的动态新 branch 时，必须加入 inventory 并补跑；但 parser、显式 key binding、
已知状态机或 prompt 历史反例中本可预见的漏项属于 pre-run planning failure，不能把零散补跑报告伪装成一次完整运行。

#### 5.1.3 日志参数 Mandatory Matrix

日志等级 selector 的语义等级为 `debug/verbose/info/warning/error/critical/quiet`；`warn` 是 `warning` 的等价拼写，
两者必须并存。显式入口与快捷别名完整集合为：

```text
--log-level debug       --debug
--log-level verbose     --verbose
--log-level info        --info
--log-level warn        --warn
--log-level warning     --warning
--log-level error       --error
--log-level critical    --critical
--log-level quiet       --quiet
```

上述 16 种 entry form 都是同一个日志等级 selector 的输入形式。一次 invocation 最多出现一次 selector；低成本
real-contract matrix 必须生成并运行全部有序双 entry 组合，包括同一 entry 重复、`warn/warning` 混用、显式入口与其
等价别名并用及 argv 顺序互换，验证都在 primary operation 前以 parser misuse 退出 2。不得只抽样几个冲突，也不得
接受“最后一个值生效”。

每个 entry form 都必须分别在有、无 `--log-file` 时执行真实 CLI primary operation，记录实际 effective ordinary
log policy、stdout/stderr、日志文件、exit code 和 Run/SQLite before/after；`warn` 与 `warning`、每个
`--log-level` 与其快捷别名必须证明语义等价，不能只证明 parser 接受。`quiet` 表示关闭普通诊断日志，不是 `error`
别名；指定 `--log-file` 时不允许截断既有内容。

`--debug-stream` 是 selector 之外的正交开关：单独使用时基于默认 `info`，可与 `debug/verbose/info/warn/warning/
error/critical` 的每个显式入口和快捷别名组合，但不得改变所选 ordinary log policy；它只额外启用高频 stream
delta、SSE 和逐 delta ingest 诊断。它与 `--log-level quiet`、`--quiet` 冲突，两个 argv 顺序都必须在 primary
operation 前退出 2。每个合法组合必须通过真实 streaming Run 证明 ordinary 与 stream 两个维度同时生效；不得只
检查解析结果或 runtime 自报等级。

`--log-file` 独立于日志等级 selector 和合法的 `--debug-stream` 组合。append chain 必须用同一路径连续运行至少两次，
以内嵌 bounded 内容和 before/after bytes/digest 证明第二次保留第一次完整内容并只在末尾追加；只比较文件大小、
日志行数或 CLI 自报不能证明 append。

#### 5.1.4 Exit Code Mandatory Matrix

CLI exit code 必须由终止原因的语义 owner 确定，不能把所有非成功结果压成同一码，也不能让相同错误因触发代码路径
不同而漂移：

| exit code | 确定性语义 |
|---|---|
| `0` | primary operation 正常完成，或 help、正常 EOF 等适用的正常退出 |
| `1` | 动态配置、资源解析、credential、provider、网络、Host 或 terminal Run 等应用/运行失败 |
| `2` | invocation 违反公开 CLI 参数契约，包括结构、缺失值、类型/格式、枚举/范围和互斥关系 |
| `130` | 当前一次性命令因用户 Ctrl+C、Escape 或其它已接受的取消输入而终止 |

边界场景必须分别真实运行：`--model` 缺少值属于 exit 2；语法有效的 model id 在本次动态 catalog 中不存在属于
exit 1；配置 JSON 存在但损坏属于 exit 1；credential 缺失、provider rejection 和 Host/Run failure 属于 exit 1；
日志 selector 冲突属于 exit 2。`interactive` 取消当前 Run 后若按其 oracle 恢复 REPL 而不结束进程，则不能伪造
process exit 130；只有进程确实因该取消终止时才适用。

mandatory matrix 至少覆盖 unknown command/option、缺失 positional/option value、非法 choice、非法数值格式、越界
数值、每类互斥冲突、unknown model、malformed config、缺失 credential、真实 provider rejection、真实
network/timeout、Host/terminal Run failure 和用户取消。工具返回 error/not_found 但 Run 按其策略继续时，不能仅因
tool result 非成功就强制进程退出 1；exit code 由最终 command/Run outcome 决定。每项必须关联 stderr/screen、
exit code/signal、Run 是否创建、
durable terminal、文件/日志和 SQLite/EventLog before/after；同一 exit code 仍必须保留明确且脱敏的错误原因，不能
只显示“失败”。exit code 只是 contract 的一个维度，不能替代实际副作用和 durable state 验证。

其它命令必须按同一原则从其状态、选项、输入、组合、跨命令消费和 evidence obligations 派生矩阵。第一轮和以后每次
完整 `full-real` 都运行全部 mandatory scenarios；`focused-real` 只用于局部复现/修复验证，不更新全量 coverage、
registry readiness 或完整 CI 结论。

#### 5.1.5 `dayu-cli download` 第一轮 Mandatory Matrix

`download` 是独立 command campaign。其它命令为了准备真实 corpus 而调用 download，只能证明该 corpus 的来源与可消费性，
不能替代本节对 download 自身的参数、UI、生成物、失败、取消和恢复语义进行观察与裁决。第一轮必须先从当前 parser、
Service、Fins runtime、市场 adapter、source-specific workflow 和 storage owner 生成 obligations；下面是最低集合，不是可用
当前实现行为填充的预期结果清单：

- **公开 invocation**：help、缺少/空/非法/边界 ticker，默认 workspace、`--base/-b/--workspace`、绝对/相对/Unicode/
  空白/symlink 路径，未知 option、缺少 option value、额外 positional、重复 option、CSV/alias 形态，以及所有共享日志入口。
  help 中不存在的 source selector 不得由 Agent 编造；若实现内部固定 `auto`，报告只记录该实际装配事实。
- **市场与真实来源**：US、CN、HK 各至少一条真实成功下载，分别冻结实际 SEC、CNInfo、HKEX source identity、canonical
  ticker、document id、form/period、filing/report date、primary file、全部业务文件 digest、manifest/meta 和来源 URL。US 还要
  覆盖国内发行人、foreign issuer、amended/SC13 与 6-K 分类路径；CN/HK 要覆盖至少一个实际 PDF + Docling 产物。
- **forms 与日期**：无 forms、每个 form family、别名/大小写/中文拼写、多 forms、CSV、重复、空项、非法项、超长和数量
  边界；无日期、year/year-month/full-date、单边窗口、精确窗口、无结果窗口、非法日期、超长和 start-after-end。默认 form/
  lookback、SC13 补拉/回溯、CN/HK missing-period 等代码分支必须分别获得真实观察或显式 gap；不得只相信 pure helper 或
  pipeline summary。默认 form 与 missing-period 必须按市场适用规则生成：A股默认集合是 `FY,H1,Q1,Q3`，制度上不存在的
  独立 Q2/Q4 不得进入 effective forms 或 missing；港股主板以年度和中期材料为基础集合，季度材料按发行人实际披露发现，
  不得把 Q1～Q4 当作所有发行人的必有材料。选定发行人实际公开了可选季度材料时，CI 必须对照发行人/交易所公开来源验证
  discovery 与分类，不能因为该材料不是强制披露就允许漏选；腾讯 `0700` 必须覆盖其实际发布的 Q2 与合并年度/Q4业绩材料。
- **workspace 状态**：fresh、init 后、已有完整 source、部分/损坏 source、目标路径冲突、只读 workspace；每种状态都记录
  command 开始前是否已产生目录，以及失败后是否存在半发布、旧文档丢失、临时 staging、锁或 recovery residue。
- **重复、overwrite 与 rebuild**：首次下载、无 overwrite 重复、overwrite、rebuild 分开运行；`--overwrite --rebuild` 与
  `--rebuild --overwrite` 必须作为互斥 usage error 在业务 operation、网络访问和 workspace 写入前 exit 2。合法场景必须用
  原始文件/meta/manifest/processed 的 before/after bytes 和 digest 证明实际行为；`--rebuild` 的名称、自报或 help 不能代替
  downstream processed 状态及后续 `process` 真正消费验证。还要观察 overwrite 在现有目标损坏时能否安全修复，以及失败/
  空结果/取消是否保留旧文档和非目标文档。
- **结果分类**：真实覆盖 downloaded、skipped、rejected、failed、zero-match、rejected-only、downloaded+rejected、可达的
  partial failure。`discovered/downloaded/skipped/rejected/failed` 必须与实际候选、rejection artifact 和 source publication
  逐项对账；CLI summary、missing-period 占位和已有 rejection 的再次分类都不能自证正确。
- **并发、中断与恢复**：同 workspace+同 ticker、同 workspace+不同 ticker，very-early Ctrl+C、provider/network wait、文件
  下载、转换和 publication 各适用阶段的 Ctrl+C；至少一个真实 process crash/kill 后以同一 workspace 重跑。记录屏幕、
  signal/exit、operation 是否达到 canonical terminal、后台工作是否继续、锁/staging/half-document、旧文档保持和 retry
  结果。harness deadline 导致的 kill 必须与产品取消分开标记。
- **外部配置与诊断**：有/无 SEC User-Agent、真实 provider transport failure、日志等级、`--log-file`、quiet 和
  `--debug-stream`。报告必须扫描 stdout/stderr/log/evidence 中的 exact credential/contact canary，只报告名称类别与计数，
  不回显值；同一 warning 的重复、只写 log 未写屏幕、以及过度泛化的失败文案都交用户裁决。
- **跨命令消费**：至少一个 US 和一个 CN/HK source 由 production read/process 路径重新加载；若 download 的业务范围只负责
  source publication，报告应把后续命令仅作为“产物可消费”证明，不在本 campaign 裁决后续命令。反向检查不得绕过
  `dayu.fins.storage` 私有布局生成 SUT 成功结论。
- **全层取证**：每个场景保存精确 argv/cwd/非秘密环境/stdin 或按键时间线、stdout/stderr/screen、exit/signal、耗时、
  filesystem before/after/diff、关键文件内容/digest、日志、Fins public state，以及 Host SQLite、runtime SQLite、legacy
  ingestion job、EventLog、Tool Trace 的 before/after 或基于代码路径和实际文件扫描的 not-applicable proof。direct command
  未创建这些 durable facts 时要记录“已查询且不存在”，不能写成“未检查”。

高成本 live download 不要求执行 form × date × market 的无收益全笛卡尔积；允许由同一 owner 的低成本参数场景、pairwise
组合和代表性真实来源链关闭等价 obligation。但不同 parser/runtime/workflow/storage owner、真实成功/拒绝/失败分类、默认
业务规则、破坏性副作用、并发、取消和 crash recovery 不能互相抵扣。代码检查发现新的动态分支后必须先扩展 inventory，
再补跑或登记显式 gap；只有 frozen observed report、用户逐 predicate 裁决、accepted oracle/scenario registry 和 readiness
proof 全部完成，才能宣称 download 第一轮闭环。

### 5.2 验证层级

场景按执行成本分为：

1. Real contract：启动真实 CLI 进程，验证 help、参数错误、互斥关系和无需模型执行的命令契约。
2. Fixed real corpus：使用来源真实且身份/digest 固定的财报、真实 Fins storage/read tools、真实 Host/SQLite 和真实模型 provider，完成可重复的业务场景。
3. Live provider：使用真实模型 provider 和当前运行配置，验证 prompt assembly、tool selection、模型交互及多轮行为。
4. Live external tool：使用真实网络、Fins 下载、预处理、上传或其它外部服务，验证最新数据、长事务、取消和恢复。

固定真实财报 corpus 用于提供稳定 oracle，但不能被改写为伪造工具结果或伪造模型调用。低成本场景负责完整
command/parameter/interaction/input coverage；高成本场景的 mandatory set 由 pairwise、高风险组合和代表性端到端
obligations 决定，而不是任意抽样。真实 provider 的非确定性通过结构化 oracle、重复运行和通过率处理，不允许为了
稳定结果切换到 mock runner。

只有两个 registries 的 readiness proof 都重新校验通过，且所有 mandatory correctness surfaces 都有适用的 accepted
oracle/objective/hard contract 时，profile 才能是 `full-real`。否则总控必须使用 `calibration-real`，继续执行并补齐
完整 mandatory matrix、evidence 和用户裁决，不能用局部候选清单结束第一轮。

## 6. 执行与取证流程

每个独立场景在独立 workspace、独立 session label 和独立日志目录中运行，避免前序状态污染。明确声明的
cross-command chain 可以在该 chain 专属的 workspace 中共享前序状态，但必须记录 chain identity、逐步
before/after snapshot 和每一步的消费结果；该 workspace 不得再被无关场景复用。

标准流程必须采用 before / execute / after 顺序：

1. 固定 run id、target/workspace canonical identity、runtime、terminal、非秘密 config、authorization、resource
   budget、parser/interactive inventories、mandatory obligations 和 registry identity；记录 `session_id`、`run_id`、
   `attempt_id`、`execution_id` 和 `tool_call_id` 的生成与关联规则。
2. 在任何场景执行前，对 CI-owned workspace/run root 做 bounded before snapshot，记录文件 manifest、生成物、Host
   public reads、Fins public state、与该场景相关的 SQLite schema/关键 rows 和其它必要 durable facts 的 evidence
   refs；不得扫描或读取授权范围外路径。
3. 对每个场景记录 stable coverage claims、精确 invocation、cwd、非秘密环境、脱敏 config/profile、stdin/按键/交互
   输入和相对时间线；先核对公开 contract/help/interactive inventory 依据、输入类别、primary operation/read flow 和
   required evidence，不预设执行结果。
4. 真实执行每个 mandatory scenario。非交互命令直接执行；交互命令使用可编程 PTY 或 detached tmux pane。每个合法
   选项、错误选项、Esc、Ctrl+C、Ctrl+D、EOF 或等待动作都必须按相应 obligation 记录精确输入和时间线。
5. 分别保留 stdout、stderr、exit code/signal、timeout/cancel 原始状态、开始/结束时间和关键 screen/cast；
   `execution_outcome` 只记录 `success/error/timeout/cancel`。`not-run/blocked` 记录为 coverage gap，不伪造 outcome。
   若 PTY/tmux harness 自身的等待条件、按键发送、输出捕获或清理动作失败，该 attempt 必须标为
   `harness-invalid`，保留为诊断证据并用新 scenario/attempt identity 重跑；不得把 harness kill、harness timeout
   或不完整 screen 计入产品的 timeout/cancel 行为或 mandatory coverage。只有场景预先声明了 bounded deadline，
   且 harness 能证明目标进程在 deadline 内持续无反馈时，才可把超时作为产品观察结果。
6. 执行 bounded after snapshot，并生成 created/modified/deleted artifact 清单、关键内容的脱敏 inline
   before/after diff、content/metadata digest 和 raw refs；执行该场景声明的真实 cross-command load/query/consume
   assertions；明确区分“没有变化”“未观察到变化”和“证据无法覆盖变化”。
7. 收集独立 debug log、Host public reads、按第 11.2 节执行相关 SQLite before/after 观察、EventLog canonical facts、
   Tool Trace、memory snapshot/source refs/diagnostics、runner-call input reconstruction、UI/final answer 和跨层
   identities。debug/private SQLite 只用于诊断，不能替代其语义 owner。
8. 完成脱敏、mock/fake absence、artifact presence/digest、identity correlation 和 evidence integrity 检查；
   分别记录 `evidence_status`、`gap_kind`、owner 和 next evidence action。
9. 先按第 11.1 节生成单一、人类无需重跑即可裁决的 `observed-behavior.md`，计算
   `observation_completeness`，完成 exact UTF-8 bytes SHA-256 准备并冻结；只有 freeze 后才允许 AgentMiMo /
   AgentDS 基于同一 report 独立 review、形成正式 suggestions、由总控 synthesis 并交用户裁决。确定性断言、
   suggestions 和用户裁决不得回写 observed facts。

tmux 主要用于需要多轮输入、异步观察和长事务控制的真实交互。无需人工观察的真实 CLI 场景优先使用可编程 PTY，以降低时间和环境不确定性。PTY 和终端模拟器只是输入与取证设施，不替换 Dayu 的任何生产组件。

## 7. CLI 与终端行为验证

### 7.1 外部 Agent CLI 只作为按需参考

Dayu CLI/UI 的 mandatory matrix 只从 Dayu 的命令、参数、交互状态、用户输入类别、设计真源、hard contract 和用户
已接受的 oracle 派生。Codex、Claude Code 或其它 Agent CLI 不是 CI target、架构真源或 correctness authority。

只有用户主动询问“其它产品怎么做”或要求 Agent 比较最佳实践时，Agent 才按需查询或真实观察对应产品，并在当前对话
中说明参考结论及不确定性。该参考不写入 `observed-behavior.md`，不建立 scenario/reference obligation，不要求冻结
版本、录屏或 artifact digest，也不进入 oracle registry、coverage 统计、evidence gap、correctness closure 或
registry readiness。

外部产品参考可以帮助用户理解替代方案，但 Dayu 的正确行为仍必须由用户针对 Dayu 的具体 predicate 裁决。即使
Dayu 与某个外部产品行为相同，也不能写成“因为与 Codex 一致所以正确”；即使无法访问外部产品，也不影响 Dayu
observation、oracle calibration 或 CI readiness。

### 7.2 终端状态检查

asciinema cast 的原始输出仍保留已被 ANSI 控制序列清除的文本，因此不能通过 grep cast 判断清屏是否成功。

CI 必须用 VT100/xterm 兼容终端模拟器回放 cast，并保存关键时刻及最终虚拟屏幕快照。下列内容都是 mandatory
observation surfaces：calibration 时记录 Dayu 的实际表现并交给用户裁决；registry ready 后才按 accepted
predicate 断言，不能把当前实现写法预设成 oracle：

- 第一个 thinking delta 新起 `Thinking:` 行，后续 delta 在同一显示区域追加。
- activity / thinking 在运行中按配置可见。
- `--no-detail` 和 `--no-thinking` 不显示对应运行态内容。
- final answer 到达后，最终屏幕中不残留 activity / thinking。
- final answer 本身不被清除或覆盖。
- interactive 终态后恢复 `dayu>`，且下一轮输入可继续执行。
- 取消回显不泄漏 `cli_sigint` 等内部 reason。
- 终端宽度变化、长文本和多次刷新不产生错位或重复行。

## 8. LLM-facing 文本验证

验证对象必须是实际进入模型上下文的最终 material，而不能只审查 prompt 源文件或 scene manifest。

每次真实 runner call 至少检查：

- 最终 system / user / assistant / tool messages。
- scene prompt 和 prompt fragments 的实际渲染结果。
- `when_tool` 过滤后的内容。
- context slots 的展开结果及空值消除。
- attempt-local effective tool schema snapshot。
- memory、compact、trace 和 accepted evidence 的 LLM-readable material。
- tool request/result continuation 和 wait resume input。

确定性检查至少包括：

- 未选择的工具不出现在 tool schema 或相关 prompt 指引中。
- prompt / schema / memory 不要求模型理解 Host、Engine、poller、wait record、runtime state、digest、cursor 等非必要内部术语。
- 裸 `event_id`、`payload_ref`、digest、cursor 或 `tool_call_id` 不替代业务语义。
- tool schema 的参数名称、业务含义、类型、必填性和允许值自足。
- tool result 和 evidence material 包含足以解释结果的 request/query 语义。
- 治理状态不被伪装成财报事实或用户可见业务结论。
- prompt、tool schema 和 memory 之间不存在相互冲突的动作要求。

字符串扫描只能发现明确泄漏，不能证明文本具备足够的自解释性和低认知负担。因此，每个新增或变化的 LLM-facing surface 还需要 AgentMiMo / AgentDS 对实际 runner input 做两路独立语义 review，由总控裁决。

## 9. Conversation Memory 多轮验证

GitHub Issue #80 是 Conversation Memory 的评测标准和行为 oracle。CLI CI 应复用其维度，以真实财报、真实 Fins 工具和真实模型 provider 构造多轮场景，但不能在 #81 的 post-memory contract 稳定前宣称完成 #80 的最终验收。

场景至少覆盖：

1. Trace continuity：追问“刚才那个”“继续”“第二点展开”时定位正确上下文。
2. Evidence-backed fact recall：已确认财务事实跨轮保留，且仍能追溯 accepted evidence。
3. Temporal update / conflict：新事实替代旧事实时使用当前有效事实，并保留冲突或替代关系。
4. Abstention：缺少足够证据时拒答、澄清或表达不确定性，不用 memory 幻觉补洞。
5. Task state / forward intent：open question、待验证假设和后续意图能延续，但不能自动驱动工具执行。
6. Dynamic profile：新偏好生效，但不压过本轮明确输入或财报证据。
7. Tool reuse efficiency：已确认事实不被无意义重复获取；需要刷新时能够解释重新调用原因。
8. Context pressure / compact：长输入、长工具结果和多次 compact 后仍保持 bounded、可解释和可追溯。
9. 财报场景：跨年度/季度指标、多公司对比、口径变化、脚注弱信号和前序风险点追问。

`interactive` 是 context pressure 与实际 compaction 触发的 mandatory command owner，必须在同一 REPL/session 中累积
真实多轮上下文并观察 compact 前后行为。一次性 `prompt` 不承担“必须触发 compaction”的 coverage obligation；prompt
run 未触发 compaction 必须标记为 command-scoped `not-applicable`，不能计作 prompt coverage gap。

多轮场景不得通过注入预制 assistant answer、伪造 tool result 或直接写 memory snapshot 来制造前序记忆。每一轮都必须由真实 CLI 提交，经真实 Host/EventLog、真实工具调用和真实 runner call 形成下一轮可用上下文。固定真实 corpus 只固定财报来源和 oracle，不固定或替代 Agent 的执行过程。

每个场景不能只评价最终回答，至少同时验证以下两层，核心场景应覆盖全部层次：

- Memory Truth / Store：EventLog、accepted evidence、artifact refs。
- Memory Projection：snapshot、source refs、更新与淘汰结果。
- Prompt Assembly：RunInputBuilder 实际注入的 memory messages、预算和相关性。
- Tool Behavior：调用次数、参数、复用或刷新原因。
- Agent Outcome：最终事实、来源、不确定性和指代解析。
- Diagnostics：projection lag、repair、compact 或 provenance 问题分类。

特别需要检查：有无 `TOOL_AWAITING` 时，普通工具 request/result 的 LLM-facing continuity 是否保持等价；Host / ToolRuntime 治理事实不得进入 Conversation Memory。

## 10. 实际财报分析功能验证

CLI、Host、tool loop 和 memory 行为正确，只能证明 Agent 运行框架可用，不能证明其具备可靠的买方财报分析能力。CI 必须增加独立的财报业务验收轴，并把工具取数、证据检索、模型分析和最终回答分层评分。

### 10.1 验证真源

财报分析场景必须使用可复核的原始财报、公告、XBRL、表格或其经过 digest 固定的仓储快照作为事实真源。固定基准场景应锁定 ticker、form、filing date、report date、accession / document id 和内容 digest，避免上游新 filing 导致预期值静默漂移。

真实最新财报场景可以使用动态数据，但只断言不随最新 filing 变化的不变量，并在 evidence bundle 中保存本次实际使用的文档身份和 digest。不得把模型既有知识、搜索摘要、assistant 历史回答或测试编写者的印象当作财报事实真源。

被测 Agent / SUT 的所有财报文档读取仍必须通过 `dayu.fins.storage` 仓储边界及其 read tools 完成。Oracle producer 不属于 SUT：它必须从 digest-locked 原始 filing/XBRL/table artifact、SEC/CNInfo/HKEX source locator 或已人工审定基准独立构造预期事实，不能调用正在被评分的 Fins read tool 生成自己的答案。Oracle producer 可以读取 evidence bundle 中显式登记的原始 artifact，但不得依赖 Fins 私有文件布局或把绕过生产路径的读取结果冒充 Agent 执行证据。

`financial-oracle.json` 必须记录 oracle producer/version、原始 source locator、artifact digest、独立提取方式、review/adjudication 状态，以及与被测 production tool path 不同源的说明。无法证明独立性时，该 financial oracle 只能标记为 `needs-more-evidence`。

### 10.2 分层验证

每个财报分析场景至少区分以下层次：

1. Document availability：目标真实财报是否被正确下载、上传、预处理并能由 ticker、form、period 和 document id 定位。
2. Tool correctness：`list_documents`、section、table、page、financial statement 和 XBRL tools 是否返回正确文档、数值、单位、期间和来源信息。
3. Retrieval quality：Agent 是否找到回答问题所需的正文、表格、脚注、管理层讨论或分部信息，而不是停在弱相关片段。
4. Calculation correctness：同比、环比、利润率、现金转化、增长贡献、分部占比等派生值是否使用正确口径、单位、符号和期间。
5. Analytical reasoning：结论是否由已接受证据支持，是否区分事实、计算、管理层表述、假设和分析判断。
6. Answer quality：最终回答是否直接回应用户问题，披露关键限制，并提供足够的证据与出处。

工具层返回错误不能由模型“猜对答案”掩盖；模型选错工具、漏取关键证据或错误解释正确工具结果，也不能归因成单纯工具故障。Verdict 必须明确失败属于数据、工具、检索、推理、memory、prompt 还是展示层。

### 10.3 核心场景矩阵

第一版至少覆盖：

- Prompt 最小真实财报成功链：通过生产 `dayu-cli download` 至少下载一份真实财报，记录实际 source identity、
  文件/生成物、Fins 状态、日志和相关 SQLite before/after；完成使该财报可被生产 read tools 查询所需的真实后续
  CLI 步骤；再由 `dayu-cli prompt` 对同一 ticker/period 发起真实问题，至少观察一次成功的 document discovery 和
  一次成功的财报内容/结构化事实读取。这里的 download/process 结果只证明 prompt 场景的真实 corpus 前置条件，
  不在 prompt campaign 中裁决这些命令自身的 UI、参数、状态或生成物语义；它们必须在各自 command campaign 中
  单独覆盖和裁决。prompt verdict 只评价 prompt 是否真实调用 read tools、最终回答是否确实来自同次财报 response，
  以及回答与 source、Tool Trace、EventLog、memory 和 SQLite 是否一致。下载命令自报成功、仅有文件存在、
  `list_documents=not_found`、模型凭记忆回答或搜索网页都不能满足该 obligation。
- 文档发现：列出指定公司的可用 10-K / 10-Q / 20-F / 6-K / 年报 / 中报，并正确识别期间和修订版本。
- 单点事实：从财务报表、XBRL 或正文提取收入、利润、现金流、债务、股本等明确指标。
- 单位与口径：区分元/千/百万、币种、季度/累计、GAAP/non-GAAP、reported/constant currency。
- 派生计算：根据原始数值计算同比、利润率、自由现金流、分部占比等，并校验公式和舍入。
- 跨期分析：比较同一公司多个季度或年度，识别趋势、拐点和口径变化。
- 多公司比较：在相同指标、期间、币种和会计口径下比较公司；不可比时必须说明原因。
- 业务与竞争优势：从业务描述、客户、产品、研发、装机基础、市场结构等证据形成分析，不把公司宣传直接写成已证实结论。
- 风险与弱信号：从风险因素、脚注、MD&A、分部披露、应收、库存、现金流和资本开支发现异常或待验证问题。
- 管理层指引：区分历史结果、当前指引和分析师推断，并识别后续修正。
- 冲突证据：正文、表格、XBRL、不同 filing 或不同口径不一致时，不静默择一。
- 无证据问题：文档中没有充分依据时明确拒答、要求补充或标注不确定性。
- 长文档与截断：需要多次检索或 `fetch_more` 时仍能覆盖关键证据，不能把截断 preview 当成完整材料。
- 中美港来源：在实际支持范围内分别验证 SEC、CNInfo 和 HKEX 文档的定位、转换、读取和分析。

### 10.4 多轮财报分析

财报分析场景必须与 Conversation Memory 场景组合，验证真实业务连续性。例如：

1. 第一轮查询某季度收入和利润率，第二轮追问“为什么下降”。
2. 第三轮要求与上一年度同期比较，第四轮追问“刚才第二个风险点”。
3. 用户随后修正指标口径或更换公司，Agent 必须更新当前分析对象，不能继续引用旧 ticker 或旧期间。
4. 已经取得且仍然适用的证据应从 memory 复用；需要新期间、不同口径或更高精度时才重新调用工具。
5. compact 前后的财务事实、来源、answer anchor 和 open question 必须保持可解释，不得由 summary 把分析判断升级成 evidence-backed fact。

### 10.5 Oracle 与评分

固定真实财报基准应优先使用结构化 oracle，而不是要求模型输出固定文案。Oracle 至少可以包含：

- 目标文档身份和允许的来源集合。
- 必须检索到的 section / table / fact 概念。
- 事实值、单位、期间、容差和来源定位。
- 派生指标公式、输入值和允许的舍入范围。
- 必须出现或禁止出现的结论。
- 必须表达的不确定性、冲突或不可比原因。
- 允许或禁止的工具调用及最大无意义重复次数。
- oracle producer/version、原始 artifact digest、独立提取方式和 adjudication evidence。

建议指标包括：

- Document selection accuracy。
- Fact extraction accuracy。
- Numeric / unit / period accuracy。
- Derived calculation accuracy。
- Evidence retrieval recall。
- Provenance coverage。
- Unsupported financial claim rate。
- Cross-period / cross-company comparability accuracy。
- Necessary refresh accuracy 与 unnecessary tool-call count。
- Abstention precision。
- Multi-turn financial fact retention。

LLM judge 可以作为补充，用于评价分析完整性、表述清晰度和买方视角，但不能成为数值正确性、来源正确性或证据充分性的唯一 oracle。核心事实和计算必须由基于真实财报真源的确定性断言校验。若使用 LLM judge，也必须调用真实 provider，并保存 judge 输入、输出、模型身份和裁决 rubric。

### 10.6 真实模型稳定性

真实模型输出具有非确定性。CI 不应断言完整回答字符串，而应断言事实、来源、工具行为和禁止事项。高风险分析场景应重复运行，并报告通过率和失败类型，避免一次偶然正确被判定为稳定能力。

真实外部数据或 provider 不可用时，场景只能标记为 `blocked` 或 `limited-signal`；不得退回 mock、缓存模型答案或伪造工具结果后仍声明真实财报分析通过。

## 11. Evidence Bundle

每个 run-level evidence root 必须且只能生成一份 `observed-behavior.md`。它是事实优先、逐场景汇总的唯一人类可读
observation report；不得拆成多个 per-leaf Markdown。`oracle-adjudication.md` 继续承载 report freeze 后的两路正式
suggestions、总控 synthesis 和 user adjudication，不与事实报告混写。

每个场景输出独立 raw evidence 目录，run-level artifacts 引用这些目录。evidence bundle 至少包含：

- `run-manifest.json`：run id、target commit、profile、registry digests、authorization、resource budget 和 artifact roots。
- `ci-owned-marker.json`：canonical run-root identity、manifest digest 和可清理资源边界。
- `observed-behavior.md`：单一 frozen observation report，schema 见第 11.1 节。
- `scenario.json`：场景 id/version、stable coverage claims、前置状态、命令/参数/交互输入、cross-command
  assertions、required evidence、oracle refs、环境和超时。
- `runtime-identity.json`：真实 CLI、Host、provider、model、tool bundle 和财报 corpus / live source 身份。
- `command.json`：实际 invocation、exit/signal/timeout/cancel 原始状态和输入时间线。
- `stdout.txt` / `stderr.txt`：分离保存的原始进程输出；不支持分离时记录限制，不得伪造。
- `filesystem-before.json` / `filesystem-after.json` / `filesystem-diff.json`：CI-owned 范围内的 bounded
  before/after manifest、digest 和生成物差异。
- `debug.log`：CLI debug 日志，仅为 diagnostic。
- `terminal.cast`：需要 UI 验证时的 asciinema 记录。
- `screen/`：关键时刻和最终虚拟终端快照。
- `identities.json`：session/run/attempt/execution/tool-call 关联标识。
- `eventlog.jsonl`：与场景相关的 canonical facts。
- `host-public-reads.json`：Host public read contract 的 bounded 输出和查询 identity。
- `sqlite-query-manifest.json`：相关 stateful 场景的只读 before/after 边界、query identity、limits、digest、脱敏记录
  和 private-schema-dependent 声明；无相关 SQLite 时记录 `not-applicable` 理由。
- `tool-trace.jsonl`：业务工具追踪。
- `memory.json`：memory snapshot、source refs 和 diagnostics。
- `runner-input.json`：实际模型输入重建结果。
- `financial-oracle.json`：目标文档、事实、单位、期间、公式、容差和来源定位。
- `financial-evidence.json`：实际检索文档、section/table/fact、来源与 digest。
- `financial-score.json`：事实、计算、证据、可比性、拒答和多轮延续指标。
- `oracle-candidates.json`：本次发现的候选 oracle、状态、依据、允许变体和 evidence refs。
- `oracle-adjudication.md`：两路正式 suggestions、总控 synthesis、用户裁决状态和后续 WU 建议。
- `oracle-usage.json`：本次实际使用的 accepted oracle id/version 及适用场景。
- `assertions.json`：确定性断言及证据定位。
- `reviews/`：report freeze 后的两路 LLM-facing / memory 语义 review。
- `verdict.md`：总控裁决、残余风险和 owner。
- `cleanup.json`：保留/删除资源、归属证明、失败原因和剩余磁盘占用。

Evidence bundle 必须执行敏感信息检查。API key、credential、authorization header、cookie 和 provider secret 不得进入 cast、日志、EventLog 导出、Tool Trace、runner input artifact 或 review 文档。

若真实产品 durable state、原始日志或 trace 本身已经写入 secret，取证流程必须保留该事实但不得传播该值：
立即限制 CI-owned run root 和相关原始文件的访问权限，不修改或“清洗”产品原始状态来伪造无泄漏结果；面向用户和
可分发 evidence 只记录 secret 类型、owner、表/列或 JSON path、命中数量、脱敏 digest 和受限 raw evidence
identity，不记录 secret value。该场景记为 hard-contract finding 和 evidence-distribution gap，但在授权范围内
继续完成其它命令的安全观察，不得因此提前结束第一轮 oracle 建立。

Evidence bundle 必须能证明场景未使用 mock/fake 组件。若无法从 runtime identity、runner trace、tool schema/call trace 和 durable records 证明真实执行链，场景不得判定 pass。

### 11.1 Observed-behavior Markdown schema

`observed-behavior.md` 必须同时支持用户全局扫读和从摘要跳转到逐场景证据。它只做 bounded narrative 和 evidence
projection；raw artifacts、Host public contract、EventLog canonical facts、Tool Trace、memory、runner input 和
filesystem artifacts 仍各自由原 owner 承诺。但“projection”不等于只列 ref：支持用户下一步裁决的关键实际内容必须
脱敏后直接展示，raw artifacts 和 digest 只承担完整性证明与深入复核。

#### A. Run-level header

必须包含：

- report schema version、report identity、status、冻结时间、digest algorithm 和 run-level final report digest
  record ref；
- run id、target commit、branch/ref、dirty exclusion 和 profile；
- 起止时间、时区、OS、Python、Dayu CLI executable/version 和安装来源；
- workspace/run-root canonical path 的脱敏表示和 CI-owned marker evidence；
- provider/model/tool bundle/financial corpus identity，仅记录非秘密标识；
- terminal emulator、`TERM`、宽高、locale 和 shell；
- authorization/resource budget；
- scenario/oracle registry version、digest、readiness proof validation 和当前 mandatory gap counts；
- `calibration_stage_at_freeze=observed-report-frozen` 和 `observation_completeness`；
- 敏感信息扫描结果和已应用的脱敏规则；

动态 `calibration_stage`、primary validation verdict 和 goal-discovery status 只记录在各自 owner 的 run-level final
report 字段，不回写本 immutable report。

frozen report digest 固定为对 `observed-behavior.md` exact UTF-8 bytes 计算 SHA-256。计算值记录在既有 run-level
final report 的 report digest 字段，并由 `oracle-adjudication.md` 引用；`observed-behavior.md` 不内嵌自身计算值，
避免 self-referential hash。任何字节变化都必须产生新 digest；frozen report 不做原地格式修订。补充证据进入新 run /
新 report，新报告引用旧 report identity/digest，旧报告原样保留。

#### B. Executive summary、导航与 coverage 表

单份报告顶部必须按以下顺序提供：

1. bounded executive summary：run 身份、`observation_completeness`、最重要 actual behaviors、objective /
   hard-contract facts 和 gaps；只陈述事实。
2. TOC：链接到 coverage 表、cross-command summary 和每个 scenario 的稳定锚点。
3. 逐 mandatory scenario 一行 coverage 表：scenario/leaf、precondition state、option/interactive branch、input class、
   combination/cross-command claims、`execution_outcome`、`evidence_status`、`gap_kind`、actual behavior 一句话摘要、
   detail anchor 和 raw refs。
4. 分离的统计区：
   - parser/interactive inventory identity、leaf/branch/option 总数、in-scope / out-of-scope 数量和理由；
   - mandatory obligations 的 planned、attempted、executed、not-run、blocked，以及
     `success/error/timeout/cancel` 各 outcome 数；
   - 按 precondition、option/branch、input class、combination、cross-command 和 path kind 分离的 coverage 统计；
   - required evidence 完整率和各 `evidence_status` 数；
   - incomplete gaps 按 `gap_kind`、owner 和 next evidence action 汇总。

每个稳定锚点由 scenario id 派生；同一 scenario version 中不得因显示文案变化而改变。单场景细节必须 bounded；
stdout/stderr、cast、log 或 trace 超出摘要预算时，不内嵌整份材料，但必须内嵌足以解释实际行为和支持裁决的 literal
excerpt、关键 screen、关键生成物内容/diff、DB delta 和跨命令结果，并附 raw artifact ref。禁止只留一句总结、
digest 或 ref，也不得另建 per-scenario Markdown 逃避全局可读性。

#### C. Per-scenario observation record

每个 mandatory scenario 独立成节；相同 leaf 的场景可以相邻展示，但不得合并后丢失 precondition、option/input 或
cross-command identity。每个场景至少包含：

1. **Identity**
   - parser leaf id、完整 command path、scenario id/version 和 path kind；
   - stable coverage claims：precondition state、parameter/interactive option、input class、combination/high-risk 和
     cross-command assertion IDs；
   - public CLI contract/help/interactive inventory 选择依据、syntactic/semantic validity、required evidence 和应
     触达的 primary operation/read flow；
2. **Preconditions**
   - 初始 workspace/session/DB 状态摘要；
   - 所需 corpus、provider、model 和 credential ref availability；
   - authorization/resource budget 和 before snapshot evidence refs。
3. **Exact input**
   - cwd、argv 的 shell-safe 展示、非秘密环境变量名称和值；
   - config/profile 的脱敏快照和 digest；
   - stdin、按键、交互输入、等待动作及相对时间线；不得记录 secret value。
4. **Observed process result**
   - started/finished timestamps 和 duration；
   - 真实执行时只记录 `process_outcome.kind=exited/timed_out/harness_error`、exit code、signal 与 timeout 原始状态；
     `not-run/blocked` 在 dependency/evidence facts 中单独记录；
   - stdout/stderr 分离后的 raw artifact refs 和 bounded literal summary。

   本段只拥有 process-level raw facts，不解释“正确/错误”、不做跨层叙述、不产生 pass/fail。exit 0 或
   `kind=exited` 不能证明任何 accepted Run succeeded、observation completeness 或 correctness。
5. **Per-Run terminal 与 dependency evidence**
   - Host EventLog/shared lifecycle terminal contract 是每个 Run terminal type 的 owner；tracked helper 必须通过物理只读
     Host store，在 frozen `(start_event_sequence, end_event_sequence]` 中使用只含 `RUN_ACCEPTED` 与 shared Run
     terminal types 的 filtered keyset reader读尽窗口，page size不得成为 semantic cap；
   - `run-terminals.json` 必须逐 Run 保存 accepted ordinal、session/run/event identity、terminal event type、
     `succeeded/failed/cancelled/lost` class、显式 required/dependent/independent role及 canonical reason；`RUN_LOST`
     保持独立且标明非 public-outbox terminal；
   - terminal 的 `session_id` 必须与同一 Run 的 `RUN_ACCEPTED.session_id` exact 相等；terminal class 与 public-outbox
     eligibility 必须复用 shared lifecycle projector，不得在 harness 中另写四分支或用“不是 lost”反推；
   - reason 的唯一源是 terminal row 的 `reason_json.reason`，禁止 fallback 到 payload、Host status、diagnostic或日志。
     validator按现有 terminal-specific canonical shape严格校验：succeeded/failed只允许 reason；cancelled可另外携带已知且
     合法的 `mode`；lost可另外携带非空 `orphan_proof`；unknown extra、malformed/non-object、missing/blank/wrong type均
     `observation_invalid`；
   - 同一 Run 两条 shared Run terminal facts（无论同型或异型）是 duplicate；Attempt terminal、`RUN_CANCELLING`与其它
     lifecycle events不参与 duplicate判断。accepted缺 terminal、terminal无 window 内 accepted、cursor不前进或越过 frozen
     end均 fail closed；
   - success-required action必须显式声明直接 upstream accepted ordinal。只有 `RUN_SUCCEEDED`允许 dependent chain继续；
     failed/cancelled/lost停止该链并记录 upstream identity/type/reason，pending只允许在deadline前，deadline后为 invalid。
     stop/invalid 后，当前 process 的所有剩余 dependent actions必须逐项记录 `not_run`，只允许发送一次显式 cleanup/EOT，
     并使用短 cleanup deadline 尽快退出；不得继续等待原计划 terminal count，也不得把 cleanup 后 exit 0当作 Run success。
     independent mandatory observation、process artifact、terminal evidence、public evidence与secret scan继续执行；
   - fresh `execution-index-f15-f16.json` 分开汇总 `process_outcomes`、`run_terminal_summary/records`、
     `dependency_gates`、`evidence_status`、`context_compaction_observation`与public evidence；其中
     `evidence_status`只表示Run/context/tool collection完整性，不得复制或冒充publication scan verdict。逐 Run record
     必须携带 record path/digest；terminal summary至少区分 accepted/succeeded/failed/cancelled/lost/missing/invalid，
     valid observation必须把四类terminal summary与逐 Run `terminal_class`分布exact对账。canonical observation缺失、重复或
     破损时，无法由typed fact确认的计数写`null`，只确定`invalid=1`并保留diagnostics；不得从diagnostic message反推
     missing/duplicate伪精度。required Run 的合法 non-succeeded terminal只使 evidence 为 `insufficient`；
     dependency-stopped不得标为complete。final publication必须先落盘最终`run-completion.json`或
     `execution-index-f15-f16.json`，其中secret scan只能引用`secret-scan.json`的record path，不复制尚未形成的
     status/digest；随后由tracked final-tree helper扫描整个evidence tree并独占创建唯一`secret-scan.json`。
     final metadata与此前全部evidence都必须出现在report descriptors中；唯一允许自排除的是调用时尚不存在、即将生成的
     `secret-scan.json`本身。report target必须经lexical traversal拒绝与resolved root containment双重校验；report已存在、
     stale、为symlink、含symlink ancestor或在scan期间出现时一律fail closed，不允许pre-scan/post-scan双真源。scan report是
     secret与path-hygiene verdict的唯一持久化真源。exact probes只能来自实际secret环境值和有意义
     canary；普通repo/run/corpus路径不是credential。path hygiene必须拒绝raw `*.sqlite`/`*.sqlite3`/`*.db`主库、其
     `-wal/-shm` sidecar、文本中的同类raw database路径以及leaf/ancestor symlink候选，任一命中均fail closed；不得用
     硬编码布尔代替扫描事实。raw DB路径分类必须由tracked typed helper唯一拥有，filesystem snapshot producer与final
     scanner复用该真源；before/after snapshot在产生路径记录时排除raw main/WAL/SHM，diff与execution index只从已过滤
     snapshot派生，不得在下游字符串替换或删除。独立`sqlite-before/after.json`仍通过物理只读查询发布业务/audit投影，
     但不发布DB文件路径。public Tool Trace必须继续由production `dayu-cli tool_trace analyze`生成；distributable evidence以
     canonical cold JSONL作为输入，避免workspace hot-store projection发布`hot_db_path/source_path`，同时保留cold
     Run/tool-call/finding/audit facts；context compact accepted facts由独立只读EventLog projection提供。raw Host SQLite
     不得进入public evidence；不得包含
     `scenario_success`、综合 `success/passed`或由exit 0推导的scenario verdict，formal oracle继续为
     `unadjudicated`。
6. **Terminal evidence**
   - 按输入/选择顺序内嵌关键 screen 或等价 literal transcript，说明对应时间和按键；不得只列 screen 文件名；
   - 内嵌 final screen 的关键可见状态，并给出完整 cast/transcript ref，以及 ANSI 清除、prompt 恢复和增量区域的
     实际观察。
7. **Filesystem / generated artifacts**
   - before/after bounded manifest 和 created/modified/deleted artifact 列表；filesystem manifest不得发布raw SQLite
     main/WAL/SHM路径，created/modified/deleted必须从同一已过滤snapshot派生；
   - 每个用户相关关键生成文件的脱敏内容或 bounded literal excerpt、before/after diff、content/metadata digest、
     路径归属、CI-owned validation 和超预算内容的摘要方式；
   - secret 明文、secret ref、redacted 或未持久化的实际状态。
8. **Diagnostics**
   - debug log ref、关键事件时间线和 warning/error 原始事实摘要；
   - 明确标记 debug log 为 diagnostic、非 durable truth。
9. **Host DB / SQLite observation**
   - `queried` / `not-queried` 及第 11.2 节 checklist 理由；
   - public read contract evidence、resolved DB path 脱敏表示和 CI-owned validation；
   - 相关 stateful 场景内嵌 SQLite schema/关键 rows 或 bounded aggregation 的 before/after 和 delta；同时给出只读
     query manifest/id、row count/digest、private-schema-dependent 标记；
   - query/redaction/row/byte/time limits，以及该证据仅为 diagnostic 的声明。
10. **Cross-layer correlation**
   - session、run、attempt、execution、tool-call identities 和映射关系；
   - CLI/Service request、Host canonical EventLog、Tool Trace、memory snapshot/source refs/diagnostics、
     runner input 和 UI/final answer refs；
   - identity 缺失或关联歧义。
11. **Cross-command consumption**
    - 对生成配置、文件、Fins/Host/DB 状态，内嵌后续真实 CLI load/query/consume 的 invocation 和实际结果；
    - 明确哪些产物没有被后续命令消费，以及对应 coverage gap；创建命令的自报 summary 不能替代本节。
12. **Observed behavior only**
    - 引用第 4-10 项 evidence refs，按时间顺序做 bounded cross-layer narrative，只描述实际发生了什么；
    - 记录层间一致/不一致事实，不重复粘贴 raw process fields；
    - objective fact / hard-contract violation 可以标注精确 authority basis；
    - 禁止用 exit code、CLI 自报数量/summary、digest 或 raw ref 替代行为描述，禁止写期望、外部产品模仿建议、修复
      方案或未裁决产品结论。
13. **Evidence integrity and gaps**
    - required artifact presence、mock/fake absence proof 和 secret scan；
    - missing/corrupt/ambiguous evidence；
    - `evidence_status`，至少区分 `sufficient/missing/corrupt/ambiguous`；
    - `gap_kind`，至少区分 `none/not-run/blocked/evidence-missing/evidence-corrupt/evidence-ambiguous/
      public-observability-gap`，并记录 owner / next evidence action；
    - 引用第 4 项 `process_outcome` 与第 5 项 per-Run/dependency facts，但不得合并重写成 scenario verdict。

Scenario observation completeness 只由该 mandatory scenario 是否真实 attempted/executed 与 required evidence 是否
sufficient 决定，不由 success/error/timeout/cancel 决定。一个 help/positive/negative 或 workspace state 的成功不能
填补其它 scenario obligation gap。

#### D. Cross-command summary

报告末尾必须包含：

- 全命令实际行为索引；
- mandatory obligations 的逐维度 coverage summary、未覆盖项和新发现 interactive branches；
- 可复查的 cross-layer identity matrix；
- 观察到的共同行为和差异，只陈述事实；
- immediate objective / hard-contract failures 及精确 authority/evidence；
- incomplete / blocked / limited evidence；
- 未执行项及原因；
- 所有 cross-command load/query/consume assertions 的实际结果；
- report freeze statement、exact UTF-8 bytes SHA-256 的 run-level final report digest record ref，以及下一阶段只允许
  AgentMiMo / AgentDS independent review / formal suggestions。

#### E. Agent suggestions 与 user adjudication

suggestions 和 adjudication 不得写入 `observed-behavior.md` 事实主体。它们只能在 report frozen 后写入既有
`oracle-adjudication.md`；两路 formal review 不替代开发 WU 的任何 Gateflow review。每条 suggestion 必须包含：

- suggestion id、对应 observed report digest、scenario/correctness surface 和 evidence refs；
- authority basis；
- proposed predicate 的 precondition、trigger、expected observable、allowed variants、forbidden behavior 和
  measurement；
- suggested disposition：建议既有 validation contract 判为 pass/fail、建议第 4.3 节 candidate accept/reject，
  或 `needs-more-evidence`；该字段只是 review 输出，不持久化为平行 verdict；
- Agent authority：可直接建议或必须由用户决定；
- 反例、替代方案、trade-off 和 confidence；
- AgentMiMo / AgentDS 分歧与总控 synthesis；
- user decision、scope、effective version、reason 和 date；
- accepted 后才产生的 oracle id/version 或后续 WU identity。

任一路 reviewer、总控或用户发现证据不足时，对应 oracle candidate 必须为第 4.3 节既有
`needs-more-evidence`。后续只允许创建新 run 和新 immutable report；`oracle-adjudication.md` 保留旧 report digest，
并把新 report 作为新证据版本引用，不得回写 frozen facts。

用户拒绝 observed behavior 时，`oracle-adjudication.md` 必须记录用户给出的 replacement behavior，或把该 correctness
surface 保持为 unresolved gap；不能把 `rejected` 当作“无需 oracle”。用户指出新状态、选项或路径时，必须扩展
scenario obligations、真实补跑并生成新 report，直至 readiness proof 不再有 gap。

### 11.2 Host DB / SQLite observation safety boundary

SQLite 是 internal observation source，不是 Host/Fins/EventLog public contract 或业务真源。对 runtime manifest
证明会读取或写入 CI-owned SQLite 的 mandatory stateful scenario，bounded read-only schema/关键 rows before/after
是 required observation，即使 public evidence 已经完整也不能省略；其目的是让用户看到实际持久化结果和发现跨层
不一致，不是把 private schema 升级为 public contract。与 SQLite 无关或 runtime 没有 SQLite 的场景才可记录
`not-applicable`。

财报文档内容的存取边界不因 CI observation 改变：禁止从 SQLite 直接读取、重建或展示 Fins document body、
section、table、fact、转换 payload 或 provider payload，也禁止依赖 Fins private file/schema layout 形成业务结论。
Fins 相关 SQLite observation 只能包含必要的 schema metadata、document opaque identity、status、count、digest 和
其它 bounded diagnostic；财报内容与业务可读状态必须通过 `dayu.fins.storage` 仓储协议及其 public read tools 取证。

只允许观察本 run manifest 和 CI-owned marker 明确归属的 workspace/run root。数据库目标必须经过 canonical path
解析与边界校验；路径越出 CI-owned root、ownership 不清或 marker 不匹配时 fail closed。查询必须绑定当前 scenario
identities/time window，并限制 query 数、行数、字段、字节和时间范围。

每个 mandatory scenario 必须执行并记录以下 checklist：

1. 从 runtime identity、workspace manifest 和 command call path 判断场景是否可能触达 CI-owned SQLite，并记录
   database owner/path identity；不得凭文件名猜测。
2. 若无相关 SQLite，记录 `not-applicable` 及直接证据。若有关联，执行 bounded schema metadata 与场景相关关键
   rows/aggregation 的 before query，场景结束后用同一 query identity 执行 after query 并生成 delta。
3. 同时检查 Host public reads、EventLog export 和既有 trace reconstruction 是否覆盖 required public facts。若存在
   public observability gap，记录 `gap_kind=public-observability-gap` 及缺失 owner；SQLite 不能把
   contract gap 补写成 public fact。
4. 查询前写明 observation 目的、目标 DB ownership、query/row/byte/time bounds 和脱敏方案。相关 SQLite 存在但
   ownership/safety/redaction 任一项不满足时，记录 `blocked` / evidence gap 并阻止该 scenario readiness；不得用
   `not-queried` 静默跳过。
5. 报告内嵌脱敏的 schema/关键 rows 或 aggregation before/after/delta 和限制，并附 query manifest/raw ref；
   不得只写“数据库已更新”、row count、digest 或 CLI 自报数量。
6. 查询后仍分别报告 public facts、internal diagnostic observation、cross-layer contradiction 和 public gap 是否
   存在；不得用 private row 消除、覆盖或隐藏 public observability gap。

SQLite 连接必须同时使用 read-only URI 和 connection-local query-only 防线。SQL 只允许 `SELECT` 和明确列举的只读
metadata inspection；禁止 DDL、DML、transactional mutation、`VACUUM`、`REINDEX`、`ATTACH`、extension loading、
user-defined function、整库 dump、创建索引/临时业务表或修改持久 pragma。运行中 WAL 无法安全一致读取时记录
evidence limitation；不得复制猜测、暂停或修改 Host 来迎合查询。

query manifest 必须记录 query id、目的、参数范围、行/字节/时间上限和结果 digest。只导出与当前 scenario identities /
time window 相关的 bounded rows 或聚合；secret、credential、authorization header、cookie、provider payload 和未授权
用户内容必须遮蔽或只保留 digest。数据库路径使用可复核但不暴露无关用户目录的表示。before/after delta 必须区分：

- “没有变化”：所定义且完整覆盖的查询结果确认无 delta；
- “未观察到变化”：bounded observation 内未见 delta，但不能外推未覆盖范围；
- “查询无法覆盖变化”：query/evidence limitation 使变化不可判定。

Host public contract、EventLog canonical facts、accepted design 和 hard contract 决定业务/治理语义。SQLite 与 public
projection 冲突时，报告冲突、identity、limitations 和正确 owner；不得在 calibration harness 中重算、择一或用 private
row 伪装成真相。

## 12. Agent 路由

推荐执行分工：

- AgentCodex（Codex Agent）：在只读 assessment 中生成场景、执行命令、操作 PTY/tmux、收集 evidence bundle并实现确定性断言；候选 WU 完成正式 Phaseflow goal confirmation 后，再按正式 gates 承担 plan/implementation/fix。
- AgentMiMo（Claude Code Agent）：独立审查 CLI/UI 行为、LLM-facing 文本、Conversation Memory 语义和财报分析结论的证据充分性。
- AgentDS（Claude Code Agent）：独立审查 Host/EventLog/Tool Trace/RunInputBuilder 传播一致性、财务事实/计算 oracle 和最佳实践。
- 总控：维护行为 oracle、关联跨层证据、裁决 findings、更新覆盖矩阵和 residual risk owner。

执行 Agent 不得只根据最终回答给出 pass。Review Agent 必须引用 evidence bundle 中可复查的具体 material。

## 13. Pass / Fail 规则

Observation completeness、registry readiness 与产品行为正确性是三个正交维度：

- `observed-behavior.md` 缺失、未生成或未冻结时，禁止进入 Agent suggestions / user adjudication，更不能接受 oracle。
- 任一当前 run mandatory scenario 为 `not-run` / `blocked`，或 required evidence
  missing/corrupt/ambiguous 到无法复核实际行为时，`observation_completeness=incomplete`。
- mandatory scenario 的 `error` / `timeout` / `cancel` 是 actual `execution_outcome`，不自动导致 observation
  incomplete，也不自动代表 pass/fail；exit 0 / `success` 同样不自动证明 completeness 或 correctness。
- 单个 help/positive/negative、parser acceptance、CLI 自报 summary、mock/fake 或其它场景的成功不能掩盖任一
  precondition/option/interactive/input/combination/cross-command obligation 的 attempt/execution/evidence 缺口。
- objective / hard-contract failure 可以立即标注，但不得掩盖 completeness 缺口、跳过其余 observation 或在用户
  裁决前自动启动修复。
- incomplete run 中证据充分的局部 predicate 可以交用户裁决；这只减少未决集合，禁止据此声明第一轮 campaign 完成、
  registry ready 或 `full-real-pass`。
- 相关 stateful scenario 缺少安全、bounded 的 SQLite before/after 是 evidence gap；private SQLite
  schema/query result 仍不能单独支持产品 pass/fail，也不能覆盖 Host public read /
  `public-observability-gap` 或升级为跨版本 public contract。
- 通用 UI surface 缺少可执行 candidate predicate 或用户裁决时，Dayu observation 可以继续，但 correctness closure
  和 registry readiness 不成立；外部产品参考是否存在不影响该判断。
- 用户裁决前不得依据外部产品参考、best-practice proposal、current implementation 或 reviewer 共识形成 accepted
  oracle、修改 registry、生成实现计划或进入修复。
- 用户裁决后，只有第 4.6 节 readiness conditions 全部通过才可结束第一轮。新 accepted oracle 若从后续
  run/version 生效，则当前 calibration observation 只形成 implementation finding，不追溯改写当前 run verdict；
  只有 target 已被既有 hard/current-design contract 或 effective accepted oracle 覆盖时才可形成正式 `fail`。无论
  是否形成 fail，都不得把 implementation mismatch 改写成 coverage gap。

场景只有在以下条件全部成立时才可判定 pass：

- 命令和参数确实生效，而非仅解析成功。
- 场景使用真实 CLI、真实 Host、真实 provider、真实工具和真实财报来源；不存在影响 verdict 的 mock/fake 组件。
- 用户可见终端行为满足适用于本场景的 accepted oracle；没有 accepted oracle 时只能形成 calibration / `oracle-review-required` 结论。
- Host canonical facts 和状态迁移符合设计真源。
- Tool Trace、memory、audit 和 UI 都从同一业务真源正确派生。
- 实际 runner input 符合 LLM-facing 文本约束。
- 多轮场景满足对应的 #80 行为维度，或明确标记为受 #81 阻塞。
- 财报分析场景选择正确文档，事实、单位、期间、计算和来源满足 financial oracle。
- 分析结论不包含无证据财务断言，并正确处理冲突、不可比和证据不足场景。
- 没有敏感信息泄漏。
- evidence bundle 足以让另一 Agent 在不重新运行命令的情况下复核结论。
- 报告主体足以让用户看到关键 screen、生成物内容/diff、SQLite/durable delta 和跨命令消费结果；不能要求用户先
  重跑命令或只根据 raw ref/digest 猜测。

以下情况不得静默判定 pass：

- 外部服务未配置或网络不可用。
- 真实 provider、真实工具或真实财报来源被 mock/fake/cached answer 替代。
- 真实 provider 返回非预期但被脚本忽略。
- 只检查最终回答，没有检查 durable truth 或 runner input。
- cast 存在但未进行终端状态回放。
- memory snapshot 正确但没有检查实际 RunInputBuilder messages。
- 只因最终回答语言流畅就认定财报分析正确。
- 数值正确但单位、期间、口径或来源错误。
- 仅凭 Codex / Claude Code 行为、Agent 最佳实践建议、当前实现或未裁决设计争议直接创建 oracle。
- 使用 `unadjudicated` / `needs-more-evidence` oracle 对产品判定 pass/fail。
- 因 projection lag、日志缺失或 trace 缺字段而无法定位事实。
- 只因某一 positive 返回 exit 0 / `success` 或 CLI 自报数量正确，就宣称 obligation matrix complete 或行为正确。
- 只因某一场景返回 error/timeout/cancel，就自动宣称 observation incomplete 或行为错误。
- `observed-behavior.md` 未冻结即生成 formal suggestions，或把 suggestions/adjudication 回写进 frozen facts。
- 使用 SQLite 私有表、列、row order 或 query result 作为唯一 oracle，或用它填平 public observability gap。
- 只把 `registry_status` 手工改为 `ready`，没有校验 inventory digest、coverage claims、correctness surfaces、
  accepted oracle refs、user adjudication 和 frozen evidence。
- 用户 rejected 当前行为后没有 accepted replacement predicate 或明确 out-of-scope 裁决，却把 correctness gap 当作
  已关闭。

这类情况必须按其真实 owner 标记为 coverage/evidence gap、`blocked`、`limited-signal`、`oracle-review-required` 或
product failure，并给出原因和后续 owner；不得统一降级或静默 pass。

## 14. 与人工验证的边界

该体系的目标是把重复执行、录屏、日志关联、EventLog / Tool Trace / memory 查询和报告生成交给 Agents，从而减少人工遗漏与时间成本。

人工裁决主要保留在以下场景：

- 第一轮完整 observed-behavior campaign 中逐项确认正确行为、允许变体和禁止事项；
- 自动终端模拟无法可靠判断的视觉体验争议。
- 真实外部账户、凭据、成本或副作用需要用户授权。
- 设计真源没有给出唯一答案的产品语义。

人工发现的新问题必须转化为基于真实执行链的可重复场景和断言。相同问题修复后，不应继续依赖用户重复手工验证作为唯一回归机制。

## 15. 实施原则

- 验证 harness 可以分步实现，但第一轮 calibration completion / registry ready 必须等到 parser + interactive
  inventories、完整 mandatory matrix、evidence 和用户裁决全部闭环；局部 smoke 不得冒充第一轮完成。
- 先支持 real-contract 和固定真实财报 corpus，再增加 live-provider / live-external lanes；所有产生 Agent verdict 的场景始终使用真实 provider。
- 先建立固定真实 filing / XBRL / table 财报基准，再增加动态最新财报场景和主观分析评分。
- 不将普通 mock-based unit test 的结果汇总为本文 CI 的通过率；两类验证分别报告。
- 复用 Host public read contracts 和已有 trace reconstruction，不从 SQLite 私有表结构拼接新的事实语义。
- 若现有 observability 无法回答场景问题，应在语义 owner 或其公共 projection contract 补足，而不是在 CI 脚本中猜测。
- 验证工具只读取和分析事实，不成为 Host 状态迁移、memory 或 trace 的新真源。
- 所有自动修复仍需遵循正常的 plan、implementation、双路 review、re-review 和 closeout gate。
