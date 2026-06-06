# WU-CM-01-F04 Plan Re-review — AgentDS

## Verdict

**pass** — 所有 7 项 DS controller accepted findings 均已修复；0 项未修复；0 项部分修复；0 项新引入 blocking issue。

AgentCodex 的 plan fix 完整关闭了原始 DS review 的全部 3 blocking + 4 non-blocking findings，且未引入新问题。Fixed plan artifact 已可移交给 implementation gate。

---

## Accepted Findings Final Status

### DS Finding 1 (BLOCKING) — Slice 4 迁移扫描范围定义不精确

**Status**: 已修复。

**Fix evidence**:
- Plan line 14 成功信号改为 "implementation 前已语义枚举...所有 proactive path 注入 compactor 的使用点...不能只搜索 `context_compactor=FakeContextCompactor()` 字面量"。
- Plan lines 115-156 新增 Slice 0，要求 grep `_RequestCapturingCompactor|_TransactionReadableCompactor|_StaleMutatingCompactor|_RaisingCompactor|_QualityRejectOnceCompactor|context_compactor=|FakeContextCompactor\(` 所有使用点，并按 accepted/rejected/stale-fallback/reactive 分类。
- Plan lines 284-287 Slice 4 重写为 "确认...所有 proactive path compactor injection 都已分类，不限于 `context_compactor=FakeContextCompactor()` 字面量"。

**验证**: 原始 review 指出 Slice 4 文本搜索无法匹配 `_TransactionReadableCompactor(store.transaction_runner)`、`_RaisingCompactor()`、`_QualityRejectOnceCompactor()` 等。Fixed plan 的 Slice 0 grep regex 覆盖了全部 5 个 compactor class 名 + `context_compactor=` 赋值 + `FakeContextCompactor()` 直接注入，且 Slice 0 invariant 明确 "如果 grep 发现清单外还有 proactive accepted/rejected compactor injection，必须归入 Slice 2 或 Slice 3"。已修复。

---

### DS Finding 2 (BLOCKING) — Decision 8 对 `_StaleMutatingCompactor` 过度迁移

**Status**: 已修复。

**Fix evidence**:
- Plan Decision 9 (line 109) 明确 "`_StaleMutatingCompactor` 明确不迁移。该 test 期望 `CONTEXT_COMPACTED` 为 0，Host stale check 在 accepted guard 前收口为 `CONTEXT_COMPACTION_FAILED`，不会触发 accepted manifest ref/digest guard；迁移反而会额外写 proposal manifest event，干扰 stale failure 语义"。
- Slice 0 excluded 清单 (line 149) 列出 stale test 并注明理由。
- Slice 2 line 215 "不迁移 `_StaleMutatingCompactor`"。
- Slice 4 line 286 "明确保留 `_StaleMutatingCompactor` legacy seam，不迁移；其验收信号是 `CONTEXT_COMPACTED == 0` 和 `CONTEXT_COMPACTION_FAILED.failure_reason == 'stale_compaction_result'`"。

**验证**: 原始 review 分析 stale check 在 manifest guard 之前触发，不经过 `_required_compactor_manifest_ref`，因此该 test 不需要也不应迁移。Fixed plan 完整采纳了此裁决，在多处显式标注不迁移及理由。已修复。

---

### DS Finding 3 (BLOCKING) — `_TransactionReadableCompactor` 迁移未在任何 slice 显式分配

**Status**: 已修复。

**Fix evidence**:
- Plan Decision 8 (line 108) 将 `_TransactionReadableCompactor` 设为 "必须显式迁移到 prepared helper 路径，并保留'compactor 调用期可开启独立读事务读取 Run'的原测试语义"。
- Slice 0 accepted inventory (line 142) 列出 `test_proactive_compaction_calls_llm_outside_write_transaction` 及其 `_TransactionReadableCompactor`。
- Slice 2 line 214 "`_TransactionReadableCompactor` 显式归入本 slice。迁移后保留 `compactor.calls == 1` 与独立读事务可读 Run 的断言语义；不要把它降级为普通 `_PreparedManifestProactiveCompactor`"。

**验证**: 原始 review 指出该 compactor 不是 `FakeContextCompactor()` 字面量，且带额外构造参数 `transaction_runner`，原 Slice 2/4 均无法匹配。Fixed plan 将其显式归入 Slice 2，并明确禁止降级为普通 prepared helper。已修复。

---

### DS Finding 4 (NON-BLOCKING) — `_RequestCapturingCompactor` 使用范围未明确

**Status**: 已修复。

**Fix evidence**:
- Plan Decision 6 (line 106) 要求 "implementation 前必须先 grep `_RequestCapturingCompactor` 全部使用点；在 proactive accepted path 中归入 accepted migration slice，不能留作模糊 residual"。
- Slice 0 inventory (lines 139-140) 列出两个 current proactive accepted 使用点：`test_proactive_compaction_uses_selected_material_not_session_start_range` 和 `test_proactive_material_pack_not_larger_than_ordinary_material_for_same_view`。
- Slice 2 lines 208-209, 213 在迁移清单中显式包含这两个 test，并要求 "迁移后仍断言 captured `CompactionRequest` 的 selected material、material refs、material pack 大小语义"。

**验证**: grep 确认 `_RequestCapturingCompactor` 在这两个 test 中使用（lines 3695, 3730）。Fixed plan 正确归档到 accepted migration Slice 2。已修复。

---

### DS Finding 5 (NON-BLOCKING) — `RUNNER_CALL_INPUT_ASSEMBLED` event count 断言风险

**Status**: 已修复。

**Fix evidence**:
- Plan Slice 2 line 220: "`RUNNER_CALL_INPUT_ASSEMBLED` count 只能作为 conditional assertion：先在 focused accepted test 中验证该 event 确实由 durable recorder 写入，且不会引入脆弱计数；只有验证成立后才加入 count 断言。核心验收仍是 `CONTEXT_COMPACTED` payload 的 manifest ref/digest"。
- Plan Slice 3 line 253: rejected path 同样 "只能作为 conditional assertion"。
- Plan residual risks line 375: "如果 `RUNNER_CALL_INPUT_ASSEMBLED` event count 受其它 compact path 影响，断言应限定在单个 test store 内且只在 focused test 验证稳定后加入；否则只断言 compacted/rejected payload manifest ref/digest"。

**验证**: 原始 review 指出该 event 是否出现在 test EventLog 取决于 `compact_artifact_root` 配置，且可能被同一 store 其他 test 污染。Fixed plan 将 count assertion 降级为 conditional，核心验收回归 manifest ref/digest payload 断言。已修复。

---

### DS Finding 6 (NON-BLOCKING) — `_COMPACTOR_TEST_DIGEST` 常量引入不必要的抽象

**Status**: Controller rejected — 证据失效。Plan 改为优先复用现有常量。

**Fix evidence**:
- Plan fix artifact 说明 controller 裁决模块级私有 digest 常量不是过度设计，项目禁止魔法字符串。
- Plan Slice 1 line 170 改为 "优先复用测试文件现有语义 digest 常量 `_CALL_CONTEXT_DIGEST` 作为 prepared input 的 stable digest；若实现时确认没有合适常量，再新增语义明确的模块级私有 digest 常量，禁止内联魔法 digest 字符串"。

**验证**: grep 确认 `_CALL_CONTEXT_DIGEST` 存在于 `tests/host/test_dispatch_scheduler.py:173`，且在文件中多处使用（lines 4898, 4949, 5036, 5038, 5761, 5798），语义合适。Plan 不再要求新增独立 `_COMPACTOR_TEST_DIGEST` 常量。已处理。

---

### DS Finding 7 (NON-BLOCKING) — `_RaisingCompactor` 被非 `-k` 范围内 test 复用的风险 + post-manifest failure 语义

**Status**: 已修复。

**Fix evidence**:
- Plan Decision 10 (line 110) 要求 "`_RaisingCompactor` 所有使用点必须先 grep。若仅 proactive rejected test 使用，则用 prepared helper 的 `fail_run=True` 或等价 prepared failure 替代纯 `compact()` 抛错路径，使 failure 发生在 manifest record 之后；这是有意的 test 语义升级，用于覆盖 post-manifest proposal failure rejected payload，不是把 proposal failure 伪装成 quality rejection"。
- Slice 0 rejected inventory (line 147) 列出 `test_compaction_repair_attempt_rejection_is_recorded_in_eventlog`，并附带 grep 要求。
- Slice 3 line 247 重申 "implementation 前先 grep `_RaisingCompactor` 所有使用点"。
- Slice 3 line 270 在 invariant 中明确 "`_RaisingCompactor` 迁移为 prepared post-manifest failure 是有意的 test 语义升级：原 legacy seam 覆盖的是 pre-manifest `compact()` failure，迁移后覆盖 manifest 已记录后的 proposal execution failure rejected payload"。

**验证**: grep 确认 `_RaisingCompactor` 仅在 line 4035 被 `test_compaction_repair_attempt_rejection_is_recorded_in_eventlog` 使用。Fixed plan 完整说明了从 pre-manifest failure 到 post-manifest failure 的语义升级，且明确不是伪装 quality rejection。已修复。

---

### MiMo F3（交叉验证）— `_QualityRejectOnceCompactor` 第一次 quality rejection manifest 覆盖

**Status**: 已修复。

**Fix evidence**:
- Plan Decision 7 (line 107) 明确 "第一次 quality rejection 的 rejected event 与第二次 accepted event 都有 manifest。第一次 rejected payload 的 manifest 断言是本 work unit 新增覆盖，不是修复既有断言"。
- Slice 0 mixed inventory (line 145) 要求 "第一次 quality rejection 与第二次 accepted 都必须有 manifest assertions"。
- Slice 3 lines 254-255 要求 "补充 rejected payload manifest assertions，证明 semantic quality rejection 也保留 proposal manifest。该断言是新增覆盖"，并 "补 accepted payload manifest assertions"。

**验证**: Fixed plan 清楚区分修复既有断言（accepted manifest ref/digest payload fields）与新增断言覆盖（第一次 quality rejection 的 rejected manifest）。已修复。

---

## Blocking Open Questions

无。

---

## New Blocking Issues Introduced by Fix

**0 项**。Fix 未引入新的 scope creep、架构边界破坏、实现歧义或矛盾指令。

Slab 检查要点：

- Slice 0 grep regex 中 `FakeContextCompactor\\(` 的转义在 markdown 中显示为 `\\`，若复制到 shell 正确有效。非 plan 级问题。
- Decision 7 的 "第一次 quality rejection manifest 是新增覆盖" 与 Decision 5 的 "failure 必须在 manifest record 之后" 之间无矛盾——`_QualityRejectOnceCompactor` 第一次 run 返回 invalid candidate（不抛异常），第二次 run 返回 clean candidate，两次 run 均在 manifest record 之后。
- Decision 10 的 "有意的 test 语义升级" 与 Slice 3 line 270 表述一致，不会误导 implementation agent。

---

## Residual Risks / Uncovered Areas

Plan residual risks section (lines 371-376) 覆盖了以下持续风险：

1. **`-k` 范围外遗漏**: Slice 0 grep + Slice 4 复核应捕获，但取决于 implementation agent 执行纪律。
2. **`_TransactionReadableCompactor` / `_RequestCapturingCompactor` / `_QualityRejectOnceCompactor` 原语义保留**: 依赖 implementation 正确性，与 plan 设计无关。
3. **`RUNNER_CALL_INPUT_ASSEMBLED` event count 脆弱性**: Plan 已降级为 conditional assertion，不会阻塞验收。
4. **pyright protocol 签名对齐**: `CompactorProposalPreparedCompactor` 是 runtime-checkable Protocol，helper 方法签名不匹配会导致 legacy 路径。Plan 在 Slice 1 invariants + residual risks 中已识别。

无新增 residual risk。

---

## Validation Performed

- 逐条对照 DS review 7 findings 与 Codex fix artifact 声明的修改点。
- 逐条验证 fixed plan artifact 中对应行号的实际内容。
- grep 验证 `tests/host/test_dispatch_scheduler.py` 中全部 compactor 类型定义和使用点，确认 Slice 0 semantic inventory 与代码一致。
- grep 验证 `_CALL_CONTEXT_DIGEST` 存在性及使用点，确认 Slice 1 复用建议可行。
- grep 验证 `CompactorProposalRunInput` 在 `dayu/host/compaction_operation.py` 中可导入。
- grep 验证 `conversation_compact_input_vnext_from_material_pack` 在 `dayu/host/compact_material.py` 中可导入。
- 读取并对照 MiMo review artifact、total control doc WU-CM-01-F04 section。
- 未运行 pytest / pyright；本 gate 只验证 plan fix 质量，不修改生产/测试/README。
