# UF-FIX03 aggregate re-review — AgentMiMo

## Review metadata

- Review type：aggregate re-review（post-F1 fix）
- Work unit：`UF-FIX03 summary-and-bounded-errors`
- Base：`c54a4fd8`（aggregate review HEAD）
- F1 fix base：`c54a4fd8` + working tree diff（3 文件）
- Reviewer：AgentMiMo
- Date：2026-08-14
- Constraint：严格只读；只新增本 artifact 文件

## 结论

**PASS** — F1 fix 正确闭环。SEC/CN filing 不可达 `DoclingConversionError` catch 及其 unused import 已删除；AST owner guard 稳健且不产生假阳性；material 不受影响；所有 frozen predicates 保持满足。首轮 LOW 观察维持 LOW，不升级。

## F1 fix 走读

### 修改文件清单

| 文件 | 变更 |
| --- | --- |
| `sec_upload_workflow.py` | 删除 L298-306 不可达 `except DoclingConversionError`；删除 L22-24 unused import |
| `cn_pipeline.py` | 删除 L918-926 不可达 `except DoclingConversionError`；从 L68-71 import block 删除 unused `DoclingConversionError` |
| `test_fins_ingestion_runtime.py` | 新增 `_direct_exception_handler_names` helper + `test_filing_workflows_consume_only_typed_admission_failure_before_generic_handlers` |

### 1. catch 删除正确性

SEC filing workflow（`sec_upload_workflow.py:287-303`）handler 顺序现在为：
`FinsUploadFailureError -> OSError -> Exception`。

CN filing workflow（`cn_pipeline.py:909-934`）handler 顺序现在为：
`FinsUploadFailureError -> OSError -> Exception`。

两处删除前的 `except DoclingConversionError` 分支均使用 `file_label=None` 构造 `fins_upload_failure_from_exception`——这与 typed admission owner 要求的 canonical label 语义不一致。当前拓扑下 `_build_pending_assets` 已将 filing 全部 `DoclingConversionError` 在逐文件边界包装为携带 canonical `file_label` 的 `FinsUploadFailureError`，因此这两条 catch 不可达。删除后 handler 序列精确匹配 typed failure owner contract。

### 2. import 删除正确性

- `sec_upload_workflow.py`：删除的 `DoclingConversionError` import 仅被已删除的 catch 使用，无其它消费点。该文件仍从 `docling_upload_service` 导入 `DoclingUploadService` 等符号，import block 完整。
- `cn_pipeline.py`：从 `docling_process_converter` import block 中删除 `DoclingConversionError`，保留 `DoclingConverter` 和 `ProcessDoclingConverter`（仍被文件使用）。`DoclingConversionError` 仅在 `docling_upload_service.py:779` 和 `docling_process_converter.py` 内部使用，不被 cn_pipeline 直接消费。

**判定：PASS。** 删除无行为回归。

### 3. material 不受影响

SEC material workflow（`sec_upload_workflow.py:571`）保持单一 `except Exception` catch。
CN material workflow（`cn_pipeline.py:1179`）保持单一 `except Exception` catch。
F1 fix 未触碰 material 路径代码。

**判定：PASS。**

### 4. AST owner guard 稳健性

`_direct_exception_handler_names()` helper（`test_fins_ingestion_runtime.py:863-909`）：
- 使用 `ast.parse` 解析 production 源文件，定位指定 class/function 的外层 `try` block。
- 只取 `ast.Name` 类型的 handler（直接异常类型引用），返回 handler 名称元组。
- 断言唯一 workflow function、唯一 outer try——若 production 结构变化会立即 AssertionError。
- 不依赖字符串匹配、不 import production 模块、不执行 production 代码。

`test_filing_workflows_consume_only_typed_admission_failure_before_generic_handlers`（`test_fins_ingestion_runtime.py:912-961`）覆盖四个 workflow：

| workflow | expected handlers |
| --- | --- |
| SEC `run_upload_filing_stream` | `(FinsUploadFailureError, OSError, Exception)` |
| CN `upload_filing_stream` | `(FinsUploadFailureError, OSError, Exception)` |
| SEC `run_upload_material_stream` | `(Exception,)` |
| CN `upload_material_stream` | `(Exception,)` |

guard 不过度耦合：
- 只验证 handler 类型名称顺序，不验证 handler 内部实现。
- 若 production 新增非 `ast.Name` handler（如 `except (A, B)`），`assert all(isinstance(...))` 会立即失败而非假阳性。
- 若 production 新增/删除/重排 handler，断言立即失败——这正是 owner guard 的目的。

**判定：PASS。** AST guard 稳健，不产生假阳性，不过度耦合。

### 5. docstring/type/coverage/README 决策

- 新增 helper 和 test 均有完整中文 docstring，含 Args/Returns/Raises。
- pyright `0 errors, 0 warnings, 0 informations`。
- 受影响测试 `334 passed, 3 warnings`。
- `README.md`、`dayu/fins/README.md`、`tests/README.md` 不更新——gateflow fix artifact 已明确说明：本 fix 只删除违背现有 typed owner contract 的不可达分支，没有新增或改变稳定公共契约。

**判定：PASS。**

### 6. frozen/no-touch

- frozen SHA 保持：`cli_ci_scenarios.json = a357e5a1…`、`cli_ci_oracles.json = 88b04ca4…`。
- no-touch 区域（Host/Engine/runtime/config/Service/storage）零改动。
- `git diff --check` 通过。
- `uploaded_files` production 零命中。
- `DoclingConversionCancelledError` 在 modified files 中零命中。

**判定：PASS。**

## 首轮 LOW 观察裁决

### deleted/cancelled requested>=0

MiMo 首轮 review（`deepreview-uf-fix03-aggregate-mimo-20260813.md`）F1 观察：`FinsUploadResultSummary.__post_init__()` 对 `deleted`/`cancelled`/`failed` 只强制 `stored_file_count == 0`，不强制 `requested_file_count == 0`。测试矩阵接受 `deleted/0/0` 但不测试 `deleted/1/0` 是否被拒绝。

**裁决：维持 LOW，不升级。**

理由：
1. accepted plan §5.3 矩阵明确规定 `deleted/cancelled/failed: requested>=0 && stored==0`——`requested>=0` 是计划内的 contract，不是遗漏。
2. `service_runtime.py:131` early-cancelled summary 构造 `requested_file_count=len(raw_request.files)` 是 plan 中的显式设计，pipeline 不返回 requested，summary 的 requested 只能来自 request。
3. CLI 层 `validate_fins_upload_filing_request()` 确保 delete 请求 `files=()`（`docling_upload_service.py` 的 `_admit_fins_upload_file_basename` 对 empty tuple 直接通过），runtime 层不需重复防御。
4. 无直接 correctness 反例：没有 production 路径会产生 `deleted`/`cancelled` 状态且 `requested > 0` 的 summary 并导致错误行为。

除非提供直接 correctness 反例（即某条 production 路径实际产生 `deleted/1/0` 并导致下游错误），不得升级为 NEEDS_FIX。

## 验证执行摘要

| 检查项 | 结果 |
| --- | --- |
| 受影响测试（5 文件） | `334 passed, 3 warnings` ✓ |
| pyright（3 文件） | `0 errors, 0 warnings, 0 informations` ✓ |
| frozen SHA-256 scenarios | `a357e5a1…` ✓ |
| frozen SHA-256 oracles | `88b04ca4…` ✓ |
| `git diff --check` | 通过 ✓ |
| `uploaded_files` production 残留 | 零命中 ✓ |
| `DoclingConversionCancelledError` in modified files | 零命中 ✓ |
| no-touch（Host/Engine/runtime/config/Service/storage） | 无改动 ✓ |
| SEC/CN filing handler 顺序 | `FinsUploadFailureError -> OSError -> Exception` ✓ |
| SEC/CN material handler 顺序 | `Exception`（不变） ✓ |

## Residual risks

- F1 已修复：dead catch / second degraded owner 由 production 删除与 AST owner guard 覆盖。
- 真实 Docling 多平台损坏样本差异：assigned to UF-PF03，本轮未执行。
- 既有 upload-tool fixture 问题：assigned to upload tool contract/test owner，本 fix 未增加兼容分支。

## 最终判定

**PASS** — F1 fix 正确闭环，无 NEEDS_FIX finding。首轮 LOW 观察（summary 不强制 delete 的 `requested_file_count == 0`）维持 LOW，归后续 runtime contract 加固，除非提供直接 correctness 反例不得升级。
