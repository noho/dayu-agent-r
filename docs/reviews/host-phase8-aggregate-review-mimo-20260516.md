# Code Review

## Scope

- Mode: current changes (aggregate)
- Branch: `feat/host-phase8-projection-core-event-stream`
- Base: `main`
- HEAD: `8b538f5`
- Output file: `docs/reviews/host-phase8-aggregate-review-mimo-20260516.md`
- Included scope: 全部 Phase 8 slice commits (S1–S3) 通过 HEAD `8b538f5`，包含 projection core、checkpoint/failure durable store、typed consumer contract、ProjectionRunner、minimal RunResult/Session timeline read model、repair helper、import boundary tests、public event stream boundary tests。
- Excluded scope: `dayu/runtime`、`dayu/engine`、`dayu/service`、`dayu/ui`、`dayu/fins`；plan/review artifact 内容本身。
- Parallel review coverage: 无（单 reviewer 直接走读）。

## Verdict

**PASS（附 1 项中等 severity finding）**

Phase 8 实现正确落地了 committed EventLog consumer framework、projection checkpoint/failure durable store、typed consumer contract、ProjectionRunner、minimal RunResult/Session timeline read model 和可重建 repair path。架构边界、import 约束、schema 不变量、public read boundary 和 test coverage 均满足 plan 和 design doc 要求。

## Findings

### 001-未修复-[中]-Schema 版本从 4 直接跳到 6，跳过 plan 规定的版本 5

- **入口/函数**: `dayu/host/durable/schema.py:24` `HOST_SCHEMA_VERSION = 6`
- **文件(行号)**: `dayu/host/durable/schema.py:24`
- **输入场景**: fresh DB bootstrap 时 `bootstrap_host_durable_store()` 读取 `PRAGMA user_version`
- **实际分支**: `current_version not in (0, HOST_SCHEMA_VERSION)` 即 `not in (0, 6)`
- **预期行为**: `docs/host/phase8-projection-core-event-stream-plan.md` §3 明确要求 "Phase 8 implementation 必须将 fresh schema version bump 到 5"。Plan 未授权跳到 6。
- **实际行为**: `HOST_SCHEMA_VERSION` 从 4 直接跳到 6。
- **直接证据**: `schema.py:24` → `HOST_SCHEMA_VERSION = 6`；plan §3 → "必须将 fresh schema version bump 到 `5`"。Branch diff 中无其他独立 schema 变更可解释跳过 5 的原因。
- **影响**: 与 plan 规范不一致；若其他独立工作线在 4→5 之间有未合并的 schema 变更，当前跳号会导致版本冲突或混淆。若无其他变更，则是纯粹的规范违反。
- **建议改法和验证点**: 确认是否存在独立的 schema 5 变更。若不存在，将 `HOST_SCHEMA_VERSION` 改回 5；若存在（已 merge 或即将 merge），在 plan artifact 中记录版本号调整理由。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

## Open Questions

- 无。Schema 版本跳号的根因可通过 git log 确认，不阻塞 review 判断。

## Residual Risk

1. **ProjectionRunner 单行失败中断批次**: `ProjectionRunner.run_once()` 在 consumer apply 失败时 `break` 退出循环（`projection.py:375`）。这是有意设计（plan §2.2 "异常时记录 projection-local failure 并停止当前批次"），但意味着一个坏 event 会阻止后续所有 event 被消费，直到 failure 被手动清除或 repair。Phase 9 Memory 接入后需评估是否有自动 retry 机制需求。
2. **Repair 不幂等保护中间批次失败**: `repair_minimal_read_models()` 的 `reset_checkpoint=True` 路径先清空再全量 replay。若 replay 中途 failure，已 replay 的 rows 已写入但 checkpoint 未到尾部。再次调用 `reset_checkpoint=False` 可从断点继续，但调用方需理解这个语义。当前测试覆盖了该场景。
3. **Concurrent consumer access**: 未测试多个 ProjectionRunner 实例同时消费同一 consumer_id 的行为。SQLite WAL mode 下 `run_write` 的串行化保证了正确性，但缺少 explicit 并发测试。
4. **Documentation sync**: `dayu/host/README.md` 已更新 Phase 8 条目，`tests/README.md` 已更新测试覆盖描述。`dayu/README.md`（架构总览）未发现需要更新的分层关系变化。无遗漏。
