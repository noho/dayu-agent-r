# WU-SEMANTIC-OWNERSHIP-01 P3-B aggregate re-review — AgentMiMo

## Scope

- Gate: aggregate re-review（P3-B-AGG-F01 修复后独立复核）。
- 输入: controller adjudication、fix artifact、fix controller validation、accepted plan。
- 复核范围: `P3-B-AGG-F01` 在当前 working tree 的完整修复，新增 material defect 扫描。
- Branch: `phaseflow/host-issues-control`。
- Base: `main`。
- Working tree status: `dayu/host/read_api.py` unstaged dirty（AGG-F01 fix）+ `tests/host/test_public_outbox_api.py` unstaged dirty（AGG-F01 test）。
- 时间戳: 20260710-154438。

## P3-B-AGG-F01 复核结论: 完整修复，无退化

### 修复落点验证

`dayu/host/read_api.py:857-860` — `_final_answer_from_outbox_json` 在类型检查之后、`terminal_status` 校验之前，对非 `None` 的 `finish_reason` 执行非空白校验:

```python
if finish_reason is not None and finish_reason.strip() == "":
    raise HostDurableError(
        "Outbox final answer field finish_reason must be non-empty text"
    )
```

- **空串 `""`**: `strip() == ""` → raise。
- **纯空白 `" \t\n"`**: `strip() == ""` → raise。
- **合法非空文本 `"stop"`**: `strip() != ""` → pass through to `HostFinalAnswerView`。
- **`None`**: `finish_reason is not None` 短路 → pass through（`None` 表示未知 finish reason，是合法状态）。

诊断信息包含 `Outbox`、`finish_reason`、`non-empty` 三个语义标记，与既有 `content` blank 处理对称，符合 field-specific durable diagnostic 要求。

### 错误传播链验证

```text
_final_answer_from_outbox_json
  → HostDurableError("Outbox final answer field finish_reason must be non-empty text")
  → _outbox_item_from_row (read_api.py:811)
  → _outbox_batch_from_page (read_api.py:753)
  → _ReadOutboxTerminalItemsOperation.__call__ (read_api.py:568-590)
  → HostCommandHandle._run_read (command.py:317-328)
    except HostDurableError as exc:
        raise _host_api_error_from_durable_error(exc) from exc
  → _host_api_error_from_durable_error fallback (command.py:1268-1272):
      HostApiError(code=INTERNAL_ERROR, retryable=False)
      __cause__ = 原 HostDurableError
```

cause chain 完整保留: `public_error.value.__cause__` 是 `HostDurableError` 实例，`HostApiErrorCode.INTERNAL_ERROR` 是唯一映射。

### HostFinalAnswerView 独立校验

`HostFinalAnswerView.__post_init__` 仍独立调用 `_require_optional_non_empty` 校验 `finish_reason`。本次未删除、捕获、转换或弱化该校验。直接构造 public contract 与 raw durable read 各自在自己的 owner boundary fail closed。

运行时验证:
- `HostFinalAnswerView(content='answer', filtered=False, degraded=False, finish_reason='', terminal_status=SUCCEEDED)` → `ValueError: HostFinalAnswerView.finish_reason must be non-empty`
- `HostFinalAnswerView(content='answer', filtered=False, degraded=False, finish_reason=None, terminal_status=SUCCEEDED)` → 正常构造

### 测试覆盖

`test_public_outbox_read_rejects_raw_blank_finish_reason` 参数化注入 `""` 和 `" \t\n"`:

1. 使用 production Host 先生成真实 Outbox item。
2. 直接用 `sqlite3.connect` 更新 raw SQLite `final_answer_json`，注入损坏的 `finish_reason`。
3. 调用 `host.read_outbox_terminal_items` 触发 public read。
4. 断言 `HostApiError(INTERNAL_ERROR)`、`isinstance(__cause__, HostDurableError)`、诊断包含 `Outbox` + `finish_reason` + `non-empty`。

测试不 mock、不 patch、不绕过任何层; 从 raw durable corruption 到 public error 的完整路径被覆盖。

### 无转换/兼容确认

fix artifact 声明 "不 trim、不替换、不填默认值、不捕获或转换 `HostFinalAnswerView` 的独立校验"。diff 确认:

- 无 `try/except ValueError` 包裹 `HostFinalAnswerView` 构造。
- 无 `finish_reason.strip()` 结果回写。
- 无默认值填充。
- `_final_answer_from_outbox_json` 只做 reject-or-pass-through，不做 normalize。

## 验证结果

| 验证项 | 结果 |
|---|---|
| focused P3-B matrix | **77 passed in 1.05s** |
| pyright | **0 errors, 0 warnings, 0 informations** |
| `git diff --check` | **clean** |
| propagation regression | **290 passed in 1.91s** |
| `HostFinalAnswerView` 独立校验 | **runtime verified** |

## 新增 material defect 扫描

对当前 working tree 的 `read_api.py` 和 `test_public_outbox_api.py` 做 adversarial pass:

1. **`_final_answer_from_outbox_json` 完整性**: `content`（必填非空 str）、`filtered`（必填 bool）、`degraded`（必填 bool）、`finish_reason`（可选非空 str）、`terminal_status`（必填 `succeeded`）— 全部字段有独立校验，无遗漏。
2. **`HostFinalAnswerView` conditional invariant**: succeeded 必须有 final_answer，failed/cancelled/lost 禁止 final_answer — `test_public_outbox_terminal_final_answer_invariants` 覆盖。
3. **raw SQLite corruption 其它字段**: `content` blank 已有对称测试; `filtered`/`degraded` 非 bool、`terminal_status` 非 `succeeded` 均被 parser 拦截。无新增 attack surface。
4. **Outbox projection catch-up failure**: `test_public_outbox_reports_lagged_then_catches_up` 覆盖 LAGGED → CAUGHT_UP 恢复路径。
5. **drain 幂等冲突**: `test_public_outbox_session_not_found_and_drain_conflict` 覆盖。
6. **closed handle**: `test_public_outbox_validation_and_closed_handle` 覆盖。

未发现新增 material defect。

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

| Residual | 分类 / owner | 状态 |
|---|---|---|
| Outbox DDL conditional `CHECK` | P3-J | 不在 P3-B 修改 schema; producer、durable validator 与 public read 继续 fail closed |
| descriptor automatic repair | P3-J / storage hardening | 本 gate 不新增 repair API 或兼容路径 |
| optional-material strictness | P3-C / design adjudication | 本 gate 不改变 optional resolver policy |
| writer/reader field constants | controller 已裁决为 private projection detail | 行为测试足以保护，不新增共享 registry |

没有未分类 residual risk。

## F01 最终状态

| Finding | 状态 | 证据 |
|---|---|---|
| P3-B-AGG-F01 blank Outbox `finish_reason` diagnostic boundary | **已修复** | parser 显式拒绝空串/纯空白并抛 field-specific `HostDurableError`; 2 个 raw SQLite → public read case 证明 `HostApiError(INTERNAL_ERROR)` 与 durable cause; propagation chain 未退化; HostFinalAnswerView 独立校验未被修改 |

## Verdict

**PASS**。P3-B-AGG-F01 在当前 working tree 完整修复，无新增 material defect，P3-B 传播链未退化。

## Residual owners

全部 residual 已有明确 owner，无未分类项。
