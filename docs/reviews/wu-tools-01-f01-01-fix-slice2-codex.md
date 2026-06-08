# WU-TOOLS-01-F01-01 Fix Slice 2 - Codex

## Work Unit / Gate / Slice

- Work unit: `WU-TOOLS-01-F01-01` Fins filelock convergence to `dayu.runtime.filelock`
- Gate: `fix`
- Slice: Slice 2 - code review accepted fix

## Accepted Finding Fixed

- A1: `_release_ticker_lock` 在无条件 `pop` `_ticker_lock_tokens` 后，应优先使用弹出的 cached token，并只在 cached token 缺失时 fallback 到显式 `token`。

## Files Changed

- `dayu/fins/storage/_fs_storage_infra.py`
- `docs/reviews/wu-tools-01-f01-01-fix-slice2-codex.md`

## Exact Changes

- 在 `_release_ticker_lock` 中保留 `cached_token = self._ticker_lock_tokens.pop(ticker, None)` 的无条件 pop 语义。
- 将 effective token 选择从显式 token 优先改为 cached token 优先：

```python
effective_token = cached_token or token
```

- 未改变 public behavior、异常语义、测试或 runtime/ingestion 代码。
- 已检查 `dayu/fins/README.md` 的 Agent 更新约束；本次改动只清晰化私有锁释放优先级，不改变 Fins 稳定能力、公共契约或架构边界，因此不更新 README。

## Validation Commands and Results

| Command | Result |
|---|---|
| `source .venv/bin/activate && pytest tests/fins/test_fins_storage_provider.py tests/fins/test_fins_ingestion_runtime.py -q` | PASS: 38 passed, 3 existing edgar deprecation warnings |
| `source .venv/bin/activate && pytest tests/runtime/test_filelock.py tests/runtime/test_import_boundary.py -q` | PASS: 23 passed |
| `source .venv/bin/activate && pyright dayu/fins/storage/_fs_storage_infra.py tests/fins/test_fins_storage_provider.py tests/fins/test_fins_ingestion_runtime.py` | PASS: 0 errors, 0 warnings, 0 informations; pyright version notice only |
| `source .venv/bin/activate && pyright` | PASS: 0 errors, 0 warnings, 0 informations; pyright version notice only |
| `git diff --check` | PASS: no output |

## Blocking Open Questions

- 无。

## Residual Risks Classification

- Low: `_release_ticker_lock` 仍依赖 `RuntimeFileLockToken.release()` 的幂等语义处理重复引用释放路径；该语义属于 `dayu.runtime.filelock` contract，并已由 runtime filelock 测试覆盖。
- None blocking: 本次 fix 不改变锁获取、释放异常传播、batch commit/rollback public behavior 或测试边界。
