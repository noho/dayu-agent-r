# F14 Goal Confirmation

## Gate

- Gate: goal confirmation
- Work unit: F14 accepted compact coverage frontier
- Status: confirmed
- Next entry point: plan
- Artifact path: `docs/reviews/f14-goal-confirmation-20260806-221301.md`

## Preflight

- Branch: `codex/interactive-oracle`
- HEAD: `ac68e77207c2809eabaf7ef51b6cdf65795889a7`
- Pull Request: 190，open draft，base `main`，head 与本地 HEAD 一致，merge state clean。
- Worktree: clean；无 merge、rebase、cherry-pick 或 revert 进行中。
- Remote: 仓库使用 `github`，不是 `origin`。
- Main fast-forward: `main` 与 `github/main` 均为 `113ea34d47b95812d79aa31705949bbb46bc6061`，ahead/behind 为 `0/0`。

## 第一性原理判断

F14 成立且严重性未被高估。accepted replacement 只能消费进入其 immutable source boundary 的材料；EventLog terminal 的写入位置只表达 ledger ordering，不能证明 terminal 之前的 raw material 已被覆盖。把两者混用会令未被 selection 选择的 protected recent raw turns 永久失去再次进入 compactor boundary 的机会，最终造成 durable correction 丢失。

## 直接证据

- Oracle observed-behavior report 的 SHA-256 为 `788ba7d7979bc2a3eca33307a2a9fccd24da6263031765cc4096a3b21463b72b`，与用户给定值一致。
- 旧 evidence DB 中 sequence 103–181 的四个 raw Run group 位于首次 accepted `CONTEXT_COMPACTED` sequence 187 之前。
- sequence 187 的 strict accepted `source_boundary_refs` 不含上述 protected groups；sequence 219、239、257 的 accepted boundary 只包含本轮 current input 与 previous compact event。
- `dayu.host.compact_material.select_compact_segment` 以完整 Host Run group 为原子，将 recent floor 标为 `protected_recent_raw_floor` 并排除出 selected pack。
- `dayu.host.compact_material._post_compact_delta_start_sequence` 在 latest accepted compact 存在时直接返回 `latest_compacted_event.event_sequence + 1`，没有读取 accepted source coverage。

## 语义 owner 与不变量

| 语义 | 唯一 owner | 不变量 |
| --- | --- | --- |
| raw material source boundary | Host `compact_material` EventLog-backed builder | 只从 canonical EventLog、payload descriptor、artifact 与 strict accepted compact truth 构造 |
| segment selection / recent floor | Host selector + `MemoryProjectionPolicy` | Host Run group 原子选择；protected group 本轮不进入 compact source boundary |
| represented / omitted coverage | Context Governance `CompactAcceptedTruthV4` | 两者只精确分区已经进入 accepted source boundary 的材料；omitted 仍是 consumed coverage |
| accepted consumption truth | strict `ContextCompactedSemanticPayload.current_input_ref` + `compacted_source_refs` | current input 未消费；其余 refs 是 represented/omitted partition 派生的实际 consumed refs |
| latest compact event | EventLog canonical terminal | 只拥有 accepted terminal identity、ordering 与 rolling projection provenance，不拥有 material frontier |
| Memory cursor | Conversation Memory projection | 只拥有 projection catch-up/checkpoint，不得作为 compact material coverage 真源 |

现有 accepted source coverage 真源足够复用。修复不得新增第二 cursor、第二 projector 或 durable schema 字段；frontier 应由 accepted coverage chain 与 canonical raw material 原子组机械派生。

## 生命周期裁决

- First compact accepted: selected source boundary 被消费；protected/unselected Run groups 与 current input 保持 raw、未消费。
- Later compact accepted: protected groups 离开 floor 后按 canonical order/atomic Run group 重新 eligible；只有进入 accepted boundary 后才推进 coverage。
- Attempt rejected / repair pending: 没有 accepted truth，不推进。
- Repair accepted / tier 1–3 accepted: 与普通 accepted 共用同一 truth，按实际 boundary 推进。
- Repair exhausted / failed / tier 4–5 fallback: 只写 failed terminal，不推进。
- Cancelled / stale / late result: terminal permit 阻止其形成新的 accepted terminal，不推进。
- Restart / reconnect: 从 strict EventLog accepted truth 重建相同 frontier；Memory、artifact、RunInput、Tool Trace 只投影同一 accepted replacement。

## 目标与成功信号

- terminal 之前但未被 accepted boundary 消费的 protected raw groups 不丢失。
- 离开 floor 后，完整 Run group exact-once、无 gap/duplicate、按 canonical order 进入 eligible material。
- rolling correction 的 FY2025 tool evidence 最终进入 durable accepted replacement，逐 fact 绑定非空 production evidence refs；FY2024 不再作为 current conclusion。
- 无工具证据的 21.7% 不形成 EvidenceFact，也不借用旧 provenance。
- correction 推出 recent window 后，reconnect 仍可由正式 Memory/accepted replacement证明正确。

## Scope boundary / Non-goals

- 修改边界：Host compact material frontier owner、对应 owner/integration tests、必要 Host design truth 与 README decision。
- 不修改 prompt、provider/model、Engine compaction contract、UI、Service、CLI renderer、Tool Trace renderer、财报工具、accepted Oracle 或 scenario predicate。
- 不增大 recent floor/cap，不添加 filler 特例、loose parsing、compatibility shim、双 cursor 或从 summary/日志/字符串反推 coverage。
- 当前证据不要求 schema/public contract 变化；若实现调查推翻这一点，必须停止并重新裁决。

## 过度设计判断

最小正确路径是让现有 Host material builder消费现有 strict accepted coverage truth，并用已有 atomic Run group语义派生 frontier。无需新表、新 schema、新全局服务、新 cursor 或跨层 contract。

## Open Questions

无 blocking open question。

## Residual Risks

- 真实 provider 输出非确定性：通过 owner tests证明 deterministic frontier，再以 fresh production CLI observation记录实际模型行为；formal acceptance 仍由用户/Oracle 总控裁决。
- 旧 evidence bundle含本机 raw SQLite；公开 post-fix bundle必须排除或脱敏 raw DB并运行 exact-value secret scan。
