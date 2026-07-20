# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN4-RW-RF01 One-test Code Rereview — AgentDS Second-Pass Immutable Re-Review

## Gate identity and verdict

- Timestamp：`2026-07-20T10:09:38+0800`。
- Umbrella：`WU-SEMANTIC-OWNERSHIP-01`；本 gate 是既有 `AR-F07 WIN4-RW-RF01` one-test code-review 最终第二路完整 immutable re-review，不是新 WU。
- Reviewer：`AgentDS`。
- Mechanical base：`39926eb85aa25441f5209a128a3c971f451b5b25`。
- Code path：`tests/cli/test_upload_filings_from_command.py`。
- Exact function：`test_windows_generated_script_runs_real_cli_into_temp_storage`。
- 本 artifact 是 re-review 唯一新增文件，不改任何现有代码、test、product、README、plan、control 或既有 review artifact；不 stage、不 commit、不 push、不 dispatch。

**Verdict：`PASS / MATERIAL_FINDING=0 / NEW_FINDING=0 / BACKFLOW_FINDING=0 / BLOCKER=0 / OPEN=0 / READY_FOR_CONTROLLER_ADJUDICATION`。**

## Frozen identity proof

| Frozen item | Expected SHA-256 | Fresh verified |
| --- | --- | --- |
| Mechanical base commit | `39926eb85aa25441f5209a128a3c971f451b5b25` | `git rev-parse HEAD` → exact match ✓ |
| Binary/full-index code diff | `fcecb15cc3f09707077a6cf016ac28b960fb13013f1dcda92d4db092734f2169` | `LC_ALL=C git diff --binary --full-index --no-ext-diff --no-renames 39926eb85 -- tests/cli/test_upload_filings_from_command.py \| shasum -a 256` → exact match ✓ |
| Implementation artifact | `f9b36d4b58d4a81c845058790f6d99d8b7994b8a35410a79242aed606163f42e` | `shasum -a 256 docs/reviews/...implementation-codex.md` → exact match ✓ |
| Zero-change fix artifact | `edb947fdb097a21cc330d8cb3c92b0a69bd86dd4c073df6e8ebb6ba45e2fd4cf` | `shasum -a 256 docs/reviews/...code-review-fix-codex.md` → exact match ✓ |
| Controller fix validation | `38035a289e90a0aebd3e4dbd68774f972ae4c628ebdf5a23ce2c30b95675ac0f` | `shasum -a 256 docs/reviews/...code-review-fix-controller-validation.md` → exact match ✓ |
| Test file 完整内容 | `3827b569fea759e6feaaba657b27a41a3303bde787d784e52677dd49a69ad110` | `python3 -c "import hashlib,pathlib;..."` → exact match ✓ |
| First-pass DS review | `c60a8db64800f37a26fdb1a384b5f980ad8d434b1a7ca765cc414a4ddbb78b4d` | `shasum -a 256` → exact match ✓ |
| First-pass MiMo review | `0fbf17bb730ec1b3cb4cb1093135acd3516de342b5e4a38caf312cefdb84d7b2` | `shasum -a 256` → exact match ✓ |
| Controller first-pass adjudication | `1dceeeb2b9d58c3e0bf1a700c19ca7f7dbfb26f1fcc2c5a6e6ab9844fdd4f569` | `shasum -a 256` → exact match ✓ |
| Controller implementation validation | `382fbf2f4a16ee1a3492b5d712212372820e2599b0595ab72b6ab6a38378e672` | `shasum -a 256` → exact match ✓ |
| Accepted plan | `571ca834a515620283447a6c2166fc7bbd5dcf9393b685457a0ee7e959dc7ff2` | `shasum -a 256` → exact match ✓ |
| Control doc（当前 snap） | `aa10713b250fe92401f55729e83e5530d8f65e43f2ba0a3a86b62f30647ce9b6` | `shasum -a 256` → exact match ✓ |

## Diff identity：plain vs binary/full-index

冻结 identity 命令：

```bash
LC_ALL=C git diff --binary --full-index --no-ext-diff --no-renames \
  39926eb85aa25441f5209a128a3c971f451b5b25 -- \
  tests/cli/test_upload_filings_from_command.py | shasum -a 256
```

结果为 `fcecb15cc3f09707077a6cf016ac28b960fb13013f1dcda92d4db092734f2169`。

对照 plain 命令（无 `--binary --full-index --no-ext-diff --no-renames`）：

```bash
LC_ALL=C git diff 39926eb85aa25441f5209a128a3c971f451b5b25 -- \
  tests/cli/test_upload_filings_from_command.py | shasum -a 256
```

结果为 `f4dd51eb87776d7ee63758f9e19dd8e627cf30aa7f323fe4694da809f463a2f7`。

`f4dd...` 与 `fcecb15c...f2169` 不同是因为 plain diff 的 index 行使用缩写 object id 而非 full hex index。两个摘要对应不同命令输入，不是同一 identity 的 mismatch，不是代码漂移，也不是 finding。**该误区已在 first-pass Controller adjudication 中关闭，零回流。**

## Scope

- **Mode**：exact-function immutable code re-review（基于冻结 diff identity 的完整从头审查）。
- **Frozen identity**：mechanical base `39926eb85` = current HEAD；working tree diff 是唯一实现变更。
- **Diff 统计**：单 hunk（`@@ -1000,10 +1000,21 @@`），目标函数 `test_windows_generated_script_runs_real_cli_into_temp_storage` 内 snapshot assertion block；14 insertions / 3 deletions；零 import、零 helper、零其它 test node、零 product/README/design/workflow 变更。
- **变更内容**：
  1. 删除 `assert snapshot.primary_filename == source_path.name`（消除 primary/raw 语义合并）。
  2. 删除旧 `assert snapshot.primary_filename in tuple(...)`（不精确的 membership）。
  3. 新增 primary exact-one membership：按 `descriptor.name == snapshot.primary_filename` 过滤，断言 `len == 1`。
  4. 新增 raw-source exact-one membership：按 `descriptor.name == source_path.name` 过滤，断言 `len == 1`。
  5. 新增 raw-source sha256 非空 guard + 精确等于 fixture bytes SHA-256。
- **Excluded scope**：本文件内其它所有 test node、helper、module constant、oracle JSON block、import 区均不含变更；`dayu/` product、其它 tests、全部 README/design/control、`.github/workflows/` 均零 diff。

## Complete adversarial re-review（从零七维度）

### Dimension 1 — code diff identity 与 owner semantics 是否与 first pass 不一致

AgentDS 独立重新计算 binary/full-index diff SHA-256，结果仍为 `fcecb15cc3f09707077a6cf016ac28b960fb13013f1dcda92d4db092734f2169`。目标 test 文件内容 SHA-256 仍为 `3827b569fea759e6feaaba657b27a41a3303bde787d784e52677dd49a69ad110`。diff hunk 仍在 exact function `test_windows_generated_script_runs_real_cli_into_temp_storage` 的 snapshot assertion block 内，14 insertions / 3 deletions layout、变量命名、断言顺序与 first pass 完全相同。

相对 mechanical base 的 tracked changed paths 为两条：

1. `docs/host/issues-implementation-control.md`：仅 status text 更新（gate 状态描述、next entry point 字段），零 code/product/test 变更。
2. `tests/cli/test_upload_filings_from_command.py`：如上 exact function single hunk。

`dayu/` product、其它 test 文件、全部 README/design/workflow 相对 base 零 diff。staged tree 为空，`git diff --check` 通过。

**结论：code diff identity 零漂移，owner semantics 与 first pass 完全一致。PASS。**

### Dimension 2 — primary exact-name 与 raw-source exact name/hash 独立性（从零复判）

**Primary side**（working tree lines 1003–1008）：

```python
primary_descriptors = tuple(
    descriptor
    for descriptor in descriptors
    if descriptor.name == snapshot.primary_filename
)
assert len(primary_descriptors) == 1
```

- `snapshot.primary_filename` 类型为 `str`（Fins contract `SourceSnapshotProtocol.primary_filename -> str`，line 170），不是 `Optional[str]`，不会出现 `descriptor.name == None` 的意外 True。
- Fins `_parse_snapshot_files`（`_fs_source_snapshot.py` lines 984–990）从 persisted meta 的 `primary_document` 读取、`_normalize_filename` 规范化、并确保精确命中一个 descriptor name 后才返回。`primary_filename` 是强保证 exact-one 的 Fins-owned 事实。
- 过滤条件使用 exact `==`，零 loose parsing、零 suffix stripping、零 normalization。
- 断言只要求恰好命中一个 descriptor，不要求 primary 等于 raw source。
- 不读取 `primary_descriptor.sha256` 或其它 field —— 按 corrected plan 设计，Fins 拥有 primary 完整性保证。

**Raw-source side**（working tree lines 1009–1017）：

```python
raw_source_descriptors = tuple(
    descriptor
    for descriptor in descriptors
    if descriptor.name == source_path.name
)
assert len(raw_source_descriptors) == 1
raw_source_descriptor = raw_source_descriptors[0]
assert raw_source_descriptor.sha256 is not None
assert raw_source_descriptor.sha256 == hashlib.sha256(fixture).hexdigest()
```

- `SourceSnapshotFileDescriptor.sha256` 类型为 `Optional[str]`（Fins contract line 65），`is not None` guard 是必要的 fail-closed 窄化。
- 两段 tuple comprehension 是独立 comprehension，独立 `len == 1` 断言，独立变量作用域。
- 若 primary 和 raw 命中同一 descriptor（即 Fins 选择 raw source 为 primary），两边各自 `len == 1` 且指向同一对象，sha256 检查仍然正确。
- 若 primary 和 raw 命中不同 descriptor（Fins 合法选择 Docling JSON 为 primary，raw HTML 仍被发布），两边各自 `len == 1`，raw sha256 独立验证。

**Fail-closed 验证表**：

| 输入条件 | primary 断言 | raw-source 断言 | 结果 |
| --- | --- | --- | --- |
| `primary_filename` 不匹配任何 descriptor | `len=0` → fail | 独立 | 正确 fail |
| `source_path.name` 不匹配任何 descriptor | 独立 | `len=0` → fail | 正确 fail |
| 同一 name 出现两次 | `len=2` → fail | `len=2` → fail | 正确 fail（两边各自 fail） |
| `sha256` 为 `None` | 独立 | `is not None` → fail | 正确 fail |
| `sha256` 与 fixture 不一致 | 独立 | 等式 fail | 正确 fail |
| primary==raw（同一 descriptor） | `len=1` | `len=1`，sha256 通过 | 正确 pass |
| primary≠raw（不同 descriptor） | `len=1` | `len=1`，sha256 通过 | 正确 pass |

**结论：primary 与 raw-source 语义完全独立，各自 exact-one 断言 fail-closed，sha256 链式 fail-closed。PASS。**

### Dimension 3 — duplicate descriptor names、zero hit、primary≠raw 合法反例 与 regressions

- **Duplicate descriptor names**：若 Fins storage 对同一 snapshot 发布两个 `name` 相同的 descriptor，至少一侧 `len > 1`，断言失败。两次 `len == 1` 独立提供防御纵深。
- **Zero hit**：`primary_filename` 或 `source_path.name` 不在任何 descriptor 中时，对应 tuple 为空，`len == 0`，断言失败。无默认值、无 fallback、无 `in`-only check。
- **primary≠raw 合法反例**：Fins 合法选择 Docling JSON 为 primary 且 raw HTML 仍被发布时，旧断言 `assert snapshot.primary_filename == source_path.name` 在此反例下必然失败（这是本 WU AR-F07 的原始动机）。新断言不表达此关系——两边各自 exact-one 通过，raw sha256 验证通过。正确的语义分离。
- **primary==raw 仍然合法**：两边各自 exact-one 通过，无冲突。
- **旧 membership 断言退化**：旧断言 `assert snapshot.primary_filename in tuple(descriptor.name for descriptor in descriptors)` 对 zero hit 返回 `False`（fail），但对 duplicate name 不提供防御（duplicate 时 `in` 仍为 True）。新 `len == 1` 断言同时覆盖 zero 和 duplicate，是 strictly stronger contract。

**结论：所有边界情况均正确 fail-closed 或 pass，回归风险为零，contract 严格强化。PASS。**

### Dimension 4 — test 越权选择 Fins primary、Docling/private meta/rglob business oracle 硬编码

逐项扫描 diff 与上下文：

| 扫描项 | diff 命中 | 上下文命中 |
| --- | --- | --- |
| test 选择 Fins primary（如 `primary_filename = source_path.name` 或 `expected_primary =`） | 0 | 0（新断言只读 `snapshot.primary_filename`，不赋值、不覆盖、不选择） |
| Docling hardcode（`docling`、`_docling.json`、`DOCLING_FILE_SUFFIX`、`.json` suffix oracle） | 0 | 0 |
| private meta（`meta.json` 读取、`_core`、`_private`、`materialize_files=True`、`get_source(`） | 0 | 0（snapshot 用 `materialize_files=False`，不物化文件；Windows test 函数内无 `meta.json`、`get_source(` 或 `source_meta` 访问） |
| rglob business oracle | 0 | 既有的 `source_artifacts = tuple(path for path in (storage / "portfolio").rglob("*") if path.is_file())` 只做物理文件 existence check（`assert source_artifacts`），不按文件名/后缀/路径选择 primary 或推导业务事实 |
| `hasattr`/`getattr` fallback | 0 | 0 |
| loose parsing / 二次格式化 | 0 | 0 |

新断言只消费 `SourceSnapshotFileDescriptor` 的两个 public field：`name: str` 和 `sha256: Optional[str]`。两者均由 Fins storage 作为 public contract 提供（`repository_protocols.py` lines 60、65），不穿透到 storage 内部实现。

**结论：test 未越权选择 Fins primary，无 Docling/private meta/rglob business oracle 硬编码。PASS。**

### Dimension 5 — exact function-block allowlist、无 import/helper/schema/oracle/README/workflow/product 扩张

diff 单 hunk 验证：

```text
@@ -1000,10 +1000,21 @@ def test_windows_generated_script_runs_real_cli_into_temp_storage(tmp_path: Path
```

- diff hunk 落在 exact function `test_windows_generated_script_runs_real_cli_into_temp_storage` 内。
- diff 不含任何 `import` / `from` 语句（`hashlib` 已在 HEAD committed 版本中存在，本次变更无需新增）。
- diff 不含任何 `def`（新 helper）、`class`、新 module-level constant。
- diff 不含 `cli-grammar-oracle.json` key 集合变更（既有六 key：`test_node`、`result`、`generated_script_sha256`、`source_artifact_count`、`cmd_invocation`、`company_name_supplied`，不变）。
- diff 不含 `dayu/` product、其它 test 文件、README、design、workflow 任何变更。
- staged tree empty；working tree 只含 target test file 与 control doc（后者只有 status text 更新，不在本次 review scope）。

**结论：exact function-block allowlist 严格遵守，零 scope creep。PASS。**

### Dimension 6 — 测试/pyright/Ruff evidence 是否足够且真实 Windows 仍 pending

AgentDS fresh 独立验证（所有 Python 命令在 `source .venv/bin/activate` 后执行）：

| Validation | AgentDS fresh result |
| --- | --- |
| `pytest tests/cli/test_upload_filings_from_command.py -q` | `20 passed, 2 skipped, 3 warnings in 11.97s` |
| Windows exact node | `1 skipped`（`requires real cmd.exe`；macOS 平台） |
| 三个 public repository owner nodes | `3 passed, 3 warnings in 1.06s` |
| `python -m pyright tests/cli/test_upload_filings_from_command.py` | `0 errors, 0 warnings, 0 informations` |
| `python -m ruff check tests/cli/test_upload_filings_from_command.py` | `All checks passed!` |
| `git diff --check` | PASS / 无输出 |
| `git diff --cached --name-only` | 空；staged tree empty |
| `dayu/` product diff | 零 diff |
| 新增 import scan | `0` matches |
| 新增 def/class scan | `0` matches |

- 三个 warning 均来自已安装 `edgar` package 的 deprecated imports（`edgar.files.htmltools` 等），不在本次变更范围内。
- macOS 不能执行真实 `cmd.exe`，Windows exact node 的 `skip` 是正确平台行为，不是 test failure。
- 真实 Windows evidence（fresh R11/R12 runs）仍为 `PENDING`——这是 corrected plan §13.8 的唯一 release closure gate，不是本次 code review 的 finding 或 waiver。
- Zero-change fix gate 已证明 code/test 零改动且所有检查保持通过；re-review 期间 code 无任何变更，所有验证值不变。

**结论：本地 evidence 一致且足够；真实 Windows 仍 pending，分类正确，不作为 code review finding。PASS。**

### Dimension 7 — 安全边界、trusted-local secret 裁决、Tool Trace/audit 明文禁止、deferred Issue 范围不漂移

- 新断言不含任何 API key / secret / token 字面量或环境变量读取。
- `cli-grammar-oracle.json` 六键字段均不包含 secrets、credentials 或 Tool Trace 内容。
- `_WINDOWS_REAL_SMOKE_COMPANY_NAME = "Apple Inc."` 是公开公司名测试常量，不是 secret。
- 不读取、派生或扫描 GitHub Secrets / configured production secrets / run-specific canary。
- Tool Trace / audit 明文不进入断言或 oracle artifact。
- deferred Issues（142/151/175/177/178）、Web/WeChat/render、setx redesign、统一 authorization/secret management、Fins generic diagnostic schema 全部保持 deferred/forbidden，零实现、零预埋。

**结论：安全边界完整；trusted-local secret 裁决不变；deferred Issue 范围零漂移。PASS。**

### Dimension 8 — correctness/stability/maintainability、semantic ownership drift、adversarial failure pass

#### 8a. Semantic ownership 判定

| 事实 | Owner | Test 行为 | 是否越权 |
| --- | --- | --- | --- |
| primary_filename 的选择 | Fins storage（`_parse_snapshot_files` lines 984–990） | 只验证 `primary_filename` 在 public `descriptors` 中恰好命中一个 | 否 — test 不选择、不覆盖、不重定义 primary |
| primary file 完整性 | Fins storage（元数据和内容一致性） | 只验证 exact-one membership | 否 — 不重复验证 primary sha256（Fins contract 内部保证） |
| raw source 的存储 name | Fins storage（上传时保留原始 basename） | 验证 `source_path.name` 在 descriptors 中恰好命中一个 | 否 — 验证 public contract 履行 |
| raw source 的字节完整性 | Fins storage + test oracle | `is not None` guard + `hashlib.sha256(fixture).hexdigest()` exact match | 否 — test 作为 consumer 验证存储结果 |
| company name | Fins storage（`FsCompanyMetaRepository`） | 只读取 `company_meta.company_name` 并比较 | 否 — 不写入、不派生 |
| 脚本 company-name oracle | Test oracle（`_assert_single_windows_upload_company_name`） | 独立验证生成脚本中业务命令的 `--company-name` | 否 — 不依赖 Fins 存储 |

每个事实有唯一 owner；test 不越权产生、解释或持久化任何业务语义。旧断言 `assert snapshot.primary_filename == source_path.name` 是典型的 semantic ownership drift——test 越权强制 Fins 层 primary == raw source。新断言正确收敛回 Fins contract boundary。

#### 8b. Adversarial failure pass

AgentDS 逐项验证以下 adversarial 场景：

| 场景 | 分析 | 结论 |
| --- | --- | --- |
| `snapshot.files` 返回空 tuple | `assert descriptors` 对空 tuple 为 False → fail | fail-closed |
| `snapshot.primary_filename` 为 `""` 且恰好有一个 descriptor 名为 `""` | `descriptor.name == ""` 匹配 → `len=1` → pass。但 Fins `_parse_snapshot_files`（line 985–986）拒绝空 `primary_document`；`_normalize_filename` 拒绝空名 → 此场景不可达 | 不可达 |
| `source_path.name` 被 Fins 规范化后与原始不同 | `raw_source_descriptors` 的 `len=0` → fail。这是对 Fins 公共 contract（保留原始 basename）的正确验证 | fail-closed |
| `hashlib.sha256(fixture).hexdigest()` 与 Fins 存储的 sha256 因上传时字节转换而不匹配 | 等式 fail → fail。Fins 应 byte-for-byte 保留上传内容 | fail-closed（contract enforcement） |
| 脚本生成成功但执行失败（exit ≠ 0） | `assert execution.returncode == 0, execution.stderr` → fail | fail-closed |
| Company meta 不存在或字段为空 | `FsCompanyMetaRepository` 抛出或 `assert company_meta.ticker == "AAPL"` → fail | fail-closed |
| `_assert_single_windows_upload_company_name` oracle 本身有 bug | Oracle 由独立 test `test_windows_upload_company_oracle_fails_closed_on_non_business_evidence` 和 `test_windows_renderer_round_trips_fixed_argument_oracles` 验证 | defense-in-depth |
| `len == 0` for raw-source（source_path.name 不存在于任何 descriptor） | `assert len(raw_source_descriptors) == 1` → fail | fail-closed |
| `len == 0` for primary | `assert len(primary_descriptors) == 1` → fail | fail-closed |
| Duplicate name in descriptors for either primary or raw | `len >= 2` → fail for the affected side | fail-closed |
| `sha256 is None` for raw descriptor | `assert raw_source_descriptor.sha256 is not None` → fail | fail-closed |
| 并发写入 portfolio（多进程） | 本 test 为单进程 subprocess，无并发 | 不适用 |

所有 adversarial 场景均 fail-closed 或不可达。

#### 8c. Stability 与 maintainability

- 新断言只用 tuple comprehension + `len == 1`，无复杂控制流、无嵌套异常处理、无外部依赖引入。
- 如果 Fins 未来改变 primary 选择策略（比如不再选 Docling JSON），test 仍然 pass（只要 primary_filename 命中一个 descriptor）。
- 如果 Fins 未来改变 raw source 命名规则，test 正确 fail（contract regression detection）。
- 无 observable 副作用：不修改 `descriptors`、不调用 mutating API、不在 `with` block 外持有 snapshot 引用（snapshot 在 `with` 退出后正确释放）。
- `cli-grammar-oracle.json` 在断言全部通过后才写入（断言失败 → 提前退出 → 不写入 `"result": "passed"` → 无假阳性 artifact）。

**结论：correctness 无 defect；stability 充分；maintainability 无退化；semantic ownership 零漂移；adversarial failure pass 全覆盖。PASS。**

## POSIX assertion asymmetry：仍为 non-finding / no-action

`test_posix_generated_script_runs_real_cli_into_temp_storage`（line 792）不包含 snapshot/descriptor 断言，只检查 generation.returncode 和 execution.returncode。这是 pre-existing asymmetry，不在本次 diff 范围内，不影响 Windows owner contract。第一路 AgentMiMo 记录为 `PRE_EXISTING / OUT_OF_SCOPE / NON_FINDING / NO_ACTION`，Controller first-pass adjudication 接受此分类，zero-change fix gate 不将其纳入 fix 或 residual ledger。

AgentDS 重新确认：POSIX test 无任何 snapshot/descriptor assertion，此事实与 first pass 一致；代码未发生任何变更使该 asymmetry 进入 scope。**POSIX asymmetry 仍为 non-finding / no-action。**

## Plain diff hash 误区：已关闭且不可回流

First-pass AgentMiMo 初稿以 plain `git diff | sha256` 得到 `f4dd51eb...a2f7`，误写成冻结 identity mismatch。Controller 指出冻结 identity 必须使用 `LC_ALL=C git diff --binary --full-index --no-ext-diff --no-renames`；same-task follow-up 独立复算并得到 exact `fcecb15c...f2169`，final artifact 已删除假 residual。

AgentDS 重新计算两组值：
- Plain：`f4dd51eb87776d7ee63758f9e19dd8e627cf30aa7f323fe4694da809f463a2f7`
- Binary/full-index：`fcecb15cc3f09707077a6cf016ac28b960fb13013f1dcda92d4db092734f2169`

差异来自 plain diff index 行使用缩写 object id，不是代码漂移、identity mismatch 或 finding。**该误区已在 first-pass Controller adjudication 中关闭，零回流。**

## 唯一 residual：真实 Windows pending

真实 Windows evidence 仍为 `PENDING`。macOS 无法执行 `cmd.exe`，Windows exact node 显示 `1 skipped`。

- 这不是 code finding，不是 waiver，不是 blocker。
- Owner/destination 唯一是 Controller 在 accepted implementation 与 aggregate gates 后执行 fresh R11 与 R12（含 embedded R11），按 accepted plan 验证两个独立 descriptor facts 与 same-run evidence。
- 若 fresh R11/R12 失败，必须回到 Controller diagnostic-first owner 裁决；不得恢复 primary==raw、硬编码 Docling expected primary、读取 private meta/path 或修改 Fins contract 迁就测试。

此 residual 由 Controller 正确分类为 `COVERED_BY_LATER_APPROVED_REMOTE_VALIDATION`。

## Full Ruff baseline

Entry full Ruff 为 `142` 项，按 `(filename, location row/column, code, message, fix-applicability)` 排序后的 canonical JSON SHA-256 为 `a11d2c84c95ddb84e8313316afb98ed81124bf18cf98a2beecb17d3d2a8ac0c9`。zero-change fix gate 已证明五元组集合与 digest 不变。本 re-review 无新增、扩散、移动或顺手清理。

## Findings

未发现实质性问题。

- Accepted code finding：`0`（inherited from first pass）
- New/backflow finding：`0`
- Blocker/open/design contradiction：`0`
- POSIX assertion asymmetry：`PRE_EXISTING / OUT_OF_SCOPE / NON_FINDING / NO_ACTION`（不变）
- Plain diff hash 误区：`CLOSED / NON_BACKFLOW`（不变）

## Open Questions

无。

## Residual Risk

- **真实 Windows evidence 仍 pending**：本 test node 在 macOS 上因 `os.name != "nt"` 被 `pytest.mark.skipif` 正确跳过。fresh R11/R12 `windows-latest` runs 是 corrected plan §13.8 的唯一 release closure gate。此 residual 已由 Controller 正确分类为 `COVERED_BY_LATER_APPROVED_REMOTE_VALIDATION`，不是本次 code review 的 finding 或 waiver。
- **Full Ruff baseline 142 项**：pre-existing immutable baseline，不在本次 diff 范围内；zero-change fix gate 已独立证明五元组集合与 digest 不变。

## Full ledger（zero-change fix 后终态）

| Category | Count | Status |
| --- | ---: | --- |
| Accepted code finding | `0` | CLOSED |
| New finding | `0` | CLOSED |
| Backflow finding | `0` | CLOSED |
| Blocker | `0` | CLOSED |
| Open/design contradiction | `0` | CLOSED |
| POSIX asymmetry | N/A | NON-FINDING / NO-ACTION |
| Plain diff hash 误区 | N/A | CLOSED / NON-BACKFLOW |
| Residual requiring later evidence | `1` | R11/R12 / Controller-owned |

## Verification ledger（AgentDS fresh）

| 项目 | 值 | 验证方式 |
| --- | --- | --- |
| Mechanical base | `39926eb85aa25441f5209a128a3c971f451b5b25` | `git rev-parse HEAD` |
| Binary/full-index diff SHA-256 | `fcecb15cc3f09707077a6cf016ac28b960fb13013f1dcda92d4db092734f2169` | `LC_ALL=C git diff --binary --full-index --no-ext-diff --no-renames 39926eb85 -- tests/cli/test_upload_filings_from_command.py \| shasum -a 256` |
| Plain diff SHA-256（对照） | `f4dd51eb87776d7ee63758f9e19dd8e627cf30aa7f323fe4694da809f463a2f7` | `LC_ALL=C git diff 39926eb85 -- tests/cli/test_upload_filings_from_command.py \| shasum -a 256` |
| Implementation artifact | `f9b36d4b58d4a81c845058790f6d99d8b7994b8a35410a79242aed606163f42e` | `shasum -a 256` |
| Zero-change fix artifact | `edb947fdb097a21cc330d8cb3c92b0a69bd86dd4c073df6e8ebb6ba45e2fd4cf` | `shasum -a 256` |
| Controller fix validation | `38035a289e90a0aebd3e4dbd68774f972ae4c628ebdf5a23ce2c30b95675ac0f` | `shasum -a 256` |
| First-pass DS review | `c60a8db64800f37a26fdb1a384b5f980ad8d434b1a7ca765cc414a4ddbb78b4d` | `shasum -a 256` |
| First-pass MiMo review | `0fbf17bb730ec1b3cb4cb1093135acd3516de342b5e4a38caf312cefdb84d7b2` | `shasum -a 256` |
| Controller first-pass adjudication | `1dceeeb2b9d58c3e0bf1a700c19ca7f7dbfb26f1fcc2c5a6e6ab9844fdd4f569` | `shasum -a 256` |
| Controller implementation validation | `382fbf2f4a16ee1a3492b5d712212372820e2599b0595ab72b6ab6a38378e672` | `shasum -a 256` |
| Accepted plan | `571ca834a515620283447a6c2166fc7bbd5dcf9393b685457a0ee7e959dc7ff2` | `shasum -a 256` |
| Control doc | `aa10713b250fe92401f55729e83e5530d8f65e43f2ba0a3a86b62f30647ce9b6` | `shasum -a 256` |
| Test file 完整 SHA-256 | `3827b569fea759e6feaaba657b27a41a3303bde787d784e52677dd49a69ad110` | `python3 -c "import hashlib,pathlib; print(hashlib.sha256(pathlib.Path('tests/cli/test_upload_filings_from_command.py').read_bytes()).hexdigest())"` |
| Target test file fresh | `20 passed, 2 skipped, 3 warnings in 11.97s` | `pytest tests/cli/test_upload_filings_from_command.py -q` |
| Owner nodes fresh | `3 passed, 3 warnings in 1.06s` | `pytest tests/fins/...owner... -q` |
| Target file pyright | `0 errors, 0 warnings, 0 informations` | `pyright tests/cli/test_upload_filings_from_command.py` |
| Target file Ruff | `All checks passed!` | `ruff check tests/cli/test_upload_filings_from_command.py` |
| `git diff --check` | PASS | `git diff --check` |
| Staged tree | empty | `git diff --cached --name-only` |
| `dayu/` product diff | 零 diff | `git diff --name-only 39926eb85 -- dayu/` |

## Correct next gate

```
Controller adjudication（本 re-review + MiMo concurrent re-review）
  → exact accepted implementation commit
  → aggregate gate
```

不得直接 remote、PR review、dispatch 或 final closeout。

本 re-review 返回 `PASS / MATERIAL_FINDING=0 / NEW_FINDING=0 / BACKFLOW=0 / BLOCKER=0 / OPEN=0`。re-review 链关闭后，授权 next gate 为 Controller adjudication，随后形成 exact accepted implementation commit，再进入 aggregate gate。

---

AgentDS 停止。不改任何现有文件，不 stage/commit/push/dispatch，不进入 fix/further re-review。
