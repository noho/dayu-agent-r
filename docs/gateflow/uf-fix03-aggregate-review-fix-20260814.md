# UF-FIX03 aggregate review fix

## Gate metadata

- Work unit：`UF-FIX03 summary-and-bounded-errors`
- Gate：`aggregate deepreview -> fix`
- Branch：`codex/upload-filing-oracle`
- Baseline HEAD：`c54a4fd8a08955a91287cc0f74070f5c9211143a`
- Input finding：`docs/reviews/deepreview-uf-fix03-aggregate-agentds-20260813.md` F1
- Controller decision：`accepted`
- Completion status：F1 fix 已实现并通过本地验证；正式 aggregate re-review 尚未执行。
- Next Gateflow entry：`aggregate deepreview re-review`
- Artifact path：`docs/gateflow/uf-fix03-aggregate-review-fix-20260814.md`

## Scope and owner adjudication

F1 动机成立，但只属于低严重度 maintainability / latent degradation：当前 filing 转换拓扑没有可触发
SEC/CN workflow `except DoclingConversionError` 的输入，因此没有现行行为错误。直接证据如下：

- `DoclingUploadService._build_pending_assets(...)` 是逐文件转换 admission owner；它只对
  `SourceKind.FILING` 将 `DoclingConversionError` fail-fast 包装为携带 canonical `file_label` 的
  `FinsUploadFailureError`，并保留原异常为 cause。
- SEC/CN filing workflow 已在 generic handlers 前直接消费 `FinsUploadFailureError.failure`，这是 accepted plan
  指定的穷尽 typed projection boundary。
- 两处额外 `except DoclingConversionError` 当前不可达；若未来绕过 typed admission，它们会用
  `file_label=None` 产生第二个退化 projection owner，静默丢失 filing canonical label。
- material conversion 仍由 `_build_pending_assets(...)` 原样抛出，再由两个 material workflow 的既有 generic
  `Exception` 边界消费；本 finding 不拥有 material public failure 语义。

Controller 因此接受删除方案。修复不增加 fallback、防御性 catch、兼容分支或注释性 shim，也不重构异常状态机；这是满足唯一
typed failure owner 的最小方案，没有引入过度设计。

## Fixes

- `dayu/fins/pipelines/sec_upload_workflow.py`
  - 删除 filing workflow 不可达的 `except DoclingConversionError`。
  - 删除仅由该分支使用的 `DoclingConversionError` import。
- `dayu/fins/pipelines/cn_pipeline.py`
  - 删除 filing workflow 不可达的 `except DoclingConversionError`。
  - 从仍需保留的 converter import 中删除未使用的 `DoclingConversionError`。
- `tests/fins/test_fins_ingestion_runtime.py`
  - 新增 production AST owner guard，精确锁定 SEC/CN filing 外层 handler 顺序为
    `FinsUploadFailureError -> OSError -> Exception`，因此 typed admission 必须优先消费且不得直接 catch
    `DoclingConversionError`。
  - 同一 guard 锁定 SEC/CN material 外层 handler 仍为既有单一 `Exception` 边界。

## Tests-first evidence

新增 AST owner test 在生产修复前按预期失败：实际 filing handler 序列在 `FinsUploadFailureError` 后多出
`DoclingConversionError`；删除不可达分支后，该测试与两条既有 material 用户可见语义测试共同通过：

- pre-fix：`1 failed, 3 warnings`；失败差异为 index 1 的 `DoclingConversionError != OSError`。
- post-fix targeted：`3 passed, 3 warnings`。

## Validation

- 受影响测试：
  `pytest -q tests/fins/test_docling_upload_service.py tests/fins/test_sec_pipeline_upload_filing_stream.py tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_cn_pipeline.py tests/fins/test_fins_ingestion_runtime.py`
  -> `334 passed, 3 warnings`。
- 修改文件 broader coverage：
  `coverage run -m pytest -q tests/fins -k 'not test_upload_tool_accepts_local_file_outside_workspace_without_source_side_effect'`
  -> pass；`cn_pipeline.py 94%`、`sec_upload_workflow.py 95%`。精确 deselect 的既有 upload-tool fixture
  与 aggregate review 裁决一致。
- 全量类型检查：`python -m pyright dayu/ tests/ utils/` -> exit 0，无输出。
- `git diff --check` -> pass。
- 静态 handler audit：SEC/CN filing 均为
  `FinsUploadFailureError -> OSError -> Exception`；SEC/CN material 均仍为 `Exception`。
- frozen SHA 保持 accepted plan 值：
  - `docs/cli_ci_scenarios.json`：`a357e5a1e0ee11cb42f8ab6e25083b23761a4c8181d14ddc1876f0bf9a788efb`
  - `docs/cli_ci_oracles.json`：`88b04ca47472f320b614ad1374a9f0a243443efaca1e0565eaf29b5f0cb770b8`

三个 warning 均为既有 `edgar` 第三方 deprecation warning，不由本 fix 引入。

## Documentation and no-touch decision

- `dayu/fins/README.md` 不更新：本 fix 只删除违背现有 typed owner contract 的不可达分支，没有新增或改变稳定公共契约。
- `tests/README.md` 不更新：新增测试属于既有 Fins owner/AST 静态守卫层级，没有新增测试层级或运行方式。
- 两个 aggregate review artifacts 保持只读；未修改 frozen JSON/evidence、Host/Engine/runtime/config/Service/storage、
  `_build_pending_assets(...)` 或 material workflow。
- 未执行 UF-PF03，未 commit、push 或创建 PR。

## Finding status

| ID | Controller decision | Fix status | Evidence |
| --- | --- | --- | --- |
| F1 | accepted | 已修复 | 不可达 catch/import 已删除；AST owner guard 与 334 项受影响回归通过 |

正式 re-review 仍是下一 gate；本 artifact 不把本地 fix 验证伪装成独立 review 结论。

## Residual risks and uncovered areas

- F1 dead catch / second degraded owner：`fixed in current slice`，由 production 删除与 AST owner guard 覆盖。
- 真实 Docling 多平台损坏样本差异：`assigned to later work unit`（UF-PF03）；按用户约束本轮未执行。
- aggregate review 已记录的既有 upload-tool fixture 问题：`assigned to later work unit`（upload tool contract/test owner）；
  本 fix 未增加兼容分支。
- 当前没有未分类 residual risk 或 blocking open question。
