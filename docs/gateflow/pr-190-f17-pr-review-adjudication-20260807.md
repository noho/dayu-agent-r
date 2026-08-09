# PR 190 F17 PR Review Adjudication

## Review inputs

- AgentMiMo：`docs/reviews/pr-190-review-20260807-152226.md`
- AgentDS：`docs/reviews/pr-190-review-20260807-152555.md`
- PR facts：PR 190 为 `OPEN`、`DRAFT`、`CLEAN`，远端 head `dcc08399`，没有 review
  requests 或 reviews；`gh pr checks 190` 报告 no checks。

## AgentMiMo findings

### M1：PR 无远端 CI checks

- 裁决：`deferred-with-owner`
- 理由：事实成立，是 CI coverage gap，不是产品 code defect。F17 已在 clean committed target
  运行 71/71 owner suite、full pyright、Ruff、compileall、JSON/digest/count 与 committed-range
  diff check；但这些本地证据不能伪装成 GitHub CI PASS。
- Owner：repository CI / merge policy 后续裁决；F17 不擅自新增 workflow。

### M2：CONTEXT_COMPACTION_FAILED 没有未来 bounded-storage fallback

- 裁决：`rejected-with-reason`
- 理由：review 明确承认当前 failed payload 是固定小型封闭结构且当前行为正确；finding 只假设未来
  schema 可能扩张。未来 schema 变更应由其 owner 同步设计 storage，不能用未发生的变化制造当前 defect。

### M3：compact_structure.py 没有同名专属测试文件

- 裁决：`rejected-with-reason`
- 理由：review 已确认 5 个 public functions 由 `test_compaction_contract.py` 与
  `test_llm_compaction.py` 覆盖。仓库要求 owner contract coverage，不要求生产模块与测试文件同名；
  这是文件组织偏好，不是 correctness/stability/maintainability defect。

## AgentDS findings

### D1：runtime 与 Engine structured-output capability 双 enum

- 裁决：`rejected-with-reason`
- 理由：`dayu.runtime` 按架构硬约束不得 import `dayu.engine`；runtime 配置 schema 与 Engine execution
  contract 属于不同层，Service 机械投影是正确边界。更关键的是 reviewer 建议增加的 invariant 已存在：
  `tests/service/test_host_assembly.py::test_structured_output_capability_enums_map_mechanically_by_value`
  精确断言两侧完整 value set 相等并逐项可构造。因此“无 invariant test”的直接证据不成立。

### D2：stream + structured_output 应互斥

- 裁决：`rejected-with-reason`
- 理由：当前 Engine design 的合法矩阵只由 request variant 与 Runner capability 决定，没有 stream
  互斥 contract；review 未提供 provider protocol 的直接失败证据，并承认当前无触发路径。不能为臆测的
  外部限制新增 Engine 拒绝语义。

### D3：F17 pre-state 有四个 drift，旧 pin 为 a486...

- 裁决：`accepted`，仅 evidence correction
- 理由：review 把完整 PR 的 `main..HEAD` 历史差异误归给 F17 work-unit pre-state。直接 git 证据：
  - `git show e1217811:docs/cli_init_workspace_manifest_v1.json | shasum -a 256` 为
    `d95de68e69b0aacc712ec6bf468c8604a91460a17f3e2497f397182517a6a9f8`；
  - `git show e1217811:tests/...` 的 `FROZEN_MANIFEST_SHA256` 同为 `d95de68e...`；
  - `git diff e1217811..305c1012` 对两个 consumer 各为 1 insertion / 1 deletion，只更新
    `conversation_compaction_user.md` entry 与 test pin；
  - F17 preflight production strict report 只有该 singleton mismatch。
- Fix owner：AgentCodex 只更正 `pr-190-review-20260807-152555.md` 的 branch typo、finding D3 与
  F17 conflict summary；不改产品或其它独立 finding。

### D4：session scope 统一无兼容路径

- 裁决：`rejected-with-reason`
- 理由：根 README 已明确公开：共享 namespace 是 `cli.agent.<label>`，旧 `cli.prompt.*` /
  `cli.interactive.*` slot 不会被自动读取或迁移；tests 也将旧 scope 明确分类为 `OTHER`。这是 accepted
  fresh contract，不是遗漏。新增 fallback/migration 还会违反当前仓库禁止兼容层的约束。

## Gate decision

没有 accepted product/code finding。D3 evidence correction 完成并经 MiMo/DS 双路 re-review 前，PR review
gate 暂不接受。CI no-checks 保留为明确 gap；三条 formal replacement scenarios 保持 `unadjudicated`，
不在 F17 内生成 readiness proof 或替用户裁决。
