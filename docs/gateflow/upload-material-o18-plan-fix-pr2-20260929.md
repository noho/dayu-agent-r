# UM-O18-F01 PR2 计划修订证据

- Gate：`plan review -> fix`。本轮仅修订 `docs/gateflow/upload-material-o18-amended-plan-20260929.md`；产品代码、测试、README、goal 和裁决均不修改。
- 修订前计划 SHA-256：`162e28ca093379e55a7cd2f34b071169c54c4fd46caa6ad23cf5e70db5a03bc6`。此值在改动计划前锁定。
- 修订后计划 SHA-256：`61a6cb02eacaed4e3e48e63d9bacb6b22cf1c46cd635530338a0f4250e27b62d`。
- 基线 HEAD：`8d8d494fbbce0052372fb1b42097c9f7222cfa28`。
- 裁决来源：`docs/gateflow/upload-material-o18-plan-review-adjudication-20260929.md` 的「MiMo 第二轮同版 plan re-review 与总控裁决」及末节用户 overwrite 裁决；原审查 `docs/reviews/plan-review-20260929-044006.md`、第二轮 `docs/reviews/plan-review-o18-rereview2-mimo-20260929.md`。当前 O18 checkout 的 review artifact 仅有这两份 MiMo，未发现 O18 Kimi review；本轮没有派发复审，不宣称双路通过。

## PR2-F1～F6 直接证据与修订

| Finding | 直接证据与修订后的计划落点 | 验收或停点 |
| --- | --- | --- |
| F1：同版 guard 消费面 | O12 当前候选计划 §「storage 同版状态与分阶段 guard」把 source business meta 与 opaque revision 分列，并要求材料 batch 同时注册 admission `expected_source_state` 和公司阶段后 `expected_company_meta`；`prepare_upload` 只收 `previous_meta`，现行 `_get_source_meta_unguarded` 返回前剥离 revision（`dayu/fins/storage/_fs_source_document_core.py`）。plan §4.2–3 改为 mutation 只带身份/目标业务值，由持有 admission 与公司 outcome 的 workflow 注册两项条件；`stage` 用 `CompanyMetaCommitOutcome.company_meta`，`keep/skip` 用 admission.company_meta。准备期不再重读公司/source 或猜 revision；仅 storage guard 做权威重读。 | O12 已集成并按实际 public 签名逐参核对；缺 source/revision/post-company 条件即停 implementation 回 plan review。合法公司阶段独立提交，材料冲突不回滚它。 |
| F2：skip 陈旧报告 | O12 候选计划同节明确 material skip 无 mutation 时在 storage guard 内只读比较 source 与 post-company；现行 `DoclingUploadService.prepare_upload` 在 Docling 前直接返回 skip，原 plan 又把报告窗口归 O33。plan §3/§4.2–3/§7 现把 prepare 结果定为**拟 skip**，经 O12 guard 双条件匹配才报告 `skipped/published_amended`；A 拟 skip→B toggle commit→A 报告必须 typed stale，不能返回旧值。 | 真实仓储 A/B 交错分别覆盖 metadata-only commit 与 skip 报告，A typed 拒绝且 B 的 meta/manifest/资产不回退；O33 只留 guard 外重试与诊断。 |
| F3：八格与 overwrite | `dayu/fins/pipelines/docling_upload_service.py:_can_skip_upload` 对 overwrite=true 禁 skip；同文件 material fingerprint 由 original name/hash/size/source 组成且当前 `identical_skip_safe=true`，`_resolve_document_version` 同安全指纹保版、异指纹升版。用户末节裁决同字节切标记无 overwrite 只改元数据，带 overwrite 强制转换发布。plan §3 以同/异指纹 × 标记同/异 × overwrite false/true 写全八格：无 overwrite 同指纹同标记 skip、异标记 `metadata_updated` 且 stored=0/零转换/文件发布；overwrite=true 两格同指纹都 Docling 转换/完整发布、`ok`/真实 original 数/vN；异指纹四格均转换发布、vN+1。 | owner 测试逐格核状态、转换调用、original/派生文件、meta/manifest/版本/计数；真实 CLI 步骤 2 对步骤 5 验证用户裁决。fingerprint 若未来不安全，按现有版本 owner 规则，不推断保版。 |
| F4：三域字段 | 当前 `MaterialManifestItem` 无 amended（`dayu/fins/domain/document_models.py`），source meta/storage 为发布真源；`read_runtime.py` 内部解析和列表输出当前都叫 `amended`，缺省 false；`ingestion_runtime.py:_upload_request_summary` 当前请求摘要也是裸 `amended`。plan §3 逐表面正/反名单：持久 source meta/manifest 为必填 bool `amended`；material 输入参数仍 `amended`、请求摘要/started 只 `requested_amended`；material 终态与 read LLM-facing 列表/详情只 `published_amended`，内部 typed read 可保留 `amended`；filing 请求/身份/read/结果原键不改。 | fresh schema 缺键/错型 fail closed；对 source kind 分支与混合 read 列表逐面断言两侧键名，不添旧键 shim。 |
| F5：LLM-facing 语义 | MiMo 第二轮指出内部表注不足以约束 LLM；现行 `upload_tools.py` 的输入描述仍是“上传文件是否为修订版本”。plan §3/§4.5 要求 tool 参数与结果字段说明、工具可读结果、job LLM 上下文自足说明：`skipped` 是本次零 material 改动的原有发布值，`deleted` 是最后发布值，均不代表本次切标记；`failed/cancelled` 为 null，不等于 false，也不证明旧材料不存在，失败原因另取 `failure`。read active 输出同理。 | `tests/fins/test_fins_ingestion_tools.py` 同时断言说明文案与实际结构化输出，含 skip/delete/failure；不靠计划表注或内部标识让模型猜。 |
| F6：CLI action | O14/O15 裁决 active create-existing 无 overwrite 为共享准入 typed conflict；原 canary 对 toggle/skip 未固定 action。plan §6 的 11 步每步显式 `--action`：首发/合法 toggle/skip 用 auto，active 明确更新用 update，delete 用 delete，恢复用 auto；步骤 2 无 overwrite metadata-only 对步骤 5/6 `update --overwrite` 强制重发。另用独立 identity 固定 A16/A17 形态的 action。 | 每步保存 exact argv、输入 SHA、exit/输出、转换证据、original/Docling 文件 hash、source meta/manifest、版本/计数及跨命令 read；O14/O15 实际准入不符即停修计划，不偷用 create。 |

计划中的先决条件仍是 **O12 同版 guard、O14/O15 共享准入已接受且完成集成**；当前 HEAD 不能把候选 O12 文本视为已实现 API。O13 重删时间/终态独立合流检查，O33 guard 外一般并发独立；filing amended 身份与 read 合同保持原样。

## 验证与未决风险

- 文档检查：八格的三维组合恰好各一次；计划无尾随空白；修订后 SHA 已复算。未修改 goal、裁决、产品、测试或 README；未运行 pytest、pyright、coverage 或真实 CLI，因为本轮仅修候选计划。工作树其余未跟踪文件是本轮开始时已有的文档，本轮只修改计划并新增本 artifact；未 commit、push、PR、merge 或派发 Agent。
- 直接停止条件核验：现行 material fingerprint/version owner 可以一致表达用户 overwrite 裁决；O12 候选合同可以在计划层表达独立 revision、source/company 双条件及 skip guard。其实际集成形状尚未知，故实施硬停且须在实施前重核；不新增下游重算或兼容 shim。
- 未决风险：O12/O14/O15 未集成，当前计划仍须 Kimi/MiMo 有效双路 re-review；O13 重删的 0 文件 `skipped` 与本计划 material upsert `skipped requested>=1` 若在合流时相撞须回终态 owner 裁决；旧 schema 不兼容读取，需 fresh workspace；真实 CLI 的市场依赖和 Docling 证据均待 implementation gate 验证。
- 失败命令披露：`rg -n 'amended|upload_material|source_kind' dayu/fins/tools/read_tools.py dayu/fins/tools/read_runtime.py dayu/fins/tools/read_schemas.py` 退出 2，原因是 `read_tools.py`、`read_schemas.py` 在本 checkout 不存在；随后只读核对实际 `read_runtime.py`。未把该检索当作通过证据。
