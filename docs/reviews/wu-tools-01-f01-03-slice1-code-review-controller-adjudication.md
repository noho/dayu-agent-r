# WU-TOOLS-01-F01-03 Slice 1 Code Review Controller Adjudication

## Scope

- Work unit: `WU-TOOLS-01-F01-03`
- Gate: Slice 1 code review
- Implementation artifact: `docs/reviews/wu-tools-01-f01-03-slice1-implementation-codex.md`
- Review artifacts:
  - `docs/reviews/wu-tools-01-f01-03-slice1-code-review-mimo.md`
  - `docs/reviews/wu-tools-01-f01-03-slice1-code-review-ds.md`
- Controller verification before review:
  - `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py -q`: 35 passed
  - `source .venv/bin/activate && pyright`: 0 errors
  - `git diff --check`: passed

## Review Verdicts

- AgentMiMo: `pass-with-findings`; 0 blocking findings.
- AgentDS: `pass-with-findings`; 0 blocking findings.

Controller verdict: accepted fix required before Slice 1 can be accepted.

## Findings Adjudication

### MIMO-S1: 模块级 docstring 未提及 upload 能力

- Source: `docs/reviews/wu-tools-01-f01-03-slice1-code-review-mimo.md`
- Severity: low
- Controller decision: accepted
- Reason: Slice 1 已将 upload request/result/runner/job lifecycle 纳入 `dayu.fins.ingestion_runtime`，模块 docstring 仍只写“下载与预处理”，会误导后续迁移实现者。
- Required fix: 更新模块 docstring，明确该模块承载 download / preprocess / upload ingestion job foundation，但仍不实现真实网络下载、真实上传 workflow、Host wait adapter、tool provider 或 CLI。

### MIMO-S2: `FinsIngestionJobRecord` docstring 未提及 upload

- Source: `docs/reviews/wu-tools-01-f01-03-slice1-code-review-mimo.md`
- Severity: low
- Controller decision: accepted
- Reason: `FinsIngestionOperationKind` 已新增 `UPLOAD`，record docstring 仍写 `operation_kind: 下载或预处理`，与当前 contract 不一致。
- Required fix: 将 `operation_kind` 描述更新为“下载、预处理或上传”，并核对同一类 docstring 中 `source` / `source_kind` 的描述是否需要包含 upload shape。

### DS-S1: `_save_cancelled` 绕过原子终态守护

- Source: `docs/reviews/wu-tools-01-f01-03-slice1-code-review-ds.md`
- Severity: low
- Controller decision: accepted
- Reason: 该问题不是 Slice 1 新增的专属 bug，但 Slice 1 的 upload 长事务路径复用了 `_save_cancelled`。在 future multi-runtime / multi-process job store 场景下，取消终态写入不应覆盖已经完成的 terminal record。由于 upload 是长事务，继续保留该缺口会扩大后续 Slice 的并发语义风险。
- Required fix: 为 job store 增加或等价实现“仅当当前 job 非终态时保存 cancelled 终态”的原子方法，并让 `_save_cancelled` 使用该语义。不能简单把 `_save_cancelled` 改成 `save_succeeded_or_cancelled`，因为 start 边界 create-after-cancel 场景需要在 record 尚无 `cancellation_requested=True` 时强制写入 cancelled。
- Required tests: 增加直接测试，证明当 job 已是 terminal record 时，`_save_cancelled` 不会把其覆盖成 `CANCELLED`；测试应覆盖生产 job store 或与 production 语义一致的 fake store。

### DS-S2: `_validate_upload_source_kind` 对 union 新增成员无穷尽防御

- Source: `docs/reviews/wu-tools-01-f01-03-slice1-code-review-ds.md`
- Severity: low
- Controller decision: accepted
- Reason: 当前 union 只有 filing/material 两个成员，不影响运行时正确性；但 Slice 1 正在建立后续 upload workflow 依赖的 contract，穷尽分支应由类型检查守护，避免未来新增 request 类型时静默按 material 通过。
- Required fix: 将 material 分支改成显式 `isinstance(request, FinsUploadMaterialRequest)`，并在尾部分支使用类型检查可感知的穷尽保护，例如 `typing.assert_never`。pyright 必须继续 0 errors。

## Deferred / Rejected Items

- Production upload runner 未接入：deferred-with-owner。由 accepted plan 的 Slice 4 承接，不属于 Slice 1 bug。
- Upload awaiting tool / wait adapter 未接入：deferred-with-owner。由 accepted plan 的 Slice 5 承接；若引入 awaiting external job / `start_upload` tracking，必须同步 GitHub Issue 129。
- Daemon-thread crash recovery：deferred-with-owner。由 WU-WAIT-02 / GitHub Issue 90 以及 existing Issue 129 tracking 承接。
- External job physical cancel / revoke：deferred-with-owner。由 WU-WAIT-03 / GitHub Issue 92 承接。

## Fix Gate Requirements

AgentCodex must implement only the accepted fixes above.

Allowed production files:

- `dayu/fins/ingestion_runtime.py`

Allowed test/doc files:

- `tests/fins/test_fins_ingestion_runtime.py`
- `dayu/fins/README.md` only if implementation changes require README sync after reading the target README update constraints
- `tests/README.md` only if test scope description changes require README sync after reading the target README update constraints
- `docs/reviews/wu-tools-01-f01-03-slice1-fix-codex.md`

Required validation:

- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py -q`
- `source .venv/bin/activate && pyright`
- `git diff --check`
