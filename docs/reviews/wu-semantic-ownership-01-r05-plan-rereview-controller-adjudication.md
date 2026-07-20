# WU-SEMANTIC-OWNERSHIP-01 R05 Plan Re-Review Controller Adjudication

## 1. Gate 与输入

- umbrella：`WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation。
- immutable plan target：`docs/host/wu-semantic-ownership-01-r05-wait-observation-state-machine-plan.md`。
- plan base：`5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1`。
- AgentMiMo complete re-review：`docs/reviews/wu-semantic-ownership-01-r05-plan-rereview-mimo.md`。
- AgentDS complete re-review：`docs/reviews/wu-semantic-ownership-01-r05-plan-rereview-ds.md`。
- Controller direct probe：对计划 §2.3 / §9.2、`dayu/host/durable/state.py` 与完整 changed-file Ruff 命令作独立复核。

本裁决不授权 implementation。下一 gate 是 AgentCodex 第二轮 plan fix，之后必须再次进行双路完整 plan re-review。

## 2. 裁决摘要

| Finding | 来源 | 裁决 | 当前动作 |
|---|---|---|---|
| `R05-PRR-F01` planned changed owner 的 Ruff 基线少登记一条 F401 | MiMo 001 | `ACCEPTED_NARROWED` | 登记 `durable/state.py` 的直接基线；实施时同时删除两条 touched-file unused import；全量 residual 预期改为 165 |
| §9.2 未包含 `tests/host/test_wait_record_state.py` | MiMo 001 子结论 | `REJECTED_EVIDENCE_CONTRADICTED` | immutable target 在 review 生成前已包含该路径，不修改这一已正确命令项 |
| PF-01 至 PF-04 关闭 | MiMo、DS | `ACCEPTED_CLOSED` | 保持关闭，不重新打开产品裁决 |
| DS changed-file Ruff / 167→166 PASS | DS §7 | `SUPERSEDED_BY_DIRECT_EVIDENCE` | 当前 directed Ruff 实际为两条 F401；该局部验证结论不能作为接受计划的依据 |

accepted new finding：`1`。blocking question：`0`。不需要新产品裁决、owner、slice 或 allowlist 扩张。

## 3. `R05-PRR-F01` — accepted narrowed

计划 §2.3 只登记：

```text
tests/host/test_phase7_waiting_integration.py:8:22
F401 datetime.UTC imported but unused
```

Controller 在固定 base / HEAD 上运行计划 §9.2 的完整 changed-file Ruff 命令，得到：

```text
dayu/host/durable/state.py:40:5
F401 TERMINAL_RUN_STATUS_VALUES imported but unused

tests/host/test_phase7_waiting_integration.py:8:22
F401 datetime.UTC imported but unused

Found 2 errors.
```

`dayu/host/durable/state.py` 是 R05-S1 必改 durable owner 文件，因此第二条既有 F401 与本 WU changed-file 集合相交，不能作为 inherited residual 留下。若计划仍只要求清理测试 import，§9.2 的 changed-file Ruff zero gate 必然失败，且全量 residual 预期 `166` 也不精确。MiMo 的这部分 finding 有直接代码与工具输出支持，予以接受。

AgentCodex 必须只作以下计划修正：

1. 在 §2.3 以相同六元组格式登记 `dayu/host/durable/state.py:40:5` 的 F401；定向命令必须覆盖最终 planned changed Python paths。
2. 在 R05-S1 `durable/state.py` 动作中明确：除删除 invalid `mark_wait_record_poll_abandon_timeout(...)` primitive 外，同时删除当前 base 已证明未使用的 `TERMINAL_RUN_STATUS_VALUES` import；这只是 touched-file lint hygiene，不扩大 durable semantic diff。
3. 保持 `tests/host/test_phase7_waiting_integration.py` 删除未使用 `UTC` import 的既有要求。
4. 将 §9.2 全量 Ruff residual 预期从 `167 - 1 = 166` 改为 `167 - 2 = 165`；仍须逐六元组核对其它 residual，不能只比较数量。
5. 对 S1 atomic completion、allowlist / stop condition 中任何“`state.py` 只允许删除 primitive”的绝对表述作同源收窄，使上述唯一 import hygiene 明确合法；不得借此清理其它 Ruff 项或扩大产品修改。

## 4. Rejected 子结论

MiMo 称 §9.2 changed-file Ruff 命令遗漏 `tests/host/test_wait_record_state.py`。该判断与 immutable target 直接矛盾：计划文件修改时间早于 MiMo review，且 §9.2 命令已经列出该路径。该子结论拒绝，不允许制造无实际 diff 的“修复”。

AgentDS 对 PF-01 至 PF-04、owner、state machine、smoke、slice 与延期边界的复核仍有效；仅其 changed-file Ruff / residual count PASS 被本次直接工具证据 supersede。

## 5. 下一 gate

AgentCodex 必须在同一 R05 plan 任务中：

1. 修订唯一 plan artifact，关闭 `R05-PRR-F01`；
2. 新增 `docs/reviews/wu-semantic-ownership-01-r05-plan-rereview-fix-codex.md`，记录 before/after、直接 Ruff 证据与 exact diff paths；
3. 只允许修改上述两个文件；不得修改产品、测试、README、design、control 或既有 review/controller artifact；
4. 运行 changed-file directed Ruff read-only probe、全量 Ruff baseline probe、`git diff --check` 和 exact path 检查；
5. 不 commit、不进入 implementation。

完成并经 Controller validation 后，AgentMiMo / AgentDS 必须再次对完整最终计划并发 re-review；不得只检查 `R05-PRR-F01` 局部 diff。
