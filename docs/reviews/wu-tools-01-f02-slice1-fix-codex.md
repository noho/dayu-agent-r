# WU-TOOLS-01-F02 Slice 1 Fix Artifact

## Metadata

- Work unit: `WU-TOOLS-01-F02 Web CI diagnostics pipeline migration`
- Gate: `fix`
- Slice: `Slice 1 Static OLD Pipeline Assets`
- Fixer: Codex
- Date: 2026-06-09
- Artifact path: `docs/reviews/wu-tools-01-f02-slice1-fix-codex.md`

## Scope

本次只修 Controller accepted finding：两个 shell wrapper 的 browser channel 参数名与 accepted plan 不一致。未执行 Slice 2/3，未修改 review/controller artifacts、tests、README、production code 或 `utils/web_ci_urls.jsonl`。

## Changed Files

- `utils/diag_web.sh`
- `utils/diag_web_batch.sh`
- `docs/reviews/wu-tools-01-f02-slice1-implementation-codex.md`
- `docs/reviews/wu-tools-01-f02-slice1-fix-codex.md`

## Fixed Finding

- Controller accepted finding: wrappers passed `--channel chrome`, while accepted plan requires `--playwright-channel <channel>`.
- Fix: both wrappers now pass `--playwright-channel chrome` to `python -m utils.diagnose_web_access`.
- Preserved behavior: `--headed`, `--manual-wait-seconds 30` and `--storage-state-dir` remain in both wrappers because they are browser diagnostic CLI options that Slice 2 parser must implement.
- Implementation artifact update: residual risk no longer requires OLD `--channel` compatibility; it only records remaining Slice 2 parser handoff for `--headed`, `--manual-wait-seconds` and `--storage-state-dir`.

## Validation

```bash
bash -n utils/diag_web.sh utils/diag_web_batch.sh
```

Result: passed, no output.

```bash
git diff --check
```

Result: passed, no output.

`pytest` not run: this fix did not modify Python code, tests, README, or production code.

`pyright` not run: this fix did not modify Python code or typed interfaces.

## Blocking Open Questions

None.
