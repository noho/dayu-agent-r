# Phase 10 Slice 2 Code Review Fix — AgentCodex

执行者：AgentCodex
日期：2026-05-18
范围：Slice 2 compaction typed contract、quality result invariant 测试、README 同步

## 处理结论

本轮按总控裁决修复 DS blocking / medium / residual R2 项；未实现 Slice 3+，未提交、未 push、未创建 PR，未引用或写入外部本地参考仓库路径。

## Finding 处理表

| 来源 | 编号 | 裁决 | 处理状态 | 说明 |
| --- | --- | --- | --- | --- |
| DS | B1 | 必须修复 | 已修复 | `CompactionRequest.__post_init__` 先校验 `current_message_summary` 是否为 `CurrentMessageSummary`，再访问 `current_user_input_ref`，非法类型现在稳定抛 `TypeError`。 |
| DS | M1 | 必须补测 | 已修复 | 新增非法 `current_message_summary` 类型直测，覆盖 B1 回归路径。 |
| DS | M2 | 必须补测 | 已修复 | 新增 `CompactQualityCheckResult` accepted/rejected invariant 直测。 |
| DS | R2 | 当前 slice 修复 | 已修复 | `ContextCompactionTriggerSource.REACTIVE` 现在要求 `attempt_id` 与 `execution_id` 均非 `None` 且非空；proactive 仍允许为 `None`。 |
| MiMo | M1 | 与 DS B1 同源 | 已修复 | 同 DS B1。 |
| MiMo | L1 | 可不修 | 未处理 | 私有 tuple 校验错误消息细化不是当前裁决项。 |
| MiMo | L2 | 可不修 | 未处理 | `to_json` 列表推导简化是风格项，非当前修复目标。 |
| MiMo | L3 | 可不修 | 未处理 | 私有 helper 重复未扩散到第三处，非当前修复目标。 |

## 修改摘要

- `dayu/host/compaction.py`
  - 调整 `CompactionRequest.__post_init__` 校验顺序，避免非法 `current_message_summary` 触发 `AttributeError`。
  - 增加 reactive compaction request 的 Attempt / execution ref 必填校验。
- `tests/host/test_compaction_contract.py`
  - 增加非法 `current_message_summary` 类型测试。
  - 增加 reactive `attempt_id` / `execution_id` 缺失或空字符串测试。
  - 增加 `CompactQualityCheckResult` accepted/rejected invariant 测试。
- `dayu/host/README.md`
  - 同步 Host Context Governance 文档：proactive refs 可为 `None`，reactive refs 必须非空。

## 验证结果

| 命令 | 结果 |
| --- | --- |
| `source .venv/bin/activate && pytest tests/host/test_compaction_contract.py tests/host/test_compact_artifact_store.py -q` | 通过，17 passed |
| `source .venv/bin/activate && pyright` | 通过，0 errors / 0 warnings / 0 informations |
| `git diff --check` | 通过 |

## 剩余风险

- DS R3 / MiMo residual：`open_questions_retained=False` 当前仍是记录项，不作为拒绝原因；该语义需由后续 orchestration slice 明确。
- 真实 LLM compactor adapter 与 canonical compact event 接入仍属于 Slice 3+ / 后续 slice 范围，本轮未实现。
- MiMo low findings 未处理，均非当前总控要求的阻塞项。
