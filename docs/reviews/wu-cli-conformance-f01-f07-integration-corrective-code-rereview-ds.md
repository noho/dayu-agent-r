# WU CLI Conformance F01-F07 — Integration Corrective Re-Review (DS)

## Scope

- Mode: current changes (corrective re-review, same review/fix loop)
- Branch: `codex/interactive-oracle`
- Base: `df99f858` (entry HEAD)
- Output file: `docs/reviews/wu-cli-conformance-f01-f07-integration-corrective-code-rereview-ds.md`
- Review timestamp: 2026-08-03T05:18:42Z
- Reviewer: AgentDS（与初轮同一 session，不清上下文）
- Prerequisite artifacts:
  - Controller adjudication: `docs/reviews/wu-cli-conformance-f01-f07-integration-corrective-controller-adjudication.md`
  - Fix artifact: `docs/reviews/wu-cli-conformance-f01-f07-integration-corrective-fix-codex.md`
  - MiMo review: `docs/reviews/wu-cli-conformance-f01-f07-integration-corrective-code-review-mimo.md`
  - DS initial review: `docs/reviews/wu-cli-conformance-f01-f07-integration-corrective-code-review-ds.md`
  - Implementation artifact: `docs/reviews/wu-cli-conformance-f01-f07-integration-corrective-implementation-codex.md`

### Included scope

| 文件 | 角色 |
|---|---|
| `tests/host/test_phase5_local_execution_integration.py` | DS-02 fix: dispatch COUNT 绑定 `run_id + attempt_id` |
| `docs/reviews/wu-cli-conformance-f01-f07-integration-corrective-implementation-codex.md` | DS-08 fix: §6.3 新增五个 corrective 文件 working-tree SHA-256 |
| `docs/reviews/wu-cli-conformance-f01-f07-integration-corrective-fix-codex.md` | fix artifact（本 re-review 的审查对象之一） |
| `docs/cli_init_workspace_manifest_v1.json` | 五文件 SHA-256 独立重算验证 |
| `tests/cli/test_smoke_cli_init_provider_matrix.py` | 同上 |
| `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py` | 同上 |
| `tests/service/test_host_assembly.py` | 同上 |

### Excluded scope

- S8 README baseline：`README.md`、`dayu/config/README.md`、`dayu/host/README.md`、`tests/README.md`（SHA-256 与 fix artifact §4 声明一致，未被本 fix loop 修改）
- Frozen registries：`docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json`（SHA-256 与 fix artifact §4 声明一致）
- S8 implementation artifact
- 所有 `dayu/` production 代码
- `tests/host/fake_compaction.py`

### Parallel review coverage

无。单路独立深度复核。

## Findings

### RR-01-已修复-中-DS-02 dispatch COUNT 已完成 run_id+attempt_id 双键绑定

- **入口/函数**: `_assert_exactly_once_dispatch_outcome`
- **文件(行号)**: `tests/host/test_phase5_local_execution_integration.py:1580-1587`
- **输入场景**: 任意 exact-once dispatch 断言场景。
- **实际分支**: dispatch record COUNT 查询。
- **预期行为**: 只统计目标 Attempt 的 dispatch record，不依赖当前单 Attempt policy 隐式保证。
- **实际行为**: 查询已从 `WHERE run_id = ?` 收敛为 `WHERE run_id = ? AND attempt_id = ?`，参数绑定为 `(refs.run_id, refs.attempt_id)`。helper 自持有 `refs.attempt_id`，无需新增参数或变更调用方。
- **直接证据**:
  - 行 1582-1586: `FROM host_attempt_dispatch_records WHERE run_id = ? AND attempt_id = ?` + `(refs.run_id, refs.attempt_id)`
  - 独立运行 Phase5 focused: `9 passed in 0.51s`
- **影响**: fix 正确，无残留问题。即使后续 continuation 场景复用本 helper，dispatch COUNT 仍只统计当前 Attempt。
- **建议改法和验证点**: 无需进一步修改。修复已完成。
- **修复风险（低）**: 已在 Phase5 单文件 9 个测试中验证。
- **严重程度（已修复）**: DS-02 已关闭。

### RR-02-已修复-低-DS-08 五文件 SHA-256 fingerprint 可独立重算且验证顺序正确

- **入口/函数**: DS-08 fix 的 implementation artifact §6.3 与 fix artifact §2。
- **文件(行号)**:
  - `docs/reviews/wu-cli-conformance-f01-f07-integration-corrective-implementation-codex.md:123-142`（§6.3 最终 validated working-tree fingerprint）
  - `docs/reviews/wu-cli-conformance-f01-f07-integration-corrective-fix-codex.md:30-38`（§2 五文件 SHA-256 表）
- **输入场景**: 第三方独立验证五文件内容与 artifact 声明一致。
- **实际分支**: 独立 `shasum -a 256` 对五个 corrective 文件逐文件重算。
- **预期行为**: 每个文件 SHA-256 与 fix artifact §2 和 implementation artifact §6.3 声明的值完全一致。
- **实际行为**: 五个文件独立重算结果均匹配（见直接证据）。
- **直接证据**:
  ```
  c646c2a0c7b508f8cc07d7f446273fb37117a8b1d9e47da82bf09f32e9dfd65e  docs/cli_init_workspace_manifest_v1.json
  cd6fe484080290a7ec66a70449697cb49e7fef7bb3c125fd0bb5240a4beaaad4  tests/cli/test_smoke_cli_init_provider_matrix.py
  c2521212c5705b68cfcdd5bc59cc24fd22ff9be45f36b80a78c2098885c2c991  tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py
  80c2c399c9a84ab63d95d4ffbdb9220edf4dc3df04248fd260f25cadfd47c884  tests/service/test_host_assembly.py
  8e84963898076b851496a51785d5c8038baf4546f448b0eb7f6bdb800fdcef83  tests/host/test_phase5_local_execution_integration.py
  ```
  fix artifact §2 表、implementation artifact §6.3 表、独立重算三源一致。
- **验证顺序**: implementation artifact §6.3 行 125-130 明确声明：先应用 DS-02 fix（dispatch COUNT 双键绑定），再在最终文件集合上运行验证并通过，最后才计算 SHA-256 并写入 artifact。artifact 写入不可逆改变验证文件集合。此顺序与 fix artifact §2 行 28 "最终 SQL 修正与本 fix loop 的全部验证完成后，才计算五个 corrective data/test 文件的 working-tree SHA-256" 一致。
- **影响**: DS-08 已正确关闭。fingerprint 可重算、顺序正确。
- **建议改法和验证点**: 无需进一步修改。
- **修复风险（低）**: 已独立验证。
- **严重程度（已修复）**: DS-08 已关闭。

### RR-03-已确认-控制器的 DS-07 disposition 经 typed contract 验证，不应重开

- **入口/函数**: Controller DS-07 `REJECT-FALSE-CONTRACT-INFERENCE` disposition。
- **文件(行号)**:
  - `dayu/config/prompts/scenes/conversation_compaction_user.md:50-51`（LLM-facing contract: 每个 label 必须"被至少一个业务语义项引用"）
  - `dayu/config/prompts/scenes/conversation_compaction_user.md:20-22`（`session_summary.source_labels` 无 source_kind 限制）
  - `dayu/host/context_governance.py:565-586`（`_represented_sections` 使用 `set.add` 支持 multi-section representation）
- **输入场景**: 两个 fake compactor 的 `session_summary.source_labels` 过滤策略不同（utils 仅 trace_material；tests/host 全量 boundary labels）。
- **实际分支**: 控制器裁决两个策略均产生合法 accepted candidate，不构成 typed contract drift。
- **预期行为**: 若 controller 判断有误，需要 frozen design/typed contract 的直接反例。
- **实际行为**: 经逐行阅读 frozen contract 与 `_represented_sections`，确认：
  1. LLM-facing contract 行 50: "被**至少一个**业务语义项引用" — 不要求排他性
  2. LLM-facing contract 行 20-22: `session_summary.source_labels` 无 source_kind 限制（不同于 `evidence_facts` 的显式限制行 30）
  3. `_represented_sections` 行 576-586: 每个 label 的 represented sections 存储为 `set`，`_add_represented` 行 603 使用 `.add(section)` — 一个 label 可以出现在多个 section
  4. 因此两个 fake compactor 对 `session_summary.source_labels` 的不同选择（仅 trace vs 全量）均落在 typed contract 的合法空间内
- **直接证据**: 上述三个文件的具体行号与逐字引用。
- **影响**: 控制器 disposition 正确。不应重开 DS-07。
- **严重程度（已确认）**: DS-07 关闭正确。

### RR-04-已确认-其余控制器 disposition（DS-01/03/04/05/06/09/10/11）均无直接反例可重开

- **入口/函数**: Controller adjudication table。
- **文件(行号)**: `docs/reviews/wu-cli-conformance-f01-f07-integration-corrective-controller-adjudication.md:19-29`
- **输入场景**: 对每一项 rejected/closed disposition，检查是否存在 frozen design/typed contract 的直接反例。
- **实际分支**: 逐项复核。

| ID | Controller disposition | DS 复核结论 | 复核依据 |
|---|---|---|---|
| DS-01 | `REJECT-NON-ACTIONABLE` | 确认，不重开 | SELECT 列与位置读取相邻 5 行，四个字段均与 EventLog/typed enum 交叉断言；即使列序漂移也会 loud-fail，无静默误通过反例 |
| DS-03 | `REJECT-OUT-OF-SLICE` | 确认，不重开 | 双场景结构在 corrective slice 之前已存在；本 slice 仅替换 stale drain/polling 为 lifecycle signal + exact-once helper |
| DS-04 | `REJECT-ALREADY-EXPLICIT` | 确认，不重开 | helper docstring 已明确 "场景累计应创建的 worker 数"；每个 Run 有独立 dispatch-record/EventLog/Attempt 断言 |
| DS-05 | `CLOSED-BY-DIRECT-EVIDENCE` | 确认，不重开 | 初轮已追踪 dispatch.py 时序：`_accept_worker_running()` 在 `consumer_started` barrier 之前同步提交 |
| DS-06 | `REJECT-BY-DESIGN` | 确认，不重开 | helper 同时断言 public `get_run` 与 durable SQLite，双 owner 交叉验证是设计意图 |
| DS-07 | `REJECT-FALSE-CONTRACT-INFERENCE` | 确认，不重开 | 见 RR-03 详细验证 |
| DS-09 | `CLOSED-CORRECT` | 确认，不重开 | accepted plan 没有 full-repository Ruff gate |
| DS-10 | `CLOSED-CORRECT` | 确认，不重开 | publication manifest 三个 digest 已独立验证 |
| DS-11 | `CLOSED-CORRECT` | 确认，不重开 | system/user prompt 语义归属符合 LLM-input/output boundary |

- **影响**: 所有 controller disposition 经独立复核均正确。无需要重开的 finding。
- **严重程度（已确认）**: 全部验证通过。

### RR-05-已确认-scope 无扩张，S8 baseline/frozen/production 未被修改

- **入口/函数**: scope 审计。
- **文件(行号)**: 全仓 working-tree diff。
- **输入场景**: 检查本 fix loop 是否引入了不在 controller fix-loop scope 内的修改。
- **实际分支**: `git diff HEAD --name-only` 返回 9 个文件：4 个 S8 README + 5 个 corrective 文件。S8 README 的 SHA-256 与 fix artifact §4 声明一致（`ce5d0a9c`、`0700d670`、`3ba963ff`、`b2b6e60e`）。frozen registry 的 SHA-256 与 fix artifact §4 声明一致（`f9972d94`、`7f283b03`）。`dayu/` 下除 README 外零 working-tree delta。
- **直接证据**:
  ```
  git diff HEAD --name-only:
    README.md                         (S8 baseline)
    dayu/config/README.md             (S8 baseline)
    dayu/host/README.md               (S8 baseline)
    docs/cli_init_workspace_manifest_v1.json  (corrective)
    tests/README.md                   (S8 baseline)
    tests/cli/test_smoke_cli_init_provider_matrix.py  (corrective)
    tests/host/test_phase5_local_execution_integration.py  (corrective)
    tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py  (corrective)
    tests/service/test_host_assembly.py  (corrective)
  ```
  全新 untracked procedural artifacts 均为本 review/fix loop 的正常产物：controller adjudication、MiMo review、DS review、fix artifact、re-review artifact。无额外 implementation file 变更。
- **影响**: scope 严格在 controller fix-loop 范围内。无扩张风险。
- **严重程度（已确认）**: 通过。

## Open Questions

无。

## Residual Risk

- DS-02 fix 的最小改动（dispatch COUNT 加 `attempt_id` 过滤）在 Phase5 focused 9 个测试中验证通过。helper 仅在本文件内使用（`test_phase5_local_execution_integration.py`），无跨文件调用方需更新。
- DS-08 fix 的五文件 SHA-256 fingerprint 三源一致（fix artifact、implementation artifact、独立重算）。但是否存在 DS-02 fix 应用前与后的验证之间有任何 silent file change，只能通过 SHA-256 不变性间接证明——对五个文件而言，SHA-256 可重算即构成直接证据。
- 两个 fake compactor 的 `session_summary.source_labels` 策略差异（RR-03）已确认不是 contract drift，但仍构成 test infrastructure maintenance risk：如果未来 production compact acceptance 对 session_summary.source_labels 增加精确语义约束，两个 fake 需要同步调整。当前不是缺陷。
