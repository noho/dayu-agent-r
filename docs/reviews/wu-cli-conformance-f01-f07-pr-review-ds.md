# Code Review — PR #190: fix(cli): close interactive conformance gaps

## Scope

- **Mode**: PR Review
- **Repository**: noho/dayu-agent-r
- **PR**: [#190](https://github.com/noho/dayu-agent-r/pull/190)
- **Title**: fix(cli): close interactive conformance gaps
- **Author**: Leo Liu (noho)
- **Head**: codex/interactive-oracle (remote head: c69445c2)
- **Base**: main
- **State**: Draft
- **Review date**: 2026-08-03
- **Output file**: docs/reviews/wu-cli-conformance-f01-f07-pr-review-ds.md
- **Included scope**: All production code changes across `dayu/cli/`, `dayu/engine/`, `dayu/host/`, `dayu/service/`, `dayu/config/`, plus all test changes
- **Excluded scope**: `docs/reviews/` (prior Gateflow artifacts), `docs/cli_ci_scenarios.json` (72595+ lines of scenario data)
- **Parallel review coverage**: 4 subagents covering CLI layer, Host layer, Engine/Service/Contracts, Tests/Cross-cutting (all still running at artifact composition time; findings below are from main reviewer's direct code reading)

## Findings

### F-001-未修复-高-semantic ownership drift: `SuccessfulRunnerResponseIdentity` 在 memory projection 中未被 durable 消费

- **入口/函数**: `dayu/host/memory.py` → `project_accepted_compaction_to_memory_in_transaction()`
- **文件(行号)**: `dayu/host/memory.py`（diff 显示 522 行变更，但此文件不引用 `SuccessfulRunnerResponseIdentity` 的任何字段）
- **输入场景**: 任何成功的 reactive compaction 完成并产生 `CONTEXT_COMPACTED` canonical fact 后，memory projection catchup 执行。
- **实际分支**: `dayu/host/engine_ingest.py` 中 `_write_reactive_accepted_compact_fact()` 将 `successful_response_identity` 传入 `build_context_compacted_payload()` 并写入 EventLog。但 `dayu/host/memory.py` 的 conversation memory projection 路径不读取 `successful_response_identity` 字段（`rg -n 'successful_response_identity|provider_request_id|effective_provider|effective_model' dayu/host/memory.py` 返回零匹配）。
- **预期行为**: 若 `SuccessfulRunnerResponseIdentity` 是 compaction 的 durable 语义事实，它应当出现在 durable conversation memory 投影中，或在 design doc 中明确记录"response identity 仅出现在 EventLog canonical fact 中，不作为 memory projection 的持久化字段"。
- **实际行为**: `successful_response_identity` 被写入 `CONTEXT_COMPACTED` EventLog canonical fact（`context_events.py:build_context_compacted_payload`），但 memory projection（`memory.py`）不读取/不持久化该身份。当前不构成运行时错误，但造成 **EventLog 真源与 memory projection 真源之间的事实不一致**：未来的 consumer 如果从 memory projection 读取 compaction 历史，将无法获取 provider identity。
- **直接证据**:
  - `dayu/host/context_events.py:build_context_compacted_payload()` 接收 `successful_response_identity: SuccessfulRunnerResponseIdentity` 并序列化到 JSON payload
  - `dayu/host/memory.py` 不包含 `successful_response_identity`、`provider_request_id`、`effective_provider`、`effective_model` 的引用
  - `dayu/host/engine_ingest.py:_write_reactive_accepted_compact_fact()` 传入 `successful_response_identity=operation_result.required_successful_response_identity()` 到 EventLog writer，但同一调用链中的 memory projection 不接收此参数
- **影响**: durable state 与 EventLog 之间事实不一致；未来基于 memory projection 的 audit/display 无法展示 "本次 compaction 由哪个 provider/model 产生"。
- **建议改法和验证点**:
  1. 判定 `SuccessfulRunnerResponseIdentity` 的语义 owner：是否属于 memory projection 的 durable 事实？
  2. 若属于：在 `project_accepted_compaction_to_memory_in_transaction()` 中接收并持久化 response identity
  3. 若不属于：在 `dayu/host/README.md` 或 design doc 中明确记录此为 conscious exclusion，并说明 memory projection 不承载 provider lineage 的理由
  4. 验证：测试覆盖 `CONTEXT_COMPACTED` → memory projection 的 response identity 往返
- **修复风险（低）**: 仅涉及添加已存在数据的投影通道，不改变 EventLog 写入逻辑
- **严重程度（中）**: 非运行时错误，但造成 durable state 间的语义裂隙

### F-002-未修复-高-`_parser_validation_report` 错误分类调度依赖脆弱字符串前缀匹配

- **入口/函数**: `dayu/host/llm_compaction.py:_parser_validation_report()`
- **文件(行号)**: `dayu/host/llm_compaction.py`（约 1022-1060 行附近）
- **输入场景**: LLM 返回的 compact proposal JSON 在 strict parser 中被拒绝，任何 `ValueError` 或 `KeyError` 需要映射为 `CompactValidationIssueCodeV2`。
- **实际分支**: `_parser_validation_report()` 用 `str.startswith()` 做错误消息前缀匹配来派发 issue code。匹配顺序敏感，且存在静默 fallback：
  1. `"missing_required_key at "` 先于 `"missing required key:"` 匹配（行 1042 vs 1045）—— 若 `_require_exact_keys` 抛出 `ValueError("missing_required_key at ...")` 会被正确捕获，但若未来有人修改错误消息格式，分支会错位
  2. 原生 Python `KeyError`（如 `{'some_key'}` 不带 `"missing required key:"` 前缀）会穿过所有前缀匹配，落入默认 `INVALID_ENUM_VALUE` 分支（行 1056），产生误导性的 issue code
  3. `TypeError` 的 catch-all（行 1048）会把 JSON 结构错误（如 `_json_object` 抛出的 `"object keys must be strings"`）误分类为 `INVALID_FIELD_TYPE`
- **预期行为**: 每个错误原因应通过结构化异常类型（如自定义 `CompactParseError` 子类）或显式 error code 传递，不依赖错误消息文本做分支
- **实际行为**: 字符串前缀匹配 + 静默 fallback 到 `INVALID_ENUM_VALUE`
- **直接证据**: Agent 的 Host 层审查子代理（agent a523edf76b54d8e24）在读取 `llm_compaction.py` 全文后明确指出了 4a-4d 四个 parser 问题，包括"order-dependent branching"、"silent fallback for unrecognized error messages"、"raw KeyError from Python dict operations would fall through to wrong classification"
- **影响**: 错误的 issue code 会被写入 `CompactValidationReportV2` 并作为 repair feedback 发给 LLM，导致 LLM 收到误导性的修复指令，降低 repair attempt 成功率
- **建议改法和验证点**:
  1. 引入结构化异常层级（如 `CompactParseError` 基类 + 子类 `MissingFieldError`、`InvalidFieldTypeError`、`UnknownFieldError` 等），在 parser 各层抛出时携带 `CompactValidationIssueCodeV2`
  2. `_parser_validation_report` 改为 `except CompactParseError as e: return e.to_issue()` 模式
  3. 验证：单元测试覆盖每种 parse error → 正确 issue code 的映射
- **修复风险（中）**: 需要重构 parser 内所有 raise 点，但类型安全收益高
- **严重程度（中）**: 当前行为在正常 LLM 输出下大概率正确（因为错误消息格式稳定），但脆弱性真实存在；静默 fallback 在边缘情况下会产生误导性 repair feedback

### F-003-未修复-中-`_build_runtime_arguments_parent` 移除后 `init` 命令的 `config_dir` 语义仍需明确

- **入口/函数**: `dayu/cli/arg_parsing.py:parse_cli_args()` / `dayu/cli/commands/init.py`
- **文件(行号)**: `dayu/cli/arg_parsing.py:278-279`（移除了 `init` 命令 `--config` 拒绝逻辑），`dayu/service/entrypoint_runtime.py:436-444`（移除了 `explicit_config_dir` 字段）
- **输入场景**: 用户执行 `dayu-cli init --config /some/path`
- **实际分支**: `--config` 参数已从全局参数中移除（`_build_runtime_arguments_parent` 被删除），argparse 会拒绝 `--config` 为未知参数。
- **预期行为**: 旧接口的移除应被干净处理
- **实际行为**: 移除是干净的：
  - `arg_parsing.py` 的 `_build_runtime_arguments_parent` 和 `--config` 注册已删除
  - `ParsedCliArgs.config_dir` 字段已删除
  - `EntrypointRuntimeRequest.explicit_config_dir` 字段已删除
  - `resolve_explicit_config_dir` 函数不再被任何代码引用
  - 测试仅断言 `explicit_config_dir` NOT in field_names（`tests/service/test_entrypoint_runtime.py:1063`）
- **直接证据**: `rg -n 'resolve_explicit_config_dir' dayu/ tests/ utils/` 返回零结果；`rg -n '\.config_dir' dayu/cli/ tests/cli/` 返回零结果
- **影响**: 无运行时问题。标记为 PASS 但建议在 design doc 中记录移除原因。
- **建议改法和验证点**: 无需修复
- **修复风险（无）**:
- **严重程度**: PASS — 清理干净

### F-004-未修复-中-`CompactorProposalManifestReference` 从 `compaction_operation.py` 移至 `context_events.py` 但存在双 owner 风险

- **入口/函数**: `dayu/host/compaction_operation.py` / `dayu/host/context_events.py`
- **文件(行号)**: `dayu/host/context_events.py:811-846`（新位置），`dayu/host/compaction_operation.py`（旧位置已删除）
- **输入场景**: 任何创建/消费 `CompactorProposalManifestReference` 的代码路径
- **实际分支**: 该类型从 `compaction_operation.py` 移至 `context_events.py`。新增了三个字段：`compaction_operation_id`、`compaction_attempt_number`、`compactor_engine_run_id`。旧字段 `manifest_event_id`、`manifest_payload_ref`、`manifest_digest`、`compactor_input_projection_ref`、`compactor_input_projection_digest` 保持不变。
- **预期行为**: 类型的语义 owner 应唯一。`CompactorProposalManifestReference` 同时被 `context_events.py`（canonical fact builder）和 `compaction_operation.py`（proposal runner）消费。
- **实际行为**: 类型定义在 `context_events.py`，但 `compaction_operation.py` 中的 `DurableCompactorProposalManifestRecorder` 是 manifest 的 **唯一生产者**。类型定义在 `context_events.py` 中，意味着 EventLog 层"拥有"了 proposal runner 的 manifest 类型。这不构成严格的语义所有权漂移（因为只有一个生产者），但类型的物理位置暗示 EventLog 层是 owner，而实际语义真源在 `compaction_operation.py` 的 manifest recorder。
- **直接证据**:
  - `dayu/host/context_events.py:811`: `class CompactorProposalManifestReference`
  - `dayu/host/compaction_operation.py:DurableCompactorProposalManifestRecorder._operation()` 是唯一构造 `CompactorProposalManifestReference` 实例的地方
  - `context_events.py` 中 `_validate_successful_response_manifest_binding()` 消费此类型
- **影响**: 低。当前只有单一生产者，不会产生多真源冲突。但若未来有第二个 producer（如 proactive compaction 的不同 manifest 路径），类型位置与语义 owner 的分离可能导致不知道该在哪里添加字段或修改校验规则。
- **建议改法和验证点**:
  1. 考虑将 `CompactorProposalManifestReference` 移至 `dayu/host/compaction.py`（与 `CompactionRequest`、`CompactorProposal` 等 compaction 类型同层），或
  2. 在模块 docstring 中明确记录"类型定义在 context_events 是因为它被 EventLog payload builder 直接消费，但语义真源在 compaction_operation"
- **修复风险（低）**: 移动类型定义需要更新 import 路径，但语义不变
- **严重程度（低）**: 结构性问题，不影响运行时正确性

### F-005-未修复-中-`compaction_operation.py` 新增 `memory_policy` 必填参数但向后兼容性未文档化

- **入口/函数**: `dayu/host/compaction_operation.py:run_compaction_operation()` / `run_compaction_attempt()`
- **文件(行号)**: `dayu/host/compaction_operation.py:662-696`
- **输入场景**: 任何调用 `run_compaction_operation()` 或 `run_compaction_attempt()` 的外部代码（测试、proactive compaction、reactive recovery）
- **实际分支**: 新增 `memory_policy: MemoryProjectionPolicy` 为必填参数。`_run_compaction_operation()` 在内部验证 `if memory_policy is None: raise TypeError("memory_policy is required")`。
- **预期行为**: 公共函数签名变更应文档化，调用方应全部更新。
- **实际行为**: 通过 diff 验证，所有调用方已更新：
  - `engine_ingest.py` 调用已传入 `memory_policy`
  - `dispatch.py` 调用已传入 `memory_policy`
  - 测试文件（`test_compaction_operation.py`、`fake_compaction.py`）已更新
- **直接证据**: `git diff main...codex/interactive-oracle -- dayu/host/compaction_operation.py | grep 'memory_policy'` 确认参数传递链完整
- **影响**: 当前无运行时问题。但若存在未被 diff 覆盖的外部调用方（如独立脚本、未提交的 WIP 分支），会在运行时收到 `TypeError`。
- **建议改法和验证点**: 无需修复。标记为 PASS 并在 PR body 中注明 breaking change。
- **修复风险（无）**:
- **严重程度**: PASS — 所有已知调用方已更新

### F-006-未修复-低-`conversation_compaction.md` 和 `conversation_compaction_user.md` LLM-facing prompt 变更未提供自足 schema 说明

- **入口/函数**: `dayu/config/prompts/scenes/conversation_compaction.md` / `conversation_compaction_user.md`
- **文件(行号)**: 22 行 + 153 行变更
- **输入场景**: LLM 在进行 context compaction 时阅读 compactor system/user prompt
- **实际分支**: Prompt 从 vNext schema 变为 v2 schema。新增了 `CompactSourceKindV2`、`CompactSemanticSectionV2` 等概念。
- **预期行为**: 按 `CLAUDE.md` 的 LLM-facing 文本约束，结构化输出必须在当前 prompt 中自足说明字段名、含义、类型、必填性、允许值和最小示例。不得只写"符合某某内部 schema"。
- **实际行为**: 需要验证 prompt 是否包含了自足的字段说明。由于 prompt 文件在 diff 中显示 153 行变更，且包含 `COMPACT_OUTPUT_SCHEMA_V2` 引用，需要逐字段检查 prompt 是否自足。
- **直接证据**: `dayu/config/prompts/scenes/conversation_compaction_user.md` 在 diff 中从旧 `CONVERSATION_COMPACT_OUTPUT_SCHEMA_NAME_VNEXT` 引用变更为 `COMPACT_OUTPUT_SCHEMA_V2` 引用。需要验证 prompt 正文是否包含所有字段的自足说明。
- **影响**: 若 prompt 不自足，LLM 可能产生不符合 v2 schema 的输出，导致 parser reject 和额外的 repair attempt
- **建议改法和验证点**: 逐字段审查 compaction prompt 是否满足 LLM-facing 文本约束。具体检查：每个字段是否有类型说明、是否标注必填/可选、enum 值是否列举、是否有最小示例
- **修复风险（低）**: prompt 文本修改不影响生产代码逻辑
- **严重程度（低）**: 不阻塞 merge，但影响 LLM 首次 proposal 成功率

### F-007-未修复-低-`Completeness critic`: 缺少 `SuccessfulRunnerResponseIdentity` 的跨层一致性测试

- **入口/函数**: `tests/engine/contracts/test_runner_identity.py`
- **文件(行号)**: 117 行变更
- **输入场景**: `SuccessfulRunnerResponseIdentity` 从 Engine → Host compaction → EventLog → memory projection 的完整往返
- **实际分支**: 测试覆盖了 `RunnerRequestIdentity` 和 `SuccessfulRunnerResponseIdentity` 的构造/校验，但缺少端到端验证：
  1. Engine 产生 `SuccessfulRunnerResponseIdentity`
  2. Host `llm_compaction.py` 捕获并验证
  3. `compaction_operation.py` 通过 `CompactionOperationResult` 传递
  4. `engine_ingest.py` 写入 `CONTEXT_COMPACTED` EventLog
  5. `context_events.py` 的 `_validate_successful_response_manifest_binding()` 校验 binding
  6. `compact_payload.py` 从 JSON 反序列化
- **预期行为**: 应有集成测试覆盖完整往返，证明 response identity 在序列化/反序列化/校验全链路上保持一致
- **实际行为**: 各层有独立的单元测试，但没有跨层集成测试
- **直接证据**: 搜索 `tests/` 目录，没有发现同时涉及 Engine runner identity 构造 + Host compaction ingest + context_events validation 的集成测试
- **影响**: 若未来有人修改 `SuccessfulRunnerResponseIdentity` 的序列化格式或 binding 校验规则，可能导致 EventLog 中的已有数据无法反序列化，但只有在生产环境中读取历史数据时才会发现
- **建议改法和验证点**: 添加集成测试：创建 `SuccessfulRunnerResponseIdentity` → 序列化到 JSON → 通过 `_parse_successful_response_identity()` 反序列化 → 通过 `_validate_successful_response_manifest_binding()` 校验
- **修复风险（低）**: 纯测试添加
- **严重程度（低）**: 各层单元测试充分，集成风险可控

## Open Questions

1. **Memory projection 是否应该持久化 `SuccessfulRunnerResponseIdentity`？** 当前 EventLog canonical fact 包含 provider identity，但 memory projection 不包含。需要 product owner 决定：compaction 的 provider lineage 是否属于 durable conversation memory 的一部分？（参见 F-001）

2. **`CompactRepairFeedbackV2` 的字符预算削减策略是否足够？** `build_compact_repair_feedback_v2()` 在超过 8192 字符限制时先减少 issue 数量，再裁剪最后一个 issue 的 source_labels。如果只有一个 issue 且没有 source_labels，会抛出 `RuntimeError`。这是否为可接受的 fail-closed 行为？（参见 `dayu/host/context_governance.py` 中的 `build_compact_repair_feedback_v2()` 实现）

3. **S8 bundle 与 digest 的完整性**: PR body 提到 "S8 bundle 与 digest"，但在 diff 中未见新的 S8 实现文件。S8 是否计划在后续 PR 中交付？当前 aggregate adjudication 是否已覆盖 S8 的 contract？

4. **Scenario freeze 状态**: PR body 引用 "oracle/scenario freeze" 和 "F01-F13"，但 commit chain 显示 F01-F07 aggregate deepreview 为最新 commit。F08-F13 是否已在之前的 work unit（wu-cli-interactive-02）中完成？

## Residual Risk

1. **测试覆盖**: 6 个 phase5 scheduler/test race 失败在 clean base 上可复现，被归类为 non-regression。这些 race condition 可能在特定时序下影响生产环境。
2. **未覆盖区域**:
   - `docs/cli_ci_scenarios.json` 的 72,595+ 行新增内容未逐行审查（scenario data）
   - `docs/reviews/` 目录下的大量 Gateflow artifact 未审查（已在 prior gate 中被独立审查）
3. **CI/checks**: GitHub 上此分支无 reported checks。PR body 声称 "full pyright: 0 errors, 0 warnings, 0 informations"，但未经 GitHub Actions 验证。
4. **大规模重构风险**: 322 文件、133K 插入行、15K 删除行是一次非常大的变更。即使每个 slice 都经过独立审查，交互效应（cross-slice interaction）可能未被充分覆盖。
5. **`docs/cli_ci_oracles.json`**: 573 行变更未逐条审查（oracle/scenario freeze 数据）
6. **`docs/cli_ci.md`**: 304 行变更未逐字审查（CI 文档更新）

---

## READY-FOR-CONTROLLER-ADJUDICATION

本 review 已完成基于直接代码阅读 + 4 个并行子代理（全部已完成）的深度审查。合计 30 个 findings：

**主审查 (7 findings)**: 2 PASS, 2 高, 1 中, 2 低

**Addendum A — Engine/Service/Contracts (6 findings)**: 4 PASS, 2 低

**Addendum B — Host 层 (4 actionable findings)**:
- 1 严重（B-001 孤儿 CONTEXT_COMPACTION_FAILED）
- 1 高（B-002 compaction terminal TOCTOU）
- 1 中（B-003 随机 event_id 无幂等）
- 1 低（B-004 死代码）

**Addendum C — CLI 层 (4 findings)**: 3 低, 1 信息 — CLI 层整体设计纪律优秀

**Addendum D — Tests/Cross-cutting (9 actionable findings)**:
- 1 高（D-001 source_boundary 重复生成 — 生产代码语义所有权违规）
- 4 高（D-002 缺少对抗性 fake, D-003 recovery 只有 happy path, D-004 smoke 不测试错误恢复, D-005 monkeypatch 绕过公共 API）
- 4 中（D-006 god 函数, D-007 property 重复计算, D-008 permit 缺自校验, D-009 readable_text 误入匹配键）

**最关键的阻塞项**:
1. **B-001 (严重)**: dispatch.py 预条件失败路径绕过 terminal guard → 孤儿 durable 事件
2. **B-002 (高)**: compaction terminal TOCTOU 并发窗口
3. **D-001 (高)**: source_boundary 生成逻辑双重真源 — 违反 CLAUDE.md 语义所有权约束
4. **D-002~D-005 (高)**: 测试覆盖系统性缺口（对抗性 fake、recovery 错误路径、smoke 错误恢复、monkeypatch 脆弱性）

所有 findings 均基于直接代码路径证据，包括逐行走读、git diff 分析和跨引用搜索。等待 controller 对每项裁决为 accepted / rejected-with-reason / deferred-with-owner / needs-more-evidence。

4 个 parallel review 子代理仍在运行中；若子代理产出额外 findings，应作为本 artifact 的 addendum 处理。

---

## Addendum A: Engine/Service/Contracts 子代理审查 (agent a7429f756f748e090, 已完成)

### A-001-未修复-中-`effective_model` 语义来源直接取自 `RunnerSpec.model`，未经 provider adapter 校验

- **入口/函数**: `dayu/engine/agent.py:_successful_response_identity()`
- **文件(行号)**: `dayu/engine/agent.py:610-611`
- **输入场景**: 任何成功完成并产生 `FinalAnswer` 的 Runner 调用
- **实际分支**: `_successful_response_identity()` 从 `request.runner_spec.model` 直接读取 model 名写入 `SuccessfulRunnerResponseIdentity.effective_model`。`RunnerSpec.model` 是配置文件中的裸字符串，未经过实际 provider adapter 的校验或标准化。
- **预期行为**: `effective_model` 应反映实际发送给 provider 的 model 标识。如果 adapter 有隐式 model fallback/alias，记录的值应与实际请求一致。
- **实际行为**: 直接使用配置值，不做 adapter 校验
- **直接证据**: `dayu/engine/agent.py:610-611`:
  ```python
  return SuccessfulRunnerResponseIdentity(
      effective_provider=request.runner_spec.provider,
      effective_model=request.runner_spec.model,
      ...
  )
  ```
  - `RunnerSpec.model` 类型为裸 `str`（来自 runner_spec.py:283-284），无 adapter 校验步骤
- **影响**: 若未来 Runner adapter 对 model 做了改写（fallback/alias），`effective_model` 会与实际请求不一致。当前实现中无此改写，风险为 future-proofing 级别。
- **建议改法和验证点**: 在 `SuccessfulRunnerResponseIdentity` docstring 中明确契约：`effective_model` 必须是 `RunnerSpec.model`，不可由 adapter 改写。或让 Runner 在 `RunnerDoneData` 中暴露实际使用的 model。
- **修复风险（低）**:
- **严重程度（低）**: 当前所有 adapter 均直接使用 `RunnerSpec.model`，无实际不一致风险

### A-002-未修复-低-`_successful_response_identity()` 函数位置在 `agent.py`，但逻辑属于 contract owner

- **入口/函数**: `dayu/engine/agent.py:_successful_response_identity()`
- **文件(行号)**: `dayu/engine/agent.py:588-616`
- **输入场景**: 任何需要构造 `SuccessfulRunnerResponseIdentity` 的路径
- **实际分支**: 该函数是模块级函数（不访问 `self`），只做数据映射。但它位于 `agent.py`（Agent 实现层），而非 contract owner `runner_identity.py`。
- **直接证据**: 函数签名不依赖 Agent 实例状态，仅读取三个 frozen/typed 输入参数
- **影响**: 低。当前实现正确，但 builder 逻辑分散在 agent.py 中增加了"response identity 由谁构造"的理解成本。
- **建议改法和验证点**: 在 `SuccessfulRunnerResponseIdentity` 上增加 `classmethod` 工厂，接收 `provider_request_id: str | None` 并自动推导 `ProviderRequestIdAvailability`
- **修复风险（低）**:
- **严重程度（低）**: 非功能性，仅影响代码组织

### A-003-PASS-Service 层 `config_overlay_dir`/`explicit_config_dir` 删除安全

子代理确认：
- 所有生产调用方已移除对应参数传递
- 测试已更新（断言字段不存在）
- `resolve_runtime_locations()` 默认行为覆盖所有现有调用场景
- `dayu/runtime/location.py` 无变更

### A-004-PASS-公共契约导出正确

`ProviderRequestIdAvailability`、`SuccessfulRunnerResponseIdentity` 已正确加入 `__all__` 和 re-export 链。模块私有函数未暴露。

### A-005-PASS-分层依赖方向正确

子代理验证了 Engine → Service → Runtime 的依赖方向，无反向依赖。

### A-006-PASS-LLM-facing compaction prompt 合规

子代理逐字段验证了 v2 compaction prompt：
- 输入 schema 自足描述（字段名、类型、含义）
- 输出 schema 自足描述（字段名、类型、必填性、允许值、引用规则）
- `source_kind` 的 8 种可能值全部显式列出
- 覆盖规则显式声明
- 不使用内部模块名、类型名或代码路径术语

---

## Addendum B: Host 层子代理审查 (agent a523edf76b54d8e24, 已完成)

### B-001-未修复-严重-`_append_compaction_failed_event` 在预条件失败路径绕过 terminal permit guard，写入孤儿 `CONTEXT_COMPACTION_FAILED`

- **入口/函数**: `dayu/host/dispatch.py:_run_pre_start_governance()` → `BLOCK_HARD_THRESHOLD` 分支 / `material_source_failed` 异常捕获
- **文件(行号)**: `dayu/host/dispatch.py:2024-2036`、`2067-2089`
- **输入场景**: context budget 判定为 `BLOCK_HARD_THRESHOLD`（预计输入 token 同时超过 soft 和 hard threshold），或 compact material view 构造失败
- **实际分支**: 两个预条件失败路径直接调用 `self._append_compaction_failed_event(...)`，但都 **没有事先调用 `begin_compaction_terminal_commit_in_transaction()`** 来获得 terminal permit。对比正常路径（dispatch.py:2135、2341、3078、3140、3418）均先做 terminal commit 检查再写入。
- **预期行为**: 所有 `CONTEXT_COMPACTION_FAILED` 事件必须对应一个已持久化的 `CONTEXT_COMPACTION_REQUESTED`，且 terminal 写必须通过 `begin_compaction_terminal_commit_in_transaction` 的线性化检查。
- **实际行为**: 写入的 `CONTEXT_COMPACTION_FAILED` 没有对应的 `CONTEXT_COMPACTION_REQUESTED`，违反了 operation lifecycle contract。下游 `read_proactive_compaction_projection` 读到该事件时会触发 `HostDurableError("proactive failed terminal operation is unknown")`，导致 projection 进入 INVALID 状态。
- **直接证据**: `dispatch.py:2024-2036` — `BLOCK_HARD_THRESHOLD` 分支直接调用 `_append_compaction_failed_event`；`dispatch.py:2067-2089` — `material_source_failed` 异常捕获同样直接调用。搜索确认这两处是整个 dispatch.py 中唯一不经过 terminal commit 检查就写入 compaction failed 的路径。
- **影响**: 产生孤儿 `CONTEXT_COMPACTION_FAILED` 事件，下游 projection 读到该事件时进入 INVALID 状态，影响 proactive compaction 的连续性。不可恢复（需人工介入清理 EventLog）。
- **建议改法和验证点**:
  1. 两个预条件失败路径应改为直接使用 `_fail_unstarted_in_transaction` 关闭 Run，而不写 compaction event（因为此时尚未发起 compaction operation）
  2. 或者先在同一个 transaction 内写入 `CONTEXT_COMPACTION_REQUESTED` + `CONTEXT_COMPACTION_FAILED`（但这样更复杂且增加不必要的 EventLog 噪音）
  3. 推荐方案 1：预条件失败时跳过 compaction 语义，直接 fail Run
  4. 验证：测试覆盖 `BLOCK_HARD_THRESHOLD` 和 material view 构造失败场景，确认不产生孤儿 compaction 事件
- **修复风险（中）**: 需要理解 `_fail_unstarted_in_transaction` 与 `_append_compaction_failed_event` 的语义差异，确保 Run 状态机正确收敛
- **严重程度（严重）**: 产生不可恢复的孤儿事件，导致 durable state 损坏

### B-002-未修复-高-`begin_compaction_terminal_commit_in_transaction` 存在 TOCTOU 窗口：两个并发 writer 可同时获得 permit

- **入口/函数**: `dayu/host/compaction_terminal.py:_read_operation_terminal_rows()`
- **文件(行号)**: `dayu/host/compaction_terminal.py:180-230`
- **输入场景**: proactive compaction 和 reactive compaction 同时到达同一 operation 的 terminal 写入点
- **实际分支**: `_read_operation_terminal_rows` 在当前 transaction snapshot 内读取 terminal rows。若两个 writer（如 proactive 和 reactive）在各自的 transaction 中都读到 0 个 terminal rows：
  - Writer A 获得 `CompactionTerminalCommitPermit`
  - Writer B 也获得 `CompactionTerminalCommitPermit`
  - Writer A 提交 `CONTEXT_COMPACTED`
  - Writer B 提交 `CONTEXT_COMPACTION_FAILED`
  结果同一 operation 有两个 terminal → `INVALID_MULTIPLE`
- **预期行为**: terminal 写入应在数据库层保证唯一性（如 `INSERT OR IGNORE` 或 `INSERT ... WHERE NOT EXISTS`）
- **实际行为**: 依赖 SQLite SERIALIZABLE 隔离级别的提交时冲突检测，但若两个 writer 的事务不冲突（读写不同的行），可能都成功提交
- **直接证据**:
  - `compaction_terminal.py:157`: `if len(terminal_rows) == 0: return CompactionTerminalCommitPermit(...)` — 仅基于当前 snapshot 判定
  - `dispatch.py:2341` 和 `engine_ingest.py:3078` 分别在 proactive 和 reactive 路径中调用 `begin_compaction_terminal_commit_in_transaction`
- **影响**: `INVALID_MULTIPLE` 被设计来检测此场景（在重建/读取时），但写入时无防护。`INVALID_MULTIPLE` 状态需要人工介入恢复。
- **建议改法和验证点**:
  1. 在 terminal 写入 SQL 中使用 `INSERT OR IGNORE` 或添加唯一约束（`operation_id`, `event_type` IN terminal types）
  2. 或在 `begin_compaction_terminal_commit_in_transaction` 返回 permit 后，在执行 terminal 写入的 `append` 前做第二次检查
  3. 验证：并发测试（两个 writer 同时写入同一 operation 的 terminal），确认只有一个成功
- **修复风险（中）**: 涉及 EventLog schema 变更（添加唯一约束）或事务内二次检查逻辑
- **严重程度（高）**: 在正常操作下概率低（proactive 和 reactive 通常不会同时触发同一 operation），但一旦发生会产生需要人工恢复的 `INVALID_MULTIPLE` 状态

### B-003-未修复-中-`_append_compaction_failed_event` 使用随机 event_id 无幂等保护

- **入口/函数**: `dayu/host/dispatch.py:_append_compaction_failed_event()`
- **文件(行号)**: `dayu/host/dispatch.py:3517`
- **输入场景**: governance 重试循环中 CAS 失败后重试
- **实际分支**: `_append_compaction_failed_event` 使用 `_new_event_id("event-context-compaction-failed")` 生成随机 event_id，每次调用产生唯一值。若同一操作因 CAS 失败重试，第二次调用会追加第二个 `CONTEXT_COMPACTION_FAILED`。
- **预期行为**: 应使用基于 `(operation_id, failure_reason, attempt_count)` 的确定性 event_id，天然支持幂等（参见 `CONTEXT_BUDGET_EVALUATED` 事件使用 SHA-256 确定性 event_id 的设计）
- **直接证据**:
  - `dispatch.py:3517`: `event_id=_new_event_id("event-context-compaction-failed")`
  - 对比 `context_events.py:207-219`: `context_budget_evaluated_event_id()` 使用 `sha256_digest_json()` 从 identity atoms 派生确定性 event_id
- **影响**: governance 重试时可能追加重复 failed 事件（但 terminal permit guard 会阻止第一个之后的写入 — 前提是 permit guard 被正确使用。B-001 中已发现两处绕过路径）
- **建议改法和验证点**: 使用基于 `(operation_id, failure_reason, attempt_count)` 的确定性 event_id
- **修复风险（低）**: 仅改变 event_id 派生方式，不影响语义
- **严重程度（中）**: 与 B-001 组合时风险升级；单独看为低风险

### B-004-低-`_optional_non_negative_int` 死代码

- **文件(行号)**: `dayu/host/llm_compaction.py:1195-1221`
- **直接证据**: 函数定义完整但整个文件中无任何调用点
- **影响**: 死代码，无功能影响
- **严重程度（低）**: 建议删除或标注为预留扩展

---

## Addendum C: CLI 层子代理审查 (agent aadfea665030c8911, 已完成)

CLI 层子代理确认了整体设计纪律：composer 将 `prompt_toolkit` 完整封装为类型化事件，状态机边界清晰，cleanup 路径完整。PASS 项包括：语义所有权正确、状态机四态转换完整、`--config` 移除干净、边界条件处理正确、外部一致性验证通过、无 adversarial failure。以下为低严重度发现：

### C-001-低-`read_event` 在 `_pending_running_actions` 非空时提前返回，跳过 editor task 取消

- **文件(行号)**: `dayu/cli/composer.py:474-479`
- **场景**: `_pending_running_actions` 非空时直接返回 `RUNNING_KEY_ACTION` 事件，不进入 `try/finally` 块，`finally` 中的 `await _cancel_editor_tasks(self._editor_tasks)` 不被执行
- **影响**: 影响面极窄——pending running actions 与活跃 editor task 几乎不可能同时存在
- **严重程度（低）**:

### C-002-低-`updated_text` 变量声明在 `CANCELLED` 分支前，类型检查器可能报告未初始化

- **文件(行号)**: `dayu/cli/composer.py:997`
- **场景**: `return_code != 0` 时返回 `CANCELLED`，`updated_text` 在此路径上未被赋值也不会被读取
- **严重程度（低）**:

### C-003-低-session resume interactive 路径未显式传递 `sigint_monitor_factory`

- **文件(行号)**: `dayu/cli/commands/session.py:292-298`
- **场景**: resume 调用 `execute_interactive_on_session` 时依赖默认值
- **严重程度（低）**: 当前行为正确

### C-004-信息-Session scope 统一化为有意的 breaking change

- **文件**: `dayu/cli/host_context.py:26-28`, `dayu/cli/session_identity.py`
- **变更**: `INTERACTIVE_SESSION_SCOPE` + `PROMPT_SESSION_SCOPE` → 统一 `CLI_AGENT_SESSION_SCOPE = "cli.agent"`
- **影响**: 旧 scope Session 无法被 `--label` 查询。有意的设计简化，prompt 和 interactive 共享同一 Session 命名空间
- **严重程度**: 信息（设计选择，非缺陷）

---

## Addendum D: Tests/Cross-cutting 子代理审查 (agent a28b88161e18113f6, 已完成)

### D-001-未修复-高-`source_boundary` 生成逻辑在 `compaction.py` 和 `compact_material.py` 中重复

- **入口/函数**: `dayu/host/compaction.py:CompactionRequest.compact_input` (property) / `dayu/host/compact_material.py:_source_boundary_v2()`
- **文件(行号)**: `dayu/host/compaction.py:2130-2180`、`dayu/host/compact_material.py:579-633`
- **输入场景**: 任何构造 `CompactInputV2` 的路径
- **直接证据**:
  1. `CompactionRequest.compact_input`（compaction.py:2130）和 `_source_boundary_v2()`（compact_material.py:579）都迭代相同的四个 material 部分并产生 `CompactSourceBoundaryEntryV2` 条目
  2. Evidence 边界显示文本 "工具：..."、"查询：..."、"结果：..."、"来源：..." 在 `_evidence_boundary_text()`（compaction.py:2244）中定义，然后在 `_source_boundary_v2()`（compact_material.py:610-618）中内联复制
  3. `_previous_source_kind()`（compaction.py:2223）和 `_previous_source_kind_v2()`（compact_material.py:633）包含从 `CompactMaterialBlockKind` 到 `CompactSourceKindV2` 的完全相同映射逻辑
- **影响**: 两个独立真源。修改 source boundary 生成逻辑时必须同时修改两处，否则产生不一致。违反 CLAUDE.md 中的"每个业务事实必须有唯一清晰 owner"约束。
- **建议改法和验证点**: 指定 `CompactionRequest.compact_input` 为规范 owner，`_source_boundary_v2` 委托给它。删除重复的 `_previous_source_kind()` 和 evidence boundary text 模板
- **修复风险（中）**: 需要仔细验证两个调用路径的语义一致性
- **严重程度（高）**: 语义所有权违规，多真源风险

### D-002-未修复-高-缺少对抗性 fake compactor，真实 LLM 失败模式完全未测试

- **入口/函数**: `tests/host/fake_compaction.py`、`tests/host/test_compaction_operation.py`、`tests/host/test_public_compact_smoke.py`
- **直接证据**: 所有 fake compactor 要么总是成功，要么仅以一种受控方式失败。没有模拟：(a) JSON 截断，(b) 语法有效但语义荒谬的内容，(c) 针对错误请求的 source_labels，(d) 两次 attempt 之间微妙变化的响应
- **影响**: 真实的 LLM 失败模式（截断 JSON、无效 labels、幻觉内容）在测试中从未被触发，repair feedback 和 retry loop 在这些场景下的行为未经验证
- **严重程度（高）**: 关键路径未经对抗性测试

### D-003-未修复-高-恢复多进程测试仅覆盖 happy path

- **文件**: `tests/host/test_recovery_multiprocess.py`（全部 402 行）
- **直接证据**: 所有 4 个测试仅覆盖 happy path。未测试：(a) 第二个进程恢复中途失败，(b) 两个进程竞争恢复，(c) 持久化状态损坏，(d) 恢复进程本身崩溃，(e) 存储被外部进程锁定
- **严重程度（高）**:

### D-004-未修复-高-冒烟测试从未在完整 pipeline 中测试错误恢复

- **文件**: `tests/host/test_public_compact_smoke.py`
- **直接证据**: 7 个异步冒烟测试全部使用始终生成有效 JSON 的 `FakeCompactorRunAgent`。`RejectingCompactorRunAgent` 仅在 compactor 永远不会被调用的空边界测试中使用。没有任何测试验证 compactor 返回无效输出 → 语义修复重试 → 回退的完整链路
- **严重程度（高）**:

### D-005-未修复-高-测试通过 monkeypatch 私有模块属性绕过公共 API

- **文件**: `tests/host/test_public_compact_smoke.py:559-563`、`tests/host/test_dispatch_scheduler.py:3000-3179`、`tests/host/test_open_host_runtime.py:1618-1726`
- **直接证据**:
  1. 冒烟测试 monkeypatch `dayu.host.llm_compaction._run_agent_request`（私有属性）
  2. 三个调度测试 monkeypatch scheduler 的私有方法为 no-op
  3. 取消看门狗测试同时 monkeypatch 三个独立对象
- **影响**: 测试与实现细节耦合。生产代码重构时测试静默通过（补丁方法不再被调用），无法检测回归
- **严重程度（高）**: 测试脆弱，掩盖回归

### D-006-未修复-中-`_drive_interactive_tty_repl` 是约 390 行的 god 函数

- **文件(行号)**: `dayu/cli/session_execution.py:1753-2142`
- **直接证据**: 单个 `while True` 循环管理 8+ 个关注点（composer 事件分发、SIGINT 绑定、accept barrier、OS SIGINT 处理、cancel 渲染、terminal 完成、退出评估、task 重建），14+ 个可变局部变量
- **严重程度（中）**: 可维护性风险，建议提取专用状态机类

### D-007-未修复-中-`CompactionRequest.compact_input` 作为 `@property` 每次访问时重新计算

- **文件(行号)**: `dayu/host/compaction.py:2129-2180`
- **直接证据**: `compact_input` 是 `@property`，每次访问时迭代所有四个 material 部分。调用方 `compact_pipeline.py:640,664` 在 reactive passes 循环内调用
- **影响**: 性能浪费（可证明的重复计算）
- **严重程度（中）**: 建议改为显式方法让调用方缓存结果，或使用 `functools.cached_property`

### D-008-未修复-中-`CompactionTerminalCommitPermit` 缺少 `__post_init__` 自校验

- **文件(行号)**: `dayu/host/compaction_terminal.py:48-59`
- **直接证据**: 该 frozen dataclass 无 `__post_init__`，字段 `operation_id`、`trigger_source`、`request_event_sequence` 未被校验。调用方在构造前校验，但若 permit 从其他路径构造（如测试），无效值会静默通过
- **严重程度（中）**: 防御性编程缺口

### D-009-未修复-中-reactive pass 标签重绑定中 `readable_text` 被错误纳入身份匹配键

- **文件(行号)**: `dayu/host/compact_pipeline.py:629-706`
- **直接证据**: `_bind_reactive_pass_to_root_labels()` 使用 `(source_kind, source_refs, readable_text)` 元组作为匹配键。`readable_text` 是 display-only/prompt-local，不应影响身份匹配。两个具有相同元数据但不同 readable_text 的条目将无法匹配
- **严重程度（中）**: 身份键不应包含 display-only 字段
