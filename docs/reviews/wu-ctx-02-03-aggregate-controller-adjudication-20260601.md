# WU-CTX-02 + WU-CTX-03 aggregate deepreview controller adjudication

## 裁决结论

WU-CTX-02 + WU-CTX-03 aggregate deepreview 通过，结论为 **Accepted**。本 work unit 可进入
`ready-to-open-draft-PR`。

两份独立 aggregate review 均审查 `9d89db3..0dcb648` 的全部 Slice A-E 变更，并给出
Accepted / no blocking findings。reviewers 报告的验证结果一致：

- `python -m pyright dayu/ tests/ utils/` -> 0 errors, 0 warnings, 0 informations
- 受影响测试集合 -> 249 passed

## 输入证据

- Aggregate review:
  - `docs/reviews/wu-ctx-02-03-aggregate-deepreview-mimo-20260601.md`
  - `docs/reviews/wu-ctx-02-03-aggregate-deepreview-ds-20260601.md`
- Design source:
  - `docs/host/design.md`
- Plan source:
  - `docs/host/wu-ctx-02-03-compact-failure-overflow-plan.md`
- Control doc:
  - `docs/host/host-core-followup-implementation-control.md`

## Findings 裁决

### AGG-F1: `_FALLBACK_ACTION_NOT_APPLICABLE` 三处私有常量重复

- Reviewer severity: Info
- Controller decision: **Deferred with owner**
- Owner / destination: `WU-LAYER-02` shared helper consolidation
- 裁决理由：当前三处值完全一致，且只作为模块私有默认值使用，不影响 `CONTEXT_COMPACTION_FAILED`
  payload correctness；在当前 work unit 收敛它会引入无关重构。后续若做层中立 helper / Host internal constant 清理，
  再把 `not_applicable` 与其它 fallback action 常量收敛到同一 owner。
- Tracking: 保持 `RR-CTX-SLICED-01` 为 `deferred-with-owner`，owner 调整为 `WU-LAYER-02`。

### AGG-F2: `hard_threshold_before_dispatch` 无前置 `CONTEXT_COMPACTION_REQUESTED`

- Reviewer severity: Info
- Controller decision: **Accepted as intentional behavior / no fix**
- 裁决理由：该路径是 pre-dispatch hard budget estimate 直接拒绝，不是已经启动的 compaction operation。
  它写入 `CONTEXT_COMPACTION_FAILED` 是为了记录 Host context governance failure 与 fallback decision，而不是声明存在一个
  upstream compaction request。当前 payload 通过 `failure_reason` 和 synthetic `operation_id` 明确区分该场景，满足
  design doc 的 durable diagnostic 要求。
- Tracking: 不新增 residual risk；若未来设计真源新增 “failed 必须引用 requested” 的 EventLog invariant，再单独调整。

### AGG-F3: `_reactive_fallback_decision` broad `except Exception`

- Reviewer severity: Info
- Controller decision: **Accepted as current fail-closed boundary / no fix**
- 裁决理由：fallback selection / budget estimate 是 recovery 末端兜底路径；异常时 fail closed 比让 Run 卡在
  recovery 中更符合 Host 强治理目标。当前实现已用 `exc_info=True` 记录异常，且返回结构化 selection failure payload。
  在当前 work unit 缩窄异常类型可能降低未知异常的 fail-closed 保证。
- Tracking: 不阻塞 ready-to-open-draft-PR；未来若 Host ingest hardening 专门收紧异常 taxonomy，再评估。

### RR-CTX-SLICEB-01: reactive precondition failure 集成覆盖

- Controller decision: **Closed**
- 裁决理由：aggregate review 的直接代码证据显示 `context_budget_policy_missing`、`input_event_missing`、
  `reactive_compact_count_unreadable` 与 `reactive_compact_limit_reached` 均走
  `_fail_reactive_recovery_without_request`，该 helper 关闭旧 Attempt，写完整
  `CONTEXT_COMPACTION_FAILED` diagnostic payload，再用 `RUN_FAILED` fail closed，不进入 fallback dispatch 或 `RUN_LOST`。
  为 `input_event_missing` 构造端到端测试需要破坏 durable invariant，当前不应为了覆盖率制造脆弱测试。
- Tracking: 在总控文档中关闭 `RR-CTX-SLICEB-01`。

## Design / Plan 对齐裁决

- Fallback 不是 compact success：实现不写 `CONTEXT_COMPACTED`，不写 compact artifact，不投影 memory stable facts。
- Host 保持 governance owner：fallback selection、budget re-estimate、EventLog failed payload、recovery Attempt 创建和
  fail-closed 均在 Host 内完成；Engine 只报告 overflow。
- Proactive 与 reactive 两条路径都写 `CONTEXT_COMPACTION_FAILED` diagnostic，并在 fallback budget pass 时才 dispatch。
- 连续 reactive overflow 通过 `max_reactive_compactions_per_run` 上限收口，最终 `RUN_FAILED`，不写 `RUN_LOST`。
- 测试覆盖 plan success signals，且 repeated overflow 测试使用 `asyncio.Condition` 同步，不依赖不可控 sleep。

## Controller 验证要求

本裁决后 controller 需要重复运行 aggregate 验证命令：

- `source .venv/bin/activate && pytest tests/host/test_context_policy.py tests/runtime/test_config_loader.py tests/runtime/test_scene_assets_migration.py tests/service/test_host_assembly.py tests/host/test_context_compact_events.py tests/host/test_run_input_builder.py tests/host/test_engine_ingest_mapping.py tests/host/test_dispatch_scheduler.py -q`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`

验证通过后，创建 accepted aggregate deepreview commit，并更新总控文档到 `ready-to-open-draft-PR`。
