# PR 190 F11/F12 S3 Scope Correction

## Decision

- Gate：S3 implementation blocker resolution
- Decision date：2026-08-05
- User decision：**“测试跟着相应修改就好了。”**
- Result：**BLOCKER RESOLVED；S3 implementation may resume**

## Direct evidence

Fresh compact v3 删除全部 v2 production contract 且禁止兼容 alias/re-export/wrapper。以下五个
Host tests/fixtures 直接 import 或构造这些 v2 symbols，但最初 accepted plan 漏列：

- `tests/host/memory_snapshot_factories.py`
- `tests/host/test_accepted_result_projection.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_tool_trace_queries.py`

不迁移会使 full `tests/host` collection/执行失败；保留 v2 名称会违反 fresh schema。用户裁决
确认正确路径是让测试跟随 owner contract 迁移。

## Corrected boundary

上述五个文件加入 S3 allowed tests，仅允许：

- v2 typed import/construction → fresh v3 typed import/construction；
- 删除 diagnostics、explicit drop ledger/reason 的旧 fixture/assertion；
- 更新为 Host-derived represented/omitted/policy audit 与新 schema/version assertion；
- 保持原测试场景的业务意图，不新增兼容行为。

生产 allowed files、F12 replacement contract、oracle/scenario boundary、S3 atomic migration 与
全部 non-goals 不变。若后续扫描发现其它直接 v2 test consumer，同样允许做必要的 mechanical
test migration；任何 scope 外 production consumer 仍是 blocker，不能自行扩张。

## Subsequent accepted clarifications

用户随后明确：测试随 contract 迁移也覆盖直接消费 v2 contract 的测试/fixture 与取证
harness。因此以下两个 `utils/` consumer 纳入 S3 纯 mechanical fresh-v3 migration：

- `utils/smoke_host_public_conversation_memory_scenarios.py`
- `utils/smoke_host_public_r03_semantic_ownership.py`

该授权只允许切换 typed import、request caps 与 candidate exact shape，不提前改变 S4 真实取证
场景语义、evidence contract 或生产行为。扫描中发现的其它直接测试 consumer（包括
`tests/host/test_open_host_runtime.py` 与 `tests/host/test_public_open_host_options.py` 的旧
compactor prompt template 构造）同样只做 placeholder contract 的 mechanical migration。

用户还接受了三项 owner 纠正：

1. LLM-facing prompt 不注入完整 formal JSON Schema；`compact_structure` 单一 descriptor
   分别派生 concise rules / concrete template、provider-native schema 与 strict parser。
2. LLM-facing 文本只描述模型动作和业务语义，不要求模型理解 Host、omitted coverage 或
   policy audit；coverage/audit 精确术语只留在 durable/event/artifact 开发 contract。
3. canonical event/artifact 的 durable audit actual 必须与 accepted candidate 通过共享
   Memory 字符计量原语及单一 audit derivation helper exact 同源；represented/omitted 必须是
   root boundary 的无重叠、无遗漏精确分区，篡改后一律 fail closed。

## Cross-slice S2 completion authorization

最终 full suite 暴露 S2 已 accepted/pushed 实现中的 owner 漏洞：动态 Custom
OpenAI-compatible 模型记录未投影当前 schema 必填的 `structured_output_capability`。总控明确
裁决该问题不得作为 residual，授权在当前 S3 收口中修改真正 owner
`dayu/cli/init_catalog.py` 与 `tests/cli/test_init_catalog.py`。冻结语义为显式 `none`；禁止在
reader 增加默认值、兼容 fallback 或根据 provider 名称推断 capability。
