# P10.5 Slice 6 Re-review — AgentDS

## 结论：PASS

CF1 fixed，0 new blocker。本 re-review 只复核 fix，不修改文件、不 commit/push/PR。

## 复核范围

依据 Controller adjudication `docs/reviews/phase10-5-slice6-code-review-controller-adjudication-20260518.md` 的 CF1 / DS H1 裁决，重点审查 fix 五要素：

1. `tests/host/public_smoke_support.py` 的 `skip_if_provider_exception` / shared marker 是否与 runner terminal skip 同源且精确
2. `tests/host/test_public_compact_smoke.py` 是否只在 RuntimeError 匹配 provider environment failure 时 skip
3. fix 是否保持 FakeContextCompactor 不计入 success signal
4. `tests/README.md` 与 fix artifact 是否准确记录 quota / rate-limit skip 和 DeepSeek 空摘要 hard-fail 边界
5. Controller 复跑结果是否足以接受 fix

---

## 1. Skip 同源性 — PASS

`skip_if_provider_terminal_failed` (`public_smoke_support.py:845`) 与 `skip_if_provider_exception` (`public_smoke_support.py:863`) 调用同一私有函数 `_skip_if_provider_failure_message` (`public_smoke_support.py:876`)，共享四层精确 marker：

| 层 | Marker Set | 覆盖场景 |
|---|---|---|
| L1 | `_NETWORK_FAILURE_MARKERS` (line 89) | clientconnectorerror, timeout, connection refused, name not known 等 |
| L2 | `_TEMPORARY_PROVIDER_UNAVAILABLE_MARKERS` (line 103) | 503, http 503, status 503, server overloaded, model is overloaded, overloaded, transient/temporarily unavailable, try again later 等 |
| L3 | `_EXPLICIT_UNAVAILABLE_MARKERS` (line 137) | "status': 'unavailable'", grpc_status=unavailable, error code: 503 等 |
| L4 | `_TEMPORARY_PROVIDER_RATE_LIMIT_MARKERS` (line 120) | 429, http 429, resource_exhausted, quota_exceeded, QuotaFailure, rate_limit_exceeded, RetryInfo, RetryDelay 等 |

每层 skip reason 格式统一：`provider=<name> endpoint=<endpoint> provider_<failure_type>=<reason> message=<original>`。

**两入口差异**：`skip_if_provider_terminal_failed` 从 `HostEvent.error_message` 取消息；`skip_if_provider_exception` 从 `str(exc)` 取消息。对于 compactor 路径，`_run_llm_summary` 将原始 Engine 异常包装为 `RuntimeError(f"compactor LLM failed: {error_box[0]}")`，`str(exc)` 包含原始 provider 错误消息的 `str()`，marker 子串匹配不受前缀包装影响。

**非目标匹配风险分析**：

- `"503"` (line 104)：作为独立 marker 存在，同时有 `"http 503"` / `"status 503"` / `"http_status=503"` / `"error code: 503"` 等上下文 marker 覆盖。纯数字 "503" 在非 HTTP 语境中出现概率极低。
- `"unavailable"` 已在 `_TEMPORARY_PROVIDER_UNAVAILABLE_MARKERS` 中有 `"temporarily unavailable"` / `"transient unavailable"` 上下文 marker，`_EXPLICIT_UNAVAILABLE_MARKERS` 中有 `"status': 'unavailable'"` 等 gRPC 格式 marker。

两者为原 DS review 中对应的 MiMo L1 / L2，已在 original review 标记为 LOW / deferred，不阻塞。Fix 未改变这些 marker 的表达方式。

---

## 2. Compactor Provider Exception Skip 精确性 — PASS

`test_public_compact_smoke.py:299-328` 的 try/except 结构：

```python
try:
    async with open_host(options) as host:
        ...
except RuntimeError as exc:
    skip_if_provider_exception(case, exc)
    raise
```

精确 skip 路径：
- `_run_llm_summary_async` 中 `run_agent_and_wait` 因 provider 503 / 429 / RESOURCE_EXHAUSTED / QuotaFailure / UNAVAILABLE / overloaded 返回失败 → Engine 层 raise 包含 provider 错误消息的异常
- 线程捕获 → `error_box.append(exc)` → 外层 `raise RuntimeError(f"compactor LLM failed: {error_box[0]}")`
- 测试 body `except RuntimeError` → `skip_if_provider_exception(case, exc)` → `str(exc)` 包含原始 provider 消息 → marker 匹配 → `pytest.skip()` 精确报告 provider、endpoint、failure 类型与原始消息

Hard fail 路径（不匹配 marker 则 `skip_if_provider_exception` 返回，`raise` 重抛原始异常）：

| 场景 | 异常消息 | 匹配 marker？ | 结果 |
|---|---|---|---|
| compactor LLM 超时 | `"compactor LLM timed out"` | 否 | hard fail |
| 无结果返回 | `"compactor LLM returned no summary"` | 否 | hard fail |
| 非 FinalAnswer outcome | `"compactor LLM did not return final answer"` | 否 | hard fail |
| 空摘要 | `"compactor LLM failed: compactor LLM returned empty summary"` | 否 | hard fail |
| API key 认证失败 (401/403) | provider 返回的错误不含 503/429/unavailable 等 | 否 | hard fail |
| 非法 model / schema failure | provider 返回 400/404 错误 | 否 | hard fail |
| 真实 provider 503 | `"compactor LLM failed: ...503..."` | 是 (L2) | skip |
| 真实 provider 429 / RESOURCE_EXHAUSTED | `"compactor LLM failed: ...RESOURCE_EXHAUSTED..."` | 是 (L4) | skip |
| 真实 provider overloaded | `"compactor LLM failed: ...overloaded..."` | 是 (L2) | skip |

**验证**：Fix artifact 明确记录 "复验期间曾观察到一次 DeepSeek compactor 空摘要；该情况仍 hard fail，符合本 fix 不 broad skip、只跳过 provider availability / quota / rate-limit 的边界"。空摘要的异常消息不包含任何 provider 环境失败 marker，确认 hard fail。

---

## 3. FakeContextCompactor 不计入 Success Signal — PASS

`test_public_compact_smoke.py` 全程使用 `_RealLLMContextCompactor` (line 263) 显式注入 `CompactorExecutionBaseline.context_compactor` (line 290)。`FakeContextCompactor` 未被 import、未被实例化、未被使用。

`compactor.call_count >= 1` 断言 (line 331) 验证真实 compactor 至少被调用一次。普通 Run 使用 `FinalAnswerWorkerFactory` deterministic worker (line 264)，不干扰 compactor 真实性的判断。

---

## 4. tests/README 与 Artifact 记录准确性 — PASS

`tests/README.md` line 96：
> real runner / compactor smoke 只允许按 provider 缺少 secret、endpoint / 网络不可用、临时不可用或 quota / rate-limit 给出精确 skip，mock runner / `FakeContextCompactor` 不计入 public-path success signal。

覆盖：
- Skip 条件：缺少 secret、网络不可用、临时不可用、quota / rate-limit（四层均覆盖）
- Hard fail 边界：不在上述条件的失败（包括空摘要）不属于允许 skip 范围
- Success signal 排除：mock runner / FakeContextCompactor 不计入

Fix artifact (`docs/reviews/phase10-5-slice6-fix-codex-20260518.md`) line 35 明确记录：
> 复验期间曾观察到一次 DeepSeek compactor 空摘要；该情况仍 hard fail，符合本 fix 不 broad skip、只跳过 provider availability / quota / rate-limit 的边界。

Implementation artifact (`docs/reviews/phase10-5-slice6-implementation-codex-20260518.md`) line 56-57 同步：
> 复验期间曾观察到一次 DeepSeek compactor 返回空摘要并 hard fail；后续重跑通过。该类空摘要不属于本 fix 允许的 provider availability / quota / rate-limit skip 范围，仍按 API / contract failure 处理。

三者一致，无矛盾。

---

## 5. Controller 复跑结果验证 — PASS

| 验证项 | 结果 | 来源 |
|---|---|---|
| `pytest tests/host/test_public_compact_smoke.py -q -rs` | 1 passed | Fix artifact L20-21 |
| target smoke 四文件 | 11 passed | Fix artifact L22-23 |
| `pytest tests/host/test_public_real_runner_matrix_smoke.py -q -rs` | 3 passed, 1 skipped (Gemini quota/rate-limit) | Fix artifact L24-25 |
| `pytest tests/host -q` | 695 passed, 1 skipped | Fix artifact L26-27 |
| `pyright dayu/host tests/host` | 0 errors, 0 warnings | Fix artifact L28-29 |
| `git diff --check` | clean | Fix artifact L30 |

Implementation-control.md line 237 已记录 Controller 本地复跑确认。

---

## CF1 Fixed / Not Fixed 判定

| CF1 要求 | 状态 | 证据 |
|---|---|---|
| 仅修测试支撑 / smoke，不改生产代码 | **Fixed** | Diff 仅涉及 `tests/host/public_smoke_support.py`、`tests/host/test_public_compact_smoke.py`、`tests/README.md`、implementation artifact |
| compactor provider 临时不可用精确 skip | **Fixed** | `skip_if_provider_exception` 调用同源 `_skip_if_provider_failure_message`，四层 marker 覆盖 503/429/RESOURCE_EXHAUSTED/QuotaFailure/overloaded/explicit unavailable |
| skip reason 包含 provider/endpoint/failure type/original message | **Fixed** | 每层 skip 消息格式：`provider=<name> endpoint=<endpoint> provider_<type>=<reason> message=<original>` |
| 不 broad skip | **Fixed** | 只有四层明确 marker 匹配才 skip；空摘要、超时、非 FinalAnswer、API key 错误等不匹配 → hard fail |
| 不吞 API/schema/public contract failure | **Fixed** | 400/401/403/404 错误消息不含 marker → hard fail |
| 更新 implementation artifact 与 residual risk | **Fixed** | Fix artifact L32-36 更新 residual risk；impl artifact L56-57 记录空摘要 hard-fail 观察 |

**CF1 全部要求已满足。**

---

## New Blocker 判定

无 new blocker。

- 原 DS review 中 deferred findings (M1/M2 跨测试私有 helper 依赖、L1/L2 标记表达) 在 Controller adjudication 中已明确 deferred 到 aggregate review / Phase 11，不因本 fix 升级。
- MiMo L1/L2 (503/unavailable 标记偏宽) 在原 review 中为 LOW，不因本 fix 升级。
- Fix 引入的 `skip_if_provider_exception` 与既有 `skip_if_provider_terminal_failed` 共享同一 `_skip_if_provider_failure_message`，未新增重复逻辑。
- 未发现测试覆盖盲区：compactor smoke 的 ordinary Run 仍通过 `skip_if_provider_terminal_failed(case, first_terminal)` (line 314) 和 `skip_if_provider_terminal_failed(case, second_terminal)` (line 330) 保护，compactor 执行异常通过 `skip_if_provider_exception(case, exc)` (line 327) 保护，三条 skip 路径一致。

---

## Residual Risk

| 风险 | Owner | 阻塞 P10.5 exit |
|---|---|---|
| Compactor provider 在执行 compaction 时可用性变化导致 skip（如 deepseek 在执行中返回 503）—已通过精确 skip 覆盖 | 环境 | 否 |
| DeepSeek compactor 空摘要 hard fail—属于 contract failure，正确 hard fail | 环境/模型行为 | 否 |
| Gemini quota / rate-limit skip—属于环境 provider residual | 环境 provider quota | 否 |

---

## 最终判定

**P10.5 Slice 6 re-review: PASS**。CF1 fixed，0 new blocker。Controller 可接受 fix 并进入 accepted slice commit。
