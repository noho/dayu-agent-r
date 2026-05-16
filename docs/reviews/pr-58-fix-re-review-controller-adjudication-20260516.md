# PR 58 Fix Re-Review Controller Adjudication - 2026-05-16

## Gate

当前 gate：PR 58 review fix re-review。

输入：

- `docs/reviews/pr-58-review-controller-adjudication-20260516.md`
- `docs/reviews/pr-58-fix-codex-20260516.md`
- `docs/reviews/pr-58-fix-re-review-ds-20260516.md`

## Controller Verdict

PASS。

PR58-F1 已修复，AgentDS re-review 确认 fixed。该 fix 包可进入 accepted PR review commit。

## Fixed Finding

### PR58-F1 RuntimeFileLock `__exit__` release failure clears active token too early

状态：fixed。

证据：

- `RuntimeFileLock.__exit__` 现在先调用 `token.release()`，只有 release 成功后才清空 `_active_token`。
- release 失败时异常继续传播，`_active_token` 保留，后续同实例 `acquire(timeout_seconds=0)` 被 active-token guard fail fast。
- `tests/runtime/test_filelock.py` 增加 release failure regression test。

## Validation

Controller 已复跑：

```bash
source .venv/bin/activate
pytest tests/runtime/test_filelock.py -q
pytest tests/host tests/runtime -q
python -m pyright dayu/ tests/ utils/
git diff --check
```

结果：

- filelock tests：13 passed
- Host + runtime tests：530 passed
- pyright：0 errors, 0 warnings, 0 informations
- diff check：clean

## Non-Blocking / Deferred Items

- MiMo low findings about marker restore logging / no-op marker touch remain non-blocking runtime hardening.
- DS F2-F6 and TG1-TG5 remain rejected or deferred per `docs/reviews/pr-58-review-controller-adjudication-20260516.md`.
