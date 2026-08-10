# Deep Review Rereview — `dayu-cli download` Aggregate Fix (WU-CLI-DOWNLOAD-01)

## Gate 状态

- **Reviewer**: AgentDS（独立 rereview，不采信其它 reviewer 结论）。
- **基线**: `9e30896accb28c44a647b57612b24ac5e50e3ce0`（上次 aggregate HEAD）。
- **当前工作树**: 基线上未提交 diff（`dayu/cli/output.py`、`tests/cli/test_fins_commands.py`）。
- **日期**: 2026-08-10。
- **参照**: 原 DS aggregate artifact（`docs/reviews/deep-review-20260810-download-aggregate-ds.md`）、MiMo aggregate artifact（`docs/reviews/deep-review-20260810-download-aggregate-mimo.md`）、aggregate fix artifact（`docs/gateflow/wu-cli-download-01-aggregate-fix-20260810.md`）。
- **结论**: **PASS** — 0 新 findings。

---

## 1. F-DS-01/02 fix：死代码清理

**原 finding**（LOW）：`dayu/cli/output.py` 中的 `render_fins_direct_local_exit_after_cancel` 函数、`_FINS_LOCAL_EXIT_AFTER_CANCEL_MESSAGE` 常量及 `__all__` 导出在 DL-F09 修复后已成为死代码。

**fix 内容**（`git diff` 直接核实）：

- `output.py:59` — 删除 `_FINS_LOCAL_EXIT_AFTER_CANCEL_MESSAGE` 常量（-1 行）。
- `output.py:279-293` — 删除 `render_fins_direct_local_exit_after_cancel` 函数定义（-15 行）。
- `output.py:589` — 从 `__all__` 删除 `"render_fins_direct_local_exit_after_cancel"`（-1 行）。
- `test_fins_commands.py:1598-1599` — 增强 `test_sigint_requests_token_and_waits_without_job_id`：
  - 新增 `assert "Fins cancelled" in captured.err`（确认 canonical terminal 渲染可见）。
  - 新增 `assert "local process exiting" not in captured.err`（确认旧 local exit 文本不可见）。

**验证**：
- `rg "render_fins_direct_local_exit_after_cancel|_FINS_LOCAL_EXIT_AFTER_CANCEL_MESSAGE" . --glob '*.py'` → exit 1（0 hits），全仓 Python 消费者彻底清除。
- `pytest tests/cli/test_fins_commands.py tests/cli/test_output.py -q` → 54 passed，0 failed。
- `pyright dayu/cli/output.py tests/cli/test_fins_commands.py` → 0 errors，0 warnings。
- `ruff check` → All checks passed。`compileall` → OK。`git diff --check` → OK。

**rereview 判定**：**FIXED**。删除干净，无残留 import/call site/导出；新增 owner test 断言对旧行为形成 regression gate。不引入新 correctness/stability/maintainability finding。

---

## 2. F-DS-03 disposition：`SecDownloader.configure()` 同值重入

**原 finding**（LOW）：`configure()` 的异常文案声称"一次性配置"，但实现允许相同 UA 值的二次调用。

**fix 裁决**：**REJECTED AS NON-DEFECT**。

**独立 re-evaluation**：

直接代码证据（独立核对，不采信 fix artifact）：

1. `sec_pipeline.py:518-521` — `SecPipeline.__init__` 构造唯一 `SecDownloader` 时解析并冻结 UA 身份。UA 解析只发生一次。
2. `sec_download_workflow.py:409-414` — 每次非 rebuild SEC operation 在 `_configure_downloader` 中对同一 downloader 调用 `configure`，传 `sleep_seconds` 和 `max_retries`。
3. `sec_downloader.py:1170-1183` — `configure()` 更新 `self._sleep_seconds` 和 `self._max_retries`（mutable transport policy），但拒绝与构造期真源不同的非空 UA。同值 UA → 不改变身份 → 不重复解析环境 → 不发重复 warning。
4. `tests/fins/test_sec_downloader.py:100-105` — owner test helper 同样从构造期 UA 进入同值 configure。

语义 owner 的真实 contract 是"UA 身份不可变"，不是"方法只可调用一次"。`configure()` 除 UA 外还负责配置 `sleep_seconds` 和 `max_retries`，这两者在每次 operation 装配时需要重新传入。异常文案的措辞不精确但对调用方不构成误导（调用方只关心"不能用不同 UA 调用"）。

**rereview 判定**：**ACCEPT DISPOSITION**。不修。同值 configure 是 production pipeline 的正常装配路径；异常语义（"身份不可变"）与实现（"拒绝不同值，允许同值/None"）一致。若未来改进异常文案措辞，需独立 plan/review，不挂在本 WU。

---

## 3. F-DS-04 disposition：`_required_cn_text_list` 的 loose parsing

**原 finding**（LOW）：`cn_pipeline.py:1421` 的 `_required_cn_text_list` 未对每个 missing period 调 `_validate_public_text`。

**fix 裁决**：**REJECTED AS DUPLICATE OWNER VALIDATION**。

**独立 re-evaluation**：

直接代码证据（独立核对）：

1. `cn_pipeline.py:1356-1364` — `_summary_from_pipeline_result` 返回 typed `FinsDownloadResultSummary` 后才构造 adapter public result；若 constructor 抛异常，adapter result 不会被构造。
2. `cn_pipeline.py:1385-1429` — `_required_cn_text_list` 的返回值无条件传入 `FinsDownloadResultSummary.from_document_rows`。
3. `download_contract.py:362-365` — summary constructor 对每个 period 执行 `_validate_public_text(period, field_name="missing_period", allow_none=False)`。
4. 全量 `_summary_from_pipeline_result` production 调用点枚举：只有上述 adapter 路径。没有绕过 constructor 的 public projection。

绕过路径不存在：从 pipeline private dict → `_required_cn_text_list` → `from_document_rows` → `__post_init__` → `_validate_public_text` 是唯一直达 public contract 的调用链。`__post_init__` 是 fail-closed 最终防线。

如果在 `_required_cn_text_list` 处增加 `_validate_public_text`，会产生跨层重复语义 owner（CN pipeline 私有 dict parser 拥有与 typed contract constructor 相同的 validation 语义），违反 owner-boundary 约束。

**rereview 判定**：**ACCEPT DISPOSITION**。不修。typed constructor 是 public contract 唯一 owner 且 fail-closed；不存在绕过路径；重复校验违反语义所有权。

---

## 4. F-DS-05 residual

**原 finding**（MEDIUM — residual）：blocking writer lock 无上界等待。

**fix 裁决**：**ACCEPTED RESIDUAL / NO CHANGE**。

**rereview 判定**：维持。plan §11 已明确接受 OS 文件系统永久 I/O 是 residual。本 WU 明确禁止引入任意业务 timeout。正常路径统一 release/notify。不构成实现缺陷，不修。

---

## 5. MiMo aggregate findings 交叉检查

MiMo aggregate artifact 列出 3 个 LOW observation（OBS-1/2/3），0 correctness/stability finding。fix artifact 对其均裁决为 accepted residual。独立核对：

| MiMo finding | 当前状态 | 独立判定 |
|---|---|---|
| OBS-1: `SecDownloader` 构造期 warning 可能因 retry 重复 | 当前 composition 每 command 只构造一次 downloader；无 retry/factory 重建 | **ACCEPT RESIDUAL** |
| OBS-2: `blocking=True` 无超时 | 同 F-DS-05；plan §11 residual | **ACCEPT RESIDUAL** |
| OBS-3: SIGKILL 时 system-temp 残留 | plan 明确不新增 stale scavenger；正常 cancel/crash 路径有 cleanup | **ACCEPT RESIDUAL** |

无 new finding。

---

## 6. 当前未提交 diff 引入的新 finding 检查

| 维度 | 判定 | 证据 |
|---|---|---|
| Correctness | 无新 finding | diff 只删除死代码（-19 行）和增强已有 test 断言（+2 行），不改任何业务逻辑 |
| Stability | 无新 finding | 不引入 race condition、资源泄漏、边界条件变更 |
| Maintainability | 无新 finding | 测试增强了 regression gate（旧 local exit 文本不得出现） |
| 架构/分层 | 无新 finding | `output.py` 仍属 CLI UI 层，依赖方向不变 |
| Semantic ownership | 无新 finding | 旧 local exit 文本 owner 已被 CLI event consumer（Fins owner terminal）替代；清除剩余物是 owner boundary cleanup |
| Secret/contact | 无新 finding | 删除的函数只输出固定字符串常量 |
| Backward compatibility | 无新 finding | 被删除的符号没有任何 Python consumer（`rg` 0 hits） |

---

## 7. 验证证据总表

| 检查项 | 状态 |
|---|---|
| 死代码全仓清除 | PASS — `rg` 0 hits（exit 1） |
| owner test 通过 | PASS — 12 passed（focused）+ 54 passed（CLI union） |
| pyright | PASS — 0 errors, 0 warnings |
| ruff | PASS — All checks passed |
| compileall | PASS — OK |
| git diff --check | PASS — OK |
| 新 correctness/stability finding | 无 |
| 新增改动越出 fix 声明范围 | 无 — diff 精确为 `output.py`（-19）、`test_fins_commands.py`（+2） |

---

## 8. 结论

**PASS** — 0 新 findings。

- F-DS-01/02：**FIXED**，死代码完整清理，owner test 形成 regression gate。
- F-DS-03/04：**ACCEPT DISPOSITION**，production call graph 证据支持不修改。
- F-DS-05：**ACCEPT RESIDUAL**，plan §11 已记录。
- MiMo OBS-1/2/3：**ACCEPT RESIDUAL**。
- 当前 diff 不引入新 correctness/stability/maintainability finding。

原 DS aggregate artifact 中 DL-F01～F11 的 PASS 结论在本 rereview 后仍完全有效，无需修订。
