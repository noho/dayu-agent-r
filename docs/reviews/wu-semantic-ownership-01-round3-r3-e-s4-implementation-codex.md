# R3-E Slice S4 Implementation Artifact（AgentCodex）

## 1. 结论与 gate 边界

状态：**COMPLETE（S4 implementation only）**。

本轮按已接受计划 `docs/host/wu-semantic-ownership-01-round3-r3-e-web-doc-egress-resource-plan.md` 的 Slice 4 / §6.5，完成 Documents source/read/list/search 预预算与 partial/resource outcome。当前 owner 闭环为：

`DocToolLimits / DocResourceBudget -> bounded Source / directory iterator -> read / list / search producer -> self-describing partial/resource outcome`。

本轮没有 commit、push，也没有进入 code review。没有修改 Fins、S5、aggregate 或 final closeout；没有实现 tool-security、file-authority、symlink race policy 或 generic capability framework。

## 2. Root cause 与 semantic owner 判断

修改动机成立，且根因不在下游 truncate 展示层：

- 旧 `read_file` 对每个候选编码调用 `readlines()`，先完整物化文件，再由 Host `ToolTruncateSpec` 处理返回文本；因此 `read_file_max_chars` 不是 producer 的业务输入，单行超长也没有读取前预算。
- 旧 `search_files` 会让 processor 从原路径重新打开来源，raw fallback 又调用 `read()` / `split()` 完整物化；source byte cap 无法在 processor/raw full read 之前成立。
- 旧 `list_files` 先把整棵目录树累积到 list，再排序和截取；result limit 不能限制 directory scan / accumulator。
- 旧 success payload 缺少 `scan_complete`、unknown total 与稳定 reason，资源跳过可能被误读为“完整扫描但没有命中”。

唯一 owner 裁决：

- `dayu.documents.processors.bounded_source` 只拥有层中立的 Source 字节快照、typed byte failure 与系统临时资源 lifecycle；它不理解工具名、allowed roots 或 LLM 输出。
- `dayu.tools.doc_tools` 拥有 provider result/character limits、内部不可配置资源 ceiling、路径 authority、processor/raw 选择、partial/failure 字段和 LLM-facing 说明。
- `_doc_processor_factory.create_doc_file_processor` 只接收调用方已经治理的 `Source`，不再自行从路径创建并重开未受限来源。

## 3. Changed files 与 owner evidence

| 文件 | semantic owner / 实现内容 |
| --- | --- |
| `dayu/documents/processors/bounded_source.py` | 新增 `BoundedSourceSnapshot` 与 `SourceBudgetExceeded`。从同一次 `Source.open()` 按 64 KiB chunk 复制到有界 `SpooledTemporaryFile`；声明长度只可早拒绝，实读第 `limit+1` byte typed fail；context 拥有正常、Python exception、协作取消与 resource failure cleanup。需路径时只在系统 `TMPDIR` 发布并复用一个有界临时文件。 |
| `dayu/documents/processors/_doc_processor_factory.py` | 工厂改为接收 `Source`；基于 Source URI/media type 选择 processor，processor constructor 不再由工厂重开原路径。没有 compatibility wrapper/re-export。 |
| `dayu/tools/doc_tools.py` | 新增 frozen `DocResourceBudget(32 MiB, 10_000 entries)` 并由 definition builder 创建、显式随 process target 传递；实现 bounded list heap、bounded raw decoder/line scanner、bounded search line window、processor snapshot 接入、source/result/directory partial 字段，以及 `read_file_section` producer 字符 cap。 |
| `tests/documents/test_processors.py` | 覆盖 declared-small/actual-large、declared early reject、exact limit、limit+1、processor snapshot、normal/exception/cancel/resource cleanup、单物化路径复用与非法预算。 |
| `tests/documents/test_import_boundary.py` | 显式确认 import boundary 扫描覆盖 `processors/bounded_source.py`；继续禁止 tools/Host/Engine/Service/UI/Fins 依赖。 |
| `tests/tools/test_doc_tools_provider.py` | 覆盖 raw long line、多编码/range、目录 entry/result cap、固定 heap 排序、raw late query、processor-supported oversize、累计 match cap、partial fields、LLM-facing 描述、direct/process 同源与取消窗口。 |
| `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s4-implementation-codex.md` | 本 implementation handoff artifact。 |

未修改 `source.py`、`local_file_source.py` 或三个 processor constructor：现有 processor 的 `materialize()` 调用由 bounded snapshot 在系统 temp 上满足，不需要扩大 processor/Fins contract。

## 4. Contract closure

### 4.1 Bounded Source lifecycle

- `BoundedSourceSnapshot` 读取内容时只依赖 `Source.open()`；`content_length` 只用于可选早拒绝，declared-small/actual-large 测试证明最终裁决仍来自同一实际流。
- 实读循环每次最多请求当前剩余额度加一个 probe byte；精确等于 limit 成功，第 `limit+1` byte 抛 `SourceBudgetExceeded(source_uri, limit_bytes, observed_bytes)`。
- snapshot 提供独立只读游标；processor 需要路径时，snapshot 在系统临时目录创建单一有界 materialized file，重复 `materialize()` 复用同一路径。
- context 正常退出、consumer Python exception、协作取消和 Source/resource exception 均清理 spool 与命名临时文件；snapshot 不可复用。
- 不承诺 SIGKILL/主机崩溃执行 Python cleanup。由于单 snapshot 只发布一个命名文件，可能残留的命名 temp 内容受 `max_source_bytes` 限制；依赖系统 temp lifecycle，未来如需 durable janitor 应进入独立 Documents temp-artifact cleanup WU。

### 4.2 Doc resource/character owners

- `DocResourceBudget` 字段拒绝 bool、零与负数；生产实例只在 `build_doc_tool_definitions` 内按冻结默认值创建，provider config 没有放宽入口，并显式进入 pickle-safe process target。
- `read_file_max_chars` 与 `read_file_section_max_chars` 除保留 Host `ToolTruncateSpec` 防线外，已同时传入 business producer。
- `SourceBudgetExceeded` 在 tool owner 投影为 `source_budget_exceeded` failure；search 的单文件 source 超限则按冻结 contract 计入 `skipped_oversized_files` 与 `source_limit` partial，不进入 processor/raw fallback。

### 4.3 `read_file`

- raw reader 使用 incremental decoder，按 `utf-8 -> gbk -> latin1 -> cp1252` 尝试；不调用 `read()`/`readlines()` 整文件文本 API。
- 行范围外内容只统计行元数据，不进入 result accumulator；单个无换行长行仍最多累积 `max_chars+1` probe。
- success 固定返回 `file_path`、`content`、`returned_chars`、`content_truncated`、`scan_complete`、`total_lines`；请求范围时额外返回二元整数 `line_range`。
- 只有扫描到 EOF 时 `scan_complete=true` 且 `total_lines` 为精确整数；字符 cap 命中时 `scan_complete=false`、`total_lines=null`，不伪造总行数。

### 4.4 `list_files`

- directory iterator 最多观察 `max_directory_entries`，result accumulator 使用固定大小反向 heap 保留确定性最小排序结果，不构造全 tree file list。
- 完整扫描时返回精确 `total`、`scan_complete=true`、`truncated_reason=null`；entry cap 命中时返回已有 bounded 结果、`total=null`、`scan_complete=false`、`truncated_reason=directory_entry_limit`。
- result limit 与 directory entry limit 分离：小目录即使仅返回前 N 项，仍完成扫描并给出精确 total。

### 4.5 `search_files`

- 同时计数 directory entries、单 Source bytes 与累计 matches；processor factory 只接收当前 context 内的 `BoundedSourceSnapshot`。
- raw fallback 使用 chunk decoder + 单行尾窗，能够在无换行长行尾部发现 query；`snippet` / `matched_line_content` 保持 300 字符有界。
- processor 投影最多 remaining hits；累计 result cap 立即停止并返回 `result_limit`。
- success 固定返回 `query`、`directory`、`matches`、`total_matches`（仅本次已返回数）、`scanned_entries`、`skipped_oversized_files`、`scan_complete`、`truncated_reason`。
- reason 封闭为 `result_limit` / `directory_entry_limit` / `source_limit` / `null`；oversize skip 不再伪装为完整无命中。

### 4.6 LLM-facing contract

`list_files`、`search_files`、`read_file` 当前 tool description 自足说明新增字段、unknown total/partial 语义与下一步动作；`read_file_section` 同步说明 producer 字符 partial。文本不要求模型理解 Python 类型名或内部模块名。

## 5. Tests 与 validation results

| 命令 | 结果 |
| --- | --- |
| `source .venv/bin/activate && pytest tests/documents/test_processors.py tests/documents/test_import_boundary.py -q` | PASS：17 passed。 |
| `source .venv/bin/activate && pytest tests/tools/test_doc_tools_provider.py -q -k "list_files or read_file or search_files or limit or bounded or cancellation"` | PASS：37 passed，29 deselected。 |
| `source .venv/bin/activate && pytest tests/documents tests/tools/test_doc_tools_provider.py -q` | PASS：83 passed。 |
| `source .venv/bin/activate && pytest tests/documents tests/tools/test_doc_tools_provider.py -q --cov=dayu.documents.processors.bounded_source --cov=dayu.tools.doc_tools --cov-report=term-missing` | **validation tooling failure，exit 2**：coverage 7.13 按 dotted source 定位新模块时会临时导入后卸载 eager `dayu.documents.processors` package；测试 collection 再次加载 pandas/NumPy 原生扩展时，当前环境报 `ImportError: cannot load module more than once per process`。没有越界修改未授权 `processors/__init__.py` 规避。 |
| `source .venv/bin/activate && coverage run -m pytest tests/documents tests/tools/test_doc_tools_provider.py -q` | 等价、无 dotted-source 预导入副作用的 coverage run PASS：83 passed。 |
| `source .venv/bin/activate && coverage report --include='dayu/documents/processors/bounded_source.py,dayu/tools/doc_tools.py' -m` | `bounded_source.py`：163 statements、19 missing、**88%**；`doc_tools.py`：790 statements、154 missing、**81%**；总计 82%。新增 owner 模块满足 >=80% 门槛。 |
| `source .venv/bin/activate && pyright` | PASS：0 errors，0 warnings，0 informations；仅有 pyright 可升级提示。 |
| `git diff --check` | PASS（artifact 写入后再次执行）。 |

指定 coverage invocation 的失败发生在测试 collection 前的 coverage source discovery，不是产品代码或测试断言失败；同一最终测试集合在普通 pytest 与 coverage-run 下均为 83 passed，且两个被测文件均达到 80% 以上。该工具链 residual 原样保留，不宣称精确 invocation 已通过。

## 6. README decision

测试改动触发了 `tests/README.md` 职责检查。目标 README 面向测试维护者记录当前测试分层，S4 行为属于其 reader boundary；但 accepted S4 plan 明确规定只有 S1-S4 行为全部 accepted 后才更新该 README。当前 gate 仍是 implementation、尚未 code review/accepted，因此本轮**不修改 `tests/README.md`**，避免提前写入未接受 contract。后续 aggregate/accepted bookkeeping 再统一更新。

没有安装、初始化、正式 CLI/Web/WeChat 入口、工作区文件位置或分层装配变化，不触发根 `README.md` / `dayu/README.md`；没有修改 Engine、Host、Fins、Config 生产目录，也不触发其 README。

## 7. Residual risks（分类）

| 分类 | residual | owner / destination | 当前裁决 |
| --- | --- | --- | --- |
| accepted operational limitation | SIGKILL/主机崩溃不保证 Python context cleanup；可能留下一个至多 `max_source_bytes` 的系统命名 temp。 | `dayu.documents.processors.bounded_source`；未来如要求 durable reconciliation，进入独立 Documents temp-artifact cleanup WU。 | S4 只承诺正常/异常/协作取消/resource failure cleanup，不作虚假 SIGKILL 保证。 |
| accepted bounded-complexity limitation | 32 MiB 输入 ceiling 限制原始字节，但 Markdown/HTML/Docling parser 的内存表示可能高于输入大小。 | 各通用 Documents processor；后续 processor complexity/per-format budget WU。 | 本轮确保 processor 构造前 byte cap，不扩张为通用资源框架。 |
| assigned authority residual | 路径校验到实际 `open()` 之间仍可能发生 symlink/rename TOCTOU。 | 后续 file-authority/symlink-race WU。 | 当前只保证最终被打开的同一 handle 受 byte cap；S4 不实现 file authority/security framework。 |
| accepted partial semantics | directory entry cap 命中时 total 必然未知，search source skip 时也不能证明全目录无命中。 | `dayu.tools.doc_tools` partial fields。 | 通过 `scan_complete=false`、`total=null`/skipped count 与稳定 reason 明示，不伪造完整结果。 |
| validation tooling residual | pytest-cov dotted source 与 eager processors package/NumPy 在当前环境发生同进程重复加载。 | coverage invocation/toolchain，不属于 S4 semantic owner。 | 保留精确失败证据；等价 coverage 证明 88%/81%。不修改非白名单 package initializer。 |

没有未分类的 product blocker；Fins processor public contract 未改变。

## 8. Explicit exclusions / handoff

- 无 `dayu.fins` 修改，无 Fins processor public contract/shim。
- 无 tool-security、upload allowlist、file-authority、symlink-safe upload、SSRF/TLS policy 或 generic capability framework。
- 无 S5、aggregate、control bookkeeping 或 final closeout。
- 未进入 code review；下一 gate 由 controller 决定。
- 无 commit、push。
