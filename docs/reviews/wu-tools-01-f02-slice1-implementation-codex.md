# WU-TOOLS-01-F02 Slice 1 Implementation Artifact

## Metadata

- Work unit: `WU-TOOLS-01-F02 Web CI diagnostics pipeline migration`
- Gate: `implementation`
- Slice: `Slice 1 Static OLD Pipeline Assets`
- Implementer: Codex
- Date: 2026-06-09
- Artifact path: `docs/reviews/wu-tools-01-f02-slice1-implementation-codex.md`

## Scope

本次只执行 Slice 1：迁移 shell wrappers 与 URL corpus。未新增 `utils/diagnose_web_access.py`，未新增 CI workflow，未运行 live diagnostics，未修改 tests、README、production Web tools、Host、Engine、Service、UI 或 controller artifacts。

## Changed Files

- `utils/diag_web.sh`
- `utils/diag_web_batch.sh`
- `utils/web_ci_urls.jsonl`
- `docs/reviews/wu-tools-01-f02-slice1-implementation-codex.md`

未修改 pre-existing dirty file：

- `docs/host/issues-implementation-control.md`

## Copied OLD Source Scope

- OLD source `utils/web_ci_urls.jsonl` 的 60 条 URL corpus record 已迁移到当前 `utils/web_ci_urls.jsonl`。内容与 OLD records 一致；当前文件补齐末尾换行，不改变 record 内容。
- OLD source `utils/diag_web.sh` 与 `utils/diag_web_batch.sh` 的 shell wrapper 语义已迁移：直接调用 `python -m utils.diagnose_web_access`，不依赖当前 repo 不存在的额外 CLI infrastructure。
- wrapper 默认输出根目录使用 `workspace/output/web_diagnostics`。
- wrapper 保留 headed browser、`chrome` channel、30 秒 manual wait 与 storage state directory 默认值；这些只在开发者显式手工运行 wrapper 时触发，不进入默认 CI 或测试路径。

## Implementation Notes

- `utils/diag_web.sh` 新增 shebang、`set -euo pipefail`、输出目录创建和 timestamped single-URL output path。
- `utils/diag_web_batch.sh` 新增 shebang、`set -euo pipefail`、输出目录创建和 timestamped batch output directory。
- 两个 wrapper 均把默认参数放在 `"$@"` 前，允许手工运行者追加参数覆盖或补充诊断选项。
- 当前 repo 仍没有 `utils/diagnose_web_access.py`；这是 Slice 2 的目标。Slice 1 保持直接 `python -m` 调用，并在本 artifact 中记录该 gap。

## Validations

```bash
bash -n utils/diag_web.sh utils/diag_web_batch.sh
```

Result: passed, no output.

```bash
python -c 'import json, pathlib; p=pathlib.Path("utils/web_ci_urls.jsonl"); rows=[json.loads(line) for line in p.read_text().splitlines() if line.strip()]; print(f"{len(rows)} rows")'
```

Result: passed, `60 rows`.

```bash
diff -u /Users/leo/workspace/dayu-agent/utils/web_ci_urls.jsonl utils/web_ci_urls.jsonl
```

Result: only final newline normalization differed; JSONL record content matched.

```bash
git diff --check
```

Result: passed, no output. Because Slice 1 files were newly added, this check was run after temporary `git add -N` intent-to-add for the new files, then the files were returned to unstaged/untracked status.

`pytest` not run: this Slice did not modify Python code or tests, and user instruction explicitly said pytest is not needed unless Python/test/README files are modified.

`pyright` not run: this Slice did not modify Python code, and user instruction explicitly said pyright is not needed unless Python/test/README files are modified.

## Docs Decision

- README files not updated. This Slice only adds opt-in `utils/` shell wrappers and corpus data; it does not add stable tests, change production architecture, or alter Host/Engine/Service/UI behavior.
- `tests/README.md` not updated because no tests were added or changed in Slice 1.
- Host/Engine README files not updated because no Host/Engine code, contract, state machine, or public boundary changed.

## Residual Risks / Uncovered Areas

| Risk | Classification | Owner / Destination | Notes |
|---|---|---|---|
| `python -m utils.diagnose_web_access` cannot run until `utils/diagnose_web_access.py` exists. | expected slice gap | WU-TOOLS-01-F02 Slice 2 | Slice 1 intentionally only migrates static assets. |
| Wrapper option parsing depends on Slice 2 implementing browser diagnostic CLI flags `--headed`, `--manual-wait-seconds` and `--storage-state-dir`. | expected slice handoff | WU-TOOLS-01-F02 Slice 2 | Channel handoff now uses accepted plan flag `--playwright-channel`; no OLD `--channel` compatibility is required. |
| URL corpus has not been exercised against live network/browser. | non-goal | WU-TOOLS-01-F02 Slice 2/F03 manual opt-in diagnostics | User instruction explicitly forbids running live diagnostics in Slice 1. |

无 unclassified residual risk。

## Completion Status

Slice 1 implementation complete. Per user instruction, stopped before Slice 2/3, review, fix, commit, push and PR gates.
