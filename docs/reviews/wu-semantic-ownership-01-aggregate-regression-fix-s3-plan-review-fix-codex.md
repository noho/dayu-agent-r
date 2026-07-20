# WU-SEMANTIC-OWNERSHIP-01 Aggregate Regression Fix Slice 3 Plan Review Fix（AgentCodex）

## 1. Gate identity / verdict

- 日期：`2026-07-19`。
- Umbrella：既有`WU-SEMANTIC-OWNERSHIP-01` aggregate regression fix Slice 3；不是新WU。
- Gate：双路corrected-plan review后的Controller-authorized plan-review fix。
- 执行者：AgentCodex；未`/clear`，未启动subagent。
- Implementation：`NOT_AUTHORIZED / NOT_STARTED`。
- Verdict：`READY_FOR_DUAL_COMPLETE_PLAN_REREVIEW`。

本gate只修复Controller接受的`S3-PR-CF01`—`S3-PR-CF05`。没有修改production、tests、README、utility、workflow、control、Controller/reviewer artifacts；没有运行coverage implementation、stage、commit、re-review、code review、aggregate、push、PR或closeout。

## 2. 第一性原理复核

修正动机成立。当前Docling schema允许document-root ref `#`，但该ref不是caption文本引用；若直接交给`RefItem.resolve()`，项目`.venv`的`docling-core==2.74.0`会抛`RuntimeError`。因此正确owner仍是Docling table projection boundary：它应在typed ref进入resolve前识别root sentinel，而不是扩大异常捕获、解析raw pointer或在下游猜caption。

这一结论不改变已接受的最小owner修复：`_build_tables()`把同一个`DoclingDocument`传入caption resolver，resolver只消费`TableItem.captions`，public consumers继续统一读取`_TableBlock.caption`。问题不需要新schema、第二resolver、兼容层或production扩域。

## 3. Authority / entry locks

### 3.1 Git与计划入口

- branch：`phaseflow/host-issues-control`。
- immutable slice base / HEAD：`9e7a4e9d4796b9c382d44494bb10efa64787b199`。
- parent：`ba44bf877138235d53606d082341a7f7280af488`。
- tree：`7dc759e3bde5f6a257c21b60434f8874d157771a`。
- reviewed plan entry SHA-256：`ef4a0832f1885e4013d673294b944a56280619baab1f97d438896af5c8cbedcf`。
- plan-correction artifact entry SHA-256：`c5b788b03ab54638841a7bd58cb8d5978ef92de8ea120ff3a3408aedbaac2072`。
- entry staged diff：空。

Authority：

| Artifact | Entry SHA-256 |
| --- | --- |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-plan-review-mimo.md` | `f3d59d0ac7e6f5528fd90f3ab6104f504b08242093d2f658bd505371a620c1fa` |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-plan-review-ds.md` | `c606f94e9353862ec30600360dfce2b21662cfbb13137d5c0b4422d0ed02fa3b` |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-plan-review-controller-adjudication.md` | `c83e76d7c2d95a1df3d4f969d39c4ca907183947a977b2150672e9e6f19ee450` |

Controller ledger：`ACCEPTED_PLAN_FINDING=5`、`REJECTED_OR_NO_ACTION=11 groups`、`IMPLEMENTATION_AUTHORIZED=NO`。

### 3.2 六个Slice 3 test paths

| Path | Protected SHA-256 |
| --- | --- |
| `tests/documents/test_processors.py` | `75ca22edd531c27fc7ccf0ea1edc6f3ddf62e389a18af24f17bb6798713f2d1c` |
| `tests/fins/test_sec_pipeline_download.py` | `f82c1416deac4f95cbe3e3feb4547410d077d41139fa0d8ac1915ca6d44a0c21` |
| `tests/fins/test_processor_read_consistency.py` | `da55b5eb32a18eeef425a264fe9a172d888f9c2608dad9d9a0a098e4fe955459` |
| `tests/fins/test_fins_ingestion_tools.py` | `6ece9288834ab3953be8880276079a003f58a02629a2230459d728b95ff2f747` |
| `tests/host/test_effective_execution_config.py` | `e3a85caded7bda956e95d5ebd336cd60815ec1d227c134f46a9678d6a96c6acf` |
| `tests/runtime/test_argparse_exit.py` | `3aa607842a96b7425b964f3c030dc2b427e5bba0dd89abc65e20ed7306ce3f3d` |

### 3.3 Controller-owned / reviewer protected paths

| Path | Protected SHA-256 |
| --- | --- |
| `docs/host/issues-implementation-control.md` | `00b40ad39ea86aaf95c01d2db89b2e4fdd3d8c38805b20328854897ff6bc6883` |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s2-accepted-commit-controller-validation.md` | `bf5842031abe4306fb50cfce918c6fd2ff90bb219584a42fc20f8d2bc8a208ed` |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-implementation-controller-authorization.md` | `7d8fb7e0723c98edd5a8aa20692fe61d084d2ff7552cf821d74410f4a80243dc` |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-production-defect-controller-adjudication.md` | `71a7a62fbee5272ea64815e85d673f1c13819e605d3a5f303d785d8728624d81` |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-implementation-codex.md` | `addd3b10091bfbdb9294c26b570a1b1808e77c079d195c2d964eb384a27dd9f8` |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-plan-correction-controller-validation.md` | `1f1d1f5ca8620d92aeec7925e6b0c007a1e14b5f3fc764db10edc615e9e823b7` |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-plan-review-mimo.md` | `f3d59d0ac7e6f5528fd90f3ab6104f504b08242093d2f658bd505371a620c1fa` |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-plan-review-ds.md` | `c606f94e9353862ec30600360dfce2b21662cfbb13137d5c0b4422d0ed02fa3b` |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-plan-review-controller-adjudication.md` | `c83e76d7c2d95a1df3d4f969d39c4ca907183947a977b2150672e9e6f19ee450` |

## 4. Accepted finding fix ledger

| ID | 状态 | 固定后的code-generation-ready contract |
| --- | --- | --- |
| `S3-PR-CF01` | `FIXED_IN_PLAN` | 模块级命名常量`_DOCLING_DOCUMENT_ROOT_REF: Final[str] = "#"`；遍历`TableItem.captions`时先比较typed `caption_ref.cref`，命中root ref即静默跳过且不调用resolve。其余ref只调用一次`resolve(document)`；仅该调用周围捕获`AttributeError`/`IndexError`，无warning/log。禁止捕获全部`RuntimeError`、匹配异常文本、raw parser、fallback或第二resolver。model-invalid loader case固定项目`.venv`真实失败值`not-a-valid-cref`；新增root-ref public case。 |
| `S3-PR-CF02` | `FIXED_IN_PLAN` | Python public typed field明确为`RefItem.cref`，serialized JSON alias明确为`$ref`。Production只使用typed API；只有model-invalid loader-boundary test编辑serialized `$ref`。 |
| `S3-PR-CF03` | `FIXED_IN_PLAN` | Page public传播fixture固定用`ProvenanceItem(page_no=1, bbox=BoundingBox(l=0.0, t=0.0, r=1.0, b=1.0), charspan=(0, 1))`，经过真实save/load后从`get_page_content()`断言；禁止private page/table state。 |
| `S3-PR-CF04` | `FIXED_IN_PLAN` | 单ASCII空格连接源于`captions: list[RefItem]`不提供ref间分隔或标点元数据；大小写敏感精确去重用于保留可能有业务区别的原文。禁止标点猜测、casefold、Unicode normalization framework或第二语义。 |
| `S3-PR-CF05` | `FIXED_IN_PLAN` | 每次coverage前精确运行`pytest --collect-only -q tests/host/test_dispatch_scheduler.py::test_wake_queue_promotion_uses_tracked_async_promotion_task`；必须exit 0、唯一输出完整node且summary为`1 test collected`，否则STOP。AR-F06仍为retained/unfixed/unwaived。 |

## 5. Rejected / no-action disposition

以下候选严格保持Controller状态，不进入implementation：

| Candidate | Controller状态 | 本fix动作 |
| --- | --- | --- |
| MiMo 001 import统一 | `REJECTED_WITH_REASON` | 不统一Docling imports；`TextItem`的runtime `isinstance` import有直接理由，其它names维持postponed annotation / loader local import。 |
| MiMo 003 warning方案 | `REJECTED_WITH_REASON` | 不增加warning/log；它不是caption业务事实或既有诊断contract。 |
| MiMo 005枚举文本子类 | `NO_ACTION` | 不枚举第三方subclasses；`isinstance(TextItem)`已覆盖子类。 |
| MiMo 009 helper docstring/matrix扩张 | `NO_ACTION` | 不复制normalizer语义；既有newline/tab/space matrix足够。 |
| DS F01任意invalid ref可load | `REJECTED_AS_ENVIRONMENT_DRIFT` | 不采用全局环境证据；项目`.venv`以`not-a-valid-cref`固定loader failure，root ref另由CF01处理。 |
| DS F02 NaN/`ValueError` | `REJECTED_AS_ENVIRONMENT_DRIFT` | 不捕获`ValueError`；`#/texts/NaN`在current model validation已失败，resolve不可达。 |
| DS F04 NBSP / `text_utils` | `REJECTED_AS_FALSE_EVIDENCE` | 不加NBSP limitation、特殊case、Unicode framework、`text_utils`抽取或production扩域；current `str.split()`已规范化相关空白。 |
| DS F05 context fallback | `NO_ACTION` | 不增加`infer_caption_from_context`或任何context/header fallback；计划已明确禁止。 |
| DS F06 typed gate | `CONFIRMED / NO_ACTION` | 保持`isinstance(TextItem)`，不新增设计。 |
| DS F08 same-document path | `CONFIRMED / NO_ACTION` | 保持`_build_tables()`传入同一个document，不新增document view。 |
| MiMo 007—013/015 | `CONFIRMED / NO_ACTION` | allowlist、locks、README、security/quota、residual与完整门禁保持原裁决。 |

被拒方案不会以“测试便利”或“防御性”名义重新进入后续实现。

## 6. Scope / README / unchanged boundaries

本轮逻辑diff精确为：

```text
M docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md
M docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-plan-correction-codex.md
A docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-plan-review-fix-codex.md
```

Production/tests/README/utility/control/Controller/reviewer artifacts均为zero-write protected。本gate不触发README更新；恢复implementation后仍需fresh读取相关README约束，精确裁决`NO_UPDATE`，若约束要求更新则STOP请求扩域，不能预先修改。

不变边界：

- Config与Host internal SQLite/EventLog=`ACCEPTED_TRUSTED_INTERNAL`；Tool Trace、audit、public、LLM-facing、logs、其它outputs、diff/reviews逐surface=`ZERO_REQUIRED`。
- Gemini=`EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING`；不追加真实provider调用，不改config/model/key/retry/quota/budget。
- `AR-F06=RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX`；`AR-F07=PENDING_RELEASE_BLOCKER`。
- Issues 142/151/175/177/178、Topic 8/9与deferred/no-code destinations不扩域；不引入secret infrastructure或统一tool authorization framework。

## 7. Review / fix / re-review gate

本artifact只完成accepted plan-finding fix，不进入re-review。下一入口固定为：

1. MiMo与DS分别对完整fixed plan、updated correction artifact与本artifact做双路complete plan re-review；只看fix hunks不算。
2. 两路确认`CF01`—`CF05`均关闭且没有新blocking finding。
3. Controller逐项裁决re-review并明确发布新的Slice 3 implementation authorization。
4. 获得授权后，implementation必须先修`S3-STOP-F01`，再继续其余九owner coverage；现有六路径test delta全部保留。

Implementation最终门禁仍为canonical suite 0 failed且AR-F06 node真实运行；每次coverage前collect-only fail-closed，coverage仅精确deselect该一个scheduler node，219/219 line coverage `>=80%`且九owner逐项列statements/covered/missing/percent；full pyright zero、Ruff immutable set无增量且mutable paths zero finding、wheel+sdist、diff/allowlist/staged、README裁决、六canonical scans、Slice 2 stale-owner scans、AAPL download/process、R03 public Host/current live browser cleanup owner、upload跨平台nodes、security matrices、configured-secret owner scan及必要smokes全部fresh通过。

## 8. Stop conditions

- root ref不能只由typed `cref`与命名常量在resolve前处理，或需要捕获`RuntimeError`、异常文本匹配、raw parser、fallback、第二resolver或warning/log。
- 需要第二个production path、修改schema/consumer、README扩域或private-state test。
- model-invalid值在项目`.venv`不再于load boundary失败，unknown/out-of-range不再分别由单次resolve抛`AttributeError`/`IndexError`，或current public provenance构造不成立。
- coverage前exact collect-only未唯一收集AR-F06完整node。
- 任一protected hash漂移、出现allowlist外path、staged非空。
- implementation再暴露真实production correctness/type/security defect，或只有其它production改动/private coupling/coverage降阈值才能达标。

触发任一条件时保存最小复现、预期/实际、stack与coverage missing-line证据并交Controller；不得顺手扩域。

## 9. Validation / final audit

本plan-only gate未运行implementation tests、coverage、pyright、Ruff、build、scans或smokes，也不补签任何implementation结果。

- final plan SHA-256：`e870921ec608247a666d03ca7845c1d8a6453409392201a95eb16933ec53ef56`。
- updated plan-correction artifact SHA-256：`f7500f03c9b8b703690c78e81cc75af3c15077b3e8e699757fec226345065c09`。
- tracked plan diff against immutable HEAD：`126 insertions / 23 deletions`。
- protected hash audit：`PASS`；§3六个test paths与九个control/Controller/reviewer paths逐项匹配entry SHA-256。
- production / README / utility audit：`PASS`；本gate未引入这些路径的新增diff。
- `git diff --check`：`PASS`，无whitespace error。
- staged diff：空。

## 10. Residual / verdict

- `S3-STOP-F01`仍是blocking production correctness defect；plan fix不等于production fix。
- AR-F05及其余九owner coverage仍未关闭。
- AR-F06/07状态与destination不变。
- 未获Controller重新授权前禁止implementation。

Final verdict：`READY_FOR_DUAL_COMPLETE_PLAN_REREVIEW`。
