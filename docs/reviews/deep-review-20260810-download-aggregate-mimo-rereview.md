# WU-CLI-DOWNLOAD-01 Aggregate Rereview — AgentMiMo

- 日期：2026-08-10
- 基线：`9e30896accb28c44a647b57612b24ac5e50e3ce0`（HEAD，含 4 slice + docs closeout）
- 审查范围：未提交 diff（2 files, +2/-19）+ aggregate fix artifact + DS aggregate artifact + MiMo aggregate artifact
- 审查目标：
  1. 删除旧 local-exit renderer 是否完整且 canonical Fins cancelled terminal 不回归
  2. F-DS-03/04 拒绝修复是否有 owner/call-chain 直接证据
  3. F-DS-05 与 OBS residual 是否仍成立
  4. 是否引入新 correctness/stability/maintainability finding
- 结论：**PASS**

---

## 1. 未提交 diff 概要

| 文件 | 变更 |
|---|---|
| `dayu/cli/output.py` | 删除 `_FINS_LOCAL_EXIT_AFTER_CANCEL_MESSAGE` 常量（:59）、`render_fins_direct_local_exit_after_cancel` 函数（:279-293）、对应 `__all__` 导出（:589） |
| `tests/cli/test_fins_commands.py` | 在 `test_sigint_requests_token_and_waits_without_job_id` 增加两条断言：`"Fins cancelled" in captured.err` 和 `"local process exiting" not in captured.err` |

---

## 2. F-DS-01/02 修复完整性验证

**目标**：确认旧 `render_fins_direct_local_exit_after_cancel` 完整删除，canonical Fins cancelled terminal 不回归。

### 2.1 删除完整性

- `output.py` diff：`_FINS_LOCAL_EXIT_AFTER_CANCEL_MESSAGE`（常量）+ `render_fins_direct_local_exit_after_cancel`（函数）+ `__all__` 导出，三处全部删除。
- `rg -n "render_fins_direct_local_exit_after_cancel|_FINS_LOCAL_EXIT_AFTER_CANCEL_MESSAGE" --glob '*.py'`：exit 1（0 hits）。无 Python 消费者残留。
- docs/gateflow 中的 .md 引用属于不可变 artifact，不影响可执行代码。

### 2.2 Canonical cancelled terminal 不回归

- `output.py:63`：`_FINS_EVENT_CANCELLED_PREFIX: Final[str] = "Fins cancelled"` 仍在。
- `output.py:244-249`：`render_fins_direct_event` 对 `FinsResultStatus.CANCELLED` 打印 `Fins cancelled:` 行到 stderr。
- `test_fins_commands.py:1592-1599`：增强的断言验证 `result.status is FinsResultStatus.CANCELLED`、`exit_code == 130`、`"Fins cancelled" in captured.err`、`"local process exiting" not in captured.err`。

### 2.3 import 链验证

- `fins.py` diff（已提交）只 import `render_fins_direct_cancel_requested` 和 `render_fins_direct_event`，不 import 删除的函数。
- `python -c "from dayu.cli.output import render_fins_direct_cancel_requested, render_fins_direct_event"` 成功。

**判定**：**PASS**。旧 local-exit renderer 完整删除，canonical cancelled terminal 通过 `render_fins_direct_event` 正确投影。

---

## 3. F-DS-03 拒绝的 call-chain 证据验证

**DS finding**：`SecDownloader.configure()` 允许二次同值调用，异常文案称"一次性配置"但实现允许幂等。

**Fix disposition**：REJECTED AS NON-DEFECT。

**独立 call-chain 验证**：

1. `sec_pipeline.py:518-521`：`SecPipeline.__init__` 创建 `SecDownloader(workspace_root=..., user_agent=user_agent)`。构造时 `_resolve_user_agent` 冻结 UA 身份（`sec_downloader.py:1098`）。
2. `sec_download_workflow.py:409-414`：每次非 rebuild SEC download operation 调用 `host._downloader.configure(user_agent=host._user_agent, sleep_seconds=..., max_retries=...)`。`host._user_agent` 来自 pipeline 构造时的同一 UA 值。
3. `sec_downloader.py:1176-1178`：`configure()` 只在 `configured_value and configured_value != self._user_agent` 时抛 `ValueError`。同值（包括 `None`）不抛异常、不重复 warning。
4. `sec_downloader.py:1179-1183`：同值 configure 只更新 `_sleep_seconds` 和 `_max_retries`（transport policy），不改变 UA 身份。

**关键推理**：若改为拒绝任何 configure 调用（含同值），标准 SEC operation 在首次 workflow configure 时就失败。若取消 configure 调用，sleep/retry 的 per-operation 装配失去唯一入口。当前 contract 的真实语义是"UA 身份不可变"，不是"方法只可调用一次"。

**判定**：**PASS**。拒绝修改有直接 production call-chain 证据支持。异常文案"一次性配置"表述不精确但不产生实际危害。

---

## 4. F-DS-04 拒绝的 owner validation 证据验证

**DS finding**：`_required_cn_text_list` 对 `missing_periods` 的 loose parsing risk。

**Fix disposition**：REJECTED AS DUPLICATE OWNER VALIDATION。

**独立投影链验证**：

1. `cn_pipeline.py:1385`：`_summary_from_pipeline_result(...)` 被调用。
2. `cn_pipeline.py:1421`：`missing_periods = _required_cn_text_list(result, "missing_periods")` 从 CN workflow private dict 读取 period 列表。
3. `cn_pipeline.py:1423`：`FinsDownloadResultSummary.from_document_rows(... missing_periods=missing_periods ...)` 把 periods 传入 typed constructor。
4. `download_contract.py:362-365`：`from_document_rows` 构造 `FinsDownloadResultSummary`。
5. `download_contract.py:296-365`：`__post_init__` 对 `self.missing_periods` 逐项调用 `_validate_public_text(period, field_name="missing_period", allow_none=False)`（:364-365），校验非空、长度、URL/路径/payload 模式。

**关键推理**：`_required_cn_text_list` 的返回值在到达任何 public contract 之前，必须经过 `FinsDownloadResultSummary.__post_init__` 的 fail-closed validation。在 `_required_cn_text_list` 后再加 `_validate_public_text` 会制造重复 owner，违反语义所有权约束。

**判定**：**PASS**。拒绝修改有直接 typed constructor owner 证据支持。

---

## 5. F-DS-05 与 OBS-1..3 residual 验证

### F-DS-05：blocking writer 无上界等待（MEDIUM residual）

- `_fs_storage_infra.py:1512`：`_acquire_ticker_lock` 使用 `blocking=True`，无显式超时。
- plan §11 明确接受：底层 OS/文件系统永久 I/O hang 可能使 blocking writer 无限等待。
- 正常 commit/rollback 路径统一 release/notify（`_close_active_batch` 的 `finally`）。
- `begin_batch` 前所有远端 I/O 已完成，transaction 只含本地 staging/publication。

**判定**：仍为已记录 residual。不修。

### OBS-1：UA warning per-downloader-instance

- 当前 composition 每 command 创建一个 `SecPipeline`/downloader（`SecPipeline.__init__`）。
- 没有 retry/factory 重建 downloader 的当前调用路径。

**判定**：仍为已记录 residual。不改。

### OBS-2：blocking writer 无超时

- 同 F-DS-05。

**判定**：仍为已记录 residual。不改。

### OBS-3：SIGKILL parent 残留 system-temp

- `cn_docling_process.py:166`：`finally` 块的 `shutil.rmtree(temp_root)` 在正常 cancel/failure/cleanup 路径执行。
- parent 被 SIGKILL 时 `finally` 不执行，system-temp 残留。

**判定**：仍为已记录 residual。不改。

---

## 6. 新 correctness/stability/maintainability finding 检查

未提交 diff 只有两处变更：

1. **output.py 删除**：删除的是 0 Python 消费者的死代码。不引入新依赖、不改变已有函数签名、不改变已有渲染逻辑。
2. **test 断言增加**：在已有 test 中增加 `"Fins cancelled" in captured.err` 和 `"local process exiting" not in captured.err`。这两条断言验证的是已有 canonical terminal 路径（`render_fins_direct_event` 对 CANCELLED 的渲染），不引入新 mock 或新行为。

**不引入新 finding 的理由**：
- 无新 production 代码逻辑。
- 无新 public contract 或 schema。
- 无新依赖关系。
- test 断言只验证已有行为的不变量。

---

## 7. DS aggregate 未覆盖项确认

DS aggregate §11 列出的未覆盖项仍然成立：

| 未覆盖项 | 状态 |
|---|---|
| DL-G01..G05 真实 CLI 运行 | 不在 aggregate review 范围 |
| Oracle/scenario registry 更新 | 仍在 Oracle pause 前 |
| `interruptible_process.py` | 未修改（0 diff） |
| `cli_ci_oracles.json` / `cli_ci_scenarios.json` | 未修改 |

---

## 8. 总结

| 验证项 | 判定 |
|---|---|
| F-DS-01/02 修复完整性 | PASS — 旧 renderer 三处删除，rg 0 hits |
| Canonical cancelled terminal 不回归 | PASS — `Fins cancelled` prefix 仍在，test 断言覆盖 |
| F-DS-03 拒绝有 call-chain 证据 | PASS — configure per-operation 同值调用链完整 |
| F-DS-04 拒绝有 owner validation 证据 | PASS — `__post_init__` 是 fail-closed 防线 |
| F-DS-05 residual 仍成立 | PASS — plan §11 已接受 |
| OBS-1..3 residual 仍成立 | PASS — 不变 |
| 新 correctness/stability finding | PASS — 无新 finding |
| 新 maintainability finding | PASS — 无新 finding |

**结论：PASS**。
