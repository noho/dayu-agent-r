# UF-FIX11 plan review controller adjudication

## Gate 元数据

- work unit：`UF-FIX11 company-metadata-ignored-change-warning`
- gate：`plan review -> fix`
- reviewed plan：`docs/gateflow/uf-fix11-company-meta-warning-plan-20260817.md`
- review artifacts：
  - `docs/reviews/plan-review-20260817-090453.md`（AgentMiMo）
  - `docs/reviews/plan-review-20260817-091441.md`（AgentDS）
- 两路结论：`pass-with-risks`
- controller decision：`fix-required-before-re-review`
- current gate：`fix`
- next entry point：plan fix 完成后进入 `re-review`

## 第一性原理裁决

Plan 的方向成立：ignored-change 事实必须由 company-meta commit owner 基于最终 published
CompanyMeta 产生，合法 alias 在 source skip 时必须通过同一 batch/identity guard 真正持久化，
而不是丢弃后仅 warning。两路没有发现需要改写架构方向或扩大到 Host/Engine/material 的 blocker。

需要修正的是可实施性和验收规格：完整 fake 收敛、SKIP metadata-only wiring、durable summary、
唯一 warning 消费点、并发测试与 degraded-tree fail-closed 取舍必须在 implementation 前写死。

## Findings 裁决

### A1 — name-only commit 刷新 updated_at / 属不必要 mutation

- 来源：MiMo 001。
- decision：`rejected-with-reason`。
- 理由：review 的反例把“名称不等价”误写成“NFKC+casefold 等价”，而 plan 已规定等价名称保持
  `keep + rollback`。代码 `_company_meta_from_published` 在 identity 不变时保留原 `updated_at`，DS
  也已直接核验 final meta 逐字段相等。name-only 不等价请求进入 commit owner，是为了满足用户明确要求的
  publication-lock final truth；不能改成 commit 前 snapshot 比较，否则重新制造早期快照真源。
- plan fix：只需补充验证 final meta bytes/字段不变、source tree 不变，并把 full-tree swap/锁成本保留为
  已接受权衡；不得采用 MiMo 建议的 commit 前 warning 推断。

### A2 — SKIP+preserve 与 UF-FIX10 no-mutation 冲突

- 来源：MiMo 002。
- decision：`rejected-with-reason`（需澄清措辞）。
- 理由：用户已明确要求 source 已存在并 skip 时合法新 alias 仍必须持久化。UF-FIX10 的 skip
  no-mutation contract 针对 filing/source assets、version、meta、manifest；本 work unit 明确授权
  company identity metadata 的原子 mutation。重新询问用户没有必要。
- plan fix：明确 source publication 继续零 mutation，而 accepted company identity update 是本 work unit
  的有意、唯一例外；补 source stage 为零、source tree/content hash 不变断言。

### A3 — commit_batch 返回类型 / fake 收敛验证盲区

- 来源：MiMo 003、DS 1。
- decision：`accepted`。
- required fix：列出仓库中全部 production/test `def commit_batch` 定义；说明 `-> None` 对 union 返回
  的协变使 pyright 不能单独强制 fake 收敛；在静态检查加入 `rg -n "def commit_batch" dayu tests`，
  并逐项断言需要 outcome 的 fake 成功路径返回 exact outcome。Slice allowed files 必须覆盖
  `tests/fins/test_fins_ingestion_runtime.py` 等全部 7 个 fake 文件。

### A4 — warnings 缺失 / null 的 schema 行为

- 来源：MiMo 004；DS 指定点 3。
- decision：`accepted`（clarification）。
- required fix：明确 `warnings` 缺失只因同一 fresh parser 同时服务 out-of-scope material payload，
  是结构性 optional，而非旧 schema compatibility；缺失 -> empty 仅适用于 material，filing completed payload
  必须显式输出 `warnings: []`。`null`、错误类型、未知/重复/超限对象全部 fail closed，并补精确 tests。

### A5 — warning 文案未直说“提交未生效 / 现有被保留”

- 来源：MiMo 005。
- decision：`accepted`。
- required fix：规范固定文案改为：
  `本次提交的公司名称未生效；已保留现有公司名称。请核对上传目标公司是否正确。`
  保持不回显 raw names、无路径、无内部术语、有界；CLI 与 LLM/tool 必须逐字投影同一 message。

### A6 — UploadOperationResult semantic drift / 双载体消费歧义

- 来源：MiMo 006、DS 5。
- decision：`accepted`（保持最小内部载体，但收紧唯一消费点）。
- required fix：允许 `UploadOperationResult` 作为 `commit_prepared_upload_batch` 的内部 outcome 载体，
  因为另建 wrapper 会扩散 material caller；但 SEC/CN 不得直接读取其中的 company outcome。shared
  filing publication 必须唯一投影 `FilingUploadPublicationOutcome.warnings`，SEC/CN 只消费该字段；
  early cancelled/delete 分支显式 `warnings=()`。补 outcome 投影一致性与早退/delete 无 warning tests。

### A7 — SKIP+preserve 继承 whole-tree COMPLETE 校验

- 来源：DS 2。
- decision：`accepted`（fail-closed tradeoff）。
- required fix：明确 metadata-only commit 仍服从 storage `_validate_complete_source_tree`；同 ticker
  存在无关 `REPAIR_REQUIRED` source 时，操作 typed failure、无 warning、无 partial mutation。这是保持
  storage 完整性 owner 的 fail-closed 取舍，不新增 bypass。加入 owner/workflow test。

### A8 — SKIP 分支可能误复用 filing publish helper

- 来源：DS 3。
- decision：`accepted`。
- required fix：Slice 2 写死 SKIP+preserve 直接调用
  `stage_upload_company_meta_decision -> batching_repository.commit_batch`，再把 commit outcome 与
  `build_prepared_filing_skip_result` 组合；禁止调用 `publish_prepared_upload` 或
  `commit_prepared_upload_batch`，禁止 stage filing assets。测试断言 source stage token 为空、source
  tree exact unchanged。

### A9 — durable job result_summary 未规格化 warnings

- 来源：DS 4。
- decision：`accepted`。
- required fix：`FinsUploadResultSummary.to_json_summary()` 必须写 `warnings`（空为 `[]`）；durable job
  save/re-read 与 direct/CLI/tool 使用同一 typed tuple。补 durable record exact warning tests，禁止仅在
  CLI 投影。

### A10 — 并发 final-truth 测试未落名

- 来源：DS 6。
- decision：`accepted`。
- required fix：Slice 2 明确命名 barrier/event-controlled tests：同 ticker publish 与后续
  skip+alias/name 请求、跨 ticker alias collision，分别断言 warning/outcome 与 final durable meta 一致，
  或 typed failure 且无 warning；不得用 sleep/polling。

## Residual risks

- name-only metadata batch 的锁/physical swap 成本：`assigned to later work unit`，除非本轮测试发现实际
  correctness/stability 回归；当前以 final truth 正确性优先。
- degraded unrelated source 使 metadata-only commit fail closed：`accepted current tradeoff`，本轮必须
  测试并记录，不允许绕过 storage completeness owner。
- material company-name warning：`assigned to later work unit`，本轮不改。
- 真实 CLI evidence、oracle/scenario/frozen evidence：用户明确排除，`assigned to later work unit`。

没有未分类 residual risk，没有需要用户再次决策的 blocker。

## Fix validation

- AgentCodex 修改 plan 与 plan-fix artifact，不改生产/测试。
- 两路 reviewer 对修订后的同一 plan 做 re-review。
- 全部 accepted findings 必须标记 `已修复`；驳回项不得被误实施。
