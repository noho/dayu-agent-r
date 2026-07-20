# P1-B Plan Review — AgentDS Adversarial Review

## 结论：pass-with-risks

P1-B plan 结构完整、证据扎实、owner boundary 清晰、slice 可执行。以下 6 个 findings 中 2 个 MEDIUM 需要在 implementation 前确认或微调 plan，4 个 LOW 记录为 deferred risk/residual。无一票否决缺陷。

---

## Review 维度覆盖

- [x] 动机是否由当前代码直接证据支撑，是否被高估
- [x] `docs/host/design.md` 是否确实需要先更新；plan 的 S0 是否足够具体
- [x] terminal helper 放置和 API 是否正确，是否会造成兼容 re-export / god helper / 反向依赖
- [x] 是否正确区分 Host terminal/lifecycle set、public outbox terminal item set、success-only helper；是否避免把 RUN_LOST 投成 public outbox item
- [x] durable cancel linkage 选择 RunRow nullable `cancel_request_event_id` 是否合理；是否需要 relation；schema strategy 是否符合 AGENTS.md
- [x] implementation slices 是否 code-generation-ready；allowed files 是否漏掉实际 consumers
- [x] validation commands 是否覆盖 schema、transition、watchdog、engine ingest、dispatch、recovery、outbox/read model/tool trace
- [x] stop conditions / propagation audit 是否足够

---

## Finding 1 (MEDIUM) — S0 design truth update 缺少目标段落

**证据**：
- Plan §3 正确指出 `docs/host/design.md` 缺少三类集合的显式区分。
- Plan §7 S0 "Required changes" 列出了 5 条需写入的设计事实，但没有指定写入 `docs/host/design.md` 的哪个段落。
- `design.md` 中与 terminal/outbox 相关的位置至少有三处：
  - §4 EventLog 不变量表（line 1537）：当前把 `RUN_SUCCEEDED / RUN_FAILED / RUN_CANCELLED / RUN_LOST` 合并一行，备注"success 触发 outbox"。
  - §4 开头（line 311-318）：Outbox 被定义为"表、投影或内部机制"。
  - §9（如存在 Outbox 专节）。

**风险**：如果 implementation 把三类集合区分插入到 design.md 的非核心位置（如仅在 EventLog 表格备注中加一句话），后续 design truth 读者可能仍然在 Outbox 设计段找不到明确语义。

**Required fix**：S0 "Required changes" 中增加一句：`明确写入位置为 §4 EventLog 不变量表或 Outbox 专节（如存在），并确保交叉引用可见。` 或在 S0 implementation artifact 中记录最终插入位置。

**违反的检查维度**：plan completeness / implementation-readiness

---

## Finding 2 (MEDIUM) — `durable/outbox.py` `_TERMINAL_EVENT_TYPES` 拆分与 `_latest_outbox_terminal_event_sequence` 的修复边界不够显式

**证据**：
- `dayu/host/durable/outbox.py:71-76` 定义 `_TERMINAL_EVENT_TYPES` 包含 `RUN_LOST`。
- `dayu/host/durable/outbox.py:752` 的 `_latest_outbox_terminal_event_sequence()` 在 SQL `IN` 子句中展开 `*_TERMINAL_EVENT_TYPES`，即包含 `RUN_LOST`。
- Plan §7 S1 "Required changes" 说 "latest public terminal sequence 必须使用 public outbox item set，不得包含 `RUN_LOST`"，但没有明确这个修复是通过：
  - (a) 拆分 `durable/outbox.py` 本地 `_TERMINAL_EVENT_TYPES` 为 public vs internal，还是
  - (b) 让 `durable/outbox.py` 直接 import `lifecycle_events.py` 的 `PUBLIC_OUTBOX_TERMINAL_EVENT_TYPES`。

**风险**：如果 implementation 选择 (a)，`durable/outbox.py` 和 `outbox.py` 的 public outbox item set 仍然是两个独立定义的 tuple。Plan 的核心目标是消除重复定义——如果 durable/outbox 和 outbox projection consumer 各自维护 public outbox item set，就违反了"单一真源"原则。

**Required fix**：S1 "Required changes" 中显式写出：`durable/outbox.py 的 _latest_outbox_terminal_event_sequence() 必须使用 lifecycle_events.PUBLIC_OUTBOX_TERMINAL_EVENT_TYPES 的字符串值形式或 event_type_values() helper，不得在 durable/outbox.py 中保留本地 public outbox item set 定义。`

**违反的检查维度**：semantic ownership — 同一事实不应在两个模块各自定义

---

## Finding 3 (LOW) — `read_api.py` 非 terminal 生命周期事件类型常量未纳入迁移范围

**证据**：
- `dayu/host/read_api.py:98-109` 定义了 `RUN_ACCEPTED`、`RUN_QUEUED`、`RUN_STARTED`、`RUN_RECOVERING`、`TOOL_CALL_REQUESTED` 等事件类型常量。
- Plan 的 `HostRunEventType(StrEnum)` 提议包含全部 Run 生命周期事件类型（`RUN_ACCEPTED`、`RUN_QUEUED`、`RUN_STARTED` 等）。
- Plan S1 只要求迁移 terminal 相关常量（`RUN_SUCCEEDED` / `RUN_FAILED` / `RUN_CANCELLED` / `RUN_LOST`），不要求迁移非 terminal 常量。

**风险**：如果 `HostRunEventType` 成为全面的事件类型枚举，`read_api.py` 会出现部分事件类型来自 helper、部分来自本地常量的不一致状态。这不是功能 bug，但增加了后续维护者理解"哪个常量从哪里来"的认知负担。

**Required fix**：在 plan §11 Residual risks 中增加一条：`非 terminal 生命周期事件类型常量（read_api.py 的 RUN_ACCEPTED/RUN_QUEUED/RUN_STARTED 等）不在 P1-B 迁移范围。若 HostRunEventType 成为全面枚举，后续 WU 应统一迁移剩余消费者。`

**违反的检查维度**：consistency / deferred cleanup

---

## Finding 4 (LOW) — `_cancel_request_event_id_from_cancelling()` 删除后需同步清理 `event_payload_object(..., RUN_CANCELLING)` 调用

**证据**：
- `dayu/host/dispatch.py:4144-4148` 和 `dayu/host/recovery.py:677-681` 在调用 `payload.get("cancel_request_event_id")` 之前，先调用 `event_payload_object(transaction, cancelling, payload_label=_EVENT_TYPE_RUN_CANCELLING)` 反序列化 payload。
- Plan §7 S2 validation 的 regex 扫描覆盖了 `_cancel_request_event_id_from_cancelling` 和 `payload.get("cancel_request_event_id")`，但没有显式扫描 `event_payload_object(.*RUN_CANCELLING)` 残余调用。

**风险**：如果 S2 删除了 `_cancel_request_event_id_from_cancelling()` 和 `payload.get("cancel_request_event_id")` 但遗留了 `event_payload_object(transaction, cancelling, payload_label=_EVENT_TYPE_RUN_CANCELLING)` 调用（该调用不再被后续代码消费），会产生死代码。这不会造成功能错误，但会让后续维护者困惑：为什么还在反序列化 RUN_CANCELLING payload？

**Required fix**：S2 validation 命令中的 regex 扫描增加一行：`rg -n "event_payload_object\(.*RUN_CANCELLING" dayu/host` 确认只在降级后的 diagnostic/audit 路径中存在（如有），不在 critical closeout 路径中。

**违反的检查维度**：validation completeness

---

## Finding 5 (LOW) — success-only 消费者（memory.py, compact_material.py, run_input.py）的 `RUN_SUCCEEDED` 常量被有意排除

**证据**：
- `dayu/host/memory.py:70` — `_EVENT_TYPE_RUN_SUCCEEDED = "RUN_SUCCEEDED"`
- `dayu/host/compact_material.py:107` — `_EVENT_TYPE_RUN_SUCCEEDED = "RUN_SUCCEEDED"`
- `dayu/host/run_input.py:164` — `_EVENT_TYPE_RUN_SUCCEEDED = "RUN_SUCCEEDED"`
- Plan §11 Residual risks 明确说 "Some `RUN_SUCCEEDED`-only helpers ... intentionally remain success-specific and should not be forced through a broad terminal helper."

**评估**：这些模块使用 `RUN_SUCCEEDED` 是为了从 payload 中提取 final answer 文本，不涉及 terminal set 语义（不判断 "is this a terminal event?"，只判断 "is this the specific event type I need to extract content from?"）。Plan 的 exclusion 合理。

**Residual risk**：如果 `HostRunEventType` 在后续 WU 中成为所有 Run event type 字符串的唯一真源，这三个模块的本地字符串常量也应迁移。当前 exclusion 是 scope 决策，不是设计缺陷。

**违反的检查维度**：n/a — 已记录为 accepted residual risk

---

## Finding 6 (INFO) — Plan 整体质量评估

**证据汇总**：

| 维度 | 评估 | 证据 |
|------|------|------|
| 动机成立 | ✓ | 7+ 模块重复 terminal strings；3 critical paths + 1 auxiliary path 从 payload JSON 解析 cancel link；RunRow 无 typed cancel column |
| design.md 需更新 | ✓ | Line 1537 将 RUN_LOST 与其它 terminal 合并为一行；未区分三类集合 |
| S0 具体性 | △ | 缺少目标段落指定（见 Finding 1） |
| terminal helper API | ✓ | 无反向依赖；不依赖 projection/outbox/engine ingest/dispatch；函数签名清晰 |
| RUN_LOST 区分 | ✓ | 三类集合区分正确；RUN_LOST 是 Host terminal fact 但不是 public outbox item |
| cancel linkage 选型 | ✓ | RunRow nullable TEXT FK 符合当前单 cancel 语义；列比 relation 简单且满足需求 |
| schema strategy | ✓ | 全新起库，不做兼容迁移，对齐 umbrella plan |
| slices code-generation-ready | ✓ | 每个 slice 有 Objective、Allowed files、Required changes、Expected tests、Validation、Stop condition |
| allowed files 完整性 | ✓ | 覆盖 outbox、durable/outbox、read_model、tool_trace、read_api、engine_ingest、dispatch、recovery、admission、schema、state、run_transition；success-only 消费者有意排除 |
| validation 覆盖 | △ | 缺少 `event_payload_object(.*RUN_CANCELLING)` 扫描（见 Finding 4） |
| stop conditions | ✓ | 5 个具体条件，每个有明确裁决路径 |
| propagation audit | ✓ | §12 覆盖 terminal event/status 和 cancel linkage 的 5-6 层传播路径 |

**整体判断**：Plan 是一份高质量、可执行的设计文档。Findings 1 和 2 需要在 implementation 前微调，但不影响 plan 的总体结构或可行性。Findings 3-5 为 deferred/low-risk 项。

---

## 验证

本轮按任务要求只运行：

```bash
git diff --check
```

（plan review artifact 是新文件，不在 git tracked 范围内。）

---

## Residual risks（AgentDS 加注）

1. **`HostRunEventType(StrEnum)` 与现有 `RunStatus` / `HostTerminalStatus` 的关系**：plan 说 helper 可以依赖 `dayu.host.api` 的状态类型。当前 `RunStatus` 和 `HostTerminalStatus` 是枚举；`HostRunEventType` 会成为第三个枚举。三者之间的映射关系由 helper 函数承载，不会产生循环依赖。但 reviewer 应注意：如果未来有人把 `HostRunEventType` 当成 `RunStatus` 使用（或反之），会造成语义混淆。Plan 的 API 设计（`run_status_for_terminal_event()` 显式映射）已经防御了这个问题。

2. **`cancel_request_event_id` 外键引用 `event_log(event_id)` 但 `event_log` 表没有 event_id 单列唯一约束以外的特殊索引**：如果未来 cancel linkage 查询成为热点（不太可能），可能需要额外索引。当前 plan 不做过度设计是正确的。

3. **`RUN_LOST` 不产生 public outbox item 的决策**：这是 controller 已裁决的设计。Plan 正确执行了这个裁决。但如果未来有消费者依赖 "每个 terminal Run 都有 Outbox item" 的假设，需要迁移该消费者，不在 P1-B scope 内。

4. **`event_payload_object()` 在 `RUN_CANCELLING` 上的调用残留**：见 Finding 4。

---

## 审查人

AgentDS, 2026-07-09

## 审查输入

- Plan: `docs/host/wu-semantic-ownership-01-p1-b-plan.md`
- Delivery: `docs/reviews/wu-semantic-ownership-01-p1-b-plan-codex.md`
- Umbrella plan: `docs/host/wu-semantic-ownership-01-umbrella-plan.md`
- Design truth: `docs/host/design.md`
- Code: `dayu/host/` and `tests/host/` as cited in findings
