RUNTIME/PROVIDER/MODEL: claude/ds-flash/deepseek-flash[1m]
CANARY=ds-flash-4a996352

# Code Review：#198 S1 final2（ds-flash 备份路，F2/F3 修复后）

## Scope

- Mode: current changes（issue #198 S1 修复候选的独立备份路 `$deepreview`；只审锁定的精确 14 文件 S1 切片，不审其它 dirty WU）
- Branch: `codex/upload-material-oracle`；Workspace: `/Users/leo/workspace/dayu-agent-r`
- Base/HEAD: `47a9cb64e63780deb568a9e2c6fdd0120441cf2f`（审查开始与结束各实测一次 `git rev-parse HEAD`，均为该值）
- Diff digest: `git diff --binary -- <14 文件，顺序见 F2/F3 fix 记录>` + `shasum -a 256` = `f1e1a91557cda273c5d0b77900920381727322a8edea69d6061cda27f0f6bd21`，与任务给定值逐字一致；审查结束时按同一命令复算仍为该值，`git status --porcelain -uno` 与开始时快照一致，本审查未修改、未格式化任何文件
- Diff stat: 14 files changed, 2163 insertions(+), 65 deletions(-)
- Included scope（14 文件白名单，顺序与锁命令一致）：`README.md`、`dayu/cli/output.py`、`dayu/fins/README.md`、`dayu/fins/direct_events.py`、`dayu/fins/ingestion_runtime.py`、`dayu/fins/pipelines/cn_download_workflow.py`、`dayu/fins/pipelines/cn_pipeline.py`、`dayu/service/fins_wait_adapter.py`、`tests/README.md`、`tests/cli/test_output.py`、`tests/fins/test_cn_download_runtime.py`、`tests/fins/test_cn_download_workflow.py`、`tests/fins/test_fins_ingestion_runtime.py`、`tests/service/test_fins_wait_adapter.py`
- Excluded scope（明确不纳入本切片、也不从其 hunk 反推 S1 语义）：`dayu/fins/storage/_fs_source_integrity.py`、`tests/fins/test_fins_storage_atomicity.py`（点号元数据独立 WU，实测 diff 仅新增「忽略非点号边界之外的 `.` 前缀条目」判定，F2 用例注入的是非点号 `foreign-post-repair.bin`，不依赖该 WU 行为）、`docs/gateflow/*` 队列/序列文档、既有 `docs/reviews/*` artifact。三份 README 的 diff 各含 1 行点号元数据句，属 adjudication MiMo F5 已登记的分行 staging 事项，本 review 只审其中的 S1 句
- 对齐材料（本轮实读）：`AGENTS.md`、accepted plan `docs/gateflow/issue-198-download-failure-projection-plan-20260928.md`（第 41–63 行 S1 正文，含第 57 行同请求重跑要求）、`docs/gateflow/issue-198-s1-implementation-20260929.md`、`docs/gateflow/issue-198-s1-code-review-adjudication-20260928.md`（含 F2/F3 裁决段）、`docs/gateflow/issue-198-s1-code-review-f2f3-fix-20260929.md`、上轮本人 review `docs/reviews/code-review-20260929-190212.md`、`docs/gateflow/issue-198-s1-cninfo-single-day-evidence-20260929.md`
- Parallel review coverage: 无。按任务约束未派发任何子 Agent，全部走读、复跑、注入反证由主 reviewer 逐条完成
- 本轮 delta 归属：`stat` 显示 12 个文件最后修改于 09-29 09:53–10:24，仅 `dayu/fins/pipelines/cn_pipeline.py`（19:08:03）与 `tests/fins/test_cn_download_runtime.py`（19:09:43）在 19 时区段被改，与 F2/F3 fix 记录自述一致。该证据只是佐证：两个 SHA 之间的旧字节未留档，无法逐字复算 delta（见 Residual Risk）

## F2 反证：真实同仓中止 → 清 mutation → 同 request 重跑

**用例**：`tests/fins/test_cn_download_runtime.py:1676`（direct/job 参数化，至 `:1873`）。

**真实链核对（逐句读产品代码，非读断言）**

1. 同仓同 request：`request` 在 `:1697` 构造一次，中止帧与重跑帧共用同一对象；仓储为 `_build_runtime_repositories`（`:1282`）的真实 FS 实现（`FsSourceDocumentRepository` 等），workflow、`CnDownloadAdapter`、direct/job 收口均为生产实现；仅 discovery/transport/converter 是确定性 fake（外部 provider，允许）。
2. 首候选中止前确为「已修复」：`inject_post_repair`（`:1771`）只在 patch 生效后的**第二次** `list_source_integrity` 调用写入外来文件，而该 list 在 patch 前已重置（`:1769`）；专利 run 1 在 patch 之前完成，故这第二次枚举正是 `cn_download_workflow.py:397` 的 **post-repair** 枚举（首次枚举在 `:261`）。注入后 `original_list` 抛真实 storage typed preflight，经 `:403` 的 typed catch 转 `_integrity_abort`（`:551`）——不是测试直接造 `CnDownloadIntegrityAbort`，也不是 fake 分类器。
3. 中止帧语义：`assert len(calls) == 2`（`:1829`）锁「初始 + post-repair 各一次、无第三次」；`:1830` 只调用了首候选传输；`:1831` 第二候选 identity 目录不存在；`:1832` 首候选 PDF 回到原字节；`:1833` 公司 meta 旧字节保持。`:1848` 计数 `discovered=downloaded=1`、`failed=0`、`:1851` 行序 `[(首候选,"skipped"/"downloaded"),…]` 与行集在 direct/job 两侧一致（`:1852`/`:1865`），未处理候选不计数、不造行 —— 与 accepted plan 第 51 行计数口径一致。
4. 重跑语义：删除唯一外来文件后**不清任何其它状态**（`:1836`），同一 request 再走 `runtime.download` / `runtime.start_download`。断言首候选行 `skipped`（`:1851`，direct）、第二候选 `downloaded`、计数 `(1,1,0,0)`、`written_document_ids == [second_id]`（job，`:1865`）；`:1866` 传输只被调用于第二候选；`:1867-1869` 首候选字节保持原值、两份来源 meta 可由真实仓储读回；`:1870-1873` 用未 patch 的真实枚举确认两份 source 均为 `COMPLETE`。
5. 语义来源核对：`skipped` 只能来自 `cn_download_filing_workflow.py:188` 的 `phase_a_integrity.status is COMPLETE`（真实 `classify_source_integrity`，per-document）或 `:431` 的 Phase B 陈旧预取分支；`downloaded`→locator 投影在 `cn_pipeline.py:1565-1581`，计数与 rows 由 `download_contract.py:437-459` 从 typed rows 唯一派生、并在 `:373-391` 校验 `discovered == rows == 四类计数`。测试没有在测试侧重算 counts/IDs，也没有手造公共 RESULT。

**独立复跑**：`pytest -k post_repair_abort_then_same_request` → **2 passed, 38 deselected**（exit 0）。

**注入反证（不改仓库任何文件，仅在 `python -c` 进程内 patch 真实仓储方法）**

- 反证 A（把 COMPLETE 一律降为 MISSING，模拟「已完整来源不再 skip」）：用例 **2 failed**，失败点 `:1846`/`:1859`（重跑终态 `PARTIAL_FAILURE` ≠ `SUCCEEDED`）。证明用例对「完整来源未被识别为完整」敏感。
- 反证 B（只在重跑阶段把首候选 COMPLETE 强制成 REPAIR_REQUIRED，即「完整来源被当作需修复/复用域被击穿」）：用例 **2 failed**，失败点 `:1866` `assert ['cn-runtime-a1','cn-runtime-b2'] == ['cn-runtime-b2']`。
- 反证 B 的附加信息（正面结论）：该注入下首候选行仍是 `skipped`（产品 Phase B「陈旧预取结果」分支也会产出 `skipped`），因此**只断言行/计数的弱化版测试会被这次回归骗过**；`:1866` 的传输调用断言是这条用例的承重断言。当前用例同时具备两者，证据链完整，不构成缺陷。

**结论**：F2 在真实 owner 链上成立，且对两类可达回归敏感；未发现伪造公共结果、测试侧重算或把上次未处理候选计为已处理的情形。

## F3 反证：状态唯一真源与依赖方向

- 全仓 `rg "integrity_failed|_INTEGRITY_FAILED_STATUS"`：生产代码只有 `cn_download_workflow.py:54`（定义）与 `:558`（产出快照）+ `cn_pipeline.py:59`（导入）/`:1472`（消费）。旧 `_CN_TERMINAL_INTEGRITY_FAILED` 已从生产代码彻底消失（唯一残留是上轮 review artifact 的历史引用，非代码）。
- 依赖方向：`cn_pipeline.py:58-62` 从 `cn_download_workflow` 同向导入；该模块原有 `run_cn_download_stream_impl`（`:61`）与 `CnDownloadIntegrityAbort`（`:60`）已是同一方向的既有依赖。`rg "cn_download_workflow"` 显示仅有 `cn_pipeline.py` 与测试导入它，**无反向依赖、无循环导入**；未新增兼容 re-export 或 shim。
- 语义 owner：状态由产生快照的 workflow 拥有（`_integrity_abort` 用该常量构造私有结果），pipeline 仅做严格校验后投影，消费者复用 owner 的常量而非各自复制字面量 —— 与 AGENTS.md「同一事实唯一 owner」及上轮 L1 建议一致。
- 严格性未回退：`_summary_from_pipeline_result`（`:1444-1447`）仍只接受 `ok/cancelled`，`_summary_from_integrity_abort`（`:1471-1473`）只接受该私有状态，两者共用 `_project_cn_pipeline_summary`（`:1477`）的纯投影。测试 `tests/fins/test_cn_download_runtime.py:839-882` 用独立字面量钉死双向拒绝（普通入口拒 `integrity_failed`、失败入口拒 `ok`、坏 row 仍抛）。

## 旧 finding 无回退核对（F1～F21 汇聚清单）

| 已接受项（来源轮次） | 当前证据 | 状态 |
| --- | --- | --- |
| MiMo F1 / 单 filing typed preflight 保真 | `cn_download_workflow.py:344-369` typed catch；测试 `test_cn_phase_b_real_preflight_aborts_with_confirmed_prior_filing`、runtime 侧 phase B 用例 | 无回退 |
| MiMo F2 / 公共 enum 双向全集 | `tests/fins/test_fins_ingestion_runtime.py:6148-6149` 断言键/值全集相等 | 无回退 |
| MiMo F3 / CLI `reason_code=` | `dayu/cli/output.py:486-495`；`tests/cli/test_output.py` 断言 `reason_code="unsafe_publication"` 与文档行 `reason="来源暂时不可用"` 并存 | 无回退 |
| Kimi F1 / MiMo F4 / `reason_code=None` 占位 | `tests/cli/test_output.py` 新 EXECUTION 帧断言 `classification="execution"`、`reason_code="-"` | 无回退 |
| Kimi F1 / typed 零候选 direct+job 同源 | `ingestion_runtime.py:6995` 起的四值映射 + `_empty_download_summary_from_request(FAILED)`；`test_initial_typed_download_job_saves_structured_zero_summary_and_safe_message` | 无回退 |
| Kimi F2 / 私有 adapter failure 类型与单点 unwrap | `ingestion_runtime.py:587`、`_download_exception_cause`（`:6916`）在 `_classify_direct_error`/`_download_public_failure_from_exception` 各解一次 | 无回退 |
| Kimi F3 / 纯投影 helper 抽取 | `cn_pipeline.py:1477-1518`，两入口先验 status 再复用 | 无回退 |
| Kimi F4 / wait `scope_note` 逐字 | `fins_wait_adapter.py:592` 常量 + `:618` 投影；`tests/service/test_fins_wait_adapter.py` 独立字面量断言 | 无回退 |
| MiMo 第四/七次 / `FinsResultSummary` 放宽与负例 | `direct_events.py:677-690`；`tests/fins/test_fins_ingestion_runtime.py:6271-6288`（无 failure、SUCCESS 与 failure 混用、FAILURE+取消态） | 无回退 |
| K-F1 / fresh ticker 非空 company intent | `tests/fins/test_cn_download_runtime.py:1315` 起真实 `commit_batch→_validate_complete_source_tree` | 无回退 |
| MiMo 第七次 F2 / typed job 二次保存 WARN 固定标识 | `ingestion_runtime.py:5034-5035`；`test_typed_download_job_second_save_failure_logs_only_fixed_event` 断言无 `exc_info`/`error_type`/类名/秘密、record 仍 `RUNNING` 且摘要 `{}` | 无回退 |
| MiMo code review F1 / revision conflict runtime 投影 | `test_cn_post_repair_real_second_source_revision_conflict_preserves_public_summary`（`tests/fins/test_cn_download_runtime.py:1877` 起，direct/job） | 无回退 |
| ds-flash F2（上轮）/ 同请求重跑 | 本文件 F2 段 | **已修复** |
| ds-flash L1（上轮）/ 双处私有常量 | 本文件 F3 段 | **已修复** |
| ds-flash L2/L3/L4（上轮，纯风格） | `tests/fins/test_cn_download_runtime.py:14-15` 仍为两条同模块 import；`fins_wait_adapter.py` `_failure_message` 仍为 Google 风格 docstring；`tests/service/test_fins_wait_adapter.py:421-422` 顶层函数间仍只有 1 空行 | 未修（非阻断，沿用上轮裁决） |
| 取消控制流保持 | 普通完整 suite 通过；插桩敏感的两条取消时序用例仅在 coverage 命令中被排除并有记录 | 无回退 |

## CLI 三日证据界限（本轮独立复核）

- 六个原始流 SHA-256 现场复算与证据文档逐字一致：单日探针 `f5c31806…`、三天探针 `b5a0c53d…`、baseline stdout `8cee933d…`、typed-failure stdout `0804026d…` / stderr `5349d095…`、readback stdout `b4980068…`。
- 内容实读：单日探针 `provider_page_total=0`；三天探针 `provider_page_total=2`，两条均为 `2025-03-28`（摘要 `1222951198` + 全文 `1222951181`），产品选中全文；baseline stdout `discovered=1 downloaded=1 skipped=0 rejected=0 failed=0`；typed-failure stderr 为 `status="failure"`、请求级零摘要、`classification="storage" … reason_code="unsafe_publication"` 与修复提示；readback 显示唯一 ID `complete` + `ingest_complete: true`。外来文件名在 stderr/stdout 均无匹配（本轮以零退出形式复跑，结果 `leak_rg_no_match`）。
- 界限判断（与上轮一致）：该证据走同一 CLI、同一 whole-kind typed 路径与同一公共投影，足以证明 S1 的 typed 失败投影；但它**不是**计划第 57 行那条单日命令，单日发现缺口（`fins-cninfo-single-day-discovery-window`）仍为独立 work unit，不得写成原命令通过。本沙箱无外网，无法独立重跑真实 provider，只能复核留档原始流。

## 其余门禁（本轮独立复跑）

| 命令 | 结果 |
| --- | --- |
| `pytest -k post_repair_abort_then_same_request tests/fins/test_cn_download_runtime.py` | 2 passed, 38 deselected（exit 0） |
| 受影响八文件 suite（`tests/runtime/test_log.py`、`tests/fins/test_fins_ingestion_runtime.py`、`tests/fins/test_cn_download_workflow.py`、`tests/fins/test_cn_download_runtime.py`、`tests/cli/test_output.py`、`tests/cli/test_fins_commands.py`、`tests/service/test_fins_wait_adapter.py`、`tests/service/test_fins_direct.py`） | **846 passed, 3 warnings**（edgartools 第三方弃用），exit 0 |
| `python -m pyright dayu/ tests/ utils/` | **0 errors, 0 warnings, 0 informations**，exit 0 |
| coverage（`coverage run --branch --source=<六改动模块>` + 同实现记录的两条取消时序 deselected） | 613 passed / 2 deselected；`cli/output.py` 81%、`fins/direct_events.py` 84%、`fins/ingestion_runtime.py` 87%、`pipelines/cn_download_workflow.py` 92%、`pipelines/cn_pipeline.py` 92%、`service/fins_wait_adapter.py` 92%，六文件均 ≥80%。新增段全覆盖：`_download_filters`/`_integrity_abort`（workflow 448-560 无缺失行）、`_summary_from_integrity_abort`/`_project_cn_pipeline_summary`（仅防御性 `:1500` ticker 不一致 raise 未覆盖）、typed job 二次保存 WARN（`:5034-5035`）已覆盖 |
| `git diff --check -- <14 文件>` | exit 0，无空白错误 |

## Findings

无阻断项。以下为按上轮格式记录的低级/风格项与观察，均不影响 S1 code gate：

### N1（low, info；中止帧行数断言依赖契约蕴含而非显式断言）

- 位置：`tests/fins/test_cn_download_runtime.py:1817`（只索引 `document_rows[0]`，未显式断言行数）。
- 反证结果：不可达。`FinsDownloadPublicSummary.__post_init__`（`direct_events.py:441-442`）强制 `len(rows) + omitted == discovered`，本帧 `discovered == 1` 且 `:1817` 成功索引 ⟹ 行数恰为 1、`omitted == 0`。
- 建议（不阻断）：可补 `document_rows == (…)` 全量断言与 sibling 用例（`test_cn_real_phase_b_abort_keeps_published_document_in_result_and_job`）对齐，纯可读性。

### N2（low；job 入口无逐项文档行）

- 位置：`dayu/fins/download_contract.py:491-521`（job 持久摘要只给 counts + written IDs，无逐项 row）。
- 真实可达反例：无（不是缺陷）。job 侧 skip 由 `skipped_count=1`、`:1866` 传输只调用第二候选、`:1870-1873` 两份真实 source `COMPLETE` 联合证明；direct 侧另有逐项行。
- 说明：F2/F3 fix 记录已如实声明该边界；若 LLM-facing 需要逐项 skip 明细，属独立需求而非 S1 gate 项。

### N3（low；README 句与其它 WU 行同 hunk）

- 位置：`README.md:322-323`、`dayu/fins/README.md:598-599`、`tests/README.md:24-25`（S1 句与点号元数据句相邻同一 hunk）。
- 影响：本 14 文件 SHA 内因此包含 3 行非 S1 内容；被锁定与复审的对象与最终提交对象需按 MiMo F5 的分行 staging 处理，否则提交会混入另一 WU。
- 修法：staging 时按行拆分（不使用 `git add -p` 的按 hunk 语义），提交前核对 staged patch 只含 S1 句。

## Open Questions

- 无。F2/F3 是否解除 gate 由总控裁决；本 review 对锁定快照给 pass-with-risks。

## Residual Risk

- **旧快照不可复算**：`86aa9a2b…` → `f1e1a915…` 的逐字 delta 无留档（未提交、无 stash），本轮以 fix 记录 + adjudication 自述 + 文件 mtime 佐证「只改两文件」；若总控要求逐字证明，需在下一轮保留旧快照。
- **混合工作树**：846 passed / 覆盖率 / pyright 均在含点号元数据独立 WU dirty 文件的树上运行；S1 新用例注入非点号条目、不依赖该 WU 行为，但纯 14 文件树未单独复跑（与前几轮相同的残余）。
- **调用计数耦合**：多候选用例把「post-repair 前恰两次 `list_source_integrity`」「`len(calls)==2`」锁为合同，未来 owner 调整枚举次数需同步更新注入点（有意的回归锁）。
- **`assert len(caplog.records) == 1`**：把 typed job 二次保存路径的 WARN 数量锁死，将来该路径新增合法 WARN 需同步调整。
- **测试调用 storage 私有成员**（`_identity_directory_path`、`_FILING_IDENTITY_NAMESPACE`、`FsSourceDocumentRepository` 实例方法 monkeypatch）：adjudication 已允许（不重算哈希、委托真源），对 storage 内部重构敏感。
- **未覆盖的独立 WU 仍成立**：单日 CNInfo 发现窗口、mid-filing revision conflict 分类（`fins-download-storage-sibling-errors`）、company commit 其它失败（`fins-download-indeterminate-publication-state`）、raw 诊断审计（`fins-other-raw-diagnostics-audit`）均未被本切片声称修复。本 review 未复验 S2 与真实网络条件。

## 失败命令与退出码披露（如实记录）

1. `rg -n "cn_download_workflow" -r dayu/ --include=*.py`：zsh 对未加引号的 `--include=*.py` 报 `no matches found`，命令退出 1。原因是本人命令的 glob 引号问题，不是仓库/测试失败；随后以 `rg … -g '*.py' || true` 复跑，exit 0。
2. 两处泄漏检查 `rg -c` 在预期无匹配时自身退出 1（`leak_rg_exit=1`），已按零退出形式复跑并记录 `leak_rg_no_match`，未依赖后续绿测抵消。
3. 两次注入反证命令的内层 pytest 退出 1（`inner_exit=1`），这是反证设计要观察的「测试必须失败」；两条命令整体以 `echo` 收尾，退出 0。除此之外本审查无其它非零退出。

## 结论

**pass-with-risks**（无阻断项；F2/F3 修复在真实 owner 链上成立）

1. 锁一致：HEAD `47a9cb64…` 与 14 文件 diff SHA-256 `f1e1a915…` 在审查前后各复算一次，逐字一致，未跨版本混审，未触碰其它 dirty WU。
2. F2 反证成立：真实 FS 仓储 + 真实 workflow/adapter/runtime 的 direct/job 两入口，同一 request 对象在清除唯一外来 mutation 后重跑，首候选按真实 per-document 完整性 `skip`（无传输调用）、第二候选 `downloaded`（恰一次传输）、计数 `discovered=2/downloaded=1/skipped=1/rejected=failed=0`、durable 字节/meta/COMPLETE 三重读回；中止帧未处理候选不计数、不造行、无目录、无传输。两次注入反证显示用例对可达回归敏感（并在反证 B 中证明传输调用断言是承重项）。
3. F3 反证成立：`integrity_failed` 私有状态全仓唯一真源在 `cn_download_workflow.py:54`，`cn_pipeline.py` 同向导入消费，旧重复常量已彻底移除，无反向/循环依赖，正常与失败两入口的严格 status 校验均未放宽。
4. 旧 finding 无回退：汇聚清单 16 项逐条有当前代码/测试证据；受影响八文件 846 passed、pyright 0/0/0、六改动文件覆盖率 81–92% 均本轮独立复跑通过；三日 CLI 证据六个原始流哈希与内容逐字复核一致，其证明界限如实保持（不替代计划单日命令）。
5. 未决/残余：N1–N3 与 Residual Risk 各条；S2、单日发现窗口、sibling 分类等独立 WU 未被本切片声称完成。
