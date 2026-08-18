# UF-FIX01 fiscal-period prevalidation residual — S2 Re-Review Adjudication

## Gate metadata

- work unit：`UF-FIX01-fiscal-period-prevalidation-residual`
- MiMo re-review：`docs/reviews/code-review-20260818-023449.md`（pass）
- DS re-review：`docs/reviews/code-review-20260818-024134.md`（2 low findings）
- status：`fix-required`
- next entry point：AgentCodex final S2 fix

## Findings adjudication

1. DS 001（activate/run 位于 try/finally 外）：`accepted`。把 `activate_observation` 与
   `executor.run_next()` 移入 try，使任何激活/执行异常都经 finally abandon；清理断言保持。
2. DS 002（UF-024 case id 被重命名、new cases 未注册）：`partially accepted / partially deferred`。
   - 接受恢复现有 CN case id 为原值 `UF-024`，并让 seeded 判定继续使用该 id；本 work unit 不应无意改写
     accepted scenario 的既有追踪锚点。
   - 新增 US/HK case 的 scenario registry/oracle 注册分配给后续真实 CLI calibration workstream。用户明确禁止本
     work unit 修改 frozen evidence、accepted oracle 或 scenario registry，因此本轮不得注册或刷新。

## Fix scope

- 只修改 `tests/fins/test_fins_ingestion_tools.py`、`tests/cli/test_fins_commands.py` 与既有 S2 fix artifact。
- 不修改 production、README、frozen evidence、oracle 或 scenario registry。
- focused、822 affected、全仓 pyright、diff-check 通过后进行两路最终 re-review。
