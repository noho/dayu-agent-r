# P8.5 Plan Amendment Re-Review Artifact

- **re-review gate name**: plan amendment re-review
- **reviewed target**: `docs/host/phase8.5-plan.md` (post-amendment)
- **amendment report**: `docs/host/phase8.5-plan-amendment-report.md`
- **previous plan re-review**: `docs/host/phase8.5-plan-rereview.md`
- **re-reviewer**: plan amendment re-review agent (Claude)
- **re-review date**: 2026-05-11
- **re-reviewer conclusion**: **pass**
- **artifact path**: `docs/host/phase8.5-plan-amendment-rereview.md`

## Scope Reviewed

本次 re-review 只检查 amendment 引入的变更，不重新完整 review P8.5 plan。检查范围：

1. 原 Slice 1 / Slice 2 是否已正确合并为 `Slice 1 — ToolRuntime generic fetch_more event model`。
2. 合并后的 Slice 1 是否仍 handoff-ready / code-generation-ready。
3. 合并后的 Slice 1 是否过粗到不可 review。
4. 后续 slice 编号是否一致。
5. review gates、validation commands、residual risk owner 中是否仍残留旧引用。
6. amendment 是否引入新的 blocking open question、scope drift 或与此前 re-review pass 的核心契约冲突。

## Per-Scope Verification

### 1. Slice 1/2 合并正确性

**判定: pass**

amendment report 的合并理由成立：原 Slice 1 单独删除 `TOOL_FETCH_MORE_*` / `ToolFetchMore*Data` 会立即打断 `_tool_runtime.py`、serializer、memory projection、tool trace projection 和相关测试。合并避免了不可运行中间态。

合并后的 `Slice 1 — ToolRuntime generic fetch_more event model` implementation prompt 包含 20 个目标点，完整覆盖原 Slice 1 和 Slice 2 的全部内容：

| 原 slice | 合并后对应目标点 |
| --- | --- |
| Slice 1 contract deletion (1-4) | 目标 1-4 |
| Slice 1 keep framework tool (5-6) | 目标 5-6 |
| Slice 2 runtime migration (1-3) | 目标 7-9 |
| Slice 2 cursor fact reshape (4-5) | 目标 10-12 |
| Slice 2 projection fix (6) | 目标 13-14 |
| Slice 1 test update (7) | 目标 15-16 |
| Slice 2 regression test (7-8) | 目标 17-18 |
| Slice 2 guard test (9) | 目标 19 |
| Slice 1 fresh schema (8) | 目标 20 |

### 2. 合并后 Slice 1 handoff-ready 验证

**判定: pass**

合并后的 implementation prompt 是完整的 contract migration slice，明确要求"完成后必须让 pyright 与 affected tests 可通过；不允许临时 compatibility reader、wrapper、re-export、bridge event"。逐项验证：

- **contract deletion**: 目标 1-4 覆盖 `RunEventType`、data classes、union members、serializer、`__init__.py` exports。
- **runtime migration**: 目标 7-9 覆盖 `_tool_runtime.py` 删除专属 append 方法、`HostToolRuntime` routing 保持、generic tool-call facts 作为真源。
- **serializer / public surface**: 目标 4、15 覆盖。
- **memory projection**: 目标 13 明确删除 `tool_name="unknown"` 伪表达。
- **tool trace projection**: 目标 14 明确用 generic tool-call facts + mechanism facts 生成 trace。
- **cursor mechanism facts**: 目标 10-12 覆盖 `owner_tool_call_id` / `emitting_tool_call_id` reshape。
- **append failure test**: 目标 17-18 覆盖 stop condition。
- **grep guard**: 验收条件包含 `rg` 命令和 expected results。
- **affected tests / pyright**: 目标 15-16、19 覆盖；implementation prompt 末尾要求"运行受影响 tests、grep guards 和 pyright"。

### 3. Slice 1 粒度评估

**判定: pass（合理）**

20 个目标点数量较多，但粒度合理：
- 所有目标点都是同一个 contract migration 的必要组成部分，拆分会导致不可运行中间态。
- 目标点按逻辑分组：contract (1-6) → runtime (7-12) → projection (13-14) → tests (15-19) → schema (20)。
- 每个目标点都是具体、可验证的代码变更指令，不是模糊的设计描述。
- 合并后的禁止清单明确约束了边界（不实现 append_many、不提前 P10、不恢复 legacy handle、不放入 dayu.runtime、不新增 compatibility 层）。

### 4. 后续 slice 编号一致性

**判定: pass**

amendment 后的 slice 编号完整一致：

| 编号 | 标题 | 原编号 |
| --- | --- | --- |
| Slice 1 | ToolRuntime generic fetch_more event model | 原 Slice 1 + 2 |
| Slice 2 | Durable memory repair stabilization | 原 Slice 3 |
| Slice 3 | Tool trace observer I/O boundary | 原 Slice 4 |
| Slice 4 | Compact / RunInput payload / semantic cleanup | 原 Slice 5 |
| Slice 5 | SSE partial tool-call trace diagnostic | 原 Slice 6 |
| Slice 6a | Attempt lease contract hardening | 原 Slice 7a |
| Slice 6b | Attempt adversarial coverage | 原 Slice 7b |
| Slice 7 | Docs, migration notes, final validation | 原 Slice 8 |

每个 slice 的 implementation prompt 中的 `前置：` 引用、禁止清单中的 cross-slice 引用、以及 `完成后` 指令均使用新编号，无错位。

### 5. 残留旧引用检查

**判定: pass**

- `rg "Slice 1-2|Slice 7a|Slice 7b|Slice 8" docs/host/phase8.5-plan.md`：零命中。
- §9 Review Gates：Contract gate 新增注释明确"该 gate 与 ToolRuntime / Projection gate 同属 Slice 1，必须在同一 slice review 中一起验证"。Attempt gate 引用 `Slice 6a` / `Slice 6b`。无旧编号。
- §10 Validation Commands：明确标注"Slice 1 必须把 contract、serializer、ToolRuntime、memory projection、tool trace projection 与 public surface 相关测试作为同一组运行"。无旧编号。
- §11 Residual Risk Owner Changes：`fetch_more concrete RunEventType` 的关闭 owner 为 `Slice 1`；attempt lease 为 `Slice 6a` / `Slice 6b`。无旧编号。
- §14 Implementation Completion Report Format：`前置：Slice 1-6b 已完成`（原为 `Slice 1-7b`）。无旧编号。

### 6. 新 blocking open question / scope drift / 契约冲突检查

**判定: pass**

- **新 blocking open question**: 无。amendment 未引入新的架构裁决或设计选择。
- **scope drift**: 无。合并仅改变 slice 粒度，不改变 P8.5 的 goal、non-goals、authoritative decisions 或 affected files。
- **与 re-review pass 核心契约冲突**: 无。此前 re-review 验证的 8 个 findings (F01-F08) 的修复内容在 amendment 后的 plan 中完整保留：
  - F01 (test paths): 目标 15 引用正确路径。
  - F02 (side store ownership): §2.4 point 3 和 §7 未变。
  - F03 (SSE partial diagnostic): Slice 5 未变。
  - F04 (fetch helper): Slice 2 未变。
  - F05 (Slice 7 粒度): 拆为 6a/6b，内容未变。
  - F06 (append_many stop condition): 目标 17-18 保留。
  - F07 (corrupt snapshot): Slice 2 保留。
  - F08 (fresh schema): 目标 20 保留。

## Findings

无 amendment 引入或未修正的问题。

## Remaining Open Questions / Residual Risk

与此前 re-review artifact (`docs/host/phase8.5-plan-rereview.md`) 一致，无新增：

| Risk | Owner | Status |
| --- | --- | --- |
| observer claim lease / outbox / hard-gate | P15 / issue #28 | Explicitly not P8.5 |
| `InMemoryRunEventStore` 生产语义收口 | P16 interface freeze | Deferred |
| schema bootstrap 半失败治理 | P15 | Deferred |
| `LocalRunHarness` God Object 膨胀 | P9 / P16 | Deferred |
| `DurableHarnessBundle` public/internal 边界 | P16 | Deferred |
| P15 required projection enforcement | P15 | Deferred |
| `HostStorage.close()` 后台 task 生命周期 | P9 lifecycle | Deferred |

## Conclusion

amendment 正确地将原 Slice 1 和 Slice 2 合并为单个纵向 contract migration slice，避免了不可运行中间态。合并后的 Slice 1 仍 handoff-ready，20 个目标点完整覆盖原两个 slice 的全部内容。后续 slice 编号顺延一致，review gates / validation commands / residual risk owner 中无残留旧引用。amendment 未引入新 blocking open question、scope drift 或与此前 re-review pass 的核心契约冲突。

**re-review 结论：pass**。plan 可回到 user confirmation / accepted plan commit。
