# WU-OBS-00 Whole-PR Deepreview Fix Artifact

status=complete

work_unit=WU-OBS-00

work_unit_type=GitHub Issue #70 observability/debug tooling issue

gate=whole-PR-deepreview-fix-controller-review-correction

pr=https://github.com/noho/dayu-agent-r/pull/186

implementation_agent=AgentCodex

implementation_base=9519b02949941477bc5e2ca3dc7684967222a4ed

controller_adjudication=docs/reviews/wu-obs-00-whole-pr-deepreview-controller-adjudication.md

correction_adjudication=docs/reviews/wu-obs-00-whole-pr-deepreview-fix-controller-adjudication.md

accepted_plan=docs/host/wu-obs-00-plan.md#74-file-consistency-and-concurrent-writers

artifact_path=docs/reviews/wu-obs-00-whole-pr-deepreview-fix-codex.md

allowed_scope=

- `dayu/host/tool_trace_analysis_input.py`
- `tests/host/test_tool_trace_analysis_input.py`
- 更新 `docs/reviews/wu-obs-00-whole-pr-deepreview-fix-codex.md`

next_entry_point=Controller review; AgentCodex stops and never self-advances

## 1. Controller review 结果、动机与 owner 判断

`PR-CTRL-01` 动机成立，Controller 评估为中等严重度符合直接代码与运行时证据：

- `_capture_cold_prefix(...)` 的 exact-prefix read / 同 handle identity 校验失败进入
  `except OSError` 后，旧实现会先构造 read
  `ToolTraceAnalysisInputError`，再进入 `finally`；
- 若同一次 handle lifecycle 的 `handle.close()` 也抛出 `OSError`，`finally` 中的新
  `ToolTraceAnalysisInputError` 会替换正在传播的 read error；
- 因而对外仍是 `cold_snapshot_read_failed`，但 summary 与 direct `__cause__` 错误地指向
  secondary close failure，直接根因被 primary error 遮蔽。

唯一语义 owner 是 `dayu.host.tool_trace_analysis_input` 的 cold snapshot handle
lifecycle：该边界负责锁内 open/fstat、锁外 exact-prefix read/identity 校验、close 与
typed input error 映射。本 fix 只修改此 owner boundary，不在 Service、CLI、public type、
schema、日志、规则、dataset 或下游消费者补偿。

上一轮 Controller review 未通过，唯一 accepted finding 为 `PR-FIX-CTRL-01`。原因是上一轮为
拆分 read/close `OSError` 删除了 `finally`，却只捕获 operation phase 的 `OSError`：
`_read_exact_prefix(...)`、后续 `os.fstat(...)` 或 identity control flow 若抛
`KeyboardInterrupt`、`SystemExit`、`MemoryError` 等非 `OSError`，函数会在调用
`handle.close()` 前直接逃逸。Controller 注入 `KeyboardInterrupt("read-interrupt")` 后直接
观察到 `handle_closed=False`，证明这是 fix 引入的真实 lifecycle 回归。

`PR-FIX-CTRL-01` 与原 finding 的唯一语义 owner 仍是
`dayu.host.tool_trace_analysis_input` cold snapshot handle lifecycle。accepted plan §7.4
要求 exact-prefix read/identity 后关闭同一 handle；正确修复必须同时拥有 operation primary、
mandatory close 与最终异常映射，不应在下游补偿或重新引入会覆盖 primary 的 `finally raise`。

最终 exception precedence 为：

| operation phase | close phase | 最终结果 |
| --- | --- | --- |
| success | success | 返回 captured prefix |
| `OSError` | success / 任意 failure | 既有 read `ToolTraceAnalysisInputError`；read summary 不变，direct cause 指向 operation `OSError` |
| 非 `OSError` `BaseException` | success / 任意 failure | operation 原异常实例原样传播 |
| success | `OSError` | 既有 close-only `ToolTraceAnalysisInputError`；close summary/direct cause 不变 |
| success | 非 `OSError` `BaseException` | close 原异常实例原样传播 |

实现分别保存 `operation_failure: BaseException | None` 与
`close_failure: BaseException | None`，operation phase 后无条件尝试 close，最后先裁决
operation primary，再在无 primary 时裁决 close failure。因此所有 operation primary 都不会被
secondary close 覆盖，同时 close-only failure 仍然 fatal。

不实施 Controller 已驳回的 rules/dataset lock-path 建议；不新增
`expected_cold_lock_path`、public schema、日志 fallback、compatibility 或下游补偿。

## 2. Changed files

- `dayu/host/tool_trace_analysis_input.py`
  - `_capture_cold_prefix(...)` 在 owner boundary 内捕获 operation phase 的任意
    `BaseException`，随后无条件尝试 close 并独立捕获任意 close `BaseException`；
  - operation `OSError` 在 close 尝试后映射为既有 read typed error；operation 非
    `OSError` 原实例传播；
  - 只有无 operation primary 时才处理 close failure：`OSError` 映射既有 close typed
    fatal，非 `OSError` 原实例传播；
  - 没有在 `finally` 中 raise，secondary close 不公开、不覆盖 operation primary；
  - 未修改 reason enum、public error type、dataset、schema 或日志。
- `tests/host/test_tool_trace_analysis_input.py`
  - 新增
    `test_non_os_operation_failure_closes_handle_and_preserves_identity`，参数化覆盖
    `KeyboardInterrupt + close success` 与 `SystemExit + close OSError`；
  - 两个分支均断言 close 精确调用一次、最终异常 `is` 预构造 operation failure；
  - 新增
    `test_cold_prefix_read_failure_is_not_masked_by_close_failure`，同时注入 exact read 与
    close failure；
  - 所有 lifecycle test 使用真实底层 binary reader，并在 `finally` 中通过
    `force_close()` 可靠清理；
  - 增强 `test_cold_handle_close_failure_is_fatal`，断言 close summary 与 direct
    `__cause__`。
- `docs/reviews/wu-obs-00-whole-pr-deepreview-fix-codex.md`
  - 更新为本 correction gate 的 durable handoff artifact。

## 3. Finding closure evidence

### 3.1 PR-FIX-CTRL-01：非 OSError operation failure

参数化 owner test 使用真实 binary reader，预先构造两种 operation primary：

- `KeyboardInterrupt("read interrupted")`：真实 close 成功；
- `SystemExit("read exited")`：close 同时抛 secondary `OSError("close failed")`。

两个分支都断言：

```text
reader.close_calls=1
raised.value is operation_failure
```

这证明 operation phase 捕获任意 `BaseException` 后 mandatory close 确实执行，且无论 close
成功或失败，非 `OSError` operation primary 都保持原实例，不被 secondary close 覆盖。

PR-FIX-CTRL-01=closed-by-owner-lifecycle-implementation-and-owner-tests

### 3.2 PR-CTRL-01 non-regression：read + close OSError 双失败

owner test 预先构造 `OSError("primary exact read failed")`，让
`_read_exact_prefix(...)` 原样抛出它，同时让同一真实 reader 的 `close()` 抛
`OSError("close failed")`。最终断言：

```text
reason=cold_snapshot_read_failed
summary=无法从同一 handle 读取完整 cold snapshot prefix。
__cause__ is read_failure
str(__cause__)=primary exact read failed
```

这同时证明 reason、read summary、direct cause identity 与内容均未被 close failure 覆盖。
真实底层 reader 在 test `finally` 中显式清理。

### 3.3 PR-CTRL-01 non-regression：close-only failure

既有 owner test 让 exact-prefix read 与 identity 校验成功，只让 close 失败。增强后的断言为：

```text
reason=cold_snapshot_read_failed
summary=关闭 cold snapshot handle 失败。
isinstance(__cause__, OSError)=true
str(__cause__)=close failed
```

这证明 accepted plan §7.4 与既有 close-only fatal contract 保持不变，没有把所有 close
failure 改为 best-effort。

PR-CTRL-01=remains-closed-by-owner-boundary-implementation-and-owner-tests

## 4. Focused input tests

```bash
source .venv/bin/activate
pytest -q tests/host/test_tool_trace_analysis_input.py
```

结果：`30 passed in 0.62s`。

## 5. Affected Tool Trace matrix

```bash
source .venv/bin/activate
pytest -q \
  tests/host/test_tool_trace_projection.py \
  tests/host/test_tool_trace_queries.py \
  tests/host/test_durable_connection.py \
  tests/host/test_tool_trace_analysis_input.py \
  tests/host/test_tool_trace_analysis_rules.py \
  tests/host/test_tool_trace_analysis.py \
  tests/service/test_tool_trace_analysis.py \
  tests/cli/test_tool_trace_command.py \
  tests/cli/test_arg_parsing.py \
  tests/cli/test_import_boundary.py
```

结果：`244 passed, 3 warnings in 4.86s`。三条 warning 均为既有 `edgar` 第三方
deprecation warning，不属于本 fix owner。

## 6. Full pyright

```bash
source .venv/bin/activate
python -m pyright dayu/ tests/ utils/
```

结果：`0 errors, 0 warnings, 0 informations`。

命令另有 pyright `v1.1.409 -> v1.1.411` 更新提示，不是类型诊断。

## 7. Changed-file branch coverage

```bash
source .venv/bin/activate
pytest -q tests/host/test_tool_trace_analysis_input.py \
  --cov=dayu.host.tool_trace_analysis_input \
  --cov-branch \
  --cov-report=term-missing
```

结果：

```text
dayu/host/tool_trace_analysis_input.py  Stmts=499 Miss=77 Branch=134 BrPart=26 Cover=81%
30 passed in 0.76s
```

唯一修改的 production Python 文件 branch coverage 为 `81%`，达到 `>=80%` 目标。

## 8. Existing workspace/cold-file analyzer read-only smoke

严格复用既有安全流程，只运行现有 `tool_trace analyze`。没有运行 prompt、interactive 或
init，没有删除、修复或改写 `workspace/.dayu`。两个 output directory 均由 `mktemp` 创建在
`/tmp`：

```bash
source .venv/bin/activate
workspace_output="$(mktemp -d /tmp/wu-obs-00-pr-fix-ctrl-01-workspace.XXXXXX)"
cold_output="$(mktemp -d /tmp/wu-obs-00-pr-fix-ctrl-01-cold.XXXXXX)"

python -m dayu.cli tool_trace analyze workspace \
  --output-dir "$workspace_output"
python -m json.tool \
  "$workspace_output/tool-trace-analysis.json" >/dev/null
test -s "$workspace_output/tool-trace-analysis.md"

python -m dayu.cli tool_trace analyze \
  workspace/.dayu/artifacts/tool-trace/tool-trace-cold.jsonl \
  --output-dir "$cold_output"
python -m json.tool \
  "$cold_output/tool-trace-analysis.json" >/dev/null
test -s "$cold_output/tool-trace-analysis.md"
```

analyzer 前后都用以下只读命令采集证据，并通过七项 `test before = after`：

```bash
shasum -a 256 \
  workspace/.dayu/artifacts/tool-trace/tool-trace-cold.jsonl \
  workspace/.dayu/host/dayu_host.sqlite3
find workspace/.dayu -type f -print0 \
  | sort -z \
  | xargs -0 shasum -a 256 \
  | shasum -a 256
find workspace/.dayu -type f | wc -l
sqlite3 -readonly workspace/.dayu/host/dayu_host.sqlite3 \
  'SELECT COUNT(*) FROM host_tool_trace_hot;'
sqlite3 -readonly workspace/.dayu/host/dayu_host.sqlite3 \
  'SELECT COUNT(*) FROM payload_descriptors;'
wc -l < workspace/.dayu/artifacts/tool-trace/tool-trace-cold.jsonl
```

两种 mode、两次 JSON parse 与两次 Markdown non-empty 检查均返回 `0`：

```text
workspace_output=/tmp/wu-obs-00-pr-fix-ctrl-01-workspace.z0ZOZq
cold_output=/tmp/wu-obs-00-pr-fix-ctrl-01-cold.MnZBqD
cold_sha=06a9d18a369ebfefa6bee815cfa8d4a7fa541c26006bee4450907a6aac2e75f9
db_sha=fe72fbfcdced9006738cd9985702488e8e804cecf077ca97559f83a4d19bf400
tree_content_sha=ef31487cebb23b36b19bd7d5f54b127b11f218dc0bd68978e85e21d18ae3b4b0
tree_files=19
hot_rows=9
payload_descriptors=7
cold_rows=9
inputs_unchanged=true
```

以上七项在 analyzer 调用前后分别采集并逐项相等：cold / DB 使用 SHA-256；tree hash 使用
稳定排序的 `.dayu` 全部文件内容 SHA-256 再聚合；hot rows 与 payload descriptors 使用
SQLite `-readonly` 查询 owner 表；cold rows 使用只读行数统计。

## 9. README decision

不修改 README。本 correction 是同一个 Host internal handle lifecycle 与 exception
precedence 的 root-cause fix，不改变用户可见命令、入口、参数、输出、public type/schema、
分层装配或 operator workflow；用户也明确禁止修改 README。`dayu/host/README.md`、
`tests/README.md`、根 README 与其它 README 均未改。

## 10. Diff / scope / immutable artifact audit

实现前 preflight：

```text
branch=work/wu-obs-00
HEAD=9519b02949941477bc5e2ca3dc7684967222a4ed
existing tracked dirty:
  dayu/host/tool_trace_analysis_input.py
  docs/host/issues-implementation-control.md
  tests/host/test_tool_trace_analysis_input.py
existing untracked Controller/review artifacts:
  docs/reviews/wu-obs-00-whole-pr-deepreview-controller-adjudication.md
  docs/reviews/wu-obs-00-whole-pr-deepreview-ds.md
  docs/reviews/wu-obs-00-whole-pr-deepreview-fix-codex.md
  docs/reviews/wu-obs-00-whole-pr-deepreview-fix-controller-adjudication.md
  docs/reviews/wu-obs-00-whole-pr-deepreview-mimo.md
```

`git diff --check` 返回 `0`。实现后 branch 与固定 HEAD 未变。本 correction 相对本轮
preflight 只进一步修改两个 allowlisted tracked 文件与同一 allowlisted artifact；没有修改
README、plan、Host public types、control_doc、Controller adjudication、两路 review 或 PR
metadata。

最终 `git status --short`：

```text
 M dayu/host/tool_trace_analysis_input.py
 M docs/host/issues-implementation-control.md
 M tests/host/test_tool_trace_analysis_input.py
?? docs/reviews/wu-obs-00-whole-pr-deepreview-controller-adjudication.md
?? docs/reviews/wu-obs-00-whole-pr-deepreview-ds.md
?? docs/reviews/wu-obs-00-whole-pr-deepreview-fix-codex.md
?? docs/reviews/wu-obs-00-whole-pr-deepreview-fix-controller-adjudication.md
?? docs/reviews/wu-obs-00-whole-pr-deepreview-mimo.md
```

所有 status path 都在本轮 preflight 已存在；本 correction 没有新增 path。

只读真源在实现前后 SHA-256 逐项完全一致：

```text
4f3b0e663323c6ea7cee4bfb2e2c7e6a75b5955a1d298819969c1e4facdc5260  docs/host/issues-implementation-control.md
d212ba00ae137da8115af85cffb82f5a290f31e98b07c29458ec32d540627c1a  docs/reviews/wu-obs-00-whole-pr-deepreview-controller-adjudication.md
c1f0f615571cfbb3907ada4905317588cc7158edd1332a887977a4de0866ef0a  docs/reviews/wu-obs-00-whole-pr-deepreview-fix-controller-adjudication.md
4ef84abf942031e8c34fefe9d014f8bcb143d8a51d676813ecd4846f1098561e  docs/reviews/wu-obs-00-whole-pr-deepreview-ds.md
bd4a77e1d116f6c80ab40b864e69408fd786dde10960277bb248dc1362b087c7  docs/reviews/wu-obs-00-whole-pr-deepreview-mimo.md
eb5365d10f754391692c0ac29f279000bde1687f6d38d0914bef8df72b09cf26  docs/host/wu-obs-00-plan.md
```

## 11. Residual / uncovered

- 本 correction 未新增 residual risk；PR-FIX-CTRL-01 已由 owner implementation 与
  deterministic failure injection 关闭，PR-CTRL-01 的两条 OSError contract 保持闭合。
- Controller 已驳回的 rules/dataset lock-path 建议未实施，也不列为 active finding 或本 fix
  residual。
- 既有 whole-PR residual 不进入本 fix；本 artifact 不重新裁决或扩展其 scope。
- 未执行真实文件系统 close/read 设备故障；owner-level deterministic failure injection
  覆盖了 operation `KeyboardInterrupt` / `SystemExit`、close success/failure、read+close
  `OSError` 双失败与 close-only typed fatal contract。

blocking_open_questions=none

commit=not-created

control_doc=not-modified-by-AgentCodex

pr_metadata=not-modified

review=self-review-not-run

stop_condition=complete-and-wait-for-Controller-review
