# Documentation Review — WU-CLI-SESSION-01 S6

## Scope

- Mode: current changes（文档同步）
- Branch: wu-cli-session-01
- Base: 653c9966 (accepted plan commit)
- Output file: docs/reviews/code-review-wu-cli-session-01-s6-ds-20260616.md
- Included scope:
  - `docs/host/design.md` — `list_sessions` 加入 public API 列表/行为矩阵/接口分层/CLOSED 状态描述，CLI resume 与 Host wait-resume 术语边界
  - `dayu/host/README.md` — handle 方法列表、包根 facade、Host 专属契约、稳定边界中加入 `list_sessions`
  - `dayu/README.md` — Host public contract 总览中加入 Session 列表读取结果与 typed read view 说明
  - `tests/README.md` — CLI 段覆盖 `--new-session` 删除 + session 全命令面 + existing-session 入口；Host 段覆盖 `list_sessions`/空库边界/解码 fail-closed
  - `docs/reviews/wu-cli-session-01-s6-doc-sync-codex.md`
- Excluded scope:
  - `docs/engine/design.md`（有意未修改，见下文）
  - `docs/host/issues-implementation-control.md`（controller bookkeeping）
  - 生产代码与测试代码（S6 纯文档 slice）
- Parallel review coverage: 无

## Findings

未发现实质性问题。

### 逐项确认

**1. 只写当前已实现事实，不写未来计划或用户手册**

| 文档 | 新增内容 | 事实依据 |
|---|---|---|
| `docs/host/design.md` | `list_sessions` 加入 public API 列表 | S1 已实现 |
| `docs/host/design.md` | `list_sessions` 标记为 Phase 4 "完整实现" | S1 已实现 |
| `docs/host/design.md` | CLI session resume 术语边界 | S5 已实现 |
| `dayu/host/README.md` | `list_sessions()` handle 方法与包根 facade | S1 已实现 |
| `dayu/host/README.md` | `SessionListItem / ListSessionsResult` 为 Host 专属契约 | S1 已实现 |
| `dayu/README.md` | "Session 列表读取结果"纳入 typed read view | S1 已实现 |
| `tests/README.md` | CLI `--new-session` 用法错误、session 全命令面、existing-session 入口 | S2/S3/S4/S5 已实现 |
| `tests/README.md` | Host 段 `list_sessions`/空库边界/解码 fail-closed | S1 已实现 |

未出现"计划实现""后续版本""将支持"等未来计划表述，未出现 CLI 使用示例或教程性质内容。

**2. `list_sessions` 表述为 Host durable read truth / typed read view**

三处关键描述一致且准确：

- `docs/host/design.md`：`"从 durable truth 读取全部未 purge Session 的列表摘要，不触发 projection worker 或执行"`（行为矩阵）；`"它直接来自 durable Session / slot / Run state truth，不是 projection，也不触发 projection catch-up 或执行"`（接口分层）
- `dayu/host/README.md`：`"从 durable Session / slot / Run state truth 生成全部未 purge Session 的列表摘要，不读取 projection truth，不触发 projection catch-up，也不启动执行"`（稳定边界）
- `dayu/README.md`：`"只返回 Host durable truth 或明确的派生 read view，不触发执行"`（contract 总览）

**3. CLI session resume 与 Host wait-resume 区分清楚**

`docs/host/design.md` 新增术语边界段落（CLOSED 状态描述之后）：

> CLI `session resume` 与 Host wait-resume 是两个不同术语。CLI resume 只是 UI / Service adapter 选择一个已有 `OPEN` Session，再提交新的 `submit_followup(queue)` 输入；它不恢复旧 Agent、Runner、Engine generator 或 Attempt，也不解析 Host wait record。Host wait-resume 只指 `resolve_wait` 接收外部等待结果后，让同一个 `WAITING` Run 创建新的 resume Attempt 并继续收口。

- CLI resume = `submit_followup(queue)` on existing OPEN Session ✓
- Host wait-resume = `resolve_wait` → new resume Attempt on WAITING Run ✓
- 明确否定："不恢复旧 Agent、Runner、Engine generator 或 Attempt" ✓
- 位置恰当：放在 CLOSED 状态描述与 `purge_session` 描述之间，与 Session 生命周期上下文邻接 ✓

**4. `dayu/host/README.md` 与 `dayu/README.md` README Agent 约束合规**

`dayu/host/README.md` 约束要求只写已实现接口与公共契约。本次新增：
- handle 方法列表中加 `list_sessions()` — 已实现 ✓
- 包根 facade 列表中加 `list_sessions` — 已实现 ✓
- Host 专属契约中加 `SessionListItem / ListSessionsResult` — 已实现 ✓
- 稳定边界中加 `list_sessions` typed read view 说明 — 已实现 ✓
- 未写未来计划、未写 CLI 用法、未写用户手册 ✓

`dayu/README.md` 约束要求只做跨包 Host public contract 总览。本次新增：
- 核心类型中加入"Session 列表读取结果" — contract 总览 ✓
- 读取语义中加入 `list_sessions` 作为 typed read view 示例 — contract 语义 ✓
- 未写 CLI 用户手册、未扩写 Host 内部机制 ✓

**5. `tests/README.md` 只记录当前测试事实**

CLI 段更新覆盖：
- `interactive` 默认 fresh anonymous + label binding + `--new-session` 用法错误 + existing-session 入口 ✓（S2/S5 事实）
- `session` 命令 list/resume/purge 全命令面 + selector 解析 + TOCTOU + INVALID_STATE + 成功输出 ✓（S3/S4/S5 事实）
- 输出不展示内部治理字段 ✓（S3 事实）

Host 段更新：
- `list_sessions` 加入 command handle / public session API 列表 ✓（S1 事实）
- 空库边界、slot row 解码 fail-closed ✓（S1 fix 事实）

**6. `docs/engine/design.md` 正确未修改**

Engine 设计语义未变：run-scoped Agent/Runner 边界保持，Session 生命周期仍归 Host。CLI `session resume` 是 UI adapter 通过 Host public `submit_followup(queue)` 提交新输入，不触及 Engine public contract。S6 report 明确记录"已核对...不冲突，因此未修改"。✓

**7. Control doc 无事实矛盾**

`docs/host/issues-implementation-control.md` 当前 gate 为 `code review`，active work unit 为 `WU-CLI-SESSION-01`，与 S6 文档同步状态一致。无矛盾。

## Open Questions

无。

## Residual Risk

- 文档同步覆盖了 S6 plan 指定的全部范围（`docs/host/design.md`、`dayu/host/README.md`、`dayu/README.md`、`tests/README.md`），但未做全仓文档审计。非 S6 scope 的文档（如 `dayu/fins/README.md`、`dayu/service/README.md`）若存在过时的 Session 管理相关描述，不在本次覆盖范围内。
