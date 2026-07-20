# WU-SEMANTIC-OWNERSHIP-01 / R02 plan entry controller adjudication

## 1. 身份与结论

- 本文只裁决既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 内部 remediation sub-WU `R02` 的 plan-entry allowlist drift；不是新 WU、feature 或 issue。
- 计划基线为 `02fcc5d8325fc7c3c2ef2f60a049910edb6ebfcb`，计划文件为 `docs/host/wu-semantic-ownership-01-r02-web-owner-policy-plan.md`。
- `R02-B01` 与 `R02-B02` 均接受并按下文精确扩展闭集。两个 plan-entry blocker 已关闭；计划可以改写为等待双路完整 plan review，但尚未 accepted、尚未 code-generation-ready，也不授权任何 implementation。

## 2. R02-B01 — accepted

精确新增 production allowlist 文件：

- `dayu/tools/web/web_search_providers.py`

直接证据：该文件当前直接 import `WebResourceBudget`，`search_public_web` 及 Tavily、Serper、DuckDuckGo response materialization signatures 都消费该类型；S1 删除七字段 budget owner 后它必然是直接迁移消费者。该文件还通过模块级 `requests.get/post` 执行 Web provider HTTP 请求；若 S2 只修改 fetch transport，统一 Web config 会对 search 与 fetch 产生不同的 proxy/peer-proof 事实。

授权边界：

- S1 只把 budget 依赖收窄到 `HttpResourceBudget`。
- S2 只让实际请求复用 Web HTTP transport owner 的 proxy/peer-proof/egress 决定与脱敏 warning。
- 不得改变 provider 选择、业务结果、credential 读取、query/domain 语义或 LLM-facing projection；不得在 search module 复制 DNS、proxy、peer rule。
- 不授权其它 production 文件。

拒绝替代方案：保留旧类名、flattened compatibility property、search 专用 transport rule 或让 search 绕过新 policy，都会违反唯一 owner 与无兼容代码约束。

## 3. R02-B02 — accepted

精确新增 test allowlist 文件：

- `tests/runtime/test_config_loader.py`

直接证据：`test_packaged_config_loads_expected_provider_metadata` 当前直接断言 packaged `allow_private_network_url is False`，而 accepted Topic 2 contract 要求默认 `true`。不修改该 owner-level packaged config test 会制造由 R02 自身引入的确定性失败。

授权边界：只更新该测试对 packaged Web 五个独立 bool 与三组 resource budget projection 的精确断言；不得迁移或重写其它 ConfigLoader 行为，不得加旧 schema 兼容或跳过。

## 4. 未授权事项

- 本裁决不接受计划中的任何其它范围扩展，也不裁决 ordinary diagnostic artifact 原子写、数值 gate sequencing 或具体 transport API 设计；这些必须由双路完整 plan review 挑战并由后续 controller adjudication 逐项裁决。
- 不实施 Issue 178 credential lifecycle、统一 tool authorization framework、R03 或其它 deferred Issue。
- 不授权产品、测试、README、control 修改；当前下一动作仅为 AgentCodex 把两项精确 allowlist 决定写回计划并移除 plan-entry blocked verdict，随后停止等待 controller 验证。
