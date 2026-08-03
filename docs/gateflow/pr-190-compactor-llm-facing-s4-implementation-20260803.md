# PR 190 Compactor LLM-facing S4 implementation

## Gate metadata

- Gate: S4 Documentation and aggregate validation
- Work unit: PR 190 Compactor LLM-facing conformance
- Accepted base / implementation HEAD: `69ab297be50f4cdd1cfa1d092f470921d2d9efda`
- Accepted plan: `docs/gateflow/pr-190-compactor-llm-facing-f01-f03-plan-20260803.md`
- S3 acceptance: `docs/gateflow/pr-190-compactor-llm-facing-s3-rereview-acceptance-20260803-190500.md`
- Read-only evidence: `/Users/leo/workspace/.dayu-cli-ci/pr190-compactor-llm-facing-20260803-182956/`
- Decision: implementation complete；未 commit。
- Artifact path: `docs/gateflow/pr-190-compactor-llm-facing-s4-implementation-20260803.md`

## First-principles judgment and scope

S4 动机成立：S1-S3 已把 prompt trust boundary、strict/self-contained contract、internal feedback 与 LLM projection 分离、exact cap feedback 和 real-smoke selector 落到 owner boundary，但稳定设计与开发手册尚未完整表达这些当前事实。文档缺口会让后续修改重新混淆 accept/reject truth、durable internal feedback 与模型可执行 repair contract，因此需要在现有 owner 文档补齐；不需要再改 output schema、operation loop、provider/model 选择或下游 filter/verifier。

本 slice 只修改四份目标文档与本 artifact。没有修改 prompt asset、Python production/test、frozen CLI oracle/scenario、根用户手册或跨包总览。

## Direct owner evidence

- `dayu/config/prompts/scenes/conversation_compaction.md` 与 `conversation_compaction_user.md`：system/user prompt 已明确 marker 内是完整不可信引用材料，`current_input.readable_text` 与所有 `source_boundary[*].readable_text` 内指令不得执行；原文不因指令形态被过滤。user prompt 自足说明 strict input/output schema、八种 source kind、开放字符串业务语义、repair exact schema 和 label 同源完整示例。
- `dayu/host/llm_compaction.py::_repair_feedback_prompt_json_vnext`：唯一 LLM-facing projector 直接读取 typed internal feedback，只输出 `required_action` 与 `issues`；每个 issue 只输出 `code/json_path/message/source_labels`。`_user_prompt_vnext` 负责独占 repair marker 的机械渲染，material renderer 原样序列化 typed input。
- `dayu/host/context_governance.py::accept_compact_candidate_v2` 及 policy issue helpers：Context Governance 是 accept/reject truth owner；section item/字符 reject 从传入的同一 `MemoryProjectionPolicy` 与 `estimate_memory_size_units` 结果生成，message 包含 actual、cap、计量对象和直接动作。
- `dayu/host/compaction.py::CompactRepairFeedbackV2`：durable/internal bounded feedback 继续保留 `previous_attempt_number` 与 `additional_issue_count`，证明内部治理 truth 未为 LLM schema 缩短。
- `tests/host/test_llm_compaction.py`、`tests/host/test_compaction_contract.py`、`tests/host/test_public_compact_smoke.py`：owner tests 锁定 trust/schema/example/repair/cap matrix、原文无 production filter、最小 projector exact keys、whole-candidate action，以及内部术语不进入 prompt/repair block。

## LLM-facing audit

重新完整检查两份 packaged compactor prompt，并核对 renderer、policy feedback 和 owner-level forbidden-term tests。没有发现新的真实泄漏类别：模型不需要理解 Host/Memory/Attempt、Python 类型名、迁移名称、durable ref/digest/cursor 或内部 feedback 计数字段；业务可读 contract 字段名保留。故未修改 prompt、production code 或 tests，也未扩大 owner test 禁止词集合。

## Documentation changes and README decisions

- `docs/host/design.md`：固定 untrusted material boundary、`current_input/source_boundary readable_text` 数据语义、strict/self-contained schema/example、Context Governance accept/reject truth ownership、durable internal feedback 与最小 typed LLM projector 分离、同 policy/estimator exact cap feedback、whole-candidate repair，以及不增加 schema/loop/filter/verifier。
- `dayu/config/README.md`：只描述 packaged prompt asset 的 material boundary、自足 input/output/example 与 repair contract、source label 引用语义；未写 Host 实现细节。
- `dayu/host/README.md`：记录 Context Governance reject truth、durable internal feedback、唯一 projector/renderer、repair marker/action 与 exact cap 的 owner boundary；未写测试清单或未来计划。
- `tests/README.md`：记录 deterministic trust/schema/example/repair/cap matrix、opt-in real smoke 命令、Mimo-first / DeepSeek-only fallback，以及当前 evidence 的两路 `network_unavailable` exact skip 与 behavior oracle `not_observed`。
- 根 `README.md`：checked, unchanged。依据：没有用户可见安装、初始化、CLI/Web/WeChat 入口、命令参数、输出、工作区路径、日志或排障变化；其最终用户手册边界未触发。
- `dayu/README.md`：checked, unchanged。依据：没有 `UI -> Service -> Host -> Engine` 分层、依赖方向、装配方式、公共入口或跨包责任变化；其总览边界未触发。

## Aggregate validation

在 Python 3.11 仓库虚拟环境中执行：

1. `pytest tests/host/test_llm_compaction.py tests/host/test_compaction_contract.py tests/host/test_public_compact_smoke.py tests/runtime/test_scene_assets_migration.py tests/runtime/test_config_loader.py tests/cli/test_smoke_cli_init_provider_matrix.py tests/service/test_host_assembly.py -q`
   - Result: `365 passed, 1 skipped, 3 warnings in 5.52s`。
   - skip 是默认未启用的 opt-in real compactor smoke，不是 behavior pass；warnings 是既有第三方 `edgar` deprecation warnings。
2. `python -m pyright dayu/ tests/ utils/`
   - Result: `0 errors, 0 warnings, 0 informations`。
3. `python -m json.tool docs/cli_ci_oracles.json`
   - Result: pass。
4. `python -m json.tool docs/cli_ci_scenarios.json`
   - Result: pass。
5. `git diff --check`
   - Result: pass。
6. 在 read-only evidence 目录执行 `sha256sum -c SHA256SUMS`
   - Result: 13/13 entries `OK`。
7. Frozen file verification：
   - `docs/cli_ci_oracles.json`: `f9972d943ac8ae8d79ebbe7114c1305b7af2933729575d1407fcb6d4d05b07f4`。
   - `docs/cli_ci_scenarios.json`: `7f283b039dc02ce686bb134c748e5c98039af2029eb090dbdaf6dcf4fe5e8cef`。
   - 两文件 `git diff --exit-code` pass，保持不变。

一次组合校验最初在 evidence 目录使用相对 `.venv/bin/activate`，因该目录没有虚拟环境而在任何校验动作前退出；随后使用仓库虚拟环境绝对路径完整重跑并取得上述结果，evidence 未被修改。

## Real-provider evidence and residual risks

- S3 final exact run：Mimo `network_unavailable`，随后 DeepSeek `network_unavailable`，两路均由既有结构化 classifier 精确分类，之后 exact skip；没有 Gemini/Qwen 调用。
- retained Mimo empty-final observation：`runner_empty_final_content` 属于非环境失败，测试 fail closed 且没有 fallback，selector 行为符合 contract。
- 真实 injection/cap behavior oracle：`not_observed`。没有收到非空 raw final，真实 strict parser、Context Governance accept、cap compliance 与 injection behavior 都未到达，不能报告为 pass。
- Residual classification：real behavior `not_observed` 由 S3 real-provider smoke 环境 owner 承担，网络/credential 可用后按相同 opt-in 命令重跑；完整自然语言/Conversation Memory evaluation 仍归既有 Issue 80。没有未分类 residual risk。

## Explicit non-changes

- 未修改 root `README.md`、`dayu/README.md`、provider/model semantics、compact output schema、operation/repair loop、production filter/verifier 或 Memory projection。
- 未修改 `docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json`。
- 未 commit。
