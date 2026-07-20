# WU-SEMANTIC-OWNERSHIP-01 AR-F07 WIN4 Real-Windows Plan Amendment Review — AgentMiMo

## Review metadata

- Timestamp（本机时钟）：`2026-07-20 05:37:27 +0800`。
- Reviewer：AgentMiMo。
- Work identity：既有 `WU-SEMANTIC-OWNERSHIP-01` umbrella remediation continuation / `AR-F07 WIN4` real-Windows
  diagnostic bounded amendment；不是新 WU。
- Reviewed target：`docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md`，完整 1045 行，SHA-256
  `79e984d6fe5fe1ce08cd1affc60b241f9691c6ba94b9ec3e75850676b9d61bb4`。
- Frozen remote code/evidence target：`b85def887e72dc69e972f42a82a18989523f8634`。
- Locked evidence runs：R11 `29703932798`；R12 `29703933666`。
- Controller validation：`docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-plan-amendment-controller-validation.md`，
  SHA-256 `2ea4080e7191e6eb656a35ce24978949896fc12a6d7c85d251cde2b5ad0a89df`。
- Conclusion：`PASS / LOW_RISK / NO_BLOCKER / IMPLEMENTATION_NOT_AUTHORIZED`。

本 review artifact 不实施 production/test/workflow 变更，不更新 control/design/README，不 stage、commit、push、dispatch
或操作 PR。

## Reviewed inputs and evidence scope

已完整读取：

- `AGENTS.md`；
- `docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md` 全部 1045 行；
- `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-failure-controller-adjudication.md`；
- `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-plan-amendment-codex.md`；
- `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-plan-amendment-controller-validation.md`；
- `docs/reviews/wu-semantic-ownership-01-ar-f07-fourth-windows-evidence-controller-adjudication.md`；
- `docs/host/issues-implementation-control.md`（current gate/状态部分）。

直接代码/测试/workflow/evidence 核对：

- `dayu/cli/output.py` — 当前 terminal summary prefix owner（`Fins summary`）；
- `tests/cli/test_upload_filings_from_command.py` — 完整文件，含 `_assert_single_windows_upload_company_name()`、
  旧 `assert "Fins result" in execution.stdout`（第 965 行）、`source_artifact_count` rglob、oracle 写入顺序；
- `dayu/cli/commands/init.py` — `_collect_environment_persistence_plan()` 的两处 `getpass.getpass()` 调用
  （第 482、494 行）、`CliInitOperationError` 定义、`_confirm()` 定义；
- `tests/cli/test_init_command.py` — `_GetpassSequence`、`_InputSequence`、`_install_ollama_inputs()` 的
  monkeypatch 模式；
- `tests/cli/test_init_smoke.py` — `_run_init()` 实现（anonymous TemporaryFile handles、Popen lifecycle、
  timeout cleanup）、`_WINDOWS_CANARY_DOMAIN` bytes literal（第 60 行）、`_github_actions_canary()`、
  `_select_windows_test_canary()`、`_render_init_timeout()`；
- `dayu/fins/storage/repository_protocols.py` — `SourceSnapshotProtocol`（context manager、ticker/document_id/
  source_kind/primary_filename/files properties）、`CompanyMetaRepositoryProtocol.get_company_meta()`、
  `SourceDocumentRepositoryProtocol.list_source_document_ids()`/`read_source_snapshot()`；
- `dayu/fins/storage/fs_company_meta_repository.py` — 构造函数接受 `workspace_root: Path`；
- `dayu/fins/storage/fs_source_document_repository.py` — 构造函数接受 `workspace_root: Path`；
- `dayu/fins/domain/document_models.py` — `CompanyMeta` 数据结构（`ticker`、`company_name` 字段）；
- CPython 3.11 `getpass.py` — `win_getpass()` 的 `sys.stdin is sys.__stdin__` 条件分支。

R12 run-specific canary 未读取、派生或回显。未读取 GitHub Secrets 或 configured production values。

## Assumptions tested

| # | Assumption | Adversarial test | Direct evidence and disposition |
|---|---|---|---|
| 1 | R11 真实 upload 是业务失败 | 检查 assertion 前的 process exit 与 published storage tree | execution 先 exit `0`；stdout 含 typed `status="ok"` summary；storage 已发布完整 company/source/Docling artifacts。假设被证伪，根因是 stale display consumer。 |
| 2 | 可用当前或另一 display prefix 替代旧词 | 比较 display renderer owner 与业务 success owner | display 由 `dayu/cli/output.py` 拥有且可演进；test 不应选择任何 prefix 作为 success oracle。替换为另一硬编码词被拒绝。 |
| 3 | raw filesystem rglob 存在即可证明业务成功 | 用 semantic-ownership 约束挑战 raw path | raw count 只证明物理 artifact 完整性；业务成功应由 public storage repositories 读取 published facts。 |
| 4 | R12 是 setx 再次 hang | 检查 input→confirmation→staging→setx 顺序 | timeout 发生在首个 required secret 读取之前，setx 尚无执行机会。假设被证伪，禁止重开 WIN4-S2。 |
| 5 | OS-level redirected handle 使 Windows getpass 消费 stdin | 检查 CPython 3.11 `win_getpass()` 对象身份条件 | `sys.stdin is sys.__stdin__` 仍成立时走 `msvcrt.getwch()`，stream 参数被忽略。root cause 成立。 |
| 6 | 修复需要 Windows 特判或 GitHub Actions 判断 | 对比 capability-based 与 platform-based 分流 | `isatty()` 是直接语义；`os.name`/`platform.system()`/GitHub Actions 是间接代理。采用 `isatty()`。 |
| 7 | test harness shim 比 production fix 更便宜 | 检查 shim 覆盖范围与 production 行为 | shim 只修单一测试入口并保留生产缺陷。被禁止。 |
| 8 | 两个 finding 可合并为一个 slice | 比较 owner、路径、blast radius 与验证矩阵 | S1 是 test success oracle，S2 是 production CLI input contract；owner/路径/回滚边界不同，精确 2 slices 合理。 |
| 9 | SourceSnapshotProtocol 无需显式 context manager 说明 | 检查协议定义与 implementation agent 可能的误解 | 协议定义了 `__enter__`/`__exit__`；plan 的"读取 snapshot"措辞未显式要求 `with` 语句。implementation agent 大概率正确使用，但措辞存在歧义。见 F-01。 |
| 10 | 现有 getpass fixtures 可无缝迁移到 `_read_secret_input` | 检查 `_GetpassSequence` monkeypatch 与 `isatty()` 分流交互 | pytest 默认 `sys.stdin` 的 `isatty()` 返回 `False`；monkeypatch `getpass.getpass` 不会生效于 redirected path。需要额外 mock `sys.stdin`。见 F-02。 |

## Required review lenses

### Architecture boundary review

`WIN4-RW-S1` 只修改 test consumer，业务事实从 `dayu.fins.storage` public repositories 读取；不把 storage 语义
复制到 CLI renderer、raw JSON 或 workflow。`WIN4-RW-S2` 只在 UI/CLI input owner 内增加模块级私有 helper；
不下沉到 `dayu.runtime`，不侵入 environment persistence、Config、Host 或 Fins。依赖方向和
`UI -> Service -> Host -> Engine` 边界没有变化。§13.3 allowlist 精确锁定 4 个 production/test 文件
（S1: 1 个 test 文件；S2: 1 个 production + 2 个 test + 1 个 README），禁止修改 output.py、init_environment.py、
test_init_smoke.py、Fins production、workflows。

### Best-practice review

方案使用 capability detection（`isatty()`）、单一 logical-line read、明确 EOF/interrupt semantics、
owner-level negative tests、动态 non-disclosure 断言、fresh remote acceptance。避免用 timeout、display text、
mock 或 warning suppression 获得假绿。README 决策与实际用户输入行为同步。

### Optimal-solution review

可信替代方案包括：修改 renderer 换 prefix、修改 harness、Windows-only input shim、PowerShell/PTY/console
wrapper、增加通用 secret infrastructure。前四项修错 owner 或制造重复语义，最后一项显著扩大 blast radius。
plan 采用两个最小 owner-local 变更，是当前证据下更简单、可测试且可演进的路径。

### Overengineering review

未增加 class/Protocol/factory/callback、跨模块 secret helper、credential broker、redaction framework、
process framework、schema 或 migration。redirected input 只增加一个模块级私有 helper；storage success 只复用
现有 public repositories。

### Overcoupling review

两个 slices 串行但没有代码依赖；只有最终 remote rerun 依赖二者同时 accepted。S1 不需要修改 Fins/output/
workflow，S2 不需要修改 harness/setx。README 与 S2 保持同一提交/回滚边界。

## Findings

### F-01-unfixed-LOW-SnapshotProtocol context manager 未在 plan 中显式要求

- **位置**: §13.2.1 第 3 点："对该 id 读取 materialize_files=False 的 storage-owned source snapshot，必须确认
  exact ticker、document id、SourceKind.FILING、primary filename 等于本次 source basename，完整 descriptor
  集合非空且包含该 primary"。
- **问题类型**: 契约缺失 / 不可直接实施。
- **当前写法**: plan 描述了"读取 snapshot"并检查其属性，但未显式要求使用 context manager（`with` 语句）
  管理 `SourceSnapshotProtocol` 的生命周期。
- **反例/失败场景**: implementation agent 直接调用
  `snapshot = repo.read_source_snapshot(..., materialize_files=False)` 后检查属性，但不进入 `with` 块。
  `SourceSnapshotProtocol.__enter__` 可能执行必要的初始化（如 publication guard 获取）；跳过它可能导致
  `RuntimeError: snapshot 已关闭时抛出` 或读取到不一致状态。
- **为什么有问题**: `SourceSnapshotProtocol` 是显式定义的 context manager 协议（`__enter__`/`__exit__`），
  其 `__enter__` 的 docstring 说"进入 snapshot 资源生命周期"，`__exit__` 说"退出 snapshot 资源生命周期并释放
  临时资源"。implementation agent 若未用 `with`，可能在 snapshot 未初始化时读取属性。
- **直接证据**: `dayu/fins/storage/repository_protocols.py` 第 87-126 行定义了 `SourceSnapshotProtocol` 的
  `__enter__`/`__exit__`；`dayu/fins/storage/_fs_source_snapshot.py` 第 302 行实现了 `__enter__`。
- **影响**: 实施 Agent 可能生成不使用 context manager 的代码，在非 Windows 本地通过（因为 mock/简化路径），
  但在真实 Windows remote run 时因 snapshot lifecycle 不完整而失败。
- **建议改法和验证点**: 在 §13.2.1 第 3 点明确要求使用 `with repository.read_source_snapshot(...) as snapshot:`
  管理生命周期。验证：owner test 必须断言 snapshot 的 ticker/document_id/source_kind/primary_filename 在
  `with` 块内读取。
- **修复风险（低/中/高）**: 低。一句话措辞修改。
- **严重程度（低/中/高/严重）**: 低。implementation agent 大概率按 Python 惯例使用 context manager，但 plan
  应显式消除歧义。

### F-02-unfixed-LOW-test_init_command.py getpass fixtures 需要 isatty() 配合

- **位置**: §13.4 WIN4-RW-S2："在 `tests/cli/test_init_command.py` 用严格 typed fakes/真实 `io.StringIO`
  直接测试 owner，更新受影响既有 getpass fixtures 使其明确处于 TTY path"。
- **问题类型**: 测试缺口 / 不可直接实施。
- **当前写法**: plan 说要"更新受影响既有 getpass fixtures 使其明确处于 TTY path"，但未说明具体如何实现。
- **反例/失败场景**: 当前 `_install_ollama_inputs()` 只 monkeypatch `getpass.getpass` 为
  `_GetpassSequence()`。引入 `_read_secret_input()` 后，production code 的调用路径变为
  `_read_secret_input() → sys.stdin.isatty() → getpass.getpass()`。在 pytest 进程中，`sys.stdin` 通常不是
  TTY（`isatty() == False`），因此 `_read_secret_input()` 走 redirected path 而非调用 `getpass.getpass()`，
  导致 monkeypatch 不生效。orchestrator 测试可能因 redirected path 的 `readline()` 从 pytest stdin 读取而 hang
  或得到意外输入。
- **为什么有问题**: 现有 `_GetpassSequence` 依赖 `getpass.getpass()` 被调用；`isatty()` 分流后该前提不再成立。
  实现 agent 需要知道必须同时 mock `sys.stdin`（使其 `isatty()` 返回 `True`）或直接 mock
  `_read_secret_input`。
- **直接证据**: `tests/cli/test_init_command.py` 第 250-273 行的 `_install_ollama_inputs()` monkeypatch
  `getpass.getpass`；`dayu/cli/commands/init.py` 第 482、494 行直接调用 `getpass.getpass()`。
  pytest 默认 `sys.stdin` 不是 TTY。
- **影响**: 实施 Agent 可能只更新 production code 而未正确更新 fixtures，导致现有 orchestrator 测试 hang 或
  失败；或者为修复测试而引入不合规的 shim。
- **建议改法和验证点**: 在 plan 中明确说明：orchestrator 测试需要同时 monkeypatch `sys.stdin` 为
  `isatty()` 返回 `True` 的对象并 monkeypatch `getpass.getpass`，或者直接 monkeypatch
  `_read_secret_input` 为 test-local fake。验证：所有现有 orchestrator 测试在引入 `_read_secret_input()`
  后继续通过。
- **修复风险（低/中/高）**: 低。标准 monkeypatch 扩展。
- **严重程度（低/中/高/严重）**: 低。plan 已识别需要更新 fixtures，只是未指定具体方法。

### F-03-unfixed-LOW-EOF exception type 未显式指定

- **位置**: §13.2.2 第 3 点："TTY getpass 或 redirected readline() 的 EOF 都在 helper 内收敛为不含 prompt
  value/secret value 的 CliInitOperationError"。
- **问题类型**: 契约缺失。
- **当前写法**: plan 描述了 EOF 语义但未显式指定需要捕获的异常类型。
- **反例/失败场景**: TTY `getpass.getpass()` 在 EOF 时抛 `EOFError`；redirected `readline()` 在 EOF 时返回
  空字符串 `""`（不抛异常）。implementation agent 需要知道两种 EOF 表现形式不同，且都需要处理。
  若只处理了 `EOFError` 而未处理空字符串返回，redirected EOF 会返回空值给 required secret，触发
  "required environment value was not provided" 而非 "secret input ended before completion"。
- **为什么有问题**: 两种路径的 EOF 语义不同（异常 vs 空返回），plan 的"收敛为同一 error"需要 implementation
  agent 自行推断如何统一。
- **直接证据**: CPython `getpass.py` 的 `fallback_getpass()` 在 EOF 时抛 `EOFError`；
  `io.StringIO.readline()` 在 EOF 时返回 `""`。
- **影响**: 低。implementation agent 大概率正确处理，但 plan 应消除推断需求。
- **建议改法和验证点**: 在 §13.2.2 第 3 点明确：TTY path 捕获 `EOFError`，redirected path 检测
  `readline()` 返回空字符串，两者都映射为同一 `CliInitOperationError`。
- **修复风险（低/中/高）**: 低。一句话补充。
- **严重程度（低/中/高/严重）**: 低。

## Open questions

`0`。三个 LOW findings 均为措辞澄清，不改变 plan 的 owner、架构、slice 结构或安全边界。implementation agent
有足够上下文正确实现，但显式说明可消除歧义并降低返工风险。

## Residual risks and tracking destination

1. 非 Windows 本地无法替代真实 CPython 3.11 Windows console/redirected handle 行为；owner unit tests 只锁定
   capability contract，最终证据唯一 destination 是 §13.8 fresh R12。
2. caller-owned pipe、OS handle 与 CLI process memory 按输入本质会暂存 secret；本 WU 只承诺 CLI 不主动回显
   或投影，不承诺外部 shell/process inspection 安全。扩大 transport threat model 需独立安全设计。
3. 若 fresh R11 exit/storage owner 事实失败，或 fresh R12 在 secret 读取之后出现新 failure，立即进入
   diagnostic-first stop；不得沿用当前两个 root cause 解释新证据。
4. Controller 继续独立拥有 same-run canary scan；implementation/test 不得取得 run-specific needle 或共享派生实现。
5. WIN4-RW-S2 的 `readline()` 在 Windows 真实 redirected stdin 下的行为（text mode line ending normalization）
   由 fresh R12 最终验证；本地 test 使用 `io.StringIO` 不能完全替代。

## Final plan review conclusion

`PASS / LOW_RISK / NO_BLOCKER / IMPLEMENTATION_NOT_AUTHORIZED`

amendment 的 motivation、root cause、semantic owners、两个 slices、允许/禁止路径、顺序、negative tests、
coverage/pyright/Ruff/diff/README/source scans、fresh remote rerun、same-run canary gate 与
deferred/security boundary 均已明确。三个 LOW findings 为措辞澄清，不阻塞 implementation。下一步只能进入
Controller finding fix 指引、AgentCodex plan fix、双路完整 re-review 与 accepted amended-plan commit；
在 accepted amended-plan commit 前不得 implementation。
