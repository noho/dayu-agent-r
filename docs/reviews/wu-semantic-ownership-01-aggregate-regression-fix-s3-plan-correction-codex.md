# WU-SEMANTIC-OWNERSHIP-01 Aggregate Regression Fix Slice 3 Plan Correction（AgentCodex）

## 1. Gate identity / verdict

- 日期：`2026-07-19`。
- Umbrella：既有`WU-SEMANTIC-OWNERSHIP-01` aggregate regression fix Slice 3；不是新WU。
- Gate：Controller完成双路plan-review adjudication后的plan-only review-fix。
- 执行者：AgentCodex；未`/clear`，未启动子代理。
- Verdict：`READY_FOR_DUAL_COMPLETE_PLAN_REREVIEW`。
- Implementation：`NOT_AUTHORIZED / NOT_STARTED`。

本gate只按Controller接受的`CF01`—`CF05`修正code-generation-ready plan，不修改production/tests/README/utility，不继续coverage implementation，不运行implementation tests，不stage/commit，不进入re-review、code review、aggregate、push、PR或closeout。

## 2. Authority 与 entry locks

直接authority：

- Controller adjudication：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-production-defect-controller-adjudication.md`。
- 裁决：`S3-STOP-F01 = ACCEPTED / PRODUCTION_CORRECTNESS_DEFECT / PLAN_CORRECTION_REQUIRED`。
- adjudication entry SHA-256：`71a7a62fbee5272ea64815e85d673f1c13819e605d3a5f303d785d8728624d81`。
- prior AgentCodex stop artifact SHA-256：`addd3b10091bfbdb9294c26b570a1b1808e77c079d195c2d964eb384a27dd9f8`。
- MiMo plan review SHA-256：`f3d59d0ac7e6f5528fd90f3ab6104f504b08242093d2f658bd505371a620c1fa`。
- DS plan review SHA-256：`c606f94e9353862ec30600360dfce2b21662cfbb13137d5c0b4422d0ed02fa3b`。
- Controller plan-review adjudication SHA-256：`c83e76d7c2d95a1df3d4f969d39c4ca907183947a977b2150672e9e6f19ee450`；只接受`CF01`—`CF05`，其余提案为rejected/no-action。

Git locks：

- branch：`phaseflow/host-issues-control`。
- immutable slice base / HEAD：`9e7a4e9d4796b9c382d44494bb10efa64787b199`。
- parent：`ba44bf877138235d53606d082341a7f7280af488`。
- tree：`7dc759e3bde5f6a257c21b60434f8874d157771a`。
- entry plan SHA-256：`afaa18c5608e6eeae0046318865bd1b3dd2f9a176c4b0739aa5b099e0ae3a252`。
- 双路review entry plan SHA-256：`ef4a0832f1885e4013d673294b944a56280619baab1f97d438896af5c8cbedcf`。
- plan-review-fix entry本artifact SHA-256：`c5b788b03ab54638841a7bd58cb8d5978ef92de8ea120ff3a3408aedbaac2072`。
- fixed plan SHA-256：`e870921ec608247a666d03ca7845c1d8a6453409392201a95eb16933ec53ef56`。
- entry staged diff：空。

## 3. Protected state

### 3.1 Slice 3六个测试路径

本plan gate没有修改、格式化或运行以下路径。当前实际delta仍是三个tracked modified与一个untracked added，另外两个授权路径保持base内容：

| path | entry SHA-256 |
|---|---|
| `tests/documents/test_processors.py` | `75ca22edd531c27fc7ccf0ea1edc6f3ddf62e389a18af24f17bb6798713f2d1c` |
| `tests/fins/test_sec_pipeline_download.py` | `f82c1416deac4f95cbe3e3feb4547410d077d41139fa0d8ac1915ca6d44a0c21` |
| `tests/fins/test_processor_read_consistency.py` | `da55b5eb32a18eeef425a264fe9a172d888f9c2608dad9d9a0a098e4fe955459` |
| `tests/fins/test_fins_ingestion_tools.py` | `6ece9288834ab3953be8880276079a003f58a02629a2230459d728b95ff2f747` |
| `tests/host/test_effective_execution_config.py` | `e3a85caded7bda956e95d5ebd336cd60815ec1d227c134f46a9678d6a96c6acf` |
| `tests/runtime/test_argparse_exit.py` | `3aa607842a96b7425b964f3c030dc2b427e5bba0dd89abc65e20ed7306ce3f3d` |

### 3.2 Controller-owned / protected dirty artifacts

| path | entry SHA-256 |
|---|---|
| `docs/host/issues-implementation-control.md` | `00b40ad39ea86aaf95c01d2db89b2e4fdd3d8c38805b20328854897ff6bc6883` |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s2-accepted-commit-controller-validation.md` | `bf5842031abe4306fb50cfce918c6fd2ff90bb219584a42fc20f8d2bc8a208ed` |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-implementation-controller-authorization.md` | `7d8fb7e0723c98edd5a8aa20692fe61d084d2ff7552cf821d74410f4a80243dc` |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-production-defect-controller-adjudication.md` | `71a7a62fbee5272ea64815e85d673f1c13819e605d3a5f303d785d8728624d81` |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-implementation-codex.md` | `addd3b10091bfbdb9294c26b570a1b1808e77c079d195c2d964eb384a27dd9f8` |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-plan-correction-controller-validation.md` | `1f1d1f5ca8620d92aeec7925e6b0c007a1e14b5f3fc764db10edc615e9e823b7` |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-plan-review-mimo.md` | `f3d59d0ac7e6f5528fd90f3ab6104f504b08242093d2f658bd505371a620c1fa` |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-plan-review-ds.md` | `c606f94e9353862ec30600360dfce2b21662cfbb13137d5c0b4422d0ed02fa3b` |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-plan-review-controller-adjudication.md` | `c83e76d7c2d95a1df3d4f969d39c4ca907183947a977b2150672e9e6f19ee450` |

上述paths均为zero-write protected state；final hash audit见§11。

## 4. 第一性原理与直接类型证据

问题与严重性成立。caption是`TableSummary.caption`与`TableContent.caption`共同承诺的`str | None`业务语义，三个public consumer必须从同一owner投影；不能由测试、下游renderer、adapter或LLM prompt猜回。

当前直接证据：

- `docling-core==2.74.0`。
- `TableItem`继承`FloatingItem`，public字段是`captions: list[RefItem]`，默认空列表。
- `RefItem.resolve(doc)`是public document-reference resolution method。
- Python typed字段是`RefItem.cref`；serialized JSON alias才是`$ref`。当前项目`.venv`中`#`可通过模型校验但直接resolve会抛`RuntimeError`，因此它是必须在typed projection boundary识别的document-root sentinel，而不是可吞掉的resolver异常。
- `TextItem`是typed文本基类；`SectionHeaderItem`、`TitleItem`、`ListItem`、`CodeItem`与`FormulaItem`均为其子类，`TableItem`/`PictureItem`不是。
- 当前`_build_tables(document, linear_items)`已经持有同一`DoclingDocument`，却调用`_extract_table_caption(table_item)`并丢弃document真源。
- 当前resolver读取不存在的旧单数`getattr(table_item, "caption", None)`，直接返回`None`。
- public `TableSummary`、`TableContent`与page table summary已统一消费`_TableBlock.caption`，无需schema或consumer改造。

唯一语义owner因此是`dayu/documents/processors/docling_processor.py`的table projection boundary。

## 5. Corrected production scope / call path

Slice 3 correction-only production allowlist精确增加：

```text
M dayu/documents/processors/docling_processor.py
```

其余八个AR-F05 production owners和所有其它production paths仍为zero diff。该path已经属于aggregate parent到当前树的219 changed-production集合，因此修改内容不改变集合成员，final仍必须精确219。

唯一允许call path：

```text
_build_tables(document, linear_items)
  -> _extract_table_caption(table_item, document)
  -> table_item.captions (ordered RefItem list)
  -> RefItem.cref == _DOCLING_DOCUMENT_ROOT_REF: skip before resolve
  -> each remaining RefItem.resolve(document) exactly once
  -> TextItem.text
  -> _TableBlock.caption
  -> list_tables / read_table / get_page_content.tables
```

模块级固定`_DOCLING_DOCUMENT_ROOT_REF: Final[str] = "#"`。Production只读typed `RefItem.cref`；禁止读取serialized `$ref`。禁止旧单数caption `getattr`、`caption_text()` fallback、raw JSON/private path parser、重新加载document、第二resolver或任何下游补偿。

## 6. Caption public contract

Corrected plan固定以下实现语义：

1. 严格按`TableItem.captions`顺序解析。
2. 每个ref先用typed `cref`与命名root常量精确比较；`#`静默跳过且不调用resolve，其余ref只调用一次public `resolve(document)`，document必须是`_build_tables()`的同一实例。
3. 仅接受`isinstance(resolved, TextItem)`；非文本item忽略。
4. 每个typed `text`用现有`_normalize_whitespace()`规范为单空格文本；空白结果忽略。
5. 按规范化后的完整文本、大小写敏感精确去重，保留第一次出现；大小写可能承载业务差异，owner不得用casefold擅自折叠。
6. 用单个ASCII空格连接剩余caption，因为`captions`只有有序refs、没有ref间分隔或标点元数据；不得猜标点，也不得增加Unicode normalization framework。无剩余值返回`None`。
7. `_TableBlock.caption`仍是唯一缓存投影，三个public consumer不重算。

Fail-safe / failure边界：

- `captions=[]`、全空白、全部非文本：`None`。
- schema-valid document-root ref `#`：在typed `cref`边界跳过，不调用resolve，不产生warning/log。
- public `resolve()`因未知collection抛出的`AttributeError`或因越界抛出的`IndexError`：只在单次resolve调用周围捕获并跳过该ref；其它有效refs继续。
- 符合JSON-pointer shape但dangling的ref属于可选caption metadata fail-safe。
- 语法非法、不能构成Docling `RefItem`的payload固定用项目`.venv`真实失败值`not-a-valid-cref`在`DoclingDocument.load_from_json()`边界失败，不得被caption resolver吞成`None`。
- `TypeError`、`ValueError`、`RuntimeError`及其它未分类异常继续暴露。禁止捕获全部`RuntimeError`、`except Exception`、异常文本匹配、warning/log后忽略、默认空字符串或context/header fallback。

该规则最小化变化：没有新schema、新类型、新resolver service、新状态机或兼容层。

## 7. Public test oracle

Caption tests必须使用真实Docling public models、`save_as_json()`、`DoclingProcessor`真实load，并从public `list_tables()`、`read_table()`及带provenance fixture的`get_page_content()`断言：

- 单caption与三个public views传播一致；page fixture用public `ProvenanceItem(page_no=1, bbox=BoundingBox(l=0.0, t=0.0, r=1.0, b=1.0), charspan=(0, 1))`，经真实serialize/load，不写private state。
- 多caption的ref顺序、空白规范化、精确去重、单空格连接；反向refs证明不依赖document collection顺序；大小写不同值分别保留。
- empty list与blank TextItem返回`None`。
- `#/missing/0`与`#/texts/999`分别验证unknown collection / out-of-range fail-safe；坏ref与有效ref并存时保留有效caption。
- typed `RefItem(cref="#")`经真实serialize/load验证root ref被跳过；与有效caption并存时保留有效值，只有root refs时为`None`。
- 非文本ref被忽略；与有效TextItem并存时保留有效值。
- model-invalid ref以真实serialized payload为基础，只在loader-boundary test把JSON alias`$ref`替换为`not-a-valid-cref`，从public processor构造入口验证load failure；其它Python构造和production判断一律使用typed `cref`。

禁止只测private helper、monkeypatch `RefItem.resolve`、修改private `_tables`、mock-only hook或在测试中复制normalization/dedup算法。当前六路径test delta全部保留；恢复implementation后先让现有S3-STOP-F01 node和caption matrix通过，再继续其余九owner coverage cases。

## 8. README / security / quota / deferred

README精确裁决为`NO_UPDATE`：

- 根`README.md`：无安装、CLI、工作区、输出或排障流程变化。
- `dayu/README.md`：无跨包关系、分层或`dayu.documents`职责变化。
- `tests/README.md`：无测试层级、运行方式或维护规则变化；现有documents processor描述已覆盖Docling表格输出。

恢复implementation后必须fresh重读三份README约束；若实现事实要求更新，STOP请Controller扩README allowlist，不得预先扩域。

其它裁决保持：

- Config与Host internal SQLite/EventLog=`ACCEPTED_TRUSTED_INTERNAL`。
- Tool Trace、audit、public、LLM-facing、logs、其它outputs、diff/reviews逐surface=`ZERO_REQUIRED`。
- Gemini=`EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING`；不追加真实provider调用，不改config/model/key/retry/quota/budget。
- `AR-F06=RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX`。
- `AR-F07=PENDING_RELEASE_BLOCKER`。
- Issues 142/151/175/177/178、Topic 8/9、secret infrastructure、统一tool authorization framework和deferred/no-code destinations均不扩域。

## 9. Review / fix / re-review gate

前置plan review与Controller adjudication已完成，`CF01`—`CF05`已在两份plan artifacts内修复。Next gate固定为：

1. AgentMiMo与AgentDS分别对完整fixed plan、本artifact及plan-review-fix artifact做双路完整re-review；只看fix hunk不算。
2. 两路均确认accepted findings关闭且无新blocking finding。
3. Controller逐项接受re-review并发布新的Slice 3 implementation authorization。

在第5步前禁止production/tests/README/utility修改与implementation。Implementation完成后仍必须经过Slice 3双路完整code review、Controller裁决、fix、双路完整re-review与Controller acceptance。

## 10. Acceptance / stop criteria

Plan-level acceptance：

- correction-only production allowlist只有Docling owner。
- owner call path、multi-caption语义、fail-safe/failure边界与public tests无需implementation时重新设计。
- root sentinel、`cref`/`$ref`边界、public provenance fixture与coverage collect-only fail-closed规则均可直接生成代码/测试/门禁。
- 当前tests与Controller artifacts hashes保持。
- README、security、Gemini、AR-F06/07与deferred/no-code边界不漂移。
- corrected plan通过双路完整review/fix/re-review并获Controller授权。

Implementation-level acceptance仍要求：

- caption public matrix全部通过，旧单数caption/fallback/第二resolver为零。
- canonical suite 0 failed且AR-F06 node真实运行。
- 每次coverage前exact `pytest --collect-only`必须唯一收集AR-F06完整node；coverage只精确deselect accepted scheduler node，final 219/219 line coverage >=80%，九owners逐项列ledger。
- full pyright zero、Ruff immutable set无增量且mutable paths zero finding。
- wheel+sdist、diff/allowlist/staged、README verdict、six scans、Slice 2 stale-owner scans、AAPL download/process、R03/public Host/live browser cleanup、upload跨平台nodes、security matrices、configured-secret owner scan与必要smokes全部满足原§6。

立即stop条件包括：需要第二production path、README扩域、raw/private resolver、broad catch、root ref必须调用resolve或捕获`RuntimeError`、schema/consumer协商、AR-F06 collect-only不唯一、protected hash漂移、staged非空、新production correctness/type/security defect、219集合变化或任一原§9 condition。

## 11. Validation / exact plan diff

本gate没有运行implementation tests、coverage、pyright、Ruff、build、scan或smoke；这些结果不能在plan-only gate被补签。

本轮plan-review-fix只修改本plan与本artifact，并新增固定plan-review-fix artifact；精确final diff与hash audit记录在该fix artifact。获准tracked修改为：

```text
M docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md
M docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-plan-correction-codex.md
```

唯一获准新增artifact为`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-plan-review-fix-codex.md`。本gate不运行implementation验证。

## 12. Residual risk / next entry

- `S3-STOP-F01`仍是blocking production correctness defect；本plan gate未修代码，不能标fixed。
- Multi-caption连接与bad-ref分类已经成为待双路review挑战的明确public contract，不再留给implementation临场决定。
- AR-F05仍未关闭；其余九owner coverage与完整§6 gates必须在caption修复后fresh执行。
- AR-F06/07保持原owner/destination。

Next entry：`DUAL_COMPLETE_PLAN_REREVIEW`。

Final verdict：`READY_FOR_DUAL_COMPLETE_PLAN_REREVIEW`。
