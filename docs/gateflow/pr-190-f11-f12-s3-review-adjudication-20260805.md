# PR 190 F11/F12 S3 implementation review adjudication

## Gate context

- Slice: S3 — fresh compact input/output v3 vertical migration
- Base: `1943904eea9e30357805c9f1d2b6f6e815b37c86`
- MiMo review: `docs/reviews/pr-190-f11-f12-s3-mimo-review-20260805.md`
- DeepSeek review: `docs/reviews/pr-190-f11-f12-s3-ds-review-20260805.md`
- Decision owner: Gateflow controller
- Decision rule: 每项 finding 单独依据 frozen contract、LLM-facing 北极星与直接代码证据裁决；两路 reviewer 是否一致不替代证据。
- Fix owner: AgentCodex
- Fix gate status: `SUPPLEMENTAL_FIX_COMPLETED`
- Next entry point: MiMo / DeepSeek fresh-session independent re-review

## Accepted findings

### A01 — LLM-facing 禁令仍暴露 Host “覆盖账本”术语

- Source: DeepSeek 010
- Severity: low
- Decision: accepted
- Evidence: `conversation_compaction_user.md` 直接写“覆盖账本”。模型只需知道不能输出材料统计/省略解释，不需要理解 Host coverage abstraction。
- Required fix: 改为业务可读的具体禁止事项；不得改变 Host-derived represented/omitted owner。
- Fix status: `已修复`。prompt 现明确禁止输出已保留/未保留材料的数量统计、逐项清单或省略解释，不再出现“覆盖账本”。

### A02 — repair 文本暴露 attempt 术语

- Source: DeepSeek 011
- Severity: low
- Decision: accepted
- Evidence: `llm_compaction.py::_user_prompt_vnext` 写“前次 attempt number”。模型只需要区分前次完整输出，不需要理解 Host attempt state machine。
- Required fix: 改为“前次输出编号”或同等业务可读表述；Host 内部 attempt binding、budget 与 durable identity 保持不变。
- Fix status: `已修复`。repair-only 文本使用“前次输出编号”；internal typed attempt binding 未改。

### A03 — cross-module public validator 未进入 `__all__`

- Source: DeepSeek 013
- Severity: low
- Decision: accepted
- Evidence: `validate_compact_represented_coverage_candidate_binding_v3` 被 `compact_artifact.py` 与 `compact_payload.py` 作为 typed owner helper 直接 import，而同级 policy validator 已在 `__all__`。
- Required fix: 将该 validator 纳入 `compaction.py::__all__`；这不是兼容 re-export，也不新增另一实现。
- Fix status: `已修复`。唯一现有 validator 已进入 `compaction.py::__all__`，owner test 锁定公共面。

### A04 — mechanical v3 test documentation remains stale

- Source: DeepSeek 014
- Severity: low
- Decision: accepted
- Evidence: reviewer 列出的 test helper/docstring 仍把已经迁移的 typed v3 candidate/input称为 v2。
- Required fix: 只修正准确命名，不改变 fixture 或生产语义。
- Fix status: `已修复`。reviewer 列出的八处 test helper/docstring 已机械改为 v3，无 fixture 行为变更。

### A05 — `session_summary` 的 meaningful-or-null 选择规则不够明确

- Source: controller adversarial pass（两路 review 未登记）
- Severity: medium
- Decision: accepted
- Evidence: frozen F08 要求“当前明确 cap 无法容纳有业务意义的 summary 时输出 null”；当前 prompt 只分别说明非 null 要可独立理解、null 会清除、禁止低信息占位，没有明确把 cap 不足与 `null` 动作连接，也没有明确禁止单字符/截断片段。真实历史反例正是 `"A"` 被接受。
- Required fix: 在 `session_summary` 字段附近用一句自足规则明确：若 cap 无法容纳有业务意义、可独立理解的摘要，则输出 `null`；不得用单字符、截断片段或占位文本凑非空。不得增加字符阈值、黑名单或自然语言 verifier；Host 仍只严格验证程序可判定的 shape/cap/低信息 contract。
- Required test: owner prompt test 锁定该选择规则与既有 `null` full-replacement behavior；不得宣称 deterministic test 能证明任意自然语言摘要质量。
- Fix status: `已修复`。字段邻近规则现明确 cap 不足时必须为 `null`，并禁止单字符、截断片段或占位文本；prompt owner test 锁定文本，既有 Memory owner test继续锁定 `null` 清除旧 summary 且保留其它四类语义。未增加或宣称自然语言质量 verifier。

### A06 — 初始请求没有精确说明各 section 的字符计量

- Source: controller adversarial pass（两路 review 未登记）
- Severity: medium
- Decision: accepted
- Evidence: prompt 只写“业务文本字符总量”。实际 owner `derive_compact_policy_usage_actuals_v3` / Context Governance 计算为：summary=`text`；facts=各 `claim`；anchors=每项 `title + "\\n" + detail`；intents=各 `text`；references=各 `text`。特别是 anchor 的换行符和 reference 的 `reason` 不计入 cap，模型无法从当前 prompt 自足推知，容易触发本可避免的 repair。
- Required fix: 以最小业务可读文本精确列出五种计量；优先由 Host 同一计量 owner 投影，或用 owner test锁定 prompt 与 estimator，禁止 provider 分支或第二 caps owner。
- Required test: 初始与 repair prompt 都包含 exact measurement contract；边界等于 cap 可接受、加一拒绝仍由 existing Host owner tests证明。
- Fix status: `已修复`。`compaction.py::compact_policy_usage_measurement_rules_v3` 从 actual 计量 owner 投影五类精确规则，Context Governance 与 initial/repair renderer 共用；owner tests 锁定规则、candidate actual、等于 cap 接受与加一拒绝。

### A07 — repair feedback fields 对无状态模型不自足

- Source: controller adversarial pass（两路 review 未登记）
- Severity: medium
- Decision: accepted
- Evidence: repair JSON 暴露 `code/json_path/message/source_labels`，当前 repair 指令没有解释这些字段。用户此前已明确要求 repair feedback 的块名、字段与限制自足；无状态模型不能依赖内部 issue type或代码路径理解它们。
- Required fix: 在 repair-only 文本中用短句解释：`json_path` 是需修正字段位置，`message` 是具体错误与动作，`source_labels` 是相关输入引用标签且不是业务事实，`code` 只是问题类别；issues 是有界摘要，必须结合本消息完整输入/规则整份重产。若某字段对模型动作无价值，可从 LLM-facing projection删除，但不得改变 Host internal typed report。
- Required test: initial 不出现 repair protocol；repair 包含字段语义、same immutable input、whole replay、bounded/redacted feedback，且继续无 digest/secret 泄漏。
- Fix status: `已修复`。repair-only 文本解释四字段、label 非业务事实与 issues 有界脱敏摘要，并要求结合同一完整输入整份重产；initial 继续不含 repair protocol，digest/secret 反泄漏断言保持通过。

## Rejected findings

### R01 — `compactor_input_projection.v2` 应改为 v1

- Source: DeepSeek 009
- Decision: rejected
- Evidence: accepted plan明确要求现有 compactor input projection 升为 `compactor_input_projection.v2`，因为该 projection version space早于 output v3且本 slice改变其 durable shape。把它改回 v1 会违背 frozen fresh-persistence contract，不是可读性修正。

### R02 — const schema mismatch 应新增 `invalid_const_value`

- Source: DeepSeek 012
- Decision: rejected
- Evidence: public `CompactValidationIssueCodeV3` 的 closed set 用 `INVALID_ENUM_VALUE` 表达字段不属于允许值；`schema` 是只有一个允许值的 closed set。新增 issue code会无业务收益地扩张 schema/repair surface；现有 path与message已能准确定位。

## Reviewer PASS items accepted as evidence

以下结论由 controller 对代码路径抽查后接受：fresh v3 无 active v2/drop-ledger compatibility；single structure descriptor 同源派生 template/schema/parser；strict duplicate/unknown/missing/type/enum/label checks；Context Governance 是唯一 accept owner；represented/omitted 与 policy audit从 candidate/policy 同源；artifact/EventLog/Memory/RunInput fail closed；successful response identity 在 parser/governance rejection 后保留；S2 custom model capability 显式为 `none`；测试包含主要 owner-level反例。

MiMo 的“prompt PASS”与 DeepSeek 的“prompt PASS”不覆盖 A05-A07：三项均来自 controller 对用户冻结 F08语义、AGENTS.md LLM-facing 北极星及实际 estimator代码的逐项对照，因此仍须修复并由两路 reviewer re-review。

## Fix gate acceptance

修复完成后必须：

1. 只改变上述 accepted findings及其直接 owner tests/hash publication；不改 v3 schema、caps值、Memory投影、provider选择或 repair budget。
2. 更新两个 prompt raw-byte hash、workspace manifest hash及其唯一 frozen test constant。
3. 运行 focused prompt/compaction/hash tests、全仓 pyright、changed-files Ruff、JSON/compileall/diff-check；若生产代码变化超出 prompt renderer/export声明，重新运行相应 branch coverage。
4. MiMo 与 DeepSeek 在 fresh session中分别执行独立 `$deepreview`/`/deepreview` re-review；两路均无未关闭 correctness/ownership finding后才可形成 S3 accepted commit。

## Fix gate result

- Changed production/config owners: `dayu/host/compaction.py`、`context_governance.py`、
  `llm_compaction.py` 与 `conversation_compaction_user.md`；未修改 v3 schema、cap 值、Memory
  projection、provider selection、repair budget 或 compatibility surface。
- Direct owner tests: `test_compaction_contract.py`、`test_llm_compaction.py`；A04 仅机械修正
  `fake_compaction.py`、`test_context_compact_events.py`、`test_compact_material.py` docstring。
- Publication: system prompt `822 bytes` / `97479acc0cc686cb9a72d18b310aff58cabba4d4b223c6773a12249b5ed333e5`；
  user prompt `3576 bytes` / `aabe5784479d855a99826bd214d7aed91bc0f20806b518daae08c77c659ec726`；
  frozen workspace manifest `e53909f2d9cb784e4ab8865dee47af495de6069208416055d951abbfefc35a21`。
- Validation: focused S3 owner/consumer suite `1071 passed, 1 skipped`；全仓 pyright `0 errors`；
  changed-file Ruff、compileall、JSON parse、raw hash/frozen hash、`git diff --check` 均 PASS。
- Branch coverage: `compaction.py 81%`、`context_governance.py 86%`、
  `llm_compaction.py 84%`。
- R01 / R02: 保持 `rejected-with-reason` 且代码未改；两份历史 review artifact 未覆盖。
- Residual risk: S4 real-provider cap-constrained behavior 与完整 Conversation Memory eval 仍按原
  approved plan deferred；当前 fix gate 无未分类 residual risk。
- Completion: implementation review fix `COMPLETED`；未 stage、commit、push。S3 acceptance
  仍需两路 fresh-session re-review 均关闭 correctness / ownership findings。

## Delayed MiMo workflow supplemental adjudication

MiMo 的 dynamic workflow 在首份 review artifact 与 A01-A07 fix 完成后才返回补充结果，并原地补充了同一 review artifact。总控因此在发起 re-review 前再次逐项裁决；不得把这些迟到 finding 静默忽略，也不得让 reviewer 共识替代 owner 证据。

### SA01 — `source_kind` 的八种业务语义未在当前 prompt 自足解释

- Source: MiMo delayed finding 01
- Severity: high
- Decision: accepted
- Evidence: output provenance 规则要求模型按 `previous_session_summary`、`previous_evidence_fact`、`previous_answer_anchor`、`previous_forward_intent`、`previous_reference_continuity`、`trace_material`、`evidence_material`、`answer_material` 判断可引用来源，但当前消息只给值名和部分 allowed-kind 组合，没有解释八种来源代表的业务材料。依赖英文标识猜测违反 AGENTS.md 对无状态模型的自足要求。
- Required fix: 在 user prompt 用一组精简、业务可读定义解释八种 kind；说明 kind 只是材料类型，不是事实证明。不得恢复 v2 drop ledger、repair protocol或长示例。

### SA02 — Host README 仍有 active v2 contract 描述

- Source: MiMo delayed finding 05
- Severity: medium
- Decision: accepted
- Evidence: `dayu/host/README.md` Conversation Memory 章节仍声明读取 `dayu.context_compaction.output.v2`、explicitly-dropped coverage、summary 缺失时保留旧 summary，并引用 `CompactAcceptedTruthV2`；均与 fresh v3、Host-derived omitted、required-null replacement直接矛盾。
- Required fix: 按当前 v3 truth 精确更新这两段；不写迁移兼容或旧库 reader。

### SA03 — durable reader 的九项 usage actual 反例不完整

- Source: MiMo delayed finding 06
- Severity: medium
- Decision: accepted
- Evidence: production validator exact 检查九项 actual，但 durable reader 参数化只覆盖五个 char actual，缺四个 item actual。测试应跟随 v3 owner contract。
- Required fix: 把四个 `*_item_actual` 加入相同 durable reader tamper matrix；不改 production行为。

### SA04 — accepted truth 未在自身边界校验 represented 的 boundary 顺序

- Source: MiMo delayed finding 08
- Severity: low
- Decision: accepted
- Evidence: `CompactAcceptedTruthV3.__post_init__` 已拥有 exact partition 与 omitted order invariant，却未对 represented 执行对称的 root-boundary order检查；该 invariant 仅在后续 durable payload reader重复验证。accepted truth 是写 artifact/event前的唯一真源，应在自身 owner boundary fail closed。
- Required fix: 添加 represented order检查与 owner反例；不得下游补偿或改变正常 canonical顺序。

### SA05 — committed semantic payload 的 typed field checks 不完整

- Source: MiMo delayed finding 11
- Severity: low
- Decision: accepted
- Evidence: `ContextCompactedSemanticPayload.__post_init__` 检查 candidate、omitted、audit，却没有先检查 `source_boundary` tuple/items 与 `represented_coverage` 类型；非法值可能在后续 attribute访问处以非契约异常失败。
- Required fix: 在该 typed durable read boundary添加明确 TypeError checks并补反例；继续复用现有 coverage binding validator。

### SR01 — system prompt 必须重复 repair protocol

- Source: MiMo delayed finding 02
- Decision: rejected
- Evidence: shared system prompt也用于 initial call。accepted contract明确 initial 不携带 repair protocol；repair-only user body现在已自足给出 same-input、feedback字段、whole-candidate replay与禁止 patch。把 repair规则复制到 system会增加 initial认知负担并违反初始/修复分离。

### SR02 — `CompactOutputCapsV3` 必须自有数值校验

- Source: MiMo delayed finding 03
- Decision: rejected
- Evidence: accepted plan明确冻结该 DTO“不拥有默认值、数值校验或配置读取”，数值唯一 owner 是已自校验的 `MemoryProjectionPolicy`，DTO只能由 Context Governance从同一 policy机械投影并在accept时逐字段绑定。给 DTO新增校验会复制owner并违背已确认设计。

### SR03 — `CompactPolicyUsageAuditV3` 必须复制全部 policy/digest/actual 校验

- Source: MiMo delayed finding 04
- Decision: rejected
- Evidence: trusted producer只有 Context Governance，从已验证 policy与candidate派生；不可信 durable JSON由 `compact_payload.py` strict parser校验 exact字段、非负整数、ref/digest，再由 candidate-binding validator检查九项actual与cap。把相同规则复制进纯 typed fact会建立第三套校验文本，没有发现可绕过accepted/artifact/read boundary的生产路径。

### SR04 — compactor input projection 应从 v2 改为 v3

- Source: MiMo delayed finding 07
- Decision: rejected
- Evidence: 与此前 R01相同。accepted plan把独立 projection version space从既有 v1升级为 `compactor_input_projection.v2`；它承载 compact input v3不代表 projection自身必须使用同一版本号。

### SR05 — structure error prefix 必须新增 exported mirror contract

- Source: MiMo delayed finding 10
- Decision: rejected
- Evidence: 当前八个 prefix均被 owner tests覆盖并安全映射；未知 prefix fail closed为 `INVALID_FIELD_TYPE` 且保留安全 path/message，不会接受 candidate。为低概率维护漂移新增 exported prefix registry仍会在 parser与projector间复制映射，或要求更大 typed-exception重构，超出本 slice最小正确方案。记录为非阻塞 maintainability risk，由未来新增 parser issue code的owner测试负责。

### Already closed

- MiMo delayed finding 09 与 DeepSeek 014相同，已由 A04机械修复。

Supplemental fix完成后必须再次同步 user prompt/hash/manifest，运行直接 owner tests与pyright/static checks；然后才能向两路 reviewer发送 fresh re-review任务。

### Supplemental fix status

- SA01：`已修复`。user prompt 已自足解释八种业务材料类型并声明 kind 不是事实证明；owner
  prompt test 锁定全部定义。
- SA02：`已修复`。Host README 已改为 active v3、represented / omitted exact partition、
  required-null summary 清旧语义与 `CompactAcceptedTruthV3`。
- SA03：`已修复`。durable reader tamper matrix 已从五个 char actual 扩展为全部九项 actual。
- SA04：`已修复`。accepted truth owner 已校验 represented root-boundary order；乱序反例在该
  owner 边界直接失败。
- SA05：`已修复`。committed semantic payload 已先校验 source boundary tuple/items 与
  represented coverage typed contract；三个非法类型反例均得到明确 TypeError。
- SR01-SR05：维持 `rejected-with-reason`，代码与契约未按这些建议修改。
- A01-A07：既有修复保持，direct/focused regression 未回退。
- Prompt/publication truth：user prompt `4301 bytes` /
  `59b50e13ea636c434fcabe26adf6d9ed22665dfcba03533ebcf5e9b524b87b76`；frozen workspace
  manifest `d95de68e69b0aacc712ec6bf468c8604a91460a17f3e2497f397182517a6a9f8`。
- Validation：direct owner tests `143 passed`；focused suite `1078 passed, 1 skipped`；coverage
  suite `706 passed, 1 skipped`，`compaction.py 81%`、`compact_payload.py 84%`；全仓 pyright
  `0 errors`；changed Ruff、compileall、JSON parse、publication/hash owner tests 与
  `git diff --check` 均 PASS。
- Residual risks：S4 real-provider cap-constrained behavior 与完整 Conversation Memory eval 继续
  由原 approved plan owner；SR05 的未来 parser prefix 维护风险保持既有分类。本 supplemental
  fix 无未分类 residual risk。
- Completion：supplemental implementation review fix `COMPLETED`；未 stage、commit、push。
  Current gate / next entry point：MiMo / DeepSeek fresh-session independent re-review。

## Fresh re-review checkpoint

- AgentMiMo：`docs/reviews/pr-190-f11-f12-s3-mimo-rereview-20260805.md`，PASS。逐项确认
  A01-A07、SA01-SA05 已在 owner boundary 关闭，R01/R02、SR01-SR05 的拒绝理由仍成立；
  current worktree 与 untracked S3 文件均纳入审查。复审过程中曾记录一个 prompt hash 偏差，
  经控制器直接以 raw bytes 复核为 reviewer 误记，reviewer 已修正 artifact；system prompt
  `822 bytes` / `97479acc0cc686cb9a72d18b310aff58cabba4d4b223c6773a12249b5ed333e5`，
  user prompt `4301 bytes` / `59b50e13ea636c434fcabe26adf6d9ed22665dfcba03533ebcf5e9b524b87b76`。
- AgentDS：`docs/reviews/pr-190-f11-f12-s3-ds-rereview-20260805.md`，PASS。逐项确认
  12 个 accepted findings 已关闭、7 个 rejected findings 维持原裁决，未发现新的 correctness、
  stability、ownership 或 compatibility finding；current worktree 与 untracked S3 文件均纳入审查。
- Controller decision：两路 re-review 均接受；不存在未裁决 finding。S3 达到 accepted slice commit
  条件。真实 provider 行为与公开 evidence 仍属于后续 S4，不由确定性 owner tests 代替。
