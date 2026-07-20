# WU-SEMANTIC-OWNERSHIP-01 AR-F07 WIN4-RW-S1 Code Re-Review — AgentDS（第二路完整重审）

## Result

`PASS / NEW_FINDING=0 / BACKFLOW_FINDING=0 / BLOCKER=0 / CONTROLLER_FIVE_NO_ACTION_RULINGS_CONFIRMED / REAL_WINDOWS_PENDING`

## Scope

- Mode: current changes（immutable payload deep re-review）
- Umbrella: `WU-SEMANTIC-OWNERSHIP-01`
- Continuation: `AR-F07` WIN4 real-Windows S1
- Branch: `phaseflow/host-issues-control`
- Base: S1 authorization commit `8fafe9bad4828c83fa6cf80a1dc2199fe78472d9`
- Output file: `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-s1-code-rereview-ds.md`
- Included scope: `tests/cli/test_upload_filings_from_command.py`（working tree unstaged diff vs HEAD `8fafe9ba`）
- Immutable payload:
  - File: `tests/cli/test_upload_filings_from_command.py`
  - Content SHA-256: `71855b783ae1191ed764c69c938f2ca29d0c51ae575f501a431e33615ebb4d3d` ✓（已核验）
  - Git tree entry: `8fafe9bad4828c83fa6cf80a1dc2199fe78472d9`
- Payload diff numstat: `1 file changed, 44 insertions(+), 3 deletions(-)`（已核验，与原初 DS review 一致）
- Excluded scope:
  - `docs/host/issues-implementation-control.md`（control-doc 状态更新，非 S1 ownership）
  - 已 commit 的 S1 oracle/argv 部分（`e34edfa3`，已由第一路 DS review 覆盖且 CI/Controller 验证未漂移）
  - POSIX real workflow test（`test_posix_generated_script_runs_real_cli_into_temp_storage`，非 S1 变更）
  - WIN4-S2 / WIN4-S3（未实施）
  - Production code（`dayu/` — S1 零 diff，已通过 pyright/Ruff baseline 不变核验）
- Parallel review coverage: 无（单文件 immutable payload，主 reviewer 全量走读）
- Pre-read artifacts（全部完整读取）:
  - `AGENTS.md`（129 行，项目约束）
  - Accepted amended plan（`docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md`，1060 行，SHA-256 `7e82df117c5d7b97e13d8ee2ec156c19de6689c129f09cec979cd0b1bf8adb76`）
  - AgentCodex implementation artifact（SHA-256 `b12e3489819482b3815bfd6056ce2bbaba66827774405440c42a221b77ca6180`）
  - Controller validation artifact（SHA-256 `2c326a9b4fb1fab49fe5acb96c197f68caa10731ceef9ec67676224703d0bc9e`）
  - AgentMiMo initial code review（SHA-256 `62b49d4025326f7079e5366a5f537de10c2cf2fb103890a72d50f1fc566de527`）
  - AgentDS initial code review（SHA-256 `332947a023904942b759bfa391d3ebf13488439407dbe325fc6e096935bec4f9`）
  - Controller adjudication（SHA-256 `365f2196465624a8068297c088be0af91270bb150881da175210218a5925b704`）
  - AgentCodex zero-change artifact（SHA-256 `09de7075e0683b946c7751e774910e3747414fe306d3f5013d2dc149875da146`）
  - Controller zero-change validation（SHA-256 `4d56682bfc33d15ae725a9eeeebe267b8899325f45d7ccd8a49355987160b74f`）
  - Direct Fins public contracts:
    - `dayu/fins/storage/repository_protocols.py`（完整 1222 行，`SourceSnapshotProtocol`、`CompanyMetaRepositoryProtocol`、`SourceDocumentRepositoryProtocol`）
    - `dayu/fins/storage/fs_source_document_repository.py`（`read_source_snapshot` 委派实现，行 510–542）
    - `dayu/fins/storage/_fs_source_snapshot.py`（`_SnapshotResourceState.close()` 幂等关闭，行 161–182；`__enter__`/`__exit__` lifecycle，行 302–352）
    - `dayu/fins/domain/enums.py`（`SourceKind` 定义）
    - `dayu/fins/storage/__init__.py`（public exports）
    - `dayu/cli/upload_script.py`（完整 393 行，renderer/publisher owner）
    - `.github/workflows/r11-upload-script-windows.yml`（R11 workflow 完整 evidence chain，行 120–178）

## Controller five no-action rulings — DS 逐项核对

本 re-review 必须核对 Controller 对 AgentDS 初始 review 中五项 `NOT_A_CURRENT_CODE_FINDING / NO_ACTION` 裁决。每项均需从实际代码与 artifact 中获取直接证据。

### Ruling 1: DS scope 表引用了先前的 `win4-s1` 路径而非本轮 `real-windows-s1` 路径

**Controller 裁决**: 引用错误不改变已锁定 payload SHA、直接代码走读和 PASS 结论；但不得用于后续 evidence lineage；Controller 只使用本轮正确 paths/hashes。

**DS 重审核验**:

初始 DS review 的 scope 表中列出的 pre-read artifacts 包含:
- `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-s1-implementation-codex.md`（旧路径）
- `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-s1-controller-validation.md`（旧路径）
- `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-s1-code-review-ds.md`（旧路径）

本轮正确实物均带 `real-windows-s1` 路径：
- `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-s1-implementation-codex.md`
- `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-s1-controller-validation.md`

**结论**: 初始 DS review 的 artifact 路径引用确实存在命名不一致。但该引用仅出现在 scope 元数据中，不进入 review 逻辑。初始 DS review 对 payload SHA `71855b783ae1191ed764c69c938f2ca29d0c51ae575f501a431e33615ebb4d3d` 的锁定和逐行代码走读均基于实际文件内容，未因路径引用不一致而漂移。**Controller 裁决成立**。本轮重审已全部使用带 `real-windows-s1` 的正确路径。

---

### Ruling 2: DS Decision 中"repository 断言在 artifact upload 后执行"是文字错误

**Controller 裁决**: 实际顺序是 `cmd.exe` exit → runner test 内 public repository/snapshot assertions → oracle 写入 → pytest 结束 → workflow 后续 artifact upload；plan 要求的"upload 前"成立。

**DS 重审核验 — 完整执行序列还原**:

```
行 939–964: CLI generation subprocess.run → generation.returncode == 0 断言（行 966）
行 967–970: _assert_single_windows_upload_company_name() — pre-execution oracle（从脚本 bytes 解析，不依赖 execution）
行 971–979: cmd.exe execution subprocess.run → execution.returncode == 0 断言（行 981）
           ⬆ exit gate：只有 returncode == 0 才进入后续
行 982–984: FsCompanyMetaRepository(storage).get_company_meta("AAPL") → ticker + company_name 断言
           ⬆ 第一个 public storage fact
行 985–991: FsSourceDocumentRepository(storage).list_source_document_ids("AAPL", SourceKind.FILING) → len == 1
           ⬆ source inventory fact
行 992–1006: with source_repository.read_source_snapshot(...) as snapshot: → ticker/document_id/source_kind/primary_filename/descriptors 断言
           ⬆ snapshot lifecycle fact（with 块内）
行 1007–1010: storage/portfolio rglob → assert source_artifacts
           ⬆ physical integrity fact
行 1011–1030: cli-grammar-oracle.json 写入
           ⬆ oracle artifact（所有事实成立后才写）
```

**所有 repository/snapshot 断言（行 982–1006）均在 oracle artifact 写入（行 1011–1030）之前执行。** 初始 DS review Dimension 2.7（行 189）的描述是正确的（"所有 repository 构造与 snapshot 断言均在 `execution.returncode == 0` 之后、oracle artifact 写入之前"），但 Decision 摘要（行 495）中的"在 artifact upload 后执行"是文字错误，顺序写反。

**结论**: 代码实际顺序正确，plan §13.5.1 要求的"execution nonzero 必须在任何 storage success assertion 和 oracle 写入前失败"成立。**Controller 裁决成立**。

---

### Ruling 3: DS 称"15 个失败场景"但表格实际列出 16 行

**Controller 裁决**: 计数错误不影响逐行 fail-closed 证据，不构成代码 finding。

**DS 重审核验**:

初始 DS review §Adversarial failure pass 表格包含以下 16 行（按出现顺序）:

| # | 失败场景 | 触发条件 | 行为 |
|---|---------|---------|------|
| 1 | `DAYU_R11_WINDOWS_ARTIFACT_DIR` 指向不存在的目录 | `_windows_test_artifact_directory` 行 101 | `raise AssertionError` |
| 2 | CLI generation 非零退出 | `generation.returncode != 0` → 行 966 | `AssertionError` |
| 3 | Oracle 检测到零 business command（只有 comment 行） | `len(body_lines) != 4` → 行 1109 | `AssertionError` |
| 4 | Oracle 检测到非 upload_filing 命令 | `business_argv[:4] != (...)` → 行 1115 | `AssertionError` |
| 5 | Oracle 检测到零 --company-name | `len(company_name_indexes) != 1` → 行 1121 | `AssertionError` |
| 6 | Oracle 检测到重复 --company-name | 同上 | `AssertionError` |
| 7 | Oracle 检测到错误 company-name 值 | `business_argv[...] != expected` → 行 1124 | `AssertionError` |
| 8 | Oracle 检测到多条 business command | `len(body_lines) != 4` → 行 1109 | `AssertionError` |
| 9 | cmd.exe 执行失败 | `execution.returncode != 0` → 行 981 | `AssertionError` |
| 10 | Company meta 未持久化 | `get_company_meta` → `FileNotFoundError` | 未捕获异常 → test error |
| 11 | Filing 未创建 | `list_source_document_ids` 返回 `[]` → `len == 1` | `AssertionError` |
| 12 | Filing 重复创建 | `list_source_document_ids` 返回 2+ → `len == 1` | `AssertionError` |
| 13 | Snapshot 不存在 | `read_source_snapshot` → `FileNotFoundError` | 未捕获异常 → test error |
| 14 | primary_filename 与 source 不匹配 | `snapshot.primary_filename != source_path.name` | `AssertionError` |
| 15 | primary_filename 不在 descriptors 中 | `primary_filename not in descriptor_names` | `AssertionError` |
| 16 | Portfolio 无文件 | `rglob` 空 → `assert source_artifacts` | `AssertionError` |

实际行数为 16，非 15（初始化 DS review 行 474 表述为"全部 15 个失败场景"）。每个场景的 evidence location、触发条件、fail-closed 行为均直接可追溯到代码行号，且每个场景的行为均正确。**Controller 裁决成立**。

---

### Ruling 4: 同文件 POSIX smoke 的 `Fins succeeded` 展示断言不在 scope

**Controller 裁决**: 不在本次真实 Windows finding、accepted amendment 或 S1 allowlist 内；拒绝在本 slice 修改或创建新 WU/Issue；后续若有直接 accepted finding，必须由其原 owner/范围单独裁决。

**DS 重审核验**:

`test_posix_generated_script_runs_real_cli_into_temp_storage`（行 792–848）:
- 行 842: `assert execution.stdout.count("Fins succeeded") == 2` — 仍为 display success dependency
- 行 843–848: `rglob("meta.json")` + `json.loads` + `source_kind` 集合断言 — 读取业务语义

此测试不在 plan §13.3 WIN4-RW-S1 allowed paths 中。plan 只授权 `tests/cli/test_upload_filings_from_command.py` 中针对真实 Windows smoke 的 display dependency 删除。POSIX 测试保持不变是 plan 的预期行为——它不是 regression，而是另一测试节点的独立语义。

`Fins succeeded` 字符串由 `dayu/cli/output.py` 的 `_render_fin_result` 生成，其语义 owner 是 CLI output 层，非 storage。POSIX 测试使用它作为额外验证是合理但不同的验证策略。将 POSIX 与 Windows 验证模式统一需要独立 plan slice，不在 S1 scope 内。

**结论**: POSIX 测试不受 S1 影响，按 plan 预期保持不变。**Controller 裁决成立**。

---

### Ruling 5: Windows filelock 底层实现推测不作为 durable product fact

**Controller 裁决**: Accepted contract 仅是 public repository 在支持平台的既有行为与 fresh R11/R12 最终证据。

**DS 重审核验**:

初始 DS review Dimension 4.2（行 259）提及 `filelock` 通过 `msvcrt` 或 `pywin32` 工作——这是对 `filelock` 底层实现机制的推测性说明，而非 durable product fact。实际上:
- `filelock` 的 Windows 实现细节取决于 `filelock` package 版本和已安装的系统库
- Dayu 的 accepted contract 是 `FsSourceDocumentRepository.read_source_snapshot()` 的 protocol contract（`repository_protocols.py:572–598`），其 Raises 列表包含 `RuntimeError: publication guard 获取或释放失败时抛出`
- Public contract 不承诺底层使用何种 OS primitive（`msvcrt`、`pywin32`、`LockFileEx` 或其他）
- 真正可信的证据是 R11 workflow 的 fresh `cmd.exe` run 中 repository 操作成功完成

**结论**: 初始 DS review 的 filelock 实现推测不应作为 durable product fact 进入 evidence lineage。正确做法是依赖 public contract 行为 + 真实 Windows evidence。**Controller 裁决成立**。

---

### 五项裁决汇总

| # | 裁决事项 | Controller 判定 | DS 重审核验 | 本轮处理 |
|---|---------|----------------|------------|---------|
| 1 | Scope 表旧路径引用 | NO_ACTION | 路径引用不一致确认，不影响结论 | 使用正确路径 |
| 2 | Decision "upload后"文字错误 | NO_ACTION | 代码顺序正确，行 495 文字反了 | 已纠正 |
| 3 | 15 vs 16 计数 | NO_ACTION | 实际 16 行，每行 evidence 正确 | 已纠正计数 |
| 4 | POSIX display 观察 out of scope | NO_ACTION | 不在 S1 allowlist | 不扩展 |
| 5 | filelock 推测 | NO_ACTION | 不构成 durable fact | 依赖 contract behavior |

**五项裁决全部确认成立。不存在因裁决遗漏的 material finding。**

---

## Six-dimension complete re-verification

### 维度 1: Display success dependency 彻底删除 / 零回流

**审查目标**: 确认 `"Fins result" in execution.stdout` 已完全移除，未用 stderr/stdout/word/parser 替代。

**逐路径完整走读**:

**1.1 旧代码删除确认**

```
diff 删除行: -    assert "Fins result" in execution.stdout
```

全文搜索 `Fins result` 在 target file: **零命中**。✓

全文搜索 `Fins summary`、`Fins succeeded`、`Fins failed`、`upload completed`、`success`（作为断言字符串）在 S1 新增行: **零命中**。✓

**1.2 stdout 零消费**

```
execution.stdout 引用计数（S1 unstaged diff 上下文，行 971–1010）: 0
execution.stdout.count(...) 调用: 0
execution.stdout.find(...) 调用: 0
"Fins" in execution.stdout: 0
```

S1 新增代码中唯一的 stdout 相关操作是 `subprocess.run(capture_output=True, text=True, encoding="utf-8")` — 这保留了 stdout 的捕获但从未读取其内容作业务判断。`capture_output=True` 非 S1 新增（旧代码已使用），且捕获本身无害。✓

**1.3 stderr 仅作诊断**

```
行 981: assert execution.returncode == 0, execution.stderr
行 966: assert generation.returncode == 0, generation.stderr
```

`execution.stderr` 仅作为 AssertionError 的诊断消息——当 `returncode != 0` 时，pytest 会将 stderr 内容显示在失败输出中帮助诊断。但它不作为成功判断的真值依据。断言本身只依赖 `returncode`。这是既有模式（旧代码行 966 已对 generation 使用同一模式），S1 未修改。✓

**1.4 零 parser/shell/word 替代**

- `shlex.split(execution.stdout)`: 零引用
- `json.loads(execution.stdout)`: 零引用
- `re.search(... execution.stdout)`: 零引用
- `execution.stdout.splitlines()`: 零引用
- `execution.stdout.strip()`: 零引用
- `str.startswith(...)` 对 stdout: 零引用

**1.5 exit→storage 顺序验证**

```
行 981: assert execution.returncode == 0  ← exit gate（第一步）
行 982: FsCompanyMetaRepository(storage).get_company_meta("AAPL")  ← storage fact（第二步及之后）
行 985: FsSourceDocumentRepository(storage).list_source_document_ids(...)  ← storage fact
行 992: with source_repository.read_source_snapshot(...) as snapshot:  ← storage fact
行 1007: rglob  ← physical integrity
行 1011–1030: oracle 写入  ← 最后一步
```

exit 断言（行 981）在任何 storage reading（行 982+）之前。如果 `returncode != 0`，AssertionError 阻止后续所有 storage 断言执行。✓

**维度 1 结论: PASS。display success dependency 已彻底删除，零回流。未用任何 stdout/stderr/word/parser 替代。**

---

### 维度 2: exit→public storage facts→physical integrity→oracle 顺序

**审查目标**: 确认完整执行序列严格按照 plan §13.5.1 的 exit-first、oracle-last 契约。

**完整序列重审（从 entry 到 oracle 写入）**:

```
Phase A — 准备与生成:
  行 929–936: _windows_test_artifact_directory → 确定性 artifact directory
  行 937–938: source_path = source_dir / "2024FY_AAPL_Annual_Report.htm"; write_bytes
  行 939–964: subprocess.run → CLI generation
  行 966:  assert generation.returncode == 0  ← Phase A gate

Phase B — 执行前 company-name preflight:
  行 967–970: _assert_single_windows_upload_company_name(script_path, _WINDOWS_REAL_SMOKE_COMPANY_NAME)
  → 从生成脚本 strict UTF-8 bytes 解析，不依赖 execution 结果 ← Phase B gate

Phase C — 真实 cmd.exe 执行:
  行 971–979: subprocess.run(("cmd.exe", "/d", "/c", str(script_path)), ...)
  行 981:  assert execution.returncode == 0, execution.stderr  ← Phase C exit gate

Phase D — Public storage facts（plan §13.2.1 #3）:
  行 982: FsCompanyMetaRepository(storage).get_company_meta("AAPL")
  行 983:   assert company_meta.ticker == "AAPL"
  行 984:   assert company_meta.company_name == _WINDOWS_REAL_SMOKE_COMPANY_NAME
  行 985–991: FsSourceDocumentRepository(storage).list_source_document_ids("AAPL", SourceKind.FILING)
               → len == 1 → document_id 提取
  行 992–1006: with read_source_snapshot("AAPL", document_id, SourceKind.FILING, materialize_files=False) as snapshot:
                 assert snapshot.ticker == "AAPL"
                 assert snapshot.document_id == document_id
                 assert snapshot.source_kind is SourceKind.FILING
                 assert snapshot.files (descriptors 非空)
                 assert snapshot.primary_filename == source_path.name
                 assert snapshot.primary_filename in descriptors_names
  ← Phase D: 所有 storage facts 在 with 块内完成

Phase E — Physical integrity:
  行 1007–1010: rglob(storage/portfolio/*) → is_file() → assert source_artifacts (非空)
  ← Phase E: 仅验证 portfolio 非空

Phase F — Oracle artifact 写入（最后一步）:
  行 1011–1030: cli-grammar-oracle.json 写入
                 包含 test_node/result/generated_script_sha256/source_artifact_count/
                 cmd_invocation/company_name_supplied
  ← Phase F: 所有断言通过后才写 oracle
```

**顺序正确性检查**:

| 检查项 | plan §13.5.1 要求 | 实际代码 | 判定 |
|--------|-------------------|---------|------|
| execution nonzero 在 storage assertions 前失败 | "execution nonzero 必须在任何 storage success assertion 和 oracle 写入前失败" | 行 981 exit assert 在行 982 storage 断言之前 | ✓ |
| exit 0 但 company meta 缺失/非法时失败 | "exit 0 但 company meta 缺失/非法...时必须失败" | `get_company_meta` → FileNotFoundError 未捕获，test error | ✓ |
| exit 0 但 filing document id 为零时失败 | "filing document id为零...时必须失败" | `len(document_ids) == 1` → [] 触发 AssertionError | ✓ |
| exit 0 但 filing document id 为多个时失败 | "filing document id为多个...时必须失败" | `len(document_ids) == 1` → [a,b] 触发 AssertionError | ✓ |
| snapshot identity/source kind/primary 不一致时失败 | "snapshot identity/source kind/primary descriptor不一致时必须失败" | 行 998–1006 分别断言 ticker/document_id/source_kind/primary_filename/descriptor membership | ✓ |
| snapshot 只在 with lifecycle 内读取 | "source snapshot...只在 public with lifecycle 内读取" | 行 992–1006: 所有 snapshot 属性访问在 with 块内 | ✓ |
| stdout 变化不导致失败 | "stdout为空...只要 exit 与 storage owner facts 成立，不得失败" | 零 stdout 内容断言 | ✓ |
| stdout 含"成功词"但 exit 非零或 storage 缺失时不通过 | "stdout 含任意看似成功词但 exit 非零或 storage owner facts 缺失时，不得通过" | exit 断言在 stdout 消费之前，storage 断言在 exit 之后 | ✓ |
| company-name oracle 继续 fail closed | "company-name pre-execution oracle...继续 fail closed" | `_assert_single_windows_upload_company_name` 签名与实现不变 | ✓ |

**维度 2 结论: PASS。exit→storage facts→physical integrity→oracle 顺序严格正确，符合 plan §13.5.1 全部契约。**

---

### 维度 3: Snapshot with lifecycle / Windows 路径 / fail closed

**审查目标**: 确认 `read_source_snapshot` context manager lifecycle 正确、路径跨平台安全、所有失败路径 fail closed。

**3.1 Snapshot lifecycle 完整追踪**

```
行 992–1006:
with source_repository.read_source_snapshot(
    "AAPL", document_id, SourceKind.FILING, materialize_files=False,
) as snapshot:
    # __enter__ (行 302–316): require_open() 确认未关闭 → return self
    assert snapshot.ticker == "AAPL"         # 行 354- 属性访问
    assert snapshot.document_id == document_id
    assert snapshot.source_kind is SourceKind.FILING
    descriptors = snapshot.files             # 行 163- 返回 tuple[SourceSnapshotFileDescriptor, ...]
    assert descriptors
    assert snapshot.primary_filename == source_path.name  # 行 170- 来自 persisted meta primary_document
    assert snapshot.primary_filename in tuple(d.name for d in descriptors)
    # __exit__ (行 318–352): self.close() → _SnapshotResourceState.close() (行 161–182)
    #   → self.closed = True → _remove_snapshot_temp_root(temp_root) → self.temp_root = None
    #   light snapshot (materialize_files=False): temp_root is None → close() 仅设置 closed=True
```

Context manager contract（`repository_protocols.py:87–125`）:
- `__enter__`: 返回可读 snapshot，已关闭时 `RuntimeError`
- `__exit__`: 始终返回 `False`（不压制异常）。正常退出时调用 `close()`；有活动异常时把 close failure 作为 secondary note 附加

Lifecycle 验证点:
- `materialize_files=False` → `temp_root=None` → `close()` 不执行 `rmtree`，仅 `closed=True`。✓
- `__exit__` 返回 `False` → 不压制断言失败。✓
- 所有属性访问在 `with` 块内 → 若 `close()` 在 block 内被意外调用（不会发生——没有显式 close 调用），下次访问会触发 `RuntimeError`。✓

**3.2 Windows 路径安全**

```
行 937: source_path = source_dir / "2024FY_AAPL_Annual_Report.htm"
行 938: source_path.write_bytes(fixture)
行 1003: assert snapshot.primary_filename == source_path.name
```

- `Path / str` 运算符: Windows 产生反斜杠路径，POSIX 产生正斜杠路径。✓
- `Path.name`: 在 Windows 上返回 `"2024FY_AAPL_Annual_Report.htm"`（纯 basename，不含 `C:\` 或 `\`）。与 `primary_filename`（来自 persisted meta，同样是 basename）比较，不受路径分隔符影响。✓
- `Path.write_bytes` / `Path.read_bytes`: 跨平台一致。✓
- `storage = artifact_directory`（行 934）: Path 对象，用于 `FsCompanyMetaRepository(storage)` 和 `FsSourceDocumentRepository(storage)` 构造。Windows 上 `Path` 使用反斜杠，repository 内部使用 `Path` / `PurePath` 操作，已经过既有测试和 R11 workflow 验证。✓

**3.3 完整 fail-closed 矩阵（16 个场景逐行验证）**

| # | 失败场景 | 代码位置 | 触发条件 | 实际行为 | Fail Closed? |
|---|---------|---------|---------|---------|-------------|
| 1 | `DAYU_R11_WINDOWS_ARTIFACT_DIR` 指向不存在目录 | 行 101 | `_windows_test_artifact_directory`: `not artifact_root.is_dir()` | `raise AssertionError(...)` | ✓ |
| 2 | CLI generation 非零退出 | 行 966 | `generation.returncode != 0` | `AssertionError` + generation.stderr 诊断 | ✓ |
| 3 | Oracle: 零 business command | 行 1109 | `len(body_lines) != 1 + 1 + len(POST_LINES)` → `!= 4` | `AssertionError` | ✓ |
| 4 | Oracle: 非 upload_filing 命令 | 行 1115 | `business_argv[:4] != ("python", "-m", "dayu.cli", "upload_filing")` | `AssertionError` | ✓ |
| 5 | Oracle: 零 --company-name | 行 1121 | `len(company_name_indexes) != 1` | `AssertionError` | ✓ |
| 6 | Oracle: 重复 --company-name | 行 1121 | 同上 | `AssertionError` | ✓ |
| 7 | Oracle: 错误 company-name 值 | 行 1124 | `business_argv[idx+1] != expected_company_name` | `AssertionError` | ✓ |
| 8 | Oracle: 多条 business command | 行 1109 | `len(body_lines) != 4` | `AssertionError` | ✓ |
| 9 | cmd.exe 执行失败 | 行 981 | `execution.returncode != 0` | `AssertionError` + execution.stderr 诊断 | ✓ |
| 10 | Company meta 未持久化 | 行 982 | `get_company_meta` contract: `FileNotFoundError` | 未捕获异常 → test error（pytest 报告为 FAILED）| ✓ |
| 11 | Filing 未创建 | 行 990 | `list_source_document_ids` 返回 `[]` → `len == 1` → `AssertionError` | `AssertionError` | ✓ |
| 12 | Filing 重复创建 | 行 990 | `list_source_document_ids` 返回 `[a, b]` → `len == 1` → `AssertionError` | `AssertionError` | ✓ |
| 13 | Snapshot 不存在 | 行 992 | `read_source_snapshot` contract: `FileNotFoundError` | 未捕获异常 → test error | ✓ |
| 14 | primary_filename 与 source 不匹配 | 行 1003 | `snapshot.primary_filename != source_path.name` | `AssertionError` | ✓ |
| 15 | primary_filename 不在 descriptors 中 | 行 1004–1006 | `primary_filename not in descriptor_names` | `AssertionError` | ✓ |
| 16 | Portfolio 无文件 | 行 1010 | `rglob` → tuple() → `assert source_artifacts` → `AssertionError` | `AssertionError` | ✓ |

全部 16 个失败场景均为 fail closed。零 `try/except` 吞错误、零 `pytest.skip`/`pytest.xfail` 降级、零 `warnings.warn` 替代。✓

**维度 3 结论: PASS。snapshot lifecycle 正确（context manager 完整 `__enter__`→属性访问→`__exit__`），Windows 路径 safe，全部 16 个失败场景 fail closed。**

---

### 维度 4: Company-name oracle / schema

**审查目标**: 确认 company-name oracle 未漂移，oracle schema 未新增 display 字段。

**4.1 Company-name oracle 未漂移证明**

| 检查项 | 代码位置 | 证据 |
|--------|---------|------|
| Oracle 函数签名 | 行 1086–1090 | `_assert_single_windows_upload_company_name(*, script_path: Path, expected_company_name: str) -> bool` — 非 S1 diff，签名不变 |
| 输入源 | 行 1101 | `script_path.read_bytes().decode("utf-8", errors="strict")` — 从生成脚本 bytes 解析，非 stdout/stderr/storage |
| 调用位置 | 行 967–970 | `_assert_single_windows_upload_company_name(script_path=script_path, expected_company_name=_WINDOWS_REAL_SMOKE_COMPANY_NAME)` — S1 unstaged 未修改此调用 |
| 预期值来源 | 行 59 | `_WINDOWS_REAL_SMOKE_COMPANY_NAME: Final[str] = "Apple Inc."` — S1 unstaged 未修改此常量 |
| 预期值消费点 | 行 954 (CLI argv), 行 970 (oracle), 行 984 (storage assert) | 三处均使用同一 `_WINDOWS_REAL_SMOKE_COMPANY_NAME` — 单真源，未漂移 |
| Oracle 不读 stdout | 全文搜索 | `_assert_single_windows_upload_company_name` 函数体内零 `execution.stdout`/`capsys`/`captured` 引用 |
| Oracle 不读 storage | 全文搜索 | 函数体内零 `FsCompanyMetaRepository`/`FsSourceDocumentRepository`/`read_source_snapshot` 引用 |
| 负例覆盖 | 行 530–562 | `test_windows_upload_company_oracle_fails_closed_on_non_business_evidence`: 1 正例 + 4 负例（零 upload_filing、非 upload_filing command、多条 upload_filing、重复 --company-name），全部 `pytest.raises(AssertionError)` |

**Company-name oracle 的语义 owner 仍是 test-local `_assert_single_windows_upload_company_name`。** 它从生成脚本文本中逐 token 解析 company-name 参数值，不从 storage metadata、execution stdout、FMP resolver 或任何 production source 反推。**未漂移。** ✓

**4.2 Oracle schema 字段稳定性**

`cli-grammar-oracle.json` 写入（行 1011–1030）包含的字段:

```python
{
    "test_node": "test_windows_generated_script_runs_real_cli_into_temp_storage",
    "result": "passed",
    "generated_script_sha256": hashlib.sha256(script_path.read_bytes()).hexdigest(),
    "source_artifact_count": len(source_artifacts),
    "cmd_invocation": "cmd.exe /d /c",
    "company_name_supplied": company_name_supplied,
}
```

字段集合: 共 6 个字段（`test_node`, `result`, `generated_script_sha256`, `source_artifact_count`, `cmd_invocation`, `company_name_supplied`）。与 S1 前 oracle 完全一致，未新增 display/word/parser 相关字段。✓

R11 workflow（行 149–155）消费 `test_node`/`result`/`cmd_invocation` 三个字段做证据契约交叉验证；`source_artifact_count`（行 166–170）与 workflow-level file enumeration 做交叉验证；`generated_script_sha256`（行 157–159）与 `Get-FileHash` 做交叉验证。所有交叉验证逻辑未因 S1 变更而漂移。✓

**维度 4 结论: PASS。company-name oracle 未漂移，oracle schema 字段稳定。**

---

### 维度 5: Typing / tests / pyright / Ruff / README / security / deferred

**5.1 Imports**

S1 unstaged 新增 imports（diff +3 行）:

```python
from dayu.fins.domain.enums import SourceKind        # 行 27
from dayu.fins.storage import FsCompanyMetaRepository, FsSourceDocumentRepository  # 行 29
```

| 检查项 | 结果 |
|--------|------|
| `SourceKind` 来源 | `dayu.fins.domain.enums` — `str, Enum`，值是产品 public contract |
| `FsCompanyMetaRepository` / `FsSourceDocumentRepository` 来源 | `dayu.fins.storage.__init__` 公开导出 |
| 依赖方向 | test → fins.storage（public API）。不违反分层约束（test 可以依赖任意 public API） |
| 无 `dayu.engine` import | ✓ |
| 无 `dayu.host` import | ✓ |
| 无 `hasattr` / `getattr` | ✓ |

**5.2 Docstring**

`test_windows_generated_script_runs_real_cli_into_temp_storage`（行 913–927）完整中文 docstring:
- Args: `tmp_path` — pytest 分配的临时目录
- Returns: 无
- Raises: `AssertionError`（生成/执行/公司名预检/仓储事实/物理产物不满足契约）、`OSError`（子进程/脚本/仓储/oracle artifact 访问失败）、`RuntimeError`（published snapshot 一致性或资源生命周期失败）、`UnicodeError`（脚本或子进程输出非严格 UTF-8）、`ValueError`（public repository 非法 published metadata）

Raises 列表精确映射到 repository/snapshot contract 的异常类型。✓

**5.3 Typing**

| 变量 | 类型来源 | 判定 |
|------|---------|------|
| `source_path` | `Path / str` → `Path` 推断 | ✓ |
| `company_meta` | `FsCompanyMetaRepository.get_company_meta() -> CompanyMeta` | ✓ |
| `source_repository` | `FsSourceDocumentRepository(...)` 构造 | ✓ |
| `document_ids` | `list_source_document_ids() -> list[str]` | ✓ |
| `document_id` | `document_ids[0]` → `str` | ✓ |
| `snapshot` | `read_source_snapshot() -> SourceSnapshotProtocol` | ✓ |
| `descriptors` | `snapshot.files` → `tuple[SourceSnapshotFileDescriptor, ...]` | ✓ |
| `source_artifacts` | `tuple(...)` → `tuple[Path, ...]` | ✓ |

零显式 `Any`、零 `# type: ignore`、零 `cast` 绕过。✓

**5.4 pyright / Ruff / tests**

| Gate | 验证结果 | 证据来源 |
|------|---------|---------|
| `pyright dayu/ tests/ utils/` | `0 errors, 0 warnings, 0 informations` | AgentCodex zero-change artifact fresh validation（行 53）+ Controller zero-change validation（行 25） |
| Scoped Ruff | `All checks passed!` | 同上 |
| Full Ruff baseline | `142` 项，SHA-256 `bcb9e45754ecb183a69859480a286c2c5e3504fb10b1db3958bf44a9deaa2be3` 精确不变 | 同上 |
| Target test file | `20 passed, 2 skipped, 3 warnings` | 同上 |
| Public repository owner nodes | `3 passed, 3 warnings` | 同上 |

三个 warnings 来自已安装 `edgar` package deprecated imports，非 S1 新增或扩散。两个 skip 中一个来自 `os.name != "nt"` marker（本地 macOS），一个来自 Windows-only marker；均不是新平台事实。✓

**5.5 README 触发**

- `tests/` 修改触发 `tests/README.md` 检查。但 plan §13.3 与 accepted plan §7 明确：`tests/README.md` 只覆盖测试层级/运行方式/维护规则变化；S1 只替换既有 test node 内部 success oracle，未改变这些读者契约。`NO UPDATE REQUIRED` 正确。✓
- 非 `dayu/engine/` / `dayu/host/` / `dayu/fins/` / `dayu/config/` 修改，不触发对应 README。✓

**5.6 Allowlist / security / deferred 扫描**

| 扫描项 | 结果 | 证据 |
|--------|------|------|
| `shell=True` | 零新增 | `subprocess.run` 使用 list argv（默认 `shell=False`） |
| `errors=replace` | 零新增 | 全部 `errors="strict"` |
| `capture_output=True`（production） | 零新增 | plan §6.6 allowlist |
| Issue 142/151/175/177/178 | 零引用 | 全文 `rg` 扫描确认 |
| `web_tools_storage_states` | 零引用 | 全文 `rg` 扫描确认 |
| 统一 authorization/secret infra | 零引入 | 无新 `os.environ` 读取（除既有 `_WINDOWS_ARTIFACT_DIR_ENV`） |
| `hasattr` / `getattr` | 零新增 | 全文 `rg` 扫描确认 |
| `FMP_API_KEY` | 零新增引用 | S1 unstaged 变更不在 infer 相关测试中 |
| `GITHUB_ACTIONS` / `GITHUB_RUN_ID` | 零新增引用 | 归 WIN4-S3 |
| `test_windows_upload_company_oracle_fails_closed_on_non_business_evidence` | 不变 | S1 unstaged 未修改此测试节点或 `_assert_single_windows_upload_company_name` 函数体 |

**维度 5 结论: PASS。imports/docstring/typing/pyright/tests/Ruff/README/allowlist/security/deferred 全部正确。**

---

### 维度 6: 真实 Windows pending / 不误报 closure / 不涉及禁止 Issue

**6.1 真实 Windows pending 正确表达**

| 检查项 | 代码位置 | 证据 |
|--------|---------|------|
| Test skip marker | 行 911 | `@pytest.mark.skipif(os.name != "nt", reason="requires real cmd.exe")` — 非 Windows 干净跳过 |
| Skip 不计入 pass | pytest 输出 | `2 skipped` — skip 不是 passed |
| Oracle `result: "passed"` | 行 1017 | `"result": "passed"` — 仅表示本地断言通过，有其 `test_node` 字段明确限定 scope |
| R11 workflow 独立验证 | workflow 行 120–178 | pytest 执行 → evidence 完整性检查 → hash 验证 → artifact count 验证 → Upload artifact |
| Accepted plan §8 closure matrix | plan 全文 | 要求 R11 4/4 + R12 9/9 + canary scan 全部通过才能关闭 WIN4-F01/F02/F03 和 AR-F07 |
| Implementation artifact 标记 | `implementation-codex.md:14` | `REAL_WINDOWS_PENDING / STOPPED_AT_S1_IMPLEMENTATION` |
| Zero-change artifact 标记 | `code-review-fix-codex.md:5` | `REAL_WINDOWS_PENDING / READY_FOR_CONTROLLER_VALIDATION` |

**本地 macOS skip 不构成真实 Windows closure。** ✓

**6.2 不引入统一 authorization/secret infra**

- 零新增 `os.environ` 读取（除既有 `_WINDOWS_ARTIFACT_DIR_ENV` 行 97）
- 零新增 API key / secret / token 处理
- 零新增 `FMP_API_KEY` 引用（只在既有 POSIX infer tests 行 306–341 中使用，非 S1 diff）
- 零新增 GitHub Secrets / `GITHUB_ACTIONS` / `GITHUB_RUN_ID` 引用

**6.3 不涉及禁止 Issue**

```bash
rg 'Issue 142|Issue 151|Issue 175|Issue 177|Issue 178|web_tools_storage_states' \
  tests/cli/test_upload_filings_from_command.py
# 零输出
```

**维度 6 结论: PASS。真实 Windows pending 正确表达，不误报 closure，不引入禁止 infra/Issue。**

---

## Complete semantic ownership chain verification

S1 unstaged 变更涉及的每一个业务事实，从 owner 到消费者的完整链路:

| 业务事实 | Owner | Owner evidence | S1 consumer | Consumer evidence | 漂移? |
|---------|-------|---------------|-------------|-------------------|------|
| "上传是否成功" | Fins storage published state | `FsCompanyMetaRepository.get_company_meta()` + `FsSourceDocumentRepository.list_source_document_ids()` + `read_source_snapshot()` | test: 行 982–1006 | 通过 typed repository contracts 读取 published tree，不复用 stdout/stderr/raw JSON | 否（从 stdout 漂移到 storage owner，方向正确） |
| "company name 是否传入" | Test-local oracle | `_assert_single_windows_upload_company_name`（行 1086–1125） | test: 行 967–970 | 逐 token 解析 batch 脚本中的 `--company-name` arg | 否（不变） |
| "上传产生了哪些文件" | Fins storage published portfolio | `FsSourceDocumentRepository` + `rglob` physical check | test: 行 1007–1010 | 仅 `assert source_artifacts`（非空），不解析业务语义 | 否 |
| "filing 的 primary document" | `SourceSnapshotProtocol.primary_filename` | storage owner 从 persisted meta `primary_document` 字段投影 | test: 行 1003–1006 | `snapshot.primary_filename == source_path.name` + `in descriptor_names` | 否 |
| CLI renderer | `dayu/cli/upload_script.py` | `render_upload_script()` + `publish_upload_script()` | 未修改 | — | 否 |
| Fins batch plan | `dayu/fins/upload_batch.py` | `generate_upload_batch_plan()` | 未修改 | — | 否 |
| 缺 company-name fail closed | `dayu/fins/pipelines/upload_company_meta.py` | 既有关键 pipeline | 未修改 | — | 否 |
| Script hash integrity | `hashlib.sha256(script_path.read_bytes())` | test oracle 写入（行 1018–1020） | R11 workflow cross-verify（行 157–159） | `Get-FileHash -Algorithm SHA256` → lowercase compare | 否（不变） |
| Physical artifact count | `len(source_artifacts)` | test oracle 写入（行 1021） | R11 workflow cross-verify（行 165–170） | `Get-ChildItem -File -Recurse` → count compare | 否（不变） |

零跨层 fallback、零 `hasattr`/`getattr`、零 loose parsing、零兼容 shim、零测试固化。所有事实均从唯一 owner 读取。**语义所有权零漂移。**

---

## Adversarial failure pass — 完整重走

对以下关键对抗场景逐路径重走:

### A. 并发写入
`read_source_snapshot` 内部使用 `_acquire_publication_guard`（filelock）保护 published tree 并发读取。若上传在 snapshot 读取期间发生，`SourceSnapshotConsistencyError` 被抛出。测试不捕获此异常 → test error（fail closed）。✓

### B. 孤儿状态
`_windows_test_artifact_directory` 通过 `shutil.rmtree(artifact_directory, ignore_errors=True)` + `mkdir()` 确保 clean state。若前次 run 留下孤儿文件，`rmtree` 清理。若 `rmtree` 失败（权限/锁定），`mkdir` 抛出 `FileExistsError` → test error。✓

### C. 跨平台路径注入
`source_path.name` 在不同平台返回纯 basename。Windows 上 `C:\tmp\2024FY_AAPL_Annual_Report.htm` → `"2024FY_AAPL_Annual_Report.htm"`。POSIX 上 `/tmp/2024FY_AAPL_Annual_Report.htm` → `"2024FY_AAPL_Annual_Report.htm"`。与 `primary_filename` 比较不受路径分隔符影响。✓

### D. 重复执行（幂等性）
本测试使用 `--action create`。若 storage 中已存在同 ticker+filing，`create_source_document` 抛 `FileExistsError` → generation 非零退出 → 行 966 AssertionError → test failure。不幂等吸收，fail closed。✓

### E. 超大文件
`_FIXTURE_SOURCE` 是 Apple 10-K HTML（~13MB）。`materialize_files=False` 不复制内容到临时树。light snapshot 只读取 meta JSON 和 descriptor，内存开销恒定。`rglob` 不读文件内容。✓

### F. 空 portfolio
若上传成功写入了 meta 但未写任何 portfolio 文件（非正常情况），`rglob` → `assert source_artifacts` 失败。✓

### G. Unicode 路径
`source_dir / "2024FY_AAPL_Annual_Report.htm"` 不包含非 ASCII 字符。fixture 文件名来自 SEC filing system（纯 ASCII）。若未来使用含 Unicode 的文件名，`Path` 在 Windows（UTF-16 LE）和 POSIX（UTF-8 bytes）上均正确处理——但这超出 S1 scope。✓

全部对抗场景 fail closed 或正确防御。零静默成功路径。

---

## Findings

未发现实质性问题。

### 从第一性原理二次确认

本轮重审的动机是执行 Controller 要求的"完整 re-review unchanged target 与 no-action 裁决"。经完整重走:

1. **Immutable payload 完整走读**: 对 `tests/cli/test_upload_filings_from_command.py` 的全部 1226 行逐行重走，特别对 S1 unstaged diff 影响的 `test_windows_generated_script_runs_real_cli_into_temp_storage`（行 911–1030）及其所有直接/间接依赖（`_windows_test_artifact_directory`、`_assert_single_windows_upload_company_name`、`_parse_windows_batch_fixed_argv`、`_decode_windows_batch_fixed_token`、`_parse_single_windows_crt_argument`）进行完整数据流追踪。

2. **Direct Fins contracts 二次确认**: 重新读取 `SourceSnapshotProtocol`、`CompanyMetaRepositoryProtocol`、`SourceDocumentRepositoryProtocol` 的全部 contract（含 Raises），确认 S1 consumer 正确消费契约而不重复测试 owner semantics。

3. **Controller 五项 no-action 裁决核对**: 逐一还原证据，确认五项裁决均成立，不存在被 no-action 掩盖的真实 code/material finding。

4. **Six-dimension adversarial re-verification**: 对 display 零回流、exit→storage→oracle 顺序、snapshot lifecycle/fail closed、company-name oracle/schema、typing/tests/security、real Windows pending 六维度逐行重走。

5. **Semantic ownership chain 复核**: 确认全部 9 个业务事实的 owner→consumer 链路无漂移。

**本轮重审未发现初始 DS review、AgentMiMo review 或 Controller adjudication 遗漏的 material finding。**

---

## Open Questions

无。

---

## Residual Risk

1. **真实 Windows R11 与 R12 embedded-R11 same-run evidence 仍 pending**: 本地 macOS `pytest` 中真实 `cmd.exe` nodes 按 `os.name != "nt"` skip。这是 accepted plan §8 的预期状态——所有 slices accepted 后由 Controller 按 §13.8 dispatch fresh R11 与 R12 embedded-R11 evidence。本 review 基于 contract trace、跨平台路径分析、lifecycle 验证和 fail-closed 矩阵确认代码路径逻辑正确，但不能替代真实 `cmd.exe` 下 `FsCompanyMetaRepository` / `FsSourceDocumentRepository` / `read_source_snapshot` 的物理行为验证。分类: `covered by later authorized closure gate`。

2. **WIN4-RW-S2（setx native stdio/timeout owner）与 WIN4-RW-S3（outer process safe failure projection）尚未实施**: S1 不依赖它们，但它们未完成前整体 AR-F07 closure 不可声称。分类: `covered by later authorized slices`。

3. **POSIX real workflow test 仍使用 display success dependency**: `test_posix_generated_script_runs_real_cli_into_temp_storage`（行 842）使用 `"Fins succeeded"` 展示断言加 `meta.json` rglob 作为双重验证。这不属于 S1 scope（plan §3.1 allowlist 未含 POSIX 测试修改），不是 S1 regression。若未来需要统一 POSIX 与 Windows 验证模式，应由独立 plan slice 处理。Controller 已将此列为 out-of-scope。分类: `pre-existing / not current slice`。

4. **Full Ruff 142 项 baseline**: pre-existing，本 slice 精确证明集合与 digest 不变（`bcb9e45754ecb183a69859480a286c2c5e3504fb10b1db3958bf44a9deaa2be3`）。分类: `pre-existing baseline / not current residual`。

5. **Unstaged changes 未 commit**: 本 review 验证其正确性，但不拥有 commit/stage 权限。commit 由 Controller 在双路 PASS 后执行。

---

## Decision

**PASS** / 0 new findings / 0 backflow findings / 0 blocker / Controller 五项 no-action 裁决全部确认成立 / S1 immutable payload unchanged target 完整重审通过 / REAL_WINDOWS_PENDING

### New findings vs backflow findings

- **New findings（本轮新发现）**: 0。本轮对 unchanged target 的完整重审未发现初始 DS review、AgentMiMo review 或 Controller adjudication 遗漏的 material finding。
- **Backflow findings（初始 review 已报告但被 Controller no-action 驳回的 finding）**: 0。Controller 的五项 no-action 裁决均针对 reviewer 观察（路径引用、文字错误、计数、scope 外观察、实现推测），不涉及实际代码 defect。本轮逐一核对后确认无 backflow。

### Blocker

0。不存在阻止 S1 commit 或 S2 proceed 的 correctness/semantic ownership/security/deferred 问题。

### Remote residual

真实 Windows R11 与 R12 embedded-R11 same-run evidence 是唯一未闭合的 remote risk。Controller 必须在所有 slices accepted 后按 plan §13.8 dispatch fresh evidence 并独立验证。本 review 的 PASS 结论仅适用于本地 code review 可验证的 contract correctness、semantic ownership、fail-closed 行为与 evidence chain integrity；不替代真实 Windows runner evidence。
