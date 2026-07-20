# WU-SEMANTIC-OWNERSHIP-01 / R12 S1 Final Re-Review — AgentMiMo（第一路）

## 1. Gate 身份

- 现有 umbrella WU `WU-SEMANTIC-OWNERSHIP-01`，R12 S1 final cumulative tree。
- 本 artifact 是第一路（AgentMiMo）独立 final code re-review，不是新 WU。
- 不授权 S2/S3、fix、stage、commit、push 或 PR。
- HEAD：`8f7a1946fa46975c3b9e1aefdc2eb3c765b001f8`。
- Branch：`phaseflow/host-issues-control`。

## 2. Authority 完整 hashes

### 2.1 计划与原始验证

| 文件 | SHA-256 |
|---|---|
| Accepted plan | `69ddfd888336cbb70d093743a96a56f18e694fa68436fb086be1c9b56dcb88c2` |
| S1 Controller validation | `826b11a6caa288c19562b1663b3000448dbdd3ff519ab40971b27f199f9bec19` |
| S1 implementation artifact (AgentCodex) | `278ced438b77b8296bf3fc4a669dbc991e24703bbf168e89c20df32bceac2fed` |

### 2.2 第一轮双路 review

| 文件 | SHA-256 |
|---|---|
| AgentMiMo initial review | `4f27c186ac0ec9f439956f5eadf34458dd7f11455d5a8684f57e9d3dfcdc7492` |
| AgentDS initial review | `06094e2704e6f8a42385f77e7d0e0fa56474be40272bfe511948b81958900652` |

### 2.3 Controller 裁决与修复

| 文件 | SHA-256 |
|---|---|
| Controller adjudication | `b3a9aca59a9f03bd1cf143bc6f4e5f30e35560d09054d1240f72d5dd5f441c19` |
| AgentCodex fix artifact | `b9702a729a080b53d4585527f722b905777102bcf9f1288f2e0dbd49bd48fb44` |
| Controller fix validation | `fd4afc8c6bc5bc52a56bf6552d8de84658a6922727a4f65fffc9658397105527` |

### 2.4 第二轮双路 re-review 与 Controller 裁决

| 文件 | SHA-256 |
|---|---|
| AgentMiMo corrected re-review | `3af83fc542c341f0de3ed4c06db957ea556e7a7a7f5fbcbe7b7767d0f1953a8a` |
| AgentDS corrected re-review | `3f51cfb6b29ee2e9bd6790b378e70c469e1f3f08133add9c17f8919f4d47d38b` |
| Controller re-review adjudication | `27b659fa56567b1d53a928c379860620cd28d6250571ce14677e177a5e4ade18` |

### 2.5 Docstring fix 与 Controller 验证

| 文件 | SHA-256 |
|---|---|
| AgentCodex docstring fix artifact | `bc3bea16836b82ea8c2b6dfb07ad26fc41bbcc59598c4430e99d9fd7e1dec997` |
| Controller docstring fix validation | `ed69741337861ae7125e2d7d599aad7cb61e35573469b6a47ab3d795a72828cf` |

### 2.6 当前 S1 final production/test 文件终态

| 文件 | 行数 | SHA-256 | 与 fix-validation 一致 |
|---|---:|---|---|
| `dayu/cli/init_catalog.py` | 854 | `937315f3a6c83004788027c891c3b18e3cf2c848db2333430661998768ffe754` | ✓（只读 lock） |
| `dayu/cli/init_environment.py` | 584 | `71be5ba886df7a9d33c6c15da1fba172540124684b02c65c67e17852d736b77f` | ✓（只读 lock） |
| `tests/cli/test_init_catalog.py` | 710 | `086a143cf8247b6fe5371d6df5c2c5c6cc974410973d81d60bb7ccd8b6d05d9f` | ✓（docstring fixed） |
| `tests/cli/test_init_environment.py` | 782 | `820c2bf262dd77628201977e7d4f823265e141ac0ae6a28791bd7d12cf5ad01a` | ✓（docstring fixed） |

### 2.7 Full Ruff immutable fingerprint

| 指标 | 值 |
|---|---|
| Ruff version | `0.15.11` |
| Raw exit | `1`（预期，锁定历史诊断） |
| Count | `144` |
| SHA-256 | `051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea` |
| Baseline cmp | `0`（逐字节零差异） |

## 3. Review scope

### 3.1 完整逐行读取的文件

| 文件 | 行数 | 读取状态 |
|---|---:|---|
| `AGENTS.md` | 128 | 完整 |
| `docs/host/wu-semantic-ownership-01-r12-init-workflow-plan.md` | 608 | 完整 |
| `docs/reviews/wu-semantic-ownership-01-r12-s1-controller-validation.md` | 166 | 完整 |
| `docs/reviews/wu-semantic-ownership-01-r12-s1-implementation-codex.md` | 248 | 完整 |
| `docs/reviews/wu-semantic-ownership-01-r12-s1-code-review-mimo.md` | 294 | 完整 |
| `docs/reviews/wu-semantic-ownership-01-r12-s1-code-review-ds.md` | 442 | 完整 |
| `docs/reviews/wu-semantic-ownership-01-r12-s1-code-review-controller-adjudication.md` | 97 | 完整 |
| `docs/reviews/wu-semantic-ownership-01-r12-s1-code-review-fix-codex.md` | 304 | 完整 |
| `docs/reviews/wu-semantic-ownership-01-r12-s1-code-review-fix-controller-validation.md` | 100 | 完整 |
| `docs/reviews/wu-semantic-ownership-01-r12-s1-code-rereview-mimo.md` | 283 | 完整 |
| `docs/reviews/wu-semantic-ownership-01-r12-s1-code-rereview-ds.md` | 477 | 完整 |
| `docs/reviews/wu-semantic-ownership-01-r12-s1-code-rereview-controller-adjudication.md` | 91 | 完整 |
| `docs/reviews/wu-semantic-ownership-01-r12-s1-code-rereview-fix-codex.md` | 252 | 完整 |
| `docs/reviews/wu-semantic-ownership-01-r12-s1-code-rereview-fix-controller-validation.md` | 77 | 完整 |
| `dayu/cli/init_catalog.py` | 854 | 完整逐行走读 |
| `dayu/cli/init_environment.py` | 584 | 完整逐行走读 |
| `tests/cli/test_init_catalog.py` | 710 | 完整逐行走读 |
| `tests/cli/test_init_environment.py` | 782 | 完整逐行走读 |

### 3.2 排除范围

- Controller-owned `docs/host/issues-implementation-control.md`（有意 dirty，非 S1 scope）。
- 所有不在 S1 allowlist 的既有 production/test 文件（未修改，非本 review scope）。
- Package config、manifests、`models.json`（只读锚点，SHA 未漂移）。

### 3.3 并行 review 覆盖

本 re-review 是单 agent 完整独立执行，未使用 subagent 分片。全部 18 个文件均完整逐行阅读。

## 4. 四文件终态逐行审查

### 4.1 `dayu/cli/init_catalog.py`（854 行）

终态 SHA-256：`937315f3a6c83004788027c891c3b18e3cf2c848db2333430661998768ffe754`。

**模块概览**：`dayu-cli init` 的模型选择与 manifest 投影 owner。唯一拥有 15 项选择顺序、
普通/思考 pair、required env ref、dynamic current-schema record 与 16 个 known manifest
role projection。

**关键结构审查**：

| 结构 | 行号 | 审查结论 |
|---|---|---|
| `InitModelChoiceKind`（8 variants） | 39-49 | 正确，8 个 StrEnum 成员 |
| `InitModelChoice`（frozen dataclass） | 52-99 | `__post_init__` 校验非空、Ollama 不声明 secret |
| `INIT_MODEL_CHOICES`（15 items） | 102-223 | 精确 15 项，与 plan table 顺序一致 |
| `ORDINARY_MANIFEST_BASENAMES`（8 items） | 225-236 | 与 plan §4.1 一致 |
| `THINKING_MANIFEST_BASENAMES`（8 items） | 239-250 | 与 plan §4.1 一致 |
| `PRODUCTION_RUNTIME_MANIFEST_BASENAMES`（13 items） | 253-269 | 与 plan 一致 |
| `TEST_OWNED_MANUAL_SMOKE_MANIFEST_BASENAMES`（3 items） | 272-278 | 与 plan 一致 |
| `_validate_choice_tuple_shape()` | 522-541 | 校验 15 项、id 唯一、Ollama/custom id 锁定 |
| `_validate_resolved_choice()` | 544-563 | 消费真实 ConfigLoader resolved ModelsConfig |
| `_validate_ollama_template()` | 566-581 | provider=ollama、api_key_ref=None |
| `_validate_package_manifest_names()` | 584-601 | 精确 16 个 basename |
| `_validate_manifest_role_sets()` | 604-618 | 正交、并集一致 |
| `_validate_dynamic_model_inputs()` | 631-645 | 非空/外围空白/控制字符/正整数/非 bool |
| `_validate_endpoint()` | 648-668 | HTTP(S) scheme/netloc/hostname/port |
| `_build_ollama_record()` | 682-695 | 复制 template，只换 3 字段 |
| `_build_custom_openai_record()` | 698-726 | 完整 current-schema + 8 hints |
| `_custom_runner_option_hints()` | 729-745 | 精确 8 个 hint |
| `_validate_dynamic_selection()` | 748-771 | 重载后核对显式字段 |
| `_project_manifest_model()` | 774-789 | 只替换 `model.default_model_id` |
| `_require_manifest_model_object()` | 792-805 | 最小投影路径校验 |
| `_read_json_object()` | 808-821 | UTF-8 JSON object |
| `_require_json_object()` | 824-838 | string-keyed object |
| `_write_json()` | 841-854 | 当前 package 风格 |

**marker 状态机审查**：

- `InitModelChoiceKind`：8 个 StrEnum 成员，`__post_init__` 使用 `is` 比较 enum 实例，不漂移。
- `INIT_MODEL_CHOICES`：15 项 tuple，`_validate_choice_tuple_shape()` 校验长度、唯一性、
  Ollama/custom id 锁定。`InitModelSelection.__post_init__` 使用 `not in`（value equality），
  不引入 identity shim。
- Manifest role 集合：`ORDINARY`（8）∩ `THINKING`（8）= ∅；`PRODUCTION`（13）∩
  `TEST_OWNED`（3）= ∅；并集 = 16 = `_known_manifest_basenames()`。`_validate_manifest_role_sets()`
  在 `validate_init_catalog` 和 `project_known_manifest_models` 入口处校验。

**结论**：production 代码与 Codex completion artifact 描述完全一致。无漂移、无新增
compat/fallback/shim、无 weak typing、无网络调用（仅 `urllib.parse.urlsplit` 本地解析）、
无 `shell=True`/`text=True`/`print`/`logging`。

### 4.2 `dayu/cli/init_environment.py`（584 行）

终态 SHA-256：`71be5ba886df7a9d33c6c15da1fba172540124684b02c65c67e17852d736b77f`。

**模块概览**：`dayu-cli init` 的环境变量持久化 owner。唯一拥有 allowlisted persistence
entry/plan/result、POSIX 单 profile marker writer、Windows `setx` 与 whole-batch
current-process injection。

**关键结构审查**：

| 结构 | 行号 | 审查结论 |
|---|---|---|
| `EnvironmentPersistenceEntry` | 74-96 | `repr=False`，reject empty/NUL/CR/LF |
| `PosixEnvironmentPersistencePlan` | 100-121 | 只接受 `.zshrc`/`.bashrc` |
| `WindowsEnvironmentPersistencePlan` | 124-142 | 无 profile_path |
| `EnvironmentPersistenceResult` | 149-172 | 只含 names，不含 values |
| `persist_environment()` | 248-265 | confirmed 检查 → dispatch → whole-batch injection |
| `_persist_posix_environment()` | 285-311 | read → render → atomic write → verify → result |
| `_persist_windows_environment()` | 314-345 | `subprocess.run(("setx", name, value), shell=False, capture_output=True, text=False, check=False)` |
| `_read_profile_state()` | 376-398 | symlink/dangling/non-regular 拒绝 |
| `_render_profile_content()` | 401-430 | 追加或替换唯一 marker block |
| `_render_managed_block()` | 433-442 | `shlex.quote` 渲染 export 行 |
| `_parse_managed_block()` | 445-486 | **修复后逐行 marker 检测**（见下文） |
| `_parse_export_name()` | 489-503 | 只解析 name，不解析 value |
| `_write_profile_atomically()` | 506-539 | mkstemp → fchmod → fsync → os.replace |
| `_verify_written_profile()` | 542-557 | 磁盘重读校验 marker/name/mode |
| `_validate_entry_batch()` | 560-572 | 非空、name 唯一 |
| `_validate_environment_name()` | 575-584 | allowlist |

**marker 状态机审查（`_parse_managed_block()` 行 445-486）**：

修复后的逐行检测逻辑：

```
行 453: lines = content.splitlines(keepends=True)
行 454: normalized_lines = tuple(line.rstrip("\r\n") for line in lines)
行 455: begin_indexes = tuple(... if line == _DAYU_BLOCK_BEGIN)  ← 逐行精确等值
行 456: end_indexes = tuple(... if line == _DAYU_BLOCK_END)      ← 逐行精确等值
行 458-472: 逐行嵌入检测：
  - 行 459-460: 独立 marker 行 → continue
  - 行 461-468: 合法 export 行（`export NAME=value`）→ marker 在 value 侧 → continue
  - 行 471-472: 剩余行含 marker → reject
行 473-476: 结构校验（恰好一对、顺序正确）
行 477-486: block 内 export 行 → `_parse_export_name()` → allowlist
```

**逐行推演关键路径**：

| 输入行 | `export_head` | `marker_is_in_export_value` | 行为 |
|---|---|---|---|
| `# >>> dayu-cli init >>>`（独立 marker） | — | — | 行 459: `in {begin}` → continue |
| `export KEY='prefix # >>> suffix'`（value 含 marker） | `export KEY` | True（五条件全满足） | 行 469: continue |
| `prefix # >>> dayu-cli init >>> embedded`（普通文本） | `prefix # ...` | False（不 startswith） | 行 471: reject |
| `# see # >>> dayu-cli init >>> docs`（注释） | `# see # ...` | False（不 startswith） | 行 471: reject |
| `export=1`（空 name） | `export` | False（`== _EXPORT_PREFIX`） | 行 471: 如含 marker 则 reject |
| `# export NAME=marker`（注释 export） | `# export NAME` | False（不 startswith） | 行 471: 如含 marker 则 reject |

**防御层次**：
1. `export_head.startswith(_EXPORT_PREFIX)` — 防止注释行绕过
2. `export_head != _EXPORT_PREFIX` — 防止空变量名绕过
3. `_DAYU_BLOCK_BEGIN not in export_head` — 防止 marker 在名称左侧
4. 所有通过嵌入检测的 export 行仍经过 `_parse_export_name()` → `_validate_environment_name()` allowlist

**结论**：marker 状态机合法/非法边界不漂移。合法 marker value 的 export 行被正确跳过；
非法嵌入（普通文本、注释、非法 export shape）仍 fail closed。值拒绝集合仍仅为
empty/NUL/CR/LF。修复未引入 regex/parser framework/compat/fallback/shim。

### 4.3 `tests/cli/test_init_catalog.py`（710 行）

终态 SHA-256：`086a143cf8247b6fe5371d6df5c2c5c6cc974410973d81d60bb7ccd8b6d05d9f`。

**test count**：16 个 test 函数。

**docstring 审查**：全部 16 个函数均有完整中文 docstring，含 `:param`、`:returns:`、`:raises`。
与 Codex docstring fix artifact 的 16/16 closure 列表精确匹配。

**签名/body/assertion/fixture 审查**：

逐行确认以下不变量：
- 无新增/删除/重命名 test 函数
- decorator 未变（`@pytest.mark.parametrize` 保持原参数）
- 参数签名未变
- test body/assertion 逻辑未变
- fixture 使用（`tmp_path`、`monkeypatch`）未变
- production code import 未变

**结论**：精确 32 项 docstring closure 的 catalog 部分（16/16）已正确完成。只改文档，
不改 decorator/signature/body/assertion/fixture/test count。

### 4.4 `tests/cli/test_init_environment.py`（782 行）

终态 SHA-256：`820c2bf262dd77628201977e7d4f823265e141ac0ae6a28791bd7d12cf5ad01a`。

**test count**：18 个 test 函数（含 `_SetxRecorder` helper class）。

**docstring 审查**：全部 18 个函数均有完整中文 docstring，含 `:param`、`:returns:`、`:raises`。
其中 16 个由 Codex docstring fix 补齐，2 个（`test_marker_substrings_in_export_values_succeed_for_create_and_replace`
与 `test_malformed_marker_structures_fail_closed_without_injection`）在 CR-F01 fix 阶段已完整。

**签名/body/assertion/fixture 审查**：

逐行确认以下不变量：
- 无新增/删除/重命名 test 函数
- decorator 未变
- 参数签名未变
- test body/assertion 逻辑未变
- `_SetxRecorder` helper class 未变
- fixture 使用未变

**结论**：精确 32 项 docstring closure 的 environment 部分（16/16）已正确完成。只改文档，
不改 decorator/signature/body/assertion/fixture/test count。

## 5. R12-S1-CR-F01 闭合验证（HIGH）

### 5.1 Finding 回顾

Controller 在 initial validation 中发现：`_parse_managed_block()` 使用全文
`content.count(marker)` 检测嵌入 marker，导致合法 secret value 包含 marker 子串时
被错误拒绝。Codex fix 将检测逻辑改为逐行解析。

### 5.2 独立验证

本 re-reviewer 独立逐行走读修复后的 `_parse_managed_block()` 行 445-486，确认：

1. **合法 marker value × create/replace 成功**：`export_head.startswith(_EXPORT_PREFIX)`
   且 `export_head != _EXPORT_PREFIX` 且 marker 不在 `export_head` 中 →
   `marker_is_in_export_value = True` → continue → 不触发嵌入拒绝。
2. **malformed 仍 fail closed**：9 个参数化 case 全部在 `_parse_managed_block` 或
   `_parse_export_name` 被正确拒绝。
3. **未扩大 value reject 集合**：`EnvironmentPersistenceEntry.__post_init__` 仍只拒绝
   empty/NUL/CR/LF。
4. **不泄 secret**：entry.value 的 `repr=False`、异常只含 name、result 只含 names。
5. **不改变 Windows/catalog contract**：`init_catalog.py` SHA 不变、Windows 路径未修改。

**裁决**：`R12-S1-CR-F01 CLOSED / VERIFIED / FIX CORRECT`。

## 6. R12-S1-RR-CF01 闭合验证（LOW）

### 6.1 Finding 回顾

Controller 在 re-review adjudication 中发现：两个测试文件各 16 个函数缺少完整中文
docstring，违反 AGENTS.md 编码硬约束。

### 6.2 独立验证

本 re-reviewer 独立运行 AST docstring contract scan：

```text
dayu/cli/init_catalog.py: 0
dayu/cli/init_environment.py: 0
tests/cli/test_init_catalog.py: 0
tests/cli/test_init_environment.py: 0
```

精确 32 个函数已补齐完整中文 docstring（`:param`、`:returns:`、`:raises`）。
decorator/signature/body/assertion/fixture/test count 未变。

**裁决**：`R12-S1-RR-CF01 CLOSED / VERIFIED / FIX CORRECT`。

## 7. 独立机械验证

### 7.1 四文件 SHA-256 终态

```text
dayu/cli/init_catalog.py:      937315f3a6c83004788027c891c3b18e3cf2c848db2333430661998768ffe754
dayu/cli/init_environment.py:   71be5ba886df7a9d33c6c15da1fba172540124684b02c65c67e17852d736b77f
tests/cli/test_init_catalog.py: 086a143cf8247b6fe5371d6df5c2c5c6cc974410973d81d60bb7ccd8b6d05d9f
tests/cli/test_init_environment.py: 820c2bf262dd77628201977e7d4f823265e141ac0ae6a28791bd7d12cf5ad01a
```

与 Controller docstring fix validation 和 Codex docstring fix artifact 一致。

### 7.2 四文件 AST param/returns/raises 缺口

```text
dayu/cli/init_catalog.py: 0
dayu/cli/init_environment.py: 0
tests/cli/test_init_catalog.py: 0
tests/cli/test_init_environment.py: 0
```

### 7.3 66 focused tests

```text
66 passed in 0.22s
```

### 7.4 双 coverage

| 文件 | Statements | Miss | Coverage | Gate |
|---|---:|---:|---:|---|
| `init_catalog.py` | 276 | 27 | 90.22% | PASS (≥80%) |
| `init_environment.py` | 233 | 13 | 94.42% | PASS (≥80%) |

### 7.5 Full pyright

```text
0 errors, 0 warnings, 0 informations
```

### 7.6 Scoped Ruff

```text
All checks passed!
```

### 7.7 Full Ruff exact baseline

```text
Raw exit: 1 (expected)
Count: 144
SHA-256: 051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea
cmp vs baseline: exit 0 (byte-identical)
```

### 7.8 Diff / staged

```text
git diff --check: exit 0, no diagnostics
git diff --cached --name-only: empty
```

### 7.9 Source / security scans

| 扫描项 | 范围 | 结果 |
|---|---|---|
| Weak typing（`Any`、`object`、`hasattr`、`getattr`） | 四文件 | 零命中 |
| Compat/fallback/shim/rollback | environment + tests | 零命中 |
| `content.count(_DAYU_BLOCK` | 四文件 | 零命中（已移除） |
| `import re` / `re.compile` | 四文件 | 零命中 |
| Network/runtime assembly | production | 仅 `urllib.parse.urlsplit`（本地解析） |
| Unsafe shell/output（`shell=True`、`text=True`、`print`、`logging`） | production | 零命中 |
| Authorization/permission | production | 零命中 |

## 8. Decorator / signature / body / assertion / fixture / test count 不漂移确认

| 检查项 | init_catalog | init_environment | test_catalog | test_environment |
|---|---|---|---|---|
| decorator 未变 | ✓ | ✓ | ✓ | ✓ |
| signature 未变 | ✓ | ✓ | ✓ | ✓ |
| body 未变 | ✓ | ✓ | ✓ | ✓ |
| assertion 未变 | ✓ | ✓ | ✓ | ✓ |
| fixture 未变 | ✓ | ✓ | ✓ | ✓ |
| test count | N/A | N/A | 16 | 18 |

## 9. Production hashes / Windows / catalog / security contract 不漂移确认

| 检查项 | 状态 |
|---|---|
| `init_catalog.py` SHA = 只读 lock | ✓ |
| `init_environment.py` SHA = 只读 lock | ✓ |
| Windows `setx` 调用仍为 `shell=False, capture_output=True, text=False, check=False` | ✓ |
| Windows partial failure 仍只报告 names | ✓ |
| POSIX `os.environ` 注入仍仅在 `result.succeeded` 后 | ✓ |
| Entry value reject 集合仍为 empty/NUL/CR/LF | ✓ |
| Manifest role 集合仍正交、并集 = 16 | ✓ |
| Secret 不泄漏到 repr/exception/captured output | ✓ |

## 10. Findings

### 10.1 R12-S1-CR-F01（HIGH）— CLOSED

见 §5。Codex fix 正确解决 marker-substring false rejection。逐行推演确认修复完整、
最小、保守。两路 re-review 一致 PASS。

### 10.2 R12-S1-RR-CF01（LOW）— CLOSED

见 §6。32 个测试函数 docstring 已补齐。AST scan 确认 0/0/0/0。只改文档，不改代码。

### 10.3 新 findings

**未发现实质性问题。**

本 re-reviewer 在独立逐行走读四个 S1 文件终态、全部 S1 artifacts、完整验证套件和
source/security scans 后，未发现新的 correctness、security 或 architecture defect。

## 11. Open Questions

无。

## 12. Residual Risk

### 12.1 Windows `setx` 跨变量不可回滚

accepted plan §10.1 的明确残余。当前实现正确地在首个失败后停止，并只报告 names。
真实 Windows runner 继续是 umbrella release blocker。本 final re-review 未改变该分类。

### 12.2 Windows `capture_output=True` 的潜在 secret 驻留

`subprocess.run` 返回的 `CompletedProcess.stdout`/`.stderr` 可能含 secret。当前
production 不读取这些属性。建议在未来 S3 添加 docstring 约束。不在 S1 scope。

### 12.3 写后校验故障的"profile 已替换"真实状态

`_verify_written_profile` 失败时 `os.replace` 已完成。当前 contract 正确反映此事实
（不注入 env、不 publish workspace），但没有 rollback。这是 accepted plan §5.2 的行为。

### 12.4 Coverage 缺口

- `init_catalog.py` 的 27 条未覆盖语句：主要是防御性 validation 分支（tuple shape、
  dynamic reload mismatch）。覆盖率 90.22%，远超 80% 门槛。
- `init_environment.py` 的 13 条未覆盖语句：主要是 `OSError`/`UnicodeError` except
  分支。覆盖率 94.42%，远超 80% 门槛。

### 12.5 S1 不覆盖的范围（按计划延后）

- S2：real Service discovery、workspace transaction、四态编排。
- S3：非网络 prewarm、真实 POSIX/Windows subprocess smoke、README、CI workflow。
- Issue 142/151/175/177/178、Topic 8/9（plan §1.3 明确排除）。

## 13. Final verdict

| Item | Status |
|---|---|
| R12-S1-CR-F01 (HIGH) | **CLOSED** — Codex fix verified |
| R12-S1-RR-CF01 (LOW) | **CLOSED** — Docstring fix verified |
| New findings | **0** |
| Accepted open | **0** |
| Blockers | **0** |
| Decorator/signature/body/assertion/fixture/test count drift | **0** |
| Production hash drift | **0** |
| Windows/catalog/security contract drift | **0** |
| Marker state machine drift | **0** |
| AST param/returns/raises gap | **0/0/0/0** |
| Residual owner | S3 real Windows gate (accepted plan) |
| Ready for Controller final adjudication | **YES** |

## 14. Artifact metadata

- 本文件路径：`docs/reviews/wu-semantic-ownership-01-r12-s1-code-final-rereview-mimo.md`
- 不修改 code/tests/plan/control/既有 artifacts，不 stage/commit。
- 未进入 S2/S3。
