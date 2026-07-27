# WU-OBS-00 Second Plan Fix — AgentCodex

## 1. Gate / Scope / Status

- Work Unit：`WU-OBS-00` Tool Trace Analyzer。
- 类型：GitHub Issue #70 对应的 observability / debug tooling work unit。
- Gate：`second plan fix`。
- 被修计划：`docs/host/wu-obs-00-plan.md`。
- 当前唯一 disposition 真源：
  `docs/reviews/wu-obs-00-plan-rereview-adjudication-controller.md`。
- 两路 re-review：
  - `docs/reviews/plan-review-20260724-112830.md`
  - `docs/reviews/plan-review-20260724-112958.md`
- Status：`complete`。
- Blocking open questions：None。
- Stop condition：按委派停在 second plan fix；不得进入 second plan re-review、accepted plan
  commit 或 implementation。

本 gate 只修改计划并新增本 artifact。没有修改 control/design、生产代码、测试、README 或既有
artifacts，也没有 commit、push、PR、Issue mutation 或 implementation。

## 2. First-principles / Owner Judgment

第二次修复动机成立。两路 re-review 证明的根因不是 Analyzer 功能范围不足，而是首轮 fix 把
Host 内部派生 lock 值错误提升成 public Service 输入、把全文件读取放进 producer 共用的独占锁、
没有复用 durable SQLite policy，并留下 report schema 与 publish secondary error 的契约歧义。

最新 Controller 裁决把唯一 owner 明确为：

- Service 只拥有显式路径发现；`cold_lock_path` 由 Host Tool Trace owner 从
  `cold_jsonl_path` 内部派生。
- Host Analyzer input loader 拥有 cold snapshot；独占锁只保护 binary open/fstat prefix
  capture，精确 prefix read 在锁外从同一 handle 完成。
- `HostSQLiteStoragePolicy` 拥有 SQLite busy timeout；`ToolTraceAnalysisPolicy` 只拥有诊断
  阈值。
- Analyzer join/report 拥有 hot-empty 与 limitation 语义。
- Service publication typed error 分别拥有 primary publish failure 与 optional cleanup
  secondary failure。

因此没有采用 public builder/factory/classmethod/wrapper、Analyzer SQLite timeout 字段、CLI
flag、全文件持锁 residual defer、复数 future schema 或下游兼容补偿。

## 3. New Adjudication → Plan Mapping

| 最新裁决 | 修复状态 | 计划章节 | 实际修改 |
|---|---|---|---|
| 1. public Source 删除 `cold_lock_path` | 已修复 | §5.1、§6、§7.3-7.4、§12.1、S1、§14.1、§15 | Source 固定为五个显式字段；Service 只发现/传路径；Host Analyzer 内部调用 `dayu.host.tool_trace` owner helper 派生；report 可投影单数 lock path；helper 不从 Host root 导出；不新增 builder/factory/classmethod/wrapper |
| 2. O(1) cold snapshot lock critical section | 已修复 | §7.4、S1、§14.1、§17.1 | 固定 acquire -> binary open -> fstat prefix length/identity -> release -> same-handle exact-prefix read -> close；禁止锁内 O(file-size) read与动态 EOF；append 留待下次；short read/truncate/prefix不满足 fatal |
| 2a. live producer non-interference test | 已修复 | S1、§14.1 | barrier 阻塞锁外 prefix read 时启动真实 producer，断言 writer 在既有5秒timeout前完成且无 timeout；本次不含新 append、下次包含 |
| 3. SQLite timeout复用 durable policy | 已修复 | §5.1、§8.2、§8.4、§9.2、§12.1、S1、§14.1、§18 | read-only opener 显式使用 `HostSQLiteStoragePolicy`；standalone 使用 `HostSQLiteStoragePolicy()`；helper只读 `busy_timeout_seconds`；无 Analyzer policy 字段、CLI flag或`5.0`复制 |
| 4. hot-empty watermark=`0` | 已修复 | §7.4、§8.3、§9.1、S1、§14.1 | cold也空时正常空报告；随后cold出现正sequence rows时全部为`input_changed_during_analysis` limitation，零`missing_hot_trace` |
| 5. Source/report单数 schema | 已修复 | §7.3、§10.1、§15 | Source/report统一`cold_jsonl_path`单数；report仅额外投影Host派生`cold_lock_path`单数；删除复数数组示例和未来多文件预留 |
| 6. producer scope表述 | 已修复 | §3.1、§5.1、§12.1、S1、§15 | 改为不修改producer语义/输出contract；允许共享helper等价重构；event filter/schema/digest/append ordering/timeout value由projection regression tests保护 |
| 7. S3 frozen-contract stop | 已修复 | §8.1、S3、§14.1、§15 | 若需修改S2字段/枚举/nullable/order/id立即停回Controller；禁止把`tool_trace_analysis_contracts.py`加回allowed files或用兼容分支绕过 |
| 8. publish primary/cleanup error separation | 已修复 | §10.3、S4、§14.1、§15 | typed error分别携带`primary_publish_error`与optional`cleanup_error`；cleanup failure tests覆盖第一次/第二次replace；原`failed_path`/`published_paths`不漂移 |
| 9. 全文同步 | 已修复 | §1、§13-§19 | status、slices、allowed files、tests、validation、risks、disposition与next gate已同步 |

## 4. Replaced Description Cleanup Evidence

计划全文已清除以下被最新裁决取代的肯定式 contract：

- public `ToolTraceAnalysisSource.cold_lock_path`；
- Service 计算或传入 lock path；
- Host root 导出 lock helper或新增 public Source builder/factory/classmethod/wrapper；
- 锁内按动态终点读取、全量复制或其它 O(file-size) critical section；
- read-only helper裸接 `busy_timeout_seconds`、Analyzer自建SQLite timeout或复制`5.0`；
- report cold/lock path 的复数数组形状；
- “不修改producer代码”的过宽表述；
- S3可修改冻结contract或把`contracts.py`重新加入allowed files；
- 单一底层错误摘要覆盖publish与cleanup failure。

Required stale-search 对上述精确旧形状零命中；计划中保留的 `cold_lock_path` 仅用于说明它不是
public Source field，或表示 report 中 Host 内部派生的单数投影。保留的“5 秒 timeout”仅描述
既有 producer contract和并发验收，不是新建 SQLite/file-lock 魔法常量。

## 5. Slice / Allowed-file Impact

- Slice 数量保持 4，切分依据不变。
- S1：
  - public Source contract 删除派生 lock；
  - 增加 Host-internal prefix snapshot、durable SQLite policy 与 live producer concurrency
    tests；
  - `dayu/host/tool_trace.py` / `dayu/host/open_host.py` 仍在 allowed files，仅允许等价 helper
    ownership refactor；
  - `dayu/host/__init__.py` 不导出 lock helper/factory。
- S2：report input 使用单数字段；hot-empty contract成为最终 limitation schema的一部分。
- S3：allowed files仍不含`dayu/host/tool_trace_analysis_contracts.py`；新增明确 stop condition。
- S4：新增 cleanup secondary failure matrix；publication owner不变。

## 6. Validation

- 全文 stale-search：通过；精确旧形状零命中。
- `git diff --check -- docs/host/wu-obs-00-plan.md
  docs/reviews/wu-obs-00-plan-rereview-fix-codex.md`：通过。
- 两个目标文件均为 untracked，额外
  `git diff --no-index --check /dev/null <file>`：通过；exit code `1` 仅表示存在内容差异，
  无 whitespace diagnostic。
- `git status --short` scope audit：通过；本 Agent 实际只修改/新增两份 allowed files，未改
  control/design/source/tests/README/既有 artifact。
- 代码 tests/pyright：未运行；本 gate 只修改 Markdown plan/artifact，Required validation未要求
  implementation tests，且当前委派禁止进入 implementation。

## 7. Residual Risks / Next Entry

保留未被最新裁决改变的已分类 residual owner：

- Issue #64 native Anthropic / Claude Code gateway signal：`limited_signal`。
- Issue #36 cold rotation/archive 与 Analyzer 内存/聚合成本；O(file-size) read已移到锁外，不再
  把 producer 阻塞风险转交该 issue。
- WU-OBS-01 prompt/final-answer定位与Service discovery复用方式。
- 两个普通report文件不能跨文件原子提交；typed partial-publish result使失败可判读。

没有 blocking open questions 或未分类 residual risk。下一入口只能是 AgentMiMo 与 AgentDS 对
同一 `docs/host/wu-obs-00-plan.md` 再次执行独立 plan re-review；本 Agent 不自行推进。

## 8. Actual Changed Files

- `docs/host/wu-obs-00-plan.md`
- `docs/reviews/wu-obs-00-plan-rereview-fix-codex.md`

Artifact path：`docs/reviews/wu-obs-00-plan-rereview-fix-codex.md`。
