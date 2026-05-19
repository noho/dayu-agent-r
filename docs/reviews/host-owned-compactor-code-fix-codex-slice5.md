# Host-owned compactor Slice 5 fix artifact

## 范围

- Gate: Slice 5 review 后 fix gate
- 角色: implementation fix agent，不是总控
- 分支: `feat/host-p10-5-public-contract-freeze`
- 约束: 不提交 commit，不 push，不改 unrelated 文件

## Root Cause

总控失败现象是首个 public compact run 进入 `FAILED`，terminal message 为 `Context compaction failed before dispatch`；EventLog 中出现 `CONTEXT_COMPACTION_ATTEMPT_REJECTED`，`failure_category=proposal_failed`，diagnostic suffix 为 `LLMCompactionProposalError`。

本机复跑 `pytest tests/host/test_public_compact_smoke.py -q -rs` 及额外连续 3 次复跑均通过，因此该问题不是稳定的本地断言错误或 artifact 读取错误。直接代码证据显示失败链路成立：

1. `LLMContextCompactor.compact()` 要求 Engine public runner 返回 `EngineRunOutcomeFinalAnswer`，否则抛出 `LLMCompactionProposalError`。
2. Slice 5 smoke 使用真实 DeepSeek compactor，原配置 `RunnerSpec.max_retries=0` 且 `ContextBudgetPolicy.max_compaction_attempts_per_operation` 沿用默认 `1`。
3. Host proactive compaction operation 捕获 proposal exception 后，在唯一 attempt 用尽时写 `CONTEXT_COMPACTION_ATTEMPT_REJECTED` / `CONTEXT_COMPACTION_FAILED`，并把未 dispatch 的 Run 收口为 `FAILED`。
4. 原实现把 `EngineRunOutcomeFailed` 等非 final outcome 统一压成 `compactor runner did not return final answer`，Host diagnostic 又只保留异常类名，导致真实 provider 的临时错误、协议错误、length/非 final 行为都不可分类。

判断：问题被高估为“测试断言错误”是不成立的；真实问题是 public smoke 在真实 provider 可用但偶发非 final / transient runner outcome 时过于脆弱，同时 Host-owned compactor 对 runner outcome 的脱敏诊断不足。

## 改动

- `dayu/host/llm_compaction.py`
  - 对非 final `AgentRunResult` 生成脱敏 proposal 失败摘要。
  - `EngineRunOutcomeFailed` 保留 `error_code`、`recoverable` 和截断后的短 message。
  - 对 `Bearer ...`、`Authorization=...`、`api_key=...` 做脱敏；不包含 provider request id、API key、headers 或完整 provider payload。

- `tests/host/test_llm_compaction.py`
  - 更新非 final outcome 断言。
  - 新增 failed runner outcome 脱敏测试，覆盖 503 / transient 文本保留与 secret 不泄漏。

- `tests/host/test_public_compact_smoke.py`
  - compactor runner 显式设置 `max_retries=1`。
  - compact policy 显式设置 `max_compaction_attempts_per_operation=2`。
  - 保持 public opener -> Host-owned `LLMContextCompactor` -> artifact 的生产接线，不恢复 Service 注入 `ContextCompactor`。

- `utils/smoke_host_public_multiturn.py`
  - manual smoke 的 compactor runner 关闭 DeepSeek thinking extension，显式设置 `max_retries=1`。
  - compact policy 显式设置 `max_compaction_attempts_per_operation=2`。
  - stdout 仍只输出 artifact 摘要，不输出 API key、Authorization header、完整 prompt 或 provider payload。

## README 决策

本次改动没有改变用户命令、公开配置入口、Host public contract 或文档中需要同步的稳定行为；`dayu/host/README.md` 与根 README 不更新。`tests/README.md` 也不更新，因为测试分层与运行方式未变化。

## 验证

- `source .venv/bin/activate && pytest tests/host/test_public_compact_smoke.py -q -rs`
  - 结果: `1 passed`
- `source .venv/bin/activate && pytest tests/host/test_public_compact_smoke.py -q -rs` 连续额外 3 次
  - 结果: 3 次均 `1 passed`
- `source .venv/bin/activate && pytest tests/host/test_llm_compaction.py -q`
  - 结果: `6 passed`
- `source .venv/bin/activate && python utils/smoke_host_public_multiturn.py --help`
  - 结果: 正常输出 help
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - 结果: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 结果: 通过，无输出

## 残余风险

- 真实 provider 仍可能连续两次返回非 final / provider failure；此时 smoke 应失败而不是伪装成功，因为生产 Host-owned compactor 链路确实没有 accepted compact output。
- Host terminal message 仍是治理层通用失败文案；更细粒度的 public terminal 错误分类若要进入 contract，需要后续单独设计，不在 Slice 5 fix 范围内。
- 本次未查看或打印真实失败环境中的 provider payload、API key 或 Authorization header。
