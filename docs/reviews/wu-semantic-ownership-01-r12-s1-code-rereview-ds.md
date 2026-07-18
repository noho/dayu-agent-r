# WU-SEMANTIC-OWNERSHIP-01 / R12 S1 第二路独立完整 Code Re-Review（AgentDS）

## 1. Gate 身份

- 现有 umbrella WU `WU-SEMANTIC-OWNERSHIP-01`，R12 S1 fixed cumulative tree。
- 本 artifact 是第二路（AgentDS）独立完整 code **re-review**，不是新 WU。
- 不授权 S2/S3、fix、stage、commit、push 或 PR。
- HEAD：`8f7a1946fa46975c3b9e1aefdc2eb3c765b001f8`。
- Branch：`phaseflow/host-issues-control`。

## 2. Authority 完整 hashes

### 2.1 计划与原始验证

| 文件 | 行数 | SHA-256 |
|---|---:|---|
| Accepted plan | 608 | `69ddfd888336cbb70d093743a96a56f18e694fa68436fb086be1c9b56dcb88c2` |
| S1 Controller validation | 166 | `826b11a6caa288c19562b1663b3000448dbdd3ff519ab40971b27f199f9bec19` |
| S1 implementation artifact (AgentCodex) | 248 | `278ced438b77b8296bf3fc4a669dbc991e24703bbf168e89c20df32bceac2fed` |

### 2.2 第一轮双路 review

| 文件 | 行数 | SHA-256 |
|---|---:|---|
| AgentMiMo initial review | 294 | `4f27c186ac0ec9f439956f5eadf34458dd7f11455d5a8684f57e9d3dfcdc7492` |
| AgentDS initial review | 442 | `06094e2704e6f8a42385f77e7d0e0fa56474be40272bfe511948b81958900652` |

### 2.3 Controller 裁决与修复

| 文件 | 行数 | SHA-256 |
|---|---:|---|
| Controller adjudication | 97 | `b3a9aca59a9f03bd1cf143bc6f4e5f30e35560d09054d1240f72d5dd5f441c19` |
| AgentCodex fix artifact | 304 | `b9702a729a080b53d4585527f722b905777102bcf9f1288f2e0dbd49bd48fb44` |
| Controller fix validation | 100 | `fd4afc8c6bc5bc52a56bf6552d8de84658a6922727a4f65fffc9658397105527` |

### 2.4 当前 S1 fixed production/test 文件

| 文件 | 行数 | SHA-256 | 与 fix-validation 一致 |
|---|---:|---|---|
| `dayu/cli/init_catalog.py` | 854 | `937315f3a6c83004788027c891c3b18e3cf2c848db2333430661998768ffe754` | ✓（只读 lock） |
| `dayu/cli/init_environment.py` | 584 | `71be5ba886df7a9d33c6c15da1fba172540124684b02c65c67e17852d736b77f` | ✓（fixed） |
| `tests/cli/test_init_catalog.py` | 610 | `23f1c406e89c62159ea89e5fd4d795aecf9237ec2d42fae0ac06870e7b0473b4` | ✓（只读 lock） |
| `tests/cli/test_init_environment.py` | 672 | `ae243050136d92e0c772caf3a51b3bdd999ff8efe3af096d73161f32473fd947` | ✓（fixed） |

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
| `dayu/cli/init_catalog.py` | 854 | 完整逐行走读 |
| `dayu/cli/init_environment.py` | 584 | 完整逐行走读 |
| `tests/cli/test_init_catalog.py` | 610 | 完整逐行走读 |
| `tests/cli/test_init_environment.py` | 672 | 完整逐行走读 |

### 3.2 排除范围

- Controller-owned `docs/host/issues-implementation-control.md`（有意 dirty，非 S1 scope）。
- 所有不在 S1 allowlist 的既有 production/test 文件（未修改，非本 review scope）。
- Package config、manifests、`models.json`（只读锚点，SHA 未漂移）。
- S2/S3 实现文件（不在本 slice）。

### 3.3 并行 review 覆盖

本 re-review 是单 agent 完整独立执行，未使用 subagent 分片。全部 13 个文件均完整逐行阅读。

## 4. 独立机械验证

### 4.1 Four-file focused tests

```bash
pytest tests/cli/test_init_catalog.py tests/cli/test_init_environment.py -q
```

**结果**：exit `0`，`66 passed in 0.21s`。与 Controller fix validation 一致。

### 4.2 单文件覆盖率

```bash
pytest tests/cli/test_init_catalog.py --cov=dayu.cli.init_catalog --cov-report=term-missing --cov-fail-under=80 -q
```

**结果**：`276 statements / 27 miss / 90.22%` ≥ 80%。与只读基线 `90.22%` 精确一致，未退化。

```bash
pytest tests/cli/test_init_environment.py --cov=dayu.cli.init_environment --cov-report=term-missing --cov-fail-under=80 -q
```

**结果**：`233 statements / 13 miss / 94.42%` ≥ 80%。与 Controller fix validation 一致。

### 4.3 Full pyright

```bash
python -m pyright dayu/ tests/ utils/
```

**结果**：`0 errors, 0 warnings, 0 informations`。通过。

### 4.4 Four-file scoped Ruff

```bash
python -m ruff check dayu/cli/init_catalog.py dayu/cli/init_environment.py \
  tests/cli/test_init_catalog.py tests/cli/test_init_environment.py
```

**结果**：`All checks passed!`。通过。

### 4.5 Full Ruff immutable fingerprint

```bash
python -m ruff check dayu/ tests/ utils/ --output-format=json > workspace/tmp/r12-ruff-current.json
```

- Raw exit：`1`（预期）
- Count：`144`
- SHA-256：`051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea`
- `cmp` vs baseline：exit `0`（逐字节相同）

### 4.6 Git diff / staged

- `git diff --check`：exit `0`，无诊断
- `git diff --cached --name-only`：空
- `git status --short`：符合预期（control dirty + S1 untracked paths + review artifacts）

### 4.7 综合 source scans

| 扫描项 | 范围 | 结果 |
|---|---|---|
| Weak typing（`Any`、`object`、`hasattr`、`getattr`） | S1 production + tests | 零命中 |
| Legacy compat（`compat`、`fallback`、`shim`、`rollback`、`_init_model_role`） | S1 production | 零命中（仅 test 负断言命中） |
| Legacy compat（`default_name`） | S1 production | 零命中（仅 test 负断言命中） |
| `content.count(marker)` | S1 production | 零命中（已移除） |
| `import re` / `re.compile` | S1 production | 零命中（未引入 regex framework） |
| Secret leaks（`print`、`logging`、stdout/stderr 读取） | S1 production | 零命中 |
| Network clients（`requests`、`httpx`、`socket`、`download`） | S1 production | 仅 `urllib.parse.urlsplit`（本地 URL 解析） |
| Runtime assembly（`prepare_entrypoint_runtime`、`open_host`、`asyncio.run`） | S1 production | 零命中 |
| Unsafe shell（`shell=True`、`text=True`） | S1 production | 零命中 |
| Authorization/permission | S1 production | 零命中 |
| `os.environ[...]` 写入 | production | 仅行 264，在 `result.succeeded` 后 |

全部 source scans 通过。

## 5. R12-S1-CR-F01 闭合独立验证

### 5.1 修复变更精确范围

修复仅修改 `_parse_managed_block()` 函数内部（`init_environment.py:457-472`），替换了原有的 `content.count(marker)` 全文子串检测逻辑。

**修复前**（行 457，已移除）：
```python
if content.count(_DAYU_BLOCK_BEGIN) != len(begin_indexes) or \
   content.count(_DAYU_BLOCK_END) != len(end_indexes):
    raise EnvironmentPersistenceError("POSIX profile contains an embedded Dayu init marker")
```

**修复后**（行 457-472，当前）：
```python
# 结构 marker 只由独立整行产生；export 的等号右侧是合法 value，不参与结构计数。
for line in normalized_lines:
    if line in {_DAYU_BLOCK_BEGIN, _DAYU_BLOCK_END}:
        continue
    export_head, separator, _export_value = line.partition("=")
    marker_is_in_export_value = (
        bool(separator)
        and export_head.startswith(_EXPORT_PREFIX)
        and export_head != _EXPORT_PREFIX
        and _DAYU_BLOCK_BEGIN not in export_head
        and _DAYU_BLOCK_END not in export_head
    )
    if marker_is_in_export_value:
        continue
    if _DAYU_BLOCK_BEGIN in line or _DAYU_BLOCK_END in line:
        raise EnvironmentPersistenceError("POSIX profile contains an embedded Dayu init marker")
```

### 5.2 修复契约逐项独立验证

#### 契约 1：合法 marker value × create/replace 成功

**验证方法**：独立逐行走读 `_parse_managed_block()` 与 `test_marker_substrings_in_export_values_succeed_for_create_and_replace`。

`_parse_managed_block()` 的判定逻辑（逐行分解）：

| 步骤 | 代码位置 | 对合法 export 行的行为 |
|---|---|---|
| 1. 识别结构 marker 行 | 455-456 | 逐行精确等值匹配 → `begin_indexes`/`end_indexes` 只包含真正独立 marker 行 |
| 2. 跳过独立 marker 行 | 459-460 | `line in {begin, end}` → continue，不计为 embedded |
| 3. 判断是否为合法 export 值行 | 461-468 | `partition("=")` + 五个条件 → `marker_is_in_export_value=True` |
| 4. 跳过合法 export 值行 | 469-470 | continue，不检查 marker 子串 |
| 5. 嵌入式检测（仅对剩余行） | 471-472 | `_DAYU_BLOCK_BEGIN in line or _DAYU_BLOCK_END in line` → reject |

对 `export OPENAI_API_KEY='prefix # >>> dayu-cli init >>> suffix'`：
- 步骤 1：不是独立 marker 行 → 不加入 begin/end indexes
- 步骤 2：不是 marker 行 → 不跳过
- 步骤 3：`export_head = "export OPENAI_API_KEY"`，满足全部五条件 → `marker_is_in_export_value=True`
- 步骤 4：continue → 不检查 marker
- 步骤 5：不执行

**测试覆盖**：测试 `test_marker_substrings_in_export_values_succeed_for_create_and_replace` 参数化 3 × 2 矩阵：
- begin marker 子串 × absent/existing profile
- end marker 子串 × absent/existing profile
- begin+end marker 子串 × absent/existing profile

六个 case 全部断言：
- `result.succeeded is True`
- 独立 begin/end marker 行各恰好一个（`lines.count(...) == 1`）
- `shlex.quote(secret)` 在 export 行中
- `os.environ[name] == secret`
- 首次创建 mode 为 `0600`，已有替换保留 `0640`

**裁决**：✅ 契约 1 满足。所有 6 个场景成功，测试使用真实 entry/plan/writer 和真实临时 profile。

#### 契约 2：malformed 仍 fail closed

**验证方法**：逐行走读 `test_malformed_marker_structures_fail_closed_without_injection`（9 参数化 case）及 `_parse_managed_block()` 逻辑。

| 输入 | 期望 | 实际 | 原因 |
|---|---|---|---|
| 缺 end marker | reject | reject | 行 475: `len(end_indexes) != 1` |
| 缺 begin marker | reject | reject | 行 475: `len(begin_indexes) != 1` |
| 逆序 | reject | reject | 行 475: `begin_indexes[0] >= end_indexes[0]` |
| 多块 | reject | reject | 行 475: `len(begin_indexes) != 1` |
| 普通文本嵌入 marker | reject | reject | 行 471-472: 不命中 Case 1/2 → marker in line |
| 注释嵌入 marker | reject | reject | 行 471-472: 不命中 Case 1/2 → marker in line |
| 非法 block 行 | reject | reject | 行 497-498: `_parse_export_name` 拒绝 |
| 缺 `=` 的 export | reject | reject | 行 497-498: `_parse_export_name` 拒绝 |
| 非法 name 但 value 含 marker | reject | reject | 行 469-470 跳过嵌入检测 → 行 502 `_validate_environment_name` 拒绝 |

每个 case 额外断言：
- `profile.read_bytes() == before`（profile 未被 mutation）
- `entry.name not in os.environ`（未注入）
- `entry.value not in repr(error.value)`（不泄漏 secret）

**裁决**：✅ 契约 2 满足。全部 9 个 malformed 场景正确 fail closed。

#### 契约 3：未扩大 value reject 集合

**验证方法**：逐行走读 `EnvironmentPersistenceEntry.__post_init__()`（行 85-96）。

```python
def __post_init__(self) -> None:
    _validate_environment_name(self.name)
    if not self.value:
        raise EnvironmentPersistenceError(...)
    if any(character in self.value for character in ("\x00", "\r", "\n")):
        raise EnvironmentPersistenceError(...)
```

value rejection 集合仍仅为：空值、NUL（`\x00`）、CR（`\r`）、LF（`\n`）。没有新增 marker 黑名单、regex/parser framework 或兼容分支。

**裁决**：✅ 契约 3 满足。value rejection 集合未扩大。

#### 契约 4：不泄 secret

**验证方法**：扫描所有 secret 相关路径。
- `entry.value` 仅在三处使用：`os.environ` 注入（行 264，在 success 后）、`setx` argument tuple（行 329）、`shlex.quote` 写入 profile（行 441）
- 无 `print`、`logging`、stdout/stderr 读取
- 全部异常/repr/result 只携带 env name / safe target
- 测试使用 `secrets.token_urlsafe()` 运行期生成 secret，不写入 source/artifact

**裁决**：✅ 契约 4 满足。无 secret 泄漏。

#### 契约 5：不改变 Windows 或 catalog contract

**验证方法**：SHA-256 比较与逐行走读。

- `init_catalog.py`：SHA `937315f3a6...` = 只读 lock，未修改
- `test_init_catalog.py`：SHA `23f1c406...` = 只读 lock，未修改
- Windows `_persist_windows_environment()`（行 314-345）：未修改，仍为 `subprocess.run(("setx", entry.name, entry.value), shell=False, capture_output=True, text=False, check=False)`
- Windows `_windows_failure_result()`（行 348-373）：未修改

**裁决**：✅ 契约 5 满足。Windows 与 catalog contract 未改变。

### 5.3 R12-S1-CR-F01 闭合裁决

| 契约 | 状态 |
|---|---|
| 1. 合法 marker value × create/replace 成功 | ✅ 通过 |
| 2. malformed fail closed | ✅ 通过 |
| 3. 未扩大 value reject | ✅ 通过 |
| 4. 不泄 secret | ✅ 通过 |
| 5. 不改变 Windows/catalog | ✅ 通过 |

**裁决**：`R12-S1-CR-F01 CLOSED / VERIFIED / FIX CORRECT`。

## 6. 补充 adversarial 独立验证

### 6.1 Parser 是否把看似 export 的任意行错误放行

逐行走读扩展边缘 case 推演：

| 行内容 | `export_head` | `marker_is_in_export_value` | 实际行为 | 正确？ |
|---|---|---|---|---|
| `export NAME=value`（合法） | `export NAME` | True | 跳过嵌入检测 → `_parse_export_name` 校验 name | ✓ |
| `export NAME = value`（空格） | `export NAME ` | True（startswith） | 跳过 → `_parse_export_name` 校验 | ✓ |
| `export =value`（空 name） | `export ` | **False**（`== _EXPORT_PREFIX`） | 嵌入检测 → 如有 marker 则 reject | ✓ |
| `# export NAME=value`（注释） | `# export NAME` | **False**（不 startswith） | 嵌入检测 → 如有 marker 则 reject | ✓ |
| `export# marker=value` | `export# marker` | **False**（marker in head） | 嵌入检测 → reject | ✓ |
| `notexport NAME=value` | `notexport NAME` | **False**（不 startswith） | 嵌入检测 → 如有 marker 则 reject | ✓ |
| `export`（无 `=`） | `export` | **False**（无 separator） | 嵌入检测 → 本身不含 marker，不触发 | ✓ |
| `export INVALID_NAME='marker'` | `export INVALID_NAME` | True | 跳过嵌入 → `_validate_environment_name` reject | ✓ |

**关键防御点**：
- `export_head != _EXPORT_PREFIX` 防止空变量名绕过
- `_DAYU_BLOCK_BEGIN not in export_head and _DAYU_BLOCK_END not in export_head` 防止 marker 在变量名左侧
- `line.startswith(_EXPORT_PREFIX)` 防止注释行绕过
- 所有通过嵌入检测的行仍经过 `_parse_export_name` → `_validate_environment_name` 的 name allowlist 校验

**裁决**：✅ 无绕过。看似 export 的任意非标准行要么被嵌入检测拒绝，要么被 name allowlist 拒绝。

### 6.2 写后 state 一致性

逐行追踪写后验证链路（`_verify_written_profile` → `_parse_managed_block`）：

1. `os.replace` 完成 → profile 磁盘内容 = 新 block 内容
2. `_read_profile_state` 从磁盘重读 → 内容 = 新 block
3. `_parse_managed_block(state.content)` 对新内容：
   - 逐行精确匹配 → begin_indexes = (n,), end_indexes = (m,) 各一个
   - 逐行嵌入检测 → export 行含 marker 子串 → `marker_is_in_export_value=True` → 跳过
   - 行 473: `begin_indexes and end_indexes` → 继续
   - 行 475: `len(begin_indexes) == 1 and len(end_indexes) == 1 and begin < end` → 通过
   - 行 477-485: `_parse_export_name` 解析 block 内 export 行 → 返回 names
4. `managed.environment_names == expected_names` → 通过
5. `state.mode == expected_mode` → 通过

**裁决**：✅ 写后 state 一致。磁盘内容与结构期望匹配，verification 不再因合法 marker value 误报。

### 6.3 Value-object equality no-fix 保持

- `init_catalog.py:358`：`if self.choice not in INIT_MODEL_CHOICES` — 仍使用 dataclass `__eq__`（值比较），未引入 identity check
- `test_selection_rejects_static_dynamic_and_dynamic_kind_mismatch`（test_init_catalog.py:492-517）— 验证 forged choice（不同 choice_id）被拒绝
- 语义相同 copy 可通过 membership 是 frozen dataclass 的正确 value-object 行为
- 无 registry、framework、identity shim 引入

**裁决**：✅ Value-object equality no-fix 保持，未退化。

### 6.4 修复范围 boundary 检查

| 检查项 | 结果 |
|---|---|
| 修改仅在 `init_environment.py` `_parse_managed_block()` 内部 | ✅ |
| 未新增 import（无 `re`、无新依赖） | ✅ |
| 未新增 class / public API | ✅ |
| 未改变 `_parse_managed_block()` 返回值类型 | ✅ |
| 未改变异常类型/语义 | ✅ |
| 未引入 compat/fallback/shim/rollback | ✅ |
| 测试扩展了既有 malformed parameter matrix（5→9 case）并新增 marker-value 正反矩阵，未引入 compat/unrelated test shim | ✅ |
| Catalog SHA 不变 | ✅ |

### 6.5 Catalog / model / manifest owner 完整链

| 检查项 | 结果 |
|---|---|
| 15 项选择顺序与 plan §4.1 精确对应 | ✅ |
| 13 static pair 通过真实 `ConfigLoader.load_models()` + extends resolver | ✅ |
| Package `ollama` template `provider=ollama`、`api_key_ref=None` | ✅ |
| Package 缺少 `custom-openai` 不是静态错误 | ✅ |
| Ollama record 复制完整 template，只替换 model/endpoint/context | ✅ |
| Custom record 完全匹配 plan §4.2（headers、capabilities、timeout/retry/SSE、八 hints） | ✅ |
| 八 hints 精确匹配 plan §4.2 投影 | ✅ |
| Dynamic 输入在 mutation 前拒绝空/空白/控制字符/非 HTTP(S) URL/非正整数/bool | ✅ |
| Dynamic record 写回后由真实 `ConfigLoader` 重载校验 | ✅ |
| 16 known manifest role 集合互斥、无交集、并集等于 package basenames | ✅ |
| Projection 只改写 `model.default_model_id`，保留其他字段 | ✅ |
| 用户自建 manifest 不被枚举或改写 | ✅ |
| 13 production / 3 test-owned manual-smoke 边界正确 | ✅ |
| Production 不含 `manual-smoke` catalog/fixture/provider 构造 | ✅ |

### 6.6 Environment persistence owner 完整链

| 检查项 | 结果 |
|---|---|
| Entry `value` 使用 `repr=False`（脱敏） | ✅ |
| Name 必须来自 allowlist | ✅ |
| 空值、NUL、CR、LF 在 entry 构造时拒绝 | ✅ |
| POSIX plan 只接受 `.zshrc` / `.bashrc` target | ✅ |
| 未确认 plan 拒绝执行（confirmed=False） | ✅ |
| Profile symlink / dangling symlink 拒绝 | ✅ |
| Profile 目录 / 非普通文件拒绝 | ✅ |
| 缺失 profile 以 `0600` 创建 | ✅ |
| 已存在 profile 保留原 mode | ✅ |
| `shlex.quote` 正确应用于所有值 | ✅ |
| 原子写入：同父目录 `mkstemp` → `fchmod` → `flush`/`fsync` → `os.replace` | ✅ |
| 写后从磁盘重读校验 marker/name/mode 结构 | ✅ |
| 写后校验失败时不注入 env | ✅ |
| 异常/result/captured output 不含 secret value | ✅ |
| Windows：`("setx", name, value)` argument tuple | ✅ |
| Windows：`shell=False`、`capture_output=True`、`text=False`、`check=False` | ✅ |
| Windows + POSIX：只有 whole-batch success 后才注入 `os.environ` | ✅ |

### 6.7 类型安全与编码约束

| 检查项 | 结果 |
|---|---|
| 无 `Any`、`object`、无类型签名 | ✅ |
| 无 `hasattr`/`getattr` | ✅ |
| 全部 production 函数有完整中文 docstring（参数、返回值、异常）；测试函数 docstring 由 Controller 另行独立裁决 | ✅ |
| 类/模块有中文概览 docstring | ✅ |
| 无嵌套函数/类 | ✅ |
| 无 magic number / magic string（仅 tool schema 内字面量） | ✅ |
| 无 lazy import | ✅ |
| 无兼容性 re-export / wrapper / facade | ✅ |

## 7. Findings

### DS-R12-S1-RR-F01 — 闭合 — 已修复 — R12-S1-CR-F01 marker 子串误判

- **状态**：`CLOSED / FIX VERIFIED`
- **来源**：AgentMiMo `R12-S1-CR-01`、AgentDS `DS-R12-S1-01`、Controller validation §5 → Controller adjudication `R12-S1-CR-F01 ACCEPTED/HIGH`
- **修复位置**：`dayu/cli/init_environment.py:457-472`（替换原有 `content.count()` 检测）
- **独立验证结论**：修复正确、完整、最小。逐行推演确认：
  - 合法 begin/end/both marker value × create/replace：6/6 成功
  - malformed text/comment/name/export/配对/多块：9/9 仍 fail closed
  - 未扩大 value reject 集合
  - 不泄 secret
  - 不改变 Windows 或 catalog contract
  - 未引入 regex/parser framework/compat/fallback
- **闭合证据**：见 §5 完整逐契约验证与 §6 补充 adversarial 验证

### DS-R12-S1-RR-NF01 — 无 finding — Value-object equality no-fix 确认

- **状态**：`CONFIRMED NO FINDING`
- **来源**：Controller adjudication `REJECTED / NO FIX`
- **独立验证结论**：`InitModelChoice` frozen dataclass value equality 行为正确；语义相同 copy 通过 membership 是 value-object 的正确 contract；语义不同的 forged choice 被正确拒绝；无 identity shim 引入

## 8. Open Questions

无。

## 9. Residual Risk

### 9.1 Windows `setx` 跨变量不可回滚

- 这是 accepted plan §10.1 的明确残余，fix 未扩域。当前实现正确地在首个失败后停止，并只报告 names。

### 9.2 Windows `capture_output=True` 的潜在 secret 驻留

- `subprocess.run` 返回的 `CompletedProcess.stdout`/`.stderr` 可能含 secret（取决于 Windows `setx` 行为）。当前 production 不读取这些属性，但若未来添加 logging/debug 可能泄漏。建议在未来 S3 或后续添加显式 docstring 约束。

### 9.3 写后校验故障的"profile 已替换"真实状态

- `_verify_written_profile` 失败时，`os.replace` 已完成。当前 contract 正确反映此事实（不注入 env、不 publish workspace），但没有 rollback。这是 accepted plan §5.2 的行为，不在本 fix scope。

### 9.4 Coverage 缺口

- `init_catalog.py` 的 27 条未覆盖语句：主要是防御性 validation 分支（tuple shape、dynamic reload mismatch），在当前稳定 package config 下难以触发。覆盖率达 90.22%，远超 80% 门槛。
- `init_environment.py` 的 13 条未覆盖语句：主要是 `OSError`/`UnicodeError` except 分支（`lstat` 失败、UTF-8 解码失败），属于 OS 级边界。覆盖率达 94.42%，远超 80% 门槛。

### 9.5 S1 不覆盖的范围（按计划延后）

- S2：real Service discovery、workspace transaction、四态编排
- S3：非网络 prewarm、真实 POSIX/Windows subprocess smoke、README、CI workflow
- Issue 142/151/175/177/178、Topic 8/9（plan §1.3 明确排除）

## 10. Reviewer 最终裁决

- **Material findings**：`0` 个（原 `R12-S1-CR-F01` 已正确修复并闭合）。
- **Confirmed no-finding**：`1` 个（Value-object equality）。
- **Mechanical gates**：全部通过（66 tests、catalog 90.22%、environment 94.42%、full pyright zero、scoped Ruff zero、full Ruff 144/SHA/cmp 零差异、`git diff --check` 通过、全部 source scans 通过）。
- **Adversarial checks**：全部通过（parser 无绕过、写后 state 一致、value-object no-fix 保持、Windows/catalog contract 不变、无 secret 泄漏、无 compat/fallback/shim/rollback 新协议）。
- **S1 review gate 裁决**：`PASS`。R12-S1-CR-F01 已正确修复闭合。S1 fixed cumulative tree 无 blocking finding。可以进入 Controller adjudication，裁决后进入 S2。
- **下一入口**：Controller adjudication。Controller 收齐两路 re-review 后统一裁决；未 PASS 不进入 S2。

## 11. Artifact metadata

- 本文件路径：`docs/reviews/wu-semantic-ownership-01-r12-s1-code-rereview-ds.md`
- 不修改 code/tests/plan/control/既有 artifacts，不 stage/commit。
- 未进入 S2/S3。
