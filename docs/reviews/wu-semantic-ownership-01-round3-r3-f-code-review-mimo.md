# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-F Implementation Code Review — AgentMiMo

## 结论

**PASS — 无 material finding。**

R3-F 的 CLI / Config / Packaging / Public Documentation / Runtime Numeric Contracts 实现与测试完整、一致，符合 plan 与 controller adjudication 的 accepted finding 要求。所有 R3-F 范围内的修改都在正确的 owner boundary 上，没有越界进入 R3-A～R3-E，没有引入兼容 shim 或下游 fallback。

## 审查范围验证

按 plan 要求逐项确认修改边界：

| Slice | 允许修改文件 | 实际修改 | 越界 |
|---|---|---|---|
| S1 Init | `init.py`, `test_init_command.py` | ✓ | 无 |
| S2 CLI/Scene/Batch/Packaging/Docs | CLI commands, arg_parsing, session_execution, agent_entrypoint, main, prompt assets, constraints, pyproject, READMEs, CLI tests | ✓ | 无 |
| S3 Config/Runtime Numeric/Gate | runtime numeric/config_loader/cancellation/filelock/lane/interruptible_process/assembly/scene_prepare, service consumers, runtime tests, contracts/audit tests | ✓ | 无 |

R3-A Host lifecycle、R3-B Engine provider、R3-C Fins storage、R3-D financial/read、R3-E Web/Documents 的 owner 文件均未修改。

## Finding 审查

### 1. Init symlink/staging/backup/rollback (DR-005)

**审查项：** fail closed、跟随 symlink、跨 workspace 写入、半安装、并发、异常路径。

**结论：PASS。**

- `_validate_workspace_path` 对 config tree 做 lexical/resolved 双重 containment 检查，并 walk 每个祖先 component 检测 symlink。
- `_validate_config_write_destination` 在 `_copy_current_config_assets` 入口和 `_install_staged_config_tree` 入口各调用一次，构成 TOCTOU 防御纵深。
- staging tree 使用 `tempfile.mkdtemp` 在 workspace root 内创建，复制完成后再 `os.replace` 安装；`finally` 块调用 `_delete_path_without_following_symlink` 清理。
- 已有 config 先移入 backup，安装失败时回滚；backup 清理不跟随 symlink。
- reset whitelist 在批量删除前和每次删除前都执行 `_validate_workspace_path`。
- `os.walk(followlinks=False)` 正确地将 symlink-to-directory 归入 `filenames`（非 `directory_names`），`is_symlink()` 可检测。
- `shutil.rmtree` 默认使用 `entry.is_dir(follow_symlinks=False)`，不跟随 tree 内部 symlink。
- 并发 init TOCTOU 已在 plan 中声明为 out of scope（无跨进程锁），符合预期。

### 2. Interactive ticker / session resume scene context (DR-026)

**审查项：** ticker 通过 shared scene context owner 进入 LLM-facing system prompt；禁止 metadata 代替 prompt。

**结论：PASS。**

- `interactive.py` 和 `session.py` 均调用 `build_entrypoint_context_slot_values(EntrypointContextSlotRequest(ticker=..., fmp_api_key=...))`，与 `prompt` 命令使用同一 Service owner。
- `interactive.json` manifest 声明 `fins_default_subject` 为 required context slot。
- `interactive.md` scene 模板渲染 `{{fins_default_subject}}`，ticker 事实进入 LLM-facing system prompt。
- 测试 `test_interactive_label_reuses_host_slot_and_fills_context_slots` 断言 `fins_default_subject` 在 context slot values 中且值为 `"# 当前分析对象\n你正在分析的是 AAPL。"`。
- `test_scene_assets_migration` 更新 `_NO_DEFAULT_SUBJECT_SCENES` 移除 `interactive`。
- `FMP_API_KEY_ENV` 在 `session.py` 和 `interactive.py` 中正确导入。

### 3. Upload filings_from JSON argv contract (DR-027)

**审查项：** JSON argv contract 完整、类型安全、无 shell quoting residual、README/tests 同步。

**结论：PASS。**

- `_render_upload_batch_plan` 输出 `{schema_version: 1, commands: [[argv...]]}` JSON。
- `_upload_batch_command_argv` 返回 `tuple[str, ...]`，`_render_upload_batch_plan` 转为 `list` 再 JSON 序列化。
- `shlex.join` 已删除；含 `&`、`%`、`!`、空格的路径保持单个 argv item。
- `json.dumps(ensure_ascii=False, indent=2)` 正确处理非 ASCII 路径。
- 测试 `_load_plan_commands` 校验 schema_version、commands 结构、每个 argument 为 str。
- 测试用 `"AAPL 10-K 2024 & echo %PATH%!.pdf"` 验证特殊字符保留在单个 argv item。
- README 包含 `"schema_version": 1`、`"commands"`、`"不生成 shell"` 语句。

### 4. Parser 删除旧 flags (DR-028)

**审查项：** 旧 flags 删除后无 downstream compatibility shim；README 只描述当前真实行为。

**结论：PASS。**

- `arg_parsing.py` 删除 `--web-provider`、`--enable-tool-trace`、`--tool-trace-dir`、`--max-duplicate-tool-calls`、`--duplicate-tool-hint-prompt`、`--doc-limits-json`、`--fins-limits-json`、`--infer`、`--ci`。
- `ParsedCliArgs` namespace 和 `_new_default_namespace` 同步删除对应字段。
- `agent_entrypoint.py` 删除 `unsupported_execution_option_names` 函数。
- `session_execution.py` 删除 `_raise_for_unsupported_execution_options` 函数及调用。
- `fins.py` 删除 `_raise_for_unsupported_flags` 函数。
- 所有测试从断言 "unsupported option" 改为断言 "unrecognized arguments"（argparse 级拒绝）。
- README 不包含 `write`、`--infer`、`--ci`、`--web-provider`、`--new-session`、`--doc-limits-json`、`--fins-limits-json`。
- `test_root_readme_matches_current_cli_public_contract` 断言 README 与 parser 同源。

### 5. Finite-number owner (DR-030)

**审查项：** 层中立、runtime 不反向依赖上层、NaN/Infinity 在 JSON/config/runtime 边界被拒绝、无下游 fallback。

**结论：PASS。**

- `dayu/runtime/numeric.py` 是层中立模块，只依赖 `math` 标准库，不 import 任何业务层。
- `is_finite_number` 显式排除 `bool`，处理 `OverflowError`（超大整数转 float 溢出）。
- `config_loader.py` 的 `_read_required_json_object` 使用 `parse_float=_parse_finite_json_float` 和 `parse_constant=_reject_non_finite_json_constant`，在 JSON 解析边界拒绝 `NaN`、`±Infinity`、`1e400`。
- `_require_float_field` 增加 `is_finite_number` 检查。
- `cancellation.py` 新增 `_validate_timeout_seconds`，使用 `is_non_negative_finite_number`。
- `filelock.py` timeout 校验从 `timeout_seconds < 0` 改为 `not is_non_negative_finite_number(timeout_seconds)`。
- `lane.py` 的 `LaneConfig` 和 `SQLiteLaneCoordinatorConfig` 全部数值字段使用 finite predicate。
- `interruptible_process.py` 的 `grace_seconds` 和新增 `wait` timeout 使用 finite predicate。
- `assembly.py`、`scene_prepare.py`、`entrypoint_runtime.py`、`host_assembly.py`、`scene_context.py` 统一复用 `numeric.py` 真源。
- 测试覆盖 `NaN`、`+Infinity`、`-Infinity`、`-0.1` 参数化矩阵。
- `test_config_json_boundary_rejects_non_finite_number_literals` 测试 `NaN`、`Infinity`、`-Infinity`、`1e400` 在 JSON 边界被拒绝。

### 6. Packaging constraints (DR-018)

**审查项：** constraints 和 pyproject 同源，不形成新的不可安装组合。

**结论：PASS。**

- `pyproject.toml` 新增 `transformers>=4.57.6,<5.0.0`。
- 五个 Python 3.11 constraints 文件统一为 `transformers==4.57.6`、`huggingface_hub==0.36.2`。
- `test_docling_transformers_runtime_contract_is_consistent_for_python_311` 断言 metadata constraint 与所有 lock 文件一致，且不含 `transformers==5.` 或 `huggingface_hub==1.`。

### 7. Tests 断言 owner-level contract (DR-037)

**审查项：** tests 断言 owner-level contract，不用旧 fixture 保护偶然行为。

**结论：PASS。**

- `test_package_exports.py` 的 `EXPECTED_EXPORTS` 新增 `AgentFallbackMode`、`AGENT_FALLBACK_MODES`，与生产包 `__all__` 同源。
- `test_audit_sink.py` 的 `_EVENT_TYPE_PREVIEW_DELTA` 从裸字符串 `"PREVIEW_DELTA"` 改为 `serialize_host_event_type(HostPreviewEventType.REASONING_DELTA)`，使用生产 owner 真源。
- `test_filelock.py` 的类型从 `FileLock` 改为 `BaseFileLock`，与生产代码同步。
- 所有新增 finite-number 测试参数化 `NaN`/`±Infinity`/负数矩阵，断言 owner 级错误消息。

### 8. R3-A～R3-E 边界

**审查项：** 是否越界修改 R3-A/R3-B/R3-C/R3-D/R3-E。

**结论：PASS。**

修改文件清单与 plan 允许范围完全一致。Host lifecycle、Engine provider、Fins storage/read、Web/Documents 的 owner 文件均未修改。`docs/host/issues-implementation-control.md` 的 diff 只是 status 更新（由 controller 持有），不是 R3-F 生产代码修改。

## 验证结果

```text
CLI tests:                          221 passed
Runtime/contracts/audit tests:      221 passed
Full pytest:                        3929 passed, 3 skipped, 5 deselected
Full pyright (dayu/ tests/ utils/): 0 errors, 0 warnings, 0 informations
git diff --check:                   passed
```

`5 deselected` 为项目配置排除的 stress tests（归属 R3-A）；`3 skipped` 为平台条件跳过。

## 结论

R3-F implementation 通过 code review。所有 8 个审查维度均 PASS，无 material finding。
