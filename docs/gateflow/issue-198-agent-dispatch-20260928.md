# issue #198 子 Agent 派发与总控裁决

日期：2026-09-28。工作区：`/Users/leo/workspace/dayu-agent-r`。本文件记录 `$sub-agents` 预检、进程和结构化结果，不能用 Agent 自述替代总控对代码/计划的裁决。

## plan：gpt-6-sol attempt 01

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: provider
```

- runtime/provider/model：`codex-agent-run` / `gpt-6-sol` / `gpt-6-sol`；task label `issue198-plan-sol-20260928-01`；显式 `--cwd /Users/leo/workspace/dayu-agent-r`；`--no-persist`。
- preflight：`sub-agent-preflight` 返回 `setup_status=ok`。exit status：0；JSONL 109 个有效 event，存在 `turn.completed`、49 个退出码 0 的 command_execution，stderr 为空，canary 与 `canary.expected` 逐字一致。计划 artifact：`docs/gateflow/issue-198-download-failure-projection-plan-20260928.md`。
- 原始输出：`/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.rJ8O63/issue198-plan-sol-20260928-01.jsonl`；stderr：同目录 `issue198-plan-sol-20260928-01.stderr`；last-message：同目录 `issue198-plan-sol-20260928-01.last.md`。
- 结构化失败：一条 `item.completed` 的 `command_execution` 状态 `failed`、exit 1；命令先读 `storage/__init__.py`，再用 `rg` 搜索反向 import，后者无匹配。该失败可能只是无匹配，但 `$sub-agents` 仅对白名单模型诊断提供非致命豁免，故整个调用不能作为已通过的 plan gate。总控保留其文件为**待验证草稿**，不进入 plan review。此项未重试或切换 provider；下次以新 label 重派同 provider，一次修复性重试。
- 总控尚未采纳 plan 设计。重点待核对：把 storage reason enum 直接加入通用 `FinsPublicFailure` 的耦合成本；在 `dayu.runtime` 新增 traceback helper 是否为当前目标最小方案；CLI 外层异常日志是否会泄漏 secrets。上述是 review 问题，非已确认 finding。

## plan：gpt-6-sol attempt 02

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: provider
```

- runtime/provider/model：`codex-agent-run` / `gpt-6-sol` / `gpt-6-sol`；task label `issue198-plan-sol-20260928-02`；显式 `--cwd /Users/leo/workspace/dayu-agent-r`；`--no-persist`。preflight 返回 `setup_status=ok`。exit status：0；JSONL 203 个有效 event、`turn.completed`、90 个退出码 0 的 command_execution、stderr 空、canary 逐字匹配；另有四条 command_execution status=failed（3 条 `rg` 引用了不存在的候选路径，exit 2；1 条 `git diff --no-index` 因有差异 exit 1）。按 `$sub-agents` 规则不判子 Agent 成功。此为唯一一次同 provider 修复性重试；不继续盲目重派。
- 输出：`/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.wexndD/issue198-plan-sol-20260928-02.jsonl`；同目录独立 `.stderr`、`.last.md`。Sol 修订了同一个 plan artifact，说明更窄的公共 reason enum、CLI 外层未知异常日志边界和无需 init 的真实 CLI 验证。
- 总控裁决：**不采纳两次子 Agent 的“成功”状态；采纳其 plan 文件为待两路 review 的候选 artifact**。总控直接核对 `source_integrity.py` 的封闭 enum/raise、`ingestion_runtime.py` 的异常映射与无日志 catch、`dayu/cli/commands/fins.py` 最后一个 raw `_LOGGER.exception` catch、`.venv/bin/dayu-cli --help` 和 `download --help` 的 `--base`/日期窗口参数，确认 plan 关键入口确实存在；候选计划仍须 Kimi/MiMo 两路 adversarial plan review 和总控裁决。此做法不把 Agent 的失败调用包装成 Gateflow plan pass，而由总控在 review gate 对可独立复核的文件作接受判断。
- retry/provider switch：按用户指定 gpt-6-sol 负责 plan，已用完同 provider 一次修复性重试；未切换到其它 provider。未解决风险：plan 的公共 enum 映射和安全调用栈细节可能过度设计或存在安全漏洞，交给两路 planreview 直接证伪。

## plan review：Kimi 与 MiMo 并行 attempt 01

两路分别以 `claude-agent-run --provider kimi|mimo`、绝对 `--cwd /Users/leo/workspace/dayu-agent-r`、唯一 label 和独立 output/stderr 派发。两路 preflight、exit 0、Claude `subtype=success`、`is_error=false`、canary 逐字匹配均已核验；`num_turns` 分别 46/75。stderr 仅各有一行白名单 `[claude-code:unrecognized_model]` warning。固定裁决块、原始输出路径、findings 和 controller 采纳/延期理由见 `docs/gateflow/issue-198-plan-review-adjudication-20260928.md`；review artifacts 为 `docs/reviews/plan-review-20260928-185948.md`、`docs/reviews/plan-review-20260928-190828.md`。两路均 `pass-with-risks`，controller 判计划需 fix/re-review，不凭 review 结论直接进入实施。

## plan fix：gpt-6-sol attempt 01

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: provider
```

- runtime/provider/model：`codex-agent-run` / `gpt-6-sol` / `gpt-6-sol`；label `issue198-plan-fix-sol-20260928-01`；绝对 `--cwd /Users/leo/workspace/dayu-agent-r`，独立 output/stderr/last-message；preflight ok，exit 0，103 条可解析 JSONL、`turn.completed`、canary 与 expected 逐字匹配，且有成功 command_execution。
- 结构化失败：一条 `command_execution` 因 memory 索引查询无匹配以 exit 1 / status failed 结束；stderr 另含 `apply_patch verification failed`，不属于豁免 warning。因此**本次 Agent 调用判 failed**，不把它当作 Gateflow fix pass。它确实只修订了 `docs/gateflow/issue-198-download-failure-projection-plan-20260928.md`，controller 静态核对 accepted finding 的文本已写入，保留为待两路 re-review 的候选 artifact，不将失败调用伪装成成功。
- 原始输出：`/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.rjvguo/issue198-plan-fix-sol-20260928-01.jsonl`；stderr 与 last-message 为同目录同 stem 的 `.stderr`、`.last.md`。本次是 plan review 后新的 fix gate，不是 plan attempt 02 的再次 provider retry。若 re-review 发现真实遗漏，再以新 label 作本 gate 最多一次有理由的修复性重试。
- 下一 gate：`plan re-review`。未进行产品代码修改、commit 或 push。

## plan fix：gpt-6-sol attempt 02（针对第一次 re-review 新 finding）

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- runtime/provider/model：`codex-agent-run` / `gpt-6-sol` / `gpt-6-sol`；label `issue198-plan-fix-sol-20260928-02`；显式绝对 `--cwd` 与独立 output/stderr/last-message；preflight ok，exit 0，90 条有效 JSONL event、`turn.completed`、37 条成功 command_execution，无 error/failed event，stderr 空，canary 逐字一致。
- output `/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.WxbDTp/issue198-plan-fix-sol-20260928-02.jsonl`；同目录同 stem `.stderr`、`.last.md`。总控核对 plan 的 CLI 单一提示、非 download 文案逐字不变、无来源文档不承诺 unknown 诊断、RESULT 先于日志与后续 work unit 登记均已写入；**仍须两路最终 re-review**，不因子 Agent 自述进入 implementation。

## 最终 plan re-review：Kimi 与 MiMo 并行 attempt 01

两路 `sub-agent-preflight` 均 ok，显式绝对 `--cwd`、独立 output/stderr、不同 instance/label。Kimi `issue198-plan-final-rereview-kimi-20260928-01`：exit 0，Claude `subtype=success`、`is_error=false`、`num_turns=28`、canary match，stderr 仅一条白名单 `[claude-code:unrecognized_model]`；output `/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.lec8vo/issue198-plan-final-rereview-kimi-20260928-01.json`，review `docs/reviews/plan-review-20260928-200635.md`，结论 `pass`。MiMo `issue198-plan-final-rereview-mimo-20260928-01`：exit 0，Claude `subtype=success`、`is_error=false`、`num_turns=26`、canary match，stderr 仅同类白名单 warning；output `/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.305OtA/issue198-plan-final-rereview-mimo-20260928-01.json`，review `docs/reviews/plan-review-20260928-200508.md`，结论 `pass`。两路原始 stderr 均在各自 output 同目录、同 stem `.stderr`。

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
canary_status: match
warnings:
  - "Kimi: [claude-code:unrecognized_model]"
  - "MiMo: [claude-code:unrecognized_model]"
retry_class: none
```

总控采纳最终 plan gate 结论与逐项 finding 状态见 `docs/gateflow/issue-198-plan-review-adjudication-20260928.md`；下一入口 `accepted plan commit`，再进入 S1 实施。
