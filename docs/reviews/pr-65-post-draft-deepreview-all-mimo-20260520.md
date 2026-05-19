# PR 65 Post-Draft-PASS Full Repository Deep Review — AgentMiMo

## Scope

- Mode: All Repository
- Branch: `feat/host-phase-11-recovery`
- PR: #65
- Date: 2026-05-20
- Reviewer: AgentMiMo (主 reviewer) + 6 parallel subagents
- Included scope: 全仓生产代码、测试、README、设计文档
- Excluded scope: `docs/reviews/` 下已有 review artifacts、`workspace/` 临时脚本、`utils/` 分析辅助代码
- Parallel review coverage:
  - Subagent 1: recovery core (`recovery.py`, `recovery_process.py`, recovery tests) — 覆盖
  - Subagent 2: durable state (`durable/liveness.py`, `durable/run_transition.py`, `durable/event_log.py`, durable tests) — 覆盖
  - Subagent 3: dispatch/admission/open_host (`dispatch.py`, `admission.py`, `open_host.py`, `command.py`, 相关 tests) — 覆盖
  - Subagent 4: contracts/boundaries (`contracts/`, `host/__init__.py`, import/typing guard tests) — 覆盖
  - Subagent 5: runtime/engine (`runtime/lane.py`, `engine/`, runtime tests) — 覆盖
  - Subagent 6: README/docs sync (全部 README, design docs) — 覆盖

## Verification Results

| 检查项 | 结果 |
|--------|------|
| `git status --short` | clean |
| `git diff --check main...HEAD` | 无 whitespace violation |
| `pytest tests/host -q` | 793 passed, 1 skipped |
| `pytest tests/runtime -q` | 107 passed |
| `pytest tests/ -q` | 1324 passed, 1 skipped |
| `python -m pyright dayu/ tests/ utils/` | 0 errors, 0 warnings, 0 informations |
| `pytest tests/contracts -q` | 48 passed |
| `pytest tests/engine -q` | 376 passed |
| Engine file changes | 0 |
| `dayu/host/__init__.py` changes | 0 |

## Findings

### F1-未修复-中-`cancel_session_runs` 对 STARTING+worker_accepted 瞬态的处理

- **入口/函数**: `_session_cancel_target_for_run` (admission.py)
- **文件(行号)**: `dayu/host/admission.py:4326-4351`
- **输入场景**: RUNNING/CANCELLING Run 的 attempt 处于 STARTING 但 dispatch record 已 worker_accepted（durable 瞬态不一致）
- **实际分支**: attempt 既非 SUSPENDED、也非 pre-dispatch STARTING、也非 RUNNING，返回 None，导致整个 session cancel 以 UNSUPPORTED_OPERATION 失败
- **预期行为**: 正常状态机流转下不应出现此组合（STARTING+worker_accepted 应很快转为 RUNNING），但 durable 瞬态不一致时 cancel_session_runs 会被阻断
- **直接证据**: `_session_cancel_target_for_run` 中 RUNNING/CANCELLING 分支只处理 SUSPENDED/waiting/active，未覆盖 STARTING+worker_accepted 的 dispatching 状态
- **影响**: 极端边界下 cancel_session_runs 可能被阻断
- **建议改法**: 对 STARTING+worker_accepted 的 dispatching 状态也归入 active worker cancel 子集
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### F2-未修复-中-`_is_direct_cancelable_dispatch_record` 重复逻辑

- **入口/函数**: admission.py `_dispatch_record_is_direct_cancelable` vs command.py `_is_direct_cancelable_dispatch_record`
- **文件(行号)**: `dayu/host/admission.py:4133-4148`, `dayu/host/command.py:1275-1294`
- **输入场景**: 任何需要判断 dispatch record 是否可 direct cancel 的路径
- **实际行为**: 两个模块各自实现了完全相同的判断逻辑
- **预期行为**: 违反"重复逻辑必须抽取"编码约束
- **直接证据**: 两个函数逐字段比较后确认实现一致
- **影响**: 若未来修改判断条件，需同步修改两处，遗漏会导致判断不一致
- **建议改法**: 提取到 `dayu/host/durable/state.py` 或公共位置
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### F3-未修复-中-根目录 README 多处断链与过时措辞

- **入口/函数**: 根目录 README.md
- **文件(行号)**: `README.md:5`, `README.md:19`, `README.md:1169`
- **输入场景**: 用户首次阅读项目 README
- **实际行为**: (1) 第 5 行声称"Host 层正在重写中"，与当前 38 个模块的完整实现不符；(2) 第 19/1169 行引用 `docs/host/interface-discussion-notes.md`，实际文件为 `docs/host/discussion-note.md`；(3) 第 36 行引用 `docs/fmp_integration_research.md`，文件不存在
- **预期行为**: README 应准确反映当前代码状态，链接应指向实际存在的文件
- **直接证据**: `ls dayu/host/` 输出 38 个文件；`ls docs/host/` 无 `interface-discussion-notes.md`；`find docs -name "*fmp*"` 无结果
- **影响**: 用户体验差，首次阅读者会误解项目状态
- **建议改法**: 删除"重写中"措辞，修正两处断链
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中（影响用户体验，不影响功能）

### F4-未修复-低-Host README 代码阅读顺序遗漏 recovery 模块

- **入口/函数**: dayu/host/README.md 代码阅读顺序
- **文件(行号)**: `dayu/host/README.md:283-292`
- **输入场景**: 开发者按阅读顺序理解 Host 代码
- **实际行为**: 代码阅读顺序只列 8 项，止于 `dayu.host.durable`，未包含 `dayu.host.recovery` 和 `dayu.host.recovery_process`
- **预期行为**: Phase 11 新增的 recovery 模块应列入阅读顺序
- **直接证据**: 第 181 行已引用 `dayu.host.recovery_process` 和 `dayu.host.recovery`，但阅读顺序未更新
- **建议改法**: 追加第 9 项
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### F5-未修复-低-heartbeat 致命退出后 scheduler 未关闭

- **入口/函数**: `_host_instance_heartbeat_loop` (dispatch.py)
- **文件(行号)**: `dayu/host/dispatch.py:1619-1631`
- **输入场景**: heartbeat write 遇到非 retryable 致命异常（如 SQLite 磁盘满）
- **实际行为**: 心跳循环退出，调用 `_best_effort_mark_host_instance_stopping`，但 scheduler 的 drain loop 和 promotion loop 继续运行
- **预期行为**: heartbeat 退出后 scheduler 可能继续 dispatch 新 Run，这些 Run 的 owner 指向已标记 stopping 的 instance
- **直接证据**: `return` 仅退出心跳循环，未设 `_closed = True`
- **影响**: 在 heartbeat 退出后、recovery scanner 介入前的窗口内，新 dispatch 的 Run 可能在 recovery 阶段被误判为 orphan。概率极低
- **建议改法**: heartbeat 致命退出后触发 scheduler graceful close
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### F6-未修复-低-clean EOF 后无 terminal 的 Run 残留

- **入口/函数**: `_consume_worker_events` (dispatch.py)
- **文件(行号)**: `dayu/host/dispatch.py:2643-2661`
- **输入场景**: worker event stream clean EOF 但 `close_clean_eof` 未成功写入 terminal
- **实际行为**: 仅记录 CRITICAL 日志，Run 停留在 RUNNING 状态
- **预期行为**: 极端边界（Engine bug 导致无 terminal 的 clean EOF），Run 永久残留
- **直接证据**: `run_terminal_closed` 为 False 时仅 log，无强制 closeout
- **建议改法**: 追加强制 terminal closeout（FAILED/LOST）
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### F7-未修复-低-`_validate_policy` 校验逻辑不一致

- **入口/函数**: `_validate_policy` (recovery_process.py:377 vs recovery.py:546)
- **文件(行号)**: `dayu/host/recovery_process.py:377`, `dayu/host/recovery.py:546`
- **输入场景**: 同一 policy 对象的校验
- **实际行为**: recovery_process.py 同时检查 `tzinfo is None` 和 `utcoffset() is None`；recovery.py 只检查 `tzinfo is None`
- **预期行为**: 两个校验函数应对同一语义做等价检查
- **直接证据**: 行号如上
- **建议改法**: 统一为只检查 `tzinfo is None`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### F8-未修复-低-`_status_placeholders` 丢弃返回值

- **入口/函数**: `_status_placeholders` (liveness.py)
- **文件(行号)**: `dayu/host/durable/liveness.py:440-449`
- **输入场景**: 任何 liveness UPDATE 操作
- **实际行为**: 调用 `_status_values(statuses)` 纯为副作用（验证非空），返回值被丢弃
- **预期行为**: 验证逻辑应直接内联
- **直接证据**: `_status_values(statuses)` 返回值未使用
- **建议改法**: 内联验证或提取无返回值辅助
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## §27/§27.1 合规性逐项验证

| 设计要求 | 实现位置 | 状态 |
|---------|---------|------|
| Host 启动时必须执行 recovery scan | `open_host.py:461-466` | ✅ |
| ACCEPTED/QUEUED/WAITING Run 保持原状态 | `recovery.py:225-238` | ✅ |
| RUNNING/CANCELLING 需 positive orphan proof | `recovery.py:303-349`, `recovery_process.py` classifier | ✅ |
| CAS ATTEMPT_LOST -> RUN_RECOVERING -> new Attempt | `run_transition.py:1325-1566` | ✅ |
| 新 Attempt + 新 execution_id + start_reason=recovery | `run_transition.py:1522-1558` | ✅ |
| 每 Run 最多 1 次 automatic recovery dispatch | `recovery.py:265-301`, `event_log.py:601-626` | ✅ |
| RECOVERING -> CANCELLED (dispatch 前) | `admission.py:1695-1757` | ✅ |
| RECOVERING -> RUNNING (dispatch 创建新 Attempt) | `run_transition.py:1526-1539` | ✅ |
| RECOVERING -> LOST (超过上限) | `run_transition.py:1426-1484` | ✅ |
| Graceful shutdown | `dispatch.py:1548-1580` | ✅ |
| host_instance_id 不是 lease | 设计文档 §27.1 明确声明 | ✅ |
| 旧 Attempt takeover 禁止 | 始终创建新 Attempt | ✅ |
| Recovery 输入仅限 durable truth | scanner 只读 Run/Attempt/dispatch/liveness rows | ✅ |
| 多进程不可用"不可确认控制"代替 orphan proof | `recovery_process.py` 只用 durable + process evidence | ✅ |

## 边界检查

### No Engine changes

`git diff main...HEAD --name-only | grep '^dayu/engine/'` — 无输出。✅

### Public API preservation

- `open_host(options)` 签名不变，内部新增 startup recovery scan
- `cancel_run` / `cancel_session_runs` 签名不变，覆盖范围扩展至 RECOVERING
- `Host` Protocol 不变
- `OpenHostOptions` 不变
- 无新增 public 导出

### dayu.runtime 边界

- `dayu/runtime/lane.py` 无变更（只有 tests/runtime/test_lane.py 新增测试）
- `dayu.runtime` 不 import `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui`。✅

### 架构分层

- `recovery.py` / `recovery_process.py` 只依赖 `dayu.host.durable` 和 `dayu.host.admission`，不反向依赖 Engine / Service / UI。✅
- `recovery_process.py` 是只读 classifier，不写数据库，不推进状态。✅

## Open Questions

无。

## Residual Risk

1. **根 README 断链与过时措辞（F3）**: 非 Phase 11 引入，属 pre-existing 文档质量问题，建议单独修复。
2. **`StdlibPidLivenessProbe` pid 复用盲区**: v1 已知限制，不会误杀 active Attempt，但降低部分 pid 复用场景的 recovery 成功率。后续可通过替换 `ProcessLivenessProbe` 实现解决。
3. **heartbeat 间隔 1s**: 单机部署合理，高密度多进程部署可能需要调优为可配置项。
4. **WAITING recovery 仅 diagnostic**: design doc §27 明确 WAITING Run 只做 diagnostic record，完整 WAITING recovery 需后续 phase 落地。
5. **heartbeat 致命退出后 scheduler 未关闭（F5）**: 极端边界，概率极低，建议后续 hardening。
6. **clean EOF 无 terminal 残留（F6）**: Engine 实现 bug 才会触发，建议后续 hardening。

## Verdict

**PASS**

PR 65 满足 Phase 11 设计要求，全仓代码审查结论：

1. **正确性**: Recovery 状态机、orphan classifier、CAS closeout、recovery dispatch、RECOVERING cancel、graceful shutdown 全部正确实现，与 `docs/host/design.md` §27/§27.1 完全对齐。
2. **稳定性**: 全量 1324 tests passed，pyright 0 errors，无 whitespace violation。多进程 recovery 测试覆盖 live owner 不误杀、crash 后恢复、projection lag 不阻塞。
3. **可维护性**: 架构边界清晰，无反向依赖，无 Engine 变更，public API 保持。8 个 finding 均为中低严重度，无 blocking。
4. **README 同步**: Host README 和 tests README 已更新。根 README 有 pre-existing 断链问题（F3），非 Phase 11 引入。

无 blocking finding。PR 65 可继续推进。
