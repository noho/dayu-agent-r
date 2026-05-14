# Host P4 Aggregate Fix —— Re-Review (AgentDS)

## 审查范围

- **Re-review target**: 上一轮 MiMo aggregate review 中 Finding F-1 (cancel_run docstring Phase 5/7/11 ownership ambiguity) 的 fix
- **Fix artifact**: `docs/reviews/gateflow-aggregate-fix-host-p4-public-api-command-path-20260514.md`
- **Baseline**: 上一轮 AgentDS aggregate review artifact `docs/reviews/gateflow-aggregate-deepreview-host-p4-public-api-command-path-ds-20260514.md`
- **Gate**: Phase 4 Implementation, Public API Command Path (aggregate)

## 变更摘要

### `dayu/host/command.py` —— cancel_run docstring 扩展

**修复前**:
```python
def cancel_run(
    host: HostCommandHandle, run_id: str, request: CancelRunRequest
) -> RunSnapshot:
    """取消单个 Run，并返回最新 Run snapshot。

    :param host: Host command handle。
    ...
```
docstring 没有明确列出各后续 phase 的 cancel 能力 ownership。

**修复后** (lines 357-359):
```python
    """取消单个 Run，并返回最新 Run snapshot。

    Phase 4 只覆盖 queued 与 pre-dispatch ``STARTING``；dispatching /
    active worker 取消由 Phase 5 负责，``WAITING`` 取消由 Phase 7 负责，
    ``RECOVERING`` 取消由 Phase 11 负责。

    :param host: Host command handle。
    ...
```

### `dayu/host/README.md` —— cancel_run 描述扩展

**修复前**:
> `cancel_run(host, run_id, request)`：复用 internal cancel，支持 queued Run cancel 与 pre-dispatch `RUNNING` / Attempt `STARTING` / dispatch `PENDING` cancel；dispatching / active worker、`WAITING`、`RECOVERING` 等后续 owner 能力映射为 `UNSUPPORTED_OPERATION`。

**修复后**:
> `cancel_run(host, run_id, request)`：复用 internal cancel，支持 queued Run cancel 与 pre-dispatch `RUNNING` / Attempt `STARTING` / dispatch `PENDING` cancel；dispatching / active worker 取消由 Phase 5 负责，`WAITING` 取消由 Phase 7 负责，`RECOVERING` 取消由 Phase 11 负责，Phase 4 将这些后续 owner 能力映射为 `UNSUPPORTED_OPERATION`。

### 变更统计

```
git diff HEAD --stat
 dayu/host/README.md  | 2 +-
 dayu/host/command.py | 4 ++++
 2 files changed, 5 insertions(+), 1 deletion(-)
```

## 逐项验证

### 1. MiMo F-1 已修复 —— cancel_run docstring 明确 Phase 5/7/11 ownership

- **command.py:357-359**: `cancel_run` docstring 明确列出 Phase 5（dispatching/active worker）、Phase 7（WAITING）、Phase 11（RECOVERING）
- **结论**: ✓ Fixed

### 2. README cancel_run 描述同步扩展

- **README.md:48**: `cancel_run` 描述与 docstring 一致，列出 Phase 5/7/11 ownership
- **结论**: ✓ Fixed

### 3. cancel_session_runs 的 Phase 5/7/11 提醒保持一致

- **command.py:397-399**: `cancel_session_runs` docstring 早已有 "dispatching / active worker、``WAITING``、``RECOVERING`` 分别由 Phase 5、Phase 7、Phase 11 负责"
- **README.md:49**: `cancel_session_runs` 描述包含 "若存在 dispatching / active worker、``WAITING``、``RECOVERING`` 或其它 unsupported non-terminal Run，会在追加任何 cancel fact 前返回 ``UNSUPPORTED_OPERATION``"
- **README.md:113**: Internal Admission 节记录 "Phase 5 负责 dispatching / active worker cancel，Phase 7 负责 ``WAITING`` cancel，Phase 11 负责 ``RECOVERING`` cancel"
- **结论**: ✓ cancel_session_runs 提醒未被削弱，两处 cancel 函数均明确 Phase 5/7/11 ownership

### 4. 无 scope creep

- 仅 `command.py` 和 `README.md` 两个文件变更
- 5 行增加 + 1 行删除，纯文档硬化的改动量
- command.py 仅 `cancel_run` docstring 块增加了 4 行注释；README.md 仅 `cancel_run` 描述行从通用 "后续 owner 能力" 改为明确的 Phase 5/7/11 映射
- 未修改 admission.py、state.py、event_log.py、read_api.py、api.py、__init__.py 或任何测试文件
- **结论**: ✓ 无 scope creep

### 5. 无行为变更

- `cancel_run` 函数体（lines 368-387）完全未变
- deferred cancel state detection（`_is_deferred_cancel_state`, `_is_predispatch_starting_run`）未变
- UNSUPPORTED_OPERATION 错误消息（line 384: "Run cancel requires a later cancel owner phase"）未变
- admission.py 中 `cancel_run` / `cancel_session_runs` 的 admission 逻辑未变
- **结论**: ✓ 无行为变更

### 6. 测试不回归

```
source .venv/bin/activate && pytest tests/host -q
→ 201 passed in 2.05s

source .venv/bin/activate && python -m pyright dayu/host tests/host
→ 0 errors, 0 warnings, 0 informations
```

- **结论**: ✓ 无回归

## Residual

无。本次 fix 是纯文档硬化，不引入新行为、新状态、新边界或新测试需求。

## Conclusion

**Fixed. No blocking findings.**

MiMo aggregate review Finding F-1 (cancel_run docstring 缺少明确的 Phase 5/7/11 ownership 映射) 已正确修复。`cancel_run` 的 command.py docstring 和 README 描述现在与 `cancel_session_runs` 保持一致，均明确列出各后续 phase 的 cancel 能力 ownership。变更范围限于 2 个文件的 docstring/README 硬化，无行为变更，无 scope creep，201 测试通过，pyright 0 errors。
