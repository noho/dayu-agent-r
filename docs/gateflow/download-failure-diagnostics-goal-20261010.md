# 下载失败诊断：目标确认

- Work unit：download-failure-diagnostics-20261010
- Gate：goal confirmation pass（巡检线依据用户委托明确确认，2026-10-10）
- Current gate / next entry point：plan
- Branch：fix/download-failure-diagnostics-20261010
- Base / HEAD：c65c2aa28fae9c47ad947783d63f7559db7768c4（main）
- Preflight：原分支 main，git status --short 为空；用户已明确授权创建新修复分支，已创建。未修改生产代码，未派发子 Agent。

## 动机与直接证据

问题成立：调用成功结束不等于所有候选获取成功；调用方需要失败身份及原因才能判断来源影响。

输入均来自 `/Users/leo/workspace/portfolio-manager-v2/orch/jobs/20261010-0700-01/`：已读取 failure-assessment、maintainer-handoff、download JSON、terminal-check JSON 及原 stdout/stderr。stdout SHA256 实测为 `a9c8a3cc2babdd8c93313345e55f1638c27fea15b6b56c5d7f8d37b1ebd07f3a`，与 terminal-check 一致；stderr 实测 0 字节。原命令已结束、退出 0 的依据是原托管终态记录，不以本次文件检查冒充原进程观察。

stdout 记录 discovered=53、downloaded=34、skipped=11、failed=8、omitted=43；8 项均有 PDF `download.file_failed` 进度，未公开原因，终态仅前 10 个跳过项。不能据此推断网络、404、转换失败或窗外影响。

直接代码链：

1. `dayu/fins/pipelines/cn_download_filing_workflow.py:259` 将真实异常经 `project_cn_filing_failure` 产生 reason_code/reason_message，并生成单候选失败结果。
2. `dayu/fins/pipelines/cn_pipeline.py:1580` 投影失败结果时保留分类，但把原因说明改成通用文案。
3. `dayu/fins/ingestion_runtime.py:6854` 对完整 typed document_rows 原序截前 10 项；`dayu/fins/download_contract.py:42` 定义该上限。
4. `dayu/fins/ingestion_runtime.py:6535` 的公开 progress 仅投影阶段和进度单位，没有失败结果详情。
5. `dayu/cli/main.py:109,130,189` 未显式指定 log-file 时打开 TemporaryFile，退出 finally 关闭。默认日志不是可追回证据。
6. 已检查 source repository 与 batching 的公开接口：前者管理 published sources，后者管理 source publication transaction；未发现本次 direct run 的完整失败结果读取契约。旧运行 8 项 published meta 缺失仍是下游 owner 检查记录，本总控尚未另行复查，不把交接主张写成独立验证。

## 已确认的 binding scope

目标：限定于 Dayu 下载职责。给定 ticker 0700、2018-01-01 至 2026-10-10 的请求，下载结果应准确，成功/跳过/失败如实可核验。本次已证实缺陷是完整失败诊断无法取得；在最小 Dayu owner 边界修复，使调用方获得完整失败候选的可核验身份、来源明确提供的表单/日期/期间信息和真实安全失败原因。调查旧 8 项可恢复证据，并对不可恢复内容明确写未知；交付修复版本在固定 CLI 入口的可用性、必要操作及剩余问题。

范围释义（plan review 总控裁决）：本轮原因保真修复针对 0700 所走的 CN/HK 共用 owner 链。完整结果取得接口可机械服务各来源，但不据此承诺本轮也修复 SEC workflow/adapter 的原因治理。此释义来自巡检线确认中“给定 ticker 0700”“按最小范围修复”“实际下载缺陷报出再确认”，不是新目标或新的全来源修复授权。

成功信号：

- 后续同类运行即使失败出现在前 10 项之后，或失败超过 10 项，也有明确可取得的完整失败诊断，不靠猜日志或内部文件树；现有有界 LLM-facing 投影不承担无界数据输出。
- 诊断与来源 workflow 的候选身份、日期/覆盖语义、失败分类及安全说明同源；来源未提供的信息显式未知，不由 adapter/UI 重算或伪造。
- 原 8 项分别说明可恢复与不可恢复内容及证据身份；需要新观测时先说明具体范围和影响，由巡检线确认后执行，不把新观测冒充原运行证据。若发现实际下载缺陷，先报出原因及最小修法，由巡检线确认范围。
- 不覆盖或整批重启原下载；保留 45 份来源。isolated fixture 验证通过，受影响测试及 pyright 通过。
- gpt-6-sol 经 runner 负责 plan / implementation / fix；mimo、ds-flash 每轮独立并行 review，经 planreview/deepreview 产出 artifacts；总控逐字核验 canary、真实外层退出码、结构化终态、工具证据并裁决。
- 新 draft PR 完成 PR review、修复/复审、最终 push 与 final closeout；说明固定 CLI 当前实际加载版本及可用状态、继续命令和剩余阻断。

非目标与边界：不修复未经证实的网络/404/provider 原因；不扩成通用 job/resume 框架；不作财务覆盖判断；不读取或处理调用方 workflow、gate、审核包或范式，不把这些背景纳入开发及验收；不修改调用方 workspace、Raw 或其它业务产物；不绕过 Dayu 直下 PDF；不自行 merge/approve/mark ready/request reviewers/comment。源码、测试、职责内 README、开发 artifacts 是本轮可修改范围。生产来源不在修改范围，调用方业务恢复由巡检线负责。

## 语义 owner 与最小设计约束

来源候选和失败原因由 discovery/downloader/workflow 产生；Fins typed result 和 public projection 是对外结果 owner；CLI 机械消费与指定输出。plan 必须在该链上选择最小完整诊断接口，不能在下游消费者补偿。接口形式及文件范围由 gpt-6-sol 在已确认目标内具体化，双路 planreview 检查，不预先承诺额外 schema、持久 job 或框架。

## 验证、文档与风险

本 gate 验证：preflight、原 stdout hash/计数与内容、stderr 字节数、上述直接代码路径。尚无代码变更，测试和 pyright 不在本 gate 执行。

Docs decision：goal artifact 已创建；实现时检查根 README、dayu/fins/README、tests/README 及其它实际触发 README 的约束后决定更新。

Residual risks：

- 旧原始失败异常及候选元数据可能已不可恢复：assigned to current work unit 的 evidence assessment；最终仍未知时如实列限制，不伪造恢复。
- 失败候选业务影响：assigned to later work unit，owner 为调用方巡检线；不纳入 Dayu 开发和验收。
- 新观测、生产获取、部署/合并：requiring explicit user decision / 巡检线裁决，不以修复授权推导新观测、生产下载或 merge 授权。

Blocking open question：无。巡检线已明确确认，并要求以上职责收窄；无需再次确认同一目标。

Completion status：goal confirmation pass；下一未完成 gate 为 plan。
