# Phase 5 Plan Fix Re-Review: RunInputBuilder 与本地执行 Dispatch

## Review Role

Independent plan fix re-review. Review only the plan fix for accepted non-blocking findings. Do not modify production code, do not commit, do not push, do not enter implementation. Write only the re-review artifact.

## Artifacts Inspected

- `docs/host/phase5-runinputbuilder-local-dispatch-plan.md` — 修复后的 plan
- `docs/reviews/gateflow-plan-review-host-p5-runinputbuilder-local-dispatch-controller-adjudication-20260514.md` — controller 裁决
- `docs/reviews/gateflow-plan-fix-host-p5-runinputbuilder-local-dispatch-codex-20260514.md` — fix artifact
- `docs/reviews/gateflow-plan-review-host-p5-runinputbuilder-local-dispatch-mimo-20260514.md` — 本 reviewer 的先前 plan review
- `docs/reviews/gateflow-plan-review-host-p5-runinputbuilder-local-dispatch-ds-20260514.md` — DS 的 plan review

---

## Finding Verdicts

### MiMo F001: `observed_at` 时区约定 — VERDICT: FIXED

**原问题**: `EngineEventCandidate.observed_at: datetime` 未指定时区约定。

**修复内容**: Plan §3.1 新增（line 128）：

> `observed_at` 必须是 `timezone.utc` aware `datetime`。写入 EventLog 时必须沿用 Phase 2 durable timestamp convention：UTC ISO-8601 TEXT、微秒精度、`Z` 后缀；naive `datetime` 属于构造错误。

**验证**: UTC 约定明确，naive datetime 被显式禁止为构造错误。与 Phase 2 durable timestamp convention 一致。Implementation agent 可直接在 `EngineEventCandidate` construction 时校验 `observed_at.tzinfo is not None`。

---

### MiMo F002: Canonical event ID 派生公式 — VERDICT: FIXED

**原问题**: 只声明输入要素，未给出派生公式。

**修复内容**: Plan §3.1 新增（lines 130-142）：

```text
event_id = "event-engine-" + sha256_digest_json({
  "execution_id": execution_id,
  "worker_event_index": worker_event_index,
  "event_class": event_class,
  "event_type": event_type,
  "sub_index": sub_index
}).removeprefix("sha256:")
```

并定义 `sub_index` 从 0 开始，用于一个 EngineEvent 映射出多条 Host events 的场景（例如 `final_answer -> ATTEMPT_SUCCEEDED + RUN_SUCCEEDED`）。明确 "同一输入必须生成同一 event id；不同 event class / event type / sub-index 必须生成不同 event id"。

**验证**: 公式确定性、可复现。`sub_index` 解决了 `final_answer` 映射两条 canonical event 的去重问题。Implementation agent 可直接实现 `sha256_digest_json` 调用。与 Phase 2 `event_id` 全局唯一约束兼容。

---

### MiMo F003: `PROVIDER_PROTOCOL_ERROR` payload 映射 — VERDICT: FIXED

**原问题**: `raw_payload` 与 `partial_tool_call_count` 的 Engine-to-Host 映射未说明。

**修复内容**: Plan §3.5 新增（line 386）：

> `partial_tool_call_count` 必须由 `len(engine_event.data.partial_tool_calls)` 派生。`raw_payload_ref` / `raw_payload_digest` 通过 Phase 2 payload descriptor 机制保存 `engine_event.data.raw_payload`；当 `raw_payload is None` 时二者均为 `None`。

**验证**: 映射关系明确。`len()` 派生简单确定。payload descriptor 机制复用 Phase 2 已有基础设施。`None` 处理边界清晰。

---

### MiMo F004: `EngineEvent` 字段枚举遗漏 `occurred_at` — VERDICT: FIXED

**原问题**: §1.2 evidence 遗漏 `EngineEvent.occurred_at` 字段。

**修复内容**: Plan §1.2 最后一条 evidence（line 30）修正为：

> 当前代码事实：`dayu/engine/contracts/engine_events.py` 的 `EngineEvent` 包含 `occurred_at`、`session_id`、`run_id`、`type`、`data`、`metadata`，没有 Host Attempt identity；这与设计要求一致，Phase 5 不得修改。

**验证**: 现在与 `engine_events.py:443` 的实际字段列表一致。

---

### MiMo F005: `AttemptDispatchSnapshot` 与 provider 字段分工 — VERDICT: FIXED

**原问题**: snapshot 与 provider 之间的字段分工未显式说明。

**修复内容**: Plan P5-S2 Exact changes 新增（line 569）：

> `AttemptDispatchSnapshot` 只携带 durable identity refs、dispatch refs、policy snapshot refs 和 cancellation token；`runner_spec`、`runner_options`、`agent_policy`、`tool_schemas`、`tool_executor` 由对应 providers 在 `build()` 时注入，不在 snapshot 中重复保存。

**验证**: 职责划分清晰。snapshot 是 durable refs 载体，providers 是 Engine request 字段注入者。Implementation agent 不会将 `runner_spec` 等塞入 snapshot。

---

### MiMo F006: `cancel_session_runs` replay best-effort re-propagation 测试 — VERDICT: FIXED

**原问题**: P5-S5 tests 缺少 replay 后 best-effort re-propagation 的测试覆盖。

**修复内容**: Plan P5-S5 Tests 新增（line 764）：

> `cancel_session_runs` replay 不追加 facts；若仍存在同 execution_id 的 active `CANCELLING` worker，best-effort re-propagation 不影响返回值与幂等记录。

**验证**: 测试期望明确覆盖了 replay 路径。Implementation agent 可直接编写测试断言 replay 返回值与幂等记录不变，同时验证 best-effort side effect 执行或跳过均不影响正确性。

---

### DS F-N1: `worker_accept_event_id` / `worker_accept_event_sequence` 语义 — VERDICT: FIXED

**原问题**: dispatch diagnostic 字段 `worker_accept_event_id` 和 `worker_accept_event_sequence` 的引用目标未定义。

**修复内容**: Plan §3.2 新增（line 177）：

> `worker_accept_event_id` 是 Host append 的 `ATTEMPT_RUNNING` EventLog `event_id`；`worker_accept_event_sequence` 是同一 `ATTEMPT_RUNNING` EventLog row 的全局 `event_sequence`。它们不是 worker-local sequence，也不是 Engine event id。

**验证**: 引用目标明确为 Host EventLog 的 `ATTEMPT_RUNNING` 事件。Implementation agent 不会误解为 worker-local 或 Engine-level identity。与 §3.3 "append ATTEMPT_RUNNING and Attempt STARTING -> RUNNING in one transaction" 和 "record worker accept refs on dispatch record" 一致。

---

### DS F-N2: Engine contract type module binding — VERDICT: FIXED

**原问题**: `AgentRunRequest`、`RunnerSpec`、`RunnerCallOptions`、`AgentPolicy` 的模块归属不明确，可能导致 Host 重新定义同名 dataclass。

**修复内容**: Plan §3.4 新增（lines 240-247）：

> `AgentRunRequest`、`RunnerSpec`、`RunnerCallOptions` 和 `AgentPolicy` 均使用现有 Engine public contract 类型：
> - `dayu.engine.contracts.agent_run.AgentRunRequest`
> - `dayu.engine.contracts.runner_spec.RunnerSpec`
> - `dayu.engine.contracts.runner_spec.RunnerCallOptions`
> - `dayu.engine.contracts.agent_policy.AgentPolicy`
>
> Host RunInputBuilder 只构造这些既有 Engine request / policy objects，不在 Host 内重新定义同名 dataclass，不扩展 Engine contract，也不要求 Engine import Host 类型。

**验证**: 类型绑定到具体 `dayu.engine.contracts` 模块路径。Host 使用而非重新定义。Import 方向为 Host → Engine contracts，不反向。Implementation agent 不会在 `dayu/host/api.py` 或 `dayu/host/run_input.py` 中创建同名 dataclass。

---

## New Blocker Check

逐项检查 fix 引入的变更是否引入新的 design ambiguity、implementation ambiguity 或 blocker：

1. **SHA256 event ID 公式**: 确定性、可复现。`sha256_digest_json` 是一个明确的辅助函数，implementation agent 可直接实现。JSON key 顺序由 `sha256_digest_json` 的 canonical JSON 约定保证（Phase 2 已有 `canonical_json` 基础设施）。**无新问题。**

2. **`sub_index` 语义**: 从 0 开始，用于一个 EngineEvent 映射多条 Host events。当前 Phase 5 只有 `final_answer -> ATTEMPT_SUCCEEDED(0) + RUN_SUCCEEDED(1)` 和 `run_failed -> ATTEMPT_FAILED(0) + RUN_FAILED(1)` 两个场景。定义清晰。**无新问题。**

3. **UTC `observed_at` 强制**: `timezone.utc` aware datetime 校验是简单 assertion。与 Phase 2 UTC convention 一致。**无新问题。**

4. **Engine contract type binding**: Host `from dayu.engine.contracts.agent_run import AgentRunRequest` 是合法 import 方向（Host → Engine contracts）。Engine 不需要知道 Host 的存在。**无新问题。**

5. **`partial_tool_call_count = len(...)` 派生**: 简单 Python `len()` 调用，无歧义。**无新问题。**

6. **P5-S5 replay test expectation**: 测试断言 "replay 不追加 facts" 和 "best-effort re-propagation 不影响返回值"，实现边界清晰。**无新问题。**

**无新 blocker。**

---

## Cross-check: Fix 与 Design Truth 一致性

| Fix Item | Design Truth Alignment |
|---|---|
| `observed_at` UTC | 与 Phase 2 durable timestamp convention 一致 |
| SHA256 event ID | 与 Phase 2 `event_id` 全局唯一约束兼容；不修改 Engine `EngineEvent` |
| `sub_index` | 与 §13.4 `final_answer -> RUN_SUCCEEDED + ATTEMPT_SUCCEEDED` 双映射一致 |
| Engine contract types | 与 §17 "Engine 公共 EngineEvent 契约不携带 Host identity" 一致；Host 使用 Engine types 而非修改它们 |
| `worker_accept_event_id` = `ATTEMPT_RUNNING` EventLog id | 与 §3.3 "append ATTEMPT_RUNNING" 和 "record worker accept refs" 一致 |
| payload descriptor for `raw_payload` | 与 Phase 2 payload foundation 一致 |

---

## Final Verdict

| Finding | Verdict |
|---|---|
| MiMo F001 observed_at timezone | **Fixed** |
| MiMo F002 canonical event ID formula | **Fixed** |
| MiMo F003 PROVIDER_PROTOCOL_ERROR mapping | **Fixed** |
| MiMo F004 EngineEvent evidence | **Fixed** |
| MiMo F005 AttemptDispatchSnapshot vs provider | **Fixed** |
| MiMo F006 cancel_session_runs replay test | **Fixed** |
| DS F-N1 worker accept refs semantics | **Fixed** |
| DS F-N2 Engine contract type binding | **Fixed** |
| New blockers | **0** |

**Gate recommendation: Plan 通过，可以进入 implementation gate。** 全部 8 个 non-blocking findings 已修复，未引入新 blocker。Plan 现在完全 code-generation-ready。
