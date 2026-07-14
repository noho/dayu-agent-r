# WU-SEMANTIC-OWNERSHIP-01 / R01-S1 Implementation — 完整 SourceSnapshot 与 source-byte-limit contract 删除

## 1. Gate 身份、范围与结论

- **umbrella WU**：既有 `WU-SEMANTIC-OWNERSHIP-01`。
- **内部 remediation sub-WU**：`R01 Doc complete input`；不是新 WU。
- **slice**：accepted-plan Slice `R01-S1`。
- **accepted plan commit**：`54e352319c7d5fd1306f1da6a6e5f4c2cb983669`（`gateflow: accept R01 doc complete input plan`）。
- **slice base / 当前控制 HEAD**：`1b4e5d33c9c2980b314f66c66ffe31b57c90fefb`（`docs: enter R01 source snapshot implementation`）。`54e35231..1b4e5d33` 在 S1 产品/测试路径上无 diff，后者只推进控制状态进入本 implementation gate。
- **gate**：implementation；本 artifact 不执行 code review、fix、re-review、accepted slice commit 或 R01-S2。
- **状态**：`implementation-pass / ready-for-code-review`。
- **结论**：S1 的 source snapshot owner 与五工具 consumer 已形成闭环；完整来源复制到真实 EOF，旧 source byte cap、预算类型/参数、typed budget failure、search oversized skip/result 字段及对应 LLM-facing 引导均已删除。目录 entry cap/partial 仍按 accepted plan 保持 S1 原行为。
- **artifact path**：`docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-implementation-s1-codex.md`。

## 2. 第一性原理判断与直接代码证据

动机成立。修前 `BoundedSourceSnapshot` 同时根据 `Source.content_length` 提前拒绝，并按 `remaining + 1` 实读拒绝未知长度来源；`DocResourceBudget.max_source_bytes` 又沿 process target、definition、同步路由和 read/get/search/section helper 传播。search 捕获同一异常后静默跳过文件，返回 source-specific partial 字段，并把规避输入 cap 的提示投影给 LLM。

这不是展示层或单一入口问题。唯一正确 owner boundary 是：

1. `dayu.documents.processors.source_snapshot.SourceSnapshot` 拥有一次性 `Source` 到可重读完整快照的复制、cursor、metadata、materialization 与 cleanup contract。
2. `dayu.tools.doc_tools` 拥有五工具的同步业务调用链、错误/结果/schema/LLM-facing 投影与 process target serialization contract。

因此修复直接落在两个 owner；没有在 Host、Engine、provider、adapter 或测试夹具增加 fallback、兼容 seam 或重算逻辑。

## 3. 实施内容

### 3.1 SourceSnapshot owner

- 删除 `dayu/documents/processors/bounded_source.py`；新增 `dayu/documents/processors/source_snapshot.py`。
- `SourceSnapshot` 不接收任何 byte limit、budget、profile 或 policy；`Source.content_length` 只作 metadata。
- 单个实例只调用原 `Source.open()` 一次，以固定 `_COPY_CHUNK_BYTES` 循环复制到真实 EOF；`_SPOOL_MEMORY_BYTES` 只决定内存转磁盘阈值。
- active 后 `content_length` / `snapshot_size` 是实际完整字节数；每次 `open()` 返回独立、seekable、只读 cursor。
- materialized prefix 改为 `dayu-doc-source-`；重复 `materialize()` 复用同一路径。
- 保留单次进入、幂等 close、正常/consumer exception/Source I/O/cancellation 的 spool 与 materialized path cleanup。
- 不导出旧模块/类/异常，不新增 alias、wrapper 或兼容 import。

### 3.2 Doc 工具 consumer

- import 切换为 `SourceSnapshot`；删除 source byte 常量、`DocResourceBudget` 与全部 `resource_budget` / `max_source_bytes` 参数和传递。
- `_DocProcessTarget` / `_DocProcessTargetFactory` 只保留可序列化路径 locator、output limits 与 timeout 标量，不捕获预算对象或 Host live object。
- `_source_snapshot(path, cancellation_token)` 构造 `LocalFileSource` 与未进入的完整 `SourceSnapshot`。
- get-sections、search、read、read-section 全部消费完整 snapshot；删除 source budget failure mapping。
- search 删除 oversized exception catch、skip counter、source-specific truncated reason 与结果字段；保留 `result_limit` 和 S1 目录 entry partial。
- search schema description 删除 source-specific partial/recovery 引导，保留仍真实存在的 `result_limit` / `directory_entry_limit` 说明。
- 按 accepted plan 的唯一 S1 过渡，`_route_doc_business` 在 list/search 分支把既有 `_DOC_DIRECTORY_MAX_ENTRIES: Final[int]` 直接传给既有 `max_directory_entries: int` 参数；未新增 assert、validator、wrapper、budget/config/optional/compat seam。
- `allowed_paths`、list/search 当前 symlink 边界、process-backed execution、父进程 cancellation/fencing、read output char limit、`ToolTruncateSpec`、framework `fetch_more` 与 `result_limit` 均未改变。

### 3.3 Owner/consumer tests

- processor owner tests覆盖未知声明长度的多 chunk EOF 复制、声明长度不拒绝、active 后精确长度、两个独立 cursor、processor 只消费 snapshot 且原 Source 只打开一次、单次进入、幂等 close、单 materialized path、正常/consumer exception/I/O/cancellation cleanup。
- import boundary test 要求扫描包含 `processors/source_snapshot.py`，并证明旧 processor 文件不再存在；forbidden-layer import 继续零命中。
- provider consumer tests删除预算构造校验和旧参数，锁定 process target 的精确字段集合，验证 read 完整输入、search 完整输入进入 processor 并产生命中、search 最终结果 key 集合、保留的 directory/result/output partial、`ToolTruncateSpec`、process/direct outcome、路径授权、symlink containment 与 cancellation/fencing contract。

## 4. 文件边界

相对 slice base `1b4e5d33` 的工作区只包含以下 accepted S1 allowlist 文件：

1. 删除 `dayu/documents/processors/bounded_source.py`。
2. 新增 `dayu/documents/processors/source_snapshot.py`。
3. 修改 `dayu/tools/doc_tools.py`。
4. 修改 `tests/documents/test_processors.py`。
5. 修改 `tests/documents/test_import_boundary.py`。
6. 修改 `tests/tools/test_doc_tools_provider.py`。
7. 新增本 implementation artifact。

没有 control、design、README、Host、Engine、runtime、contracts、config、Fins、UI、Service 或其它 semantic diff。`workspace/tmp/.coverage-r01-s1` 与 `workspace/tmp/coverage-r01-s1.json` 是验证产物，不进入版本控制 diff。

## 5. 验证

### 5.1 修改前 baseline

```text
pytest tests/documents/test_processors.py tests/documents/test_import_boundary.py tests/tools/test_doc_tools_provider.py -q
83 passed in 3.13s
```

baseline 无失败。S1 删除了只固化旧预算 contract 的 parameterized cases，因此修后 node 数减少，不是测试丢失；新 owner/consumer contract assertions 已按 §3.3 迁移。

### 5.2 Focused tests

```text
pytest tests/documents/test_processors.py tests/documents/test_import_boundary.py tests/tools/test_doc_tools_provider.py -q
75 passed in 2.45s
```

coverage 采样使用相同三文件完整 suite：

```text
coverage run --data-file=workspace/tmp/.coverage-r01-s1 -m pytest \
  tests/documents/test_processors.py \
  tests/documents/test_import_boundary.py \
  tests/tools/test_doc_tools_provider.py -q
75 passed in 2.76s
```

### 5.3 逐文件 coverage

coverage JSON：`workspace/tmp/coverage-r01-s1.json`。

| changed production file | covered / statements | exact coverage | gate |
|---|---:|---:|---|
| `dayu/documents/processors/source_snapshot.py` | 134 / 147 | 91.15646258503402% | `>=80%` pass |
| `dayu/tools/doc_tools.py` | 616 / 768 | 80.20833333333333% | `>=80%` pass |

两个精确 `coverage report --include=... --fail-under=80` 命令均 exit `0`。已删除文件不伪造 coverage。

### 5.4 Type / diff / source scans

- `python -m pyright`：`0 errors, 0 warnings, 0 informations`。
- `git diff --check`：exit `0`，无输出。
- 对新增 `source_snapshot.py` 执行 `git diff --no-index --check /dev/null ...`：无 whitespace error 输出；exit `1` 仅表示两端内容不同。
- `rg -n 'DocResourceBudget|SourceBudgetExceeded|max_source_bytes|source_budget_exceeded|skipped_oversized_files|source_limit' dayu tests README.md`：exit `1`，零命中、无输出。
- `rg -n 'bounded_source|BoundedSourceSnapshot|dayu-doc-bounded' dayu tests`：exit `1`，零命中、无输出。
- retention audit 仍命中 `_DOC_DIRECTORY_MAX_ENTRIES` 及 list/search 两个 `max_directory_entries` 调用链；这是 S1 accepted intermediate contract，R01-S2 才删除。
- retention audit 仍命中 `ToolTruncateSpec` / `_text_content_truncate`、`result_limit`、`_project_doc_paths`、`_resolve_search_files_candidate`、`_raise_if_doc_cancelled` 与 `ProcessBackedToolExecutionCapability`，对应 owner/consumer tests 全部通过。

没有新增或扩散的 validation failure，无需 baseline failure registry。

## 6. README trigger decision

| README | S1 decision | 依据 |
|---|---|---|
| `tests/README.md` | 本 slice 不修改；由已批准的 R01-S2 统一更新 | 修改 tests 命中 trigger，当前 README 仍描述待由 R01-S2 一并删除的 source 与 directory 两类旧 contract。accepted plan §8.5/§13.1 明确 S1 不先写中间态，S2 在 source + directory 终态形成后统一迁移 Documents/Tools 两处事实；用户也明确禁止本 slice 修改 README。 |
| `dayu/config/README.md` | 无需更新 | provider 配置 owner、`allowed_paths` 和五个 output/argument limits 均未改变；source byte cap 从未属于 provider 配置。 |
| 根 `README.md` | 无需更新 | 安装、初始化、CLI/Web/WeChat 入口、参数、输出通道、日志、workspace 位置与最终用户工作流均未改变。 |
| `dayu/README.md` 及 Engine/Host/Fins README | 无需更新 | 分层、装配与对应层 contract 无变更。 |

因此 S1 README diff 为零；`tests/README.md` 的终态迁移明确分类为 later approved slice work，不在本 slice 形成中间文档 contract。

## 7. Residual risks 与未覆盖项

| residual / uncovered area | classification | owner / destination |
|---|---|---|
| S1 仍保留 10,000 directory entry cap、list/search directory partial 与相关 LLM 文本 | `covered by later approved slice` | R01-S2；本 slice 禁止提前删除或改写 |
| `tests/README.md` 在 S1 中间态仍描述旧 source/directory contract | `covered by later approved slice` | R01-S2 按 accepted plan §13.1 统一更新 |
| >32 MiB / >10,000 entries 真实 discovery→callable smoke 未在 S1 运行 | `covered by later approved slice` | R01-S2 / R01 completion 的固定 smoke node；S1 owner tests已验证 declared/unknown-length 完整复制 |
| 五工具尚未完整接入 `TruncationManager` / framework remainder continuation | `tracked by existing issue` | GitHub Issue #177；S1 保留现有 `ToolTruncateSpec` / `fetch_more` owner，不做半接线 |
| 极大输入可能消耗磁盘与处理时间 | `assigned to later work unit` | 后续 input governance 设计；当前 contract 按 accepted 产品裁决使用完整 spool、process fencing 与 cancellation，不恢复输入 hard-fail |

没有未分类 residual risk，没有需要扩张 allowlist、改变 owner 或修改 accepted contract 的 open question。

## 8. Completion signal 与下一入口

R01-S1 implementation 已满足：owner/consumer code 和 tests 同源迁移、focused tests 通过、两个 changed production file coverage 均 `>=80%`、full pyright 通过、diff hygiene 通过、两条删除语义 scan 零命中、README decision 已记录、无 allowlist 外 semantic diff。

**下一入口只有 R01-S1 code review。** AgentCodex 在此停止，不进入 R01-S2，不修改 control/design/README，不 commit、push 或创建 PR。
