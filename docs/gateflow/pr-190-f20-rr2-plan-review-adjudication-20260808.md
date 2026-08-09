# PR 190 F20 RR2 Plan Review Adjudication

## Gate decision

- Work unit：F20。
- Gate：`plan-review RR2`。
- Reviewed plan：`docs/gateflow/pr-190-f20-plan-20260808.md`，SHA-256
  `503e7d1a27757c763d2a4f9cb68e047c3532f960daaec1d41e29e0640c651d0a`。
- Independent reviews：
  - AgentDS：`docs/reviews/plan-review-20260808-205705.md`，`FAIL`，SHA-256
    `d252d036692a3dc61aca6178b2bb04ecc98a414f5330a4e11c1f1137afc86305`；
  - AgentMiMo：`docs/reviews/plan-review-20260808-205808.md`，`FAIL`，SHA-256
    `84ae6448303f155a9af0f7d8d1709b15831d93e3728bbb58d47742a987d23ba5`。
- Controller verdict：`FAIL`。共同的 formal pre-forward seam finding 与 DS 的 deadline-state finding 均接受；只修 plan，
  修订后必须对同一新 SHA 做 MiMo/DS 两路独立 RR3。

本裁决不授权实现、真实 provider、产品/CLI 装配修改、oracle/scenario 修改、B2 裁决或 readiness 变更。

## Controller direct verification

Controller 没有用 reviewer 自报替代 owner 核验，已确认：

1. production Service assembly 在 `dayu/service/host_assembly.py` 直接把 `DefaultLocalEngineWorkerFactory()`写入
   `OpenHostOptions.worker_factory`；interactive CLI 取得 assembly 后直接调用 `open_host(options)`。当前 CLI 没有 observation
   wrapper/factory callback 或 external composition 参数。
2. ordinary Engine request 的 typed delegate seam 是 `LocalEngineWorker.accept(snapshot, request)`；production default worker 随后在
   events 打开时调用 `run_agent_messages(request)`。计划声称的“既有 audited transparent transport wrapper seam”不存在已冻结的
   owner、public installation path 或 production CLI consumption proof。
3. `worker_factory`只拥有 ordinary Engine dispatch。compactor proposal 的唯一 typed owner 是独立的
   `HostLocalExecutionOptions.context_compactor`；production `open_host`从 `CompactorRunnerBaseline`构造
   `LLMContextCompactor`。因此 provider-free proof 也不得声称 ordinary 与 compactor call 都经过同一个 worker factory。
4. proof 不等于 formal chain。proof 可以在显式 Host typed construction中分别注入 run-owned deterministic
   `LocalEngineWorkerFactory`与 deterministic `ContextCompactor`，并由各自 ledger 与 Host EventLog/manifest exact 对账；formal MiMo
   chains则必须继续使用未经包装的 production CLI/default factory/production `LLMContextCompactor`。
5. 当前 Python runtime 的 audit hook直接观察到 `socket.__new__`、`socket.connect`与`socket.getaddrinfo`事件；当前主机
   `/usr/bin/sandbox-exec` SHA-256 为
   `8290e4be7387a0df83cd1559e86afd880464f269450573d012795761fe298f16`，以 deny-network profile运行 numeric TCP
   connect得到 `PermissionError(EPERM)`，其 spawned Python child 也继承同一 deny。该诊断只证明可行 enforcement seam，尚不是
   Slice 1 PASS；实现仍须冻结 bootstrap/profile/binary identity、完整事件集与 parent/child negative self-test。
6. allocation-time“每 chain 540s 上限”与 activation-time absolute cutoff 是不同事实。未启动 chain 只有 allocation/skip truth，
   不应伪造 active deadline。原 summary common keys 把二者混成一个 `chain_deadline_ref`，不能同时支撑 skipped publication 与
   attempted remaining-time计算。

## Finding adjudication

### F20-RR2-PA-01 — Formal pre-forward wrapper seam 是未证明的计划自增约束

- 来源：`F20-RR2-DS-001`、`F20-RR2-MIMO-001`。
- 裁决：`accepted`，严重程度 `high`。
- 理由：reviewer 对旧计划的反例成立；stock production CLI不能合法安装该 wrapper。该缺口不是已证明的产品 defect，也不授权为
  observation tooling新增产品/CLI seam。
- 修订方向：
  1. 删除 formal “transparent pre-forward wrapper”、request interception、delegate zero-call及其不存在的装配声明；禁止以
     monkeypatch、`sitecustomize`替换产品符号、endpoint/profile改写或 custom opener冒充 production CLI。
  2. formal chain保持 stock production CLI。每次 actual accepted replacement 后，下一 ordinary boundary 只认 Host canonical
     `CONTEXT_BUDGET_EVALUATED`、manifest、candidate projection与 action owner；publication/evidence gate要求
     `soft <= predicted < hard`且 action=`compact_soft_threshold`。不满足就把该 chain seal为`needs-more-evidence`/failed，停止后续
     segment并不得计入 B2 predicate。这里的 fail-closed 是**证据接受 gate**，不谎称 external driver能在同一 segment 内拦截
     production transport。
  3. R4 若打开第三个 operation，允许当前已启动 segment在既有 99-call hard cap与 deadline内产生 canonical terminal；segment结束
     后立即 seal `needs-more-evidence`，不再启动 follow-up/segment，也不得声明 reconnect成立。删除 race-free “第三 operation
     首次 compactor call=0”主张。
  4. provider-free proof 使用 production Host typed construction，但分别注入 run-owned deterministic ordinary
     `LocalEngineWorkerFactory`与 deterministic `ContextCompactor`。两份 owner ledger必须与 ordinary runner manifests、compactor
     proposal manifests/attempts/terminals exact equality；不得把 compactor calls记到 worker factory。
  5. proof process tree在任何 Dayu import/Host construction前进入冻结的 OS deny-network policy，并安装仅用于审计、不修改请求或
     owner语义的 Python audit hook。计划必须列出被拒事件与参数判定，覆盖 DNS、numeric TCP、UDP及已知 Python child；隔离
     negative self-test分别命中 parent/child并证明调用在 syscall/endpoint接触前失败。actual proof audit hit须为0，OS policy必须
     对全部 descendants生效；任一 identity/coverage/ledger偏差都在provider前 blocking stop。

### F20-RR2-PA-02 — Allocation 与 active deadline 未 typed 分型

- 来源：`F20-RR2-DS-002`。
- 裁决：`accepted`，严重程度 `high`。
- 理由：三条 540s 是 allocation maxima，总计上限 1,620s，不是 allocation时同时启动的三个 absolute clock。skipped chain没有
  active deadline，不能发布伪造的 cutoff。
- 修订方向：
  1. global owner在 allocation前冻结 global start/provider cutoff/finalization reserve/ref/SHA；每条 chain都冻结 immutable
     allocation entry（ordinal、role、`max_wall_seconds=540`、call caps、allocation ref/SHA、state=`not_started`）。
  2. 只有 attempted chain在spawn/provider start前原子创建 active deadline owner：activation time、
     `cutoff=min(activation+540s, global_provider_cutoff)`、effective seconds、state=`active`、ref/SHA。remaining-time只从该 active
     owner与global owner计算。
  3. `provider_not_started` variant只发布 allocation ref/SHA、state=`not_started`与 skip seal，明确 active deadline
     `not_created`；不得填 active cutoff/ref。
  4. publication schema按 discriminator定义 exact variant keys：common global/allocation identity；attempted额外要求 active deadline
     ref/SHA/activation/cutoff；provider-not-started额外要求 `active_deadline_state=not_created`与 skip reason，禁止 active fields。
     private typed projection独立重算这些状态、有效时长与总 allocation max `3×540=1620`，corruption matrix覆盖伪造 active
     deadline、missing activation、cutoff超global与 variant/key漂移。

## Required revised plan

RR3 target必须同时做到：

1. proof明确分开 ordinary worker factory与 compactor typed port ledger，并以 OS deny-network + Python audit hook覆盖实际 proof
   process tree；formal stock production CLI完全不包装。
2. formal actual sizing只作为 canonical evidence acceptance predicate；删除不存在的 pre-forward transport guard与 race-free zero-call
   主张，保持 bounded 99/73/73=245 calls与失败保真。
3. deadline owner分成 allocation与activation两类 typed truth，publication union按 attempted/skipped精确分型。
4. PA01 storage material、scenario-existence/universal residual、clean-seed隔离、publication terminal exact complement等 RR2 已关闭
   部分保持不退化。

修订 plan 与 fix artifact 后冻结 byte SHA，再由两路独立 RR3。RR3 双 PASS 前禁止实现与真实 provider。
