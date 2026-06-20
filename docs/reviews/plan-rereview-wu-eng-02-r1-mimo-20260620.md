# Plan Re-Review: WU-ENG-02-R1 Provider Debugging Correlation Default Enablement And Fallback Diagnostics

- **Review target**: `docs/host/host-issues/wu-eng-02-r1-provider-debugging-correlation-plan.md`
- **Work unit**: WU-ENG-02-R1
- **Gate**: plan re-review
- **Reviewer**: AgentMiMo
- **Timestamp**: 20260620-211719
- **Inputs**: plan artifact, plan-fix artifact (`docs/reviews/wu-eng-02-r1-plan-fix-codex-20260620.md`), prior reviews (`docs/reviews/plan-review-20260620-210618.md`, `docs/reviews/plan-review-20260620-210656.md`)

---

## Re-Review Scope

验证 plan-fix 后的 plan 是否关闭了 controller 裁决的 6 条 accepted findings。不重复初始 review 的全局扫描，只聚焦 accepted finding closure。

---

## Accepted Finding Verification

### Finding 1: Terminal diagnostic path converged to minimal Host public projection suffix path, no durable payload message/digest mutation

**Verdict: CLOSED**

Plan 现在明确了单一方案：

- §6 "Required Public Projection Change For Terminal Diagnostic" 要求仅在 Host public projection 边界（`read_api.py` 的 `_failed_host_event` 和 `outbox.py` 的 terminal item projection）追加 bounded diagnostic suffix 到 `error_message`。
- §6 明确 "Do not append the suffix during Engine ingest, EventLog append, payload-store write, or any path that mutates durable terminal payload `message`; payload digest must remain unchanged."
- §7 Decision 7 移除了方案选择，只保留 error_message suffix 方案。
- §8 Slice 4 Step 7 明确 "Do not change durable terminal payload `message`, payload digest, EventLog facts, public dataclass fields, or Service / CLI renderer contracts."

**代码事实验证**：
- `read_api.py:978` 的 `_optional_payload_text(payload, field_name="message")` 当前只读 payload message，不追加 suffix —— plan 改动在这里追加 suffix 是安全的。
- `outbox.py:279` 的 `_error_message(event)` 同理。
- 两个投影函数都不修改 payload 本身。

**无残余 blocker。**

### Finding 2: Live watcher and outbox fallback use same suffix formatting helper and both have tests

**Verdict: CLOSED**

Plan 现在明确要求：

- §6 "Both projection paths must call the same module-level private Host projection helper for suffix formatting, so `provider_request_id=None` plus the same `client_correlation_id` renders identically in live and outbox fallback views."
- §8 Slice 4 Step 1: "Add a module-level private helper in the Host projection layer that formats the bounded suffix."
- §8 Slice 4 Step 5: "Call the helper from the live failed terminal projection in `dayu/host/read_api.py`."
- §8 Slice 4 Step 6: "Call the same helper from the outbox terminal item projection in `dayu/host/outbox.py`."
- §8 Slice 4 Step 8: "Add tests covering `provider_request_id=None` and `client_correlation_id` present for both live watcher and outbox fallback, and assert the rendered suffix is identical across both paths."
- §9 Expected assertions: "Live watcher and outbox fallback projected terminal `error_message` contain the same fallback `client_correlation_id` suffix when provider id is missing."

**无残余 blocker。**

### Finding 3: Python runner log visibility is mandatory on existing runner.http.response line, same log site and level, no extra log line

**Verdict: CLOSED**

Plan 现在移除了 escape hatch：

- §1 Success Signal: "既有 Python runner `runner.http.response` 日志行必须在同一 log site、同一 log level、同一行携带 `client_correlation_id`；不得新增专用日志事件、额外日志行或提高日志等级。"
- §7 Decision 4 移除了 "if and only if" 和 "if not feasible" escape hatch，改为明确决定：扩展 `_do_attempt(...)` 签名增加 `client_correlation_id: str | None` 参数，在日志行追加。
- §8 Slice 2 Step 4: "Pass `client_correlation_id` from `request_identity` into the private attempt method, likely `_do_attempt(...)`." —— 明确了参数传递路径。
- §8 Slice 2 Step 5: "Extend the existing `runner.http.response` debug message to include `client_correlation_id` on the same line and same log level."
- §8 Slice 2 Step 6: "Add a log capture test for the existing `runner.http.response` site showing the same log line contains `provider_request_id` and `client_correlation_id`."
- §9 Expected assertions: "Existing `runner.http.response` log line contains `client_correlation_id` on the same log line and same log level."

**代码事实验证**：
- `runner.py:607-613`：当前日志行 `_LOGGER.debug("runner.http.response status=%d content_type=%s provider_request_id=%s", ...)` —— 需要在同一行追加 `client_correlation_id=%s`。
- `runner.py:383`：`_call_impl` 调用 `self._do_attempt(payload, effective_options, headers=headers)`，`request_identity` 在作用域内但未传入 —— plan 的 Step 4 指导是正确的。

**无残余 blocker。**

### Finding 4: provider_request_id extraction remains x-request-id only; no tracing/infrastructure headers mapped to provider_request_id

**Verdict: CLOSED**

Plan 现在明确禁止扩展 header allowlist：

- §1 Success Signal: "Provider request id 提取保持当前 `x-request-id` 单一路径；不得把 `x-trace-id`、`x-correlation-id`、`cf-ray` 或其它 tracing / infrastructure header 映射为 `provider_request_id`。"
- §7 Decision 5: "Current extraction only checks `x-request-id`; keep that behavior." 以及 "Do not map `x-trace-id`, `x-correlation-id`, `cf-ray`, W3C trace context headers, proxy headers, CDN headers, or other infrastructure/tracing headers into `provider_request_id`."
- §8 Slice 2 Step 1: "Keep `_extract_provider_request_id(...)` limited to `x-request-id`; preserve case-insensitive extraction, trimming, and empty value ignore behavior."
- §8 Slice 2 Step 2: "Add or update tests confirming `x-trace-id`, `x-correlation-id`, `cf-ray`, and other infrastructure/tracing headers are not extracted as `provider_request_id`."

**代码事实验证**：
- `runner.py:94`：当前 `_PROVIDER_REQUEST_ID_HEADER_NAMES = ("x-request-id",)` —— plan 不改变此常量。
- `runner.py:114-129`：`_extract_provider_request_id` 只检查 allowlist 中的 header name —— plan 保持此行为。

**无残余 blocker。**

### Finding 5: Tool Trace diagnostic_ref=None is explicitly allowed; no fake event_id/provider id fallback

**Verdict: CLOSED**

Plan 现在明确 `diagnostic_ref=None` 是合法值：

- §7 Decision 6: "Current Tool Trace hot row validation permits `diagnostic_ref=None`; keep `None` when there is no raw payload ref or provider request id. Do not introduce an `event_id` fallback, do not fake `diagnostic_ref`, and do not put `client_correlation_id` into `provider_request_id`."
- §8 Slice 3 Step 3: "Assert hot row has `provider_request_id is None`, `diagnostic_ref is None` when no raw payload ref exists..."
- §11 Risks: "Tool Trace diagnostic rows with `diagnostic_ref=None` are currently valid. Tests should lock that a row with no provider id and no raw payload ref can still preserve `client_correlation_id`."

**代码事实验证**：
- `tool_trace.py:918-926`：`diagnostic_refs` 由 `raw_payload_ref` 和 `provider_request_id` 组成；两者都为 None 时 `diagnostic_ref=None` —— plan 不改变此逻辑。
- `tool_trace.py:911-915`：当前 skip 条件只检查 `provider_request_id is None`（当 event_type 为 `ENGINE_EVENT_DIAGNOSTIC` 时）。Plan 要求 Slice 3 修改 skip 条件使 `client_correlation_id` 单独存在时也保留行。

**无残余 blocker。**

### Finding 6: Slice 1 requires baseline assembly tests before default enablement

**Verdict: CLOSED**

Plan 现在明确要求基线验证：

- §8 Slice 1 Step 1: "Before changing the default, run the current baseline assembly tests listed for this slice and record whether they pass."
- §8 Slice 1 Step 6: "If tests fail after the default changes, classify each failure before editing: expected behavior change: update assertions that assumed `DISABLED` Service assembly default. regression: fix the implementation rather than weakening tests."
- §9 Expected assertions: "Existing disabled policy tests still pass."

**无残余 blocker。**

---

## Residual Issues Check

在复核 accepted findings 时，检查是否有 plan-fix 引入的新问题：

### Check 1: Slice 4 affected files 与 plan §5 是否一致

§5 列出 `dayu/host/read_api.py`、`dayu/host/outbox.py`、"a shared private Host projection helper module or existing Host projection utility"。Slice 4 的 files 列表一致。§5 还列出 `tests/host/test_public_run_api.py`、`tests/host/test_public_outbox_api.py`、`tests/service/test_entrypoint_runtime.py`、`tests/service/test_entrypoint_runtime_prompt_path.py`、`tests/cli/test_prompt_command.py` —— 这些在 Slice 4 steps 中通过 "related host / service / CLI tests" 覆盖。无过度耦合。

### Check 2: `_extract_diagnostic_trace` skip 条件是否需要修改

当前 `tool_trace.py:911-915` 的 skip 条件是：
```python
if (
    event.event_type == _EVENT_TYPE_ENGINE_EVENT_DIAGNOSTIC
    and provider_request_id is None
):
    return None
```

Plan Slice 3 Step 1 要求 "Change diagnostic extraction skip condition so `client_correlation_id` alone is enough to keep the trace row." 这意味着需要修改为：
```python
if (
    event.event_type == _EVENT_TYPE_ENGINE_EVENT_DIAGNOSTIC
    and provider_request_id is None
    and client_correlation_id is None
):
    return None
```

Plan 正确描述了这个改动，且 Slice 3 的测试步骤覆盖了此场景。无遗漏。

### Check 3: Plan §7 Decision 4 的 `_do_attempt` 参数传递是否过度设计

`_do_attempt` 是 `_AsyncAgent` 的私有方法，从 `_call_impl` 调用。增加一个 `client_correlation_id: str | None` 参数是标准的私有方法签名扩展。Plan 明确 "This is an intra-class private signature change, not a public contract change." —— 无过度设计。

---

## Open Questions

无新增 open questions。Prior review 的 open questions 已由 plan-fix 收敛。

---

## Residual Risks

| ID | 风险 | 严重程度 | Owner / Destination |
|---|---|---|---|
| RR1 | Provider 拒绝 `X-Client-Request-Id` header（400 或静默忽略）→ 需 revert 默认启用或改为 per-model opt-in | 低 | Plan §12 Stop Condition 已覆盖 |
| RR2 | `error_message` 后缀方案可能让现有 CLI 输出测试 exact-match 失败 | 低 | Implementation gate 应在 Slice 4 实施前跑现有 CLI/output 测试确认基线 |
| RR3 | `tool_trace.py` 第二条 diagnostic extraction path（约 line 970）是否也需要同步修改 skip 条件 | 低 | Slice 3 Step 5 已要求 "If there are multiple diagnostic extraction paths with the same `provider_request_id is None` guard, update and test each path." |

---

## Final Plan Re-Review Conclusion

**conclusion: pass**

全部 6 条 accepted findings 已关闭。Plan 现在是 code-generation-ready 的：

1. 终端诊断路径收敛到 minimal Host public projection suffix path，不修改 durable payload。
2. Live watcher 和 outbox fallback 使用同一 suffix formatting helper，且有测试覆盖。
3. Python runner log 可见性是 mandatory 的，在既有 `runner.http.response` 日志行上扩展，无 escape hatch。
4. Provider request id 提取保持 `x-request-id` only，不扩展 header allowlist。
5. Tool Trace `diagnostic_ref=None` 显式允许，不伪造 fallback。
6. Slice 1 要求基线 assembly tests 后再改变默认值。

Residual risks 均为低严重程度，由 plan stop conditions 和 implementation gate 覆盖。

**Material findings**: 0
**Blocking findings**: 0
