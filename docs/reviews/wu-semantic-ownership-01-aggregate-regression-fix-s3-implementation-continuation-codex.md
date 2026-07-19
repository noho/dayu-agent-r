# WU-SEMANTIC-OWNERSHIP-01 Aggregate Regression Fix Slice 3 Resumed Implementation Continuation（AgentCodex）

## 1. Verdict

`STOPPED_SECOND_PRODUCTION_CORRECTNESS_DEFECT`。

恢复实现后，授权内的 `S3-STOP-F01` 已在唯一 production allowlist
`dayu/documents/processors/docling_processor.py` 内按 final accepted plan 精确修复；原失败节点和完整 8-node public caption matrix 均已通过。

随后开始其余九 owner 的 public-contract coverage 时，真实公开入口稳定复现第二个 production correctness defect：合法、最小的 10-K HTML 含一张真实表格，`TenKFormProcessor.supports(...)` 返回 `True`，但公开构造器在 `sec_form_section_common.py` 的虚拟章节/table ownership 刷新中抛出：

```text
ValueError: 存在无法分配到最终虚拟章节的 table_ref: ['t_0001']
```

该缺陷需要修改第二个 production path 或重新裁决跨 owner contract，命中 corrected plan §4.3 stop condition 与 resumed authorization 第 3 项。实现已立即停止；没有修改 `dayu/fins/processors/sec_form_section_common.py`、`dayu/fins/processors/sec_processor.py` 或其它非授权 production 路径，没有继续 canonical、final aggregate coverage、build、smokes、scans 或 security matrices，也不声称 `AR-F05`/`219/219` 已关闭。

## 2. Entry locks

- WU：既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` aggregate regression fix Slice 3 resumed implementation；不是新 WU。
- Base / HEAD：`48c6cc5ef74f273b1b592682ae9ab3e14cb48cbe`，branch `phaseflow/host-issues-control`。
- final accepted plan：`docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md`，SHA-256 `e870921ec608247a666d03ca7845c1d8a6453409392201a95eb16933ec53ef56`。
- umbrella control：`docs/phaseflow-umbrella-optimization-control.md`，SHA-256 `6d924e919a4ba797e6213879aadca7bdd4f47a37418630e1ee43cb1995e461db`。
- 五个 subsystem design 真源已完整读取并锁定：
  - `docs/engine/design.md`：`f209126046ffdb8a55f41a538c929842817f328f8c3bbc8f080b8c1c5489bf31`
  - `docs/host/design.md`：`2be90cc2e107ce14fd5ee594c85e2a223217b9d6689b2d4a0cafba2adf3ec628`
  - `docs/fins/design.md`：`97033cf1330e6018df2cf7bf676fa550c24e3e99beb99792f718eac31727abdd`
  - `docs/tool/design.md`：`ddc6efc03c15ad5ba50332593f2282b1035dbc88d243071597814c7b4dceea7c`
  - `docs/ui/design.md`：`ed25d5d4577864cbf7ca6860aad043607921bd7db4f72cffb876c871fb99b4b7`
- 总设计 `docs/design.md` 亦完整读取，SHA-256 `0e48f8f19d32ba909e02d8e9880b2bd52287b0167e01029c7a4555ad32f171a7`。
- 已完整读取 `AGENTS.md`、`docs/host/issues-implementation-control.md`、S3 初次 authorization、旧 stop artifact、production defect adjudication、plan correction、双路 plan review、controller adjudication、plan-review fix、validation、双路完整 re-review、corrected-plan accepted-commit validation 与 resumed implementation authorization 的完整链。
- 未启动 subagent；未 stage、commit、push、code review 或 aggregate regression。

### 2.1 Controller-owned dirty hash protection

下列三个 Controller-owned dirty path 在入口与停止收尾时 hash 完全相同，未修改：

| path | entry/final SHA-256 |
|---|---|
| `docs/host/issues-implementation-control.md` | `f7afd84a8a37fb018ae62a102348a8eb020abd9f630538ae89c6c71a54fbddc9` |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-corrected-plan-accepted-commit-controller-validation.md` | `4d0b7b64544584be9dca8a57301cf3d27343130fad5664c9635681e45c88eba5` |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-resumed-implementation-controller-authorization.md` | `a21eaabc88885a5134f000a94e965e495fbcd9f79a9b080abb857ea31967eb3c` |

## 3. 动机、语义 owner 与 S3-STOP-F01 root cause

Slice 3 动机成立：accepted aggregate ledger 的 219 个现存 changed production Python 中只有九个 owner 未达到 line coverage 80%，并且真实 caption case 已证明 Docling 表格标题投影错误。标题业务事实的唯一 owner 是 `dayu/documents/processors/docling_processor.py` 的 table projection boundary，不应由下游 list/read/page consumer、fixture 或展示层重算。

直接同源证据是：当前 `docling-core==2.74.0` 的合法 public contract 是 `TableItem.captions: list[RefItem]`，每个 `RefItem` 用 `resolve(document)` 在同一 `DoclingDocument` 中解析；旧实现却读取不存在的单数 `caption` 属性，因而合法 caption 稳定丢失。

修复只落在该 owner boundary：

1. `_build_tables()` 把同一 `DoclingDocument` 传给 `_extract_table_caption(table_item, document)`。
2. 模块级定义 `_DOCLING_DOCUMENT_ROOT_REF: Final[str] = "#"`；root 在 resolve 前跳过。
3. 只遍历 `TableItem.captions`，只读取 typed `RefItem.cref`；其它 ref 各执行一次 `resolve(document)`。
4. 只在单次 resolve 周围捕获 `AttributeError` / `IndexError`；无 `RuntimeError` catch、warning/log、异常文本匹配、raw parser、fallback 或第二 resolver。
5. `isinstance(resolved, TextItem)` 后读取 typed `text`；用既有 whitespace normalizer，按规范化后的完整字符串大小写敏感精确去重、首次保留，并以单个 ASCII 空格连接；无剩余文本返回 `None`。
6. `_TableBlock.caption` 仍是 list/read/page 三个公开消费者的唯一真源。

Production diff 中新增行扫描只命中唯一合法 `resolved = caption_ref.resolve(document)`；没有新增旧 caption `getattr`、`caption_text`、`RuntimeError`、warning/logger、serialized `$ref` 或 raw JSON resolver。

## 4. S3-STOP-F01 public caption matrix

全部 case 都构造真实 `DoclingDocument`、`TableItem.captions`、`TextItem`，经 `save_as_json()` 和 `DoclingProcessor` 真实 load，再断言 public outputs；没有直接调用 private resolver、修改 `_tables`、monkeypatch `RefItem.resolve` 或复制 production normalizer/deduper。

落成并通过的节点：

```text
test_docling_json_processor_projects_referenced_table_caption
test_docling_json_processor_preserves_normalized_unique_caption_order
test_docling_json_processor_returns_none_for_empty_or_blank_captions
test_docling_json_processor_skips_dangling_caption_references
test_docling_json_processor_skips_document_root_caption_reference
test_docling_json_processor_rejects_model_invalid_caption_reference
test_docling_json_processor_skips_non_text_caption_references
test_docling_json_processor_propagates_caption_to_public_table_views
```

覆盖的 public contract 包括：单 caption；正向/反向 refs 顺序；换行、制表与连续空白规范化；规范化后 exact duplicate；大小写不同文本分别保留；空列表与全空白；root `#`；未知 collection；越界 index；真实非文本 `TableItem`；serialized `$ref` 仅在 loader-boundary test 被替换为 `not-a-valid-cref`；`ProvenanceItem(page_no=1, bbox=BoundingBox(...), charspan=(0, 1))` 的页级传播；`list_tables`、`read_table`、`get_page_content` 三视图一致。

Fresh evidence：

```text
pytest tests/documents/test_processors.py::test_docling_json_processor_projects_referenced_table_caption -q
1 passed in 0.42s

pytest tests/documents/test_processors.py -k 'docling and caption' -q
8 passed, 15 deselected in 0.49s
```

在第二缺陷出现前，六个 authorized test files 的 focused suite 为 `204 passed, 3 warnings in 3.43s`。

## 5. 第二 production correctness defect

### 5.1 Public minimal reproduction

新增的最小复现节点只使用 public `TenKFormProcessor`、`LocalFileSource` 与合法 HTML；输入包含规范的 Part/Item 序列和一张 2x2 表格。它先断言：

```text
TenKFormProcessor.supports(source, form_type="10-K", media_type="text/html") is True
```

然后从公开构造入口期望得到可枚举的 sections/tables，并要求 table 的 `section_ref` 与 `read_section(...)["tables"]` 双向一致。实际在构造期间失败，公开结果不可达。

命令与结果：

```text
pytest tests/fins/test_processor_read_consistency.py::test_ten_k_public_processor_assigns_tables_without_marker_capability -q
1 failed, 3 warnings in 0.83s
```

关键 stack：

```text
TenKFormProcessor.__init__
  -> _BaseSecReportFormProcessor.__init__
  -> _initialize_virtual_sections(min_sections=3)
  -> _refresh_virtual_section_state()
  -> ValueError: 存在无法分配到最终虚拟章节的 table_ref: ['t_0001']
```

### 5.2 同源 root cause evidence

这不是从日志、偶然顺序或 coverage 间接推断的根因，而是同一 call path 的直接逻辑/数据矛盾：

1. `TenKFormProcessor` 是已注册的 10-K edgartools fallback public processor，合法输入的 `supports(...)` 返回 `True`。
2. 其底层 `SecProcessor.get_full_text_with_table_markers()` 的 public protocol 实现明确返回 `""`，模块 docstring 同时声明“SecProcessor 不支持 marker”。
3. `sec_form_section_common._assign_tables_to_virtual_sections()` 把空 marker 文本定义为安全降级，在 `if not marked_text: return` 处不建立任何 table mapping。
4. 紧接着同一次 `_refresh_virtual_section_state()` 从 public `list_tables()` 取得 `base_table_refs={'t_0001'}`，而 `section_table_refs` 仍为空。
5. owner 随后要求两集合严格相等，并在 `base_table_refs != section_table_refs` 时抛出上述 `ValueError`。

因此当前 contract 同时承诺“不支持 marker 时安全降级”和“全部 base table 必须已分配”，两者对任何形成虚拟章节且包含真实表格的 SecProcessor-backed report form 都不可同时成立。正确 owner/fix boundary 可能涉及虚拟章节 table assignment owner，也可能涉及 SecProcessor marker 能力；当前授权既未开放第二 production path，也未裁决这两个 owner 之间的契约，因此不得局部 fallback 或猜测修复。

### 5.3 Real AAPL corroboration

在最小化前，现有真实 AAPL fixture
`tests/fins/fixtures/aapl_xbrl/fil_0000320193-24-000123/aapl-20240928.htm`
经同一 public `TenKFormProcessor` 路径复现相同异常。只用 public `SecProcessor` 检查同源输入时：

```text
list_tables() count = 55
get_full_text_with_table_markers() marker count = 0
missing table refs count = 55
```

这排除了“合成 fixture 构造了不可能状态”的解释；最终保留的回归节点仍使用更小、确定性的合法 HTML。

## 6. Coverage evidence

### 6.1 AR-F06 collect-only gate

每次本轮 coverage 前均 fresh 执行：

```text
pytest --collect-only -q tests/host/test_dispatch_scheduler.py::test_wake_queue_promotion_uses_tracked_async_promotion_task
tests/host/test_dispatch_scheduler.py::test_wake_queue_promotion_uses_tracked_async_promotion_task
1 test collected in 0.27s
```

该证据只证明 node 唯一可收集；由于 STOP 后没有运行 canonical non-coverage suite，不声称 AR-F06 在本 continuation 中真实执行通过。

### 6.2 Pre-stop focused feedback coverage

- JSON：`workspace/tmp/wu-semantic-ownership-01-ar-fix-s3-focused-coverage.json`
- SHA-256：`25d715913d445582a70ee82eb85508c13123751ea6334e39416b9d2f9b2908c7`
- Test result：`204 passed, 3 warnings`。

该 run 只覆盖六个 authorized test files，是快速反馈，不是 final aggregate 签署。九 owner line ledger：

| owner | statements | covered | missing | line percent |
|---|---:|---:|---:|---:|
| `dayu/documents/processors/docling_processor.py` | 649 | 462 | 187 | 71.19% |
| `dayu/fins/pipelines/sec_6k_rules.py` | 447 | 302 | 145 | 67.56% |
| `dayu/fins/processors/sec_form_section_common.py` | 1098 | 402 | 696 | 36.61% |
| `dayu/fins/processors/sec_report_form_common.py` | 416 | 92 | 324 | 22.12% |
| `dayu/fins/processors/sec_section_build.py` | 303 | 56 | 247 | 18.48% |
| `dayu/fins/processors/sec_table_extraction.py` | 863 | 108 | 755 | 12.51% |
| `dayu/fins/tools/preprocess_tools.py` | 62 | 57 | 5 | 91.94% |
| `dayu/host/_execution_config_projection.py` | 157 | 146 | 11 | 92.99% |
| `dayu/runtime/argparse_exit.py` | 7 | 7 | 0 | 100.00% |

### 6.3 Stop reproduction coverage

- JSON：`workspace/tmp/wu-semantic-ownership-01-ar-fix-s3-continuation-stop-coverage.json`
- JSON SHA-256：`438b93c19f85e70576fff4c89b650f04908b2b0f57763d8db37d168fe2005645`
- data file：`workspace/tmp/wu-semantic-ownership-01-ar-fix-s3-continuation-stop.coverage`
- data SHA-256：`c804144b20f5f4767fc4199f624ad7f29a65b327df37ae33e4680a4033ebac34`
- Test result：`1 failed, 3 warnings`，无 skip/xfail/retry/deselect。

Stop node 对直接 owner 的 line coverage 是 `331/1098 = 30.145719%`。更重要的执行线证据：

- `sec_processor.py:574` 的 public marker `return ""` 已执行；
- `sec_form_section_common.py:813` 的 protocol call 已执行；
- `sec_form_section_common.py:881-882` 的空 marker 降级返回已执行；
- `sec_form_section_common.py:468`、`471-477` 的刷新/底层 table 收集已执行；
- `sec_form_section_common.py:495-497` 的集合不等与 exact `ValueError` 已执行；
- marker 分配主体 `884-922` 未执行，与空 marker 数据事实一致。

Final exact-exclusion aggregate coverage 因 STOP 未运行；不生成、不声称 final `219/219 >=80%` ledger，`AR-F05` 保持 open。

## 7. Exact diff / allowlist

相对 base `48c6cc5ef74f273b1b592682ae9ab3e14cb48cbe`，停止时 implementation code/test delta 为：

| status | path | + | - | final SHA-256 / state |
|---|---|---:|---:|---|
| M | `dayu/documents/processors/docling_processor.py` | 27 | 9 | `e2ab00fd984a4c27c30254d62ce038fafb91b9bc88d03eb786ad29f27acfd649` |
| M | `tests/documents/test_processors.py` | 519 | 0 | `6aba755cdb920f2f427f8f0375886ce14eb7b32f521f2d5ecde3c20d58be8f0b` |
| — | `tests/fins/test_sec_pipeline_download.py` | 0 | 0 | 保持 HEAD；`f82c1416deac4f95cbe3e3feb4547410d077d41139fa0d8ac1915ca6d44a0c21` |
| M | `tests/fins/test_processor_read_consistency.py` | 63 | 0 | `e3aec818f1a397b46c004de1e6dc2b58bd1eb334d8c9cc142f97baecdea09489` |
| M | `tests/fins/test_fins_ingestion_tools.py` | 89 | 0 | 保持入口 delta；`6ece9288834ab3953be8880276079a003f58a02629a2230459d728b95ff2f747` |
| M | `tests/host/test_effective_execution_config.py` | 146 | 0 | 保持入口 delta；`e3a85caded7bda956e95d5ebd336cd60815ec1d227c134f46a9678d6a96c6acf` |
| A | `tests/runtime/test_argparse_exit.py` | 45 | 0 | 保持入口 delta；`3aa607842a96b7425b964f3c030dc2b427e5bba0dd89abc65e20ed7306ce3f3d` |

`tests/documents/test_processors.py` 的 base-relative 519 行新增由入口已接受 91 行与本 continuation 增量 428 行组成；原 caption repro 未删除。`tests/fins/test_processor_read_consistency.py` 的 63 行是第二缺陷的最小 public reproduction。两个 authorized-but-initially-zero-diff paths 中，`test_sec_pipeline_download.py` 仍为 zero diff，另一个只增加 stop repro。

唯一 production diff 的 exact semantic hunks为：

```text
+ import Final
+ runtime import TextItem
+ _DOCLING_DOCUMENT_ROOT_REF: Final[str] = "#"
- _extract_table_caption(table_item)
+ _extract_table_caption(table_item, document)
- old singular caption/getattr projection
+ TableItem.captions -> root pre-skip -> single resolve(document)
+ TextItem narrowing -> whitespace normalize -> ordered exact dedup -> single-space join
```

- 其它八个 AR-F05 production owners：零 diff。
- 其它 production、utility、README、design、control：零 AgentCodex diff。
- 本 artifact 是用户明确要求的新 review artifact；没有覆盖旧 stop artifact。
- `git diff --check`：PASS，无输出。
- staged diff / staged name-status：空。

## 8. Tests、typing 与 Ruff

Fresh completed evidence：

| gate | result |
|---|---|
| 原 S3-STOP-F01 exact node | `1 passed` |
| complete caption matrix | `8 passed, 15 deselected` |
| six authorized files before second repro | `204 passed, 3 warnings` |
| second defect exact node | `1 failed, 3 warnings`，预期 STOP evidence |
| changed production + six authorized test paths Pyright | `0 errors, 0 warnings, 0 informations` |
| changed production + six authorized test paths Ruff | `All checks passed!` |
| diff whitespace | PASS |

Full-repository Pyright、immutable Ruff 144-set delta、canonical non-coverage suite 与 final aggregate coverage 未运行；在 production correctness STOP 后继续执行并不能关闭当前 blocker，因此不得用局部静态 PASS 代替 final gates。

## 9. Build、smoke、scans 与 security

下列 final gates 均为 `NOT_RUN_DUE_STOP`：

- wheel + sdist build；
- six canonical scans 与 Slice 2 direct-stream/awaiting stale-owner scans；
- AAPL real download/process；
- R03 public Host smoke；
- current live browser cleanup；
- upload POSIX/Windows cross-platform nodes与 init smoke；
- HKEX deterministic evidence；
- security matrices、configured-secret owner scan 与其它必要 smoke；
- canonical suite 中 AR-F06 scheduler node 的真实非 coverage 执行。

Security/deferred/no-code 裁决没有改变：

- Config 与 Host internal SQLite/EventLog：`ACCEPTED_TRUSTED_INTERNAL`；
- Tool Trace、audit、public、LLM-facing、logs、outputs、diff/review：`ZERO_REQUIRED`；
- Gemini quota：`EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING`，本 continuation 没有追加真实 provider 调用，也没有修改 config/model/key/retry/quota/budget；
- `AR-F06=RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX`；
- `AR-F07=PENDING_RELEASE_BLOCKER`；
- Issues 142/151/175/177/178、Topic 8/9 与统一 tool authorization 仍 deferred/no-code。

本轮没有引入 secret、token、provider credential、新日志面或新 LLM-facing 文本；但由于 final matrices/scans 未运行，不作 final security PASS 声明。

## 10. README verdict

`NO_UPDATE`。

已 fresh 完整读取 `tests/README.md`。其更新边界只在新增测试层级、测试运行方式或测试维护规则变化时触发；本 continuation 只在现有 Documents/Fins test files 增加 owner/public-contract cases，没有新增层级、命令约定或维护规则。Docling production 修复保持既有 `TableSummary.caption` / `TableContent.caption` schema、CLI/Service/Host/Engine 分层和用户工作流不变；根 README、`dayu/README.md`、各 layer README 与 `tests/README.md` 均不应机械更新。

## 11. Residual risk / Controller handoff

1. `S3-STOP-F01` 的代码与完整 public matrix 已在 worktree 中关闭，但尚未经过后续 code review/commit；本 artifact 不越过 gate。
2. 第二 production defect 未修复，最小 failing node保留在 authorized test path。正确 semantic owner 尚需 Controller 明确裁决：是由虚拟章节 table assignment owner在 marker capability 缺失时从同源 public section/table contract建立映射，还是扩展 SecProcessor 的 marker capability；禁止在 consumer、test fixture或 `list_tables()` 展示层补默认 section。
3. 任何修复都会超出当前唯一 production allowlist；不得在本 authorization 下继续。
4. 其余 SEC owner cases、canonical、219-path ledger、build、scans、smokes/security仍待新的 owner/allowlist裁决后重跑。
5. 所有 Controller-owned dirty hashes保持不变，staged area为空；没有 stage、commit、push、code review 或 aggregate。

最终 verdict 保持：`STOPPED_SECOND_PRODUCTION_CORRECTNESS_DEFECT`。
