# WU-SEMANTIC-OWNERSHIP-01 Slice 3 第二个 Production Defect Implementation（Codex）

## 1. Gate identity 与结论

- 日期：`2026-07-19`。
- Umbrella：`WU-SEMANTIC-OWNERSHIP-01` continuation；不是新 WU、不是新 slice。
- Accepted plan base / current HEAD：`9ad5711e20dd35d5a0cdc0cf79067333ff3b3daf`。
- Accepted plan SHA-256：`552df22871f3eb07465b971ca3fdf182032f3b2087e27442b0d78a1b7d8acc04`。
- 本轮没有启动 subagent，没有 stage、commit、push、PR 或 code review。
- Implementation verdict：`S3-STOP-F02_IMPLEMENTED / LOCAL_CODE_AND_REGRESSION_GATES_PASS / REQUIRED_R03_REAL_SMOKE_PROVIDER_NONCOMPLIANCE_RECORDED / CONTROLLER_VALIDATION_REQUIRED`。

第一性原理判断：缺陷动机成立。`DocumentProcessor` marker contract 允许不支持 marker 的底层 processor 返回空文本；旧 refresh 又要求 base table 与 virtual table 全等，使合法 `SecProcessor` 10-K 在 public 构造期间失败。这个矛盾发生在 virtual/base publication decision owner 内，不应由 `SecProcessor`、form-common guard、下游 consumer 或位置猜测补偿。唯一正确修复边界是 `dayu/fins/processors/sec_form_section_common.py`。

## 2. 精确实现

相对 implementation entry 唯一新增 production path：

```text
dayu/fins/processors/sec_form_section_common.py
```

该路径相对 accepted base 的精确 diff 为 `453 insertions / 287 deletions`，final SHA-256 为：

```text
9f66893b6c3c2af2427f02967c16ba1557fb1c5070c58978c9c8de70902c45a2
```

实现内容：

1. 新增 owner-private typed `_VirtualSectionPublicationMode`：`BUILDING`、`VIRTUAL_PUBLISHED`、`BASE_FALLBACK_PUBLISHED`。
2. refresh 先在局部 candidate 中完成 base table identity、raw marker、virtual tree、candidate 双向映射验证，再一次性发布；失败前不修改公开状态。
3. raw marker 保留重复项并按 contradiction-first 顺序验证：base 空/重复 ref、marker dangling/duplicate、章节树和双向映射矛盾均 fail closed。
4. 只有无矛盾但 marker 缺失、范围/标题不能唯一证明归属或映射不完整时，才原子发布 whole-base fallback；不发布半套 virtual state。
5. complete mapping 与合法 zero-table 文档发布完整 virtual state；`_remap_tables_to_deepest_virtual_sections()` 直接消费同一 owner-local `candidate_mapping`，并受最终双向校验。
6. 删除 silent availability filter、unmapped position assignment、首个/最近章节补偿；没有 `fallback_ref`、`last_known_ref`、标题相似度或顺序猜测。
7. base fallback 是 terminal no-op；virtual refresh 校验 identity 并重建同一业务映射。10-K/10-Q 首次与二次 postprocess/refresh 幂等。
8. `list_tables`、`list_sections`、`get_section_title`、`read_section`、`search` 五个 public consumers 只读取同一 typed publication mode；base fallback 完整透传底层 owner contract。

未修改并由 diff/scans 证明：`DocumentProcessor`、`SecProcessor`、10-K/10-Q 与 BS 同族 processor、两个 form-common zero guards、公共 schema。没有新增兼容 shim、deferred 能力、secret infrastructure 或统一 authorization。

## 3. 测试增量与受保护语义

只在六个授权测试路径中增加 owner/public contract cases；其中本轮实际增加 case 的路径是：

- `tests/documents/test_processors.py`：真实 Docling page/section/table/full-text/cache/support、空文档/headerless/empty-table 与 malformed support 边界；受保护 8-node caption matrix未改写。
- `tests/fins/test_sec_pipeline_download.py`：6-K business signal classification 参数矩阵与 candidate type/filename/rank/positive selection owner contract。
- `tests/fins/test_processor_read_consistency.py`：S3-STOP-F02 public/base oracle、complete/incomplete/contradiction/zero-table/second-postprocess matrix，以及 report/section/table public owner coverage。

其余三个授权路径内容保持 entry hash不变：

```text
6ece9288834ab3953be8880276079a003f58a02629a2230459d728b95ff2f747  tests/fins/test_fins_ingestion_tools.py
e3a85caded7bda956e95d5ebd336cd60815ec1d227c134f46a9678d6a96c6acf  tests/host/test_effective_execution_config.py
3aa607842a96b7425b964f3c030dc2b427e5bba0dd89abc65e20ed7306ce3f3d  tests/runtime/test_argparse_exit.py
```

受保护 Docling production delta保持 entry SHA 精确不变：

```text
e2ab00fd984a4c27c30254d62ce038fafb91b9bc88d03eb786ad29f27acfd649  dayu/documents/processors/docling_processor.py
```

## 4. Focused 与 canonical regression

| Gate | Fresh result |
| --- | --- |
| S3-STOP-F02 minimal public 10-K node | `1 passed` |
| accepted virtual fallback/mapping/refresh/postprocess selection | `9 passed, 42 deselected` |
| 六个授权测试文件 | `252 passed, 3 warnings` |
| protected Docling caption matrix | `8 passed, 18 deselected` |
| canonical non-coverage | `5260 passed, 10 skipped, 5 deselected, 3 warnings` |
| AR-F06 exact collect preflight | 唯一完整 node id，`1 test collected` |
| AR-F06 non-coverage exact node | `1 passed` |

canonical 没有排除、skip 或 retry AR-F06。状态继续为：

```text
AR-F06 = RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX
```

## 5. Fresh aggregate coverage

运行前执行 AR-F06 exact unique-collection preflight；coverage 只 deselect 该单一已裁决 node，没有其它 omit/deselect/skip/retry/config 改动。

```text
5259 passed, 10 skipped, 6 deselected, 3 warnings
changed production Python = 219
line coverage qualified = 219/219 >= 80.00%
minimum = dayu/fins/storage/_fs_identity.py 92/115 = 80.00%
```

九个 Slice 3重点 owner 的 final line ledger：

| Production owner | Statements | Covered | Missing | Line % |
| --- | ---: | ---: | ---: | ---: |
| `dayu/documents/processors/docling_processor.py` | 649 | 534 | 115 | 82.2804% |
| `dayu/fins/pipelines/sec_6k_rules.py` | 447 | 385 | 62 | 86.1298% |
| `dayu/fins/processors/sec_form_section_common.py` | 1125 | 901 | 224 | 80.0889% |
| `dayu/fins/processors/sec_report_form_common.py` | 416 | 343 | 73 | 82.4519% |
| `dayu/fins/processors/sec_section_build.py` | 303 | 256 | 47 | 84.4884% |
| `dayu/fins/processors/sec_table_extraction.py` | 863 | 691 | 172 | 80.0695% |
| `dayu/fins/tools/preprocess_tools.py` | 62 | 57 | 5 | 91.9355% |
| `dayu/host/_execution_config_projection.py` | 157 | 146 | 11 | 92.9936% |
| `dayu/runtime/argparse_exit.py` | 7 | 7 | 0 | 100.0000% |

Final artifacts：

```text
52b5d2458397af203965197a531a6834ebcad2f963885bf17c9bd10de11b7b68  workspace/tmp/wu-semantic-ownership-01-ar-fix-aggregate.coverage       12042240 bytes
c19bb159b250ab6aa35e49fcb71224f23e050c2df4955e3f95f5b4f9f763e711  workspace/tmp/wu-semantic-ownership-01-ar-fix-aggregate-coverage.json  16121949 bytes
```

`AR-F05 = CLOSED_BY_FRESH_219_OF_219_LEDGER`；coverage exclusion不改变 AR-F06 状态。

## 6. Pyright / Ruff / build

### Pyright

- Full `python -m pyright`：exit `0`，`0 errors, 0 warnings, 0 informations`。

### Ruff

- Full Ruff tool exit `1`，因为 immutable historical findings仍存在；没有把 tool exit冒充全绿。
- Slice 2 locked set：`143`；current：`142`；精确集合 `ADDED=0 / REMOVED=1`。
- 唯一 removed 是 `sec_form_section_common.py` 的历史 F401；本实现删除未使用的 `SecProcessor` import。
- current raw JSON SHA-256：`46a4a54cf302d9a83047fef257799575ba2ec774326b5c55f0fec465841981ad`。
- Docling、唯一新增 production path与六个 mutable test paths的 scoped Ruff：`All checks passed!`。

### Build

`python -m build --outdir workspace/tmp/wu-semantic-ownership-01-ar-fix-s3-build` exit `0`：

```text
6c9b4451122b053d5021ea387cfecad75f461fc003658fb88a60fb7db3b7a993  dayu_agent-0.1.4-py3-none-any.whl  2101692 bytes
8d5c1a2a0bce4f7f285fb3410dcf9c95aa83b7b2ffe1e1d1ba9f1939955555d5  dayu_agent-0.1.4.tar.gz             1836846 bytes
```

build 仅有既有 setuptools license metadata deprecation warnings。

## 7. README judgment

先读取 `dayu/fins/README.md` 的 `Agent更新约束【必须遵守】`。本次 virtual/base publication owner 是稳定的 processor 状态机与公共 consumer 行为，属于该 README 的 Processors 职责，因此：

- `dayu/fins/README.md = UPDATE`：新增两行，说明 atomic validation/publication、whole-base fallback、contradiction fail-closed、terminal idempotence 与 no guessing。
- 根 `README.md`、`dayu/README.md`、`tests/README.md = NO_UPDATE`：没有最终用户入口、安装/CLI 工作流、分层装配或测试文档职责变化。

README final SHA-256：

```text
adcfd166ec7f9ab1c519cf3e8c161092a4a83a2317af7602bbb0c48f37242525  dayu/fins/README.md
```

## 8. Scans / security / no-code ledger

### Canonical 与 owner scans

- Six canonical scans：S1—S4均 exit `1` / zero match；S5 为既有 `48` occurrences / `10` paths、`raw_total=0`；S6 为既有 `3` 个 Web operational labels。Current added hunks在 S5/S6均为零。
- Direct-stream stale path、awaiting旧 private definitions/imports均 exit `1` / zero match；新 direct consumer精确 3 production + 3 tests，新 awaiting owner精确 3 definitions，imports只落在 accepted consumers。
- `_filter_table_refs_by_availability|_assign_unmapped_tables_by_position|fallback_ref|last_known_ref`：zero match。
- `sec_form_section_common.py` added hunks中的 `hasattr/getattr`、`except Exception`、warning/logger、similarity/nearest/position guess：zero match。
- marker producer、`SecProcessor`、10-K/10-Q 与 BS 同族受保护路径相对 `48c6cc5...`：`git diff --exit-code` exit `0`。
- Topic 8两个 production owner相对 accepted base零 diff；deferred/secret/auth/lazy-import added-shape scan为零。

### Security matrices

| Matrix | Fresh result |
| --- | --- |
| Doc containment/truncation + Web DNS/private/proxy/redirect/diagnostic | `346 passed, 1 skipped, 3 warnings` |
| Host digest/EventLog/opaque-ref/compact/trace/wait fence + Engine | `495 passed` |
| Full Fins transaction/atomic swap/path/opaque id/direct validator | `998 passed, 1 skipped, 3 warnings` |
| CLI POSIX quoting/init containment/process fencing | `8 passed, 5 skipped, 3 warnings` |
| current live-browser cleanup owner | `1 passed`，不是 skip |
| deterministic HKEX tests | `77 passed` |

计划中的旧 live-browser node不存在，原命令 exit `4` / no tests；按已裁决 current owner node运行并通过。CLI 五个 skip均是 Darwin 上不可执行的真实 Windows nodes：

```text
AR-F07 = PENDING_RELEASE_BLOCKER / REAL_REMOTE_WINDOWS_EVIDENCE
```

没有重发 HKEX official GET。R10 accepted immutable evidence：

```text
db1f67c5966ff32877f0c4889293a9f74f5552610a1bde793f904de47acf06fe  manifest.json       3046 bytes / 107 lines
cfec10de8f3d20d8a6b7eefc73937cf00a71c61124061f49ec16704222d1ed18  round-001-body.json  56514 bytes
548254d47e805d841a39b60fb51af879d453b36c9bb5c9987156f251969e8fdd  round-002-body.json  864825 bytes
```

### Configured-value semantic-owner scan

扫描只从 current typed model config 解析非空 configured values，只输出计数：

```text
CONFIGURED_VALUE_COUNT=5
ACCEPTED_TRUSTED_INTERNAL Config_source configured_value_count=5 matched_path_count=0
ACCEPTED_TRUSTED_INTERNAL Host_internal_physical match_count=27 matched_path_count=4
ACCEPTED_TRUSTED_INTERNAL Host_internal_exact_path logical_match_count=23 logical_row_count=23
HOST_LOGICAL_OTHER=0
ZERO_REQUIRED tool_trace match_count=0 matched_path_count=0
ZERO_REQUIRED audit match_count=0 matched_path_count=0
ZERO_REQUIRED public match_count=0 matched_path_count=0
ZERO_REQUIRED llm match_count=0 matched_path_count=0
ZERO_REQUIRED logs match_count=0 matched_path_count=0
ZERO_REQUIRED other_output match_count=0 matched_path_count=0
ZERO_REQUIRED review_diff match_count=0 matched_path_count=0
SCAN_VERDICT=PASS
```

Config source与Host internal SQLite/EventLog按裁决为 `ACCEPTED_TRUSTED_INTERNAL`；其它 surface保持明文零泄露。没有输出 value、ref、header或命中正文，没有引入 secret infrastructure。

### Deferred / quota

- Issues `142/151/175/177/178` 与其它 deferred destinations不变。
- 没有 TruncationManager wiring、storage-state lifecycle、Fins hard-kill/process isolation、assets migration、统一 authorization/capability/policy/role framework。
- Gemini低budget账号继续分类为 `EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING`；没有修改 config/model/key/retry/quota/budget，也没有执行额外 quota probe。

## 9. Real smoke

### 通过项

1. AAPL 2025 10-K public download：唯一 success terminal，`discovered=1 / downloaded=1 / failed=0`。
2. 同 workspace public process：唯一 success terminal，`selected=1 / processed=1 / failed=0`。
3. public upload_filing 用固定 fixture建立 smoke 前置源文档：唯一 success terminal，document id与调用方固定 id一致。
4. current live-browser、CLI real shell、HKEX deterministic smoke见 §8。

### R03 required real-provider residual

计划列出的 R03 命令首次在未 seed 的独立 workspace运行：doc/web rounds通过，Fins awaiting明确失败为“未找到 ticker=AAPL 的 filing 源文档”。按 public `upload_filing`补齐前置后复用该 workspace，全部六轮通过，但最终 exact-once oracle被前一次遗留历史污染。

随后在全新的 `workspace/tmp/wu-semantic-ownership-01-ar-fix-s3-r03-fresh` 先 public upload，再只运行一次 R03：doc、web、fins-awaiting、fins-list、fins-read、observation 六轮全部 `ROUND_PASS`，但最终仍 exit `1`：

```text
required tool search_web must occur exactly once
```

直接只读查询该 fresh workspace EventLog 的 canonical `TOOL_CALL_REQUESTED` facts：`read_file`、`start_fins_preprocess`、`list_documents`、`get_document_sections` 各 1，`search_web` 为 0。根因证据因此是 real provider 在 web round直接终结、没有产生必需 canonical tool call，不是 virtual-section实现、ToolRuntime丢失、workspace重复或 quota错误。

遵守“禁止追加真实 provider 调用”：确认 fresh canonical事实后不再重试，不修改 provider/model/key/retry/quota/budget，不把 mock或上一轮结果伪装成 PASS。该 external/provider-adherence residual留给 Controller按真实 smoke evidence裁决；本 artifact不把 R03 gate写成通过。

## 10. Scope / protected state / next gate

Final-tree production Python diff相对 accepted base精确为：

```text
dayu/documents/processors/docling_processor.py            protected pre-existing delta
dayu/fins/processors/sec_form_section_common.py           only new production path
```

Controller/control/plan artifacts仍为：

```text
f89603f8d8c94f7e12455570ae6927ec19469fa42e68e407160b15932239bda1  docs/host/issues-implementation-control.md
552df22871f3eb07465b971ca3fdf182032f3b2087e27442b0d78a1b7d8acc04  docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md
3c8a39a5d15d8d11394640ccec649181acdf37fac34d84a042f5f4fc69d66b7f  accepted-plan commit validation
75d54a37015059b82ed15fe1d8533702b102a8afd3a90da78097c6a045054666  implementation authorization
```

- `git diff --check` exit `0`。
- staged tree：`EMPTY`。
- 没有覆盖既有 stop/continuation/correction/validation/review artifacts。
- 没有第二个新增 production path、公共 schema、兼容分支或 deferred Issue能力。

Finding state：

```text
S3-STOP-F01 = PROTECTED_IMPLEMENTATION_REGRESSION_PASS / REVIEW_PENDING
S3-STOP-F02 = IMPLEMENTED / LOCAL_CODE_AND_REGRESSION_GATES_PASS / REVIEW_PENDING
AR-F05 = CLOSED_BY_FRESH_219_OF_219_LEDGER / CONTROLLER_VALIDATION_PENDING
AR-F06 = RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX
AR-F07 = PENDING_RELEASE_BLOCKER / REAL_REMOTE_WINDOWS_EVIDENCE
R03_REAL_SMOKE = FAILED_EXTERNAL_PROVIDER_EXACT_TOOL_ORACLE / NO_CODE_ACTION / CONTROLLER_ADJUDICATION_REQUIRED
```

下一 gate 仅为 Controller 独立 validation。不得自行进入 code review、stage、commit、push 或 PR。
