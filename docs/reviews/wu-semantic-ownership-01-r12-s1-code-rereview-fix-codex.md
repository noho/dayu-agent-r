# WU-SEMANTIC-OWNERSHIP-01 / R12 S1 Final Re-Review Fix（AgentCodex）

## 1. Gate 身份与结论

- 本文是现有 umbrella WU `WU-SEMANTIC-OWNERSHIP-01` 的 R12 S1 final
  re-review fix artifact，不是新 WU。
- 修复 authority 是 Controller accepted LOW `R12-S1-RR-CF01`；本轮不进入
  S2/S3，不修改 plan/control/既有 artifacts/production/README，不 stage、commit、push
  或创建 PR。
- finding 动机成立但严重性确为 LOW：四文件 AST 直接证据为 production `0/0`、两份
  S1 新测试各 `16` 个函数缺少完整中文 docstring。产品运行时 contract 未错误，但测试
  函数违反 `AGENTS.md` 的参数、返回值与异常说明要求。
- 语义 owner 是每个测试函数自身。修复只扩展精确 32 个函数的首个 docstring；不在
  production、fixture、下游消费者或 lint 配置中补偿。
- `R12-S1-RR-CF01`：`FIXED / WAITING CONTROLLER VALIDATION`。

## 2. Authority 与 immutable 输入

| 输入 | SHA-256 | 终态 |
|---|---|---|
| `docs/host/wu-semantic-ownership-01-r12-init-workflow-plan.md` | `69ddfd888336cbb70d093743a96a56f18e694fa68436fb086be1c9b56dcb88c2` | 未修改 |
| `docs/reviews/wu-semantic-ownership-01-r12-s1-code-rereview-controller-adjudication.md` | `27b659fa56567b1d53a928c379860620cd28d6250571ce14677e177a5e4ade18` | 未修改 |
| `docs/reviews/wu-semantic-ownership-01-r12-s1-code-rereview-ds.md` | `3f51cfb6b29ee2e9bd6790b378e70c469e1f3f08133add9c17f8919f4d47d38b` | 未修改 |
| `docs/reviews/wu-semantic-ownership-01-r12-s1-code-rereview-mimo.md` | `3af83fc542c341f0de3ed4c06db957ea556e7a7a7f5fbcbe7b7767d0f1953a8a` | 未修改 |

上述文件与 `AGENTS.md`、两份当前测试文件均在修改前完整读取。Controller 裁决明确
拒绝借本 finding 新增 AST framework、repo-wide lint rule、compat/test shim 或 README。

## 3. 精确变更范围与 hashes

| 路径 | Before SHA-256 | After SHA-256 | 变更 |
|---|---|---|---|
| `dayu/cli/init_catalog.py` | `937315f3a6c83004788027c891c3b18e3cf2c848db2333430661998768ffe754` | `937315f3a6c83004788027c891c3b18e3cf2c848db2333430661998768ffe754` | 无 |
| `dayu/cli/init_environment.py` | `71be5ba886df7a9d33c6c15da1fba172540124684b02c65c67e17852d736b77f` | `71be5ba886df7a9d33c6c15da1fba172540124684b02c65c67e17852d736b77f` | 无 |
| `tests/cli/test_init_catalog.py` | `23f1c406e89c62159ea89e5fd4d795aecf9237ec2d42fae0ac06870e7b0473b4` | `086a143cf8247b6fe5371d6df5c2c5c6cc974410973d81d60bb7ccd8b6d05d9f` | 精确 16 个 test docstring |
| `tests/cli/test_init_environment.py` | `ae243050136d92e0c772caf3a51b3bdd999ff8efe3af096d73161f32473fd947` | `820c2bf262dd77628201977e7d4f823265e141ac0ae6a28791bd7d12cf5ad01a` | 精确 16 个 test docstring |
| 本 artifact | `ABSENT` | 文件关闭后在 Controller handoff 机械报告 | 新增 |

终态机械度量：

- `tests/cli/test_init_catalog.py`：710 lines / 27,503 bytes；
- `tests/cli/test_init_environment.py`：782 lines / 29,982 bytes。

apply patch 只把既有一行 docstring 扩展为完整中文 docstring；decorator、signature、body、
assertion、fixture、测试数量与 production 均未改。两个 environment 既有完整函数
`test_marker_substrings_in_export_values_succeed_for_create_and_replace` 与
`test_malformed_marker_structures_fail_closed_without_injection` 未触碰。

## 4. 精确 32 项 closure

每个下列函数均逐一列出全部显式参数，统一写明 `:returns: None`，并按实际路径说明
测试 assertion、fixture 文件系统 I/O 或本应成功的被测 owner 边界可能传播的异常。

### 4.1 Catalog：16/16

1. `test_choice_catalog_order_and_exact_mapping`
2. `test_current_package_catalog_uses_resolved_models_and_ollama_template`
3. `test_raw_thinking_child_with_only_extends_uses_current_resolver`
4. `test_static_pair_missing_or_resolved_mismatch_fails_closed`
5. `test_ollama_template_provider_and_secret_ref_fail_closed`
6. `test_static_validation_does_not_require_package_custom_record`
7. `test_package_manifest_set_must_equal_exact_known_sixteen`
8. `test_ollama_record_copies_template_and_replaces_only_explicit_fields`
9. `test_custom_record_is_complete_current_schema_with_exact_eight_hints`
10. `test_dynamic_endpoint_boundary_rejects_invalid_values`
11. `test_dynamic_model_name_boundary_rejects_blank_or_control_text`
12. `test_dynamic_context_window_rejects_non_positive_and_bool`
13. `test_selection_rejects_static_dynamic_and_dynamic_kind_mismatch`
14. `test_static_selection_does_not_rewrite_models_file`
15. `test_projection_changes_only_default_model_id_and_current_parser_reads_all_sixteen`
16. `test_projection_validates_all_known_files_before_any_write`

### 4.2 Environment：16/16

1. `test_plan_selects_exactly_one_supported_posix_profile`
2. `test_plan_rejects_unsupported_platform_or_shell`
3. `test_direct_posix_plan_rejects_non_profile_target`
4. `test_unconfirmed_posix_plan_does_not_create_profile_or_inject_environment`
5. `test_absent_profile_is_private_atomic_quoted_and_injected_after_success`
6. `test_existing_marker_block_is_replaced_once_and_mode_is_preserved`
7. `test_profile_symlink_and_dangling_symlink_are_rejected`
8. `test_profile_directory_is_rejected_as_non_regular_file`
9. `test_atomic_replace_failure_preserves_profile_and_does_not_inject`
10. `test_post_write_structure_verification_precedes_environment_injection`
11. `test_windows_uses_argument_tuple_binary_capture_and_injects_only_after_all_success`
12. `test_windows_partial_failure_reports_names_only_and_injects_nothing`
13. `test_windows_first_failure_has_failure_status_and_no_injection`
14. `test_unconfirmed_windows_plan_never_calls_setx`
15. `test_entry_and_plan_validation_never_expose_secret_values`
16. `test_environment_presence_check_uses_non_empty_value_and_fixed_names`

Closure 数量精确为 `16 + 16 = 32`。未新增、删除或重命名测试；最终 test definition
数量仍为 catalog `16`、environment `18`、合计 `34`。

## 5. AST contract scan

在 `.venv` Python 3.11 下对四文件使用同一 AST 规则：每个函数必须有中文 docstring，
每个非 `self/cls` 参数必须有精确 `:param <name>:`，并同时包含 `:returns:` 与
`:raises`。

修改前：

```text
dayu/cli/init_catalog.py: 0
dayu/cli/init_environment.py: 0
tests/cli/test_init_catalog.py: 16
tests/cli/test_init_environment.py: 16
```

修改后：

```text
dayu/cli/init_catalog.py: 0
dayu/cli/init_environment.py: 0
tests/cli/test_init_catalog.py: 0
tests/cli/test_init_environment.py: 0
```

终态同时报告函数/test 数量为 `28/0`、`20/0`、`28/16`、`26/18`。未把扫描器
写入仓库或测试框架。

## 6. Tests、coverage 与类型验证

所有命令均先执行 `source .venv/bin/activate`。

### 6.1 66 focused

```bash
pytest tests/cli/test_init_catalog.py tests/cli/test_init_environment.py -q
```

结果：exit `0`，`66 passed in 0.24s`。

### 6.2 单文件 coverage

```bash
pytest tests/cli/test_init_catalog.py \
  --cov=dayu.cli.init_catalog --cov-report=term-missing --cov-fail-under=80 -q
pytest tests/cli/test_init_environment.py \
  --cov=dayu.cli.init_environment --cov-report=term-missing --cov-fail-under=80 -q
```

- catalog：`276 statements / 27 miss / 90.22%`，31 passed；与 corrected
  re-review 基线精确一致，无退化；
- environment：`233 statements / 13 miss / 94.42%`，35 passed；与 corrected
  re-review 基线精确一致，无退化。

### 6.3 Full pyright

```bash
python -m pyright dayu/ tests/ utils/
```

结果：exit `0`，`0 errors, 0 warnings, 0 informations`。

## 7. Ruff immutable gates

### 7.1 Four-file scoped Ruff

```bash
python -m ruff check \
  dayu/cli/init_catalog.py dayu/cli/init_environment.py \
  tests/cli/test_init_catalog.py tests/cli/test_init_environment.py
```

工具版本 `ruff 0.15.11`；结果 exit `0`，`All checks passed!`。

### 7.2 Full Ruff exact baseline

```bash
python -m ruff check dayu/ tests/ utils/ --output-format=json \
  > workspace/tmp/r12-ruff-current.json
cmp workspace/tmp/r12-ruff-baseline.json workspace/tmp/r12-ruff-current.json
```

- Ruff raw exit：`1`，即锁定历史诊断存在的预期状态；
- baseline/current count：`144 / 144`；
- baseline/current SHA-256：均为
  `051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea`；
- `cmp` exit `0`，逐字节零差异。

## 8. Diff、staged、scope 与 source scans

### 8.1 Whitespace 与 staged

```bash
git diff --check
git diff --cached --check
git diff --cached --name-only
git diff --no-index --check /dev/null tests/cli/test_init_catalog.py
git diff --no-index --check /dev/null tests/cli/test_init_environment.py
```

- 两个 workspace/cached diff check 均 exit `0`；
- staged name list 为空，本轮未 stage/commit；
- 两个 untracked test no-index check raw exit 均为 `1`（存在新增 diff 的预期状态），
  stdout/stderr 为空，即无 whitespace 诊断。

### 8.2 Scope

- 四个 authority hashes 未变化；两个 production hashes 未变化；
- `git diff --name-only` 仍只显示进入本轮前既有的 Controller-owned
  `docs/host/issues-implementation-control.md`；本轮未修改它；
- `git status --short` 相对 entry 只新增本 artifact，既有 R12 S1 untracked scope 保持；
- decorators/signatures/bodies/assertions/fixtures/test definition counts 未改；
- 没有修改 plan、control、既有 artifacts、README 或 S2/S3 文件。

### 8.3 Source scans

以下四文件扫描均为 raw exit `1`、零命中：

```bash
rg -n '\bAny\b|:\s*object\b|->\s*object\b|hasattr\(|getattr\(' <four-files>
rg -n '\bcompat\b|\bfallback\b|\bshim\b|\brollback\b|hasattr\(|getattr\(|(^|[[:space:]])import re$|re\.compile|noqa|type:\s*ignore' \
  dayu/cli/init_environment.py tests/cli/test_init_environment.py
rg -n 'authorization|authorisation|tool[_ -]?auth|shell=True|text=True|print\(|logging|requests\.|httpx\.|socket|open_host|asyncio\.run' \
  dayu/cli/init_catalog.py dayu/cli/init_environment.py
rg -n 'content\.count\(_DAYU_BLOCK|ast\.parse|import ast|repo-wide|lint rule' <four-files>
```

结论：无 weak typing、compat/fallback/shim/rollback、regex/parser framework、AST
framework、repo-wide lint rule、ignore 绕过、unsafe shell/output、network/runtime assembly 或
tool authorization 新协议。

## 9. README decision

不修改 README。用户明确禁止本 fix 新增 README；本轮只完善既有测试函数的内部文档，
没有新增测试层级、运行方式、public CLI grammar、输出、用户工作流或排障 contract。
`tests/README.md` 的当前职责只要求新增测试层级时同步，因此不命中更新条件；accepted plan
仍把 R12 用户文档留在 S3。

## 10. Residual risks 与 uncovered areas

- `R12-S1-RR-CF01` 本身无未分类 residual：32/32 已关闭，AST 缺口为 0/0/0/0。
- Windows `setx` 跨变量不可回滚与真实 Windows runner 仍是 accepted plan 的既有 S3 /
  external-runner owner；本 docstring fix 未改变或扩大该风险。
- Windows captured output observation、POSIX 写后校验失败时 profile 可能已替换但不注入/
  不 publish，维持 Controller corrected re-review 的既有分类；不是本 finding 的 deferred fix。
- S2 workspace transaction 与 S3 prewarm/smoke/README 均未执行，属于明确未授权范围，不能
  用本 artifact 宣称完成。
- 无 blocking open question、无 design contradiction、无新增 finding。

## 11. Completion status 与下一入口

- Finding：`R12-S1-RR-CF01 FIXED`。
- Validation：本 artifact 写入前的代码侧门槛全部通过；文件关闭后再执行 artifact
  whitespace/hash/status 终检。
- Artifact path：
  `docs/reviews/wu-semantic-ownership-01-r12-s1-code-rereview-fix-codex.md`。
- 下一且唯一入口：`Controller validation`，随后由 Controller 安排两路完整 S1 final
  re-review。
- 明确停止：不进入 S2/S3，不 stage/commit，不更新 control，不修改既有 artifacts。
