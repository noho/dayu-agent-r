# Fins 安全点号元数据完整性：plan

- Gate：`plan review -> fix`；work unit：`fins-hidden-metadata-integrity`；本次修复唯一 label：`dotfile-plan-fix-sol-20260928-01`；原 plan label：`dotfile-plan-sol-20260928-01`；日期：2026-09-28。
- 工作区：`/private/tmp/dayu-upload-dotfile`；分支：`codex/upload-material-dotfile`；基线 HEAD：`8d8d494fbbce0052372fb1b42097c9f7222cfa28`。
- 上游约束：`fins-hidden-metadata-integrity-goal-20260928.md` 已记录 `goal confirmation pass`；本 plan 只解释该目标所需的实现与验证，不批准主工作区候选代码。
- 本 gate 状态：**按总控裁决完成 plan review fix，等待独立 plan re-review**。下一 gate：`plan re-review`；通过前不进入 implementation。
- Design document alignment：本 work unit 无独立 design document；binding 范围只取同目录已确认的 goal artifact。

## 目标、动机与直接证据

目标是在 `dayu.fins.storage` 的 source integrity owner 内，把 source kind 根及 source 文档目录中**未声明、安全的点号元数据**排除在业务 inventory 外；已声明业务文件仍严格校验。安全点号普通文件，以及递归仅含非链接普通文件/目录的点号目录可忽略。点号 symlink、特殊文件、不可读或扫描中消失的隐藏树不能因此成为 complete。成功信号是 filing/material 的 published 与 staged exact、whole、snapshot、batch commit 对安全元数据保持原有 complete、revision、manifest/snapshot 事实，非法条目继续失败关闭。

动机成立，严重性限于 storage 的业务命名空间识别：goal 所引用的隔离下载复验中，空 `.claude/.cc-writes` 使 whole-kind preflight 抛 `UNSAFE_PUBLICATION`，清理后来源恢复 complete。当前 HEAD 的 `_fs_source_integrity.py`：`_inspect_source_kind_unguarded` 在 root 枚举中把非 identity 目录或普通文件记为 unassignable（约 271–307 行）；`_validate_physical_structure` 在 document 枚举中把未声明普通文件判为 `UNDECLARED_BUSINESS_FILE`，目录判为 `UNSAFE_FILESYSTEM_ENTRY`（约 833–867 行）。这直接解释点号残留造成的失败。CLI/downloader 不是原因 owner，不能在失败投影中改写成功。

当前 `_fs_identity.py` 的 document 目录键为 `id-` 加 digest，真实 source identity 目录不会以点号开头；root 点号目录不需先尝试业务 identity 解析。`_parse_declared_source_files` 接受合法单组件点号文件名（排除 `.identity.json` 等控制名），因此 document 目录的忽略判定必须先检查 `declared_names`。`_classify_physical_file_facts` 仍对声明文件执行 presence、size、SHA-256 检查，不能修改。

## Owner 与调用路径

- 唯一语义 owner：`dayu/fins/storage/_fs_source_integrity.py` 的统一 `_inspect_source_kind_unguarded`，具体在 source root 枚举与 document `_validate_physical_structure` 边界。新增一个私有、typed 的隐藏条目安全判定 helper，两个枚举点复用；不改变 `source_integrity.py` 的 public enum、仓储协议或上层投影。
- `repository_protocols.py` 的 `classify_source_integrity`、`classify_staged_source_integrity`、`list_source_integrity` 由 `fs_source_document_repository.py` 转发至 `_fs_source_document_core.py`；三者分别在 published exact、staged exact、published whole 模式调用统一 inspector。`_classify_source_integrity_unguarded` 及 repair 路径也调用它。
- `read_source_snapshot` 由 source repository/core 进入 `_fs_source_snapshot.py`；snapshot 的 exact target 与可选 kind 判定均调用同一 inspector，并要求 target `COMPLETE`。snapshot 文件集合来自 inspector 已声明文件，不能另扫点号目录。验证 `materialize_files=False/True` 的行为。
- `fs_batching_repository.py` 的 `commit_batch` 进入 `_fs_storage_infra.py` 的 `_validate_complete_source_tree`，对 filing/material 的 `_validate_complete_source_kind_tree` 都以 whole 模式调用同一 inspector，之后才 publication swap。安全点号项不应阻止 commit；非法条目仍由现有 typed preflight/complete 校验封闭。
- `fs_filing_upload_state` 也消费统一 inspector；本 work unit 无需修改调用者。此路径仅作为回归风险，不增加新的上传状态契约。

## 决策与不变量

1. 保持现有 root manifest/control 跳过规则先于新判定；仅对其余 root 直属条目判定。对 document 目录，保持 `meta.json`、`.identity.json` 控制文件规则；对其余条目，仅当 `child.name not in declared_names` 时考虑忽略。已声明的 `.name` 即使是普通文件也走原结构、containment、内容和指纹路径；若变成目录、symlink 或特殊文件，仍是 unsafe。
2. helper 输入 `Path` 与该条目的 `lstat` 状态；非点号返回 false；点号普通文件返回 true；点号目录仅在递归枚举的每个后代均由 `lstat` 证明为普通文件或目录时返回 true，后代名称无需继续以点号开头。任何直属/嵌套 symlink 或特殊文件、`lstat` 返回 missing 均返回 false；目录枚举或状态读取的其他 I/O 错误沿 storage 既有 path-free `OSError` 传播。不能使用 `is_dir()`/`is_file()` 跟随链接，也不读元数据文件内容。
3. root 对 unsafe 点号项沿用 `unassignable_root_fact`：whole 抛 `SourceIntegrityPreflightError(UNSAFE_PUBLICATION)`，exact 按既有 cross-source/repair-blocked 规则关闭。document 对 unsafe 点号项沿用 `UNSAFE_FILESYSTEM_ENTRY`；非点号未声明普通文件沿用 `UNDECLARED_BUSINESS_FILE`。不造新 enum 或特殊成功状态。
4. helper 只作当前物理扫描判断，不加入文件名白名单、全局 dotfile 忽略、缓存、manifest/schema 变更或消费者 fallback。现有 publication guard 与 staging 稳定视图边界不变。该最小改动覆盖所有消费者，避免按入口重复修补，也没有 goal drift。

目标对齐：决策 1–2 对应“只忽略未声明安全元数据，声明文件仍校验”；决策 3 对应“非法条目失败关闭”；决策 4 与单个 S1 切片对应“exact/whole/snapshot/batch/commit 同源”。正向测试证明完整性与 revision 不变，反向测试证明非法条目不降级；README 裁决只解释已落地行为。无 public interface、schema、manifest 格式或状态机变更。

## 唯一实施切片：安全元数据不改变来源发布事实

- ID：`S1-safe-hidden-metadata`。前置条件：plan review 通过，基线及候选状态重新核对；只实施本已确认目标。
- 允许文件：`dayu/fins/storage/_fs_source_integrity.py`、`tests/fins/test_fins_storage_atomicity.py`；按下述读者职责裁决后，可更新 `dayu/fins/README.md`、`tests/README.md`、根 `README.md`。不改 `repository_protocols.py`、snapshot/core、`source_integrity.py`、下载/CLI/Service/Host 层。
- 实现：在 owner 模块新增私有 helper，完整中文参数/返回/异常 docstring；root 枚举在 `lstat` 成功后、identity 目录要求之前忽略安全点号项；document 枚举在声明名称集合判定之后、结构失败之前忽略安全点号项。其它判断顺序、manifest、revision、error 投影不改。可参考候选 hunk，但须重新审查并由隔离实现验证。
- 正向 owner 测试：用真实 `build_fs_repository_set` 创建 filing 与 material complete source，分别在 source root 和 document 目录加入 `.DS_Store` 类未声明普通文件、空及多层安全点号目录（嵌套普通文件）。断言 published exact 与 whole inventory 均 `COMPLETE`，revision/manifest 投影不变；open batch 的 staged exact 同值；`read_source_snapshot` 两种 `materialize_files` 模式只含已声明文件、revision 相同；含安全元数据的 staging 经 `commit_batch` 后仍 complete 且 revision 不因元数据自增。可在一个参数化测试内覆盖，避免机械拆 slice。
- 反向 owner 测试：在 source root、document 直属与点号目录内部放点号 symlink、特殊文件（如 FIFO）及嵌套非法条目，至少覆盖根和文档各自的点号特殊文件；用同一类非法物理事实分别断言四象限：root × whole 抛 typed `SourceIntegrityPreflightError(UNSAFE_PUBLICATION)`；root × exact 的目标为 `UNSAFE`、含 `CROSS_SOURCE_INCONSISTENCY`、无 revision，且 repair 被 `CROSS_SOURCE_PUBLICATION_UNSAFE` 阻断；document × exact 为 `UNSAFE_FILESYSTEM_ENTRY`、无 revision；document × whole 不得产出 complete inventory，且 snapshot/commit 拒绝 unsafe。分别检查直属与嵌套非法项，不以非点号 corruption grid 代替点号命名变体。非点号未声明业务文件仍 `UNDECLARED_BUSINESS_FILE`；保留现有 corruption grid 作为回归。
- 已声明点号文件测试：通过真实仓储 API 发布名字以点号开头的业务文件，断言初始 complete；篡改内容或 size 后必须出现现有 mismatch，移除后出现现有 missing reason，改为链接/特殊条目必须 unsafe。不得通过直接改 meta 伪造不一致 fixture 来证明“已声明”契约。
- upload-state 回归：沿用 `tests/fins/test_fins_storage_atomicity.py` 中 published/batch upload-state 读取与损坏失败关闭测试，并核对 `tests/fins/test_filing_upload_publication.py`、`tests/fins/test_fins_ingestion_runtime.py` 中实际消费 source integrity 的用例；安全元数据下同一 source 事实与 publication identity 不漂移，非法条目仍失败关闭。不新增上传状态契约或实施切片。
- 结束信号：上述正反断言、upload-state 回归、受影响测试和 pyright 通过，按下节核对修改单文件覆盖率目标 `>=80%`，文档按职责裁决，review 能确认两个入口共用同一 helper；若 owner 或已声明文件行为与上述代码事实冲突，停下重新确认 goal，不加下游 shim。

## 主工作区候选 hunk 归属与文档裁决

主工作区同一基线上的未提交 diff 仅为审查输入，未验证、未接受：storage `+39` 行（root/document 两个入口及递归 helper）归 `S1` 候选；atomicity 测试 `+109` 行（安全项与隐藏 symlink）归 `S1` 候选，但缺已声明点号文件、特殊文件、staged 与两种 materialization 的明确断言，实施时补齐或改写，不机械复制。主工作区 README 各 `+2` 行必须按语义拆分：

- `dayu/fins/README.md` 中 source integrity inspector 句是本切片候选，需在实现验证后以当前代码事实陈述；同段“四种封闭原因映射到 storage 公共失败”句属于 #198，不纳入。
- `tests/README.md` 中仓储完整性测试句只在对应测试实际存在后更新；下载终态/public failure 句属于 #198，不纳入。该 README 仅描述已存在的测试事实及维护方式。
- 根 `README.md` 面向终端用户，只在核对当前入口、用户输出及排障职责后写必要的简短行为/操作说明；候选点号句应限定为未声明的安全来源元数据，不暗示任意点号内容均可忽略。候选 `classification="storage"` / `reason="unsafe_publication"` 的失败投影与重试建议属于 #198，不纳入本切片。若本变更未改变用户操作/可行动排障，则记录根 README 无需更新的理由。

## 验证路径与预期

本 plan fix 只做只读环境预检，不实施代码或测试；隔离 worktree 当前没有 `.venv`，主工作区现成依赖 venv 存在。实施 gate 在隔离 worktree 建立本地 `.venv` **符号链接**指向该现成 venv，以满足 AGENTS.md 的 `source .venv/bin/activate`；链接只供应解释器/依赖，不代表主工作区源码获准作为测试对象。创建前确认本地 `.venv` 尚不存在且目标 venv 有 Python 3.11、pytest、pyright；若目标变化或本地已有不同 `.venv`，先核清环境，不覆盖。所有 Python/pytest/CLI 调用显式设置指向隔离 worktree 的 `PYTHONPATH` 与 `PYTHONDONTWRITEBYTECODE=1`；从工作区外 cwd 核对 `dayu.__file__` 必须精确指向本 worktree，再运行测试。pytest 禁用 cacheprovider。示例（以下链接创建只属于后续 implementation gate）：

```bash
cd /private/tmp/dayu-upload-dotfile
ln -s /Users/leo/workspace/dayu-agent-r/.venv .venv
source .venv/bin/activate
DAYU_WORKTREE="$PWD"
(cd /private/tmp && PYTHONPATH="$DAYU_WORKTREE" PYTHONDONTWRITEBYTECODE=1 python -c 'from pathlib import Path; import dayu; assert Path(dayu.__file__).resolve() == Path("/private/tmp/dayu-upload-dotfile/dayu/__init__.py").resolve()')
PYTHONPATH="$DAYU_WORKTREE" PYTHONDONTWRITEBYTECODE=1 python -m pytest -p no:cacheprovider tests/fins/test_fins_storage_atomicity.py -q
PYTHONPATH="$DAYU_WORKTREE" PYTHONDONTWRITEBYTECODE=1 pyright --project "$DAYU_WORKTREE/pyrightconfig.json" --venvpath /Users/leo/workspace/dayu-agent-r "$DAYU_WORKTREE/dayu" "$DAYU_WORKTREE/tests" "$DAYU_WORKTREE/utils"
```

`pyrightconfig.json` 的 `venvPath="."`、`venv=".venv"` 与本地链接相符；`--venvpath` 指向依赖 venv 的父目录，绝对 `dayu/ tests/ utils/` 参数固定分析对象为本 worktree。当前 pyright 拒绝同时使用 `--pythonpath` 与 `--venvpath`，因此 pyright 只传后者；`PYTHONPATH` 与工作区外导入检查约束 Python/pytest/CLI 的代码树身份。实施 gate 先记录基线、修改后分别记录 pyright 诊断，必须无 `venv ... not found`、import 或代码树身份歧义，且零新增/扩散类型错误；不得接受仅有 `0 errors` 但仍有 missing-venv 诊断的输出。若链接路径仍不能证明解释器、代码树或 pyright 诊断身份，则在隔离 worktree 移除该链接，以 Python 3.11 创建真正本地 `.venv`，按本仓库 `README.md` 的平台锁定 constraints 安装测试/开发依赖，再 `source .venv/bin/activate` 重跑全部身份检查、受影响测试与 pyright；此 fallback 可能涉及重型依赖与网络，不能以主工作区源码的结果替代。若本地锁定依赖 venv 仍无法形成无歧义证据，停止实施并上报。

实施结束时用 pytest-cov 对修改的 `dayu/fins/storage/_fs_source_integrity.py` 单文件核对 `>=80%` 目标，记录覆盖率数值、未覆盖分支及测试命令；既有大文件若未达目标，记录基线与增量差异并交 review 裁决，不为追数字编写镜像测试，也不以候选测试行数代替 owner contract。受影响测试至少包括 atomicity owner 测试及上述 upload-state 消费回归；任何测试生成的缓存/临时文件应保持在 pytest 临时目录并在提交前清理。

## 风险、边界与完成报告

- 文件系统在扫描后变化仍有既有 TOCTOU 风险；本目标只要求当前 inspector 检查不可读/消失/非法条目时失败关闭，不扩大为全局无竞态保证。若验证发现无法在现有 guard 下满足 confirmed goal，停止并重新确认。
- 安全点号目录递归扫描的成本无固定上界；本 goal 不增设任意大小限制、白名单或缓存。rejected filing/control 区可能仍因点号元数据阻塞独立清理路径，已由总控登记为后续 `fins-rejected-control-hidden-metadata` work unit；本切片及 README/closeout 不宣称全仓点号元数据免疫。
- 对点号普通文件只验物理类型、不读内容是 deliberate scope：它不进入业务 manifest、revision、snapshot；已声明点号文件仍按内容校验。点号目录后代不限命名，但只接受普通文件/目录。source kind 根之外（ticker root、processed/blob、rejected filing/control 区）不在此规则内。
- #198 的 public failure/CLI 投影，以及非点号异物分类、schema/manifest、下载 provider、外部用户工作区内容均属其它 owner/work unit；不借本次修复纳入。
- 完成报告格式：首行 `RUNTIME/PROVIDER/MODEL`；随后列 artifact 的完整绝对路径、实际验证与未运行项目、状态/下一 gate、未覆盖风险、canary。plan review 应独立审查切片数量、候选充分性及上述残余风险；通过前不得进入 implementation。

## Plan review finding 状态与交接

| 裁决项 | 本次状态 | 后续核对 |
| --- | --- | --- |
| MiMo F1：隔离验证与 missing-venv | **已修复于 plan** | 本地链接、AGENTS 激活、外部 cwd 导入身份、显式 worktree pyright 与锁定依赖 fallback；implementation 执行并留证。 |
| MiMo F2：反向四象限 | **已修复于 plan** | S1 owner 测试覆盖点号 symlink/特殊文件及 root/document × exact/whole。 |
| MiMo Q2：单文件覆盖率 | **已修复于 plan** | S1 结束时实测 `>=80%` 目标并记录差异。 |
| Kimi：upload-state 回归 | **已修复于 plan** | S1 沿既有消费测试集合核对，不新增切片。 |
| 超大隐藏树成本、TOCTOU、rejected/control 区 | **依裁决 deferred-with-owner** | 实施/closeout 记录风险；rejected/control 另归后续 work unit。 |
| material `.rejections` 与 filing control 不对称 | **依裁决 rejected-with-reason** | filing 控制名规则与 material 安全点号规则各按现有 owner 处理，无新修复项。 |

本次只修订 plan；只读预检确认主工作区 venv 的 Python 导入在工作区外 cwd 指向 `/private/tmp/dayu-upload-dotfile/dayu/__init__.py`，并确认以 `--venvpath` 加显式 worktree 目录运行 pyright 为 `0 errors, 0 warnings, 0 informations`，无 missing-venv 诊断；同时实测当前 pyright 不能组合 `--pythonpath` 与 `--venvpath`。尚未创建链接、运行 pytest/覆盖率或实施代码。下一 gate：**plan re-review**，独立 review 通过后才可进入 implementation。
