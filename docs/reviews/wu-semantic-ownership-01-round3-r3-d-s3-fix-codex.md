# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-D S3 Code Review Fix

## Artifact Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / Round3 / R3-D`
- Slice: `S3 — Fiscal And Normalization Owners, SEC Version Alignment, Docs And Aggregate Closure`
- Gate: `code review fix`
- Agent: `AgentCodex`
- Status: `fix-complete`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s3-code-review-controller-adjudication.md`
- Artifact path: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s3-fix-codex.md`
- Stop boundary: 本次只完成 accepted finding fix；未进入 re-review、commit 或 R3-E。

## Scope And First-Principles Judgment

`R3-D-S3-CR-F01` 成立且严重度为 low。`dayu/fins/processors/sec_xbrl_query.py` 的可选浮点转换 helper 是普通 `float(...)` 转换失败语义的 owner；原 `except Exception` 会把非转换异常也错误投影为缺失值。将捕获范围收窄到 `TypeError` 和 `ValueError` 位于 owner boundary，保留现有普通转换失败返回 `None` 的行为，不需要下游 fallback、兼容分支或额外重构。

review finding 使用 `_safe_float(...)` 名称描述该 helper；当前代码中的实际函数名为 `_to_optional_float(...)`，controller 指定的文件、定位行和 `except Exception` 行为均唯一对应此函数。

## Changed Files

- `dayu/fins/processors/sec_xbrl_query.py`
  - 仅将 `_to_optional_float(...)` 的 `except Exception` 收窄为 `except (TypeError, ValueError)`。
- `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s3-fix-codex.md`
  - 新增本 fix gate artifact。

未修改其它文件；工作区原有 S3 changes 不属于本 fix 新增改动。

## Finding Status

| Finding | Controller decision | Fix status | Evidence |
| --- | --- | --- | --- |
| `R3-D-S3-CR-F01` | accepted / low | 已修复 | `_to_optional_float(...)` 仅捕获 `TypeError`、`ValueError`；普通 `float(...)` 转换失败仍返回 `None`，其它异常不再被静默吞掉。 |

## Validation Results

所有 Python 命令均在 `source .venv/bin/activate` 后执行。

- `pytest tests/fins/test_fiscal_normalization_contracts.py tests/fins/test_read_runtime_semantic_ownership_guards.py -q`：`37 passed, 3 warnings`。
- `pytest tests/fins/test_sec_pipeline_download.py -q -k 'xbrl or 6k or skip or not_modified or download_version'`：`12 passed, 24 deselected, 3 warnings`。
- `python -m pyright dayu/ tests/ utils/`：`0 errors, 0 warnings, 0 informations`。
- `git diff --check`：通过。

pytest warnings 均为既存 edgartools deprecated import warnings；本 fix 未新增测试失败、类型错误或格式错误。

## README Decision

不更新 README。本 fix 只收窄内部转换 helper 的异常捕获范围，不改变财报业务契约、用户可见行为、安装/CLI 工作流、分层关系或测试组织；现有 README 职责范围内没有需要新增或修订的事实。

## Residual Risks And Uncovered Areas

- **Assigned to later work unit:** SEC downloader 的 `errors="ignore"` 路径仍由后续 Fins downloader decode-policy owner 处理；不在本 fix allowed files 内。
- **Assigned to later work unit:** broad `DocumentMeta` type migration 与 6-K BS-only routing 仍按 accepted plan 交由后续 owner；本 fix 未改变其状态。
- **Tracked dependency warning:** edgartools deprecated import warnings 仍由依赖升级工作处理，不影响本 finding 的 correctness。

没有未分类 residual risk；本次限定 finding 已完全修复。

## Scope Confirmation

- 未进入 re-review、commit 或 R3-E。
- 未修改 R3-E、Host、Engine、upload/download security 或 tool-security 文件。
- 未新增 fallback、compat、loose parsing 或其它逻辑变更。
- Blocking questions: 无。
