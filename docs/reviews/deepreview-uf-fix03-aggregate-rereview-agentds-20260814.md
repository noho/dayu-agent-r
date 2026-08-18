# UF-FIX03 Aggregate Re-review（AgentDS，post-F1 fix）

## Review metadata

- Review type：aggregate re-review（严格只读，复核 F1 fix 闭环）
- Work unit：`UF-FIX03 summary-and-bounded-errors`
- Branch：`codex/upload-filing-oracle`
- Base：`c54a4fd8a08955a91287cc0f74070f5c9211143a`
- Review date/time：2026-08-14 00:24:36 +0800
- Output file：`docs/reviews/deepreview-uf-fix03-aggregate-rereview-agentds-20260814.md`
- Included scope：F1 fix 三个变更文件（`dayu/fins/pipelines/cn_pipeline.py`、`dayu/fins/pipelines/sec_upload_workflow.py`、`tests/fins/test_fins_ingestion_runtime.py`）逐行走读；`docs/gateflow/uf-fix03-aggregate-review-fix-20260814.md`、本 reviewer 与 MiMo 的两份 aggregate review；typed admission owner（`docling_upload_service.py`）、分类 owner（`upload_failure.py`）、`DoclingConversionFailureKind` 枚举与 `tests/README.md` AST 守卫层级证据
- Excluded scope：无（diff 仅 3 文件，全部走读；material workflow 未修改部分只做边界确认）
- Parallel review coverage：无（单 reviewer 全量走读）
- 执行约束遵守：全程只读；未改代码/既有 artifact/JSON/evidence；未 commit/push；未执行 UF-PF03；pytest 以 `-p no:cacheprovider` 运行（仓库零写入），pyright 输出重定向 `/tmp`；仅新增本 artifact

## 结论

**PASS** — F1 已正确闭环，未发现实质性问题。所有复核项均以直接代码证据与独立运行验证闭环，见下。

## Findings

未发现实质性问题。

## 复核清单与证据

### 1. SEC/CN filing typed failure 唯一 owner

- SEC filing 外层 handler 现为 `FinsUploadFailureError`（`sec_upload_workflow.py:287`）→ `OSError`（:295）→ `Exception`（:304）；`except DoclingConversionError` 分支与专用 import 均已删除（diff hunk 直接证据）。
- CN filing 外层 handler 现为 `FinsUploadFailureError`（`cn_pipeline.py:909`）→ `OSError`（:917）→ `Exception`（:926）；converter import 缩减为 `DoclingConverter`/`ProcessDoclingConverter`，未使用符号删除。
- 唯一 typed admission owner 未动：`docling_upload_service.py:779-792` 逐文件 catch 对 FILING 将 `DoclingConversionError` 以 canonical `file_label` 包装为 `FinsUploadFailureError` 并 `raise ... from exc`（:792），非 FILING 原样 re-raise（:780-781）。filing 路径上不存在绕过该 owner 的转换入口。
- `rg DoclingConversionError` 在两 workflow 文件零命中；分类 owner `fins_upload_failure_from_exception`（`upload_failure.py:161`）与 typed 消费 `exc.failure`（`sec_upload_workflow.py:293`、`cn_pipeline.py:915`）均未被本 fix 触碰。
- 判定：filing typed 投影收敛为「`FinsUploadFailureError` 直投 + generic 经单一 mapper」两层，每层 owner 唯一。✓

### 2. 删除 catch/import 无行为回归

- 被删分支不可达：filing 全部转换经 `_build_pending_assets` 逐文件 catch（`docling_upload_service.py:779`），任何 FILING `DoclingConversionError` 都以 typed 异常到达 `except FinsUploadFailureError`；prior review coverage missing 行（旧 `sec_upload_workflow.py:299-301`、`cn_pipeline.py:919-921`）证实零覆盖。
- 更强证据：即便假设未来出现未包装的 `DoclingConversionError`，被删分支与 `except Exception` 兜底的行为也完全相同——两者都调用 `fins_upload_failure_from_exception(exc, file_label=None)`，mapper 的 isinstance 分支（`upload_failure.py:179-186`）产生同一 CONTENT reason（唯一差异是 `_LOGGER.exception` 的日志文案，仅 operator log）。因此删除在可达与不可达场景下均为零可观察行为变化，被删分支是纯冗余投影点而非独立 owner。
- 独立运行：`pytest -q -p no:cacheprovider tests/fins/test_docling_upload_service.py tests/fins/test_sec_pipeline_upload_filing_stream.py tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_cn_pipeline.py tests/fins/test_fins_ingestion_runtime.py` → `334 passed, 3 warnings`（与 fix doc 声称一致；warnings 为 edgar 第三方弃用提示）。
- fix doc 的 pre-fix 失败证据（`1 failed`，index 1 `DoclingConversionError != OSError`）本轮未复现（需 stash，违反只读约束），但与 pre-fix handler 序列推导完全一致，无矛盾。✓

### 3. material 不受影响

- SEC material `run_upload_material_stream` 外层仍为单一 `except Exception`（`sec_upload_workflow.py:571`）；CN material `upload_material_stream` 同样单一 `except Exception`（`cn_pipeline.py:1179`）。diff 未触碰任何 material 代码行。
- 两文件的 `except BaseException`（`sec_upload_workflow.py:503`、`cn_pipeline.py:1111`）位于嵌套 rollback try 内，非外层 handler，AST guard 的「唯一外层 try」断言因此不误伤。✓

### 4. AST guard 稳健性评估

- guard 本体：`tests/fins/test_fins_ingestion_runtime.py:863-910`（`_direct_exception_handler_names`）与 `:912-963`（测试）。合同为精确四元组：SEC/CN filing `("FinsUploadFailureError", "OSError", "Exception")`、SEC/CN material `("Exception",)`（`:929-947`）。
- 真阳性能力（设计目标）：handler 重排、重新引入 `DoclingConversionError` catch、material 边界变更均触发精确匹配失败。`FinsUploadFailureError(RuntimeError)`（`upload_failure.py:126`）必须先于 `Exception` 消费，顺序锁定是真实语义合同，非风格约束。
- 防误读：`len(outer_tries) == 1` 与 `all(isinstance(handler_type, ast.Name))`（`:885-887`）保证读取的是外层投影边界而非嵌套 try 或 tuple handler，避免 guard 静默读到错误结构（假阴性）。
- 假阳性面（已评估，不构成 finding）：若未来在外层新增 `try/finally`（如资源释放）、把 handler 改为 tuple 形式或裸 except，guard 会在无语义回归的情况下失败；且断言无自定义 message，诊断需读测试。判断：失败模式响亮、更新合同本身即是该测试的存在目的，属精确合同锁的可接受权衡，与既有 AST audit 层级（`test_production_upload_count_constructors_are_explicit_and_complete`）风格一致。✓
- 独立运行：`pytest -q -p no:cacheprovider tests/fins/test_fins_ingestion_runtime.py -k test_filing_workflows_consume_only_typed_admission_failure_before_generic_handlers` → `1 passed`（确证 collect 且通过，非跳过）。✓

### 5. unknown exception 投影边界挑战（不穿透 Docling 原始文本）

- 唯一分类 owner `fins_upload_failure_from_exception`（`upload_failure.py:161-201`）只做 isinstance 分类 + 固定文案：Docling → CONTENT + `_DOCLING_FAILURE_CODES[error.kind]`（:179-186）、OSError → `STORAGE_IO`（:187-194）、其余 → `RUNTIME/UNEXPECTED_RUNTIME`（:195-201）。三分支 message/retry_hint 均为固定中文字面量，不含 `str(exc)`、路径或底层文本。
- 映射穷尽性：`DoclingConversionFailureKind` 恰 6 成员（`docling_process_converter.py:197-202`），与 `_DOCLING_FAILURE_CODES`（`upload_failure.py:148-155`）一一对应，当前不存在 KeyError 路径。
- filing 侧：OSError/Exception handler 均以 `file_label=None` 调同一 mapper（`sec_upload_workflow.py:297,306`、`cn_pipeline.py:919,928`）；未知异常稳定投影为固定文案 RUNTIME reason；raw traceback 仅进入 `_LOGGER.exception` operator log（:288/:296/:305、:910/:918/:927）。filing 公共投影无 Docling 原始文本穿透。✓
- 边界外确认（非本 fix 回归）：material generic 边界仍把 `str(exc)` 写入 `message` 与 `payload.error`（`sec_upload_workflow.py:592,598`、`cn_pipeline.py:1200,1206`）——这是既有 material 失败语义，controller 裁决与两份 aggregate review 均明确排除在 F1/WU 范围外（「本 finding 不拥有 material public failure 语义」）。本 re-review 确认该边界裁决成立：material 失败走 workflow 事件而非 frozen `upload_filing` predicate，改它需要独立 WU 与语义决策。✓

### 6. docstring / type / coverage / README 决策

- 新 helper 与测试均有完整中文 docstring（Args/Returns/Raises，`:863-910`、`:912-926`），符合项目编码硬约束；无嵌套函数、无 `Any`、`class_name: str | None` + keyword-only 参数设计干净。
- `python -m pyright dayu/fins/pipelines/cn_pipeline.py dayu/fins/pipelines/sec_upload_workflow.py tests/fins/test_fins_ingestion_runtime.py` → exit 0，`0 errors, 0 warnings, 0 informations`。
- coverage：删除的行原为 coverage missing 行（prior review 证实），删除不可达代码只会提高或持平覆盖率，未用 pragma/降阈值掩盖。
- README 决策成立：`dayu/fins/README.md` 不更新——fix 仅删除违背既有 typed owner contract 的冗余不可达分支，未新增/改变稳定公共契约，现有 typed projection 描述仍准确；`tests/README.md` 不更新——AST 守卫层级已有文档先例（`tests/README.md:285` CLI import boundary AST 阻止、`:330` AST 扫描守卫），新测试属既有层级，无新测试层级或运行方式。✓

### 7. frozen / no-touch

- 独立复核 frozen SHA 与 plan §1 字面一致：`docs/cli_ci_scenarios.json = a357e5a1e0ee11cb42f8ab6e25083b23761a4c8181d14ddc1876f0bf9a788efb`、`docs/cli_ci_oracles.json = 88b04ca47472f320b614ad1374a9f0a243443efaca1e0565eaf29b5f0cb770b8`。
- `git status --short` 仅 3 个修改文件 + 3 个 docs artifact；Host/Engine/runtime/config/Service/storage、`_build_pending_assets`、material workflow、frozen JSON 零改动；`git diff --check c54a4fd8` pass。
- 本轮及 fix 均未执行 UF-PF03。✓

## Open Questions

无。

## Residual Risk

- AST guard 结构严格性：外层新增 `try/finally`、tuple handler 或裸 except 会在无语义回归时使 guard 失败（假阳性），断言无自定义 message。属合同锁的可接受权衡；若未来该 guard 频繁误报，可放宽为「handler 序列子序列匹配」而非结构同构。
- material generic `str(exc)` 原始文本面（`sec_upload_workflow.py:592,598`、`cn_pipeline.py:1200,1206`）仍存在，为既有 material 失败语义，明确排除在本 WU 外；归后续 material failure-semantics 工作项。
- `_DOCLING_FAILURE_CODES[error.kind]` 为 dict 索引（`upload_failure.py:182`）：若未来新增 `DoclingConversionFailureKind` 成员而漏配映射，mapper 会在 workflow except 体内抛 KeyError（同 try 的兄弟 handler 不捕获），filing 会以未投影异常终止。当前枚举 6 成员全部映射、无该路径；属既有 mapper 设计的演进注意项，不在 F1 范围内。
- pre-fix 「1 failed」证据未独立复现（只读约束禁止 stash），但推导与证据链一致。

## 验证命令与结果（本 review 独立执行）

- `pytest -q -p no:cacheprovider tests/fins/test_docling_upload_service.py tests/fins/test_sec_pipeline_upload_filing_stream.py tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_cn_pipeline.py tests/fins/test_fins_ingestion_runtime.py` → `334 passed, 3 warnings`。
- `pytest -q -p no:cacheprovider tests/fins/test_fins_ingestion_runtime.py -k test_filing_workflows_consume_only_typed_admission_failure_before_generic_handlers` → `1 passed, 234 deselected`。
- `python -m pyright`（3 个变更文件）→ exit 0，`0 errors, 0 warnings, 0 informations`。
- `git diff --check c54a4fd8` → pass；frozen SHA 复核、`rg DoclingConversionError` 静态审计、git status no-touch 复核均通过（见 §7）。
