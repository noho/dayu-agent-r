# 安全点号元数据 S1 code review 总控裁决

- Gate：code review -> fix；基线 `70dc5aa9e4637691e8fd1725eefebe1f7d5f39de`，候选未提交。
- 两路独立 artifact：`docs/reviews/code-review-20260929-001535.md`（Kimi）、`docs/reviews/code-review-20260929-002058.md`（MiMo）。总控完整读取两份及 owner 证据。两路均确认候选产品行为正确，638 个受影响测试通过、pyright 0、owner 文件覆盖率 86%。Sol 实施派发含五条失败 command_execution，按协议 `agent_status=failed`，代码仅作经独立复核的候选。
- MiMo：预检 ok、显式 `--cwd /private/tmp/dayu-upload-dotfile`、独立 output/stderr；退出 0，Claude JSON `subtype=success`、`is_error=false`、55 turns、canary 匹配，stderr 仅模型名白名单提示，`agent_status=completed`。
- Kimi：预检 ok、同样独立派发，虽然在 HTTP 403 前写下完整 review artifact 和 canary，最终退出 1，JSON `is_error=true`、`terminal_reason=api_error`、`api_error_status=403`（五小时额度耗尽），**agent_status=failed，不能计为完成的 Kimi code review**。artifact 只作为可查的部分诊断，待额度恢复后新 label 复审。

## Findings 与修复登记

| 来源 | 裁决 | owner、修复与完成信号 | 状态 |
| --- | --- | --- | --- |
| Kimi F1 / MiMo F1：隐藏树后代消失与不可读的失败关闭分支缺回归断言 | **accepted** | 行为探针证明实现方向正确，但 `:1875` 未覆盖。由 `tests/fins/test_fins_storage_atomicity.py` 的 owner 契约测试确定性注入后代 lstat missing 和隐藏目录枚举 OSError；断言 exact/whole 的失败关闭、原因/revision 与 path-free 异常。测试注入直接作用于 storage owner，不能 fake 下游结果；不需产品补丁。 | 待 Sol fix、双路复审 |
| MiMo F2：路径式 `--cov=…py` 是死参数，实施 artifact 归因不准 | **accepted** | 依据 coverage 7.13.5 对照实测，修正实施证据和本 work unit 原总控命令规格：只用目录式收集、读取单文件 86% 行，披露旧 warning/失败；新命令无 `module-not-imported`。上一个 artifact 已追加勘误。 | 待 Sol 修实施 artifact 与复跑 |
| Kimi F2 / MiMo residual：忽略的 `.coverage` 留在 worktree | **accepted（卫生）** | 文件已在 `.gitignore` 内，不污染提交，但应在本 work unit 结束前删除；新覆盖率运行设置隔离的 `COVERAGE_FILE`，核对无遗留。 | 待清理 |

MiMo OQ 顶层条目在 list/lstat 间消失：**deferred-with-owner** 至本 work unit closeout 的 TOCTOU 记录。当前调用方对点号/非点号统一 `continue`，而 helper 仅在已取得隐藏目录后检查后代；无证据证明本候选额外掩盖顶层消失，改变通用语义会越出已确认 goal。超大隐藏树扫描成本及 rejected/control 命名空间分别按原裁决延期。Kimi artifact 的结构化失败不改变本次 finding 的直接证据，也不能作为 gate 通过凭证。

当前 gate 未通过。gpt-6-sol 只修测试、实施证据与清理，随后 Kimi/MiMo 双路独立 code re-review；通过后 commit 并汇入 PR #197。用户手工 merge main。

## S1 code review fix 候选登记（2026-09-29）

- 唯一 label：`dotfile-s1-review-fix-sol-20260929-01`；runtime/provider/model：`codex/gpt-6-sol/gpt-6-sol`。开始及验证后 HEAD 均为 `70dc5aa9e4637691e8fd1725eefebe1f7d5f39de`；保留原有产品候选 diff，未修改生产代码、goal、plan、冻结 review、README 或其它测试。
- F1：只在 `tests/fins/test_fins_storage_atomicity.py` 新增 8 个参数化 owner 契约用例。真实仓储完成 filing/material 发布后，在 root/document 隐藏树的精确后代注入 `_lstat_optional` missing：exact 均为 `UNSAFE`、`revision=None`，root reason 为 `CROSS_SOURCE_INCONSISTENCY`、whole 抛 typed `UNSAFE_PUBLICATION`；document reason 为 `UNSAFE_FILESYSTEM_ENTRY`、whole inventory 保留同一 UNSAFE fact。另对精确隐藏目录的 `Path.iterdir` 注入含物理路径的 `PermissionError(EACCES)`，使 storage owner 原 `_list_directory` 投影，再核对 exact/whole 均传播 `PermissionError`，异常文本、filename、cause 均不含物理路径，context 为 `None`。未 fake classifier 返回值。focused 运行 `8 passed, 231 deselected`；最终全量受影响测试见下。
- F2：`fins-hidden-metadata-s1-implementation-20260928.md` 保留实施期原命令与结果，补充 coverage 7.13.5 勘误：单独 `.py` 目标有 `module-not-imported` / `no-data-collected`；历史组合命令也有 `module-not-imported` warning，574 / 81 / 86% 仅来自 `--cov=dayu/fins/storage`。本次复跑仅用该有效目录式参数。
- 卫生：清理前 worktree 根 `.coverage` 为 53248 字节、mtime `2026-09-28 23:49:52`，`git check-ignore -v` 显示 `.gitignore:21:.coverage`。仅删除该已确认 gitignored 的生成文件；删除后 `test ! -e .coverage` 成立、`git status --ignored --short .coverage` 无输出。新覆盖率数据写到 worktree 外本任务独立的 `/private/tmp/dotfile-s1-review-fix-sol-20260929-01-final.coverage`，未与旧数据合并。
- 磁盘与 Git 前后状态：开始 `git status --short` 为 5 个已修改路径（`dayu/fins/README.md`、`dayu/fins/storage/_fs_source_integrity.py`、plan review adjudication、`tests/README.md`、本 atomicity 测试）与 4 个未跟踪 artifact（S1 code adjudication、S1 implementation、两份 code review）；结束仍是同一 5 个已修改路径与同一 4 个未跟踪 artifact，仅本任务允许的测试和两份 S1 文档内容增加。根 `.coverage` 从存在变为不存在；结束 `git status --ignored --short .coverage` 仍无输出。未 stage、commit、push、PR、merge 或评论。

最终验证从 `/private/tmp` 激活本 worktree `.venv` 后，显式 `PYTHONPATH=/private/tmp/dayu-upload-dotfile PYTHONDONTWRITEBYTECODE=1` 核对 `dayu.__file__` 为 `/private/tmp/dayu-upload-dotfile/dayu/__init__.py`，Python 为 3.11.15。最终测试命令：

```bash
source .venv/bin/activate
COVERAGE_FILE=/private/tmp/dotfile-s1-review-fix-sol-20260929-01-final.coverage PYTHONPATH=/private/tmp/dayu-upload-dotfile PYTHONDONTWRITEBYTECODE=1 python -m pytest -p no:cacheprovider tests/fins/test_fins_storage_atomicity.py tests/fins/test_filing_upload_publication.py tests/fins/test_fins_ingestion_runtime.py -q --cov=dayu/fins/storage --cov-report=term-missing:skip-covered
# 646 passed, 3 warnings in 24.51s；3 项均为 edgar 第三方 DeprecationWarning，无 module-not-imported / no-data-collected。
# dayu/fins/storage/_fs_source_integrity.py：574 statements / 79 missed / 86%；新增的后代 missing 分支 :1875 已覆盖，达到 >=80%。

PYTHONPATH=/private/tmp/dayu-upload-dotfile PYTHONDONTWRITEBYTECODE=1 pyright --project /private/tmp/dayu-upload-dotfile/pyrightconfig.json --venvpath /Users/leo/workspace/dayu-agent-r /private/tmp/dayu-upload-dotfile/dayu /private/tmp/dayu-upload-dotfile/tests /private/tmp/dayu-upload-dotfile/utils
# 0 errors, 0 warnings, 0 informations；另有 pyright 新版本可用提示（v1.1.409 -> v1.1.414），非类型诊断。
```

`tests/README.md` 已按其“仅记录测试分层、运行方式与维护约定”职责检查：此次只为既有 storage atomicity 层补契约变体，不改变测试层级或运行方式，故不再修改。`git diff --check` 通过。候选仅供后续独立复审；Kimi 原 code review 进程仍因 403 为 `agent_status=failed`，不能称双路 gate 已过。本次不判 gate pass，不派发复审、不提交或推进下一 gate。顶层条目消失的通用 TOCTOU 语义保持原裁决延期。

总控结构化复核：Sol 本轮 JSONL 有 `turn.completed`、42 个 command execution、canary 匹配、stderr 空，但一条 `rg 'Agent更新约束' tests/README.md` 返回 1，按协议 `agent_status=failed`，其余结果仍只作候选证据。总控独立核对新增测试的精确 owner 注入与断言，在本点号 worktree 重跑 8 个新用例 `8 passed、231 deselected、exit 0`，pyright 显式 worktree 路径/venvpath 结果 `0 errors、exit 0`。最终 646 passed 与 86% 覆盖率为 Sol 原始命令观察，待独立 re-review 再验；不倒改失败派发状态。

## MiMo re-review 新 finding 裁决（2026-09-29 01:13）

`dotfile-s1-code-rereview-mimo-20260929-01` 退出 0，结构化 `subtype=success`、`is_error=false`、`terminal_reason=completed`、canary `mimo-f6123b49` 匹配，stderr 仅白名单模型名提示；artifact `docs/reviews/code-review-20260929-011242.md`。本路独立复跑 8 新用例、三文件 646 passed、owner 86%、pyright 0；对既有 F1/F2/卫生三项候选修复判为成立。

新 Finding 1（低）**accepted**：`tests/fins/test_fins_storage_atomicity.py::test_hidden_directory_enumeration_error_propagates_without_path` 手写仅直接 cause 的 path-free 断言，未复用同文件现有 `_assert_exception_graph_path_free` 全图合同，并钉住私有 action 文案；这会遗漏 notes/深 cause/traceback 的原始路径泄露，也会因纯措辞改动误报。测试是本 S1 新增且直接验证 accepted F1 的 owner 错误边界，故在本 review fix 中收敛到已有全图 helper，保留 errno、typed 异常和四象限断言、补 raw 错误不可达，不修改生产。验证聚焦 8 例、三文件、覆盖率、pyright，再由 MiMo/Kimi 独立 re-review。当前 gate **未通过**；Kimi 初审 403 及本轮 re-review 仍待有效路，不把 MiMo 单路 pass 冒充双路。

## MiMo re-review Finding 1 fix 候选登记（2026-09-29）

- 本轮 `codex/gpt-6-sol/gpt-6-sol`；起点 HEAD `70dc5aa9e4637691e8fd1725eefebe1f7d5f39de`。仅修改 `tests/fins/test_fins_storage_atomicity.py` 中指定枚举错误用例，并追加本记录；原有未提交候选保持原样。现有 `_assert_exception_graph_path_free` 已覆盖异常图、notes 与格式化 traceback，能承担本用例的 path-free 断言。
- 用例保存同一 `raw_error=PermissionError(EACCES, 含物理路径)` 注入对象；exact/whole 两次调用继续验证 `PermissionError`、`errno=EACCES`、顶层与安全 cause 的 `filename/filename2 is None`、`__context__ is None`。全图断言同时禁止 workspace 物理路径和 raw 消息，显式断言 raw 对象在 `_exception_graph_nodes` 中不可达；删除私有 action 文案精确断言。filing/material × root/document 参数化与既有四象限事实未变。未修改生产代码。
- 从本 worktree 激活 `.venv`，设置 `PYTHONPATH=/private/tmp/dayu-upload-dotfile`、`PYTHONDONTWRITEBYTECODE=1`；导入核对 Python 3.11.15、`dayu.__file__=/private/tmp/dayu-upload-dotfile/dayu/__init__.py`，退出码 0。focused 命令：`python -m pytest -p no:cacheprovider tests/fins/test_fins_storage_atomicity.py -q -k 'hidden_descendant_disappearing_during_lstat_fails_closed or hidden_directory_enumeration_error_propagates_without_path' --tb=short`，`8 passed, 231 deselected`，退出码 0。
- 三文件命令：`python -m pytest -p no:cacheprovider tests/fins/test_fins_storage_atomicity.py tests/fins/test_filing_upload_publication.py tests/fins/test_fins_ingestion_runtime.py -q --cov=dayu/fins/storage --cov-report=term-missing:skip-covered`，`COVERAGE_FILE=/private/tmp/dotfile-s1-mimo-f1-sol-8bfe0019.coverage` 独立保存，`646 passed, 3 warnings`，退出码 0。三条 warning 均为 edgar 第三方 `DeprecationWarning`；无 coverage dead-target warning。单文件 `dayu/fins/storage/_fs_source_integrity.py` 为 574 statements、79 missed、86%，达到 >=80% 目标。
- `pyright --project /private/tmp/dayu-upload-dotfile/pyrightconfig.json --venvpath /Users/leo/workspace/dayu-agent-r /private/tmp/dayu-upload-dotfile/dayu /private/tmp/dayu-upload-dotfile/tests /private/tmp/dayu-upload-dotfile/utils`：`0 errors, 0 warnings, 0 informations`，退出码 0；另有版本更新提示，非类型诊断。`tests/README.md` 已核对读者职责和触发条件：本轮只收紧既有用例的断言，不改变测试层级、运行方式或已记录的测试事实，因此无需修改 README。
- 本轮产物仅作为候选供后续独立 MiMo/Kimi re-review；此处不判 gate pass，不执行 re-review、commit、push、PR 或 merge。既有 TOCTOU、隐藏树上界及 rejected/control 风险维持原登记。

总控结构化复核：Sol fix2 `dotfile-s1-review-fix2-sol-20260929-01` 退出 0、JSONL `turn.completed`、全部 command execution exit 0、stderr 空、canary `gpt-6-sol-8bfe0019` 匹配，按协议 `agent_status=completed`。总控核对指定断言块已复用 `_assert_exception_graph_path_free`，保留 errno、filename/filename2、raw 不可达且删除私有文案锁；候选未越过测试及本 adjudication 白名单。下一 gate 仍为有效 Kimi/MiMo code re-review，不提前 commit。

MiMo fix2 code re-review `dotfile-s1-code-rereview2-mimo-20260929-01` 已结构化完成，退出 0、`subtype=success`、`is_error=false`、`terminal_reason=completed`、canary `mimo-54ba0613` 匹配，stderr 仅白名单模型名提示。完整 artifact `docs/reviews/code-review-20260929-013335.md` 无新 finding；前一路低 finding、首轮 F1/F2/卫生均由本路独立验证为已修复。其独立测试 8 passed、三文件 646 passed、owner 86%、pyright 0，且合成异常探针证明全图 helper 会捕捉 note/cause/path 泄漏。残余按原分类不变；Kimi 有效路仍缺，故当前只算 MiMo 单路通过，Gateflow slice 仍未 commit。

## Kimi 当前候选复审与 S1 gate 裁决（2026-09-29 02:12）

Kimi `dotfile-s1-code-rereview3-kimi-20260929-01` 退出 0、Claude JSON `subtype=success`、`is_error=false`、canary `kimi-45015a15` 匹配，stderr 仅白名单模型名提示；完整 artifact `docs/reviews/code-review-20260929-020902.md` 已读。该路不读取 MiMo 当前候选复审，独立复现 focused 30/30、三文件 646 passed、目录式单文件覆盖率 86%、pyright 0，并以真实权限探针和全图异常断言确认 nested disappearance、枚举不可读 fail-closed/path-free；无新 finding。MiMo `013335` 与 Kimi `020902` 对同一 Sol fix2 候选均无 correctness/stability/maintainability finding。

总控裁决：首轮 F1（后代消失/不可读测试）、F2（coverage 死参数）、卫生（`.coverage`）、MiMo RF03（OSError 全图 path-free 与私有文案锁）均 **已修复**；两路审查 artifact 与实现/修复证据完整，S1 code review/re-review gate **pass**。Sol 早期失败 command 的派发状态仍记 failed，候选代码之所以可采纳，是两路当前候选独立审查与总控核验，不倒改派发状态。

残余分类维持：TOCTOU 及顶层消失通用语义、隐藏树扫描无上界归本 work unit closeout；rejected/control 命名空间归后续 `fins-rejected-control-hidden-metadata`；共享结构分支的等价未测变体与 `_lstat_optional` 既有缺行记录为 accepted low residual；`tests/README.md` 未列两个新增注入变体但现有句真实且非穷举，按其读者职责不阻塞。无未分类阻塞风险。下一 gate 为 **accepted slice commit**，再进入 aggregate deepreview；本节不宣称 PR 已汇入或工作完成。
