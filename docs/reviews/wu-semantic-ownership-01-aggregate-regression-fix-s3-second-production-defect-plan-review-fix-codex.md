# WU-SEMANTIC-OWNERSHIP-01 Slice 3 第二个 Production Defect Plan Review Fix（AgentCodex）

## 1. Gate identity / verdict

- 系统时钟：`2026-07-19T17:17:21+0800`。
- Umbrella：既有`WU-SEMANTIC-OWNERSHIP-01` aggregate regression fix Slice 3；不是新WU。
- Gate：第二次plan correction后的plan-review fix。
- 执行者：AgentCodex；未启动subagent。
- Verdict：`PLAN_FIX_COMPLETE / READY_FOR_CONTROLLER_VALIDATION_AND_DUAL_COMPLETE_REREVIEW`。
- Implementation / tests / review / stage / commit：`NOT_AUTHORIZED / NOT_RUN`。
- Immutable reviewed plan SHA-256：`466fd5fd717c1ea35a4da0807ef425300ea7b4c855c400361805438681bcea6b`。
- Final fixed plan SHA-256：`552df22871f3eb07465b971ca3fdf182032f3b2087e27442b0d78a1b7d8acc04`。

本gate只修改既有aggregate fix plan并新增本artifact。没有修改production、tests、README、utility、workflow、control或既有artifact；没有实施或运行修复，没有执行review，没有stage/commit/push/PR。

## 2. Authority

唯一plan-review-fix authority：

| Artifact | SHA-256 |
|---|---|
| MiMo complete plan review | `6e747659183c0c59efed30e22129e3c5510802ae154be307d2d122f3449854dc` |
| DS complete plan review | `6c7556f20c78901b188f01649184b2df7cd479ab3d2facd3bf9a1c3af56ed822` |
| Controller adjudication | `725db848f7fb0eb9a2418a55ae90008b74131b5b360e8948415d3bb17b88daeb` |

Controller verdict为`PLAN_FIX_REQUIRED / ACCEPTED_GROUPS=4 / BLOCKER=0 / DESIGN_CONTRADICTION=0`。本次只修`S3-P2-PF01`—`S3-P2-PF04`，没有新增fix、schema、production path、test path或allowlist。

## 3. 完整读取与代码证据

本gate完整读取用户指定的`AGENTS.md`、两份control、overdesign Controller discussion、Host/Engine/Tool/Fins/UI五份design、immutable reviewed plan、MiMo/DS reviews、Controller adjudication、second-defect Controller/correction/validation链及S3 stop→correction→review/fix/re-review→accepted-commit→resume→continuation历史链。

当前代码直接证据：

- `sec_form_section_common.py`当前五个public consumers是`list_sections()`、`list_tables()`、`get_section_title()`、`read_section()`、`search()`；不存在第六个consumer。
- `_initialize_virtual_sections()`内首次调用`_refresh_virtual_section_state()`，当前公开构造失败在这次首次publication入口发生。
- `_filter_table_refs_by_availability()`会静默丢弃不在base table refs中的raw marker ref。
- `_assign_unmapped_tables_by_position()`会按最近前驱或首章节猜测未映射表格归属。
- `list_tables()`当前存在`fallback_ref`/`last_known_ref`下游补偿。
- `expand_ten_k_virtual_sections_content()`与`expand_ten_q_virtual_sections_content()`都以现有`if not full_text or not virtual_sections: return`开头，空candidate行为不是未知事实。

因此四组accepted finding均由同一owner代码直接证据支持；修复动机成立，严重性没有被高估。最小正确方向仍是在`sec_form_section_common.py`唯一owner内固定原子typed publication，而不是扩marker producer、subclass或下游consumer。

## 4. Finding closure

### S3-P2-PF01 — CLOSED IN PLAN

Plan已固定owner-private typed state：

```text
BUILDING
VIRTUAL_PUBLISHED
BASE_FALLBACK_PUBLISHED
```

- `_initialize_virtual_sections()`只初始化`BUILDING`并建立candidate。
- `_refresh_virtual_section_state()`是唯一terminal transition owner。
- Base fallback是幂等terminal；virtual refresh保持既有identity约束。
- 五个public consumers逐一固定`mode != VIRTUAL_PUBLISHED -> base processor`guard；只有virtual mode消费virtual projection。
- Reviewer“六个public methods”的计数已纠正为五个。

### S3-P2-PF02 — CLOSED IN PLAN

Plan已作唯一helper处置与固定validation order：

1. 物理删除`_filter_table_refs_by_availability()`及其调用，保留raw marker refs、出现次数与range/title归属证据。
2. 物理删除`_assign_unmapped_tables_by_position()`及其调用，不保留最近/首章节猜测。
3. 先验证每张base table的`table_ref`非空、唯一；缺失/重复fail-closed。
4. 再验证raw marker dangling；再验证marker重复/多section、tree与双向矛盾，全部fail-closed。
5. 只有矛盾检查通过后，`base_refs - mapped_refs`非空才是incomplete并whole-base fallback；完整且双向一致才publish virtual。
6. `incomplete + dangling`固定dangling优先fail-closed；无dangling但range/title不能唯一归属固定为incomplete whole-base fallback。

### S3-P2-PF03 — CLOSED IN PLAN

- Plan显式追溯`_initialize_virtual_sections()`内首次refresh是首次publication decision与当前失败入口。
- 首次refresh与10-K/10-Q subclass第二次postprocess/refresh复用同一typed终态。
- 首次fallback必须清空全部candidate并发布`BASE_FALLBACK_PUBLISHED`；后续refresh在读取marker/base前幂等no-op。
- Base tables为空时空mapping已完整，发布`VIRTUAL_PUBLISHED`。
- 两个form-common expand函数现有空candidate guard被锁定为zero-diff直接证据，并要求public 10-K/10-Q re-entry验证；guard漂移才STOP，不扩form-common/subclass allowlist。

### S3-P2-PF04 — CLOSED IN PLAN

Public unsupported/incomplete fallback oracle已收紧为逐值比较：

- base/form完整section ref序列；
- 完整table ref序列；
- 每张table的`section_ref`；
- 每个base section的`read_section(ref)["tables"]`；
- 通过每个base ref调用form的`get_section_title()`、`read_section()`与`search(..., within_ref=ref)`并与base结果逐值比较。

Counterexample matrix已固定`incomplete + dangling -> ValueError`，以及“无dangling但range/title不能唯一归属 -> incomplete whole-base fallback”。禁止只比较长度、非空、摘要或“不抛异常”。

## 5. Rejected / narrowed candidates retained

- MiMo 05作为独立finding保持`rejected-as-duplicate`；其有效guard精确化只归入PF01，没有形成第五组fix。
- DS-F03“expand空列表行为未知”保持`rejected-as-evidence-invalid`；现有guard证据与re-entry test要求归入PF03。
- Private enum没有升级为public schema。
- 没有新增production/test/README/utility路径，没有修改allowlist。

## 6. Exact scope

本gate允许且实际只有：

```text
M docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md
A docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-second-production-defect-plan-review-fix-codex.md
```

相对当前HEAD，plan diff为`135 insertions / 53 deletions`；本artifact为新增`155`行。两项合计就是本gate exact doc-only diff，未把其它pre-existing dirty paths归入本gate。

## 7. Protected hash audit

以下本gate实际entry protected paths均保持不变：

| Path | SHA-256 |
|---|---|
| `dayu/documents/processors/docling_processor.py` | `e2ab00fd984a4c27c30254d62ce038fafb91b9bc88d03eb786ad29f27acfd649` |
| `tests/documents/test_processors.py` | `6aba755cdb920f2f427f8f0375886ce14eb7b32f521f2d5ecde3c20d58be8f0b` |
| `tests/fins/test_sec_pipeline_download.py` | `f82c1416deac4f95cbe3e3feb4547410d077d41139fa0d8ac1915ca6d44a0c21` |
| `tests/fins/test_processor_read_consistency.py` | `e3aec818f1a397b46c004de1e6dc2b58bd1eb334d8c9cc142f97baecdea09489` |
| `tests/fins/test_fins_ingestion_tools.py` | `6ece9288834ab3953be8880276079a003f58a02629a2230459d728b95ff2f747` |
| `tests/host/test_effective_execution_config.py` | `e3a85caded7bda956e95d5ebd336cd60815ec1d227c134f46a9678d6a96c6acf` |
| `tests/runtime/test_argparse_exit.py` | `3aa607842a96b7425b964f3c030dc2b427e5bba0dd89abc65e20ed7306ce3f3d` |
| `docs/host/issues-implementation-control.md` | `7bcbacccf14b2b0d1fb73d935453709403a5887c1ed20e03dd475fc93659430b` |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-implementation-continuation-codex.md` | `3432724515aff3d1591a0c91ad83b31b7085fd01b39d7fe418ef68839951aaa7` |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-second-production-defect-controller-adjudication.md` | `9a7f640fad66a8e26edf86e8fea72d09dbadf1c8e80f7d12e6a14106a8a67fa8` |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-second-production-defect-plan-correction-codex.md` | `15b53e8223883e572653eb4d26aa54390d2081ba84d986f10523722926da86a6` |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-second-production-defect-plan-correction-controller-validation.md` | `36df4cedf04e01746446de96d92b1b5e6f035d9b601e54ea8b084cdd456d836f` |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-second-production-defect-plan-review-mimo.md` | `6e747659183c0c59efed30e22129e3c5510802ae154be307d2d122f3449854dc` |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-second-production-defect-plan-review-ds.md` | `6c7556f20c78901b188f01649184b2df7cd479ab3d2facd3bf9a1c3af56ed822` |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-second-production-defect-plan-review-controller-adjudication.md` | `725db848f7fb0eb9a2418a55ae90008b74131b5b360e8948415d3bb17b88daeb` |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-corrected-plan-accepted-commit-controller-validation.md` | `4d0b7b64544584be9dca8a57301cf3d27343130fad5664c9635681e45c88eba5` |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-resumed-implementation-controller-authorization.md` | `a21eaabc88885a5134f000a94e965e495fbcd9f79a9b080abb857ea31967eb3c` |

Control doc的当前hash与immutable reviewed plan中保存的更早plan-correction入口hash不同；本gate以开始工作后实际读取到的`7bcb...430b`为保护基线，未写control。

## 8. Validation

- `git diff --check`：`PASS`，exit 0，无输出。
- staged diff / staged name-status：空。
- Production/tests/README/utility/control/protected artifacts：zero-write；§7逐hash复核全部通过。
- Implementation tests / coverage / pyright / Ruff / build / scans / smokes / security：`NOT_RUN_BY_PLAN_ONLY_GATE`。

## 9. Open questions / residual risks

没有plan-level open question。`S3-STOP-F02`仍是未实施的blocking production correctness defect；本artifact只关闭plan findings，不关闭production defect、AR-F05、AR-F06或AR-F07。

Retained residuals不变：`AR-F06=RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX`；`AR-F07=PENDING_RELEASE_BLOCKER`；Gemini quota与Issues 142/151/175/177/178、Topic 8/9及统一tool authorization边界不变。

## 10. Next gate

唯一next gate：Controller validation与AgentMiMo/AgentDS对完整final plan及本fix artifact做双路完整re-review。

禁止直接恢复implementation、进入code review/aggregate、修改control、stage/commit/push/PR或closeout。只有Controller validation、双路完整re-review与Controller新授权全部完成后，才可恢复Slice 3 implementation。

Final conclusion：`PLAN_FIX_COMPLETE / READY_FOR_CONTROLLER_VALIDATION_AND_DUAL_COMPLETE_REREVIEW`。
