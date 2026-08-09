# Interactive Conversation Memory closure F08–F10：Plan review 总控裁决

## Gate identity

- Work unit：Interactive Conversation Memory closure F08–F10。
- Reviewed plan：`docs/reviews/wu-interactive-memory-closure-f08-f10-plan-codex.md`。
- Review lanes：AgentMiMo、AgentDS 两路独立 plan review 与 re-review。
- Base ref：`github/main`（仓库无 `origin`，等价于用户指定的 `origin/main`）。
- Conclusion：`accepted-plan-pass`。

## 逐项裁决

| 来源 | Finding | 裁决 | 关闭证据 |
|---|---|---|---|
| DS F1 / MiMo F1 | frozen baseline checkpoint 缺失 | 接受 | 修订 plan §1/§10 要求单一 accepted-plan commit 精确包含三份 baseline 与全部 plan/review artifacts；implementation 后三份 digest 不变。 |
| DS F2 | F08 prompt 自足性不足 | 接受，但拒绝字符/词表阈值 | 修订 plan 用当前目标、已建立结论或进展、仍影响后续的约束/下一步定义完整业务陈述；cap 内无法形成完整陈述则 `null`，禁止占位符、孤立字符、孤立标点、无上下文缩写和截断片段。 |
| MiMo F4 | 用 negative test 固化 Host 接受句点 | 拒绝 | 这会把不合规 LLM 输出固化为 owner contract。Host 继续只校验确定性 shape/cap/coverage，prompt owner 承担选择规则；正式 provider 行为留给后续 Agent-in-the-loop scenario。 |
| Controller / DS F6 | F08 publication consumer 与 README 证据遗漏 | 接受 | F08 allowed files 纳入 workspace publication manifest 与 init smoke raw manifest digest consumer；已按 `dayu/config/README.md` 职责判断不更新正文。 |
| MiMo F2 | F09 hot payload 描述有歧义 | 接受 | 修订 plan 明确 hot JSON inline manifest body 并携带 ref/digest；EventLog row descriptor 写同源 ref/digest，projector/resolver 不改。 |
| MiMo F5 | F09/F10 共享文件未说明顺序 | 接受顺序问题，拒绝 rebase 建议 | 固定先 F09 checkpoint、后 F10；禁止 rebase，符合用户 Git 约束。 |
| DS F3 | oversized group fallback 未闭环 | 接受 finding，拒绝新增 signal | 完整 group 全部标记 `budget_limit`，canonical frozen source snapshot 不删 raw blocks；既有 tier 4/5 raw-window owner消费完整 snapshot或 fail closed。 |
| DS F4 / MiMo F3 | 新 digest 与历史 durable fact 边界不清 | 接受 | 按全新当前 schema处理，不做旧库兼容；历史 EventLog digest 保持产生时 immutable，新代码只绑定当前冻结 request/source boundary。 |
| DS F5 | group selector 两阶段结构欠规格 | 接受 | 修订 plan 明确稳定归并/collective exclusion 与 unit-level prefix budget 两阶段，item cap 仍按真实 block 数计。 |
| DS F7 | typed surface 不明确 | 接受 | 使用最小 `TurnGroupMembership` 与 root/transient scope，作为 `CompactSegmentSelection` 同一 canonical contract 的字段，不新增 public schema、facade 或 God helper。 |
| DS F8 | feedback mismatch defensive 路径不足 | 接受 | dispatcher 正常清空跨-boundary feedback；operation 防御校验返回 non-repairable failed result，provider 不调用、异常不逃逸、继续单一 terminal/fallback。 |
| Controller | 验证命令与明确不跑场景不足 | 接受 | 修订 plan 包含 focused/full pytest、coverage、全仓 pyright、Ruff、compileall、JSON validation、diff check；五条正式 CLI scenarios 明确归属后续 Oracle 总控。 |

## 两路 re-review 独立结论

- AgentMiMo：`PASS`，artifact 为 `docs/reviews/wu-interactive-memory-closure-f08-f10-plan-rereview-mimo.md`。
- AgentDS：`PASS`，artifact 为 `docs/reviews/wu-interactive-memory-closure-f08-f10-plan-rereview-ds.md`。
- 总控没有以两路一致替代证据；上述每项均按 owner、直接代码事实、反例和用户冻结语义单独裁决。

## Accepted baseline digests

- `docs/cli_ci_oracles.json`：`da04923193a04c0e33eca9c60e0d8eb919b74963b2c2f4170954be2f07261201`
- `docs/cli_ci_scenarios.json`：`7c991d14ebc79f9f8e8c66d9eb94c10156c5a36eecd3bb11df24ed18cbca2093`
- `docs/reviews/wu-interactive-memory-closure-f08-f10.md`：`95a09543fc7f1a2a09f99dbe2c2c014e71ac22f2c386dc5364f6a1a2d14b1b08`

## Gate decision

`accepted-plan-pass`。无 blocking open question。下一 gate 是按 F08、F09、F10 顺序执行 implementation slice，并在每个 slice 完成两路独立 code review、fix、re-review 和 accepted commit。
