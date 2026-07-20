# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-F Implementation Code Review — AgentDS

## 审查结论

**PASS — 0 material findings.**

全部 8 个审查领域均已按 plan 与 Codex 实现报告逐条验证，每条均取得直接 file/line 证据。未发现实现缺口、安全边界被突破、语义 owner 漂移或越界修改 R3-A～R3-E 的问题。

---

## 1. init symlink / staging / backup / rollback fail-closed

**真源文件**：`dayu/cli/commands/init.py`

### 1.1 写入 containment guard（line 262-294, 349-373）

- `_validate_config_write_destination` 在复制前与 `_install_staged_config_tree` 安装前两次调用，形成 double validation。
- `_validate_workspace_path` 执行三层检查：
  1. **lexical containment**：`path.relative_to(workspace_root)`（line 361）
  2. **per-component symlink**：逐 path 组件检查 `is_symlink()`（line 364-368）
  3. **resolved containment**：`path.resolve(strict=False).relative_to(resolved_workspace)`（line 370-373）
- `os.walk(followlinks=False)` 遍历已有 config tree 拒绝任何子孙 symlink（line 281-294）。

**验证**：`test_init_copy_rejects_config_directory_symlink_without_writing_outside`（test_init_command.py:131）、`test_init_copy_rejects_nested_symlink_without_writing_outside`（test_init_command.py:160）均断言外部目录零写入。

### 1.2 私有 staging + atomic install（line 136-183, 310-346）

- staging 目录使用 `tempfile.mkdtemp(prefix=_STAGING_DIR_PREFIX, dir=workspace_root)` 确保在 workspace 内（line 163）。
- 已有 config 先经 `os.replace` 移动到 workspace 内私有 backup（line 338），再经 `os.replace` 把 staging tree 安装为目标 config（line 340）。
- `os.replace` 在同一文件系统上为原子操作，不跟随目标 symlink。
- 安装失败时：backup 经 `os.replace` 回滚（line 343），staging 由 `finally` 块清理（line 183）。
- backup 成功安装后由 `_delete_path_without_following_symlink` 安全删除（line 346, 376-392），该函数先做 `is_symlink()` 检查再选择 `unlink/rmtree`。

**验证**：`test_init_staged_install_failure_restores_existing_config`（test_init_command.py:192）精确模拟 staging install 失败并断言旧内容恢复、新内容不泄漏、backup 目录已清理。

### 1.3 reset 白名单 fail-fast（line 395-466）

- reset 白名单为硬编码 `(config_dir, host_dir, artifact_root, web_tools_storage_state_dir)`（line 418-431）。
- 删除前每个路径经 `_validate_workspace_path` 预检 symlink 与 containment（line 434-448）。
- 实际删除前二次 validation（line 461-465），用 `_delete_path_without_following_symlink` 执行（line 466）。
- `test_init_reset_symlink_escape_fails_fast_without_deleting`（line 296）、`test_init_reset_parent_symlink_containment_escape_fails_fast`（line 326）验证 symlink 逃逸时 fail-fast 且不动其他路径。

### 1.4 并发与异常路径

- `finally` 块确保 staging 总是被清理（line 182-183）。
- `except BaseException` 捕获 `KeyboardInterrupt` 在内的所有异常（line 341）。
- 并发 init 不在本轮承诺内（Codex report §残余风险1），属于合理的 scope boundary。

**结论**：fail-closed 设计完整，三明治 validation、staging+atomic install、backup/rollback 与 symlink-safe cleanup 均经 owner 级测试覆盖。**PASS**。

---

## 2. interactive --ticker / session resume --mode interactive --ticker 共享 scene context

**真源文件**：`dayu/cli/commands/interactive.py`、`dayu/cli/commands/session.py`、`dayu/service/scene_context.py`、`dayu/config/prompts/manifests/interactive.json`、`dayu/config/prompts/scenes/interactive.md`

### 2.1 interactive 命令（interactive.py:96-140, 204-225）

- `_run_interactive_command_async` 调用 `build_interactive_context_slot_values(ticker=ticker, fmp_api_key=...)` (line 118)
- `build_interactive_context_slot_values` 调用 `build_entrypoint_context_slot_values(EntrypointContextSlotRequest(ticker=ticker, ...))` (line 218-223)
- `build_entrypoint_context_slot_values` 生成 `fins_default_subject` 与 `current_time` 两个 slot（scene_context.py:99-116）
- `fins_default_subject()` 产生 LLM-facing Markdown：`"# 当前分析对象\n你正在分析的是 AAPL（Apple Inc.）。"` (line 61-76)

### 2.2 session resume --mode interactive（session.py:294-306）

- `_run_session_resume` 对 interactive mode 调用 `build_interactive_context_slot_values(ticker=interactive_ticker, fmp_api_key=...)` (line 301-303)
- 传入 `prepare_interactive_session_execution` → `_prepare_session_runtime` → `prepare_entrypoint_runtime` → ScenePrepare

### 2.3 LLM-facing 投影链路

- interactive manifest 声明 `fins_default_subject` 为 `required: true` 的 context slot（interactive.json:65-69）
- interactive scene 模板在 system prompt 中渲染 `{{fins_default_subject}}`（interactive.md:10）
- `fins_default_subject` 始终由 `build_entrypoint_context_slot_values` 这一 shared Service owner 生成；不存在 metadata-only 路径

**结论**：两条路径共享同一 scene context owner，ticker 进入 LLM-facing system prompt 而非仅留在 invocation metadata。**PASS**。

---

## 3. upload_filings_from JSON argv contract

**真源文件**：`dayu/cli/commands/fins.py`（line 253-307）、`tests/cli/test_upload_filings_from_command.py`

### 3.1 公共契约定义（fins.py:294-307）

```python
payload: dict[str, JsonValue] = {
    "schema_version": 1,
    "commands": [["dayu-cli", "upload_filing", "--ticker", "AAPL", ...]],
}
return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
```

- 每条 command 是 `list[str]`（raw argv items），不经 shell quoting
- `schema_version` 字段允许 consumer 做 forward-compat 判断

### 3.2 类型安全与 shell quoting

- `_upload_batch_command_argv`（line 310-334）构造 `tuple[str, ...]`，文件路径用 `str(path)` 转换
- 不再使用 `shlex.join()`——旧的 POSIX shell command renderer 已删除
- `shlex` 导入仅保留用于 `_quoted_diagnostic_text`（line 841）的日志诊断格式化，不影响公共输出

### 3.3 测试验证

- `test_upload_filings_from_writes_structured_argv_plan_to_stdout`（line 26-98）：文件名含 `& echo %PATH%!` 保持单 argv item
- `_load_plan_commands`（line 346-363）：校验 `schema_version==1`、`commands` 为 list of list of str
- 所有测试均通过 `_install_forbidden_direct_service` 确保 `upload_filings_from` 不启动 Fins direct service

### 3.4 README 同步

- `test_root_readme_matches_current_cli_public_contract`（test_arg_parsing.py:304）断言 README 包含 `"schema_version": 1`、`"commands"` 和 `不生成 shell`

**结论**：跨平台 JSON argv contract 完整类型安全，无 shell quoting residual，README/tests 同源。**PASS**。

---

## 4. parser 删除旧 flags

**真源文件**：`dayu/cli/arg_parsing.py`、`dayu/cli/agent_entrypoint.py`、`dayu/cli/session_execution.py`

### 4.1 已删除的 parser surface

- `--web-provider`、`--enable-tool-trace`、`--tool-trace-dir`、`--max-duplicate-tool-calls`、`--duplicate-tool-hint-prompt`、`--doc-limits-json`、`--fins-limits-json`
- `--infer`、`--ci`、`--new-session`
- `--web-provider` 字段从 `ParsedCliArgs` 中移除
- `_new_default_namespace` 不再初始化这些字段

### 4.2 已删除的 downstream 兼容代码

- `unsupported_execution_option_names()` 从 `agent_entrypoint.py` 删除（diff line 228-257），同时从 `__all__` 移除
- `session_execution.py` 中 21 行删除包括对该函数的调用
- `EXCLUDED_COMMAND_NAMES` 保留 `write` 等旧命令名但仅用于确保 unknown command → usage error

### 4.3 README 验证

- `test_root_readme_matches_current_cli_public_contract`（test_arg_parsing.py:304-328）断言 README 不含 `` `write` ``、`--infer`、`--ci`、`--web-provider`、`--new-session`、`--doc-limits-json`、`--fins-limits-json`
- 同时断言 README 包含当前真实行为描述

### 4.4 不存在 downstream compatibility shim

- `ParsedCliArgs` 不含已删除字段的类型标注
- 无 re-export 或 fallback 路径

**结论**：parser surface 清理完整，无 downstream compatibility shim，README 只描述当前真实可用行为。**PASS**。

---

## 5. finite-number owner 层中立

**真源文件**：`dayu/runtime/numeric.py`（新增）、`dayu/runtime/config_loader.py`、`dayu/runtime/cancellation.py`、`dayu/runtime/lane.py`、`dayu/runtime/filelock.py`、`dayu/runtime/interruptible_process.py`、`dayu/runtime/assembly.py`、`dayu/runtime/scene_prepare.py`、`dayu/service/host_assembly.py`、`dayu/service/entrypoint_runtime.py`、`dayu/service/scene_context.py`

### 5.1 层中立性（numeric.py:1-55）

- 依赖仅 `math`（stdlib），零上层 import
- 三个 predicate：`is_finite_number`（拒绝 bool、NaN、±Inf、溢出）、`is_positive_finite_number`、`is_non_negative_finite_number`
- 不抛异常，由各 owner boundary 翻译错误类型

### 5.2 ConfigLoader JSON boundary（config_loader.py:963-995）

- `_parse_finite_json_float`：JSON parser callback，`float(value)` 后经 `is_finite_number` 校验，拒绝溢出为无穷的值（line 973-984）
- `_reject_non_finite_json_constant`：拒绝 Python JSON 扩展的 NaN/Infinity 常量（line 987-995），返回类型为 `Never`
- `_require_float_field`：拒绝 bool 与非数值类型后用 `is_finite_number` 统一 guard（line 2517-2534）
- 新增 `_require_non_negative_finite_float_field`（line 2555-2570）

### 5.3 各 owner 消费者

| 模块 | 替换前 | 替换后 | 保留自有错误 |
|------|--------|--------|-------------|
| `cancellation.py` | `> 0 / < 0` | `is_positive_finite_number` / `is_non_negative_finite_number` | `ValueError` + 自有消息 |
| `lane.py` | `<= 0 / < 0` | `is_positive_finite_number` / `is_non_negative_finite_number` | `RuntimeLaneConfigError` + 自有消息 |
| `filelock.py` | `< 0` | `is_non_negative_finite_number` | `RuntimeFileLockError` + 自有消息 |
| `interruptible_process.py` | `math.isfinite` + `< 0` | `is_non_negative_finite_number` | `ValueError` / `TypeError` + 自有消息 |
| `assembly.py` | `math.isfinite` + `<= 0` | `is_positive_finite_number` | `RuntimeAssemblyFieldError` + 自有消息 |
| `scene_prepare.py` | `math.isfinite` + `<= 0` | `is_positive_finite_number` | `ScenePrepareError` + 自有消息 |
| `host_assembly.py` | `math.isfinite` + `<= 0` | `is_finite_number` / `is_positive_finite_number` | `ValueError` + 自有字段名 |
| `entrypoint_runtime.py` | `math.isfinite` + `<= 0` | `is_positive_finite_number` | `ValueError` + 自有消息 |
| `scene_context.py` | — | `is_positive_finite_number` | `ValueError` + 自有消息 |

- 新增 `_validate_timeout_seconds`（cancellation.py:294-318）和 `_validate_wait_timeout_seconds`（interruptible_process.py:777-790）填补之前缺失的 boundary 校验。

### 5.4 测试

- `tests/runtime/test_numeric.py`（63 行）：覆盖有限值接受、bool/NaN/inf/overflow 拒绝、正数/非负数符号一致性
- `test_is_finite_number_rejects_non_finite_or_non_json_number` 参数化覆盖 `True, False, float("nan"), float("inf"), float("-inf"), 10**1000`

**结论**：finite-number owner 层中立（stdlib only），NaN/Infinity 在 JSON/config/runtime 边界被各自 owner 拒绝，无下游 fallback。每位消费者保留自有错误类型。**PASS**。

---

## 6. packaging constraints 与 pyproject 同源

**真源文件**：`pyproject.toml`、`constraints/min-py311.txt`、`constraints/lock-*.txt`、`tests/cli/test_public_package_entrypoints.py`

### 6.1 pyproject.toml 约束（line 53）

```
"transformers>=4.57.6,<5.0.0",
```

### 6.2 五个 constraints 文件同步

| 文件 | transformers pin | huggingface_hub pin |
|------|-----------------|---------------------|
| `min-py311.txt` | `==4.57.6` | `==0.36.2` |
| `lock-linux-x64-py311.txt` | `==4.57.6` | `==0.36.2` |
| `lock-macos-arm64-py311.txt` | `==4.57.6` | `==0.36.2` |
| `lock-macos-x64-py311.txt` | `==4.57.6` | `==0.36.2` |
| `lock-windows-x64-py311.txt` | `==4.57.6` | `==0.36.2` |

### 6.3 自动化验证

`test_docling_transformers_runtime_contract_is_consistent_for_python_311`（test_public_package_entrypoints.py:155-172）：
- 断言 pyproject.toml dependencies 包含 `transformers>=4.57.6,<5.0.0`
- 遍历 5 个 constraints 文件，断言均包含 `transformers==4.57.6`、`huggingface_hub==0.36.2`
- 断言不含 `transformers==5.` 或 `huggingface_hub==1.` 漂移

**结论**：packaging metadata 与全部 Python 3.11 lock 同源，无 5.x 漂移，自动化测试持续保护。**PASS**。

---

## 7. tests 断言 owner-level contract

### 7.1 numeric owner

- `tests/runtime/test_numeric.py`：直接测试 `is_finite_number` / `is_positive_finite_number` / `is_non_negative_finite_number` 的边界行为

### 7.2 init write-destination owner

- `test_init_copy_rejects_config_directory_symlink_without_writing_outside`：断言 symlink config 被拒绝、外部目录零写入
- `test_init_copy_rejects_nested_symlink_without_writing_outside`：断言嵌套 symlink 被拒绝
- `test_init_staged_install_failure_restores_existing_config`：断言 rollback 恢复旧内容、新内容不泄漏
- `test_init_overwrite_preserves_unmanaged_config_file`：断言用户自管文件保留
- `test_init_reset_only_deletes_hardcoded_whitelist`：断言 reset 只删白名单、不越界
- `test_init_reset_symlink_escape_fails_fast_without_deleting`：断言 symlink escape fail-fast
- `test_init_reset_parent_symlink_containment_escape_fails_fast`：断言父目录 symlink containment

### 7.3 public contract owner

- `test_root_readme_matches_current_cli_public_contract`：断言 README 不含已删除/未实现行为
- `test_upload_filings_from_writes_structured_argv_plan_to_stdout`：断言 JSON argv schema 与内容
- `test_docling_transformers_runtime_contract_is_consistent_for_python_311`：断言跨文件约束一致性
- `test_package_exports.py`：更新 whitelist 纳入 `AgentFallbackMode` / `AGENT_FALLBACK_MODES`
- `test_audit_sink.py`：fixture 改用 `HostPreviewEventType.REASONING_DELTA` 与 `serialize_host_event_type()`

### 7.4 未用旧 fixture 保护偶然行为

- init 测试使用 `tmp_path`、新写文件而非依赖预置 workspace
- test_numeric.py 直接测试 predicate 而非通过上层间接验证
- test_upload_filings_from 直接校验 JSON contract 结构而非截取 stdout 文本匹配

**结论**：测试断言 owner 级行为，未用旧 fixture 固化偶然行为。**PASS**。

---

## 8. 越界修改 R3-A～R3-E 检查

### 8.1 变更文件清单（与 Codex report §改动文件 完全一致）

所有 48 个变更文件均属于以下范畴：
- **CLI**：`dayu/cli/` 下 8 个文件
- **Runtime**：`dayu/runtime/` 下 8 个文件
- **Service**：`dayu/service/` 下 3 个文件
- **Config**：`dayu/config/` 下 3 个文件（README + 2 个 prompt asset）
- **Packaging**：`pyproject.toml` + 5 个 constraints files
- **Documentation**：`README.md`、`docs/host/issues-implementation-control.md`（4 行控制追踪）
- **Tests**：`tests/` 下 19 个文件

### 8.2 未触及的模块

- `dayu/engine/`：零修改
- `dayu/host/`（生产代码）：零修改（`tests/host/test_audit_sink.py` 仅 fixture 更新）
- `dayu/fins/`（storage/read）：零修改
- `dayu/web/`：零修改
- `dayu/wechat/`：零修改

### 8.3 test_audit_sink.py 变更性质

- 仅 fixture 从旧 event type 迁移为 `HostPreviewEventType.REASONING_DELTA` 与 `serialize_host_event_type()`，属于测试资产对齐公共契约，不改变 Host 生产行为。

**结论**：未越界修改 R3-A（Host lifecycle）、R3-B（Engine provider）、R3-C（Fins storage）、R3-D（Web）、R3-E（Documents）。**PASS**。

---

## 审查核对表

| # | 审查领域 | 结果 | 直接证据 |
|---|---------|------|---------|
| 1 | init symlink/staging/backup/rollback fail-closed | PASS | `init.py:262-466` + 7 个 owner 级测试 |
| 2 | interactive --ticker shared scene context | PASS | `interactive.py:118` → `scene_context.py:99` → `interactive.md:10` |
| 3 | upload_filings_from JSON argv contract | PASS | `fins.py:294-307` + `test_upload_filings_from_command.py:26-98,346-363` |
| 4 | parser 删除旧 flags 无 downstream shim | PASS | `agent_entrypoint.py` diff, `arg_parsing.py` diff, `test_arg_parsing.py:304-328` |
| 5 | finite-number owner 层中立 | PASS | `numeric.py:1-55`, `config_loader.py:973-995`, 10 个 consumer 替换 |
| 6 | packaging constraints 与 pyproject 同源 | PASS | 5 constraints + `test_public_package_entrypoints.py:155-172` |
| 7 | tests 断言 owner-level contract | PASS | 各测试直接校验 owner boundary |
| 8 | 未越界 R3-A～R3-E | PASS | diff stat 无 engine/host/fins/web/wechat 生产代码 |

---

## 残余风险确认

以下风险来自 Codex 实现报告，AgentDS 确认其仍在合理 scope boundary 内：

1. **并发 init**：无进程间互斥锁，两进程同时 init 不在本轮承诺内。影响面有限（init 是低频操作），若产品要求并发再进入独立 WU。
2. **JSON argv breaking change**：旧 shell script consumer 需适配，不提供 compatibility renderer。这是明确的设计决策，README 已正确描述。
3. **runner-call stress**：归 R3-A，本轮未触碰。
4. **fresh-lock 环境验证**：现有开发 venv 不能替代全新 Python 3.11 minimum 环境验证。归 packaging/release pipeline。

---

## 验证方法

- 阅读全部 48 个变更文件的 diff
- 对照 Codex 实现报告逐条核实
- 追踪 ticker → scene context 的完整调用链
- 逐项检查 finite-number 替换前后的 diff
- 交叉验证 constraints 文件与 pyproject.toml
- 检查 R3-A～R3-E 模块是否出现在 diff stat 中
