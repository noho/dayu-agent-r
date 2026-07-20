# Code Re-Review — WU-SEMANTIC-OWNERSHIP-01 P3-B S1

## Gate

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / P3-B`
- Gate: S1 code re-review（controller adjudication → fix → re-review）
- Controller 真源: `docs/reviews/wu-semantic-ownership-01-p3-b-s1-code-review-controller-adjudication.md`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-p3-b-s1-fix-codex.md`
- 原两路 review: `docs/reviews/wu-semantic-ownership-01-p3-b-s1-code-review-ds.md`、`docs/reviews/wu-semantic-ownership-01-p3-b-s1-code-review-mimo.md`
- Re-review 范围: 仅复核 controller accepted findings P3-B-S1-CR-F01/F02，检查新增 material defect；不重开 rejected/deferred concerns

## Scope

- Mode: current changes（working tree 相对 accepted plan bookkeeping commit）
- Branch: `phaseflow/host-issues-control`
- Base: `4c6ec694`（accepted P3-B plan bookkeeping commit）
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-b-s1-code-rereview-ds.md`
- Included scope: F01/F02 修复涉及的生产代码与测试，以及相关 propagation 路径
- Excluded scope: rejected/deferred concerns（P3-J DDL CHECK、descriptor auto repair、optional-material policy tightening）；CLI-CI 并发文件

## F01 复核 — Outbox public JSON read boundary

### Controller 要求

`_final_answer_from_outbox_json` 在构造 `HostFinalAnswerView` 前显式拒绝 `content == ""` 与纯空白文本，抛出包含 `Outbox` / `field` / `content` 语义的 `HostDurableError`。保留 `HostFinalAnswerView` 的独立 public 校验。测试必须走 production Host 路径污染真实 SQLite raw row，断言 public facade `HostApiError(INTERNAL_ERROR)` 且 cause 带 Outbox field 诊断。

### 代码验证

**生产代码** — `dayu/host/read_api.py:847-850`:

```python
if content.strip() == "":
    raise HostDurableError(
        "Outbox final answer field content must be non-empty text"
    )
```

- 位置: `isinstance(content, str)` 检查（行 845）之后，`HostFinalAnswerView` 构造（行 859）之前。
- 语义: 错误消息包含 `Outbox`、`field`、`content` 三个 controller 要求的关键词。
- `HostFinalAnswerView.__post_init__` 的独立校验保留在 `api.py:2739-2742`，未被移除或绕过。

**测试代码** — `tests/host/test_public_outbox_api.py:105-187`:

- `@pytest.mark.parametrize("content", ("", " \t\n"))` — 覆盖空串与纯空白两种输入。
- 测试流程: production `FinalAnswerWorkerFactory` → `open_host` → `submit_followup` → 等待 `SUCCEEDED` → 通过 `Host.read_outbox_terminal_items` materialize item → 用 `sqlite3.connect` 直接污染 raw SQLite row 的 `final_answer_json.content` → 再次调用 public `Host.read_outbox_terminal_items`。
- 断言: `HostApiError` 且 `.code is INTERNAL_ERROR`；`__cause__` 是 `HostDurableError` 实例；`str(durable_error)` 包含 `"Outbox"`、`"field"`、`"content"`。
- 没有直接调用 private `_final_answer_from_outbox_json`；验证的是完整 public read 路径。

### 判定: FIXED

无兼容转换、无 owner 变更、无 propagation 变更。`HostFinalAnswerView` 校验保留作为第二道防线。

---

## F02 复核 — malformed `finish_reason` 行为测试

### Controller 要求

生产路径已 fail closed，需新增行为测试覆盖非文本 `finish_reason` 在 Outbox projection failure 和 succeeded HostEvent read 两条路径的 fail-closed 行为，断言稳定 `finish_reason` 诊断。不添加兼容转换。

### 代码验证

**Outbox projection failure 路径** — 生产代码 `dayu/host/outbox.py:381-384`:

```python
_PAYLOAD_FIELD_FINISH_REASON: optional_payload_text(
    payload,
    field_name=_PAYLOAD_FIELD_FINISH_REASON,
),
```

`optional_payload_text`（`_event_payload.py:442-444`）对非文本值抛 `HostDurableError("payload field finish_reason must be non-empty text")`——已 fail closed。

测试 `tests/host/test_outbox_projection.py:736-738` 在 `test_succeeded_projection_rejects_invalid_metadata_or_summary_pair` 参数化矩阵中新增:

```python
(
    {
        "final_answer": "answer",
        "filtered": False,
        "degraded": False,
        "finish_reason": 123,
    },
    "finish_reason",
),
```

断言: `result.failures == 1`、`item is None`（无半成品）、`failure.last_error_code == "HostDurableError"`、`expected_fragment in failure.last_error_message`。

**succeeded HostEvent read 路径** — 生产代码 `dayu/host/read_api.py:929-933`:

```python
finish_reason=_optional_payload_text(
    payload,
    field_name=_PAYLOAD_FIELD_FINISH_REASON,
    row=row,
),
```

`_optional_payload_text`（`read_api.py:1659-1662`）对非文本值抛 `HostDurableError`——已 fail closed。

测试 `tests/host/test_read_api_terminal_policy.py:208-228` 新增独立测试 `test_succeeded_terminal_projection_rejects_non_text_finish_reason`:

```python
with pytest.raises(HostDurableError, match="finish_reason"):
    _project_terminal_event(
        tmp_path,
        event_type="RUN_SUCCEEDED",
        payload={
            "final_answer": "inline answer",
            "filtered": False,
            "degraded": False,
            "finish_reason": 123,
        },
    )
```

**附加防御** — `dayu/host/read_api.py:855-856` 在 Outbox JSON read boundary 新增:

```python
if finish_reason is not None and not isinstance(finish_reason, str):
    raise HostDurableError("outbox final answer finish_reason is invalid")
```

这是 `_final_answer_from_outbox_json` 内部对 JSON 解析后字段的类型校验，与 F01 属于同一防御层次——在 durable read boundary 对已 materialize 的 JSON 做二次校验。不是兼容转换（不 `str()` 非文本值），不改变 owner。

### 判定: FIXED

两条行为测试均已新增，生产路径 fail closed 不变，无兼容转换。

---

## 新增 Material Defect 检查

### 1. read boundary finish_reason 校验（行 855-856）

`_final_answer_from_outbox_json:855-856` 在本次修复中新增了对 `finish_reason` 非文本的类型校验。该检查与 F01 的 `content` 校验处于同一防御层，且语义一致（fail closed，不转换）。**不构成 material defect**——这是 read boundary 防御的合理补全。

### 2. 参数化矩阵扩展的影响

`test_succeeded_projection_rejects_invalid_metadata_or_summary_pair` 参数化矩阵新增 `finish_reason=123` case 后，与既有 `filtered` 缺失/非 bool、`degraded` 缺失/非 bool、单边 summary ref case 共用同一验证逻辑。所有 case 共享 `assert result.failures == 1`、`assert item is None`、`assert failure.last_error_code == "HostDurableError"`、`assert expected_fragment in failure.last_error_message`。新增 case 的 `expected_fragment="finish_reason"` 与 `optional_payload_text` 的原始错误消息 `"payload field finish_reason must be non-empty text"` 精确匹配。**无 material defect**。

### 3. 测试互不干扰

F01 测试（`test_public_outbox_api.py`）使用独立 tmp_path、独立 session/run id；F02 测试使用参数化矩阵内的独立 event id（`"event-invalid-success-metadata"`）和独立 tmp_path。与前 75 项 focused 测试无冲突。

### 4. Owner / propagation 一致性

- `content` 事实: 仍由 `_resolve_assistant_final_answer_continuity_text`（`_terminal_answer.py`）统一产生；Outbox projection 通过 `required_assistant_final_answer_continuity_text` 获取；Outbox JSON read boundary 通过 `_final_answer_from_outbox_json` 解析已 materialize 的 JSON。
- `finish_reason` 事实: 仍由 canonical `RUN_SUCCEEDED` payload 拥有；Outbox projection 通过 `optional_payload_text` 读取；HostEvent read 通过 `_optional_payload_text` 读取。
- 无新增 source-of-truth、无重复 parser、无下游修正上游语义。

### 5. 无兼容转换

全量 `grep` 确认: 无 `str()` 包装非文本 `finish_reason`、无 `compat` / `convert` 函数、无 try/except 吞掉类型错误后降级为默认值。

---

## 验证结果

| 验证项 | 结果 |
|---|---|
| F01/F02 聚焦测试（32 个） | 全部通过 |
| P3-B 完整聚焦测试（75 个） | 全部通过 |
| 传播回归测试（305 个） | 全部通过 |
| pyright | 0 errors, 0 warnings, 0 informations |
| git diff --check | 通过 |

---

## Findings

### F01 与 F02 均完整修复，无新增 material defect。

---

## F01/F02 Final Status

| Finding | Status | 证据 |
|---|---|---|
| P3-B-S1-CR-F01 | **FIXED** | `read_api.py:847-850` 显式拒绝空/空白 content，`HostDurableError` 含 Outbox/field/content 语义；`test_public_outbox_api.py:105-187` 走 production Host 路径验证 raw row 污染 → public read → `HostApiError(INTERNAL_ERROR)` cause 含 Outbox field 诊断 |
| P3-B-S1-CR-F02 | **FIXED** | `test_outbox_projection.py:736-738`（Outbox projection failure）与 `test_read_api_terminal_policy.py:208-228`（HostEvent read）均新增非文本 `finish_reason=123` fail-closed 行为断言；无兼容转换 |

## 新 Finding 数

**0** — 无新增 material defect。

## Open Questions

无。

## Residual Risk

1. **P3-J DDL conditional CHECK**: 状态不变，仍由原 owner 负责。
2. **read boundary finish_reason 校验（行 855-856）**: 当前 `_final_answer_from_outbox_json` 对 `finish_reason` 的类型校验与 producer 端（`optional_payload_text`）独立且语义等价。若 producer 端未来变更错误消息格式，read boundary 的独立错误消息可能产生诊断差异。当前不构成 defect——两层校验各自 fail closed，且测试覆盖了 producer 端的诊断片段。建议后续统一 `finish_reason` 的 canonical 校验 helper 以减少诊断漂移风险，但优先级低，不阻塞本轮。

## Verdict

**PASS** — Controller accepted findings P3-B-S1-CR-F01 和 P3-B-S1-CR-F02 均已在当前 working tree 完整修复，无新增 material defect。

- F01/F02 final status: both **FIXED**
- 新 finding 数: **0**
- Verdict: **PASS**

Artifact: `docs/reviews/wu-semantic-ownership-01-p3-b-s1-code-rereview-ds.md`
