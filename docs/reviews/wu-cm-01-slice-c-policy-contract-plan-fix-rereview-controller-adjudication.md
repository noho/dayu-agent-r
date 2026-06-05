# WU-CM-01 Slice C Policy Contract Plan Fix Re-Review - Controller Adjudication

## 裁决

- Gate: WU-CM-01 Slice C policy contract plan fix re-review
- Verdict: pass
- Accepted plan fix commit: 49990e97
- Next gate: WU-CM-01 Slice C implementation

Controller 接受本轮 policy contract plan fix。两路 review 均为 pass；DS F7 / F8 经 fix gate 后由 MiMo 与 DS re-review 确认关闭，无新增 blocking finding。

## 裁决依据

Accepted:

- `docs/host/wu-cm-01-conversation-memory-plan.md` 已明确后续 Slice C implementation 必须以 `docs/host/design.md` 的 `memory_projection_policy` 字段清单为唯一真源。
- retry prompt 中的错误 generic policy shape 已被显式禁止进入 production dataclass、config JSON key、typed config view、Service assembly 参数、test fixture 或 README 术语。
- `engine_ingest.py` 的迁移目标已收敛为 `selected_recent_window_turn_floor`，不再允许“本 slice 明确的新字段”。
- direct consumer closure list 已覆盖 Host policy、durable/projection、compact material、RunInputBuilder、dispatch/ingest、runtime config、Service assembly 与 tests。
- DS F7 已关闭：plan 现在明确 Slice C 修改 `dayu/config/execution_profiles.json.memory_projection_policy` 时必须同 slice 检查并按职责更新 `dayu/config/README.md`；Slice D 只做残留旧术语和配置入口一致性的 re-check。
- DS F8 已关闭：Codex artifact 中“第一性原理判断”措辞已修正。

Rejected:

- 不接受继续使用 `selected_recent_window_floor_turns`、`max_memory_items_per_category`、`max_text_chars_per_memory_item`、`projection_max_repair_attempts`、`projection_max_rebuild_rows`、`projection_max_catchup_rows` 作为 Slice C production/config/test/README contract。
- 不接受通过 alias、compatibility wrapper、旧字段兼容读取、默认补齐、extra payload、raw dict patch 或双字段真源绕过设计真源字段集合。
- 不接受把 `dayu/config/README.md` 的字段级配置说明同步完全推迟到 Slice D；若 Slice C 修改 packaged config 字段，Slice C 必须同 slice 处理。

## Review 结果

- `docs/reviews/wu-cm-01-slice-c-policy-contract-plan-fix-review-mimo.md`: pass，0 blocking findings。
- `docs/reviews/wu-cm-01-slice-c-policy-contract-plan-fix-review-ds.md`: pass，F7/F8 为 observation / low-severity plan quality issues。
- `docs/reviews/wu-cm-01-slice-c-policy-contract-plan-fix-review-fix-codex.md`: 已修复 F7/F8。
- `docs/reviews/wu-cm-01-slice-c-policy-contract-plan-fix-rereview-mimo.md`: pass，F7/F8 已关闭。
- `docs/reviews/wu-cm-01-slice-c-policy-contract-plan-fix-rereview-ds.md`: pass，F7/F8 已关闭。

## 验证

本 gate 只修改 plan / review artifact，不修改生产代码、测试或 README 实体文件。未运行 pytest 或 pyright；该判断成立，因为 pytest / pyright 不能验证文档 contract fix，且当前 production memory code 仍处于待 Slice C 迁移状态。

轻量校验由 AgentCodex 执行：

```bash
git diff --check
```

结果：通过。

## 后续入口

进入 `WU-CM-01 Slice C implementation gate`。下一轮 implementation prompt 必须直接使用 plan 中的 design-source policy field list，并把 partial memory draft stash 仅作为反例/历史失败记录，不得直接恢复为实现基础。
