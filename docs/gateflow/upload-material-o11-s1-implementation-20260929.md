# UM-O11-F01 S1 实施记录（2026-09-29）

- Gate：implementation；decision：S1 实施完成并经本 worktree 验证，未进入 code review gate。
- Work unit：UM-O11-F01；基线 branch `codex/upload-material-o11`，HEAD `9141b5e9c65caaf52416f177a2641f8a7e1134ad`；实施前 `git status --short` 为空。O05/O16 未进入本 HEAD；本轮未修改其规则。
- 工作区：`../..`；已接受计划：`upload-material-o11-dates-plan-20260929.md`；裁决：`upload-material-o11-plan-review-adjudication-20260929.md`。
- 本轮没有 commit、push、PR、merge 或子 Agent 派发。

## 动机、owner 与实现

动机由当前代码直接支持：material request 的 `_normalize_upload_request` 原先只归一化 action，而 `upload`、`prepare_observed_upload`、`start_upload` 都在 direct producer、observation 和 queued job 创建前调用 `_validate_runtime_upload_request`。CLI/tool 原先还会对非空 material 日期做 strip，使带空白日期绕过严格 parser。冻结 oracle 只作为历史背景，不作为本 HEAD 的验证。

日期规则 owner 仍是 `dayu/fins/domain/filing_semantics.py` 的 `parse_iso_calendar_date`；Fins admission 通过既有 `_validate_optional_upload_iso_date` 将非法原文投影为 `invalid_filing_date` / `invalid_report_date`。material 分支现对两字段在返回 normalized request 前调用该 helper；仅 `None` 跳过，非 `None` 的空串、纯空白、非补零、首尾空白和不存在的公历日均按字段拒绝，不重写合法原文。

CLI material 日期参数使用窄投影保留既有空值折叠，非空文本原样交给 Service。tool material 两日期使用已有 raw nullable 参数读取；省略或 `null` 为 `None`，非空和空白字符串均原样进入 Fins admission。tool schema 的两段描述分别给出业务含义、filing/material 适用范围、可省略/`null`、精确格式、真实公历示例及空白禁令。没有修改 Service、runner、pipeline、storage、parser 或 schema 结构。

## 实际修改与 README 判断

| 文件 | 修改 |
| --- | --- |
| `../../dayu/fins/ingestion_runtime.py` | 共享 material admission 两字段 typed 校验及异常 docstring |
| `../../dayu/cli/commands/fins.py` | material 非空日期保真、既有空值投影 |
| `../../dayu/fins/tools/upload_tools.py` | material raw 日期传递和 LLM-facing 两字段说明 |
| `../../tests/fins/test_fins_ingestion_runtime.py` | US/CN/HK 的非法日期、四入口零副作用、合法闰日/`None` |
| `../../tests/fins/test_fins_ingestion_tools.py` | tool 原文、字段级错误、零副作用和 schema 断言 |
| `../../tests/cli/test_fins_commands.py` | CLI 显式空 filing 日期及非空日期参数投影 |
| `../../dayu/fins/README.md` | 更新 Fins 稳定日期准入边界 |
| `../../README.md` | 更新最终用户直接上传日期规则及既有空 filing 日期语义 |

已读目标 README 的 `Agent更新约束`。`tests/README.md` 只记录既有测试分层，未新增层级或命令类别，故不改；`dayu/README.md` 的分层/装配边界未变，故不改。

## 环境与验证

- 在本 worktree 用 `uv venv --python python3.11 .venv` 建环境，以 `uv pip install --python .venv/bin/python -e '.[test,dev]' -c constraints/lock-macos-arm64-py311.txt` 安装锁定依赖；为全量 pyright 解析 web 可选导入，再以同一约束安装 `.[browser]`。`uv` 缓存位于 worktree 外的临时目录。Python `3.11.15`，解释器为 `../../.venv/bin/python`，`dayu.__file__` 为 `../../dayu/__init__.py`。
- 最终受影响测试：激活 `.venv` 后运行 `python -m pytest tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_ingestion_tools.py tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_cn_pipeline.py tests/cli/test_fins_commands.py --cov=dayu --cov-report= -q`，**714 passed**、3 条 edgartools 依赖 deprecation warning。覆盖 US/CN/HK material 流程回归。最初不带 coverage 的同组测试也为 **714 passed**。
- 单文件 coverage（上述最终测试运行后 `python -m coverage report --include=...`）：`dayu/cli/commands/fins.py` **86%**（457/66 missed）；`dayu/fins/ingestion_runtime.py` **91%**（2373/208 missed）；`dayu/fins/tools/upload_tools.py` **93%**（115/8 missed）。三个修改生产文件均达到 >=80%。
- `python -m pyright dayu/ tests/ utils/`：**0 errors, 0 warnings**。`git diff --check`：通过。
- 方法偏差：计划中的三个模块名分别作为 `--cov=` source 的精确命令在 pytest collection 时触发 pandas/numpy `ImportError: cannot load module more than once per process`；改用 package source `--cov=dayu --cov-report=`，再用 coverage 的 `--include` 读取相同三文件的单文件数字。首轮 pyright 因未安装 browser 可选依赖出现 15 个导入错误，锁定安装该 extra 并修正新增测试的动态构造类型后复跑为零；没有改产品以掩盖环境问题。

## 真实隔离 CLI 与发布读回

运行目录 `../../../um-o11-cli-20260929/`，每场景使用 fresh `--base`，输入同一 `input/material.md`，SHA-256 `7a74f575f76989d97b1398cae3a7e6e4e52ceb1859272756b2761fd222d37948`。执行的是本 worktree 的 `.venv/bin/dayu-cli`，`--ticker AAPL --action create --forms MATERIAL_OTHER --material-name Deck --company-name 'Apple Inc.'`，无外部 provider/网络输入；具体完整 argv、exit、stdout、stderr、前后文件树、成功文件 digest 均在对应 `<scenario>.*` 证据文件中。非法场景的 stdout 为空、没有上传 progress，fresh base 前后均为 0 个文件，因此无公司/source/meta/manifest/job 发布。

| 场景 | 日期参数 | exit | 关键结果 |
| --- | --- | ---: | --- |
| `invalid-filing` | `--filing-date 2025-02-30` | 2 | stderr `披露日期（filing_date）必须是实际存在的 YYYY-MM-DD 日期`；文件树 0→0 |
| `invalid-report` | `--report-date not-a-date` | 2 | stderr `报告期日期（report_date）必须是实际存在的 YYYY-MM-DD 日期`；文件树 0→0 |
| `valid-dates` | 两字段均 `2024-02-29` | 0 | success；Fins repository source meta 和 material manifest 两字段均为 `2024-02-29` |
| `empty-filing` | `--filing-date ""` | 0 | success；Fins repository source meta 和 material manifest 两字段均为 `null` |

成功场景读回证据为 `../../../um-o11-cli-20260929/valid-dates.readback.json` 与 `../../../um-o11-cli-20260929/empty-filing.readback.json`。使用 `DefaultFinsRuntime.create(...).source_repository.list_source_document_ids/get_source_meta` 读取 source meta；manifest 无公开单独读 API，按仓储发布的 `material_manifest.json` 原文读取并核对同一 `document_id`。两个 fresh base 各有一条 source，meta/manifest 与 CLI 成功结果一致。该读取方式未作为产品 fallback。

## Findings、残余与交接

- 本切片 finding：无未解决阻塞。shared admission 在 direct producer、observation、job 和 runner 之前 typed 拒绝，由 owner 测试及真实 CLI 双重证实。
- R1：`upload_filings_from` 的脚本元数据预折叠差异属于后续独立 work unit。
- R2：CLI material 现有空串/纯空白投影仍会折叠为 `None`；本裁决仅承诺显式空 `--filing-date ""` 例外，不从历史行为推定显式空 `report_date` 的新产品承诺。raw request/tool 的非 `None` 空串/纯空白由共享 admission typed 拒绝。
- R3：O05/O16 也修改共享 admission；后续 PR 集成 owner 必须基于实际 HEAD 串行复核多错误字段优先级及受影响测试。本 worktree 未集成它们。
- 下一 gate 由总控另行决定；本轮到 implementation 证据为止，不提交、不推送、不进入 code review gate。
