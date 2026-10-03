# 正式 PR197 review 总控修复登记

- gate：正式 PR review；work unit：upload-material-unified-repair。
- target：base `fac32ecbff9bfe792b63ee9667c8697826b631f4` ... head `44c1892e7361dba799154fc01b2a4dfe43407e75`。
- MiMo / ds-flash 均已托管 outer0 结束并经总控核收；成立项收齐为 UPR-R01/R02，gpt-6-sol一次集中fix已actual0/fullpyright0；同版MiMo/DS复审及总控全轨迹核收完成，两项已修，不增加slice。PR gate通过，下一accepted PR review commit；不是WU final closeout。

## UPR-R01：OCR 辅助转换用 object/getattr 消去已知 Docling 契约

- 裁决：accepted；状态：已修复。严重程度：低。
- 入口：`utils/ab_ocr_convert.py:_extract_full_text`，由 `main` 传入真实 `ConversionResult.document`。
- 直接证据：目标 head 第 59 行签名 `document: object`，第 70 行 `getattr(document, "iterate_items")`；随后直接迭代返回项。该 PR 新增完整脚本；当前返回值有明确 DoclingDocument owner，不是异构插件协议。
- 项目约束：AGENTS.md 编码硬约束禁止 object / 无法严格检查的签名；getattr 需充分理由，不能逃避类型/边界。utils 仅免测试和覆盖率，没有豁免此项。
- 影响：真实转换输出至全文/数字证据的链路失去方法及迭代项的静态契约，未来上游 API 变化不能由此调用处类型检查发现；现有代码不证明错误抽取，不将抽取准确性纳入项目职责。
- owner / 修复方向：使用第三方 DoclingDocument 类型并直接调用其 iterate_items；仅类型导入可在 TYPE_CHECKING 下，不新增 parser / 通用 adapter / 验收门槛。保持原全文及数字 token 逻辑。
- 验证：受影响工具的静态检查及项目全量 pyright；无需重跑完整 OCR A/B 或新增 utils 单测。
- 风险：低；生产业务逻辑不变。

## UPR-R02：新增分析工具的 dict 签名未声明数据形状

- 裁决：accepted；状态：已修复。严重程度：低。
- 直接证据（均为本 PR 新增脚本）：`utils/build_semantic_sample_list.py:30` 返回 `tuple[dict[str, dict], dict[str, dict]]`；`utils/diagnose_semantic_digests.py:65,124` 输入/输出裸 `dict`；`utils/inspect_semantic_digests.py:49,70,92` 输入裸 `dict`；`utils/pptx_docx_smoke.py:251,267` 输入 `list[dict]` / `dict`；`utils/trace_missing_tokens.py:41` 输入裸 `dict`。AST 定位明细保留在本轮 tmp `root-signature-observations.json`。
- 同源数据链：digest 由 `build_semantic_digests.py` 产生，已有明确 `DigestResult` / `DigestDocument` / `DigestTable` / `DiffBlock` 等类型；消费者直接下标读取相同字段。schema 样本结果由 `docling_schema_regression.py` 产生，已有 `ItemCounts` / `SchemaSummary` 等类型。诊断行由 `_diagnose_one` 产生并由 `_suspect_score` 消费。
- 项目约束及影响：AGENTS.md 禁止无类型参数的签名；当前 pyright 配置包含 utils，但基本检查通过不代表这些签名符合明确约束。无参数 dict 隐式消去输入/输出形状，消费者无法静态发现字段/值类型漂移。
- owner / 修复方向：优先复用现有生产者的数据类型；仅为本地诊断结果/密度输入补必要显式形状。保持既有读取、排序、统计、裁剪、输出及异常行为；不新增财务质量门槛、JSON 验证框架、兼容转换或改变抽取逻辑。
- 验证：对应工具及全量 pyright；utils 按项目规定免测试及覆盖率，不为类型标注重跑昂贵真实 Docling 转换。
- 风险：低；与 UPR-R01 同一次集中 fix/re-review 收口，不新增 slice。

## 待合并的双审结果

两路正式完整 main...44 审查已结束；DS 两项与root递归AST收束为 UPR-R01/R02。MiMo无新增业务finding，root补两未改MRO context行、收窄报告范围/历史计数/失败概述后部分采纳。详见两路 formal-pr root audit。

## Residual Risk

- 本轮已登记修复：fixed in current slice（本PR gate集中fix/re-review已核通过）。
- 完整 CLI CI / oracle/scenario：assigned to later assessment，用户明确要求修复 WU final closeout 后独立执行。
- Linux / Windows XBRL 部署验证：assigned to later work unit，依既有平台延期裁决。

## 集中修复最终同版复审裁决

UPR-R01/R02均已修复：gpt修复report/rootproof、491delta、8source身份、全pyright0、9382保护项zero、两路outer0/完整工具轨迹核收与必要实际逐字Read闭合。参见formal-pr-rereview-ds/mimo-root-audit及相应coverage proof。两原报告保留，不覆写。

UPR-RR-MIMO-01：rejected-with-reason；无现存提前读取texts_delta/对外误投影，其反例要求未来新增代码。当前cast恒等/数据流和owner实际字段正确，新增view层不属于本goal必要修复；不新增micro-slice。两路临时diff越own tmp写入及掩盖失败已root如实登记，不冒全部工具成功。

当前accepted修复无未修/部分修/失效项、无blocking open question；正式PR review pass，下一accepted PR review commit、普通push/readback，后draft-PR-pass/final closeout。完整CLI/registry仍独立未启动。
