# WU-CM-01 Compact Contract Closure Plan Blocker Follow-Up Fix Re-Review (DS)

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | compact contract closure plan blocker follow-up fix re-review |
| reviewer | AgentDS |
| design source | `docs/host/design.md` |
| control doc | `docs/host/issues-implementation-control.md` |
| plan doc | `docs/host/wu-cm-01-conversation-memory-plan.md` |
| controller adjudication | `docs/reviews/wu-cm-01-compact-contract-closure-plan-blocker-fix-rereview-controller-adjudication.md` |
| follow-up fix artifact | `docs/reviews/wu-cm-01-compact-contract-closure-plan-blocker-followup-fix-codex.md` |
| current commit | `464bfa1c` |
| artifact path | `docs/reviews/wu-cm-01-compact-contract-closure-plan-blocker-followup-fix-rereview-ds.md` |

## Scope

本 re-review 只判断 follow-up fix 是否处理上一轮 Controller accepted findings。不修改 production code、tests、README、plan 或 control doc。

## Finding 1: Pre-Slice C Allowed Production Files — open_host.py / api.py

**检查项**：Pre-Slice C allowed production files 是否已加入 `dayu/host/open_host.py` 与 `dayu/host/api.py`，且 scope 严格限于 `LLMContextCompactor` construction、`HostLocalExecutionOptions.context_compactor` typed option、single public `compact()` vNext contract 类型对齐。

**直接证据**：

- Plan 第 247 行：`dayu/host/open_host.py`，仅限 `LLMContextCompactor` construction 与单一 public `ContextCompactor.compact()` vNext contract 的类型对齐；不得修改 `open_host()` public lifecycle、scheduler wiring、runtime behavior 或 Service assembly 语义。
- Plan 第 248 行：`dayu/host/api.py`，仅限 `HostLocalExecutionOptions.context_compactor` typed option 与单一 public `ContextCompactor.compact()` vNext contract 的类型对齐；不得新增 / 修改 public option 字段、配置服务入口、Service assembly、UI 入口或 OpenHost 行为。
- Plan 第 552 行（Allowed Files / Modules Summary）：`dayu/host/open_host.py`，仅限 Pre-Slice C `LLMContextCompactor` construction 与 single public `ContextCompactor.compact()` vNext contract 类型对齐。
- Plan 第 553 行（Allowed Files / Modules Summary）：`dayu/host/api.py`，仅限 Pre-Slice C `HostLocalExecutionOptions.context_compactor` typed option 与 single public `ContextCompactor.compact()` vNext contract 类型对齐。

**裁决**：Controller F1 / DS F1 **已处理**。两个文件已增补到 Pre-Slice C allowed files 与 Allowed Files / Modules Summary，scope 严格限定为 construction、typed option 与 single public compact contract 类型对齐。

---

## Finding 2: open_host.py / api.py 禁止越界扩大

**检查项**：plan 是否明确禁止 `open_host.py` / `api.py` 修改扩大到 Service assembly、config-service、UI、OpenHost lifecycle、scheduler wiring、runtime behavior 或 public behavior 重构。

**直接证据**：

- Plan 第 278 行（implementation boundary）：`open_host.py` / `api.py` 只允许为 `ContextCompactor` / `LLMContextCompactor` construction、typed option 和单一 public `compact()` vNext contract 做类型对齐；不得混入 `dayu/service/host_assembly.py`、`dayu/runtime/config_loader.py`、`dayu/config/execution_profiles.json`、`dayu.ui` 或 OpenHost lifecycle / scheduler / public behavior 重构。
- Plan 第 323 行（exit signal）：`dayu/host/open_host.py` 与 `dayu/host/api.py` 如被修改，修改仅限 compactor construction / typed option / single public compact contract 类型对齐；不得出现 Service assembly、config-service、UI 或 OpenHost lifecycle / scheduler / public behavior 重构。

**裁决**：Controller F1 scope 约束 **已处理**。Implementation boundary 与 exit signal 两处均明确禁止越界扩大，覆盖了 Service assembly、config-service、UI、OpenHost lifecycle、scheduler wiring、runtime behavior 与 public behavior 重构全部禁止项。

---

## Finding 3: run_input.py 旧 CompactMaterialBlockKind 依赖切断边界

**检查项**：`run_input.py` 是否澄清旧 `CompactMaterialBlockKind` enum members 删除前必须替换为 vNext section 分类 helper 或本模块私有分类，且不得提前迁移 full vNext memory prompt assembly。

**直接证据**：

- Plan 第 280 行：`run_input.py` 在本 slice 只承担旧 compact material public symbol 删除的最小 owner：删除旧 `CompactMaterialBlockKind` enum members 前，必须先把本模块对 `PINNED_STATE`、`WORKING_ASSUMPTION`、`OPEN_QUESTION`、`EPISODE_SUMMARY` 等旧 members 的引用替换为 vNext section 分类 helper 或本模块私有分类；当前仍需构造 selected recent window / current input material 时，必须使用 vNext material section typed API 或本模块私有分类 helper。不得提前迁移 full vNext memory prompt assembly、固定 prompt section 顺序或 fallback prompt 语义。

**裁决**：Controller MiMo F2 **已处理**。边界澄清完整且具体：明确了旧 members 清单（`PINNED_STATE`、`WORKING_ASSUMPTION`、`OPEN_QUESTION`、`EPISODE_SUMMARY`）、替换目标（vNext section 分类 helper 或本模块私有分类）与禁止项（不得提前迁移 full vNext memory prompt assembly）。

---

## Finding 4: EvidenceBackedFactCandidate 处置策略

**检查项**：`EvidenceBackedFactCandidate` 是否要求 implementation closeout 单独说明处置策略，并禁止新旧定义并存、alias、compatibility re-export 或旧 candidate wrapper。

**直接证据**：

- Plan 第 282 行（implementation boundary）：`EvidenceBackedFactCandidate` 的符号处置必须在 implementation closeout 中单独说明：若当前定义与 design 24.3 vNext schema 完全一致，可以保留为 vNext shape；若不一致，必须重建或迁移到 vNext shape。禁止旧定义与 vNext 定义并存，禁止 alias、compatibility re-export 或旧 candidate wrapper。
- Plan 第 325 行（exit signal）：implementation closeout 已单独说明 `EvidenceBackedFactCandidate` 的处置策略，且代码中不存在旧定义与 vNext 定义并存、alias、compatibility re-export 或旧 candidate wrapper。

**裁决**：Controller DS F2 **已处理**。处置策略要求同时出现在 implementation boundary 与 exit signal 中；禁止项覆盖了并存、alias、compatibility re-export 与旧 candidate wrapper 四种违规形态。

---

## Finding 5: 条件测试边界

**检查项**：条件测试 `test_public_open_host_options.py`、`test_open_host_runtime.py` 是否只在 `api.py` / `open_host.py` typed option 或 construction 断言需要同步时追加，且不扩大行为范围。

**直接证据**：

- Plan 第 258 行：`tests/host/test_public_open_host_options.py`，仅当 `dayu/host/api.py` typed option 或 `dayu/host/open_host.py` compactor construction 类型对齐需要测试断言同步；不得新增 OpenHost 行为重构断言。
- Plan 第 259 行：`tests/host/test_open_host_runtime.py`，仅当 `LLMContextCompactor` construction 参数或 typed option 注入路径因单一 public `compact()` contract 对齐而变更；不得扩大到 scheduler、lifecycle 或 public runtime 行为重构。
- Plan 第 303-309 行：条件测试命令明确只在 typed option 或 construction 需要同步时追加，并附 pyright 全量验证。

**裁决**：Controller accepted **已处理**。两个条件测试均有明确的触发条件与行为范围约束，禁止扩大行为范围。

---

## Finding 6: Control Doc Gate/Status/Next Entry Point 一致性

**检查项**：control doc gate/status/next entry point 是否一致指向 re-review。

**直接证据**：

- Control doc 第 143 行：`gate | re-review`
- Control doc 第 144 行：`implementation status | compact-contract-closure-plan-blocker-followup-fix-complete-needs-rereview`
- Control doc 第 147 行：`next entry point | WU-CM-01 compact contract closure plan blocker follow-up fix re-review gate`
- Control doc 第 164 行：`compact contract closure plan blocker follow-up fix artifacts | docs/reviews/wu-cm-01-compact-contract-closure-plan-blocker-followup-fix-codex.md`

**裁决**：**一致**。gate、implementation status、next entry point 均指向 re-review gate；follow-up fix artifact 已记录。

---

## Conclusion

**Verdict**: `pass`

全部 6 项 Controller accepted findings 均已在 plan 中可验证地处理：

| Controller accepted finding | 状态 | 验证位置 |
|---|---|---|
| Blocking: open_host.py / api.py 增补为 allowed files | fixed | Plan L247-248, L552-553 |
| Scope 严格限定，禁止扩大到 Service/config/UI 等 | fixed | Plan L278, L323 |
| run_input.py 旧 enum 删除前替换边界澄清 | fixed | Plan L280 |
| EvidenceBackedFactCandidate 处置策略 | fixed | Plan L282, L325 |
| 条件测试边界 | fixed | Plan L258-259, L303-309 |
| Control doc gate/status/next 一致性 | consistent | Control doc L143-147, L164 |

无 blocking finding，无 non-blocking finding。

下一入口：WU-CM-01 compact contract closure implementation gate。
