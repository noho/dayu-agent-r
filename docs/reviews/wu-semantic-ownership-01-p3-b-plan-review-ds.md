# WU-SEMANTIC-OWNERSHIP-01 P3-B Plan Review — Adversarial (AgentDS)

## Review metadata

- **Reviewed artifact**: `docs/host/wu-semantic-ownership-01-p3-b-terminal-final-answer-outbox-plan.md`
- **Review type**: adversarial plan review
- **Gate**: plan review only；不实施、不修改 plan / 生产代码 / 测试 / control doc / 其它 artifact
- **Reviewer**: AgentDS (adversarial)
- **Timestamp**: 2026-07-10T14:11:40+08:00
- **Artifact path**: `docs/reviews/wu-semantic-ownership-01-p3-b-plan-review-ds.md`

## Scope

本 review 审阅 P3-B 计划 artifact，依据以下真源：

- `CLAUDE.md` 项目指令
- `docs/host/design.md` Host 设计真源
- `docs/engine/design.md` Engine 设计真源
- `docs/host/issues-implementation-control.md` issue-backed work unit 总控
- `docs/reviews/wu-semantic-ownership-01-fullrepo-deepreview-round2-controller-adjudication.md` round 2 controller 裁决

涵盖 8 个显式 challenge domain 加上 architecture boundary / best-practice / optimal-solution / overengineering / overcoupling lenses。

## Assumptions tested

1. **Inline `final_answer` is a valid production source form** (plan §5.2 step 1, §5.3 inline precedence): tested against `_run_terminal_payload` in `dayu/host/durable/run_transition.py:4569-4584` — see F-01.

2. **`build_outbox_terminal_item_row` can receive `HostTransaction` without breaking callers** (plan §6.2): tested against `OutboxTerminalProjectionConsumer.apply_event` at `outbox.py:147-178` — `transaction` already in scope, no new import dependency needed. Passes.

3. **Required resolver fail-closed is safe for both HostEvent and Outbox read paths** (plan §6.1-6.2): tested against `_host_event_from_row` at `read_api.py:867-900` and `_final_answer_from_outbox_json` at `read_api.py:826-864`. HostEvent path already fails on malformed payload; Outbox read already fails on malformed JSON. Passes.

4. **`read_api._sqlite_payload_object` / `_terminal_payload_object` have no callers beyond `_succeeded_host_event`** (plan §6.1): verified by grep — both only called at `read_api.py:923`. Passes.

5. **`FinalAnswerWorkerFactory` exists and exercises production ingest/terminal descriptor path** (plan §10 behavior tests): verified at `tests/host/public_smoke_support.py:348`. Passes.

6. **Outbox idempotency key excludes answer text** (plan §6.2): tested against `build_outbox_terminal_item_identity` at `outbox.py:181-224`. Passes.

7. **ProjectionRunner wraps apply/insert/checkpoint in single write transaction** (plan §6.3): tested against `ProjectionRunner._process_next_event` at `projection.py:558-651`. Confirmed: consumer apply, checkpoint advance, failure clear all in one `run_write` transaction. Passes.

8. **`HostFinalAnswerView.content` currently allows blank strings** (plan §7.1): tested against `HostFinalAnswerView.__post_init__` at `api.py:2728-2746` — checks `isinstance(self.content, str)` but NOT `content.strip() != ""`. Confirmed gap. Passes.

## Findings

### F-01 — MEDIUM — Inline `final_answer` field provenance is undefined；与 "非旧库兼容" 政策潜在冲突

- **位置**: plan §5.2 step 1 (line 126), §1 成功信号 (line 16), §3.4 DS-2/DS-4 裁决, §5.3 (line 130)
- **问题类型**: 契约缺失 / 不可直接实施
- **当前写法**: plan 将 `RUN_SUCCEEDED.final_answer` 描述为 "第一优先级来源"、"当前设计真源和 resolver 已声明的两种合法 source form 之一"、"这不是旧 shape compatibility" (line 16, 126-130)
- **反例/失败场景**:
  1. `dayu/host/durable/run_transition.py:4569-4584` 的 `_run_terminal_payload` 构建 `RUN_SUCCEEDED` 规范 payload 时**不写入** `final_answer` 字段 — grep 确认该文件零引用 `final_answer`。
  2. `dayu/host/engine_ingest.py:4885-4931` 的 `_final_answer_plan` 将 content 写入 terminal payload descriptor 顶层 `content`，不写入规范 payload 的 `final_answer`。
  3. 生产中 success terminal closeout 路径 (`engine_ingest.py:1230-1265`) 先 `_write_terminal_payload` 产 descriptor，再 `terminal_closeout_in_transaction` 传 `terminal_summary_ref/digest`；整个过程不产生 inline `final_answer` 字段。
  4. 因此 `_terminal_answer.py:60-64` 对 `final_answer` 的 inline-first 读取**在生产环境永不命中**；它只在测试 fixture 中被手动写入 payload (如 `test_outbox_projection.py:196`, `test_terminal_payload.py:236`)。
- **为什么有问题**: plan 声称 inline 是 "设计真源" 而非 "旧库兼容"，但证据显示它不是生产者写入的字段，而是消费者预留的读取路径。CLAUDE.md 明确禁止兼容性代码，但 plan 恰好保留了仅被测试 fixture 使用的 inline 路径而不说明其实际用途。若 implementation agent 按照 plan 字面理解，可能错误地认为需要同时维护 inline 生产路径与 descriptor 生产路径，造成隐式双重真源。
- **直接证据**:
  - `run_transition.py` 零 `final_answer` 引用 (grep 结果)
  - `_run_terminal_payload:4569-4584` 未写入 `final_answer`
  - `engine_ingest.py:4915-4920` 将 content 写入 terminal descriptor 而非规范 payload
  - `outbox.py:360` 当前 `_final_answer_json` 读 `final_answer` 字段但始终返回 `None` (因为字段缺失)
- **影响**: 实施 Agent 可能困惑 inline 路径的定位、是否应保留、是否应为其添加生产者代码；reviewer 无法判断 inline precedence test 的目标是 safety net 还是 production path。
- **建议改法和验证点**:
  1. plan 应明确说明 inline `final_answer` 当前仅在测试中使用，生产中 answer 始终通过 terminal descriptor 路径。
  2. 为 inline 路径给出明确理由 (如 "测试便捷性，允许测试直接设 payload 而不构造完整 descriptor chain")。
  3. 若 inline 路径没有 production 使用场景，应标记为测试辅助路径并说明预期生命周期；若未来也不会用于 production，应考虑按 CLAUDE.md "禁止兼容性代码" 规则移除。
- **修复风险（低）**: 仅需澄清 plan 文本，不改变实现方案。
- **严重程度（中）**: 不影响功能正确性，但设计真源声明与代码事实矛盾，可能导致实施 Agent 误解。

---

### F-02 — MEDIUM — "恢复同 ref/同 digest descriptor" retry 测试场景欠规格

- **位置**: plan §10 行为测试 "Outbox failure atomicity" (line 373)
- **问题类型**: 不可直接实施 / 测试缺口
- **当前写法**: "用正式 `PayloadStore` 恢复同 ref/同 digest descriptor后重跑，item和checkpoint提交、failure清除；再次replay item数仍为1且duplicate计数增加。"
- **反例/失败场景**:
  1. `dayu/host/payload_resolution.py` 的 `write_payload_descriptor` 每次生成新的 `payload_id` (基于 UUID + timestamp)，`payload_ref` 由 `sha256(payload_id)` 派生。**不存在** "以给定 ref 恢复同一 descriptor" 的公共 API。
  2. 要 "恢复同 ref/同 digest descriptor"，必须直接向 `sqlite_payloads` 表 INSERT 一行，指定特定 `payload_id` 以匹配 ref，并写入完全相同的 `payload_json` 以匹配 digest。这不是 `PayloadStore` contract 的正式操作，而是测试层直接操作 durable 内部表。
- **为什么有问题**: plan 用 "正式 PayloadStore" 描述方法，但实际需要的操作是直接 SQL INSERT。若 implementation agent 按字面在 `PayloadStore` 上找 "恢复" API，会找不到并能/或写出绕路的测试；若 review 时发现测试直接操作内部表，可能被视为 test-to-implementation coupling。
- **直接证据**:
  - `write_payload_descriptor` 生成 `payload_id = _generate_payload_id()` (UUID+timestamp)，ref 由此派生 — 不可重现
  - `sqlite_payload_object` (resolver 使用的) 读 descriptor 后查询 `sqlite_payloads WHERE payload_id = ?` — 必须匹配 descriptor 中的 `sqlite_payload_id`
- **影响**: 实施 Agent 或写出不测试真场景的 mock-based test，或用绕过 contract 的 SQL 直接操作写出测试后被 review 质疑。
- **建议改法和验证点**:
  1. plan 应明确说明 "恢复" 的具体操作：向 `sqlite_payloads` 表重新 INSERT 相同的 payload row (同 payload_id, 同 payload_json)。
  2. 确认该操作在测试环境中是合法且可执行的 (SQLite 同文件)。
  3. 或改用更简单的测试策略：删除 Outbox item row + 重置 checkpoint → 重跑，验证相同 idempotency key 阻止重复插入。
- **修复风险（低）**: 仅需澄清测试策略。
- **严重程度（中）**: 不影响实现方案正确性，但测试场景欠规格可能导致 implementation agent 写出错误或绕路的测试。

---

### F-03 — MEDIUM — Required resolver 抛 `HostDurableError` 时不区分 "descriptor 对缺失" vs "content 空白"

- **位置**: plan §5.1 required helper (line 111-118), §5.3 strict/lenient policy (line 133-138), §8 failure matrix (lines 242-246)
- **问题类型**: 契约缺失 / 可观测性缺口
- **当前写法**: required helper "当没有可显示文本时抛 `HostDurableError`" (line 117-118)。failure matrix 列出了多个不同 root cause (ref/digest 缺失、单边、missing descriptor、digest mismatch、content 缺失/空白) 但都映射到同一行为 "no row + checkpoint不动 + failure记录"。
- **反例/失败场景**:
  1. 当前 `assistant_final_answer_continuity_text` 在 ref/digest 缺失 (line 72-73) 返回 `None`，在 `sqlite_payload_object` 失败时抛 `HostDurableError` (line 74-79)。required wrapper 统一抛 `HostDurableError`，但调用方无法从异常类型或 error message 区分 "没有 descriptor pair" vs "digest mismatch" vs "content 空白"。
  2. `_validate_item_row` (durable/outbox.py:841) 仅校验 `final_answer_json` 非空文本，不关心失败原因。但 `ProjectionRunner._record_failure` (projection.py:672-674) 只记录 `exception.__class__.__name__` 与 `str(exception)`，这意味着不同 root cause 的失败行可能难以在生产日志中区分。
- **为什么有问题**: failure matrix 区分了 7 种不同的失败根因，但 durable failure row 只记录 `HostDurableError` + error message。若 message 不包含足够区分信息，运维排障时需要读 Python traceback 或分析代码才能定位根因。
- **直接证据**:
  - `_terminal_answer.py:74-79` — `sqlite_payload_object` 的异常自然包含具体消息 (如 "terminal payload descriptor is missing", "terminal payload digest mismatch")；但 ref/digest 缺失时 resolver 返回 `None`，required wrapper 需自行生成消息。
  - `projection.py:672-674` — failure row 只记录 `error_code=exception.__class__.__name__` + `error_message=str(exception)`
- **影响**: 排障效率降低；若 required wrapper 只抛 "no assistant final answer text" 而不包含 root cause 上下文，不同根因在 failure row 中不可区分。
- **建议改法和验证点**:
  1. plan 应要求 required wrapper 的 `HostDurableError` 消息明确包含失败原因：是 "no inline answer and no descriptor pair"、"descriptor pair malformed (one-sided)"、"descriptor missing"、"payload digest mismatch" 还是 "descriptor content missing/blank"。
  2. 测试应验证不同 root cause 产生可区分的 error message。
- **修复风险（低）**: resolver 内部调用 (`sqlite_payload_object`) 已产生区分消息；仅 `None` 返回路径需在 required wrapper 生成具体消息。
- **严重程度（中）**: 不影响功能正确性，但排障可观测性不足。

---

### F-04 — LOW — Read API `_succeeded_host_event` 用 required resolver 替代后，其当前 `_required_payload_text` 对 ref/digest 的硬性检查被后移到 resolver 中

- **位置**: plan §6.1 (line 151-156), plan §10 allowed production changes item 2 (line 360)
- **问题类型**: 契约缺失
- **当前写法**: plan 要求 `read_api._succeeded_host_event` "改用 required resolver，metadata 从 canonical run payload读取；删除 read API 私有 terminal descriptor/SQLite parser" (line 360)。
- **反例/失败场景**:
  1. 当前 `_succeeded_host_event` (read_api.py:912-927) 对 `terminal_summary_ref` / `terminal_summary_digest` 使用 `_required_payload_text` — 这两个字段在 `RUN_SUCCEEDED` 规范 payload 中**永远存在** (由 `_run_terminal_payload:4574-4575` 写入)。如果缺失，当前代码会在读 payload 时立即抛异常。
  2. 改用 required resolver 后，若规范 payload 因未知原因缺少 ref/digest 对，resolver 的 inline-first 逻辑会先尝试读 `final_answer` (不存在) → 然后检测 ref/digest 缺失 → 返回 `None` → required wrapper 抛错。
  3. 行为等价 — **但错误的抛出点从 read_api layer 后移到了 resolver layer**。这是正确的架构收敛，不是行为退化。
- **为什么有问题**: 这不是 plan 的问题，而是需要确认的重构等价性。当前 `_succeeded_host_event` 的 ref/digest 检查是重复检查 (生产规范 payload 永远有这对字段)，删除它不会丢失校验能力，因为 resolver 内部也会校验。
- **直接证据**:
  - `read_api.py:912-927` — `_required_payload_text` 对 `terminal_summary_ref/digest` 强制要求
  - `_run_terminal_payload:4574-4575` — 始终写入 `terminal_summary_ref/digest`
  - `_terminal_answer.py:72-73` — resolver 在 inline 缺失时检测 ref/digest 缺失
- **影响**: 低。重构等价性成立，但 plan 应显式确认这一点。
- **建议改法和验证点**: plan 可加一句：`_succeeded_host_event` 当前对 `terminal_summary_ref/digest` 的硬性检查等价于 resolver 内部的 descriptor pair 校验，删除它不丢失任何语义。
- **修复风险（低）**: 仅需文档澄清。
- **严重程度（低）**

---

### F-05 — LOW — `_validate_outbox_terminal_payload` 当前未校验 succeeded + `final_answer=None`；plan §7.1 承诺修复但 exact change site 不够具体

- **位置**: plan §7.1 (line 213-214), plan §10 exact allowed changes item 5 (line 364)
- **问题类型**: 契约缺失 / 不可直接实施
- **当前写法**: "`OutboxTerminalItem(terminal_status=SUCCEEDED)` 升级为必须有 `final_answer`" (line 213)。
- **反例/失败场景**:
  1. 当前 `_validate_outbox_terminal_payload` (api.py:3149-3166) 仅检查：succeeded 不能携带 error/cancel；非 succeeded 不能携带 final_answer。**未检查 succeeded 必须有 final_answer**。
  2. plan 在 exact changes item 5 (line 364) 说 "`OutboxTerminalItem` 条件不变量要求 succeeded final answer 必填" — 这意味着需要在 `__post_init__` (调用 `_validate_outbox_terminal_payload` 处) 或 `_validate_outbox_terminal_payload` 内添加 `if item.terminal_status is SUCCEEDED and item.final_answer is None: raise ValueError(...)`.
  3. plan 没有精确指出修改 `_validate_outbox_terminal_payload` 还是 `__post_init__` 还是两者。
- **为什么有问题**: implementation agent 可能把校验加在错误位置 (如只加在 `__post_init__` 而不更新 `_validate_outbox_terminal_payload`，反之亦然)。
- **直接证据**: `api.py:3157-3166` — 明确缺少 succeeded + final_answer=None 检查
- **影响**: implementation agent 可能漏加或重复加校验。
- **建议改法和验证点**: plan exact changes 应写 "`_validate_outbox_terminal_payload` 新增 succeeded + final_answer=None 检查" 而不是笼统的 "条件不变量要求"。
- **修复风险（低）**: 修改单函数，低风险。
- **严重程度（低）**

---

### F-06 — LOW — `HostFinalAnswerView.content` blank check 需要同时处理纯空白字符串，但 plan 未说明

- **位置**: plan §7.1 (line 211), plan §10 exact changes item 5 (line 364)
- **问题类型**: 契约缺失
- **当前写法**: "`HostFinalAnswerView.content` 必须是非空、非纯空白文本" (line 211)。
- **反例/失败场景**:
  1. 当前 `HostFinalAnswerView.__post_init__` 检查 `isinstance(self.content, str)` 但不检查 `content.strip() == ""`。
  2. Engine `_final_answer_plan` (engine_ingest.py:4893) 已拒绝对空白 content 产生成功 terminal。但 descriptor payload 中的 content 可能被外部破坏。
  3. Outbox `_final_answer_from_outbox_json` (read_api.py:848-849) 检查 `isinstance(content, str)` 但不检查空白。
- **为什么有问题**: 防御深度不完整。plan 说明意图但未指出具体在哪几个 site 添加 blank check。
- **直接证据**: `read_api.py:848-849` — `if not isinstance(content, str): raise ...` — 允许 `content = "   "`
- **影响**: implementation agent 可能只在 `HostFinalAnswerView.__post_init__` 加检查，而漏掉 `_final_answer_from_outbox_json`。
- **建议改法和验证点**: plan exact changes 应列明 `HostFinalAnswerView.__post_init__` 和 `_final_answer_from_outbox_json` 都需要加 blank check。
- **修复风险（低）**
- **严重程度（低）**

---

### F-07 — INFO — plan §10 允许 `dayu/host/terminal_payload.py` 的修改仅用于澄清 docstring/语义；若无需修改则不触碰。当前 docstring 已充分说明 intended usage，修改可能不需要

- **位置**: plan §10 allowed production files (line 332)
- **问题类型**: 范围漂移
- **当前写法**: "`dayu/host/terminal_payload.py`，仅用于澄清 `PayloadTextReadPolicy` docstring/语义；若无需修改则不触碰"
- **反例/失败场景**: terminal_payload.py 当前 docstring (lines 1-8) 已明确说明 `content` 只是 continuity fallback、不属于 compact fact。`PayloadTextReadPolicy` 的 docstring (lines 22-30) 已区分 STRICT vs LENIENT。若 implementation agent 找不到 "需要澄清" 的点，可能会做无意义改动。
- **为什么有问题**: 允许修改项给了不必要的灵活度；plan 可以更果断地声明该文件无需修改。
- **直接证据**: terminal_payload.py docstring 已充分说明语义
- **影响**: 极低，可能浪费少量实现时间。
- **建议改法和验证点**: 建议改为 "`dayu/host/terminal_payload.py` 无需修改，当前 docstring 已充分"。
- **修复风险（低）**
- **严重程度（信息）** — 不阻塞

---

## Architecture boundary review

### AB-01 — 通过 (resolver 不反向耦合 memory consumer)

plan §5.4 明确 memory consumer 只消费 typed material，不反向打开 descriptor。`memory.py` lenient inline fallback 保留但限于 descriptor-blind 范围。正确。

### AB-02 — 通过 (Outbox 不新增 PayloadStore 依赖类型边界)

Outbox 通过已存在的 `HostTransaction` + resolver 访问 descriptor，解析语义集中在 `_terminal_answer.py`。Outbox 不直接 import `payload_resolution` 或 `sqlite_payload_object`。正确。

### AB-03 — 通过 (read API 不再持有第二套 descriptor parser)

删除 `_terminal_payload_object` / `_sqlite_payload_object` 后将消除重复实现。确认无其他调用方。正确。

---

## Best-practice / Overengineering / Overcoupling review

### BP-01 — 通过 (单一 slice 是最小可维护方案)

plan §10 论证了 1 个 slice 的合理性：修改量围绕同一 terminal-answer projection contract。若拆成 3 个 slice 会产生 contract-only 半成品 (resolver 已有但 Outbox 仍丢 answer；public succeeded 必填但 producer 仍写 NULL)。符合 control doc 的 slice 原则。

### OE-01 — 通过 (required resolver 是薄包装，非 God builder)

plan §5.1 明确禁止 `HostFinalAnswerView` god builder、resolver registry、callback/factory/profile。`required_assistant_final_answer_continuity_text` 只是带 throw 的薄包装，不引入新抽象层。正确。

### OC-01 — 通过 (不新增跨层回调)

plan 只用 `HostTransaction` + payload dict 传参，不引入 callback seam、lazy import 或 payload loader。符合 CLAUDE.md 编码硬约束。

---

## Scope / non-goals boundary verification

### SG-01 — 通过

plan §12 non-goals 明确不触碰 P3-C (compact/evidence contract)、P3-J (schema/DDL hardening)、UI/CLI、terminal EventLog schema、Run/Attempt 状态机、Outbox DDL/version。allowed files §10 不包含 P3-C/P3-J 相关文件 (如 `compact_material.py` production code change)。正确。

### SG-02 — 通过

plan 不修改 `dayu/host/durable/memory.py` production code (仅 regression test)，不修改 `memory.py`。正确。

### SG-03 — README 触发审查

plan §11 的 README 决策：
- `dayu/host/README.md` 应更新 — 正确。当前 Outbox section (line 687-691) 未声明 succeeded item 的 final answer 必须从同一 resolver 派生。
- `tests/README.md` 预计无需更新 — 需要实现后确认 (若新增独立测试层/命令职责则需要)。
- 根 `README.md`、`dayu/README.md`、design docs 不更新 — 正确。

---

## Open questions

1. **OQ-01**: inline `final_answer` 作为 "当前设计真源" 的声明与代码事实矛盾 (见 F-01)，是否需要 plan 澄清其实际使用范围 (仅测试)，或从 resolver 中移除 inline 路径？

2. **OQ-02**: `read_api._succeeded_host_event` 切换为 required resolver 后，其当前对 `terminal_summary_ref/digest` 的 `_required_payload_text` 校验被后移到 resolver。这一重构等价性能否在 plan 中显式确认而非留待 implementation agent 自己发现？

3. **OQ-03**: `_final_answer_json` 改为调 required resolver 后，`filtered`/`degraded`/`finish_reason` 仍从规范 payload 读取。但规范 payload 中 `finish_reason` 是 `request.finish_reason` 而 terminal descriptor payload 中 `finish_reason` 是 `data.finish_reason.value` — 它们来自同一 `_EngineTerminalPlan.finish_reason` (engine_ingest.py:4922)。这一同源性能否在 propagation audit 中显式记录？

---

## Residual risks and suggested tracking

| Risk | Severity | Suggested owner | Notes |
|---|---|---|---|
| Inline `final_answer` 路径是测试专用的 dead code 路径 (production-wise)，若不解清可能误导后续维护者 | Low | P3-B implementation agent 在 handoff 中说明 | plan 澄清后消除 |
| Retry 测试 "恢复" 方法欠规格导致测试绕过 durable contract | Low-Medium | P3-B implementation / review | plan 澄清测试方法后消除 |
| Required resolver error messages 不够具体导致排障困难 | Low | P3-B implementation | 添加 error message 区分逻辑后消除 |
| SQLite DDL 无 conditional CHECK —— 由 P3-J 承接 | Known | P3-J | plan §12 residual risks 已记录 |

---

## Finding disposition summary

| # | Severity | Status | Summary |
|---|---|---|---|
| F-01 | MEDIUM | accepted-candidate | Inline `final_answer` provenance is undefined |
| F-02 | MEDIUM | accepted-candidate | "恢复同 ref/同 digest descriptor" test mechanism underspecified |
| F-03 | MEDIUM | accepted-candidate | Required resolver error messages don't distinguish root causes |
| F-04 | LOW | accepted-candidate | `_succeeded_host_event` ref/digest check migration equivalence unconfirmed |
| F-05 | LOW | accepted-candidate | `_validate_outbox_terminal_payload` exact change site unspecified |
| F-06 | LOW | accepted-candidate | `HostFinalAnswerView.content` blank check sites not enumerated |
| F-07 | INFO | needs-evidence | `terminal_payload.py` may not need changes |

**No rejected concerns. No needs-more-evidence (beyond F-07 which is informational).**

---

## Final plan review conclusion

**Verdict: `pass-with-risks`**

**Blocking questions: 0.**

**Rationale**: plan 达到了 code-generation-ready 标准：owner boundary 清楚、API shape 固定、transaction semantics 描述正确、failure matrix 完整、allowed files 受控、stop conditions 具体、README 决策合理。6 个 material findings 均不阻塞实施 — 它们主要是文档澄清、测试规格精化、错误消息区分度等低风险问题，可在 plan fix 或 implementation 阶段解决，无需重新设计。

唯一结构性风险 (F-01，inline `final_answer` 的 provenance) 不影响实现正确性，但需要在 handoff 时明确：若 inline 路径无 production 用途，在 future WU 中应按 CLAUDE.md "禁止兼容性代码" 评估是否移除。

**Finding count**: 7 (6 accepted-candidate + 1 informational)

**Artifact**: `docs/reviews/wu-semantic-ownership-01-p3-b-plan-review-ds.md`
