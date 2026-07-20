# WU-SEMANTIC-OWNERSHIP-01 P1-B Plan Review (AgentMiMo)

- Date: 2026-07-09
- Reviewer: AgentMiMo
- Plan: `docs/host/wu-semantic-ownership-01-p1-b-plan.md`
- Delivery: `docs/reviews/wu-semantic-ownership-01-p1-b-plan-codex.md`
- Umbrella: `docs/host/wu-semantic-ownership-01-umbrella-plan.md`

## Conclusion

**pass-with-risks**

Plan 动机成立，直接证据充分，架构方向正确。但存在 3 个 medium findings 和 2 个 low findings 需要在 implementation 前确认或修正。

## Findings

### F1. S0 Design Truth Update 缺少具体内容结构 (medium)

**证据**: Plan S0 (lines 176-198) 只描述了"在 EventLog / Outbox 设计处明确"三类集合的区分，但没有给出具体的新增段落结构、与现有 design.md 段落的对应关系、以及新增内容的最小可验证形式。

**违反的 owner boundary**: S0 作为 design truth update slice，必须产出可验证的 design 变更；当前描述只有 "Required changes" 的意图，没有具体到 design.md 哪个段落后新增什么结构。

**风险**: Implementation agent 可能自由发挥 design 更新的结构和措辞，导致 design truth 变更与 plan 意图不一致，或遗漏关键边界说明。

**Required fix**: S0 的 Required changes 应至少指定：
1. 新增段落位于 design.md 的哪个现有段落之后（例如 "EventLog / Outbox" 或 "Run terminal canonical facts" 段落之后）。
2. 新增内容的最小结构：至少包含三个 bullet points 分别定义 Host terminal event set、public outbox terminal item set、non-public terminal fact skip/diagnostic behavior。
3. 明确 `RUN_LOST` 在 Read Model / Read API / HostEvent 中的投影行为（是 `lost` terminal），与 Outbox 的 skip 行为形成对比。

### F2. terminal helper 函数签名使用 `str` 而非 `HostRunEventType` (medium)

**证据**: Plan S1 (lines 116-120) 定义的函数签名：
```python
run_status_for_terminal_event(event_type: str) -> RunStatus | None
host_terminal_status_for_terminal_event(event_type: str) -> HostTerminalStatus | None
is_host_run_terminal_event(event_type: str) -> bool
is_public_outbox_terminal_item_event(event_type: str) -> bool
```

所有函数参数类型为 `str`，但 plan 同时定义了 `HostRunEventType(StrEnum)`。

**违反的编码约束**: CLAUDE.md 要求"禁止使用 `object`、`Any`、无类型参数、无类型返回值"。虽然 `str` 不是无类型，但使用 `str` 而非 `HostRunEventType` 会让调用方可以传入任意字符串，失去类型检查保护。

**风险**: 调用方可能传入非法 event type string，运行时才返回 None；不如在类型层面就约束。

**Required fix**: 有两个合理选择，plan 应明确选择其中一个：
1. **选项 A (推荐)**: 参数类型保持 `str`，因为当前 consumers（outbox、read_model 等）的 event_type 来自 EventLog row，是 `str` 类型；强转 `HostRunEventType` 需要额外的 parse/validate 逻辑。但应在 docstring 中说明接受 `HostRunEventType` 或合法 event type string。
2. **选项 B**: 参数类型改为 `HostRunEventType`，调用方在调用前做 parse；这会增加调用方负担但提供更强的类型安全。

Plan 应明确选择并说明理由。当前 plan 没有讨论这个 trade-off。

### F3. `_latest_outbox_terminal_event_sequence` 修复未在 S1 Validation 中明确覆盖 (medium)

**证据**: `dayu/host/durable/outbox.py:737-759` 的 `_latest_outbox_terminal_event_sequence()` 使用包含 `RUN_LOST` 的 `_TERMINAL_EVENT_TYPES` 查询最新 terminal sequence。当 `RUN_LOST` event 存在时，`read_outbox_terminal_projection_state()` 会返回 `LAGGED` 状态，但 outbox consumer 实际 skip 了 `RUN_LOST`，不会创建 item。这会导致 "checkpoint < latest_terminal" 的假滞后。

Plan S1 (line 219) 提到 "durable/outbox.py latest public terminal sequence 必须使用 public outbox item set，不得包含 `RUN_LOST`"，但 S1 Validation commands (lines 233-238) 只列出了 projection read model / public host event / context compact / tool trace / engine ingest 的测试，没有明确包含 `test_outbox*.py` 或验证 `_latest_outbox_terminal_event_sequence` 行为的测试。

**风险**: Implementation agent 可能只修改 outbox.py 的 `_TERMINAL_EVENT_TYPES` 但忘记修改 `durable/outbox.py` 的 `_latest_outbox_terminal_event_sequence`，或修改了但没有对应的测试验证。

**Required fix**: S1 Validation commands 应增加：
```bash
source .venv/bin/activate && pytest tests/host/test_outbox*.py tests/host/test_durable_outbox*.py
```
或等价的 outbox/durable-outbox 测试命令。同时 S1 Expected tests 应明确包含 "latest public terminal sequence 不被 `RUN_LOST` 推进" 的测试场景。

### F4. S2 Allowed Files 遗漏 `dayu/host/admission.py` 的 terminal event strings (low)

**证据**: `dayu/host/admission.py` 使用 `cancel_request_event_id` 作为 id factory output（创建 event id），但不使用 terminal event type strings（`RUN_SUCCEEDED` 等）。Plan S2 allowed files (line 253) 已包含 `admission.py`，这是正确的。

但 `dayu/host/_terminal_answer.py`、`dayu/host/compact_material.py`、`dayu/host/durable/memory.py`、`dayu/host/memory.py`、`dayu/host/run_input.py`、`dayu/host/terminal_payload.py` 这些文件只使用 `RUN_SUCCEEDED`（success-only 消费者），不在 S1 allowed files 中。Plan residual risks (line 380) 已说明 "Some `RUN_SUCCEEDED`-only helpers...intentionally remain success-specific"，这是正确的判断。

**结论**: 此 finding 实际上是正面确认——Plan 正确识别了 success-only consumers 不应被强制迁移为 generic terminal helper。无需修改 plan。

### F5. S2 stop condition 缺少 "typed link 非空约束在 direct cancel 路径失败" 场景 (low)

**证据**: Plan S2 (lines 270-274) Expected tests 包含 "direct queued / accepted / waiting / pre-worker cancel terminal rows 均写入 typed link"，但 stop condition (line 288) 只提到 "发现现有 workspace 必须迁移历史 `RUN_CANCELLING` payload 才能继续运行" 和 "发现同一 Run 需要多条 accepted cancel request history"。

**风险**: 若 implementation 发现 direct cancel 路径（queued/accepted/waiting/pre-worker）在某些 edge case 无法写入 typed link（例如 Run row 不存在或状态不对），plan 没有明确的 stop condition。

**Required fix**: S2 stop condition 增加一条："发现 direct cancel 路径在某些 Run 状态下无法安全写入 `cancel_request_event_id`（例如 Run row 不存在、状态已 terminal），且不能通过调整 transition 顺序解决。"

## Positive Confirmations

1. **动机成立**: 直接证据显示 terminal event type strings 在 11+ production modules 重复，`cancel_request_event_id` 只存在于 `RUN_CANCELLING` payload JSON，确实需要收敛。

2. **三类集合区分正确**: Plan 正确区分 Host terminal/lifecycle event set（含 `RUN_LOST`）、public outbox terminal item set（不含 `RUN_LOST`）、non-public terminal fact skip/diagnostic behavior。这与 `outbox.py:166-171` 的 skip 逻辑和 `durable/outbox.py:737-759` 的 latest terminal sequence 问题一致。

3. **cancel linkage 选择合理**: 选择 nullable 列而非 relation 表，因为当前状态机只有一个 accepted cancel request。Stop condition 正确设置了 "若发现需要多条 accepted cancel request history 则停止"。

4. **S1 helper 模块放置正确**: `dayu/host/lifecycle_events.py` 作为 Host-owned lifecycle event helper 是正确的位置，不是兼容 re-export，不从 projection 层反向抽取。

5. **implementation slices 边界清晰**: S0 (design truth) → S1 (terminal helper) → S2 (cancel linkage) → S3 (doc/audit) 的顺序合理，依赖关系正确。

6. **propagation audit plan 完整**: Plan section 12 的 terminal event/status propagation 和 cancel linkage propagation 覆盖了从 producer → durable → projection → user/LLM-visible output 的完整链路。

## Residual Risks (Plan 已声明)

1. 若 controller 要求兼容既有 workspace DB，则"全新 schema 起库"方案需重新裁决。
2. `RUN_SUCCEEDED`-only helpers 不应被机械迁移为 generic terminal helper。
3. Public outbox read API 的 item-query watermark 和 EventLog latest-terminal logic 都需审计。

## Summary

Plan 整体质量良好，可以直接进入 implementation，但建议在开始前：
1. 补充 S0 的具体 design 更新结构。
2. 明确 terminal helper 函数签名的 `str` vs `HostRunEventType` 选择。
3. 补充 S1 validation 的 outbox 测试命令。
4. 补充 S2 stop condition 的 direct cancel 路径 edge case。
