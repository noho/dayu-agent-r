# UF-FIX01 F1 bounded follow-up fix implementation

## Gate

- Work unit：`UF-FIX01 validation-atomic-boundary`
- Gate：existing implementation review 的 bounded `fix`
- Baseline：`2f5ec1215cc6bd420f9cc6ae4acde3e1e5e457c6`
- Scope source：双路 code review 与 Controller 裁决共同指出的 3 个 finding
- Artifact path：`docs/gateflow/uf-fix01-validation-atomic-boundary-f1-bounded-followup-fix-implementation-20260813.md`

用户给定的 review target 为 `b3304eb4`。开始 fix preflight 时 Controller 已把两份 review artifact 与裁决 artifact 提交为 `2f5ec121`，工作树干净；本 fix 以该 Controller commit 为基线，未改写三份上游 artifact。

## Scope 与 changed files

- `dayu/fins/pipelines/docling_process_converter.py`：隔离退出 flush 保留已有主异常，仍通过既有 `finally` 恢复 FD2 并关闭复制 FD。
- `tests/fins/test_docling_process_converter.py`：让 logger 测试真实经 stdlib `lastResort` 写 inherited FD2；新增主异常与 exit flush 双失败的 owner contract test。
- `tests/cli/test_fins_commands.py`：改为测试在 `tmp_path` 内自建不可解析 PDF，保留真实 subprocess / `dayu-cli` / converter 路径和原有全部断言。
- `dayu/fins/README.md`：记录 stderr 隔离 owner 已实现的稳定退出语义。
- `tests/README.md`：记录 lastResort、双失败 cleanup 和自建 corrupt PDF 的当前测试契约。

## Decisions 与 finding 状态

1. `lastResort` 覆盖为 **已修复**：测试清空 logger/root handlers，设置 `propagate=True`，先在隔离外断言同一 logger 的 stdlib `lastResort` 确实写入 capfd 观察的 FD2，再断言隔离内无公开泄漏。
2. exit flush 遮蔽主异常为 **已修复**：已有隔离主体异常时抑制 flush 的次生 `Exception`；无主体异常时 flush 失败仍传播，不扩大原契约。owner test 断言 construction descriptor 分类不变、FD2 恢复且复制 FD 已关闭。
3. CLI calibration 绝对路径为 **已修复**：不变更 production workflow，只由 integration test 自建与原 calibration 同字节的 `b"not a PDF"` 输入；真实 CLI 仍返回 exit `1`、typed content reason、bounded stderr 且 fresh workspace 零 mutation。

## Validation

- `pytest -q tests/fins/test_docling_process_converter.py -k 'child_target_isolates_inherited_stderr_while_preserving_failure_descriptor or child_target_preserves_primary_exception_when_exit_flush_fails'`：`2 passed, 39 deselected`。
- `pytest -q tests/cli/test_fins_commands.py -k 'real_cli_corrupt_pdf_has_bounded_stderr_and_zero_fresh_workspace_mutation'`：`1 passed, 78 deselected`。
- `pytest -q tests/fins/test_docling_process_converter.py tests/cli/test_fins_commands.py`：`120 passed`；仅有 3 条既有 edgar dependency deprecation warning。
- `coverage run -m pytest -q tests/fins/test_docling_process_converter.py` 后对 `dayu/fins/pipelines/docling_process_converter.py` 执行 coverage report：`41 passed`，单文件覆盖率 `95%`。
- `python -m pyright dayu/ tests/ utils/`：`0 errors, 0 warnings, 0 informations`。
- `git diff --check`：通过。
- 所有 Python 验证均在 `source .venv/bin/activate` 后运行。
- 按用户边界未运行 UF-PF01。

## Docs decision

- `dayu/fins/README.md`：触发且已按其 Agent 更新约束修正当前稳定机制。
- `tests/README.md`：触发且已同步当前存在的 owner/integration coverage。
- 根 `README.md` 与 `dayu/README.md`：无用户可见工作流、CLI 参数、输出通道或分层/装配变化，不触发修改。

## Scope exclusions

- 未修改 upload owner/workflow/storage 或 UF-FIX09 生命周期。
- 未修改 frozen evidence/registry。
- 未修改 `docs/reviews/code-review-20260813-134144.md`、`docs/reviews/code-review-20260813-135000.md` 或 `docs/gateflow/uf-fix01-validation-atomic-boundary-f1-review-adjudication-20260813.md`。
- 未触碰 Controller 忽略文件 `workspace/tmp/uf_pf01_runner.py`。

## Residual risks 与 uncovered areas

- macOS 本地已验证 FD2/`dup`/`dup2`/`close` 契约；Windows descriptor 差异未在本轮实跑，分类为 **assigned to existing cross-platform CI owner**。
- UF-PF01 focused-real evidence 明确不在本 fix 执行范围，分类为 **covered by the Controller's next approved gate**。
- 3 条 edgar dependency deprecation warning 与本次变更无关，分类为 **assigned to upstream dependency maintenance**。
- 无未分类 residual risk，无 blocking open question。

## Completion status

`PASS`。双路 review 共同指出的 3 个 bounded finding 均已修复并完成受影响测试与完整 pyright；可进入 Controller 指定的下一 gate。
