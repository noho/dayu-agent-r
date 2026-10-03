# UM-O20-F01 S1 implementation

- RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/gpt-6-sol
- 工作区：`/private/tmp/dayu-upload-o20`；分支：`codex/upload-material-o20`；实施基线 HEAD：`8c9e1d3473e5fd9c8e4509a38539a1a940140070`。未提交、未推送，未进入 code review gate。
- CANARY=gpt-6-sol-542b94b9
- 输入：本 worktree 的 `AGENTS.md`、F01 goal、accepted plan、plan review adjudication、owner/CLI/tool/batch 代码及对应测试、目标 README 约束。

## 事实、owner 与切片

`dayu.documents.docling_runtime.DOCLING_CONVERTER_CAPABILITY` 将 `.json` 对应 `JSON_DOCLING`，`.xml/.xbrl` 对应 `XML_XBRL`；它定义格式能力，不负责 Fins 帮助文案。`dayu.fins.upload_format_contract.project_fins_upload_format_text` 是 material 格式说明的唯一 owner：`dayu/cli/arg_parsing.py` 直接消费 `material_files`，`dayu/fins/tools/upload_tools.py` 直接消费组合后的 `upload_tool_files`；batch 仅调用同一 Fins capability 的 `accepts_primary` 判断后缀。现有 material 文案缺少内容子类型说明，因此 F01 动机成立，影响限于公开说明。无需修改转换能力、依赖或下游入口。

仅在 `dayu/fins/upload_format_contract.py` 的 `material_files` 原有后缀警示句后、`delete` 句前连续插入计划固定两句：

> `.json` 仅是 Docling 格式的 JSON 文档候选，不代表任意 JSON 内容可转换。`.xml/.xbrl` 仅是 XBRL 财报实例文档候选，不代表任意 XML 或独立 linkbase 文件可转换。

原有首句、有序 suffix 句、后缀警示句及 `delete` 句逐字保留；filing 文案、capability、schema 参数结构及实际上传行为未变。更新 owner、CLI help、真实构造 tool schema 三处测试，并在根 `README.md` 上传章节增补 material 输入选择说明。根 README 面向最终用户，符合其 `Agent更新约束`；`dayu/fins/README.md` 的开发者边界、`tests/README.md` 的测试层级说明仍成立，无需修改。

## 本地环境身份

- 本机 `Darwin arm64`；使用 `/opt/homebrew/bin/python3.11` 创建本 worktree 的 `.venv`，按根 README §1.1 执行 `python -m pip install -e '.[test,dev,browser]' -c constraints/lock-macos-arm64-py311.txt`，退出码 0。
- 约束文件 SHA-256：`lock-common-py311.txt` 为 `3a68c4afcbc537212b0ef5c29a0f3bc76f0b106e78f98dc11a3eecc27d4b05e3`；`lock-macos-arm64-py311.txt` 为 `c8242535d33f97c1b55e7b3d34e4cd504caacbe2d5ac8aba7735b9a20ed41563`。
- 激活后 `python=3.11.15`，`sys.executable=/private/tmp/dayu-upload-o20/.venv/bin/python`，`dayu.__file__=/private/tmp/dayu-upload-o20/dayu/__init__.py`；Docling `2.127.0`、Torch `2.14.0`、Transformers `5.16.1`、pyright `1.1.409`、coverage `7.13.5`。`python -m pip check`：`No broken requirements found.` 本轮验证未借用主工作区解释器。

## 验证证据

以下命令均在本 worktree `source .venv/bin/activate` 后运行。

| 验证 | 结果 |
| --- | --- |
| `python -m pytest -q tests/fins/test_upload_format_contract.py tests/cli/test_arg_parsing.py tests/fins/test_fins_ingestion_tools.py tests/fins/test_upload_batch.py tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_cn_pipeline.py tests/fins/test_docling_upload_service.py` | 退出 0；`779 passed, 3 warnings in 48.40s`。三条警告均来自已安装 edgartools 的废弃 API。 |
| `coverage erase`；以上七文件执行 `coverage run -m pytest -q ...`；`coverage report --include='dayu/fins/upload_format_contract.py' --fail-under=80` | 退出 0；测试 `779 passed, 3 warnings in 13.57s`；被改生产单文件 `165 Stmts / 12 Miss / 93% Cover`，超过 80% 门槛。 |
| `pyright` | 退出 0；`0 errors, 0 warnings, 0 informations`。另有工具新版本提示，不属于类型错误。 |
| `python -m dayu.cli upload_material --help` | 退出 0；真实 `--files` 段有原有完整 suffix 顺序、转换资格警示、固定两句及 `delete` 规则；折行后语义连续。 |
| `python -m dayu.cli upload_filing --help` | 退出 0；真实 filing `--files` 段保持现有文案；生产 diff 未触及 `filing_files`。 |
| 本 worktree Python 以隔离临时 workspace 构造 `DefaultFinsRuntime.create(...).get_ingestion_runtime()` 和 `build_fins_upload_tool(runtime)` | 退出 0；`files.description == FINS_UPLOAD_FORMAT_TEXT.upload_tool_files` 为 `True`；material 子段逐字包含 owner `material_files` 为 `True`；`files.maxItems=100`。 |
| `git diff --check`；新增 artifact 的 `git diff --no-index --check /dev/null <artifact>`；本地 `.venv` 的固定文案精确顺序断言 | 已跟踪文件检查退出 0；新文件 no-index 检查无空白诊断（差异存在，退出 1）；固定两句仅出现一次，位于原有后缀警示与 `delete` 句之间。 |

真实 material CLI `--files` 段的关键原文（argparse 只增加显示折行）：

> `后缀通过只表示具备转换资格，不保证文件内容转换成功。.json 仅是 Docling 格式的 JSON 文档候选，不代表任意 JSON 内容可转换。.xml/.xbrl 仅是 XBRL 财报实例文档候选，不代表任意 XML 或独立 linkbase 文件可转换。delete 不得提供文件。`

## 残余与边界

- `UM-O20-F02`：当前标准安装的完整 XBRL instance 转换能力仍需独立裁定和补证。本切片仅声明候选资格，不声称 XBRL 在本环境成功，不改依赖、转换器或 capability。
- `UM-O20-E01`：Docling JSON 的先前正样本结论属于其记录环境；本切片未在本地重新做真实上传或内容抽取准确率评估。冻结负样本不作为本次能力结论。
- schema 描述变长，存在已接受的少量 LLM token 增量；argparse 的现有 CJK 折行仍在，但本次真实 help 可读。

最终 HEAD 仍为 `8c9e1d3473e5fd9c8e4509a38539a1a940140070`。变更仅为 `dayu/fins/upload_format_contract.py`、`tests/fins/test_upload_format_contract.py`、`tests/cli/test_arg_parsing.py`、`tests/fins/test_fins_ingestion_tools.py`、根 `README.md` 及本实施记录；无提交或推送。
