# WU-CLI-DEBUG-STREAM-01 Slice 4 Implementation

## 目标

更新 `--debug-stream` 的用户可见文档和测试覆盖职责说明，不修改生产代码、测试代码或控制文档。

## 已读取的 README 约束

- `README.md`：已读取 `Agent更新约束【必须遵守】`。该文档是最终用户使用手册，只写当前可用 CLI / Web / WeChat 入口、用户可见参数、输出、日志和排障信息，不写内部架构、测试清单、work unit 状态或开发者迁移计划。
- `tests/README.md`：已读取 `README 更新边界`。该文档只描述当前 `tests/` 已存在的测试事实、运行方式和维护规则，不写用户手册、Engine 设计文档、review prompt、未落地测试体系或时间敏感记录。
- `dayu/host/README.md`：已读取 `Agent更新约束【必须遵守】`。该文档只写当前 `dayu.host` package 的稳定开发接口、公共契约、架构、关键路径和机制，不写用户手册、测试清单或 work unit 状态。
- `dayu/engine/README.md`：已读取 `Agent更新约束【必须遵守】`。该文档只写当前 `dayu.engine` package 的稳定开发接口、公共契约、架构、事件流、Runner 机制和扩展点，不写用户手册、测试清单或 work unit 状态。

## 改动

- 更新 `README.md` 的 CLI 共享参数，新增 `--debug-stream`。
- 说明 `--debug` 是普通诊断，`--debug-stream` 是高频 stream delta / SSE / 逐 delta ingest 诊断，且单独使用 `--debug-stream` 已包含普通 `DEBUG` 诊断。
- 明确 activity stream 与 Python logging 诊断日志分离：`--detail` 控制终端 activity stream，`--debug` / `--debug-stream` 控制诊断日志。
- 更新 `prompt` / `interactive` 参数摘要与示例，补齐 `--debug-stream` 的用户可见入口。
- 更新 `tests/README.md`，记录 CLI、runtime logging、Host ingest logging、Engine OpenAI Runner diagnostics 的覆盖职责。

## 未改文档的理由

- 未修改 `dayu/host/README.md`：本 Slice 没有新增 Host public contract、状态机、EventLog 语义、HostEvent 语义或 package-level 开发接口；Host ingest delta 只是日志级别重分类，稳定用户说明放在根 README，测试职责放在 tests README。
- 未修改 `dayu/engine/README.md`：本 Slice 没有新增 EngineEvent / RunnerEvent contract、RunnerSpec / RunnerCallOptions 字段或 Engine public API。Engine README 现有可观测日志段落属于 developer-facing package semantics；本次只需在用户手册和测试手册记录 `--debug-stream` 行为与覆盖职责，避免把 CLI flag 写进 Engine 包手册。

## 验证

- `git diff --check`：通过。
- `git diff --check README.md tests/README.md`：通过。
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`：通过，0 errors / 0 warnings / 0 informations。

## 残余风险

- 根 README 现有 `--log-level` 仍列出 `critical`，但当前 CLI parser choices 为 `debug`、`verbose`、`info`、`warn`、`error`。该不一致已在计划中标为既有非本 WU 范围，Slice 4 未扩大修复。
- 本 Slice 只更新文档，不重新运行 pytest；前序 Slice 已由代码和测试覆盖 `--debug-stream` 行为，本 Slice 按要求运行 diff check 与 pyright。
