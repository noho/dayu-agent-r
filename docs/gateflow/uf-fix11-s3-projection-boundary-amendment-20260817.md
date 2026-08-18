# UF-FIX11 S3 Direct Projection Boundary Amendment

## Gate metadata

- work unit：`UF-FIX11 company-metadata-ignored-change-warning`
- gate：`S3 plan amendment`
- 日期：2026-08-17
- 分支：`codex/upload-filing-oracle`
- 前置 accepted slice：`5bb122d3`
- blocker：`docs/gateflow/uf-fix11-s3-projection-boundary-blocker-20260817.md`
- completion status：`ACCEPTED`
- implementation status：`PAUSED`
- blocking open questions：无

## Motivation and direct evidence

原 S3 已正确要求 direct terminal event 从 typed upload summary 复制 warnings，却把
`dayu/fins/ingestion_runtime.py` 的 symbol 白名单限制为 upload summary、invariant 与 serialization。真实代码中，
`FinsUploadResultSummary` 只在 `_direct_upload_terminal_events` 可见，`FinsResultSummary` 的 production 构造发生在
`_direct_result_event`。`direct_events.py` 只拥有 public contract，无法单独完成 typed copy。

因此问题真实且严重性准确：若不修订，只能静默丢失 direct warning、从 details/raw request 反推，或引入 side
channel/compatibility shim；这些路径都会破坏唯一 semantic owner。生产文件全集无需扩大，缺口只是既有 allowed
file 内的 symbol boundary 漏列。

## Accepted amendment proposal

### Frozen boundaries

- production、test、README allowed 文件全集不变。
- S1+S2 的 `FinsUploadPipelineResult` parser、closed warning codec、四个 `SourceKind` callsites、publication-final
  owner 与 storage contract 全部冻结。
- Host、Engine、material、oracle、scenario、registry、frozen/real CLI evidence 继续禁止修改。

### Direct typed copy symbols

S3 在 `dayu/fins/ingestion_runtime.py` 额外允许且只允许修改：

- `_direct_upload_terminal_events`：把 `FinsUploadResultSummary.warnings` exact 传给 direct builder；
- `_direct_result_event`：新增无默认值的 typed `warnings` 参数，并传入 `FinsResultSummary`；
- `_emit_claimed_direct_result`：作为唯一 generic/non-upload helper callsite 显式传 `warnings=()`。

`_direct_result_event` 禁止提供 warnings 默认值。这样每个 production producer 都必须显式声明该事实，pyright 与结构
测试可捕获未来漏传。upload producer 不得复制、重新 parse 或构造 warning，只能传同一个 immutable tuple。

### Public summary empty state

`FinsResultSummary.warnings` 使用 `tuple[CompanyMetadataWarning, ...] = ()`。这是跨 download/preprocess/upload
operation 的自然业务空状态：绝大多数合法终态不存在 company metadata warning。它不是 compatibility fallback，
因为：

- producer helper 的参数仍必填且无默认值；
- `__post_init__` exact 校验 tuple 元素、最多一个 warning 与仅 SUCCESS 可非空；
- direct upload owner tests 必须断言 uploaded/skipped exact copy；
- failed/cancelled 与 generic non-upload tests 必须断言空值。

把 public field 改为 required 会迫使修改大量与本事实无关的 download/preprocess 构造点及当前 S3 allowed files 之外
的测试，仅用于重复表达自然空状态，增加耦合而不提升 upload copy 的严格性，因此拒绝。

`FinsUploadResultSummary.warnings` 同样使用 `tuple[CompanyMetadataWarning, ...] = ()`，但 service projection
必须显式传 `result.warnings`，不得依赖默认值。它的可携带 warning 状态闭集精确为 `ok`/`skipped`；
`failed`/`cancelled`/`deleted` 必须为空。`_direct_result_event` 收到 CANCELLED + 非空 warning 时禁止静默归零，
必须让 `FinsResultSummary` constructor invariant fail closed。

## Test and static contract

测试文件仍限原 S3 allowed list，按 owner 分工：

- `tests/fins/test_fins_ingestion_runtime.py` 覆盖 `FinsUploadResultSummary` 的 exact-element、at-most-one 与
  `ok`/`skipped` success-only invariant；非精确元素、超过一个、`failed`/`cancelled`/`deleted` + 非空都拒绝。
- 同一文件覆盖 uploaded/skipped exact warning copy、uploaded 空值 exact copy、failed/cancelled/deleted 与
  generic non-upload 空值，以及 CANCELLED + 非空 direct result fail closed。
- 同一文件的 AST contract 穷举 `ingestion_runtime.py` 中 `_direct_result_event` 的全部 `Call` 节点：数量必须
  exact 为两个，warnings 实参集合必须 exact 为 `summary.warnings` 与 `()`；新增任何 callsite 立即红。
- `tests/fins/test_fins_direct_stream.py` 只覆盖 `FinsResultSummary` public invariant 与 stream contract：非精确
  元素、超过一个、FAILURE/CANCELLED + 非空拒绝，以及 SUCCESS 正例；禁止 import ingestion runtime private helper。

其余 summary/durable/CLI/wait tests 与 validation 命令保持 accepted S3 plan 不变。实现若需要第三个 production
callsite、修改 S1+S2 parser/codec、从 raw fields 推断或扩大文件范围，必须再次停止。

`_observation_failure_result`、`_observation_cancelled_result`、`_mark_observation_failed` 是非 SUCCESS observation
构造点，保持 `FinsResultSummary.warnings=()` 的自然空状态；S3 禁止修改这三个函数。它们不属于 direct typed copy
symbol 白名单。

## Review and commit boundary

本 amendment 必须经过 MiMo/DS 双路 plan review、controller adjudication、必要 fix 与双路 re-review。acceptance 后
形成独立 plan-gate commit，才可恢复 S3 implementation。

plan-gate commit 只允许包含：

- `docs/gateflow/uf-fix11-company-meta-warning-plan-20260817.md`
- `docs/gateflow/uf-fix11-s3-projection-boundary-blocker-20260817.md`
- 本 amendment artifact
- 本 amendment 的双路 review、fix、re-review 与 acceptance artifacts

禁止 stage production、test 或 README。建议 commit message：
`gateflow: accept UF-FIX11 S3 projection boundary amendment`。

## Residual classification

- `must close in this amendment`：direct typed copy symbol 漏列与 helper/default 参数策略。
- `covered by resumed S3`：summary、durable、direct、CLI、wait、README implementation 与验证。
- `assigned to later work unit`：S1+S2 acceptance 已记录的运维与未来 material warning residuals，不受本修订影响。
- 未分类 residual risk：无。

## Completion status

本 plan amendment 已通过双路 initial review、controller review-fix 与双路定向 re-review，并由 controller
接受。S3 implementation 在独立 plan-gate commit 创建前仍暂停；该 commit 不得包含 production/test/README diff。
