# WU-SEMANTIC-OWNERSHIP-01 / R12 S2 stop-condition corrected plan — adversarial plan review (AgentDS)

## 1. Gate 身份

- 本 artifact 是既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 的 R12 S2 corrected plan 的独立 adversarial plan review（第二路，AgentDS），不是新 WU，不是第一路 MiMo review 的重复。
- 本轮只做 plan review；不改 plan/code/test/control/其它 artifact，不 stage/commit/实现。
- 目标：压测 corrected plan（634 行 / 81,713 字节 / SHA-256 `1f4df5f942a49a5c95bd60f75d0ef3e8a3cbfacede2c2d8f7ecf3c42a1436715`）关于 accepted HIGH `R12-S2-IMPL-STOP-F01` 的 closure 是否真正成立。

## 2. Authority hashes（完整输入）

| Artifact | 行数 / 字节 | SHA-256 |
|---|---:|---|
| AGENTS.md | 128 / 10,036 | `cb26618ab566804c97a3ef2f269537b7313e59370e5ddd0258d9b753b08ac45e` |
| Corrected plan `docs/host/wu-semantic-ownership-01-r12-init-workflow-plan.md` | 634 / 81,713 | `1f4df5f942a49a5c95bd60f75d0ef3e8a3cbfacede2c2d8f7ecf3c42a1436715` |
| Plan-fix artifact `docs/reviews/wu-semantic-ownership-01-r12-s2-stop-condition-plan-fix-codex.md` | 95 / 10,202 | `ca0b3f9287c266b9776adfc8dff9373a36d824e70b191f753388213a3980b43b` |
| Plan-fix Controller validation `docs/reviews/wu-semantic-ownership-01-r12-s2-stop-condition-plan-fix-controller-validation.md` | 90 / 5,059 | `d715add66c544919116021e14f0c9c128ff1dafccc8cf05aaf2324fe1a659bbf` |
| Implementation stop handoff `docs/reviews/wu-semantic-ownership-01-r12-s2-implementation-codex.md` | 155 / 9,139 | `b123dff616a0c4ac22bb3d1f47b00fe5913a9747e9f3e413ff34462ddbd82fcd` |
| Controller stop adjudication `docs/reviews/wu-semantic-ownership-01-r12-s2-stop-condition-controller-adjudication.md` | 89 / 5,770 | `f2bb4029d83716e5e2a18e16fe1ac8c7970db7396adf54e951d9378ae4e3785c` |
| Updated S2 authorization `docs/reviews/wu-semantic-ownership-01-r12-s2-controller-authorization.md` | 96 / 6,667 | `259abecca9fb36112013dcc3be72320d9fe824604ca39eeddb44936f779c2f86` |

直接代码证据（均已完整读取并用于本 review）：

| 代码文件 | 关键行 | 证据要点 |
|---|---|---|
| `dayu/service/host_assembly.py` | L122, L1461-L1503 | `_FINS_WORKSPACE_ROOT_CONFIG_FIELD = "workspace_root"`；`_effective_fins_workspace_root_config_value` 在 provider config 未显式配置时把传入 `workspace_root` 注入 effective config |
| `dayu/service/host_assembly.py` | L528-L545, L1424-L1458 | `assemble_effective_tool_provider_configs` 对每个 Fins provider 调用上述解析并注入 effective config |
| `dayu/service/host_assembly.py` | L477-L510 | `discover_service_tools` 真实执行 provider binding |
| `dayu/fins/service_runtime.py` | L338-L379 | `DefaultFinsRuntime.create(workspace_root=...)` → `build_fs_repository_set(workspace_root=...)` → `FsFinsIngestionJobStore.from_workspace_root(workspace_root)` |
| `dayu/fins/storage/_fs_repository_factory.py` | L24-L57 | `build_fs_repository_set` → `FsStorageCore(workspace_root=..., create_directories=True)` |
| `dayu/fins/storage/_fs_storage_core.py` | L23-L30 | `FsStorageCore` 继承 `_FsStorageInfra` |
| `dayu/fins/storage/_fs_storage_infra.py` | L397-L451 | `_FsStorageInfra.__init__` 创建 `portfolio_root = workspace_root / "portfolio"` 并在 `create_directories=True` 时 `mkdir(parents=True, exist_ok=True)`；`_ensure_batch_storage_dirs()` 创建 `.dayu/repo_batches` 等 |
| `dayu/fins/ingestion_runtime.py` | L1511-L1526 | `FsFinsIngestionJobStore.__post_init__` 执行 `self.root_dir.mkdir(parents=True, exist_ok=True)` 创建 `.dayu/fins_ingestion/jobs` |

Probe 磁盘证据：`workspace/tmp/r12-s2-probe-a` 中真实 discovery 在 publication 前创建了 `portfolio/`、`.dayu/repo_batches`、`.dayu/repo_backups`、`.dayu/batch_recovery.lock`、`.dayu/fins_ingestion/jobs`（见 implementation stop handoff §3）。

## 3. Review posture 与 scope

本 review 是对 corrected plan 的 constructively adversarial 压测。默认假设 plan 可能在 subtle、高成本处失败，直到证据证明足够可靠。

压测重点（按用户指定）：
- private validation root/container owner 唯一性
- real discovery 与 13/3 boundary
- identity/containment/no-follow cleanup/parent fsync 可实现性与 public path 安全
- 删除后 fsync 失败 truth
- RESET/public identity/四态
- pre-publication validation fault 与 post-publication warning 分界
- fault matrix、real side-effect/public byte+identity/zero-diff/no synthetic shim 的测试可执行性
- overdesign/coupling/遗漏反例

每个 finding 标注：status（`accepted-candidate`）、severity、owner、精确 plan 修复建议。

## 4. R12-S2-IMPL-STOP-F01 closure 判定

### 4.1 Core mechanism audit：workspace_root 重定向

Corrected plan 的唯一实质修改：把传给 `assemble_effective_tool_provider_configs(..., workspace_root=...)` 的参数从 public workspace 改为 transaction-private staging 内的 dedicated validation workspace root。

直接代码证据证明该机制正确：
- `_effective_fins_workspace_root_config_value`（host_assembly.py:1480-L1483）在 provider config 没有显式 `workspace_root` 时，返回 `str(workspace_root.expanduser().resolve(strict=False))`——即完全使用调用方传入的值。
- Package default config 的 Fins provider configs 均不包含显式 `workspace_root` 字段（entry `RuntimeConfig` 以此为默认），因此传入的 private root 会完整支配 side effect 位置。
- `_FsStorageInfra.__init__`（_fs_storage_infra.py:433-451）把 `self.portfolio_root` 构造为 `self.workspace_root / "portfolio"`，所有 `mkdir` 均相对于该 root。
- `FsFinsIngestionJobStore.__post_init__`（ingestion_runtime.py:1526）的 `mkdir` 也相对于 `workspace_root`。

**判定**：mechanism 正确。workspace_root → effective config → Fins runtime → filesystem side effect 的完整链中，每一环都使用传入 root，无硬编码路径、无环境变量 shortcut、无 bypass。

### 4.2 Owner uniqueness audit

Corrected plan §3 语义所有权表新增行：

> `private validation workspace 内 Fins runtime layout/content` 的 owner 是 Service/Fins production；`init_workspace.py` 只拥有 private container 的 identity、containment、pre-publication cleanup 与 durability

该拆分精确：container lifecycle（创建、身份锁定、清理）与 container content（Fins 在 root 内创建的 `.dayu`/`portfolio` 内部结构）分属不同 owner。`init_workspace.py` 的 no-follow recursive delete 不需要理解内部语义。

无 split-brain：container 的创建和销毁都在 `init_workspace.py`；content 的产生在 Service/Fins。两者通过 private root path 交接，不共享可变状态、不互相调用、不形成循环依赖。

**判定**：owner 唯一性成立。

### 4.3 13/3 boundary audit

Corrected plan §6.4 step 3 保留：
- 13 个 production runtime manifests 经真实 Service effective-provider assembly/discovery 验证
- 3 个 `smoke_host_public_*` manifests 仅由 test-owned explicit `manual-smoke` catalog fixture 验证
- 同一真实 `SceneToolCatalog.from_tool_bundle` 复用于全部 13 次 `prepare_scene`
- 两个 locked required slots `{"current_time": "", "fins_default_subject": ""}`

workpace_root 重定向不影响 catalog 内容：discovery 产生的 `tool_bundle` 是 in-memory 结构，不由 workspace_root 决定。13 个 manifests 的 `prepare_scene` 使用 staging config 中的 scene 定义 + in-memory catalog，不依赖 private root 的内部结构。

**判定**：13/3 boundary 成立，real discovery 保留。

### 4.4 Cleanup 可实现性 audit

Corrected plan §6.3 的 cleanup 序列：
1. 传入 assembly 前记录 private validation root 的 identity（resolved path + 类型）
2. 13 个 manifests 全部通过后，重新核验 root identity/containment
3. no-follow 递归删除整棵 private validation tree
4. `fsync` private staging parent directory

**可实现性分析**：

| 步骤 | 依赖 | 可执行性 |
|---|---|---|
| identity recording | `Path.resolve()` + `lstat` | POSIX 标准操作，trivial |
| identity re-verification | 同上 | trivial |
| no-follow delete | `shutil.rmtree` + 预先的 symlink 检查 | 可行；需注意 permission 边界（见 Finding DS-F02） |
| parent fsync | `os.open(parent, O_RDONLY)` + `os.fsync(fd)` | 可行；需注意平台差异（见 Finding DS-F03） |

public path 安全：cleanup 只操作 recorded identity 下的路径，该路径位于 workspace 内的 transaction-private staging 子目录。identity re-verification 防止 TOCTOU（time-of-check-time-of-use）替换。containment check 防止路径越界。plan 明确禁止任何情况下触碰 public `.dayu`/`portfolio`/`assets`。

**判定**：可实现，public path 安全。存在可管理的实现细节风险（见 findings）。

### 4.5 RESET / public identity / 四态 audit

Corrected plan §6.4 与 §15：
- RESET 在 validation 期间保持 public `.dayu` 不变（因为 validation 在 private root 进行）
- RESET publication 越过 boundary 后仍按四态 contract 移除 public `.dayu`（移到 backup）
- FIRST 不创建/删除 public `.dayu`
- PRESERVE/OVERWRITE public `.dayu` 不变
- public `portfolio`/`assets` 在任何状态下均不创建、不删除、不修改

validation 使用 private root 后，RESET 的 validation 阶段不再触碰 public `.dayu`，自然满足"validation 期间不变"的要求。publication 阶段的 contract 未修改。

**判定**：四态语义完整保留，无 contradiction。

### 4.6 Fault boundary audit

Corrected plan §6.4 step 4 与 step 7 建立两条不可互换的 fault boundary：

| boundary | 时机 | fault 行为 | public impact |
|---|---|---|---|
| pre-publication validation cleanup | 13 manifests 通过后、config publication 前 | abort，保留 staging path，不 publish | public roots 不变 |
| post-publication backup cleanup | publication success boundary 之后 | typed warning，不 rollback | config 已发布 |

**关键区分验证**：
- plan §6.3 明确 "validation workspace cleanup 必须在 config publication 前重新核对 root identity/containment"，且 "identity/type/symlink 漂移、删除失败或 parent `fsync` 失败都属于 pre-publication abort"
- plan §6.4 step 8 明确 backup cleanup failure "不 rollback、不把已发布 config 报告为失败、不改变 init 成功 exit status"
- plan §6.4 step 4 明确禁止把 validation cleanup fault "降级成 publication 后 warning"
- plan §6.4 step 8 明确 "该 post-publication backup cleanup fault 与第 4 项 pre-publication validation cleanup fault 是两个不同边界，禁止复用 warning 语义"

**判定**：两边界语义清晰、互斥、不可互换。

### 4.7 F01 closure 整体结论

`R12-S2-IMPL-STOP-F01` 的核心矛盾——"真实 Service discovery 的 filesystem side effect 与 pre-publication no-mutation contract 冲突"——已通过 workspace_root 重定向到 transaction-private validation root 得到纠正。该纠正：

- 不修改 Service/Fins production（零 production diff）
- 不降低 validation 真实性（同一 Service assembly 链）
- 不扩张 managed-root manifest（public portfolio/assets 不加入）
- 不引入 synthetic/fake provider、metadata-only discovery、duplicate parser、test shim
- 不改变产品裁决（FIRST/PRESERVE/OVERWRITE/RESET）

**F01 已闭合。** 以下 findings 是 plan 在可实施性、边界条件与测试可执行性上的 residual risks，不是 F01 未闭合的证据。

## 5. Findings

### 5.1 DS-F01 — fsync fault injection 机制未指定（MEDIUM / accepted-candidate）

- **位置**：Corrected plan §8 S2 必须断言段："对 validation root ... private parent-fsync failure 分别注入故障"
- **问题类型**：测试缺口 / 不可直接实施
- **当前写法**：要求测试覆盖 "private parent-fsync failure" 并断言 pre-publication abort，但未指定故障注入机制。
- **反例/失败场景**：cleanup 函数内部执行 `fd = os.open(parent, os.O_RDONLY); os.fsync(fd); os.close(fd)`。在正常文件系统上，对有效 fd 的 `os.fsync` 不会失败（除非触发 ENOSPC/EIO）。要让 `os.fsync` 在测试中有控制地失败，需要以下至少一种机制：
  - `unittest.mock.patch('os.fsync', side_effect=OSError(...))`——这是 Python 标准 mocking，但 plan §9.2 的 "test shim" prohibition 若被严格解读可能覆盖它；
  - 在 cleanup 函数中引入可选的 `fsync_callable` 参数——这引入了仅服务于测试的 production seam，违反 CLAUDE.md 的 "禁止胶水 seam" 约束；
  - 在 cleanup 前 close fd 然后传 closed fd 给 fsync——这要求 cleanup 函数的 fd 生命周期可被外部操纵，同样引入 seam。
- **为什么有问题**：plan 没有澄清"注入故障"的实施方式。如果 implementation agent 被 "no test shim" 约束阻止使用 `unittest.mock.patch`，且不能引入 test-only seam，则 fsync failure path 无法测试——而 plan 要求它被测试。这会导致实现时要么跳过该测试（留下未覆盖 fault path），要么引入违反 plan 自身约束的 seam。
- **直接证据**：
  - plan §9.2 scans 要求 "禁止 synthetic/fake/metadata-only/test shim"；
  - plan §8 S2 断言要求覆盖 fsync fault；
  - CLAUDE.md 禁止 "胶水 seam" 和 `hasattr/getattr` 作为边界设计逃逸；
  - `os.fsync` 在正常文件系统上对有效 fd 几乎不会失败，需要控制性故障注入。
- **影响**：implementation agent 可能在 test 和 constraint 之间两难，导致 fsync fault path（pre-publication abort 的关键路径之一）未被测试覆盖。
- **建议改法和验证点**：
  1. 在 plan §8 S2 或 §10.3 中明确：对 OS-level 系统调用（`os.fsync`、`os.open`、`shutil.rmtree`）的故障注入允许使用 `unittest.mock.patch`，这不属于 "test shim"（test shim 指替换整个 Service/Fins provider chain 或 catalog construction 的 fake）；或
  2. 将 cleanup 函数设计为接受 `_fsync: Callable[[int], None] = os.fsync` 默认参数，在 plan 中明确这属于 "朴素接口参数" 而非 "胶水 seam"。
- **修复风险**：低（只需在 plan 中加一行说明）
- **严重程度**：中（不修复可能导致 implementation agent 跳过关键 fault path 测试）

### 5.2 DS-F02 — rmtree partial failure 后 retained path 诊断价值降低（LOW / accepted-candidate）

- **位置**：Corrected plan §6.3 cleanup 段："任何失败路径都不得触碰 public `.dayu`、`portfolio`、`assets` 或旧 `config`"，以及 "必须保留并报告可定位的 transaction-private staging path"
- **问题类型**：状态机漏洞 / 契约缺失
- **当前写法**：plan 承诺 cleanup 失败时 "保留并报告可定位的 transaction-private staging path 供诊断"，但未区分 "完全未删除"与"部分删除"两种故障状态。
- **反例/失败场景**：`shutil.rmtree` 的 `onerror` 机制在删除部分文件后遇到 `PermissionError`。此时 private validation tree 可能处于：`portfolio/` 已删除、`.dayu/repo_batches/` 已删除、`.dayu/fins_ingestion/jobs/` 仍存在（因该目录下某文件的权限阻止删除）。retained staging path 仍然可定位，但内部状态不完整——diagnostic 价值降低。
- **为什么有问题**：plan 的 "保留可定位 staging path" 承诺在 partial deletion 场景下仍然成立（staging 目录仍在），但其诊断充分性打了折扣。这不是功能正确性问题（abort 仍正确触发，public roots 仍不受影响），但在真实排障时，用户/开发者看到的 private tree 可能不包含完整的 Fins side effect 证据。
- **直接证据**：plan §6.3 "保留并报告可定位的 transaction-private staging path 供诊断"；`shutil.rmtree` Python 文档的 `onerror` 行为。
- **影响**：排障信息不完整；不影响 correctness（abort 正确，public roots 安全）。
- **建议改法和验证点**：在 plan §6.3 或 §10.1 中补充一句：partial deletion 后 staging path 内部状态可能不完整，diagnostic 应以 retained staging path + 删除异常类型/路径为准。无需改变 abort 行为。
- **修复风险**：低（文档级补充）
- **严重程度**：低（不影响正确性、安全性或四态 contract）

### 5.3 DS-F03 — PRESERVE 路径中用户显式 provider workspace_root 可绕过 private root（LOW / accepted-candidate）

- **位置**：Corrected plan §6.4 step 3 的 workspace_root 重定向 + `_effective_fins_workspace_root_config_value` 的实际行为
- **问题类型**：契约缺失 / 边界条件遗漏
- **当前写法**：plan §6.4 step 3 要求 "assembly root 明确不是 public workspace"，将 workspace_root 改为 `<transaction private staging/validation-workspace>`。
- **反例/失败场景**：`_effective_fins_workspace_root_config_value`（host_assembly.py:1480-L1483）的逻辑是：**若 provider config 已包含显式 `workspace_root` 字段，直接使用该值，忽略传入的 `workspace_root` 参数**。对于 FIRST/OVERWRITE/RESET，staging 从 package defaults 起步——package default Fins provider configs 不包含显式 `workspace_root`，因此传入的 private root 生效。但对于 PRESERVE，staging 从现有用户 config 复制。如果用户曾手工编辑 `config.json` 为 Fins provider 配置了显式 `workspace_root`（指向其真实 workspace），则该值会进入 staging config。此时 `_effective_fins_workspace_root_config_value` 返回的是用户配置的路径，而非传入的 private root。Fins side effect 会发生在用户配置的路径上。
- **为什么有问题**：plan 声称的 "side effect 隔离到 private root" 在 PRESERVE + 用户显式配置了 provider `workspace_root` 的场景下不完全成立。不过影响极小：(1) 用户显式配置 `workspace_root` 的场景罕见；(2) 即便是真实 workspace，`mkdir(exist_ok=True)` 也是幂等的；(3) snapshot drift 检测仍会捕获 `.dayu` 变化并阻止 publish。
- **直接证据**：`host_assembly.py:1480-L1483`；plan §6.2 PRESERVE staging base = "逐字节复制现有整个 `config/`"。
- **影响**：极端边缘场景下 isolation 不完全，但有 snapshot drift 作为 defense-in-depth。
- **建议改法和验证点**：在 plan §10.1 残余风险中记录此边界条件，或（更强）在 PRESERVE staging 时对 provider config 显式移除 `workspace_root` 字段使其回到 package-default 行为。后者需评估是否改变用户配置语义。
- **修复风险**：低（记录为已知边界条件即可；移除字段方案需评估用户配置兼容性）
- **严重程度**：低（罕见场景 + defense-in-depth 存在）

### 5.4 DS-F04 — 跨平台 parent fsync 语义差异未记录（LOW / accepted-candidate）

- **位置**：Corrected plan §6.3 cleanup 段要求的 "`fsync` validation root 的 private staging parent"
- **问题类型**：契约缺失
- **当前写法**：plan 要求对 private staging parent directory 执行 `fsync` 以确保 deletion durability。
- **反例/失败场景**：
  - macOS: `os.fsync` on directory fd 受支持，行为是 sync 目录条目到 disk。
  - Linux (ext4/xfs): `fsync` on directory fd 确保目录条目（文件名→inode 映射）持久化，但**不保证已删除文件的数据块已写入 disk**。对于 `rmtree` 删除的文件，其 inode 和数据块的持久化由文件系统自身的 journal 保证，`fsync` 父目录不覆盖这些。
  - 网络文件系统 (NFS/SMB): `fsync` 语义取决于服务端实现。
  - plan §6.3 的 parent fsync 正确保证了 "目录条目中不再包含已删除的 validation root 条目"这一事实的持久化。但它不能保证 "已删除的文件内容绝对不可能被 forensic 恢复"——这是文件系统层面的固有限制，不是 plan defect。
- **为什么有问题**：plan 对 fsync 的 durability 承诺需要限定在 "目录条目持久化" 语义内。当前行文可能被解读为更强的保证。
- **直接证据**：POSIX `fsync` 规范；Linux man page `fsync(2)` 关于目录 fsync 的说明。
- **影响**：不影响 correctness。仅在需要精确审计 durability 语义时有意义。
- **建议改法和验证点**：在 plan §10.1 残余风险中注明：parent fsync 保证目录条目持久化，不保证已删除文件数据块的独立持久化（这是文件系统层面的已知限制，不影响 init 的 correctness contract）。
- **修复风险**：低（文档级补充）
- **严重程度**：低

## 6. Architecture boundary / overdesign / overcoupling 检查

### 6.1 Architecture boundary

| 检查项 | 结论 |
|---|---|
| `init_workspace.py` 新增职责（private container lifecycle）是否在其 owner boundary 内 | 是。transaction owner 管理 transaction 产生的临时路径是合理的。 |
| Service/Fins production 是否被修改 | 否。workspace_root 是既有 public parameter，not 新增 seam。 |
| 是否穿透 `dayu.runtime` 约束 | 否。private root 在 `dayu/cli` 层管理，不涉及 `dayu.runtime`。 |
| 是否违反分层 `UI → Service → Host → Engine` | 否。init (UI 层) 通过既有 Service public API 调用，不穿透 Host/Engine。 |

### 6.2 Overdesign

- 未新增通用 sandbox/runtime abstraction、cleanup framework、lifecycle manager 或 callback protocol。
- private container 的 identity/containment/cleanup 是三个具体操作，没有抽象成通用接口。
- **无 overdesign finding。**

### 6.3 Overcoupling

- `init_workspace.py` 知道 Service/Fins 会在 workspace_root 产生 side effect——这是耦合，但属于 "知道对方有 side effect 所以隔离" 的防御性耦合，不是 "知道对方内部结构所以依赖它" 的侵入性耦合。
- Service/Fins 不因 init 的行为改变任何实现。
- **无 overcoupling finding。**

### 6.4 Optimal-solution

替代方案比较：
- 方案 A（当前 corrected plan）：重定向 workspace_root → private staging 子目录。最小改动，不改 Service/Fins。
- 方案 B：修改 Service/Fins 增加 `create_directories=False` 参数。改动 allowlist 外 production，引入配置开关。
- 方案 C：在 discovery 后删除 public side effect。违反语义所有权（init 清理 Service/Fins 的副作用）。
- 方案 D：`portfolio` 纳入 managed-root manifest。违反产品裁决（见 authorization §5.2）。

当前 corrected plan 是 credible alternatives 中最优解。

### 6.5 遗漏反例

我系统扫描了以下反例类别，未发现遗漏的 material counter-example：

| 反例类别 | 检查结果 |
|---|---|
| Fins provider 使用环境变量而非 workspace_root 定位路径 | 当前代码路径全走 `workspace_root` → effective config → `_FsStorageInfra` 构造，无环境变量 bypass |
| 非 Fins provider 也有 workspace_root-dependent side effect | Web/Playwright provider 使用 `storage_state_dir` 而非 `workspace_root` 做文件系统操作；其 `discover_tools` 不创建目录 |
| discovery 本身（非 Fins）产生文件系统 side effect | `ToolsDiscovery.discover_from_bindings` 执行 import + 调用 provider entry point；非 Fins provider 的 discovery 不创建文件系统目录 |
| `SceneToolCatalog.from_tool_bundle` 有延迟文件系统访问 | `from_tool_bundle` 是纯 in-memory 构造，不接受 path 参数 |
| `prepare_scene` 间接访问 workspace_root | `prepare_scene` 使用 staging config 中的 scene 定义 + in-memory catalog，scene 路径均在 staging config 内 |
| init lock 在 validation/cleanup 期间被释放 | plan §6.3 明确 "锁覆盖... staging、校验、swap、rollback、cleanup" |

## 7. Open questions

1. **`unittest.mock.patch` 是否被 plan 视为 "test shim"？** 这决定 fsync fault injection 测试能否在不违反 plan 约束的情况下实现。建议 Controller 在 adjudication 中明确。

## 8. Residual risks

| 风险 | 归属 | 跟踪 |
|---|---|---|
| PRESERVE + 用户显式 provider `workspace_root` 时 isolation 不完整 | `init_workspace.py` / plan §10.1 | 建议在 §10.1 记录，或在 PRESERVE staging 时剥离显式 `workspace_root` |
| parent fsync 只保证目录条目持久化，不保证已删除文件数据块独立持久化 | 文件系统层固有限制 | 建议在 §10.1 记录 |
| Windows `os.fsync` 对目录 fd 的行为不同于 POSIX | 平台差异 | S3 Windows smoke 应覆盖 cleanup fault path |
| `shutil.rmtree` 的 `onerror` 行为可能导致 partial deletion | Python 标准库行为 | 不影响 correctness，diagnostic 价值降低 |

## 9. Final conclusion

**`PASS-WITH-RISKS`**

- `R12-S2-IMPL-STOP-F01` **已闭合**。core mechanism（workspace_root 重定向到 transaction-private validation root）经直接代码证据验证正确。Owner uniqueness、13/3 boundary、四态 contract、fault boundary separation 均成立。
- Material finding：**1 个 MEDIUM**（DS-F01：fsync fault injection 机制未指定），**3 个 LOW**（DS-F02/D03/D04）。
- No blocker。MEDIUM finding 不影响 plan correction 方向，只需在进入 implementation 前澄清测试中 OS-level mocking 的许可范围。
- 未发现 overdesign、overcoupling 或遗漏的 material counter-example。
- 不阻止 corrected plan 进入双路 plan review 的 Controller adjudication / closeout。

---

**Reviewer**：AgentDS（adversarial plan review，第二路）
**Timing**：20260718-101322
**Next gate**：Controller adjudication（合并 MiMo review 与本 review，判定 PASS/FAIL/Rework）
