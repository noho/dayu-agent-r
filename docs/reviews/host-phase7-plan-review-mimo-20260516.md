# Host Phase 7 Plan Review - MiMo - 2026-05-16

## Review Target

- **Plan**: `docs/host/phase7-tool-awaiting-resolve-wait-plan.md`
- **Design truth**: `docs/host/design.md` §20, §21, §22
- **Control truth**: `docs/host/implementation-control.md` Phase 7 and Current Status
- **Review artifacts**: `docs/reviews/host-phase7-design-re-review-controller-adjudication-20260516.md`、`docs/reviews/host-phase7-design-fix-re-review-controller-adjudication-20260516.md`

## Assumptions Tested

1. Plan 是否覆盖 design fix re-review controller adjudication 的所有 plan gate requirement。
2. 公共契约是否足够具体，implementation agent 无需重新设计。
3. Schema / status machine / CAS helpers 是否可实现。
4. Slice 边界是否合理、file ownership 是否清晰。
5. Host / Engine 边界是否被正确维护。
6. 并发 / 幂等 / 状态机行为是否可测试。
7. 是否存在过度设计、弱类型、兼容性路径。

## Findings

### 1-未修复-高-`resolve_wait` pipeline 幂等检查与 late result diagnostic 写入顺序未指定

- **位置**: §3.9 `resolve_wait` Pipeline，步骤 3-7
- **问题类型**: 状态机漏洞 / 不可直接实施
- **当前写法**: Plan 步骤 3 先读 idempotency record，步骤 4 判断 same key + same digest 是否存在，步骤 7 判断 wait record status 为 `cancelled` / `lost` 时追加 `WAIT_LATE_RESULT_REJECTED` diagnostic。
- **反例/失败场景**:
  - 场景 A：wait record 已 `cancelled`。Poll adapter 带回与之前已完成 resolution 相同 `(wait_id, idempotency_key)` + 相同 digest 的结果调用 `resolve_wait`。按步骤 4，idempotency match 存在，直接返回既有 RunSnapshot，步骤 7 永远不执行。`WAIT_LATE_RESULT_REJECTED` diagnostic 不会被写入。
  - 场景 B：wait record 已 `cancelled`。Poll adapter 带回相同 `(wait_id, idempotency_key)` 但不同 digest 的结果。按步骤 4，raise `IDEMPOTENCY_CONFLICT`，步骤 7 不执行。同样无 diagnostic。
  - 场景 C：wait record 已 `cancelled`。Poll adapter 带回全新 `idempotency_key`。步骤 4 无 match，步骤 7 读到 `cancelled` 状态，写入 `WAIT_LATE_RESULT_REJECTED` 并 raise `INVALID_STATE`。这是唯一能写出 diagnostic 的路径。
- **为什么有问题**: Plan §3.10 明确要求 `cancelled` / `lost` wait record 的迟到结果"必须至少追加 `WAIT_LATE_RESULT_REJECTED` diagnostic EventLog event"。§3.12 也要求 poll adapter `resolve_wait` 使用 deterministic idempotency key。但 pipeline 顺序使得大多数 late result 被 idempotency check 短路，diagnostic 无法写出。Implementation agent 不得不自行决定：(a) 是否在 idempotency check 之前检查 wait record status；(b) 是否为 late rejection 使用独立 idempotency scope；(c) 是否接受大部分 late result 不写 diagnostic。这些都是架构决策，不应留给 implementation agent。
- **直接证据**: §3.9 步骤 3-7 顺序；§3.10 "必须至少追加 `WAIT_LATE_RESULT_REJECTED`"；§3.12 "deterministic idempotency key derived from adapter key, wait id and external job id"。
- **影响**: Implementation agent 被迫自行设计 idempotency 与 late diagnostic 的交互语义，可能导致不同实现路径间行为不一致。
- **建议改法和验证点**:
  方案 A（推荐）：在 pipeline 步骤 3 中，先读 wait record status。如果 status 是 `cancelled` / `lost`，跳过 idempotency check，直接写 `WAIT_LATE_RESULT_REJECTED` diagnostic 并 raise `INVALID_STATE`。原因：late result 对已终态 wait record 不是有效的幂等重放候选，用同一 idempotency key 不应绕过终态保护。
  方案 B：为 late rejection 使用独立 idempotency scope（如 `wait_late_rejection`），与 `wait_resolution` scope 分离。
  验证点：测试必须覆盖 (a) `cancelled` wait + same idempotency key + same digest → 写 diagnostic + raise INVALID_STATE（非 idempotent replay）；(b) `cancelled` wait + new idempotency key → 写 diagnostic + raise INVALID_STATE。
- **修复风险（低/中/高）**: 低 — 只需调整 pipeline 步骤顺序或增加 early return 分支。
- **严重程度（低/中/高/严重）**: 高

### 2-未修复-中-`TOOL_RESULT_ACCEPTED` payload 扩展字段未指定

- **位置**: §3.10 EventLog Facts，`TOOL_RESULT_ACCEPTED` 条目
- **问题类型**: 契约缺失
- **当前写法**: "If current P6 payload codec cannot express wait source refs, extend it rather than creating a second weak event."
- **反例/失败场景**: Implementation agent 需要向 `TOOL_RESULT_ACCEPTED` payload 添加字段来承载 wait resolution 来源信息（`wait_id`、`source`、`resolution_kind` 等），但 plan 没有指定具体要添加哪些字段。Agent 可能添加过多字段（暴露 wait record 内部结构到 EventLog）或过少字段（后续 projection 无法从 EventLog 重建 wait resolution 语义）。
- **为什么有问题**: §3.10 详细列出了 `WAIT_LATE_RESULT_REJECTED` diagnostic event 的 payload 字段（14 个），但对 `TOOL_RESULT_ACCEPTED` 如何扩展来承载 wait source refs 只有一句话。两个事件的 payload 设计应同等具体。
- **直接证据**: §3.10 "If current P6 payload codec cannot express wait source refs, extend it rather than creating a second weak event" — 无具体字段列表。
- **影响**: Implementation agent 临场决定 payload 字段，可能与后续 projection / tool trace phase 的消费预期不匹配。
- **建议改法和验证点**: 在 §3.10 中明确 `TOOL_RESULT_ACCEPTED` payload 扩展字段列表，至少包括 `wait_id`、`source`（`WaitResolutionSource`）、`resolution_kind`（`completed` / `failed` / `cancelled` / `lost`）、`outcome_digest`。同时说明哪些字段是 wait resolution 专有、哪些是普通 tool result 也使用的既有字段。
- **修复风险（低/中/高）**: 低 — 只需补充字段列表。
- **严重程度（低/中/高/严重）**: 中

### 3-未修复-中-`WaitAdapterKey` 和 `ExternalJobRef.external_job_id` 缺少具体约束值

- **位置**: §3.5 Adapter Key Source，§3.6 `snapshot_ref` / `external_job_id` Typed Ref Constraints
- **问题类型**: 契约缺失
- **当前写法**:
  - `WaitAdapterKey(value: str)`：非空、长度受限、只允许稳定 registry key。
  - `ExternalJobRef.external_job_id`：非空、长度受限、只允许 adapter 可重读的稳定外部 job id。
- **反例/失败场景**: "长度受限"未给出具体 max length。Implementation agent 可能选择 256、512、1024 或其它值。不同 slice 的 agent 可能选择不同长度，或在 schema DDL 与 dataclass validation 之间不一致。
- **为什么有问题**: Plan §3.7 的 wait record schema 中 `adapter_key TEXT NOT NULL` 和 `external_job_id TEXT NULL` 没有长度约束。但 §3.5 / §3.6 要求"长度受限"。Implementation agent 需要在这两处保持一致。
- **直接证据**: §3.5 "非空、长度受限"；§3.6 "非空、长度受限"；§3.7 schema DDL 无 CHECK 约束体现长度。
- **影响**: 低 — 不会导致功能失败，但可能导致不同模块间约束不一致。
- **建议改法和验证点**: 指定具体 max length，如 `WaitAdapterKey` max 64 chars、`external_job_id` max 256 chars。或说明长度约束只在 dataclass `__post_init__` 中验证，不在 DDL CHECK 中体现。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 4-未修复-低-`ToolFactKind.LOST` 枚举扩展位置未显式声明

- **位置**: §3.10 EventLog Facts，lost outcome 条目
- **问题类型**: 不可直接实施
- **当前写法**: "Lost outcome must use `TOOL_RESULT_ACCEPTED` with typed `ToolFactKind.LOST` / payload `tool_fact_kind='lost'`"
- **反例/失败场景**: `ToolFactKind` 定义在 `dayu/host/tool_runtime.py:178`，当前成员为 `COMPLETED`、`FAILED`、`CANCELLED`、`GOVERNED_ERROR`、`REUSE`。Plan 要求添加 `LOST`，但 §4.1 P7-S3 的 allowed files 不包含 `tool_runtime.py`（只有 P7-S2 包含）。S3 是 `resolve_wait` 实现 slice，需要用 `ToolFactKind.LOST`，但该文件不在 S3 allowed files 中。
- **为什么有问题**: `ToolFactKind` 是 `tool_runtime.py` 的模块级 enum。S3 需要引用 `LOST` 成员，但不能修改 `tool_runtime.py`。要么 S1 / S2 预先添加 `LOST`，要么 S3 的 allowed files 需要包含 `tool_runtime.py`。
- **直接证据**: §4.1 P7-S3 allowed files 不含 `tool_runtime.py`；§3.10 要求 `ToolFactKind.LOST`。
- **影响**: Implementation agent 可能在 S3 发现需要修改不在 allowed files 中的文件而被迫停止。
- **建议改法和验证点**: 在 P7-S1 或 P7-S2 的 exact changes 中明确添加 `ToolFactKind.LOST` 到 `dayu/host/tool_runtime.py`，或在 P7-S3 allowed files 中添加该文件。验证：S3 完成后 `ToolFactKind` 包含 `LOST` 成员。
- **修复风险（低/中/高）**: 低 — 只需调整 slice 文件归属。
- **严重程度（低/中/高/严重）**: 低

### 5-未修复-低-`ResolveWaitLostOutcome` 与其它 outcome 成员的字段互斥未显式声明

- **位置**: §3.2 `ResolveWaitRequest` Typed Outcome Envelope
- **问题类型**: 契约缺失
- **当前写法**: 四个 outcome 类型分别定义了不同字段。`ResolveWaitLostOutcome` 有 `reason_code`、`message`、`provider_status_ref`，没有 `result` 或 `payload_ref`。其它三个有 `result` 和 `payload_ref`。
- **反例/失败场景**: Implementation agent 在 `__post_init__` 校验时可能不确定 `ResolveWaitLostOutcome` 是否可以同时携带 `payload_ref`（当前定义没有该字段，但也没有显式禁止）。这不是真正的歧义——dataclass 字段定义已经排除了——但 plan 的文字描述"outcome digest 输入必须包含 outcome kind、typed result fields、payload ref / provider status ref"可能暗示 lost outcome 也有 `payload_ref`。
- **为什么有问题**: §3.2 说 digest 输入必须包含 "payload ref / provider status ref"，暗示两者都存在。但 lost outcome 只有 `provider_status_ref`，没有 `payload_ref`。Implementation agent 可能在 digest 计算时困惑。
- **直接证据**: §3.2 "digest 输入必须包含 outcome kind、typed result fields、payload ref / provider status ref"。
- **影响**: 低 — dataclass 定义已经足够清晰，但 digest 计算逻辑可能有歧义。
- **建议改法和验证点**: 在 §3.2 digest 描述中明确"对 lost outcome，`payload_ref` 为 None；对其它 outcome，`provider_status_ref` 为 None"。或简化为"digest 输入包含所有非 None 字段"。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

无。Plan §10 声明 "blocking question count: 0"，经 review 确认无需 controller 裁决的 blocking open question。Finding #1 的 idempotency-vs-diagnostic 交互需要 plan 明确，但属于 plan 内可修复的 sequencing 问题，不需要 controller 新决策。

## Residual Risks

1. **Callback productization 延迟**: Plan 正确 defer，§11 已追踪。
2. **Cross-process duplicate governance**: Phase 6 run-local in-memory 限制在 §11 已追踪。
3. **Recovery scan after restart**: Plan §11 已追踪到 Phase 11。
4. **`TOOL_RESULT_ACCEPTED` payload 扩展与后续 projection phase 的兼容性**: Finding #2 要求明确字段列表，但后续 Phase 8 projection 消费该 payload 的具体需求可能在 Phase 8 plan 中才完全明确。当前 plan 应至少列出 Phase 7 需要的最小字段集。

## Plan Gate Requirement Coverage Check

| Plan Gate Requirement（来自 controller adjudication） | Plan 覆盖 | 证据位置 |
| --- | --- | --- |
| `ResolveWaitRequest` typed outcome envelope 字段名、封闭联合成员、payload ref / result ref 约束 | 已覆盖 | §3.2 |
| `observed_at` 使用 `datetime` 还是 strict validated string | 已覆盖 | §3.3 |
| adapter reported lost 与 Host wait record `lost` 终态区别 | 已覆盖 | §3.4 |
| `adapter_key` 来源；不得扩展 Engine 契约 | 已覆盖 | §3.5 |
| `snapshot_ref` 与 `external_job_id` typed ref 约束 | 已覆盖 | §3.6 |
| `WAIT_LATE_RESULT_REJECTED` diagnostic EventLog event schema | 已覆盖 | §3.10 |
| `WAITING` cancel 与 `resolve_wait` 并发 first-committer-wins | 已覆盖 | §3.11 |
| poll adapter 观察到 cancelled wait 后停止 / abandon observation | 已覆盖 | §3.12 |

## Conclusion

**pass-with-risks**

Plan 整体 code-generation-ready，覆盖面完整，所有 plan gate requirement 均有对应 plan section。Slice 边界清晰，file ownership 明确，stop conditions 具体。Host / Engine 边界正确维护，没有引入兼容性路径或弱类型。

主要风险是 Finding #1（`resolve_wait` pipeline 幂等检查与 late diagnostic 写入顺序冲突），需要在实施前明确 sequencing 解决方案。该 finding 修复成本低，不影响 plan 整体结构。Finding #2 和 #3 是契约补充项，修复成本低。Finding #4 和 #5 是文件归属和措辞精确性问题。

建议 controller 接受 Finding #1 作为 plan fix，Finding #2-5 作为 implementation guidance 补充。
