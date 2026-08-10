# AgentDS Documentation Closeout Review — WU-CLI-DOWNLOAD-01

- **Reviewer**: AgentDS（第二路独立 docs review）
- **Date**: 2026-08-10
- **Baseline**: `5f5b19949817eaeaa309cf5f75135f57a29e4c14`
- **Closeout artifact**: `docs/gateflow/wu-cli-download-01-docs-closeout-20260810-093827.md`
- **Scope**: 未提交 working tree diff 中的 `README.md`、`dayu/fins/README.md`、`tests/README.md`；`dayu/README.md` 零 diff 确认
- **Verdict**: **PASS** — 无 blocking finding

## 1. 审查方法

对三份 README 的每一个新增/修改断言，逐条在生产代码中查找直接反证。方法：

1. 完整阅读三个 diff（+增加行/-删除行）
2. 用 `grep` 在生产代码中交叉验证每条事实声明
3. 检查旧述是否完全清除（`rebuild_processed` for download、`asyncio.to_thread` for Docling）
4. 检查是否泄漏内部治理标识（BatchToken、Phase A/B、reservation 等术语是否出现在用户文档中）
5. 检查 tests README 是否引入 work-unit 术语或未存在测试的宣称
6. `dayu/README.md` 零 diff 确认

## 2. 根 README.md 逐条验证

| 文档声明 | 生产代码证据 | 判决 |
|---|---|---|
| 静态用法校验先于 workspace/runtime | `dayu/service/fins_direct.py:440-466` `build_direct_download_request` → `build_fins_download_request` 在 runtime 构造前完成；`FinsDownloadUsageError` 在 `:463` 声明 | **PASS** |
| 非法输入退出码 `2` | `dayu/cli/exit_codes.py:10` `EXIT_USAGE_ERROR: int = 2` | **PASS** |
| 零 workspace/runtime 副作用 | `build_fins_download_request` 是纯函数，不接触文件系统、不解析 workspace、不构造 runtime | **PASS** |
| `--ticker` 只接受一个 ticker | `build_fins_download_request` 拒绝 CSV — plan §5.1 明确规定 single ticker（Slice 1 实现） | **PASS** |
| `--forms` 按市场规范化、稳定去重 | SEC/CN domain form parsers 在 `filing_semantics.py` 中统一 canonicalize + dedupe | **PASS** |
| `--start`/`--end` YYYY/YYYY-MM/YYYY-MM-DD → 包含边界窗口 | `FinsDownloadDateRange.__post_init__` 展开为 inclusive bound（plan §5.1） | **PASS** |
| SEC User-Agent 必须配置 | `sec_downloader.py:2297-2320` `_resolve_user_agent`；`:2335-2336` `SecUserAgentConfigurationError` 在 UNCONFIGURED 时抛出；`:112` 环境变量 `SEC_USER_AGENT` | **PASS** |
| `--overwrite` 只替换单目标、不删除非目标旧文档 | `sec_download_workflow.py` 无 `_cleanup_stale_filing_dirs` 调用（已删除）；overwrite 只影响当前 `begin_batch` 内的 target | **PASS** |
| `--rebuild` 不发送 provider 请求、不修改 source | `sec_rebuild_workflow.py:99-204` 从本地 source meta/files 读取并重建；不调用 downloader/provider；不 write source bytes | **PASS** |
| 下载摘要含规范 ticker、forms、日期窗口、overwrite/rebuild、counts、缺失期间 | `FinsResultSummary` typed contract 包含这些字段（Slice 2 实现） | **PASS** |
| Ctrl-C → 协作取消 → 退出码 `130` | `dayu/fins/direct_events.py:30` `FINS_RESULT_EXIT_CANCELLED: Final[int] = 130`；`:942-943` cancelled result 强制校验 exit code 130 | **PASS** |
| 不用内部取消原因替代用户可见摘要 | cancelled terminal 只由 Fins owner 产生唯一 RESULT event；CLI 机械使用其 exit code | **PASS** |

### 2.1 精度备注

- "下载 SEC 文件前必须提供合规的 User-Agent 身份"：此句按字面理解是准确的——"下载 SEC 文件前" 仅当实际需要下载时适用。`--rebuild` 模式不发 provider 请求，此时不需要 User-Agent；该句未声称 rebuild 也需要。**无需修改**。
- 示例 `export SEC_USER_AGENT="Your Organization contact@example.com"` 中 `contact@example.com` 是明确的占位示例，不会被视为可工作的真实值。**无需修改**。

## 3. dayu/fins/README.md 逐条验证

| 文档声明 | 生产代码证据 | 判决 |
|---|---|---|
| 同进程 per-ticker condition 等待 | `_fs_storage_infra.py:449` `threading.Condition()`；`:1261-1263` `_reserve_batch_ticker` while loop + wait | **PASS** |
| 跨进程 blocking writer lock 串行化 | `_fs_storage_infra.py:1512` `blocking=True` in `_acquire_ticker_lock` | **PASS** |
| recovery nonblocking try-lock | `_fs_storage_infra.py:1877` `blocking=False` in `_try_acquire_recovery_ticker_lock` | **PASS** |
| 统一 release/notify | `_fs_storage_infra.py:1328-1329` `_close_active_batch` finally 块 discard + notify_all | **PASS** |
| 不使用 timeout 猜测写者完成 | 无任何业务 timeout 参数或 sleep | **PASS** |
| `MISSING`/`COMPLETE`/`REPAIR_REQUIRED` typed integrity | `source_integrity.py:13-18` `SourceIntegrityStatus` enum | **PASS** |
| malformed SHA-256 结构损坏直接失败 | `_fs_storage_infra.py:307` `_require_canonical_sha256`；`_fs_source_document_core.py:640` 调用并 raise ValueError（不降级为 repair） | **PASS** |
| whole-tree preflight 在 company/maintenance/rejected 前 | `sec_download_workflow.py:583-584` `classify_source_integrity_preflight` + `list_source_integrity` 在 `:814-826` company 前；`cn_download_workflow.py:223-224` 同理 | **PASS** |
| 单一选中损坏 target repair-first | `sec_download_workflow.py:589-593` `SelectedSourceRepairRequired` → stable partition；`:650-684` repair 完成后才进入 company | **PASS** |
| 多处/未选中 corruption fail closed | `source_integrity.py:214-215` `MULTIPLE_REPAIR_REQUIRED`；`:222-223` `UNSELECTED_REPAIR_REQUIRED` | **PASS** |
| repair transport 始终重新获取（unconditional） | `sec_download_filing_workflow.py:480-483` `allow_not_modified=False` for repair | **PASS** |
| Phase B 按原 overwrite policy + 同版 identity 决定 | `sec_download_filing_workflow.py:494-549` `classify_staged_source_integrity` + identity check + overwrite check | **PASS** |
| provider/PDF/Docling I/O 不在 writer reservation 内 | prefetch + PDF/Docling 在 `begin_batch` 前完成；batch 内只有 staged classification + materialize + upsert + validator | **PASS** |
| `rebuild_local_artifacts=true` local-only，不调 provider | `sec_pipeline.py:1856` `rebuild=request.rebuild_local_artifacts`；rebuild 内部只读本地 source | **PASS** |
| 与 preprocess `rebuild_processed` 是两个独立 owner | download contract 中只有 `rebuild_local_artifacts`；preprocess 保留同名 `rebuild_processed` | **PASS** |
| Docling 子进程 + terminate/kill/close + temp 清理 | `cn_docling_process.py:91-177` `ProcessCnDoclingConversionRunner` 使用 `InterruptibleProcessHandle` | **PASS** |
| 转换失败/取消/损坏不发布半成品 source | conversion completed checkpoint 在 batch 前；失败不回退已发布 old tree | **PASS** |
| `FinsResultSummary` typed terminal | `download_contract.py` 中 typed result summary（Slice 2 实现） | **PASS** |
| SEC 首个 HTTP 前要求 User-Agent | `sec_downloader.py:2335-2336` `_resolve_user_agent_header` raises if UNCONFIGURED | **PASS** |
| 缺失身份/provider failure/取消/完整性失败按封闭类型进入 terminal | `direct_events.py` closed failure classification | **PASS** |

### 3.1 旧述清除确认

| 旧述 | 搜索 | 结果 |
|---|---|---|
| "Production download adapter 必须消费 `FinsDownloadRequest.rebuild_processed`" | `grep -n` in `dayu/fins/README.md` | **零命中** |
| "CN/HK Docling convert 当前通过 `asyncio.to_thread`" | `grep -n` in all three READMEs | **零命中** |
| "同 ticker writer mutex"（旧术语，非 reservation-based） | `grep -n` in `dayu/fins/README.md` | 已被 "reservation" + "blocking writer lock" 替代 |

## 4. tests/README.md 逐条验证

### 4.1 术语检查

| 检查项 | 搜索 | 结果 |
|---|---|---|
| work unit 术语（"work unit"/"WU-"/"Slice"/"Phase.*gate"/"Gateflow"） | `grep -n` in `tests/README.md` | **零命中** |
| "同 ticker writer mutex"（旧术语）→ 替换为 "同 ticker writer reservation 与跨进程 blocking lock" | diff 确认 | **已替换** |
| "production persisted-summary adapter 消费 `rebuild_processed`"（旧述） | `grep -n` in `tests/README.md` | **零命中** |

### 4.2 新增 Download owner coverage 段落 → 既有测试映射

| 文档声称的覆盖 | 对应测试文件/场景 | 判决 |
|---|---|---|
| ticker/forms/date 静态校验 | `tests/cli/test_arg_parsing.py`、`tests/cli/test_fins_commands.py` | **PASS** |
| 显式 start-window → SEC SC13 | `tests/fins/test_sec_pipeline_download.py` | **PASS** |
| 普通下载不执行 stale prune | 代码中 `_cleanup_stale_filing_dirs` 已删除；AST 静态 gate 可证明 | **PASS** |
| CN 缺失期间不伪装 skipped | `tests/fins/test_cn_download_workflow.py` | **PASS** |
| SEC User-Agent prerequisite | `tests/fins/test_sec_downloader.py` | **PASS** |
| overwrite 单目标非删除 | `tests/fins/test_sec_pipeline_download.py`、`tests/fins/test_cn_download_workflow.py` | **PASS** |
| 仅从本地 source 重建（provider 零调用） | rebuild workflow 由 pipeline tests 间接覆盖 | **PASS** |
| typed terminal summary | `tests/fins/test_fins_ingestion_runtime.py` | **PASS** |
| Docling 子进程 terminate/kill/close | `tests/fins/test_cn_docling_process.py`（Slice 3） | **PASS** |
| 同目标双 overwrite last-writer | `tests/fins/test_sec_pipeline_download.py` barrier-based test | **PASS** |
| 不同目标 union | `tests/fins/test_sec_pipeline_download.py` barrier-based test | **PASS** |
| async generator 提前关闭 | `tests/fins/test_sec_downloader.py::test_download_files_stream_aclose_finalizes_shared_prefetch_generator` | **PASS** |
| Phase A prefetch 后 identity/revision churn | `tests/fins/test_sec_pipeline_download.py` 3-round retry test | **PASS** |
| repair unconditional transport | `tests/fins/test_sec_downloader.py`、`tests/fins/test_sec_pipeline_download.py` | **PASS** |
| MISSING/COMPLETE/REPAIR_REQUIRED 分类 | `tests/fins/test_fins_storage_provider.py` | **PASS** |
| size/digest corruption repair | `tests/fins/test_fins_storage_atomicity.py` | **PASS** |
| malformed SHA-256 strict | `tests/fins/test_fins_storage_atomicity.py` | **PASS** |
| whole-tree repair-first revalidation | `tests/fins/test_sec_pipeline_download.py`、`tests/fins/test_cn_download_workflow.py` | **PASS** |
| multiple/unselected corruption fail closed | `tests/fins/test_sec_pipeline_download.py::test_sec_top_level_unselected_corruption_fails_before_company_batch`、`tests/fins/test_cn_download_workflow.py::test_cn_no_filing_with_corruption_fails_before_company_batch` | **PASS** |
| Event/barrier 而非 sleep 控制时序 | 所有 race test 使用 `threading.Event`/`multiprocessing.Event`/`Barrier` | **PASS** |

### 4.3 无过强承诺

- "并发与完整性矩阵以 Event/barrier 而非 sleep 控制时序" — 描述的是测试设计原则，不承诺生产行为。**PASS**。
- 段落中无 "always"、"never fails"、"guarantees" 等绝对化词汇。**PASS**。

## 5. dayu/README.md 零 diff 确认

```bash
git diff --exit-code -- dayu/README.md
# exit code 0
```

`UI -> Service -> Host -> Engine` 主链、Fins direct 边界与 `dayu.runtime` 层中立边界均未变化，与 closeout artifact §1 裁决一致。**PASS**。

## 6. 残余风险

- 文档只投影当前已接受代码的事实；未来若修改 SEC User-Agent policy、rebuild 语义或 cancel contract，三份 README 需同步更新。
- 根 README 的 SEC User-Agent 示例使用占位邮箱 `contact@example.com`——首次使用者可能误以为不需要替换。当前示例格式明确可辨认为占位符，风险为低。

## 7. 判决

**PASS**

三份 README 的修改均与生产代码一致：
- 根 `README.md`：最终用户可见的 download 行为（静态校验、单 ticker、UA 前提、overwrite 非删除、rebuild local-only、cancel 130、终端摘要）均准确，无内部治理泄漏。
- `dayu/fins/README.md`：package 级 contract（blocking writer、recovery try-lock、typed integrity、whole-tree preflight、repair-first、Docling 子进程、rebuild_local_artifacts 与 rebuild_processed 分离）均准确，旧述已清除。
- `tests/README.md`：既有测试覆盖事实准确，无 work-unit 术语，无未存在测试的宣称。
- `dayu/README.md`：零 diff。

无 blocking finding。无修改要求。
