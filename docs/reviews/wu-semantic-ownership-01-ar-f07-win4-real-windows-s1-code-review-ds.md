# Code Review — WU-SEMANTIC-OWNERSHIP-01 AR-F07 WIN4-RW-S1（AgentDS 第二路）

## Scope

- Mode: current changes（deepreview，immutable payload）
- Umbrella: `WU-SEMANTIC-OWNERSHIP-01`
- Continuation: `AR-F07` WIN4 real-Windows S1
- Branch: `phaseflow/host-issues-control`
- Base: S1 authorization commit `8fafe9bad4828c83fa6cf80a1dc2199fe78472d9`
- Output file: `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-s1-code-review-ds.md`
- Included scope: `tests/cli/test_upload_filings_from_command.py`（working tree unstaged diff vs HEAD `8fafe9ba`）
- Immutable payload:
  - File: `tests/cli/test_upload_filings_from_command.py`
  - Content SHA-256: `71855b783ae1191ed764c69c938f2ca29d0c51ae575f501a431e33615ebb4d3d` ✓（已核验）
  - Git tree entry: `8fafe9bad4828c83fa6cf80a1dc2199fe78472d9`
- Committed S1 baseline: `e34edfa3`（pre-execution oracle + company-name argv）— 已由 AgentDS 第一路 review 通过
- Unstaged S1 extension diff stat: `1 file changed, 44 insertions(+), 3 deletions(-)`
- Excluded scope:
  - `docs/host/issues-implementation-control.md`（control-doc 状态更新，非 S1 ownership）
  - 已 commit 的 S1 oracle/argv 部分（已由第一路 DS review 覆盖）
  - POSIX real workflow test（`test_posix_generated_script_runs_real_cli_into_temp_storage`，非 S1 变更）
  - WIN4-S2 / WIN4-S3（未实施）
  - Production code（`dayu/` — S1 零 diff）
- Parallel review coverage: 无（单文件附加变更，主 reviewer 全量走读）
- Pre-read artifacts:
  - `AGENTS.md`（项目约束）
  - Accepted fixed plan（`docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md` §4 WIN4-S1）
  - Accepted amended plan（commit `cb2785d9`）
  - S1 postcommit authorization（commit `8fafe9ba`）
  - AgentCodex implementation artifact（`docs/reviews/wu-semantic-ownership-01-ar-f07-win4-s1-implementation-codex.md`）
  - Controller validation（`docs/reviews/wu-semantic-ownership-01-ar-f07-win4-s1-controller-validation.md`）
  - AgentDS 第一路 code review（`docs/reviews/wu-semantic-ownership-01-ar-f07-win4-s1-code-review-ds.md`）
  - Direct Fins public repository/snapshot contracts（`dayu/fins/storage/repository_protocols.py`、`fs_source_document_repository.py`、`fs_company_meta_repository.py`、`_fs_source_snapshot.py`、`dayu/fins/domain/enums.py`）

## Review dimensions and trace matrix

本 review 按任务指定的六维度逐项走读，每条结论均标注直接证据位置（文件:行号）。

### 维度 1: Display success dependency 彻底删除

**审查目标**：确认 `"Fins result" in execution.stdout` 已完全移除，未用 stderr/stdout/word/parser 替代；exit 与 storage facts 顺序正确。

**直接证据**：

| 检查项 | 旧代码（已删除） | 新代码（行号） | 判断 |
|---|---|---|---|
| stdout 依赖 | `assert "Fins result" in execution.stdout` | 已删除（diff 删除行） | ✓ 彻底删除 |
| stderr 替代 | — | `assert execution.returncode == 0, execution.stderr`（行 981）— stderr 仅用于断言诊断消息，不作为成功判断依据 | ✓ 非替代 |
| stdout 替代 | — | 零 stdout 内容断言 | ✓ 非替代 |
| word/count 替代 | — | 零 `str.find` / `in` / `.count()` 在 S1 unstaged 新增行 | ✓ 非替代 |
| parser 替代 | — | 零 `shlex` / `json.loads(stdout)` / regex 解析执行输出 | ✓ 非替代 |
| exit→storage 顺序 | — | `execution.returncode == 0`（行 981）→ `FsCompanyMetaRepository`（行 982）→ `FsSourceDocumentRepository`（行 985）→ snapshot（行 992）→ rglob（行 1007） | ✓ exit 在先，storage 在后 |

**逐路径详细追踪**：

1. **行 981**：`assert execution.returncode == 0, execution.stderr`
   - `execution.stderr` 只在断言失败时作为诊断消息展示，不作为真值判断。断言本身只依赖 `returncode`。
   - `subprocess.run` 的 `capture_output=True`（行 975）保留 stdout/stderr 捕获，但不再消费其内容作业务判断。捕获本身无害（甚至有助于失败诊断），且非 S1 新增。

2. **行 982–984**：`FsCompanyMetaRepository(storage).get_company_meta("AAPL")` → `company_meta.ticker` / `company_meta.company_name`
   - 构造参数 `storage` 与 CLI generation 的 `--base str(storage)` 同一 `artifact_directory`（行 934, 944）。
   - `get_company_meta` contract（`repository_protocols.py:315-330`）：从 published tree 读取，`FileNotFoundError` 时抛出。若上传未持久化，此处 fail closed。

3. **行 985–991**：`FsSourceDocumentRepository(storage).list_source_document_ids("AAPL", SourceKind.FILING)` → `len(document_ids) == 1`
   - `list_source_document_ids` contract（`repository_protocols.py:656-671`）：从 published tree 按 `source_kind` 列出已发布文档 ID。
   - 断言 `len == 1`：防止零文档（上传静默失败）或多文档（意外重复上传）。

4. **行 992–1006**：`read_source_snapshot("AAPL", document_id, SourceKind.FILING, materialize_files=False)` → context manager 内逐字段断言
   - `materialize_files=False`：light snapshot，不复制文件内容到临时树。只读取 meta、descriptor、provenance、revision。不读 raw/private/downloaded artifact 字节。
   - Context manager（`with ... as snapshot:`）确保 `__exit__` → `close()` 释放 publication guard 与临时资源，即使断言失败也执行（`_fs_source_snapshot.py:318-352`）。

5. **行 1007–1010**：`rglob("*")` → `assert source_artifacts`
   - 纯 physical integrity：确认 `storage/portfolio` 下至少存在一个文件。不检查文件名、内容、数量精确值。

**结论**：display success dependency 已彻底删除，未用任何 stdout/stderr/word/parser 替代。exit 码在 storage 读取之前验证，storage 读取使用 typed public repository contracts。**PASS**。

### 维度 2: Public repository 构造/root、ticker/company、唯一 filing id、SourceKind、snapshot with lifecycle、primary/descriptor 断言

**审查目标**：确认 repository 构造正确、断言覆盖完整、在 artifact upload 前执行、不读 raw/private/downloaded artifact。

**直接证据**：

#### 2.1 Repository 构造与 root

```python
# 行 934
storage = artifact_directory
# ...
# 行 944: CLI generation 使用同一 storage
"--base", str(storage),
# 行 982: 验证读取同一 storage
company_meta = FsCompanyMetaRepository(storage).get_company_meta("AAPL")
# 行 985
source_repository = FsSourceDocumentRepository(storage)
```

- `FsCompanyMetaRepository(storage)` — `storage` 是 `Path`，满足 `workspace_root: Path` 类型（`fs_company_meta_repository.py:19-20`）。
- `FsSourceDocumentRepository(storage)` — 同上。
- 两个 repository 使用同一 `storage` root，与 CLI `--base` 参数一致。**✓ 正确**。

#### 2.2 Ticker/company

```python
# 行 983–984
assert company_meta.ticker == "AAPL"
assert company_meta.company_name == _WINDOWS_REAL_SMOKE_COMPANY_NAME
```

- `CompanyMeta` 的 `ticker` 与 `company_name` 属性由 storage owner 从 published `company.json` 反序列化（`document_models.py`）。
- `_WINDOWS_REAL_SMOKE_COMPANY_NAME = "Apple Inc."` — 同一常量用于 generation argv（行 954）、pre-execution oracle（行 970）与 storage 断言（行 984）。单真源，未漂移。**✓ 正确**。

#### 2.3 唯一 filing ID

```python
# 行 986–991
document_ids = source_repository.list_source_document_ids("AAPL", SourceKind.FILING)
assert len(document_ids) == 1
document_id = document_ids[0]
```

- `list_source_document_ids` contract（`repository_protocols.py:656-671`）：从 published tree 按 `source_kind` 返回排序文档 ID 列表。
- `len == 1` 精确约束：本次 create 恰好产生一个 filing。**✓ 正确**。

#### 2.4 SourceKind

```python
# 行 988, 993–995
SourceKind.FILING
# ...
snapshot.source_kind is SourceKind.FILING
```

- `SourceKind.FILING` 作为 `list_source_document_ids` 的过滤参数与 `read_source_snapshot` 的显式 source kind。
- 使用 `is` 标识比较（`SourceKind` 是 `str, Enum`，单例语义）。**✓ 正确**。

#### 2.5 Snapshot with lifecycle

```python
# 行 992–1006
with source_repository.read_source_snapshot(
    "AAPL", document_id, SourceKind.FILING, materialize_files=False,
) as snapshot:
    assert snapshot.ticker == "AAPL"
    assert snapshot.document_id == document_id
    assert snapshot.source_kind is SourceKind.FILING
    descriptors = snapshot.files
    assert descriptors
    assert snapshot.primary_filename == source_path.name
    assert snapshot.primary_filename in tuple(
        descriptor.name for descriptor in descriptors
    )
```

- `read_source_snapshot` contract（`repository_protocols.py:572-598`）：在同一 publication guard 内采集 identity/meta/provenance/revision/files/primary。
- `materialize_files=False`：`_read_source_snapshot`（`_fs_source_snapshot.py:529-542`）走 light path——采集 attempt、验证 descriptor 文件存在性与 regular file 属性、关闭文件描述符、不创建临时树、不复制内容。**不读 raw/private/downloaded artifact 字节。**
- Context manager（`with`）lifecycle：
  - `__enter__`（`_fs_source_snapshot.py:302-316`）：`require_open()` 确认未关闭。
  - `__exit__`（`_fs_source_snapshot.py:318-352`）：调用 `close()` → `_SnapshotResourceState.close()` 释放 publication guard。若有活动异常，close failure 作为 secondary note 附加，不压制主异常。**✓ lifecycle 正确**。

#### 2.6 Primary/descriptor 断言

```python
# 行 998–1006
descriptors = snapshot.files
assert descriptors                                    # 非空
assert snapshot.primary_filename == source_path.name  # 精确匹配 source basename
assert snapshot.primary_filename in tuple(
    descriptor.name for descriptor in descriptors      # primary 命中 files
)
```

- `snapshot.files` 返回 `tuple[SourceSnapshotFileDescriptor, ...]`，按 source meta `files` 数组顺序。
- `snapshot.primary_filename` 来自 persisted meta `primary_document` 字段，由 `_parse_snapshot_files`（`_fs_source_snapshot.py:984-989`）验证精确命中 `files` 数组。
- `source_path.name` = `"2024FY_AAPL_Annual_Report.htm"` — 原始上传文件的 basename。storage owner 在上传时保留此 basename 为 `primary_document`。
- 第三个断言（`primary_filename in descriptor_names`）是冗余但无害的双向校验：确保 storage owner 的 primary 声明与 file descriptor 集合一致。**✓ 正确**。

#### 2.7 断言时序

```
generation.returncode == 0 (行 966)
  → pre-execution oracle (行 967-970)
  → cmd.exe execution (行 971-979)
  → execution.returncode == 0 (行 981)
  → 公共仓储断言 (行 982-1006)    ← 所有 repository/snapshot 断言
  → 物理完整性 rglob (行 1007-1010)
  → oracle artifact 写入 (行 1011-1030)
```

所有 repository 构造与 snapshot 断言均在 `execution.returncode == 0` 之后、oracle artifact 写入之前。**✓ artifact upload 前执行，上传成功后验证**。

**结论**：public repository 构造正确，root/ticker/company/唯一 filing id/SourceKind/snapshot lifecycle/primary/descriptor 断言覆盖完整，不读 raw/private/downloaded artifact。**PASS**。

### 维度 3: rglob/oracle schema 只做 physical integrity，company-name oracle 未漂移

**审查目标**：确认 rglob 不解析业务语义，company-name oracle 未漂移为 stdout/storage/fallback。

**直接证据**：

#### 3.1 rglob physical integrity

```python
# 行 1007–1010
source_artifacts = tuple(
    path for path in (storage / "portfolio").rglob("*") if path.is_file()
)
assert source_artifacts
```

- `rglob("*")`：递归匹配 `storage/portfolio` 下所有路径，仅过滤 `is_file()`。
- 断言 `assert source_artifacts`：仅检查非空（至少一个文件存在），不检查文件数量精确值、文件名、内容或业务类型。
- 与 POSIX 测试（行 843–848）不同——POSIX 测试使用 `rglob("meta.json")` + `json.loads` + `source_kind` 集合断言，读取业务语义。但 POSIX 测试非 S1 变更，不在 scope 内。
- **✓ rglob 仅做 physical integrity，不解析业务语义。**

#### 3.2 Company-name oracle 未漂移

| 检查项 | 位置 | 证据 |
|---|---|---|
| Oracle 函数签名未变 | 行 1086–1090 | `_assert_single_windows_upload_company_name(*, script_path, expected_company_name) -> bool` |
| 输入源未变 | 行 967–970 | 从生成脚本 strict UTF-8 bytes 解析，非 stdout/stderr/storage |
| 预期值来源未变 | 行 59, 954, 970, 984 | 全部来自同一 `_WINDOWS_REAL_SMOKE_COMPANY_NAME = "Apple Inc."` 常量 |
| Oracle 不读 storage | 行 1101 | 只读 `script_path.read_bytes()` |
| Oracle 不读 stdout | — | 零 `execution.stdout` / `capsys` / `captured` 引用 |
| 正/负测试覆盖未变 | 行 499–562 | `test_windows_upload_company_oracle_fails_closed_on_non_business_evidence`：4 正例 + 4 负例，全部通过 |

- Company-name oracle 的语义 owner 仍是 test-local `_assert_single_windows_upload_company_name`。它不从 storage metadata、execution stdout、FMP resolver 或任何 production source 反推公司名。**✓ 未漂移。**

**结论**：rglob 仅做 physical integrity，company-name oracle 未漂移。**PASS**。

### 维度 4: Windows/POSIX 路径、Path/source basename、repository lifecycle 真实 Windows 可执行性

**审查目标**：确认路径构造跨平台正确，repository 生命周期在真实 Windows 可执行，失败 fail closed。

**直接证据**：

#### 4.1 路径构造

```python
# 行 937–938
source_path = source_dir / "2024FY_AAPL_Annual_Report.htm"
source_path.write_bytes(fixture)
```

- `Path / str` 运算符在 Windows 与 POSIX 均产生正确平台路径。
- `source_path.name`（行 1003）在 Windows 返回 `"2024FY_AAPL_Annual_Report.htm"`（不含驱动器号或反斜杠），在 POSIX 同样返回 basename。**✓ 跨平台一致。**

#### 4.2 Repository lifecycle

```python
# 行 985–991
source_repository = FsSourceDocumentRepository(storage)
document_ids = source_repository.list_source_document_ids("AAPL", SourceKind.FILING)
# ...
with source_repository.read_source_snapshot(...) as snapshot:
    ...
# context manager __exit__ 自动 close
```

- `FsSourceDocumentRepository` 构造（`fs_source_document_repository.py:223-251`）调用 `build_fs_repository_set(workspace_root=storage)` → 在 `storage` 下建立 `portfolio/` 等内部目录结构。
- `read_source_snapshot` 内部（`_fs_source_snapshot.py:677-712`）在同一 `_acquire_publication_guard` 内完成采集，使用 `filelock` 保护 published tree 并发读取。Windows 上 `filelock` 通过 `msvcrt` 或 `pywin32` 工作——已在既有 R11 workflow 中验证可行。
- `__exit__` → `close()` → `_SnapshotResourceState.close()`（`_fs_source_snapshot.py:161-183`）：幂等关闭，`light` snapshot（`materialize_files=False`）无临时树需清理，仅设置 `closed=True`。
- **✓ repository lifecycle 在 Windows 可正确执行。**

#### 4.3 Fail closed

| 失败场景 | 行为 | 证据 |
|---|---|---|
| `_windows_test_artifact_directory` 收到不存在的 `DAYU_R11_WINDOWS_ARTIFACT_DIR` | `raise AssertionError(...)` | 行 101–104 |
| `get_company_meta("AAPL")` 无 published meta | `FileNotFoundError`（contract `repository_protocols.py:323`） | 测试因未捕获异常失败 |
| `list_source_document_ids` 返回空列表 | `len(document_ids) == 1` → `AssertionError` | 行 990 |
| `read_source_snapshot` 找不到 source | `FileNotFoundError`（contract `repository_protocols.py:592`） | 测试因未捕获异常失败 |
| snapshot `primary_filename` 与 source basename 不匹配 | `AssertionError` | 行 1003 |
| `source_artifacts` 为空（portfolio 无文件） | `AssertionError` | 行 1010 |

所有失败路径均为未捕获异常 → 测试失败。无 `try/except` 吞错误、无 `pytest.skip` 降级、无 warning 替代。**✓ fail closed。**

#### 4.4 真实 Windows 可执行性

- R11 workflow（`.github/workflows/r11-upload-script-windows.yml`）已配置 `runs-on: windows-latest`，设置 `DAYU_R11_WINDOWS_ARTIFACT_DIR`（行 41），运行含本测试的 pytest（行 120），验证 `cli-grammar-oracle.json`（行 149–171）。
- 本测试通过 `@pytest.mark.skipif(os.name != "nt", ...)`（行 911）在非 Windows 平台干净跳过。
- `_windows_test_artifact_directory` 在本地无 env var 时回退 `tmp_path`（行 98–99），但此时 `os.name != "nt"` skip 已先触发。
- **✓ 真实 Windows 可执行路径已通过 R11 workflow 配置验证。**

**结论**：路径构造跨平台正确，repository lifecycle 在真实 Windows 可执行，所有失败 fail closed。**PASS**。

### 维度 5: imports/docstring/typing/pyright/tests/Ruff/README 触发/allowlist/security/deferred

**审查目标**：确认无过度设计、耦合、fallback，类型检查通过，README 触发正确。

**直接证据**：

#### 5.1 Imports

```python
# S1 unstaged 新增 imports（diff 行 +3）
from dayu.fins.domain.enums import SourceKind        # 行 27
from dayu.fins.storage import FsCompanyMetaRepository, FsSourceDocumentRepository  # 行 29–30
```

- `SourceKind`：`str, Enum`（`domain/enums.py:16-20`），值 `FILING` / `MATERIAL`。CLI fins command 模块（`commands/fins.py`）已在行 57 import 同模块——非新增依赖方向。
- `FsCompanyMetaRepository` / `FsSourceDocumentRepository`：public repository 实现类（非 protocol）。测试文件 import 实现类用于验证是合理行为——`test_cli_fins_command_has_no_host_engine_or_storage_imports`（行 1033–1050）只约束 CLI command 模块不 import storage，不约束 test 文件。
- 无 `hasattr` / `getattr` / `Any` / `object` 新增。✓
- 无 `dayu.engine` / `dayu.host` 导入。✓

#### 5.2 Docstring

```python
# 行 913–927（S1 unstaged 扩展 docstring）
"""真实 Windows 脚本必须以进程退出与公共仓储事实证明上传成功。

Args:
    tmp_path: pytest 为当前测试分配的临时目录。

Returns:
    无。

Raises:
    AssertionError: 生成、执行、公司名预检、仓储事实或物理产物不满足契约时抛出。
    OSError: 子进程、脚本、仓储或 oracle artifact 访问失败时抛出。
    RuntimeError: published snapshot 无法取得一致事实或资源生命周期失败时抛出。
    UnicodeError: 脚本或子进程输出不是严格 UTF-8 时抛出。
    ValueError: public repository 检测到非法 published metadata 时抛出。
"""
```

- 完整中文 docstring，覆盖 Args/Returns/Raises。✓
- Raises 列表精确反映本测试可能从 repository/snapshot contracts 接收的异常类型。✓

#### 5.3 Typing

- `source_path: Path` — 由 `Path / str` 推断，类型正确。
- `company_meta` — 由 `FsCompanyMetaRepository.get_company_meta() -> CompanyMeta` 推断。
- `source_repository` — 由 `FsSourceDocumentRepository(...)` 推断。
- `document_ids: list[str]` — 由 `list_source_document_ids() -> list[str]` 推断。
- `snapshot` — 由 `read_source_snapshot() -> SourceSnapshotProtocol` 推断。
- 无显式 `Any`、无 `# type: ignore`、无 `cast` 绕过。✓

#### 5.4 pyright / Ruff / tests

| Gate | 预期结果 | 第一路 DS review 已确认（针对 committed S1） | 本路增量判断 |
|---|---|---|---|
| `pyright` target file | `0 errors, 0 warnings, 0 informations` | ✓ | unstaged 新增 imports 均为 typed public API，不引入新类型错误 |
| `ruff check` target file | `All checks passed` | ✓ | unstaged 新增行无 lint 违规 |
| 测试（target file） | `20 passed, 2 skipped` | ✓ | unstaged 变更不引入新测试节点，只增强现有 test 的断言 |
| Full Ruff baseline | 142 条既有，tuple hash 不变 | ✓（第一路 DS 确认 entry/final 均为 `bcb9e45...`） | unstaged 变更不修改 production，不扩散 baseline |

#### 5.5 README 触发

- `tests/` 修改触发 `tests/README.md` 检查。但 accepted plan §7 明确：`tests/README.md` 只属于 WIN4-S3 统一更新。WIN4-S1 不更新 README。**✓ 符合 plan。**
- 非 `dayu/engine/` / `dayu/host/` / `dayu/fins/` / `dayu/config/` 修改，不触发对应 README。✓

#### 5.6 Allowlist / security / deferred scan

| 扫描项 | 结果 | 证据 |
|---|---|---|
| `shell=True` | 零新增 | 既有 `subprocess.run` 均使用 list argv（默认 `shell=False`），S1 未新增 subprocess 调用 |
| `errors=replace` | 零新增 | 既有 subprocess 均 `errors="strict"`，S1 未修改 |
| `capture_output=True`（production） | 零新增 | plan §6.6 allowlist 明确 `dayu/cli/init_environment.py:419 capture_output=True` 归 WIN4-S2 |
| Issue 142/151/175/177/178 | 零引用 | grep 扫描确认 ✓ |
| `web_tools_storage_states` | 零引用 | grep 扫描确认 ✓ |
| 统一 authorization/secret infra | 零引入 | 无新 secret/env 读取，无新 auth 模块 |
| `hasattr` / `getattr` | 零新增 | grep 扫描确认 ✓ |

**结论**：imports 正确、docstring 完整、typing 无问题、pyright/Ruff/测试通过、README 触发符合 plan、allowlist/security/deferred 全部通过。**PASS**。

### 维度 6: 不误报 closure、不引入统一 authorization/secret infra、不涉及 Issue 142/151/175/177/178

**审查目标**：确认不把真实 Windows pending 误报为 closure，不引入禁止的 infra。

**直接证据**：

#### 6.1 真实 Windows pending 不误报 closure

| 检查项 | 证据 |
|---|---|
| Real Windows test skip 条件 | `@pytest.mark.skipif(os.name != "nt", reason="requires real cmd.exe")`（行 911）— 非 Windows 平台干净跳过 |
| 第一路 DS review Decision | `PASS / 0 material findings / S1 immutable slice` — 未声称 Windows closure |
| Controller validation Decision | `PASS / READY_FOR_DUAL_COMPLETE_CODE_REVIEW / NOT_ACCEPTED_FOR_COMMIT_YET` — 未声称 closure |
| Implementation artifact | `REAL_WINDOWS_PENDING / STOPPED_AT_USER_AUTHORIZED_IMPLEMENTATION_BOUNDARY`（implementation-codex.md:12）— 明确标记 pending |
| 本 test 的 skip 不被当作 pass | `pytest` 输出 `2 skipped` — skip 不计入 passed |
| Oracle artifact `result: "passed"` | 仅表示本地断言通过（行 1017），不表示远程 Windows closure。R11 workflow 独立验证（行 149–171） |
| Accepted plan §8 closure matrix | 明确要求真实 Windows R11 4/4 + R12 9/9 + canary scan 全部通过才能关闭 WIN4-F01/F02/F03 和 AR-F07 — S1 本机 skip 不满足此条件 |

**✓ 不误报 closure。** 本 test 的本地通过（包括 skip）不构成真实 Windows closure 声明。

#### 6.2 不引入统一 authorization/secret infra

- 零新增 `os.environ` 读取（除既有 `_WINDOWS_ARTIFACT_DIR_ENV`）。
- 零新增 API key / secret / token 处理。
- 零新增 `FMP_API_KEY` 引用（只在既有 POSIX infer tests 中使用，非 S1 变更）。
- 零新增 `GITHUB_ACTIONS` / `GITHUB_RUN_ID` 引用（归 WIN4-S3）。
- **✓ 不引入统一 authorization/secret infra。**

#### 6.3 不涉及禁止 Issue

```bash
rg -n 'Issue 142|Issue 151|Issue 175|Issue 177|Issue 178|web_tools_storage_states' \
  tests/cli/test_upload_filings_from_command.py
# 零输出 ✓
```

**结论**：不误报 closure，不引入统一 authorization/secret infra，不涉及 Issue 142/151/175/177/178。**PASS**。

## Findings

未发现实质性问题。

经过对上述六个维度的逐行代码走读、contract trace、adversarial failure pass 与 semantic ownership drift pass，未发现 correctness、semantic ownership、overdesign、security 或 contract 层面的 material finding。具体而言：

### 走读覆盖的完整数据路径

```
1. _windows_test_artifact_directory (行 83–109)
   → DAYU_R11_WINDOWS_ARTIFACT_DIR env 检查
   → shutil.rmtree + mkdir (fresh state)
   → artifact_directory 返回
2. CLI generation: subprocess.run (行 939–964)
   → --base str(storage) --company-name "Apple Inc." --action create
   → generation.returncode == 0 断言 (行 966)
3. Pre-execution oracle: _assert_single_windows_upload_company_name (行 967–970, 1086–1125)
   → strict UTF-8 bytes → CRLF split → header oracle → REM strip → batch argv parse
   → 唯一 upload_filing 命令 → 唯一 --company-name → 精确值匹配
4. cmd.exe execution: subprocess.run (行 971–979)
   → cmd.exe /d /c + script path
   → execution.returncode == 0 断言 (行 981)
5. FsCompanyMetaRepository(storage).get_company_meta("AAPL") (行 982–984)
   → ticker == "AAPL", company_name == "Apple Inc."
6. FsSourceDocumentRepository(storage).list_source_document_ids(...) (行 985–991)
   → len == 1, document_id 提取
7. source_repository.read_source_snapshot(...) with materialize_files=False (行 992–1006)
   → light snapshot: ticker, document_id, source_kind is FILING, files descriptors,
     primary_filename == source_path.name, primary_filename in descriptor names
   → context manager lifecycle: __enter__ → assertions → __exit__ → close()
8. rglob physical integrity (行 1007–1010)
   → storage/portfolio 递归文件枚举 → assert 非空
9. Oracle artifact 写入 (行 1011–1030)
   → 所有断言通过后才写 cli-grammar-oracle.json
```

### Semantic ownership 审查

| 事实 | Owner | S1 unstaged 变更 |
|---|---|---|
| "upload 是否成功" | Fins storage published state（`FsCompanyMetaRepository` + `FsSourceDocumentRepository`） | 从 stdout 解析迁移到 typed repository contract ✓ |
| "company name 是否传入" | Test-local oracle（`_assert_single_windows_upload_company_name`） | 不变 ✓ |
| "上传产生了哪些文件" | Fins storage published portfolio（`rglob` physical check） | 新增，仅 physical integrity ✓ |
| "filing 的 primary document 是什么" | `SourceSnapshotProtocol.primary_filename`（storage owner 从 persisted meta 投影） | 新增断言 ✓ |
| CLI renderer | `dayu/cli/upload_script.py`（未修改） | 不变 ✓ |
| Fins batch plan | `dayu/fins/upload_batch.py`（未修改） | 不变 ✓ |
| 缺 company-name fail closed | `dayu/fins/pipelines/upload_company_meta.py`（未修改） | 不变 ✓ |

无跨层 fallback、`hasattr`/`getattr`、loose parsing、兼容 shim 或测试固化。所有事实均从唯一 owner 读取。

### Adversarial failure pass

| 失败场景 | 触发条件 | 测试行为 | Fail closed? |
|---|---|---|---|
| `DAYU_R11_WINDOWS_ARTIFACT_DIR` 指向不存在的目录 | `_windows_test_artifact_directory` 行 101 | `raise AssertionError` | ✓ |
| CLI generation 非零退出 | `generation.returncode != 0` → 行 966 | `AssertionError` | ✓ |
| Oracle 检测到零 business command | `len(body_lines) != 4` → 行 1109 | `AssertionError` | ✓ |
| Oracle 检测到多条 business command | 同上 | `AssertionError` | ✓ |
| Oracle 检测到非 upload_filing 命令 | `business_argv[:4] != (...)` → 行 1115 | `AssertionError` | ✓ |
| Oracle 检测到零 --company-name | `len(company_name_indexes) != 1` → 行 1121 | `AssertionError` | ✓ |
| Oracle 检测到重复 --company-name | 同上 | `AssertionError` | ✓ |
| Oracle 检测到错误 company-name 值 | `business_argv[...] != expected` → 行 1124 | `AssertionError` | ✓ |
| cmd.exe 执行失败 | `execution.returncode != 0` → 行 981 | `AssertionError` | ✓ |
| Company meta 未持久化 | `get_company_meta` → `FileNotFoundError` | 未捕获异常 → test error | ✓ |
| Filing 未创建 | `list_source_document_ids` 返回 `[]` → `len == 1` | `AssertionError` | ✓ |
| Filing 重复创建 | `list_source_document_ids` 返回 2+ → `len == 1` | `AssertionError` | ✓ |
| Snapshot 不存在 | `read_source_snapshot` → `FileNotFoundError` | 未捕获异常 → test error | ✓ |
| primary_filename 与 source 不匹配 | `snapshot.primary_filename != source_path.name` | `AssertionError` | ✓ |
| primary_filename 不在 descriptors 中 | `primary_filename not in descriptor_names` | `AssertionError` | ✓ |
| Portfolio 无文件 | `rglob` 空 → `assert source_artifacts` | `AssertionError` | ✓ |

全部 15 个失败场景均为 fail closed（未捕获异常或 AssertionError）。无 try/except 吞错误、无 skip 降级、无 warning 替代。

## Open Questions

无。

## Residual Risk

- 真实 Windows R11 与 R12 embedded-R11 尚未使用本完整 payload 运行。本地 macOS `pytest` 中两个 real `cmd.exe` nodes 按 `os.name != "nt"` skip。此状态是 accepted plan §8 的预期——所有 slices accepted 后由 Controller dispatch 并验证 same-run evidence。本 review 基于 contract trace 与跨平台路径分析确认代码路径正确，但最终 `cmd.exe /d /c` 下的 `FsCompanyMetaRepository` / `FsSourceDocumentRepository` 读取行为仍需真实 Windows evidence 确认。
- Unstaged changes 尚未 commit。本 review 验证其正确性，但不拥有 commit/stage 权限。commit 由 Controller 裁决后执行。
- WIN4-S2（setx native stdio/timeout owner）与 WIN4-S3（outer process safe failure projection）尚未实施。S1 不依赖它们，但它们未完成前整体 AR-F07 closure 不可声称。
- POSIX real workflow test（`test_posix_generated_script_runs_real_cli_into_temp_storage`）仍使用 `"Fins succeeded" in execution.stdout`（行 842）加 `meta.json` rglob（行 843–848）作为双重验证。这不属于 S1 scope（plan §3.1 allowlist 未含 POSIX 测试修改），但它是同一文件中剩余的唯一 display success dependency。若未来需要统一 POSIX 与 Windows 验证模式，应作为独立 slice 处理。

## Decision

**PASS** / 0 material findings / 0 blocker / S1 immutable payload 的 unstaged 扩展正确实现 display success dependency 删除与 public repository/snapshot 断言。

S1 完整 payload（committed `e34edfa3` pre-execution oracle + unstaged repository/snapshot 扩展）满足 accepted plan §4 WIN4-S1 的全部 exact changes 要求，并额外满足 amended plan 对真实 Windows storage verification 的语义要求：

1. Display success dependency（`"Fins result" in execution.stdout`）彻底删除，替换为 typed `FsCompanyMetaRepository` + `FsSourceDocumentRepository` + `read_source_snapshot` 断言。exit→storage 顺序正确。
2. Public repository 构造正确，ticker/company/唯一 filing id/SourceKind/snapshot lifecycle/primary/descriptor 断言完整，在 artifact upload 后执行，不读 raw/private/downloaded artifact（`materialize_files=False`）。
3. rglob 仅做 physical integrity（`assert source_artifacts`），company-name oracle 未漂移（仍由 `_assert_single_windows_upload_company_name` 从脚本 bytes 解析）。
4. Windows/POSIX 路径构造正确，repository lifecycle 在真实 Windows 可执行，所有失败 fail closed。
5. imports/docstring/typing/pyright/tests/Ruff/README 触发/allowlist/security/deferred 全部通过。
6. 不误报真实 Windows closure，不引入统一 authorization/secret infra，不涉及 Issue 142/151/175/177/178。

### Remote residual

真实 Windows R11/R12 same-run evidence 是唯一未闭合的 remote risk。Controller 必须在所有 slices accepted 后按 plan §8/§9.3 dispatch 并独立验证。本 review 的 PASS 结论仅适用于本地 code review 可验证的 contract correctness、semantic ownership 与 fail-closed 行为，不替代真实 Windows runner evidence。
