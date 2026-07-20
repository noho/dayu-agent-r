# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-E Slice S1 Code Review Re-Review — AgentMiMo

## Review Metadata

- **Reviewer**: AgentMiMo
- **Review type**: S1 code-review fix re-review
- **Timestamp**: `20260713-131500`
- **Scope**: 只验证 `R3-E-S1-CR-F01` 是否关闭，以及 fix 是否引入 S1 内新 material issue

## R3-E-S1-CR-F01 Closure

**已关闭。**

### 原始 finding

- **来源**: AgentDS F-01（MiMo 01 为同一问题的低严重度可读性观察）
- **问题**: `_build_requests_profile` 的 `(requests.RequestException, RuntimeError)` handler 中 `session.close()` 位于 `return profile` 之后，不可达。局部 `requests.Session` 在异常路径下未关闭。

### Fix 验证

**代码变更**（`utils/diagnose_web_access.py:1344-1360`）:

```python
except (requests.RequestException, RuntimeError) as exc:
    profile["status"] = "request_exception"
    profile["error"] = str(exc)
    profile["result"] = {
        "ok": False,
        "status": "request_exception",
        "error_type": type(exc).__name__,
        "error_message": str(exc),
        "elapsed_seconds": _round_elapsed(started_at),
    }
    session.close()    # ← 现在位于 return 之前
    return profile
```

- ✓ `session.close()` 移至 `return profile` 之前。
- ✓ 旧的两行不可达代码（`session.close()` + `return profile`）已删除。
- ✓ 成功路径仍由 `finally: session.close()` 兜底。
- ✓ `_FetchUrlSafetyError` 路径的 `session.close()` 未受影响。

### 测试验证

新增 `test_requests_profile_closes_session_on_request_exception`（`test_diagnose_web_access.py`）：

- `_SessionCloseSpy` 继承 `requests.Session`，记录 `close_count`。
- `_raise_diagnostic_request_exception` 模拟 `requests.Timeout`。
- monkeypatch `requests.Session` → `_SessionCloseSpy`，`_request_with_safe_redirects` → `_raise_diagnostic_request_exception`。
- 断言：`profile["status"] == "request_exception"`、`len(instances) == 1`、`instances[0].close_count == 1`。

验证 session 在异常路径被关闭恰好一次。✓

## New Findings

Fix 未引入 S1 内新 material issue：

- `_SessionCloseSpy` 使用类变量 `instances: list` 跟踪实例，测试入口重置为 `[]`，不会跨测试泄漏。✓
- `_raise_diagnostic_request_exception` 签名完整匹配 `_request_with_safe_redirects` 的参数，所有多余参数用 `del` 消除。✓
- Fix 不修改任何 S1 核心安全行为（peer proof、retry、redirect、response close、Playwright gate）。✓
- Fix 不引入新的 `getattr`/`hasattr`/`Any`/`object`/无类型签名。✓
- Fix 不触及 S2/S3/S4 边界。✓

**新 findings 计数：0**

## Blocking Questions

无。

## Completion Report

- **Verdict**: pass
- **R3-E-S1-CR-F01**: closed
- **New findings**: 0
- **Blocking questions**: 0
