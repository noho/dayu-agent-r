# WU-AUDIT-01 Purge Audit Reconciliation Plan Re-review

- **Re-reviewed target**: `docs/host/wu-audit-01-purge-audit-reconciliation-plan.md`（更新版）
- **Previous review**: `docs/reviews/wu-audit-01-plan-review-ds-20260531.md`
- **Re-review date**: 2026-05-31
- **Re-review scope**: 验证第一轮 review 的 4 个 findings 是否已关闭，确认未重新引入过度设计

## Previous Findings Re-check

### Finding 01（中）— Retry 后 completed append 的检测机制未具体化

**状态：CLOSED**

证据：

1. Section 4 新增 "retry / replay 规则"（lines 176-181）：
   - `purge_session_durable(...)` 返回 `idempotent_replay is True` 时，command path **必须无条件**尝试 append `purge_completed`。
   - 不读取、不扫描 JSONL 来判断 completed 是否已存在；只依赖 `_append_audit_json_line` 的 source key `(line_kind, purge_attempt_ref)` 幂等去重。
   - 同 key retry 可以再次构造 deterministic started line；若 started 已存在，append helper 通过同 source key / same digest 幂等跳过。
   - 同 key retry 在 tombstone replay 后仍尝试 completed append；如果 completed 已存在则幂等跳过；如果上次失败则本次补写。

2. Section 5.3 line 261 明确要求："`PurgeSessionDeleteResult.idempotent_replay is True` 时仍无条件调用 `append_purge_completed_audit_record(...)`，不扫描 JSONL。"

3. Section 6 Slice 3 验收信号（line 328）："completed append 失败后同 key retry 最终只有一条 completed。"

4. Section 7.4 新增完整的测试段落 "completed append 失败后 retry 幂等补写"，包含：
   - 第一次 purge：completed append 注入失败 → retryable error。
   - 第二次同 key retry：tombstone replay → 无条件尝试 completed append → JSONL 幂等去重。
   - 断言生产代码不扫描 JSONL。

机制已经完全具体化，implementation agent 可以直接按此实现。

### Finding 02（低）— Command path 直接写 audit 与设计真源的 tension 未显式声明

**状态：CLOSED**

证据：

1. Section 2.2 新增显式例外声明（lines 71-72）：
   > purge command path 直接写 JSONL 是 purge 专用例外：目标 Session 的 EventLog 会被 purge 删除，无法依赖常规 EventLog audit projection 在事后生成 destructive purge 流水。该例外不得扩散成通用 command path 直接写 audit 模式；普通 Host command 仍应通过 committed EventLog facts 驱动 audit projection。

   这段声明准确解释了为什么 purge 是例外（EventLog 被删除，projection 无法事后生成），并明确划定了边界（不得扩散）。

2. Section 9 docstring 清单（line 425-426）要求 command.py docstring 同步说明："direct JSONL write 仅为 purge 专用例外，原因是目标 EventLog 将被删除，不得扩散为通用 command audit 模式。"

架构 tension 已被显式记录并有防止扩散的护栏。

### Finding 03（低）— `purge_failed` line 与 started line 在重试时的幂等交互未完全覆盖

**状态：CLOSED**

证据：

1. Section 2.2 新增 builder 字段派生规则（line 69）：
   > `schema_version`、`line_kind`、`audit_record_ref`、`line_digest` 必须由 builder 生成，调用方不得传入。`purge_attempt_ref` 必须由 builder 使用 `tombstone_id` 派生，调用方不得直接传入，避免上层传入不一致 ref。

2. Section 2.3 新增 deterministic 约束（line 87）：
   > 字段必须完全 deterministic，不包含 timestamp、random id、进程 id 或其它会随 retry 变化的值，保证同一 `session_id`、`client_request_id`、semantic digest retry 时 started line digest 稳定，并依赖 `(line_kind, purge_attempt_ref)` 幂等去重。

3. Section 5.2 新增 request dataclass 显式字段列表（lines 208-234）：
   - `PurgeStartedAuditRecordRequest` 字段列表完全不包含 timestamp、random id、进程 id 等非确定值。
   - 不包含 `schema_version`、`line_kind`、`audit_record_ref`、`purge_attempt_ref`、`line_digest`（这些由 builder 派生）。

4. Section 4 retry/replay 规则（line 180）覆盖了 started 去重场景："同 key retry 可以再次构造 deterministic started line；若 started 已存在，append helper 通过同 source key / same digest 幂等跳过，不产生重复 line。"

5. Section 7.1 测试新增断言（line 339）："同 key retry 再次尝试 append deterministic started line 后，JSONL 中仍只有一条 started line。"

started line 的 deterministic 属性有显式约束，request dataclass 字段排除了非确定来源，幂等交互有具体规则和测试覆盖。

### Finding 04（低）— docstring 更新范围不够明确

**状态：CLOSED**

证据：

Section 9 新增显式 docstring 更新清单（lines 417-426），列出了 7 个具体位置：

1. `dayu/host/durable/purge.py` 模块 docstring — 说明 durable purge 不直接写 JSONL，started/completed 编排在 purge command path，且这是 purge 专用例外。
2. `PurgeTombstoneRow` docstring — 说明 `audit_record_ref`/`audit_record_digest` 指向 `purge_started` audit line。
3. `PurgeSessionDeleteRequest` docstring — 说明接收 started audit ref/digest，不接收 audit recorder。
4. `PurgeSessionDeleteResult` docstring — 说明 `idempotent_replay=True` 时 command path 仍需尝试 completed audit append。
5. `build_purge_tombstone_digest` docstring — 列明 digest 覆盖全部已持久 tombstone 字段，包含 started audit ref/digest，不包含 completed line。
6. `dayu/host/audit.py` purge audit request/result dataclass 与 builder/append 函数 docstring — 说明哪些字段由 request 提供，哪些字段由 builder 派生。
7. `dayu/host/command.py` `purge_session` docstring — 说明 direct JSONL write 仅为 purge 专用例外。

每条都有明确的更新内容说明，implementation agent 可以直接按清单逐项执行，review 时有明确检查点。

## 新增内容审查：是否引入过度设计

对 plan 更新部分逐项审查：

| 新增内容 | 位置 | 必要性 | 是否过度 |
|---|---|---|---|
| retry/replay 规则（4 条） | Section 4 lines 176-181 | 关闭 Finding 01，填补 retry 机制空白 | 否 — 精确、可执行、无新抽象 |
| builder 字段派生规则 | Section 2.2 line 69 | 关闭 Finding 03，防止调用方传入不一致派生字段 | 否 — 单行约束，不引入新机制 |
| purge command path 专用例外声明 | Section 2.2 lines 71-72 | 关闭 Finding 02，显式声明架构例外并防止扩散 | 否 — 说明性质，不引入新机制 |
| started deterministic 约束 | Section 2.3 line 87 | 关闭 Finding 03 | 否 — 单行约束 |
| request dataclass 显式字段列表 | Section 5.2 lines 208-234 | 提升 code-generation-readiness | 否 — 具体化已有设计，不是新增功能 |
| `build_purge_tombstone_digest` 字段清单 | Section 3 lines 142-158 | 提升 code-generation-readiness | 否 — 具体化 digest 语义边界 |
| docstring 更新清单（7 项） | Section 9 lines 417-426 | 关闭 Finding 04 | 否 — 实施检查清单 |
| 测试 7.4（completed append 失败 retry） | Section 7.4 lines 370-378 | 验证 retry 机制 | 否 — 新增测试闭合验证缺口 |

**结论：所有新增内容均为对第一轮 findings 的针对性修复或 code-generation-readiness 增强，未引入新抽象、新机制、新层或新的依赖关系。**

## 最终 Plan Review Re-review Conclusion

**PASS**

第一轮 review 的 4 个 findings 全部 CLOSED：

- Finding 01（中）: retry 机制已具体化，实现 Agent 可直接按 Section 4 规则实现，Section 7.4 有对应的测试覆盖。
- Finding 02（低）: purge command path 直接写 JSONL 的专用例外已在 Section 2.2 显式声明，并有关联的 docstring 更新。
- Finding 03（低）: started line deterministic 约束已显式写入 Section 2.3，request dataclass 排除了非确定字段，幂等交互有规则和测试。
- Finding 04（低）: docstring 更新范围已细化为 7 项清单。

无新增 findings。plan 现在满足 code-generation-ready 标准：

- 三个 slices 边界清晰，依赖顺序正确（durable → audit contract → orchestration）。
- 每个 slice 有明确的 allow/forbid 文件变更范围、验收信号。
- Failure paths（started append fail、SQLite fail、completed append fail、retry）均有具体规则和测试覆盖。
- stop conditions 明确，避免 implementation agent 在实施中 scope creep。
