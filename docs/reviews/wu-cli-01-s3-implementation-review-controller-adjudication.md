# WU-CLI-01 / CLI-01-S3 Implementation Review Controller Adjudication

## 裁决

Pass。

本轮 review 的裁决标准是：迁移旧 `dayu-agent` prompt 的业务逻辑与用户可见语义，并适配新的 Host public contracts / API；不是迁移旧代码实现，也不以旧实现一致性替代当前 contract 正确性。

## Review 输入

- Implementation report: `docs/reviews/wu-cli-01-s3-implementation-codex.md`
- AgentMiMo review: `docs/reviews/wu-cli-01-s3-implementation-review-mimo.md`
- AgentDS review: `docs/reviews/wu-cli-01-s3-implementation-review-ds.md`

## 通过项

- `dayu-cli prompt` 通过 `ConfigLoader -> ScenePrepare -> ToolsDiscovery -> Service assembly -> Host public API` 触达 Host；未直接构造 Engine request，未访问 Host durable internals，未读取 Fins storage。
- CLI / Service 边界清晰：CLI adapter 负责参数、signal、stdout / stderr、exit code 与 Host context/id 构造；`dayu.service.entrypoint_runtime` 不解析 CLI、不安装 signal handler、不写终端，可被未来 WeChat / GUI 复用。
- `--ticker`、`--label`、`--model-name`、可映射 execution overrides 与 unsupported legacy flags 的处理符合 accepted plan。
- SIGINT 语义符合 plan：Host accepted Run 前本地 130；accepted 后构造 typed `CancelRunRequest` 并等待同一 Run terminal；重复 SIGINT 不产生重复 cancel request。
- `submit_entrypoint_turn_and_wait(..., on_run_accepted=...)` 不破坏 S2 的 watcher attach-before-submit、terminal observation、caller-owned timeout contract。
- AGENTS.md 约束未发现阻断问题：新增/修改函数中文 docstring、严格类型签名、无 `Any` / `object` / `hasattr` / `getattr` 逃逸、无兼容 wrapper、无越层 import。

## Findings 裁决

AgentMiMo：Pass，无 blocker 或 severity warning。

AgentDS：Pass，提出两个低风险非阻塞项。

- DS-F01：`render_prompt_terminal_result` 的 CANCELLED / LOST / SUCCEEDED-without-answer 分支无直接测试覆盖。
  - 裁决：non-blocking observation。
  - 理由：当前输出 helper 单文件覆盖率 80%，满足仓库单文件覆盖率门槛；S3 已覆盖 SUCCEEDED / FAILED 用户可见主路径、SIGINT cancel Host request 语义与 terminal status。该项不影响当前 Host public path 正确性。
  - 后续：如后续 slice 触碰 CLI output，可顺手补齐纯渲染单测；不进入当前 S3 fix gate。
- DS-F02：不支持 `loop.add_signal_handler` 的事件循环环境会降级为默认 `KeyboardInterrupt`，Run accepted 后不保证 typed cancel。
  - 裁决：non-blocking observation。
  - 理由：当前目标运行环境为 Python 3.11 下的 macOS / Linux 类 SelectorEventLoop；代码已明确降级语义，且 accepted plan 未要求 Windows ProactorEventLoop typed cancel。该项不是当前 S3 scope blocker。
  - 后续：若未来需要跨平台 CLI typed cancel，再单独设计 signal / cancellation adapter contract。

## Controller 验证

- `source .venv/bin/activate && pytest tests/cli/test_prompt_command.py tests/service/test_entrypoint_runtime_prompt_path.py tests/cli/test_arg_parsing.py tests/service/test_entrypoint_runtime.py -q`：62 passed，3 条 edgar deprecation warnings。
- `source .venv/bin/activate && pytest tests/cli/test_prompt_command.py tests/cli/test_arg_parsing.py --cov=dayu.cli.commands.prompt --cov=dayu.cli.host_context --cov=dayu.cli.output --cov=dayu.cli.arg_parsing --cov-report=term-missing -q`：41 passed，总覆盖率 95%；`arg_parsing.py` 100%，`prompt.py` 91%，`host_context.py` 98%，`output.py` 80%。
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`：0 errors。
- `git diff --check`：clean。

## 下一步

接受 CLI-01-S3 implementation。进入 CLI-01-S4 implementation gate。
