# WU-SEMANTIC-OWNERSHIP-01 / R01 Doc Complete Input 独立实施计划

## 0. Gate 身份、base 与硬边界

- **umbrella**：既有 `WU-SEMANTIC-OWNERSHIP-01`。
- **内部 remediation sub-WU**：`R01`，slug 固定为 `r01-doc-complete-input`；它不是新 WU、feature 或 issue。
- **artifact 身份**：本文是 R01 的独立 code-generation-ready plan，不是 umbrella plan 的替代品，也不是 implementation/review/completion artifact。
- **accepted umbrella base**：`227317a0cf9c0b6fc95ddc16221f333cfe1de115`（`gateflow: accept semantic ownership remediation plan`）。
- **plan-time HEAD**：`edc6ea62c7685d6d1625422df7b18ec6a22c323e`，分支 `phaseflow/host-issues-control`。
- **base 一致性证据**：`227317a0..edc6ea62` 在 R01 production/tests/README 路径上无 diff；下列关键 blob 在两个 SHA 完全相同：
  - `dayu/documents/processors/bounded_source.py`：`4a09dbb43a20f0530aa1c0691b89ee3ff013764b`；
  - `dayu/tools/doc_tools.py`：`09aa9b2c333ff45549a10005bcbe5d4f9b28f5f3`；
  - `dayu/tools/doc_provider.py`：`b6521d0e2ce87e813b26260529a00869d1ae9767`；
  - `tests/documents/test_processors.py`：`3b2c882e1b06488aec3ea379084b41e11c7969d1`；
  - `tests/documents/test_import_boundary.py`：`e144b2602650b550bf13c4a2a2f79e528c85a032`；
  - `tests/tools/test_doc_tools_provider.py`：`af7729f0d5bd0b3ddbcff783eb14ef0231b4b96a`；
  - `dayu/config/README.md`、`tests/README.md`、根 `README.md` 也分别保持同一 blob。
- **当前 gate**：只完成本文；后续必须执行双路 plan review、controller adjudication、plan fix、双路完整 re-review 与 controller accepted-plan local commit，之后才可 implementation。
- **本 gate 写权限**：只新增本文。不得修改 control/design/产品代码/测试/README/review，不 commit、push、建 PR 或进入 implementation。
- **Issue 177**：`WU-SEMANTIC-OWNERSHIP-01-DOC-TRUNC-R1` / GitHub Issue #177 仍是 Doc 五工具完整接入 `TruncationManager` / `fetch_more` 的唯一 destination。R01 不实施、部分实施或预埋该 issue。

## 1. 必读真源与裁决优先级

本文按以下优先级冻结 R01：

1. `AGENTS.md` 的语义 owner、LLM-facing、分层、编码、测试、README 约束。
2. `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` Topic 1 与 Topic 9 的最终 controller/user 裁决。
3. 五份稳定设计真源中的相关边界：
   - `docs/tool/design.md` §1、§2、§10：Doc 完整授权输入、业务可读 schema、现有 `allowed_paths` 与 I/O 防御；
   - `docs/host/design.md` §18、§18.4、§19、§22：ToolRuntime/accept barrier、authorization 与 I/O 防御分工、`ToolTruncateSpec` / `fetch_more`、取消；
   - `docs/engine/design.md` §10、§11、§13、§16：Engine 只消费 `ToolExecutor`/schema，handshake timeout 与取消边界，不拥有 truncation；
   - `docs/fins/design.md`：Fins 只拥有财报 domain/storage 语义，不拥有通用 Doc source/read contract；
   - `docs/ui/design.md`：UI/CLI 只消费下层 typed contract，不拥有 Doc 输入预算或工具结果重算。
4. `docs/host/wu-semantic-ownership-01-overdesign-remediation-plan.md` §0、§6、§7、§8、§21—§24 的 R01 mandatory starting baseline。
5. `docs/host/issues-implementation-control.md` 当前 entry：R01 plan gate、accepted umbrella SHA、Issue #177 transferred owner 与 baseline failure registry。
6. 当前 production code、tests、README 的直接证据。

若 review artifact、历史测试或旧实现与上述裁决冲突，不保留兼容行为；若当前直接证据实质改变 owner、依赖、production allowlist 或 accepted contract，则按 §15 停止回 controller。

## 2. 第一性原理判断与 root cause

### 2.1 动机成立，但修复范围必须保持窄

缺陷真实存在，且 umbrella 的 `production-high` 评估成立：Doc 是读取用户已授权本地文档的通用只读工具，当前实现却在产品未要求时把文件大小和目录规模变成输入能力上限。超过阈值时，数据不是仅在首次 LLM 输出中被分页，而是在 producer 读取/扫描阶段被拒绝或遗漏；模型无法通过 `fetch_more` 恢复被丢弃的输入。因此这不是性能偏好，而是完整性错误。

严重性不能被扩大成 Host/Engine、durable schema、统一 authorization 或通用资源治理重做。正确修复只需删除 Doc owner 自造的输入 hard cap/partial contract，继续保留既有路径 authority、取消、process capsule 和输出限制。

### 2.2 同源 root cause 证据

| 错误语义 | 产生 owner 的直接证据 | 下游传播 |
|---|---|---|
| 单 source 32 MiB hard-fail | `bounded_source.py::BoundedSourceSnapshot.__enter__` 先比较 declared length，再按 `max_bytes + 1` 实读并抛 `SourceBudgetExceeded`；`doc_tools.py::_DOC_SOURCE_MAX_BYTES` / `DocResourceBudget.max_source_bytes` 固定为 32 MiB | `_execute_doc_business_value` 把异常投影为 `source_budget_exceeded` 和“拆分/较小来源”提示；read/section/search 都从 `_bounded_local_source` 进入该路径 |
| 目录 10,000 entry partial | `doc_tools.py::_DOC_DIRECTORY_MAX_ENTRIES` / `DocResourceBudget.max_directory_entries` 固定为 10,000；`_list_files_business` 与 `_search_files_business` 在 counter 命中时 `break` | list/search 返回 `scan_complete=false`、`directory_entry_limit`，schema description 要求模型缩小目录 |
| oversized 文件静默跳过 | `_search_files_business` 捕获 `SourceBudgetExceeded`，累加 `skipped_oversized_files` 并继续 | search 结果成为不可恢复 partial，`source_limit` 与“较小文件”进入 LLM-facing description |
| rejected semantics 被测试固化 | `tests/documents/test_processors.py` 与 `tests/tools/test_doc_tools_provider.py` 直接断言 exception、budget dataclass、entry cap、oversized skip 和 LLM 文本 | 测试倒逼 production 保留错误 owner contract |

根因不在 Host 输出截断：Host 的 `TruncationManager` 只能处理 producer 已返回的完整目标值，不能恢复 source snapshot 已拒绝的字节或目录循环已跳过的 entry。也不在 UI/README；在下游改文案或 fallback 只会造成“显示完整、事实仍丢失”。

### 2.3 Plan-time stop audit 结论

- 语义 owner：未变化，仍为 `dayu.documents.processors` + `dayu.tools.doc_tools`。
- 依赖：未变化，R01 无前置 sub-WU，仍是第一个 remediation sub-WU。
- production allowlist：未变化，当前调用链完全落在 umbrella §7.4 R01 闭集内。
- accepted contract：未变化；当前代码正是 controller 要删除的基线实现。
- 结论：不触发回 controller，可以形成独立 R01 plan。

## 3. Exact owner contract

### 3.1 `SourceSnapshot`：一次性 source 的完整可重读快照 owner

`dayu.documents.processors.source_snapshot.SourceSnapshot` 是唯一 source snapshot owner，contract 固定如下：

- 输入：一个 `Source` 和可选无参 `cancellation_check`；不接收字节上限、budget/profile/policy 或 Host 类型。
- 建立：只调用原 `Source.open()` 一次，按固定内部 chunk 复制到 `SpooledTemporaryFile`，直到真实 EOF；`Source.content_length` 只作为来源 metadata，绝不用于拒绝或提前停止。
- spool：`_SPOOL_MEMORY_BYTES` 只决定内存转磁盘阈值，是内部性能细节，不是可见输入 cap；任何长度都走同一复制状态机。
- 读取：active 期间每次 `open()` 返回独立、seekable、只读 cursor；不同 processor/caller 不共享位置。
- 物化：同一 active snapshot 最多拥有一个 materialized path；重复 `materialize()` 复用；suffix 不形成第二个副本 contract。
- metadata：进入前 `content_length` 可返回 source 声明值；active 后返回完整复制得到的精确字节数；`uri/media_type/etag` 机械透传。
- 状态：`new -> active -> closed`。同一实例只允许进入一次；`close()` 幂等；正常退出、Python 异常、I/O 异常与取消都关闭 spool 并删除 materialized path。
- 错误：`Source.open/read` 的真实 `OSError` 与 cancellation check 的异常原样透出给直接 owner consumer；不存在 size/budget exception 或同义错误。
- 分层：模块只依赖标准库和同包 `Source` 协议，不导入 Tool/Host/Engine/Service/UI/Fins。

删除 `bounded_source.py` 并新增 `source_snapshot.py`；类名从 `BoundedSourceSnapshot` 改为 `SourceSnapshot`。不得保留旧模块、旧类、`SourceBudgetExceeded` re-export、wrapper、alias 或兼容 import。

### 3.2 `doc_tools`：授权路径、完整目录观察与业务结果 owner

`dayu.tools.doc_tools` 继续拥有五个工具的 schema、参数校验、路径投影、同步业务函数、结果/error 投影与 process-backed target：

- `list_files` 对授权目录按确定顺序遍历全部相关 entry，结果为：
  - `directory`、有界 `files`、完整匹配数 `total`、`returned`、完整遍历计数 `scanned_entries`；
  - 当 `total > returned` 时只是现有 output `limit` 使首屏记录有界；输入扫描仍完整；
  - 删除只为 10,000 partial 存在的 list `scan_complete` / `truncated_reason` 字段，避免保留永远为 `true/null` 的死 contract。
- `list_files` 的 file-symlink owner 保持当前 directory-entry 语义：遍历 entry 的 `is_file()` 成立时，继续按 symlink entry 的相对路径/名称和 `stat()` metadata 形成记录；list 不读取文件正文，不调用 `_resolve_search_files_candidate`，也不新增 per-entry resolved containment 或新的 symlink/authorization policy。
- `search_files` 对授权目录使用同一 deterministic iterator；每个候选仍经 resolved containment/file 检查：
  - 不因文件字节数跳过；
  - `matches` 仍受现有 `limit/max_results` 控制；达到该输出 limit 可以停止并保留 `scan_complete=false`、`truncated_reason=result_limit`；
  - 未达到输出 limit 时遍历到 EOF，返回 `scan_complete=true`、`truncated_reason=null`；
  - 删除 `skipped_oversized_files`，不再允许 `source_limit` / `directory_entry_limit`。
- `get_file_sections`、`read_file`、`read_file_section` 都通过 `SourceSnapshot`，不接收或传递 `max_source_bytes`；真实 I/O/decode/unsupported/ref/argument 错误保持现有 typed projection。
- deterministic traversal 使用模块级私有 helper，而不是复制 list/search 两套规则。Python 3.11 当前 `Path.rglob("*")` 会产出 file/directory symlink entry，但不会递归进入 directory-symlink target；新 helper 必须保持这一现状，不得把“不递归”描述或实现成 R01 新安全修复。helper 按每层 entry 的 `(name.casefold(), name)` 稳定排序、递归时保持稳定 depth-first 顺序、每个 entry 前观察 cancellation。search 仍在实际内容读取前调用 `_resolve_search_files_candidate` 重新 resolve/containment；direct read 仍在 `_project_doc_paths` 对输入路径 canonical resolve/containment 后才读取。三者是不同 owner boundary，不得包装成统一权限 contract。
- 不引入目录 index、cache、pagination、异步 walker、第二种 Source 抽象或新的公开 dataclass。

### 3.3 `doc_provider`：配置 owner 保持不变

`dayu.tools.doc_provider` 仍只解析：

- 必需且非空的 `allowed_paths`；
- `DocToolLimits` 的五个输出/参数 limit；
- provider identity/version/source ref。

它从未解析 32 MiB / 10,000 cap，当前证据不要求修改。R01 不把输入预算迁入 config，也不重命名五个现有 limit。

### 3.4 Host/Engine output owner 保持不变

- `DocToolLimits` 保留；`list_files_max`、`get_sections_max`、`search_files_max_results`、`read_file_max_chars`、`read_file_section_max_chars` 仍是 output/argument 侧控制。
- `read_file` 与 `read_file_section` 当前 `ToolTruncateSpec(TEXT_CHARS, target_field="content")` 声明保持原样。
- ToolRuntime 注入的 framework `fetch_more`、cursor/scope token、accept barrier、run-local remainder、取消/TTL/error contract 均不改。
- 当前 list/get-sections/search producer pre-limit 与五工具未完整接入 `TruncationManager` 的缺口继续由 Issue #177 拥有。R01 不声称该缺口已关闭，也不在 Doc provider 内注册业务 `fetch_more`。
- Engine 仍只看到 `ToolSchema` 与 `ToolExecutor` outcome，不增加 Doc、snapshot、budget 或 fetch-more 特例。

## 4. 删除、保留与非目标清单

### 4.1 必须删除

- 文件/符号：`bounded_source.py`、`BoundedSourceSnapshot`、`SourceBudgetExceeded`、`DocResourceBudget`。
- 常量/参数/字段：`_DOC_SOURCE_MAX_BYTES`、`_DOC_DIRECTORY_MAX_ENTRIES`、`max_source_bytes`、`max_directory_entries`、process target/factory 的 `resource_budget`。
- 行为：declared-length early reject、`limit+1` byte probe、source budget error mapping、directory counter break、oversized catch/skip。
- 结果/schema：`source_budget_exceeded`、`source_limit`、`directory_entry_limit`、`skipped_oversized_files`；list 专用于 entry partial 的 `scan_complete/truncated_reason`。
- LLM-facing 文本：要求模型缩小/拆分文件、改用较小来源、缩小目录来规避这些输入 cap 的 description/message/hint/assertion。
- 测试：固化 budget/partial/skip 的 owner 与 fixture contract。

### 4.2 必须保留

- provider `allowed_paths` 必填/fail-fast、顶层 path canonical resolve、containment、文件/目录类型检查；direct read 继续在这个边界拒绝 resolved outside file symlink。
- Python 3.11 当前 directory symlink entry 可见但不被递归；list 的 file symlink 继续按 directory entry 列出且不增加 per-entry resolved containment；search candidate 继续在正文读取前 resolve/containment，symlink escape 不读取；process child 内再次解析 allowed root/path。
- process-backed execution capability、父进程取消/timeout/late-publication fencing、direct callable fallback 的 cooperative cancellation。
- Source snapshot 的完整 spool、独立 cursor、materialization、cleanup、取消检查。
- `DocToolLimits`、参数 schema `limit/maximum`、read/section output char limit 与当前 `ToolTruncateSpec`。
- search 的 `result_limit`，read/read-section 的 `content_truncated` / `scan_complete` output 事实。
- Host `TruncationManager` / framework `fetch_more` 及其安全校验。
- 真实 I/O、decode、unsupported format、invalid ref、file-not-found、permission、invalid-argument 错误。
- 五个 tool name、provider id/source ref、display name/tag 与 process serialization contract。

### 4.3 明确非目标

- Issue #177 的五工具 complete target value、remainder store、fetch-more 无损续读接线。
- 新的 input budget、quota、大小 warning、目录分页、文件 index、cache 或 durable cursor。
- Host/tool authorization 框架、`allowed_paths` 迁移、symlink/TOCTOU 新策略。
- Engine/Host/Service/UI/Fins contract、durable schema、EventLog、Memory、Compact、Trace 改造。
- 新 schema 兼容读取、旧 import 兼容、fallback、loose parsing 或默认值 shim。
- 修改五份 design truth、control doc、Issue、根用户工作流或 package config。

## 5. 当前与目标 production 调用链

### 5.1 当前真实生产路径

```text
tool_discovery.json provider spec
  -> dayu.tools.doc_provider.discover_tools
  -> parse allowed_paths + DocToolLimits
  -> build_doc_tool_definitions
  -> ToolDefinition.execution = ProcessBackedToolExecutionCapability
  -> parent ToolRuntime process capsule
  -> _DocProcessTargetFactory.build_process_target
  -> child _DocProcessTarget.__call__
  -> _execute_doc_business_value
  -> validate/project arguments
  -> _project_doc_paths (resolved allowed-root containment)
  -> _route_doc_business
  -> list/get-sections/search/read/read-section business helper
  -> BoundedSourceSnapshot / capped directory iterator
  -> raw JsonValue
  -> _project_tool_response_paths
  -> process completed/failed envelope
  -> parent ToolRuntime output truncation / accept barrier
  -> Engine tool result
```

`ToolDefinition.callable -> _invoke_doc_business -> asyncio.to_thread` 是直接调用测试与非生产 fallback；它与 process target 共享 `_execute_doc_business_value`，不是第二个业务 owner。

### 5.2 R01 目标路径

```text
tool_discovery.json
  -> doc_provider (allowed_paths + output limits only)
  -> five ToolDefinitions (same names/schema parameters/execution capability)
  -> process target or direct callable fallback
  -> one _execute_doc_business_value / _route_doc_business owner
  -> _project_doc_paths
  -> list/search: stable directory-entry iterator under the projected directory, no byte/entry cap
     get/read/search/section:
       with _source_snapshot(path, cancellation_token) as snapshot
         (_source_snapshot helper: LocalFileSource input -> unentered SourceSnapshot context-manager instance)
       -> active snapshot -> processor/raw reader
  -> complete input observation + existing bounded output value
  -> existing ToolTruncateSpec/ToolRuntime path
  -> accept barrier -> Engine
```

不变量：任何 source 长度都不会产生 size/budget terminal；任何授权目录 entry 数都不会产生 entry partial；只有现有 output limit/字符截断可以产生 output-side partial fact；取消不能伪造 complete。

## 6. Closed production/test/document allowlist

### 6.1 Umbrella production allowlist 保持不变

| umbrella 文件 | R01 exact disposition | 直接证据 |
|---|---|---|
| `dayu/documents/processors/bounded_source.py` | S1 删除，并在同一 slice 新增 `source_snapshot.py` | 移除 bound 后旧文件/类名不再表达 owner contract；umbrella 明确允许同 slice rename，且禁止兼容 re-export |
| `dayu/documents/processors/source_snapshot.py`（新增） | S1 新增 | `BoundedSourceSnapshot` 的 spool/cursor/cleanup 能力仍需要唯一 owner，只删除 limit，不删除 snapshot |
| `dayu/documents/processors/__init__.py` | 闭集内保留、预期无 diff | 当前 bounded helper 没有从 package `__init__` 导出；consumer 使用直接模块 import。新增 export 会无需求扩大 public API |
| `dayu/documents/__init__.py` | 闭集内保留、预期无 diff | 当前包根无 snapshot export；层级/包职责不变 |
| `dayu/tools/doc_tools.py` | S1 + S2 修改 | 五工具 schema、process target、路由、business helper、结果/error 的唯一 owner |
| `dayu/tools/doc_provider.py` | 闭集内保留、预期无 diff | 只解析 `allowed_paths` 与 output limits，不产生被删语义 |

上述是 production 闭集，不是全部文件都必须产生 diff。若 implementation 证明三个“预期无 diff”文件必须修改，先按 §15 停止并回 plan/controller；不得现场扩大 public surface。

### 6.2 允许测试、README 与 gate artifact

- S1 测试：`tests/documents/test_processors.py`、`tests/documents/test_import_boundary.py`、`tests/tools/test_doc_tools_provider.py`。
- S2 测试/文档：`tests/tools/test_doc_tools_provider.py`、`tests/README.md`。
- run-only、预期无 diff：`tests/tools/test_combined_tools_acceptance.py`、`tests/host/test_toolruntime_truncation_fetch_more.py`、`tests/host/test_toolruntime_effective_bundle.py`。
- README inspect-only、预期无 diff：`dayu/config/README.md`、根 `README.md`、`dayu/README.md`。
- LLM inventory inspect-only、预期无 diff：`dayu/config/prompts/base/tools.md`、`dayu/config/tool_discovery.json`。
- review/implementation/fix/re-review/completion artifact 只允许使用 umbrella §7.3 和 slug `r01-doc-complete-input` 规定的精确命名；它们不扩大 semantic production allowlist。
- 禁止修改 control/design/其它 production/test/README。

## 7. Umbrella R01 baseline 逐项映射

映射值只允许 `保留`、`基于直接证据细化`、`等价替换`。下表覆盖 umbrella §7.4、§7.5、§8、§21、§22 中每个 R01 baseline 项。

| umbrella baseline | exact mapping | R01 exact 项与证据 |
|---|---|---|
| R01 production allowlist | 保留 | §6.1 保持完整闭集；expected diff 收窄不改变 allowlist。三个 export/provider 文件无 owner 修改需求 |
| R01 两 slices | 保留并基于直接证据细化 | 仍为 S1 source byte semantics、S2 directory completeness；`DocResourceBudget` 同时携带两类 cap，S1 删除该 class/全链 `resource_budget` 后，`_route_doc_business` 只把既有 `_DOC_DIRECTORY_MAX_ENTRIES: int` 直接传给 list/search 的既有 `max_directory_entries: int` 参数；S2 删除该参数与常量。过渡不增加校验 helper、wrapper、budget 类型、配置、alias 或 public contract |
| S1 `bounded_source.py`/`*source*.py` | 保留 | 同 slice delete/add 为 `source_snapshot.py`，类改名 `SourceSnapshot`，不保留旧 import |
| S1 `doc_tools.py` source call path | 保留并细化 | 删除 `max_source_bytes` 全链、`SourceBudgetExceeded` mapping、oversized skip/result 字段/source-specific LLM text；process/direct 两入口共享同一业务路由 |
| S1 test command `-k 'source or read_file or section'` | 等价替换（加强） | 运行三份完整 owner/consumer test 文件，避免节点 rename 后 `-k` 漏测；另在 §10 列出 source/read/section exact assertions |
| S1 declared large / unknown large / >32 MiB assertions | 保留 | Source owner tests 覆盖 declared length 不拒绝、无声明长度完整复制；真实 >32 MiB 在 S2 共用 smoke 中从 discovery 进入 read/search，避免两个 slice 重复创建巨型 fixture |
| S1 cancellation/cleanup | 保留 | snapshot normal/exception/I/O/cancel cleanup + Doc runtime process cancel/late accept tests |
| S1 coverage include `*source*.py,doc_tools.py` | 基于直接证据细化 | changed production files 是新增 `source_snapshot.py` 与 `doc_tools.py`；两个文件分别 `--fail-under=80`，删除文件不伪造覆盖率 |
| S1 scan `DocResourceBudget|SourceBudgetExceeded|max_source_bytes|source_budget_exceeded` | 保留 | 对 `dayu tests README.md` 全局零命中；另扫 old module/class/prefix 与 LLM guidance |
| S1 README `documents无README；config/tests，根按文本` | 保留 | documents 无 README；S1 不先更新 README，S2 统一更新 tests README；config/root 无 rejected cap 文本 |
| S2 `doc_tools.py` directory path | 保留并细化 | 删除 entry cap/counter break，list/search 共用 stable cancellable iterator；list 删除死 partial fields，search 只保留 `result_limit` |
| S2 test command `-k 'list_files or search_files or schema or description'` | 等价替换（加强） | 运行完整 provider 文件 + exact large-input smoke + security/output-owner consumer tests，避免仅用名称过滤漏掉 process target/路径投影 |
| S2 >10k tail、创建顺序、>32 MiB searchable | 保留 | 一个实际 10,001+ entry / 33 MiB discovery→callable test，同时覆盖 list tail 与 search tail；独立 deterministic order test 覆盖不同创建顺序 |
| S2 allowed_paths/symlink/containment/result-limit | 保留 | 复跑现有 deny、nonexistent、symlink escape、result limit、read char partial、process cancellation tests |
| S2 coverage include `doc_tools.py` | 保留 | 完整 provider suite 采样后对 `doc_tools.py` 单文件 `>=80%`，不以总体覆盖率代替 |
| S2 scan `directory_entry_limit|source_limit|skipped_oversized_files|10_000` | 基于直接证据细化 | semantic identifiers 全局零命中；数值 literal 只在 Doc 路径扫描，因为 `dayu/documents/processors/html_extraction.py` 与 Web tests 有无关 `10_000`，不能把无关数值误判为 R01 residual |
| S2 README `config/tests/根` | 保留并形成 exact decision | `tests/README.md` 更新；`dayu/config/README.md` 只描述仍合法的 output limits，无 diff；根 README 不描述 Doc cap/error/workflow，无 diff |
| §8.5 >32 MiB / >10k / escaped/symlink smoke | 保留并自动化 | §11 固定 exact pytest node；同一 node 使用真实文件/目录与 discovery/callable，不用 monkeypatch 或 declared length 冒充；现有 escape/symlink nodes 同命令复跑 |
| §8.5 R03 handoff | 保留并细化 | §13 预先冻结逐文件 inventory；completion 必须写实际删除/保留/final disposition，不能只给 grep |
| §21 `allowed_paths`/resolve/symlink | 保留 | §10 security matrix + §12 security scan；任何失败 release-blocking |
| §21 Doc output truncation/cancellation | 保留 | current `ToolTruncateSpec`/Host `fetch_more` nodes + source/loop/process cancellation nodes；R01 不接 Issue #177 |
| §22 aggregate Doc smoke | 保留 | aggregate 时重新运行 §11 exact smoke；R01 completion 的一次通过不能替代 umbrella aggregate rerun |

没有 baseline 被静默遗漏，没有验证被降级。把 umbrella 的全局 `10_000` grep 改为 Doc scoped literal scan是基于当前无关命中的等价修正，不改变 semantic identifier 全局零残留要求。

## 8. Slice R01-S1 — 完整 SourceSnapshot 与 source-limit contract 删除

### 8.1 原子目标

一次提交形成完整 source owner 闭环：snapshot 不再拥有 byte policy，五工具 consumer 不再传 byte budget，source budget error/skip/result/LLM 文本同时消失。S1 结束时不得出现“新 snapshot 已完整读取、旧 consumer 仍传 max”或“错误码已删、search 仍静默 skip”的中间 schema。

目录 entry cap 在 S1 只保持原行为，并按以下唯一临时签名机械过渡：删除 `DocResourceBudget` 及 process target/factory/builder/definition、`_execute_doc_business_value`、`_route_doc_business` 全链的 `resource_budget` 参数；`_route_doc_business` 不接收替代 budget 参数，只在 list/search 分支把既有模块常量 `_DOC_DIRECTORY_MAX_ENTRIES: int` 直接传给两个业务函数原有的 `max_directory_entries: int` 参数。S2 随后同时删除该常量和这两个参数。S1 是可独立 review 的中间 slice，不是 R01 可交付终态；中间态不得新增正整数 assertion/校验 helper、wrapper、dataclass 或其它 budget 类型、配置、optional 参数、alias、兼容逻辑或 public contract。

### 8.2 Production 改动

1. 删除 `dayu/documents/processors/bounded_source.py`，新增 `source_snapshot.py`：
   - 模块/类/docstring 全部改成“完整快照”；
   - 删除 `SourceBudgetExceeded`、`max_bytes`、declared-length check、`remaining + 1`；
   - spool `max_size` 固定为 `_SPOOL_MEMORY_BYTES`，复制循环每次最多 `_COPY_CHUNK_BYTES` 直到 EOF；
   - materialized prefix 改为语义准确的 `dayu-doc-source-`；
   - active/error 文本不再出现 `bounded`；
   - 保留 independent reader、lock、seek、materialize、cleanup、cancel 行为。
2. `doc_tools.py`：
   - import `SourceSnapshot`，删除旧 import/exception；
   - 删除 `_DOC_SOURCE_MAX_BYTES` 与 `DocResourceBudget`；
   - `_DocProcessTarget` / `_DocProcessTargetFactory` / builder/definition、`_execute_doc_business_value`、`_route_doc_business` 全链删除 `resource_budget`，不增加替代 budget 参数；
   - `_route_doc_business` 在 S1 的 list/search 分支暂时把既有 `_DOC_DIRECTORY_MAX_ENTRIES: int` 直接传给 `_list_files_business` / `_search_files_business` 原有的 `max_directory_entries: int`；其它工具不接收 source max，且不为该固定常量新增 assertion、校验 helper、wrapper 或 budget 类型；
   - `get/search/read/read-section` 与 `_source_snapshot(path, token)` 的 signature 删除 `max_source_bytes`；
   - `_source_snapshot` 构造 `LocalFileSource` + `SourceSnapshot`；
   - 删除 `_execute_doc_business_value` 的 `SourceBudgetExceeded -> source_budget_exceeded` mapping；
   - search 删除 oversized catch、counter、`skipped_oversized_files`、`source_limit`；保留 `result_limit`/directory cap 到 S2；
   - search description 同步删除 source budget/较小文件引导，directory entry 文本留到 S2；
   - 所有改动/新增函数提供完整中文 docstring 和严格类型。

### 8.3 S1 允许文件

```text
dayu/documents/processors/bounded_source.py          # delete
dayu/documents/processors/source_snapshot.py         # add
dayu/tools/doc_tools.py
tests/documents/test_processors.py
tests/documents/test_import_boundary.py
tests/tools/test_doc_tools_provider.py
docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-implementation-s1-codex.md
```

任何其它 semantic file diff 立即 stop。review/fix artifacts 按统一 gate 命名另行允许。

### 8.4 S1 owner/consumer tests

- `tests/documents/test_processors.py`：
  - 旧 budget tests 改为 `SourceSnapshot` 完整 stream、declared length 不拒绝、active 后 exact size；
  - 同一 snapshot 两个 cursor 独立 seek/read；
  - processor 只消费 snapshot、不重开 source；
  - normal/consumer exception/source I/O/cancellation 都关闭 spool并删除 materialized file；
  - reuse 仍拒绝、close 仍幂等；删除非法 byte-limit test。
- `tests/documents/test_import_boundary.py`：
  - scan 必须包含 `processors/source_snapshot.py`；
  - 明确不再存在 `processors/bounded_source.py`；
  - forbidden-layer import 仍零命中。
- `tests/tools/test_doc_tools_provider.py`：
  - imports/type annotations 全部迁到 `SourceSnapshot`；
  - process target pickle round-trip 明确没有 `resource_budget`/Host live object；
  - 删除 `DocResourceBudget` validation test；
  - read/get-sections/read-section/search helper 不再接受 `max_source_bytes`；
  - 原 source-limit failure test 改为大 declared/实际 source 进入 processor/read，而不是异常；
  - search 旧 oversize-skip test 改为 source 进入 processor/line scan并返回命中，结果无 `skipped_oversized_files/source_limit`；
  - `read_file`/`read_file_section` `ToolTruncateSpec` 与 current partial fields 仍原样通过；
  - process/direct outcome、allowed path 与 cancellation tests 继续通过。

### 8.5 S1 命令

```bash
source .venv/bin/activate
pytest tests/documents/test_processors.py tests/documents/test_import_boundary.py tests/tools/test_doc_tools_provider.py -q

coverage run --data-file=workspace/tmp/.coverage-r01-s1 -m pytest \
  tests/documents/test_processors.py \
  tests/documents/test_import_boundary.py \
  tests/tools/test_doc_tools_provider.py -q
coverage report --data-file=workspace/tmp/.coverage-r01-s1 \
  --include='dayu/documents/processors/source_snapshot.py' --fail-under=80
coverage report --data-file=workspace/tmp/.coverage-r01-s1 \
  --include='dayu/tools/doc_tools.py' --fail-under=80
coverage json --data-file=workspace/tmp/.coverage-r01-s1 \
  -o workspace/tmp/coverage-r01-s1.json

python -m pyright
git diff --check
rg -n 'DocResourceBudget|SourceBudgetExceeded|max_source_bytes|source_budget_exceeded|skipped_oversized_files|source_limit' dayu tests README.md
rg -n 'bounded_source|BoundedSourceSnapshot|dayu-doc-bounded' dayu tests
```

两条 `rg` 预期无输出。coverage JSON 必须在 implementation artifact 中逐文件记录百分比；删除的 `bounded_source.py` 不要求伪造 coverage。

## 9. Slice R01-S2 — 完整目录遍历、LLM contract 收敛与 R01 closure

### 9.1 原子目标

一次提交删除 directory cap 的 producer、result 与 LLM-facing contract，并同时给出 deterministic/cancellable traversal、真实阈值 smoke、README decision 和 R03 handoff。S2 结束时，目录只可能因合法 output result limit 而停止；不能因 entry 数产生 partial。

### 9.2 Production 改动

1. 按 §8.1 封闭临时签名：删除 `_DOC_DIRECTORY_MAX_ENTRIES`、`_list_files_business` / `_search_files_business` 的 `max_directory_entries: int` 参数及对应 docstring/传递与 counter break；不保留 S1 过渡参数或新增替代抽象。
2. 新增模块级私有 deterministic iterator + sort-key helper，供 list/search 共用：
   - 非递归按 entry name casefold + 原名稳定排序；
   - 递归按相同规则 depth-first；
   - 与 Python 3.11 当前 `Path.rglob("*")` 一致，产出 directory symlink entry 但不递归进入其 target；这是现状保持，不是新安全修复；
   - file symlink 继续作为 entry 产出；list 保持 `is_file()` / `stat()` 的 directory-entry 语义，不做 per-entry resolve/containment；
   - 枚举/产出 entry 时观察 cancellation；
   - 不吞掉现有 I/O error，不增加 fallback。
3. `list_files`：
   - 遍历全部 entry，继续使用 bounded heap 只保存最小 `actual_limit` 个结果，避免返回 limit 失效；
   - `total` 始终是完整匹配数，`scanned_entries` 是完整观察数；
   - 删除 list `scan_complete/truncated_reason`；description 说明 `returned` 是首屏数量、`total` 是完整匹配数。
4. `search_files`：
   - 使用同一 iterator；实际内容读取前保留 candidate resolved containment，外部 file-symlink target 不读取；
   - 达到 `actual_limit` 时仍可停止并返回 `result_limit`；否则扫描到 EOF；
   - description 只解释 `result_limit` 与下一步，不出现 entry/source cap 或较小文件/目录引导。
5. 不改变 `DocToolLimits`、parameter `limit/maximum`、read output fields、truncate declaration、process capability 或 provider config。

### 9.3 S2 允许文件

```text
dayu/tools/doc_tools.py
tests/tools/test_doc_tools_provider.py
tests/README.md
docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-implementation-s2-codex.md
```

### 9.4 S2 owner/consumer tests

- list 超过旧 entry boundary 仍得到 exact `total` 和 tail pattern 命中；结果不含 list partial-only fields。
- search 唯一命中位于旧 boundary 之后仍可见；不含 removed fields/reasons。
- 两棵内容相同、创建顺序相反的目录，list records 与 search matches 顺序完全相同。
- directory symlink entry 不被递归；allowed-root 内指向 allowed-root 内文件的 file symlink 仍作为 list entry 返回，记录使用 symlink entry 的相对路径/名称，不把该 list 元数据行为宣称为 authorization。
- 指向 allowed-root 外文件的 file symlink 仍由 search 的 candidate resolve/containment 跳过，并由 direct read 的 `_project_doc_paths` 拒绝；不得通过给 list 新增 per-entry containment 来“统一”这三条行为。
- `result_limit` 仍使 search `scan_complete=false/truncated_reason=result_limit`；list `total > returned` 仍表达有界 output。
- schema descriptions 明确保留业务动作、输入、输出和合法 output limit，且 rejected tokens/guidance 零命中。
- existing allowed path、outside path、nonexistent、file-vs-directory、symlink escape、iteration cancellation、process cancel、read char partial 都继续通过。
- §11 真实大输入 smoke 加入本文件，默认 pytest 可执行，不打 skip/xfail，不用 monkeypatch 或伪 declared length。

### 9.5 S2 命令

```bash
source .venv/bin/activate
pytest tests/tools/test_doc_tools_provider.py -q
pytest \
  tests/tools/test_combined_tools_acceptance.py::test_combined_truncate_specs_and_fetch_more_owner \
  tests/host/test_toolruntime_effective_bundle.py::test_enabled_fetch_more_injects_schema_and_callable_when_truncation_enabled \
  tests/host/test_toolruntime_truncation_fetch_more.py::test_truncated_result_exposes_only_cursor_and_scope_token \
  tests/host/test_toolruntime_truncation_fetch_more.py::test_fetch_more_dispatches_as_normal_tool_and_is_single_use -q

coverage run --data-file=workspace/tmp/.coverage-r01-s2 -m pytest \
  tests/documents/test_processors.py \
  tests/documents/test_import_boundary.py \
  tests/tools/test_doc_tools_provider.py -q
coverage report --data-file=workspace/tmp/.coverage-r01-s2 \
  --include='dayu/tools/doc_tools.py' --fail-under=80
coverage json --data-file=workspace/tmp/.coverage-r01-s2 \
  -o workspace/tmp/coverage-r01-s2.json

python -m pyright
git diff --check
```

## 10. Owner/consumer regression matrix

| Contract | Owner test | Consumer/integration test | 通过信号 |
|---|---|---|---|
| Source 完整 snapshot | `tests/documents/test_processors.py` | provider read/get/search/section tests | declared/actual length不拒绝，processor可读完整 snapshot |
| independent cursor/cleanup | processor snapshot tests | Markdown/Docling fixture tests | 多 cursor 独立；所有 exit path 无临时资源残留 |
| list 完整目录事实 | provider list tests | real threshold smoke | >10k 后 tail 可见，`total` 精确，output仍有界 |
| search 完整输入 | provider search tests | real threshold smoke | >10k 后且 >32 MiB 文件尾 marker 命中，无 skip/size reason |
| deterministic traversal | reversed-creation-order owner test | list→read、search→section chaining | 两目录返回次序一致，路径可直接消费 |
| allowed_paths/containment | deny/nonexistent/type tests | process target denied test | root 外仍 permission denied，业务函数未运行 |
| directory/file symlink traversal | directory-symlink no-recursion + allowed-root 内 file-symlink list-entry tests | list traversal regression | 保持 Python 3.11 现状：不递归 directory symlink；list 按 entry 返回 file symlink，不新增 per-entry containment 或统一授权语义 |
| search/direct-read symlink containment | search symlink escape + direct-read denied tests | threshold smoke 的 outside file-symlink case | search 在候选读取边界跳过外部 target，direct read 在输入投影边界拒绝，root 外正文零泄漏/零命中 |
| cancellation | snapshot/loop tests | process-backed cancel + no late accept | 取消快速收口，不伪造 complete，不接受 late result |
| output limits | list/search/result/read/section tests | ToolRuntime truncate/fetch_more tests | `result_limit`/char partial 保留，framework owner不变 |
| LLM-facing | exact schema description assertions | combined discovery schema | 无 rejected cap/recovery guidance，剩余字段自解释 |

不得用 mock 构造旧 budget 类型；测试必须跟随新 owner signature。真实大输入 smoke 不能只断言函数没有抛异常，必须断言 tail 业务事实和 removed-field absence。

## 11. >32 MiB 与 >10k 真实 smoke

在 `tests/tools/test_doc_tools_provider.py` 新增固定 node：

```text
test_doc_complete_input_real_smoke_above_legacy_thresholds
```

test contract：

1. 在 `tmp_path/allowed` 创建 10,001 个按稳定名称排序的小 `.txt` 文件；按 1 MiB ASCII chunk 循环写一个大于 33 MiB 的 `zzzz-large-tail.txt`，唯一 marker 位于文件尾，避免用大内存单次构造或 sparse/declared-length 冒充真实读取。
2. 用真实 `ToolsDiscoveryProviderSpec -> doc_provider.discover_tools -> ToolDefinition.callable` 发现五工具，`allowed_paths` 只含该 root。
3. 调 `list_files(pattern="zzzz-large-tail.txt", recursive=True)`：必须返回该 tail 文件，`total=1`，`scanned_entries>10_000`，且无 `directory_entry_limit`/list partial-only fields。
4. 调 `read_file`：必须成功并保持现有 bounded output/`ToolTruncateSpec` 声明；不能返回 `source_budget_exceeded`。
5. 调 `search_files(query=<tail marker>)`：必须命中大文件，`scanned_entries>10_000`，无 `skipped_oversized_files/source_limit/directory_entry_limit`。
6. 在 allowed root 内放置指向 root 外 marker 文件的 file symlink；search 不得读到 outside marker，direct read 的 `_project_doc_paths` resolved containment 仍拒绝。这个 smoke 只证明 search/direct-read 的内容读取边界，不给 list 增加 per-entry containment，也不把三者包装成统一 authorization contract。
7. test cleanup 完全依赖 `tmp_path`，仓库不新增二进制/大 fixture。

单独 smoke 命令：

```bash
source .venv/bin/activate
pytest \
  tests/tools/test_doc_tools_provider.py::test_doc_complete_input_real_smoke_above_legacy_thresholds \
  tests/tools/test_doc_tools_provider.py::test_disallowed_path_returns_failed_outcome \
  tests/tools/test_doc_tools_provider.py::test_search_files_does_not_read_symlink_escape -q
```

本 node 同时是 R01 completion 与 umbrella §22 aggregate Doc smoke 的可重复入口；aggregate 必须再次运行。若真实文件系统无法在合理测试环境创建这些输入，R01 blocked，不能把阈值缩小或 monkeypatch 旧常量后宣称真实 smoke。

## 12. Diff/source/LLM/security/Issue-177 scans

### 12.1 Allowed-file diff

每个 slice 记录 controller accepted-plan commit / previous accepted slice SHA 为 `<slice-base>`，执行：

```bash
git diff --name-only <slice-base> --
git diff --check <slice-base> --
```

逐行比对 §8.3/§9.3。R01 completion 再以 accepted-plan commit 为 base 比对 §6 完整闭集；临时 coverage、large fixture、spool、materialized file、`__pycache__`、secret 或 workspace config 不得进入 diff/status。

### 12.2 删除语义/source scan

```bash
rg -n 'DocResourceBudget|SourceBudgetExceeded|max_source_bytes|max_directory_entries|source_budget_exceeded|directory_entry_limit|source_limit|skipped_oversized_files' \
  dayu tests README.md

rg -n 'bounded_source|BoundedSourceSnapshot|dayu-doc-bounded' dayu tests

rg -n '32[[:space:]]*(MiB|MB)|32[[:space:]]*\*[[:space:]]*1024[[:space:]]*\*[[:space:]]*1024|10_000|10,000' \
  dayu/tools/doc_tools.py \
  dayu/documents/processors \
  tests/documents \
  tests/tools/test_doc_tools_provider.py \
  dayu/config/README.md tests/README.md README.md
```

全部预期无输出。数值 scan 故意限定 Doc surface；全局 semantic identifier scan 仍不可限定。

#### 12.2.1 list partial-only 字段传播分类 scan

`scan_complete` / `truncated_reason` 仍分别属于 search `result_limit` 与 read/read-section 字符输出事实，不能全局删除或把同名字段视为同一 owner。S2 与 completion 必须执行生产全范围 source scan，并对每个命中按所在 symbol/tool/owner 分类：

```bash
rg -n --glob '*.py' 'scan_complete|truncated_reason' dayu

rg -n 'scan_complete|truncated_reason|directory_entry_limit' \
  tests/tools/test_doc_tools_provider.py tests/README.md
```

第一条允许命中且必须在 S2 implementation/completion artifact 逐项记录 `path:line / symbol / tool / semantic owner / disposition`。合法分类只有 search 的 `result_limit` schema/result producer 与 read/read-section 的字符输出 schema/result producer；若出现 list producer、list schema description、读取 list 字段的任何生产 consumer，或无法判定 owner 的命中，立即 stop。第二条中 list 相关测试只允许“字段不存在”的 negative assertion，不得保留 partial 值/reason assertion；`tests/README.md` 的 list contract 不得再描述这两个字段或 directory partial。结合 §12.2 第一条 semantic identifier 零命中，最终必须证明 list producer、生产 consumer、schema/test assertion 与 README 均无 `directory_entry_limit` 或 list entry-partial 残留，同时不误删 search/read 的合法同名字段。

### 12.3 LLM-facing scan

```bash
rg -n 'directory_entry_limit|source_limit|skipped_oversized_files|source_budget_exceeded|较小文件|拆分文件|缩小文件范围|缩小目录' \
  dayu/tools/doc_tools.py dayu/config/prompts tests/tools/test_doc_tools_provider.py
```

预期无输出。`dayu/config/prompts/base/tools.md` 的“大文件先看章节”不命中上述 rejected guidance；它是 output/导航效率建议，按 §13 保留，不得机械删除。

### 12.4 Output owner / Issue #177 non-implementation scan

```bash
rg -n 'ToolTruncateSpec|truncate=_text_content_truncate' \
  dayu/tools/doc_tools.py tests/tools/test_doc_tools_provider.py
rg -n 'TruncationManager|FetchMoreToolCallable|fetch_more' \
  dayu/tools/doc_tools.py dayu/tools/doc_provider.py
git diff --name-only <r01-accepted-plan-base> -- \
  dayu/host dayu/runtime dayu/contracts dayu/config/tool_discovery.json
```

第一条必须命中 current read/read-section declaration/tests；后两条预期无输出。它们与 §9.5 的 consumer tests共同证明“保留既有 output owner，但未接 Issue #177”。

### 12.5 Security/cancellation scan

```bash
rg -n 'allowed_paths|_project_doc_paths|_resolve_search_files_candidate|_raise_if_doc_cancelled|ProcessBackedToolExecutionCapability' \
  dayu/tools/doc_provider.py dayu/tools/doc_tools.py
```

这些 owner 必须仍有预期命中，并由 §10 tests 证明行为；有名字不等于通过，测试失败仍是 release blocker。

## 13. README 决策与 R01 -> R03 逐文件 LLM-facing handoff

### 13.1 README trigger decision

| README | decision | 证据 |
|---|---|---|
| `tests/README.md` | S2 更新 | tests owner contract 从 budget/partial/oversize skip 迁到 complete snapshot/full traversal/real threshold smoke，命中 tests trigger |
| `dayu/config/README.md` | 无需更新 | 只描述 `allowed_paths` 和五个仍合法的 Doc output limits，没有 32 MiB、10,000、source/entry partial/error 文本 |
| 根 `README.md` | 无需更新 | 不描述 Doc provider cap/error 或 Doc 用户工作流；R01 不改变安装、CLI/Web/WeChat 入口、命令参数、默认输出、日志或 workspace 位置 |
| `dayu/README.md` | 无需更新 | 分层与装配不变；`dayu.documents` 与 ToolRuntime owner 边界未改变 |
| `dayu/engine/README.md` / `dayu/host/README.md` / `dayu/fins/README.md` | 无需更新 | 未修改对应层 production contract；Host/Engine/Fins 只是保留性验证 |

S2 修改 `tests/README.md` 前先重读其当前写作职责；只改 Documents/Tools 分层两处，不扩写实现过程或未来 Issue #177。

### 13.2 Completion 必须交给 R03 的逐文件 inventory

R01 completion artifact 必须包含下表的最终逐文件记录，列出 `file / exact source / LLM-facing? / owner / delete|rewrite|retain / final text or assertion / evidence`。本文先冻结最低 inventory：

| 文件 | source | disposition | R03 handoff 要求 |
|---|---|---|---|
| `dayu/tools/doc_tools.py` | 五个 `ToolFunctionSchema.description` | list/search 改写；get/read/read-section 保留或只做必要同源措辞调整 | 逐工具贴出最终 description 摘要；明确只删除 input cap/partial 引导，保留 output limit/章节导航 |
| `dayu/tools/doc_tools.py` | 五工具 parameter property descriptions | 保留 | 逐工具/参数记录无 rejected token；`limit/maximum` 是 output/argument contract |
| `dayu/tools/doc_tools.py` | `_DocBusinessFailure` message/hint 与 `_invoke_doc_business` errors | 删除 `source_budget_exceeded` 及拆分/较小文件 hint；保留 invalid/path/not-found/I/O/cancel/error | 按错误码列出 owner 与模型可行动含义；不暴露 Host治理词 |
| `dayu/tools/doc_tools.py` | list/search/read result field names | 删除 entry/source-only fields；保留 output partial fields | 列出最终 result keys；说明 search `result_limit` 与 read `content_truncated` 仍合法 |
| `dayu/config/prompts/base/tools.md` | Doc 工具路径 A/B 与“大文件先看章节” | 保留、无 diff | 说明这是导航/output-efficiency guidance，不声称大文件会失败/跳过，不得让 R03 误删 |
| `tests/tools/test_doc_tools_provider.py` | schema/description 与真实 LLM tool-call fixture | 改写 assertions | 记录 absence assertions、remaining self-contained field assertions 与真实 smoke prompt/arguments |
| `tests/tools/test_combined_tools_acceptance.py` | combined tool schema/effective bundle fixture | 保留、无 diff | 记录 `ToolTruncateSpec` + framework `fetch_more` owner test，明确不代表 Issue #177 complete wiring |
| `dayu/tools/doc_provider.py` | provider config errors | `not-LLM-facing-with-evidence`、无 diff | config discovery fail-fast 给 operator/composition，不进入 model tool schema/result |
| `dayu/config/tool_discovery.json` | Doc provider raw config | `not-LLM-facing-with-evidence`、无 diff | ConfigLoader/provider 输入，不是 model prompt；五 limits 继续存在且只表示 output/argument control |
| `dayu/config/README.md` / `tests/README.md` / 根 README | 开发/用户文档 | 非 LLM runtime input | 记录 README decision，不把开发文本混作 prompt source |

completion 不能只写“grep 零命中”。如果 implementation/source scan 发现额外真实 Doc LLM-facing 文件，必须在同一 R01 owner/allowlist 内才能处理；否则停止回 controller。R03 必须消费该 completion inventory，不得回改 R01 owner、重复发明删除规则或把保留的 output guidance 当 input cap 删除。

## 14. Baseline failure registry、全量验证与 completion

### 14.1 Baseline registry

当前 control 记录的明确 broad-probe residual 是两个 `tests/host/test_dispatch_scheduler.py` compaction previous-view failure，基线 SHA 为 `0bc75a5b`；它与 R01 Doc files/source propagation 无交集。R01 的 mandatory tests 不包含这两个 node，因此不得主动把它们写成 R01 pass/fail 或新建 registry。

若 full pyright/额外 broad pytest 命中失败，只能按 umbrella §7.2 的六项指纹（命令、node、错误类型、首稳定栈帧/rule、文本、基线 SHA）证明 inherited；数量/位置/指纹变化或进入 R01 changed owner 一律视为新增/扩散并 stop。

### 14.2 R01 completion 验证

```bash
source .venv/bin/activate
pytest tests/documents tests/tools/test_doc_tools_provider.py -q
pytest \
  tests/tools/test_combined_tools_acceptance.py::test_combined_truncate_specs_and_fetch_more_owner \
  tests/tools/test_combined_tools_acceptance.py::test_toolruntime_executes_representative_provider_tools_and_accepts_facts \
  tests/host/test_toolruntime_effective_bundle.py::test_enabled_fetch_more_injects_schema_and_callable_when_truncation_enabled \
  tests/host/test_toolruntime_truncation_fetch_more.py::test_truncated_result_exposes_only_cursor_and_scope_token \
  tests/host/test_toolruntime_truncation_fetch_more.py::test_fetch_more_dispatches_as_normal_tool_and_is_single_use -q
pytest \
  tests/tools/test_doc_tools_provider.py::test_doc_complete_input_real_smoke_above_legacy_thresholds \
  tests/tools/test_doc_tools_provider.py::test_disallowed_path_returns_failed_outcome \
  tests/tools/test_doc_tools_provider.py::test_search_files_does_not_read_symlink_escape -q

coverage run --data-file=workspace/tmp/.coverage-r01-final -m pytest \
  tests/documents tests/tools/test_doc_tools_provider.py -q
coverage report --data-file=workspace/tmp/.coverage-r01-final \
  --include='dayu/documents/processors/source_snapshot.py' --fail-under=80
coverage report --data-file=workspace/tmp/.coverage-r01-final \
  --include='dayu/tools/doc_tools.py' --fail-under=80
coverage json --data-file=workspace/tmp/.coverage-r01-final \
  -o workspace/tmp/coverage-r01-final.json

python -m pyright
git diff --check
```

随后执行 §12 全部 scans、README decision、allowed-file audit。coverage report 必须逐 changed production file `>=80%`；总体 `>=80%` 不能掩盖单文件不足。若 review fix 新增/改变 production 行，重新运行完整矩阵与逐文件 coverage。

### 14.3 Completion artifact

最终 `docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-completion.md` 至少记录：

- 状态 `complete|blocked`、umbrella/R01 身份；
- accepted umbrella SHA、accepted R01 plan commit、slice bases/accepted commits；
- exact owner contract 与真实调用链；
- 删除/保留 contract；
- 每条 test 命令与结果；
- 每个 changed production file coverage；
- full pyright、diff/scan、baseline delta；
- >32 MiB / >10k / escaped/symlink smoke 实际数值与结果；
- README decision；
- §13.2 逐文件 R03 handoff；
- 双路 plan/code review、fix、完整 re-review、controller adjudication 与所有 severity finding 最终状态；
- Issue #177 non-implementation 证据；
- residual/stop/remaining questions 与下一依赖 R02（同时把 inventory 交 R03 controller 保存）。

AgentCodex/reviewer不得创建 accepted commit、改 control 或开启 R02/R03；这些 gate 动作只由 controller 执行。

## 15. Stop conditions

任一条件命中立即停止并回 controller，不用 fallback、compat shim、默认值或扩大 residual 继续：

1. 当前实现证明完整 source owner 不在 `dayu.documents.processors`，或目录/result/schema owner 不在 `dayu.tools.doc_tools`。
2. 需要 umbrella §7.4 R01 production 闭集之外的生产文件，尤其 Host/Engine/runtime/contracts/config/Fins/UI/Service。
3. 必须改变 `allowed_paths`、containment/symlink policy、process cancellation/fencing、五个 tool name 或 provider identity 才能删除 cap。
4. 必须接入/修改 `TruncationManager`、remainder store、cursor/scope token、framework `fetch_more` 或五工具完整 output continuation；转 Issue #177，不在 R01 做半接线。
5. 实现发现 controller accepted contract要求保留某种 input hard-fail/entry partial，或设计真源与 controller discussion 实质冲突。
6. S1/S2 之间只能通过临时 wrapper/re-export/alias/optional budget 参数才能保持可运行；应重新切片并回 plan review，不保留兼容 seam。
7. retained security/cancellation/output-owner test 失败、真实 smoke partial/skip、coverage 任一 changed production file `<80%`、full pyright 新增/扩散、allowed-file 外 diff。
8. 新 LLM-facing source 位于 R01 allowlist 外，或无法确定其语义 owner/disposition。
9. 任一 accepted plan/code-review finding 未闭合，或 `needs-more-evidence` 尚未裁决。

## 16. Residual risks、alternatives 与 remaining questions

### 16.1 Residual risks（不降低 R01 accepted contract）

| residual | 当前处理 | owner/destination |
|---|---|---|
| 极大本地 source/目录可能消耗磁盘、时间或 inode | 完整 spool、process boundary、cooperative/parent cancellation 与 output limit；不恢复未经裁决 hard-fail | Issue #177 / 后续输入治理设计，必须先写 owner/可见错误/配置语义 |
| 五工具 output/remainder 没有全部通过 `TruncationManager` 无损续读 | 保留 current spec/framework owner，不扩张 R01 | GitHub Issue #177 |
| search 达到合法 result limit 后不会扫描剩余 entry，因此 `total_matches` 只是返回数 | schema 自解释为 output result limit；不伪造完整 total | Issue #177 若未来以 complete result + fetch_more 重构 |
| symlink/TOCTOU 是既有局部防御边界 | 保持三条不同 owner 行为：directory symlink 不递归、list file symlink 仅按 entry metadata 且无 per-entry containment、search/direct read 分别在候选读取/输入投影边界 resolve/containment；R01 不统一权限或重设计 symlink policy | 后续独立 tool authorization/filesystem hardening WU，仅有直接证据时立项 |

### 16.2 被拒绝的替代方案

- 把 32 MiB/10,000 改成更大数字或可配置：仍把无需求 cap 作为产品事实，root cause 未消失。
- 在 schema/README 隐藏错误但保留 producer cap：下游补偿，事实仍丢失。
- 流式跳过 snapshot 直接让 processor 重开文件：破坏一次性 Source、独立 cursor、cleanup owner。
- 在 R01 顺手完成 Issue #177：跨入 Host/ToolRuntime output continuation owner，扩大 allowlist/测试/风险。
- 保留旧 class/module alias：违反无兼容代码与唯一 owner。
- 为目录遍历引入 index/cache/pagination service：当前没有需求，增加状态与失效语义。

### 16.3 Remaining questions

**无 blocking product/owner/dependency/allowlist question，也无待 implementation agent 自行裁决的 remaining question。**

controller accepted 的四项 plan finding 已分别冻结为可复核 contract：§3.2、§4.2、§9.2、§9.4、§10 与 §11 明确 Python 3.11 directory/file symlink、list/search/direct-read 的不同 owner 行为；§7、§8.1、§8.2 与 §9.2 封闭 S1→S2 临时签名；§12.2.1 给出生产范围逐命中分类 scan；§5.2 区分 `_source_snapshot` helper、`LocalFileSource` 输入与 `SourceSnapshot` context-manager type。完整 re-review 若给出直接反证，按统一 finding gate 处理；在 controller 接受修后 plan 前不 implementation。
