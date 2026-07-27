# WU-OBS-00 Slice 1 Implementation

```text
status=blocked
work_unit=WU-OBS-00
slice=S1
artifact path=docs/reviews/wu-obs-00-slice-1-implementation-codex.md
next entry point=dual code review（未进入；需 Controller 先裁决 live schema stop condition）
```

## 基线与范围

- accepted plan commit：`e1799abc3341872ba19ff609de15b236813a3533`
- branch：`work/wu-obs-00`
- preflight：实现前 `HEAD=e1799abc3341872ba19ff609de15b236813a3533`，worktree clean。
- 实施范围仅为 accepted plan 的 Slice 1 Trusted input snapshot and integrity boundary。
- 未实现 behavior rules、renderer、Service、CLI、Slice 2，也未预定义 report/finding/vendor public skeleton。
- 未 commit、push、创建 PR 或 Issue。

## Changed files

Production：

- `dayu/host/tool_trace_analysis_contracts.py`
- `dayu/host/tool_trace_analysis_input.py`
- `dayu/host/tool_trace.py`
- `dayu/host/open_host.py`
- `dayu/host/durable/connection.py`
- `dayu/host/durable/transaction.py`
- `dayu/host/durable/tool_trace.py`
- `dayu/host/__init__.py`

Tests：

- `tests/host/test_tool_trace_analysis_input.py`
- `tests/host/test_tool_trace_projection.py`
- `tests/host/test_durable_connection.py`
- `tests/host/test_tool_trace_queries.py`

Implementation artifact：

- `docs/reviews/wu-obs-00-slice-1-implementation-codex.md`

## Semantic owner / interface decisions

- `dayu.host.tool_trace_analysis_contracts` 拥有 Slice 1 public input contract。`ToolTraceAnalysisSource`
  仅有 `requested_path`、`mode`、`cold_jsonl_path`、`hot_db_path`、`artifact_root` 五个字段；
  `ToolTraceInputMode`、`ToolTraceAnalysisSource`、`ToolTraceAnalysisPolicy` 是本 slice 唯一新增
  Host-root exports，无 `cold_lock_path`。
- `dayu.host.tool_trace` 继续拥有 producer/reader 共用的相邻 cold lock 路径语义；
  `_tool_trace_cold_lock_path` 保持 Host internal，未从 Host root 导出，也未增加
  builder/factory/wrapper。
- `dayu.host.durable.connection` 与 `dayu.host.durable.transaction` 拥有物理只读 SQLite
  connection lifecycle 与只读 PRAGMA。opener 使用 URI `mode=ro`、`query_only=ON`，
  只消费 `HostSQLiteStoragePolicy.busy_timeout_seconds`，不执行 WAL、bootstrap、DDL 或 write。
- `dayu.host.durable.tool_trace` 拥有 unfiltered hot-row ASC cursor page query。
- `dayu.host.tool_trace_analysis_input` 拥有 hot-first snapshot、cold same-handle exact-prefix
  capture、strict current-schema parsing、digest/ref 校验、hot/cold join、resolver/reconstruction
  orchestration、input diagnostics 与 limitations。
- cold 锁内只执行 binary open 与 `fstat` prefix/identity capture；锁外从同一 handle 精确读取固定
  prefix。short read、truncate、identity、lock/open/read/close failure 均 fail closed。
- hot path 仅“实际缺失”可 limited；已存在但 open/schema/corrupt/permission/type 失败均 fatal。
  hot-empty/cold-late 全部投影为 `input_changed_during_analysis` limitation。

## Tests

Focused command：

```bash
source .venv/bin/activate
pytest -q \
  tests/host/test_durable_connection.py \
  tests/host/test_tool_trace_projection.py \
  tests/host/test_tool_trace_queries.py \
  tests/host/test_tool_trace_analysis_input.py
```

结果：`111 passed in 1.11s`。

覆盖的 owner-level contract 包括：

- public Source 五字段、四种 mode、路径布局/存在性/type/alias matrix 与 Host-root exports；
- read-only opener 默认/override timeout、物理只读、query-only、无 bootstrap/WAL/write；
- unfiltered hot query pagination；
- production projection digest/ref baseline 与破坏测试；
- strict parser、duplicate/conflict、hot/cold join、resolver/reconstruction；
- hot/cold empty 与 hot watermark limitation；
- barrier 驱动的真实 producer 并发，不依赖 sleep；
- same-handle path replacement、truncate/short-read/close/lock fatal matrix；
- file-only 不打开 payload ref。

额外 Host regression：

```bash
pytest -q tests/host
```

结果：`2294 passed, 3 skipped, 6 deselected, 1 failed`。唯一失败为允许范围外
`tests/host/test_package_exports.py::test_host_all_matches_current_public_contracts`，其旧 expected
set 尚未包含 accepted plan 要求新增的 `ToolTraceInputMode`、`ToolTraceAnalysisSource`、
`ToolTraceAnalysisPolicy`。本 slice 不允许修改该文件，未通过兼容导出或越界测试修改规避。

用于覆盖率的成功 Host regression 排除该整个范围外文件：

```bash
coverage run --branch --source=dayu.host -m pytest -q \
  tests/host --ignore=tests/host/test_package_exports.py
```

结果：`2281 passed, 2 skipped, 6 deselected in 67.67s`。

## Pyright

Targeted command：

```bash
python -m pyright \
  dayu/host/tool_trace_analysis_contracts.py \
  dayu/host/tool_trace_analysis_input.py \
  dayu/host/tool_trace.py \
  dayu/host/open_host.py \
  dayu/host/durable/connection.py \
  dayu/host/durable/transaction.py \
  dayu/host/durable/tool_trace.py \
  tests/host/test_tool_trace_analysis_input.py
```

结果：`0 errors, 0 warnings, 0 informations`。

Full command：

```bash
python -m pyright dayu/ tests/ utils/
```

结果：`0 errors, 0 warnings, 0 informations`，无新增或扩散错误。

## Per-file coverage

口径：`coverage.py --branch --source=dayu.host`；表中 `Cover` 同时计入 statement 与 branch。

| Production file | Statements | Miss | Branches | Partial branches | Cover |
| --- | ---: | ---: | ---: | ---: | ---: |
| `dayu/host/__init__.py` | 11 | 0 | 0 | 0 | 100% |
| `dayu/host/durable/connection.py` | 178 | 15 | 46 | 9 | 89% |
| `dayu/host/durable/tool_trace.py` | 385 | 51 | 72 | 23 | 82% |
| `dayu/host/durable/transaction.py` | 237 | 16 | 54 | 12 | 90% |
| `dayu/host/open_host.py` | 755 | 83 | 124 | 23 | 86% |
| `dayu/host/tool_trace.py` | 760 | 80 | 266 | 61 | 86% |
| `dayu/host/tool_trace_analysis_contracts.py` | 148 | 18 | 60 | 14 | 85% |
| `dayu/host/tool_trace_analysis_input.py` | 488 | 76 | 126 | 25 | 81% |

总计：2962 statements、748 branches、85%；全部新增/修改 production Python 文件均 `>=80%`。

## Current workspace read-only smoke

真实输入：

- cold：`workspace/.dayu/artifacts/tool-trace/tool-trace-cold.jsonl`
- DB：`workspace/.dayu/host/dayu_host.sqlite3`

严格 loader 结果：

```text
status=blocked-as-expected
fatal_reason=hot_store_read_failed
fatal_cause_type=HostSchemaMismatchError
schema_validation_error=Host durable schema version mismatch:
  expected fresh schema 24, got 20; recreate the durable database for this version
```

只读前后证据：

```text
cold_sha256=d0dac70d764063d73e6a11a6c0fa333c0c215c3af485756e71e74a06a0019cd4
cold_mtime_ns=1783576408816616370
cold_size=25450
cold_rows=9
db_sha256=b71556ed8eb6ca8b0c310ed3862464b625c23ece3073635710e2f459bab25b7f
db_mtime_ns=1783576408817726926
db_size=577536
db_user_version=20
hot_rows=9
inputs_unchanged=True
```

未对 workspace 执行 migration、bootstrap、DDL、write、raw-SQLite analyzer fallback 或 loose
parsing；未在 repo 留下临时产物。

## Docs decision

`not-yet-due`。accepted plan 将 README 更新放在 Slice 4；本次 allowed files 又明确禁止修改
README、control、plan、design。故本 slice 不越界更新文档，唯一新增文档是本 implementation
artifact。

## Findings / residual risks

1. **Blocking — live schema mismatch**：当前 workspace durable DB 是 schema 20，当前代码严格
   schema owner 要求 24。该事实直接阻止 accepted plan 要求的 live WAL/current workspace
   read-only smoke 成功，命中 Slice 1 stop condition。
2. **Validation residual — stale package export assertion**：完整 Host suite 的唯一失败位于不允许
   修改的 `tests/host/test_package_exports.py`；它仍固化旧 public export 集合。focused tests、
   pyright 与排除该文件后的 Host regression 均通过。
3. **Platform residual**：same-handle exact-prefix、path replacement、truncate/short read 和真实
   producer non-interference 已在当前 macOS/Python 3.11 环境验证；本次未获得其他 OS CI 证据。
4. **Downstream not reached in live smoke**：live schema gate 在 resolver 之前 fail closed，因此
   当前 workspace descriptor 的 live resolver 验证尚未发生；unit/fixture resolver contract 已通过。

## Stop condition

`blocked`。直接证据是 `HostSchemaMismatchError(expected=24, actual=20)`。按照 accepted plan 与
用户边界，禁止通过迁移真实 workspace、raw SQLite、loose parser、compatibility shim、扩大
allowed files 或修改 producer/schema 语义绕过。

## Next

下一入口为 dual code review，但本 Agent 不自推进；在进入 review 前需由 Controller 对上述
live schema stop condition 与范围外 package-export 测试进行裁决。
