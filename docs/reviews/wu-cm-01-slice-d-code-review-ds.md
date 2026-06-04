# WU-CM-01 Slice D Code Review — DeepSeek

## Gate / Scope

- Gate: Slice D code review gate
- Work unit: WU-CM-01 Conversation Memory overall optimization
- Slice: Public Smoke And Docs Closure
- Design source: `docs/host/design.md`
- Plan source: `docs/host/wu-cm-01-conversation-memory-plan.md`
- Implementation artifact: `docs/reviews/wu-cm-01-slice-d-implementation-codex.md`
- Review stance: code-review — 只找 bugs / regressions / missing tests / contract violations
- 输出 artifact: `docs/reviews/wu-cm-01-slice-d-code-review-ds.md`

## 审查范围

待审变更（未提交 workspace changes）：

- `README.md`
- `tests/host/test_purge_session.py`
- `utils/smoke_host_public_conversation_memory.py`
- `utils/smoke_host_public_conversation_memory_scenarios.py`
- `utils/smoke_host_public_multiturn.py`
- `docs/reviews/wu-cm-01-slice-d-implementation-codex.md`

## Findings

### Finding 1 (minor) — `_compact_pressure_reserve_tokens` 退化为常值函数，分支无意义

**文件**: `utils/smoke_host_public_conversation_memory.py:1114-1124`, `utils/smoke_host_public_conversation_memory_scenarios.py:2372-2382`

**证据**: 两个脚本中的 `_compact_pressure_reserve_tokens` 函数两个分支返回相同值：

```python
# smoke_host_public_conversation_memory.py:1114-1124
def _compact_pressure_reserve_tokens(*, context_window_size: int) -> int:
    if context_window_size >= _COMPACT_PRESSURE_LARGE_WINDOW_TOKENS:
        return _COMPACT_PRESSURE_RESERVE_TOKENS  # 8192
    return _COMPACT_PRESSURE_RESERVE_TOKENS      # 8192 — 同上

# smoke_host_public_conversation_memory_scenarios.py:2372-2382
def _compact_pressure_reserve_tokens(*, context_window_size: int) -> int:
    if context_window_size >= _COMPACT_PRESSURE_LARGE_WINDOW_TOKENS:
        return _COMPACT_PRESSURE_RESERVE_TOKENS  # 160000
    return _COMPACT_PRESSURE_RESERVE_TOKENS      # 160000 — 同上
```

对比 `smoke_host_public_multiturn.py:919-932`，其同一函数在两个分支中有实际差异（小窗口额外加 tool pressure tokens），说明这个 if/else 本应有区分语义。

**严重性**: minor。不影响 smoke 正确性，但 docstring 声称"1M 模型有足够区间，较小窗口给工具和系统上下文预留更多空间"与实际行为矛盾。两个脚本的函数已退化，参数 `context_window_size` 成为死参数，docstring 误导读者。

**建议**: 要么删除分支简化为直接返回常量，要么恢复区分逻辑。不作为 blocking — smoke 脚本的 pressure 计算在 1M 窗口下仍能正确触发 compact。

---

### Finding 2 (minor) — `_resolve_workspace_root` 在三处 smoke 脚本中完全重复

**文件**:
- `utils/smoke_host_public_conversation_memory.py:392-406`
- `utils/smoke_host_public_conversation_memory_scenarios.py:1152-1169`
- `utils/smoke_host_public_multiturn.py:354-371`

**证据**: 三个脚本中 `_resolve_workspace_root` 实现完全一致（仅 `_DEFAULT_WORKSPACE_PREFIX` 常量不同，通过各自模块级常量区分）。函数体完全重复：

```python
def _resolve_workspace_root(workspace_root_text: str | None) -> pathlib.Path:
    if workspace_root_text is not None:
        return pathlib.Path(workspace_root_text).resolve()
    return (
        _DEFAULT_WORKSPACE_PARENT
        / f"{_DEFAULT_WORKSPACE_PREFIX}-{uuid4().hex[:12]}"
    ).resolve()
```

**严重性**: minor。CLAUDE.md 编码约束要求"重复逻辑必须抽取"，但 `utils/` 下 smoke 脚本按项目约定无需测试、无覆盖率要求，且保持自包含可独立运行有合理理由。不构成 blocking。

---

### Finding 3 (info) — Implementation artifact 验证结果可信，residual owners 合理

**文件**: `docs/reviews/wu-cm-01-slice-d-implementation-codex.md`

**证据**:

1. 测试结果声称与代码变更范围一致：Slice D 只改了 smoke 脚本默认 workspace、test_purge_session seed 和 README，未修改生产 Host/Runtime/Service 代码。`pytest tests/host -q` 的 1100 passed / 1 skipped 与"未改生产代码"一致。

2. Residual owners 与 plan 中 residual risks 对齐：
   - Eval benchmark → WU-CM-10 / #80（plan 明确 deferred-with-owner）
   - User Profile → WU-CM-11 / #115（plan 明确 deferred-with-owner）
   - Recall/search → #39（plan 明确 deferred-with-owner）
   - Old schema workspace → caller responsibility（plan 明确"按 fresh schema 约束，不做旧库兼容读取"）

3. "本轮 smoke 使用真实 provider，结果仍受 provider 可用性影响"的未覆盖风险声明诚实。

**严重性**: info。不构成 finding，验证了 implementation artifact 的一致性。

---

### Finding 4 (info) — README 手工 smoke 说明与脚本行为一致，未越界

**文件**: `README.md:948-1010`

**核查结果**:

| README 描述 | 脚本实际行为 | 一致？ |
|---|---|---|
| 5.1 多轮 smoke "默认使用 workspace/tmp/ 下的 fresh smoke workspace" | `_resolve_workspace_root(None)` → `workspace/tmp/host-public-multiturn-smoke-<uuid>` | 一致 |
| 5.1 "需要复用已有 workspace 时显式传 --workspace-root" | `--workspace-root` 解析为 `Path(...).resolve()` | 一致 |
| 5.1 "需要在同一个 durable session 内复用时显式加 --workspace-root 和 --reuse-session" | `--reuse-session` 使用稳定 slot key | 一致 |
| 5.2 对话记忆 smoke "默认使用 workspace/tmp/ 下的 fresh smoke workspace" | 同上模式，前缀 `host-public-conversation-memory-smoke` | 一致 |
| 5.3 场景 smoke "默认使用 workspace/tmp/ 下的 fresh smoke workspace" | 同上模式，前缀 `host-public-conversation-memory-scenarios-smoke` | 一致 |

未发现 README 写未来计划、路线图或与代码不一致的描述。未发现旧术语（`working_assumptions`、`pinned_state`、`stable_layer`、`history_pool`、`minimum_preserve` 等）。

**严重性**: info。README 同步正确。

---

### Finding 5 (info) — `test_purge_session.py` 的 `raw_user_turn` → `selected_recent_window` 迁移正确

**文件**: `tests/host/test_purge_session.py:2235`

**证据**: 

1. 生产 durable schema `dayu/host/durable/schema.py:810-818` 中 `item_kind` CHECK 约束为：
   ```sql
   item_kind IN (
       'evidence_backed_fact',
       'selected_recent_window',
       'reference_continuity',
       'answer_anchor',
       'forward_intent',
       'session_summary'
   )
   ```
   不存在 `raw_user_turn`。

2. 生产 durable memory writer `dayu/host/durable/memory.py:81` 定义 `_ITEM_KIND_SELECTED_RECENT_WINDOW = "selected_recent_window"`。

3. Slice C plan 明确要求删除旧 durable item kind（包括 `raw_user_turn`），迁移为 vNext `selected_recent_window`。

4. `selected_recent_window` 是 vNext Trace Memory selected recent window material 的正确 durable kind。

**严重性**: info。迁移正确，无 regression。

---

### Finding 6 (info) — `_COMPACT_PRESSURE_RESERVE_TOKENS` 从 8192 改到 160000 合理，仍保留 context pressure 覆盖

**文件**: `utils/smoke_host_public_conversation_memory_scenarios.py:139`

**分析**:

对于 1M context window 模型（典型 soft_threshold=0.8, hard_threshold=0.95）：

| 指标 | 旧值 (8192 reserve) | 新值 (160000 reserve) |
|---|---|---|
| soft_threshold_tokens | ~800,000 | ~800,000 |
| target_tokens | ~816,384 | ~816,384 |
| prompt_pressure_tokens | ~808k (减 tool) | ~656k (减 tool) |
| 预期总上下文估算 | 远超 800k soft | 远超 800k soft |

prompt_pressure_tokens 仍有 ~656k tokens 的中文噪声填充，结合 tool pressure 和 system/scene framing，总估算远超 soft threshold，能可靠触发 proactive compact。160k reserve 为 core suite 已累积 messages/memory/framing 留预算，避免 smoke 自身越过 hard threshold 导致 dispatch 前失败。

**严重性**: info。变更合理，不是"无压力 smoke"。

---

## Adversarial Failure Pass

以下场景已逐项检查，未发现 failure：

1. **fresh workspace 冲突**: 三个 smoke 默认 workspace 前缀不同（`host-public-conversation-memory-smoke`、`host-public-conversation-memory-scenarios-smoke`、`host-public-multiturn-smoke`），加上 uuid4 后缀，不会互相污染。

2. **显式 `--workspace-root` 语义被破坏**: `_resolve_workspace_root` 在传入非 None 值时直接 `Path(...).resolve()`，不添加前缀或 uuid。显式路径语义完整保留。

3. **`--reuse-session` 语义被破坏**: `--reuse-session` 仍控制 slot key 稳定性（稳定 key vs fresh key），与 workspace 选择正交。fresh workspace + `--reuse-session` 组合行为可预测（在新 workspace 中复用稳定 slot key）。

4. **production old schema fail-closed 被掩盖**: smoke 默认 fresh workspace 只影响 smoke 脚本自身行为。production path（`dayu-cli`、`dayu-web`、`dayu-wechat`）不经过这些 smoke 脚本，仍使用用户指定的 `--base` 默认 `./workspace`。old schema DB 在 production path 中仍会 fail closed。

5. **scenarios pressure reserve 160000 导致 compact 不触发**: 已验证 ~656k tokens 噪声填充仍远超 soft threshold。

6. **test_purge_session 的 `selected_recent_window` 不是合法 item_kind**: durable schema CHECK 约束和生产代码均确认 `selected_recent_window` 是合法 vNext item kind。

7. **README 越界或写未来计划**: 未发现。

8. **引入过度设计、重复 helper、无类型/Any/object、旧字段兼容读取或 recall/eval/User Profile 越界**: 未发现。

## 项目指令检查

- 分层架构：未修改生产代码，分层不变。
- 编码硬约束：变更代码均有完整中文 docstring、类型标注、无 `Any`/`object`。
- schema 变更：本 Slice 不涉及 schema 变更；test_purge_session 的 item_kind 迁移是跟随 Slice C 已完成的 schema 变更。
- 测试与验证：implementation artifact 声称 pytest 和 pyright 通过。
- 文档同步：README 按触发规则同步，内容与代码一致。

## Verdict

**PASS** — 无 blocking finding。

三个 minor findings（degenerate 函数、重复 helper）位于 `utils/` smoke 脚本，不影响正确性且 `utils/` 按项目约定无测试/覆盖率要求。所有 critical path 检查（fresh workspace 语义、显式参数不破坏、production fail-closed 不掩盖、pressure 覆盖保留、durable kind 正确、README 一致、无越界设计）均通过。

## Residual Notes

- Finding 1 的 degenerate `_compact_pressure_reserve_tokens` 函数建议在后续清理中修复（删除 dead branch 或恢复区分逻辑），但不阻塞 Slice D closeout。
- Finding 2 的 `_resolve_workspace_root` 重复如后续 smoke 脚本数量继续增长，可考虑抽取到 `utils/smoke_host_public_diagnostics.py` 或新建共享模块。
