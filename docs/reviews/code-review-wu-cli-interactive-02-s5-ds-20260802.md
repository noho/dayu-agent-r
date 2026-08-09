# Code Review

## Scope

- **Mode**: current changes
- **Branch**: `codex/interactive-oracle`
- **Base**: `ce7ef846f7b8aac2d0b942bb487819fe0210b746` (accepted HEAD, same as current HEAD)
- **Head**: uncommitted workspace changes (54 modified files + 1 untracked implementation report)
- **Provider/Reviewer**: DeepSeek (AgentDS)
- **Output file**: `docs/reviews/code-review-wu-cli-interactive-02-s5-ds-20260802.md`
- **Diff scope**: 53 production/test/utils modified files, 4329 insertions, 392 deletions
- **Parallel review coverage**: 无 — 本次全部由主 reviewer 直接走读

### Included scope

全部 53 个 modified files（13 production + 7 Engine tests + 30 Host tests/support + 3 Service test/utils），覆盖 S5/F13 的完整 Engine → Host → durable event identity chain。

### Excluded scope

- `docs/reviews/gateflow-wu-cli-interactive-02-s5-implementation-codex-20260802.md`（untracked implementation report，只作为 reference 阅读，不 review 其内容）
- S1-S4、S6 未修改文件（不在 S5 diff 范围内）
- 未跟踪的临时 workspace 文件

### Required documents read

- `AGENTS.md`
- `docs/host/wu-cli-interactive-02-conformance-fixes-plan.md`（全文，含 S5/§9/§10.5/§13）
- `docs/reviews/gateflow-wu-cli-interactive-02-s5-durable-builder-amendment-final-adjudication-20260801.md`
- `docs/reviews/gateflow-wu-cli-interactive-02-s5-plan-amendment-final-adjudication-20260801.md`
- `docs/reviews/gateflow-wu-cli-interactive-02-s5-utils-closure-amendment-final-adjudication-20260802.md`
- `docs/reviews/gateflow-wu-cli-interactive-02-s5-implementation-codex-20260802.md`

### Validation evidence exclusion

Controller 通知并行 reviewer MiMo 在 full test suite 运行期间短暂 stash/pop 了工作树，虽已恢复但该次 full suite result（2955 passed, 6 failed）视为时序受污染，不作为本 artifact 证据。以下所有 validation 证据均来自后续稳定工作树重新运行：

- `python -m pyright dayu/ tests/ utils/` → 0 errors, 0 warnings
- S5 owner focused tests (18 files, 850 tests) → 850 passed
- 五类 pattern inventory checks → 精确匹配 27/8/2/6/33

## Findings

### 1-未修复-低-CompactorProposalManifestReference 从 compaction_operation 移至 context_events 引入循环依赖风险但实际未触发

- **入口/函数**: `dayu/host/context_events.py` — `CompactorProposalManifestReference` 定义
- **文件(行号)**: `dayu/host/context_events.py:838-868`
- **输入场景**: 模块加载时 `context_events.py` 被 import
- **实际分支**: `CompactorProposalManifestReference` 定义在 `context_events.py`，但 `compaction_operation.py`（原 owner）仍 import 该类型
- **预期行为**: `context_events.py`（durable event owner）拥有 manifest reference 类型，`compaction_operation.py` 从 context_events import
- **实际行为**: `compaction_operation.py` 通过 `from dayu.host.context_events import CompactorProposalManifestReference` 导入，与 `context_events.py` 自身对其他 Host 模块的 import 形成潜在循环
- **直接证据**: `dayu/host/compaction_operation.py:41` 执行 `from dayu.host.context_events import CompactorProposalManifestReference`；`context_events.py` 自身 import `dayu.host.compaction`（line 17）。Codex 报告 §2.2 声明此移动"解除了 context_events → compaction_operation → durable schema → api → memory → context_events 循环，未使用 lazy import"。经检查：当前 `compaction_operation.py` 不 import `context_events.py` 之外的 Host 模块，且 `context_events.py → compaction.py`（不是 `compaction_operation.py`）的 import 不经过 manifest reference 类型，因此循环确实未形成。但此依赖方向（durable event owner 的类型被 operation owner 消费）是微妙的架构决策，未来的 `compaction_operation.py` 变更可能重新引入循环。
- **影响**: 当前无实际影响；未来 `compaction_operation.py` 若增加对 `context_events.py` 间接依赖链上模块的 import，可能触发循环导入
- **建议改法和验证点**: 在 `compaction_operation.py` 的模块 docstring 或 manifest reference import 处添加注释，说明此 import 是单向的且 `CompactorProposalManifestReference` 的 semantic owner 是 `context_events.py`。若未来出现循环，应把 manifest reference 提取到独立的 `_compaction_manifest.py` 公共类型模块
- **修复风险（低）**: 仅添加注释，无行为变更
- **严重程度（低）**: 当前无实际循环，仅架构微风险

### 2-未修复-低-非 prepared compactor 路径缺少 prepared-level identity 交叉校验

- **入口/函数**: `dayu/host/compaction_operation.py` — `_prepare_compactor_proposal()`
- **文件(行号)**: `dayu/host/compaction_operation.py:1188-1193`（非 prepared 分支）
- **输入场景**: compactor 不实现 `CompactorProposalPreparedCompactor` 协议时走非 prepared 路径
- **实际分支**: `proposal = await compactor.compact(request, cancellation_token)` 成功后直接使用 `proposal.successful_response_identity`，不经过 `_validate_prepared_proposal_identity`
- **预期行为**: 非 prepared compactor 自行负责返回正确的同源 identity；operation 层不重复校验
- **实际行为**: 与 prepared 路径不同，非 prepared 路径没有 Engine run id / provider / model / attempt/execution 的交叉校验。如果非 prepared compactor 返回错配 identity（例如用相邻 Run 的 identity），operation 层会静默接受
- **直接证据**: `dayu/host/compaction_operation.py:1188-1193` — 非 prepared 分支只做 `proposal = await compactor.compact(request, cancellation_token)` 然后直接构造 `_CompactorProposalAttempt`，无 identity validation；对比 prepared 分支（line 1136-1166）有 `_validate_prepared_proposal_identity` 调用
- **影响**: 当前所有真实 compactor（`LLMContextCompactor`）都走 prepared 路径，`FakeContextCompactor` 也实现了 prepared 协议。仅当有自定义 compactor 不实现 prepared 协议且返回错配 identity 时才会触发。影响面极小
- **建议改法和验证点**: 可在 `ContextCompactor` 协议 docstring 中明确：`compact()` 返回的 `CompactorProposal.successful_response_identity` 必须与该次 invocation 的实际成功 Runner call 同源。当前设计已足够，因为 typed `CompactorProposal` 强制携带 identity
- **修复风险（低）**: 仅文档增强，无行为变更
- **严重程度（低）**: prepared 路径覆盖所有真实 compactor；非 prepared 路径仅用于 legacy/simple test doubles

## Open Questions

1. **utils smoke 的 awaiting entrypoint 测试 pre-existing 断裂**：Codex 报告 §8 指出 `smoke_host_public_awaiting_entrypoint.py` 在 `run_accepted` 前因 `callback_execution_port is required when callbacks are set` 失败，clean HEAD archive 同样失败。当前 diff 中该文件只含冻结 identity 机械变更，未触及 callback 路径。Controller 已将此分类为 pre-existing。问题是：此断裂是否需要在 S6 修复？当前不在 S5 scope。

2. **phase5 scheduler race 的根本原因**：6 个 `test_phase5_local_execution_integration.py` 失败（`drain.dispatched == 0` vs `1`）被 Controller 确认为 pre-existing。当前 diff 中 phase5 文件只含 identity 机械变更（`bind_dispatch` 替代 `bind_snapshot`），不改变 scheduler 时序。此 race 的根本原因及修复不在 S5 scope。

## Residual Risk

### correctness
- **无未覆盖 correctness risk**：Engine identity 从实际成功 Runner call 构造（`_successful_response_identity` 使用同一次 `_IterationState.request_identity` + `runner_done.provider_request_id` + `request.runner_spec.provider/model`）；normal/filter/force/LENGTH continuation 各路径均携带正确 identity；compactor fail-closed on LENGTH
- Host accepted/rejected durable payload 通过 `_require_exact_fields` 拒绝 extra/missing fields；mapping/null 分类由 `_POST_SUCCESS_REJECTION_CATEGORIES` / `_NO_SUCCESS_REJECTION_CATEGORIES` frozen sets 强制执行
- A/B/C 串线反例由 prepared identity validation（两处：`_validated_prepared_response_identity` + `_validate_prepared_proposal_identity`）和 test（`rejected.successful_response_identity != result.accepted_successful_response_identity`）覆盖
- `CompactorProposalManifestReference` 绑定 operation_id/attempt_number/compactor_engine_run_id，由 `_validate_successful_response_manifest_binding` 在 durable event build 时校验

### concurrency/recovery
- S5 不引入新的并发原语；identity 构造在 Engine run 内是单线程的（`_classify_iteration` 在每个 iteration 串行调用）
- Host compactor proposal attempt 是串行的（`_run_compaction_operation` for loop），不存在多 attempt 并发 identity 竞争

### platform/external provider evidence
- `provider_request_id` 的 PRESENT/UNAVAILABLE 分类正确；真实 provider 成功 compaction evidence 仍待 G06/行为项 29（S6 scope）
- POSIX PTY 和 Windows non-TTY 边界不受 S5 影响

### explicitly out of scope
- G01-G07
- S1-S4、S6 docs/registry
- 真实 provider successful compaction continuity
- phase5 scheduler race 修复
- awaiting smoke callback_execution_port 修复

### Compatibility statement
- 无旧参数/namespace/schema 兼容
- `FinalAnswerData` / `EngineRunOutcomeFinalAnswer` 的 `response_identity` 为 required field（无 default）
- `build_context_compacted_payload` / `build_context_compaction_attempt_rejected_payload` 的 identity 参数为 required typed（无 default、无 optional seam）
- `ContextCompactor.compact()` 返回类型从 `ConversationCompactOutputVNext` 改为 `CompactorProposal`（breaking change）
- 旧 `CONTEXT_COMPACTED` / `CONTEXT_COMPACTION_ATTEMPT_REJECTED` payload 不兼容（fresh schema，`_require_exact_fields` 拒绝旧字段）

## Verdict

**PASS** — 未发现阻塞级 defect。

经对全部 8 个 adversarial check 区域逐代码路径走读、inventory verification、focused test validation 和 pyright 检查：

1. Engine identity 正确来自实际终结成功 call；normal/filter/force/LENGTH continuation 不串线
2. Provider id present/unavailable 与 client correlation 严格成对；provider/model 只从同源 `AgentRunRequest.runner_spec` 取得
3. LLM compactor post-success LENGTH/parse/schema 保留 identity；no-final/timeout 正确为 null
4. Operation A/B/C、多 attempt/repair 不串线；accepted candidate+attempt+manifest+identity 原子同源
5. Durable accepted/rejected exact schema 使用 `_require_exact_fields`；mapping/null 分类按 `_POST_SUCCESS_REJECTION_CATEGORIES` / `_NO_SUCCESS_REJECTION_CATEGORIES` frozen sets 严格执行；manifest operation/attempt/run binding 完整
6. Endpoint/credential/ref/Authorization/header/secret 零泄漏 — identity type 刻意只含 provider/model/client correlation/provider request id
7. 33-file mechanical union 精确闭合；0 `type: ignore`、0 compat、0 lazy import、0 `hasattr`/`getattr`；Controller 已纠正的断言可达、单 source request/token、quality fixture mapping、phase5 顺序均已确认
8. 850 S5 owner focused tests 全绿；pyright 0 errors, 0 warnings；2 个 clean-HEAD residual（phase5 race + awaiting smoke）证据充分且不在 S5 scope

2 个 low-severity finding（manifest reference 循环依赖微风险、非 prepared path 无 prepared-level identity 校验）均无当前实际影响，不阻塞 merge。
