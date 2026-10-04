RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/gpt-6-sol
CANARY=gpt-6-sol-2b86f7f3

# #198 S1 code review F2/F3 修复记录

## 范围与 diff 锁

- 工作区：`/Users/leo/workspace/dayu-agent-r`；HEAD：`47a9cb64e63780deb568a9e2c6fdd0120441cf2f`。
- 原 14 文件 S1 候选的 `git diff --binary -- <14 文件> | shasum -a 256`：`86aa9a2bdecdd4f9f817c555cf2eb94da668f9329a264428e192bf91f07b8cb5`。
- 本次完成后同一 14 文件顺序与命令的 SHA-256：`f1e1a91557cda273c5d0b77900920381727322a8edea69d6061cda27f0f6bd21`。14 文件依次为 `README.md`、`dayu/cli/output.py`、`dayu/fins/README.md`、`dayu/fins/direct_events.py`、`dayu/fins/ingestion_runtime.py`、`dayu/fins/pipelines/cn_download_workflow.py`、`dayu/fins/pipelines/cn_pipeline.py`、`dayu/service/fins_wait_adapter.py`、`tests/README.md`、`tests/cli/test_output.py`、`tests/fins/test_cn_download_runtime.py`、`tests/fins/test_cn_download_workflow.py`、`tests/fins/test_fins_ingestion_runtime.py`、`tests/service/test_fins_wait_adapter.py`。
- 本轮实际改动仅 `dayu/fins/pipelines/cn_pipeline.py` 与 `tests/fins/test_cn_download_runtime.py`，以及本记录。原有其它 dirty diff 未覆盖、未格式化；未提交、未 push、未操作 PR。

## 根因与 owner

- F2 动机成立：accepted plan 第 57 行要求修复 mutation 后用同请求重跑，而旧真实 post-repair 用例只到中止帧。缺的是恢复路径的 owner 回归，并无证据表明产品失败映射本身出错。下载文档的 durable 完整性由 `dayu.fins.storage` 负责，候选执行与中止快照由 CN workflow 负责，adapter/runtime 投影该快照；测试必须从这条真实链观察结果。
- F3 动机成立但风险较低：workflow 在 `_integrity_abort` 生成 `integrity_failed`，pipeline 在 `_summary_from_integrity_abort` 再用独立字面量验证同一私有状态。状态真源是产生快照的 `cn_download_workflow.py`。`cn_pipeline.py` 原已直接导入该 workflow 的 abort 类型与执行函数，因此改为同向导入其私有状态常量，删除 pipeline 的重复常量；没有跨层反向依赖、兼容 shim 或公开合同变化。

## F2 真实恢复回归

本次将原 post-repair runtime 用例替换为 direct/job 参数化的同仓同请求恢复用例；原有中止侧关键断言与新增重跑侧断言的并集保留。

在 `tests/fins/test_cn_download_runtime.py::test_cn_post_repair_abort_then_same_request_skips_complete_source_and_downloads_next` 中，direct/job 两入口各用隔离真实 FS 仓库与实际 adapter/runtime 链：

1. 先发布 2025 年候选；随后 discovery 给同一请求增加尚未发布的 2024 年候选，损坏首候选 PDF 以触发真实 repair。
2. 在 repair 后的第二次真实完整性枚举前向 `filings/` 注入非点号外来文件。原 storage 枚举与 classifier 抛 typed preflight；中止帧只记录已修复的首候选，`discovered=downloaded=1`、`failed=0`，第二候选的 storage 身份目录不存在，传输仅调用首候选。整体 direct RESULT / job record 仍失败，且公司旧字节保留。
3. 删除外来文件，以**同一个 request 对象**、同仓库再次执行。direct 的真实文档行依次为首候选 `skipped`、第二候选 `downloaded`；job 的 `written_document_ids` 只有第二候选。两者 `discovered=2, downloaded=1, skipped=1, rejected=failed=0`；传输只调用第二候选。首候选 PDF 字节保持原值，两份来源 meta 可由仓储读回，真实完整性枚举均为 `COMPLETE`。先前未处理的第二候选只在本次重跑计入摘要。

测试保留确定性 fake discovery/transport，文件系统仓储、workflow、adapter、direct/job 收口均为生产实现；没有手造公共 RESULT 或从进度事件回填摘要。

## 验证与 README

- `.venv` 中 focused 测试：`3 passed, 37 deselected`。
- `.venv` 中受影响八文件测试：`846 passed, 3 warnings`；三条均为 edgartools 弃用警告。
- 第一次 pyright 指出新增测试中的 `collect` 可能未绑定；把局部收集函数移到分支前后，重跑 `python -m pyright dayu/ tests/ utils/` 为 `0 errors, 0 warnings, 0 informations`，八文件测试再次 `846 passed`。
- `git diff --check` 对本轮相关代码与测试文件返回 0。
- 已核对 `dayu/fins/README.md` 与 `tests/README.md` 的更新约束：本次没有改变 Fins 公共契约、测试层级或运行方式，现有 CN typed 中止与 direct/job 覆盖说明仍成立；无必要 README 修改。根 README 的用户入口、命令、输出和工作流未变。

## 风险与后续 gate

- 回归的 provider discovery/transport 是确定性 fake，真实 FS owner 和运行链受测；它不证明外部 CNInfo 单日发现问题，后者仍属独立 work unit。
- job 摘要公开 counts 与 downloaded IDs，没有逐项 skipped row；job 的 skip 由 `skipped_count=1`、首候选未调用传输、两份真实来源 `COMPLETE` 联合证明。direct 另核对逐项 row。
- 新 14 文件 SHA 尚需按总控要求进行同版双路 code re-review。本记录不宣布 S1 gate 已通过。
