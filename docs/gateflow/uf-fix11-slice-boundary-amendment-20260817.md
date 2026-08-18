# UF-FIX11 slice-boundary plan amendment

## Gate 元数据

- Work unit：`UF-FIX11 company-metadata-ignored-change-warning`
- Gate：`plan amendment review -> fix -> re-review`
- 日期：2026-08-17
- 分支：`codex/upload-filing-oracle`
- 状态：`accepted`
- 修订计划：`docs/gateflow/uf-fix11-company-meta-warning-plan-20260817.md`
- blocker：`docs/gateflow/uf-fix11-s1-slice-boundary-blocker-20260817.md`
- DS review：`docs/reviews/uf-fix11-slice-amendment-review-ds-20260817.md`
- fix artifact：`docs/gateflow/uf-fix11-slice-amendment-review-fix-20260817.md`
- acceptance：`docs/gateflow/uf-fix11-slice-amendment-acceptance-20260817.md`
- 下一入口：原子 `S1+S2 implementation`

## 动机与直接证据

原 Slice 1/2 的业务设计成立，但 implementation boundary 不成立。原 Slice 1 要求 fresh 不同名称产生
`stage/preserve_published` intent；现有 `_canonical_skip_requirements_are_met` 又只允许 `keep/no intent` 进入 canonical skip。
因此 domain producer 一落地，同内容 fresh recheck 就从预期 `skipped` 变为 `ok`。完整 Slice 1 focused suite 已以
`639 passed, 1 failed` 证明该冲突，失败测试为
`test_upload_filing_fresh_recheck_discards_stale_action_and_company_decision`。

正确 owner 修复必须让 intent/outcome、storage return、publication arbitration/metadata-only skip、warning codec、SEC/CN
terminal producer 和 strict parser/显式 `SourceKind` 在同一可绿 slice 收敛。丢弃 intent、修改旧测试期望或提前提交红色
domain/storage diff都会固化错误语义。

## 修订决策

1. 原 Slice 1 与 Slice 2 合并为不可拆分的原子 `S1+S2`。
2. 当前原 Slice 1 dirty diff 保留为 `S1+S2` partial implementation，不回退、不单独接受、不单独提交。
3. `S1+S2` allowed files 是原两 slice 的精确并集；不扩张 Host、Engine、material、oracle、scenario、registry 或 frozen evidence。
4. `S1+S2` 用一个完整 focused suite、§12.2 combined regression、逐文件 coverage、全仓 pyright、static checks 和一个 implementation review/fix/re-review loop 验收；任一红测、coverage/type failure 都禁止 implementation artifact acceptance 与 commit。
5. 只有完整 review loop 通过后才允许一个 accepted `S1+S2` slice commit；禁止为原 Slice 1/2 或任何红色中间态分别提交。
6. 原 Slice 3 改为后续 `S3 public/durable/CLI/tool projections`，只复用 S1+S2 已冻结的 warning/parser contract，不重新判断业务事实。
7. blocker 测试的新契约固定为 `skipped + metadata-only commit`：begin/commit 各恰一次且同 token、零 rollback、company stage 使用同 token、raw warnings 恰为规范 warning、final CompanyMeta canonical bytes（含 `updated_at`）与全部既有 source/tree hash 不变；同时继续证明 publication-lock fresh re-read 丢弃 stale preflight action/decision。
8. 两个共享 runtime 文件按符号拆分：S1+S2 只拥有 `FinsUploadPipelineResult` warning parser/invariant 与四个 service parser `SourceKind` callsite；S3 才拥有 `FinsUploadResultSummary.warnings`/`to_json_summary()`、`_upload_summary_from_result` 及 direct/durable projection。
9. amendment gate docs 独立形成 plan-gate commit，production/test partial diff 绝不 stage；后续 accepted S1+S2 code commit 不混入 plan docs。

## DS review fix 后的冻结契约

### Blocker 测试 exact contract

`test_upload_filing_fresh_recheck_discards_stale_action_and_company_decision` 必须从旧的 rollback/no-stage 期望改为以下不可删减断言：

- terminal `filing_action == "update"` 且 `status == "skipped"`；
- metadata-only batch `begin` 恰一次、`commit` 恰一次，且 `commit_tokens == begin_tokens`；caller `rollback_tokens == []`；
- `company.stage_tokens == begin_tokens`，source stage token 为空；
- raw terminal `warnings` 精确等于
  `[{"kind": "company_name_ignored", "message": "本次提交的公司名称未生效；已保留现有公司名称。请核对上传目标公司是否正确。"}]`；
- 提交前后 final `CompanyMeta` canonical JSON 序列化 bytes 完全相同，显式覆盖 `company_name` 与 `updated_at`；
- `published_tree_sha256` 与既有 source revision/version/meta/manifest/assets 完全不变；
- 原回归语义必须保留：publication-lock fresh re-read 丢弃 stale preflight 的 `create` action 和旧 company decision，依据最终 published truth 重新产生 `update + preserve_published`。不得把测试弱化成仅验证 warning、skip 或 name 未改。

### Combined regression gate

Plan §12.2 是 S1+S2 implementation review/accepted commit 的硬前置：focused suite 后、进入 review 前必须全绿；review fix 改动代码/测试后，accepted commit 前必须再次全绿。失败或缺失时禁止 acceptance/stage/commit，且不得递延到 S3。

### 共享 runtime 符号边界

- S1+S2 的 `dayu/fins/ingestion_runtime.py` 只允许 `FinsUploadPipelineResult.warnings`、其 warnings/status invariant、`from_pipeline_json(..., source_kind)` 与 `CompanyMetadataWarning` 闭集解析。
- S1+S2 的 `dayu/fins/service_runtime.py` 只允许四个 pipeline parser callsite：SEC/CN filing 传 `SourceKind.FILING`，US/CN material 传 `SourceKind.MATERIAL`。
- S3 才允许 `FinsUploadResultSummary.warnings`/success-only invariant、`FinsUploadResultSummary.to_json_summary()`、`service_runtime._upload_summary_from_result` 及 direct/durable/CLI/tool projection。
- S1+S2 禁止提前实现 S3 symbols；S3 禁止重新定义 pipeline parser、warning codec 或四个 `SourceKind` callsite。

### Plan-gate 与 code commit 文件集

amendment 接受后先创建独立 plan-gate commit，只允许逐个显式 stage 以下已存在的文件：

- `docs/gateflow/uf-fix11-company-meta-warning-plan-20260817.md`
- `docs/gateflow/uf-fix11-s1-slice-boundary-blocker-20260817.md`
- `docs/gateflow/uf-fix11-slice-boundary-amendment-20260817.md`
- `docs/gateflow/uf-fix11-slice-amendment-review-fix-20260817.md`
- `docs/gateflow/uf-fix11-slice-amendment-acceptance-20260817.md`
- `docs/reviews/uf-fix11-slice-amendment-review-ds-20260817.md`
- `docs/reviews/uf-fix11-slice-amendment-review-mimo-20260817.md`
- re-review 实际产生并由 acceptance artifact 点名的 DS/MiMo artifacts。

当前 production/test partial diff 绝不 stage；禁止目录级 glob，cached diff 必须证明零 production/test path。建议 commit message：`gateflow: accept UF-FIX11 slice-boundary amendment`。

随后 accepted S1+S2 code commit 只包含本 slice production/test implementation、accepted scope 内必要 README（当前计划正常为零）与本 slice implementation/review/fix/re-review/acceptance closeout artifacts；不得混入任何 plan/amendment review docs。若 S1+S2 确需 README，必须先修订 allowed files，不能临时越界提交。

## Plan 具体变更

- Gate metadata 改为 `plan amendment re-review`，记录 blocker、amendment 与 partial implementation 状态。
- §10 改为两个 slices，补齐 S1+S2 objective、prerequisites、allowed files、atomic stop conditions 与 review/commit boundary。
- §6.6 按 S1+S2 parser symbols 与 S3 summary/durable symbols 拆分，不再让共享 runtime 文件的职责重叠。
- §10 冻结 blocker 测试的新 exact contract，并补齐 plan-gate/code commit 两个互斥文件集。
- §12 合并原 Slice 1/2 focused tests，明确 blocker test 不得 deselect，并把 combined regression 绑定为 S1+S2 review/commit 前置；分别定义 S1+S2 与 S3 coverage gate，两个 slice都在 review 前运行全仓 pyright。
- §13 将 slice-boundary 红色中间态列为本 work unit 内必须关闭的风险，并声明 amendment re-review 接受前 implementation blocked。
- §16 将 next gate/entry point 固定为 `plan amendment re-review`。

## 文件与验证

本 gate 只修改：

- `docs/gateflow/uf-fix11-company-meta-warning-plan-20260817.md`
- `docs/gateflow/uf-fix11-slice-boundary-amendment-20260817.md`
- `docs/gateflow/uf-fix11-slice-amendment-review-fix-20260817.md`

已有 production/test dirty diff 未在本 gate 继续修改。按用户指令，本 gate 不运行 pytest、coverage、pyright 或真实 CLI，
不 stage/commit。

## 风险与未覆盖项

- `fixed in current slice`：原 Slice 1 落地即红、无法形成独立 acceptance 的计划边界缺陷，已由本 amendment 改成原子 S1+S2；是否接受由下一 gate 裁决。
- blocker 红测、metadata-only skip、capability transfer、SEC/CN producer/parser 原子闭环是 S1+S2 的未完成 validation obligations，不在本 plan-only gate 伪装成已关闭 residual。
- durable/direct/CLI/tool projection 与 README 是 S3 的未完成 validation obligations，不在本 plan-only gate 伪装成已实现事实。
- `assigned to later work unit`：真实 CLI evidence、scenario/oracle/frozen evidence；沿用 accepted plan 既有 owner。
- Unclassified residual risk：无。

## Completion status

Plan amendment 已由 MiMo、DS 两路 final re-review `pass` 并被 controller 接受。当前 production/test partial diff
仍是未接受的原子 S1+S2 implementation，不得拆分提交；下一入口仅为完成、验证并 review 原子 S1+S2。
