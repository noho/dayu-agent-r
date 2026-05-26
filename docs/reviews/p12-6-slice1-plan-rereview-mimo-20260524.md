# P12.6 Slice 1 Plan Re-review

## Reviewed Target

`docs/host/p12-6-conversation-memory-redesign-implementation-plan.md` Slice 1 plan-fix。

## Gate

Slice 1 plan-fix re-review。本文档不授权实施。

## Scope

验证 accepted finding S1-PF1 是否已修复：首个实现切片是否具备 compile-safe ownership boundary，能删除旧 `CompactionRequest` 字段且不保留 deprecated aliases、compat wrappers、old-field defaults 或 test-only compatibility。

## Assumptions Tested

1. S1-PF1 要求的直接生产消费者全部纳入 Slice 1 allowed files。
2. Slice 1 不引入兼容性过渡路径。
3. Slice 1 完成后旧 `CompactionRequest` 字段在生产代码和测试中彻底消失。
4. 设计目标（§24 / §25）未被削弱。
5. 无范围蔓延：不触碰 Engine / Fins / Service / UI / public API。

## Findings

无 material findings。

### 验证清单

| 检查项 | 结果 | 证据 |
|--------|------|------|
| S1-PF1 列出的 5 个直接生产消费者全部在 Slice 1 allowed files | PASS | plan §8 Slice 1 允许修改文件清单包含 `llm_compaction.py`、`context_governance.py`、`dispatch.py`、`engine_ingest.py`、`compaction_evidence.py` |
| `compaction.py` 自身在 allowed files | PASS | 同上 |
| `compact_artifact.py` 在 allowed files | PASS | `rg` 确认该文件引用旧字段；plan §8 Slice 1 允许修改文件清单已包含 |
| `context_events.py`、`compaction_operation.py` 在 allowed files | PASS | 用于 compile break cleanup，plan §8 已列出 |
| 旧字段 `input_event_refs`、`current_message_summary`、`accepted_evidence_envelopes`、`compact_raw_context_items` 在 Slice 1 明确删除 | PASS | plan §8 Slice 1 "具体修改" 第二条 |
| `CurrentMessageSummary`、`CompactRawContextItem` 从 exported contract 删除 | PASS | plan §8 Slice 1 "具体修改" 第二条 |
| 禁止 deprecated alias / compat wrapper / old-field default / test-only compatibility | PASS | plan §8 Slice 1 "依赖"段、"具体修改"倒数第二条、停止条件 |
| `rg` no-match 验证命令覆盖所有 Slice 1 生产文件 | PASS | plan §8 Slice 1 验证段 `rg` 命令覆盖 `compaction.py`、`compact_material.py`、`compaction_evidence.py`、`llm_compaction.py`、`context_governance.py`、`dispatch.py`、`engine_ingest.py`、`compaction_operation.py`、`conversation_compaction_user.md` |
| 无 EventLog ledger dump 进入 compactor prompt | PASS | plan §1、§3.2、§8 Slice 1 均禁止 |
| 无 `result_preview` 读取 / 生成 / 回退 | PASS | plan §3.2、§6.5、§8 Slice 1 |
| 无 Host provenance key 作为 LLM semantic input | PASS | plan §6.1、§6.2、§8 Slice 1 `llm_compaction.py` 修改要求 |
| 无 public API drift | PASS | plan §5 禁止修改清单；§8 Slice 1 停止条件 |
| 无 Engine / Fins / Service / UI 修改 | PASS | plan §3.2、§7 禁止修改清单 |
| `dispatch.py` / `engine_ingest.py` 在 Slice 1 改为构造新 request shape | PASS | plan §8 Slice 1 "具体修改"第七条 |
| `llm_compaction.py` 在 Slice 1 改为渲染 material pack sections | PASS | plan §8 Slice 1 "具体修改"第八条 |
| `context_governance.py` 在 Slice 1 改为使用 material labels / provenance map | PASS | plan §8 Slice 1 "具体修改"第九条 |
| `compaction_evidence.py` 在 Slice 1 改为 evidence / history material collector | PASS | plan §8 Slice 1 "具体修改"第六条 |
| prompt asset 同步（`conversation_compaction_user.md`） | PASS | plan §8 Slice 1 "具体修改"第十条 |
| 测试覆盖直接消费者构造、governance 校验、prompt asset、旧字段消除 | PASS | plan §8 Slice 1 测试清单 8 项 |
| Slice 依赖图正确：Slice 1 是后续所有 slice 的 contract root | PASS | plan §8.0 依赖图 |

## Open Questions

无。

## Residual Risks

1. **Slice 1 范围扩大**：计划明确承认 Slice 1 比原计划更大，这是 compile-safe contract deletion 的代价。非 blocker，属于已知 tradeoff。
2. **`compact_material.py` vs `compaction_material.py` 文件名**：pyright 命令使用 `compact_material.py`，若实现选择 `compaction_material.py` 需同步替换。plan §8 Slice 1 验证段已说明。
3. **`compact_artifact.py` 旧字段引用**：`rg` 确认该文件存在旧字段引用，但已在 Slice 1 allowed files 中。实现 agent 需确保该文件的旧字段引用一并清除。

## Conclusion

**PASS**

S1-PF1 已修复。Slice 1 现在具备 compile-safe ownership boundary：所有当前直接生产构造 / 消费旧 `CompactionRequest` 字段的文件均已纳入同一 accepted checkpoint，且明确禁止 deprecated aliases、compat wrappers、old-field defaults 和 test-only compatibility。设计目标 §24 / §25 保持完整，无范围蔓延，无 public API drift，无 Engine / Fins / Service / UI 变更。

plan-fix re-review gate 通过，可进入 Slice 1 实施。
