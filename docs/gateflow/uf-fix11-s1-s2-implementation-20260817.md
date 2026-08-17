# UF-FIX11 S1+S2 Implementation

## Gate metadata

- work unit：`UF-FIX11 company-meta-warning`
- slice：`UF-FIX11-S1+S2 — atomic authoritative company identity commit and filing warning`
- gate：`implementation`
- 日期：2026-08-17
- 分支：`codex/upload-filing-oracle`
- 基线提交：`0b4740fa1a1334d0e242f31311c6d6902ff70035`
- completion status：`IMPLEMENTATION PASS / READY FOR IMPLEMENTATION REVIEW`
- next entry point：`S1+S2 implementation review`
- commit：未创建
- blocking open questions：无

## Motivation 与 owner decision

问题成立：旧实现只从 preparation-time observation 或下游结果猜测公司名称是否生效，无法在
publication lock 下区分 fresh success、exact skipped metadata-only commit、并发覆盖、alias collision
与失败回滚。这样既不能保证 warning 来自最终持久化事实，也会让 skipped 路径无法原子持久化合法 alias。

语义 owner 固定如下：`company_meta_contract` 拥有 requested company name 与最终 canonical company
identity 的 closed decision；storage `commit_batch(...)` 在 publication lock 的 final re-read 后拥有
authoritative commit outcome；`filing_upload_publication` 是唯一把该 outcome 投影为 typed warning 的
consumer；SEC/CN terminal producer 与 ingestion warning codec 只机械序列化和严格解析。Service 四个
parser callsite 显式传入 `SourceKind`，不从 terminal payload 或下游 summary 反推来源类型。

## Implemented scope

- `company_meta_contract.py`：增加 requested name intent、Unicode NFKC/空白规整/casefold 等价判断、
  `CompanyNameIgnoredChange` 与 `CompanyMetaCommitOutcome`。merge 在 final published company meta 上作出
  authoritative identity decision；identity 未变化的 name-only commit 保留 canonical bytes 所需字段和
  `updated_at`。
- `company_metadata_warning.py`：定义唯一 closed warning kind、固定中文消息、严格 closed object/list codec
  及 domain outcome projection；warning 最多一个，未知字段、未知 kind、错误 message、重复值和错误类型均拒绝。
- `upload_company_meta.py`：保留 requested name intent；fresh name-only 或 alias-only candidate 不再在
  preparation 阶段丢失 intent，stale refresh 继续携带同一 intent。
- storage protocol、filesystem batching implementation 与 repository：三个 production `commit_batch(...)`
  contract exact 返回 `CompanyMetaCommitOutcome | None`；在 publication lock final re-read 后产生 outcome。
- `docling_upload_service.py`：successful commit 后把 exact storage outcome 附着到 operation result；commit
  exception 不产生 outcome。
- `filing_upload_publication.py`：canonical skip 允许无 metadata intent 的 rollback skip，或有合法 metadata
  intent 的 metadata-only stage/commit skip。warning 只由成功 commit 返回的 final outcome 产生；stage、commit、
  cancel、rollback 或 collision failure 均不产生 warning，也不由 raw name 或历史状态重算。
- SEC/CN 全部 terminal producer：`ok`/`skipped` 机械序列化 publication warnings；early terminal 与全部
  `failed`/`cancelled` 显式输出空 warning list。
- `ingestion_runtime.py`：仅在 pipeline result 增加 typed warnings；filing payload 必须显式携带 warnings，
  material 缺失 warnings 解析为空，`null` 与非空 material warning 均拒绝；未修改 summary/durable contract。
- `service_runtime.py`：四个 filing/material parser callsite 显式传入同一 `SourceKind` 真源。
- tests：覆盖 SEC/CN fresh different name 的 success/skip warning、合法 alias-on-skip、invalid/collision typed
  failure、failure/cancel/rollback no warning、并发 winner final-name warning、严格 codec、material missing-to-empty、
  全 terminal producer、四个 SourceKind callsite，以及 name-only commit 的 canonical `CompanyMeta` bytes、
  `updated_at` 和 source tree 不变。

## Changed files

### Production

- `dayu/fins/company_metadata_warning.py`
- `dayu/fins/domain/company_meta_contract.py`
- `dayu/fins/ingestion_runtime.py`
- `dayu/fins/pipelines/cn_pipeline.py`
- `dayu/fins/pipelines/docling_upload_service.py`
- `dayu/fins/pipelines/filing_upload_publication.py`
- `dayu/fins/pipelines/sec_upload_workflow.py`
- `dayu/fins/pipelines/upload_company_meta.py`
- `dayu/fins/service_runtime.py`
- `dayu/fins/storage/_fs_storage_infra.py`
- `dayu/fins/storage/fs_batching_repository.py`
- `dayu/fins/storage/repository_protocols.py`

### Tests

- `tests/fins/test_cn_download_workflow.py`
- `tests/fins/test_cn_pipeline.py`
- `tests/fins/test_company_identity_storage_contract.py`
- `tests/fins/test_company_meta_contract.py`
- `tests/fins/test_docling_upload_service.py`
- `tests/fins/test_filing_upload_publication.py`
- `tests/fins/test_fins_ingestion_runtime.py`
- `tests/fins/test_fins_service_runtime.py`
- `tests/fins/test_sec_pipeline_download_stream.py`
- `tests/fins/test_sec_pipeline_upload_filing_stream.py`
- `tests/fins/upload_filing_test_support.py`

### Artifact

- `docs/gateflow/uf-fix11-s1-s2-implementation-20260817.md`

## Validation evidence

### Plan §12.1 focused suite

按计划完整运行，未 deselect：`706 passed, 3 warnings in 12.79s`。

### Plan §12.2 combined regression

按计划完整运行：`2129 passed, 1 skipped, 3 warnings in 87.01s`。唯一 skip 位于既有
`test_docling_upload_service_integration.py` 集成测试；未使用 deselect。三个 warning 均来自 `edgar`
依赖的 deprecated import，不是本 slice 新增失败。

### Plan §12.3.1 per-file coverage

完整 `tests/fins` coverage run：`1951 passed, 1 skipped, 3 warnings in 66.26s`。

| Production file | Coverage |
| --- | ---: |
| `dayu/fins/company_metadata_warning.py` | 80% |
| `dayu/fins/domain/company_meta_contract.py` | 93% |
| `dayu/fins/ingestion_runtime.py` | 88% |
| `dayu/fins/pipelines/cn_pipeline.py` | 90% |
| `dayu/fins/pipelines/docling_upload_service.py` | 85% |
| `dayu/fins/pipelines/filing_upload_publication.py` | 82% |
| `dayu/fins/pipelines/sec_upload_workflow.py` | 91% |
| `dayu/fins/pipelines/upload_company_meta.py` | 97% |
| `dayu/fins/service_runtime.py` | 87% |
| `dayu/fins/storage/_fs_storage_infra.py` | 84% |
| `dayu/fins/storage/fs_batching_repository.py` | 95% |
| `dayu/fins/storage/repository_protocols.py` | 81% |
| **Total** | **87%** |

全部 modified/new production files 达到单文件 `>= 80%` 目标。

### Type and static validation

- 全仓 pyright：`0 errors, 0 warnings, 0 informations`。
- `git diff --check`：通过。
- `commit_batch` inventory：production exact 3 个定义；tests exact 7 个文件/9 个定义，其中 Docling test
  文件 3 个；全部注解为 `CompanyMetaCommitOutcome | None`。
- warning failure-path、batch lifecycle、禁止下游 summary/direct/CLI 投影、禁止 `hasattr/getattr` 与宽类型等
  §12.5 static boundary checks：通过。

## Behavioral evidence

- SEC/CN 既有 canonical source 的 fresh different name，在 changed publication success 与 exact skipped
  metadata-only commit 两条路径均保留 canonical name，并输出同一个 fixed typed warning。
- 合法 alias-only exact skip 原子提交 alias，warning 为空；source publication state 与 source content tree
  保持不变。
- name-only skipped commit 前后 canonical `CompanyMeta` JSON bytes 完全相同，`updated_at` 不变；source tree
  hash 与 filing published state 不变。
- invalid name 与 final-lock alias collision 均为 typed failure；whole-tree unrelated degraded material path
  fail closed，不发生 partial company/source mutation，warning 为空。
- Event/Barrier 控制的 concurrent winner/loser 测试证明 warning 根据 final lock winner 的 authoritative name
  产生，不根据 preparation observation 推断；未使用 sleep 或 polling。
- stage、commit、cancel、rollback failure tests 均证明 warning 为空，并保持既有 rollback ownership。
- filing parser 对 warnings 为 required strict field；material missing warnings 精确解析为空，material 非空、
  `null`、unknown field/kind/message、重复 warning 均被 owner contract 拒绝。

## Documentation and scope decision

`tests/README.md` 的更新边界要求只有新增测试层、测试运行方式或维护规则变化才更新；本 slice 仅在既有
Fins 测试层补充 contract/regression，因此不触发 README。根 README、`dayu/fins/README.md` 与用户可见
summary/durable/direct/CLI/tool 文档属于 accepted S3 projection slice，本轮未修改。

工作树未触及 Host、Engine、material workflow/schema、frozen oracle/scenario/evidence、CLI、tool、direct、
durable summary 或任何 README；未执行 stage、commit、push、PR，也未开始 implementation review。

## Findings and residual risks

- 当前 slice correctness blocker：无。authoritative final decision、metadata-only skip、alias collision、
  failure/cancel/rollback no-warning 与 strict producer/parser contract 均有 owner-level 和 integration evidence。
- accepted tradeoff：metadata-only skip 仍通过现有 batch physical publication 完成，但 canonical company bytes、
  timestamp 与 source tree 有 exact no-change evidence；底层 physical swap 成本归入后续独立 work unit。
- accepted tradeoff：warning 使用固定业务消息且不暴露 raw requested/stored name；closed codec 最多一个 warning，
  避免下游把内部 identity 或治理字段当作财报事实。
- covered by later approved slice：summary、durable、direct、CLI、tool projection 与相应 README/真实 CLI evidence
  属于 S3；S1+S2 accepted slice commit 前不得开始。
- assigned to later work unit：material 若未来需要同类 company-name warning，必须独立确认 owner 与 schema；
  本 slice 只实现 accepted 的 material missing-warnings-to-empty parser contract。
- 未分类 residual risk：无。

## Completion status

UF-FIX11 原子 S1+S2 implementation 已完成并具备完整绿色 validation evidence。下一 gate 是一次完整
implementation review；本文不预判 review 结论、acceptance 或 accepted slice commit，也未开始 S3。
