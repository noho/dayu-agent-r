# WU-SEMANTIC-OWNERSHIP-01 R05 第二轮 Plan Re-Review Fix（AgentCodex）

## 1. Gate 身份与边界

- umbrella：`WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation；不是新 WU。
- 当前 gate：R05 第二轮 plan-fix；plan base / HEAD 为 `5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1`。
- 唯一权威 finding：Controller `ACCEPTED_NARROWED` 的 `R05-PRR-F01`。
- 已拒绝子结论：§9.2 changed-file Ruff 命令遗漏 `tests/host/test_wait_record_state.py`。当前 immutable plan 已包含该路径，本轮不制造无实际 diff 的修复。
- `R05-PF-01` 至 `R05-PF-04` 保持关闭；不新增 product decision、semantic owner、slice 或 allowlist。
- 本轮只修改 plan target 并新增本 artifact；不修改产品、测试、README、design、control 或既有 artifact，不进入 implementation，不 commit/push。

## 2. 动机与直接证据

问题成立，但边界很窄：`dayu/host/durable/state.py` 已是 R05-S1 的 planned changed owner file，其 base 上的 F401 与 changed-file 集合相交。若计划只删除测试中的 unused `UTC`，implementation 的 changed-file Ruff zero gate 必然失败；这不是产品语义缺口，也不需要新增 owner。

在未修改产品、测试的固定 base / HEAD 上直接复核：

```text
branch: phaseflow/host-issues-control
HEAD: 5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1
git diff --exit-code 5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1 -- dayu tests utils: PASS
```

计划 §9.2 的完整 changed-file Ruff 命令：

```bash
python -m ruff check \
  dayu/host/durable/state.py \
  dayu/host/wait_adapter.py \
  tests/host/test_wait_observation_runner.py \
  tests/host/test_wait_adapter_polling.py \
  tests/host/test_phase7_waiting_integration.py \
  tests/host/test_wait_record_state.py \
  tests/engine/test_agent_phase3_tool_call.py \
  utils/smoke_host_public_awaiting_entrypoint.py
```

返回：

```text
dayu/host/durable/state.py:40:5
F401 dayu.host.durable._row_rules.TERMINAL_RUN_STATUS_VALUES imported but unused

tests/host/test_phase7_waiting_integration.py:8:22
F401 datetime.UTC imported but unused

Found 2 errors.
```

全量只读 probe `python -m ruff check dayu tests utils` 返回 `Found 167 errors`。两条 touched-file F401 都在该 base registry 内，因此 implementation 后的精确数量预期是 `167 - 2 = 165`；数量相符仍不足以继承，必须逐六元组核对其它 residual。

## 3. `R05-PRR-F01` Before / After

| 位置 | Before | After | 直接依据 |
|---|---|---|---|
| §0 gate 状态 | 上一轮 plan-fix 已完成，写作直接进入双路 re-review | 标记第二轮 plan-fix 只关闭 `R05-PRR-F01`，完成后停回 Controller validation；PF-01..04 保持关闭 | Controller §5 规定先 AgentCodex second plan fix，再 Controller validation 与完整双路 re-review |
| §2.3 定向 Ruff 基线 | 只登记测试文件 `UTC` 的一条 F401，命令未表达最终 planned changed Python paths | 使用最终 changed-file 路径命令，以相同六元组分别登记 `state.py:40:5` 与测试 `:8:22` 两条 F401 | 固定 base 的 directed Ruff 直接返回两条 F401 |
| R05-S1 `state.py` 动作 | 绝对措辞只允许删除 invalid primitive 及其专属代码 | primitive 删除之外，同时只删除已登记的 unused `TERMINAL_RUN_STATUS_VALUES` import；明确这是 touched-file lint hygiene，不改变 durable contract | `state.py` 是既定 S1 owner file，F401 会阻断 changed-file zero gate |
| `test_phase7_waiting_integration.py` | 要求删除 unused `UTC` import | 原要求完整保留 | Controller 明确要求保留该项 |
| §0 owner 边界 / S1 atomic completion / §6.2 allowlist / §13 stop / §14 handoff | 对 `state.py` 的绝对边界只容纳 primitive 删除 | 同源收窄为“primitive 相关删除 + 唯一已登记 import hygiene”，并继续禁止其它 lint cleanup、schema 或产品扩域 | Controller `R05-PRR-F01` 第 5 项 |
| §9.2 full Ruff residual | `167 - 1 = 166` | `167 - 2 = 165`，仍逐六元组核对 | directed Ruff 为 2 条 changed-file F401；full Ruff base 为 167 |
| §9.2 `test_wait_record_state.py` 路径 | 已存在 | 无 diff | Controller 以 immutable plan 直接证据拒绝 MiMo 子结论 |

## 4. Finding 关闭判定

`R05-PRR-F01` 在 plan 层已关闭：

1. §2.3 已用六元组登记 `dayu/host/durable/state.py:40:5` 的 F401，并保留测试文件 F401 登记；exact command 覆盖最终 planned changed Python paths。
2. R05-S1 明确要求在删除 invalid primitive 的同时删除 `TERMINAL_RUN_STATUS_VALUES` unused import。
3. `tests/host/test_phase7_waiting_integration.py` 删除 unused `UTC` 的要求未丢失。
4. full Ruff residual 预期已从 166 改为 165，且保留逐六元组校验规则。
5. §0 owner 边界、S1 atomic completion、allowlist、stop condition 与 review handoff 已同源收窄；没有授权其它 lint cleanup 或产品扩域。
6. PF-01..04、owner、slice、allowlist 与产品裁决均未重开。

## 5. Exact Diff Paths 与验证

本 gate 的唯一预期写路径：

```text
docs/host/wu-semantic-ownership-01-r05-wait-observation-state-machine-plan.md
docs/reviews/wu-semantic-ownership-01-r05-plan-rereview-fix-codex.md
```

只读/静态验证：

| 检查 | 结果 |
|---|---|
| fixed-base product/test diff | `PASS`；`dayu tests utils` 相对 base 无 diff |
| `python -m pyright dayu/ tests/ utils/` | `PASS`；`0 errors, 0 warnings, 0 informations` |
| directed Ruff base probe | 预期非零；精确为上述 2 条 F401 |
| full Ruff base probe | 预期非零；精确为 167 条既有 errors |
| `git diff --check` | `PASS` |
| 两个本 gate 文件的 untracked-content whitespace check | `git diff --no-index --check /dev/null <path>` 均无 whitespace diagnostic；exit 1 仅表示 no-index 内容不同 |
| exact path/status 检查 | 两条均为预期 `??`；相对 preflight status 唯一新增路径是本 artifact，既有 worktree 改动保持原状 |

exact target status：

```text
?? docs/host/wu-semantic-ownership-01-r05-wait-observation-state-machine-plan.md
?? docs/reviews/wu-semantic-ownership-01-r05-plan-rereview-fix-codex.md
```

对 `dayu`、`tests`、`utils`、README、design 与 umbrella control 等禁止写路径执行 fixed-base `git diff --exit-code` 为 0。完整 tracked diff name-only 仍只有 preflight 已存在的 `docs/host/issues-implementation-control.md`；本轮没有修改它。

本轮是文档 plan-fix，未修改 Python，因此没有受影响的 pytest，也未运行功能测试；按仓库修改后检查执行 pyright sanity check 并全绿。Ruff 只作为用户与 Controller 要求的 read-only base probe。README 触发检查结论为不更新：本轮没有已实现 contract，且 README 不在 gate write allowlist。

## 6. 残余风险与下一 gate

- implementation 尚未发生：两条 F401 当前仍真实存在。该风险由未来经授权的 R05-S1 同 slice 删除与 changed-file Ruff zero gate 覆盖，本轮不得提前修改代码。
- full Ruff 的其余 165 条是 implementation 后的预期 residual，不以数量相等自动豁免；必须逐六元组证明与 R05 changed source / propagation 不相交。
- 若 `state.py` 实施需要超出 invalid primitive、仅服务其 invalid semantic 的代码与唯一已登记 import hygiene，必须停止交 Controller，不得清理其它 Ruff 项或扩产品 scope。
- MiMo 关于 §9.2 路径遗漏的子结论已被直接证据否定；本轮无该处 diff，避免把正确计划改坏。
- 没有未分类的新产品、owner、slice、allowlist 或 blocking question；既有 §15 residual owners 保持原归属。

本轮停在 second plan-fix，等待 Controller validation。未经 Controller 接受，不启动 AgentMiMo / AgentDS 下一轮完整 plan re-review，不进入 implementation、commit、push 或 PR。
