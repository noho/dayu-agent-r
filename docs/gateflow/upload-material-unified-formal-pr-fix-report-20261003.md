RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/gpt-6-sol
CANARY=gpt-6-sol-dd7e8579

# 正式 PR197 UPR-R01/R02 集中修复报告

label：`upload-material-unified-formal-pr-fix-sol-20261003-01`。仅实施已 accepted 的两项辅助 utils 静态契约修复；未新增 slice/WU，未重做业务裁决。本报告是实现与验证交付，PR gate、WU pass 与下一 gate 由 root 独立核收及同版 MiMo/DS delta 复审裁决。

## 输入与边界

已读 `AGENTS.md`、正式 findings register，并按需定位两路 formal-pr root audit 与既有 aggregate 同版证据。直接源码证明两项动机成立：已知 Docling 文档方法被反射抹去，消费既有 JSON 的函数签名缺少递归数据形状。影响限于静态检查；不证明或重评财务抽取准确性。

- workspace：`/Users/leo/workspace/dayu-agent-r`。
- 初末 HEAD：`44c1892e7361dba799154fc01b2a4dfe43407e75`。
- 初末 main：`fac32ecbff9bfe792b63ee9667c8697826b631f4`，只读。
- 初末 branch：`codex/upload-material-oracle`。
- 初末 index diff SHA：`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`，无 staged 变更。
- 未派发子 Agent，未 commit/push/操作 GitHub，未修改 root register/control/历史报告、产品/tests/config/locks/README 或财务 Raw。已有 dirty 治理文件按原字节保留。

## UPR-R01

`utils/ab_ocr_convert.py:_extract_full_text` 的 owner 是真实 caller `ConversionResult.document` 所提供的 `DoclingDocument`。参数改为该真实类型，以 `TYPE_CHECKING` 导入并沿用 future annotations；直接调用 `document.iterate_items()`。去除 `object` 与 `getattr`，保留原 `TextItem` 筛选、顺序、换行拼接和数字 token 逻辑。原函数内 `TextItem` 导入未搬移，未增加 adapter、校验或抽取门槛。

## UPR-R02

- `_load_layers`：密度输入声明最小 `DensityRow`（stem/ticker/pages/density）。`workspace/tmp/docling-regression/pdf-textlayers.json` 实际不存在，未声称读取、生成或验证该文件。回归输入复用 `SchemaSummary` 与 `ItemCounts`；本脚本的 `SampleSummary` 仅描述原下标读取的计数视图及原 `texts_delta`。字典展开仍保留所有原摘要字段，原筛选、缺字段异常及计数差运算不变。
- `_diagnose_one/_suspect_score`：摘要形状由 `build_semantic_digests.py` 的 producer 负责；诊断指标由 `_diagnose_one` 负责，新增 `DiagnosticRow` 精确列出其原有 24 个输出字段，评分与 TSV 共用。诊断规则、排序、取样、统计与输出字段不变。
- `_print_diff_blocks/_print_numbers/_print_structure` 与 `_token_block_evidence`：复用 producer 的完整摘要静态视图及其嵌套类型，保持裁剪、格式化和块定位逻辑。
- `_table_cells_text/_merged_number_set`：复用 `DigestTable`、`DigestDocument`，保留原默认、单元格拼接和数字集合计算。

首次 full pyright 揭示 `DigestResult` 是构建中/异常前的可选字段视图，不足以直接描述这些消费者原本下标读取的完成结果；delete 块的 ratio 也在通用块类型中可选。故在允许 producer `build_semantic_digests.py` 补 `CompleteDigestResult`，复用原 `TextLens`/`NumberDiff`/`PairedTableSummary`/`HeadingSummary`/`OrderSummary` 等；补 `DiffBlockContent` 共用字段与 `DeleteDiffBlock` 的必写 ratio 视图。直接证据是 `_build_one` 成功路径原有字段赋值，以及 `_diff_blocks` 对 delete 块无论有无数字均写 ratio（无数字为 None）。原 partial `DigestResult` 和构建函数的输出行为保留。

这些 cast 是静态字段声明，恒等返回原值，不是运行时验证。诊断 delete 筛选后使用 producer 的 delete 视图；ratio 的 cast 仅表达原非空判断，原 get 与下标两次读取均保留。JSON/导出边界使用字符串 cast 类型参数；消费者的 producer 类型均在 `TYPE_CHECKING` 内导入，不因纯读 JSON 而加载转换模型。未新增 JSON parser/validator、fallback、重算或兼容分支。

## 实际改动

仅下列 7 个源文件发生变化：

- `utils/ab_ocr_convert.py`
- `utils/build_semantic_sample_list.py`
- `utils/diagnose_semantic_digests.py`
- `utils/inspect_semantic_digests.py`
- `utils/pptx_docx_smoke.py`
- `utils/trace_missing_tokens.py`
- `utils/build_semantic_digests.py`

`utils/docling_schema_regression.py` 原字节未变；仅从其既有类型读取静态契约。另新建本报告与独占 tmp；无其它新非忽略路径。

## 实际验证与失败恢复

两次均执行 `source .venv/bin/activate && python -B workspace/tmp/upload-material-unified-formal-pr-fix-sol-20261003-01/run_pyright.py`；采集器实际 `Popen(["pyright"], cwd=workspace)`，独立 stdout/stderr，使用 `Popen.wait()`，未用 echo/pipeline 改写退出码。argv、cwd、venv/Python、PID、时间、8 源文件运行前后 SHA、流 SHA 与实际 wait/returncode 均在原 receipt 中。

| 实际尝试 | Popen.pid | wait/exit | 实际 stdout | 票据（独占 tmp 下） |
|---|---:|---:|---|---|
| 1 | 4925 | 1 | 21 errors, 0 warnings, 0 informations | `pyright-receipt.json` |
| 2 | 4979 | 0 | 0 errors, 0 warnings, 0 informations | `attempt-02/pyright-receipt.json` |

首次 exit=1 的 21 项均为本轮采用实际 TypedDict 后暴露的 NotRequired 下标访问。未丢弃日志或票据；该版 8 源文件保存在 `failed-attempt-01-source/`，初版采集器保存在 `run_pyright-attempt-01.py`。按真实 producer 完成/delete 字段契约修正，并在样本清单边界声明原下标计数视图，第二次 full pyright 实际 exit=0。最终源 SHA 与成功票据完全相同。两次 stderr 都只有 pyright 可升级版本提示；未安装升级或改变配置。

- `verify_static.py` 实际 exit=0：递归遍历全部 8 文件的函数参数与返回注解，包含泛型 slice 内的嵌套容器，裸容器/object/Any 签名违规为 0。不是仅比较顶层注解字符串。
- 同一检查对 8 文件剥离类型声明、docstring、恒等 cast，并统一 R01 的旧方法绑定与直接调用、同一映射的 count_view 别名后，执行 AST 全部相等。其限制是静态等价核查，不是运行时文档/财务质量验收。
- 实际以激活 venv 的 Python `-B` 导入 6 个消费者，`docling*`/`dayu.documents*`/`dayu.fins*` 新加载模块列表为空；未执行 main 或转换，未写入 import bytecode。
- 最终允许 8 文件的 `git diff --check` 实际 exit=0。
- `check_guard.py` 实际 exit=0：9,382 个保护文件初末 zero drift；完整 tracked/nonignored 路径集合无未授权新增；guard 本身 SHA 未变；HEAD/main/branch/index diff 与初始 guard 一致。两次票据的真实双流 SHA、wait/exit、各自源前后 SHA 均匹配，成功版源 SHA 等于最终源。
- 辅助定位中初次批量源码与 source88 清单预览有工具输出截断；不将其作为全文证明。必要 owner/消费者源码已定点读取，source88 由 stdlib 完整解析逐 SHA 核查恢复为 88/88、zero drift，无空循环或省略项。

按 AGENTS 对 `utils/` 的明确测试/覆盖率豁免及本轮授权，不新增单测，不重复 pytest/真实 OCR/Docling/XBRL 内核。README 触发仅涉及产品层或用户工作流变化；本轮纯辅助脚本静态类型收口，无对应职责触发，不修改 README。

## 初末源身份

本表仅授权 8 源文件；完整保护清单未展开。独占 tmp 的 `initial-check.json`、`final-check.json`、成功 pyright receipt 与 own-summary 保存相同身份。

| 文件 | 初始 SHA256 | 最终 SHA256 |
|---|---|---|
| `utils/ab_ocr_convert.py` | `d7909e7747b3cb320e0861ef9d34b542a2c75c6a0934a015c66552c14531e548` | `db242df55627857d8c0dbfa83ca37c256b62c287ca848fc75f54408c062c8d2c` |
| `utils/build_semantic_sample_list.py` | `52a4d07685cda080f61aa1522625a3d2b808d1bb665403b42bd10d63fbc286c1` | `10cb39f31b46a38e9cc3678203d373702f12105bf24c0fbb9a46de92025f6ed3` |
| `utils/diagnose_semantic_digests.py` | `b83ab4dd92c95999def70c0cd40835909b741fa4268e82bbc5884850f8af2838` | `03f2bb69e4043e7e16efcd6161f42f16e12aa4579e20c3a841f2209393cb333c` |
| `utils/inspect_semantic_digests.py` | `a830586aabd089618cfc7a387db1a7dc39e1915e9fb40f1e28079e3637f67400` | `10e84931201d57759e0bf3366ca32fff9d22e0a8cae1e86efb72e5e6af7d48fc` |
| `utils/pptx_docx_smoke.py` | `f3812c3c78eef42aa6a4c19db802479886b8b9755afefde4d708d81936785fcb` | `92be59a3f774ddef12434f35707ce74268ddc806bacb7a1ab705ef89d6d533c4` |
| `utils/trace_missing_tokens.py` | `65231901d1817250a3786e36d361c3f76c6f009aa4f9e0886529d87a38726bc0` | `3f611fd22de030df2b024434daf2820a88062e28833fafda6868911f80ea8c27` |
| `utils/build_semantic_digests.py` | `9b5da92e8713cebdf5b2d3d3a47ee03d19792c6e5d22759784874b18d11a681e` | `636d9fb60f4121623ac9745668df6fe803542fa7f6702293c62d6097b31186b0` |
| `utils/docling_schema_regression.py` | `77481e460c2cc17586b1997921c8b450e42c48055eea7277e49e4592e4b47878` | `77481e460c2cc17586b1997921c8b450e42c48055eea7277e49e4592e4b47878` |

## 继承证据与风险

本轮实际完整解析并逐项核对既有 `workspace/tmp/upload-material-unified-aggregate-fix-sol-20261003-01/source-final-v2.json`（SHA `8b16119e01c413d869cf38a660ade0da5650ac4586a70530189abd002c1ca91d`）：88 项全部当前同 SHA，且全部包含在初始保护清单。生产/tests/config/财务 Raw 未改。`inherited-identity.json` 记录本次身份核查及对应 accepted root 报告；671 passed、2841 passed/3 skipped、真实 XBRL 5 passed 依原 root 核收的同版证据继承。本轮未重跑或逐一重验历史测试票据，不把它们说成当前 fresh 测试；当前 full pyright 是本轮实际运行。

风险限于静态视图对既有 producer/consumer 的声明：cast 不检查磁盘 JSON，缺字段/格式错误仍按原路径抛错；不存在的密度数据不具有本轮运行时样本证据。未验证抽取准确性、跨平台部署、完整 CLI campaign 或 registry，保持原延期/独立阶段归属；未扩 residual 或目标。实现交付后停止，等待 root 独立核全部工具、代码、票据与同版 delta 复审，未宣称 PR/WU pass。
