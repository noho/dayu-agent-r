# WU-CLI-DOWNLOAD-01 Aggregate Deep Review Fix

## 1. Gate 与边界

- 日期：2026-08-10
- 基线 HEAD：`9e30896accb28c44a647b57612b24ac5e50e3ce0`
- review 真源：
  - `docs/reviews/deep-review-20260810-download-aggregate-ds.md`
  - `docs/reviews/deep-review-20260810-download-aggregate-mimo.md`
- 本轮只处理 aggregate review 已接受 finding；未运行真实 CLI 或 provider，未修改 Oracle、scenario registry、readiness、两份 review artifact、历史 PR 190，也未 commit、push 或创建 PR。
- 开始时两份 aggregate review artifact 已是未跟踪文件；它们属于 reviewer 输出，本轮保持原样。

## 2. 第一性原理裁决

### F-DS-01 / F-DS-02 — 接受并修复

**Disposition：FIXED。**

`dayu/cli/commands/fins.py` 当前只 import `render_fins_direct_cancel_requested` 与 `render_fins_direct_event`。SIGINT owner 首次观察到取消时只请求 cancellation token 并渲染 request acknowledgement，随后继续等待 validated Fins stream clean exhaustion；terminal event 仍由 `render_fins_direct_event` 机械投影。旧 `render_fins_direct_local_exit_after_cancel` 没有 production/test Python 消费者，却仍暴露旧的 CLI-local exit 语义，因此属于 owner 边界清理遗漏，而不是兼容 contract。

本轮从 `dayu/cli/output.py` 删除：

- `_FINS_LOCAL_EXIT_AFTER_CANCEL_MESSAGE`；
- `render_fins_direct_local_exit_after_cancel`；
- 对应 `__all__` 导出。

同时增强既有 deterministic SIGINT owner test：取消请求后 task 仍未结束；释放 Fins stream 后结果必须是 canonical `CANCELLED`/130，stderr 必须包含 `Fins cancelled` terminal projection，且不得出现旧 `local process exiting` 文本。

全仓 Python 消费者 gate：

```text
rg -n "render_fins_direct_local_exit_after_cancel|_FINS_LOCAL_EXIT_AFTER_CANCEL_MESSAGE" . --glob '*.py'
exit 1（0 hits）
```

历史 plan/review 文档中的文字记录不是可执行消费者，本轮按不可变 artifact 约束不修改。

### F-DS-03 — 拒绝产品修改

**Disposition：REJECTED AS NON-DEFECT。**

异常文案不是 contract 判断依据。直接调用链证明同值重入是当前装配所需：

1. `SecPipeline.__init__` 在 `dayu/fins/pipelines/sec_pipeline.py:518-521` 创建并持有唯一 `SecDownloader`，构造时即解析并冻结 UA 身份。
2. 每次非 rebuild SEC operation 都在 `dayu/fins/pipelines/sec_download_workflow.py:409-414` 对同一 downloader 调用 `configure`，用于应用当前 pipeline 的 `sleep_seconds` 与 `max_retries`。
3. `SecDownloader.configure` 在 `dayu/fins/downloaders/sec_downloader.py:1170-1183` 更新可变 transport policy，但只拒绝与构造期真源不同的非空 UA；同值 UA 不改变身份，也不重复解析环境或发 warning。
4. owner test helper `tests/fins/test_sec_downloader.py:100-105` 也从构造期 UA 进入同值 configure，覆盖与 production 相同的装配关系。

若改为拒绝任何 configure 调用或拒绝相同 UA，标准 SEC operation 会在首次 workflow configure 就失败；若取消 configure，则 sleep/retry 的 operation 装配失去唯一入口。当前 contract 的真实含义是“UA 身份不可变”，不是“方法只可调用一次”。因此不修改 protocol、docstring、异常或实现。

### F-DS-04 — 拒绝下游重复校验

**Disposition：REJECTED AS DUPLICATE OWNER VALIDATION。**

完整 public 投影链为：

```text
CN/HK workflow private result dict
  -> CnDownloadAdapter.download
  -> _summary_from_pipeline_result
  -> FinsDownloadResultSummary.from_document_rows
  -> FinsDownloadResultSummary.__post_init__
  -> FinsSourceDownloadAdapterResult.persisted_summary
```

直接证据：

- `dayu/fins/pipelines/cn_pipeline.py:1356-1364` 只有在 `_summary_from_pipeline_result` 返回 typed summary 后才构造 adapter public result；
- `dayu/fins/pipelines/cn_pipeline.py:1385-1429` 无条件把 `_required_cn_text_list` 的 `missing_periods` 交给 `FinsDownloadResultSummary.from_document_rows`；
- `dayu/fins/download_contract.py:362-365` 的 summary constructor 是该 public 语义唯一 owner，对重复值及每个 period 的 strict public text 执行 fail-closed validation；
- 全部 `_summary_from_pipeline_result` production 调用点枚举只有上述 adapter 路径，没有绕过 constructor 的 public projection；`_required_cn_text_list` 的另一调用只用于 typed effective filters，最终也进入 typed owner。

因此不存在脏 `missing_periods` 到达 public contract 的绕过路径。把 `_validate_public_text` 再放进 CN 私有 dict parser 会制造重复语义 owner，违反 owner-boundary 约束；本轮不改产品或测试。

### F-DS-05 — 接受 residual，不修

**Disposition：ACCEPTED RESIDUAL / NO CHANGE。**

plan §11 已明确接受底层 OS/文件系统永久 I/O hang 可能使 blocking writer 无上界等待。本 WU 明确禁止引入任意业务 timeout；正常 commit/rollback 路径仍统一 release/notify。该 finding 不构成当前实现缺陷。

### MiMo OBS-1..3

- **OBS-1：记录 residual，不改。** 当前 composition 每 command 创建一个 `SecPipeline`/downloader；UA warning 只在 downloader 构造期解析时产生一次。没有 retry/factory 重建 downloader 的当前调用路径。
- **OBS-2：记录已接受 residual，不改。** 与 F-DS-05 相同，是 plan §11 的 OS/file-lock 永久 hang 风险。
- **OBS-3：记录已接受 residual，不改。** parent 被不可收口的 SIGKILL 直接终止时，system temp 可能残留；plan 已明确不为此在 workspace 新增 stale scavenger。正常 cancel/failure 路径仍由 process owner 清理。

## 3. Changed files

- `dayu/cli/output.py`
  - 删除旧 Fins local-exit renderer、message constant 与导出。
- `tests/cli/test_fins_commands.py`
  - 增强 canonical cancellation owner 断言：terminal renderer 可见，旧 local exit 不可见。
- `docs/gateflow/wu-cli-download-01-aggregate-fix-20260810.md`
  - 本 immutable fix artifact。

README 不更新：本轮只删除不可达且与当前稳定 contract 冲突的死导出，没有改变用户可见 CLI contract、Fins package contract 或测试职责说明。

## 4. 验证记录

所有命令均在仓库根目录执行；未运行真实 CLI/provider。

### 4.1 最小 owner 回归

```text
source .venv/bin/activate && pytest -q tests/cli/test_fins_commands.py::test_cli_stream_owner_sigint_waits_for_canonical_cancelled_terminal tests/cli/test_fins_commands.py::test_sigint_requests_token_and_waits_without_job_id tests/cli/test_fins_commands.py::test_terminal_failed_and_cancelled_status_exit_mapping tests/cli/test_output.py
exit 0
12 passed, 3 warnings in 1.13s
```

warnings 均来自已安装 `edgar` package 的 deprecation warning，不是本轮新增。

### 4.2 受影响 CLI union

```text
.venv/bin/pytest -q tests/cli/test_fins_commands.py tests/cli/test_output.py
exit 0
54 passed, 3 warnings in 1.36s
```

### 4.3 Changed-path pyright

```text
.venv/bin/pyright dayu/cli/output.py tests/cli/test_fins_commands.py
exit 0
0 errors, 0 warnings, 0 informations
```

### 4.4 Ruff / format

```text
.venv/bin/ruff check dayu/cli/output.py tests/cli/test_fins_commands.py
exit 0
All checks passed!
```

```text
.venv/bin/ruff format --check dayu/cli/output.py tests/cli/test_fins_commands.py
exit 0
2 files already formatted
```

### 4.5 Compileall

```text
.venv/bin/python -m compileall -q dayu/cli/output.py tests/cli/test_fins_commands.py
exit 0
```

### 4.6 Static/diff gates

```text
rg -n "render_fins_direct_local_exit_after_cancel|_FINS_LOCAL_EXIT_AFTER_CANCEL_MESSAGE" . --glob '*.py'
exit 1
0 hits
```

```text
git diff --check
exit 0
```

人工 diff 确认只有上述 production/test 删除与 owner test 断言；两份 aggregate review artifact 未被修改。

## 5. Gate 结论与剩余风险

- F-DS-01/02 已从 CLI output owner 完整清理。
- F-DS-03/04 经 production call graph 与 typed constructor owner 证据裁决为不应修改。
- F-DS-05 与 MiMo OBS-1..3 均保留为已记录 residual，不扩 scope。
- 当前停止在原 MiMo/DS aggregate rereview 门；不 commit、push 或创建 PR。
