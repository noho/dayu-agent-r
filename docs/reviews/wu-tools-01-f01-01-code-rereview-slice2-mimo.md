# WU-TOOLS-01-F01-01 Slice 2 Code Re-Review — MiMo

## Work Unit / Gate / Slice

- Work unit: `WU-TOOLS-01-F01-01` Fins filelock convergence to `dayu.runtime.filelock`
- Gate: code re-review
- Slice: Slice 2 - storage batch lock convergence
- Reviewer: AgentMiMo

## Verdict

**pass**

## A1 Re-Review Status

**已修复**

## Evidence

### Fix 验证

- 文件: `dayu/fins/storage/_fs_storage_infra.py:501-502`
- 当前代码:
  ```python
  cached_token = self._ticker_lock_tokens.pop(ticker, None)
  effective_token = cached_token or token
  ```
- 预期: `_release_ticker_lock` 必须保持无条件 pop `_ticker_lock_tokens`，并优先使用 popped cached token，再 fallback 到显式 token。
- 实际: 无条件 pop 语义保持不变；effective token 选择逻辑为 `cached_token or token`，cached token 优先。与预期完全一致。

### 调用方分析

| 调用方 | 位置 | 传参 | 影响 |
|---|---|---|---|
| `begin_batch` error path | `:195` | `token=lock_token` | lock_token 已存入 `_ticker_lock_tokens[ticker]`，cached_token == token，行为不变 |
| `commit_batch` finally | `:257` | 无显式 token | 依赖 cached_token pop，行为不变 |
| `rollback_batch` finally | `:291` | 无显式 token | 依赖 cached_token pop，行为不变 |

### 语义改进

修复前 `token or cached_token` 在 cached_token 与 token 为同一对象时功能正确，但优先级语义倒置——显式 token 覆盖了 `_acquire_ticker_lock` 创建并存入 dict 的权威 cached token。修复后 `cached_token or token` 准确表达了 cached token 作为锁持有权威来源的语义，显式 token 仅作为 cached miss fallback。

## Validation Performed

| 命令 | 结果 |
|---|---|
| `source .venv/bin/activate && pytest tests/fins/test_fins_storage_provider.py tests/fins/test_fins_ingestion_runtime.py -q` | 38 passed |
| `source .venv/bin/activate && pytest tests/runtime/test_filelock.py tests/runtime/test_import_boundary.py -q` | 23 passed |
| `source .venv/bin/activate && pyright dayu/fins/storage/_fs_storage_infra.py` | 0 errors |
| `_release_ticker_lock` 无条件 pop 语义检查 | PASS — `pop(ticker, None)` 无条件执行 |
| effective_token 优先级检查 | PASS — `cached_token or token` |

## Residual Risks / Uncovered Areas

- Low: `_release_ticker_lock` 仍依赖 `RuntimeFileLockToken.release()` 的幂等语义处理重复引用释放路径；该语义属于 `dayu.runtime.filelock` contract，并已由 runtime filelock 测试覆盖。
- None blocking: 本次 fix 不改变锁获取、释放异常传播、batch commit/rollback public behavior 或测试边界。

## Blocking Open Questions

无。
