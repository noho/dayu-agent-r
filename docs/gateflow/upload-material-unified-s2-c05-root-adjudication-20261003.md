# S2 US2-C05 总控裁决：推荐槽位保留文档引用合同

## 状态与直接依据

US2-C05：计划中“两个列表”的前提不符合真实返回类型，**rejected-with-reason**；原 amended 单一发布事实的 accepted 修复及 V9 验收保持，不能据此豁免真实文档事实投影。

同一个 WU/S2，HEAD `f7e60c9d3e4c6e77a6c2abf18d09cd8020c19235`，唯一 workspace `/Users/leo/workspace/dayu-agent-r`、分支 `codex/upload-material-oracle`。原计划 SHA `c99c35adba919a8baf371b0142e0ab1abf256a951e89b2fc15e8a2d38988e8ea` 保持，不添加 schema、slice/gate 或新验收标准。

总控直接核对了本轮报告、当前与精确 HEAD 的 `read_runtime.py::_collect_list_document_recommendations`、`list_documents`，以及 `tools/result_types.py::ListDocumentsResult`、`tools/fins_tools.py` 和正式 `docs/reviews/upload-material-um-o18-oracle-adjudication.md`。真实 `documents` 是逐文档事实列表，`recommended_documents` 始终是推荐槽位 → document_id/null 的映射，包含基于全量文档的推荐，筛选后的 documents 可以不包含该推荐引用。正式 O18 要求源 meta、manifest 和已有事实事件/结果同源，没有裁决将引用映射改为事实列表。

## 确定的实施与验证边界

1. 保留 recommended_documents 的既有 ID/null 映射和推荐/筛选规则，不改为列表、嵌套事实或加入 amended 字段；不扩 `result_types.py` 白名单，不新增 unfiltered 文档列表，不让推荐映射成为第二个业务事实真源。
2. 每份材料在真实 documents 事实投影中输出 `published_amended: bool`，严格消费其已读取 source meta 的唯一 amended reader；filing 保既有 amended 字段。推荐选择复用同一次已严格读取的 typed 文档集合，引用仅标识文档，不能携请求意图或从版本/标题/时间反推 amended。
3. 两个输出位置的既有同源成功信号按实际合同验证：真实无过滤 list_documents 的材料条目为实际发布 true/false，latest_material_document_id 指向该条目的同一 document_id；同 marker metadata 更新后读取反映新的 persisted flag，推荐仍按现有身份；缺失/非 bool amended 在 owner 失败关闭，不因它只可能被推荐而默认 false。过滤时引用可能不在 filtered documents，是现有规则，不构成新增缺陷或补偿理由。
4. 如需让 LLM 理解引用与事实的区别，在既有白名单 fins_tools.py 的当前 description 最小说明：推荐槽位是文档 ID 引用，材料当前修订事实见文档条目的 published_amended。不暴露 opaque revision、内部类型或要求模型重算。

这里纠正真实类型前提，落实已接受的 owner 事实投影；不是新增业务取舍或修改公开返回形状，无需用户再确认。按本明确边界同轮继续全部 S2；首末版本核验、受影响 tests/full pyright 和同版双审仍必需。不能把本 rejected 的“第二事实列表”当未修复 accepted finding，也不能宣称真实 amended 投影已通过 review。
