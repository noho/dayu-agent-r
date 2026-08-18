# UF-FIX11 S1+S2 Implementation Review Fix

## Gate metadata

- work unit：`UF-FIX11 company-metadata-ignored-change-warning`
- slice：`S1+S2 — atomic authoritative company identity commit and filing warning`
- gate：`implementation review fix`
- 日期：2026-08-17
- 分支：`codex/upload-filing-oracle`
- 基线提交：`0b4740fa1a1334d0e242f31311c6d6902ff70035`
- review artifacts：
  - `docs/reviews/uf-fix11-s1-s2-implementation-review-mimo-20260817.md`
  - `docs/reviews/uf-fix11-s1-s2-implementation-review-ds-20260817.md`
- completion status：`FIX PASS / READY FOR RE-REVIEW`
- next entry point：`S1+S2 implementation re-review`
- commit：未创建
- blocking open questions：无

## Scope and owner decision

两路 review 未发现 production correctness、stability 或 architecture defect。Controller 接受的内容均为
owner contract 与结构测试缺口：material parser 边界由 `FinsUploadPipelineResult.from_pipeline_json` 拥有；
publication warning 同源不变量由 `FilingUploadPublicationOutcome` 拥有；warning closed codec 由
`company_metadata_warning` 模块拥有；四个 parser callsite 的 source kind 由
`ProductionFinsUploadRunner` 对应 filing/material 方法拥有；空白输入的 missing 决策由 upload pipeline
boundary 拥有。因此本 fix 只修改 accepted S1+S2 tests，不修改 production normalization、错误文案或任何
S3 projection。

## Controller decisions and fix evidence

### DS Finding-001 — ACCEPT / 已修复

- 在 `test_pipeline_warning_parser_requires_filing_field_but_allows_material_missing` 直接增加
  `SourceKind.MATERIAL` owner contract：显式 `warnings=[]` 合法并解析为 `()`；显式携带唯一规范 warning
  必须以 material-specific `ValueError` fail closed。
- 测试直接调用 parser owner，没有通过 service、summary 或下游投影反推 schema 行为。

### DS Finding-002 — ACCEPT / 已修复

- `FilingUploadPublicationOutcome` direct tests 增加两条拒绝契约：`cancelled + nonempty warning` 必须拒绝；
  warnings 与内部 `CompanyMetaCommitOutcome` 的规范投影不一致必须拒绝。
- warning codec direct parameterized tests 覆盖：runtime kind 不是精确 enum、message 非规范、
  `company_metadata_warnings_to_json` 元素超过一个、serializer 元素不是精确 typed warning，以及
  `project_company_name_ignored_warning` 输入不是精确 `CompanyNameIgnoredChange`。
- 所有断言命中 owner constructor/serializer/projection，不复制 SEC/CN、pipeline 或 UI 层推断。

### DS Finding-003 — ACCEPT / 已修复

- 重写 `test_production_runner_parser_callsites_use_explicit_source_kind`：先定位唯一
  `ProductionFinsUploadRunner` class，再按所属 `_run_filing_upload` / `_run_material_upload` 方法收集
  `from_pipeline_json` callsites。
- exact contract 为 filing 方法恰有两个且全部 `SourceKind.FILING`，material 方法恰有两个且全部
  `SourceKind.MATERIAL`，全 class 总数恰为四个；不再依赖源码物理顺序，并会拒绝 callsite 漂移到其他方法。

### MiMo Finding-002 test suggestion — ACCEPT / 已修复

- 在既有 `test_fresh_upload_equivalent_or_missing_name_keeps_metadata` 参数矩阵加入 ASCII 纯空白与
  `U+3000 IDEOGRAPHIC SPACE + U+00A0 NO-BREAK SPACE` 的 NFKC 空白输入。
- 两类输入都必须得到 `keep` 且 `company_meta_intent is None`，直接证明 pipeline owner 把它们视为未提交；
  没有 commit intent，因此不产生 company-name warning 事实。

### MiMo Finding-001 — REJECT-WITH-REASON / 不修改

两处错误分别属于不同 contract：pipeline 的 `_require_upload_company_name` 校验用户输入必填值，domain 的
`_normalize_optional_requested_company_name` 防御绕过上游 owner 的非法 intent。它们不是同一个公共错误
contract，下游也没有被授权按内部错误文案做匹配。本 work unit 不创建错误常量、共享抽象或兼容文案，
避免把不同 owner 强耦合。

### MiMo Finding-002 production semantic change — REJECT-WITH-REASON / 不修改

现有 pipeline owner 明确把空白输入折叠为 missing；domain constructor 对绕过 pipeline 的空白 intent
fail closed。两层职责不同且 review 已确认真实调用路径不会把空白 intent 传入 domain。统一两层行为会
削弱 domain 防御不变量或改变既定用户输入语义，没有根因证据支持。本轮只接受并完成上述 pipeline-boundary
测试，不修改 normalization production code。

## Changed files in this fix

### Tests

- `tests/fins/test_company_meta_contract.py`
- `tests/fins/test_filing_upload_publication.py`
- `tests/fins/test_fins_ingestion_runtime.py`
- `tests/fins/test_fins_service_runtime.py`

### Artifact

- `docs/gateflow/uf-fix11-s1-s2-implementation-review-fix-20260817.md`

本 fix 未修改任何 Python production 文件；既有 S1+S2 dirty production/test diff 与两份 review artifact
均保留，未 reset、discard、stage 或 commit。

## Validation evidence

### Affected new branches

按新增 test node 运行：`13 passed, 3 warnings in 1.13s`。其中参数展开覆盖 material 两条新增分支、
publication 两个不变量、warning constructor/serializer/projection 五个负例、AST 方法归属契约，以及四个
fresh missing/equivalent 参数。

### Plan §12.1 complete focused suite

按 accepted plan 的十个文件完整运行，未使用 `-k`、`--deselect` 或其他排除：
`715 passed, 3 warnings in 12.57s`。

### Plan §12.2 combined regression

按 accepted commit 前硬门完整运行 `tests/fins`、CLI output/commands 与 service wait adapter：
`2138 passed, 1 skipped, 3 warnings in 63.28s`。唯一 skip 为既有 Docling integration 条件 skip；三个
warning 均来自 `edgar` 依赖 deprecated import。

### Type and coverage decision

- 全仓 `python -m pyright dayu tests utils`：`0 errors, 0 warnings, 0 informations`。
- 本 review-fix 没有修改 Python production；按 controller 指示不重复 coverage。DS review 已独立复跑
  `tests/fins` coverage，确认全部 12 个 S1+S2 production 文件逐文件 `>=80%`，总计 `87%`；本轮新增
  direct tests 正向关闭其报告的防御分支缺口。

## Documentation and boundary decision

本 fix 没有新增测试层、改变测试运行方式或维护规则，因此不触发 `tests/README.md`；其他 README 同样不触发。
未修改 Host、Engine、material workflow/schema、oracle、scenario、frozen evidence、summary、durable、direct、
CLI 或 tool projection。S3 尚未开始。

## Residual risks

- `fixed in current slice`：DS Finding-001/002/003 与 MiMo Finding-002 的 pipeline 空白输入测试建议均已由
  direct owner/structure tests 关闭。
- `covered by later approved slice`：summary、durable、direct、CLI、tool warning projection 与相应 README
  属于 accepted S3；S1+S2 accepted slice commit 前不得开始。
- `assigned to later work unit`：name-only metadata batch 的 writer lock/physical swap 成本；material 若未来
  需要同类 company-name warning 的独立 owner/schema；commit durable 后 guard-release/cleanup 异常的运维可见性。
- MiMo Finding-001 与 Finding-002 production change 均为 `rejected-with-reason`，不是 deferred risk。
- 未分类 residual risk：无。

## Completion status

UF-FIX11 原子 S1+S2 implementation review-fix 已完成，所有 controller accepted findings 状态为`已修复`，
rejected findings 均保留证据化理由。下一 gate 是 implementation re-review；本 artifact 不预判 re-review
结论、slice acceptance 或 accepted commit，且未开始 re-review。
