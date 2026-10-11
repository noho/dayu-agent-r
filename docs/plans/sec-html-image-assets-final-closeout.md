# SEC HTML 图片修复 final closeout — PASS

Work unit sec-html-image-assets；branch fix/sec-html-image-assets；base297bfbbc67b7d7468e3dfb6669a3385c4dd10d18。
Draft PR https://github.com/noho/dayu-agent-r/pull/200，保持 draft。accepted plan771299b8244e5cb25ce8f943ab41671d8e59e16c；accepted S1 da0ebd0d06196f3cff6d44b68af661e2d6679ceb；accepted deepreview db0d0e68557a42ca2b6f33500cd9ffe87033c1e7；PR N1 fix checkpoint 0b931bebc72be3a250a518db2a48b8c530805c3a；accepted PR review checkpoint daf6c00b61af937068d7143e9c94abb95223af9f 已推送，远端 head、draft OPEN 和源码一致性已核实。

## 行为与五项成功信号

1. 已选 SEC HTML 的本轮实际字节发现 img/src、img/srcset、picture/source/srcset；同申报候选通过现有 transport 下载，与 HTML 一起发布为来源仓储可寻址资产。首 base/首重复属性、archive/accession/文件名合法百分号路径的同源单次解码与碰撞使用明确有限边界；不硬编码 TSM、accession、29行或15份。
2. 下载契约 sec_pipeline_download_v1.3.0；普通 download 自动补齐旧来源。既有内容版本、完整集合指纹和 processed 重处理规则复用；rebuild 不产生下载认证；未知指纹无快跳资格、无错误升位。
3. 必要图片发现/GET 失败准确诊断及 exit1，原 publication/processed 原子保留，retry/repeat 验证；不以 logo/表格猜测丢弃引用。
4. 最终4169collect/4160pass/9skip，852受影响测试、全仓pyright0，七生产owner无排除coverage最低82.71%。两个真实 TSM 临时base，24CLI（20成功、4预期失败），27目标/28完整申报图片、112readbacks、metadata/URI/size/SHA/集合FP/版本/增量/repeat/故障/retry；原base只读、baseline正式下载播种，无手补。
5. accepted plan/S1/aggregate deepreview/PR review checkpoints 齐全；mimo 与 ds-flash 对同一冻结修复和验证独立 re-review PASS，总控已裁决并回写，accepted PR review 已推送，draft-PR-pass PASS。此 closeout 记录满足最终关口，无阻塞问题、未修复 accepted finding 或未分类 residual risk。

## 证据与 docs

权威 docs/validation/sec-html-image-assets-pr-percent-path-fix.json SHA c87e6655774a7e964773870ee7644ad4c3525b79b7b1d9290e4d437ccef5b6c8，11源码/test哈希、207库存、12final commands、24CLI七producer同源核对。前五validationJSON和失败尝试原样保留，superseded不作为final。
README、dayu/fins/README、tests/README按职责更新；无分层、LLM-facing prompt/schema变化。源资产可读不等于OCR或财务数值提取已完成，不把全部图片称财务表。

## Live 使用与补齐

实际入口 /Users/leo/workspace/dayu-agent-r/.venv/bin/dayu-cli；dayu-agent0.1.4 editable指向本repo，新进程读取v1.3.0修复，11hash同源。是本机分支可用性，未merge、未安装新发布版本、未部署服务。

以下供用户执行；本任务未在原业务base执行：

```zsh
repair_log=$(mktemp /private/tmp/dayu-tsm-images.XXXXXX)
/Users/leo/workspace/dayu-agent-r/.venv/bin/dayu-cli \
  --base /Users/leo/workspace/portfolio-manager-v2/workspace \
  --log-file "$repair_log" download --ticker TSM \
  --start 2018-01-01 --end 2026-10-11
```

使用正常shell已有SEC_USER_AGENT配置；不要输出其值。无需新flag/--rebuild/--overwrite；当前known完整快跳，强制远端重检才用既有--overwrite。本任务未证明全部79份业务来源已补齐。

## Residual owner / destination

R3当前known缓存不重检远端→SEC transport/workflow独立重校验需求；R4平铺地址/编码/其它形态→SEC downloader/storage有样本独立契约需求；R5外站/跨申报/OCR/数值→独立需求提出方；R6 HTTP200非图片与HEAD/GET validator一致性→SEC transport独立响应校验；R7真实processor/LLM/OCR→Fins分析维护者独立验收；C2Unicode展示未采纳→storage/展示；DS-OQ2/RR10公共typed transport→downloader/workflow；DS-RR9真实新形态→downloader/tests。全部assigned to later work unit，无新增approved slice，不改变目标。

## 授权与 next entry

无外部issue号，本次是独立bug fix，issue linkage/comment不适用且未创建/对外评论。TCOM rejected接口任务用户撤回，独立branch/worktree/证据保留，无子Agent派发或代码修复，不混入PR200。merge/部署/ready/approve/reviewer另行确认。

Final closeout gate：PASS；work unit：completed。关口依据为下列完整 artifact、finding 裁决、最终验证和已完成的 draft-PR-pass。此 summary/control 的后续 checkpoint 只记录治理文档，不改变被两路审核的源码。用户另行授权 merge 后可进入主线采纳；部署及原业务 workspace 的补齐操作分别按授权执行。


## 审核、finding 最终状态与 checkpoint 范围

- [目标契约](sec-html-image-assets-goal.md)、[实施计划](sec-html-image-assets-plan.md)和[控制历史](sec-html-image-assets-control.md)记录全部 gate 及路由变更。
- 最终 PR re-review：[mimo](../reviews/pr-200-review-20261012-021002.md)、[ds-flash](../reviews/pr-200-review-20261012-021003.md)均实际退出 0，报告 PASS；[总控最终裁决](../reviews/pr-200-review-20261012-023603.md)核对 needs_review 恢复证据并裁决通过。没有在途 runner。
- 全部 accepted 计划项、C1/C3/C4/C5/C6/C7、AGG001/002、PR200-N1 已修复且经独立复审；C2、OBS1 rejected-with-reason。历史 DS 两次原生空失败、缺失报告及唯一 retry 计数原样保留，不能记为通过；获授权的历史 sol 替补结果另行保留。用户禁用 REA 后，新 reviewer 已恢复 mimo + ds-flash，未特意终止在途 runner。
- 双路精确审核代码头 0b931bebc72be3a250a518db2a48b8c530805c3a；accepted PR review daf6c00b61af937068d7143e9c94abb95223af9f 仅增改六份治理文档。11 项源码/测试 SHA 与冻结验证逐项相同，不将后续治理头说成重新完整审核的代码头。
- [最新修复与验证说明](sec-html-image-assets-pr-percent-path-fix.md)、[最终权威验证 JSON](../validation/sec-html-image-assets-pr-percent-path-fix.json)保存可执行命令、准确 argv、日志哈希、coverage、真实 CLI 与仓储断言。真实 CLI 运行时 HEAD 是 db0d0e68 加未提交 N1；其 11 项源码/测试哈希随后纳入 0b931beb，代码身份一致，不能称运行时 git ref 已是 0b931beb。
- 真实样例：2019 accession 0001193125-19-110066 的 d733154d6k.htm，17 处引用对应 15 张唯一图片；2025 accession 0001046179-25-000082 的演示 HTML 引用 12 张图片，完整申报另含 image_1a.jpg，共 13 张。两例目标图片 27、完整申报图片 28。验证不代表全部缺图 HTML 都是财务表。
- GitHub 未提供本 PR 的 checks/status 结果，不宣称远端 CI 已通过；本地测试与类型检查结果按权威证据报告。源码无新增变更，因此收尾文档 checkpoint 不重复运行代码或真实网络测试。

Artifact：docs/plans/sec-html-image-assets-final-closeout.md；final closeout decision date：2026-10-12（Asia/Shanghai）。
