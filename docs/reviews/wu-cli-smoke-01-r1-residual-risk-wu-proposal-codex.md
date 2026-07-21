# WU-CLI-SMOKE-01-R1 Residual Risk 代码证据核对与 WU 映射提案

## 1. Scope 与动机裁决原则

本文仅核对 `docs/reviews/wu-cli-smoke-01-r1-final-closeout.md` 的 Residual Risk Reconciliation 五项，并提出主总控表映射文本；不修改生产代码、测试、README、design、control document、Issue 或 PR metadata。

核对真源为：

- Engine 设计：`docs/engine/design.md`；
- Host 设计：`docs/host/design.md`；
- 主总控：`docs/host/issues-implementation-control.md`；
- 附加总控：`docs/phaseflow-umbrella-optimization-control.md`；
- R1 final closeout：`docs/reviews/wu-cli-smoke-01-r1-final-closeout.md`；
- 当前分支真实生产代码、owner-level tests，以及原始 `WU-CLI-SMOKE-01` 的人工验证证据。

判断原则：事实存在不等于仍有 implementation risk。只有同时具备未满足的产品/可靠性目标、清晰 semantic owner、可验证的失败条件，才应保留为 active residual。已被设计明确接受的边界若没有新产品需求，不应为了形式制造 implementation WU。对于“当前 WU 能否关闭”，本文不以本任务的 artifact-only 写权限作为理由，而是从 R1 scope、owner、实现规模、风险与验证矩阵独立判断。

结论如下：

- 第 1 项事实成立，但属于明确的 live-only accepted boundary；从 remaining risks 删除。
- 第 2 项固定容量事实成立，但“容量不正确”尚无生产证据；保留为 `needs-more-evidence`，且必须按 Host watcher 与 Service relay 两个 owner/失败域拆成两个 validation/tuning WU。
- 第 3 项事实成立，但属于明确的双序列域 accepted boundary；从 remaining risks 删除。
- 第 4 项对 R1 E2E 夹具的描述成立，但将其定性为 R1 remaining risk 被高估；原 WU 已有真实 provider 与真实交互证据，R1 的变更路径也不包含 provider；从 remaining risks 删除。
- 第 5 项是独立 CLI UX backlog，但原描述不精确：160 字符是“每个 delta”的截断上限，不是累计 thinking 行的总上限。复用已有 `WU-CLI-SMOKE-01-R2`，等待产品语义确认。
- 五项均不应标为 `current-WU-fix`。第 1、3 项若“修复”会推翻已接受协议；第 2 项缺少 workload/SLO，当前改常量只会产生任意参数；第 4 项不存在 R1 代码缺口；第 5 项属于已有、不同 scope 的产品 UX WU。

## 2. 五项逐项代码路径证据与裁决

### 2.1 overflow / detach / disconnect / Host close-crash-restart 后 transient delta 不补放

**动机判断：事实真实，风险定性被高估。** Transient delta 的确不会在晚订阅、detach、overflow、Host close 或进程重启后补放；但这不是遗漏的 durable delivery，而是 R1 明确采用的 live-only contract。若没有“断线后恢复 reasoning/content/tool-call 增量”的独立产品需求，把该边界继续列为 remaining risk 会把已接受的协议选择误报成缺陷。

**正确 semantic owner：** `HostTransientDeltaHub` 与 Host 的 `watch_session_events(...)` 生命周期共同拥有运行态 fan-out、订阅、溢出、终态 fence 和关闭语义；`EventLog` 只拥有 durable `HostEvent`。Service、CLI、Engine 均无权在下游补造或重放 transient delta。

**直接设计与代码证据：**

- `docs/host/design.md:333-361` 定义 durable/transient 两域；其中 `:359` 明确 disconnect、detach、overflow、Host close、进程退出与新 runtime 后不 replay，`:361` 明确 watcher 的有界 slow-consumer 行为。
- `dayu/host/api.py:2988-3054` 的 `HostTransientDelta` 只有 `runtime_id/runtime_sequence`，没有 durable `event_sequence`；`dayu/host/api.py:3411-3476` 的 `HostEvent` 才携带 durable `event_sequence`。
- `dayu/host/transient_delta.py:187-220` 为每个 subscription 建立有界 queue；`:242-258` 负责 drain 与 terminal filter；`:285-319` 在 overflow、terminal fence、detach、close 时停止订阅；`:321-336` 使用 non-blocking offer，并在满队列时 detach slow consumer；`:388-464` 由新 hub 生成 `runtime_id` 与 runtime-local sequence；`:477-494` 在 hub close 时清理全部订阅。
- `dayu/host/open_host.py:905-929` 建立 watcher；`:964-1020` 在 durable terminal 前排空已接收 transient 并设置 terminal fence；`:1022-1047` 的 Host close 关闭 hub；`:1194-1283` 的 closable iterator 在退出时 detach；`:1460-1549` 表明每次 `open_host(...)` 创建新的 hub，启动失败也会关闭，不存在跨 Host 实例 replay source。
- `dayu/host/engine_ingest.py:1030-1042` 与 `:5212-5294` 将三类 Engine delta 映射并发布为 transient envelope，发布失败与 durable transaction 隔离；没有写入 `EventLog` 的路径。

**直接测试证据：**

- `tests/host/test_transient_delta.py:157-190` 断言 fan-out、late attach 不补放，以及新 runtime identity/sequence；`:193-216` 覆盖 detach、terminal 与 hub close；`:282-346` 覆盖 overflow、close readiness，以及慢 watcher 不拖累快 watcher。
- `tests/host/test_watch_session_events.py:493-617` 断言 live delta 可在 terminal 前被 watcher 看到、三类 delta 的 `EventLog` 行数为零，以及容量满时慢 watcher 失败而快 watcher与 durable terminal 仍正常；`:659-805` 覆盖 never-started、detach、missing session、Host close、watcher cancel 与 late attach 不 replay。
- `tests/host/test_transient_delta_stress.py:57-140` 对三类各 1,000 个 delta 验证 live fan-out、durable terminal/Outbox 正常且 transient 仍为零持久化。

**裁决：`accepted boundary`。** 从 remaining risks 删除，不创建 WU。

**能否在当前 WU 实施关闭：否。** “关闭”该项意味着新增 durable transient log、ack/cursor、恢复与淘汰策略，或者破坏现有 live-only contract；这不是 R1 的最小修复，而是新的跨持久化、生命周期与查询协议产品能力。若未来出现明确断线恢复需求，应先定义新的 Host-owned replay contract，而不是从现有 runtime sequence 或日志字符串反推。

### 2.2 Host watcher 与 Service relay 固定容量 256、无真实负载调优

**动机判断：事实真实，但严重性未知。** 两处容量均为 256，现有测试验证的是有界行为与失败隔离，不是代表性生产 workload 下的吞吐、积压、内存和终态延迟。当前没有证据证明 256 过小或过大；因此不能定性为已知 defect，也不能直接把两个 256 合并为一个“统一调参”任务。

**正确 semantic owner：**

- Host watcher 容量属于 `HostTransientDeltaSubscription` / `HostTransientDeltaHub` 的订阅隔离与 slow-consumer contract。
- Service relay 容量属于 `_WatchAndWaitRuntime.queue` 与 `_drain_host_events(...)` 的入口并发协调和 terminal-observation contract。

两者虽恰好取值相同，但 queue 的生产者、消费者、阻塞方式、失败传播与观测指标不同；不存在应共享的业务事实或跨层常量 owner。

**直接设计与代码证据：**

- `docs/host/design.md:361` 明确 Host watcher 当前固定容量为 256，并定义 slow consumer 只终止自身 watcher。
- `dayu/host/transient_delta.py:26` 定义 Host 私有容量常量；`:187-220` 将其用于 subscription queue；`:285-336` 定义满队列后的 typed failure、detach 与对其他订阅者的隔离。
- `dayu/service/entrypoint_runtime.py:76` 独立定义 Service relay 容量 256；`:500-511` 的 `_WatchAndWaitRuntime` 持有 relay；`:1013-1033` 建立有界 queue；`:1036-1054` 的 drain 使用 `await queue.put(...)` 形成 backpressure，并保留原始 watcher exception；`:1157-1212` 消费 Host session events；`:1268-1318` 只把 reasoning delta 投影为 `EntrypointThinking`，content/tool-call delta 不进入 CLI thinking。
- `dayu/service/README.md:27` 记录 Service relay 的 256 容量；`dayu/README.md:100,134` 记录有界 relay/live delta 边界。这些是当前行为说明，不是生产调优证据。

**直接测试证据与证据缺口：**

- `tests/host/test_transient_delta.py:311-346` 与 `tests/host/test_watch_session_events.py:545-617` 验证 Host 精确容量边界、slow watcher detach、快 watcher 不受影响及 durable terminal 可达。
- `tests/service/test_entrypoint_runtime.py:1781-1815` 验证 Service relay 的 `maxsize == 256` 与 drain failure 保留原始异常。
- `tests/cli/test_transient_slow_consumer_path.py:52-55,129-135,230-400` 使用每类 400 个 delta 压过 256 容量，并通过真实 Host → Service → CLI 生产路径验证 slow-consumer error、Outbox fallback 与 durable terminal；其可控 worker 用来确定性地产生所需三类 delta。
- 上述测试没有提供生产 delta burst 分布、CLI/Service 消费时延、允许内存预算、slow-consumer 可接受频率或 terminal-observation SLO，因此不能从测试值推导生产最优容量。

**裁决：`needs-more-evidence`，并以两个 `deferred-with-owner` WU 保留。** 建议 ID 为 `WU-HOST-TRANSIENT-CAPACITY-01` 与 `WU-SVC-ENTRYPOINT-RELAY-CAPACITY-01`，不得合并。

**能否在当前 WU 实施关闭：否。** 没有 workload 与 SLO 时，把 256 改成任意其他值不会关闭风险；提前增加 public knob、共享常量或 unbounded queue 则会扩张 contract 并掩盖 owner 差异。当前可验证的是机制正确，不是参数最优。两个 WU 均应以“有真实证据后先 profile/benchmark，再决定是否改代码”为 trigger，而不是立即进入 implementation。

### 2.3 durable 与 transient 无跨域可重放总序

**动机判断：事实真实，风险定性被高估。** 当前只有 durable `event_sequence` 和 runtime-local transient `runtime_sequence`，没有可用于恢复的跨域全序；这是有意避免将 live presentation delta 冒充 durable business fact。没有审计、重放或恢复产品需求时，全序本身不产生用户可见正确性目标。

**正确 semantic owner：** durable 顺序由 Host `EventLog/HostEvent` 拥有；live 顺序由 `HostTransientDeltaHub` 拥有。若未来需要跨域 replayable timeline，它必须是新的 Host public persistence/query contract，不能由 Service/CLI 用到达时间、两个 sequence、日志或时间戳拼接得出，也不应下沉给 Engine。

**直接设计与代码证据：**

- `docs/engine/design.md:28-38,450-513` 将 Engine stream 定义为单次 generator 的观察顺序；`EngineEvent` 没有 durable cursor/fan-out/replay 语义，持久化由 Host 拥有。
- `docs/host/design.md:345-359` 明确 durable/transient owner、不同 envelope identity、两套 sequence domain、terminal fence，以及“不承诺跨域 global total order”。
- `dayu/host/api.py:2988-3054` 与 `:3411-3476` 分别定义 transient runtime sequence 和 durable event sequence；类型层没有可误用的统一 cursor。
- `dayu/host/open_host.py:964-1020` 只保证 watcher 已接收 transient 在 durable terminal 前被 drain，并不把两域写成统一日志。
- `dayu/host/engine_ingest.py:864-875,5276-5294` 先完成 durable transaction/promote，再 best-effort 发布 transient；transient 发布错误不会回滚 durable state，证明两者故意不是同一提交序列。

**直接测试证据：**

- `tests/host/test_transient_delta.py:138-154` 断言 durable/transient identity 字段分离。
- `tests/host/test_watch_session_events.py:493-617` 同时断言 live delta、durable terminal 与 transient 零 EventLog 行；`:1079-1100` 的测试 helper 会在预期 delta 前先到 terminal 时失败，验证的是 terminal fence，而不是虚构全序。
- `tests/host/test_transient_delta_stress.py:57-140` 验证高量 transient 与 durable terminal/Outbox 可以在各自 owner contract 下同时正确。

**裁决：`accepted boundary`。** 从 remaining risks 删除，不创建 WU。

**能否在当前 WU 实施关闭：否。** 最小实现并不存在：任何“统一 sequence”若不持久化便不可重放，若持久化则会改变 EventLog schema、事务边界、恢复/保留策略与 public query contract。缺少独立产品需求时实施会是过度设计。

### 2.4 E2E 使用可控 worker、没有真实外部 LLM provider

**动机判断：测试事实真实，但作为 R1 remaining risk 不成立。** R1 的受影响生产路径是 Engine delta 映射后的 Host fan-out、Service relay、CLI 展示及 slow-consumer/terminal failure；可控 worker 只替换 worker factory，以确定性地产生三类 delta，其余 Host → Service → CLI 路径均为生产实现。真实 provider 具有凭证、网络、成本和输出非确定性，也不能保证单次响应覆盖 reasoning/content/tool-call 三种 delta，因此不是该 failure matrix 的更强替代。

**正确 semantic owner：** R1 acceptance 的证据组合由该 WU 的测试/closeout owner 负责；外部 provider wire/conformance 属于 Engine provider integration lane。不能为满足 R1 形式要求而在 CLI 或 Service 测试中复制 provider 语义。

**直接代码与测试证据：**

- `tests/cli/test_transient_slow_consumer_path.py:230-400` 通过真实 `open_host(...)`、Service entrypoint 与 CLI 路径执行，只注入 `TransientStreamWorkerFactory`；测试断言 typed slow-consumer error、Outbox fallback、terminal 与清理，而不是 mock 下游消费者。
- `tests/cli/test_transient_slow_consumer_path.py:52-55,129-135` 明确使用 400 个 delta 跨越容量 256，覆盖真实 overflow 机制。随机外部模型响应无法稳定构造同一矩阵。
- `docs/reviews/wu-cli-smoke-01-manual-validation-evidence.md:10-30` 已记录原始 `WU-CLI-SMOKE-01` 的真实 provider 调用与 HTTP 200 最终答案；`:32-59` 记录真实交互运行与 Ctrl+C 路径。
- `docs/reviews/wu-cli-smoke-01-final-closeout.md:87` 起记录原 WU 的真实交互用户验证；`docs/host/issues-implementation-control.md:289-345` 也将真实环境验证作为原 WU 验收证据。
- `utils/smoke_async_agent_providers.py` 已提供 Engine/provider smoke 入口；该入口验证 provider 集成，不拥有 R1 的 Host watcher/Service relay/CLI slow-consumer contract。
- `git diff main...HEAD -- dayu/cli/thinking.py` 显示 R1 对 renderer 的生产变更集中在 runtime identity/sequence，不涉及 provider transport 或 provider event normalization。

**裁决：`rejected`（作为 R1 remaining risk）；同时接受 deterministic test boundary。** 从 remaining risks 删除，不创建 WU。真实 provider smoke 可以按既有 Engine/provider 流程继续运行，但不应伪装为 R1 未关闭代码风险。

**能否在当前 WU 实施关闭：否。** 没有待修生产缺陷。当前追加一次真实 provider 调用只增加环境相关验证，仍无法覆盖三类 delta 与 overflow/terminal 的确定性组合；新增 provider-specific implementation 更会越过 R1 scope 与 semantic owner。

### 2.5 CLI thinking 160 字符单行展示 / R2

**动机判断：独立 UX 动机成立，但原描述部分失真。** 当前并非“整条 thinking 运行态行最多 160 字符”：每个 delta 会先被单行化并截断到 160 字符，再持续追加到同一 `_line_text`，所以累计行可以超过 160 字符。真实 backlog 是没有明确的累计缓冲上限、滚动/展开 panel 或 history 语义，而非现有总长 160 的简单放宽。

**正确 semantic owner：** `CliThinkingRenderer` 是终端投影、单行化、截断与清理行为的唯一 owner。Host transient contract、Service relay 与 provider reasoning 开关都不拥有 CLI 展示策略。

**直接代码与测试证据：**

- `dayu/cli/thinking.py:21-23` 定义 `_TEXT_MAX_CHARS = 160`；`:167-181` 的 `_single_line_delta_text(...)` 对单个 delta 做空白折叠与截断；`:106-116` 的 `record(...)` 再把每个已截断 delta 追加到 `_line_text`，没有累计 160 字符 cap。
- `dayu/cli/thinking.py:87-117,155-203` 分别拥有事件接收、渲染、单行化与完成/清理行为。
- `tests/cli/test_thinking_renderer.py:11-83` 断言 thinking 输出、追加和单行行为；`:86-199` 覆盖 finish、TTY/非 TTY、close、顺序和 runtime identity，但没有累计长度、单 delta 截断边界或可展开 history 的产品断言。
- `git diff main...HEAD -- dayu/cli/thinking.py` 表明 R1 只把 renderer 顺序校验从 durable event identity 改为 runtime identity/sequence；160 字符与单行追加逻辑来自 R1 之前，不是本 PR 引入的 regression。
- `docs/host/issues-implementation-control.md:251-253` 已有 `WU-CLI-SMOKE-01-R2` residual；因此不能新建重复 ID。

**裁决：`deferred`，复用 `WU-CLI-SMOKE-01-R2`。** 应修正总控描述，使其准确反映“单 delta 160 截断 + 累计单行追加”，并等待用户 UX requirement。

**能否在当前 WU 实施关闭：否。** R2 需要先选择至少三项产品语义：累计缓冲上限、滚动或可展开交互、TTY/非 TTY 与历史保留边界。直接删除 160、把累计行硬截断或引入 panel 都会未经需求选择不同用户体验，并扩张 R1 的 runtime identity 修复 scope。

## 3. WU mapping table

下表包含全部五项；只有状态仍为 remaining risk 的行才分配/复用 WU。`current-WU-fix?` 是对生产实现可闭环性的判断，不受本次 artifact-only 写权限影响。

| 来源项 | 稳定 WU ID | type | 裁决 / 主总控状态 | current-WU-fix? | 理由 | owner / destination | trigger | next action | 若实施则 slice / allowed files | non-goals |
|---|---|---|---|---|---|---|---|---|---|---|
| 1. live delta 不补放 | — | accepted contract boundary | `accepted boundary`；从 residual 删除 | 否 | 行为与设计、类型及测试一致；关闭它需要新的 durable replay 产品协议 | 当前 owner 为 Host transient hub/watch lifecycle；未来新需求应进入 Host persistence/query contract lane | 只有用户明确要求断线/重启后恢复 transient presentation history 时，才新开 goal confirmation | 当前无动作 | 当前无 implementation slice | 不将 transient 写入 EventLog；不在 Service/CLI 补放；不以 runtime sequence 冒充 durable cursor |
| 2a. Host watcher 256 | `WU-HOST-TRANSIENT-CAPACITY-01` | validation / performance tuning | `needs-more-evidence` → `deferred-with-owner` | 否 | 缺少 workload、SLO 与生产失效数据；任意改常量无法证明更正确 | Host transient hub performance-validation lane / user decision；无 GitHub Issue | 提供代表性 delta burst/consumer workload 与 watcher SLO，或观测到 slow-consumer 频率、backlog、内存、交付延迟不满足 SLO | 先 owner-level profile/benchmark；据证据决定保留或调整私有容量 | Validation slice：`tests/host/test_transient_delta.py`、`tests/host/test_transient_delta_stress.py`，必要时仅在 `utils/` 放分析脚本；若证据要求实现，再限于 `dayu/host/transient_delta.py`、对应 Host tests，并按触发规则更新 `docs/host/design.md`、`dayu/host/README.md`、`tests/README.md` | 不修改 Service relay；不共享跨层常量；不增加 public knob、unbounded queue、silent drop 或 replay |
| 2b. Service relay 256 | `WU-SVC-ENTRYPOINT-RELAY-CAPACITY-01` | validation / performance tuning | `needs-more-evidence` → `deferred-with-owner` | 否 | queue 的阻塞/消费失败域不同于 Host；同样缺少 workload/SLO，不能因为数值相同而联动调参 | Service entrypoint runtime performance-validation lane / user decision；无 GitHub Issue | 提供代表性 CLI/Service consumer workload 与 terminal-observation SLO，或观测到 relay backlog、watcher failure/Outbox fallback、内存或终态延迟不满足 SLO | 单独 profile `_WatchAndWaitRuntime.queue` 与 `_drain_host_events(...)`；据证据决定保留或调整私有容量 | Validation slice：`tests/service/test_entrypoint_runtime.py`、`tests/cli/test_transient_slow_consumer_path.py`，必要时 `utils/`；若证据要求实现，再限于 `dayu/service/entrypoint_runtime.py` 与对应 Service/CLI tests，并按触发规则更新 `dayu/service/README.md`、`tests/README.md` | 不修改 Host watcher；不引入跨层共享常量/public knob；不 silent drop、不设 unbounded relay、不替代 Outbox terminal owner |
| 3. 无跨域可重放总序 | — | accepted contract boundary | `accepted boundary`；从 residual 删除 | 否 | 双序列域是避免 live presentation 冒充 durable fact 的设计；统一可重放序列需要全新持久化/query contract | 当前分别由 Host EventLog 与 transient hub 拥有；未来新 contract 的 owner 应为 Host public persistence/query boundary | 只有独立审计/重放/恢复产品需求成立时，才新开 goal confirmation | 当前无动作 | 当前无 implementation slice | 不由 Service/CLI 按到达时间、日志、时间戳或两套 sequence 合成全序；不把 persistence 下沉 Engine |
| 4. 无真实外部 provider 的 R1 E2E | — | test-strategy boundary | `rejected`；从 residual 删除 | 否 | R1 受影响生产路径已被确定性覆盖；原 WU 已有真实 provider 证据；真实模型无法稳定替代三类 delta/overflow 矩阵 | R1 acceptance evidence；provider conformance 另属 Engine/provider integration lane | 无 R1 trigger；provider 变更时按既有 Engine/provider smoke 运行 | 当前无动作 | 当前无 implementation slice | 不新增 provider-specific CLI/Service 逻辑；不把网络/凭证可用性当作 Host fan-out 正确性 |
| 5. CLI thinking UX | `WU-CLI-SMOKE-01-R2` | product UX / feature | `deferred-with-owner` | 否 | 真实问题是单 delta 截断后累计单行无明确上限/展开语义；需要产品选择，且并非 R1 regression | CLI UI adapter lane / user decision；无 GitHub Issue | 用户明确 thinking UX、累计缓冲上限、TTY/非 TTY 与历史保留要求 | goal confirmation 后先冻结展示 contract，再实现与测试 | 建议 slice：`dayu/cli/thinking.py`、`tests/cli/test_thinking_renderer.py` 及必要 CLI integration tests；若用户可见行为变化，按触发规则检查根 `README.md` 与 `tests/README.md` | 不改 Host transient/durable contract；不持久化 thinking；不增加 replay；不改变 provider reasoning 开关 |

表中 allowed files 是未来 WU goal confirmation 后的建议边界，不构成本次任务的修改授权。

## 4. Existing WU / Issue duplicate audit

### 4.1 本地 WU 与总控

- `docs/host/issues-implementation-control.md:251-253` 已存在 `WU-CLI-SMOKE-01-R2`，与第 5 项完全同源；必须复用，不得另建 CLI thinking WU。但其现有文字“160 字符单行”容易被理解为累计总长，应按本文精确行修正。
- `WU-STRESS-SQLITE-01` / Issue #38 面向 SQLite 慢盘、多进程与 durable persistence，不拥有 live in-memory watcher 或 Service relay 容量，不能承接第 2 项。
- `WU-WAIT-04` 面向 awaiting E2E，未覆盖 transient 容量或 provider conformance。
- `WU-CLI-DEBUG-STREAM-01` / Issue #148 面向逐 delta diagnostic logging，不拥有 bounded queue 容量、slow-consumer SLO 或 thinking UX。
- `WU-ENG-01` 的 provider reasoning round-trip 与 `WU-ENG-02` 的诊断语义属于 Engine provider 层；它们不能替代 R1 的 Host → Service → CLI 确定性 E2E，也不构成第 4 项的新重复 WU。
- 原始 `WU-CLI-SMOKE-01` 已记录真实 provider 与真实交互验证，这正是第 4 项不应继续保留的直接 duplicate/evidence audit 结论。
- `docs/phaseflow-umbrella-optimization-control.md:287-323` 只有已完成 fix batches 与 accepted baseline boundaries，没有可承接第 2 项两个性能验证 owner 的 active WU，也没有新的第 1、3、4 项产品需求。

### 4.2 GitHub Issue / PR 只读核对

- Draft PR #180 的 head 为当前分支 `phaseflow/wu-cli-smoke-01-r1`，没有 Issue closing reference；本提案不修改 PR metadata。
- Open Issue 搜索 `thinking`、`transient`、`slow consumer`、`relay` 未发现直接重复项。
- `capacity` 命中 Issue #38，但其语义是 SQLite durable stress，已判定不同 owner/失败域。
- `live stream` 命中的 Web、GUI 与 WeChat entrypoint 工作项属于其他入口，不拥有 Host watcher 或 CLI thinking 展示语义。

因此，第 2 项两个 ID 是新的且按 owner 拆分的稳定提案；第 5 项复用已有 R2；第 1、3、4 项不制造 WU。

## 5. 建议写入主总控的精确行

仅以下三项仍保留为 residual。第 1、3、4 项不得写入 active residual 或 current work units。

### 5.1 Residual Risk Reconciliation 表

```markdown
| WU-HOST-TRANSIENT-CAPACITY-01 | deferred-with-owner | Host transient hub performance-validation lane / user decision；无 GitHub Issue | 来源 `WU-CLI-SMOKE-01-R1`。仅在代表性生产 workload 与 watcher consumption SLO 已提供，或生产观测出现 `session_live_stream/slow_consumer` 频率、峰值 backlog、内存或交付延迟不满足 SLO 时进入 goal confirmation；先对 `HostTransientDeltaSubscription` 私有 queue 做 owner-level profiling/benchmark，再依据证据决定保留或调整内部常量。不得预先增加 public knob、unbounded queue、drop-and-continue、replay 或修改 Service relay。 |
| WU-SVC-ENTRYPOINT-RELAY-CAPACITY-01 | deferred-with-owner | Service entrypoint live relay performance-validation lane / user decision；无 GitHub Issue | 来源 `WU-CLI-SMOKE-01-R1`。仅在代表性 CLI/Service 消费 workload 与 terminal-observation SLO 已提供，或生产观测出现 relay backlog、watcher failure/Outbox fallback 频率、内存或终态延迟不满足 SLO 时进入 goal confirmation；先对 `_WatchAndWaitRuntime.queue` 与 `_drain_host_events(...)` 做 owner-level profiling/benchmark，再依据证据决定保留或调整内部常量。不得修改 Host watcher 容量、引入跨层共享常量/public knob、silent drop、unbounded relay 或替代 Outbox terminal owner。 |
| WU-CLI-SMOKE-01-R2 | deferred-with-owner | CLI UI adapter lane / user decision；无 GitHub Issue | `CliThinkingRenderer` 当前把每个 delta 单行化并按 160 字符截断后持续追加到同一运行态行，累计行并非 160 字符总上限，也没有可展开 panel/history；仅在用户提出明确 thinking UX、累计缓冲上限与终端交互要求后进入 goal confirmation。不得修改 Host transient/durable contract、持久化 thinking、增加 replay，或改变 provider reasoning 开关。 |
```

### 5.2 Current Work Units 表

```markdown
| WU-HOST-TRANSIENT-CAPACITY-01 | deferred | Host transient watcher capacity evidence and tuning | Host transient hub performance-validation lane / user decision；无 GitHub Issue | 来源 WU-CLI-SMOKE-01-R1；等待代表性生产 workload/SLO 或实际 slow-consumer/内存/延迟证据，不是当前 implementation entry point。 |
| WU-SVC-ENTRYPOINT-RELAY-CAPACITY-01 | deferred | Service entrypoint live relay capacity evidence and tuning | Service entrypoint runtime performance-validation lane / user decision；无 GitHub Issue | 来源 WU-CLI-SMOKE-01-R1；等待代表性消费 workload/SLO 或实际 relay backlog/fallback/终态延迟证据，不是当前 implementation entry point。 |
| WU-CLI-SMOKE-01-R2 | deferred | Expandable CLI thinking runtime display | CLI UI adapter lane / user decision；无 GitHub Issue | 等待明确用户 UX 要求；先裁决累计行上限、滚动/展开语义、TTY/非 TTY 与历史保留边界，不是当前 implementation entry point。 |
```

## 6. Design / README 变化判断

本任务不需要且不允许修改 design 或 README：

- 第 1、3 项的 accepted boundary 已由 `docs/host/design.md` 与 `docs/engine/design.md` 精确表达，不应为了从 remaining risks 删除而重复改 design。
- 第 4 项只涉及验证证据归类，不改变任何运行时或用户 contract。
- 第 2 项当前只登记 evidence-gated validation WU；在没有 workload/SLO 和实现变化前，不应改文档声称新容量策略。未来若 Host 容量 contract 改变，应检查 `docs/host/design.md`、`dayu/host/README.md`、`tests/README.md`；若仅 Service 私有 relay 改变，应检查 `dayu/service/README.md`、`tests/README.md`。两者不得机械联动。
- 第 5 项等待产品 UX 决策；未来若改变用户可见 CLI 行为，应检查根 `README.md` 与 `tests/README.md`。它不触发 Host/Engine design 变化，除非未来需求错误地扩张为新的 durable contract，而本文明确将其列为 non-goal。

## 7. 验证命令与结果

本文完成后执行以下验证：

```bash
source .venv/bin/activate
pytest tests/host/test_transient_delta.py tests/host/test_watch_session_events.py tests/service/test_entrypoint_runtime.py tests/cli/test_thinking_renderer.py tests/cli/test_transient_slow_consumer_path.py -q
pytest -o addopts="" -m stress tests/host/test_transient_delta_stress.py -q
pyright
git diff --check
git diff --no-index --check /dev/null docs/reviews/wu-cli-smoke-01-r1-residual-risk-wu-proposal-codex.md
git status --short
git diff --name-only
```

结果：

- 相关 owner/path 测试：`75 passed, 3 warnings in 5.90s`。3 项均为第三方 `edgar` deprecated module warning，不是本任务新增失败。
- Host transient stress：`1 passed in 0.64s`。
- Pyright：`0 errors, 0 warnings, 0 informations`；另有工具自身的新版本提示，不影响类型检查结论。
- `git diff --check`：exit code 0，无 tracked whitespace error。
- 对尚未跟踪 artifact 执行 `git diff --no-index --check /dev/null ...`：无错误输出；exit code 1 仅表示 `/dev/null` 与新文件内容不同，没有 whitespace diagnostic。
- `git status --short`：仅 `?? docs/reviews/wu-cli-smoke-01-r1-residual-risk-wu-proposal-codex.md`。
- `git diff --name-only`：无输出，因为唯一变更是尚未跟踪的新 artifact；与 `git status --short` 合并核对后确认没有其他文件变化。

## 8. Residual / open questions

- Host watcher 与 Service relay 都缺少代表性生产 workload、消费 SLO、内存预算和可接受 slow-consumer/fallback 频率；这正是两个 WU 的 trigger，不是授权当前任意调参的理由。
- 当前没有断线/重启 replay 或跨域 durable total order 的产品需求。若未来提出，需从 Host public persistence/query contract 重新做 goal confirmation，不能复活 R1 transient runtime identity 作为伪 cursor。
- `WU-CLI-SMOKE-01-R2` 尚缺累计缓冲、滚动/展开、TTY/非 TTY 和历史保留的明确 UX 决策；现有总控文字需要先纠正“160 字符”的语义。
- 本文只给出主总控精确候选行；按用户约束未实际修改 control document。由总控 owner 在另行授权的 reconciliation 动作中写入。
- 没有发现可在当前 R1 WU 通过最小正确生产实现关闭的事项；因此不存在因 defer 而遗漏的 current-WU implementation slice。

## 9. Completion status

`evidence-complete / proposal-complete / control-write-pending-owner-authorization`。

五项均已完成动机、semantic owner、代码/测试/设计路径、重复项、current-WU-fix 与 WU 映射核对。最终保留两个 evidence-gated capacity WU 与既有 CLI R2；删除三项已接受或不成立的 R1 remaining risk。本 artifact 未执行生产、测试、README、design、control、Issue 或 PR metadata 修改。
