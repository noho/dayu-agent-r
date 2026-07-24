# WU-OBS-00 Plan Review Controller Adjudication

## 1. Scope

- Work Unit：`WU-OBS-00`
- 被审计划：`docs/host/wu-obs-00-plan.md`
- 第一路 review：`docs/reviews/plan-review-20260724-110330.md`
- 第二路 review：`docs/reviews/plan-review-20260724-110122.md`
- Gate 结论：`plan-fix-required`
- Blocking open questions：None。以下 accepted findings 已由 Controller 给出确定修复方向，
  不需要 implementation agent 或 reviewer 重新做架构选择。

## 2. First-principles conclusion

两路 review 都确认当前方案的动机、`CLI -> Service -> Host` 分层、只读 analyzer owner、
provider identity 禁止推断边界与四个 slice 的总体切分成立。问题集中在 code-generation-ready
细节：并发文件读取、损坏 hot DB、只读 SQLite PRAGMA、public source 字段和跨 slice contract
handoff 尚未完全闭合。

当前 Work Unit 不应扩 Tool Trace producer/schema。正确修复位置是 analyzer input/public
contract、durable read-only capability、规则/limitation contract 与测试计划，而不是在
Service、CLI 或 renderer 做 fallback。

## 3. Finding adjudication

| Finding | 裁决 | Controller 依据与要求 |
|---|---|---|
| MiMo F001 reader-side file lock contract | accepted | 当前默认 producer 使用相邻 `.lock` 与 `RuntimeFileLock` 包住 cold append。计划必须明确 lock path 的唯一来源、reader 获取同一锁、timeout 和失败分类；不得假设 OS append 原子性，也不得在 Host/Service 各自复制不一致的 lock-path 规则。 |
| MiMo F002 corrupt hot DB fail/degrade 冲突 | accepted，修复方向调整 | CLI 没有独立 `--hot-db` 模式；目录 contract 发现的 DB 也是本次显式输入的一部分。hot path 缺失可产生 `hot_store_unavailable` limitation；hot path 已存在但 open/schema/corruption 失败必须 fail analysis，并映射 exit code 1。operator 若只需 cold 分析，应显式传 cold file。禁止把已存在的损坏 DB 伪装成“未提供”。 |
| MiMo F003 S4 code 与 README 混合 | rejected | S4 是用户可见 CLI/Service/publication 的单一交付闭环，README 决策依赖最终行为；单独建立 docs slice 会增加 gate 成本且留下代码已交付、文档未同步的半成品。保留 S4，但修正 allowed-files 重复项并在 completion signal 中要求先读各 README 更新约束。 |
| MiMo F004 contracts.py 跨 S1/S2/S3 | accepted，和 DS F-DS-02 合并 | 不采用“S1 预定义所有未被路径消费的 public skeleton”。S1 只稳定 input/read-only 所需 contract；S2 必须一次冻结最终 report 顶层 schema、finding ordering 和 vendor block contract；S3 只能追加 Engine/provider rule 结果，不修改 S2 Host/Tool 规则语义、排序或 report schema。 |
| MiMo F005 read-only PRAGMA | accepted | 计划必须命名 read-only PRAGMA helper 及精确设置：`busy_timeout`、`foreign_keys=ON`、`query_only=ON`；明确禁止调用当前会设置 WAL 的 `configure_connection_pragmas`，禁止设置 `journal_mode` / `wal_autocheckpoint`。 |
| MiMo F006 dual publish failure evidence | accepted | publication error 必须分别记录已成功发布和失败的具体路径；测试第二次 replace 失败时的 old/new 组合与临时文件清理。 |
| MiMo F007 CLI policy flags | rejected for current WU | 首版 CLI 使用 report 中可见的默认 policy，WU-OBS-01 可通过 typed Host API 注入 policy；新增 CLI tuning flags 不是 Issue #70 验收要求。 |
| DS F-DS-01 missing stable limitation code | accepted | 为 concurrent watermark 场景定义稳定 limitation reason code，并在 schema、规则表和测试矩阵保持同名；不得误计为 integrity finding。 |
| DS F-DS-02 S2 -> S3 handoff | accepted，和 MiMo F004 合并 | S2 tests 按 `rule_id`/证据断言，不依赖全局 finding 总数；S3 必须复跑 S1/S2 矩阵，并保持已冻结 contract 和规则不回归。 |
| DS F-DS-03 cold-line size semantics | accepted | `cold_line` 是 JSONL projection record bytes，不是 resolved raw payload bytes。计划必须让 measure/report 明确 measurement source；可参与 byte ranking，但不得把它描述成原始 payload 大小。 |
| DS F-DS-04 awaiting/waiting aggregation | accepted | `TOOL_AWAITING` / `RUN_WAITING` 作为 known timeline facts 与 summary 计数保留；首版不因存在或缺失这些事件单独推断故障。只有已有 typed failure/rejection signal 才产生 finding，并补 owner-level 测试。 |
| DS F-DS-05 WU-OBS-01 Service reuse | deferred to WU-OBS-01 | 本 WU 承诺复用 typed Host analyzer/source/report；WU-OBS-01 是否复用当前 Service path discovery 取决于它的 prompt/final-answer 定位输入，当前提前固定会扩大 scope。 |
| DS F-DS-06 fixture policy | accepted | parser syntax/type unit tests可直接构造当前schema的最小合法/非法JSONL；digest、hot/cold join、descriptor/resolver integration必须从production projection生成baseline后做目标破坏。禁止旧schema fixture或让mock成为业务语义owner。 |
| Controller CTRL-PF-01 public source field contract incomplete | accepted | `ToolTraceAnalysisSource` 仅列类型名，未列字段、必填性、mode-specific invariants、path/lock ownership。计划必须给出完整 typed dataclass contract 和校验矩阵，使 S1 无需重新设计。 |
| Controller CTRL-PF-02 S4 allowed files duplicate | accepted | 删除重复的 `dayu/cli/main.py`，保持 allowed-files 清单精确。 |

## 4. Required plan-fix acceptance criteria

AgentCodex 必须只修改计划和新增 plan-fix artifact，不实施代码。修复后的计划至少满足：

1. `ToolTraceAnalysisSource` 字段、类型、必填性、mode-specific validation、cold lock path
   owner 完整自足。
2. cold reader 的锁获取、timeout、失败行为、snapshot 边界与 watermark limitation code 明确。
3. hot DB “缺失可 limited；已存在但不可打开/不可校验则 fatal”与 exit code 一致。
4. read-only SQLite helper 不复用写侧 WAL PRAGMA。
5. S2 冻结最终 report contract，S3 只能追加规则结果；测试断言和复跑矩阵明确。
6. cold-line measurement、known wait events、parser/integration fixture 分层语义明确。
7. dual-file partial publish failure 返回具体成功/失败路径。
8. 保持四 slices；S4 同步 README，但清理重复 allowed file。
9. 同步计划头部状态、open questions、review findings disposition 与 validation matrix。

## 5. Residual risks retained

- Issue #64 native Anthropic / Claude Code gateway signal：`limited_signal`，owner 保持 Issue #64。
- Issue #36 cold rotation/archive 与极大历史文件治理：owner 保持 Issue #36。
- WU-OBS-01 prompt/final-answer 定位和 Service discovery 复用方式：由 WU-OBS-01 plan 裁决。
- 两个普通 report 文件无法跨文件原子提交：接受为 operator-file residual，但失败结果必须可判读。

## 6. Gate transition

`plan review -> plan fix`

修复后必须由 AgentMiMo 与 AgentDS 对同一计划重新执行独立 `/planreview`；两路都明确 pass 且
Controller 裁决无 accepted finding 后，才可创建 accepted plan commit。
