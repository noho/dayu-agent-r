# WU-CLI-01 / CLI-01-S5 Implementation Review Controller Adjudication

## Gate / Scope

- Gate: code review。
- Work unit: WU-CLI-01。
- Slice: CLI-01-S5，Fins direct job Service boundary and direct commands。
- Design sources: `docs/host/design.md`、`docs/engine/design.md`。
- Control doc: `docs/host/ui-implementation-control.md`。
- Accepted plan: `docs/host/wu-cli-01-cli-entrypoint-plan.md`。
- Implementation report: `docs/reviews/wu-cli-01-s5-implementation-codex.md`。
- Review artifacts: `docs/reviews/wu-cli-01-s5-implementation-review-mimo.md`、`docs/reviews/wu-cli-01-s5-implementation-review-ds.md`。

## Controller Judgment

总控裁决：**PASS**。

本轮 review 的核心判断标准是：迁移旧 direct data commands 的业务语义，并适配当前 approved Service/Fins boundary；不是搬迁旧 CLI 实现。两路 review 均未发现 blocking finding。实现满足 S5 accepted plan：

- Fins direct commands 不创建 Host Run，不写 Host EventLog，不伪装成 Host wait。
- CLI 通过 `dayu.service.fins_direct` 启动 durable Fins ingestion job、轮询 terminal、请求 durable cancel。
- Service helper 构造 Fins typed request；CLI 只做 UI adapter 参数转换、轻量输入校验、stdout/stderr 与 SIGINT 映射。
- upload wrapper 使用 `runtime.start_upload(request)` union API，不要求 runtime 暴露 `start_upload_filing(...)` / `start_upload_material(...)`。
- `upload_filings_from`、`--infer`、`--ci` 按 accepted plan fail fast / deferred，不偷做旧逻辑。
- `prompt` / `interactive` 既有 Service assembly -> Host public API 路径未被破坏。

## Finding Adjudication

| Finding | Source | Decision | Rationale |
|---|---|---|---|
| S5-REVIEW-F01: `tests/cli/test_fins_commands.py` 缺少模块级 docstring | MiMo | rejected-with-reason | 证据不成立。`tests/cli/test_fins_commands.py:1` 已有模块级 docstring：`"""``dayu-cli`` Fins direct commands 测试。"""`。 |
| S5-REVIEW-F02: `_FinsSigintMonitor.notify` 未对未使用参数执行 `del` | MiMo | rejected-with-reason | 这是风格一致性建议，不是 AGENTS.md 或 pyright 要求。参数以下划线前缀表达兼容 signal handler 签名，`python -m pyright dayu/ tests/ utils/` 为 0 errors；不应为了非问题进入 fix gate。 |
| S5-RV-O01: SUCCEEDED 输出未展示 `result_summary` | DS | deferred-with-owner | 当前 accepted plan 只要求 terminal exit mapping、job id 可追踪和 direct command boundary；`dayu/cli/output.py:137-142` 输出 job id 满足 S5 pass。更丰富的业务摘要属于 CLI output UX follow-up，owner: CLI / Fins product owner；destination: 后续 CLI output polishing 或 S6 后统一 direct command result display。 |
| S5-RV-O02: 无 `loop.add_signal_handler` 平台静默降级 | DS | deferred-with-owner | 当前目标运行环境是 macOS/Linux SelectorEventLoop；`dayu/cli/commands/fins.py:134-140` 的降级不阻塞本 slice。该风险归入 cross-platform signal adapter / Fins cancel responsiveness，owner: CLI runtime / Fins runtime owner；destination: 延续 `WU-CLI-01-RR-06` 或后续跨平台 cancel WU。 |

## Evidence Highlights

- Plan 允许 CLI 导入 Fins 枚举 / request 类型和只读 domain value，但禁止直接读写 Fins storage：`docs/host/wu-cli-01-cli-entrypoint-plan.md:202`。
- CLI 对 Fins 的直接依赖只包含 `SourceKind` 枚举：`dayu/cli/commands/fins.py:40`；CLI storage guard 测试扫描 `dayu.fins.storage` import：`tests/cli/test_fins_commands.py:686-708`。
- Fins cancel 行为有测试覆盖：第一次 SIGINT 后 `request_cancel(job_id)` 并等待 terminal：`tests/cli/test_fins_commands.py:543-571`；第二次 SIGINT 本地退出并打印 job id：`tests/cli/test_fins_commands.py:574-614`；job id 前 KeyboardInterrupt 不请求 durable cancel：`tests/cli/test_fins_commands.py:617-660`。
- Signal cancel 状态机在 CLI 层，不在 Service 层：`dayu/cli/commands/fins.py:423-468`。
- SUCCEEDED 输出当前只打印 job id：`dayu/cli/output.py:137-142`；这不是 S5 accepted plan 的 blocking requirement。

## Validation

Controller 已复跑：

- `source .venv/bin/activate && pytest tests/service/test_fins_direct.py tests/cli/test_fins_commands.py -q`：22 passed，3 条 edgar deprecation warnings。
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`：0 errors。
- `git diff --check`：clean。

AgentCodex implementation report 与双路 review 还记录了：

- `source .venv/bin/activate && pytest tests/cli tests/service tests/fins/test_fins_ingestion_runtime.py -q`：195 passed。
- `dayu/service/fins_direct.py` 覆盖率 92%；`dayu/cli/commands/fins.py` 覆盖率 88%。

## Residual Risks

| Risk | Classification | Owner / Destination |
|---|---|---|
| `upload_filings_from` 未实施 | covered by later approved slice | CLI-01-S6 |
| `--infer` alias inference 未实施 | deferred-with-owner | Fins owner；后续 alias inference WU；沿用 `WU-CLI-01-RR-01` |
| `--ci` process snapshot 未实施 | deferred-with-owner | Fins / tooling owner；后续 CI snapshot contract WU；沿用 `WU-CLI-01-RR-02` |
| Fins cancel responsiveness 取决于 ingestion pipeline checkpoint | deferred-with-owner | Fins runtime owner；沿用 `WU-CLI-01-RR-06` |
| 无 `add_signal_handler` 平台无法提供 durable cancel UX | deferred-with-owner | CLI runtime / cross-platform signal adapter owner；归入 `WU-CLI-01-RR-06` destination |
| SUCCEEDED direct command 输出缺少 `result_summary` 摘要 | deferred-with-owner | CLI / Fins product owner；后续 CLI output polishing 或 S6 后统一 result display |
| `upload_filing --action delete` runtime 支持仍需验证 | deferred-with-owner | Fins owner；沿用 `WU-CLI-01-RR-07` |

## Completion Status

CLI-01-S5 code review gate passed. No accepted blocking finding; no fix / re-review gate required for S5. Next gate: accepted slice commit for CLI-01-S5.
