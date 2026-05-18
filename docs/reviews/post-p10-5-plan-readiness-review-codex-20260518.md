# Host P10.5 Plan Readiness Review

生成时间：20260518-204732

## Findings

### F1-未修复-中-clarification-建议 slice 未显式承接全部必测 smoke

- **标记**: clarification
- **位置**: `docs/host/implementation-control.md` Phase 10.5 建议 slice 与验证要求；`docs/host/post-p10.md` Smoke Coverage Matrix。
- **问题类型**: 切片归属澄清 / 测试缺口防护
- **当前写法**: 总控验证要求明确要求 `real-runner no-tool multi-turn smoke`、`mock-tool wiring smoke`、`real-runner matrix smoke`、`真实 compactor compact smoke`、`WAITING -> public resolve_wait(...) resume smoke`、`steer / retry / replay local smoke`、`cancel smoke`、`close_session(...) public contract smoke`。但建议 slice 只显式列出 opener、event stream、steer、retry/replay、S1/S2/S5、S3，未在 slice 名称中直接承接 S4 compact、WAITING resume、multi-client watch、`close_session` 边界。
- **反例/失败场景**: implementation-ready plan 若机械照抄建议 slice，可能把 compact 与 wait resume 只留在验证清单中，没有实现 owner 和验收点；实现后期才发现 `open_host(options)` 没接 compactor baseline、memory catch-up 或 `resolve_wait` wakeup，Service 仍需碰内部 scheduler / compact store / wait table。
- **为什么有问题**: P10.5 的证明问题不是“最后拿到字符串”，而是普通 Service 只通过 Host public interface 完成多轮闭环。`post-p10.md` 明确要求 S4 compact 不能从 success signal 中拿掉，且 `resolve_wait` 后必须通过同一 public opener 自动唤醒 dispatch。
- **直接证据**:
  - `docs/host/post-p10.md:72-82` 定义 S1-S5，S4 compact 与 S5 cancel 是矩阵项。
  - `docs/host/post-p10.md:122-131` 要求 S4 使用真实 compactor adapter、canonical compact event、artifact、memory projection 和 subsequent Run continuity。
  - `docs/host/post-p10.md:263-270` 要求 `WAITING` 后调用方只通过 public `resolve_wait(...)` 恢复，并最终从 terminal HostEvent 观察 final answer。
  - `docs/host/implementation-control.md:1237` 把 compact、WAITING resume、steer / retry / replay、cancel、`close_session(...)` 都列入 P10.5 smoke 覆盖矩阵。
  - `docs/host/implementation-control.md:1248-1253` 的建议 slice 未显式命名 compact / WAITING resume / close-session smoke owner。
  - `docs/host/implementation-control.md:1255-1258` 又把这些项列为验证要求。
- **影响**: 实施计划可能切片过粗或 owner 漏配，导致 review 时发现 smoke 覆盖无法落地，或让 Service 仍需 import Host internals。
- **建议改法和验证点**: implementation-ready plan 必须把 S4 compact、WAITING resume、multi-client watch、`close_session != cancel != opener close` 分配到具体 slice 和测试文件，且在 coverage checklist 中逐项标 `covered / not covered but accepted / blocking gap`。可调整建议 slice，不需要改设计真源。
- **修复风险**: 低
- **严重程度**: 中

### F2-未修复-低-clarification-`HostEventStream` 术语需要在 plan 中收敛为非 handle 语义

- **标记**: clarification
- **位置**: `docs/host/design.md` Host public interface 与类型归属；`docs/host/implementation-control.md` P10.5 目标和 HostEvent terminal contract。
- **问题类型**: 公共契约术语澄清
- **当前写法**: 设计主语义已经固定为 `watch_session_events(session_id) -> AsyncIterator[HostEvent]`，并明确不暴露 context manager / subscription handle。但设计的类型归属段落仍列出 `HostEventStream` 作为 Host 公共 API 类型之一，总控目标也偶尔写“HostEventStream 中观察 terminal final answer”。
- **反例/失败场景**: implementation agent 可能把 `HostEventStream` 做成 Service 必须理解的 subscription handle / context manager，从而偏离“朴素 async iterator”主契约，并为 Service 增加额外生命周期对象。
- **为什么有问题**: P10.5 的目标是冻结最薄普通 Service contract。若事件入口既可以是 `AsyncIterator[HostEvent]`，又可以是一个 public stream handle，会扩大调用方认知面，也容易让 `wait_final_answer` 或 payload reader 之外的第三条读路径重新出现。
- **直接证据**:
  - `docs/host/design.md:871-903` 给出的调用形态是 `events = host.watch_session_events(session_id)` 并用 `async for` 消费，且说明 terminal event 不自动结束 iterator。
  - `docs/host/design.md:905-911` 定义 `HostEvent` 与 `HostEventView` 边界，强调 Service-facing typed event 不是内部薄读模型。
  - `docs/host/design.md:916` 把 `HostEventStream` 列入 Host 公共 API 类型。
  - `docs/host/design.md:1173` 又说明 `HostEventStream` 若保留，只能作为内部实现或类型别名，不得成为 Service 需要理解的 context manager / subscription handle。
  - `docs/host/implementation-control.md:1235` 明确 terminal final answer view 通过 `watch_session_events(...)`，P10.5 不定义 `wait_final_answer(...)`。
- **影响**: 若 plan 不收敛术语，public API 可能被实现得过宽，后续 Service 需要依赖额外 stream object 或生命周期方法。
- **建议改法和验证点**: implementation-ready plan 明确：Service-facing 签名只冻结 `watch_session_events(session_id) -> AsyncIterator[HostEvent]`；如代码需要 `HostEventStream`，只能是返回类型别名 / Protocol 或内部实现细节，不要求 Service 调用 stream-specific public 方法。测试只从 async iterator 的 terminal `HostEvent` 读取 final answer。
- **修复风险**: 低
- **严重程度**: 低

## Reviewed Target And Scope

- **Review question**: 基于 `docs/host/design.md`、`docs/host/implementation-control.md` 与 `docs/host/post-p10.md` 进入 P10.5 plan / implementation 后，未来真实生产 Service 是否可以只调用 Host public interface / contract 完成普通本地多轮会话闭环。
- **Design truth**: `docs/host/design.md`
- **Control truth**: `docs/host/implementation-control.md`
- **Supporting artifact**: `docs/host/post-p10.md`
- **本次不 review 代码实现质量**: 当前任务要求的是 implementation-ready plan 前的 public API / contract decision review；未实施、未提交、未推进 gate。

## Motivation Check

动机成立。`post-p10.md:11-21` 直接说明 Phase 10 后 Host 内部多轮主体能力基本成立，但 Service 仍需手工装配 `HostDispatchScheduler`、durable store、`ActiveWorkerRegistry`、local execution、ToolingOptions、compactor 并显式唤醒 scheduler；这不是稳定 Host public runtime。P10.5 的目标不是表面补测试，而是把这条生产接线收口到 Host public opener / handle。

## Assumptions Tested

- 普通 Service 只允许依赖 `dayu.host` public namespace，不依赖 `dayu.host.dispatch`、scheduler、durable tables、dispatch rows、payload tables、test helpers。
- 第一条 prompt 与后续普通 prompt 统一走 `submit_followup(queue)`；`start_run(...)` 不再是 Service-facing public API。
- `open_host(options)` 是 async-only public opener，内部接线 scheduler / wakeup / dispatch / active registry / LocalProxy / ToolRuntime / compactor / memory catch-up。
- final answer 主路径只来自 session-level `watch_session_events(session_id)` 的 terminal `HostEvent`，不定义 `wait_final_answer(...)`、public payload reader、`read_payload(ref)` 或 `get_run_result(...)`。
- P10.5 不实现 Recovery、Outbox concrete read / drain、ToolsDiscovery / ScenePrepare、真实 Service / CLI / WeChat / GUI 接入、web tools 迁移。
- 后续 P11 / P13 等 phase 可以在不要求 Service API rewrite 的前提下扩展 Recovery / Outbox。

## Consistency Checklist

| 核对项 | 结论 | 证据 |
| --- | --- | --- |
| P10.5 goal | covered | `post-p10.md:33` 与 `implementation-control.md:1174-1178` 一致要求冻结普通本地多轮 Host public contract，后续真实 Service 使用同一 contract。 |
| scope / non-goals | covered | `post-p10.md:23-33`、`implementation-control.md:1203-1221` 排除真实 Service/CLI/WeChat/GUI、业务工具发现、动态 ScenePrepare、web tools、ConfigLoader、Outbox drain、Recovery、purge cleanup。 |
| public API | covered | `design.md:920-946` 固定最小接口集合和排除项；`post-p10.md:41-57` 同步 public API 变更护栏。 |
| runtime opener | covered | `design.md:849-869` 与 `implementation-control.md:1224-1226` 要求 `open_host(options)` 内部完成 scheduler / wakeup / active registry / dispatch 接线，不暴露给 Service。 |
| event stream | covered with F2 clarification | `design.md:871-903`、`design.md:1127-1131`、`post-p10.md:383-393` 均要求 session-level live watch，run-scoped stream / `HostEventView` 只做内部 diagnostic。 |
| final answer path | covered | `design.md:1146-1150`、`design.md:905-911`、`post-p10.md:46-55`、`post-p10.md:97` 均禁止 payload reader / wait helper 作为普通 Service 主路径。 |
| runner options | covered | `design.md:861-865`、`post-p10.md:407-417`、`implementation-control.md:1230-1232` 固定 opener baseline 与 per-run typed `runner_spec` / `runner_options` / `agent_policy` override。 |
| tool options | covered | `design.md:798-808`、`post-p10.md:313-321` 固定 opener 注入全量 `ToolBundle`，per-run `tool_names` 只选业务工具名，`None=all`、empty=none。 |
| compactor options | covered | `design.md:865-869`、`post-p10.md:303-312`、`implementation-control.md:1232` 固定 compactor independent construction-time baseline，不受 ordinary Run override 影响。 |
| cancel / close / session lifecycle | covered | `design.md:851-857`、`design.md:1132-1135`、`design.md:2311-2373`、`post-p10.md:280-291` 区分 opener close、`close_session`、cancel、purge。 |
| wait / resolve | covered | `design.md:2116-2235`、`post-p10.md:263-270`、`implementation-control.md:1233` 要求 `resolve_wait(...)` 是 public resume path，P10.5 不做生产 callback / poller loop。 |
| retry / replay / steer | covered | `design.md:1215-1305`、`design.md:2236-2309`、`implementation-control.md:1236` 要求 P10.5 按既有语义落地本地路径，Recovery-only 状态归 P11。 |
| multi-client | covered | `post-p10.md:205-214`、`implementation-control.md:1228` 固定无 client ownership / attach token，多 watcher 与并发 `submit_followup(queue)` 由 durable transaction / idempotency / event sequence 决定。 |
| Outbox exclusion | covered | `design.md:1679-1699`、`post-p10.md:198-203`、`implementation-control.md:1219`、`implementation-control.md:1229` 把 concrete read / drain 与离线 terminal smoke 交给 P13，P10.5 只冻结 identity / dedupe recipe。 |
| Recovery exclusion | covered | `design.md:2672-2739`、`post-p10.md:272-278`、`implementation-control.md:1212-1213`、`implementation-control.md:1275-1289` 把 startup recovery / positive orphan proof 交给 P11，且 P11 不得改变 P10.5 Service contract。 |
| hidden Service / CLI / WeChat assumptions | covered | `post-p10.md:23-33`、`post-p10.md:373-381`、`implementation-control.md:1203-1206` 明确真实入口改造不进 P10.5，薄 Service 只做最小 consumer proof。 |
| tool discovery / web tools assumptions | covered | `design.md:73-74`、`post-p10.md:397-405`、`implementation-control.md:1336-1400` 把 ToolsDiscovery / ScenePrepare 交给 P12；web tools 不迁移，不作为 smoke。 |

## Smoke Matrix Challenge

| Smoke / proof area | Review result |
| --- | --- |
| S1 real-runner no-tool multi-turn | Contract is ready for planning. Must use `open_host(options)`, `submit_followup(queue)`, memory catch-up, LocalProxy / real runner, terminal HostEvent. Evidence: `post-p10.md:84-98`. |
| S2 mock-tool wiring | Contract is ready for planning, with deterministic proof strategy required. Mock tool is allowed only for tool wiring and must not cheat by expected answer / run id / test private state. Evidence: `post-p10.md:100-110`. |
| S3 real-runner matrix | Contract is ready for planning. Must cover mimo, ds/deepseek, gemini, qwen through same public path; provider unavailable skips must report reason. Evidence: `post-p10.md:112-120`, `implementation-control.md:1206`. |
| S4 compact | Required and must not be dropped. Needs explicit slice owner per F1. Evidence: `post-p10.md:122-131`, `design.md:865-869`. |
| S5 cancel | Required and aligned with close/cancel/recovery boundary. Evidence: `post-p10.md:133-144`, `design.md:2311-2373`. |
| No mock runner as correctness proof | Covered. `post-p10.md:61-68` forbids counting mock runner / runner test double as P10.5 smoke success signal. |
| No `wait_final_answer` / payload reader | Covered. `design.md:1146-1150`, `post-p10.md:46-55`, `implementation-control.md:1221`. |
| Terminal HostEvent final answer | Covered. `design.md:905-911`, `post-p10.md:383-393`, `implementation-control.md:1235`. |

## Public Contract Ambiguity

No blocking ambiguity remains in the design/control truth for entering implementation-ready planning.

The remaining ambiguity is plan-level allocation and terminology:

- F1 requires the plan to assign owner slices and tests for S4 compact, WAITING resume, multi-client watch, and `close_session` boundary.
- F2 requires the plan to state `HostEventStream` is not a Service-facing handle contract beyond `AsyncIterator[HostEvent]`.

These do not require reopening public API decisions before planning, but they must be closed in the implementation-ready handoff plan before coding starts.

## Production Wiring Check

No remaining required production wiring was found that would force future ordinary Service to import Host internals if P10.5 implements the documented scope.

The docs explicitly require P10.5 to provide:

- `open_host(options)` public opener and handle: `design.md:849-869`, `post-p10.md:343-351`.
- Internal command -> scheduler wakeup ownership: `design.md:867`, `post-p10.md:355-361`.
- Session-level live watch and terminal final answer view: `design.md:871-911`, `post-p10.md:383-393`.
- Per-run tool selection and execution override without extra payload: `design.md:798-808`, `design.md:1086-1099`, `post-p10.md:407-417`.
- Compactor / memory catch-up public opener construction contract: `design.md:865-869`, `post-p10.md:419-433`.
- `resolve_wait(...)` resume path through public command and event stream: `design.md:2190-2203`, `post-p10.md:435-443`.

The docs also explicitly forbid Service dependency on scheduler / wakeup / dispatch control, durable internal rows, internal payload readers, `create_host_command_handle(...)`, `HostLocalRuntime`, `HostLocalExecutionOptions`, `stream_run_events(...)`, and `HostEventView`: `design.md:939-946`, `post-p10.md:48-55`.

## Residual Risks And Owners

- **P10.5 implementation-ready plan**: assign exact slice ownership for compact smoke, WAITING resume smoke, multi-client watch smoke, close/session lifecycle smoke, and deterministic mock-tool wiring proof.
- **P10.5 validation gate**: real-runner matrix may be partially skipped when provider secrets or network are unavailable. The test files and wiring must still exist, and validation must state provider-specific skip reasons.
- **Phase 11**: startup Recovery, positive orphan proof, `RECOVERING` dispatch/cancel, prompt accepted but not answered crash recovery, and active cancel watchdog / stuck `CANCELLING` hardening.
- **Phase 12**: ToolsDiscovery / ScenePrepare and concrete business tool / scene assembly outside Host.
- **Phase 13**: Outbox concrete read / drain API, OutboxSink terminal delivery queue, offline terminal delivery smoke, Audit / Tool Trace projections.
- **Phase 14**: RemoteProxy / RemoteStub.
- **Phase 15 / production hardening owner**: purge destructive cleanup, retention, production polling scale, and external job physical cancel / revoke.

## Conclusion

Conclusion: `pass-with-risks`.

Blocking findings: 0.

P10.5 can proceed to implementation-ready planning. The design and control docs are consistent on the public API direction, runtime opener, event stream, final answer path, runner/tool/compactor options, cancel/close/session lifecycle, wait/resolve, retry/replay/steer, multi-client semantics, Outbox and Recovery exclusions, and smoke intent. The next plan must close F1 / F2 as implementation planning details and must not start coding until each required smoke item has a named owner and public-path assertion.
