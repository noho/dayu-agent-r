# WU-SEMANTIC-OWNERSHIP-01 P3-B S1 code re-review

## Scope

- Mode: current changes（相对 accepted plan bookkeeping commit `4c6ec694`）
- Branch: `phaseflow/host-issues-control`
- Base: `4c6ec694`
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-b-s1-code-rereview-mimo.md`
- Included scope: controller accepted findings `P3-B-S1-CR-F01` / `P3-B-S1-CR-F02` 修复验证 + 新增 material defect 检查
- Excluded scope: CLI-CI 并发文件、rejected / deferred concerns
- Parallel review coverage: 无

## 输入

- Controller 真源：`docs/reviews/wu-semantic-ownership-01-p3-b-s1-code-review-controller-adjudication.md`
- Fix artifact：`docs/reviews/wu-semantic-ownership-01-p3-b-s1-fix-codex.md`
- 原两路 review：
  - `docs/reviews/wu-semantic-ownership-01-p3-b-s1-code-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-b-s1-code-review-ds.md`
- Accepted plan：`docs/host/wu-semantic-ownership-01-p3-b-terminal-final-answer-outbox-plan.md`

## 验证结果摘要

| 验证项 | 结果 |
|---|---|
| F01 raw durable row → public read 抛 HostDurableError cause | ✅ 已验证 |
| F02 finish_reason 非文本 Outbox projection failure fail closed | ✅ 已验证 |
| F02 finish_reason 非文本 HostEvent read fail closed | ✅ 已验证 |
| 无兼容转换 | ✅ 已验证 |
| owner/propagation 不变 | ✅ 已验证 |
| focused tests（75 个） | 全部通过 |
| propagation regression（305 个） | 全部通过 |
| pyright | 0 errors, 0 warnings, 0 informations |
| git diff --check | 通过 |
| 新增 material defect | 0 |

---

## Finding final status

### P3-B-S1-CR-F01 — Outbox public JSON read boundary

**Status: FIXED**

**修复验证：**

1. **Production code**（`dayu/host/read_api.py:847-850`）：
   ```python
   if content.strip() == "":
       raise HostDurableError(
           "Outbox final answer field content must be non-empty text"
       )
   ```
   在 `_final_answer_from_outbox_json` 中，`isinstance(content, str)` 检查之后、构造 `HostFinalAnswerView` 之前，显式拒绝空白 content。诊断包含 `Outbox`、`field`、`content` 语义。

2. **Test**（`tests/host/test_public_outbox_api.py:105-163`）：
   - `test_public_outbox_read_rejects_raw_blank_final_answer_content` 参数化测试 `""` 和 `" \t\n"` 两种空白输入
   - 通过 production Host 路径 materialize Outbox item
   - 直接污染真实 SQLite raw row 的 `final_answer_json.content`
   - 调用 public `Host.read_outbox_terminal_items`
   - 断言 `HostApiError(INTERNAL_ERROR)` 且 cause 是 `HostDurableError`
   - 断言 diagnostic 包含 `Outbox`、`field`、`content`

3. **Owner boundary 不变**：
   - `content` 事实由 terminal-answer owner 产生
   - Outbox JSON read boundary 负责解析与字段语义校验
   - `HostFinalAnswerView` 继续负责 public contract 校验（双层防御保留）
   - 损坏 raw row 不再绕过 Outbox boundary，不再泄漏 `HostFinalAnswerView` 的 `ValueError`

**直接证据**：`read_api.py:847-850` 的 `content.strip() == ""` 检查 + `test_public_outbox_api.py:105-163` 的真实 raw row 污染测试。

---

### P3-B-S1-CR-F02 — malformed `finish_reason` regression

**Status: FIXED**

**修复验证：**

1. **Outbox projection failure**（`tests/host/test_outbox_projection.py:731-739`）：
   - `test_succeeded_projection_rejects_invalid_metadata_or_summary_pair` 参数化矩阵新增 `finish_reason=123` case
   - expected_fragment 为 `"finish_reason"`
   - 断言 `failure.last_error_code == "HostDurableError"`
   - 断言 `failure.last_error_message` 包含 `finish_reason`

2. **HostEvent read**（`tests/host/test_read_api_terminal_policy.py:208-229`）：
   - `test_succeeded_terminal_projection_rejects_non_text_finish_reason` 使用 `finish_reason=123`
   - 断言 `pytest.raises(HostDurableError, match="finish_reason")`

3. **无兼容转换**：
   - `read_api.py:855-856`：`if finish_reason is not None and not isinstance(finish_reason, str): raise HostDurableError(...)`
   - `outbox.py` 通过 `_event_payload.optional_payload_text` 读取，非文本值抛 `HostDurableError`
   - 没有任何 `int(str)`、`str(value)` 或 fallback 转换

4. **Owner boundary 不变**：
   - `finish_reason` 由 canonical `RUN_SUCCEEDED` 拥有
   - Outbox projection 与 succeeded HostEvent read 只严格投影该字段
   - 非文本值 fail closed，不转换、不兼容、不从 descriptor 或下游重建

**直接证据**：`test_outbox_projection.py:731-739` + `test_read_api_terminal_policy.py:208-229` 的行为测试锁定 non-text `finish_reason` fail closed。

---

## Propagation audit

1. **正常成功路径**：`FinalAnswerData.content → terminal descriptor / canonical RUN_SUCCEEDED → required terminal-answer resolver → Outbox final_answer_json → durable row read → public Outbox item`。focused 与 production public smoke 通过，新检查不改变正常非空回答。

2. **Outbox raw-row 损坏路径**：`raw final_answer_json.content empty/blank → durable row decode → _final_answer_from_outbox_json → HostDurableError → public HostApiError cause`。两种空白输入均 fail closed，诊断同时指明 Outbox、field 与 content；不再泄漏 `HostFinalAnswerView` 的 `ValueError`。

3. **Outbox canonical metadata 路径**：`RUN_SUCCEEDED.finish_reason(non-text) → Outbox projection optional text validation → apply transaction rollback → projection failure row`。断言 item 不存在、failure code 为 `HostDurableError`、diagnostic 含 `finish_reason`；没有转换或兼容。

4. **HostEvent canonical metadata 路径**：`RUN_SUCCEEDED.finish_reason(non-text) → succeeded HostEvent read → HostDurableError`。诊断含 `finish_reason`，content resolver 和 descriptor metadata 不会覆盖 canonical 非法值。

5. **其它消费者**：`RUN_SUCCEEDED → optional resolver → memory / compact / run input` 与 ProjectionRunner retry/idempotency 回归共 305 项通过。本轮未修改事实产生、持久化、audit/trace/memory 或 LLM-facing 投影，不存在第二套 source-of-truth。

6. **非成功路径**：failed / cancelled / lost 仍不提升 forged final answer；focused 回归通过，本轮未触及该边界。

---

## 新增 material defect 检查

**结果：未发现新增 material defect。**

检查范围：
- `dayu/host/read_api.py`：仅新增 F01 空白 content 检查，未修改其它逻辑
- `tests/host/test_public_outbox_api.py`：仅新增 F01 测试
- `tests/host/test_outbox_projection.py`：仅新增 F02 测试 + P3-B 实现测试
- `tests/host/test_read_api_terminal_policy.py`：仅新增 F02 测试 + P3-B 实现测试

所有变更均落在 controller accepted findings 的修复边界内，未引入新的 production code 变更。

---

## Open Questions

无。

---

## Residual Risk

- `assigned to later work unit`：P3-J DDL conditional CHECK 仍由原 owner 负责，本轮无 schema 变更。
- `requiring new issue or explicit user decision`：descriptor 自动 repair 和 optional-material policy tightening 仍是原非目标，本轮无新证据要求扩大范围。
- 没有未分类 residual risk，没有 blocking open question。

---

## Verdict

**P3-B S1 code re-review: PASS — 0 new findings, F01/F02 fully fixed.**

两项 controller accepted findings 均已在当前 working tree 完整修复：
- `P3-B-S1-CR-F01`：raw durable row 空白 content 在 Outbox JSON read boundary fail closed，诊断包含 Outbox field 语义，public read 抛 `HostApiError(INTERNAL_ERROR)` 且 cause 为 `HostDurableError`。
- `P3-B-S1-CR-F02`：non-text `finish_reason` 在 Outbox projection failure 与 HostEvent read 两条路径均 fail closed，无兼容转换。

修复落在事实的直接解析/投影边界，未修改 terminal-answer source selection、Outbox transaction、durable schema、public exception mapping 或任何下游 UI / Service 消费者。owner boundary 与 propagation 路径不变。
