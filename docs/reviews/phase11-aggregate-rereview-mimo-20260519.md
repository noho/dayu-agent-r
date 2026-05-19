# Phase 11 Aggregate Fix Re-review — AgentMiMo — 2026-05-19

## Verdict: PASS

P11-AGG-F1 与 P11-AGG-F2 已收口，未引入新 blocker。Phase 11 可推进到 accepted aggregate fix commit / ready-to-open-draft-PR。

---

## 1. Review Scope

- **Fix artifact**: `docs/reviews/phase11-aggregate-fix-codex-20260519.md`
- **Adjudication artifact**: `docs/reviews/phase11-aggregate-deepreview-controller-adjudication-20260519.md`
- **Aggregate review artifacts**: `docs/reviews/phase11-aggregate-deepreview-mimo-20260519.md`, `docs/reviews/phase11-aggregate-deepreview-ds-20260519.md`
- **Diff files**: `dayu/host/durable/state.py`, `dayu/host/durable/run_transition.py`, `dayu/host/recovery.py`, `docs/host/implementation-control.md`
- **审查角色**: AgentMiMo，strict re-review specialist，不修改文件、不提交

---

## 2. 验证命令结果

| 命令 | 结果 |
|------|------|
| `pytest tests/host/test_recovery_scan.py tests/host/test_run_attempt_transitions.py tests/host/test_public_cancel_session_runs.py -q` | **50 passed** (0.53s) |
| `pytest tests/host -q` | **793 passed, 1 skipped** (54.79s) |
| `pytest tests/runtime -q` | **107 passed** (1.98s) |
| `python -m pyright dayu/host dayu/runtime tests/host tests/runtime` | **0 errors, 0 warnings, 0 informations** |
| `git diff --check` | **clean** |

---

## 3. P11-AGG-F1 收口验证

### 改动摘要

- `state.py` 新增 `cancel_recovering_run_row(...)`（line 3339-3394），使用 `_validate_run_terminal_update(...)` 做输入校验，SQL CAS 条件与结果分类（UPDATED / NOT_FOUND / CAS_LOST）与其他 terminal helper 一致。
- `run_transition.py` 改为 import 并调用 `cancel_recovering_run_row(...)`（line 50, 2402），删除旧私有 `_cancel_recovering_run_row(...)`（原 line 2751-2814），移除不再需要的 `serialize_run_status` 和 `TABLE_HOST_RUNS` 导入。

### 正确性验证

| 检查项 | 结果 |
|--------|------|
| 新 helper SQL 逻辑与旧私有函数一致 | PASS：CAS 条件（`WHERE run_id = ? AND status = 'recovering' AND terminal_event_id IS NULL AND terminal_event_sequence IS NULL AND terminal_at IS NULL`）、SET 子句、result 分类逻辑完全一致 |
| 输入校验一致性 | PASS：新 helper 使用 `_validate_run_terminal_update(...)`，与 `terminal_recovering_run_row(...)` 等同类 helper 统一；旧私有函数使用分散的 `_require_*` 调用，已被替换 |
| `run_transition.py` 不再直接引用 `TABLE_HOST_RUNS` | PASS：`grep TABLE_HOST_RUNS run_transition.py` 无结果 |
| `run_transition.py` 不再导入 `serialize_run_status` | PASS：import 行已移除 |
| `cancel_recovering_run_in_transaction(...)` 调用路径正确 | PASS：line 2402 改为调用 `cancel_recovering_run_row(...)`（state.py 公开函数），参数签名匹配 |

### 架构边界验证

PASS。RECOVERING cancel 的 Run-row CAS mutation 归属 `dayu.host.durable.state`，`run_transition.py` 只编排 EventLog append + state helper 调用。符合"数据处理、存储、工具调用职责分离"和"重复逻辑必须抽取"。

---

## 4. P11-AGG-F2 收口验证

### 改动摘要

- `recovery.py` line 58：在 `_DEFAULT_STALE_AFTER_SECONDS = 30` 上方新增注释 `# heartbeat 周期必须显著小于 stale 阈值，避免破坏 positive orphan proof。`

### 正确性验证

PASS。注释位于常量定义正上方，明确表达了 heartbeat interval 必须显著小于 stale threshold 的约束关系，与 `StartupRecoveryPolicy.default()` docstring（line 110: "stale 阈值大于 Slice 1 scheduler heartbeat 周期"）形成互补。不改变 policy 值、不新增 public option。

---

## 5. 新 Blocker 检查

无。

### Diff 边界审查

| 检查项 | 结果 |
|--------|------|
| 仅修改指定文件 | PASS：diff 只涉及 `state.py`、`run_transition.py`、`recovery.py`、`implementation-control.md` 共 4 文件 |
| 未修改 Engine / public API / schema | PASS |
| 未引入新依赖 | PASS：`state.py` 使用已有的 `_validate_run_terminal_update`、`RunMutationResult`、`StateMutationStatus` 等内部符号 |
| 未引入 `Any` / `object` 类型 | PASS：pyright 0 errors |
| 未引入魔法数字 / 字符串 | PASS：SQL 使用常量 `TABLE_HOST_RUNS`、`serialize_run_status(RunStatus.RECOVERING/CANCELLED)` |
| docstring 完整 | PASS：新函数有完整中文 docstring 含参数、返回值、异常 |

### 隔离性验证

- fix 不改变 recovery policy、dispatch heartbeat、public cancel 语义或 durable schema
- 既有 focused tests（50 passed）已覆盖 RECOVERING cancel、startup recovery scan 与 public cancel session/run 行为
- 全量 host tests（793 passed, 1 skipped）和 runtime tests（107 passed）无回归

---

## 6. Control Doc Gate 状态验证

`docs/host/implementation-control.md` diff 更新：

- 当前 gate 改为 `Phase 11 aggregate re-review`，下一 gate 改为 `Phase 11 accepted aggregate fix commit / ready-to-open-draft-PR`：正确反映当前流程位置
- 新增 3 条 gate 追加事实：Slice 5 accepted commit → aggregate deepreview → aggregate fix，记录完整历史链
- 纯 gate 状态追踪更新；不修改设计、不引入新约束

---

## 7. Conclusion

P11-AGG-F1（RECOVERING cancel Run-row CAS helper 下沉到 durable state boundary）和 P11-AGG-F2（heartbeat interval / stale threshold 安全关系注释）均已收口。改动精确、边界清晰、验证完整。未引入新 blocker。

**PASS。**
