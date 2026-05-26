# Gateflow Implementation Artifact: Host public conversation memory scenario smoke S3

## Gate 与范围

- 当前 gate：implementation。
- 角色：implementation worker，不是 controller。
- Work unit：Host public conversation memory scenario smoke。
- Slice：S3 assembly and pure helper tests。
- Approved plan：`docs/reviews/gateflow-plan-public-memory-scenario-smoke-20260526.md`。
- Accepted prior commits：S1a `2c98662`，S1b `b984460`，S2 `33077d1`。

## 动机判断

动机成立。新增场景 smoke 已进入脚本与资产层，但真实 LLM / Host end-to-end smoke 不适合作为自动测试；本 slice 用装配测试与纯 helper 测试覆盖运行前契约、CLI fail closed、固定规格生成、压力文本边界、mock tool 计数和回答断言，能在不读取内部 durable state 的前提下防止 runtime-only 回归。

用户给定的限定路径合理：本 slice 不需要改生产代码、scene assets、README 或既有测试。`tests/runtime/test_scene_assets_migration.py` 已包含新 scene 约束，当前只作为验证目标运行。

## 变更文件

- `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py`
  - 新增 Host public 财报对话记忆场景 smoke 的 assembly / helper focused tests。
- `docs/reviews/gateflow-implementation-public-memory-scenario-smoke-s3-codex-20260526.md`
  - 新增本 implementation artifact。

## 已实现测试覆盖

- runtime assembly 默认注入内置 `get_mock_finance_memory_fact`，并确认新 scene 只选择 `manual-smoke` mock tool。
- workspace overlay 中出现同名非 `MockFinanceMemoryTool` 时 fail closed。
- CLI `--suite core/long/all` 成功；`--long-rounds 20/25` 成功；`19/26/0/-1` 通过 argparse fail closed。
- 纯 spec 选择：
  - core 最终累计工具调用数为 4。
  - long 首轮累计工具调用数为 1。
  - all 中 long 首轮累计工具调用数为 5。
  - long20 最后一轮保持 `long-l25-constraint-assert`。
- C2 比亚迪长输入生成确定，长度在 `8_000..15_000`，三个 anchor 各出现一次。
- `MockFinanceMemoryTool` 只统计 tracked session，已知 / 未知 fact 的 `calls_by_key` 摘要稳定。
- pressure off 返回空用户压力与空工具压力；auto padding 估算落在 soft threshold 以上、hard threshold 以下。
- answer normalization / required contains / forbidden contains 行为稳定。
- fresh / reuse session slot key 规则。
- provider contract 输出单个 manual-smoke 工具。

## 验证结果

```bash
source .venv/bin/activate && pytest tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py -q
```

结果：

```text
11 passed in 0.87s
```

```bash
source .venv/bin/activate && pytest tests/runtime/test_scene_assets_migration.py tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py -q
```

结果：

```text
17 passed in 0.71s
```

```bash
source .venv/bin/activate && pyright
```

结果：

```text
0 errors, 0 warnings, 0 informations
```

## 文档决策

未修改 README。原因：用户明确限定本 slice 只允许新增测试与 implementation artifact，且明确禁止修改 README；本次变更也没有改变用户命令、配置入口、scene asset 或生产接口。

## 残余风险

- 未运行真实 LLM / Host end-to-end smoke：这是本 slice 的明确 non-goal，真实 provider 行为仍由手工 smoke 和后续 gate 覆盖。
- 自动测试通过 public/runtime helper 与脚本 testable functions 验证装配与规格，不证明 Host 内部 compaction 或 memory projection 的具体状态；该内部语义由既有 host 单元 / 集成测试承担。

## Stop Status

当前 implementation slice 完成。未提交、未推送、未进入 code review、fix、PR 或其它 gate。
