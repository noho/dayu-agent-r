RUNTIME/PROVIDER/MODEL: claude/mimo/mimo-v2.6-pro[1m]
CANARY=mimo-7fa02fba

# UM-O18-F01 PR3 候选计划独立审查（MiMo）

- 审查时间（本机系统时钟）：2026-09-29 20:01:30 CST
- 审查对象：`docs/gateflow/upload-material-o18-amended-plan-20260929.md`
- 计划 SHA-256（实测）：`0d3f109b2f538d26cddd8ca6b4dd89da03e3ac27cd7e57915aefaa4b055892ce`，与目标 SHA 一致
- Binding goal：`docs/gateflow/upload-material-o18-amended-goal-20260929.md`（goal confirmation pass）
- 最新总控裁决：`docs/gateflow/upload-material-o18-plan-review-adjudication-20260929.md`（含 PR3-F1 撤回、PR3-F2～F9、用户 2026-09-29 overwrite 公开行为裁决）
- PR3 fix artifact：`docs/gateflow/upload-material-o18-plan-fix-pr3-20260929.md`
- **结论：pass-with-risks**
- **material findings：2 条（均为低严重度、未修复、accepted-candidate），无中/高/严重级发现**
- **残余：processed 快照独立 WU、拟 skip 比较后微窗口、上游未集成硬停、filing 独立风险（均已有跟踪去向）**
- **验证声明：本次审查只做静态读码与文档核对。未运行 pytest、pyright、真实 CLI canary 或任何产品命令；计划中的测试/CLI 步骤是未来实施验收配方，不是本轮运行结果。本文件不是 implementation handoff。**

## 1. 审查目标与范围

按 `$planreview` 对候选计划做 constructively adversarial 审查：以独立证伪为目标，优先核验①八格状态机、②全 material mutation/skip 的同版 guard 消费、③read LLM 投影 owner、④processed amended 时间真源、⑤O13 重删交界、⑥上游集成依赖（O05/O12/O14/O15/O16 与 O13/O33）。范围为计划 artifact、binding goal、总控裁决、PR3 fix、O12 accepted plan、O14/O15 共用 state plan、O13 goal 与本工作区当前代码（基线 HEAD `8d8d494fbbce0052372fb1b42097c9f7222cfa28`）。非目标：不修改计划/目标/裁决/产品/测试/README/旧 review，不实施、不提交、不派发。

## 2. 上游证据身份核验（全部实测一致）

| 证据 | 计划声明 | 实测 | 结论 |
| --- | --- | --- | --- |
| 目标计划 SHA-256 | `0d3f109b...92ce` | `0d3f109b2f538d26cddd8ca6b4dd89da03e3ac27cd7e57915aefaa4b055892ce` | 一致 |
| O12 accepted plan（`/private/tmp/dayu-upload-o12/docs/gateflow/upload-material-o12-company-plan-20260929.md`） | SHA `48e0598bd8c949e7257b6fd6c6a03adbdca31b0def2d680d4b0cea93f7ed5e60` | 同值 | 一致 |
| O14/O15 共用 state plan（`/private/tmp/dayu-upload-state/docs/gateflow/upload-material-state-plan-20260929.md`） | SHA `1fe2f5462a0d7a7bdb54edda3985965713a2e87890f5c8dba9b9c823e98778b6` | 同值 | 一致 |
| state plan 第 103 行 tombstone+create 无 overwrite | 保持现有 source upsert/storage 拒绝、不作新 typed O14 标准 | 原文逐字核对一致 | 一致 |
| O13 重删合同 | 重删终态 `deleted`、O13 拥有时间幂等 | `/private/tmp/dayu-upload-o13/docs/gateflow/upload-material-o13-tombstone-goal-20260929.md`：同周期重删「仍返回成功/已删除」，保留 `deleted_at`/`updated_at`/业务字节；O18 amended 另行处理 | 一致 |
| O12/O14/O15 产品未实施 | 计划称接口尚不存在 | `rg 'MaterialUploadPublishedState|read_material_upload_state|MaterialUploadPublishedStateConflictError' dayu/` 零匹配（显式捕获，预期无匹配） | 一致 |

## 3. 假设证伪与代码事实核验

逐项尝试证伪计划的直接证据主张（`file:line` 为本 HEAD 实读）：

1. **输入链路**：`ingestion_runtime.py:1573` `FinsUploadMaterialRequest.amended: bool = False`；`upload_batch.py:191/542/582` filing/material entry 均透传 `amended`；`dayu/cli/commands/fins.py:347/694/735`、`upload_tools.py:276-278/344/361` 均接收/传递。**传输缺口确认**：`service_runtime.py:198-270` `_run_material_upload` 到 SEC/CN/HK 的调用参数无 `amended`；`sec_upload_workflow.py:537-558` material `prepare_upload(meta=...)` 无 `amended`（同文件 232 行 filing meta 有）；material `UPLOAD_STARTED` payload（493-508 行）无该字段。计划动机成立。
2. **八格的 skip/版本/身份基础**：`docling_upload_service.py:1616-1648` `_can_skip_upload` 只看 repair 授权、overwrite、`is_deleted`、`identical_skip_safe` 与指纹相等——**不含 amended**，同指纹异标记今天会被 skip 吞掉，计划 cell 2 修的正是此洞；`:1723-1735` material 指纹 payload 为 name/hash/size/source 且 `identical_skip_safe=True`（死例外已按 PR3-F6 删除）；`:1745-1770` `_resolve_document_version` 初次 v1、异指纹升版、同指纹保版；`:1820-1851` `build_material_ids` 仅 form/name/fiscal，amended 不进身份；`:329-330` `_build_upsert_meta` 清 tombstone。八格与用户 overwrite 裁决（同字节切标记：无 overwrite 仅元数据、带 overwrite 强制重转换/发布、同指纹保版）逐格一致；delete/恢复格与 `:1643` tombstone 禁 active skip 一致。八格内部无矛盾。
3. **同版 guard 消费面**：O12 accepted plan「storage 同版状态与分阶段 guard」（O12 计划 43-47 行）明定 material batch 双 precondition（`expected_source_state` 全值+独立 opaque revision 与 post-company `expected_company_meta`）、skip 在同一 guard 只读比较、`MaterialUploadPublishedStateConflictError` 单一 typed 冲突。O18 计划 §4 第 2/3 条逐字消费该合同，且按 PR3-F2 把**每个** material mutation batch（metadata-only、delete、常规/overwrite 内容发布）纳入双 guard 注册、拟 skip 只读比较，不自建第二套 guard、不凭 `get_source_meta` 猜 revision。当前 `replace_source_meta`（`_fs_source_document_core.py:950-1009`）确为显式 batch 精确覆盖+同批 `MaterialManifestItem.from_source_meta` 投影、`_prepare_complete_source_meta`（1898-1927）剥离并重写 storage revision——计划「当前同批精确替换不足以证明条件发布安全」的判断准确。
4. **read LLM 投影 owner**：`fins_tools.py:387-419` `_build_list_documents_definition` 是 `list_documents` LLM-facing 说明真 owner（白名单条件收录 ✓）；`read_runtime.py:607-639` `_parse_source_document_meta` 缺 `amended` 默认 false（`:632`），计划对 material 改 fail closed ✓；`:887-915` `documents` 项现含裸 `amended`、混合列表无 source_kind 分支，`:725-773` `recommended_documents` 仅 ID/null 槽位，`:2546-2575` `_SourceDocumentMeta` 为内部投影且 `is_deleted` 过滤——与计划「read 只取 source meta 当前发布事实、tombstone 不显示为 active、详情不虚构」逐点一致。三域键名（内部/输入 `amended`、请求摘要与 started `requested_amended`、结果与 read `published_amended`）与 PR2-F4/PR3-F3/F4 裁决一致。
5. **processed 时间真源**：`ingestion_runtime.py:8491-8514` `_build_processed_meta` 整体复制 source meta；`_fs_processed_core.py:565-588` 以宽松 `bool(...)` 写 processed manifest `amended`；`read_runtime.py:2750-2776` 仅从 processed meta 取财务能力标志。全仓 `.amended` 属性消费扫描（显式捕获）未见任何消费者把 processed/`DocumentSummary.amended`（`document_models.py:856-905`，源自 processed manifest）当作当前发布事实投影到 read/tool/结果——计划的停止条件当前不触发，独立 WU `fins-material-processed-amended-projection` 登记合理，O18 不改 processed writer 的边界正确。
6. **O13 重删交界**：O13 goal 明定同周期重删「成功/已删除」+ 时间字节幂等；O18 终态表重删为 `deleted`（requested=stored=0、保留最后发布 amended），`skipped` 仅指有文件的 identical upsert（requested>=1，与 `ingestion_runtime.py:1853-1864` 现有计数闭集一致）。两者无冲突；计划 §8「不把 O13 时间幂等改作本项验收」切分干净。
7. **终态/投影可行性**：`_UPLOAD_TERMINAL_DISPOSITIONS`（`ingestion_runtime.py:327-333`）现为 ok/skipped/deleted→COMPLETED、failed→FAILED、cancelled→CANCELLED，`metadata_updated`→COMPLETED 是精确单点扩展；`sec_upload_workflow.py:635-648` 与 `cn_pipeline.py:1901-1914` `_resolve_upload_status` 仅映射 uploaded→ok、其余原样透传，`metadata_updated` 可直通；`FinsUploadResultSummary.__post_init__`（1830-1877）计数矩阵可按计划扩展；direct 详情由 `ingestion_runtime._upload_result_details`（6903-6937）构造，工具终态 value 由 `fins_wait_adapter._completed_result_value` 通用透传 details（566-587）——LLM-facing 解释可全部落在白名单内 `ingestion_runtime.py`/`upload_tools.py`/`fins_tools.py`，无白名单外 owner 缺口（`direct_events.py`/`direct_event_text.py`/CLI/Service 状态渲染均为通用枚举透传，不需要改动）。
8. **上游依赖闭合**：O12/O14/O15/O16/O05 未集成为实施硬停、逐格核对与回 plan review 的停止条件齐全；O12 若无法表达三类 material batch 与 skip 条件则回裁决最小扩展——owner 归属清晰，无自造兼容。

## 4. findings

### 1-未修复-[低]-state plan 第 102 行「相同内容→skipped、材料零 diff」未标注被八格细化，存在跨计划合流歧义
- **位置**: 计划 §3 八格（同指纹×异标记→`metadata_updated`）、§7 O14/O15 集成边界；对照 `/private/tmp/dayu-upload-state/docs/gateflow/upload-material-state-plan-20260929.md:102`
- **问题类型**: 契约缺失（跨计划合同精度）
- **当前写法**: 计划 §7 精确引用了 state plan 第 103 行（tombstone create）并声明八格「先经 O14/O15 共享 action/target 准入」，但未处理 state plan CLI 状态矩阵第 102 行「active + update/auto，相同内容并有合法公司更新意图 | 按 O12 集成合同 skipped；公司更新生效，材料零 diff」。
- **反例/失败场景**: O18 集成后，同内容但 `amended` 变化的 update/auto 走 cell 2（`metadata_updated`，材料 meta 有 diff），而 state plan 第 102 行字面预期是 `skipped`、材料零 diff。若 O14/O15 的真实 CLI 矩阵或回归测试按第 102 行字面固化「相同内容→skipped」且其样本带标记差异，或后续集成者把两份计划当成互相矛盾，将在合流时产生误判或错误回归失败。
- **为什么有问题**: skip/metadata-only/content 的决策 owner 是 O18 的八格（state plan 动作表 48 行自己写「update…ALLOWED，沿现有 update/skip」，即决策外放），但 state plan 的验收矩阵行在 O18 引入标记维度后已不精确；O18 计划逐行引用了 103 行却漏掉 102 行的同类修文需求。
- **直接证据**: state plan `:102` 原文；O18 计划 §3 八格 cell 1/2 与 §7 对 state plan 的引用（只引 103 行）；state plan `:48` 动作表把 skip 决策留给「现有 update/skip」。
- **影响**: 合流/集成期回归误判、两计划文本冲突被误读为设计分叉、O14/O15 测试固化与 O18 相反的终态。
- **建议改法和验证点**: 在 §7 的 O14/O15 段加一句：state plan 第 102 行的「相同内容→skipped、材料零 diff」由八格细化为「同内容**且同标记**→skipped；同内容异标记→`metadata_updated`（仅 amended/updated_at/revision 变化）」，并要求 O14/O15 回归/CLI 矩阵不固化无标记维度的 skip 断言；合流测试加一条「同内容异标记 + 公司更新意图」对照（公司更新生效、材料为 `metadata_updated` 而非 skipped）。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 2-未修复-[低]-cell 2「仅更新 amended」对同请求非 amended 元数据的冻结未钉死构造真源与测试断言
- **位置**: 计划 §3 八格 cell 2（「仅更新 amended、updated_at、storage-owned revision 与同批 manifest，内容字段、首次时间及文件字节不变」）、§4 第 2 条 `_PreparedMaterialMetaMutation`（「只携稳定身份、业务目标 amended 与构造 staged meta 必需的业务字段」）、§6 owner 测试断言清单
- **问题类型**: 契约缺失 / 测试缺口
- **当前写法**: cell 2 的结果合同是「仅更新 amended+updated_at+revision+manifest」，但 staged meta 的构造真源未钉死为「admission previous business meta + amended 替换」；mutation 描述「构造 staged meta 必需的业务字段」可被读成携带**本次请求**的业务字段（如更正后的 `filing_date`/`report_date`）。
- **反例/失败场景**: 同字节重传且用户更正了 `filing_date`：同标记时落入 cell 1 skip、异标记时落入 cell 2——按 cell 文本日期应保持旧值（与今日 skip 吞日期一致，无回归），但实现者若按第二种读法把请求日期写入 staged meta，就会出现「同指纹异标记更新了日期」的隐性合同漂移；§6 的断言清单（精确 bool、meta/manifest 同值、ID/fingerprint、版本、文件字节、revision/updated_at）不含「非 amended 业务字段不变」，测试拦不住该漂移。反向同理：若产品意图是元数据-only 应同步请求元数据，cell 2 的冻结本身就是错的，两者目前没有裁决。
- **为什么有问题**: 同一「元数据变更」家族里 amended 被救出、日期更正仍被同指纹路径静默丢弃（goal 句「不能被相同指纹 skip 吞掉元数据变更」按字面读可涵盖日期）；同时 mutation 构造描述有双读法，owner 级精确规则未完全自足。
- **直接证据**: 计划 §3 cell 2 文本与 §4 第 2 条 mutation 描述；`docling_upload_service.py:288-331` `_build_upsert_meta` 以请求 base_meta 合并九字段（内容发布路径会刷新日期），与 metadata-only 冻结路径不对称；§6 断言清单无「非 amended 字段不变」；binding goal 成功信号 2 的「不能被相同指纹 skip 吞掉元数据变更」原句。
- **影响**: 实现走错读法产生未裁决的元数据写入；或测试固化错误行为；日期更正场景静默丢弃无任何契约说明。
- **建议改法和验证点**: ①在 cell 2 或 §4 明写 staged meta = admission 同版 previous business meta 仅替换 `amended`（并列出不变字段含 `filing_date`/`report_date`）；或经裁决改为「更新本次请求的全部非身份业务元数据」并同步改 cell 文本；②§6 断言清单补「cell 2 的非 amended 业务字段逐字段不变（含日期）」；③若维持冻结，在 LLM-facing `metadata_updated` 说明中已有「本次只改变了该标记」的基础上，于 open question 请总控确认 goal 的「元数据变更」是否仅限 amended。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## 5. open questions

1. **八格二元之外的「旧指纹缺失/无效」格**：八格把「同指纹」限定为「`identical_skip_safe=true` 且旧指纹有效」，其余归「异指纹…按现有 `_resolve_document_version` 递增」；但现有 `docling_upload_service.py:1767-1770` 在旧指纹为空时**保版不递增**。该格对正常 material（所有 upsert 路径均写指纹、O12 UNSAFE/REPAIR 先 fail closed）实际不可达，但建议计划补一句「旧指纹无效不在八格内，按现有版本 owner 保版行为处理」，避免实施测试写反断言。
2. **goal「元数据变更」的范围**：binding goal「不能被相同指纹 skip 吞掉元数据变更」按文义可涵盖非 amended 元数据（见 finding 2）。维持 cell 2 冻结即只对 amended 兑现该句；请总控确认此为预期范围，或授权扩大 cell 2 语义。

## 6. 残余风险与跟踪去向

| 残余风险 | 去向 |
| --- | --- |
| processed meta/manifest 的 `amended` 是 preprocess 时点快照，metadata-only 后可与发布值不同 | 计划 §8 已登记独立 WU `fins-material-processed-amended-projection`（时间语义/失效重处理/消费者契约）；本次全仓扫描未发现把它当当前发布事实的消费者，实施前按计划停止条件逐调用链复核 |
| 拟 skip 的 guard 只读比较通过后、报告前存在微窗口（B 可在比较释放后提交） | 事务化读-报语义，与 O12 accepted 合同一致（裁决窗口「prepare→B commit→A 无验证报告」已由 guard 关闭）；LLM-facing 文案已要求判断现态时重新读取；不再开新 WU，若未来要收紧可在 O33/O12 合同内讨论 |
| O16/O05→O12 与 O14/O15、O13、O33 均未集成 | 计划 §4 第 1 条/§7 硬停条件已覆盖；O18 完成报告须列各集成版本与 owner 重核 |
| filing identical skip 吞 filing amended | 计划 §1 已登记 `fins-filing-amended-identical-skip` 独立跟踪，不纳入本 WU |
| 旧库 material meta 缺 `amended` 被 fail closed 后读失败 | 全新 schema 起库、不承诺旧库读取（符合 AGENTS.md schema 规则）；README 读者边界内按计划判定是否需要运维说明 |
| state plan 第 102 行字面预期与八格的合流歧义 | finding 1，待总控裁决后在计划 §7 补一句修文 |

## 7. 结论

**pass-with-risks**。理由：

1. **身份与证据链完整**：目标计划 SHA、O12/state 两份上游 SHA、state plan 103 行、O13 goal 合同均实测一致；PR3-F2～F9 修订逐条落到计划文本，撤回的 PR3-F1 未再被虚构。
2. **六项重点证伪均未击穿**：八格与用户 overwrite 裁决、现有 skip/版本/身份 owner 代码逐行一致且无内部矛盾；全 material mutation（metadata-only/delete/content）双 precondition 与 skip 只读 guard 的消费面与 O12 accepted 合同严丝合缝、owner 闭合、不自建第二套 guard；read LLM 投影 owner（`fins_tools.py`/`read_runtime.py`）与三域键名精确、白名单无缺口；processed amended 定性为时点快照且独立 WU+停止条件完备；O13 重删 `deleted` 交界无冲突；上游依赖链（O16/O05→O12→O14/O15→O18）硬停与回裁决条件齐全。
3. **遗留的两条均为低严重度精度问题**（跨计划第 102 行修文、cell 2 非 amended 字段冻结钉死），不构成结构性不安全，可由总控裁决后随下一次计划触碰顺手修入；另有两条 open question 收敛方向明确。
4. 依停止条件复核：计划 SHA 与上游证据身份相符、owner 可闭合、八格无不可裁决矛盾——允许通过结论。产品实施仍以 O16/O05/O12 与 O14/O15 集成为硬前提，本审查不构成 implementation handoff。

再次声明：本轮未运行任何测试、pyright 或真实 CLI，以上全部为静态证据核对结论。
