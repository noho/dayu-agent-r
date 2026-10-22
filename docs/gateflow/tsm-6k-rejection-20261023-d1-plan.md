# D1 最小修复计划

范围沿用 [D1 授权](tsm-6k-rejection-20261023-d1.md)。基线：`investigation/tsm-6k-20261022`，HEAD `26ed15b91fc3ee81d5c6cde4dbd0a4fa709d2536`，包 `0.1.5`。本轮仅写计划，未修改实现、测试、版本或运行验证。下一入口：总控核对后 resume 实现。

## Owner 与改动

动机成立：`warn_insufficient_filings` 把所有 raw skipped 算有效；正常 summary 与 typed row 已排除 `6k_filtered`，但各有重复判定。取消函数实际名为 `_cancelled_pipeline_completed_event`，其 skipped 计数也未排除拒绝；当前早期取消调用只传空行，不能夸称已观测到非空快照错误。

新增层内真源 `dayu/fins/pipelines/sec_download_disposition.py`：

```python
def project_sec_filing_disposition(
    item: Mapping[str, JsonValue],
) -> FinsDownloadDocumentDisposition: ...
```

仅将 SEC 确认行投影为现有 enum：downloaded/failed/显式 rejected 直接映射；skipped 的 `skip_reason` 或 `reason_code` 为 `6k_filtered` 时映射 REJECTED，其余保留 SKIPPED。沿用 typed 边界的严格文本语义，缺失/非法 status、参与判定的非法原因字段抛 ValueError；禁止 `str()` 宽松转换、文件特判、注册表反推或默认分类。该模块只依赖公共 JSON、现有下载契约与标准库，不依赖 pipeline facade/workflow，避免循环；不放 runtime，不增加 schema、wrapper 或兼容导出。

删除 workflow/pipeline 两份 `_is_rejected_filing_result`。`_build_sec_download_result` 按投影互斥统计四类；取消事件复用此 builder，完整性中止继续使用它。`_project_sec_document_row` 消费同一 disposition，保留字段校验、原因类别/安全文案、locator 与 `from_document_rows` 计数契约。诊断三组有效数统一仅纳入 DOWNLOADED/SKIPPED；注册表补充说明及阈值不变。保留 raw status/reason、持久化和公开字段；不改 downloader、6-K 政策、CLI 或其它日志。

## 同源验证与文档

新增 `tests/fins/test_sec_download_disposition.py`，覆盖四值、两原因入口、非法输入；在现有 download/stream 测试复用真实隔离仓储及工作流确认行，联验 raw summary、typed row/summary、warning：①拒绝有效0/rejected1/skipped0；②完整缓存再次下载跳过仍有效1；③两份有效加一份拒绝，有效2/rejected1且仍报低于3。覆盖年报/季报/DEF14A 分组控制，禁止 mock 投影或计数 owner。

补失败行不计有效、拒绝资产下载失败原类别；回归完整性中止的拒绝前缀/原 cause/行守恒、三个循环尾及 repair 后取消。早期取消保零行；取消 builder 以同一确认行集验证互斥计数，不制造生产可达性。维持严格非法字段拒绝。

只改 `pyproject.toml` 的 project version 为 `0.1.6`，不改 SEC download version。wheel 核对文件名、METADATA 版本及改动源码字节，不以已安装 metadata 冒充被测版本，不安装。

已读 README 职责：Fins 补稳定的有效/拒绝计数语义，tests 补回归边界与命令；根 README 操作/排障步骤未变，无需更新；整体分层未变，`dayu/README.md` 无需更新。

一个 slice；属于既有契约内部投影收束，无重要契约/架构/迁移/状态机决策，无需独立 planreview，由总控核对。

## 实施后命令与证据

所有新数据/临时脚本置于 D；旧 s1/controller 只读。以下命令仅为待执行计划，各自记录命令、stdout/stderr、退出码、HEAD/diff、源码路径/hash 与版本。

```bash
source .venv/bin/activate
D=workspace/tmp/tsm-6k-20261022/d1
mkdir -p "$D"
export COVERAGE_FILE="$PWD/$D/.coverage"
python -m pytest tests/fins/test_sec_download_disposition.py tests/fins/test_sec_pipeline_download.py tests/fins/test_sec_pipeline_download_stream.py tests/fins/test_sec_pipeline_upload_filing_stream.py tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_sec_earnings_repair.py -q --basetemp="$D/pytest" --junitxml="$D/pytest.xml" --cov=dayu.fins.pipelines.sec_download_disposition --cov=dayu.fins.pipelines.sec_download_workflow --cov=dayu.fins.pipelines.sec_download_diagnostics --cov=dayu.fins.pipelines.sec_pipeline --cov-report=term-missing --cov-report=json:"$D/coverage.json"
pyright --outputjson > "$D/pyright.json"
python -m pip wheel . --no-index --no-deps --no-build-isolation --wheel-dir "$D/wheel"
python "$D/check_wheel.py" --wheel-dir "$D/wheel" --expected-version 0.1.6
python "$D/verify_offline.py" --capture workspace/tmp/tsm-6k-20261022/s1/pipeline-requests --output "$D/offline"
```

两个临时脚本由实现阶段编写。离线脚本逐请求匹配 method/URL/顺序及响应 hash，无网络 transport/缺项兜底，须耗尽记录；fresh base 经真实 CLI→workflow→仓储，断言有效0/rejected1、active0、原拒绝原因与原件不变，保存新 warning/typed/持久化读回及输入清单。不得复用旧运行结果作为通过证据。

改动生产文件逐文件覆盖率目标≥80%，据报告补必要分支，不排除生产行；全量 pyright 零新增/扩散错误，触及已有错误须修复。范围内风险由当前 slice 消除：严格校验、失败/取消计数漂移；离线补证只证明保存响应的修后行为，不能复原历史 GET。live 同步归后续明确授权，merge 另授权。当前无真正 blocker。
