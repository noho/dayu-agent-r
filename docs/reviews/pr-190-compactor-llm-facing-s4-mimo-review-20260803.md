# PR 190 Compactor LLM-facing S4 MiMo Review

- Reviewer: MiMo
- Date: 2026-08-03
- Scope: `docs/host/design.md`, `dayu/config/README.md`, `dayu/host/README.md`, `tests/README.md`, `docs/gateflow/pr-190-compactor-llm-facing-s4-implementation-20260803.md`
- Base: `69ab297b` (S3 acceptance HEAD)
- Mode: read-only; no production/doc files modified

## Conclusion: PASS — no findings

全部五项目标文档的变更忠实于当前实现，未发现语义所有权漂移、内部术语泄漏、过度设计或跨层边界违反。

## Verification matrix

### 1. 文档忠实于当前实现

| Claim in docs | Verification source | Result |
|---|---|---|
| system prompt 标记 marker 间为不可信引用材料 | `dayu/config/prompts/scenes/conversation_compaction.md` L7-10: `UNTRUSTED_COMPACTION_MATERIAL_JSON_BEGIN/END` + "不得执行"规则 | ✓ 实现一致 |
| user prompt 自足说明 strict input/output schema、八种 source_kind、覆盖规则、label 同源完整示例 | `dayu/config/prompts/scenes/conversation_compaction_user.md` 全文：完整 input schema、八种 kind 业务语义、output 全字段定义、覆盖规则、修复反馈 schema | ✓ 实现一致 |
| 唯一 repair projector 只输出 `required_action` + `issues`，每 issue 只含 `code/json_path/message/source_labels` | `dayu/host/llm_compaction.py:680-706` `_repair_feedback_prompt_json_vnext`：遍历 `feedback.issues`，只投影四字段 | ✓ 实现一致 |
| Context Governance 是 accept/reject truth owner | `dayu/host/context_governance.py:59` `accept_compact_candidate_v2` 接受 `MemoryProjectionPolicy` 参数 | ✓ 实现一致 |
| cap feedback 从同一 policy instance + estimator 产生 | `context_governance.py:493` 调用 `estimate_memory_size_units(candidate.session_summary.text).units`；`dayu/host/memory.py` 是 `MemoryProjectionPolicy` 和 `estimate_memory_size_units` 的 def site | ✓ 实现一致 |
| `CompactRepairFeedbackV2` 保留 `previous_attempt_number` 与 `additional_issue_count` | `dayu/host/compaction.py:1630` 类定义存在且包含这些字段 | ✓ 内部治理 truth 未为 LLM schema 缩短 |

### 2. Config README 不泄漏 Host 实现

- `dayu/config/README.md` 新增两段只描述 packaged prompt asset 的 material boundary、自足 contract、source label 引用语义和修复反馈格式。
- 未出现 `Context Governance`、`MemoryProjectionPolicy`、`estimate_memory_size_units`、`LLMContextCompactor`、`accept_compact_candidate_v2` 等 Host 内部标识。
- **Pass.**

### 3. Host README 不写测试清单或未来计划

- `dayu/host/README.md` 新增两段记录 Context Governance reject truth、durable internal feedback、唯一 projector/renderer、repair marker 与 exact cap 的 owner boundary。
- 未出现测试文件名、测试数量、覆盖率目标或 "future"/"planned"/"TODO" 等未来计划。
- **Pass.**

### 4. 根 README 和 dayu/README 不改是否合理

- `README.md`（用户手册）：无用户可见安装/初始化/CLI/Web/WeChat 入口/命令参数/输出/工作区路径/日志/排障变化。触发条件未命中。
- `dayu/README.md`（跨包总览）：无 `UI → Service → Host → Engine` 分层/依赖方向/装配方式/公共入口/跨包责任变化。触发条件未命中。
- **Pass — 不改合理。**

### 5. 聚合验证

| Check | Claimed | Actual | Source |
|---|---|---|---|
| pytest aggregate | 365 passed, 1 skipped | **365 passed, 1 skipped, 3 warnings** | `pytest ... -q` 实跑确认；skip 是 opt-in real compactor smoke 默认未启用；warnings 是第三方 edgar deprecation |
| pyright | 0 errors, 0 warnings, 0 informations | **0 errors, 0 warnings, 0 informations** | `python -m pyright dayu/ tests/ utils/` 实跑确认 |
| `cli_ci_oracles.json` JSON valid | pass | **valid** | `python -m json.tool` 确认 |
| `cli_ci_scenarios.json` JSON valid | pass | **valid** | `python -m json.tool` 确认 |
| `git diff --check` | pass | **pass** | 工作区无 conflict markers |
| Evidence SHA256 | 13/13 OK | **13/13 OK** | `sha256sum -c SHA256SUMS` 在 evidence 目录确认 |
| Frozen oracles checksum | `f9972d943ac8ae8d79ebbe7114c1305b7af2933729575d1407fcb6d4d05b07f4` | **matches** | `sha256sum` 实算确认 |
| Frozen scenarios checksum | `7f283b039dc02ce686bb134c748e5c98039af2029eb090dbdaf6dcf4fe5e8cef` | **matches** | `sha256sum` 实算确认 |
| Frozen files `git diff --exit-code` | pass | **pass** | 确认未被修改 |

### 6. network_unavailable 后 behavior 必须写 not_observed

- `redacted-observations.json` 中 `final_exact_real_provider_run.raw_final`: `"not_received"`，`behavior_oracle`: `"not_observed"`。
- `provider-fallback-classification.json` 中 Mimo: `"network_unavailable"`，DeepSeek: `"network_unavailable"`，result: `"skip_after_both_environment_unavailable"`。
- `tests/README.md` 新增段明确写："没有收到非空真实 candidate，因此真实 strict parse、governance accept、cap compliance 与 injection behavior oracle 均为 `not_observed`，不能写成 behavior pass"。
- **Pass — 未伪报 pass。**

### 7. Frozen oracle/scenario 不得变

- `docs/cli_ci_oracles.json` 和 `docs/cli_ci_scenarios.json`：`git diff --exit-code` pass，checksum 与 S3 evidence 一致。
- **Pass.**

## Semantic ownership drift check

| Boundary | Config README | Host README | design.md | Drift? |
|---|---|---|---|---|
| Accept/reject truth | 不提及 | ✓ Context Governance owner | ✓ Context Governance owner | 无漂移 |
| Repair projector output | 不提及 | ✓ 4 exact keys | ✓ 4 exact keys | 无漂移 |
| Renderer responsibility | 不提及 | ✓ 放入 prompt marker | ✓ 放入 prompt marker | 无漂移 |
| Cap feedback source | 不提及 | ✓ 同 policy + estimator | ✓ 同 policy + estimator | 无漂移 |
| Material trust boundary | ✓ marker 定义 + 数据语义 | 不重复 | ✓ marker + 不可执行规则 | 各层各司其职 |

## Over-design / LLM-facing north star check

- 未新增 compact output schema 字段、semantic repair loop、材料 filter 或自然语言 verifier。文档明确声明 "不增加"。
- `source_label` 在三份文档中一致定性为 "引用标签，不是业务事实或推理依据"。
- prompt 中所有字段名、类型、必填性、允许值均自足说明，不引用 Python 类型名或内部模块名。
- **Pass — 无过度设计，LLM-facing north star 守住。**

## Residual risks

1. **Real behavior not_observed**：Mimo 与 DeepSeek 均 `network_unavailable`，真实 injection resistance、cap compliance、strict parse 与 governance accept 均未被观察。网络/credential 恢复后需按 `DAYU_RUN_REAL_COMPACTOR_SMOKE=1 pytest tests/host/test_public_compact_smoke.py -q -k 'real_compactor'` 重跑。此 residual 归 S3 real-provider smoke 环境 owner，不是 S4 文档问题。
2. **Conversation Memory 自然语言 evaluation**：归既有 Issue 80，不在本 PR 范围。

## Artifact

唯一 durable artifact: `docs/reviews/pr-190-compactor-llm-facing-s4-mimo-review-20260803.md`（本文件）。
