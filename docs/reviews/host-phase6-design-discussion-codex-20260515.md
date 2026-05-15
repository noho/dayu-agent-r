# Host Phase 6 Design Discussion Input - Codex - 2026-05-15

## 结论

Phase 6 当前不满足进入 handoff implementation-ready plan 的条件。

动机成立：Phase 6 要落地 Host-owned ToolRuntime、ToolBundle snapshot、Host accept barrier、TruncationManager、`fetch_more` 与同 Run 语义级重复工具调用治理；这些能力是 Phase 5 no-tool / fake-tool 本地执行闭环后的必要下一步。严重性没有被高估：总控文档明确把 Phase 6 进入条件定义为 ToolRuntime ports、accept idempotency key、effective ToolBundle 与 truncation descriptor 的最小 typed contract 已确认，且关键设计问题必须确认后才能继续。

但设计真源目前更多是语义边界和约束，尚未把若干会影响 typed contract、状态机和持久化语义的点收敛到可直接生成 contract / test matrix 的程度。下一步应先由 controller 收敛 blocking questions，并把决策写回 `docs/host/design.md`，再进入 Phase 6 handoff plan。

## 直接证据

- `docs/host/implementation-control.md:643-644`：Phase 6 进入条件是确认 ToolRuntime ports、accept idempotency key、effective ToolBundle 与 truncation descriptor 的最小 typed contract；确认形式为用户确认或设计章节已细化到可直接生成 typed contract / test matrix。
- `docs/host/implementation-control.md:655-658`：Phase 6 关键设计问题包括 accepted ack 失败 / timeout 默认治理动作、truncation cursor / `scope_token` durable descriptor 的存储位置与恢复输入、replay no-tool 双层防线。
- `docs/host/design.md:1829-1840`：ToolRuntime 最小 port 只列出职责边界，尚未定义每个 port 的 typed request / response、错误 envelope、同步/异步调用形态和测试切面。
- `docs/host/design.md:1759-1764` 与 `docs/host/design.md:1867`：ack timeout 后不得让 LLM 消费未确认结果，但默认动作仍是“重试，或按 Host policy 进入 governed tool error / awaiting / Attempt failed / recoverable”，未收敛为 Phase 6 第一版行为。
- `docs/host/design.md:1871-1877`：tool fact candidate 必须携带 truncation descriptor、外部副作用 idempotency key、policy decision、diagnostic refs、accept idempotency key，但未固定 typed candidate / accepted ack 结构。
- `docs/host/design.md:1951-1952` 与 `docs/host/design.md:1973-1978`：cursor / `scope_token` 必须可通过 durable descriptor 恢复，descriptor 保存 handle metadata、scope binding、artifact ref、digest、offset / page / path、expiry / retention policy 和 access policy；但具体存储 owner、descriptor id、EventLog / payload descriptor / attempt snapshot 的引用关系未定。
- `docs/host/design.md:1806`：`fetch_more` 由 ToolRuntime factory 注入 effective `ToolBundle`，RunInputBuilder schema 与 ToolRuntime callable 必须来自同一个 effective `ToolBundle`；但 attempt-local effective snapshot 的字段、digest 口径和注入失败语义未固定。
- `docs/host/design.md:2130-2133`：replay no-tool 双层防线已经明确：RunInputBuilder 不暴露 tool schemas 是主防线，ToolRuntime replay policy 拒绝是 defense-in-depth，默认 hard stop 或 governed tool error。
- `docs/host/implementation-control.md:1268`、`docs/host/implementation-control.md:1365-1366`、`docs/host/implementation-control.md:1397`：Phase 6 必须明确外部副作用 / 付费 / 长耗时工具的 idempotency key、side-effect policy、可取消能力和测试。
- `docs/host/implementation-control.md:1789-1796`：P1-P5 corrected review 未发现 blocking design deviation，但剩余风险明确把 ToolRuntime / `fetch_more` 交给 Phase 6，WAITING / `resolve_wait` 交给 Phase 7，orphan recovery 交给 Phase 11，RemoteProxy 交给 Phase 14，Memory / Context Governance / compact artifact 交给 Phase 9 / Phase 10。

## Phase 6 Success Signal 对齐

已对齐的 success signal：

- Engine 只能通过 Host-governed `ToolExecutor` 使用工具，方向已由 `docs/host/design.md:1846-1852` 固定。
- 工具事实必须通过 Host accept barrier durable accepted 后才能返回给 Engine，方向已由 `docs/host/design.md:1854-1864` 固定。
- `fetch_more` 必须是普通 framework tool，不允许 Host / Engine 特化分支，方向已由 `docs/host/design.md:1954-1972` 固定。
- 重复工具调用治理只做同 Run、run-local deterministic duplicate key，不做跨 Run / 跨 Session memory retrieval，边界已由 `docs/host/design.md:1892-1925` 固定。
- replay no-tool 双层防线已经足够进入测试矩阵输入，见 `docs/host/design.md:2130-2133`。

未对齐到 implementation-ready 的 success signal：

- ToolRuntime ports 只有职责名，没有 typed protocol 形状。
- accept idempotency key 有派生输入原则，但没有 scope_kind / scope_id / semantic digest / result ref 的 Phase 6 具体映射，也没有 accepted ack typed shape。
- effective `ToolBundle` 有语义链路，但没有 attempt-local snapshot fields、digest 口径、framework injection 决策记录和 schema/callable 同源校验 contract。
- truncation descriptor 有必须保存的内容，但没有存储位置、descriptor id、恢复输入和失败 envelope 的 durable contract。
- ack timeout / rejected 的默认治理动作未收敛，implementation agent 会被迫选择状态机行为。

## Design Sufficiency 判定

判定：不足。

当前 design 足以证明 Phase 6 的职责边界、非目标和若干硬约束，但不足以让 planning / implementation agent 不重新设计 contract。若现在进入 handoff plan，计划必须在以下领域自行发明 typed contract 或状态机语义：Host accept ack、effective ToolBundle snapshot、truncation descriptor persistence、ToolRuntime port protocols、side-effect policy。按 Gateflow 标准，这些属于 blocking open questions，不应转嫁给 implementation。

## Blocking Questions For Controller

### BQ1 - accepted ack timeout / rejected 的 Phase 6 默认治理动作是什么？

- **直接证据**：`docs/host/implementation-control.md:655-656` 要求必须确认；`docs/host/design.md:1763-1764` 和 `docs/host/design.md:1867` 只给出候选动作，没有收敛默认策略。
- **为什么阻塞**：这会决定 ToolRuntime 在 ack timeout 后返回什么、是否关闭 Attempt、是否生成 governed tool error、是否允许 retry，以及测试如何断言 LLM 不消费未确认结果。
- **建议裁决选项**：
  - A：Phase 6 第一版采用 bounded accept retry；仍未确认时返回 governed tool error，不进入 `WAITING`，不自动 recovery。适合把 wait / recovery 留给 Phase 7 / Phase 11。
  - B：Phase 6 允许 ack timeout 触发 Attempt failed / recoverable。需要明确 Run / Attempt 终态与 recovery owner，容易夹带 Phase 11。
  - C：Phase 6 允许进入 awaiting / suspend。该选项会夹带 Phase 7，不建议作为 Phase 6 默认。
- **建议**：选 A，并写明 ack rejected 为结构化拒绝，ack timeout 为未确认，二者都不得向 Engine 返回原始工具结果。

### BQ2 - tool fact accept idempotency 的 Phase 6 typed mapping 是什么？

- **直接证据**：`docs/host/design.md:1760-1762` 定义稳定 key 的派生输入；`docs/host/design.md:1244-1247` 定义通用幂等 primitive；`docs/host/design.md:1871-1877` 列出 candidate 必备信息，但没有把 tool accept path 映射到具体 scope / digest / result ref。
- **为什么阻塞**：没有该映射，就无法写出 accept path 的 typed contract、冲突测试和 ack retry 测试。
- **建议裁决选项**：
  - A：`scope_kind=tool_fact_accept`，`scope_id=attempt_id + tool_call_id`，`idempotency_key` 由 attempt identity、tool call identity、tool fact kind、result / awaiting digest 确定性派生；`semantic_input_digest` 覆盖 normalized args、payload digest、policy decision、truncation descriptor digest。
  - B：`scope_id=run_id`，key 内包含 attempt / tool call / fact kind。实现简单但 scope 更宽，冲突诊断不如 A 精确。
  - C：按 event type 分多个 scope_kind。可解释性高，但 Phase 6 第一版 contract 更分散。
- **建议**：选 A，并同步定义 `accepted_ack` 至少包含 accepted event refs、tool fact id、result ref、duplicate/reuse refs 和 diagnostic refs。

### BQ3 - effective ToolBundle / ToolRuntime snapshot 的最小 typed contract 是什么？

- **直接证据**：`docs/host/design.md:1774-1787` 和 `docs/host/design.md:1806` 定义 construction business bundle 到 effective bundle 的语义链路；`docs/host/design.md:742-781` 定义 Phase 1 construction-time tooling options；但 Phase 6 未定义 attempt-local effective snapshot 的字段。
- **为什么阻塞**：RunInputBuilder 和 ToolRuntime 必须验证 tool schemas 与 callable binding 同源；没有 snapshot 字段和 digest 口径，测试只能断言行为，不能断言治理真源。
- **建议裁决选项**：
  - A：Phase 6 固化 `ToolRuntimeSnapshot` / `EffectiveToolBundleSnapshot`，包含 business bundle digest、schema digest、source refs、enabled framework tools、injected framework tool names、effective schema digest、attempt id、policy snapshot refs。
  - B：只在 Attempt snapshot 中记录 business bundle refs，effective bundle 运行时派生不持久化。实现较轻，但 `fetch_more` 注入和 replay/resume 解释性弱。
- **建议**：选 A，但只记录 digest / refs / names，不持久化 callable，不引入 ToolsDiscovery 或多 profile registry。

### BQ4 - truncation cursor / scope_token durable descriptor 存在哪里，如何恢复？

- **直接证据**：`docs/host/implementation-control.md:657` 要求必须确认；`docs/host/design.md:1951-1952` 和 `docs/host/design.md:1973-1978` 要求 descriptor 可恢复且不依赖远端内存，但没有确定存储 owner。
- **为什么阻塞**：这会影响 schema / payload descriptor / EventLog payload 关系，属于持久化语义，不应由 plan 或 implementation agent 选择。
- **建议裁决选项**：
  - A：descriptor 作为 tool result accepted payload 的结构化子 descriptor，随 EventLog canonical fact 通过 SQLite payload / artifact descriptor 持久化；`fetch_more` 用 descriptor id + scope_token digest 恢复。
  - B：新增专用 cursor descriptor table。查询直接，但会扩大 schema。
  - C：只放 artifact ref，不建结构化 descriptor。实现轻，但 scope 校验、TTL 和 digest mismatch 测试困难。
- **建议**：选 A，除非已有 schema 查询需求证明必须建专表；Phase 6 不做完整 retention cleanup，把 TTL / retention policy 作为 descriptor 字段和校验输入。

### BQ5 - Phase 6 如何处理 Tool Awaiting port，避免夹带 Phase 7？

- **直接证据**：`docs/host/design.md:1755` 明确 Phase 6 / Phase 7 分别拥有 ToolRuntime governance 与 Tool Awaiting / `resolve_wait`；但 `docs/host/design.md:1835` 又把 awaiting / wait outcome port 放入 ToolRuntime 最小 port，`docs/host/design.md:1988-2003` 定义 awaiting accept path。
- **为什么阻塞**：如果 Phase 6 实现 awaiting accept，会创建 wait record、更新 Run 为 `WAITING`、关闭 Attempt，这属于 Phase 7 状态机；如果完全不定义 port，又可能破坏 ToolRuntime port 完整性。
- **建议裁决选项**：
  - A：Phase 6 只定义 awaiting outcome port 的 typed placeholder / rejected unsupported policy，不创建 wait record，不进入 `WAITING`；Phase 7 接管实现。
  - B：Phase 6 实现 awaiting candidate accept，但不实现 `resolve_wait`。这会留下半状态机，不建议。
- **建议**：选 A，并在 design.md 写明 Phase 6 tests 不期待 `WAITING`。

### BQ6 - 外部副作用 / 付费 / 长耗时工具的第一版 side-effect policy 边界是什么？

- **直接证据**：`docs/host/implementation-control.md:1268`、`docs/host/implementation-control.md:1365-1366`、`docs/host/implementation-control.md:1397` 都把 side-effect policy、工具级 idempotency key、可取消能力交给 Phase 6；`docs/host/design.md:1875` 和 `docs/host/design.md:1925` 只说明需要工具级 idempotency key，未定义缺失时的执行策略。
- **为什么阻塞**：没有默认策略，Phase 6 无法决定缺少 idempotency key 的付费/写入工具是拒绝、允许、要求确认还是降级诊断。
- **建议裁决选项**：
  - A：Phase 6 第一版只支持 read-only 或声明 idempotency key 的 side-effect tool；缺少 required idempotency 的工具调用走 governed rejection。
  - B：允许执行但记录 diagnostic warning。风险较高，不符合 Host 强治理。
  - C：要求人工确认 / waiting。会夹带 Phase 7 或 UI/Service 行为。
- **建议**：选 A，并把 job id / cancel handle 作为可选 diagnostic / adapter metadata，不承诺 Host exactly-once 或外部 job cancel。

## Non-blocking Assumptions

- Replay no-tool 双层防线可作为已收敛输入：RunInputBuilder 不暴露 tool schemas 是主防线，ToolRuntime replay policy 拒绝是 defense-in-depth；Phase 6 只需在测试矩阵覆盖模型仍发起 tool call 时 hard stop 或 governed tool error。
- 语义级重复工具调用治理的范围已足够：只做同 Run、run-local deterministic duplicate key；跨 Run / Session retrieval 属于 Phase 9 Memory / retrieval，不进入 Phase 6。
- RemoteProxy 等价 tool fact accept ack 属于 Phase 14；Phase 6 只固定语义和 LocalProxy 函数调用等价点，不设计 wire protocol。
- Tool trace projection、hot JSON / cold JSONL、Outbox / Audit 属于 Phase 13；Phase 6 只需要最小 `ToolTraceDiagnosticEmitter` interface 与 diagnostic refs，不写投影。
- ToolsDiscovery / ScenePrepare 属于 Phase 12；Phase 6 不新增业务工具扫描、provider registry、manifest schema 或 scene prompt assembly。
- Host lifecycle restart / orphan recovery 属于 Phase 11；Phase 6 只确保 descriptor / accepted facts 具备可恢复信息，不实现完整 startup recovery。

## 建议写回项

必须写回 `docs/host/design.md` 的设计点：

- Phase 6 ack rejected / timeout 默认治理动作，明确不进入 Phase 7 `WAITING`，不让 LLM 消费未确认工具结果。
- Tool fact accept candidate / accepted ack 的最小 typed fields，包括 idempotency scope、semantic digest、accepted event refs、result refs、duplicate/reuse refs、diagnostic refs。
- `ToolRuntimeSnapshot` / effective `ToolBundle` snapshot 的最小字段和 digest 口径，明确 schema projection 与 callable binding 同源。
- truncation durable descriptor 的存储 owner、descriptor id、EventLog / payload descriptor 引用方式、恢复输入和错误 envelope。
- Phase 6 对 awaiting / wait outcome port 的 non-goal 写法，避免实现 wait record / `resolve_wait`。
- 外部 side-effect / paid / long-running tool 的第一版 policy：缺少工具级 idempotency key 时的默认拒绝或允许策略。

可写入 Phase 6 handoff plan 而不必扩展 design.md 的点：

- slice 内 file ownership、具体类名、模块内 helper 分解。
- test matrix 的具体文件名、fixture 名、fake tool 名称。
- `ToolTraceDiagnosticEmitter` 第一版 no-op / in-memory fake 测试实现细节。

## Plan Gate Readiness

当前 readiness：not ready。

进入 handoff plan 前的最小 contract checklist：

- ToolRuntime port protocols：schema projection、dispatcher、policy decision、truncation / fetch_more、duplicate governance、Host accept、diagnostic emitter；每个 port 有 typed input / output / error shape。
- Accept barrier：tool fact candidate、accept idempotency mapping、accepted ack、rejected ack、timeout retry / governed error policy。
- Effective ToolBundle：business bundle validation、framework tool injection、reserved name conflict、effective schema digest、attempt-local snapshot refs、RunInputBuilder / ToolRuntime 同源校验。
- Truncation descriptor：cursor、scope_token、descriptor id、artifact / payload ref、digest、offset/page/path、expiry / access policy、scope mismatch / expired / digest mismatch error。
- Duplicate governance：duplicate key、policy actions、prior accepted refs、`reuse` 不伪造新事实、hard_stop 终止语义。
- Replay no-tool：RunInputBuilder no schema + ToolRuntime rejection 的测试断言。
- Phase boundary guards：Phase 7 wait、Phase 11 recovery、Phase 12 discovery、Phase 13 projection、Phase 14 remote transport 均不进入 Phase 6。

建议测试矩阵输入：

- Unit：business `ToolBundle` reserved `fetch_more` 冲突、effective bundle 注入 `fetch_more`、schema/callable digest 同源、disabled truncation 不注入。
- Unit：accept idempotency same key same digest returns existing ack；same key different digest returns conflict；ack rejected 不返回原始 tool result；ack timeout bounded retry 后 governed tool error。
- Unit：truncation descriptor cursor/scope binding 正常续读、scope mismatch、expired/revoked、artifact digest mismatch、descriptor missing。
- Unit：duplicate policy `allow` / `reuse` / `hint` / `require_justification` / `hard_stop`，`reuse` 引用 prior accepted event 而不追加新 tool result fact。
- Integration：fake business tool 经 Engine -> ToolExecutor -> ToolRuntime -> Host accept barrier -> Engine continuation。
- Integration：`fetch_more` 作为普通 tool call 经过同一 ToolExecutor / accept barrier，不走 Host / Engine 特化分支。
- Integration：replay Attempt 不暴露 tool schemas；若模型仍发 tool call，ToolRuntime 按 replay policy 拒绝并记录 diagnostic。
- Boundary：awaiting / wait outcome 在 Phase 6 为 unsupported / deferred，不创建 wait record、不进入 `WAITING`。

## 风险与 Owner

- Phase 6 owner：ToolRuntime typed contracts、effective ToolBundle snapshot、Host accept barrier、truncation descriptor、`fetch_more` 普通工具路径、run-local duplicate governance、side-effect policy 第一版。
- Phase 7 owner：Tool Awaiting、wait record、`resolve_wait`、`WAITING` cancel / resume、外部 wait adapter 结果接收。
- Phase 11 owner：Host lifecycle / recovery / orphan proof / stuck cancelling / startup recovery；Phase 6 只提供可恢复 descriptor 和 accepted facts。
- Phase 12 owner：ToolsDiscovery / ScenePrepare provider、manifest、业务工具扫描与 scene input assembly。
- Phase 13 owner：Audit / Tool Trace / Outbox projection、hot JSON / cold JSONL、provider request 排错查询。
- Phase 14 owner：RemoteProxy / RemoteStub transport、remote ack wire contract、迟到 remote tool fact / terminal event 处理。

## Controller 下一步建议

先裁决 BQ1-BQ6，并把 accepted decision 写回 `docs/host/design.md` 的 §18 / §19 及相关 Tool fact accept ack 语义段落。写回后再进入 Phase 6 handoff implementation-ready plan；计划应只实现 Phase 6 owner 项，不能夹带 wait record、Remote wire protocol、ToolsDiscovery、tool trace projection或 lifecycle recovery。
