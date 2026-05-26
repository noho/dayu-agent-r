# gateflow aggregate deepreview controller adjudication — public memory scenario smoke (2026-05-26)

## 范围

本裁决覆盖当前工作单元 `e38913c..HEAD`：保留既有最小化 `utils/smoke_host_public_conversation_memory.py`，新增 Host public API only 的 conversation memory scenario smoke、scene asset、assembly tests、README / tests README 与对应 gateflow artifacts。

## Review 输入

- AgentDS aggregate deepreview artifact：`docs/reviews/gateflow-aggregate-deepreview-public-memory-scenario-smoke-ds-20260526.md`
- Review 结论：PASS，无 blocking finding。
- 非阻塞 residual：真实 LLM scenario smoke 未在自动 review 中运行；conversation memory 语义通过 public answer 间接验证，不替代 Host memory 单元 / 集成测试；`_PROVIDER_IMPORT_DISPLAY_PATH` 继承既有 `__main__` display path pattern。

## Controller 裁决

接受 AgentDS aggregate PASS。本工作单元的成功信号是新增 public smoke harness 与装配 / 边界测试可用，而不是在 review gate 内强制消耗真实 provider 调用。真实 LLM 运行依赖 provider secret、网络和成本，保留为 operator 手动 smoke，不作为 ready-to-open-draft-PR 阻塞项。

接受 public answer 间接验证为该 smoke 的合理边界：脚本明确禁止读取 durable DB、EventLog、memory 表或 compact payload，避免把 public contract smoke 退化为内部投影测试。Host memory 物化语义仍由 Host 层 focused tests 承担。

接受 `_PROVIDER_IMPORT_DISPLAY_PATH` 为 non-blocking residual：当前脚本通过 `discover_from_bindings(provider=discover_smoke_tools)` 传入 callable，该 display path 不被解析。后续若统一 smoke provider display path，应同时处理既有 `smoke_host_public_multiturn.py` pattern。

## Controller 验证

- `source .venv/bin/activate && pytest tests/runtime/test_scene_assets_migration.py tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py -q`：17 passed
- `source .venv/bin/activate && pyright`：0 errors, 0 warnings, 0 informations
- `git diff --check`：passed

## Gate 结论

当前工作单元达到 `ready-to-open-draft-PR`。后续若进入 PR gate，应推送当前分支到 PR 68，并在 PR 上追加本工作单元 review / validation 结论。
