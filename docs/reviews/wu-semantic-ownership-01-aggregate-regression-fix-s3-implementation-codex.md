# WU-SEMANTIC-OWNERSHIP-01 Aggregate Regression Fix Slice 3 Implementation（AgentCodex）

## 1. Verdict

`STOPPED_PRODUCTION_CORRECTNESS_DEFECT`。

Slice 3 在补充 Docling owner/public contract 真实业务 case 时，公开入口稳定复现表格标题丢失：有效的 Docling 2.74.0 文档使用 `TableItem.captions: list[RefItem]` 引用标题文本，但 `DoclingProcessor.list_tables()` 返回 `caption=None`。预期值为 `Consolidated statements of operations`。这属于 production owner correctness defect，命中 accepted plan §4.3/§9 与 Controller authorization 的 stop condition。

本次没有修改 production、utility、README、coverage 配置，也没有降低阈值或增加 deselect/skip/xfail/retry。发现缺陷后没有继续 SEC cases、canonical suite、aggregate coverage、build、smoke、scan 或 security gate；等待 Controller 重新裁决 production owner 与 allowlist。

## 2. Entry locks

- WU：既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 的 aggregate regression fix Slice 3；不是新 WU。
- 执行者：AgentCodex；未启动子代理。
- branch：`phaseflow/host-issues-control`。
- immutable slice base / entry HEAD：`9e7a4e9d4796b9c382d44494bb10efa64787b199`。
- parent：`ba44bf877138235d53606d082341a7f7280af488`。
- tree：`7dc759e3bde5f6a257c21b60434f8874d157771a`。
- accepted plan SHA-256：`afaa18c5608e6eeae0046318865bd1b3dd2f9a176c4b0739aa5b099e0ae3a252`。
- Controller control doc SHA-256：`badc03741bc0f8d70377370169af1e1a98a442dd9ad152628bcade0fe13040a4`。
- S2 postcommit validation SHA-256：`bf5842031abe4306fb50cfce918c6fd2ff90bb219584a42fc20f8d2bc8a208ed`。
- S3 authorization SHA-256：`7d8fb7e0723c98edd5a8aa20692fe61d084d2ff7552cf821d74410f4a80243dc`。
- entry staged diff：空。
- entry Controller-owned dirty artifacts：
  - `M docs/host/issues-implementation-control.md`
  - `?? docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s2-accepted-commit-controller-validation.md`
  - `?? docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-implementation-controller-authorization.md`
- 上述三个 artifact 未被删除、修改、覆盖或纳入 mutable implementation diff；最终锁复核见 §10。

## 3. 动机、语义 owner 与 root cause

Slice 3 的动机成立：immutable base 的 aggregate coverage ledger 中九个 production owner 未达到 80%，accepted plan 要求仅通过 owner/public contract 测试补足覆盖率。测试不得替 production 重算语义。

本缺陷的唯一语义 owner 是 `dayu/documents/processors/docling_processor.py` 的 Docling 表格投影边界。直接数据与逻辑证据同源：

1. 当前环境 `docling-core==2.74.0` 的公开 `TableItem` 合法字段是 `captions: list[RefItem]`。
2. 最小复现创建真实 `DoclingDocument`，`TableItem.captions` 指向 `#/texts/1`，该 `TextItem.text` 为 `Consolidated statements of operations`，然后用 `save_as_json()` 写出真实 Docling JSON。
3. production `_extract_table_caption()` 在 `dayu/documents/processors/docling_processor.py:1185` 读取不存在的单数属性 `getattr(table_item, "caption", None)`；因此在 1186—1187 直接返回 `None`，没有解析 `captions` 引用，也没有读取文档中的标题文本。
4. 公开 `DoclingProcessor.list_tables()[0]["caption"]` 实际为 `None`。

因此不能在测试 fixture、下游展示、adapter 或消费者中填默认值/重算标题。若继续本 WU，Controller 需要显式重新授权 Docling production owner；修复应落在该表格投影 owner boundary，并由本最小公开入口用例约束。

## 4. 精确 implementation diff

发现 stop defect 前形成的测试 diff（相对 immutable slice base，不含本 artifact）为 371 行新增、0 行删除：

| path | 状态 | 新增 | 删除 | 语义 |
|---|---:|---:|---:|---|
| `tests/documents/test_processors.py` | M | 91 | 0 | Docling 真实 `captions` 引用最小复现 |
| `tests/fins/test_fins_ingestion_tools.py` | M | 89 | 0 | preprocess material/过滤/重建有效参数与非法 `source_kind` 公共 outcome |
| `tests/host/test_effective_execution_config.py` | M | 146 | 0 | 六类 provider extension、完整 RunnerSpec/options/policy round-trip、缺席语义与 fail-closed matrix |
| `tests/runtime/test_argparse_exit.py` | A | 45 | 0 | int 原样保留与非 int 归一为 argparse error code |

授权 allowlist 中以下两个路径保持零 diff：

- `tests/fins/test_sec_pipeline_download.py`
- `tests/fins/test_processor_read_consistency.py`

production / utility / README allowlist 严格为空。九个 production owner 逐项均为零 diff：

- `dayu/documents/processors/docling_processor.py`
- `dayu/fins/pipelines/sec_6k_rules.py`
- `dayu/fins/processors/sec_form_section_common.py`
- `dayu/fins/processors/sec_report_form_common.py`
- `dayu/fins/processors/sec_section_build.py`
- `dayu/fins/processors/sec_table_extraction.py`
- `dayu/fins/tools/preprocess_tools.py`
- `dayu/host/_execution_config_projection.py`
- `dayu/runtime/argparse_exit.py`

没有触碰 Issues 142/151/175/177/178、Topic 8/9、secret infrastructure 或统一 tool authorization framework。

## 5. 最小复现、预期/实际与 stack

命令：

```text
source .venv/bin/activate
COVERAGE_FILE=workspace/tmp/wu-semantic-ownership-01-ar-fix-s3-stop.coverage python -m coverage erase
COVERAGE_FILE=workspace/tmp/wu-semantic-ownership-01-ar-fix-s3-stop.coverage python -m coverage run --branch -m pytest tests/documents/test_processors.py::test_docling_json_processor_projects_referenced_table_caption -q
```

结果：`1 failed`，node 真实运行，无 skip/xfail/retry/deselect。

```text
E       AssertionError: assert None == 'Consolidated statements of operations'
tests/documents/test_processors.py:1019: AssertionError
```

- 最小复现 node：`tests/documents/test_processors.py::test_docling_json_processor_projects_referenced_table_caption`
- 预期：`processor.list_tables()[0]["caption"] == "Consolidated statements of operations"`
- 实际：`processor.list_tables()[0]["caption"] is None`
- production 路径：`_build_tables()` 调用 `_extract_table_caption(table_item)`，后者命中 `caption_obj is None` 的返回分支。
- 测试只走真实 Docling serialize/load 与公开 processor 结果；没有 monkeypatch、mock-only hook、private-state padding、不可能状态或 production 算法复制。

## 6. Coverage evidence

### 6.1 Stop reproduction coverage

证据文件：

- `workspace/tmp/wu-semantic-ownership-01-ar-fix-s3-stop.coverage`
- `workspace/tmp/wu-semantic-ownership-01-ar-fix-s3-stop-coverage.json`

最小复现单 node 对 Docling owner 的 line ledger：

| owner | statements | covered | missing | line percent |
|---|---:|---:|---:|---:|
| `dayu/documents/processors/docling_processor.py` | 635 | 341 | 294 | 53.70% |

关键 missing-line 证据：1185—1187 已执行并返回 `None`；用于读取真实 caption 内容的 1188—1189 未执行。coverage report 明确列出 `1188-1189` 为 missing。完整 missing-line 列表保存在上述 JSON；命令行报告总体为 `635 statements / 294 missing`。

### 6.2 Immutable base aggregate shortfall captured before implementation

Slice 3 preflight 读取 immutable base 的 aggregate coverage JSON，九 owner line ledger 为：

| owner | statements | covered | missing | line percent |
|---|---:|---:|---:|---:|
| `dayu/documents/processors/docling_processor.py` | 635 | 403 | 232 | 63.46% |
| `dayu/fins/pipelines/sec_6k_rules.py` | 447 | 302 | 145 | 67.56% |
| `dayu/fins/processors/sec_form_section_common.py` | 1098 | 859 | 239 | 78.23% |
| `dayu/fins/processors/sec_report_form_common.py` | 416 | 271 | 145 | 65.14% |
| `dayu/fins/processors/sec_section_build.py` | 303 | 235 | 68 | 77.56% |
| `dayu/fins/processors/sec_table_extraction.py` | 863 | 571 | 292 | 66.16% |
| `dayu/fins/tools/preprocess_tools.py` | 62 | 47 | 15 | 75.81% |
| `dayu/host/_execution_config_projection.py` | 157 | 120 | 37 | 76.43% |
| `dayu/runtime/argparse_exit.py` | 0 | 0 | 0 | not imported |

最终 219/219 aggregate coverage 没有执行，也没有声称通过。原因不是测试覆盖困难，而是先出现真实 production correctness defect；按 stop condition 不得继续用其它 cases 掩盖失败或达到阈值。

## 7. 已执行测试与静态验证

### 7.1 Pre-stop focused evidence

- Slice 3 原五个现有测试文件 baseline focused：`174 passed, 3 warnings`。
- runtime/Host/preprocess 新增用例（caption repro 加入前）：`88 passed, 3 warnings`。
- caption 最小复现：`1 failed`；失败内容见 §5。

一次 preprocess 初稿曾错误断言 prepare 会立即产生内部 job JSON；公开契约和既有测试证明 prepare 只创建 lightweight observation。该测试假设已删除，最终用例只断言 awaiting kind、opaque resume token 与 snapshot，未把测试耦合到内部存储布局。这不是 production defect。

### 7.2 Strict typing / Ruff on all six authorized mutable paths

命令对六个授权测试路径执行：

- `pyright ...`：`0 errors, 0 warnings, 0 informations`。
- `ruff check ...`：`All checks passed!`。

这只证明当前 mutable paths 的严格类型与 Ruff 零 finding。full-project pyright、full immutable Ruff 144-finding set delta 因 stop condition 未执行，未声称通过。

## 8. 未执行门禁（因 stop condition）

以下 accepted plan §4.3/§6 门禁在 defect 后全部保持 `NOT_RUN_DUE_STOP`：

| gate | 状态 | 说明 |
|---|---|---|
| 其余 Docling/SEC form/report/build/table/SEC 6-K owner cases | NOT_RUN_DUE_STOP | 禁止在已知 owner correctness failure 后继续 padding coverage |
| canonical full suite | NOT_RUN_DUE_STOP | 未声称 0 failed；AR-F06 node 未在本 Slice final gate 取证 |
| exact one-node deselect aggregate coverage | NOT_RUN_DUE_STOP | 未运行；未增加任何 deselect |
| final changed production set 219 与 219/219 >=80% | NOT_RUN_DUE_STOP | production 零 diff，但 final ledger 未生成 |
| full pyright | NOT_RUN_DUE_STOP | 仅 mutable paths 已验证 |
| full Ruff immutable set delta | NOT_RUN_DUE_STOP | 仅 mutable paths 已验证 |
| wheel + sdist build | NOT_RUN_DUE_STOP | 未构建 |
| six canonical scans | NOT_RUN_DUE_STOP | 未运行 |
| Slice 2 direct-stream/awaiting owner/stale scans | NOT_RUN_DUE_STOP | 未运行 |
| AAPL download/process 与必要 smokes | NOT_RUN_DUE_STOP | 未发起真实下载/provider 调用 |
| R03 public Host/current/live browser cleanup owner | NOT_RUN_DUE_STOP | 未运行 |
| upload POSIX/Windows nodes | NOT_RUN_DUE_STOP | 未运行 |
| security matrices/configured-secret owner scan | NOT_RUN_DUE_STOP | 未运行 final matrix |
| accepted immutable HKEX evidence复核 | NOT_RUN_DUE_STOP | 未运行 |

Gemini 仍按 `EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING` 分类：没有新增真实 provider 调用，没有修改 config/model/key/retry/quota/budget。

## 9. README 与 security 裁决

README verdict：`NO_UPDATE`。本 slice 只增加既有测试层中的 owner/public contract cases，没有改变测试目录职责、测试运行方式、维护规则、用户安装/CLI/Web/WeChat 工作流或分层装配。production 零 diff，因而根 README、`dayu/README.md`、各 layer README 与 `tests/README.md` 都不应机械同步。

Security verdict：当前 stop 原因是 Docling caption correctness，不是 secret/security defect。未引入 secret、token、provider key、authorization framework 或新 output surface。Config 与 Host internal SQLite/EventLog 的 trusted-internal 裁决未改变；Tool Trace、audit、public、LLM-facing、logs、其它 outputs、diff/reviews 的 `ZERO_REQUIRED` 规则也未改变。由于 final security matrices/scans 未运行，不对 Slice 3 final zero-match 作通过声明。

## 10. Diff、allowlist、staged 与 protected-state final audit

- 相对 base 的 production owner diff：空。
- utility diff：空。
- README diff：空。
- 两个未修改的授权测试路径：零 diff。
- 当前 implementation test diff 只在 §4 的四个授权路径；本 implementation artifact 是用户明确要求的新增 200 行 review artifact。
- staged diff：空；未 stage、未 commit。
- 未进入 code review、aggregate、push、PR 或 closeout。
- Controller-owned control/review artifacts 保持 entry SHA-256；没有写入它们。

## 11. Residual risk 与 Controller handoff

当前 residual risk 为 `BLOCKING`：带有效引用标题的 Docling 财报表格会在公开表格摘要中丢失业务标题，影响 LLM/工具消费者识别表格语义。该缺陷也阻止按 accepted plan 完成 caption 业务 family 与最终 Docling owner coverage。

Controller 后续需要：

1. 裁决是否在同一 umbrella 中重新开放 `dayu/documents/processors/docling_processor.py` 的 production allowlist。
2. 明确 caption 的 owner contract：基于当前 Docling 公共数据模型解析 `TableItem.captions` 引用，并从同一 `DoclingDocument` 真源读取业务标题；不得在下游消费者 fallback。
3. production 修复后重新授权从本最小复现继续 Slice 3，并完整重跑尚未执行的 §6 gates。

在 Controller 重新授权前，AgentCodex 不修改 production，不删除失败复现，不降低 coverage threshold，也不推进 review/commit/aggregate/push/PR/closeout。
