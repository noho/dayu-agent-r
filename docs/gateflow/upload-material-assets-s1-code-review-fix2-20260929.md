# UM-O04/O23 S1 code review F6/F7 修复记录

- 工作区：`/private/tmp/dayu-upload-assets`；分支：`codex/upload-material-assets`；HEAD：`1453a659a79d4c9a93838412dfdecfa7feeddf98`。
- 预检读取了 `AGENTS.md`、`upload-material-assets-s1-code-review-adjudication-20260929.md` 的新增 F6/F7 裁决、上一修复记录、accepted goal、当前 diff，以及 usage/handoff owner。修改前 `git diff --binary | shasum -a 256` 为 `ad8b77d51756bc12f176526e5599bb7fd05c6a53637550dbc54fdbf34a5502bd`，与总控裁决记录一致；未跟踪路径也与上一记录后的候选文件相符。
- 本轮只改 `dayu/fins/upload_usage_contract.py`、`dayu/fins/ingestion_runtime.py`、对应的 owner/CLI 测试及本记录。没有提交、推送、创建 PR、合并或推进 gate。

## 动机、根因与 owner

F6 动机成立。planner 的 canonical basename 最长可占 240 字符，而 `FinsUploadUsageFailure.message` 的完整上限也是 240。原投影直接把标签插入模板，合法的 222 个 `a` 加 `.txt` 与中文前后文合并后越界，构造 typed failure 前裸抛 `ValueError`。唯一文案 owner `upload_usage_contract.py` 现在从每个文件相关模板计算剩余标签预算；短标签逐字不变，超长标签稳定保留首尾片段及省略号，继续保留 closed code、重命名/缩短提示和路径安全。完整消息仍由 owner 的 240 字符不变量兜住。四个新增带标签 planner reason 均经同一预算函数；未改 CLI/tool 投影。

F7 动机成立。`ValidatedFinsUploadMaterialRequest.__post_init__` 把两个 tuple 的对象身份误作保序业务相等。handoff 类型是请求、selection、plan 的一致性 owner；现改为 `converter_pairs != ordered_pairs` 的保序值比较，后续 path/name/derived identity 不变量仍执行。owner 测试分别证明不同 tuple 对象但值相等可构造、逆序值不等被拒绝。

## 验证及原始命令

所有 Python 命令均先执行 `source .venv/bin/activate`。解释器为 Python 3.11.15、`/private/tmp/dayu-upload-assets/.venv/bin/python`。本轮验证命令无非零退出或失败测试；未以最终绿测替代过程记录。

| 命令 | exit | 结果 |
| --- | ---: | --- |
| `source .venv/bin/activate && python -m pytest tests/fins/test_upload_usage_contract.py tests/fins/test_fins_ingestion_runtime.py::test_validated_material_handoff_rejects_cross_field_drift tests/cli/test_fins_commands.py::test_real_cli_long_duplicate_basename_is_typed_usage_without_publication tests/cli/test_fins_commands.py::test_upload_material_cli_names_conflicting_basename_without_path -q` | 0 | 14 passed、3 warnings。四种新增 planner 文件原因均有长标签 owner 断言；短标签原文案继续验证。真实 CLI 子进程对两个不同目录的相同 `"a"*222 + ".txt"` 普通文件 exit 2、stdout 空、stderr 精确等于 typed owner message 加固定命令前缀，message ≤240、无绝对路径或 traceback，隔离 workspace 未创建。 |
| 下方完整受影响矩阵命令 | 0 | 1448 passed、1 skipped、3 warnings；原始完整输出 `/private/tmp/dayu-upload-s1-fix2-matrix.log`。 |
| `source .venv/bin/activate && python -m pyright` | 0 | 0 errors、0 warnings、0 informations；原始输出 `/private/tmp/dayu-upload-s1-fix2-pyright.log`，另有版本更新提示。 |
| `source .venv/bin/activate && python -m coverage report --include='dayu/fins/upload_usage_contract.py' --fail-under=80` | 0 | 94%。 |
| `source .venv/bin/activate && python -m coverage report --include='dayu/fins/ingestion_runtime.py' --fail-under=80` | 0 | 91%。 |
| `git diff --check` | 0 | 无空白错误。 |

完整受影响矩阵原始命令：

```bash
source .venv/bin/activate && python -m pytest tests/fins/test_upload_asset_plan.py tests/fins/test_upload_usage_contract.py tests/fins/test_storage_asset_filename_contract.py tests/fins/test_fins_storage_atomicity.py tests/fins/test_docling_upload_service.py tests/fins/test_docling_upload_service_integration.py tests/fins/test_upload_failure.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_sec_pipeline_upload_filing_stream.py tests/fins/test_cn_pipeline.py tests/fins/test_filing_upload_publication.py tests/fins/test_fins_service_runtime.py tests/fins/test_fins_ingestion_tools.py tests/service/test_fins_direct.py tests/service/test_fins_wait_adapter.py tests/cli/test_fins_commands.py tests/fins/test_sec_pipeline_download.py tests/fins/test_sec_pipeline_download_stream.py tests/fins/test_cn_download_workflow.py tests/fins/test_cn_download_runtime.py --cov=dayu.fins --cov=dayu.service.fins_direct --cov=dayu.cli.commands.fins --cov-report=term-missing -q
```

矩阵通过前没有失败的测试命令。上表的 3 个 warnings 均来自共享依赖 `edgar` 的弃用提示。聚焦和矩阵均在同一修复版运行。真实 CLI 的 closed reason 由同一测试中直接调用 admission 并断言 `DUPLICATE_ORIGINAL_BASENAME`，再断言真实 CLI stderr 精确等于该 typed failure 的消息；CLI 本身只承诺面向用户的可修正文案。

## README、精确候选与剩余边界

已阅读 `dayu/fins/README.md`、`tests/README.md` 和根 `README.md` 的写作约束。F6/F7 不新增用户命令、参数、流程、包边界或测试层级；现有手册已说明 material 预检用法错误及有界文案，本轮无需改 README。

最终 tracked diff SHA-256（`git diff --binary | shasum -a 256`）：`07281b59ba635466ba700dbaf2a9b32f760e2efb4a33a618133ef39b1bd98666`。该值按 Git 惯例**不含未跟踪文件**；本轮改动的未跟踪 owner/test 文件内容 SHA-256 分别为 `dayu/fins/upload_usage_contract.py`：`64e5b33a7f907d3b604f3a9efd341b1849b5f9ac8615da1feab13c7e29ae8659`，`tests/fins/test_upload_usage_contract.py`：`0c56fd77f5d81746a91ad2da87b97f01de8d8d5335d19ced11b6125f5b3f17bd`。本记录也是未跟踪新文件；review 应读取 `git status --short` 的全部候选路径，不能只用 tracked SHA 代表完整候选。

环境偏差：`.venv/lib/python3.11/site-packages/dayu_shared_dependencies.pth` 指向 `/Users/leo/workspace/dayu-agent-r/.venv/lib/python3.11/site-packages`，所以本轮复用主仓依赖，不代表独立依赖安装验证；pyright 当前版本为 v1.1.409，提示可升级到 v1.1.414。未复跑真实 Docling 转换或仓储发布；本轮反例在前置准入退出，隔离 workspace 未创建。O16/O25/O34、filing identity、TOCTOU/最终 storage 完整性边界及双路同版 re-review 均保留在原裁决范围，不据此宣告 code gate 通过。
