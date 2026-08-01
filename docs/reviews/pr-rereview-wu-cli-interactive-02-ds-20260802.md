# wu-cli-interactive-02 PR re-review (AgentDS)

## Scope

- **Mode**: PR re-review — 对 adjudicated PR-A01 fix 的独立验证
- **PR**: [#190](https://github.com/noho/dayu-agent-r/pull/190)
- **Remote HEAD**: `a4ff05db`
- **Fix scope**: 本地未提交 diff（4 tracked files relative to HEAD）
- **Reviewed files**:
  - `dayu/host/compaction_operation.py` — owner 新增两个 required accessor
  - `dayu/host/dispatch.py` — proactive caller 迁移 + 删除两个 local helper
  - `dayu/host/engine_ingest.py` — reactive caller 迁移 + 删除两个 local helper
  - `tests/host/test_compaction_operation.py` — guard test 迁移 + 新增 missing-identity test
- **Artifacts read**:
  - `AGENTS.md`
  - `docs/reviews/pr-review-wu-cli-interactive-02-ds-20260802.md`（AgentDS 初审）
  - `docs/reviews/gateflow-wu-cli-interactive-02-pr-review-adjudication-20260802.md`
  - `docs/reviews/gateflow-wu-cli-interactive-02-pr-review-fix-codex-20260802.md`
- **Excluded scope**:
  - AgentMiMo 初审 artifact（按指令不读）
  - PR scope 外代码（本次仅 review fix diff，不重读 PR 全量 diff）
  - 未修改的远端 PR body、README、design、oracle、scenario

## 走读方法

1. 读取 adjudication 确认 accepted finding（PR-A01）的精确 fix 要求。
2. 读取 Codex fix artifact 确认声称的变更范围与验证结果。
3. 独立逐文件走读 exact diff，不依赖 Codex artifact 的结论。
4. 对每个变更点做独立验证：owner 正确性、helper 完全移除、异常/typing/schema/CAS/behavior 保持、测试 owner-level。
5. 扫描 scope creep：检查是否修改了 adjudication 未授权的文件或语义。
6. 执行 adversarial pass：检查是否有遗漏的重复 helper、不一致的错误文本、未迁移的 caller、残留引用。
7. 独立运行 `pytest tests/host/test_compaction_operation.py` 和 `pyright` 验证。

## PR-A01 Fix 验证

### 验证项 1：CompactionOperationResult 是否真正拥有这两个 invariant

**直接证据**：

- `CompactionOperationResult` 定义在 `dayu/host/compaction_operation.py:490-546`，其 dataclass fields 已包含 `accepted_successful_response_identity: SuccessfulRunnerResponseIdentity | None`（行 513）和 `accepted_proposal_manifest_reference: CompactorProposalManifestReference | None`（行 514）。
- 这两个字段由 compaction operation 执行器填充——result 是唯一产生并携带这两个事实的 typed object。
- 新增的 `required_successful_response_identity()`（行 516-530）和 `required_proposal_manifest_reference()`（行 532-546）直接读取各自字段，字段缺失时抛出 `RuntimeError`，不引入新类型、新异常类或新错误文本。

**结论**：语义 ownership 正确。`CompactionOperationResult` 是这两个 accepted-result presence invariant 的 sole source of truth。两个 accessor 完整中文 docstring 含 `:returns:` 和 `:raises:`，符合编码硬约束。

### 验证项 2：四个 local helper 是否完全移除

**dispatch.py**：

- `_required_successful_response_identity`：旧定义在 `6257-6274`，已删除。`grep` 确认 dispatch.py 中零引用。
- `_required_compactor_manifest_reference`：旧定义在 `6277-6293`，已删除。`grep` 确认 dispatch.py 中零引用。
- Caller（行 2550-2555）已迁移为 `accepted_result.required_proposal_manifest_reference()` 和 `accepted_result.required_successful_response_identity()`。

**engine_ingest.py**：

- `_required_successful_response_identity`：旧定义在 `8818-8842`，已删除。`grep` 确认 engine_ingest.py 中零引用。
- `_required_compactor_manifest_reference`：旧定义在 `8845-8861`，已删除。`grep` 确认 engine_ingest.py 中零引用。
- Caller（行 3120-3125）已迁移为 `operation_result.required_proposal_manifest_reference()` 和 `operation_result.required_successful_response_identity()`。

**全仓扫描**：`dayu/` 和 `tests/` 中零处残留引用。

**结论**：四个 local helper 已完全移除，两个 caller 已正确迁移。

### 验证项 3：异常/typing/schema/CAS/behavior 是否保持

**异常**：

| 维度 | 旧 helper | 新 accessor |
|---|---|---|
| 异常类型 | `RuntimeError` | `RuntimeError` ✓ |
| identity 错误文本 | `"accepted compaction is missing successful response identity"` | 同 ✓ |
| manifest 错误文本 | `"accepted compaction is missing proposal manifest reference"` | 同 ✓ |

**typing**：

- `required_successful_response_identity() -> SuccessfulRunnerResponseIdentity`：返回类型与旧 helper 一致 ✓
- `required_proposal_manifest_reference() -> CompactorProposalManifestReference`：返回类型与旧 helper 一致 ✓
- 两个方法签名无 `Any`、无 `object`、无缺失类型标注 ✓

**schema**：

- `CompactionOperationResult` dataclass fields 未变更：字段名、类型、顺序、默认值均保持 ✓
- 无新增/删除/重命名字段 ✓

**CAS（terminal first-committer-wins）**：

- 本 fix 不修改 `begin_compaction_terminal_commit_in_transaction`、write transaction 边界或线性化点 ✓
- proactive/reactive caller 仍在各自 write transaction 内调用 accessor，不改变事务范围或提交顺序 ✓

**behavior**：

- 两个 accessor 仅在各自字段为 `None` 时 `raise RuntimeError`，与原 helper 行为完全一致 ✓
- dispatch caller 在 `_compaction_result_accepted()` 返回 True 后、`accepted_candidate is None or quality_result is None` guard 通过后调用——与原调用顺序一致 ✓
- engine_ingest caller 在 accepted 路径内、`_append_reactive_compacted_event` 前调用——与原调用顺序一致 ✓

**结论**：异常类型、错误文本、typing、schema、CAS、behavior 全部保持。

### 验证项 4：测试是否 owner-level

**变更前**：

- `test_accepted_compaction_missing_proposal_manifest_guard_fails_closed` 通过 `dispatch._required_compactor_manifest_reference(result)` 间接测试——依赖 `import dayu.host.dispatch`，测试的是 dispatch 的私有 helper 而非 result owner 的 contract。

**变更后**：

- 同一测试迁移为直接调用 `result.required_proposal_manifest_reference()`——直接断言 result owner contract ✓
- 新增 `test_accepted_compaction_missing_successful_response_identity_guard_fails_closed`——直接构造 `CompactionOperationResult`（`accepted_successful_response_identity=None`），断言 `result.required_successful_response_identity()` 抛出 `RuntimeError` 且错误文本匹配 ✓
- `import dayu.host.dispatch` 已从测试文件中删除 ✓
- 两个测试均不依赖 dispatch 或 engine_ingest 模块——纯 owner-level contract test ✓

**结论**：测试已迁移为 owner-level contract test，符合 AGENTS.md "测试必须断言 owner 级 contract 行为" 的要求。

### 验证项 5：scope creep 检查

**允许修改的文件**：按 adjudication 和 Codex fix artifact，仅 4 个文件。

| 文件 | 实际修改 | scope creep? |
|---|---|---|
| `dayu/host/compaction_operation.py` | +2 methods | 否——adjudication 明确要求 |
| `dayu/host/dispatch.py` | caller 迁移 + 删除 2 helpers | 否 |
| `dayu/host/engine_ingest.py` | caller 迁移 + 删除 2 helpers | 否 |
| `tests/host/test_compaction_operation.py` | test 迁移 + 新增 1 test | 否 |

**未修改的语义**：

- dataclass fields、类型、顺序 ✓
- 异常类型和错误文本 ✓
- transaction 边界 ✓
- terminal CAS ✓
- 任何 LLM-facing 文本 ✓
- PR body、README、design、oracle、scenario ✓

**结论**：无 scope creep。fix 精确限定在 adjudication 授权范围。

## 独立测试验证

| Validation | Result |
|---|---|
| `pytest -q tests/host/test_compaction_operation.py` | `33 passed in 0.34s` |
| `pyright dayu/host/compaction_operation.py dayu/host/dispatch.py dayu/host/engine_ingest.py tests/host/test_compaction_operation.py` | `0 errors, 0 warnings, 0 informations` |
| 全仓 `_required_successful_response_identity` / `_required_compactor_manifest_reference` 引用 | 零处残留 |
| `import dayu.host.dispatch` in test_compaction_operation.py | 已删除 |

与 Codex fix artifact 报告的测试结果（33 passed, 0 pyright errors）完全一致。独立复现验证通过。

## Findings

### RE-01-未修复-低-engine_ingest-dispatch-duplicate-accepted-attempt-number-helper

- **入口/函数**: `_required_accepted_attempt_number` — 在两个 Host 模块中以不同签名重复定义
- **文件(行号)**:
  - `dayu/host/dispatch.py:6176` — `def _required_accepted_attempt_number(value: int | None) -> int:`
  - `dayu/host/engine_ingest.py:8804` — `def _required_accepted_attempt_number(result: CompactionOperationResult) -> int:`
- **输入场景**: compaction operation 返回 accepted result 后，proactive（dispatch）和 reactive（engine_ingest）writer 需要校验 accepted attempt number 为非 None 正数
- **实际分支**: dispatch 版本接受裸 `int | None`（caller 预先从 `accepted_result.accepted_attempt_number` 提取），engine_ingest 版本接受 `CompactionOperationResult` 整体（内部提取字段）
- **预期行为**: 同一 invariant（`accepted_attempt_number` 必须为非 None 正数）应由 `CompactionOperationResult` 唯一拥有，提供统一的 `required_accepted_attempt_number()` accessor
- **实际行为**: 两个模块各自维护校验逻辑，且**错误文本不一致**——dispatch 抛出 `"accepted compaction is missing attempt number"`，engine_ingest 抛出 `"accepted compaction is missing accepted attempt number"`
- **直接证据**:
  - `dispatch.py:6184`: `raise RuntimeError("accepted compaction is missing attempt number")`
  - `engine_ingest.py:8814`: `raise RuntimeError("accepted compaction is missing accepted attempt number")`
  - dispatch caller（行 2542）传入预提取的 `int | None`；engine_ingest caller（行 3110）传入 `CompactionOperationResult`
- **影响**: 当前两个错误文本不同——若未来 error message 被用于日志分类、监控告警或测试断言，同一语义条件会产生不同可观测信号。此外单边修改校验逻辑（如放宽 `<= 0` 检查）可能导致 proactive/reactive 路径行为分歧
- **建议改法和验证点**:
  1. 在 `CompactionOperationResult` 上新增 `required_accepted_attempt_number() -> int`
  2. dispatch 和 engine_ingest 迁移为调用 owner accessor
  3. 统一错误文本
  4. 将现有 attempt number guard test 迁移到 `test_compaction_operation.py`
- **修复风险（低）**: 纯重构，不改变运行时行为（仅统一错误文本）
- **严重程度（低）**: 当前无功能缺陷，但与已修复的 PR-A01 属同一类 semantic ownership drift，且错误文本已出现不一致

**注**：此 finding 不在本次 adjudication 接受的 PR-A01 范围内。PR-A01 仅覆盖两个 identity/manifest helper。本 finding 作为独立的同模式 drift 在此记录，建议在后续 work unit 中修复。

## Open Questions

1. **`_required_accepted_attempt_number` 是否为 PR-A01 的 scope creep 遗漏**：adjudication 明确指出"只接受其中一项"（仅 PR-A01），controller 未 classify 此 helper。但从第一性原理判断，它与已修复的两个 helper 属完全相同的 semantic ownership drift 模式，且错误文本已出现分歧。建议 controller 裁决是否纳入本次或后续 fix。

## Residual Risk

1. **`_required_accepted_attempt_number` 错误文本不一致**：dispatch 用 `"missing attempt number"`，engine_ingest 用 `"missing accepted attempt number"`。当前无消费者依赖具体错误文本做分支判断，但属于可观测行为的不一致。
2. **Codex fix artifact 报告的 6 个 Phase 5 integration baseline failures**：本 re-review 未独立运行全量 Host 测试（仅运行 `test_compaction_operation.py`），但 Codex artifact 已确认这 6 个 failure 与 S5/S6 baseline 一致且不由本 fix 引入。Risk 与 PR-A01 无关。
3. **GitHub CI 未运行**：与初审一致，远端 PR 分支无 reported checks。local pyright + pytest 通过但缺少 CI 自动化验证。

## Validation Assessment

| 验证维度 | 状态 | 证据 |
|---|---|---|
| PR-A01 owner correctness | **PASS** | `CompactionOperationResult` 是字段的 typed owner；两个 accessor 直接读取各自字段 |
| 四个 local helper 完全移除 | **PASS** | `grep` 全仓零引用；两个 caller 已迁移 |
| 异常类型/错误文本保持 | **PASS** | `RuntimeError` + 原错误文本，逐字一致 |
| typing 保持 | **PASS** | 返回类型、参数类型完整；pyright 0 errors |
| schema 保持 | **PASS** | dataclass fields 未变更 |
| CAS/behavior 保持 | **PASS** | 事务边界、调用顺序、terminal guard 不变 |
| 测试 owner-level | **PASS** | 直接断言 result owner contract；`dispatch` import 已删除 |
| 无 scope creep | **PASS** | 仅修改 4 个允许文件；未修改 PR body/README/design/oracle/scenario |
| 独立测试验证 | **PASS** | 33 passed, pyright 0 errors——与 Codex artifact 一致 |

## Conclusion

**PASS** — PR-A01 fix 通过独立 re-review。

`CompactionOperationResult` 已正确成为 `accepted_successful_response_identity` 和 `accepted_proposal_manifest_reference` 两个 presence invariant 的唯一 owner。四个重复 local helper 已从 `dispatch.py` 和 `engine_ingest.py` 完全移除。异常类型、错误文本、typing、schema、CAS 和 behavior 全部保持。测试已迁移为 owner-level contract test，新增 missing-identity guard test。无 scope creep。

发现一个与 PR-A01 同模式的未修复 semantic ownership drift：`_required_accepted_attempt_number` 在 dispatch 和 engine_ingest 中以不同签名和不同错误文本重复定义（RE-01）。此 finding 不在本次 adjudication scope 内，建议 controller 裁决处置。

**Next gate**: 等待 AgentMiMo 独立 re-review。双路均 PASS 后推进 final closeout。
