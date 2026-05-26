# Gateflow implementation artifact：public memory scenario smoke S4

- Gate：implementation
- Work unit：Host public conversation memory scenario smoke
- Slice：S4 README/docs and final local validation
- Approved plan：`docs/reviews/gateflow-plan-public-memory-scenario-smoke-20260526.md`
- Role：implementation worker；未启动 gateflow controller，未进入其它 gate，未 commit / push / PR。

## 范围

允许文件：

- `README.md`
- `tests/README.md`
- `docs/reviews/gateflow-implementation-public-memory-scenario-smoke-s4-codex-20260526.md`

非目标：

- 不修改 smoke 脚本、scene asset、测试代码或生产代码。
- 不运行真实 LLM smoke。
- 不读取或验证 durable DB、EventLog、memory 表、compact payload 或真实 Fins。

## 变更文件

- `README.md`
  - 保留 5.2 最小 Host public 财报对话记忆 smoke。
  - 新增 5.3 Host public 财报对话记忆场景 smoke。
  - 说明 `utils/smoke_host_public_conversation_memory_scenarios.py` 的 `--suite core|long|all`，默认 core，long 需要显式运行。
  - 明确脚本只使用 `manual-smoke` mock finance tool，不调用真实 Fins，不读取 durable DB、EventLog、memory 表或 compact payload 内容。
  - 将 Engine provider smoke 从 5.3 顺延为 5.4。
- `tests/README.md`
  - 在 assembly helpers 覆盖说明中加入 `test_smoke_host_public_conversation_memory_scenarios_assembly.py`，覆盖 CLI suite 解析、mock finance tool 装配、tool selection、pressure 文本和 slot key 语义。
- `docs/reviews/gateflow-implementation-public-memory-scenario-smoke-s4-codex-20260526.md`
  - 记录本 slice 的文档决策、验证结果和剩余风险。

## 文档决策

本 slice 只更新根 README 的手工 smoke 用户入口和 tests README 的测试覆盖说明。没有把 scenario 编排、fixture 数据、内部 Host / memory 实现细节写入 README，避免用户手册越界为实现文档。

## 验证结果

```bash
source .venv/bin/activate && pytest tests/runtime/test_scene_assets_migration.py tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py -q
.................                                                        [100%]
17 passed in 0.89s
```

```bash
source .venv/bin/activate && pyright
0 errors, 0 warnings, 0 informations
```

真实 LLM smoke 未运行；本 slice 的目标是 README/docs 与本地轻量验证，真实 provider smoke 属于人工入口，运行成本、网络、secret 与 provider 可用性不适合作为此 handoff 的自动验证。

## 剩余风险

- public smoke 仍只能通过最终回答间接验证 conversation memory 语义，不读取内部 memory 单调演进；owner：Host memory 单元 / 集成测试继续覆盖。
- 真实 provider 行为未在本 slice 运行；owner：operator 按 README 手工执行 smoke。

## 停止状态

S4 文档更新和指定本地验证已完成；未 commit / push / PR，停止并交回 controller。
