# F5 用户裁决计划更新与本轮读取凭据

RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/gpt-6-sol
CANARY=gpt-6-sol-036658c1
label：`pr197-f5-user-decision-plan-sol-20261001-01`。
唯一 workspace：`/Users/leo/workspace/dayu-agent-r`；branch：`codex/upload-material-oracle`。

## 必要差异

- v2 以用户“先推断，失败保全 A、单列 B”替换旧 P1；旧文档不改。
- 新增最小 typed unknown 来源引用与独立计数，串通 discovery/storage/rebuild/adapter/runtime/direct/job/CLI/wait；不伪造 document_id，不改六字段 FinsPublicFailure。
- storage 同一稳定根组合 raw meta 与既有 inspector；F4 raw prefix API 不升级 trust，Q2 原读异常与 Q3 同集合一致保留。
- N01/N02 同 F5-S1；推荐有未知整体失败，已发布 A 保留 partial 摘要，取消也保留已经提交事实；此为 root 技术裁决候选。
- 一个完整可验证 slice，列出必填 fresh-schema、真实迁移点、4096 durable/10 行公开边界、owner 回归、逐生产文件 80% 与 README 职责。

## 本次 preflight 与读取范围

本次直接 cat 本轮 canary，不用旧报告凭据。起始 HEAD `26979bd109a94417e227f55cff3ff64b42bb5d8e`，main `fac32ecbff9bfe792b63ee9667c8697826b631f4`。
冻结文件 SHA256 `67e2dc4587edb1b5fc1bd26943f473e77fd95011d4ffc04114d3472cb5ea20b3`；首检逐件 45 current+45 originals 全匹配。
起始 status 的三 controller 修改及未跟踪 binding decision 保持原现场；只看 status，未读取可变 controller 内容。
末次 HEAD 为 root docs checkpoint `b3e4e0905fef9cc7eca7c66338e519b798ab9c91`，branch/main 不变；末检逐件 45 current+45 originals 全匹配，允许该 checkpoint 前移，不以它替换 input。

实际内容读取的冻结输入：AGENTS；F5 binding/goal/plan-adjudication/official-raw-evidence；calendar/selection/rebuild；CN models/protocol/workflow/source-upsert/pipeline；HK/CN discovery；download contract/direct events/ingestion runtime；storage source_meta_read/protocol/core/FS/inspector/infra/包导出；根/Fins/tests README、pyrightconfig；selection/rebuild 测试；official owner-validation JSON。
其余冻结文件只逐件 hash 核对，未声称全仓内容审查；旧 proposal/F4 plan/final-closeout/execution-cost 文档未作为本次设计真源。

实际新增必要读取身份（冻结清单外，仅源码/既有 tests 与个人规则；末检附 SHA）：

- `dayu/fins/pipelines/cn_download_rebuild.py`：HK 结果进入正常 rebuild envelope 的实际调用。
- `dayu/fins/pipelines/sec_pipeline.py`：shared summary 构造的真实迁移点；只读相关局部。
- `dayu/fins/domain/document_models.py`：provenance source owner；只读相关局部。
- `dayu/fins/direct_event_text.py`：公共中文说明 owner。
- `dayu/service/fins_wait_adapter.py`：observed direct 消费路径、失败/取消输出。
- `dayu/fins/ingestion/observation_handle.py`：轻量观察协议；检索相关定义，不推断 durable job 读取。
- `dayu/contracts/tool_outcome.py`、`dayu/contracts/tool_result.py`：现有取消/失败 message 可承载自解释下载结果，不新增工具 outcome 字段。
- `tests/fins/test_cn_download_runtime.py`、`tests/fins/test_cn_pipeline.py`：真实 discovery fake 签名迁移；只读相关局部。
- `tests/fins/test_fins_storage_atomicity.py`：检索既有同窗/deep JSON 回归，不冒称执行。
- `/Users/leo/.codex/memories/MEMORY.md`：轻量旧 handoff 查询；不采用其中旧 clone/停工推荐，本轮唯一主树及明确授权优先；旧结果不作现态证据。
- `git log -3`、HEAD checkpoint stat、目录/调用点 rg：只读定位，不读取另一 Agent 的新报告。

上述新增读取文件的逐件实际 SHA256 及末次 Git 身份见本轮独占证据 `workspace/tmp/pr197-f5-user-decision-plan-sol-20261001-01/final-input-verification.json` 的 `additional_reads_sha256`；该记录为本轮生成，非旧报告凭据。

## 所有检索失败与恢复

- 两次 zsh glob 无匹配：`dayu/fins/*observation*`、`dayu/fins/domain/*provenance*`；改用 `rg --files`/类型定义搜索，定位真实 ingestion/observation_handle 与 domain/document_models。
- `rg dayu/fins/observation.py` 报不存在；同上恢复。组合命令随后成功项导致 outer exit 0，不把该子命令错误算成功。
- `cat dayu/fins/pipelines/cn_download_integrity.py` 报不存在；实际 sealed wrapper 定义在 cn_download_workflow，已直接读原定义恢复；该复合 outer exit 0 同样不抹去失败。
- `sed dayu/fins/direct_messages.py` 报不存在，outer exit 1；`rg -l` 定位 direct_event_text 后读真实 owner。
- 新两 doc 未创建时路径 rg 无命中，随后 label/CANARY 在 freeze 无命中，复合 outer exit 1；均为预期未存在/未列字段的检索结果，不是输入校验失败。
- 无测试/类型/coverage执行失败；本轮不执行产品 pytest/pyright/cov 基线。仅对新增未知行会否挤爆现有 4096 字摘要这一具体风险运行 inline JSON 尺寸探针，不调用生产 resolver/runtime、不写永久临时 Python 脚本；结果记在本任务独占 tmp。

## 交付与残余

JSON 尺寸探针：`workspace/tmp/pr197-f5-user-decision-plan-sol-20261001-01/json-size-probe.json`；合成 240 字可转义 ID、六财期/32字 ticker，零 written IDs+首条未知=1715 字，原十 IDs=6552 字，缩短至四 IDs=3648 字，原引用保持、六省略有显式计数。不是生产测试或业务限值证明。

新文件仅本计划及本说明；无产品源码/tests/README/config 修改，无 runner/子 Agent、网络、commit/push/PR 写入。
README/tests/type/cov 本轮 N/A，不报告“0 files pass”。计划列出的测试及覆盖率是实施 gate 义务，不是本轮验证结果。
总体终态投影/必填 schema/上界方案交 root 技术裁决；信息边界归 calendar/selection，N01/N02 归 F5-S1，N03 归 Raw 回归。
本轮完成后停止，不自行实施或 gate pass。
