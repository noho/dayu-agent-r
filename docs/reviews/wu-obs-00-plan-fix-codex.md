# WU-OBS-00 Plan Fix — AgentCodex

## 1. Gate / Scope / Status

- Work Unit：`WU-OBS-00` Tool Trace Analyzer。
- 类型：GitHub Issue #70 对应的 observability / debug tooling work unit。
- Gate：`plan fix`。
- 被修计划：`docs/host/wu-obs-00-plan.md`。
- Controller disposition 真源：
  `docs/reviews/wu-obs-00-plan-review-adjudication-controller.md`。
- 第一路 review：`docs/reviews/plan-review-20260724-110330.md`。
- 第二路 review：`docs/reviews/plan-review-20260724-110122.md`。
- Status：`complete`。
- Blocking open questions：None。
- Stop condition：按委派停在 plan fix；不得进入 plan re-review、accepted plan commit 或
  implementation。

本 gate 只修改计划并新增本 artifact。没有修改 control doc、design、生产代码、测试、README，
也没有 commit、push、PR 或 Issue mutation。

## 2. First-principles / Owner Judgment

修复动机成立。两路 review 指向的根因不是 Tool Trace signal 或 producer/schema 缺失，而是计划
尚未把并发 cold snapshot、hot DB fail-closed、read-only SQLite、public source、report freeze
与发布失败语义写成实现无需再设计的单一 contract。

修复边界遵循 Controller 裁决：

- cold lock path/timeout 由 Host Tool Trace projection owner 唯一产生，writer/reader 复用
  `dayu.runtime.filelock`；Service/CLI 不复制。
- hot DB 只有实际缺失才能 limited；已发现但损坏/不可打开/不可校验属于 fatal analysis。
- S1 只拥有 input/read-only contract，S2 冻结最终 report，S3 只追加 Engine/provider 结果。
- Analyzer report/rules 拥有 finding/limitation/measure/timeline 语义；renderer 不重算。
- output publication 由 Service 拥有，并把 partial success/failure path 作为 typed error 证据。

没有通过修改 producer/schema、增加 CLI flags、拆 docs slice、预判 WU-OBS-01 Service discovery
或兼容旧 schema 来绕开上述 owner。

## 3. Adjudication Finding → Plan Mapping

| Finding | Controller disposition | 修复状态 | 计划章节 | 实际修改 |
|---|---|---|---|---|
| MiMo F001 reader-side file lock | accepted | 已修复 | §5.1、§6、§7.3-7.4、§12.1、S1、§14.1 | 定义 shared adjacent lock helper/5秒timeout owner；hot snapshot 后、cold lock 内复制完整 bytes；timeout/acquire/release/read fatal；禁止 OS append 原子性和无锁 fallback |
| MiMo F002 corrupt hot DB | accepted with adjusted direction | 已修复 | §7.3、§8.4、S1、§14.1 | 仅 hot path 实际缺失可 `hot_store_unavailable`；已存在但 type/open/schema/corrupt/permission failure fatal，Service不发布、CLI 1；明确拒绝 reviewer 的 auto-discovered corrupt degrade 建议 |
| MiMo F003 S4 code/docs | rejected | 未按 reviewer 建议修改；保持裁决 | §15 disposition、S4 | 保持 S4 单一 code/docs 闭环；completion 要求先读五份 README 更新约束，不新增 docs slice |
| MiMo F004 contracts across slices | accepted，merged with DS F-DS-02 | 已修复 | §8.1、§10.1、S1-S3 | S1 只稳定已消费 input/read-only contract；S2 一次冻结最终 schema/order/vendor block；S3 从 allowed files 删除 contracts，只追加结果 |
| MiMo F005 read-only PRAGMA | accepted | 已修复 | §8.4、§12.1、S1、§14.1 | 命名独立 `configure_read_only_connection_pragmas`；只设 busy_timeout、foreign_keys、query_only；禁止写侧 helper、WAL/autocheckpoint/bootstrap/DDL |
| MiMo F006 dual publish | accepted | 已修复 | §10.3、S4、§14.1 | 固定 JSON→Markdown publish；typed error 分列 `published_paths`/`failed_path`；覆盖第二次 replace 的 old/new 与 no-old-file 两条路径及 temp cleanup |
| MiMo F007 CLI policy flags | rejected current WU | 未修改；保持裁决 | §3.1、§15 | 明确首版不新增 CLI tuning flags；默认 policy 写入 report，typed Host API 仍可注入 |
| DS F-DS-01 watermark reason | accepted | 已修复 | §7.4、§9.1、§10.1、S1、§14.1 | stable `reason_code=input_changed_during_analysis` 贯穿 schema/rule/test matrix；携带 watermark evidence；不计 finding |
| DS F-DS-02 S2→S3 handoff | accepted，merged with MiMo F004 | 已修复 | §8.1、§10.1、S2、S3、§14.1 | S2 tests 按 rule/reason/evidence 断言且不锁全局数量；S3 复跑完整 S1/S2 tests/pyright，冻结 contract/Host/Tool rule/order |
| DS F-DS-03 cold-line size | accepted | 已修复 | §9.2、§10.1、S2、§14.1 | 增加 `measurement_source`；cold line 明确为不含 terminator 的 JSONL record UTF-8 bytes，不称 raw payload；resolved bytes 独立 measure |
| DS F-DS-04 awaiting/waiting | accepted | 已修复 | §9.3、§10.1、S2、§14.1 | 两类 event 只作为 known timeline facts 和 summary counts；存在/缺失不猜故障；只有 typed failure/rejection 可触发 finding |
| DS F-DS-05 WU-OBS-01 Service reuse | deferred | 未修改；保持 deferred owner | §3.1、§15、§17.1 | 本 WU 仅承诺 typed Host source/analyzer/report 复用；Service discovery 由 WU-OBS-01 plan 决定 |
| DS F-DS-06 fixtures | accepted | 已修复 | §12.2、S1 | parser syntax/type unit 可手写 current-schema 最小 JSONL；digest/ref/integrity/join/resolver 必须 production projection baseline 后单点破坏 |
| CTRL-PF-01 Source contract | accepted | 已修复 | §7.3、S1、§14.1 | 列出六个字段、类型、必填性、absolute path contract、四 mode path/existence/type/null matrix、shared lock invariant、拒绝矩阵 |
| CTRL-PF-02 S4 duplicate | accepted | 已修复 | S4、§15 | S4 allowed-files 中 `dayu/cli/main.py` 只保留一个条目 |

## 4. Code-generation-ready Contract Additions

### 4.1 Input / lock / snapshot

- `ToolTraceAnalysisSource` 固定为
  `requested_path`、`mode`、`cold_jsonl_path`、`cold_lock_path`、`hot_db_path`、
  `artifact_root`，并给出四 mode 完整矩阵。
- `tool_trace_cold_lock_path(...)` 与
  `TOOL_TRACE_COLD_FILE_LOCK_TIMEOUT_SECONDS=5.0` 是 producer/reader 唯一共享真源。
- 读取顺序固定为：单一 hot read transaction + watermark → 关闭 transaction → 同一 cold
  lock 下复制完整 bytes → release → strict parse/join。
- hot store 可用但无 rows 时 watermark=`0`；hot store 不可用时才为 `null`。

### 4.2 Read-only / failure

- read-only PRAGMA helper 的允许项与禁止项已枚举。
- cold lock/read failure 和 existing hot DB failure 都是 fatal orchestration error，不进入
  finding/limitation report。
- 只有 absent hot path 可以生成 `hot_store_unavailable`。

### 4.3 Report / rules / tests

- S2 最终 report、finding ordering、limitation、payload measure、run wait counts 与完整 vendor
  block types一次冻结。
- S3 不改 contracts/schema/order/Host/Tool rules。
- `input_changed_during_analysis`、cold record measurement source、known wait facts 与 fixture
  layering 已进入 owner-level validation matrix。

### 4.4 Publication / docs

- partial dual publish 的成功路径、失败路径、旧/新文件状态、temp cleanup 与 CLI 1 已固定。
- 保持四 slices；S4 在同一用户可见闭环内先读 README 约束再按职责更新。

## 5. Explicitly Not Changed

- 未新增 CLI policy flags、`--fail-on` 或 tuning profile。
- 未新增独立 docs slice。
- 未决定 WU-OBS-01 的 Service path discovery 复用方式。
- 未扩 Tool Trace event filter、producer、cold schema、hot schema、EventLog 或 usage/provider
  schema。
- 未采用“目录发现的 corrupt DB 自动降为 cold-only”。
- 未让 S1 预定义尚未被路径消费的 report/vendor public skeleton。
- 未引入旧 schema fixture、compatibility alias、fallback/loose parsing 或下游补偿。

## 6. Validation

- 修后计划对 Controller adjudication 逐项自审：通过；15 项 finding 全部具有唯一 disposition，
  accepted 项均有计划章节/测试映射，rejected/deferred 项未变相进入 scope。
- 计划头部 status/open questions、review disposition、四 slices、S4 docs closeout 与完整
  validation matrix：通过。
- `git diff --check -- docs/host/wu-obs-00-plan.md docs/reviews/wu-obs-00-plan-fix-codex.md`：
  通过。
- 由于两个目标文件均为 untracked，额外执行逐文件
  `git diff --no-index --check /dev/null <file>`：两次均无 whitespace diagnostics；命令
  exit code=`1` 仅表示 `/dev/null` 与目标文件存在内容差异，是 `--no-index` 的预期状态。
- `git status --short`：通过 scope audit；只有 Controller 既有 control/goal/adjudication、
  两路 review、计划与本 fix artifact；无生产代码、测试或 README 变化。
- 代码测试/pyright：未运行；本 gate 只修改 Markdown 计划/artifact，Required validation 未要求
  执行 implementation tests，且禁止进入 implementation。

## 7. Residual Risks / Next Entry

保留 Controller 已分类 residual risks：

- Issue #64 native Anthropic / Claude Code gateway signal：`limited_signal`，owner=Issue #64。
- Issue #36 cold rotation/archive 与极大历史文件治理：owner=Issue #36。
- WU-OBS-01 prompt/final-answer 定位和 Service discovery：owner=WU-OBS-01 plan。
- 两个普通 report 文件不能跨文件原子提交：accepted operator-file residual；typed partial
  publish result 已使失败可判读。

没有 blocking open questions 或未分类 residual risk。下一入口只能是 AgentMiMo 与 AgentDS 对
同一 `docs/host/wu-obs-00-plan.md` 执行独立 plan re-review；本 Agent 不自行推进。

## 8. Actual Changed Files

- `docs/host/wu-obs-00-plan.md`
- `docs/reviews/wu-obs-00-plan-fix-codex.md`

Artifact path：`docs/reviews/wu-obs-00-plan-fix-codex.md`。
