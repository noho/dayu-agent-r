# PR 190 Compactor LLM-facing S4 独立 deepreview

## 范围

- **Work unit**: PR 190 Compactor LLM-facing conformance S4 — Documentation and aggregate validation
- **Accepted base**: `69ab297b`
- **Scope**: only `docs/host/design.md`, `dayu/config/README.md`, `dayu/host/README.md`, `tests/README.md`, `docs/gateflow/pr-190-compactor-llm-facing-s4-implementation-20260803.md`
- **Decision**: 文档忠实于当前实现与唯一 owner；没有 finding。

## 验证摘要

### 文档忠实度

| 文档 | 声称 | 证据 | 判定 |
|------|------|------|------|
| `docs/host/design.md` | untrusted material boundary、strict/self-contained contract、Context Governance accept/reject truth ownership、durable internal feedback 与最小 typed LLM projector 分离、同 policy/estimator exact cap feedback、whole-candidate repair | `docs/host/design.md:3322-3387` 新增段落与 `dayu/host/context_governance.py:59,117`、`dayu/host/llm_compaction.py:680`、`dayu/host/compaction.py:1630` 实现一致 | **PASS** |
| `dayu/config/README.md` | packaged prompt 的 material boundary、自足 input/output/example 与 repair contract、source label 引用语义 | `dayu/config/README.md:360-362` 新增段落与 `dayu/config/prompts/scenes/conversation_compaction.md:9,17`、`conversation_compaction_user.md:7,72,83` 一致 | **PASS** |
| `dayu/host/README.md` | Context Governance reject truth、durable internal feedback、唯一 projector/renderer、repair marker/action、exact cap 的 owner boundary | `dayu/host/README.md:524,526` 新增段落与 `dayu/host/context_governance.py:59,117`、`dayu/host/llm_compaction.py:680` 一致 | **PASS** |
| `tests/README.md` | deterministic trust/schema/example/repair/cap matrix、opt-in real smoke 命令、Mimo-first + DeepSeek-only fallback、当前 evidence `network_unavailable` exact skip、behavior oracle `not_observed` | `tests/README.md:384-392` 新增段落与 `tests/host/test_llm_compaction.py:297-389`、`tests/host/test_public_compact_smoke.py` real compactor test、evidence `provider-fallback-classification.json:11-13`、`real-provider-pytest-with-skip-reasons.log:99`、`validation-summary.md:4-7` 一致 | **PASS** |

### 语义所有权与分层边界

- **Config README 不泄漏 Host 实现**: 新增行 grep 确认不含 `LLMContextCompactor`、`_repair_feedback_prompt`、`projector`、`renderer`、`typed internal`、`durable governance`、`estimate_memory_size_units` 等 Host 内部术语。只描述 packaged prompt asset 的 trust boundary、自足 contract 与 repair schema。
- **Host README 不写测试/未来**: 新增行 `dayu/host/README.md:524,526` 不含测试清单、未来计划或 TODO。只描述 Context Governance accept/reject truth ownership、internal feedback 与 LLM-facing projector 的 owner boundary。
- **根 README 不改合理**: 无用户可见安装、初始化、CLI/Web/WeChat 入口、命令参数、输出、工作区路径、日志或排障变化。
- **dayu/README.md 不改合理**: 无 `UI -> Service -> Host -> Engine` 分层、依赖方向、装配方式或跨包责任变化。

### 内部术语泄漏检查

- `dayu/config/prompts/scenes/conversation_compaction.md` 与 `conversation_compaction_user.md`: grep 确认不含 `Host`、`Memory`、`Attempt`、`migration`、`v1`、`vNext`、`legacy`、`OLD` 等泄漏项。`v2` 仅出现在 schema version 字符串 `dayu.context_compaction.input.v2` 和 `dayu.context_compaction.output.v2`——这些是模型必须输出的 schema 字段值，不是泄漏。
- `tests/host/test_llm_compaction.py:297-304`: forbidden internal terms test 锁定 `previous_attempt_number`、`additional_issue_count`、`CompactRepairFeedbackV2`、`CompactValidationIssueV2`、`Memory policy` 不进入 LLM-facing repair block。
- `tests/host/test_llm_compaction.py:374-381`: prompt asset test 确认 `schema_version`、`current_input_anchor`、`previous_compacted_view`、`evidence_backed_facts`、`reference_continuity_items` 不进入 user prompt。
- `dayu/host/compaction.py:1630` (`CompactRepairFeedbackV2`): 保留 `previous_attempt_number` 与 `additional_issue_count`，证明 durable internal feedback 未为 LLM schema 缩短。
- `dayu/host/llm_compaction.py:692-703` (`_repair_feedback_prompt_json_vnext`): 唯一 LLM-facing projector 只输出 `required_action` 与 `issues`（`code`、`json_path`、`message`、`source_labels`）——exact-key projection，不泄漏内部 fields。

### 过度设计检查

- 四份文档新增内容全部描述当前实现事实；无未来预留、未落地能力、output schema 扩展、repair loop、材料 filter 或 verifier 描述。
- S4 实现文档 `docs/gateflow/pr-190-compactor-llm-facing-s4-implementation-20260803.md:72-77` 显式声明非改动：未修改 output schema、operation/repair loop、production filter/verifier、Memory projection、frozen oracle/scenario。

### 聚合验证结果

| 校验项 | S4 声称 | 实测 | 判定 |
|--------|---------|------|------|
| pytest (7 files) | `365 passed, 1 skipped, 3 warnings` | `365 passed, 1 skipped, 3 warnings in 6.00s` | **PASS** |
| pyright | `0 errors, 0 warnings, 0 informations` | `0 errors, 0 warnings, 0 informations` | **PASS** |
| `json.tool` oracles | pass | pass | **PASS** |
| `json.tool` scenarios | pass | pass | **PASS** |
| `git diff --check` | pass | pass（无输出） | **PASS** |
| `sha256sum -c SHA256SUMS` | 13/13 OK | 13/13 OK | **PASS** |
| frozen oracle checksum | `f9972d94...` | `f9972d94...` | **PASS** |
| frozen scenario checksum | `7f283b03...` | `7f283b03...` | **PASS** |
| `git diff --exit-code` frozen files | pass | pass | **PASS** |

### Real provider evidence

- `provider-fallback-classification.json:11-13`: Mimo `network_unavailable`，随后 DeepSeek `network_unavailable`，result `skip_after_both_environment_unavailable`。无 Gemini/Qwen 调用。
- `provider-fallback-classification.json:16-21`: 留存 Mimo `runner_empty_final_content` 观察，分类为 `unclassified_non_environment_failure`，非环境可用分类，测试 fail closed 无 fallback。
- validation-summary.md:11: 因未收到非空 raw final，strict parse、governance accept、cap compliance、injection behavior 全部 `not_observed`，不能报告为 pass。
- deterministic matrix 只证明 owner contract，不替代真实模型行为观察。

### 显式非改动验证

- root `README.md`：`git diff HEAD -- README.md` 无输出 → 未改。
- `dayu/README.md`：`git diff HEAD -- dayu/README.md` 无输出 → 未改。
- `docs/cli_ci_oracles.json`：`git diff --exit-code HEAD` pass → 未改。
- `docs/cli_ci_scenarios.json`：`git diff --exit-code HEAD` pass → 未改。
- prompt assets：S4 文档显式声明 "未修改 prompt asset"——`git diff HEAD -- dayu/config/prompts/` 无输出 → 未改。

## Findings

**无 finding。** 全部四份文档新增内容忠实于当前实现、不越层泄漏内部术语、不预留未来设计。聚合验证 365 passed / 1 skipped、pyright 0、JSON/diff/checksum 全部通过。Real provider behavior oracle 正确标为 `not_observed`，不伪报 pass。

## Residual

- **Real behavior not_observed**: 真实 strict parse、governance accept、cap compliance 与 injection behavior 仍归 S3 real-provider smoke 环境 owner 承担。网络/credential 可用后按 `DAYU_RUN_REAL_COMPACTOR_SMOKE=1` 重跑。
- **完整自然语言/Conversation Memory evaluation**: 仍归既有 Issue 80。
- **S4 文档本身**: 作为 gateflow 内 implementation artifact，其声称（owner evidence、LLM-facing audit、非改动、aggregate validation）已在本 review 中逐项交叉核验通过。
