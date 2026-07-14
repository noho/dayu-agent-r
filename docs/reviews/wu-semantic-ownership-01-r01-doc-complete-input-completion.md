# WU-SEMANTIC-OWNERSHIP-01 / R01 Doc Complete Input Completion

## 1. 状态、身份与 gate 边界

- **状态**：`complete`。这里的 `complete` 只表示 R01 completion artifact 已按 accepted plan §13.2/§14.3 完整形成；R01 仍停在 **controller completion 复核前**，尚无 aggregate accepted commit。
- **umbrella WU**：既有 `WU-SEMANTIC-OWNERSHIP-01`。
- **internal remediation sub-WU**：`R01 Doc complete input`；不是新 WU。
- **当前 gate**：R01 completion artifact gate。
- **本 gate 唯一写入**：本文件 `docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-completion.md`。
- **明确未做**：未修改 production、tests、README、design、control 或任何既有 artifact；未 commit、push、建 PR；未进入 R02、R03 或 Issue #177 implementation。
- **下一动作权**：仅 controller 可复核本 artifact、决定是否创建 R01 aggregate accepted local commit、更新 control 并进入下一 numbered sub-WU。

动机成立：旧 source byte cap 与 directory entry cap 会在 producer 层永久丢失输入事实，并把该观察预算错误投影成 tool result、schema、LLM 恢复动作和测试事实。修复必须发生在完整 source owner 与目录/result/schema owner，而不是下游展示、Host、provider adapter、README 或测试 fallback。当前代码和全部 accepted evidence 已证明该 root cause 存在且已在 owner boundary 闭合。

## 2. Accepted SHA、slice base 与提交链

| gate/fact | exact SHA | 状态与含义 |
|---|---|---|
| umbrella overdesign remediation accepted plan | `227317a0cf9c0b6fc95ddc16221f333cfe1de115` | `WU-SEMANTIC-OWNERSHIP-01` remediation 总计划 accepted；R01 是其第一个内部 sub-WU |
| R01 accepted plan | `54e352319c7d5fd1306f1da6a6e5f4c2cb983669` | `gateflow: accept R01 doc complete input plan`；本 completion 的 contract 真源 |
| R01-S1 slice base | `1b4e5d33c9c2980b314f66c66ffe31b57c90fefb` | control-only entry commit；相对 accepted plan 未改变 S1 production/test 事实 |
| R01-S1 accepted commit | `1a94d798db27eee02d7acb48876027efdf36cb4b` | `gateflow: accept R01-S1 complete source snapshot` |
| R01-S2 slice base | `547c926e057d2bc78c9bb4e4d3940f87c5e94b52` | control-only entry commit；父链包含 accepted S1 |
| R01-S2 accepted commit | `aa875ea500c6510c0654cf1afe0cd5b39980d1f2` | `gateflow: accept R01-S2 directory completeness` |
| aggregate validation entry / 当前 HEAD | `26a65b0eec470aa3997f4320a31f6c2b9f1e1d8e` | `docs: enter R01 aggregate validation`；父提交为 accepted S2 |
| R01 aggregate accepted commit | **不存在** | completion 尚待 controller 复核；本 artifact 不创建 accepted commit |

## 3. Exact owner contract

### 3.1 完整 source owner

唯一 owner 是 `dayu.documents.processors.source_snapshot.SourceSnapshot`：

1. 单个实例只调用原 `Source.open()` 一次，以固定 64 KiB chunk 复制到真实 EOF；`Source.content_length` 进入前只作 metadata，绝不参与拒绝、截断或 skip。
2. `_SPOOL_MEMORY_BYTES = 1 MiB` 只决定标准库 `SpooledTemporaryFile` 的内存/磁盘 rollover，是内部性能细节，不是业务 cap、配置字段或 LLM-visible 事实。
3. active 后 `snapshot_size` 与 `content_length` 都是实际完整字节数；每次 `open()` 返回独立、seekable、只读 cursor。
4. `materialize()` 对同一 snapshot 只发布一个路径；完整复制期间持续观察同一 cancellation check。
5. `Source.open/read`、取消、consumer exception、materialize 写失败和正常退出都由该 owner 保持原异常语义并清理 spool/partial/materialized path。
6. 同一 lock 串行化 active spool 的 read、detach 与 actual close；close 后 reader 稳定得到 owner-level inactive `ValueError`。
7. 旧 `bounded_source.py`、`BoundedSourceSnapshot`、`SourceBudgetExceeded` 及任何 alias/re-export/wrapper 均不存在。

### 3.2 目录完整性、result 与 schema owner

唯一 owner 是 `dayu.tools.doc_tools`：

1. `_iter_directory_entries()` 在每层按 `(entry.name.casefold(), entry.name)` 稳定排序，以 depth-first 顺序枚举到真实 EOF并持续观察取消。
2. directory symlink 作为 entry 产出但不递归 target；这保持 Python 3.11 既有行为，不宣称为 R01 新安全修复。
3. `list_files` 完整观察所有 entry；`scanned_entries` 是完整观察数，`total` 是完整匹配文件数，output `limit` 只限制稳定顺序首批返回记录。list 不再生产 `scan_complete` / `truncated_reason`。
4. `search_files` 在正文读取前继续执行 resolved containment；未达到 result limit 时扫描到 EOF，只有合法 `result_limit` 可产生 `scan_complete=false` / `truncated_reason="result_limit"`。
5. 五个 `ToolDefinition` 的 name、schema description、parameter description、error projection 与 result keys 都由同一模块产生；没有 provider、Host、README 或测试层重算/补偿。
6. `DocToolLimits` 只保留五个 output/argument limits：list 返回数、section 返回数、search 返回命中数、read 返回字符数、read-section 返回字符数；不包含 source byte 或 directory entry 输入 cap。

### 3.3 真实调用链

```text
ToolsDiscoveryProviderSpec
  -> dayu.tools.doc_provider.discover_tools(spec)
  -> _parse_allowed_paths / _parse_limits
  -> dayu.tools.doc_tools.build_doc_tool_definitions(limits, allowed_roots)
  -> 五个 ToolDefinition / ToolFunctionSchema
  -> Host ToolRuntime 读取 ProcessBackedToolExecutionCapability
  -> _DocProcessTargetFactory.build_process_target(call, context)
  -> _DocProcessTarget.__call__()
  -> _execute_doc_business_value()
  -> validate_and_project_arguments()
  -> _project_doc_paths()
  -> _route_doc_business()
  -> list/get/search/read/read-section owner helper
```

source consumer 分支为：

```text
get/search/read/read-section helper
  -> _source_snapshot(path, cancellation_token)
  -> LocalFileSource(path, uri)
  -> SourceSnapshot(source, _DocSourceCancellationCheck(token))
  -> with SourceSnapshot as active complete snapshot
  -> create_doc_file_processor(snapshot) 或 raw snapshot reader
```

`ToolDefinition.callable` 仍提供测试/非生产 direct fallback，但与 process target 共用 `_execute_doc_business_value()` 真源；生产默认 cancellation/timeout/fencing 由父进程 Host capsule 独占治理，子进程不伪造 cancelled/timeout 信封。

## 4. 删除与保留 contract

### 4.1 已删除

- source 输入预算：`_DOC_SOURCE_MAX_BYTES`、`DocResourceBudget`、`resource_budget`、`max_source_bytes`、`SourceBudgetExceeded`。
- directory producer cap：`_DOC_DIRECTORY_MAX_ENTRIES`、`max_directory_entries`、counter break、`directory_entry_limit`。
- source/directory 丢失投影：`source_budget_exceeded`、`source_limit`、`skipped_oversized_files`、list 专属 `scan_complete/truncated_reason`。
- LLM-facing 规避输入 cap 指引：较小文件、拆分文件、缩小文件范围、缩小目录等恢复动作。
- 旧 module/type/prefix：`bounded_source`、`BoundedSourceSnapshot`、`dayu-doc-bounded`。
- 所有为旧 contract 服务的兼容 alias、re-export、wrapper、optional budget parameter 或下游 fallback。

### 4.2 已保留

- 五个 tool name、provider id/version/source refs、process-backed execution 与 direct fallback 的公共行为。
- `allowed_paths` provider fail-fast、direct path projection、search candidate containment、directory/file symlink 的三条既有边界。
- cooperative cancellation、父进程 process termination/fencing、no-late-accept contract。
- list/get/search 的 output count limits，read/read-section 的字符 output limits。
- read/read-section 的 `ToolTruncateSpec`，以及 Host ToolRuntime 注入并拥有 framework `fetch_more` 的既有能力。
- search 的合法 `result_limit`；read/read-section 的 `content_truncated`、`scan_complete` 与可行动续读说明。
- `base/tools.md` 的章节导航与“大文件先看章节”建议；它描述导航/output efficiency，不声称输入会失败、跳过或不完整。
- provider 的 `invalid_argument`、path policy、`file_not_found`、I/O/permission、cancel 与 generic execution error 投影。

## 5. 最终文件边界

相对 R01 accepted plan `54e35231`，最终 semantic production/test/README 变更闭集为：

| 类别 | 文件 | disposition |
|---|---|---|
| production | `dayu/documents/processors/bounded_source.py` -> `dayu/documents/processors/source_snapshot.py` | 删除 bounded owner，建立完整 snapshot owner |
| production | `dayu/tools/doc_tools.py` | 删除 source/directory cap 全链；完整目录、result、schema 与 consumer 同源迁移 |
| tests | `tests/documents/test_processors.py` | owner 状态机、完整 EOF、取消/异常/cleanup 回归 |
| tests | `tests/documents/test_import_boundary.py` | 扫描新 owner，拒绝旧 module |
| tests | `tests/tools/test_doc_tools_provider.py` | consumer/schema/result/security/真实阈值 contract |
| README | `tests/README.md` | 仅迁移 Documents/Tools 当前测试事实 |

没有其它 production/test/README semantic diff；Host/runtime/contracts/config/tool-discovery 没有 R01 product diff。implementation/review/controller artifacts 与 control gate 状态属于 phaseflow 证据链，不是新增产品语义。

## 6. Test 命令与结果

以下是 accepted artifacts 中已经实际执行的结果；completion artifact gate 没有重跑会产生缓存/临时文件的 pytest，以保持“本 gate 只新增本 artifact”的写边界。

### 6.1 Accepted slice 历史验证

| gate/evidence | 命令 | 结果 |
|---|---|---|
| S1 pre-change baseline | `pytest tests/documents/test_processors.py tests/documents/test_import_boundary.py tests/tools/test_doc_tools_provider.py -q` | `83 passed` |
| S1 initial implementation/controller | 同一 focused matrix | `75 passed`；删除的是旧 budget contract nodes |
| S1 initial coverage run | `coverage run ... -m pytest` 同一三文件 matrix | `75 passed`；当时 `source_snapshot.py 134/147=91.15646258503402%`、`doc_tools.py 616/768=80.20833333333333%` |
| S1 fix controller | 同一 focused matrix | `80 passed` |
| S1 fix owner-only | `pytest tests/documents/test_processors.py -q` / 对应 coverage run | `15 passed`；`source_snapshot.py 144/154=94%` |
| S1 MiMo full re-review | focused matrix；processor coverage run | `80 passed in 2.46s`；`15 passed`；coverage `94%` |
| S1 DS full re-review | focused matrix；processor tests | `80 passed in 2.41s`；`15 passed in 0.44s`；`source_snapshot.py 94%`、`doc_tools.py 80%` |
| S2 controller | `pytest tests/tools/test_doc_tools_provider.py -q` | `66 passed` |
| S2 controller | 4 个 `ToolTruncateSpec` / framework `fetch_more` owner nodes | `4 passed`，仅 3 条第三方 `edgar` deprecation warnings |
| S2 controller | real smoke + symlink/containment + cancellation 6 nodes | `6 passed` |
| S2 controller coverage matrix | `coverage run ... tests/documents/test_processors.py tests/documents/test_import_boundary.py tests/tools/test_doc_tools_provider.py -q` | `84 passed` |
| S2 MiMo review | provider / real smoke / 4 owner nodes / affected matrix | `66 passed in 4.13s`；`1 passed in 2.04s`；`4 passed`；`84 passed in 3.97s` |
| S2 DS review | provider / real smoke / adversarial / owner nodes | `66 passed`；`1 passed in 2.06s`；`10 passed`；`4 passed`（3 warnings） |

### 6.2 R01 completion canonical matrix（accepted plan §14.2）

| exact command | result |
|---|---|
| `pytest tests/documents tests/tools/test_doc_tools_provider.py -q` | `84 passed` |
| `pytest tests/tools/test_combined_tools_acceptance.py::test_combined_truncate_specs_and_fetch_more_owner tests/tools/test_combined_tools_acceptance.py::test_toolruntime_executes_representative_provider_tools_and_accepts_facts tests/host/test_toolruntime_effective_bundle.py::test_enabled_fetch_more_injects_schema_and_callable_when_truncation_enabled tests/host/test_toolruntime_truncation_fetch_more.py::test_truncated_result_exposes_only_cursor_and_scope_token tests/host/test_toolruntime_truncation_fetch_more.py::test_fetch_more_dispatches_as_normal_tool_and_is_single_use -q` | `5 passed`，3 条第三方 `edgar` deprecation warnings；计数由 4 个 output-owner nodes + 1 个 representative-provider accept node 组成 |
| `pytest tests/tools/test_doc_tools_provider.py::test_doc_complete_input_real_smoke_above_legacy_thresholds tests/tools/test_doc_tools_provider.py::test_disallowed_path_returns_failed_outcome tests/tools/test_doc_tools_provider.py::test_search_files_does_not_read_symlink_escape -q` | `3 passed` |
| `coverage run --data-file=workspace/tmp/.coverage-r01-final -m pytest tests/documents tests/tools/test_doc_tools_provider.py -q` | `84 passed` |

Aggregate MiMo deepreview 独立记录 `84 passed`、上述五节点组 `5 passed`、真实 smoke/security 三节点 `3 passed`；aggregate controller 的“MiMo output-owner 4”是只数 output-owner 子集，不少算第五个 representative-provider node。Aggregate DS 独立记录 Documents/Doc provider `84 passed`。两路 aggregate deepreview 均 `PASS`。

## 7. Coverage、类型、diff、scans 与 baseline delta

### 7.1 最终逐 changed production file coverage

| changed production file | covered/statements | exact coverage | gate |
|---|---:|---:|---|
| `dayu/documents/processors/source_snapshot.py` | `144/154` | `93.50649350649351%` | `>=80%` PASS |
| `dayu/tools/doc_tools.py` | `620/770` | `80.51948051948052%` | `>=80%` PASS |

已删除的 `bounded_source.py` 不伪造 coverage。最终值来自同一 aggregate coverage data，不用 S1 中间态或总体百分比替代逐文件事实。

### 7.2 Type / diff / lint

- `python -m pyright`：`0 errors, 0 warnings, 0 informations`。
- `git diff --check 54e35231..HEAD`：aggregate validation PASS。
- S1/S2 修改 Python 文件的 scoped `ruff check`：均 PASS；S2 明确不以整文件 formatter churn 作为 gate。
- completion 写入后的当前工作树 `git diff --check` 与新增文件 whitespace check：见 §14 自检。

### 7.3 删除语义与 owner scans

| scan | 最终结果 |
|---|---|
| `DocResourceBudget|SourceBudgetExceeded|max_source_bytes|max_directory_entries|source_budget_exceeded|directory_entry_limit|source_limit|skipped_oversized_files` in `dayu tests README.md` | 零命中 |
| `bounded_source|BoundedSourceSnapshot|dayu-doc-bounded` in `dayu tests` | 零命中 |
| rejected LLM guidance：`较小文件|拆分文件|缩小文件范围|缩小目录` in Doc tool/prompt/provider tests | 零命中 |
| `TruncationManager|FetchMoreToolCallable|fetch_more` in `doc_tools.py` / `doc_provider.py` | 零命中；证明 Issue #177 未接入 Doc producer |
| `54e35231..HEAD` 对 `dayu/host dayu/runtime dayu/contracts dayu/config/tool_discovery.json` | 零 product diff |
| `allowed_paths|_project_doc_paths|_resolve_search_files_candidate|_raise_if_doc_cancelled|ProcessBackedToolExecutionCapability` | 均在预期 owner 位置命中，并有行为测试 |

最终 production `scan_complete/truncated_reason` 命中全部可分类：

- `_BoundedTextRead.scan_complete`：read/read-section 字符 output typed fact。
- search schema 与 producer/result：只允许 `result_limit` 或 `null`。
- read/read-section schema 与 result：字符 output / line scan owner。
- `_read_source_with_encoding`：字符 output scan producer。
- list producer、list schema与其它 production consumer：零命中。

数值 scan 仅命中 `dayu/documents/processors/html_extraction.py:323,333` 的两个 `-10_000`；它们是**未修改的 HTML 评分哨兵**，不控制 source bytes、directory entries、扫描停止或 Doc tool result，故保留。

### 7.4 Baseline delta

- R01 mandatory matrix、pyright、coverage、diff 与 scans 均无新增/扩散 failure，baseline delta 为 **零**。
- accepted plan §14.1 提及的两个 `tests/host/test_dispatch_scheduler.py` compaction previous-view broad-probe residual 以 `0bc75a5b` 为历史基线，与 R01 owner/mandatory matrix 无交集；本 R01 不执行、不认领，也不把它们写成 R01 pass/fail。
- 验证中的唯一已收敛测试失败是 S2 首次 fixture 在 macOS 大小写不敏感文件系统同时创建 `beta.txt` / `Beta.txt`，违背“两棵树内容相同”的测试前提；fixture 改为无别名名称，production 未增加平台 fallback，最终矩阵全绿。

## 8. 真实阈值 smoke 数值与结果

真实 fixture 不使用 sparse file、伪 declared length、阈值 monkeypatch 或 fake discovery：

| fact | exact value | result |
|---|---:|---|
| allowed root 内小型普通文件 | `10,001` 个 | 全部逐文件真实落盘 |
| 额外大型普通文件 | `1` 个 `zzzz-large-tail.txt` | `34` 个 1 MiB ASCII chunk + 换行 + 36-byte marker |
| 大文件实际字节数 | `35,651,621 bytes` | 大于旧 32 MiB/plan 33 MiB 反证阈值 |
| allowed root 内 symlink | `1` 个 file symlink | 指向 root 外、正文含同一 marker 的普通文件 |
| allowed root entry 总数 | `10,003` | `10,001` 小文件 + `1` 大文件 + `1` symlink |
| list | pattern 仅匹配大文件 | `total=1`、`returned=1`、`scanned_entries=10,003`；无 list partial-only fields |
| read | 读取大文件 | 成功；当前 output limit 返回 `2,000` chars，`content_truncated=true`，`ToolTruncateSpec.target_field="content"` |
| search | 搜索 36-byte 尾部 marker | 唯一命中为大文件；`scanned_entries=10,003`、`total_matches=1`、`scan_complete=true`、`truncated_reason=null`；证明读取到真实 EOF |
| escaped symlink search | outside target 含相同 marker | outside 内容零泄漏，不产生第二命中 |
| escaped symlink direct read | `read_file(outside_link)` | `permission_denied` |

调用链是实际 `ToolsDiscoveryProviderSpec -> dayu.tools.doc_provider.discover_tools -> ToolDefinition.callable`；不是直接调用内部 helper 的伪 smoke。

## 9. README decision

| README | final decision | 直接证据 |
|---|---|---|
| `tests/README.md` | **已在 S2 更新** | 只改 Documents/Tools 两处：完整 source snapshot、完整目录、真实阈值与现有 owner tests；未写 implementation 过程或未来 Issue |
| `dayu/config/README.md` | **无需更新、无 diff** | 只说明 `allowed_paths` 与五个 output/argument limits；没有 source bytes、directory entry cap 或 partial/error 旧语义 |
| 根 `README.md` | **无需更新、无 diff** | R01 不改变安装、初始化、CLI/Web/WeChat 入口、命令参数、默认输出、日志、workspace 位置或最终用户工作流 |
| `dayu/README.md` | **无需更新、无 diff** | UI/Service/Host/Engine 分层和装配关系不变 |
| Engine/Host/Fins README | **无需更新、无 diff** | 对应 production contract 无变更；Host/Fins 只参与 retained owner 验证 |

README 是开发/用户文档，不是 runtime LLM input；不得把 README 文本混作 prompt source。

## 10. Plan / code / aggregate finding 最终 ledger

### 10.1 Plan review

| finding | controller decision | final state |
|---|---|---|
| `R01-PF-01` file/directory symlink owner 边界 | accepted | **closed**；plan 与实现分别保持 directory symlink 不递归、list file-symlink entry、search/direct-read containment |
| `R01-PF-02` S1->S2 临时签名 | accepted | **closed**；S1 仅直传 typed directory constant，S2 同时删除常量/参数，无 shim |
| `R01-PF-03` list partial-only 传播分类 | accepted | **closed**；production 全命中逐 owner 分类，list producer/schema/consumer 零残留 |
| `R01-PF-04` SourceSnapshot 调用链措辞 | accepted | **closed**；helper、`LocalFileSource` 输入与 context-manager type 已消歧 |
| “rglob 跟随 directory symlink”与给 list 新增 resolved containment | rejected | 未实施；Python 3.11.15 直接证据否定前提，R01 不重设计授权 |
| 临时正整数 assert | rejected | 未实施；固定 typed literal 不需要过渡 validator |
| 固定 iterator 私有函数名/API | rejected | 未把 implementation detail 升格成 plan contract |
| smoke slow/skip/并行/timeout 建议 | rejected | 未弱化真实阈值；实际约 2 秒 |
| SourceSnapshot contract 重复标注 | rejected | 未增加重复产品 contract |
| MiMo Finding 07/08 | rejected as self-disproved | 未改；scan 已覆盖且不误伤合法中间态 |
| MiMo OQ-2 sort key | rejected | 最终 `(casefold, original)` + depth-first 确定性已验证 |
| MiMo OQ-3 spool threshold 配置 | no-fix | 1 MiB 仍是内部性能细节，不新增 config owner |
| DS Finding 7/8/9 | passed/no-fix | LLM scan、prompt retain、精确 coverage include 已正确 |

修后 MiMo/DS plan re-review 均 `PASS`；controller 接受 plan，零 open plan finding、零 blocking question。

### 10.2 S1 code review

| finding | severity | final state / owner closure |
|---|---|---|
| `DS-F01` reader/close 并发 | 中 | **accepted -> closed**；同一 owner lock 覆盖 read/detach/actual close，确定性线程测试通过 |
| `DS-F02` materialize 无取消检查 | 中 | **accepted -> closed**；物化循环复用 cancellation owner，partial/spool cleanup 测试通过 |
| `DS-F03` 空 source 边界 | 低 | **accepted -> closed**；exact zero size、EOF、`SEEK_END`、空物化与清理测试 |
| `DS-F04` `Source.open()` OSError | 低 | **accepted -> closed**；原异常身份透出且 spool 关闭 |
| `DS-F05` materialize write OSError | 低 | **accepted -> closed**；原异常身份透出且 partial path 删除 |
| `DS-F06` disk-spill 实现细节测试 | 低 | **rejected / no current fix**；标准库无独立分支，真实 35,651,621-byte smoke 已覆盖 rollover/consumer chain |
| `DS-F07` 非法 seek 防御测试 | 低 | **rejected / no fix**；无本 remediation failure evidence |
| `DS-F08` 放宽 exact LLM description assertion | 低 | **rejected / no fix**；exact assertion 是 LLM-facing owner contract，不能退化成关键词集合 |
| controller test-overdesign follow-up | controller follow-up | **closed**；删除通用 lock/spool、armable cancellation、成功/失败 output factory 层，只保留最小单用途 seam |

MiMo 初审无 material finding；修后 MiMo/DS 完整 re-review 均 `PASS`，零新 finding。S1 controller 最终 accepted。Aggregate DS 文本中“6 个 S1 rejected/deferred”是计数笔误；权威事实是 `DS-F06`、`DS-F07`、`DS-F08` 三项 rejected，加一个后来闭合的 controller test-overdesign follow-up。

### 10.3 S2 与 aggregate

- S2 MiMo review：`PASS`，零 material finding、零 open question。
- S2 DS review：`PASS`，零 material finding、零 open question。
- S2 controller：零 accepted finding，不制造空 fix/re-review gate；S2 accepted。
- Aggregate MiMo deepreview：`PASS`，零 material finding、零 open question。
- Aggregate DS deepreview 的 `AF-01` 至 `AF-06` 都是“无 material finding”的 pass 分类，不是六条 finding；最终 `PASS`，零 open question。
- Aggregate controller：接受两路零 finding 结论，不制造空 fix/re-review gate；当前唯一未完成项就是本 completion artifact 与 controller 对其复核。

## 11. R03 LLM-facing 逐文件 handoff inventory

本节是 accepted plan §13.2 的完整交付，不能由 grep 零命中替代。R03 必须消费本 inventory，不得回改 R01 owner、重新发明 input-cap 删除规则，或误删保留的 output/导航 guidance。

### 11.1 五个 `ToolFunctionSchema.description`

| file | exact source | LLM-facing? | owner | delete/rewrite/retain | final text or assertion | evidence |
|---|---|---|---|---|---|---|
| `dayu/tools/doc_tools.py` | `_build_list_files_definition` / `ToolFunctionSchema.description` | yes | list result/schema owner | **rewrite** | “列出配置允许访问目录中的文件。files 是按稳定顺序返回的首批记录，returned 是返回数，total 是完整遍历后的匹配文件总数，scanned_entries 是完整检查的目录项数。若 total 大于 returned，表示 limit 限制了本次返回数量；可收紧 pattern 或在参数允许范围内提高 limit。定位后把 files[].path 交给 get_file_sections、read_file 或 read_file_section。” | provider test exact equality；list result absence assertions；真实 `10,003` entry smoke |
| `dayu/tools/doc_tools.py` | `_build_get_file_sections_definition` / description | yes | section navigation schema owner | **retain** | “列出文件的章节结构。先用它定位章节；若返回的 sections[].ref 不为 null，就把 ref 交给 read_file_section。若 ref 为 null，改用 read_file，不要猜 ref。” | current source；provider section/read chain tests；无 input-cap token |
| `dayu/tools/doc_tools.py` | `_build_search_files_definition` / description | yes | search result/schema owner | **rewrite** | “在配置允许访问目录中按关键词查找。matches 是本次命中，total_matches 等于返回命中数，scanned_entries 是已检查目录项数。scan_complete=false 且 truncated_reason=result_limit 表示命中数达到 limit，可收紧关键词或在参数允许范围内提高 limit 后重试；完整扫描时 scan_complete=true 且 truncated_reason 为 null。若命中带 ref，把 matches[].file 和 ref 交给 read_file_section；ref 为 null 时用 read_file。” | provider test exact equality；search key exact set；EOF/result-limit tests；无 directory/source reason |
| `dayu/tools/doc_tools.py` | `_build_read_file_definition` / description | yes | read character-output schema owner | **retain** | “按整文件或按行范围读取内容。content 是本次返回文本，returned_chars 是其字符数。content_truncated=true 或 scan_complete=false 表示字符预算命中，total_lines 会是 null；请用 start_line/end_line 缩小范围继续读取。完整扫描时 scan_complete=true 且 total_lines 为整数；请求行范围时 line_range 是两个整数。没有 ref、或文件不支持章节读取时用它。” | exact current source；provider asserts retained `content_truncated/scan_complete`；read output tests |
| `dayu/tools/doc_tools.py` | `_build_read_file_section_definition` / description | yes | section character-output schema owner | **retain** | “按章节 ref 读取内容。ref 必须来自 get_file_sections；支持的格式有 md, markdown, html, htm, *_docling.json。returned_chars 是返回 content 的字符数；content_truncated=true 或 scan_complete=false 时，改用 read_file 按更小行范围继续读取。若文件不支持章节读取或 ref 为 null，也改用 read_file。” | current source；section partial fields test；ref/navigation tests |

### 11.2 五工具 parameter property descriptions

| file | exact source | LLM-facing? | owner | delete/rewrite/retain | final text or assertion | evidence |
|---|---|---|---|---|---|---|
| `dayu/tools/doc_tools.py` | `_list_files_parameters`: `directory/pattern/recursive/limit` | yes | list parameter schema owner | **retain** | `directory` 必须是允许且存在的起点目录并从 `files[].path` 选文件；`pattern` 是可选文件名 glob；`recursive` 控制递归；`limit` 只表示最多返回多少文件，默认 20、maximum 来自 `list_files_max`（packaged 200） | current property descriptions；schema maximum/limits tests；无 rejected token |
| `dayu/tools/doc_tools.py` | `_get_file_sections_parameters`: `file_path/limit` | yes | section parameter schema owner | **retain** | `file_path` 使用 list 返回路径，大文件先定位章节；`limit` 只表示最多返回章节，默认 10、maximum 来自 `get_sections_max`（packaged 200） | current schema；explicit limits tests；“大文件先定位章节”是导航效率，不是 input cap |
| `dayu/tools/doc_tools.py` | `_search_files_parameters`: `query/directory/include_types/limit` | yes | search parameter schema owner | **retain** | `query` 是明确搜索词；`directory` 是允许且存在的起点目录；`include_types` 是可选扩展名数组；`limit` 只表示最多返回命中，默认 20、maximum 来自 `search_files_max_results`（packaged 50） | current schema；provider limits tests；无 source/directory input-cap token |
| `dayu/tools/doc_tools.py` | `_read_file_parameters`: `file_path/start_line/end_line` | yes | read parameter schema owner | **retain** | `file_path` 使用 list 路径；`start_line/end_line` 都从 1 开始且包含端点，用于按行缩小 **output** 范围；schema 不暴露 source byte limit | current schema；range tests；read description/output fields |
| `dayu/tools/doc_tools.py` | `_read_file_section_parameters`: `file_path/ref` | yes | section parameter schema owner | **retain** | `file_path` 使用允许路径；`ref` 必须来自 `get_file_sections.sections[].ref`，null 时用 `read_file`，禁止猜 ref | current schema；section/ref tests；无 rejected token |

所有 `minimum/maximum/default` 都是参数/output contract；五个 parameter schemas 中没有 source byte、directory entry、resource budget、split/smaller-file 恢复语义。

### 11.3 Error code / message / hint owner

| file | exact source | LLM-facing? | owner | delete/rewrite/retain | final text or assertion | evidence |
|---|---|---|---|---|---|---|
| `dayu/tools/doc_tools.py` | `validate_and_project_arguments` -> `_DocBusinessFailure` | yes，进入 failed tool result | shared argument-validation owner + Doc failure projection | **retain** | schema 失败使用 `invalid_argument` 与 validator 产生的业务可读 message/hint；缺 `file_path` 的 test 证明 message 不混入 `Hint:`，hint 为 `Add required fields and retry: file_path.` | process-target argument-validation test |
| `dayu/tools/doc_tools.py` | `_project_doc_paths` | yes，进入 failed tool result | Doc path policy owner | **retain** | 无 roots/越界/非目录为 `permission_denied`；路径类型错误/非文件为 `invalid_argument`；不存在为 `file_not_found`。静态 hints 分别要求配置/使用 allowed roots、设置路径字符串、校验路径后重试 | direct/process path tests、outside symlink smoke |
| `dayu/tools/doc_tools.py` | `_execute_doc_business_value` exception projection | yes | Doc business error owner | **retain** | `_DocToolArgumentError -> invalid_argument` + `Fix arguments to match the tool schema and retry.`；`_DocFileAccessError`/`PermissionError -> permission_denied` + allowed-path hint；`FileNotFoundError -> file_not_found` + `Verify the file path and retry.`；未知异常 -> `execution_error` + `Inspect provider diagnostics or retry with narrower arguments.` | direct/process outcome parity tests；provider full suite |
| `dayu/tools/doc_tools.py` | `_invoke_doc_business` / `_cancelled_outcome` | yes | fallback callable cancel projection；生产取消由 Host owner | **retain** | Host-cancelled outcome 使用业务可读停止说明与 `当前工具调用已停止；如仍需要该结果，请等待用户确认后再重新发起。`；不暴露 run/session/payload/digest/correlation/token 等治理字段 | 五工具 pre-cancel 与 ToolRuntime cancellation/fencing tests |
| `dayu/tools/doc_tools.py` | former source budget failure/catch/hints | no longer present | former source-cap owner | **delete** | `source_budget_exceeded`、较小/拆分文件与 source skip hint 均删除；真实 source I/O 走现有 file/permission/execution error owner，不伪装为 budget failure | 全域零命中；完整 source read/search tests |

`_DocBusinessFailure` 本身是内部 typed carrier；只有其 `error/message/hint` 经 direct outcome 或 process failed envelope 投影后才是 LLM-facing。process target、Host governance id、timeout scalar和内部异常类型名不进入 model result。

### 11.4 Result keys

| file | exact source | LLM-facing? | owner | delete/rewrite/retain | final text or assertion | evidence |
|---|---|---|---|---|---|---|
| `dayu/tools/doc_tools.py` | `_list_files_business` result | yes | list result owner | **delete + retain** | 最终 keys：`directory, files, total, returned, scanned_entries`；删除 `scan_complete/truncated_reason` 与所有 source/entry-only fields | owner tests断言字段不存在；真实 smoke |
| `dayu/tools/doc_tools.py` | `_search_files_business` result | yes | search result owner | **retain + narrow** | 最终 keys：`query, directory, matches, total_matches, scanned_entries, scan_complete, truncated_reason`；reason 只允许 `result_limit` 或 `null`，`total_matches` 明确等于返回命中数 | exact key-set test、EOF/result-limit tests、schema exact assertion |
| `dayu/tools/doc_tools.py` | `_read_file_business` result | yes | read character/line scan result owner | **retain** | 必有 `file_path, content, returned_chars, content_truncated, scan_complete, total_lines`；按行请求时另有 `line_range`。这些是 output partial/scan facts，不是 input loss | raw long line、encoding/range、complete source 与 output partial tests |
| `dayu/tools/doc_tools.py` | `_get_file_sections_business` / `_sections_via_processor` | yes | section navigation result owner | **retain** | 顶层 `file_path, sections, total_sections, returned, total_lines`；processor section 含 `ref,title,level,parent_ref,table_refs,table_count,preview,line_range,line_count` | Markdown/Docling section tests |
| `dayu/tools/doc_tools.py` | `_read_file_section_business` result | yes | section character-output result owner | **retain** | `file_path, ref, title, content, returned_chars, content_truncated, scan_complete, tables, children, content_word_count` | section partial test、combined provider fixtures |

### 11.5 其它逐文件 source

| file | exact source | LLM-facing? | owner | delete/rewrite/retain | final text or assertion | evidence |
|---|---|---|---|---|---|---|
| `dayu/config/prompts/base/tools.md` | `<when_tag doc>` 路径 A/B 与“大文件先看 get_file_sections，避免整文件 read_file” | **yes** | base Doc workflow guidance owner | **retain / no diff** | 这是章节导航与 output-efficiency 指引；不声称大文件失败、被跳过、需要拆分或目录不完整，R03 不得误删 | 当前 prompt 原文；R01 diff 为零；rejected-token scan 零命中 |
| `tests/tools/test_doc_tools_provider.py` | `test_doc_tool_descriptions_explain_only_retained_output_facts` | test LLM fixture | tool schema owner-contract test | **rewrite assertions** | exact equality 锁定 list/search final descriptions；断言 list 无 `scan_complete/truncated_reason`，search 仅 `result_limit`，read 保留 `content_truncated/scan_complete` | test source；provider/aggregate matrix通过 |
| `tests/tools/test_doc_tools_provider.py` | `test_doc_complete_input_real_smoke_above_legacy_thresholds` | test LLM tool-call fixture | public discovery/callable contract test | **rewrite fixture/arguments** | 无自然语言 prompt；真实 LLM-facing 输入由 discovery 生成 schema 与 `ToolCallRequest.arguments` 构成：list=`directory/pattern/recursive`，read=`file_path`，search=`directory/query`。真实 tail marker、result fields 与 containment assertions如 §8 | 真实 `ToolsDiscoveryProviderSpec -> discover_tools -> ToolDefinition.callable`；3-node aggregate smoke通过 |
| `tests/tools/test_doc_tools_provider.py` | search/read/list key、absence与完整 source assertions | test LLM fixture | result/schema owner-contract tests | **rewrite** | search exact keys；list entry/source partial fields absence；read完整 source；search完整 snapshot进 processor；保留合法 output fields | provider `66 passed`、aggregate `84 passed` |
| `tests/tools/test_combined_tools_acceptance.py` | `test_combined_truncate_specs_and_fetch_more_owner` | test schema/effective-bundle consumer | Host ToolRuntime output owner test | **retain / no diff** | 业务 bundle 中所有 truncating definitions 使用 current `ToolTruncateSpec`；业务 bundle没有 `fetch_more`；effective ToolRuntime 注入 framework `fetch_more` 并拥有 callable/schema | owner node通过；这**不代表** Doc/TruncationManager complete wiring或 Issue #177完成 |
| `dayu/tools/doc_provider.py` | provider config parse/errors，含 empty `allowed_paths` fail-fast | **no，operator/composition** | Doc provider config owner | **retain / no diff** | enabled provider 缺失/空白名单在 discovery 阶段抛 Doc-specific `ValueError`；配置类型/正整数错误也在 discovery fail-fast，不进入 tool schema/result/model context | `test_provider_enabled_without_allowed_paths_fails_fast`；definition 构造前抛错 |
| `dayu/config/tool_discovery.json` | `providers.doc-tools` raw config | **no，ConfigLoader/provider input** | raw provider config owner | **retain / no diff** | `enabled=false`、`allowed_paths=[]`；五 limits 为 `200/200/50/80000/50000`，只表示 output/argument control；没有 input cap | `dayu/config/README.md` 明确 ConfigLoader 原样读取、不 import provider、不做 discovery；R01 config diff为零 |
| `dayu/config/README.md` | `tool_discovery.json` 与 Doc provider说明 | **no，开发文档** | config README owner | **retain / no diff** | 记录 raw config、allowed paths 与五个合法 limits；不含旧 source/directory cap | README decision与当前原文 |
| `tests/README.md` | `tests/documents` / `tests/tools` owner职责 | **no，开发测试文档** | tests README owner | **rewrite** | 已记录完整 snapshot、完整目录、真实 10,001/33 MiB+ smoke与 retained output/security tests；不作为 runtime prompt | S2 accepted diff与 README 更新边界 |
| `README.md` | 最终用户安装/CLI工作流 | **no，用户文档，非 runtime prompt** | root README owner | **retain / no diff** | R01 不改变其读者职责内事实，不写内部 Doc cap/remediation | root README update constraints与零 diff |

扫描和逐 source 回查没有发现 allowlist 外额外 Doc LLM-facing source。R03 应把以上每一行纳入其人工 source inventory，并把本表视为 R01 已完成的输入，而不是重新审判 R01 contract。

## 12. Issue #177 non-implementation 与 retained security

### 12.1 Issue #177 边界

- Issue #177 **只拥有 Doc output / remainder 经 `TruncationManager` 的完整 continuation wiring**。
- 当前 read/read-section 只声明现有 `ToolTruncateSpec`；Host ToolRuntime 可在 effective bundle 注入 framework `fetch_more`，但 Doc producer 没有接 `TruncationManager`、remainder store、cursor/scope token 或 `FetchMoreToolCallable`。
- `TruncationManager|FetchMoreToolCallable|fetch_more` 在 `dayu/tools/doc_tools.py` 与 `dayu/tools/doc_provider.py` 零命中；Host/runtime/contracts 无 R01 product diff。
- 当前 search `total_matches` 等于返回命中数并由 description 自解释；只有未来**另行授权的 output-continuation 设计**明确要求 complete-result continuation 时才能改，不是本 R01 open finding。
- 极大 input 的磁盘/时间/inode 风险**不属于 Issue #177**，不得借 Issue #177 恢复 source/directory hard-fail。

### 12.2 Retained security

- provider 启用时 `allowed_paths` 不能为空；raw default 保持 disabled/empty。
- direct read/get/section 由 `_project_doc_paths` 在输入边界 canonicalize 并做 allowed-root containment。
- search 在读取候选正文前由 `_resolve_search_files_candidate(resolve(strict=True))` 重新做 containment；outside symlink 内容不读取。
- list 保持 directory-entry 语义：file symlink 按 entry path/name 与 target metadata列出，不新增 per-entry containment；directory symlink 产出但不递归。
- cancellation、process termination/fencing、ToolRuntime accept barrier/no-late-accept 保持。
- R01 没有创建统一 authorization framework、角色 schema、兼容 facade 或新 auth WU。

## 13. Residual、owner/destination 与下一依赖

| residual | final classification | owner / destination |
|---|---|---|
| 极大 source/目录会增加磁盘、时间、内存排序或 inode 消耗 | accepted current product tradeoff；当前以完整 spool/遍历、process boundary、cancellation 和 output limits治理，不恢复未经授权 hard-fail | **未来需明确授权的 input-governance 设计**；本 R01 不创建 authorization WU/schema。若未来授权，owner 必须是 **Host ToolRuntime 或同级 Host governance boundary**，并同时定义配置、可见错误、LLM contract 与 tests |
| 五工具 output/remainder 尚未全部无损续读 | tracked existing issue | **GitHub Issue #177**；仅 Doc/TruncationManager output continuation |
| search result limit 后不扫描剩余 entry，`total_matches` 是返回数 | accepted current output contract | 当前无 open owner；只有 future authorized output-continuation scope 才可由 Issue #177设计改变 |
| symlink/TOCTOU 是三条既有局部边界 | retained security behavior，不是当前 defect | 当前保持；不创建 auth WU/schema。未来若有直接证据并获授权，owner 同样是 Host ToolRuntime 或同级 Host governance，而不是 list/search 下游 shim |

这组 residual 采用 aggregate controller adjudication 的最终收窄结论，覆盖 accepted plan §16 中把极大 input 泛化指向 Issue #177 的旧表述。没有未分类 residual、blocking owner question、allowlist expansion 或 `needs-more-evidence` finding。

下一依赖顺序：

1. controller 独立复核本 completion artifact；
2. controller 若接受，创建 R01 aggregate accepted local commit并更新 control；
3. 然后才可进入 **R02 Web provider config + HTTP/browser/diagnostic executors**；本 artifact 不进入 R02；
4. 本 §11 inventory 由 controller 保存给后续 **R03 Host accepted-call/evidence LLM projection**，R03 必须消费但不得回改 R01 owner；本 artifact 不进入 R03。

## 14. Completion author 自检

- 已按用户指定顺序完整读取总控、umbrella control、controller discussion、remediation plan、R01 accepted plan、aggregate validation、两份 aggregate deepreview、aggregate controller adjudication，以及全部 S1/S2 implementation/review/fix/re-review/controller artifacts。
- 已对当前 `source_snapshot.py`、`doc_tools.py`、processor/import-boundary/provider/combined-owner tests、`base/tools.md`、`doc_provider.py`、`tool_discovery.json`、`tests/README.md`、`dayu/config/README.md` 与根 README 做直接证据回查。
- accepted SHA、slice base/commit、owner contract、调用链、删除/保留 contract、测试、逐文件 coverage、真实阈值、README、finding、Issue #177、安全、residual 与 R03 inventory 均已逐项交叉核对。
- 当前 artifact 与 existing evidence 一致。
- `git diff --check`：exit `0`、无输出。
- `git diff --no-index --check /dev/null docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-completion.md`：无 whitespace error 输出；exit `1` 仅表示新增文件与 `/dev/null` 内容不同。
- `git status --short` 与 preflight 比较后，唯一新增路径是本 completion artifact；既有 `docs/host/issues-implementation-control.md` 修改与四份 aggregate artifact 的 untracked 状态未被本 gate 改写。
- stop point：**controller completion 复核前**。
