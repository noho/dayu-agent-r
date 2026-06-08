# WU-TOOLS-01-F01-01 Code Re-Review — Slice 2 (AgentDS)

## Review Metadata

- **Reviewer**: AgentDS
- **Work Unit**: WU-TOOLS-01-F01-01 Fins filelock convergence to dayu.runtime.filelock
- **Slice**: Slice 2 — code re-review（复核 accepted fix A1）
- **Gate**: code re-review
- **Adjudication Source**: `docs/reviews/wu-tools-01-f01-01-code-review-slice2-controller-adjudication.md`
- **Fix Artifact**: `docs/reviews/wu-tools-01-f01-01-fix-slice2-codex.md`
- **Original Review Artifacts**:
  - `docs/reviews/wu-tools-01-f01-01-code-review-slice2-mimo.md`
  - `docs/reviews/wu-tools-01-f01-01-code-review-slice2-ds.md`

## Verdict: PASS

A1 已完整修复，无 residual issue。

---

## A1 Re-Review

### Finding Summary

- **Source**: MiMo F1; DS F3.
- **Controller Decision**: accepted.
- **Required Fix**: `_release_ticker_lock` 必须保持无条件 pop `_ticker_lock_tokens`，并优先使用 popped cached token，再 fallback 到显式 token。预期为 `effective_token = cached_token or token` 或等价逻辑。

### Re-Review Status: 已修复

### Evidence

**文件**: `dayu/fins/storage/_fs_storage_infra.py`，第 501–502 行：

```python
cached_token = self._ticker_lock_tokens.pop(ticker, None)
effective_token = cached_token or token
```

逐项验证：

| 要求 | 实际代码 | 状态 |
|---|---|---|
| 无条件 pop `_ticker_lock_tokens` | 第 501 行 `pop(ticker, None)`，无任何条件分支包裹 | 满足 |
| 优先使用 popped cached token | 第 502 行 `cached_token or token`，cached 在前 | 满足 |
| cached token 缺失时 fallback 到显式 token | `or token` 提供 fallback | 满足 |
| `effective_token is None` 时 early return（无锁可释放） | 第 503–504 行 | 语义保持 |

**调用点一致性验证**：

| 调用点 | 行号 | 传参 | 行为 |
|---|---|---|---|
| `begin_batch` 异常路径 | 195 | `token=lock_token`（与 cached 同对象） | cached 优先，语义正确 |
| `commit_batch` finally | 257 | 无显式 token | 纯依赖 cached，语义正确 |
| `rollback_batch` finally | 291 | 无显式 token | 纯依赖 cached，语义正确 |

三个调用点均与修复后语义一致，无新增风险路径。

---

## Validation Performed

| 验证项 | 方法 | 结果 |
|---|---|---|
| 无条件 pop 语义 | 直接读取第 501 行 | 确认 |
| cached-or-token 优先级 | 直接读取第 502 行 | 确认 |
| 调用点一致性 | 全文搜索 `_release_ticker_lock` 调用 | 3 处调用，全部兼容 |
| 修复文档一致性 | 对比 fix artifact 与代码 | 完全一致 |
| pyright | fix artifact 报告 0 errors | 采信 |
| 测试 | fix artifact 报告 61 passed | 采信 |

---

## Residual Risks / Uncovered Areas

- `_release_ticker_lock` 仍依赖 `RuntimeFileLockToken.release()` 的幂等语义处理重复释放路径；该语义属于 `dayu.runtime.filelock` contract，已由 runtime filelock 测试覆盖。**风险等级: Low。**
- `dayu/fins/_file_lock.py` 删除仍为 Slice 3 范围，不在本次复核范围内。
- 其他 controller rejected-with-reason 的 findings（R1–R4）不在本次复核范围内。

---

## Blocking Open Questions

无。
