# WU-SEMANTIC-OWNERSHIP-01 / R12 S2 corrected-plan — 第二路独立完整 final re-review (AgentDS)

## 1. Gate 身份与结论

- **Gate**: 既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` / R12 S2 corrected-plan 的第二路独立完整 final re-review，不是新 WU/sub-WU，不依赖 MiMo 结论。
- **Reviewer**: AgentDS（adversarial plan review，第二路）。
- **Review target**: `docs/host/wu-semantic-ownership-01-r12-init-workflow-plan.md`，708 行 / 105,368 字节 / SHA-256 `aa7b50a90c9623ea8dcafe8c4c651665b16b9ee3be76ec8357c4d47977fb2a4c`。
- **权限**: 只 review，不实现、不改 plan/code/test/control/其它 artifact、不 stage/commit。
- **结论**: **`PASS`** — `R12-S2-PR-F01..F06` 6/6 闭合，rejected/no-fix 保持正确，无 design contradiction，无 blocking question。

## 2. Authority hashes（完整输入，均已独立核验）

### 2.1 Plan 与 control artifacts

| Artifact | 行数 / 字节 | SHA-256 | 核验状态 |
|---|---:|---|---|
| AGENTS.md | 128 / 10,036 | `cb26618ab566804c97a3ef2f269537b7313e59370e5ddd0258d9b753b08ac45e` | ✓ |
| Fixed plan `docs/host/wu-semantic-ownership-01-r12-init-workflow-plan.md` | 708 / 105,368 | `aa7b50a90c9623ea8dcafe8c4c651665b16b9ee3be76ec8357c4d47977fb2a4c` | ✓（锁） |
| Umbrella control `docs/host/issues-implementation-control.md` | 2,297 / 564,089 | 未锁定（只读上下文） | ✓ |
| Controller adjudication (plan-review) | 94 / 10,426 | `56633e23f77c5c70dd2d6052d6a3ddd2e4ec322effbe8f009590f817fb6e2bee` | ✓ |
| AgentCodex fix artifact | 73 / 8,938 | `ba141650a8c2bc94a3e82bce63bf2b840c4255ceda64a8f431839b14146d4664` | ✓（锁） |
| Controller validation | 73 / 6,817 | `a8e692565a0c87121141a79462f33de56cb2f7a306ac63e53bff517158d706bd` | ✓（锁） |

### 2.2 双路 review artifacts（作为 context 读取，独立核验 SHA）

| Artifact | 行数 / 字节 | SHA-256 |
|---|---:|---|
| AgentMiMo final review | 276 / 23,704 | `b59e529f6371cee21279124cfe3b8d2e7f7d3c013eab8396652e641563e9bec4` |
| AgentDS final review | 293 / 25,633 | `b8e4773047caade4020a1d55847a87bfad47918c2ea33da5ae41b210b3425c32` |

### 2.3 直接代码证据（均已完整读取并用于独立核验）

| 代码文件 | 关键行 | 证据要点 |
|---|---|---|
| `dayu/service/host_assembly.py` | L528-L551 | `assemble_effective_tool_provider_configs` 当前签名为 `(provider_configs, *, workspace_root)` — 无 override 参数 |
| `dayu/service/host_assembly.py` | L1421-L1458 | `_effective_tool_provider_config` 对 Fins provider 调用 `_effective_fins_workspace_root_config_value` |
| `dayu/service/host_assembly.py` | L1461-L1503 | `_effective_fins_workspace_root_config_value` 在 `configured_workspace_root is None` 时用传入 `workspace_root`；显式配置时优先 raw 值 |
| `dayu/service/host_assembly.py` | L1550-L1566 | `_is_fins_workspace_bound_provider_config` 通过 `provider_id` / `import_path` / `source_id` / `awaiting_tool_name` 识别 Fins |
| `dayu/service/host_assembly.py` | L166-L176 | Web provider 使用独立 `playwright_storage_state_dir`，不消费 Fins workspace_root |
| `dayu/service/entrypoint_runtime.py` | L514-L517 | 当前调用 `assemble_effective_tool_provider_configs(..., workspace_root=request.workspace_root)` — 无 override |
| `tests/service/test_host_assembly.py` | L1821-L1849 | `test_fins_tool_discovery_spec_preserves_explicit_workspace_root` 锁定 ordinary runtime 保留显式 Fins root 的现行 contract |
| `tests/service/test_host_assembly.py` | L1852-L1880 | `test_fins_tool_discovery_spec_resolves_relative_workspace_root` 锁定相对路径解析行为 |

### 2.4 平台证据

| 证据 | 值 |
|---|---|
| Python 版本 | 3.11.15 |
| macOS `shutil.rmtree.avoids_symlink_attacks` | `True` |
| macOS symlink creatable | `True` |
| `shutil.rmtree` signature | `(path, ignore_errors=False, onerror=None, *, dir_fd=None)` — 无 `follow_symlinks` 参数 |
| Service test count (`test_host_assembly.py`) | 73 tests |
| `entrypoint_runtime.py` current coverage | 88% |
| `host_assembly.py` current coverage | 95% |

## 3. R12-S2-PR-F01..F06 逐项独立 closure 验证

### 3.1 R12-S2-PR-F01 — HIGH — 显式 Fins workspace root 必须受 validation-only override 支配

**Plan closure**: §3、§6.4、§8、§9

**独立验证**:

1. **动机成立**: `_effective_fins_workspace_root_config_value` (host_assembly.py:1480-1503) 在 Fins provider config 含显式绝对/相对 `workspace_root` 时直接使用 raw 值，忽略传入的 `workspace_root` 参数。`tests/service/test_host_assembly.py:1821` 直接锁定了 ordinary runtime 保留显式 root 的现行 contract。PRESERVE 模式逐字节复制现有 `config/`，合法用户显式 Fins root 会进入 staging。因此仅改变 `workspace_root` 参数的 original correction 无法隔离 PRESERVE + 显式 Fins root 场景。

2. **Owner 正确**: Plan 把 override 放在既有 `assemble_effective_tool_provider_configs` — 该函数已是 Fins effective-config 的唯一 classification/precedence owner（通过 `_is_fins_workspace_bound_provider_config` 和 `_effective_fins_workspace_root_config_value`）。CLI strip raw field 或按 `provider_id`/`import_path` 猜 Fins 都会复制 owner 并改变 PRESERVE bytes。

3. **Precedence 正确**: Plan §6.4 明确 override 无条件支配合法 raw 未配置/绝对/相对 Fins root；ordinary runtime 显式传 `None` 保留现行行为。`_is_fins_workspace_bound_provider_config` (L1550-1566) 精确识别 Fins provider（`financial-read-tools`、`financial-download-tools`、`financial-preprocess-tools`、`financial-upload-tools` 及其 import path/source id + awaiting tool）；Web provider 走独立 `playwright_storage_state_dir` 路径（L1447-1454、L1506-1546），不消费 Fins override。

4. **raw bytes 不变**: Plan §6.4 明确 "不得改写 `ToolDiscoveryProviderConfig.config`、staging/public bytes或 schema"。Override 只改变 in-memory effective config，staging/public `config.json` 中用户显式 root 逐字节保留。

5. **allowlist 正确**: S2 新增 Service allowlist 精确限于 `host_assembly.py`（effective-config owner）、`entrypoint_runtime.py`（ordinary caller）、`tests/service/test_host_assembly.py`（direct owner test）、`dayu/service/README.md`（owner contract doc）。Fins/package/Host/Engine/Tool/runtime/design/deferred ISSUE paths 继续零 diff。

6. **反例构造与验证**:
   - **PRESERVE + 显式绝对 Fins root**: 用户 `config.json` 含 `"workspace_root": "/home/user/fins-data"`。PRESERVE 逐字节复制到 staging。Validation 时 override 传入 canonical absolute private root → `_effective_fins_workspace_root_config_value` 先校验 raw 为合法绝对路径，随后 override 在 path resolution 处支配 → effective config 的 Fins root 为 private root → discovery side effect 在 private root。Published `config/` 仍含原始 `"/home/user/fins-data"`。**Plan 正确覆盖。**
   - **PRESERVE + 显式相对 Fins root**: 用户 `config.json` 含 `"workspace_root": "fins-data/"`。同上：raw `"fins-data/"` 通过校验（合法相对路径）→ override 在 path resolution 处无条件支配。**Plan 正确覆盖。**
   - **FIRST/OVERWRITE/RESET + package default (无显式 root)**: raw config 不含 `workspace_root` → override 仍支配 → 与改变 `workspace_root` 参数等价但 override 语义统一。**Plan 正确覆盖。**
   - **非 Fins provider (Web)**: `_is_fins_workspace_bound_provider_config` 对 Web 返回 `False` → `_effective_tool_provider_config` 不进入 Fins 分支 → override 不消费。Web 的 `playwright_storage_state_dir` 继续使用 ordinary public `workspace_root`。**Plan 正确隔离。**
   - **Ordinary runtime (entrypoint_runtime.py)**: 显式传 `fins_workspace_root_override=None` → raw 显式 root 优先（现行行为不变）。**Plan 正确保留。**

**Verdict**: **CLOSED**。Override 的 semantic owner、precedence、raw-byte preservation、non-Fins isolation 和 ordinary runtime preservation 均经直接代码证据验证正确。

**Residual concern** (见 §6 Finding FR-DS-F01): override 的插入点必须在 raw validation 通过后、raw path 返回前。Plan §3 的两段式 contract（先校验、合法后 override 支配 path selection）和 §10.2 stop condition 已充分覆盖，S2 owner tests 的三类合法 raw coverage 可验证 path domination 正确性。

---

### 3.2 R12-S2-PR-F02 — MEDIUM — OS fault injection 与 "test shim" 边界必须自洽

**Plan closure**: §8 fault matrix

**独立验证**:

1. Plan §8 明确 "Syscall fault injection 只允许 tests 使用 `pytest.monkeypatch` / `unittest.mock` 在实际 owner module lookup boundary 替换 `os.open`、`os.stat/lstat`、`os.fsync`、`os.replace`、`os.unlink/os.rmdir`、`shutil.rmtree` 或抛 `KeyboardInterrupt` / `OSError(ENOSPC|EIO|EPERM)`"。

2. Plan 明确 "这是 syscall fault injection，不是 provider/catalog test shim" — 区分了 OS-level mock 与 business-logic fake。

3. Plan 禁止 "Production 函数为此新增 callback、factory、profile、默认 callable 参数或 test-only branch" — 防止 test seam 泄漏到 production。

4. Fault matrix 逐行枚举了 10 个精确 fault stage（validation cleanup identity → recursive delete → POSIX sync → secret persistence → backup moves → config publish → POSIX publication sync → rollback → post-publication delete → post-publication POSIX sync），每个 stage 指定注入的 operation 和预期 owner truth。

5. **反例验证**: 若 implementation agent 使用 `unittest.mock.patch('os.fsync')` 注入 `OSError(EIO)`，这替换了 OS-level syscall，不替换 Service/Fins provider chain、catalog construction 或 business logic。**符合 plan 的 "syscall fault injection ≠ test shim" 定义。**

**Verdict**: **CLOSED**。Fault injection 机制、边界和禁止项均已精确指定。

---

### 3.3 R12-S2-PR-F03 — MEDIUM — cleanup 后 parent-fsync 失败的 retained truth 必须唯一

**Plan closure**: §6.3.1、§6.4、§8

**独立验证**:

1. Plan §6.4 step 4 明确: "validation child 已删除而 POSIX parent sync 失败时只报告仍存在的 staging/container、child absent 与 `deletion durability unconfirmed`。不得降级成 publication 后 warning。"

2. Plan §6.3.1 明确: "删除中途失败时，只承诺 transaction-private staging/container 仍可定位，并报告精确 operation、失败 path、异常类型和 partial-deletion 状态；不承诺已删除内容仍完整，不复制/快照取证树，也不新增 cleanup journal。"

3. Plan §8 fault matrix "validation delete 后 POSIX sync" row 明确: "staging/container 存在、validation child 与 quarantine 不存在；diagnostic=`validation_parent_directory_sync` + `deletion durability unconfirmed`；Windows 无此 unsupported fault point。"

4. **反例构造**: Validation tree 的 `portfolio/` 和 `.dayu/repo_batches/` 已删除，`.dayu/fins_ingestion/jobs/` 仍在（`shutil.rmtree` 中途 `PermissionError`），随后 parent fsync 失败。Plan 的 retained truth: staging/container 仍存在（含部分未删除内容），report 包含 failing operation `rmtree`、failed path `.dayu/fins_ingestion/jobs/`、异常类型 `PermissionError`、stage `validation_recursive_delete`，不声称完整取证树。**Plan 的 truth 承诺精确且诚实。**

5. Plan §10.1 残余风险记录: "validation tree 已全部删除但其 POSIX parent directory sync 失败时，唯一 retained truth 是仍存在的 transaction-private staging/container；validation child 必须不存在。"

**Verdict**: **CLOSED**。Retained truth 的三种场景（删除完成+sync 失败、删除中途失败、全部成功）均有唯一、可测试的 truth 定义。

---

### 3.4 R12-S2-PR-F04 — MEDIUM — no-follow 删除必须形成可执行的跨平台 contract

**Plan closure**: §6.3.1、§8、S3

**独立验证**:

1. **POSIX path**: Plan §6.3.1 在 `shutil.rmtree.avoids_symlink_attacks is True` 时使用 Python 3.11 fd-safe `lstat/open/fstat` traversal。macOS `.venv` Python 3.11.15 实测 `True`。Plan 要求调用时不提供吞错/重试 callback。Plan 要求前后 identity/containment 检查。**可执行。**

2. **Windows path**: Plan §6.3.1 基于 Python 3.11 官方文档: Windows 自 3.8 起 `shutil.rmtree` 不先删除 directory junction target contents，`os.stat(..., follow_symlinks=False)` 禁用 name-surrogate reparse traversal 并提供 `st_file_attributes` / `st_reparse_tag`。Plan 使用 owner-local quarantine + identity + reparse classification path:
   - Quarantine 前: no-follow `lstat`/`stat` 检查 `st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT` / `st_reparse_tag`
   - 拒绝 root/nested symlink/junction/mount-point/其他 reparse entry
   - 对已验证 ordinary tree 调用 Python 3.11 `shutil.rmtree`
   - Scan-delete race: 若 scan 与删除间出现 reparse entry，标准库只删除/拒绝该 entry，外部 sentinel 不变
   - 任何无法分类的 attribute、identity drift 或删除错误 fail closed

3. **关键区分**: Plan 不把 `avoids_symlink_attacks=False` 解释为 "所有正常 Windows init 必须失败"。`avoids_symlink_attacks` 只描述 `shutil.rmtree` 内部是否使用 fd-safe traversal；Windows 的安全路径不依赖该 flag，而是通过 quarantine 前后的显式 reparse 分类和 identity 校验实现。

4. **Pre-seeded junction vs scan-delete race 分界**:
   - Pre-seeded junction job (S3): scan 前已存在 nested directory junction 指向外部 sentinel → 在 quarantine 前被 `FILE_ATTRIBUTE_REPARSE_POINT` 检测拒绝 → pre-publication fail closed → public config 不发布 → external sentinel byte/identity 不变。
   - Scan-delete race proof: 正常 scan 未发现 reparse，但在 scan 与 `rmtree` 之间出现新 reparse entry → `rmtree` 只删除/拒绝该 entry 自身 → 外部 sentinel 不变。
   - **两者分界清晰**：前者是 pre-existing condition 导致 fail-closed，后者是 race condition 下 `rmtree` 的安全行为证明。

5. **反例**: Windows 上用户无权限创建 symlink (non-admin) → S3 job 无法创建 nested junction 测试。Plan S3 明确: "普通 symlink 仅在 runner 缺少 privilege 时按精确错误 skip，normal transaction/pre-seeded junction/root-identity/replace-failure rollback 与 scan-delete race/fault 证明不得 skip。" Junction 创建通常不需要 admin 权限（与 symlink 不同），但若 runner 确实无法创建 junction，必须保留 skip reason。

**Verdict**: **CLOSED**。跨平台 contract 基于 Python 3.11 官方文档和项目 `.venv` 直接 probe，形成可执行的 POSIX/Windows 双路径。Pre-seeded junction fail-closed 与 scan-delete race 的分界在 Controller validation follow-up 后已精确锁定。

---

### 3.5 R12-S2-PR-F05 — MEDIUM — directory durability 的平台语义必须真实

**Plan closure**: §6.3.2、§6.4、§8、S3

**独立验证**:

1. Plan §6.3.2 精确区分三个事实:
   - `fsync` 普通文件 → 提交该文件已写内容
   - parent directory sync → 提交 directory entry/namespace change
   - symlink/reparse-safe deletion → 防越界或跟随外部 target，不承诺擦除已删除数据块或阻止 forensic recovery

2. **POSIX boundary**: Plan 定义 publication success boundary 包含 staging file content sync + directory sync + 全部 replace + workspace-root directory sync。Pre-publication file/directory sync failure → abort/rollback。

3. **Windows boundary**: Plan 基于 Python 3.11 官方文档 (Windows `os.fsync` → `_commit()` for files; `dir_fd` operations 只在 Unix 工作) 诚实收窄承诺:
   - 保留普通文件 `fsync`
   - 保留 same-volume `os.replace` 的 process-visible atomic transition
   - 保留 live rollback、isolation、typed diagnostics
   - **明确不承诺** power-loss 后 directory entry crash-durability
   - **不因**缺少 directory fsync 永久拒绝正常 Windows init

4. **S3 证据要求**: 真实 Windows job 必须跑正常 FIRST→PRESERVE→OVERWRITE→RESET No→RESET Yes transaction，证明缺少 POSIX directory fsync 不阻止正常 init。

5. **Plan 不引入** `ctypes`/Win32 flush framework 来扩大承诺。这是正确的工程 tradeoff：用文档诚实替代未验证的平台机制。

6. **反例**: 若有人错误解读 "Windows 缺少 parent-directory crash-durability" 为 "Windows init 不可靠" → Plan §10.1 残余风险和 §6.3.2 明确区分了 crash-durability（power-loss 后 directory entry 可能丢失）与 process-visible atomicity（`os.replace` 保证 live process 看到完整 transition）。正常操作下 Windows init 可靠。

**Verdict**: **CLOSED**。Platform durability 语义的区分精确、诚实、有 Python 3.11 官方文档和 S3 真实 Windows evidence 支撑。

---

### 3.6 R12-S2-PR-F06 — LOW — source/propagation scans 必须随 owner 修正

**Plan closure**: §8、§9

**独立验证**:

1. Plan §8 S2 验证块精确限定 Service diff:
   ```
   test "$(git diff --name-only -- dayu/service tests/service | sort)" = \
     "$(printf '%s\n' dayu/service/README.md dayu/service/entrypoint_runtime.py \
       dayu/service/host_assembly.py tests/service/test_host_assembly.py | sort)"
   ```

2. Plan §9 S2 scans 包含:
   - `fins_workspace_root_override` scan → production non-`None` consumer 只有 R12 init validation
   - CLI classification/raw-strip negative scan → production 必须为空
   - `_is_fins_workspace_bound_provider_config` / `discover_service_tools` / `SceneToolCatalog.from_tool_bundle` positive scan → 命中唯一 production validation chain
   - `metadata-only`/`synthetic`/`fake_provider`/`test_shim` negative scan → production 必须为空
   - Fins/package/Host/Engine/Tool/runtime/design/deferred ISSUE paths tracked+untracked zero-diff

3. Plan §9.1 coverage table 覆盖 7 个累积 production 文件，各自 ≥80%。

4. **反例**: 若实现时新增 Service helper 函数但未加入 allowlist → `git diff --name-only` check 会捕获。若 CLI 代码中出现 Fins `provider_id` 字符串 → classification negative scan 会捕获。**Scans 形成完整 defense-in-depth。**

**Verdict**: **CLOSED**。Allowlist、scans、coverage 和 zero-diff scope 均与 accepted owner correction 自洽。

---

## 4. Rejected / no-fix 独立验证

### 4.1 DS-F02 独立方案：REJECT / NO FIX

**原始提出**: AgentDS 建议为 partial deletion 场景提供完整 forensic tree copy 或 pre-snapshot。

**Controller 裁决**: 拒绝。Partial deletion 后 diagnostic tree 可能不完整是删除失败的固有事实；当前 owner 只需保留可定位 staging path 和精确异常阶段。

**独立验证**: Plan §6.3.1 已明确 "不承诺已删除内容仍完整，不复制/快照取证树，也不新增 cleanup journal"。Partial deletion 场景下，真实 retained truth 是仍存在的 staging/container（含部分未删除内容）+ 精确 failure stage/path/异常类型。完整 forensic copy 在 pre-publication abort 场景下诊断价值有限（abort 本身已阻止 publication，retained staging 已足够定位问题），且会增加 I/O 和复杂度。**拒绝正确。**

### 4.2 MiMo Finding 003：REJECT / NO FIX

**原始提出**: AgentMiMo 建议为 RESET 双 root snapshot 增加 single-syscall atomic 或扩展 Host/process lock。

**Controller 裁决**: 拒绝。两个 managed roots 的 snapshot 不是单 syscall 原子是已知 residual。init lock 已串行化 init writers；非 init writer 竞争由 reset 前强警告、锁后 identity 复核和现有 residual owner 承接。

**独立验证**: Plan §6.3 lock 覆盖从第二次 snapshot、选择、staging 到 cleanup 的全过程。Lock 串行化所有 init 进程。非 init Dayu 进程对 managed root 的并发写入属于 §10.1 残余风险 "RESET 仍可与外部 writer 竞争"，由 reset 前强警告用户停止 active Dayu 进程缓解。扩展到 Host/process lock 或 filesystem watcher 会突破 R12 scope 和 Host 进程治理 owner。**拒绝正确。**

---

## 5. Counter-example stress tests（用户指定重点）

### 5.1 PRESERVE 显式绝对/相对 Fins root 与 raw byte truth

**Stress**: 用户 `config.json` 含 `"workspace_root": "/home/user/existing-fins-data"`。PRESERVE mode 下 init 逐字节复制到 staging → validation 运行 → publication。

**Trace**:
1. PRESERVE staging: 用户 `config.json` bytes（含 `"workspace_root": "/home/user/existing-fins-data"`）逐字节复制到 staging
2. Staging `RuntimeConfig` 由真实 `ConfigLoader` 加载 → `ToolDiscoveryProviderConfig.config` 含 `{"workspace_root": "/home/user/existing-fins-data"}`
3. `assemble_effective_tool_provider_configs` 收到 `fins_workspace_root_override=<canonical absolute private root>`
4. `_is_fins_workspace_bound_provider_config` → `True`
5. Raw `"/home/user/existing-fins-data"` 通过 type/non-empty 校验（合法绝对路径）→ override 在 path resolution 处无条件支配 → effective config 的 `workspace_root` = `<private root>`
6. `discover_service_tools` → `DefaultFinsRuntime.create(workspace_root=<private root>)` → side effect 在 private root
7. Validation 通过 → cleanup private root → publish
8. Published `config/` 仍含原始 `"workspace_root": "/home/user/existing-fins-data"` bytes
9. Public `.dayu`/`portfolio`/`assets` byte/identity 不变

**Verdict**: **PASS**。Raw byte truth 保留，override 隔离完整。

### 5.2 Override 对 ordinary runtime/Web/非 Fins 的隔离及 Service owner 最小性

**Stress 1 — Ordinary runtime**: `entrypoint_runtime.py` 调用 `assemble_effective_tool_provider_configs(..., workspace_root=request.workspace_root, fins_workspace_root_override=None)`。`_effective_fins_workspace_root_config_value` 对未配置 Fins root 注入 `request.workspace_root`，对显式绝对/相对 root 保留 raw 值。**现行行为不变。**

**Stress 2 — Web provider**: `_is_fins_workspace_bound_provider_config` 对 `web-tools` provider 返回 `False` → 不进入 Fins effective-config 分支 → `fins_workspace_root_override` 不消费。Web `playwright_storage_state_dir` 继续使用 `_effective_web_storage_state_dir_config_value` → 只消费 ordinary `workspace_root`。**隔离正确。**

**Stress 3 — 非 Fins 非 Web provider** (如 future custom provider): `_is_fins_workspace_bound_provider_config` 对未知 provider 返回 `False`（除非其 `provider_id`/`import_path`/`source_id` 命中 Fins 常量或含 awaiting tool name）→ override 不消费。**隔离正确。**

**Stress 4 — Service owner 最小性**: 变更只在 `assemble_effective_tool_provider_configs`（新增一个 keyword-only 参数）和其下游 `_effective_fins_workspace_root_config_value`（新增 override 短路逻辑）。不改变 `_is_fins_workspace_bound_provider_config`、不新增 provider classification、不修改 Fins/Web provider 实现、不改变 discovery chain。**最小性成立。**

**Verdict**: **PASS**。

### 5.3 Default 参数是否形成 compat/fallback

**Stress**: `fins_workspace_root_override: pathlib.Path | None = None` 的默认值 `None`。

**分析**:
- `None` 是 "no override" 的语义正确默认值
- Plan 要求所有已知 production caller 显式传参: `entrypoint_runtime.py` 传 `None`，R12 init validation 传 canonical absolute private root
- Plan 的 scans (§9) 正向上检查 `fins_workspace_root_override` 的 production non-`None` consumer 只有 R12 init validation
- 若未来新增 caller 忘记传参 → 默认 `None` = "no override" → 安全（不会意外隔离 Fins root）。这不是 compat shim，是 defensive default
- CLUADE.md 禁止 "兼容性代码" 指 "仅为保持旧导入路径而转发符号" / "仅为兼容旧名字而重复导出常量" / "方法体仅透传到真源模块" 的 wrapper/facade。一个语义正确的默认参数值不属于此类

**Verdict**: **PASS**。`None` 默认值是 defensive design，不是 compat/fallback。See Finding FR-DS-F01 对文档完备性的补充建议。

### 5.4 POSIX/Windows symlink/junction/reparse/TOCTOU 与 quarantine/rmtree 实际可行性

**POSIX path**:
1. macOS `.venv` Python 3.11.15 实测 `shutil.rmtree.avoids_symlink_attacks is True`
2. `shutil.rmtree` 内部使用 `os.open(O_NOFOLLOW)` + `os.fstat` fd-safe traversal
3. Quarantine 前 no-follow `lstat` → `os.replace` 到 quarantine → 重取 identity → 一致后 `rmtree`
4. TOCTOU: quarantine 后的 identity 重取防御 quarantine rename 与 delete 之间的替换
5. dangling symlink: `lstat` 检测 `S_ISLNK` → 拒绝，不进入 quarantine

**Windows path**:
1. Python 3.11 官方 contract: Windows 自 3.8 起 `shutil.rmtree` 不先删除 directory junction target contents
2. `os.stat(..., follow_symlinks=False)` 禁用 name-surrogate reparse traversal
3. `st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT` / `st_reparse_tag` 分类 reparse entries
4. Quarantine 前拒绝所有 reparse entries → 只有 ordinary tree 进入 `rmtree`
5. Scan-delete race: 若 scan 后出现 reparse → `rmtree` 只删除/拒绝该 entry → 外部 sentinel 不变

**两者共同点**:
- Quarantine → identity re-verify → safe delete 的三步模式在两种平台上均适用
- Identity 包含 canonical path、`st_dev`、`st_ino`、file type（Windows 另加 `st_file_attributes`/`st_reparse_tag`）
- 任一 identity drift fail closed

**Verdict**: **PASS**。POSIX path 已由项目 `.venv` 直接 probe 验证；Windows path 基于 Python 3.11 官方文档且不依赖 `avoids_symlink_attacks` flag。

### 5.5 Pre-seeded junction fail-closed 与 scan-delete race 分界

**Pre-seeded junction (S3 job)**:
1. Test harness 在 scan 前于 workspace 内创建 nested directory junction 指向外部 sentinel
2. Init transaction 执行 managed-root no-follow scan → 发现 reparse entry → 拒绝
3. Pre-publication fail closed → public config 不发布
4. Typed diagnostic 报告 retained staging/quarantine path、absent path、精确 failure stage
5. External sentinel 的 bytes 与 filesystem identity 不变

**Scan-delete race proof (独立)**:
1. Normal scan 未发现 reparse
2. Scan 与 `rmtree` 之间外部进程创建 reparse entry
3. `rmtree` 只删除/拒绝该 entry 自身（Python 3.11 官方 contract）
4. External sentinel 不变

**两者分界**: 前者是 pre-existing condition → reject before any mutation；后者是 race condition → prove `rmtree` safe against late-arriving reparse。Plan S3 已锁定 pre-seeded junction 必须 fail-closed，"只移除 entry" 仅限 scan-delete race 证明。**分界清晰。**

**Verdict**: **PASS**。

### 5.6 Windows crash-durability 诚实性

Plan §6.3.2 和 §10.1 明确:
- Windows 保留: file `fsync`、same-volume `os.replace`、live rollback、isolation、typed diagnostics
- Windows 不承诺: parent-directory crash-durability（power-loss 后 directory entry persistence）
- Windows 不因缺少 directory fsync 永久拒绝正常 init

这是 **honest-by-design**: 不伪造平台能力，不引入未验证的 `ctypes`/Win32 flush framework，不削弱其他安全保证。S3 real Windows job 是 release evidence。

**Verdict**: **PASS**。

### 5.7 完整 fault/rollback/typed diagnostics

Plan §8 fault matrix 覆盖 10 个精确 stage，每个指定:
- 注入的 operation
- 预期 owner truth（public roots 状态、rollback 行为、diagnostic 内容、Windows 差异）
- `OSError` + `KeyboardInterrupt` 双重覆盖
- ENOSPC 只在能实际抛出它的 boundary 注入

Plan §6.3.1 typed diagnostic 包含:
- 精确 operation（`validation_identity` / `validation_quarantine` / `validation_recursive_delete` / `validation_parent_directory_sync`）
- 失败 path
- 异常类型
- retained staging/container path
- `deletion durability unconfirmed`（适用时）

Rollback 逆序恢复：先删本 transaction 已发布的 config → 逐个 `backup → original` replace → POSIX sync workspace root。Rollback 自身失败时报告精确 stage、当前每个 public root truth 与仍存在 backup/staging path。

**Verdict**: **PASS**。

### 5.8 Exact allowlist/tests/coverage/README/scans

**Allowlist**: S1 (4 files) → S2 (S1 + 10 files) → S3 (S2 + 5 files)。每个 slice 的 allowlist 精确且可执行。

**Tests**: 每个 slice 验证块列出精确的 pytest 命令和 expected scope。

**Coverage**: 7 个累积 production 文件各自 ≥80%。Controller validation 已确认 `host_assembly.py` 95%、`entrypoint_runtime.py` 88% 当前覆盖。

**README**: Plan §8 S3 指定根 README、`dayu/config/README.md`、`tests/README.md` 的更新边界；`dayu/service/README.md` 在 S2 更新。

**Scans**: §9 列出 13 个 `rg` scan 命令，覆盖:
- Forbidden patterns (`_init_model_role`、`compat`、`fallback`、`shim`、`hasattr`/`getattr`)
- Env name exposure（允许名称，禁止 sentinel 值）
- `assets`/`portfolio`/`.dayu` 的 init workspace boundary
- `fins_workspace_root_override` consumer scan
- CLI classification/raw-strip negative scan
- `metadata-only`/`synthetic`/`fake_provider`/`test_shim` negative scan
- Service exact diff verification
- Fins/package/Host/Engine/Tool/runtime/design zero-diff verification
- Prewarm forbidden runtime assembly call scan
- Prewarm import roots scan
- Network scan

**Verdict**: **PASS**。

### 5.9 三 slices 和所有 deferred/no-code 边界

**S1**: Catalog + environment contract（纯内部，不改变 public `dayu-cli init` 行为）。**review gate 严格。**

**S2**: Workspace transaction + 四态 orchestration + Service Fins-root override。**review gate 要求逐状态、逐 fault row 审核。**

**S3**: Prewarm + POSIX/Windows real smoke + README + closeout。**review gate 要求真实 CI evidence。**

**Deferred/no-code**: Issue 142/151/175/177/178、Web/WeChat/render、Topic 8/9、统一 tool authorization——均在 §1.3 和 §10.1 明确列为非目标或残余风险。**边界清晰。**

**Verdict**: **PASS**。

---

## 6. Findings

### FR-DS-F01 — LOW — `fins_workspace_root_override` 在 effective-config chain 中的精确插入点未逐行指定

- **位置**: §3 语义所有权表、§6.4 step 3、§10.2 stop condition
- **问题类型**: 可实施性
- **当前写法**: Plan §3 明确两段式 contract：(a) "Service 仍校验 raw Fins root 的现行 type/non-empty grammar"；(b) "当 raw 值是合法未配置、显式绝对或显式相对路径时，override 无条件成为 in-memory effective Fins root，不得改写 raw bytes/schema"。§6.4 step 3 和 §8 进一步要求 override 对三类合法 raw root 无条件产出同一 canonical absolute private root、ordinary runtime 显式传 `None` 保留现行行为。
- **反例/失败场景**: 若 implementation agent 误读 "无条件支配" 为 "跳过 raw validation"，可能让 override 掩盖 raw 类型错误（如 `workspace_root: 123` 或空字符串），导致 invalid raw config 在 validation 阶段被静默覆盖而非正确 reject。Plan §3 的 "仍校验" 明确禁止此行为，但两段式 contract（先校验、合法后才由 override 支配 path selection）的精确边界未在 single sentence 中表达。
- **为什么有问题**: Implementation agent 可能对 "无条件支配" 的 scope 理解不一致——是支配 validation（错误）还是支配 path resolution（正确）。但 plan 两份直接证据已自洽：(1) §3 明确 "仍校验 raw Fins root 的现行 type/non-empty grammar"；(2) §10.2 stop condition 要求验证 "Service override不能支配合法 raw 未配置/绝对/相对 Fins root" 时停止——其措辞 "合法 raw" 隐含了 "不合法 raw 必须先被 validation 拒绝" 的前提。
- **直接证据**: `host_assembly.py:1484-1494` 的 current raw type/non-empty validation；plan §3 "仍校验 raw Fins root 的现行 type/non-empty grammar，但当 raw 值是合法...时，override 无条件成为 in-memory effective Fins root"；plan §8 要求 S2 owner tests 覆盖 "override 对未配置/显式绝对/显式相对三个合法 raw case 都无条件产出同一 canonical absolute private root"（三类均是合法 raw，未要求覆盖非法 raw 被 override 掩盖的反例）。
- **影响**: S2 owner tests 的三类合法 raw coverage 足以验证 path domination 正确性。非法 raw 被 override 掩盖的风险由 §3 的 "仍校验" 和 §10.2 stop condition 兜底，且非法 raw 本身在 ordinary runtime 也会被 reject（非 R12 引入的新行为）。**风险低，不需 plan 修改。**
- **建议改法和验证点**: 无需 plan 修改。Implementation agent 应确保 override insertion 在 `_effective_fins_workspace_root_config_value` 的 validation 通过后、raw path 返回前。S2 tests 的三类合法 raw coverage 已充分，可额外增加一个非法 raw + override 的反例测试（验证非法 raw 仍被 reject，不被 override 掩盖）以加固 defense-in-depth。
- **修复风险**: 低
- **严重程度**: 低

### FR-DS-F02 — LOW — S3 import-only prewarm 的 CURRENT transitive graph 漂移检测仅依赖测试，未在 plan 中设 stop condition

- **位置**: §7 prewarm contract、§10.2 stop conditions
- **问题类型**: 可实施性 / 契约缺失
- **当前写法**: §7 锁定 exact two roots (`dayu.cli.commands.prompt` / `dayu.cli.commands.interactive`)，要求测试证明 CURRENT transitive graph 加载 `dayu.cli.session_execution` 和 `dayu.service.entrypoint_runtime`。§10.2 stop condition 覆盖 roots 不存在或 import 需要 secret/network/runtime state。
- **反例/失败场景**: Transitive graph 未来可能新增 import-time side effect（如新模块在 import 时读取环境变量、打开 FDs、注册 signal handler）。当前 `dayu.cli.session_execution` → `dayu.service.entrypoint_runtime` 的 graph 可能因正常开发而漂移（新增 dependency），但 stop condition 只检查 "import 开始需要 secret/network/Dayu runtime state"，不检查更一般的 "import 产生不可预期的 side effect"。
- **为什么有问题**: 若 future 开发者在 `dayu.cli.session_execution` 或 `dayu.service.entrypoint_runtime` 的 import chain 中新增模块级 `log` 初始化或 config 读取，prewarm import 会触发这些 side effect 而 plan 的 stop condition 不一定会捕获（因为它们不是 secret/network/runtime assembly）。
- **直接证据**: §7 "CURRENT roots 的 transitive import 未来可能新增 import-time side effect" 已在 §10.1 列为残余风险，但未在 §10.2 中设为 stop condition。
- **影响**: Prewarm 可能产生超出 "仅 `sys.modules` import cache" 的 side effect，但现有测试（隔离 subprocess + socket/network fail-fast seam + workspace tree hash + environment snapshot）应能检测。风险低。
- **建议改法和验证点**: 可选：在 §10.2 补充 "prewarm import 产生除 `sys.modules` 外的任何可观察 side effect（文件系统、环境变量、FDs、signal handlers、log output）时停止"。当前测试已覆盖该场景，不强制修改。
- **修复风险**: 低
- **严重程度**: 低

---

## 7. Open questions

无。所有 plan 声称的代码路径、side effect、owner 边界和验证要求均经直接代码证据确认。

## 8. Residual risks

| 风险 | 严重程度 | Owner | 跟踪方式 |
|---|---|---|---|
| PRESERVE + 用户显式 Fins `workspace_root` 在 override 支配下 raw bytes 不变，但用户后续 ordinary runtime 仍使用其显式 root（非 init private root）。这是 R12 设计意图——init validation 隔离，ordinary runtime 保留用户配置。用户若误解此行为可能困惑 | 低 | `dayu/config/README.md` (S3) | README 说明 PRESERVE 的 raw config 保留语义 |
| Windows `setx` 多变量不具事务性，中途失败时已写变量无法回滚 | 低 | `init_environment.py` (S1) | 已在 §5.3 和 §10.1 记录；报告 "已写/未写" |
| 两个 managed roots 不能 single-syscall 原子替换 | 低 | `init_workspace.py` (S2) | 已在 §10.1 记录；same-volume per-root replace + reverse rollback |
| `.dayu-init.lock` 只串行 init，不阻止 Host 或其它 Dayu 进程并发写 managed roots | 低 | `commands/init.py` (S2) | 已在 §10.1 记录；RESET 前强警告用户停止 active Dayu 进程 |
| import-only prewarm 的 CURRENT transitive graph 未来可能新增 import-time side effect | 低 | `commands/init.py` (S3) | S3 隔离 subprocess test 检测；若漂移停止并交 Controller |
| Repository full Ruff 144 个历史诊断归 repository owner | 低 | Repository | R12 只对 changed paths 零诊断和 full fingerprint 零差异负责 |
| Finding FR-DS-F01: override 插入点需在 raw validation 之后、path 返回之前 | 低 | `host_assembly.py` (S2) | S2 owner tests 覆盖三类合法 raw；plan §3 两段式 contract 明确 |
| Finding FR-DS-F02: prewarm transitive graph side effect 漂移检测 | 低 | `commands/init.py` (S3) | 现有隔离 subprocess test 覆盖 |

## 9. Final conclusion

**`PASS`**

`R12-S2-PR-F01..F06` 6/6 闭合经独立、基于直接代码证据的逐项验证确认。Rejected/no-fix 两项保持正确。所有用户指定的 counter-example stress tests 通过。

Plan 的 core mechanism（Service-owned `fins_workspace_root_override` 无条件支配 Fins effective root）是对 accepted HIGH F01 的正确、最小、owner-correct 修复。POSIX/Windows 双平台 deletion safety 基于 Python 3.11 官方文档和项目 `.venv` 直接 probe，形成可执行的 contract。Platform durability 语义诚实区分 POSIX directory sync 与 Windows 收窄承诺。Fault matrix、allowlist、coverage、scans 与三 slice boundary 精确且可执行。

2 个 LOW findings（FR-DS-F01、FR-DS-F02）均非 blocker：前者由 S2 owner tests 和 §10.2 stop condition 兜底；后者由现有隔离 subprocess test 覆盖。两者不阻止 plan 进入 implementation。

**Design contradiction**: `NONE`
**Blocking questions**: `NONE`
**Accepted closure**: `6/6`
**Rejected/no-fix**: `2/2` 保持正确
**New findings**: `2` (LOW × 2)
**Implementation authorization**: 未授权（本 gate 只做 plan review）

---

**Reviewer**: AgentDS（第二路独立完整 final re-review）
**Timing**: 20260718-105326
**Output artifact**: `docs/reviews/wu-semantic-ownership-01-r12-s2-stop-condition-plan-final-rereview-ds.md`
**Next gate**: Controller final adjudication（合并本 review 与 MiMo final re-review，判定 R12-S2-PR-F01..F06 closure 与 plan PASS/FAIL）
