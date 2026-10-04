# Plan: `upload_filings_from` CLI 错误投影修复

- work unit: `upload_filings_from --output` workspace 外目标被降级为通用未知错误的 CLI typed error projection 缺口修复
- 任务定义: `/Users/leo/workspace/portfolio-manager/dayu-upload-download修复prompt.md`
- 基线: `ed7057cf`（分支 `codex/upload-material-oracle`，工作树 clean；交付不 commit / 不 push / 不建 PR）
- Goal Confirmation: 已经用户确认（2026-09-18，含分支归属与 Agent 路由裁决）

## 1. Goal / Motivation / Success Signal

**Goal**：`upload_filings_from --output <workspace 外路径>` 时，CLI stderr 投影 `UploadScriptPublishError` 的具体、安全、可操作消息（如 `output target escapes workspace root: ...`），退出码保持 `EXIT_FAILURE`。

**Motivation**：当前该 typed 错误未被 CLI adapter 映射，落入宽泛 `except Exception`，用户只看到 `命令执行失败，请使用 --log-file PATH 重试并查看日志`，无法得知是 output containment 违例。README 已公开承诺 output 必须位于 workspace 内并给出可操作错误，当前行为违反既有公开契约。

**Success Signal**：
1. `tests/cli/test_upload_filings_from_command.py::test_upload_filings_from_usage_empty_and_write_failures` 转绿；
2. 验收集合（`test_fins_commands.py`、`test_upload_filings_from_command.py`、`test_fins_service_runtime.py`、`test_filing_upload_publication.py`、`test_sec_pipeline_download_stream.py`、`test_cn_download_runtime.py`）无新增失败；
3. 同一 publisher contract 的其它 typed 错误变体（internal symlink、父目录不存在、目标类型非法）经 CLI 投影同样得到具体消息（新增测试逐一断言），且 workspace 外 output 未创建文件、workspace 内无临时文件残留；
4. generic 未知异常仍走 `_FINS_DIRECT_UNKNOWN_FAILURE_MESSAGE`，stderr 不泄漏内部异常消息（新增测试断言）；
5. `KeyboardInterrupt -> 130`、batch empty、source usage error、direct stream 既有映射不变；
6. pyright 无新增或扩散错误。

## 2. Non-Goals / Scope Boundary

- 不修改 portfolio-manager；不改变 upload/download 业务语义；不动 download 路径；
- 不新增兼容性 wrapper、下游 fallback、异常字符串解析或消息特判；
- 不把 `UploadScriptPublishError` 重分类为 usage error（回归测试明确要求 `EXIT_FAILURE`）；
- 不重构 `run_fins_direct_command` except 链整体结构；不为其它未映射 typed exception 预防性加分支；
- 不重构 publisher / planner / storage；不改 README（见 §7 决策）；
- 不 commit、不 push、不建 PR。

## 3. First-Principles 判断与直接代码证据

**问题真实存在**（已独立复现，非测试倒推）：

1. 复现命令实际 stderr 为 `dayu-cli upload_filings_from: 命令执行失败，请使用 --log-file PATH 重试并查看日志`，与任务描述一致。
2. 语义 owner：`dayu/cli/upload_script.py:273-337` `_resolve_publish_target` 拥有 output containment / symlink / target-type 校验；`upload_script.py:316` 正确抛出 `UploadScriptPublishError("output target escapes workspace root: {target}")`。
3. 无副作用：`publish_upload_script`（`upload_script.py:125-130`）在 `tempfile.mkstemp` 之前完成 target 解析，containment 失败不创建 target 文件、不产生 `.<name>.*.tmp` 临时文件残留。精确边界：`_resolve_publish_target` 内 `lexical_root.mkdir(parents=True, exist_ok=True)`（upload_script.py:300）位于 containment 检查（:315）之前，故 `--base` 目录本身可能被创建——这是 publisher 负责 bootstrap workspace root 的既有行为，不属于发布副作用，也非本 work unit 改变对象。
4. 投影缺口：`dayu/cli/commands/fins.py:175-218` `run_fins_direct_command` 的 except 链覆盖 `CliFinsUsageError / UploadBatchPlanUsageError / UploadBatchPlanEmptyError / FinsDownloadUsageError / FinsUploadUsageError / FinsUploadFormatError / FinsUploadPrevalidationError / FinsDirectStreamProtocolError / KeyboardInterrupt`，**无** `UploadScriptPublishError` 分支 → 落入 `fins.py:212` `except Exception` → `_FINS_DIRECT_UNKNOWN_FAILURE_MESSAGE`。
5. 全仓检索确认 `UploadScriptPublishError` 的消费方只有 `run_fins_direct_command` 这一处 CLI adapter 边界（除 publisher 自身与测试），无其它遗漏投影点。

**语义 owner 判定**：错误语义（containment 规则与消息文本）owner 是 `dayu.cli.upload_script`；typed error → exit code / stderr 投影的 owner 是 CLI adapter `dayu.cli.commands.fins.run_fins_direct_command`。修复必须且只需发生在 CLI adapter 的 except 链，不动 owner 层。

**严重性评估**：用户可见契约回归，但爆炸半径单一（单命令、单 typed 错误、无状态损坏），修复面极小。任务严重性评估恰当，不存在高估。

## 4. Affected Files

| 文件 | 改动性质 |
| --- | --- |
| `dayu/cli/commands/fins.py` | 生产：import 增加 `UploadScriptPublishError`；except 链增加映射分支 |
| `tests/cli/test_upload_filings_from_command.py` | 测试：新增一个 CLI 投影变体用例（原失败用例不改断言，自动转绿） |
| `docs/plans/upload-publish-error-projection-fix.md` | 本 plan artifact |

无 schema / state-machine / public interface 变更。公开行为变化仅为恢复 README 已承诺的 stderr 契约。

## 5. Implementation Decisions

- **D1 映射分支**：在 `run_fins_direct_command` except 链中、`FinsDirectStreamProtocolError` 分支之后、`KeyboardInterrupt` 之前插入：
  ```python
  except UploadScriptPublishError as exc:
      render_cli_error(f"dayu-cli {args.command_name}: {exc}")
      return EXIT_FAILURE
  ```
  specific typed exception 先于 generic `except Exception`；`UploadScriptPublishError` 是 `RuntimeError` 子类，位置保证优先匹配。
- **D2 不加 `_LOGGER.exception`**：判定规则是——消息自足且已完整投影到 stderr 的用户输入类 contract 错误不记 traceback（既有先例：`UploadBatchPlanEmptyError`、`FinsDirectStreamProtocolError`）；stderr 投影遮蔽了内部细节或属于运营型失败的才记（既有先例：`FinsUploadPrevalidationError`（fins.py:203-206，同为 RuntimeError 派生、同为 EXIT_FAILURE，但其 `exc.failure.message` 可能遮蔽内部 cause，故 `_LOGGER.exception`）与 generic `except Exception` 分支）。`UploadScriptPublishError` 属前者：确定性 contract 违例，消息仅含用户输入派生路径（`--base`、`--output`），无私有 storage locator / secret / 内部异常，直接投影安全且自足；publisher 内部 I/O 失败（`OSError` 透传）仍走 generic 分支保留 operator traceback。plan review 两路均指出初版论证选择性引用，此处已补全反例与判定规则；实现决策不变。
- **D3 import**：复用现有 `from dayu.cli.upload_script import (...)`（fins.py:43-47），加入 `UploadScriptPublishError`，无新模块依赖。
- **D4 测试**：
  - 新增 `test_upload_filings_from_publish_contract_errors_project_specific_message`，经 `cli_main.main` 逐一覆盖同一 typed contract 的三个变体，每个变体断言 `EXIT_FAILURE` + stderr 含对应消息片段 + target 文件未创建 + workspace 内无 `.<name>.*.tmp` 残留：
    1. internal symlink（workspace 内 `linked -> real`，`--output <linked>/upload.sh` → `internal symlink`；沿用同文件既有 symlink 测试惯例，无平台 guard）；
    2. 父目录不存在（`--output <workspace>/missing/upload.sh` → `output parent is not an existing directory`）；
    3. 目标类型非法（workspace 内预建与默认文件名同名的目录，`--output` 缺省 → `output target is not a regular file`）。
    目的：证明映射分支按 exception type 对整个 `UploadScriptPublishError` 家族生效、不特判 `escapes workspace root` 字符串，并给验收标准 2（无发布副作用）提供可执行证据。
  - 既有 `test_upload_filings_from_usage_empty_and_write_failures` 仅在 escape 场景末尾补一行 `assert not (tmp_path / "outside.sh").exists()`（发布副作用断言增强）；既有断言语义（exit code + stderr 消息）不变，修复使其自然转绿。
  - 新增 `test_upload_filings_from_unknown_failure_uses_generic_message`：monkeypatch `fins_command.publish_upload_script` 抛 `RuntimeError(<内部消息>)`，断言 `EXIT_FAILURE` + stderr 含 `_FINS_DIRECT_UNKNOWN_FAILURE_MESSAGE` 文案 + stderr 不含该内部消息。给验收标准 5（generic 不泄漏内部异常）在 `upload_filings_from` 路径上提供直接证据（现有覆盖在 download 路径，共享同一 except 链）。
- **D5 异常契约 docstring**：`_run_upload_filings_from` 的 docstring `:raises` 列表补 `UploadScriptPublishError`（脚本发布违反 containment/symlink/target-type contract 时抛出），满足 CLAUDE.md 完整异常 docstring 硬约束，使 adapter 异常边界在类型层自描述。

## 6. Implementation Slice

**Slice S1（唯一 slice）**：CLI adapter typed error projection + 投影变体与 generic 边界测试。

- objective：`UploadScriptPublishError` 经 CLI 投影为具体消息 + `EXIT_FAILURE`；generic 未知异常行为锁定不变。
- allowed files：`dayu/cli/commands/fins.py`、`tests/cli/test_upload_filings_from_command.py`。
- exact allowed changes：D1–D5；禁止触碰其它文件、其它 except 分支、其它测试。
- error handling / invariants：`KeyboardInterrupt -> 130`、usage error 类分支、generic unknown 分支行为不变；except 顺序保持 typed-before-generic。
- non-goals：见 §2。
- completion signal：§8 全部 validation 通过。

**为什么单 slice**：生产改动是一个 except 分支 + 一个 import 符号 + 一行 docstring，测试改动是同一边界的两个用例加一行断言；按行为增量无法也无意义再拆，多 slice 的 gate 成本远超实现风险。

## 7. Docs Decision

不修改任何 README。依据：

- 根 README（README.md:452、:591）已说明 output 必须位于 `--base` 工作区内、内部目录和既有目标不能是 symlink 且应给出可操作错误；本修复是**恢复**既有公开契约而非新增行为，README 未引用具体消息文本，投影具体化不构成文档漂移。
- `tests/README.md` 触发项已裁决：新增用例落在既有文件与既有测试层级，tests/README 记录的层级划分、运行命令与维护约定均不变化，无需更新。
- 分层关系、`UI/Service/Host/Engine` 边界未变化，`dayu/README.md` 无触发。

若 code review / deepreview 发现 README 表述与新行为有实质出入，再按触发规则重估。

## 8. Validation

```bash
cd /Users/leo/workspace/dayu-agent-r
source .venv/bin/activate
pytest -q tests/cli/test_upload_filings_from_command.py
pytest -q \
  tests/cli/test_fins_commands.py \
  tests/cli/test_upload_filings_from_command.py \
  tests/fins/test_fins_service_runtime.py \
  tests/fins/test_filing_upload_publication.py \
  tests/fins/test_sec_pipeline_download_stream.py \
  tests/fins/test_cn_download_runtime.py
pyright
```

预期：`test_upload_filings_from_command.py` 全绿（含新增用例）；回归集合无新增失败（基线 `1 failed, 263 passed, 2 skipped` → `264 passed, 2 skipped` 加上新增用例）；pyright 无新增或扩散错误。

## 9. Risks / Open Questions

- symlink 用例在受限 Windows 环境可能无法创建 symlink：与同文件既有 publisher symlink 测试同风险，遵循仓库既有惯例，不新增平台 guard（assigned to later work unit，如 CI 实际失败再处理）。
- `_run_upload_filings_from` 中 `render_upload_script` 的 `ValueError`（如空 commands）与 publisher `OSError` 透传仍走 generic 分支：这是既有行为；且 CLI 路径上 `generate_upload_batch_plan` 会先抛 `UploadBatchPlanEmptyError`，`ValueError` 实际不可达。非本 work unit 目标（assigned to later work unit，如有真实需求）。
- `--base` 指向 symlink 目录时，`_resolve_workspace_root`（fins.py:1101）`resolve(strict=False)` 先解引用，使 publisher 的 `workspace root must not be a symlink`（upload_script.py:292-295）经 CLI 不可达，而 README.md:452 有相关表述：既有行为，超出本 work unit non-goals（deferred-with-owner，由用户裁决是否另立 work unit）。
- `str(exc)` 无长度上限投影到 stderr：与既有 `CliFinsUsageError(_MISSING_UPLOAD_FILE_TEMPLATE)`（fins.py:1138）同一惯例，本修复未引入新问题；是否统一 bound 由 owner 日后裁决（deferred-with-owner）。
- 无 blocking open question。

## 10. 为什么不过度设计 / 无 goal drift

每个 decision 均可映射到已确认 goal 或 success signal：D1 是根因的直接修复（goal）；D2 满足"保留 operator log 诊断能力"且与既有分支模式一致（success signal 5）；D3 是实现 D1 的最小手段；D4 对应验收标准 4（success signal 3）且防止未来有人把映射退化成字符串特判；D5 遵守"测试断言 owner 级 contract"。不为其它 typed exception 加分支、不重构 except 链、不改 exit code，均显式排除在 non-goals。

## 11. Completion Report Format

最终汇报包含：根因、语义 owner、修改文件、测试命令与结果、pyright 结果、README 是否修改及原因、各 gate finding 状态、剩余风险与 owner。
