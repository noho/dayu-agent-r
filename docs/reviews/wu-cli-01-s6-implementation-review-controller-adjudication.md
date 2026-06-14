# WU-CLI-01 / CLI-01-S6 Implementation Review Controller Adjudication

## Gate / Scope

- Gate: code review。
- Work unit: WU-CLI-01。
- Slice: CLI-01-S6，`upload_filings_from` batch plan generation。
- Design sources: `docs/host/design.md`、`docs/engine/design.md`。
- Control doc: `docs/host/ui-implementation-control.md`。
- Accepted plan: `docs/host/wu-cli-01-cli-entrypoint-plan.md`。
- Implementation report: `docs/reviews/wu-cli-01-s6-implementation-codex.md`。
- Review artifacts: `docs/reviews/wu-cli-01-s6-implementation-review-mimo.md`、`docs/reviews/wu-cli-01-s6-implementation-review-ds.md`。

## Controller Judgment

总控裁决：**pass-with-fix**。

两路 review 均确认 S6 的核心边界成立：`upload_filings_from` 的业务语义迁移到当前 Fins typed boundary，未搬迁旧实现或旧隐式目录规则；Fins helper 返回结构化 plan，不返回 shell text；CLI 只做 request 构造与脚本渲染；不启动 ingestion job，不创建 Host Run，不写 Host EventLog，不导入 Host / Engine / Service / Fins storage。

需要进入 fix gate 的问题不是架构阻塞，而是当前 slice 引入的可维护性重复与几个低成本错误路径测试缺口。Fix 后必须 re-review。

## Finding Adjudication

| Finding | Source | Decision | Rationale |
|---|---|---|---|
| S6-REVIEW-F01 / S6-RV-F02：upload suffix allowlist 在 `dayu.fins.upload_batch` 与 CLI 直接上传校验中重复 | MiMo / DS | accepted | 这是当前 S6 新增的真实重复。Batch plan 生成的可识别后缀与 direct upload 前置校验必须同源，否则未来支持新上传类型时会产生 batch 可生成但 direct 拒绝，或 direct 可上传但 batch 跳过的漂移。应把后缀集合收敛到 Fins public constant，由 CLI 复用。 |
| S6-REVIEW-F02 / S6-RV-F01：`_optional_stripped_text` 跨模块重复 | MiMo / DS | rejected-with-reason | 重复面并非 S6 新增孤例：`prompt`、`interactive`、`host_context`、`fins.py` 已存在相近但带不同 field-name 语义的 helper。为 S6 抽到 `dayu.runtime` 会扩大 slice、改变多条已通过 review 的 CLI path，并为一个简单文本 trim 引入新公共 API。当前 S6 中 Fins helper 需要保持不依赖 CLI；保留局部私有 helper 是当前 slice 的最小可维护选择。后续如要统一 CLI text normalization，应另设专门 WU。 |
| S6-REVIEW-F03：同步 `_run_upload_filings_from` 在 async wrapper 中执行 | MiMo | rejected-with-reason | 当前 CLI 进程没有并发 UI task，且 S6 明确是本地计划生成；同步目录扫描期间 KeyboardInterrupt 已映射为 130。使用 `asyncio.to_thread` 会增加线程边界、取消语义和测试复杂度，不是当前最佳实践。 |
| S6-REVIEW-F04：output 写失败测试未验证具体错误消息 | MiMo | rejected-with-reason | 当前要求是写 output 失败 exit 1 并输出原因；现有测试验证 exit 1 和 command 前缀。底层 `OSError` 消息跨平台差异较大，不应把测试绑定到具体异常文本。 |
| S6-RV-F03：`cast(BatchUploadAction, args.action)` 绕过类型检查 | DS | rejected-with-reason | argparse choices 是 CLI UI adapter 的运行时约束真源；同一文件的 direct upload action 也依赖 parser choices。额外 runtime guard 会重复 parser 规则，增加分支而不提高当前 correctness。 |
| S6-RV-F04：`entry.command_name == COMMAND_UPLOAD_MATERIAL` 混用 CLI 常量与 typed literal | DS | rejected-with-reason | `COMMAND_UPLOAD_MATERIAL` 是用户可见 CLI command name 真源，`BatchUploadCommandName` 的 literal 值也必须与 CLI command surface 对齐。使用该常量能避免命令名字符串漂移。 |
| S6-RV-F05：空 `--from` 错误路径无测试覆盖 | DS | accepted | 当前实现有明确分支，补测试低风险，能固定 exit 2 行为。 |
| S6-RV-F06：`material_forms` 空字符串错误路径无测试覆盖 | DS | accepted | Fins helper 是未来 GUI / internal caller 可复用边界；直接调用时该错误路径有意义，补测试低风险。 |
| S6-RV-F07：`source_dir` 为文件错误路径无测试覆盖 | DS | accepted | 当前实现有明确分支，补测试低风险，能固定 usage error 行为。 |

## Accepted Fix Scope

AgentCodex fix gate 只处理以下事项：

1. 将 upload suffix allowlist 收敛到 Fins boundary 的单一 public constant，并让 CLI direct upload precheck 复用该常量。
2. 补充三条测试：
   - `upload_filings_from --from ""` 或等价 parser namespace 空值路径返回 exit 2。
   - `UploadBatchPlanRequest(material_forms=("",))` 抛 `UploadBatchPlanUsageError`。
   - `source_dir` 是普通文件时抛 `UploadBatchPlanUsageError`。
3. 更新必要 README / tests README 仅在公共常量或测试说明变化需要时最小同步。

不得在本 fix gate：

- 抽取 `_optional_stripped_text` 到 `dayu.runtime`。
- 改写 CLI async/sync 边界。
- 改变 recognition rule。
- 扩大到 S7 `init`、Host management commands 或旧 CLI parity。

## Validation Baseline

Controller 已复跑：

- `source .venv/bin/activate && pytest tests/fins/test_upload_batch.py tests/cli/test_upload_filings_from_command.py tests/cli/test_fins_commands.py -q`：28 passed，3 条 edgar deprecation warnings。
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`：0 errors。
- `source .venv/bin/activate && pytest tests/fins/test_upload_batch.py tests/cli/test_upload_filings_from_command.py --cov=dayu.fins.upload_batch --cov=dayu.cli.commands.fins --cov-report=term-missing -q`：15 passed；`dayu/fins/upload_batch.py` 96%。
- `source .venv/bin/activate && pytest tests/cli/test_fins_commands.py tests/cli/test_upload_filings_from_command.py --cov=dayu.cli.commands.fins --cov-report=term-missing -q`：22 passed；`dayu/cli/commands/fins.py` 90%。
- `git diff --check`：clean。

## Residual Risks

| Risk | Classification | Owner / Destination |
|---|---|---|
| 旧 CLI 完全 recognition parity | deferred-with-owner | Fins owner；沿用 `WU-CLI-01-RR-04`，后续如需更完整识别规则需定义 typed recognition contract |
| `SUCCEEDED` direct command 输出缺少 `result_summary` 摘要 | deferred-with-owner | CLI / Fins product owner；沿用 `WU-CLI-01-RR-08` |

## Completion Status

CLI-01-S6 code review gate is pass-with-fix. Next gate: AgentCodex fix accepted findings, then MiMo / DS re-review.
