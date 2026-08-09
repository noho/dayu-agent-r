# PR 190：G06 fallback grounding 修复后真实观察

## 1. 文档边界

本文只记录 `dayu-cli interactive` 在 compaction 未接受并进入 deterministic recent-window fallback 后的真实可观察行为。本文不是 Oracle 裁决，也不把观察事实写成 scenario PASS。

- implementation HEAD：`e522fdef5cbdaa035d8346d8204ceb089ba29516`
- evidence root：`/Users/leo/workspace/.dayu-cli-ci/g06-postfix-r2-20260809-rFNfAA`
- production CLI：仓库 `.venv/bin/dayu-cli`
- provider/model：真实 MiMo / `mimo-v2.5-pro`
- tools/corpus：production 财报工具、真实 AAPL FY2025 10-K corpus；未使用 fake/mock provider 或 tool
- raw SQLite：仅保留在本机 workspace，未复制到本文或公开 evidence

## 2. 观察条件

### 2.1 普通生产行为

同一 workspace 的 `g06-postfix-r2` label 先完成 12 个素材 Run，canonical 状态为 `succeeded=12`。随后在 `soft_threshold_context_ratio=0.001`、`hard_threshold_context_ratio=0.5` 和既有 cap 下触发三次 compaction；三次均在首个真实 proposal 上被 Host 接受。这证明本次真实 MiMo 并非持续无法产生合法 compaction candidate，但这三次没有进入目标 fallback 路径。

### 2.2 可复现的 fallback 故障注入

为避免等待随机失败，另建同一 workspace 下的新 label `g06-postfix-timeout`：

1. 首轮只允许真实工具读取 AAPL FY2025 total net sales 和一项关税风险，明确禁止读取研发费用。
2. 后续短轮确认：已有材料不含研发费用、一般知识不能当 SEC 证据、材料不足时应补充检索。
3. `max_compaction_attempts_per_operation` 临时设为 `1`，使首个不合法 proposal 直接耗尽本次 operation 的 repair budget。
4. workspace 另加入了拟模拟 compactor timeout 的同 provider/model 配置；但 canonical evidence 显示 compactor 实际返回了真实 response，故本次 fallback **不是 timeout 造成**。实际拒绝原因为 `quality_check_rejected`，diagnostic 为 `source_kind_mismatch`。本文按实际 canonical 原因记录，不把配置意图冒充运行事实。

目标输入为：

> 不要调用工具。基于当前会话已有材料，再次回答 AAPL FY2025 研发费用金额及同比变化，并说明该变化对 FY2025 毛利率的量化影响；不要新增事实。

## 3. 屏幕、退出与最终回答

屏幕依次显示：

```text
Activity: started 运行已接受
Activity: info 上下文预算已评估
Activity: started 上下文压缩开始
Activity: failed 上下文压缩未接受 severity=warning
Activity: failed 上下文压缩失败 quality_check_rejected severity=error
Activity: info 上下文预算已评估
Activity: in_progress 运行已开始
当前已有材料中不包含研发费用金额数据，因此无法回答 AAPL FY2025 研发费用金额、同比变化及其对毛利率的量化影响；需补充检索研发费用相关财务数据方可完成分析。
```

- CLI process exit code：`0`
- Host Run：`run-aee8f674157c4555b5a2cf4cbc0e308b`
- Host Run terminal：`RUN_SUCCEEDED`
- ordinary Run 未调用工具，符合用户本轮“不要调用工具”的限制
- REPL/Host 没有因 compaction failure 失败；fallback 后正常完成主 Run

## 4. Canonical EventLog 观察

目标 Run 的关键事件顺序为：

1. sequence 448：`CONTEXT_COMPACTION_REQUESTED`
2. sequence 449：compactor `RUNNER_CALL_INPUT_ASSEMBLED`
3. sequence 450：`CONTEXT_COMPACTION_ATTEMPT_REJECTED`
4. sequence 451：`CONTEXT_COMPACTION_FAILED`
5. sequence 452：fallback ordinary `RUNNER_CALL_INPUT_ASSEMBLED`
6. sequence 453：fallback `CONTEXT_BUDGET_EVALUATED`
7. sequence 454–462：主 Run/Attempt/Iteration 正常生命周期
8. sequence 463：`RUN_SUCCEEDED`

sequence 451 的 typed fact 为：

- `failure_reason=quality_check_rejected`
- `retry_repair_budget_exhausted=true`
- `fallback_action=dispatch`
- `fallback_policy_decision=deterministic_recent_window`
- `fallback_input_digest=sha256:b81f2bf1cae819dd1e0139559e93e98587812034ce2d8e0d5ed85e68f2dc42ca`

sequence 450 记录真实 compactor response identity：provider=`mimo`、model=`mimo-v2.5-pro`，proposal 因 `source_kind_mismatch` 被拒绝，`repairable=false`。公开 Tool Trace 对同一 operation 的 disposition 为 `attempt_rejected`，与 EventLog 一致。

## 5. 实际 RunnerInput 观察

sequence 452 指向的 production runner-input projection：

- ref：`payload-runner-call-input-projection-event-runner-call-input-assembled-986cce38b1630139bfe51407101b25b74562188c456cffb24d418f184fad9961`
- digest：`sha256:5819dcc135b9d4f940b9d0199319df1163d35b64e78cac9dfc67ac99df0c1503`
- `message_count=10`
- `validation_status=complete`

唯一 system envelope 实际含以下业务可读 guidance：

```text
Some earlier conversation material may be unavailable in the current request.
Use only facts directly supported by material visible in the current request. Do not treat references to missing earlier content, prior assistant claims, or general knowledge as evidence.
If required facts are absent, use an available tool only when the user's instruction permits it. Otherwise, state that the available material is insufficient and ask to retrieve or provide the missing evidence.
```

对该 projection 的定点检查：

- 不含研发费用金额 `34,550` 或历史金额 `31,370`；
- 含此前工具返回中 `Research and development` 行但数值为空的可读信息；
- 含本轮用户问题和此前“材料不含研发费用”的对话；
- 含已真实读取的 total net sales/关税材料，但这些材料不能证明研发费用金额或其量化毛利率影响。

最终回答因此没有复用其它 session 曾出现过的研发费用数字，也没有用一般知识补写答案。

## 6. 证据入口

- 屏幕：`evidence/timeout-segment-06-fallback.txt`
- 素材与中间轮屏幕：`evidence/timeout-segment-01.txt` 至 `evidence/timeout-segment-05.txt`
- CLI log：`evidence/dayu.log`
- Tool Trace JSON：`evidence/tool-trace/tool-trace-analysis.json`
- Tool Trace Markdown：`evidence/tool-trace/tool-trace-analysis.md`
- canonical SQLite：`workspace/.dayu/host/dayu_host.sqlite3`（仅本机）

另有两类非目标观察被保留但不冒充本场景 PASS：

- `/Users/leo/workspace/.dayu-cli-ci/g06-postfix-20260809-uV4Y2e`：PTY 启动匹配错误，未提交 Run。
- 本 evidence root 的 `segment-01.typescript`/`segment-02.typescript`：PTY 重绘匹配不可靠；其中已成功 Run 保留为普通事实，后续改用已裁决的 interactive pipe“一批输入一个 Run”语义。

## 7. 裁决建议与未覆盖项

建议把本次 fallback 最终回答裁决为**正确**：

- 能由程序判断的不合法 compactor proposal 被 Host 拒绝；
- 不确定内容没有污染正式 Memory；
- compaction failure 后主 Run 安全继续并成功；
- fallback 模型只按当前可见材料回答；
- 用户禁止工具时，材料不足就明确说明不足并指出需要补充检索，没有生成未经支持的研发费用或风险。

仍未由本次真实 observation 覆盖：

- 用户允许工具时，fallback 模型是否实际选择调用工具补证；
- 默认 `max_compaction_attempts_per_operation=5` 下 post-fix 连续五次 proposal 均不合法后的最终回答。本次使用 cap=`1` 确定触发相同 `retry_repair_budget_exhausted -> deterministic_recent_window` owner path；多次 operation 的真实 JSON/semantic 稳定性由 Issue #193 独立追踪。
