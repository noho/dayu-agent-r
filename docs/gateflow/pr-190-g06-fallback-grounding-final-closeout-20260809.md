# PR 190：G06 fallback grounding final closeout

## 1. Final verdict

- Gateflow work unit：**FINAL CLOSEOUT PASS**
- implementation：**PASS**
- deterministic owner validation：**PASS**
- fresh real observation：**已完成，待用户 Oracle 裁决**
- Oracle/scenario registry：**未修改、未擅自标记 ready**
- scope drift：**无**

本 closeout 只关闭 G06 fallback grounding 修复，不宣称 init/prompt/interactive 总体 readiness 已闭环。

## 2. Root cause 与 owner 修复

Root cause：Host 在 compaction failure 后已经正确选择 deterministic recent-window fallback，但 ordinary RunnerInput 没有获得与该截断事实同源的业务可读 grounding guidance。模型因此可能把缺失历史的间接引用、prior assistant claim 或一般知识当成证据，生成当前可见材料不支持的事实。

唯一 owner 为 Host ordinary RunnerInput projection：

- `dayu/host/run_input.py` 从 typed `ActiveRecentWindowFallback` 事实派生一次性 LLM-facing guidance；
- 无 fallback 时不投影；
- fallback 时复用既有唯一 system envelope，不新增 developer/assistant 伪历史消息；
- guidance 不向模型暴露 Host、compaction、tier 或内部 ref/digest；
- durable manifest、projection artifact 和实际 RunnerInput 从同一 projection 真源派生。

未修改 compactor parser、repair、fallback selection、Memory、schema、provider、状态机、terminal semantics 或最终回答自然语言 verifier。

## 3. Accepted commits

- `c7a937e1`：accepted plan
- `907a6ab3`：owner implementation、tests、design/README
- `540cff06`：accepted deepreview
- `e522fdef`：accepted PR review

## 4. Deterministic validation

- focused owner cases：4 passed
- affected suite：`tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py`，238 passed
- `dayu/host/run_input.py` affected coverage：83%
- full pyright：0 errors、0 warnings、0 informations
- changed Python Ruff：PASS
- compileall：PASS
- `git diff --check`：PASS
- implementation code review：PASS，无 finding
- deepreview：PASS，无 finding
- PR review：PASS，无 finding

Owner tests使用 deterministic test runner/fake 检查 exact projection contract；这些结果没有被表述成真实 provider observation。

## 5. Fresh real observation

Evidence root：

`/Users/leo/workspace/.dayu-cli-ci/g06-postfix-r2-20260809-rFNfAA`

使用 production `dayu-cli interactive`、真实 MiMo、production 财报工具和真实 AAPL FY2025 10-K corpus，未使用 fake/mock provider 或 tool。

目标 fallback Run 的 canonical chain：

- `CONTEXT_COMPACTION_REQUESTED`
- 真实 compactor response 因 `source_kind_mismatch` 被 Host 拒绝
- `CONTEXT_COMPACTION_FAILED`：`retry_repair_budget_exhausted=true`、`fallback_action=dispatch`、`fallback_policy_decision=deterministic_recent_window`
- fallback ordinary RunnerInput `validation_status=complete`
- 主 Run 最终 `RUN_SUCCEEDED`，process exit 0

实际 RunnerInput 含新的 grounding guidance；当前可见 material 不含研发费用金额 `34,550`/`31,370`。最终回答明确说明当前材料不足、没有生成研发费用数字或量化毛利率影响，并要求补充检索。

故障注入边界：临时 scenario 把 `max_compaction_attempts_per_operation` 收紧为 1。另配置了拟模拟 timeout 的 compactor alias，但 canonical evidence 证明实际 provider 返回了 response；真实 failure 原因是 proposal `source_kind_mismatch`，不是 timeout。报告按 canonical 原因记录。

Observed report：`docs/reviews/pr-190-g06-fallback-grounding-postfix-observed-20260809.md`

Digests：

- target screen：`332e7735c54fcb79324a529c1bba3eb208cdcbc854b0dc47a64f1882257b77d2`
- Tool Trace JSON：`d20a75693d729267dc5de31fecfcf5cc29d0866cdd17014db94c1194cad479b6`
- observed report：`f4cefda475ebc0c6bf9b31d0b7a11cf12116eda4a7bd6d18236b648d19a881d4`
- exact credential scan：14 个当前可用 credential values、25 个 evidence/report files、0 hit、0 unreadable；未记录 credential 值

## 6. Reviews 与文档

- plan review：`docs/reviews/plan-review-20260809-112541.md`
- implementation review：`docs/reviews/code-review-20260809-113640.md`
- deepreview：`docs/reviews/code-review-20260809-113833.md`
- PR review：`docs/reviews/pr-190-review-20260809-114000.md`
- design truth：`docs/host/design.md`
- Host README：`dayu/host/README.md`

Engine design、Engine README、Config README、分层 README 与根 README 经职责检查无需修改；CLI 参数、安装、workspace 位置和最终用户命令面没有变化。

## 7. Residual risks / next owner

1. 用户尚未裁决本次 post-fix observed behavior；在裁决前不能更新 accepted Oracle 或把 scenario 标记 ready。
2. 本次没有真实覆盖“用户允许工具时，fallback 模型主动调用工具补证”。owner guidance 已覆盖该分支，但仍需单独运行、观察、裁决后才能进入正式 scenario。
3. 默认 repair budget=5 下的多次真实 compaction output 稳定性由 Issue #193 独立追踪；它不阻塞本 owner 修复，但不能把 cap=1 observation 冒充五次连续失败的概率测量。
4. 真实 provider 输出仍非确定性；Host parser/repair/fallback 是 fail-closed 防线。
5. 两个早期 PTY driver 尝试按原状态保留；未删除、覆盖或重标为 PASS。

下一入口：用户根据 observed report 裁决 G06 fallback 最终回答；接受后再更新对应 Oracle/scenario，并回到 init/prompt/interactive readiness 检查。
