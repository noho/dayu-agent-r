# Dayu CLI 真实环境行为 CI

## 1. 定位

本文定义 Dayu CLI 的真实环境行为验证方案。目标不是增加一组只验证参数解析的单元测试，而是把目前依赖人工运行、录屏、查日志和查数据库的验收过程，收敛为可重复执行、可关联证据、可自动发现覆盖遗漏的 CI 体系。

该体系需要同时回答三个问题：

1. CLI 的用户可见行为是否符合 Dayu 设计，并在通用 Agent 交互层面与 Codex / Claude Code 的成熟行为保持一致。
2. Host 的 canonical truth、状态迁移、Tool Trace、Conversation Memory 和实际模型输入是否符合设计真源与最佳实践。
3. 实际进入 LLM 上下文的 prompt、tool schema、memory 和 evidence material 是否符合 `AGENTS.md` 的“LLM-facing 文本约束”。

本文是验证体系设计，不表示当前仓库已经实现完整覆盖。现有 CLI smoke、PTY 测试和真实环境验证可以作为后续实现的输入，但不能替代本文定义的完整场景矩阵。

本文定义的 CI 是真实环境验收 CI。任何 mock runner、fake provider、fake tool、内存替身 Host、伪造 EventLog 或手工拼接 memory snapshot 都不能作为场景通过证据。普通单元测试仍可按其测试边界使用 test double，但它们属于开发回归，不计入本文 CI 的 pass verdict。

## 2. 新会话执行契约

本文必须能够作为新总控会话的自包含执行入口。用户给出“按 `docs/cli_ci.md` 执行 CLI CI”、准备好 `ai` tmux session 中的四个 Agent（总控、AgentCodex、AgentMiMo、AgentDS），并提供第 2.2 节规定的机器环境与授权配置。CLI 被测环境由总控自动创建、运行、取证和清理。

### 2.1 默认输入

新会话未提供额外参数时，默认规则如下：

- repository：包含本文档的当前仓库。
- target ref：当前 `HEAD` 对应的 commit SHA。
- profile：场景与 oracle registries 都为 `ready` 时使用 `full-real`；否则自动使用 `calibration-real`，不得伪装成 full pass。
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
- 可选成本/时间/磁盘上限通过 invocation 或 `DAYU_CLI_CI_AUTH_PROFILE` 指向的 operator 配置提供。配置至少可表达 `max_wall_time_seconds`、`max_model_calls`、`max_disk_bytes`、`allow_public_financial_download`、`allow_ci_owned_upload` 和 `allow_external_write`。未提供时，每个 accepted 或 calibration provisional scenario 只执行一次主路径，不做自动模型重试或额外高成本采样，并在 run manifest 中记录预计和实际消耗。

用户不需要提前创建 validation worktree、venv、CLI tmux session、workspace、日志、cast 或 evidence 目录。总控不得要求用户手工执行本可自动完成的命令。

### 2.3 总控自动创建的环境

总控必须按以下顺序完成 bootstrap：

1. 阅读仓库 `AGENTS.md` 和本文档，在任何文件写入、Agent dispatch 或运行资源创建前执行 `git branch --show-current` 与 `git status --short`，记录只读 assessment preflight。
2. 阅读 `docs/host/design.md`、`docs/engine/design.md` 和当前项目总控文档；涉及 #80 时读取其当前 issue 内容。
3. 使用 `$init-agents` 约定发现并确认 `ai` session 中的 Agent 类型、pane 和空闲状态。
4. 解析 target ref 为不可变 commit SHA，记录 branch/ref、commit、dirty state、被排除的未提交改动和仓库 remote identity。
5. 读取稳定 scenario/oracle registries，按其 readiness 决定 `full-real` 或 `calibration-real`。
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
- parser inventory 能生成，且每个命令/参数都有场景 owner 或明确缺失报告。

任何真实依赖缺失都必须产生 `blocked` preflight 结论。不得自动切换到 mock/fake、缓存模型答案或更低语义的替代路径。

### 2.5 Phaseflow-aligned Goal Discovery 与 Agent 路由

总控保持唯一裁决权，具体工作按以下角色路由：

- AgentCodex：Codex Agent，承担 goal-discovery evidence acquisition，生成 inventory/场景、操作 CLI tmux panes、收集 evidence、分析直接证据；候选 WU 完成正式 Phaseflow goal confirmation 后，再承担对应 `plan` / `implementation` / `fix` gate。
- AgentMiMo：Claude Code Agent，在 assessment 内独立审查 UI/Codex 行为对齐、LLM-facing 文本、Conversation Memory 和财报分析证据充分性。
- AgentDS：Claude Code Agent，在 assessment 内独立审查 Host/EventLog/Tool Trace/RunInputBuilder 传播、财务 oracle 和架构/最佳实践。
- 总控：维护 oracle、监督 Agent、不轻易中断长任务、关联证据、裁决 findings、决定 rerun 范围并输出最终 verdict。

AgentMiMo / AgentDS 的独立审查是候选 WU goal confirmation 的输入证据，不是 Gateflow 的 `plan review`、`code review`、`aggregate deepreview` 或 `PR review` gate，不得因此跳过后续开发 WU 中的任何正式 review gate。

一次 CLI CI 是只读 assessment，不是 Phaseflow work unit。它复用 Phaseflow 的 preflight、Agent liveness、finding taxonomy 和 goal confirmation 输出要求，但不进入 Gate Order：

```text
ASSESSMENT PREFLIGHT
  -> GOAL-DISCOVERY EVIDENCE ACQUISITION
       -> INVENTORY
       -> EXECUTE
       -> CORRELATE
       -> DETERMINISTIC ASSERTIONS
       -> MIMO INDEPENDENT REVIEW + DS INDEPENDENT REVIEW
       -> ORACLE CLASSIFICATION / CALIBRATION
       -> CONTROLLER ADJUDICATION
  -> ONE GOAL-CONFIRMATION-READY ARTIFACT PER CANDIDATE WU
  -> AWAITING USER CANDIDATE SELECTION / GOAL CONFIRMATION
```

每个 goal-confirmation-ready artifact 只描述一个稳定候选 WU identity，并包含动机、直接证据、语义 owner、传播路径、严重性、成功信号、非目标、scope boundary、blocking questions 和建议优先级。`unadjudicated` oracle difference 只进入 oracle candidate 清单，用户裁决前不得伪装成实现 finding。若多个 findings 不属于同一语义闭环，必须生成多个独立 artifacts，不能为了减少 gate 数量硬塞进一个实现范围。

Agent 执行期间，总控应耐心等待其完成；只有确认任务失去进展、进入错误目标或可能造成未授权副作用时才可中断。长事务不得仅因短时间无终端输出而被判定卡死，应同时观察 debug log、EventLog、Tool Trace 和外部 operation 状态。

### 2.6 CI 与修复边界

CI runner 是只读验证者，不修改被冻结测 worktree。发现 failure 后：

1. 总控先用直接证据定位语义 owner 和传播路径。
2. 两路独立审查对 finding、严重性和修复边界提供 goal confirmation evidence。
3. 总控裁决 findings，为每个语义闭环生成独立候选 WU artifact，并停在 `awaiting-user-candidate-selection`；用户完成正式 Phaseflow goal confirmation 前禁止进入 `plan`、修改产品代码、创建修复 commit 或开启 PR。
4. 用户选择某个候选 WU 后，总控以正确 design_doc 和既有项目 control_doc 启动新的 Phaseflow，重新执行 branch/status preflight；若已有未完成 active WU，先等待或请用户裁决，不能覆盖。Preflight 通过后，由 Phaseflow 把该稳定 WU identity 写入项目 control_doc，current gate / next entry point 均指向 `goal confirmation`。Phaseflow 直接引用 assessment evidence并向用户复述目标；用户确认后才进入 `plan`。此后必须完整遵循既有 Gate Order，一直推进到 `final closeout pass`，不得因为 CI 已经做过双路审查而省略 plan review、code review、aggregate deepreview 或 PR review。
5. 开发 Git 流程完全复用 Phaseflow：branch/status preflight、accepted local commits、push、draft PR、PR review 和 final closeout。CLI CI 不定义第二套 branch、commit 或 PR 规则。
6. 修复不得直接修改 validation worktree。修复提交后，为新 commit 创建新的 CI run id 和 validation worktree。
7. 先执行 focused-real regression，再执行受影响矩阵；需要形成 full pass 时必须重新完成 `full-real`。

若 CI 未发现成立的问题且不存在待裁决 oracle，总控输出 `no-implementation-goal`，不创建开发 branch、commit 或 PR。若存在 `unadjudicated` oracle candidate，则停在 `awaiting-user-candidate-selection` / `oracle-review-required`，不能用 `no-implementation-goal` 跳过用户裁决。若用户不选择候选 WU 或不裁决 oracle，本次 assessment 保留 evidence 后结束，不启动任何 Phaseflow WU。

旧 run 的 evidence 不得被新 commit 覆盖。跨 run 复用结论时，必须证明 target commit、场景定义、真实财报 corpus digest、provider/model policy 和 oracle 均未变化。

### 2.7 重复执行、收尾与最终输出

每次执行必须生成唯一 run manifest 和最终报告。报告至少包含：

- target commit、profile、run id、起止时间和 runtime identity。
- command/parameter inventory 覆盖率及缺失项。
- CLI/UI、Host、LLM-facing、Conversation Memory、财报分析五类 verdict。
- 每个失败或 limited-signal 场景的直接证据、语义 owner、严重性和建议 owner。
- 本次使用的 accepted oracle id/version，以及新增 `unadjudicated` / `needs-more-evidence` candidates。
- mock/fake absence proof 与敏感信息扫描结果。
- 两路 review 结论和总控裁决。
- evidence bundle 根目录及可复现命令。
- 是否满足 `full-real-pass`，以及哪些场景 blocked/not-run。
- 候选 WU 列表，或没有成立 implementation goal 的直接理由。
- assessment 状态；若用户已选择候选 WU，则记录对应项目 control_doc、WU id 和 Phaseflow next entry point。

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

- 永久保留 bounded run manifest、verdict、oracle/scenario candidates、review/adjudication，以及必要 EventLog/Tool Trace/memory/runner-input 的 bounded 摘要与 digest。完整 logs、casts、screen snapshots 和受控 evidence artifacts 只在它们被未关闭 finding 引用，或该 run 是同一 target/profile 的最新基线时保留。
- 所有 Agent 完成且 evidence integrity 校验通过后，停止并删除本 run 的 detached tmux session，移除 detached validation worktree 和 run-local venv；重现必须创建新 run，不依赖旧可执行环境。
- `full-real-pass` / `focused-real-pass` 场景的 CI workspace、下载和处理中间产物在 evidence 固化后删除。
- `fail` / `oracle-review-required` / `limited-signal` 场景只保留最新一份尚未裁决的 CI workspace。用户完成裁决、候选 WU 进入 Phaseflow、明确拒绝候选，或更新 run 已提供同等/更强证据后，删除旧大型 workspace。
- 新基线取代旧 run，或相关 finding/WU 关闭后，旧 run 只保留上述 bounded summary/digest；删除不再被 active finding 引用的完整 logs/casts/screens 和大 evidence payload。
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

“对齐 Codex / Claude Code”“对齐最佳实践”“对齐设计真源”都不能直接作为可执行 oracle：

- Codex / Claude Code 只提供参考行为；其产品版本、终端状态和任务上下文可能不同，不天然适合 Dayu。
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
| reference behavior | Codex / Claude Code 的终端或交互行为 | 带版本/环境的观察证据 | 用户决定是否采纳为 Dayu oracle |
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

### 4.4 Oracle Record

每条候选或已接受 oracle 至少记录：

- `oracle_id` 与 `version`。
- category、适用 command/scene/surface 和前置状态。
- 可判定的 expected behavior / predicate，以及允许的有效变体。
- 明确禁止的行为。
- authority basis：objective source、hard contract、current design、reference observation、best-practice proposal 或 user decision。
- Dayu 实际行为和对应 evidence refs。
- Codex / Claude Code 参考行为时的产品、版本、日期、环境和 evidence refs。
- 设计依据及精确章节；若质疑设计，记录 design conflict。
- AgentMiMo / AgentDS 的独立意见、替代方案和 trade-off。
- 当前状态、用户裁决、裁决日期、适用起始版本和 `supersedes` / `superseded_by`。

Oracle predicate 应验证语义不变量，避免锁定真实模型的完整回答、固定措辞或唯一工具调用顺序。真实模型存在多个合理路径时，只约束必须满足的事实、证据、禁止事项和用户可见结果。

### 4.5 校准与用户裁决

第一次或前几次 CI 允许处于 oracle calibration：

1. AgentCodex 执行真实场景并记录 Dayu 实际行为。
2. 需要参考对齐时，收集可复核的 Codex / Claude Code 行为证据。
3. AgentMiMo / AgentDS 分别提出候选 oracle、反例、替代方案和风险。
4. 总控合并同义候选、保留分歧，不自行把建议升级为 oracle。
5. 用户可以在一次或多次运行后批量裁决。
6. Accepted oracle 冻结版本，从后续指定 run 开始参与正式 pass/fail。

校准运行仍必须完整保存 evidence。不得因为用户尚未裁决，就只给结论而丢弃后续建立 oracle 所需的 runner input、terminal、EventLog、Tool Trace、memory 或财报证据。

### 4.6 Oracle Registry 与 Phaseflow 衔接

稳定 scenario registry 为 `docs/cli_ci_scenarios.json`，稳定 accepted oracle registry 为 `docs/cli_ci_oracles.json`。两个 registry 都包含 `schema_version`、`registry_status` 和记录列表；`registry_status` 只允许 `calibration` 或 `ready`。新总控必须先读取并校验两个 registry，再决定执行 profile。

每次 run 在 evidence bundle 中生成 `oracle-candidates.json` 和 `oracle-adjudication.md`。不存在 accepted oracle 的场景默认进入 calibration，不得根据当前实现猜测期望值。

用户确认候选 oracle 后：

- 纯 CI 行为标准通过正式 WU 写入版本化 oracle registry。
- 若裁决改变架构、Host/Engine/Memory 契约或产品设计，必须先在对应候选 WU 中更新设计真源，再修改实现和 registry。
- 若 accepted oracle 暴露实现 failure，则同一候选 WU 的 goal confirmation 已具备直接证据，用户确认后顺畅进入 Phaseflow `plan`。
- Oracle registry、设计更新和实现修复都复用现有 Phaseflow Git/gate 流程，不建立独立的 oracle commit/PR 流程。

`docs/cli_ci_oracles.json` 中每条 oracle 至少包含第 4.4 节要求的 identity、scope、predicate、authority、状态和版本字段；只有 `accepted` 记录参与正式 verdict。`rejected` / `superseded` 可以保留在 registry 用于历史解释，但不得参与当前判定。per-run candidate/adjudication artifact 不能伪装成跨 run 已冻结 registry。

### 4.7 总控 Oracle 裁决算法

总控对每个 observed difference 固定按以下顺序处理：

1. 固定实际观察：引用 terminal、runner input、EventLog、Tool Trace、memory 或财报原文，不先写期望结论。
2. 判断是否违反 objective fact 或既有 hard contract。若是，形成 failure；若 hard contract 本身受到有材料的质疑，另建 design-review candidate，但不能让当前实现静默改写硬约束。
3. 查找 scope 和 version 均适用的 accepted oracle。存在时按其 predicate 判定 pass/fail，并记录 oracle usage。
4. 没有 accepted oracle 时，检查当前有效设计真源。实现与设计不一致时记录 conformance failure；若 reviewer 认为设计本身不合理，同时生成独立 design-review candidate，并在用户裁决前禁止直接修实现。
5. 收集 Codex / Claude Code 参考行为和最佳实践建议，但只作为 candidate evidence，不升级为 oracle。
6. AgentMiMo / AgentDS 独立给出 accept/reject/needs-more-evidence 建议、反例和 trade-off。
7. 总控合并材料，状态保持 `unadjudicated` 或 `needs-more-evidence`，并提交用户裁决。
8. 用户裁决 `accepted` 后冻结 oracle version；随后重新解释本次 observation 是否构成候选 implementation WU。用户裁决 `rejected` 后保留理由，防止下次运行重复提出同一无效候选。

总控不得因为两路 reviewer 意见一致而代替用户完成产品 oracle 裁决；两路一致只表示候选证据更充分。

## 5. 覆盖模型

### 5.1 命令与参数清单

命令和参数 inventory 必须从 `dayu.cli.arg_parsing.build_parser()` 派生，不能手工维护另一份可能漂移的完整清单。

场景 registry 必须和 parser inventory 做覆盖比对。registry 为 `ready` 时，新增命令、参数、正反开关或子命令后没有对应验证场景，CI 必须判定 registry drift failure。registry 为 `calibration` 时，缺失项进入 scenario candidates，当前 run 不得形成 `full-real-pass`。

`docs/cli_ci_scenarios.json` 中每条 scenario 至少包含 scenario id/version/status、覆盖的 command/parameter ids、profile、真实 invocation 与交互步骤、前置财报 corpus/live source、accepted oracle refs、authorization requirements、timeout/resource budget、expected evidence 和 supersession identity。只有用户已裁决并标记为 `accepted` 的 scenario 参与正式覆盖率；calibration run 生成的新场景写入 per-run candidates，不能直接修改 registry。

registry 为 `calibration` 时，AgentCodex 必须从 parser inventory 生成本次 run-local provisional scenario plan，覆盖每个 command 的 help/minimal path并优先选择高风险参数、真实 provider、多轮 memory 和财报分析代表场景。总控在执行前检查授权、预计资源和 scope；provisional scenarios 可以真实执行并用于收集 oracle/场景证据，但其覆盖率只能报告为 calibration coverage，不能计入 `full-real-pass`。

“覆盖所有命令及参数”定义为：

- 每个命令至少具有 help、最小合法调用和典型失败场景。
- 每个参数至少在一个场景中证明已被解析且真正影响其语义 owner，而不只是 parser 接受了该参数。
- 每个布尔参数验证默认值、正向开关和反向开关。
- 必填、互斥、依赖、重复、空值、非法值和边界值分别验证。
- 参数组合使用 pairwise 覆盖，并额外维护人工裁决的高风险组合。
- 不执行所有参数组合的笛卡尔积；该做法成本指数增长，且不能提供相称的行为保证。

### 5.2 验证层级

场景按执行成本分为：

1. Real contract：启动真实 CLI 进程，验证 help、参数错误、互斥关系和无需模型执行的命令契约。
2. Fixed real corpus：使用来源真实且身份/digest 固定的财报、真实 Fins storage/read tools、真实 Host/SQLite 和真实模型 provider，完成可重复的业务场景。
3. Live provider：使用真实模型 provider 和当前运行配置，验证 prompt assembly、tool selection、模型交互及多轮行为。
4. Live external tool：使用真实网络、Fins 下载、预处理、上传或其它外部服务，验证最新数据、长事务、取消和恢复。

固定真实财报 corpus 用于提供稳定 oracle，但不能被改写为伪造工具结果或伪造模型调用。低成本场景负责完整命令/参数覆盖，高成本场景负责代表性端到端和真实财报业务验证。真实 provider 的非确定性通过结构化 oracle、重复运行和通过率处理，不允许为了稳定结果切换到 mock runner。

只有 scenario registry 为 `ready`，且所有 mandatory oracle-governed scenarios 都有适用的 accepted oracle 时，profile 才能是 `full-real`。否则总控必须使用 `calibration-real`，输出缺失 scenario/oracle candidates，并停在用户裁决入口。

## 6. 执行与取证流程

每个场景在独立 workspace、独立 session label 和独立日志目录中运行，避免前序状态污染。

标准流程如下：

1. 生成场景 invocation，包括命令、参数、环境、真实财报 corpus / live source、预期不变量和超时策略。
2. 非交互命令直接执行；交互命令在 PTY 或 tmux pane 中执行。
3. 自动发送用户输入、Esc、Ctrl+C、Ctrl+D 和必要的等待动作。
4. 使用 `--log-level debug` 和独立 `--log-file` 保存诊断日志。
5. 需要验证动态终端行为时，以 asciinema 记录输出。
6. 记录并关联 `session_id`、`run_id`、`attempt_id`、`execution_id` 和 `tool_call_id`。
7. 查询 Host DB、EventLog、Tool Trace、memory snapshot 和 runner-call input reconstruction。
8. 执行确定性断言和双路语义 review。
9. 生成场景 verdict 和 evidence bundle。

tmux 主要用于需要多轮输入、异步观察和长事务控制的真实交互。无需人工观察的真实 CLI 场景优先使用可编程 PTY，以降低时间和环境不确定性。PTY 和终端模拟器只是输入与取证设施，不替换 Dayu 的任何生产组件。

## 7. CLI 与终端行为验证

### 7.1 Codex / Claude Code 对齐边界

Codex / Claude Code 是通用 Agent 终端体验的参考实现，不是 Dayu 的架构真源。对齐范围只包括通用交互行为，例如：

- idle 和 running 状态下 Ctrl+C / Esc 的取消与退出语义。
- 取消当前 Run 后 REPL 是否仍可继续使用。
- thinking 和 activity 的增量显示与清除。
- final answer 到达后的终端状态。
- 多轮会话、重试、EOF 和恢复的用户反馈。

Dayu 特有的 Host 治理、Fins 长事务、Conversation Memory 和证据语义以设计真源为准，不以 Codex / Claude Code 的实现替代。

参考实现行为必须先转写为可判定的行为 oracle。例如：“运行中第一次 Ctrl+C 取消当前 Run，不退出 interactive REPL”，而不是只写“行为与 Codex 一致”。参考实现升级导致行为变化时，应先重新裁决 oracle，再更新 CI。

### 7.2 终端状态检查

asciinema cast 的原始输出仍保留已被 ANSI 控制序列清除的文本，因此不能通过 grep cast 判断清屏是否成功。

CI 必须用 VT100/xterm 兼容终端模拟器回放 cast，并保存关键时刻及最终虚拟屏幕快照。至少断言：

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

每个场景输出独立目录，至少包含：

- `run-manifest.json`：run id、target commit、profile、registry digests、authorization、resource budget 和 artifact roots。
- `ci-owned-marker.json`：canonical run-root identity、manifest digest 和可清理资源边界。
- `scenario.json`：场景 id、命令、参数、环境、oracle 和超时。
- `runtime-identity.json`：真实 CLI、Host、provider、model、tool bundle 和财报 corpus / live source 身份。
- `command.json`：实际 invocation、退出码和时间线。
- `debug.log`：CLI debug 日志。
- `terminal.cast`：需要 UI 验证时的 asciinema 记录。
- `screen/`：关键时刻和最终虚拟终端快照。
- `identities.json`：session/run/attempt/execution/tool-call 关联标识。
- `eventlog.jsonl`：与场景相关的 canonical facts。
- `tool-trace.jsonl`：业务工具追踪。
- `memory.json`：memory snapshot、source refs 和 diagnostics。
- `runner-input.json`：实际模型输入重建结果。
- `financial-oracle.json`：目标文档、事实、单位、期间、公式、容差和来源定位。
- `financial-evidence.json`：实际检索文档、section/table/fact、来源与 digest。
- `financial-score.json`：事实、计算、证据、可比性、拒答和多轮延续指标。
- `oracle-candidates.json`：本次发现的候选 oracle、状态、依据、允许变体和 evidence refs。
- `oracle-adjudication.md`：两路意见、总控整理、用户裁决状态和后续 WU 建议。
- `oracle-usage.json`：本次实际使用的 accepted oracle id/version 及适用场景。
- `assertions.json`：确定性断言及证据定位。
- `reviews/`：两路 LLM-facing / memory 语义 review。
- `verdict.md`：总控裁决、残余风险和 owner。
- `cleanup.json`：保留/删除资源、归属证明、失败原因和剩余磁盘占用。

Evidence bundle 必须执行敏感信息检查。API key、credential、authorization header、cookie 和 provider secret 不得进入 cast、日志、EventLog 导出、Tool Trace、runner input artifact 或 review 文档。

Evidence bundle 必须能证明场景未使用 mock/fake 组件。若无法从 runtime identity、runner trace、tool schema/call trace 和 durable records 证明真实执行链，场景不得判定 pass。

## 12. Agent 路由

推荐执行分工：

- AgentCodex（Codex Agent）：在只读 assessment 中生成场景、执行命令、操作 PTY/tmux、收集 evidence bundle并实现确定性断言；候选 WU 完成正式 Phaseflow goal confirmation 后，再按正式 gates 承担 plan/implementation/fix。
- AgentMiMo（Claude Code Agent）：独立审查 CLI/UI 行为、LLM-facing 文本、Conversation Memory 语义和财报分析结论的证据充分性。
- AgentDS（Claude Code Agent）：独立审查 Host/EventLog/Tool Trace/RunInputBuilder 传播一致性、财务事实/计算 oracle 和最佳实践。
- 总控：维护行为 oracle、关联跨层证据、裁决 findings、更新覆盖矩阵和 residual risk owner。

执行 Agent 不得只根据最终回答给出 pass。Review Agent 必须引用 evidence bundle 中可复查的具体 material。

## 13. Pass / Fail 规则

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

这类场景应标记为 `blocked`、`limited-signal` 或 `not-run`，并给出原因和后续 owner。

## 14. 与人工验证的边界

该体系的目标是把重复执行、录屏、日志关联、EventLog / Tool Trace / memory 查询和报告生成交给 Agents，从而减少人工遗漏与时间成本。

人工验证主要保留在以下场景：

- 首次观察并裁决新的 Codex / Claude Code 行为 oracle。
- 自动终端模拟无法可靠判断的视觉体验争议。
- 真实外部账户、凭据、成本或副作用需要用户授权。
- 设计真源没有给出唯一答案的产品语义。

人工发现的新问题必须转化为基于真实执行链的可重复场景和断言。相同问题修复后，不应继续依赖用户重复手工验证作为唯一回归机制。

## 15. 实施原则

- 先建立 parser inventory 与场景覆盖检查，再逐步迁移现有 smoke。
- 先支持 real-contract 和固定真实财报 corpus，再增加 live-provider / live-external lanes；所有产生 Agent verdict 的场景始终使用真实 provider。
- 先建立固定真实 filing / XBRL / table 财报基准，再增加动态最新财报场景和主观分析评分。
- 不将普通 mock-based unit test 的结果汇总为本文 CI 的通过率；两类验证分别报告。
- 复用 Host public read contracts 和已有 trace reconstruction，不从 SQLite 私有表结构拼接新的事实语义。
- 若现有 observability 无法回答场景问题，应在语义 owner 或其公共 projection contract 补足，而不是在 CI 脚本中猜测。
- 验证工具只读取和分析事实，不成为 Host 状态迁移、memory 或 trace 的新真源。
- 所有自动修复仍需遵循正常的 plan、implementation、双路 review、re-review 和 closeout gate。
