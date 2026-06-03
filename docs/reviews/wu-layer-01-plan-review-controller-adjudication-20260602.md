# WU-LAYER-01 Plan Review Controller Adjudication

- Gate: plan review adjudication
- Date: 2026-06-02
- Work unit: WU-LAYER-01 Durable Row Primitive / Type Owner Cleanup
- Plan artifact: `docs/host/wu-layer-01-durable-row-primitive-cleanup-plan.md`
- Review artifacts:
  - `docs/reviews/wu-layer-01-plan-review-mimo-20260602.md`
  - `docs/reviews/wu-layer-01-plan-review-ds-20260602.md`

## 结论

接受 plan review 的非阻塞修订要求，进入 plan fix gate。两份 review 均判定 plan code-generation-ready 且无 blocking finding；但 medium findings 都指向 implementation 前应补齐的计划精度，必须先修 plan 再进入 re-review。

## 裁决

### ADJ-01 accepted: schema definition validation 与 DDL CHECK 重组的 slice dependency

- 来源: AgentDS FIND-01；AgentMiMo M-01 相关。
- 裁决: accepted。
- 理由: 基于设计真源中 Host durable facts 可恢复与强约束目标，schema definition validation 必须与当前 `HOST_DURABLE_DDL` 同源；如果 Slice 2 改写 DDL CHECK 生成方式，plan 必须要求重新运行 Slice 1 definition validation tests，避免中间 slice 引入 false fail 或定义漂移。
- plan fix 要求: 在 Slice 2 dependency / expected assertions 中明确，Slice 2 修改 DDL CHECK 片段后必须重跑 Slice 1 schema definition validation tests；若生成 SQL 文本变化，必须证明 fresh bootstrap 与 expected SQL 同源且 opener 不误报。

### ADJ-02 accepted: WaitRecord corrupted CAS scenario test

- 来源: AgentDS FIND-02；AgentMiMo residual risk 3 相关。
- 裁决: accepted。
- 理由: `terminal_at IS NULL` CAS 谓词的唯一语义差异是 corrupted `status=waiting` 且 `terminal_at IS NOT NULL` row 被 fail-closed 排除；按第一性原理，行为差异必须有直接测试，不能只写 residual risk。
- plan fix 要求: 在 Slice 2 tests 中显式加入 corrupted wait record scenario，断言 CAS 被拒绝并分类为 CAS lost 或 invalid state；构造方式必须限定为 test-only，不进入生产 repair 逻辑。

### ADJ-03 accepted: `_row_rules.py` 与 `_validation.py` 职责边界

- 来源: AgentDS FIND-03；AgentMiMo M-02 相关。
- 裁决: accepted。
- 理由: Host durable helper 必须有清晰 owner，避免把 terminal state-machine 规则混入 scalar validation，也避免未来被 runtime/helper consolidation 误迁移。
- plan fix 要求: 补充 `_row_rules.py` 只承载 terminal status constants、terminal refs SQL fragments、terminal shape validation；`_validation.py` 只承载 durable scalar validation。明确 `_row_rules.py` 不在 `dayu/host/durable/__init__.py` re-export。

### ADJ-04 accepted: row decode `KeyError` wrapping

- 来源: AgentDS FIND-04；AgentMiMo L-01 相关。
- 裁决: accepted。
- 理由: WU-LAYER-01 验收信号要求 row decode 失败有稳定错误类型；缺列从 `HostRow.get()` 泄漏 `KeyError` 是 root cause 证据，plan 必须要求 decode helper 显式包装该路径。
- plan fix 要求: 在 Slice 3 implementation decisions 中明确 `_decode_*` helper 捕获 `KeyError` 与 scalar helper 的 `HostDurableError`，统一转换为 `HostRowDecodeError`，并保留 `row_name` / `field_name`。

### ADJ-05 accepted: schema SQL normalization minimal spec

- 来源: AgentDS FIND-05；AgentMiMo M-01 / open question 1 相关。
- 裁决: accepted。
- 理由: definition validation 必须可测试且可维护；“whitespace normalization only”需要最小明确语义，避免 implementation agent 自行发明更宽的 SQL parser。
- plan fix 要求: 明确 normalization 只做首尾空白去除、连续空白归一为单个空格、保持大小写与标识符引用不变；若当前 SQLite 输出证明还需要更宽规则，停止并回报 controller。

### ADJ-06 rejected as non-blocking: add generic `_decode_enum`

- 来源: AgentMiMo open question 2。
- 裁决: rejected as implementation preference。
- 理由: Plan 已要求只有在不引入 `Any` / `object` 时才考虑 `_decode_enum`；最佳实践是让 implementation agent 优先直接调用现有 typed enum deserializer 并包装错误，不需要为偏好修改 plan。

### ADJ-07 deferred-within-implementation: baseline transition tests before Slice 2

- 来源: AgentMiMo L-02。
- 裁决: deferred-within-implementation。
- 理由: 这是实施顺序验证要求，不阻塞 plan fix；plan 已列 final validation，Slice 2 implementation report 必须记录是否运行 transition baseline 或为何无需修改 transition tests。

## 下一步

派发 planning fix 给 AgentCodex，只允许修改 plan artifact，补齐 ADJ-01 到 ADJ-05。修订完成后进入 plan re-review，reviewers 复核 accepted findings 是否关闭。
