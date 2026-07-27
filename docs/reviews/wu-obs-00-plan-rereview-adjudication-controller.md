# WU-OBS-00 Plan Re-Review Controller Adjudication

## 1. Scope and decision

- Work Unit：`WU-OBS-00`
- 修后计划：`docs/host/wu-obs-00-plan.md`
- AgentMiMo re-review：`docs/reviews/plan-review-20260724-112830.md`
- AgentDS re-review：`docs/reviews/plan-review-20260724-112958.md`
- 两路结论：均为 `pass-with-risks`
- Controller decision：`plan-fix-required`
- Blocking open questions：None。Controller 已对所有 accepted findings 指定 owner-level
  修复方向。

两路均确认首轮 Controller 的 15 项 disposition 已被逐项追踪，rejected/deferred 项没有
scope creep。但 re-review 基于新增代码证据发现：修复过程中引入的 lock/source 形状仍会让
implementation agent 重新设计，且全文件独占锁会让只读 analyzer 反向影响 live producer。
因此当前计划不能创建 accepted plan commit。

## 2. Finding adjudication

| Finding | 裁决 | Controller 依据与必须修复方向 |
|---|---|---|
| MiMo OQ-1 / DS F-R4：Service 无法合法派生 `cold_lock_path` | accepted；拒绝新增 public builder/factory | `cold_lock_path` 是由 `cold_jsonl_path` 唯一派生的 Host 内部运行期值，不是 Service 输入事实。将它作为 public Source 参数会迫使 Service 依赖 Host internal helper或新增只做透传/派生的 factory seam。应从 `ToolTraceAnalysisSource` public fields 删除 `cold_lock_path`；Service 只传显式发现路径，Host analyzer 内部调用 Tool Trace owner helper 派生并可投影到 report。helper 不从 Host package root 导出。 |
| DS F-R1：reader 持独占锁复制全文件阻塞 producer | accepted，必须在当前 plan 修复 | 现有 writer 只等 5 秒。未治理的大 cold 文件或慢盘上，全文件复制可使 analyzer 导致 producer lock timeout 和 cold trace append 失败；这违反只读/non-interference，不能仅记 residual 或转交 Issue #36。锁临界区改为：acquire shared owner lock -> open binary handle -> `fstat` 记录 prefix byte length和必要 identity -> release lock -> 从同一 handle只读精确 prefix -> close。不得读到动态 EOF；短读/截断为 fatal。追加到 prefix 后的 bytes 留给下一次分析。补 live producer 并发测试，证明 reader 不持锁做 O(file-size) I/O。 |
| MiMo OQ-2 / DS F-R2：read-only busy timeout 真源缺失 | accepted | 不把 SQLite I/O policy 混入诊断阈值 `ToolTraceAnalysisPolicy`，也不新增 CLI flag。内部 read-only opener 显式接收/持有 `HostSQLiteStoragePolicy`，standalone analyzer 使用 `HostSQLiteStoragePolicy()` 的既有 durable 默认值；`configure_read_only_connection_pragmas` 只读取其 `busy_timeout_seconds`。测试断言使用 durable policy 的命名默认/显式注入值，不复制魔法 5.0。 |
| MiMo OQ-3：hot-empty watermark 行为 | accepted as clarification | hot store可用且snapshot为空时watermark=`0`；若随后cold snapshot出现正sequence rows，只能证明观察窗口变化，全部按`input_changed_during_analysis` limitation处理，不得报`missing_hot_trace`。若cold也为空则正常空报告。把两种case写入join contract和validation matrix；不从数量/时间猜 stale DB。 |
| MiMo Spot-check 4 / DS F-R3：report单复数冲突 | accepted | 首版每个Source只有一个expected cold file。Source与report input统一使用`cold_jsonl_path`单数；report可包含Host派生的`cold_lock_path`单数。删除复数数组示例，不为未来多文件预留当前无需求schema。 |
| MiMo Spot-check 5：不修改producer表述 | accepted | 改为“不修改producer语义/输出contract”；明确S1只移动共享lock helper并保持event filter、schema、digest、append ordering、timeout value不变，projection regression tests保护。 |
| DS F-R5：S3冻结contract的stop condition | accepted | S3若必须修改S2冻结字段、枚举、nullable语义、ordering或id assignment，必须停止回Controller；不得偷偷把contracts.py加回allowed files。 |
| DS cleanup secondary error观察 | accepted（Controller补充） | `ServiceToolTraceAnalysisPublishError`明确分别承载primary publish error与可选cleanup error，不得用一个summary覆盖二者；第一次/第二次replace和cleanup-failure tests都断言原`failed_path`不漂移。 |

## 3. Required second plan-fix acceptance criteria

1. Public `ToolTraceAnalysisSource` 不再携带派生 lock path；Service -> Host call path无需访问
   `dayu.host.tool_trace` internal helper，也不新增 factory/wrapper。
2. cold snapshot 的独占锁临界区是 O(1) 的 open/fstat/prefix-boundary capture；全文件读取在
   释放锁后从同一 handle精确读取prefix，并覆盖短读、追加、替换/截断可观察失败。
3. read-only SQLite timeout 复用 durable `HostSQLiteStoragePolicy` 唯一默认/显式注入contract。
4. hot-empty/cold-empty 与 hot-empty/cold-late 两条行为进入文字contract和tests。
5. Source/report单数字段一致；derived lock path只由Host投影。
6. scope表述、S3 stop condition、publish cleanup secondary error闭合。
7. 同步计划全部相关章节、fix artifact、slice allowed files/tests/validation/residual risks；
   删除被新裁决取代的“全文件锁复制可接受”或public lock field描述。

## 4. Rejected/deferred reviewer suggestions

- 拒绝把全文件锁风险仅记录到 Issue #36；当前 WU 必须保证 analyzer 不损害 live producer。
- 拒绝新增 Host public `build_tool_trace_analysis_source` factory/classmethod；这会让 derived
  lock path 继续泄漏到上层并形成无必要 seam。
- 拒绝给 `ToolTraceAnalysisPolicy` 增加 SQLite busy timeout；诊断规则 policy 与 durable
  connection policy owner不同。
- 不改变 Issue #64、Issue #36、WU-OBS-01 和双文件非事务发布等既有 residual owner。

## 5. Gate transition

`plan re-review -> second plan fix`

AgentCodex 只可修改计划并新增第二次 plan-fix artifact。完成后必须再次由 AgentMiMo 与
AgentDS 对同一计划执行独立 `/planreview`。只有两路明确 `pass`、无 actionable finding，
且 Controller 最终裁决通过后，才创建 accepted plan commit。
