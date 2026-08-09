# Code Review

## Scope

- Mode: current changes
- Branch: codex/interactive-oracle
- Base: ce7ef846 (gateflow: close S5 utils identity closure)
- Head: current uncommitted workspace changes
- Reviewer/Provider: MiMo
- Output file: docs/reviews/code-review-wu-cli-interactive-02-s5-mimo-20260802.md
- Included scope: 53 files (13 production, 38 test, 2 utils) — all files in `git diff ce7ef846`
- Excluded scope: generated/vendor/build/cache files
- Parallel review coverage: 无

## Findings

### 001-未修复-低-`runner_identity.py` 的 `__all__` 未导出新增公共类型

- **入口/函数**: `dayu/engine/contracts/runner_identity.py:384`
- **文件(行号)**: `dayu/engine/contracts/runner_identity.py:384`
- **输入场景**: `from dayu.engine.contracts.runner_identity import *` 或依赖 `__all__` 做公共 API 发现的工具。
- **实际分支**: `__all__ = ["RunnerRequestIdentity", "build_runner_request_identity"]`
- **预期行为**: `__all__` 应包含模块内所有公共类型：`ProviderRequestIdAvailability`、`SuccessfulRunnerResponseIdentity`、`RunnerRequestIdentity`、`build_runner_request_identity`。
- **实际行为**: `ProviderRequestIdAvailability` 和 `SuccessfulRunnerResponseIdentity` 缺失。
- **直接证据**: `runner_identity.py:384` — `__all__ = ["RunnerRequestIdentity", "build_runner_request_identity"]`；`ProviderRequestIdAvailability` 定义于行 28，`SuccessfulRunnerResponseIdentity` 定义于行 93，均为 `@dataclass` 公共类型且被 `dayu/engine/contracts/__init__.py` 和 `dayu/engine/__init__.py` 显式 re-export。
- **影响**: 仅影响 `import *` 和 API 发现工具；所有实际 import 均为显式 named import，功能不受影响。属于文档/契约完整性缺陷。
- **建议改法和验证点**: 在 `__all__` 中添加 `"ProviderRequestIdAvailability"` 和 `"SuccessfulRunnerResponseIdentity"`。验证 `from dayu.engine.contracts.runner_identity import *` 能导入所有四个符号。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 002-未修复-低-`context_events.py` 的 `__all__` 未导出 `CompactorProposalManifestReference`

- **入口/函数**: `dayu/host/context_events.py:2146`
- **文件(行号)**: `dayu/host/context_events.py:2146`
- **输入场景**: `from dayu.host.context_events import *` 或依赖 `__all__` 做公共 API 发现的工具。
- **实际分支**: `__all__` 列表中无 `CompactorProposalManifestReference`。
- **预期行为**: `CompactorProposalManifestReference` 是从 `compaction_operation.py` 迁移到 `context_events.py` 的公共 dataclass，应出现在 `__all__` 中。
- **实际行为**: 未出现。
- **直接证据**: `CompactorProposalManifestReference` 定义于 `context_events.py:839`，被 `dispatch.py`、`engine_ingest.py`、`compaction_operation.py` 及11个测试文件显式 import。
- **影响**: 仅影响 `import *` 和 API 发现工具。功能不受影响。
- **建议改法和验证点**: 在 `__all__` 中添加 `"CompactorProposalManifestReference"`。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

- 无。

## Residual Risk

1. **phase5 六个 pre-existing scheduler race**: `test_phase5_local_execution_integration.py` 中6个测试在 base ce7ef846 上同样失败（已独立验证：`git stash` 后在 clean base 运行首个测试同样 `assert 0 == 1`）。S5 diff 不改变 timing、scheduler 或断言顺序。按 Controller 裁决，不在 S5 scope 内修复。

2. **awaiting smoke callback execution port 断裂**: clean HEAD 同样存在，不在 S5 scope。

3. **`__all__` 未更新**: 两个 finding 均为低严重程度的契约完整性问题，不影响功能。

## Adversarial Verification Summary

以下按 S5 review 指令的8个检查维度逐项报告：

### 1) Engine identity 来源与串线检查

**PASS**。`_successful_response_identity()` (`agent.py:588-616`) 从三个同源 facts 构造：`request.runner_spec.provider/model`（当前 AgentRunRequest）、`state.request_identity`（当前 iteration 的 RunnerRequestIdentity）、`runner_done.provider_request_id`（当前 call 的 provider 返回值）。identity 在 `_decide_final_answer()` 中一次性构造（`agent.py:1927-1931`），通过不可变 `_FinalDecision` dataclass 传递。normal final、content-filter、force-answer、LENGTH continuation exhausted、continuation merge 五条路径均透传同一个 `decision.response_identity`，不重新构造。LENGTH continuation 返回 `None` 进入下一轮时丢弃当前 identity（正确：下一轮将产生新 call 的新 identity）。

### 2) provider id availability 与 client correlation

**PASS**。`ProviderRequestIdAvailability` 与 `provider_request_id` 在 `SuccessfulRunnerResponseIdentity.__post_init__` 中严格配对校验（`runner_identity.py:135-153`）：PRESENT 要求非 None 非空，UNAVAILABLE 要求 None。`client_correlation_id` 由 `RunnerRequestIdentity.__post_init__` 重新计算 SHA-256 并与传入值比对（`runner_identity.py:75-89`）。durable 反序列化 `_parse_successful_response_identity()` 再次校验 canonical client correlation（`context_events.py:1774`）。provider/model 只从 `request.runner_spec` 取得，不从 provider response body 推断。

### 3) LLM compactor post-success LENGTH/parse/schema identity 保留

**PASS**。`LLMContextCompactor.run_prepared_compactor_proposal()` (`llm_compaction.py:305-361`) 在取得成功 Engine final 后立即调用 `_validated_prepared_response_identity()` 校验同源（run_id、attempt_id=None、execution_id=None、provider、model），然后在 LENGTH rejection（行344-347）、parse/schema rejection（行353-357）中均携带已校验的 `response_identity`。timeout（行330-333）和 no-final outcome（行335-338）设置 `successful_response_identity=None`。

### 4) operation A/B/C 多 attempt 不串线

**PASS**。`_run_compaction_operation()` (`compaction_operation.py:760-1060`) 的每个 proposal attempt 独立取得 `_CompactorProposalAttempt`，其中 `successful_response_identity` 来自该 attempt 的 `proposal.successful_response_identity`。accepted 赋值（行1002-1010）从当前 proposal 的 identity 同源赋值。manifest reference 由 `_record_compactor_proposal_manifest()` 在 provider call 前记录，并在行1260-1286校验 operation_id/attempt_number/compactor_engine_run_id 三者一致。`_validate_prepared_proposal_identity()` (`compaction_operation.py:1240-1286`) 在 proposal 返回后再次校验 Engine run、ordinary attempt/execution、provider/model 一致性。

### 5) durable accepted/rejected schema 与 fail closed

**PASS**。`CONTEXT_COMPACTED` 使用 `_require_exact_fields()` 校验（`context_events.py:1277`），`successful_response_identity` 为 required mapping。`CONTEXT_COMPACTION_ATTEMPT_REJECTED` 同样使用 `_require_exact_fields()`（行1591），`successful_response_identity` 为 required field（可为 null）。post-success rejection（quality_check_rejected、hard_threshold_after_compact）要求 identity 非 null（行1639-1643）；no-success rejection（cancellation_requested）要求 identity 为 null（行1646-1650）。identity nested object 使用 `_require_exact_fields()` 校验（行1744、1749），rejects extra fields。compactor identity 的 attempt_id/execution_id 必须为 null（行1752-1755）。

### 6) credential/secret/provider payload 泄漏

**PASS**。`_successful_response_identity_json()` (`context_events.py:1696-1730`) 只序列化：effective_provider（名称字符串）、effective_model（名称字符串）、runner_request_identity（run_id/attempt_id/execution_id/iteration_id/iteration_index/runner_call_index/client_correlation_id）、provider_request_id_availability、provider_request_id。不含 endpoint、URL、API key、Authorization header、cookie、secret、credential ref 或 provider request/response body。implementation report 声称扫描276个 JSON records 中敏感字段命中0。

### 7) 53-file scope、mechanical closure、无 default/compat/lazy import

**PASS**。实际 diff 为53文件（13 production +38 test +2 utils）。`CompactorProposalManifestReference` 从 `compaction_operation.py` 迁移到 `context_events.py`，旧定义已删除（grep 确认），所有13个 import 点指向新位置。`CompactorProposal` 和 `CompactorProposalError` 新增于 `compaction.py` 并加入 `__all__`。`SuccessfulRunnerResponseIdentity` 和 `ProviderRequestIdAvailability` 通过 `__init__.py` re-export。无 lazy import、无 compatibility seam、无 default value fallback。

### 8) tests、pyright、coverage

**PASS**（有条件）。pyright: 0 errors, 0 warnings。全量测试（排除 phase5）: 6516 passed。phase5: 6 failures 为 pre-existing（base ce7ef846 独立验证）。implementation report 声称所有13个 production 文件 coverage >= 80%。
