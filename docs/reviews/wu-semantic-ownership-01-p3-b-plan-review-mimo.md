# WU-SEMANTIC-OWNERSHIP-01 P3-B Plan Review (AgentMiMo)

## Review scope

- Target: `docs/host/wu-semantic-ownership-01-p3-b-terminal-final-answer-outbox-plan.md`
- Gate: adversarial plan review
- Source docs: `docs/host/design.md`, `docs/engine/design.md`, `docs/host/issues-implementation-control.md`, `docs/reviews/wu-semantic-ownership-01-fullrepo-deepreview-round2-controller-adjudication.md`
- Code verification: `_terminal_answer.py`, `outbox.py`, `read_api.py`, `api.py`, `durable/outbox.py`, `terminal_payload.py`, `engine_ingest.py`, `durable/memory.py`, `compact_material.py`, `run_input.py`, `memory.py`

## Assumptions tested

1. Terminal-answer resolver is the single source-of-truth for final answer text — **confirmed**.
2. Outbox and read API currently bypass the resolver — **confirmed**.
3. `HostEvent` succeeded requires `final_answer` — **confirmed** (`api.py:3121`).
4. `OutboxTerminalItem` succeeded requires `final_answer` — **NOT confirmed** (gap exists).
5. Durable outbox row validator enforces status-specific `final_answer_json` — **NOT confirmed** (gap exists).
6. `HostFinalAnswerView.content` rejects empty string — **NOT confirmed** (allows empty string).
7. Existing typed material consumers already call the resolver — **confirmed** (durable/memory, compact_material, run_input).
8. Plan source evidence line references are accurate — **one factual error found**.

## Findings

### F01-未修复-高-OutboxTerminalItem succeeded 公共不变量缺失 final_answer 必填校验

- **位置**: plan §7.1 "Public contract tightening"、§7.2 "Durable Outbox invariant"、代码 `api.py:3149-3166`
- **问题类型**: 契约缺失
- **当前写法**: plan 声称 "`OutboxTerminalItem(terminal_status=SUCCEEDED)` 升级为必须有 `final_answer`"，但当前 `_validate_outbox_terminal_payload`（`api.py:3149-3166`）在 `terminal_status == SUCCEEDED` 时只检查 `error_message` 和 `cancel_reason` 为 `None`，然后直接 `return`，**不检查 `final_answer` 是否存在**。
- **反例/失败场景**: 实施 agent 修改 Outbox projection 让 succeeded item 的 `final_answer_json` 为 `None`（例如 resolver 抛错但 row 仍被写入），`OutboxTerminalItem` construction 不会报错，公共 API 返回 `succeeded + final_answer=None`，与 plan 声称的 invariant 矛盾。
- **为什么有问题**: plan §1 成功信号明确要求 "`RUN_SUCCEEDED` 在 HostEvent 与 public Outbox contract 中都必须携带非空 `HostFinalAnswerView`"。`HostEvent` 已有此校验（`api.py:3121`），但 `OutboxTerminalItem` 缺失。这是 owner/producer/read 边界未闭合。
- **直接证据**: `api.py:3157-3166`：
  ```python
  if item.terminal_status is HostTerminalStatus.SUCCEEDED:
      if item.error_message is not None or item.cancel_reason is not None:
          raise ValueError(...)
      return  # <-- 不检查 final_answer
  ```
- **影响**: 公共 contract 只有一半闭合；succeeded Outbox item 可以合法携带 `final_answer=None`。
- **建议改法和验证点**: 在 `_validate_outbox_terminal_payload` 的 succeeded 分支增加 `if item.final_answer is None: raise ValueError(...)`。测试必须覆盖 `OutboxTerminalItem(terminal_status=SUCCEEDED, final_answer=None)` 被拒绝。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 高

### F02-未修复-高-HostFinalAnswerView.content 允许空白字符串

- **位置**: plan §7.1 "HostFinalAnswerView.content 必须是非空、非纯空白文本"、代码 `api.py:2710-2747`
- **问题类型**: 契约缺失
- **当前写法**: plan 声称 "`HostFinalAnswerView.content` 必须是非空、非纯空白文本"。但 `HostFinalAnswerView.__post_init__`（`api.py:2728`）只检查 `isinstance(self.content, str)`，允许空字符串 `""`。
- **反例/失败场景**: resolver 返回空白 content（例如 descriptor content 为空白但 strict policy 返回空字符串而非 `None`），`HostFinalAnswerView(content="", ...)` 构造成功，public read 返回空回答。
- **为什么有问题**: plan §1 成功信号要求 "succeeded `HostEvent.final_answer.content` 与 public Outbox read/drain `item.final_answer.content` 都等于非空文本"。当前 `__post_init__` 不拒绝空白 content，invariant 不闭合。
- **直接证据**: `api.py:2728-2729`：
  ```python
  if not isinstance(self.content, str):
      raise TypeError("HostFinalAnswerView.content must be str")
  # 没有 content.strip() == "" 检查
  ```
- **影响**: 空白 content 可穿透公共 contract 到达 UI/Service/LLM-facing 输出。
- **建议改法和验证点**: 在 `__post_init__` 增加 `if self.content.strip() == "": raise ValueError("HostFinalAnswerView.content must be non-empty")`。测试必须覆盖 `HostFinalAnswerView(content=" ", ...)` 和 `HostFinalAnswerView(content="", ...)` 被拒绝。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 高

### F03-未修复-高-durable Outbox row validator 缺失 final_answer_json 与 terminal_status 的条件校验

- **位置**: plan §7.2 "durable Outbox row write/read validation 执行同一 succeeded/non-success final answer 组合校验"、代码 `durable/outbox.py:821-873`
- **问题类型**: 契约缺失
- **当前写法**: plan 声称 "`_validate_item_row` 必须在写边界校验：`terminal_status == 'succeeded'` 时 `final_answer_json` 必填；failed/cancelled 时 `final_answer_json` 必须为 `None`"。但当前 `_validate_item_row`（`durable/outbox.py:841`）对 `final_answer_json` 只调用 `_require_optional_non_empty_text`，不与 `terminal_status` 关联。`_item_row_from_host_row`（`durable/outbox.py:935`）用 `_optional_text` 读取，同样无状态关联。
- **反例/失败场景**: 外部 DB 损坏或旧 row 写入 `succeeded + final_answer_json=NULL`，`_item_row_from_host_row` 不报错，durable read 返回非法 row。
- **为什么有问题**: plan 要求 "raw DB 损坏也在 durable read boundary fail closed"。当前 validator 不做状态关联校验，raw DB 损坏可穿透。
- **直接证据**: `durable/outbox.py:841` 调用 `_require_optional_non_empty_text`，无 `terminal_status` 参数。`durable/outbox.py:935` 用 `_optional_text`，无状态关联。
- **影响**: durable read boundary 不闭合；raw DB 损坏可产生 `succeeded + final_answer=None` row。
- **建议改法和验证点**: 在 `_validate_item_row` 增加条件校验：`terminal_status == "succeeded"` 时 `final_answer_json` 必须非 `None`；`terminal_status in ("failed", "cancelled")` 时 `final_answer_json` 必须为 `None`。测试必须覆盖 raw row 损坏被拒绝。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 高

### F04-未修复-低-plan 源证据行引用事实错误

- **位置**: plan §3.1 "直接生产证据" 第三条
- **问题类型**: 不可直接实施
- **当前写法**: plan 声称 "`dayu/host/durable/run_transition.py:4569-4584` 的 `RUN_SUCCEEDED` payload 保存 terminal descriptor pair 以及 `finish_reason` / `filtered` / `degraded`，不保存 inline `final_answer` 文本"。
- **反例/失败场景**: 实施 agent 按此行引用查找代码，找不到对应逻辑。实际 `RUN_SUCCEEDED` payload 的 terminal descriptor pair 保存在 `engine_ingest.py` 的 terminal closeout 路径（engine path `1230-1267`，host lifecycle path `1318-1356`），通过 `terminal_closeout_in_transaction` 的 `TerminalCloseoutInput.terminal_summary_ref` / `terminal_summary_digest` 传入。
- **为什么有问题**: plan 作为 code-generation-ready artifact，源证据行引用必须准确。行引用错误会导致实施 agent 浪费时间定位或误解代码结构。
- **直接证据**: `engine_ingest.py:1250-1251`：
  ```python
  terminal_summary_ref=descriptor.payload_ref,
  terminal_summary_digest=descriptor.payload_digest,
  ```
  `run_transition.py:4569-4584` 实际是 `_latest_rows_for_types` 辅助函数，与 `RUN_SUCCEEDED` payload 保存无关。
- **影响**: 实施 agent 定位困难；reviewer 信任度下降。
- **建议改法和验证点**: 修正行引用为 `engine_ingest.py:1230-1267`（engine closeout path）或 `engine_ingest.py:1318-1356`（host lifecycle closeout path）。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### F05-未修复-中-resolver 输出仅为 text，HostEvent 构造需要完整 metadata

- **位置**: plan §5.1 "required helper"、§6.1 "HostEvent/read API"
- **问题类型**: 架构边界
- **当前写法**: plan 提出 `required_assistant_final_answer_continuity_text(transaction, run_payload) -> str`，只返回 text。同时 plan §6.1 要求 `_succeeded_host_event` 调用此 resolver 取得 content，然后 "从同一 canonical payload 读取 `filtered` / `degraded` / `finish_reason`" 构造 `HostFinalAnswerView`。
- **反例/失败场景**: resolver 返回 text 后，`_succeeded_host_event` 仍需自行解析 `RUN_SUCCEEDED` payload 读取 metadata。如果 metadata 解析逻辑与 resolver 的 source precedence 不一致（例如 resolver 用了 inline text 但 metadata 从 descriptor payload 读取），会产生 content 与 metadata 来源不一致的 `HostFinalAnswerView`。
- **为什么有问题**: plan 声称 "metadata 从 canonical `RUN_SUCCEEDED` payload 读取，避免 Outbox 再解析 artifact shape"。但 `filtered` / `degraded` 在 inline source 时来自 `RUN_SUCCEEDED` payload，在 descriptor source 时来自 terminal artifact payload。resolver 选择 source 的逻辑需要同步到 metadata 读取。
- **直接证据**: `_terminal_answer.py` resolver 选择 inline 或 descriptor source 时，metadata 来源不同：inline 时 `filtered`/`degraded` 在 `RUN_SUCCEEDED` payload 中；descriptor 时在 terminal artifact payload 中。`_succeeded_host_event` 当前只从 terminal artifact payload 读取 metadata（`read_api.py:925-934`）。
- **影响**: 若 resolver 选择 inline 但 metadata 从 descriptor 读取，content 与 metadata 可能不一致。
- **建议改法和验证点**: plan 应明确：resolver 返回 text 时，metadata 从哪个 payload 读取。建议 resolver 同时返回 source indicator（inline/descriptor），或 `required` helper 返回 `(text, metadata_source_payload)` tuple。或者明确 inline precedence 时 metadata 也从 inline payload 读取。测试必须覆盖 inline precedence + metadata 一致性。
- **修复风险（低/中/高）**: 中
- **严重程度（低/中/高/严重）**: 中

### F06-未修复-中-ProjectionRunner 事务原子性假设需验证

- **位置**: plan §6.3 "原子性、cursor 与 retry"
- **问题类型**: 需要更多证据
- **当前写法**: plan 声称 "现有 runner 已保证 consumer apply、Outbox insert 与 checkpoint advance 在同一 write transaction"，并给出伪代码流程。
- **反例/失败场景**: 如果 ProjectionRunner 的 apply 和 checkpoint advance 不在同一事务中（例如 apply 后单独 commit checkpoint），resolver 失败时 checkpoint 可能已推进但 item 未写入，导致该 event 被永久跳过。
- **为什么有问题**: plan 的 failure/retry/idempotency 语义完全依赖此事务原子性。若假设不成立，整个 failure matrix 不成立。
- **直接证据**: plan 未引用 ProjectionRunner 的具体代码行或事务边界。需要验证 `OutboxTerminalProjectionConsumer.apply_event` 的 `transaction` 参数是否与 `insert_outbox_terminal_item_if_absent` 和 checkpoint advance 共享同一事务。
- **影响**: 若事务不原子，failure 后 retry 可能丢失 event 或产生不一致状态。
- **建议改法和验证点**: plan 应引用 ProjectionRunner 的具体事务边界代码。实施 agent 应在 S1 开始前验证此假设，若不成立则触发 stop condition。
- **修复风险（低/中/高）**: 中
- **严重程度（低/中/高/严重）**: 中

### F07-未修复-中-production smoke 测试依赖需确认

- **位置**: plan S1 "Behavior tests / expected assertions" 最后一条
- **问题类型**: 需要更多证据
- **当前写法**: plan 声称 "production public smoke：使用 `FinalAnswerWorkerFactory` 的真实 Host ingest/terminal descriptor 路径"。
- **反例/失败场景**: `FinalAnswerWorkerFactory` 若不存在或不产生 descriptor-backed answer（例如只产生 inline answer），smoke 测试无法验证 descriptor-only production shape 这一核心场景。
- **为什么有问题**: descriptor-only production shape 是 P3-B 的核心修复场景。若 smoke 只覆盖 inline path，descriptor fallback 的正确性未被验证。
- **直接证据**: plan 未验证 `FinalAnswerWorkerFactory` 是否存在以及是否支持 descriptor-backed answer production。
- **影响**: 核心场景未被 smoke 覆盖。
- **建议改法和验证点**: plan 应验证 `FinalAnswerWorkerFactory` 存在且能产生 descriptor-backed answer。若不存在，应设计替代 smoke fixture 使 terminal closeout 产生 descriptor-only `RUN_SUCCEEDED`。
- **修复风险（低/中/高）**: 中
- **严重程度（低/中/高/严重）**: 中

### F08-未修复-中-Outbox 失败原子性测试依赖 PayloadStore 恢复语义

- **位置**: plan S1 "Outbox failure atomicity" 测试
- **问题类型**: 需要更多证据
- **当前写法**: plan 声称 "用正式 `PayloadStore` 恢复同 ref/同 digest descriptor 后重跑，item 和 checkpoint 提交、failure 清除"。
- **反例/失败场景**: 如果 `PayloadStore` 的恢复语义不是"同 ref/同 digest 可恢复"（例如 ref 被标记为 deleted 而非 missing），测试无法构造恢复场景。
- **为什么有问题**: 此测试验证 plan 的 retry 闭环。若 PayloadStore contract 不支持此恢复路径，retry 语义无法验证。
- **直接证据**: plan 未引用 `PayloadStore` 的恢复 API 或 contract。
- **影响**: retry 闭环无法被测试覆盖。
- **建议改法和验证点**: plan 应引用 `PayloadStore` 的恢复 API（如 `write_payload_descriptor` 或等价接口），确认同 ref/同 digest 可重新写入。若不支持，应设计替代测试策略。
- **修复风险（低/中/高）**: 中
- **严重程度（低/中/高/严重）**: 中

## Rejected concerns

### R01-已拒绝-纯 memory consumer 反向耦合到 durable transaction

plan §5.4 正确保留了 `memory.py` 的 lenient inline fallback（`memory.py:1650-1657`），不让纯 memory consumer import `durable.transaction` 或 `_terminal_answer` 的 transaction API。这是正确的设计：纯 consumer 消费 typed material，不反向打开 descriptor。plan 在此点上无问题。

### R02-已拒绝-required/optional 与 strict/lenient policy 不自洽

plan §5.3 正确定义了 `STRICT_NON_EMPTY`（用于 durable/public projection）和 `LENIENT_NON_EMPTY`（用于纯 memory consumer 的 inline fallback）的边界。`required` helper 固化 `STRICT_NON_EMPTY` + 非 nullable 返回类型，`optional` resolver 保持 `str | None`。两者语义一致，无不自洽。

### R03-已拒绝-slice 过粗需要拆分

plan 只有 1 个 slice，修改量围绕同一个 terminal-answer projection contract。control doc 建议小型同一语义 cleanup 为 1-3 slices。拆成 resolver contract / Outbox materialization / public invariant 三个 slice 会产生 contract-only 半成品（"resolver 已有但 Outbox 仍丢 answer"），没有独立风险收益。1 slice 是合理的。

## Open questions

### OQ01-required resolver 返回 text 后，metadata 来源如何确定？

resolver 选择 inline 或 descriptor source，但 `filtered` / `degraded` / `finish_reason` 的来源取决于 resolver 选择的 source。plan 应明确 metadata 读取策略：是否从同一 source payload 读取？是否需要 resolver 返回 source indicator？

### OQ02-ProjectionRunner 事务原子性假设是否成立？

plan 的 failure/retry/idempotency 语义完全依赖 ProjectionRunner 的 apply + insert + checkpoint 在同一事务。实施 agent 应在 S1 开始前验证此假设。

### OQ03-FinalAnswerWorkerFactory 是否存在且支持 descriptor-backed answer？

production smoke 测试依赖此 factory。若不存在或不支持 descriptor path，需设计替代 fixture。

## Residual risks

1. **DDL conditional CHECK 缺失**: plan 正确识别 P3-B 不做 DDL hardening，succeeded row 的 `final_answer_json` 非 NULL 由 producer/validator/public validator 覆盖。P3-J 负责 DDL 层。
2. **descriptor storage 外部破坏后自动 repair**: plan 正确识别不属于 P3-B。本 slice 只保证 failure 可观察、无半成品、恢复后可 retry。
3. **terminal descriptor 与 RUN_SUCCEEDED metadata 双副本一致性**: plan 正确识别不属于 P3-B。若未来发现 metadata 副本可独立漂移，应进入单独 owner/schema 裁决。

## Final plan review conclusion

**pass-with-risks**。

Plan 整体架构正确：terminal-answer resolver 作为 source-of-truth owner，Outbox 和 read API 迁回 owner，durable/public invariant 补齐。设计决策（inline precedence、required/optional、strict/lenient、transaction boundary、failure matrix、1 slice）均合理且与设计真源对齐。

但有 3 个高 severity findings（F01-F03）需要在实施前修复：`_validate_outbox_terminal_payload` 缺失 succeeded final_answer 必填校验、`HostFinalAnswerView.content` 允许空白字符串、durable outbox row validator 缺失状态关联校验。这些是 plan 自己声称要修复但未在 plan 文本中给出具体修改位置的 invariant gap。

3 个 medium severity findings（F05-F08）需要实施 agent 在 S1 开始前验证或在实施中处理：resolver 输出与 metadata 来源一致性、ProjectionRunner 事务原子性假设、production smoke 依赖。

1 个 low severity factual error（F04）需要修正行引用。

**Verdict**: pass-with-risks (3 high, 3 medium, 1 low findings; 0 blocking questions; 3 open questions)

**Artifact**: `docs/reviews/wu-semantic-ownership-01-p3-b-plan-review-mimo.md`
