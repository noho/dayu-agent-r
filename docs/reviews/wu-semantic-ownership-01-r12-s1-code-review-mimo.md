# WU-SEMANTIC-OWNERSHIP-01 / R12 S1 Code Review — AgentMiMo

## 1. Gate identity

- Umbrella work unit：`WU-SEMANTIC-OWNERSHIP-01`。
- Internal remediation sub-WU：R12，`dayu-cli init` workflow。
- Slice：S1 — typed catalog、manifest projection 与 OS environment owner。
- Review type：第一路完整 code review（AgentMiMo）。
- Accepted-plan HEAD：`8f7a1946fa46975c3b9e1aefdc2eb3c765b001f8`。
- Controller validation artifact：
  `docs/reviews/wu-semantic-ownership-01-r12-s1-controller-validation.md`，
  166 lines / SHA-256
  `826b11a6caa288c19562b1663b3000448dbdd3ff519ab40971b27f199f9bec19`。
- AgentCodex completion artifact：
  `docs/reviews/wu-semantic-ownership-01-r12-s1-implementation-codex.md`，
  248 lines / SHA-256
  `278ced438b77b8296bf3fc4a669dbc991e24703bbf168e89c20df32bceac2fed`。

本 artifact 只报告 review findings。不接受 S1、不授权 fix、不授权 S2/S3、不
stage/commit。

## 2. Scope、完整阅读与独立验证

Reviewer 完整阅读了以下文件：

| 文件 | 行数 |
|---|---:|
| `AGENTS.md` | 128 |
| `docs/host/wu-semantic-ownership-01-r12-init-workflow-plan.md` | 608 |
| `docs/reviews/wu-semantic-ownership-01-r12-s1-controller-validation.md` | 166 |
| `docs/reviews/wu-semantic-ownership-01-r12-s1-implementation-codex.md` | 248 |
| `dayu/cli/init_catalog.py` | 854 |
| `dayu/cli/init_environment.py` | 570 |
| `tests/cli/test_init_catalog.py` | 610 |
| `tests/cli/test_init_environment.py` | 567 |

独立验证结果：

```bash
source .venv/bin/activate
pytest tests/cli/test_init_catalog.py tests/cli/test_init_environment.py -q
# exit 0: 56 passed in 0.20s

pytest tests/cli/test_init_catalog.py \
  --cov=dayu.cli.init_catalog --cov-report=term-missing --cov-fail-under=80 -q
# exit 0: 276 statements / 27 miss / 90%

pytest tests/cli/test_init_environment.py \
  --cov=dayu.cli.init_environment --cov-report=term-missing --cov-fail-under=80 -q
# exit 0: 226 statements / 13 miss / 94%

python -m pyright dayu/ tests/ utils/
# exit 0: 0 errors, 0 warnings, 0 informations

python -m ruff check dayu/cli/init_catalog.py dayu/cli/init_environment.py \
  tests/cli/test_init_catalog.py tests/cli/test_init_environment.py
# exit 0: All checks passed!

git diff --check
# exit 0: 无输出
git diff --cached --name-only
# 空
```

## 3. Findings

### R12-S1-CR-01-未修复-高-_parse_managed_block 的 content.count 在 quoted secret 含 marker 子串时误判

- **入口/函数**：`_parse_managed_block()` / `persist_environment()` POSIX 路径
- **文件(行号)**：`dayu/cli/init_environment.py:457`
- **输入场景**：用户选择持久化的 secret value 经 `shlex.quote` 后包含 begin 或 end
  marker 完整子串，例如 `value = "prefix # >>> dayu-cli init >>> suffix"`
- **实际分支**：`_render_profile_content` 正确构造含 export 行的完整 profile
  → `_write_profile_atomically` 成功将 profile 写入磁盘（`os.replace` 完成）
  → `_verify_written_profile` 调用 `_parse_managed_block` → 第 457 行
  `content.count(_DAYU_BLOCK_BEGIN)` 对**全文**计数，匹配到 export 行中
  `shlex.quote(value)` 内的 marker 子串 →
  `count != len(begin_indexes)` → 抛出 `EnvironmentPersistenceError("POSIX profile
  contains an embedded Dayu init marker")`
- **预期行为**：marker 检测只应关注**结构层面**——marker 是否作为独立行存在、
  是否配对、是否完整。quoted secret value 中恰好包含 marker 文本是合法输入，
  不应触发 `content.count()` 的嵌入误判（plan §5.1 的 value rejection 集合只
  包含 empty / NUL / CR / LF；§5.2 的 marker 结构 owner 关注的是缺失、配对、
  重叠、多块）
- **实际行为**：profile 已被原子替换到磁盘，但 `_verify_written_profile` 抛出
  异常。结果是：
  1. 合法 secret 被拒绝；
  2. profile 已经发布到磁盘（不是"零 mutation"）；
  3. `os.environ` 未注入、workspace 不能 publish；
  4. 用户得到一个不准确的错误信息
- **直接证据**：
  - `init_environment.py:457`：
    `if content.count(_DAYU_BLOCK_BEGIN) != len(begin_indexes) or
    content.count(_DAYU_BLOCK_END) != len(end_indexes):`
  - 独立复现：以真实 `EnvironmentPersistenceEntry`、
    `plan_environment_persistence()` 和 `persist_environment()` 构造
    `value = "prefix # >>> dayu-cli init >>> suffix"` →
    `EnvironmentPersistenceError("POSIX profile contains an embedded Dayu init
    marker")`，`profile_path.exists() == True`，`secret in profile_content == True`
  - 测试覆盖：当前测试集无 quoted-value 含 marker 子串的 case
- **影响**：合法用户输入被错误拒绝；profile 已写入但系统报告失败；状态不一致
- **建议改法和验证点**：
  1. 在 `_parse_managed_block` 中，把 `content.count()` 替换为：先用正则
     `_EXPORT_LINE_PATTERN.sub('', content)` 移除所有 export 行，再用
     `_MARKER_LINE_PATTERN.sub('', stripped)` 移除独立 marker 行，然后检查
     剩余文本是否仍包含 marker 子串
  2. 添加 `import re` 和两个模块级 compiled pattern：
     - `_EXPORT_LINE_PATTERN = re.compile(r'^' + re.escape(_EXPORT_PREFIX) +
       r'.*$', re.MULTILINE)`
     - `_MARKER_LINE_PATTERN = re.compile(r'^(' +
       re.escape(_DAYU_BLOCK_BEGIN) + r'|' + re.escape(_DAYU_BLOCK_END) +
       r')$', re.MULTILINE)`
  3. 替换后的检测逻辑：
     ```python
     stripped = _EXPORT_LINE_PATTERN.sub('', content)
     stripped = _MARKER_LINE_PATTERN.sub('', stripped)
     if _DAYU_BLOCK_BEGIN in stripped or _DAYU_BLOCK_END in stripped:
         raise EnvironmentPersistenceError(
             "POSIX profile contains an embedded Dayu init marker"
         )
     ```
  4. 必须新增测试：quoted secret 含 begin marker 子串、end marker 子串、两者
     同时存在、以及非 export 行嵌入 marker 的正确拒绝
  5. 验证：现有 56 测试仍全部通过；新测试覆盖 quoted-value 场景
- **修复风险（低/中/高）**：低
- **严重程度（低/中/高/严重）**：高
- **是否 current accepted candidate**：是，Controller mandatory evidence 的直接
  确认

### R12-S1-CR-02-未发现实质问题-InitModelSelection 的 dataclass value equality catalog membership

- **入口/函数**：`InitModelSelection.__post_init__()` 第 358 行
- **文件(行号)**：`dayu/cli/init_catalog.py:358`
- **输入场景**：构造 `InitModelSelection(choice=<catalog entry 的语义相同副本>)`
- **实际分支**：`self.choice not in INIT_MODEL_CHOICES` 使用 `__eq__` 比较；
  `frozen=True` dataclass 的 `__eq__` 基于所有字段值
- **预期行为**：value-object 语义——字段值完全相同的副本应被接受；字段值不同的
  forged choice 应被拒绝
- **实际行为**：语义相同副本被接受（`True`），forged choice 被拒绝
  （`InitCatalogError`）。符合 value-object contract
- **直接证据**：独立复现确认 `original == copy: True`、
  `copy in INIT_MODEL_CHOICES: True`、`forged in INIT_MODEL_CHOICES: False`
- **影响**：无。行为正确。不需要引入 registry/framework/identity shim
- **建议改法和验证点**：无需修改。现有测试 `test_selection_rejects_static_dynamic_and_dynamic_kind_mismatch`
  已覆盖 forged choice 拒绝。可选补充：显式测试语义相同副本被接受
- **修复风险（低/中/高）**：不适用
- **严重程度（低/中/高/严重）**：无 finding
- **是否 current accepted candidate**：否，不是 finding

## 4. Review completeness checklist

### 4.1 Plan §4 / catalog / model / manifest

- [x] 15 项 catalog 顺序与精确映射：`test_choice_catalog_order_and_exact_mapping`
- [x] 前 13 pair 消费真实 `ConfigLoader` resolved `ModelsConfig`：
  `test_current_package_catalog_uses_resolved_models_and_ollama_template`
- [x] raw thinking child 只写 extends 成功：
  `test_raw_thinking_child_with_only_extends_uses_current_resolver`
- [x] 缺失/provider/ref mismatch fail closed：
  `test_static_pair_missing_or_resolved_mismatch_fails_closed`
- [x] Ollama template provider/secret ref：
  `test_ollama_template_provider_and_secret_ref_fail_closed`
- [x] package 缺 custom-openai 不是错误：
  `test_static_validation_does_not_require_package_custom_record`
- [x] manifest set 精确 16：
  `test_package_manifest_set_must_equal_exact_known_sixteen`
- [x] Ollama 只换三字段：
  `test_ollama_record_copies_template_and_replaces_only_explicit_fields`
- [x] custom 完整 current-schema + 八 hints：
  `test_custom_record_is_complete_current_schema_with_exact_eight_hints`
- [x] URL/model/context boundary rejection：
  `test_dynamic_endpoint_boundary_*`、`test_dynamic_model_name_boundary_*`、
  `test_dynamic_context_window_rejects_*`
- [x] static/dynamic kind mismatch：
  `test_selection_rejects_static_dynamic_and_dynamic_kind_mismatch`
- [x] 静态不重写 models.json：
  `test_static_selection_does_not_rewrite_models_file`
- [x] 16 projection 只改 default_model_id + current parser 验证 + 13/3 catalog
  boundary：
  `test_projection_changes_only_default_model_id_and_current_parser_reads_all_sixteen`
- [x] projection 失败不部分改写：
  `test_projection_validates_all_known_files_before_any_write`
- [x] `_init_model_role`、`default_name`、`extends` 不存在于 custom record

### 4.2 Plan §5 / environment persistence

- [x] entry value `repr=False`：确认 `field(repr=False)`
- [x] name allowlist：`_validate_environment_name` 只接受 `ALLOWED_ENVIRONMENT_NAMES`
- [x] value rejection（empty / NUL / CR / LF）：`EnvironmentPersistenceEntry.__post_init__`
- [x] POSIX 单 profile（.zshrc / .bashrc）：
  `test_plan_selects_exactly_one_supported_posix_profile`
- [x] 不支持 platform/shell fail closed：
  `test_plan_rejects_unsupported_platform_or_shell`
- [x] 非 profile target 拒绝：
  `test_direct_posix_plan_rejects_non_profile_target`
- [x] 未确认 plan 零 mutation：
  `test_unconfirmed_posix_plan_does_not_create_profile_or_inject_environment`
- [x] 新 profile 0600、shlex.quote、原子写入、injection：
  `test_absent_profile_is_private_atomic_quoted_and_injected_after_success`
- [x] 已有 marker block 替换、保留 mode：
  `test_existing_marker_block_is_replaced_once_and_mode_is_preserved`
- [x] malformed marker 0/1/多块/嵌入/非法 export：
  `test_malformed_marker_structures_fail_closed_without_injection`
- [x] symlink / dangling symlink：
  `test_profile_symlink_and_dangling_symlink_are_rejected`
- [x] 非普通文件：
  `test_profile_directory_is_rejected_as_non_regular_file`
- [x] replace 故障保留旧 profile：
  `test_atomic_replace_failure_preserves_profile_and_does_not_inject`
- [x] 写后校验失败不注入：
  `test_post_write_structure_verification_precedes_environment_injection`
- [x] Windows exact argv/flags：
  `test_windows_uses_argument_tuple_binary_capture_and_injects_only_after_all_success`
- [x] Windows partial / first failure、names-only：
  `test_windows_partial_failure_reports_names_only_and_injects_nothing`、
  `test_windows_first_failure_has_failure_status_and_no_injection`
- [x] Windows 未确认零 setx：
  `test_unconfirmed_windows_plan_never_calls_setx`
- [x] secret 不泄漏到 repr/error：
  `test_entry_and_plan_validation_never_expose_secret_values`
- [x] `has_non_empty_environment_value`：
  `test_environment_presence_check_uses_non_empty_value_and_fixed_names`
- [ ] **缺失**：quoted secret 含 marker 子串不被误判 → CR-01

### 4.3 Semantic owner / AGENTS.md compliance

- [x] `init_catalog.py` 唯一拥有 catalog/model/manifest 投影
- [x] `init_environment.py` 唯一拥有 secret persistence
- [x] `ConfigLoader` / `ModelsConfig` 继续唯一拥有 schema 解析
- [x] `prepare_scene` 继续拥有 manifest parser
- [x] 无 `Any`、`object`、无类型签名
- [x] 无 `hasattr` / `getattr`
- [x] 无 lazy import（除 `from __future__ import annotations`）
- [x] 无嵌套类/函数
- [x] 无兼容性 shim / fallback / re-export
- [x] 无 `_init_model_role` / `default_name` 旧字段
- [x] 无网络调用（仅 `urllib.parse.urlsplit` 本地语法校验）
- [x] 无 `shell=True` / `text=True` / `print`
- [x] 所有函数有完整中文 docstring
- [x] 模块有中文概览 docstring

### 4.4 Adversarial failure pass

- [x] secret 不泄漏到异常、repr、stdout/stderr、captured output
- [x] POSIX 原子写入 + fsync + mode 保留
- [x] symlink / dangling symlink / 非普通文件拒绝
- [x] malformed marker fail closed
- [x] Windows partial failure 不注入
- [x] whole-batch success 才注入 `os.environ`
- [x] 写后结构校验先于环境注入
- [x] 13/3 validation 集合正交
- [x] user manifest 不被枚举或改写
- [ ] **CR-01**：marker substring 在 quoted value 中的 false rejection

### 4.5 Coverage 与 typing

| 文件 | Statements | Miss | Coverage | Gate |
|---|---:|---:|---:|---|
| `init_catalog.py` | 276 | 27 | 90.22% | PASS (≥80%) |
| `init_environment.py` | 226 | 13 | 94.25% | PASS (≥80%) |

pyright：`0 errors, 0 warnings, 0 informations`。changed-path Ruff：`All checks
passed!`。

## 5. Open Questions

- 无。

## 6. Residual Risk

- CR-01 的修复需要新增 `import re`（标准库），不影响现有依赖图。
- Windows `setx` 跨变量不可回滚是 accepted plan residual，不是 S1 finding。
- `init_catalog.py` 的 27 条未覆盖语句主要是防御性 validation 分支（如
  `_validate_choice_tuple_shape` 中的 tuple 形状检查、`_validate_dynamic_selection`
  中的 reload 后 mismatch 检查），属于 schema drift guard，在当前稳定 package
  config 下难以触发，coverage 仍远超 80% 门槛。
- `init_environment.py` 的 13 条未覆盖语句主要是 OSError / UnicodeError 的
  except 分支（如 `lstat` 失败、UTF-8 解码失败），属于 OS 级边界，coverage 远超
  80% 门槛。

## 7. Review Conclusion

发现 **1 个 material finding**（CR-01，severity HIGH）：`_parse_managed_block`
的 `content.count()` 检测在合法 quoted secret 含 marker 子串时误判，导致 profile
已写入磁盘但操作被报告为失败。Controller mandatory evidence 已由 reviewer 独立
复现并确认。

InitModelSelection 的 dataclass value equality 行为正确，不是 finding。

两个 production 文件 coverage 分别为 90% 和 94%，满足 S1 gate。pyright 零诊断、
changed-path Ruff 零诊断。无其它 material finding。

CR-01 需要 Controller adjudication。若 accepted，交 AgentCodex 修复后需双路
re-review；未 PASS 不进入 S2。
