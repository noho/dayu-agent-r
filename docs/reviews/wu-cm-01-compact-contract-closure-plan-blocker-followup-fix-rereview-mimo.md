# WU-CM-01 Compact Contract Closure Plan Blocker Follow-Up Fix Re-Review

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | compact contract closure plan blocker follow-up fix re-review |
| reviewer | AgentMiMo |
| design source | `docs/host/design.md` |
| control doc | `docs/host/issues-implementation-control.md` |
| plan doc | `docs/host/wu-cm-01-conversation-memory-plan.md` |
| controller adjudication | `docs/reviews/wu-cm-01-compact-contract-closure-plan-blocker-fix-rereview-controller-adjudication.md` |
| follow-up fix artifact | `docs/reviews/wu-cm-01-compact-contract-closure-plan-blocker-followup-fix-codex.md` |
| date | 2026-06-04 |

## Verdict

`pass`。

Follow-up fix 完整处理了 Controller adjudication 的全部 accepted findings。Plan、control doc 与 follow-up fix artifact 三者一致，Pre-Slice C 可进入 implementation gate。

## Checkpoint 逐项验证

### 1. `open_host.py` / `api.py` 已加入 allowed files，scope 严格限定

**结论**: 通过。

Plan Pre-Slice C allowed files（第 247-248 行）已增补：

- `dayu/host/open_host.py`，仅限 `LLMContextCompactor` construction 与单一 public `ContextCompactor.compact()` vNext contract 的类型对齐；不得修改 `open_host()` public lifecycle、scheduler wiring、runtime behavior 或 Service assembly 语义。
- `dayu/host/api.py`，仅限 `HostLocalExecutionOptions.context_compactor` typed option 与单一 public `ContextCompactor.compact()` vNext contract 的类型对齐；不得新增 / 修改 public option 字段、配置服务入口、Service assembly、UI 入口或 OpenHost 行为。

Allowed Files / Modules Summary（第 552-553 行）同步补齐了这两个文件及对应 scope 限定。

上一轮 MiMo re-review 的 blocker finding（`open_host.py` / `api.py` 缺失于 allowed files 导致退出信号不可执行）已闭合。

### 2. 明确禁止修改扩大到 Service assembly、config-service、UI、OpenHost lifecycle、scheduler wiring、runtime behavior 与 public behavior 重构

**结论**: 通过。

Plan 实现边界（第 278 行）明确：

> `open_host.py` / `api.py` 只允许为 `ContextCompactor` / `LLMContextCompactor` construction、typed option 和单一 public `compact()` vNext contract 做类型对齐；不得混入 `dayu/service/host_assembly.py`、`dayu/runtime/config_loader.py`、`dayu/config/execution_profiles.json`、`dayu.ui` 或 OpenHost lifecycle / scheduler / public behavior 重构。

Follow-up fix artifact Accepted Findings Handling 表（第 31 行）同步确认：

> Plan 的 implementation boundary 与 exit signal 明确禁止在 `open_host.py` / `api.py` 修改中混入 `dayu/service/host_assembly.py`、`dayu/runtime/config_loader.py`、`dayu/config/execution_profiles.json`、`dayu.ui`、OpenHost lifecycle、scheduler wiring、runtime behavior 或 public behavior 重构。

禁止范围覆盖全部 7 类越界场景，无遗漏。

### 3. `run_input.py` 澄清旧 enum members 删除前必须替换

**结论**: 通过。

Plan 实现边界（第 280 行）明确：

> `run_input.py` 在本 slice 只承担旧 compact material public symbol 删除的最小 owner：删除旧 `CompactMaterialBlockKind` enum members 前，必须先把本模块对 `PINNED_STATE`、`WORKING_ASSUMPTION`、`OPEN_QUESTION`、`EPISODE_SUMMARY` 等旧 members 的引用替换为 vNext section 分类 helper 或本模块私有分类；当前仍需构造 selected recent window / current input material 时，必须使用 vNext material section typed API 或本模块私有分类 helper。不得提前迁移 full vNext memory prompt assembly、固定 prompt section 顺序或 fallback prompt 语义。

上一轮 MiMo F2（non-blocking）与 DS F-1（non-blocking）的歧义已消除：dependency severance 边界从模糊的"旧 compact public symbols"收窄为具体操作——先替换旧 enum member 引用，再删除旧 enum members，且不得提前迁移 full vNext memory prompt assembly。

### 4. `EvidenceBackedFactCandidate` 要求 implementation closeout 单独说明处置策略

**结论**: 通过。

Plan 实现边界（第 282 行）明确：

> `EvidenceBackedFactCandidate` 的符号处置必须在 implementation closeout 中单独说明：若当前定义与 design 24.3 vNext schema 完全一致，可以保留为 vNext shape；若不一致，必须重建或迁移到 vNext shape。禁止旧定义与 vNext 定义并存，禁止 alias、compatibility re-export 或旧 candidate wrapper。

退出信号（第 325 行）同步要求：

> implementation closeout 已单独说明 `EvidenceBackedFactCandidate` 的处置策略，且代码中不存在旧定义与 vNext 定义并存、alias、compatibility re-export 或旧 candidate wrapper。

上一轮 DS F-2（non-blocking）要求的 closeout 策略裁决已被纳入 plan。Follow-up fix artifact Accepted Findings Handling 表（第 33 行）确认此处理。

### 5. 条件测试只在需要同步时追加，且不扩大行为范围

**结论**: 通过。

Plan 条件测试说明（第 303-309 行）明确：

> 如果 `dayu/host/api.py` typed option 或 `dayu/host/open_host.py` compactor construction 因单一 public `compact()` contract 需要测试同步，同 slice 追加：
> ```bash
> pytest tests/host/test_public_open_host_options.py tests/host/test_open_host_runtime.py -q
> python -m pyright dayu/ tests/ utils/
> ```

两个条件测试文件的 scope 限定：

- `test_public_open_host_options.py`：仅当 `dayu/host/api.py` typed option 或 `dayu/host/open_host.py` compactor construction 类型对齐需要测试断言同步；不得新增 OpenHost 行为重构断言。
- `test_open_host_runtime.py`：仅当 `LLMContextCompactor` construction 参数或 typed option 注入路径因单一 public `compact()` contract 对齐而变更；不得扩大到 scheduler、lifecycle 或 public runtime 行为重构。

条件触发逻辑正确：只有 typed option 或 construction 因 contract 对齐需要同步时才追加，不扩大行为范围。

### 6. Control doc gate/status/next entry point 一致指向 re-review

**结论**: 通过。

Control doc 当前状态（第 140-147 行）：

- `implementation status`：`compact-contract-closure-plan-blocker-followup-fix-complete-needs-rereview`
- `gate`：`re-review`
- `next entry point`：`WU-CM-01 compact contract closure plan blocker follow-up fix re-review gate`

三者一致指向当前 re-review gate，无矛盾。

Follow-up fix artifact（第 49-52 行）确认 control doc 变更内容与上述一致。

## 上一轮 Non-Blocking Findings 闭合验证

### MiMo F1（blocker）— `open_host.py` / `api.py` 缺失于 allowed files

**状态**: 已闭合。Follow-up fix 已将这两个文件增补到 Pre-Slice C allowed files，scope 严格限定为 construction / typed option / contract 对齐。Allowed Files / Modules Summary 同步补齐。

### MiMo F2（non-blocking）— `run_input.py` dependency severance 边界模糊

**状态**: 已闭合。Plan 实现边界已具体化为"删除旧 enum members 前替换引用为 vNext section 分类 helper 或本模块私有分类"，歧义消除。

### MiMo F3（non-blocking）— `test_package_exports.py` 条件触发

**状态**: 无需 plan fix。条件测试说明已正确覆盖。Follow-up fix artifact 确认 implementation agent 在删除旧 `__all__` entries 时必须运行该测试。

### DS F-1（non-blocking）— ContextCompactor owner 清单与 allowed files 不完全一致

**状态**: 已闭合。`open_host.py` / `api.py` 已纳入 allowed files，owner 清单与 allowed files 一致性问题消除。

### DS F-2（non-blocking）— `EvidenceBackedFactCandidate` 符号迁移策略未单独裁决

**状态**: 已闭合。Plan 已要求 implementation closeout 单独说明处置策略，并禁止新旧定义并存、alias、compatibility re-export 或旧 candidate wrapper。

## Design Source 24/25 章一致性

Follow-up fix 的处理方向与 design source 一致：

- 第 24.3 章要求 `ConversationCompactOutputVNext` 作为 compactor 唯一输出 schema，与 plan 要求收敛到单一 public `compact()` vNext contract 一致。
- 第 24.3 章定义 `EvidenceBackedFactCandidate` 作为 vNext output candidate 子结构，与 plan 要求 closeout 单独裁决该符号处置策略一致。
- 第 25 章要求 Context Governance 只接受 vNext candidate，与 plan 禁止旧 candidate wrapper / adapter 一致。
- Follow-up fix 不引入 compatibility wrapper / alias / re-export，与 design 禁止兼容性代码一致。

## Control Doc / Plan / Follow-up Fix Artifact 三方一致性

| 检查项 | 一致性 |
|---|---|
| control doc implementation status | 与 follow-up fix artifact 第 49 行一致 |
| control doc next entry point | 与 follow-up fix artifact 第 51 行一致 |
| control doc follow-up fix artifacts 记录 | 与 follow-up fix artifact 第 52 行一致 |
| plan allowed files 增补 | 与 follow-up fix artifact 第 30 行一致 |
| plan implementation boundary 禁止范围 | 与 follow-up fix artifact 第 31 行一致 |
| plan `run_input.py` 边界澄清 | 与 follow-up fix artifact 第 32 行一致 |
| plan `EvidenceBackedFactCandidate` closeout 要求 | 与 follow-up fix artifact 第 33 行一致 |
| plan 条件测试说明 | 与 follow-up fix artifact 第 44 行一致 |

三方一致，无矛盾。

## Conclusion

`pass`。

Follow-up fix 完整处理了 Controller adjudication 的全部 accepted findings：

1. **Blocking**: `open_host.py` / `api.py` 缺失于 allowed files → 已增补，scope 严格限定。
2. **Non-blocking**: `run_input.py` dependency severance 边界模糊 → 已具体化，歧义消除。
3. **Non-blocking**: `test_package_exports.py` 条件触发 → 已确认覆盖。
4. **Non-blocking**: `EvidenceBackedFactCandidate` 迁移策略未裁决 → 已纳入 closeout 要求。

上一轮全部 5 项 findings（1 blocker + 4 non-blocking）均已闭合。Plan、control doc 与 follow-up fix artifact 三方一致。Pre-Slice C 可进入 implementation gate。
