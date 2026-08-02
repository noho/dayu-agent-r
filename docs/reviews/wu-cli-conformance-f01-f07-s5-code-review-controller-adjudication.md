# WU-CLI-CONFORMANCE-F01-F07 S5/F05 Code Review 总控裁决

## Gate 元数据

- Work unit：`WU-CLI-CONFORMANCE-F01-F07`
- PR：`190`
- Slice：`S5 / F05`
- Entry HEAD：`c556df2bc6d175f34b7a80c3a83cf1b079e61cc7`
- Review artifacts：
  - `docs/reviews/wu-cli-conformance-f01-f07-s5-code-review-mimo.md`
  - `docs/reviews/wu-cli-conformance-f01-f07-s5-code-review-ds.md`
- 裁决：`PASS — 可进入 accepted slice commit`

## 独立证据核验

总控逐项检查 manifest 与四个测试 diff，并沿真实
`interactive manifest -> discovery -> scene prepare -> Service -> Host -> Engine request`
链路核对语义 owner。唯一 production change 是从
`dayu/config/prompts/manifests/interactive.json` 的 `tool_tags_any` 删除
`fins-preprocess`；其它 tag、值和顺序未变。最终 `AgentRunRequest.tool_schemas`
不含 `start_fins_preprocess`，仍含 `start_fins_download`、`list_documents`、
`read_section`。Fins preprocess provider/实现和 WeChat scene 未修改。

两路 review 均复跑 focused tests 与 pyright 并得到通过结果；两路都没有把
“一致”本身当作通过理由，而是分别给出了代码链、反例和测试边界证据。

## Findings 裁决

### MiMo

MiMo 报告“未发现实质性问题”，无 finding 需要 fix。

### DeepSeek

DeepSeek 报告“未发现实质性问题”，无 finding 需要 fix。其三个 residual risk
分别裁决如下：

| residual | 裁决 | 理由 / owner |
|---|---|---|
| discovery 后 preprocess awaiting adapter 仍可装配 | `accepted-as-non-blocking` | F05 只冻结 interactive 向 Host/Engine 提供的 effective tool set；保留独立 preprocess provider 是明确要求。当前 adapter 不进入该 Run 的 LLM-facing schema，也不创建工具调用。对 discovery/poller 做额外按 scene 裁剪会扩张 Service owner 与本 slice scope。 |
| 测试常量 `_DEFAULT_FINS_LONG_TRANSACTION_TOOL_NAMES` 名称偏泛 | `rejected-as-finding` | 该常量是测试内局部集合，当前只用于 WeChat 断言且值正确，不产生 production 语义漂移；为了命名重构测试不构成 F05 correctness fix。 |
| 下载后读取未预处理文档的产品行为 | `tracked-by-S8-real-evidence` | 这是 frozen download/list/read 跨轮真实场景的验证事项，不属于 tool-registration owner；S8 必须以真实 CLI evidence 记录，不在 S5 改写 download/process 行为。 |

## 不变量与 gate 结论

- 未在 CLI、Service、Host 或 Engine 增加 `start_fins_preprocess` 名称黑名单。
- 未删除或修改 preprocess provider/实现。
- WeChat 仍由自身 manifest 选择 preprocess。
- owner-level integration test 抵达最终 Engine request，不是 mock name set 自证。
- frozen oracle/scenario 与 design truth 未修改。
- 无 blocker、无 accepted code finding、无需 fix/re-review loop。

S5/F05 code review gate 通过。下一合法动作是精确 stage 本 slice 的 manifest、四个
测试和三份 durable artifacts，提交 accepted slice commit；随后按固定顺序进入 S6。
