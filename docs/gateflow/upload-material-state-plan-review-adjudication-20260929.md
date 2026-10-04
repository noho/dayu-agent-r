# UM-O14/O15 plan review 总控裁决登记

- 当前 gate：plan review 进行中。MiMo 首轮 review `state-plan-review-mimo-20260929-01` 尚未返回结构化结果；Kimi 有效第二路尚缺；本文件仅登记总控独立代码/计划核对，不代表 gate pass。

## 总控预先登记的修复项

**C1：与 O12 material 同版状态 owner 重复。** O12 当前候选计划 `docs/gateflow/upload-material-o12-company-plan-20260929.md` 已把 `MaterialUploadPublishedState` 与同版 company/source business meta + opaque revision 的 storage 协议读取列为唯一真源；本计划 §「最小设计」第 1 项又写成从零新增 material published/staging state，依赖段遗漏 O12。两项涉及同一个 exact target、presence/tombstone/revision 与 publication guard，若分头实施会产生两个 public contract 或重复读取逻辑。裁决方向：O14/O15 implementation 以 **O12 状态 owner 已接受并集成** 为硬前提，实读其最终 API，仅对动作判定确需的 open-batch staging 同版读取作最小扩展并复用同一状态类型/语义；不能复制第二套 snapshot、在下游重算或靠两个仓储读拼同版。若 O12 最终 public contract 无法表达状态重检，则先回计划裁决最小 owner 扩展。该 finding 由总控在等待 MiMo 期间独立发现，待 MiMo/Kimi 和 Sol plan fix 后复审。

**C2：单 batch 公司/材料发布路径也与 O12 重叠。** O12 候选计划已把旧两次 company/material commit 收拢为一个 caller-owned batch/一个 commit 作为它的成功条件；O14/O15 计划 §4 与 S2 仍写成再实现相同收拢。后项应在 O12 已集成的单 batch 路径上增加动作状态的 writer-owned 重检与 typed 冲突，验证不回退公司业务事实，而不第二次重构同一 workflow。若 O12 最终实现未满足原子性，先回 O12 gate 修复其已确认目标，不能让 O14/O15 承担前项欠账。此项与 C1 一并等待独立 review 后裁决。

产品代码未实施；不得依据此预裁决提前修改计划或实现。

## MiMo 首轮结构化 planreview 与总控裁决

MiMo `docs/reviews/plan-review-20260929-051004.md`：预检 ok、显式 `/private/tmp/dayu-upload-state`、独立 output/stderr，process exit0、Claude JSON `subtype=success/is_error=false/terminal_reason=completed`、canary `mimo-6571eea8` 匹配，stderr 仅白名单模型名提示，`agent_status=completed`。结论 `pass-with-risks`，7 项 finding；**高项未闭合，不能计 plan pass**。Kimi 有效第二路尚缺。

| Finding | 总控裁决 | Sol plan fix / 验收 |
| --- | --- | --- |
| F1 高：三态动作表缺 create/update+tombstone | **accepted，保持 binding goal 的非目标**。material `create+tombstone` 仍由现有 source upsert/storage 拒绝，不在本项擅自把它改为成功或新 typed O14 规则；filing 保持现有 target-exists。material `update+tombstone` 沿现有可恢复路径，不因 active-only 规则误拒。 | 共享 evaluator 的输入明确 source kind + exact 三态，闭合所有格但只把 O14/O15 已接受的 active/missing 格改为新 typed 结果；对 tombstone 格写明现行路径与隔离回归，不留实现者猜。若实现必须改变 material tombstone create 终态，停止并回 goal，而不是在此拓宽。 |
| F2 高：遗漏 O12 同版状态/公司决策 | **accepted finding，拒绝 reviewer 的“O12 follower、预留槽位”顺序建议**。总控 C1/C2 已登记：O12 的同版 company/source snapshot 和单 batch 公司/材料 publication 必须先 accepted+integrated，O14/O15 消费其**实际** public contract，不另造空槽或第二套 state。 | plan 改成 O12 硬依赖；在实施基线实读 company decision、source meta/revision、validated request、共享单 batch 接缝。O14/O15 仅扩动作状态与 writer-owned staging 重检；静态文件组合→目标状态→公司名顺序与 O16/O12 对齐，补混合错误测试。若 O12 无法表达，回 owner plan 裁决。 |
| F3 中：S2 SEC/CN 可能复制 publication 状态机 | **accepted**。shared publication owner 应由 O12 已集成的唯一 material commit 路径提供，Fins shared precondition 只判动作。 | 两市场只传 request/市场事件，writer 重检与冲突/commit 由同一 owner 执行；计划和 owner 测试明确对象身份/调用点，不能在两个 workflow 各写状态机。 |
| F4 中：writer conflict 文案、优先级、分类 owner 不清 | **accepted，但不采纳“漂移后再按 fresh 动作表报 usage”**：admission 时静态→目标→公司；**已接收之后** initial→writer 同版状态变化统一 `source_publication_conflict` typed，不能把竞态误报为用户原请求缺字段/目标不存在。无漂移但初始状态违反动作表早已在 admission 拒绝。 | `upload_failure.py` 的 public reason/message 改为业务可读的来源文档（或 material 专用文案），不把 material 称 filing；`fins_upload_failure_from_exception` 精确直通已 typed `FinsUploadFailureError`，usage→failure 在原 Fins owner 映射，三市场消费同一 reason。加竞争与两入口文案/LLM-facing 测试。 |
| F5 中：REPAIR_REQUIRED/UNSAFE 与 delete 交叉格 | **accepted 须明确，拒绝 reviewer 建议在损坏 source 上放行 delete**。用户确认的重复 tombstone 成功指可信完整状态；REPAIR_REQUIRED 虽 meta 可信但 source 树不完整，storage 最终完整性无法证明安全发布，仍 fail closed；UNSAFE 更不得猜 missing。 | 计划矩阵写 COMPLETE tombstone + delete 允许；REPAIR_REQUIRED/UNSAFE 各动作均由 storage typed integrity/operational 拒绝，不映为目标缺失、不旁路修复。测试健康重复 delete 和损坏状态 fail closed。若现有代码直接证据证明 storage 可安全删除损坏 source，需另做 owner/goal 裁决。 |
| F6 中：依赖接缝、就绪核对、CLI 并发/优先级验收 | **accepted**。 | O16/O05/O17/O07/O09/O10/O12 的实际 owner 接缝与实施前核对列明，但不猜未实施 API；可控 barrier 属 owner/仓储自动测试，真实 CLI 只测可稳定复现状态矩阵；加无 files+missing、delete 携 files+missing、缺公司名+missing 的第一错误测试。 |
| F7 低：skipped 公司的同批意图未决 | **accepted，由 O12 先定**。O12 已把 material skip 时 company-only/空 batch 同源提交列为计划内容。 | 以 O12 已集成的实际 skip/公司发布合同为前提，保持现行有意公司更新的结果；O14/O15 只回归，补 active+同内容 skip+公司意图测试，不独立设计第二套 batch。 |

MiMo OQ1 source protocol 归属由 O12 最终实现决定，本项不先预留第二协议；OQ2 并发 delete-during-delete 统一 post-admission drift conflict，健康重试可走 O13；OQ3 create+overwrite 同内容遵循当前 overwrite 触发发布的独立回归，不能偷偷变 skip。以上均在修订计划中固定测试或残余。Sol 下一轮只修本 plan，后续 Kimi/MiMo 对同版计划有效复审；产品仍未实施。

Sol `state-plan-fix-sol-20260929-01`：预检 ok、显式 `/private/tmp/dayu-upload-state`、独立 output/stderr，process exit0、JSONL `turn.completed` 且无失败 command/error、canary `gpt-6-sol-64c0b2f1` 匹配、stderr 空，`agent_status=completed`。总控核对计划 SHA `b4d98a8d57e3d3a959f1358b0ffff3406b4a691698f0d653229604cfa2ce1ba0`：O12 accepted+integrated 和 O16/身份依赖硬门槛、kind×三态表、健康/损坏 tombstone 分界、接收后漂移同一 publication conflict、两市场共享 owner、稳定 CLI 与注入并发分层、skip 公司意图均写入。此为修订候选，尚需 Kimi/MiMo 对同版有效 plan re-review；未实施产品。

## MiMo 第二次同版复审与总控裁决

MiMo `docs/reviews/plan-review-20260929-054535-state-mimo.md` 对上述 SHA 同版复审，结构化完成、canary `mimo-1919d834`、结论 `pass-with-risks`。旧 F1–F7、C1/C2 闭合，但新增以下修复项；计划尚不能计 pass，Kimi 有效第二路仍缺。

- **F8 高，accepted，跨 O12 owner 修复。** O12 候选 `source_meta=None` “无有效 active”有歧义；若 COMPLETE tombstone 被投影为 None，`auto` 会误解为 create，显式 update 会重置 `document_version`、`first_ingested_at`、`created_at`。O12 storage 同版状态必须保留 tombstone 的完整可信 canonical business meta，含 `is_deleted=true`、`deleted_at`，并与 presence/tombstone 和 revision 同版；仅真正 missing/unsafe 无可信 meta 才是 None。O12 owner 测试要断言 auto+tombstone→update、update 恢复保持首次时间且版本递增。O14/O15 计划将此列为集成前硬核对和停止条件，并对恢复连续性作回归；不能下游补造 meta。已同步登记 O12 裁决和主队列。
- **F9 中，accepted。** O14/O15 计划须准确列出 `UploadOverwritePrecondition`、`FinsUploadUsageCode`、`FinsUploadFailureCode` 的 target closed-code 增量，三个 public target reason 统一投影为 `FinsUploadFailureKind.USAGE`，并将 `tests/fins/test_upload_failure.py` 放入受影响切片白名单和验证命令。把“无新 schema”明确为无新数据形状/协议，但 closed public enum 成员确有扩展。owner 测试断言 kind/code/message、typed exception 直通和 filing 既有投影不漂移。不得复用误导性 `storage_io` 或按字符串重算。
- OQ filing 的 delete-missing 不对称：本 WU 仅 material，filing 保持现行；若需要 filing 的新 typed 行为另立 goal。S2 guard 仍复用 O12 唯一比较，实施前按最终集成 API 收窄白名单。

下一步仅由 Sol 修 O12 与本计划文本，之后 Kimi/MiMo 对各自同版计划有效复审；产品未实施。

## 总控对 Sol 第二次修订候选的独立拦截

`state-plan-fix2-sol-20260929-01` 预检 ok、绝对 cwd/独立 output/stderr/last-message，process exit0、JSONL `turn.completed`、canary `gpt-6-sol-c6343f32`、stderr 空；一条误读不存在的 O12 adjudication 路径的复合 `sed` 命令 exit1，严格 `agent_status=failed`。总控实读候选 SHA `6571ffb44b263d48d0ed2e40668006f086b32b64c9a99e23e3877c9a58518070`，F8 的 COMPLETE tombstone meta 硬依赖和 F9 的 closed enum/测试文件已入文，但发现新的阻断性合同冲突，**不得用此版进入 review/pass**。

- **F10 高，accepted，O13 已接受事实优先。** 候选 plan §Pure/prepare owner 写“相同内容的恢复也必须测版本递增”，与主工作区 `docs/reviews/upload-material-um-o13-oracle-adjudication.md` 用户已接受行为直接冲突：UM-A09 在同内容 auto 恢复原 ID，版本保持 v3；当前 `_resolve_document_version` 对相同 fingerprint 保留旧版本。O12 因复审只用“不同旧指纹”验证递增是恰当分层，O14/O15 必须改为两格：同内容 tombstone 恢复版本不变，内容不同且满足既有版本规则才递增；两格均保留 `first_ingested_at`/`created_at`，复位 `is_deleted`/`deleted_at`，meta/manifest 同源。不得把 O12 的“非 None 避免重置 v1”误读成“所有恢复都递增”。在依赖核对、纯函数测试和 CLI 矩阵中保持此区别。若实测代码不能同时满足，返回 source version owner/goal 裁决，不改写 accepted oracle。

Sol 只修本 plan 的 F10，并核对 F8/F9 不回退；之后同版 Kimi/MiMo 复审。产品未实施。

`state-plan-fix3-sol-20260929-01` 预检 ok、绝对 cwd/独立 output/stderr/last-message，process exit0、JSONL `turn.completed`、canary `gpt-6-sol-2681de1f`、stderr 空；三个探索查询命令 exit1/2，按严格协议 `agent_status=failed`，只采纳总控独立核对的文本。候选 plan SHA `4ae27dadd044b3ed4185079a0397a90f9eeb4bbc1faad25fab6f2426b4f9a7f4` 已把同指纹恢复保留旧版本、不同指纹按现行规则递增写入矩阵、owner 测试和停止条件；F8/F9 仍在。待 Kimi/MiMo 对此同版有效复审，产品未实施。

## 跨 O34 阻断：不能消费 O12 单 batch 候选作为已接受前提

主工作区 `docs/reviews/upload-material-um-o34-oracle-adjudication.md` 是用户已接受行为：合法公司 identity/meta 可在 material 转换失败或取消后独立保留，文档缺 manifest 条目仍未成功。O12 当前候选的“prepare 后公司/材料唯一 batch”会撤销此公司事实；总控已在 O12 adjudication 登记 blocking F3，撤回此前对无条件单 batch 的支持。当前 O14/O15 计划 §O12 依赖、§writer-owned 复验、S2/测试/stop condition 多处把 O12 单 batch/单 commit 当硬前提，**因此旧候选 SHA `4ae27d...` 不可计 plan pass/实施**。后续本 plan 必须消费 O12 重订后的实际公司独立提交与材料单独 guard 合同：稳定目标拒绝仍在公司写入前；合法公司已提交后的材料转换/取消保持 O34，接收后材料状态漂移不得使材料错误发布，但不能无依据承诺公司业务零发布。manifest 必须由权威材料 commit 保证；不能 UI/CLI 回滚公司。O12 新版确认前，O14/O15 仅保留目标状态矩阵与公共 failure owner 的条件设计，整体回 plan gate。当前正在运行的 MiMo 第三次复审针对被阻断旧 SHA，只作旧版证据，不能放行。

## MiMo 第三次旧版复审与新增低项

MiMo `docs/reviews/plan-review-20260929-state-rereview3-mimo.md` 对旧 SHA `4ae27d...` 结构化 success、canary `mimo-8227b431`、stderr 仅白名单模型提示，结论 `pass-with-risks`；其范围读了 O13/O14/O15 和旧 O12，**未包含 O34 已接受公司独立持久化裁决**，故不能推翻上节 blocking 反例，也不能计 Gateflow plan pass。其 F8/F9/F10 在旧版本内部闭合可保留为修订时回归要求。

新增低 finding **F11 accepted**：plan 声称 tool 与 Fins public failure 有完全相同的 `kind/code/message`，而现有 `upload_tools.py:101-133` 把前置 `ValueError` 投影为 tool 协议 `invalid_argument`，无 Fins code 字段；原 O15 binding 只要求 Fins typed reason 跨市场同源。修订时须明确 tool 的业务可读 message/hint 消费同一 Fins usage 真源，tool 协议 code 保持其自身封闭合同；awaited Fins summary 才投影 Fins public code。若要改 tool 协议形状，须回 goal/schema 裁决并扩 `upload_tools.py` 白名单，不能用“同码”口号掩盖实际协议差异。

MiMo 另发现 O12 adjudication 早期“恢复版本递增”未限定指纹。总控确认 O12 **当前计划**已限定不同旧指纹才递增、同内容 UM-A09 保旧版本；O12 adjudication 早期句被最新 F8/F10 裁决覆盖，Sol 修 O12 计划时要逐字钉死，不能从历史段复活错误断言。产品未实施。

## Sol 第四次修订候选与总控核对（2026-09-29）

`state-plan-fix4-sol-20260929-01` 预检 ok、绝对 `/private/tmp/dayu-upload-state`、独立 JSONL/stderr/last-message；进程 exit0、`turn.completed`、canary `gpt-6-sol-52472e74` 匹配。但两条探测/替换命令 exit1，stderr 有非白名单 `apply_patch verification failed`，严格 **agent_status=failed**。总控实读候选 SHA-256 `cdf8d73d73c72b1dbf716b5c1cb964dbd99d90cdb3d1b689f010f68f7f0c4c70`：旧 O12 单 batch 前提已撤，依赖改为公司独立提交与材料自己的同版 guard；稳定目标拒绝早于公司写入，后续材料失败/取消可留合法公司事实，manifest 才算文档成功。O13 同指纹恢复旧版本/异指纹按现行规则升版、F11 tool `invalid_argument` 与 Fins message/hint 同源、Fins public code 留 awaited summary 都入 plan。O12 SHA `45b6478a...` 仍是双路待审条件候选；本项必须在 O12 accepted+integrated 后重核实际 API，若变更则回 plan/re-review。当前仅作 Kimi/MiMo 同版审查候选，**非 plan gate pass/产品实施**。

## 总控新增依赖基线修复项（2026-09-29）

- **C3 中，accepted／未修复**：本计划 SHA `cdf8d73d...` §依赖仍锁 O12 旧候选 `45b6478a...`，写“O12 仍待双路复审”；但 O12 已经 Kimi/MiMo 同版 plan gate pass、accepted plan checkpoint `b201d9f3b1c84e49fe0751d75ea7dc31e2c0f14c`，当前计划 SHA `48e0598bd8c949e7257b6fd6c6a03adbdca31b0def2d680d4b0cea93f7ed5e60`。旧条件候选不再是准确依赖真源。修计划时以 accepted O12 plan/裁决核 company 独立 commit、材料同版 source+post-company guard、COMPLETE tombstone 可信 meta、active-only 终态保存与 alias/typed 分类；将“待双路 review”改为“计划 accepted、产品未实施且未集成”，O12 accepted+integrated 仍是 O14/O15 implementation 硬门槛。不得把 accepted 计划当已存在 API、也不得自行补 O12 实施。F8～F11 和 O34/UM-A09 已裁行为保持。
- 下一 entry：gpt-6-sol 仅修 C3 计划及新 fix artifact；随后 Kimi/MiMo 对同一最终 SHA 重新 planreview。产品未实施，PR #197 未包含本 WU。

## Sol C3 计划修订候选核验

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- gpt-6-sol `state-plan-c3-fix-sol-20260929-01` 显式绝对 state workspace、独立 JSONL/stderr/last-message/canary，进程 exit0、JSONL `turn.completed`、41 条完成 shell 中一次 memory `rg` 无匹配 exit1，stderr 有非白名单 Goal router 错误（`get_goal` 需要 persistent thread），canary `gpt-6-sol-560461ed` 匹配。按全工具/逐命令协议严格 `agent_status=failed`，不能以最终计划 SHA 代替执行成功。fix artifact `docs/gateflow/upload-material-state-plan-c3-fix-20260929.md` 原样披露。
- 总控实读 C3 fix artifact 和计划新 SHA `5b74854bc10873e29fa94a716d88713d7ee48bd9236eb3d0a6d6a5445efeb191`：O12 依赖改指 accepted checkpoint `b201d9f3` / plan SHA `48e0598b...`，产品未实施/集成；公司独立 commit、材料自己的同版 source+post-company guard、COMPLETE tombstone 可信业务 meta、alias 与 typed 分类及 O12 active-only 终态保存均作为实施前核对，而非当前 API 声称。旧候选 SHA 与“待双路复审”时态已移除；O34 公司事实、UM-A09 同指纹版本、F8～F11 均在修复记录中保留。C3 **计划内容候选已修**，须由独立 Kimi/MiMo 对本 SHA 从 actual O12 accepted 合同与 state owner 再审，不能提前 accepted plan commit/实施。

## MiMo C3 同版复审与投影 owner 缺口

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
canary_status: match
warnings:
  - "Claude stderr: [claude-code:unrecognized_model] mimo-v2.6-pro[1m]；精确白名单非致命诊断"
retry_class: none
```

- MiMo `state-plan-c3-rereview-mimo-20260929-01` 显式绝对 state workspace、独立 JSON/stderr/canary，进程 exit0、JSON `subtype=success/is_error=false/stop_reason=end_turn`、49 turns、canary `mimo-38f1feb5` 匹配；`docs/reviews/plan-review-20260929-150200.md` 锁 state plan SHA `5b74854...`、O12 HEAD `b201d9f3`/plan SHA `48e0598b...`，全部检查命令自身 exit0。内容认为 C3/O34/UM-A09/F8～F11 无回退，新增一项低 finding；该有效一路尚不能使 plan gate 通过。
- **PR-C3-F1 低，accepted／未修复**：state plan §5 把“`ingestion_runtime.py` 的精确 usage→public 映射”写成既有事实，但现有 `FinsUploadUsageFailure` 仅 code/message，`FinsUploadFailureReason` 全部在 `upload_failure.py` 构造且含 retry_hint；tool 仍在自身 `except ValueError` 中拼通用 hint。总控实读 `ingestion_runtime.py:707-741`、`upload_failure.py:37-105`、`upload_tools.py:121-127` 后接受：修计划明确 usage fact/message/hint 由唯一 Fins usage owner 产生，`upload_failure.py` 是唯一 Fins public reason 构造/映射 owner，消费 typed usage fact 映射三个 target code 与 hint；tool 的 typed usage 分支只消费该同源 fact 的 message/hint，协议 code 保留 `invalid_argument`，无第二张 code→hint 表。当前接口尚无 hint，应把其承载字段及 producer 列为待实施新增，不虚称既有。若选择另一 owner 必须明确迁移并避免双构造点，不能只用“同源”字样。补 owner/tool/failure 测试白名单与一手投影断言。
- C3 内容候选已修但本 finding 未修；下一 gate gpt-6-sol 仅修 PR-C3-F1 计划与新 fix artifact，再 Kimi/MiMo 同最终 SHA 复审。O12 产品未集成，state 产品未实施。
## Sol PR-C3-F1 计划候选核验

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- gpt-6-sol `state-plan-prc3f1-fix-sol-20260929-01` 显式绝对 state workspace、独立 JSONL/stderr/last-message/canary，进程 exit0、JSONL `turn.completed`、canary `gpt-6-sol-e07b8934` 匹配；一次 `rg` 猜错 `tests/fins/test_upload_tools.py` 路径 exit2，另有 JS 包装语法失败，严格 `agent_status=failed`，候选不计有效实施 gate。新修订记录 `docs/gateflow/upload-material-state-plan-prc3f1-fix-20260929.md` 如实披露。
- 总控实读 state plan 新 SHA `f2496dd1da34f0556cff7e032b6f68ba7e7918b525c7b7aae5318b5ddc420cee`：当前 usage fact 仅 code/message、hint 待实施新增；Fins usage owner 产生 kind-aware code/message/hint，`upload_failure.py` 唯一构造 public reason 并映射三 target code、原样传同源 message/hint；tool typed 分支消费同一 fact、协议 error 仍 `invalid_argument`，普通 ValueError 的通用 hint 不变。若跨模块需搬类型，先迁入 Fins 下层 contract，禁止反向 import/兼容 re-export。owner 与入口测试白名单、O12 未集成硬门槛均保留。**PR-C3-F1 计划内容候选已修**，state 产品未实施。
- 下一 gate 同一 plan SHA 的有效 Kimi/MiMo 独立 `$planreview`；此前 review 只针对旧 SHA，不跨版计数。

## MiMo PR-C4 format usage 与测试边界裁决

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- MiMo `state-plan-prc3f1-rereview-mimo-20260929-01` 显式绝对 state workspace、独立 JSON/stderr/canary，进程 exit0、JSONL `turn.completed`、canary `mimo-0fb9d6f0` 匹配；`docs/reviews/plan-review-20260929-164438.md` 锁 plan SHA `f2496dd1...`。四条探索命令非零（含 `/private/tmp` 扫描权限拒绝及无匹配 rg），严格 `agent_status=failed`，不计有效 MiMo plan gate。内容判 fail，以下根因由总控核读计划与 owner 代码接受。
- **PR-C4-F1 中，accepted／未修复**：当前 `FinsUploadUsageFailure.code` 还接受 `FinsUploadFormatFailureKind`，而 `_raise_upload_format_usage` 直接构造 fact，绕过计划所称唯一 `fins_upload_usage_failure` producer。给 fact 增必填 hint 会让 format 路径失败，或迫使第二套文案/hint、tool fallback；既有 format error 的 `file_label` 还须同源进入 public reason。计划须明定 format owner 产生何种 typed fact、usage 装箱与 hint 必填/校验边界，覆盖全部 format kind、原有 usage、三 target，`upload_failure.py` 仍唯一 public reason 映射，tool/direct/可达 awaited 消费同一 message/hint/file_label。不得在 `_raise_upload_format_usage` 或 tool 复制 message/hint 表。
- **PR-C4-F2 低，accepted／未修复**：现有 `tests/fins/test_company_identity_storage_contract.py:636-670` 直接锁 alias conflict/corruption 的 public reason 和 JSON round-trip，state S1/S2 扩 closed code 分组/alias 优先却遗漏此文件于测试白名单及 focused 命令。补入并锁 alias/identity 分类、retry_hint、JSON 同源；若 O12 最终 API 迁移则迁移 owner 测试，不能删掉这条合同证据。
- O12/O34/UM-A09/F8～F11、状态机与原子 guard 无新反例。下一 gate Sol 仅修 PR-C4-F1/F2 计划与新 fix artifact，同最终 SHA Kimi/MiMo 有效复审前不实施 state。

## Sol PR-C4 计划候选核验

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- gpt-6-sol `state-plan-prc4-fix-sol-20260929-01` JSONL `turn.completed`、canary `gpt-6-sol-6ecb257c` 匹配，stderr 空；一次精确路径探测的复合命令内部 Git exit128、一次重复替换断言 exit1，且中断后 exec session 退出码不可回读，严格 `agent_status=failed`。总控实读新 plan SHA `1fe2f5462a0d7a7bdb54edda3985965713a2e87890f5c8dba9b9c823e98778b6` 与 `docs/gateflow/upload-material-state-plan-prc4-fix-20260929.md`：format owner 产角色/public 双文案、hint 和 canonical label，统一 Fins usage producer 装箱且 hint 必填/校验；`upload_failure.py` 唯一 public 映射，tool 同源消费 usage message/hint；S1/S2 增 alias/public reason 测试与两条 focused 命令。**PR-C4-F1/F2 计划内容候选已修**。O12 产品未集成，下一 gate 同 SHA Kimi/MiMo 独立 plan review，state 产品未实施。
## PR-C4 MiMo 同版复审内容核验

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- MiMo `state-plan-prc4-mimo-20260929-01` 进程 exit0、JSONL 186 条可解析、`turn.completed`、82 条 shell exit0、无 error/failed event、stderr 空、canary `mimo-40234d2e` 匹配；四条探索命令 exit1/2/2/1，违反该次任务正文额外“所有检查命令自身 exit0”，严格不计有效 plan gate。`docs/reviews/plan-review-state-prc4-mimo-20260929.md` 锁 plan SHA `1fe2f5462a0d7a7bdb54edda3985965713a2e87890f5c8dba9b9c823e98778b6`，内容 pass-with-risks、零 material finding：PR-C4-F1/F2 的 producer/mapper/tool 和 alias 测试清单已闭合；O12 产品未集成是实施硬门槛。canonical label 算法在 `direct_events.py`，format owner 装入并校验事实，实施不可复制算法；raw CLI format 入口须纳入同一 typed fact 测试。Kimi 同版仍在途，state 产品未实施。

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- Kimi `state-plan-prc4-kimi-20260929-01` 进程 exit0、JSONL 226 条可解析、`turn.completed`、86 条 shell exit0、无 failed/error event、stderr 空、canary `kimi-74886b45` 逐字匹配，唯一 artifact `docs/reviews/plan-review-state-prc4-kimi-20260929.md`。内容 pass-with-risks、零 material finding；总控复核 format fact 与 usage producer/public mapper 的 owner 分工、alias 白名单及 O12 accepted checkpoint 与停止条件均与计划一致。MiMo 同版内容也无 finding，但结构化失败；需唯一修复性 MiMo 复审才可计双路 plan gate。即使双路通过，O12 accepted+integrated 前 state implementation 仍不得启动。
- 对上一 MiMo 同 SHA 审查的非零命令执行协议失败，按新 label `state-plan-prc4-mimo-rereview-20260929-01` 修复性重派：同计划 SHA `1fe2f546...`、显式绝对 state workspace、独立 JSON/stderr/canary、固定新 artifact，preflight ok，session `49527` 在途。Kimi 原有效一路保持，只在本轮 MiMo 结构化及内容有效后判双路 plan gate；O12 产品未集成硬停不变。

## PR-C4 MiMo 修复性复审新增计划缺口

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: ["[claude-code:unrecognized_model]"]
retry_class: none
```

- `state-plan-prc4-mimo-rereview-20260929-01` 进程 exit0、JSON success/50 turns、canary `mimo-4d4e69a4` 匹配，stderr 仅白名单提示；锁同一计划 SHA `1fe2f5462a0d7a7bdb54edda3985965713a2e87890f5c8dba9b9c823e98778b6`。review `docs/reviews/plan-review-state-prc4-mimo-rereview-20260929.md` 自披露一条复合 `rg && sed` 因无匹配 exit1，违反本轮所有 shell 命令自身 exit0 的额外合同，严格 agent_status failed；Kimi 有效结论不能单路通过 plan gate。其内容 pass-with-risks、新低 finding 与 OQ 由总控实读计划 §5、`ingestion_runtime._USAGE_MESSAGES`、`FinsUploadFailureReason.retry_hint` 和 CLI raw format 入口后裁决如下。
- **PR-C5-F1 中低／accepted／未修复**：同一 CREATE_TARGET_EXISTS/UPDATE_TARGET_MISSING code 同时用于 filing/material，但当前 `_USAGE_MESSAGES` 是一码一文案，filing 旧文案与 material “目标材料”文案不同；计划没有指定统一 producer 的 source-kind 入参，实施者会造第二表或改错 filing 文案。计划明确 usage producer 接收 source kind/目标名词，由同一 code+kind 投影文案/hint；filing 旧文案逐字保持，material 文案自足。DELETE_TARGET_MISSING 仅 material。测试同码两 kind 正反例，不能下游补文案。
- **PR-C5-F2 低／accepted 为类型边界／未修复**：计划“hint 不允许 optional”只适用新增 usage fact 的 hint 必填；`FinsUploadFailureReason.retry_hint` 既有 `str | None` 且非本 WU 的 reason 允许 None。修计划明说 target/format 映入 public reason 时须非空，**不收紧全局 reason schema**。
- **PR-C5-F3 低／accepted 为入口验收／未修复**：CLI material file selection 的 raw `FinsUploadFormatError` 可在 runtime producer 前抛出，既有 CLI 单独捕获；计划必须要求该实际入口经同一 typed fact 的 message/hint 或共享 validator 归一，并在测试矩阵锁 raw CLI 与 runtime/tool 同源，不能只测 `_raise_upload_format_usage` 后假定入口已统一。
- canonicalizer 算法现唯一在 `direct_events.py`，format owner 只装入/校验；旧计划已按此边界表述，不接受“为独占而迁移/复制算法”的额外修复。PR-C5-F1～F3 修计划并新 SHA 双路有效复审前不得实施 state；O12 产品尚未集成仍为实施硬停。

## PR-C5 Sol 计划候选及暂停交接

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- `state-prc5-sol-20260929-01` 进程 exit0、78 条 JSONL 有 `turn.completed` 且无 failed/error event、stderr 空、canary `gpt-6-sol-67e4e85e` 匹配。仅修计划并新增 `docs/gateflow/upload-material-state-plan-prc5-fix-20260929.md`；新计划 SHA-256 `4ab1546efdc7f73a5acbd79064299459b6062af95acc4db1283fbb9ae6f0b24d` 已总控复算。
- 总控实读 fix 与新 §5：target 同码双 kind 的唯一 producer 文案/hint、fact hint 必填而 public reason optional、CLI raw format 早期异常回同一 typed producer 均为明确的实施落点/测试；PR-C5-F1～F3 **计划内容候选已修**。用户现要求完成当前 WU 后停下，故本 WU 不再派新 SHA 双路 review；下一 Agent 应从该计划 SHA 的 MiMo/用户授权 Kimi 额度备份 ds-flash 同版 plan review 接手。O12 产品未集成，state 产品未实施、plan gate 未过。
