# WU-SEMANTIC-OWNERSHIP-01 Aggregate Regression Fix Slice 3 第二个 Production Defect Plan Correction（AgentCodex）

## 1. Gate identity / verdict

- 日期：`2026-07-19`。
- Umbrella：既有`WU-SEMANTIC-OWNERSHIP-01` aggregate regression fix Slice 3；不是新WU。
- Gate：`S3-STOP-F02`第二次plan correction。
- 执行者：AgentCodex；未启动subagent。
- Verdict：`READY_FOR_DUAL_COMPLETE_PLAN_REVIEW`。
- Implementation / tests / review / stage / commit：`NOT_AUTHORIZED / NOT_RUN`。
- Final corrected plan SHA-256：`466fd5fd717c1ea35a4da0807ef425300ea7b4c855c400361805438681bcea6b`。

本gate只修改既有aggregate fix plan并新建本artifact。没有修改production、tests、utility、README、workflow、control或既有review/continuation/Controller artifacts；没有实施或测试修复，没有执行code/plan review，没有stage/commit/push/PR。

## 2. Authority 与 entry locks

唯一当前authority：

- Controller artifact：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-second-production-defect-controller-adjudication.md`。
- SHA-256：`9a7f640fad66a8e26edf86e8fea72d09dbadf1c8e80f7d12e6a14106a8a67fa8`。
- Verdict：`S3-STOP-F02 = ACCEPTED_CURRENT_FIX / PLAN_CORRECTION_REQUIRED / NOT_READY_FOR_CODE_REVIEW`。

Git locks：

- branch：`phaseflow/host-issues-control`。
- accepted corrected-plan base / HEAD：`48c6cc5ef74f273b1b592682ae9ab3e14cb48cbe`。
- parent：`9e7a4e9d4796b9c382d44494bb10efa64787b199`。
- tree：`b4904404c43dd0c36132433af74dd6740d24c713`。
- entry plan SHA-256：`e870921ec608247a666d03ca7845c1d8a6453409392201a95eb16933ec53ef56`。
- entry staged diff：空。

## 3. 完整读取范围

已完整读取用户指定真源：

1. `AGENTS.md`
2. `docs/host/issues-implementation-control.md`
3. `docs/phaseflow-umbrella-optimization-control.md`
4. `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md`
5. `docs/host/design.md`
6. `docs/engine/design.md`
7. `docs/tool/design.md`
8. `docs/fins/design.md`
9. `docs/ui/design.md`
10. `docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md`
11. `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-implementation-continuation-codex.md`
12. `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-second-production-defect-controller-adjudication.md`

已完整读取S3原stop/纠正/plan review/fix/re-review/accepted-commit/resume链：

- `wu-semantic-ownership-01-aggregate-regression-fix-s3-implementation-controller-authorization.md`
- `wu-semantic-ownership-01-aggregate-regression-fix-s3-implementation-codex.md`
- `wu-semantic-ownership-01-aggregate-regression-fix-s3-production-defect-controller-adjudication.md`
- `wu-semantic-ownership-01-aggregate-regression-fix-s3-plan-correction-codex.md`
- `wu-semantic-ownership-01-aggregate-regression-fix-s3-plan-correction-controller-validation.md`
- `wu-semantic-ownership-01-aggregate-regression-fix-s3-plan-review-mimo.md`
- `wu-semantic-ownership-01-aggregate-regression-fix-s3-plan-review-ds.md`
- `wu-semantic-ownership-01-aggregate-regression-fix-s3-plan-review-controller-adjudication.md`
- `wu-semantic-ownership-01-aggregate-regression-fix-s3-plan-review-fix-codex.md`
- `wu-semantic-ownership-01-aggregate-regression-fix-s3-plan-review-fix-controller-validation.md`
- `wu-semantic-ownership-01-aggregate-regression-fix-s3-plan-rereview-mimo.md`
- `wu-semantic-ownership-01-aggregate-regression-fix-s3-plan-rereview-ds.md`
- `wu-semantic-ownership-01-aggregate-regression-fix-s3-plan-rereview-controller-adjudication.md`
- `wu-semantic-ownership-01-aggregate-regression-fix-s3-corrected-plan-accepted-commit-controller-validation.md`
- `wu-semantic-ownership-01-aggregate-regression-fix-s3-resumed-implementation-controller-authorization.md`
- `wu-semantic-ownership-01-aggregate-regression-fix-s3-implementation-continuation-codex.md`
- `wu-semantic-ownership-01-aggregate-regression-fix-s3-second-production-defect-controller-adjudication.md`

当前相关代码已核对：DocumentProcessor marker协议、`SecProcessor`空marker实现、`sec_form_section_common.py`的初始化/refresh/table mapping/public consumers、10-K/10-Q与BS同族二次postprocess、现有owner harness与public最小复现，以及受保护Docling diff。

## 4. 第一性原理与root cause

动机成立且严重性判断正确。直接证据来自同一public call path：

1. DocumentProcessor协议允许不支持marker的processor返回空字符串，并要求上层安全降级。
2. `SecProcessor.get_full_text_with_table_markers()`正确返回`""`。
3. `_assign_tables_to_virtual_sections()`遇空marker直接返回，不产生table mapping。
4. 同一次`_refresh_virtual_section_state()`随后要求base table refs与virtual table refs完全相等。
5. 因而任何“形成合法virtual sections + base含表 + marker unsupported”的SecProcessor-backed表单都必然在构造期失败。

这不是日志、顺序、coverage或测试夹具推断。Controller已从public `TenKFormProcessor`复现，continuation又以真实AAPL与最小合法HTML闭合同一数据矛盾。

唯一owner是`dayu/fins/processors/sec_form_section_common.py`的虚拟章节构建/刷新/table ownership state machine。扩展SecProcessor marker能力会扩大不必要边界；把表格放入首/最近章节会把未知归属伪装为业务事实；下游`list_tables()`补偿则违反唯一真源。最小正确修复是owner内原子发布完整virtual projection，证明不足时整体发布同源base contract。

## 5. Corrected implementation contract

Corrected plan固定以下可直接实施的owner contract：

1. 引入owner-private publication mode，明确区分candidate、published virtual与published base fallback；public methods不从空dict/list或偶然状态反推模式。
2. refresh先在局部候选中验证section tree、base tables、marker material及双向mapping；验证完成前不污染已发布三个projection字段。
3. base tables为空时，空mapping已完整，允许发布合法virtual sections。
4. base tables非空且marker缺失，或marker不能证明每个base table唯一归属时，整体回退base sections/tables/read contract；不发布partial virtual state。
5. marker完整时，每个public base table必须有唯一非空ref、在marker material中恰好出现一次并落入恰好一个无歧义virtual range，随后一次提交完整`_virtual_sections`、`_virtual_section_by_ref`、`_table_ref_to_virtual_ref`与section table refs。
6. 重复base ref、marker dangling ref、同ref重复/多归属、section tree悬挂或双向矛盾继续在commit前`ValueError` fail-closed，不被fallback吞掉。
7. 删除`_assign_unmapped_tables_by_position()`与`list_tables()`的`fallback_ref`/`last_known_ref`首/最近章节补偿；virtual mode只消费exact published mapping，base mode只消费base tables。
8. `list_sections()`、`list_tables()`、`read_section()`只消费同一publication；`get_section_title()`与`search()`不得形成混合视图。
9. base fallback是初始化生命周期终态。10-K/10-Q父类初始化后的第二次postprocess/refresh必须幂等短路，不再读marker/base、不重建candidate、不重新触发失败或half state；virtual成功路径保留现有10-Q identity约束。
10. DocumentProcessor marker contract、`SecProcessor`空marker、10-K/10-Q与BS同族subclass保持零diff；不新增DOM/raw HTML marker、capability schema、compatibility wrapper或第二resolver。

## 6. Exact allowlists / protected delta

Slice 3整体production allowlist：

```text
M dayu/documents/processors/docling_processor.py
M dayu/fins/processors/sec_form_section_common.py
```

前者是已完成、review-pending的`S3-STOP-F01` protected delta；第二次correction重新授权后只允许新增后者implementation diff。任何第三个production path立即STOP。

Slice 3 test allowlist保持既有六路径：

```text
M tests/documents/test_processors.py
M tests/fins/test_sec_pipeline_download.py
M tests/fins/test_processor_read_consistency.py
M tests/fins/test_fins_ingestion_tools.py
M tests/host/test_effective_execution_config.py
A tests/runtime/test_argparse_exit.py
```

当前六路径delta全部受保护；后续授权只能保留既有cases并增量增加owner/public tests，不得删除、重写或弱化已完成Docling matrix、preprocess/Host/runtime cases与S3-STOP-F02最小复现。

Slice 3 README allowlist只含`dayu/fins/README.md`，用于按现有开发者手册职责同步已经实现的atomic virtual/base publication与no-guessing稳定语义。根README、`dayu/README.md`、`tests/README.md`均为`NO_UPDATE`。本plan-only gate未修改任何README。

## 7. Six owner/public counterexamples

Corrected plan纳入Controller §4全部反例：

1. public `TenKFormProcessor` + marker unsupported + base table：构造成功，逐值回退同源public `SecProcessor` sections/tables/read contract，双向一致。
2. marker supported + complete mapping：发布virtual sections与完整唯一双向mapping。
3. marker supported + incomplete proof：不发布partial virtual state，整体回退base contract。
4. duplicate / dangling / contradictory：commit前fail closed，不被fallback吞掉，不留下half state。
5. zero-table：marker unsupported不导致合法virtual sections被无意义放弃。
6. 10-K/10-Q second postprocess refresh：fallback后幂等、不读marker、不重入、不失败、不重生half state；existing complete virtual refresh/identity contract保持。

这些cases必须从public constructor/methods或typed owner harness的public list/read结果观察；禁止首/最近章节expected、private-only assertion、try/except“不抛即可”或测试内mapping算法镜像。

## 8. Validation / coverage / README / scans correction

计划保持并强化以下门禁：

- 先关闭S3-STOP-F02六类matrix，再fresh回归已完成Docling 8-node caption matrix，再继续九owner coverage。
- canonical non-coverage suite仍要求0 failed且AR-F06真实执行；coverage前exact collect-only必须唯一收集accepted scheduler node，coverage只deselect该单node。
- final changed-production集合仍精确219，`219/219` fresh line coverage均`>=80.00%`；Docling与`sec_form_section_common.py`本来就在集合内，不得改变成员数。Continuation focused/stop百分比不作签署。
- full pyright仍为0 errors/warnings/informations；Ruff immutable 144-set无新增且mutable paths零finding；不得加ignore/noqa/cast/Any/object/getattr fallback。
- wheel+sdist build、six canonical scans、Slice 2 stale-owner scans、real AAPL download/process、R03 public Host、live browser cleanup、upload POSIX/Windows相关nodes、HKEX evidence、安全矩阵与configured-secret semantic scan全部fresh执行。
- virtual owner scan要求`_assign_unmapped_tables_by_position|fallback_ref|last_known_ref`零命中，并证明DocumentProcessor/SecProcessor marker contract与10-K/10-Q/BS subclass相对base零diff。
- README按§6所述：`dayu/fins/README.md=UPDATE`，其它三个README=`NO_UPDATE`。

这些要求不削弱canonical、pyright、Ruff、build/smoke/security或`219/219 >=80%`任何既有gate。

## 9. Retained security / deferred / quota decisions

- Config source与Host internal SQLite/EventLog exact effective-execution canonical fact继续是`ACCEPTED_TRUSTED_INTERNAL`。
- Tool Trace hot/cold/query、audit、public HostEvent/read/outbox、memory/compact/evidence/runner-call observation等LLM-facing material、operator logs、其它outputs、diff与reviews继续逐surface `ZERO_REQUIRED`。
- Gemini quota保持`EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING`；禁止额外真实provider调用，禁止修改config/model/key/retry/quota/budget。
- `AR-F06=RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX`。
- `AR-F07=PENDING_RELEASE_BLOCKER`，Darwin skip不代替真实Windows evidence。
- Issues 142/151/175/177/178、Topic 8/9、统一tool authorization、secret infrastructure、TruncationManager wiring、storage-state lifecycle与Fins hard-kill/process isolation均不实施。

## 10. Entry protected hashes

以下用户指定paths在本gate必须且最终仍须保持entry hash：

| path | entry SHA-256 |
|---|---|
| `dayu/documents/processors/docling_processor.py` | `e2ab00fd984a4c27c30254d62ce038fafb91b9bc88d03eb786ad29f27acfd649` |
| `tests/documents/test_processors.py` | `6aba755cdb920f2f427f8f0375886ce14eb7b32f521f2d5ecde3c20d58be8f0b` |
| `tests/fins/test_sec_pipeline_download.py` | `f82c1416deac4f95cbe3e3feb4547410d077d41139fa0d8ac1915ca6d44a0c21` |
| `tests/fins/test_processor_read_consistency.py` | `e3aec818f1a397b46c004de1e6dc2b58bd1eb334d8c9cc142f97baecdea09489` |
| `tests/fins/test_fins_ingestion_tools.py` | `6ece9288834ab3953be8880276079a003f58a02629a2230459d728b95ff2f747` |
| `tests/host/test_effective_execution_config.py` | `e3a85caded7bda956e95d5ebd336cd60815ec1d227c134f46a9678d6a96c6acf` |
| `tests/runtime/test_argparse_exit.py` | `3aa607842a96b7425b964f3c030dc2b427e5bba0dd89abc65e20ed7306ce3f3d` |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-implementation-continuation-codex.md` | `3432724515aff3d1591a0c91ad83b31b7085fd01b39d7fe418ef68839951aaa7` |
| `docs/host/issues-implementation-control.md` | `e48b41c343121931913e7bd7ce52833cfd2fc47a3ae9d0f975ddbe490b0bbcc2` |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-second-production-defect-controller-adjudication.md` | `9a7f640fad66a8e26edf86e8fea72d09dbadf1c8e80f7d12e6a14106a8a67fa8` |

附加Controller-owned dirty paths同样zero-write：

| path | entry SHA-256 |
|---|---|
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-corrected-plan-accepted-commit-controller-validation.md` | `4d0b7b64544584be9dca8a57301cf3d27343130fad5664c9635681e45c88eba5` |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-resumed-implementation-controller-authorization.md` | `a21eaabc88885a5134f000a94e965e495fbcd9f79a9b080abb857ea31967eb3c` |

## 11. Stop conditions

立即STOP条件包括：

- 需要第三个production path、扩test allowlist、改marker producer contract、改10-K/10-Q/BS subclass或增加capability/schema/raw DOM marker。
- 需要首/最近章节、标题/顺序/相似度、偶然base ref或日志猜ownership；需要compat分支、下游fallback、第二resolver、broad catch。
- incomplete proof不能整体base fallback；duplicate/dangling/contradictory不能fail closed；zero-table不能保留virtual；二次postprocess不能在owner内幂等。
- protected hash漂移、plan gate出现production/test/README/utility diff、staged非空或Controller-owned artifact被覆盖。
- AR-F05再暴露F01/F02之外production defect；219集合变化；coverage需要第二deselect；canonical/pyright/Ruff/build/smoke/security任一gate不能满足。
- configured-secret zero-required surface非零，或trusted-internal logical path超出exact Config/Host owner。

## 12. Exact plan-only diff / validation evidence

本节在artifact完成后记录final doc-only evidence；不包含implementation测试结果。

- AgentCodex allowlist：

  ```text
  M docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md
  A docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-second-production-defect-plan-correction-codex.md
  ```

- Plan diff：`130 insertions / 51 deletions`。
- New artifact：`A`，`221`行。
- `git diff --check`：`PASS`，exit 0，无输出。
- staged diff / staged name-status：空。
- protected hash audit：§10全部十个用户指定path与两个附加Controller-owned path逐项等于entry SHA-256。
- Implementation tests / coverage / pyright / Ruff / build / scans / smokes / security：`NOT_RUN_BY_PLAN_ONLY_GATE`。

## 13. Next gate

唯一next gate：AgentMiMo / AgentDS对完整final plan与本artifact做双路完整plan review。

禁止直接恢复implementation、进入code review、aggregate、stage/commit/push/PR或closeout。第一次plan correction的review/re-review结论不能代替本次完整review；只有双路review、Controller逐条裁决、AgentCodex plan-only fix、双路完整re-review与Controller新授权全部完成后，才可恢复Slice 3 implementation。

Final verdict：`READY_FOR_DUAL_COMPLETE_PLAN_REVIEW`。
