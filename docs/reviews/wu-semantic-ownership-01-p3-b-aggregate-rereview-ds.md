# P3-B Aggregate Re-Review — F01 Fix Verification

## Gate

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / P3-B`
- Gate: aggregate re-review（controller accepted `P3-B-AGG-F01` 修复复核）
- Input:
  - Aggregate review（DS）: `docs/reviews/wu-semantic-ownership-01-p3-b-aggregate-deepreview-ds.md`
  - Aggregate review（MiMo）: `docs/reviews/wu-semantic-ownership-01-p3-b-aggregate-deepreview-mimo.md`
  - Controller adjudication: `docs/reviews/wu-semantic-ownership-01-p3-b-aggregate-deepreview-controller-adjudication.md`
  - Fix artifact: `docs/reviews/wu-semantic-ownership-01-p3-b-aggregate-fix-codex.md`
  - Fix controller validation: `docs/reviews/wu-semantic-ownership-01-p3-b-aggregate-fix-controller-validation.md`
  - Accepted plan: `docs/host/wu-semantic-ownership-01-p3-b-terminal-final-answer-outbox-plan.md`

## Scope

- **Mode**: current changes（P3-B-AGG-F01 fix only）
- **Branch**: `phaseflow/host-issues-control`
- **Base**: `08394e52`（P3-B S1 acceptance，aggregate review head）
- **Working tree dirty files**:
  - `dayu/host/read_api.py` — F01 fix（production）
  - `tests/host/test_public_outbox_api.py` — F01 fix（test）
  - `docs/host/issues-implementation-control.md` — 无关变更（非本 WU 产出）
- **Output file**: `docs/reviews/wu-semantic-ownership-01-p3-b-aggregate-rereview-ds.md`
- **Non-goals**: 不修改代码、CLI-CI、commit、push、PR

## 验证矩阵

| 验证项 | 结果 |
|---|---|
| P3-B 聚焦测试（77 个） | 全部通过（含新增 2 个 blank finish_reason case） |
| P3-B propagation regression（305 个） | 全部通过 |
| pyright（dayu/host/） | 0 errors, 0 warnings, 0 informations |
| git diff --check | 通过（无空白诊断） |

---

## F01 修复逐项复核

### 1. raw durable Outbox finish_reason 空/空白 → public read HostApiError(INTERNAL_ERROR) + Outbox-specific HostDurableError cause

**结论: 已修复。**

`read_api.py:857-860`（`_final_answer_from_outbox_json` 内）新增：

```python
if finish_reason is not None and finish_reason.strip() == "":
    raise HostDurableError(
        "Outbox final answer field finish_reason must be non-empty text"
    )
```

**检查项：**

| 子项 | 结果 | 证据 |
|---|---|---|
| 空串 `""` 被拒绝 | ✓ | `.strip() == ""` 覆盖空串 |
| 纯空白 `" \t\n"` 被拒绝 | ✓ | `.strip() == ""` 覆盖纯空白 |
| `None` 正常通过 | ✓ | `finish_reason is not None` 短路 |
| 合法非空文本 `"stop"` 正常通过 | ✓ | `isinstance` + `.strip() != ""` 均通过 |
| 非文本值（`123`）仍被类型检查拒绝 | ✓ | 行 855-856 的 `isinstance(finish_reason, str)` 先于空白检查 |
| 错误类型为 `HostDurableError` | ✓ | 直接 `raise HostDurableError(...)` |
| 错误消息含 `Outbox` / `finish_reason` / `non-empty` | ✓ | 完整诊断: `"Outbox final answer field finish_reason must be non-empty text"` |
| 错误消息与 `content` 空白检查对称 | ✓ | `content` 检查消息: `"Outbox final answer field content must be non-empty text"` |

**错误传播链完整验证：**

```text
_read_outbox_terminal_items (public API)
  → _run_read (command.py:327-328)
  → catch HostDurableError → _host_api_error_from_durable_error(exc) from exc
  → HostApiError(code=INTERNAL_ERROR, message="Host durable operation failed")
  → __cause__ = 原始 HostDurableError
```

测试 `test_public_outbox_read_rejects_raw_blank_finish_reason`（`test_public_outbox_api.py:190-274`）走 production Host 路径：
1. 创建真实 Outbox item → 获取 `terminal_event_id`
2. 直接 `UPDATE host_outbox_terminal_items SET final_answer_json = corrupted_json`
3. public `read_outbox_terminal_items` → `HostApiError(INTERNAL_ERROR)`
4. `__cause__` 为 `HostDurableError` 实例
5. 诊断含 `"Outbox"` + `"finish_reason"` + `"non-empty"`

### 2. HostFinalAnswerView 保留，无转换/兼容

**结论: 已验证。**

`HostFinalAnswerView.__post_init__`（`api.py:2745-2748`）仍调用 `_require_optional_non_empty(self.finish_reason, field_name="HostFinalAnswerView.finish_reason")` 进行独立 public validation。本次 fix 没有：

- 删除、捕获、转换或弱化 `HostFinalAnswerView` 的独立校验
- 新增 `hasattr`/`getattr`、兼容 wrapper、fallback 或默认值填充
- 新增跨模块依赖、schema 变更或 DDL 修改

### 3. 正常路径不退化

**结论: 已验证。**

正常 producer 路径中 `finish_reason` 由 `optional_payload_text`（`_event_payload.py:427-444`）校验：`None` 或非空文本。`_final_answer_from_outbox_json` 的新检查仅在 raw SQLite row 被外部 corruption 绕过 producer 时触发。正常路径下 `finish_reason` 值不变、不 trim、不转换。

Propagation regression 305 项全部通过，确认 P3-B 传播链未退化。

### 4. 与 content 空白检查的对称性

**结论: 已对齐。**

| 字段 | 类型检查 | 空白检查 | HostDurableError 消息 |
|---|---|---|---|
| `content` | 行 845-846: `isinstance(content, str)` | 行 847-849: `content.strip() == ""` | `"Outbox final answer field content must be non-empty text"` |
| `finish_reason` | 行 855-856: `isinstance(finish_reason, str)` | 行 857-859: `finish_reason.strip() == ""` | `"Outbox final answer field finish_reason must be non-empty text"` |

两字段的校验层次、错误消息模板、`HostDurableError` 类型完全对称。`filtered`/`degraded`（bool 字段）无空白检查需求，其 `isinstance(x, bool)` 已排除 `None`/非 bool。

---

## Findings

### 未发现实质性问题。

F01 fix 在正确的 owner boundary（durable Outbox JSON → public typed view 的 read parser）补齐了与 `content` 对称的 blank `finish_reason` 防御。错误类型（`HostDurableError`）、错误链（`HostDurableError → HostApiError(INTERNAL_ERROR)` with `__cause__`）、错误消息（Outbox field-specific 诊断）均符合 controller adjudication 要求。`HostFinalAnswerView` 独立 public validation 完整保留。无新增转换、兼容路径或 material defect。

---

## Propagation Audit

### Outbox JSON `finish_reason` 完整传播链

**正常路径（不变）：**
```text
canonical RUN_SUCCEEDED.finish_reason
  → outbox._final_answer_json
  → optional_payload_text（None 或非空文本）
  → canonical final_answer_json
  → durable Outbox row
  → read_api._final_answer_from_outbox_json
     ├── isinstance check（行 855-856）
     ├── blank check（行 857-859）  ← F01 fix
     └── 通过
  → HostFinalAnswerView.__post_init__
     └── _require_optional_non_empty（行 2745-2748，独立 public validation）
  → public Outbox read / drain consumer
```

**raw corruption 路径（F01 fix 加固后）：**
```text
raw SQLite final_answer_json.finish_reason = "" 或纯空白
  → read_api._final_answer_from_outbox_json
  → isinstance check 通过（空白仍为 str）
  → blank check 命中（行 857-859）← F01 fix
  → HostDurableError("Outbox final answer field finish_reason must be non-empty text")
  → HostCommandHandle._run_read（command.py:327-328）
  → _host_api_error_from_durable_error（command.py:1268-1272）
  → HostApiError(INTERNAL_ERROR) with __cause__ = HostDurableError
```

**所有消费路径一致:**
- Live `HostEvent`: `finish_reason` 从 canonical `RUN_SUCCEEDED` payload 读取，不经过 Outbox JSON round-trip
- Outbox read/drain: 经过 `_final_answer_from_outbox_json` → `HostFinalAnswerView`，现在对 blank finish_reason fail closed
- Memory/compact/run-input: 不消费 `finish_reason` 字段，不受影响

---

## Adversarial 审查

### 1. finish_reason 为 JSON `null` 时的行为

`json.loads` 将 JSON `null` 解析为 Python `None`。`_final_answer_from_outbox_json:855` 的 `finish_reason is not None` 短路，不进入任何校验，直接传入 `HostFinalAnswerView(finish_reason=None)`。`HostFinalAnswerView.__post_init__:2745-2748` 的 `_require_optional_non_empty` 接受 `None`。行为正确。

正常 producer 写入 `None` 表示 finish reason 未知；corrupted row 的 `null` 与正常 `None` 无法区分，但这是 raw corruption 无法检测的固有限制，`None` 本身是无害展示元数据，不阻塞 public read。此行为与 P3-B plan 一致。

### 2. 新增测试的隔离性

`test_public_outbox_read_rejects_raw_blank_finish_reason` 使用 `session_id="outbox-raw-blank-finish-reason"` + `run_id="outbox-raw-blank-finish-reason-run"`，与已有的 blank `content` 测试（`session_id="outbox-raw-blank"` + `run_id="outbox-raw-blank-run"`）使用不同的 session/run ID，无并行隔离冲突。

### 3. 错误消息诊断精度

| 场景 | 错误 | 诊断关键字 |
|---|---|---|
| blank content | `HostDurableError("Outbox final answer field content must be non-empty text")` | Outbox, field, content, non-empty |
| blank finish_reason | `HostDurableError("Outbox final answer field finish_reason must be non-empty text")` | Outbox, finish_reason, non-empty |
| non-text finish_reason | `HostDurableError("outbox final answer finish_reason is invalid")` | outbox, finish_reason, invalid |

blank content 与 blank finish_reason 的错误消息共享模板 `"Outbox final answer field {name} must be non-empty text"`，包含 `field` 关键字。non-text finish_reason 的错误消息为旧有（小写开头），与 blank case 的大写开头不一致，但不影响排障可读性。**不构成 material finding** — 这是一种低优先级一致性改进，可在后续统一 Outbox JSON parser 错误消息格式。

### 4. 语义 ownership 确认

| 阶段 | Owner | F01 fix 后状态 |
|---|---|---|
| 事实产生 | Engine / Host terminal closeout | 不改 |
| producer 校验 | `outbox._final_answer_json` → `optional_payload_text` | 不改 |
| durable 持久化 | `host_outbox_terminal_items.final_answer_json` | 不改 DDL |
| **public read 校验** | **`read_api._final_answer_from_outbox_json`** | **F01 fix 落点** |
| public typed contract | `HostFinalAnswerView.__post_init__` | 独立保留 |
| public error 投影 | `_host_api_error_from_durable_error` | 保持 INTERNAL_ERROR |

无 semantic ownership drift。F01 fix 的 owner boundary 与已修复的 `content` blank check 完全一致。

---

## Open Questions

无。

---

## Residual Risk

| 项目 | Owner | 说明 |
|---|---|---|
| P3-J DDL conditional CHECK | P3-J | SQLite 无 `CHECK` 约束禁止 succeeded row 带空白 finish_reason；四层覆盖（producer + durable validator + public JSON parser + public dataclass） |
| descriptor 自动 repair | P3-J / storage hardening | P3-B 只保证 failure 可观察、可 retry |
| Outbox JSON parser 错误消息大小写一致性 | 无（Low priority） | blank content/blank finish_reason 用大写 `"Outbox..."`，non-text finish_reason 用小写 `"outbox..."`；纯风格，不影响排障 |

---

## F01 最终状态

| Finding | 状态 | 证据 |
|---|---|---|
| **P3-B-AGG-F01** — blank Outbox `finish_reason` diagnostic boundary | **已修复** | parser 显式拒绝空串/纯空白并抛 field-specific `HostDurableError`；2 个参数化 raw SQLite → public read case 证明 `HostApiError(INTERNAL_ERROR)` + `HostDurableError` cause；`HostFinalAnswerView` 独立校验完整保留，无转换/兼容 |

## 新 Finding 数

**0** — 无新增 material defect。

## Verdict

**P3-B-AGG-F01: FIXED — PASS.**

Aggregate fix 在正确的 owner boundary（`_final_answer_from_outbox_json` durable Outbox JSON parser）补齐了 blank `finish_reason` 防御，与已修复的 `content` blank check 完全对称。错误链（`HostDurableError → HostApiError(INTERNAL_ERROR)` with `__cause__`）、错误消息（Outbox field-specific diagnostic）、`HostFinalAnswerView` 独立 public validation 均符 controller adjudication 要求。P3-B 传播链 77 focused + 305 propagation 全部通过，pyright 零报错。

## Residual Owners

| Residual | Owner |
|---|---|
| P3-J DDL conditional CHECK | P3-J |
| descriptor automatic repair | P3-J / storage hardening（出现直接产品需求时） |
| optional-material strictness | P3-C / design adjudication |
| writer/reader field constants | 已裁决为 private projection detail |
| Outbox JSON parser 错误消息大小写统一 | 低优先级，可纳入后续 Host hardening |

Artifact: `docs/reviews/wu-semantic-ownership-01-p3-b-aggregate-rereview-ds.md`
