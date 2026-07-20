# WU-SEMANTIC-OWNERSHIP-01 R05-S1 Validation Plan Correction — AgentMiMo Review

## 1. Gate 与 verdict

- umbrella：`WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation。
- 内部 remediation sub-WU / slice：既有 `R05-S1`。
- plan correction artifact：`docs/reviews/wu-semantic-ownership-01-r05-s1-validation-plan-correction-codex.md`。
- plan-drift Controller adjudication：`docs/reviews/wu-semantic-ownership-01-r05-s1-validation-plan-drift-controller-adjudication.md`。
- plan correction Controller validation：`docs/reviews/wu-semantic-ownership-01-r05-s1-validation-plan-correction-controller-validation.md`。
- 修订后 plan 全文：`docs/host/wu-semantic-ownership-01-r05-wait-observation-state-machine-plan.md`。
- implementation artifact：`docs/reviews/wu-semantic-ownership-01-r05-s1-implementation-codex.md`。
- 原 accepted plan review chain：`docs/reviews/wu-semantic-ownership-01-r05-plan-second-rereview-controller-adjudication.md` 及其引用的两路 final review。

**verdict：PASS / zero finding。**

本 review 覆盖修订后 plan 全文、plan-drift Controller adjudication、AgentCodex correction artifact、Controller validation artifact、当前七路径 S1 产品/test/design diff、implementation artifact、原 accepted plan review chain 与 scheduler direct source/test evidence。修订后的 plan 正确地将 R05 changed-owner coverage measurement 与独立 scheduler lifecycle owner 解耦，同时完整保留全部 R05 功能矩阵、逐文件覆盖率门禁、静态检查、scan、README decision 与后续 aggregate gate。

## 2. Finding ledger

| # | 挑战点 | 结论 | 证据 |
|---|--------|------|------|
| F01 | 排除整个 `test_dispatch_scheduler.py` 是否隐藏 R05 regression | **不隐藏** | 该文件对 `wait_adapter`、`WaitPoller`、`WaitObservation`、`WaitRecord`、`mark_wait_record_poll_abandon_timeout`、`_MarkWaitRecordAbandonTimeoutOperation`、`release_wait_record_poll_claim`、`wait_observation_timeout`、`wait_abandon_timeout` 的 source scan 为零命中；`dayu/host/dispatch.py` 与 `dayu/host/engine_ingest.py` 相对 R05 plan base 无 diff。scheduler close / terminal promotion 线性化缺口已由确定性 probe（`workspace/tmp/test_r05_scheduler_close_probe.py`，`1 passed`）独立证实，root cause 与 R05 timeout semantic transaction 无传播交集 |
| F02 | 排除是否构成一般失败豁免或削弱安全/coverage | **不构成** | plan 明确禁止新增第三个 ignore/deselect/xfail/retry/failure exemption；coverage measurement 仍要求整体绿色；两个实际 changed production files 仍分别执行 `--fail-under=80`；排除的文件受各自 owner 的项目矩阵治理 |
| F03 | §7 functional matrices 是否被 coverage measurement 替代 | **未替代** | plan diff 的 §7 无 hunk；§8 开头明确声明"本节 session 只测量 R05 两个实际 changed production owner 的覆盖率，不是完整 Host regression acceptance，也不能替代、删减或放宽 §7.1 的任何功能节点" |
| F04 | measurement 整体绿色与逐文件 >=80% 是否可执行 | **可执行且不被 aggregate 掩盖** | 独立运行验证：`1830 passed, 2 skipped, 5 deselected`；`durable/state.py=83%`、`wait_adapter.py=86%`；两个 `coverage report --fail-under=80` 均通过。逐文件门禁独立于 session 整体计数 |
| F05 | scheduler root cause 是否被错误标为 flake/inherited/已修复 | **未被错误标记** | plan §12 完整记录六元组、失败 session 结果、确定性 probe `1 passed`、同源 root cause 五步事件顺序与 disposition："这不是 flake、不是 inherited pass、不是已修复问题，也不是 R05 timeout semantic transaction 的失败" |
| F06 | residual owner/destination 是否足够 | **足够** | plan §15 明确登记为"Host scheduler close / terminal promotion coordination：scheduler `close()` 先提交私有 close gate……这是已由确定性 probe 复现的独立 Host lifecycle owner 缺口，不属于 R05 timeout transaction"；"当前 umbrella 不修复、不创建 issue、不归入 Issue 175；后续 destination 只能由 Controller / 用户另行裁决" |
| F07 | gate、stop conditions、baseline registry、completion handoff 是否自洽 | **自洽** | §13 stop condition 12 条完备；§12 baseline registry 包含完整六元组与 disposition；§14 completion handoff 要求 Controller validation → 双路 review → fix/re-review → Controller adjudication → accepted plan-correction commit → 恢复 R05-S1 validation；当前 gate 统一为 `WAITING_FOR_CONTROLLER_VALIDATION_AFTER_R05_S1_VALIDATION_PLAN_CORRECTION` |
| F08 | S1 diff 是否只实现 non-terminal release/backoff | **是** | `wait_adapter.py`：poll timeout 改为 `_release_with_backoff(...)` + `ADAPTER_ERROR/wait_observation_timeout`，保持 WAITING；abandon timeout 改为同一路径 + `ABANDON_ERROR/wait_abandon_timeout`，保持 CANCELLED，不写 `poll_abandoned_at`；删除 `_MarkWaitRecordAbandonTimeoutOperation` 与 import。`durable/state.py`：删除 `mark_wait_record_poll_abandon_timeout(...)` 定义与 unused `TERMINAL_RUN_STATUS_VALUES` import |
| F09 | 是否保留 late-publication fence、claim CAS、capacity、shared close deadline、authoritative typed lost、explicit lifecycle terminal | **全部保留** | implementation artifact §5 focused matrix 已覆盖：token invalidation、shared close deadline、Ready、NotReady、authoritative typed lost、adapter exception、capacity、explicit applied terminal、abandon retry、active/expired claim、invalid deadline、durable explicit lifecycle terminal。`_wait_observation.py`、`waiting.py` 无 diff |
| F10 | R04 config ownership 是否保留 | **保留** | §1.2 完整列出 12 字段 policy 与三个 packaged provider modes；§13 stop condition 8 禁止 R04 变化；implementation artifact focused matrix 包含 R04 preservation nodes |
| F11 | 是否偷带 scheduler fix、Issue 175、callback、统一 authorization、R05-S2 或 R06+ | **未偷带** | `git diff --unified=0 HEAD -- dayu/host/wait_adapter.py dayu/host/durable/state.py | grep -i 'authorization\|permission\|callback transport\|process isolation\|process_backed\|subprocess\|Issue 175'` 零命中；plan §1.3 明确非目标清单；§6 closed allowlist 精确；§13 stop condition 11 禁止 allowlist 外文件 diff |
| F12 | 受保护七路径 digest 是否一致 | **一致** | `3439b542e4a4785aaff5be56d93c87e17065d13d0d370742475c3e9e595b0ba2`，correction 前后均匹配 |
| F13 | `git diff --check` 是否通过 | **通过** | 无 whitespace error |

## 3. 旧 findings closure

原 accepted plan review chain 的 findings 保持已关闭：

| Finding | 状态 | 本轮验证 |
|---------|------|----------|
| `R05-PF-01` cancelled abandon 长期 capped retry residual | CLOSED | §2.1 / §4 / §15 保持同源；不发明 terminal evidence |
| `R05-PF-02` smoke timing 可执行性 | CLOSED | event/condition/state-poll、monotonic deadline、named margins 完整 |
| `R05-PF-03` Host design close marker 真源纠错 | CLOSED | S1 精确 writeback，保留 explicit lifecycle terminal |
| `R05-PF-04` invalid timeout-only durable primitive | CLOSED | storage owner deletion、owner test、zero-symbol guard 完整 |
| `R05-PRR-F01` touched-file Ruff registry | CLOSED | 两条 F401 已清理，full residual 预期 165 |

本次 correction 不重新打开任何已关闭 finding。

## 4. 独立验证结果

| 验证项 | 命令 | 结果 |
|--------|------|------|
| 受保护七路径 digest | `git diff --binary -- <7 paths> \| shasum -a 256` | `3439b542e4a4785aaff5be56d93c87e17065d13d0d370742475c3e9e595b0ba2` |
| 修订后 coverage session | `pytest -q tests/host --ignore=... --cov=...` | `1830 passed, 2 skipped, 5 deselected` |
| `durable/state.py` coverage | `coverage report --include=... --fail-under=80` | 83% PASS |
| `wait_adapter.py` coverage | `coverage report --include=... --fail-under=80` | 86% PASS |
| `git diff --check` | `git diff --check HEAD` | PASS |
| scheduler source scan | `grep -c <R05 symbols> test_dispatch_scheduler.py` | 0 命中 |
| dispatch.py R05 diff | `git diff 5ba0d8b6 -- dayu/host/dispatch.py` | 无 diff |
| engine_ingest.py R05 diff | `git diff 5ba0d8b6 -- dayu/host/engine_ingest.py` | 无 diff |
| §7 plan diff hunks | `git diff HEAD -- plan.md \| grep §7` | 无 §7 hunk |
| deferred scope scan | `git diff --unified=0 \| grep <deferred keywords>` | 零命中 |
| 确定性 probe | `pytest workspace/tmp/test_r05_scheduler_close_probe.py` | `1 passed`（由 Controller 已验证） |

## 5. Retained safety

修订后的 plan 完整保留：

- late-publication token/generation fence（`_wait_observation.py` 无 diff）
- claim CAS、release/backoff 唯一真源（`_release_with_backoff` 唯一调用点）
- outstanding capacity 与 shared close deadline
- authoritative typed `WaitPollLost` 经 common resolver terminalize
- explicit applied / unsupported / noop lifecycle 写 terminal `poll_abandoned_at`
- invalid timeout-only symbol production/tests 零定义零调用
- R04 config ownership：12 字段 policy、三个 typed modes、provider config owner
- `durable/schema.py` 无 diff；`poll_abandoned_at` 继续只承载 explicit lifecycle terminal
- Engine `agent.py` no-diff regression 固化

## 6. Deferred scope

与原 accepted plan 一致，本次 correction 不改变 deferred scope：

- scheduler close / terminal promotion coordination 线性化缺口（registered non-R05 residual owner boundary）
- Issue 175 process isolation / process-backed containment
- callback transport 与 authenticated callback ingress
- unified authorization / permission schema
- future Host cancel/abandon durable evidence policy
- future Host LOST durable evidence policy
- R06+ semantic ownership remediation

## 7. Reviewed paths 与 commands

### 读取的文件

1. `AGENTS.md`
2. `/planreview` skill 全文
3. `docs/phaseflow-umbrella-optimization-control.md`
4. `docs/host/issues-implementation-control.md` R05 状态
5. `docs/reviews/wu-semantic-ownership-01-r05-s1-validation-plan-drift-controller-adjudication.md`
6. `docs/reviews/wu-semantic-ownership-01-r05-s1-validation-plan-correction-codex.md`
7. `docs/reviews/wu-semantic-ownership-01-r05-s1-validation-plan-correction-controller-validation.md`
8. `docs/host/wu-semantic-ownership-01-r05-wait-observation-state-machine-plan.md` 全文
9. `docs/reviews/wu-semantic-ownership-01-r05-s1-implementation-codex.md`
10. `docs/reviews/wu-semantic-ownership-01-r05-plan-second-rereview-controller-adjudication.md` 及其引用的两路 final review
11. 当前七路径 S1 产品/test/design diff（`git diff HEAD`）
12. `dayu/host/dispatch.py:2557-2715`（close/wake/health gate）
13. `dayu/host/engine_ingest.py:2764-2787`（terminal promotion retry）
14. `dayu/host/_execution_health.py:240-290`（forced gate）
15. `tests/host/test_dispatch_scheduler.py:4900-4941`（失败节点）
16. `workspace/tmp/test_r05_scheduler_close_probe.py`

### 运行的 read-only commands

1. `git diff --name-only HEAD`
2. `git diff --stat HEAD`
3. `git diff --binary -- <7 paths> | shasum -a 256`
4. `pytest -q tests/host --ignore=... --cov=...`（coverage measurement）
5. `coverage report --include=... --fail-under=80`（两文件各自）
6. `git diff --check HEAD`
7. `grep -c <R05 symbols> test_dispatch_scheduler.py`
8. `git diff 5ba0d8b6 -- dayu/host/dispatch.py`
9. `git diff 5ba0d8b6 -- dayu/host/engine_ingest.py`
10. `git diff HEAD -- plan.md | grep §7`
11. `git diff --unified=0 HEAD -- <production files> | grep <deferred keywords>`

## 8. 修正建议

无。本次 correction 的修订内容正确、完整、可执行。

## 9. 是否需要 fix / re-review

- **fix**：不需要。
- **re-review**：本次为零 finding，不需要 re-review。
- **下一动作**：Controller adjudication。通过后恢复 R05-S1 validation。

## 10. Controller follow-up closure 验证

AgentCodex correction artifact §10 记录了 Controller follow-up 指出的三处旧 gate 文本冒充当前 gate 的修复。验证：

- §0 已改为"同一 `R05-S1 validation plan correction` 已完成，当前等待 Controller validation"
- §14 已删除旧 second-plan-fix 当前态，改为"本 correction artifact 已完成并等待 Controller validation"
- §15 末尾已改为"Controller validation 当前 R05-S1 validation plan correction"

三处 stale 字符串扫描在修订后 plan 全文中零命中。
