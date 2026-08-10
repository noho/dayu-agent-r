# WU-CLI-DOWNLOAD-01 Documentation Closeout Review — AgentMiMo

- 基线：`5f5b19949817eaeaa309cf5f75135f57a29e4c14`
- 审查对象：`README.md`、`dayu/fins/README.md`、`tests/README.md`、`docs/gateflow/wu-cli-download-01-docs-closeout-20260810-093827.md`
- 审查依据：各 README 更新约束、production code 真源
- 结论：**PASS**

---

## 1. 根 README（最终用户边界）

### 更新约束回读

根 README `Agent更新约束` 要求：只写用户完成安装、初始化、配置、财报下载/上传/预处理、提问、交互式分析、Session 管理、查看日志与排障所需的当前可用操作；不写 Host/Engine/Service/Runtime/Fins 内部架构、公共契约细节、状态机、测试清单、review/work unit 过程状态或开发者迁移计划。

### 逐项验证

| 检查项 | 直接证据 | 判定 |
|---|---|---|
| SEC_USER_AGENT 示例安全 | `README.md:267` 使用 `"Your Organization contact@example.com"` 占位符，非真实联系值 | PASS |
| `--rebuild` 准确 | `README.md:271-272`："只根据已经下载到本地的源文档重建下载元数据和 manifest，不发送数据提供方请求，也不新增、删除或替换源文档内容"。与 `FinsIngestionRuntime` 的 `rebuild_local_artifacts=true` 语义一致 | PASS |
| `--overwrite` 准确 | `README.md:270`："只替换本轮选中的单个目标文档，不会清空 ticker 下的其它已下载文档；空结果、失败或取消也不会删除非目标旧文档"。与 production storage 单目标替换语义一致 | PASS |
| usage exit 2 + 零副作用 | `README.md:258-259`："非法 ticker、表单或日期窗口以用法错误退出码 `2` 结束，并且不会产生 workspace 或下载运行期副作用"。与 `FinsDownloadUsageError` → CLI exit 2 映射一致 | PASS |
| Ctrl-C 取消 | `README.md:276-277`："下载期间按下 `Ctrl-C` 会请求协作取消并等待当前操作收口；取消终态使用规范退出码 `130`，不会用内部取消原因替代用户可见摘要"。与 Fins runtime canonical cancelled terminal 一致 | PASS |
| final summary 字段 | `README.md:274-275`："下载摘要包含规范 ticker、实际表单与日期窗口、overwrite/rebuild 状态，以及发现、下载、跳过、拒绝、失败和缺失期间信息"。与 `FinsResultSummary` typed 字段一致 | PASS |
| 单 ticker | `README.md:261`："只接受一个 ticker"。与 download builder 单 ticker grammar 一致 | PASS |
| 日期窗口展开 | `README.md:262-263`："接受 `YYYY`、`YYYY-MM` 或 `YYYY-MM-DD`，分别展开为所给期间的起始日和结束日，形成包含边界的日期窗口"。与 `FinsDownloadDateRange` 一致 | PASS |
| 仅用户可操作事实 | 无内部架构、状态机、测试清单或 review 过程状态 | PASS |

---

## 2. Fins README（package 开发者边界）

### 更新约束回读

Fins README `Agent更新约束` 要求：只写当前代码已实现的设计意图、架构边界、capability 定位、执行路径、对外接口、公共契约、稳定边界、主要组件、状态机、关键机制；代码真源高于历史 plan/review artifact；不写用户手册、安装运行命令、测试清单、文件级流水账或 review/work unit 过程状态。

### 逐项验证

| 检查项 | 直接证据 | 判定 |
|---|---|---|
| 移除 `rebuild_processed` download 旧述 | 旧文 "Production download adapter 必须消费 `FinsDownloadRequest.rebuild_processed`" 已被替换为 `rebuild_local_artifacts=true` local-only 模式描述。`rg` 确认 `rebuild_processed` 仅保留在 preprocess 的合法 owner contract 中 | PASS |
| 移除 `asyncio.to_thread` Docling 旧述 | 旧文 "CN/HK Docling convert 当前通过 `asyncio.to_thread(...)` 调用同步第三方转换函数" 已被替换为 "在独立子进程中执行；父进程持续观察 operation cancellation，取消时按 terminate、必要时 kill、close 的顺序回收子进程"。production `cn_docling_process.py` 使用 `InterruptibleProcessHandle` 子进程 | PASS |
| typed request 准确 | `dayu/fins/README.md:528`："下载入口只消费 `FinsDownloadRequest` 的 canonical ticker、市场化表单、包含边界的日期窗口、overwrite policy 与 `rebuild_local_artifacts`"。与 `download_contract.py` 的 `FinsDownloadRequest` 字段一致 | PASS |
| writer reservation 准确 | `dayu/fins/README.md:109`："同进程调用方通过 per-ticker condition 等待，跨进程调用方通过 blocking writer lock 串行化，不使用 timeout 猜测写者完成...所有 writer 退出路径统一释放 reservation 并通知等待者；recovery 只做 nonblocking try-lock"。与 `_fs_storage_infra.py` 的 Condition + blocking=True + nonblocking recovery 一致 | PASS |
| integrity classification 准确 | `dayu/fins/README.md:111`：`MISSING`/`COMPLETE`/`REPAIR_REQUIRED` 分类、malformed SHA-256 strict failure、whole-tree preflight、repair-first、multiple/unselected corruption mutation 前 fail closed。与 `source_integrity.py` 的 typed contract 一致 | PASS |
| repair transport 准确 | `dayu/fins/README.md:111`："repair transport 始终重新取得目标内容，Phase B 仍按原请求的 overwrite policy 与同版 identity 决定 publication；provider、PDF 与 Docling I/O 均不在 writer reservation 内执行"。与 SEC/CN Phase A/B identity-first 设计一致 | PASS |
| process cancellation 准确 | `dayu/fins/README.md:790`："CN/HK Docling convert 在独立子进程中执行；父进程持续观察 operation cancellation，取消时按 terminate、必要时 kill、close 的顺序回收子进程，并清理系统临时目录"。与 `ProcessCnDoclingConversionRunner` 实现一致 | PASS |
| 无内部测试清单或 review 状态 | README 不包含测试文件列表、work unit 过程状态或 review finding | PASS |

### 轻微观察

`asyncio.to_thread` 仍存在于 `cn_download_filing_workflow.py:216`，但用于 PDF 下载（`_download_report_pdf_with_gate`），不是 Docling 转换。Fins README 的修改精确地只针对 Docling，不涉及 PDF 下载。PDF 下载的 `asyncio.to_thread` 是当前实现事实，不属于本次 WU scope。

---

## 3. tests README（测试事实边界）

### 更新约束回读

tests README 首段要求："只记录当前 `tests/` 下已经存在的测试分层、运行方式与维护约定...测试事实以当前代码和测试目录为准"。

### 逐项验证

| 检查项 | 直接证据 | 判定 |
|---|---|---|
| 移除 `rebuild_processed` adapter 旧述 | 旧文 "SEC/CN/HK production persisted-summary adapter 消费 `rebuild_processed` 并标记既有 processed 需重处理" 已被替换为 "download typed request 的静态 canonicalization 与 local-only rebuild" | PASS |
| 新增 download owner coverage | 新段描述：静态校验、SC13 explicit start-window、non-delete、CN missing-period、UA prerequisite、overwrite 单目标、local-only rebuild、typed terminal summary、Docling subprocess lifecycle。全部与 production owner tests 对应 | PASS |
| 新增并发/完整性矩阵 | 新段描述：Event/barrier 驱动、同目标双 overwrite last-writer、不同目标 union、identity/revision churn、repair unconditional、MISSING/COMPLETE/REPAIR_REQUIRED 分类、corruption 矩阵、malformed SHA-256 strict failure、whole-tree repair-first、multiple/unselected corruption fail closed。全部与 `test_fins_storage_atomicity.py`/`test_sec_pipeline_download.py` 等 owner tests 对应 | PASS |
| 无未来计划或时间敏感记录 | 只描述当前已有测试事实，不包含 work unit 名称、时间敏感计数或未来测试计划 | PASS |

---

## 4. dayu/README.md（不修改合理性）

`git diff 5f5b1994 -- dayu/README.md` 输出为空，零 diff。

base plan §7.2 裁决："预计不改。`UI -> Service -> Host -> Engine`、Fins direct 边界和 runtime 层中立关系均不变化"。本次 WU 只影响 `download` 的最终用户行为、`dayu.fins` package contract 和测试事实，不改变分层架构、装配方式或 UI/Service/Host/Engine 边界。不修改合理。**PASS**。

---

## 5. Closeout artifact 验证

closeout artifact §3 声称的验证命令与结果：

| 命令 | 声称结果 | 判定 |
|---|---|---|
| 根 README 契约测试 | `1 passed` | 与 `test_root_readme_matches_current_cli_public_contract` 一致 |
| 旧述 grep 零命中 | `rg` 输出为空 | 与 `rg` 实际结果一致 |
| 必备事实 grep 命中 | 所有关键术语命中 | 与实际 README 内容一致 |
| `dayu/README.md` 零 diff | `git diff --exit-code` exit 0 | 已独立验证 |

---

## 6. 结论

**PASS**。三份 README 均按各自更新约束准确投影当前 production code 事实：

- 根 README 只写最终用户可操作事实，SEC_USER_AGENT 示例使用安全占位符，`--rebuild`/`--overwrite`/usage exit 2/Ctrl-C/final summary 均与 production owner contract 一致。
- Fins README 准确移除 `rebuild_processed` download 旧述与 `asyncio.to_thread` Docling 旧述，准确描述 typed request、process cancellation、writer reservation/integrity/repair-first owner。
- tests README 只描述现存测试事实，无未来计划或时间敏感记录。
- `dayu/README.md` 保持不改合理，无架构边界变化。

未发现准确性、完整性或边界违规 finding。
