# WU-CLI-01 Plan Re-Review Controller Adjudication

## Gate

- Work unit: WU-CLI-01 CLI entrypoint integration aligned with dayu-agent CLI
- Gate: plan re-review controller adjudication
- Timestamp: 2026-06-14T13:38:08+08:00
- Plan artifact: `docs/host/wu-cli-01-cli-entrypoint-plan.md`
- Re-review artifacts:
  - `docs/reviews/wu-cli-01-plan-rereview-mimo.md`
  - `docs/reviews/wu-cli-01-plan-rereview-ds.md`

## Controller Verdict

结论：pass。

两路 re-review 均确认 controller-adjudicated accepted findings 已关闭，且未发现新的 material blocker。WU-CLI-01 plan 可以进入 accepted plan commit，并可作为 implementation gate 的输入。

本裁决特别确认以下约束继续成立：

- 本轮迁移目标是旧 CLI 的业务语义、用户可见行为、参数面与 cancel 语义，而不是迁移旧代码实现、旧目录结构或旧内部 contract。
- Agent 命令路径必须保持 `UI adapter -> reusable Service boundary -> Host public API -> Engine`，不得绕过 Service 直接触达 Host internals 或 Engine。
- Fins 直接数据命令不伪装成 Host run，必须走 approved Service / Fins boundary，不得散落直接读取 Fins storage。
- interactive 所需的 session/follow-up/terminal observation/cancel/error mapping 应沉淀在可复用 Service 边界，不能写成 CLI-only 编排。

## Accepted Findings Status

| Finding | Controller status |
|---|---|
| `CancelRunRequest` 使用 `context` / `client_request_id` / `reason` / `mode=CancelMode.GRACEFUL` | closed |
| `ReadOutboxTerminalItemsRequest` 使用 `OutboxTerminalCursor`、`seen_terminal_event_ids`、projection status、`has_more` 与 caught-up-without-match policy | closed |
| `HostCallContext` 使用真实字段，且 UI adapter 与 reusable Service boundary 清晰 | closed |
| `compose_submit_followup_request_with_overrides(...)` 与 `ServiceRunOverrides` shape 具体且复用 `host_assembly` | closed |
| Fins upload wrapper 构造 typed request 后调用 `FinsIngestionRuntime.start_upload(...)` union API | closed |
| interactive watcher lifecycle 覆盖 attach-before-submit、`aclose()`、多轮隔离、failed/cancelled/lost policy | closed |
| explicit `--config` 行为具体 | closed |
| `--ticker` 映射到 `fins_default_subject`，`base_user` 默认值具体 | closed |
| `init --reset` 删除白名单明确，排除 Fins data、runtime lane DB 与用户文件 | closed |
| unsupported old flags fail fast，exit 2，无 silent ignore，无 raw payload | closed |
| Fins direct job poll interval 有命名默认值 | closed |
| interactive terminal fatal/nonfatal policy 具体 | closed |

## Residual Risk Routing

以下风险不阻塞 plan acceptance，但必须在总控文档中以 deferred-with-owner 跟踪：

- 旧 `--infer` alias inference 目前没有 approved Fins boundary。
- 旧 `--ci` process snapshot 目前没有公共 contract。
- 旧 debug / trace / duplicate governance flags 没有当前 Host public per-run contract。
- `upload_filings_from` 的旧文件识别规则可能依赖旧 Fins helper。
- `--thinking` / `--no-thinking` 不是当前模型 schema 中的独立布尔开关。
- Fins job cancel 是协作式，长事务可能延迟响应。
- `upload_filing --action delete` 是否由当前 Fins upload runtime 支持需在 implementation slice 中验证。

## Next Gate

- 更新 `docs/host/ui-implementation-control.md`，记录 re-review artifacts 与 deferred residual risks。
- 创建 accepted plan commit。
- accepted plan commit 完成后，进入 implementation gate，由 AgentCodex 按 accepted plan 实施。
