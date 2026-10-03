# UM-O33-E01：同一 `auto` identity 并发失败的当前 HEAD 底层异常补证

日期：2026-09-29。证据基线为主工作区 HEAD `8d8d494fbbce0052372fb1b42097c9f7222cfa28`，Python 3.11.15 的 `.venv/bin/dayu-cli`；本次没有修改产品代码。冻结 UM-L06A/B 仍保留原样，本文件是新隔离试验，不替代冻结记录，也不宣称修复完成。

## 输入、隔离与运行

两次有效试验分别使用独立 evidence root `/private/tmp/dayu-o33-current.Wlove7` 与 `/private/tmp/dayu-o33-diag2.utHNE1`；以下路径均相对各自 root。每组 fresh `workspace/`，同一 `inputs/probe.txt`（内容 `Concurrent evidence text.\n`），两个线程 Barrier 后并发启动两个独立 CLI 进程；参数同为 `upload_material --base <该组 root>/workspace --ticker AAPL --action auto --forms MATERIAL_OTHER --material-name 'Concurrent Same' --files <该组 root>/inputs/probe.txt --company-name 'Apple Inc.' --log-level debug`，仅 `--log-file` 分别指向 `A.log`/`B.log`。stdin=`DEVNULL`；stdout/stderr/log 各自隔离。PID、纳秒启动/结束时刻与退出码保存在 `results.json`。

第一组是真实 `.venv/bin/dayu-cli`，A/B 启动时刻相差 27 微秒：A exit1、B exit0；失败方 `A.stderr` 为 `failure_kind=storage`、`failure_code=storage_io`、`stored_files=0`，成功方 `B.stdout` 为 `stored_files=1`。debug `A.log` 只记录已收口的公共失败，没有底层异常或 traceback，因此仅凭常规 log 不能定根因。

第二组用 `.venv/bin/python workspace/tmp/o33_exception_probe.py` 作为临时诊断入口（脚本只在 `sec_upload_workflow.fins_upload_failure_from_exception` 的捕获边界记录原始异常并调用原函数，不修改业务分支/参数；可执行脚本有 `__main__` 守卫以避免 Docling 子进程重新进入 CLI）。A/B 启动时刻相差 25 微秒：A exit0、B exit1；`B.stderr` 同样为 `storage_io`。临时钩子的 `B.diagnostic` 给出原始 traceback：`sec_upload_workflow.py:562` → `commit_prepared_upload_batch` → `publish_prepared_upload` → `_store_upload_assets` → `_create_source_document` → `fs_source_document_repository.py:352` → `_fs_source_document_core.py:162/1749`，最终 `FileExistsError: 文档已存在`。前置的 `sec_pipeline.py:224 RuntimeError: no running event loop` 是 sync-to-async 正常分支的异常上下文，不是最终失败原因。

本 HEAD 代码直接对应：`sec_upload_workflow.py:486-497` 在 `UPLOAD_STARTED` 前读取 `previous_meta` 并用 `resolve_upload_action(action, previous_meta)` 定 `create/update`，随后 `:520-566` 先提交公司 batch、转换，再提交材料 batch；`_fs_source_document_core.py:1746-1749` 对 `is_create and meta_path.exists()` 抛 `FileExistsError`。因此在当前复现中，失败方的 `auto` 对 fresh 旧快照解析为 `create`，成功方先发布同一 document，失败方到仓储 create 时才被目标已存在拒绝；workflow 的泛异常投影把它收成 `storage_io`。这是直接 traceback 与代码同源的根因判断，不把冻结 L06 的具体抛错点追认为已知。

第二组最终 `workspace/portfolio/AAPL/materials/material_manifest.json` 有恰一条 document；对应目录的 `meta.json` 是同一 `document_id=mat_8cb632e4d3f818fbf9dcd03d28e91822661f6c2e`、`is_deleted=false`、`document_version=v1`，含 `probe.txt` 与 `probe_docling.json`。最终单份完整发布与冻结观察一致，但失败方终态仍不满足用户已接受的并发幂等 skip。

## 原始证据与限制

第二组关键 SHA-256：`results.json` `47aed51fa04e71ce8487f606168d51cb67cea0241e72407a3ff8fd525d2a9b6c`；`B.diagnostic` `4854e560d992859d4ac1aa729512accdb9a5cc733deb5142e13557b7555971f3`；`B.stderr` `22819b606f1b0a28234b02e017de7769069b89bc9341ba38bd13fb4c`；`A.stdout` `5b636d24fffe301a306bc5e2bf6f9eb059be222d51fa57ac36c1b78195b1a2c5`。第一组的 `results.json`、A/B stdout/stderr/log 也留在对应 root。诊断脚本只供本次取证，不属于产品或正式测试；该钩子可影响调度，故两组分别记录，根因只认第二组真实异常链，非确定性并发成功率不从两轮推断。

有一次无效诊断试跑 `/private/tmp/dayu-o33-diag.8m8UWs`：临时脚本初版缺 `__main__` 守卫，Docling 子进程重入 CLI，两路均 `docling_child_crash`；此结果与 O33 业务并发无关，不作为缺陷证据。随后修正诊断入口并用全新 root 执行上述第二组。两个父 CLI 进程均由 `Popen.wait()` 收集终态；本轮未另作完整后代进程树审计，故不以此补证声称无所有后代残留。

## 修复依赖与下一 gate

O33 的用户目标仍是：同 identity/同指纹竞争，一方创建、另一方在**权威已发布 state 与完整性确认**后 skipped；不同指纹/状态不可证明相同则 typed 冲突，真实 I/O 保持 I/O。此补证说明本 HEAD 的失败在 stale `auto` 动作与仓储 create 边界，不是“缺少锁”的充分证据。实施须待 O12 同版 admission/单 batch guard、O14/O15 动作状态、O04/O23/O25 身份/指纹及 O13 skip 语义集成后，重新确认最终 owner 接缝；不能在 CLI 将 `storage_io` 字符串改写为 skipped，也不能对所有 `FileExistsError` 无条件重试。下一 Gateflow goal/plan 应据当前真实异常和集成后的状态机设计封闭冲突后的同指纹权威裁决，并用可控 barrier owner 测试与真实双进程 CLI 复跑。
