# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-E Slice S1 Code Review Re-Review — AgentDS

## Re-review metadata

- **Reviewer**: AgentDS
- **Review type**: S1 code-review fix re-review（只验证 accepted finding 闭合，不修改代码，不 stage/commit/push）
- **Original reviews**:
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s1-code-review-mimo.md` (MiMo, pass, 1 low cosmetic finding)
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s1-code-review-ds.md` (DS, pass-with-findings, 1 low finding: F-01)
- **Fix artifact**: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s1-code-review-fix-codex.md`
- **Timestamp**: 20260713-131515

## Scope

只验证 accepted finding `R3-E-S1-CR-F01` 是否在 current git diff 中闭合，以及 fix 是否在 S1 范围内引入新的 material issue。不重新审查 S2/S3/S4，不重新审查已在 original review 中 verified 的 S1 正向行为。

## R3-E-S1-CR-F01 closure verification

### Original finding (AgentDS F-01)

- **位置**: `utils/diagnose_web_access.py:1344-1356`
- **问题**: `_build_requests_profile` 的 `except (requests.RequestException, RuntimeError)` 分支中，`session.close()` (line 1355) 位于 `return profile` (line 1354) 之后，不可达。局部创建的 `requests.Session` 在该异常路径下未关闭，造成连接池泄漏。

### Fix applied (verified from git diff)

**`utils/diagnose_web_access.py`**:

```diff
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
+        session.close()
         return profile
-        session.close()
-        return profile
```

修改内容：
- `session.close()` 从 `return profile` **之后**（不可达）移至 `return profile` **之前** ✓
- 删除不可达的 `session.close()` 与重复 `return profile` ✓
- `_FetchUrlSafetyError` 路径的 `session.close()` (line 1342) 保持不变 ✓
- 成功路径的 `finally: session.close()` (line 1387) 保持不变 ✓

**`tests/tools/web/test_diagnose_web_access.py`**:

新增 `test_requests_profile_closes_session_on_request_exception`:
- `_SessionCloseSpy` 继承 `diag.requests.Session`，override `close()` 记录 `close_count` ✓
- `_raise_diagnostic_request_exception` 模拟 `_request_with_safe_redirects` 抛出 `requests.Timeout` ✓
- 测试断言 `profile["status"] == "request_exception"` ✓
- 测试断言 `len(_SessionCloseSpy.instances) == 1` 且 `close_count == 1` ✓

### Closure evidence summary

| 验证点 | 状态 | 证据 |
|---|---|---|
| `session.close()` 移至 `return profile` 之前 | ✓ | diff `utils/diagnose_web_access.py` line 1354 |
| 不可达代码删除 | ✓ | 旧 line 1355-1356 已删除 |
| 测试覆盖异常路径 session close | ✓ | `test_requests_profile_closes_session_on_request_exception` |
| 测试断言 `close_count == 1` | ✓ | `assert _SessionCloseSpy.instances[0].close_count == 1` |
| 其他路径 session close 未被破坏 | ✓ | `_FetchUrlSafetyError` 路径 `session.close()` + 成功路径 `finally: session.close()` 均保持 |
| Pyright | ✓ | Fix artifact reports 0 errors, 0 warnings |
| Tests | ✓ | 88 passed, 1 skipped (新增 1 test) |

**Verdict**: `R3-E-S1-CR-F01` **CLOSED**. 修复正确，测试覆盖。

## Additional observations

### MiMo-01 (cosmetic) — implicitly resolved

AgentMiMo 的 finding 01 指出 success-path `session.close()` 位置不明显。当前 fix 虽然未移动 success-path 的 `session.close()`（该路径仍通过 line 1387 `finally: session.close()` 关闭），但 fix 统一了异常路径的 close-before-return 模式。success-path 的 `finally` 覆盖是正确的——`with lease:` 块内的 `return profile` 在退出 context 后、函数返回前执行 `finally`。MiMo finding 是 cosmetic，DS finding 是 concrete bug，后者已修复。

### No new S1 material issues

对 fix diff 的 adversarial review 确认：

1. **`_SessionCloseSpy` class variable `instances`** — 类级别列表，测试开头重置。pytest 默认顺序执行，无并发问题。✓
2. **`_raise_diagnostic_request_exception` 函数签名** — 匹配 `_request_with_safe_redirects` 的完整参数列表，包含 `normalize_url_for_http` 和 `cancellation_token`。✓
3. **`test_requests_profile_records_raw_response_byte_length` 测试更新** — 从旧的 `FakeSession`/`FakeResponse` 模式迁移到 monkeypatch `_request_with_safe_redirects` + `AuthorizedResponseLease`。测试现在使用 `WebEgressPolicy(allow_private_network=True)` 传递 egress policy 而非 `allow_private_network_url=True` flag。✓
4. **`test_url_safety_rejects_private_and_local_hosts_by_default` 测试更新** — 从调用已删除的 `_validate_url_safety`/`_is_private_or_local_host` 迁移到 `WebEgressPolicy.authorize_http_target`。测试保持私网拒绝 + IPv4-mapped IPv6 拒绝语义。✓
5. **新增 diagnostic 测试 `test_diagnostic_requests_egress_rejection_uses_shared_policy`** — 验证 raw requests 诊断路径由 shared `WebEgressPolicy` 在请求发送前拒绝私网 URL。✓
6. **新增 diagnostic 测试 `test_diagnostic_playwright_public_egress_is_typed_unavailable`** — 验证公网 browser direct 返回 `browser_egress_policy_unavailable`。✓

所有测试更新均从旧 API（`allow_private_network_url` flag、`_validate_url_safety`、`FakeSession`）迁移到新 API（`WebEgressPolicy`、`_request_with_safe_redirects`、`AuthorizedResponseLease`），无旧 API 残余。

### S1 scope boundary preserved

Fix 仅修改 `utils/diagnose_web_access.py`（1 行移动 + 原有 S1 改动）和 `tests/tools/web/test_diagnose_web_access.py`（测试更新 + 新增）。无 S2/S3/S4 文件变更。无 Host/Engine/Fins/Documents 文件变更。

## Re-review conclusion

**Verdict: pass**

- `R3-E-S1-CR-F01` — **CLOSED**（`session.close()` 正确移至 `return` 之前，不可达代码删除，测试覆盖）
- New S1 material issues — **0**
- S1 scope boundary — **preserved**
- Blocking questions — **0**

S1 implementation 在 fix 后无已知 material defect。建议 controller 接受 S1 并进入 S2 implementation gate。

## Completion report

- **Verdict**: pass
- **Artifact path**: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s1-rereview-ds.md`
- **Fixed ID verified closed**: R3-E-S1-CR-F01 ✓
- **New findings**: 0
- **Blocking questions**: 0
- **S1 scope boundary**: preserved
- **Tests**: 88 passed, 1 skipped
- **Pyright**: 0 errors
