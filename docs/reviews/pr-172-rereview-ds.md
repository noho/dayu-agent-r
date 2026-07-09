# PR Re-Review — Draft PR #172 Fix Gate

## Gate

- **Review type**: adversarial fix re-review (AgentDS)
- **Date**: 2026-07-06
- **PR**: https://github.com/noho/dayu-agent-r/pull/172
- **Branch**: `phase/host-issues-control` → `main`
- **Work unit**: WU-CLI-SMOKE-01
- **Previous DS artifact**: `docs/reviews/pr-172-review-ds.md`
- **Fix artifact under review**: `docs/reviews/pr-172-review-fix-codex.md`
- **Controller adjudication**: fix DS-F01 and DS-F02 now; defer DS-F03.

## Scope

Re-review only the controller-accepted fix gate diff against the four changed files and the previous DS review artifact:

- `docs/host/design.md`（DS-F01：映射表更新）
- `tests/host/test_host_activity_event_projection.py`（DS-F02：防卫性测试）
- `docs/host/issues-implementation-control.md`（状态/next entry point 更新）
- `docs/reviews/pr-172-review-fix-codex.md`（fix evidence artifact）

No code changes beyond the fix gate diff were reviewed. DS-F03 remains deferred by controller decision.

## Findings

### DS-F01 复核：已修复 ✅

- **原 finding**：设计真源 `docs/host/design.md` 第 1602 行 `reasoning_delta -> accepted non-durable delta; no EventLog row by default` 与实现（REASONING_DELTA 写入 PREVIEW row）矛盾。
- **修复内容**（git diff 直接证据）：
  - 第 1593 行：解释性文本从"非 delta 的 UI / progress 事件可以映射为 preview event"更新为"当前 transient delta 子集是 `content_delta` 与 `tool_call_delta`。`reasoning_delta` 因 live thinking 展示需要写入 `PREVIEW` row，但仅供运行态 Host event stream 投影，不成为 memory、audit、resume、outbox terminal 或 canonical replay 真源。"
  - 第 1602 行：映射表条目从 `reasoning_delta -> accepted non-durable delta; no EventLog row by default` 更新为 `reasoning_delta -> preview (live thinking display only; not canonical replay truth)`
- **修复质量**：映射表条目现在准确反映 REASONING_DELTA 写入 PREVIEW row 的行为。解释性文本（第 1593 行）明确将 reasoning_delta 从 transient delta 子集中排除，并解释了 PREVIEW row 的目的和约束。修正后的文本与实现（`engine_ingest.py:897-903` 写入 PREVIEW row）、Host README（第 534 行）、outbox 语义（第 1828 行）和 PREVIEW 事件定义（第 335 行）无矛盾。
- **微小残余不一致（不阻塞）**：第 339 行（第 4 节术语与概念）仍写"Host 默认不把 `content_delta`、`reasoning_delta`、`tool_call_delta` 这三类 per-delta EngineEvent 写入主 EventLog"。此语句是修复前的第 4 节通用原则声明，映射表在第 13.4 节已更新为权威真源。"主 EventLog"措辞可解读为"作为 canonical fact 写入 EventLog"（此时 PREVIEW row 不违反），但若按字面解读可能引起困惑。建议后续 doc cleanup 中将第 339 行措辞同步为显式说明 reasoning_delta 的 PREVIEW row 例外，但不阻塞当前 fix gate。

### DS-F02 复核：已修复 ✅

- **原 finding**：`_validate_host_event_terminal_payload` 中 `event.thinking is not None` 的 ValueError 抛出（`api.py:3115-3116`）无测试覆盖。
- **修复内容**（git diff 直接证据）：
  - 新增测试 `test_terminal_host_event_rejects_thinking_payload`（`test_host_activity_event_projection.py:766-785`）
  - 导入 `HostTerminalStatus` 和 `HostThinkingView`（第 47-48 行）
- **测试真实性验证**：
  - 测试构造真实 `HostEvent` 实例，`kind=HostEventKind.FAILED`（终端类型），`thinking=HostThinkingView(text_delta="hidden reasoning")`
  - `HostEvent.__post_init__()` → `_validate_host_event_terminal_payload(self)` 被 dataclass 机制触发
  - 终端 kind 跳过 PROGRESS 检查（`api.py:3108`），命中 `event.thinking is not None` 分支（`api.py:3115`），抛出 `ValueError("HostEvent terminal kind must not include thinking")`
  - 测试用 `pytest.raises(ValueError, match="terminal kind must not include thinking")` 断言异常类型和消息
  - **实测通过**：`pytest tests/host/test_host_activity_event_projection.py::test_terminal_host_event_rejects_thinking_payload -v` → `1 passed in 0.26s`
- **修复质量**：测试是真实防御性测试，非伪测试。它构造了生产代码中不应出现的输入组合（thinking 在终端事件上），验证了防御代码会 panic 而非静默忽略。直接证据链完整：构造 → `__post_init__` → `_validate_host_event_terminal_payload` → ValueError。

## 设计真源与实现一致性检查

以对抗性视角逐条核验映射链：

| 检查点 | 设计真源（design.md） | 实现 | 一致？ |
|---|---|---|---|
| REASONING_DELTA 映射 | 第 1602 行：`preview (live thinking display only)` | `engine_ingest.py:897-903`：`_append_preview_event` 写 PREVIEW row | ✅ |
| transient delta 子集 | 第 1593 行：`content_delta` 与 `tool_call_delta`（排除 reasoning_delta） | `engine_ingest.py:4593-4601`：`_is_transient_delta_event` 仅含 CONTENT_DELTA 和 TOOL_CALL_DELTA | ✅ |
| PREVIEW row 语义 | 第 335 行：可进入 Host event stream，不可作为 recovery/memory/audit 真源 | PREVIEW row 仅用于 live thinking projection，不进入 outbox/transcript/activity | ✅ |
| Outbox 排除 reasoning | 第 1828 行：不补 reasoning delta | Outbox 不返回 PREVIEW row | ✅ |
| Terminal thinking 拒绝 | `api.py:3115-3116`：`event.thinking is not None → ValueError` | 现已测试覆盖 | ✅ |
| Host README | 第 534 行：reasoning delta 写 PREVIEW row 只用于 live thinking | 与实现一致 | ✅ |

**结论：无剩余矛盾。** 设计真源映射表（权威）、实现行为、Host README、outbox 语义、PREVIEW row 定义和终端防护之间形成闭合一致链。

## 测试非伪测试检查

### DS-F02 测试逐要素核验

| 要素 | 检查结果 |
|---|---|
| 是否构造真实对象？ | ✅ `HostEvent(...)` 直接构造 dataclass 实例，无 mock |
| 是否触发真实代码路径？ | ✅ `__post_init__` → `_validate_host_event_terminal_payload`，均为生产代码 |
| 异常是否由被测试代码抛出？ | ✅ 异常来自 `api.py:3116`，非测试框架或 mock |
| 断言是否匹配生产错误信息？ | ✅ `match="terminal kind must not include thinking"` 精确匹配 `api.py:3116` |
| 测试是否可独立运行？ | ✅ `pytest ...::test_terminal_host_event_rejects_thinking_payload` 独立通过 |
| 测试是否验证了防御的价值？ | ✅ 构造了生产代码不应产生的输入组合，验证防御会 panic 而非静默 |

**结论：测试是真实防御性测试，非伪测试。**

## Control Doc Residual Owner 准确性

| Residual ID | Owner / Destination | 准确性评估 |
|---|---|---|
| WU-CLI-SMOKE-01-R1 | WU-RET-03 / GitHub Issue #78 under #43 retention lane | ✅ PREVIEW row 清理策略确属存储治理（retention lane）职责。描述准确。 |
| WU-CLI-SMOKE-01-R2 | Future CLI UI enhancement / user decision | ✅ 160 字符截断是 CLI UX 决策，描述准确。 |
| DS-F03 | Future CLI UI/runtime hardening | ✅ dedupe set boundedness 确属 runtime hardening 范畴。 |

Control doc 状态更新检查：

- WU-CLI-SMOKE-01 状态：`review` → `review-fix` ✅
- next entry point：`Run PR review for draft PR #172` → `Controller re-review PR #172 review fixes, then create accepted PR review commit / push if accepted` ✅
- WU-CLI-SMOKE-01 详细状态段末尾新增 PR review artifact 和 fix artifact 引用 ✅

**结论：Control doc residual owner 准确，状态更新与 fix gate 进度一致。**

## Open Questions

无。

## Residual Risk

| Risk | Classification | Owner / Destination |
|---|---|---|
| 第 339 行"主 EventLog"措辞可被误读 | 微小 doc polish | 未来 design.md 术语同步清理；不阻塞当前 fix gate |
| DS-F03 dedupe set boundedness | deferred-with-owner | Future CLI UI/runtime hardening（controller 已裁决） |

## Verdict

**pass**

**Rationale**：

1. **DS-F01 已修复**：设计真源映射表（第 1602 行）和解释性文本（第 1593 行）已同步为 live thinking PREVIEW row 行为。映射表、实现、Host README、outbox 语义和 PREVIEW 定义之间已形成闭合一致链。第 339 行的残余措辞是微小 doc polish，不构成设计矛盾。

2. **DS-F02 已修复**：新增 `test_terminal_host_event_rejects_thinking_payload` 测试，构造终端 HostEvent 携带 thinking，断言 ValueError。测试是真实防御性测试，直接证据链完整（构造 → `__post_init__` → `_validate_host_event_terminal_payload` → ValueError），已通过实测验证。

3. **DS-F03 维持 deferred**：按 controller 裁决不处理。

无需 blocking fix。当前 fix gate 可关闭，进入 accepted PR review commit / push。
