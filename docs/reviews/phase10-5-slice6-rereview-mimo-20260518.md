# P10.5 Slice 6 Re-Review — AgentMiMo

## Gate

当前 gate：P10.5 Slice 6 re-review。
Re-review 依据：Controller adjudication（`docs/reviews/phase10-5-slice6-code-review-controller-adjudication-20260518.md`）、Fix artifact（`docs/reviews/phase10-5-slice6-fix-codex-20260518.md`）、Implementation artifact（`docs/reviews/phase10-5-slice6-implementation-codex-20260518.md`）、当前 workspace diff。

## 结论

**PASS**。CF1 已修复，无 new blocker。

---

## 审查范围

本轮复核 Controller adjudication 接受的 CF1 fix：compactor provider transient unavailable / explicit unavailable / quota / rate-limit 精确 skip，不 broad skip，API / schema / public contract failure 必须 hard fail。

审查文件：
- `tests/host/public_smoke_support.py`（skip_if_provider_exception / shared marker）
- `tests/host/test_public_compact_smoke.py`（compactor smoke skip 逻辑）
- `tests/README.md`（文档同步）
- Fix artifact 与 Implementation artifact（记录准确性）

---

## 1. skip_if_provider_exception / shared marker 同源性与精确性

**判定：PASS。**

`public_smoke_support.py` 定义核心函数 `_skip_if_provider_failure_message`（line 876-911），被两个公开函数共同调用：
- `skip_if_provider_terminal_failed`（line 845-861）：只在 `terminal_status is HostTerminalStatus.FAILED` 时检查。
- `skip_if_provider_exception`（line 863-873）：对任何异常字符串检查。

四组 marker 严格分离：

| Marker 组 | 覆盖范围 | 示例 |
|---|---|---|
| `_NETWORK_FAILURE_MARKERS` | 网络层失败 | clientconnectorerror、timeout、connection refused |
| `_TEMPORARY_PROVIDER_UNAVAILABLE_MARKERS` | 临时不可用 | 503、unavailable、overloaded、try again later |
| `_EXPLICIT_UNAVAILABLE_MARKERS` | 显式 unavailable | status=unavailable、grpc_status=unavailable |
| `_TEMPORARY_PROVIDER_RATE_LIMIT_MARKERS` | quota / rate-limit | 429、resource_exhausted、quotafailure、retrydelay |

匹配逻辑：`any(marker in lowered for marker in ...)`，只在匹配时 `pytest.skip(...)`，未匹配则不 skip。skip reason 精确包含 `provider={name}`、`endpoint={endpoint}`、failure type 与原始 message。

**与 runner terminal skip 同源**：`skip_if_provider_terminal_failed` 和 `skip_if_provider_exception` 共用 `_skip_if_provider_failure_message`，确保 terminal event 和 exception 路径的 skip 逻辑一致。

---

## 2. test_public_compact_smoke.py 的 skip 逻辑

**判定：PASS。**

`test_real_compactor_public_opener_compacts_and_preserves_continuity`（line 242-336）：

```python
try:
    async with open_host(options) as host:
        ...
except RuntimeError as exc:
    skip_if_provider_exception(case, exc)
    raise
```

逻辑：
1. `RuntimeError` 由 `_RealLLMContextCompactor._run_llm_summary` 抛出（line 189: `raise RuntimeError(f"compactor LLM failed: {error_box[0]}")`）。
2. `skip_if_provider_exception` 检查异常消息是否匹配四组 marker。
3. **匹配**：`pytest.skip(...)`，测试跳过。
4. **不匹配**：`raise` 继续抛出，测试 hard fail。

这意味着：
- provider 503 / 429 / overloaded / transient unavailable → skip
- API key invalid / model not found / schema violation / empty summary → hard fail
- 空摘要（`outcome.content.strip() == ""`）→ `RuntimeError("compactor LLM returned empty summary")` → 不匹配任何 marker → hard fail

**符合 Controller adjudication 要求**：不能 broad skip，不能吞掉 API / schema / public contract failure。

---

## 3. FakeContextCompactor 不计入 success signal

**判定：PASS。**

- 测试使用 `_RealLLMContextCompactor`（line 122-239），显式实现 `ContextCompactor` 协议。
- `compact()` 调用 `_run_llm_summary()` → `asyncio.run(run_agent_and_wait(...))`，使用真实 Engine runner。
- 普通 Run 使用 `FinalAnswerWorkerFactory`（deterministic worker），但 compact smoke 的验证重点是 compaction 触发 → canonical compact events → memory projection → subsequent Run continuity。
- 断言 `compactor.call_count >= 1`（line 331），验证真实 compactor 被调用。
- 未使用 `FakeContextCompactor` 或 mock compactor。

---

## 4. 文档与 artifacts 记录准确性

**判定：PASS。**

### tests/README.md

line 96 准确描述：
> real runner / compactor smoke 只允许按 provider 缺少 secret、endpoint / 网络不可用、临时不可用或 quota / rate-limit 给出精确 skip，mock runner / `FakeContextCompactor` 不计入 public-path success signal。

### Fix artifact

line 35 准确记录：
> 复验期间观察到一次 DeepSeek compactor 空摘要；该情况仍 hard fail，符合本 fix 不 broad skip、只跳过 provider availability / quota / rate-limit 的边界。

### Implementation artifact

line 57 准确记录：
> 复验期间曾观察到一次 DeepSeek compactor 返回空摘要并 hard fail；后续重跑通过。该类空摘要不属于本 fix 允许的 provider availability / quota / rate-limit skip 范围，仍按 API / contract failure 处理。

文档与代码实现一致，无遗漏或误导。

---

## 5. Controller 复跑结果

**判定：PASS。**

Fix artifact 记录的 Controller 复跑结果：

| 验证项 | 结果 |
|---|---|
| `pytest tests/host/test_public_compact_smoke.py -q -rs` | 1 passed |
| target smoke（4 文件） | 11 passed |
| `pytest tests/host/test_public_real_runner_matrix_smoke.py -q -rs` | 3 passed, 1 skipped |
| `pytest tests/host -q` | 695 passed, 1 skipped |
| `python -m pyright dayu/host tests/host` | 0 errors |
| `git diff --check` | clean |

- compactor smoke 1 passed：真实 compactor 在当前环境通过。
- runner matrix 1 skipped：Gemini provider quota / rate-limit（HTTP 429 / RESOURCE_EXHAUSTED / QuotaFailure / RetryInfo），精确 skip。
- tests/host 1 skipped：同一 Gemini skip。
- pyright 0：无类型错误。
- diff check clean：无未提交 whitespace 问题。

**复跑结果充分，满足 Controller adjudication 的 Required Validation。**

---

## CF1 修复状态

| 要求 | 状态 | 证据 |
|---|---|---|
| 仅修测试支撑 / smoke，不改生产代码 | ✓ | 只修改 `public_smoke_support.py`、`test_public_compact_smoke.py`、`tests/README.md`、artifacts |
| 对 compactor provider 临时不可用做精确 skip | ✓ | `_skip_if_provider_failure_message` 四组 marker 覆盖 |
| skip reason 包含 provider、endpoint、failure type、原始消息 | ✓ | `pytest.skip(f"provider={case.name} endpoint={case.endpoint} ... message={message}")` |
| 不能 broad skip | ✓ | 只在 marker 匹配时 skip，不匹配则 raise |
| 不能吞掉 API / schema / public contract failure | ✓ | 空摘要、无效 API key、模型不存在等不匹配任何 marker |
| 更新 implementation artifact 的验证与 residual risk | ✓ | artifact 已更新 |

**CF1 已修复。**

---

## New Blocker 检查

无 new blocker。

---

## Findings

无新增 findings。原 review 的 M1、M2、L1、L2、L3 仍为 deferred，不阻塞 P10.5 exit。

---

## 最终判定

**P10.5 Slice 6 Re-Review: PASS。**

CF1 已修复。Controller 复跑结果充分。无 new blocker。建议接受进入 accepted slice commit。
