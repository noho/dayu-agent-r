# UM-O07/O08 首轮 plan review 总控裁决

- Workspace：`/private/tmp/dayu-upload-ids`；MiMo review：`docs/reviews/plan-review-20260929-030538.md`，进程退出 0、结构化 `subtype=success/is_error=false`、canary `mimo-aab1f33a` 匹配，stderr 只有白名单模型提示。Kimi 同轮 403，没有有效第二路。Sol 原 plan 运行中两条测试环境命令失败，agent_status=failed，计划只作候选；MiMo 独立确认是该隔离 worktree 无锁定 venv 与依赖，不可把失败测试说成通过。
- 动机成立：公开内部 ID 仍可透传，显式不匹配在 started 后才发现。身份 owner 是 `docling_upload_service.py` 的 material ID 构建/校验；runtime 是直接上游 admission，CLI/tool/Service 是公开入口。不能在下游从文案猜原因。

| Finding | 裁决 | 计划修订与验收 |
| --- | --- | --- |
| F1 seed 门控与 EMPTY 丢失 | **accepted；拒绝长期过渡门控** | O05 必填字段前置 typed 校验是 O07 实施前置依赖；在此之后 material admission 有完整 form/name seed，O07 无条件校验显式空 `document_id`，再校验 mismatch。O07 单独的旧基线下不得实现 `form_type is not None` 临时门控并宣称闭环。计划增加缺 form/name + 空 document_id 的集成测试，错误优先级由 O05 typed 必填 owner 决定且均早于 started；完整 seed + 空 ID 必为 O08 typed EMPTY。 |
| F2 CLI flag 文案泄入工具/Service | **accepted** | runtime closed usage message 使用通道中立 `document_id` 字段名，不用 `--document-id`；CLI 的已存在 O08 argv 空串文案由 CLI owner 保留。tool outcome 与 Service 文案测试断言无 CLI flag，CLI mismatch 仍可行动。 |
| F3 真实 CLI 配方不具体 | **accepted** | plan 固定隔离 workspace、fixture、exact argv 模板、exit/stdout/stderr/event/source/meta/manifest 证据路径与每场景预期。方案应复用当前可运行 fixture，不凭空假设文件格式；依赖锁定 Python 3.11 venv。 |
| F4 跨 WU seed 变动/旧身份 | **accepted，分两个 owner** | 总控 repair-sequence 登记 O05/O17/O09/O10 合入后重算 O07 owner/真实 CLI 证据，集成关卡负责执行；已发布旧 material seed 改变可能产生双身份，单独登记 `fins-material-legacy-identity-seed-disposition`，在依赖 WU goal 阶段裁决新起算/迁移，未裁决前不把已有 workspace 兼容性说成完成。O07 plan 提示该残余，不实现迁移。 |

下一 gate：Sol 仅修 O07 plan；双路有效 re-review 前不实施。O05 与 O17/O09/O10 的依赖检查须在实施入口重新核对，不能用本次候选隔离基线模拟已合入状态。

## MiMo 第二次独立 plan re-review

`docs/reviews/plan-review-20260929-033249.md`：exit 0、结构化 success、canary `mimo-c9cd3d67` 匹配、stderr 仅白名单模型提示。结论 `pass-with-risks`，四项已接受修订均无新增 material finding：O05 硬前置取消临时门控，EMPTY/MISMATCH 先于 started；runtime 文案通道中立；10 case exact CLI 配方和 fixture/证据模板；跨 WU seed 重算与 legacy 旧身份 owner 分列。总控核对 review 的代码位置与本计划对应段，采纳为**本路通过**，不把依赖尚未实施或 fixture 尚未实测误作 plan finding 通过后的产品证明。

实施检查点：完整 seed 下 EMPTY 优先于 MISMATCH，缺 seed 的字段优先级由已集成 O05 owner 给出；旧公开 `internal_document_id` 输入必须全部退场，持久/输出及 filing 身份不删。Kimi 当前 403 无有效第二路；本 work unit 仍停在 plan re-review，不能提交 accepted plan 或实施。
