# PR 190 F11/F12 S0 Design Review 裁决记录

## Gate metadata

- Gate：`fix`，slice `S0 — design truth`
- Work unit：PR 190 F11 public compactor response identity 与 F12 fresh compact v3
- Base：`427b1c858d5e926f309935fa206963deb1618436`
- Branch：`codex/interactive-oracle`
- Implementation artifact：`docs/gateflow/pr-190-f11-f12-s0-design-implementation-20260805.md`
- MiMo review：`docs/reviews/pr-190-f11-f12-s0-design-review-mimo-20260805.md`
- DS review：`docs/reviews/pr-190-f11-f12-s0-design-review-ds-20260805.md`
- Controller verdict：两路全部 semantic / owner 检查 PASS；DS 唯一微小计数 finding 成立并已修复；semantic still-open 为 0
- Next entry point：S0 re-review

## Scope and preservation

本 fix gate 只做两项变更：

1. 把 implementation artifact 中过期的 Markdown fence marker 计数由 Host 180 / Engine 6 修正为实际的 Host 182 / Engine 8。
2. 新增本裁决记录，固定两路 review 结果、finding 处置和 re-review 入口。

`docs/host/design.md`、`docs/engine/design.md` 与两份 review artifact 在本 gate 中均为只读；不修改生产代码、tests、registry、README、finding/review artifact，不 stage、commit 或 push。

## MiMo review adjudication

MiMo review 没有提出 finding；以下逐项裁决均为 PASS，无需 design fix：

| # | Review check | Controller adjudication |
|---:|---|---|
| 1 | F11 unique owner | PASS；Host Tool Trace durable resolver 是唯一 public response identity owner |
| 2 | Canonical response identity exact binding | PASS；terminal、manifest、operation、attempt 与 Engine response identity exact binding 已冻结 |
| 3 | Pagination fail closed | PASS；固定正数 page size、完整 keyset exhaustion、无总页数 cap 与异常 cursor fail closed 已冻结 |
| 4 | 安全白名单 | PASS；只投影批准字段，不泄露 header、credential、authorization、raw response 或 prompt/body |
| 5 | Fresh analysis schema v2 | PASS；fresh v2 替换 v1，不保留双读或兼容 parser |
| 6 | Fresh v3 schema — input | PASS；input v3 exact fields 与真实 caps boundary 已冻结 |
| 7 | Fresh v3 schema — output | PASS；output v3 exact root、required nullable summary 与 strict unknown-key rejection 已冻结 |
| 8 | Typed facts — 五类子项 | PASS；五类业务语义均由明确 typed owner 定义 |
| 9 | Host-derived coverage/omission/caps audit | PASS；represented / omitted exact complement 与 policy usage audit 归 Host |
| 10 | Repair/digest LLM boundary | PASS；initial 与 repair 分离，Host internal digest 不进入 LLM-facing 文本 |
| 11 | Persistence — fresh cut | PASS；input projection v2、artifact schema 4 与旧 replay 不兼容边界已冻结 |
| 12 | Single structure owner | PASS；template、schema 与 parser 由同一 structure truth 派生 |
| 13 | Caps DTO — immutable projection | PASS；MemoryProjectionPolicy 继续唯一拥有 cap 数值、default、校验与 digest |
| 14 | Engine generic structured output / no inference / no downgrade | PASS；Engine 只处理 provider-neutral typed request |
| 15 | Capability matrix fail fast | PASS；none / json_object / json_schema matrix 与 outbound 前 fail fast 已冻结 |
| 16 | Host compactor 不变 Engine special case | PASS；Engine 不知道 compact schema、coverage、repair、artifact 或 Host budget |
| 17 | 旧 v2 normative 真删除 | PASS；冲突 v2 contract 已替换而非并列追加 |
| 18 | 无兼容性设计 | PASS；无 alias、双读 parser、re-export 或 compatibility wrapper |
| 19 | 无过度设计 | PASS；没有新增第二存储、推断器、classifier 或 provider router |
| 20 | 无 semantic owner drift | PASS；artifact、event、Memory、RunInput 与 Tool Trace 同源消费 accepted truth |
| 21 | AsyncRunner.call breaking change 声明 | PASS；required、无 default 的 keyword-only 参数及同 commit 迁移要求明确 |
| 22 | OpenAI-compatible payload projection | PASS；typed request 到 exact `response_format` 的投影明确 |
| 23 | Capability evidence 归属 | PASS；capability 来源与真实 provider observation 责任边界明确 |

MiMo 路径的 semantic still-open：0；owner still-open：0。

## DS review adjudication

DS review 的 semantic / owner 检查逐项均为 PASS；`S0-03` 的合同级 parity 结论仍为 PASS，但其中记录的具体计数过期，按下一节单独接受并修复：

| ID | Review check | Controller adjudication |
|---|---|---|
| F11-01 | response identity owner 唯一归属于 Host Tool Trace durable resolver | PASS |
| F11-02 | canonical terminal exact binding 与 pagination fail closed | PASS |
| F11-03 | security whitelist 显式白名单 | PASS |
| F11-04 | Tool Trace analysis fresh v2 与旧 v1 删除 | PASS |
| F12-01 | CompactInputV3 完整定义 | PASS |
| F12-02 | CompactCandidateV3 五个 typed children 与全部 required root keys | PASS |
| F12-03 | CompactOutputCapsV3 是 immutable DTO，MemoryProjectionPolicy 唯一拥有数值 | PASS |
| F12-04 | Host-derived represented / omitted exact complement 与 policy usage audit | PASS |
| F12-05 | 模型不返回 diagnostics、explicit drop ledger 或 drop reason | PASS |
| F12-06 | 单一 structure owner | PASS |
| F12-07 | fresh persistence：`compactor_input_projection.v2` 与 artifact schema 4 | PASS |
| F12-08 | 旧 compact artifact/session replay 不支持且不扩大为整个 DB 不可打开 | PASS |
| F12-09 | digest 不进入 initial 或 repair 的 LLM-facing 文本 | PASS |
| F12-10 | initial 无 repair protocol，repair 自足整体重产 | PASS |
| F12-11 | rejected candidate 不写 artifact、Memory 或 `CONTEXT_COMPACTED` | PASS |
| ENG-01 | StructuredOutputRequest 是显式一等字段 | PASS |
| ENG-02 | StructuredOutputCapability 三值与 fail-fast matrix | PASS |
| ENG-03 | Engine 不推断、不降级、不按 provider 名称 dispatch | PASS |
| ENG-04 | AsyncRunner.call required keyword-only structured_output | PASS |
| ENG-05 | Engine 不知道 compact schema，不提供 compactor special case | PASS |
| V2-01 | 旧 v2 compact type 名全部删除 | PASS |
| V2-02 | §24.3 从 v2 整节替换为 v3，而非追加并列真源 | PASS |
| V2-03 | 无兼容 alias、re-export 或 wrapper 残留 | PASS |
| OD-01 | F11 不新增第二 EventLog、缓存或推断器 | PASS |
| OD-02 | F12 不增加 semantic classifier，caps DTO 不定义第二 owner | PASS |
| OD-03 | Engine 不增加 provider probe、fallback router 或 provider-name 分支 | PASS |
| OD-04 | §24 / §25 v3 contract 无 owner 冲突 | PASS |
| OD-05 | S0 不新增无类型签名或反射式 fallback | PASS（S0 纯 design slice） |
| S0-01 | implementation artifact 声称的 design 修改与实际内容一致 | PASS |
| S0-02 | v2 normative scan 声称 0 命中可复验 | PASS |
| S0-03 | Markdown fence parity 可复验 | PASS；具体计数 finding accepted / fixed |

DS 路径的 semantic still-open：0；owner still-open：0。

## Count finding disposition

- Finding：implementation artifact 写为 Host 180 / Engine 6；最终新增 exact type code fences 后没有刷新该数值。
- Direct evidence：按行首三个反引号 marker 的实际计数为 Host 182、Engine 8；两者均为偶数，fence parity 结论不变。
- Root cause：实施记录先写入计数，随后 design 增加最后一对 fence，记录未同步刷新；这是 artifact 事实值滞后，不是 design semantic 或 owner contract 缺陷。
- Adjudication：`accepted`。
- Fix：只把 implementation artifact 的计数更新为 Host 182 / Engine 8；不修改 design 或 review artifact。
- Status：`fixed`。

## Gate result

- Semantic still-open：0。
- Owner still-open：0。
- Non-semantic still-open：0；唯一计数 finding 已修复。
- Design delta required by review：无。
- Re-review scope：确认 implementation artifact 计数为 Host 182 / Engine 8、两份 design 与两份 review 未被本 fix gate 修改，并复验 diff/status。
- Next gate：S0 re-review；本 artifact 不自行宣告 S0 accepted，也不进入 S1。
