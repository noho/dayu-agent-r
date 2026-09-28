RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/gpt-6-sol

# fins-hidden-metadata-integrity：唯一 S1 implementation

- Label：`dotfile-implement-sol-20260928-01`；Gate：`implementation`；日期：2026-09-28。
- Worktree：`/private/tmp/dayu-upload-dotfile`；分支：`codex/upload-material-dotfile`；实施基线 HEAD：`70dc5aa9e4637691e8fd1725eefebe1f7d5f39de`；实施前工作树为空。
- 已读取本 worktree 的 `AGENTS.md`、goal、approved plan、总控 plan review 裁决，以及 Kimi `plan-review-20260928-232008.md` 和 MiMo `plan-review-20260928-233739.md` 两份最新 re-review。总控裁决 plan review pass。本记录只完成 S1 implementation，不进入 code review gate。

## 动机、owner 与实现

动机成立且严重性限定在来源业务命名空间：原 inspector 的 root 枚举把未声明点号项计为不可归属；document 枚举把它判为未声明业务文件或不安全目录。该逻辑会让安全工具元数据阻断完整来源的 whole preflight。唯一语义 owner 是 `dayu/fins/storage/_fs_source_integrity.py`，无需在 download、CLI、snapshot 或 upload-state 消费者补偿。

仅在该 owner 的两个枚举点复用 `_is_ignorable_hidden_metadata_entry`：root 保持 manifest/control 优先；document 保持控制文件与已声明名称优先。helper 用当前条目及每个后代的 `lstat` 判定，未声明点号普通文件或全为普通文件/目录的点号树才忽略。symlink、FIFO 等特殊文件与消失的后代返回不安全；其它扫描 I/O 错误沿原有 path-free `OSError` 投影。声明点号文件仍进入原结构、size、digest 校验；非点号未声明业务文件沿用 `UNDECLARED_BUSINESS_FILE`。未改 schema、public enum、revision 生成或消费者。

## 测试与身份

`.venv` 是 `/Users/leo/workspace/dayu-agent-r/.venv` 的符号链接，仅提供 Python 3.11.15、pytest 与 pyright 依赖。激活后从 `/private/tmp` 执行、显式设置 `PYTHONPATH=/private/tmp/dayu-upload-dotfile` 与 `PYTHONDONTWRITEBYTECODE=1` 的导入检查：`dayu.__file__` 解析为 `/private/tmp/dayu-upload-dotfile/dayu/__init__.py`。测试和类型检查分析对象均为本 worktree；没有把主工作区源码当成验证对象。

新增的 owner 回归覆盖 filing/material：安全点号普通文件、空目录、多层目录在 root/document 共存时，published exact/whole、staged exact、light/full snapshot 的已声明文件集合、manifest 字节与 revision 保持不变；copy batch commit 不因元数据增加 revision；filing upload-state 与 exact 同源。点号 symlink/FIFO 在 root/document 直属及嵌套位置覆盖 root × whole typed `UNSAFE_PUBLICATION`、root × exact `CROSS_SOURCE_INCONSISTENCY` 且无 revision、repair blocked reason `CROSS_SOURCE_PUBLICATION_UNSAFE`，以及 document × exact/whole 的 `UNSAFE_FILESYSTEM_ENTRY`、snapshot 拒绝和 commit 拒绝。已声明点号 material 文件通过真实仓储 API 发布，随后分别验证 digest 损坏、缺失、symlink、FIFO。原非点号 corruption grid 保留。

以下为 2026-09-28 实施期实际执行命令与结果，保留原始运行记录；其覆盖率归因见本节末尾勘误：

```bash
source .venv/bin/activate
PYTHONPATH=/private/tmp/dayu-upload-dotfile PYTHONDONTWRITEBYTECODE=1 python -m pytest -p no:cacheprovider tests/fins/test_fins_storage_atomicity.py -q -k 'safe_hidden_metadata or hidden_unsafe_entries or declared_dotfile' --tb=short
# 22 passed, 209 deselected

PYTHONPATH=/private/tmp/dayu-upload-dotfile PYTHONDONTWRITEBYTECODE=1 python -m pytest -p no:cacheprovider tests/fins/test_fins_storage_atomicity.py tests/fins/test_filing_upload_publication.py tests/fins/test_fins_ingestion_runtime.py -q --cov=dayu/fins/storage/_fs_source_integrity.py --cov-report=term-missing:skip-covered
# 638 passed；但本机 coverage 7.13.5 / pytest-cov 把单独 .py 参数解释为 module，报告 no-data-collected，不能用作覆盖率证据。

PYTHONPATH=/private/tmp/dayu-upload-dotfile PYTHONDONTWRITEBYTECODE=1 python -m pytest -p no:cacheprovider tests/fins/test_fins_storage_atomicity.py -q --cov=dayu/fins/storage/_fs_source_integrity.py --cov=dayu/fins/storage --cov-report=term-missing:skip-covered
# 231 passed；_fs_source_integrity.py 为 574 statements / 81 missed / 86%。有效数据仅来自 --cov=dayu/fins/storage；组合命令中的 .py 参数是死参数，另有 module-not-imported warning。

PYTHONPATH=/private/tmp/dayu-upload-dotfile PYTHONDONTWRITEBYTECODE=1 pyright --project /private/tmp/dayu-upload-dotfile/pyrightconfig.json --venvpath /Users/leo/workspace/dayu-agent-r /private/tmp/dayu-upload-dotfile/dayu /private/tmp/dayu-upload-dotfile/tests /private/tmp/dayu-upload-dotfile/utils
# 0 errors, 0 warnings, 0 informations；无 missing-venv 诊断。
```

实施期单文件覆盖率达到 `>=80%` 目标。实施期未覆盖行由报告列为 `206, 216, 233-234, 236, 245, 251, 280-281, 292, 303-304, 438-448, 526, 581-582, 656, 661, 664, 667-668, 677, 680, 692, 703, 740, 761-762, 807, 832, 862, 903, 925, 930, 934, 984, 987-988, 991, 1034, 1037, 1040, 1101, 1111, 1122, 1135-1136, 1139, 1142, 1174-1175, 1273, 1282, 1286, 1289, 1295-1296, 1380, 1397-1398, 1468, 1498-1499, 1562, 1584, 1783, 1826, 1875, 1901-1902, 1956-1959, 1982-1983, 2008, 2021`；主要为既有异常、损坏或竞争分支，未为覆盖率数字新增镜像测试。`git diff --check` 通过。

## S1 code review 后的覆盖率证据勘误（2026-09-29）

当前 coverage 7.13.5 将 `--cov=dayu/fins/storage/_fs_source_integrity.py` 当作模块名。上面的单独使用命令出现 `module-not-imported` 与 `no-data-collected`，不能提供覆盖率证据；组合命令的 `.py` 参数同样产生 `module-not-imported` warning，且不贡献数据。实施期的 574 statements / 81 missed / 86% 只来自组合命令中的 `--cov=dayu/fins/storage` 目录式收集，不应归因于 `.py` 参数。此处保留历史命令和结果，不改写当时运行。

code review fix 使用本任务独立的 `/private/tmp/dotfile-s1-review-fix-sol-20260929-01-final.coverage` 作为 `COVERAGE_FILE`，仅以目录式参数复跑三个受影响测试文件；最终精确命令与结果登记在 `fins-hidden-metadata-s1-code-review-adjudication-20260929.md`。目标文件的最终行、warning 与 pyright 结果以该复跑记录为准。

## 候选 hunk、README 与残余风险

主工作区未提交的 storage hunk 只读参考：采用其两个枚举点与迭代 `lstat` 的方向，重新按 approved plan 实施和验证。其 atomicity 候选只覆盖安全项与隐藏 symlink 的部分路径；未复制，补齐 FIFO、四象限、声明点号文件、staged、双 snapshot 模式和 upload-state 断言。主工作区 README 中 #198 的 public failure/CLI 映射句未采用，也未修改主工作区。

按 README 职责核对并更新 `dayu/fins/README.md` 的已实现 storage 机制及 `tests/README.md` 的现有测试事实。根 `README.md` 已核对用户手册职责：本次不改变命令、参数、输出通道、用户操作或可行动排障步骤，因此无需更新；不把 storage 规则扩写为全仓点号忽略。`dayu/README.md` 的分层关系与装配方式未变。

残余风险按已批准 plan 保留：超大隐藏树递归扫描成本无固定上界；扫描中的 TOCTOU 不形成全局无竞态保证；rejected/control 区仍属后续 `fins-rejected-control-hidden-metadata` work unit。batch copy guard 在非法 published tree 上会先于 commit 拒绝复制；测试将同类非法项置入 staging 后核对 commit 的既有 owner 契约。没有修改该 guard 或放宽 symlink/特殊文件。未 stage、commit、push、PR、merge、评论或派发子 Agent。

CANARY=gpt-6-sol-3f660336
