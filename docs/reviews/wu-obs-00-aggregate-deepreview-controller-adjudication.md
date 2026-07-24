# WU-OBS-00 Aggregate Deepreview Controller Adjudication

status=complete

work_unit=WU-OBS-00

gate=whole-WU-aggregate-deepreview

decision=needs-fix

review_base=9588ee7a1801f2e88352368fe920fe881612d7fb

review_head=f8d6d669

review_artifacts=

- docs/reviews/code-review-20260724-163910.md
- docs/reviews/code-review-20260724-164901.md

## Review 总结

AgentDS 与 AgentMiMo 均给出 aggregate `PASS`。共同验证 whole-WU tests、pyright、
coverage、Source 四模式、只读 snapshot、structured report、Host/Engine/Tool rules、
provider identity、CLI→Service→Host、publication、public exports 与 README。

但 reviewer verdict 不是 disposition 真源。AgentMiMo 同时报告 2 个 medium 与 6 个 low
finding；Controller 又在核对 strict UTF-8 publication contract 时取得一条 reviewer 未覆盖的
直接失败证据。因此本 gate 裁决为 `needs-fix`。

## Accepted findings

### CTRL-AGG-01 — strict UTF-8 写入失败泄漏本次临时文件

severity=medium

owner=dayu.service.tool_trace_analysis publication boundary

直接代码证据：

- `_write_temporary_text` 使用 `NamedTemporaryFile(delete=False, errors="strict")`；
- `_publish_report_pair` 的 temp-write 阶段只捕获 `OSError`；
- strict UTF-8 对未配对 surrogate 抛出 `UnicodeEncodeError`，其不是 `OSError`；
- `_write_temporary_text` 在异常前没有返回 temp path，调用方无法清理该文件。

Controller 隔离复现：

```text
_write_temporary_text(temp_dir, "\ud800")
-> UnicodeEncodeError
-> isinstance(error, OSError) == False
-> temp_dir 残留 .tool-trace-analysis-*.tmp
```

这违反 accepted plan §10.3 的“任一发布失败时 best-effort 清理本次临时文件”，并使 CLI
返回 1 时磁盘状态与 publication contract 不一致。

修复边界：

- 在 Service publication owner 内保证当前正在写入的 temp 与此前已写成功的 temp 在
  `UnicodeEncodeError`、`OSError` 及中断/异常传播时都执行 best-effort cleanup；
- `KeyboardInterrupt` / `SystemExit` 必须清理后原样传播，不得被转为普通 failure；
- 不把 loose encoding、replacement character 或 `errors="ignore"` 当修复；
- 不修改 Host report schema/renderer 来掩盖 Service 临时文件 lifecycle bug；
- owner-level tests 至少覆盖 JSON 首个 temp 写失败、Markdown 第二个 temp 写失败、旧报告
  保持与无 temp 泄漏。

### CTRL-AGG-02 — 双文件 publication 措辞必须与 partial truth 一致

severity=low

owner=Service publication contract documentation

`_publish_report_pair`、Service module/docstring 与开发 README 当前使用“原子发布报告对”或
“原子发布 JSON/Markdown”，但计划明确：

- 每个目标通过同目录 temp + `os.replace` 单文件原子替换；
- 第二次 replace 失败允许新 JSON + 旧/无 Markdown；
- 双文件不创建 transaction/journal。

因此“报告对原子发布”会把不存在的跨文件事务语义写入开发 contract。修复只应统一为
“按 JSON→Markdown 确定顺序逐文件原子替换；双文件不构成事务”，不改变行为或 public type
name。

## Reviewer findings disposition

| Finding | Disposition | Controller reasoning |
|---|---|---|
| DS-1 / MiMo-3：`_validate_source` future enum bare else | reject-nondefect | 当前 `StrEnum` 是封闭四值且 tests 穷举；只在未来新增 contract 时才需同步，不为假设性扩展增加当前兼容/防御分支。 |
| DS-2：write-side PRAGMA 未回读 | reject-out-of-scope | write helper 在本 WU 前已存在；本 WU 只新增并严格验证 read-only helper，且 plan 明确不得调用写侧 WAL helper。 |
| MiMo-1：durable→engine 反向依赖 | reject-nondefect/pre-existing | import 自 `bd1d3e94` 已存在，WU range 未新增或扩散；`dayu.host.durable` 不是独立业务层，Host→Engine 是允许方向。 |
| MiMo-2：Service/Host 路径常量重复 | reject-nondefect | Service discovery 提议 source，Host public contract authoritative revalidate；任何漂移 fail closed。公开内部布局常量会破坏 S2 frozen contract并加深上层对下层实现细节耦合，无当前错误语义。 |
| MiMo-4：锁外 exact-prefix read | reject-plan-conflict | accepted plan 明确锁内只做 open/fstat，锁外同 handle 精确读取，避免 O(file-size) 锁阻塞；并发/replace/truncate tests 已覆盖。 |
| MiMo-5：`lexists` 与 Host `stat` 不同 | reject-nondefect | Service discovery 保留 dangling path 候选，Host authoritative validation 拒绝并投影 usage error；全链 fail closed。 |
| MiMo-6：CLI 兜底错误文本 | reject-nondefect | bounded Host/Service error 作为 operator diagnostic 返回 1，未输出 traceback/secret；不属于 LLM-facing 文本，且无错误退出码或语义证据。 |
| MiMo-7：原子措辞 | accepted-as-CTRL-AGG-02 | 修正文档语义，不改 publication 行为。 |
| MiMo-8：Analyzer 注入 SQLite policy | reject-plan-conflict | accepted plan 明确 standalone 使用 `HostSQLiteStoragePolicy()` durable 默认，override 仅供 internal tests/opener，禁止进入 Analyzer policy/CLI。 |

## 真实 workspace 事实纠正

AgentMiMo 首次 artifact 曾错误写“本次环境无 `.dayu`”。实际
`workspace/.dayu` 存在并包含 Slice 4 真实 producer 生成的 current-schema 数据；其手写 smoke
两次失败分别来自缺 `Path` import 与错误 source 路径。MiMo 已修正 artifact。Controller 现场
执行：

```text
python -m dayu.cli tool_trace analyze workspace --output-dir <mktemp>
```

成功发布 JSON/Markdown；AgentDS aggregate 也只读分析得到 `9 records / 2 findings /
5 limitations`。该 reviewer script error 不构成 production finding。

## Fix gate

AgentCodex 只允许修改：

- `dayu/service/tool_trace_analysis.py`
- `tests/service/test_tool_trace_analysis.py`
- `dayu/service/README.md`
- `dayu/README.md`
- aggregate fix artifact

不得修改 frozen Host contracts/rules/input/producer/schema、CLI behavior、control_doc、既有
review artifact 或真实 workspace 数据。fix 后必须复跑 focused/full affected、full pyright、
changed-file branch coverage 与现有 workspace analyzer 只读 smoke；不得删除 `.dayu` 或重新
运行 prompt/interactive。

blocker=none

next_entry_point=AgentCodex aggregate deepreview fix; never self-advance
