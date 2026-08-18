# UF-FIX11 slice-boundary amendment review fix

## Gate 元数据

- Work unit：`UF-FIX11 company-metadata-ignored-change-warning`
- Gate：`plan amendment review -> fix -> re-review`
- 日期：2026-08-17
- Review artifact：`docs/reviews/uf-fix11-slice-amendment-review-ds-20260817.md`
- 修订计划：`docs/gateflow/uf-fix11-company-meta-warning-plan-20260817.md`
- Amendment：`docs/gateflow/uf-fix11-slice-boundary-amendment-20260817.md`
- 状态：Finding-001/002/003 与 OQ-1 均已文档修复
- 下一入口：`plan amendment re-review`

## Scope 与边界

本 fix 只收紧已接受业务设计的测试、符号、validation 与 commit 文件集，不重新打开 §1-§9 owner/typed contract/state machine。
未修改任何 production/test 现有 diff，未运行 pytest、coverage、pyright 或真实 CLI，未 stage/commit。

## Finding-001：blocker 测试新契约欠规格

- 裁决：`accepted / 已修复`
- Plan 证据：§10 S1+S2 `Exact changes：publication/warning/producer/parser` 新增 blocker 测试改写要求；同节
  `Tests：publication/warning/producer/parser` 冻结完整 exact assertions。
- Amendment 证据：`DS review fix 后的冻结契约 -> Blocker 测试 exact contract` 同步相同约束。
- 修复内容：测试最终必须为 `filing_action=update`、`status=skipped`；metadata-only begin/commit 各一次且 token exact
  对应；零 caller rollback；company stage token exact 对应且 source stage 为空；raw warnings 恰为唯一规范 warning；final
  `CompanyMeta` canonical JSON bytes（含 `company_name`、`updated_at`）不变；`published_tree_sha256` 与既有 source
  revision/version/meta/manifest/assets 不变。
- 原回归语义：明确保留 publication-lock fresh re-read 丢弃 stale preflight `create` action/旧 company decision，并按最终
  published truth 重算 `update + preserve_published`；禁止弱化为只测 warning/skip。

## Finding-002：combined regression 未绑定 acceptance

- 裁决：`accepted / 已修复`
- Plan 证据：§12.2 明确 combined regression 是 S1+S2 implementation review 与 accepted commit 的硬前置；§10
  `Completion / review / commit boundary` 同步列入该门槛。
- 修复内容：focused suite 后、进入 review 前必须全绿；review fix 修改代码/测试后，accepted commit 前必须再次全绿。
  任一失败或缺失都禁止 acceptance/stage/commit，不得递延到 S3；S3 后续重跑不能补认 S1+S2 缺失 evidence。

## Finding-003：共享 runtime 文件缺符号级边界

- 裁决：`accepted / 已修复`
- Plan 证据：§6.6 拆为 `6.6.1 原子 S1+S2` 与 `6.6.2 后续 S3`；§10 两个 slice 的 allowed files、exact
  changes、tests 与 stop conditions 同步符号边界。
- S1+S2 owner：`FinsUploadPipelineResult.warnings`、其 warnings/status invariant、
  `FinsUploadPipelineResult.from_pipeline_json(..., source_kind)`、`CompanyMetadataWarning` 闭集解析，以及
  `service_runtime.py` 四个 parser callsite 的显式 `SourceKind`。
- S3 owner：`FinsUploadResultSummary.warnings`/success-only invariant、`to_json_summary()`、
  `service_runtime._upload_summary_from_result` 与 direct/durable/CLI/tool projection。
- 防漂移：S1+S2 stop condition 禁止提前触碰 S3 symbols；S3 stop condition 禁止重写 pipeline parser/codec/四个 callsite。

## OQ-1：plan docs 与 S1+S2 code commit 文件集

- 裁决：`closed / 已修复`
- Plan 证据：§10 S1+S2 新增 `Plan-amendment gate commit boundary`，逐项列出完整 plan、blocker、amendment、
  DS/MiMo review、当前 fix、可选 re-review 与 acceptance artifacts；要求显式逐文件 stage、cached diff 证明零
  production/test path，禁止目录 glob。
- Plan-gate commit：建议 message 为 `gateflow: accept UF-FIX11 slice-boundary amendment`；当前 production/test partial
  diff 保留在工作区，绝不 stage，因此不会被误判为已提交红色中间态。
- S1+S2 code commit：只允许本 slice production/test implementation、accepted scope 内必要 README（当前正常为零）及
  slice implementation/review/fix/re-review/acceptance closeout artifacts；明确排除 blocker/amendment/plan review/fix/re-review/
  acceptance 与完整 plan。若需 README，必须先修订 allowed files。

## Changed files

- `docs/gateflow/uf-fix11-company-meta-warning-plan-20260817.md`
- `docs/gateflow/uf-fix11-slice-boundary-amendment-20260817.md`
- `docs/gateflow/uf-fix11-slice-amendment-review-fix-20260817.md`

## Validation 与 residual risks

- 文档修复依据：DS artifact 的 direct code/test evidence；本 gate 不执行代码验证。
- `fixed in current slice`：Finding-001/002/003 与 OQ-1 的计划规格缺口。
- `covered by later approved slice`：amendment re-review 接受后，由原子 S1+S2 关闭 blocker 与实现验证；由 S3 关闭
  summary/durable/direct/CLI/tool projection。若 re-review 未接受，则该分类失效并返回 fix。
- `assigned to later work unit`：真实 CLI evidence、scenario/oracle/frozen evidence，沿用 accepted plan owner。
- Unclassified residual risk：无。

## Completion status

Fix artifact 完整，所有 accepted findings 均为 `已修复`，OQ-1 已关闭。当前 amendment 尚未 accepted，不得恢复
implementation、stage production/test 或提交；下一入口为 `plan amendment re-review`。
