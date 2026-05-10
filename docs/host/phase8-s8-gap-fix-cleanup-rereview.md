# P8-S8 Gap Fix Cleanup Re-review

## 结论

**CONDITIONALLY PASSED**

本轮只复审 P8-S8 gap fix code review 后的两个 Low cleanup finding，未做全量架构 review。生产代码与 smoke 当前行为均满足 P8-S8 repair 预期；未发现新 blocker。

但 Low Finding 002 仅部分修复：`phase8-s9-code-review.md` 的 Finding 003 修复状态段落已改为 `fixed`，且明确写出 P8-S9 初始发现 gap、P8-S8 gap fix 已通过 `repair_missing_session_snapshots` 修复，smoke S7 当前事实为 `memory_recovered=true recovery_mode=checkpoint_rebuild`。不过该 artifact 顶部结论与 S7 场景分析仍残留旧态措辞，读者可能误以为 S7 当前仍在演示最终 gap。因此当前不建议进入 user confirmation + commit gate；先清理这些 review artifact 措辞后再进入该 gate。

---

## 复审范围

已读取并核对：

- `AGENTS.md`
- `docs/host/phase8-s8-gap-fix-code-review.md`
- `docs/host/phase8-s9-code-review.md`
- `dayu/host/_conversation_memory_durable.py`
- `utils/smoke_host_p8_attempt_lease.py`

执行过的复核命令：

```bash
rg -n "_has_terminal_or_canonical_fact|gap demonstrated|gap_confirmed" \
  dayu/host/_conversation_memory_durable.py \
  docs/host/phase8-s8-gap-fix-code-review.md \
  docs/host/phase8-s9-code-review.md \
  utils/smoke_host_p8_attempt_lease.py

source .venv/bin/activate && python utils/smoke_host_p8_attempt_lease.py
```

smoke 实测 S7 输出包含：

```text
[s7] checkpoint_caught_up=True snapshot_deleted=True memory_recovered=True recovery_mode=checkpoint_rebuild
```

未重跑 pytest / pyright；本轮复审重点是两个 Low cleanup finding，且用户已报告：

- `pytest tests/host/test_phase8_durable_memory_recovery.py -q` -> 9 passed
- `python -m pyright dayu/host tests/host utils` -> 0 errors
- `git diff --check` -> clean

---

## Finding 001：helper 命名误导

**判定：fixed**

直接证据：

- `dayu/host/_conversation_memory_durable.py` 中旧名 `_has_terminal_or_canonical_fact` 已不存在。
- 调用点已更新为 `_has_terminal_event(canonical_events)`。
- `_has_terminal_event` 的 docstring 明确说明只判断 terminal 事件，并把 `TERMINAL_RUN_EVENT_TYPES` 作为 session 已落定的完整事实信号。
- 实现仍只检查 `event.type in TERMINAL_RUN_EVENT_TYPES`。

行为复核：

- 只有 `USER_INPUT_ACCEPTED`、无 terminal 事件时，`_repair_missing_session_snapshots_locked` 会 `continue`，不会写入半成品 snapshot。
- repair 行为未被 cleanup 改变；只有 terminal event 存在才触发 missing snapshot repair。

结论：命名、调用点、docstring 与行为已经一致。

---

## Finding 002：S9 review artifact 措辞对齐

**判定：partially fixed**

已修复部分：

- `docs/host/phase8-s9-code-review.md` 的 Finding 003 修复状态已写为 `fixed`。
- Finding 003 的修复状态段落已表达为：P8-S9 初始发现 memory recovery gap，P8-S8 gap fix 已通过 `DurableConversationMemoryStore.repair_missing_session_snapshots` 和 `DurableHarnessBundle.startup_reconcile` 联动修复。
- smoke S7 当前事实已对齐为 `memory_recovered=true recovery_mode=checkpoint_rebuild`。
- 指定 `rg` 命令未在 `phase8-s9-code-review.md` 命中 `gap demonstrated` 或 `gap_confirmed`。

仍需 cleanup 的证据：

- `docs/host/phase8-s9-code-review.md:5-8` 顶部结论仍是 `CONDITIONALLY PASSED`，并写着 “S7 演示 checkpoint-caught-up 后 memory rebuild gap”。这会把历史 gap 描述成当前 S7 仍在演示的状态。
- `docs/host/phase8-s9-code-review.md:64-68` 的 S7 场景分析仍描述为普通 reopen 后读取已有 snapshot，并标为 Finding 003 未覆盖 recovery 语义；这与当前 smoke 代码中删除 snapshot 后通过 repair 重建的事实不一致。
- `docs/host/phase8-s9-code-review.md:180-198` 的验证命令仍是旧的宽泛 pyright / smoke 复核记录，没有反映当前已报告的 targeted pytest、S7 checkpoint rebuild smoke、targeted pyright 与 `git diff --check` 组合。

`gap_confirmed` 复核：

- 指定 `rg` 仍在 `docs/host/phase8-s8-gap-fix-code-review.md` 命中 `gap_confirmed`，内容是 “S7 从 gap_confirmed 改为 recovery 成功”。该处属于历史变更说明，不是当前 gate 状态。
- 同一文件中 `gap demonstrated` 出现在旧 Finding 002 的问题描述里，并紧接着标明已修复。它不是 S9 当前状态，但该段同时混有“当前写为 / 建议 / 已修复”，可在后续 artifact cleanup 中一并改得更清楚。

结论：核心 Finding 003 状态段落已修复，但 S9 artifact 仍存在会误导当前 gate 状态的旧态措辞，因此本 finding 只能判为 partially fixed。

---

## 新 blocker

未发现新 blocker。

当前未通过的是 review artifact 表述一致性问题，不是 durable memory repair 的代码正确性问题。

---

## Gate 建议

当前不建议进入 user confirmation + commit gate。建议先做一个很小的 artifact cleanup：

- 将 `phase8-s9-code-review.md` 顶部结论与摘要改为当前事实：Finding 003 已 fixed，S7 现在验证 checkpoint caught-up + snapshot row missing 后的 repair rebuild。
- 更新 S7 场景分析，删除“只覆盖普通 reopen 持久化”的当前态表述，改为描述当前 smoke 的 checkpoint rebuild 路径。
- 将验证命令段落对齐本轮报告的 targeted pytest、smoke S7、targeted pyright、`git diff --check`。

完成后可再做一次窄范围 re-review；若无新增问题，即可进入 user confirmation + commit gate。

---

## Residual Risks 与 Owner

| 风险 | Owner | 状态 |
| --- | --- | --- |
| repair 全表扫描 / 大 EventLog 延迟 | P9 / 容量评估 | deferred |
| production startup lifecycle 自动 wire | P9 | deferred |
| 多进程同时 `startup_reconcile` stress | issue #38 | deferred |
| 自定义 non-durable memory store 恢复语义 | 调用方 | 调用方负责 |
