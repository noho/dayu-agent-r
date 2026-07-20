# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-F Final Closeout

## 结论

Round3 R3-F CLI / Config / Packaging / Public Documentation / Runtime Numeric Contracts 已完成本地 final closeout。所有 R3-F accepted findings 与 code-review accepted finding 均已修复，controller validation 通过。

这不是 umbrella WU 的最终 closeout。Round3 controller adjudication 仍接受了 R3-A、R3-B、R3-C、R3-D、R3-E；umbrella WU 需要继续推进后续 sub WU。

## 输入与裁决

- Round3 controller adjudication: `docs/reviews/wu-semantic-ownership-01-fullrepo-deepreview-round3-controller-adjudication.md`
- R3-F plan: `docs/host/wu-semantic-ownership-01-round3-r3-f-cli-config-public-contract-plan.md`
- R3-F implementation: `docs/reviews/wu-semantic-ownership-01-round3-r3-f-implementation-codex.md`
- R3-F code review MiMo: `docs/reviews/wu-semantic-ownership-01-round3-r3-f-code-review-mimo.md`
- R3-F code review DS: `docs/reviews/wu-semantic-ownership-01-round3-r3-f-code-review-ds.md`
- R3-F code review controller adjudication: `docs/reviews/wu-semantic-ownership-01-round3-r3-f-code-review-controller-adjudication.md`
- R3-F code-review fix: `docs/reviews/wu-semantic-ownership-01-round3-r3-f-code-review-fix-codex.md`

MiMo 与 DS 对初始 implementation 均 PASS。Controller 追加接受 `R3-F-CR-01`，要求收窄 `dayu-cli init` staging install rollback 的异常边界。该 finding 已修复。

## Fixed Scope

- `dayu-cli init` 写入 `config/` 的 symlink-safe validation、staging、backup 与 rollback。
- Python 3.11 packaging / Docling `transformers` runtime contract。
- `prompt` / `interactive` / `session resume --mode interactive` 共享 scene context subject slot。
- `upload_filings_from` JSON argv public output contract。
- 删除无 owner 的旧 CLI flags 和 downstream unsupported-option shim。
- `dayu.runtime.numeric` finite-number owner 与 config/runtime/service 消费边界。
- README / Config README / Tests README 与当前 public contract 同步。

## Final Controller Validation

```text
pytest tests/cli/test_init_command.py -q
17 passed, 3 warnings

python -m pyright dayu/ tests/ utils/
0 errors, 0 warnings, 0 informations

git diff --check
passed

rg -n "except BaseException" dayu/cli dayu/runtime dayu/service
no matches

pytest -q
3930 passed, 3 skipped, 5 deselected, 3 warnings
```

Warnings are existing `edgar` deprecation warnings from installed dependencies, not introduced by R3-F.

## Residuals

- R3-F does not implement a cross-process lock for two concurrent `dayu-cli init` invocations on the same workspace.
- R3-F does not rebuild a fresh minimum Python 3.11 environment for Docling model initialization; metadata and constraints are locked by tests.
- `upload_filings_from` JSON argv is an intentional breaking public output change; no legacy shell renderer is retained.
- Runner-call hot payload stress remains assigned to R3-A.

## Next Entry Point

Proceed to Round3 R3-A Host lifecycle / wait / admin / durable integrity, unless the controller reorders R3-A-R3-E based on dependency evidence.
