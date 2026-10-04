# UM-O12-F01：material 公司名称状态条件校验 goal confirmation

- Gate：goal confirmation pass。隔离工作区 `/private/tmp/dayu-upload-o12`，分支 `codex/upload-material-o12`，基线 HEAD `8d8d494fbbce0052372fb1b42097c9f7222cfa28`，开始时干净。
- 用户在 `docs/reviews/upload-material-um-o12-oracle-adjudication.md` 接受运行参数级的状态条件必填裁决，后续授权全部修复进入 PR #197。本项不把 `--company-name` 改为 argparse 无条件必填。

## 动机与直接代码证据

`dayu/fins/pipelines/upload_company_meta.py:resolve_upload_company_meta_decision` 已依据已发布公司 meta、解析动作和请求名称抛 `UploadCompanyNameRequiredError`；filing 的 `dayu/fins/ingestion_runtime.py` 已在状态感知准入将其映射 `COMPANY_NAME_REQUIRED`。material workflow 在 `upload.started` 后才发起公司 batch 并调用公司决策，普通异常投影可能成为 `unexpected_runtime`。冻结 A19 观察到缺名 fresh 请求的运行错误和锁文件副作用；该问题真实存在，严重性为字段错误分类及生命周期时序。别名冲突则由 storage 发布边界确保唯一性，不能因前置读取而替代最终并发安全校验。

## 目标与成功信号

1. material 请求在权威公司发布状态与实际动作可判定后，复用 `resolve_upload_company_meta_decision` 同一真源，fresh create/auto 及确实需刷新公司 meta 的请求缺名时，在 `upload.started`、公司/材料业务写入前给字段明确 typed usage；CLI 显示可执行的 `--company-name` 修正方向。已有公司且无需新名称的合法请求仍可省略。
2. 该前置拒绝不发布公司/材料业务事实；锁/辅助文件若存在要单独记录，不能当作业务成功。跨 US/CN/HK、direct/job/observation、Service、tool/CLI 消费同一状态判断和错误投影，不在每个入口自己重算“fresh”。
3. 已发布公司的 canonical ticker/alias 唯一性仍由 storage publication owner 最终检查；冲突时明确 `ticker_alias_conflict`、不污染原/新公司。owner/市场/入口测试及隔离真实 CLI 补跑 fresh 缺名、提供名、existing 省略名、异名 alias 冲突，记录双流/exit/文件/meta/manifest/SQLite/事件；受影响测试、pyright、逐生产文件 >=80% coverage、README 职责核对。

## 边界与停止条件

O05 的 form/name 无条件必填、O16 action/files、O14/O15 目标状态准入与本项可能同落 Fins material 请求 owner，集成时串行核对字段优先级；本项不实现它们。公司状态读取必须通过 `dayu.fins.storage` 协议，不用 CLI 文件探测或 adapter fallback。若要保证缺名早于 `upload.started` 必须重构公共状态读取/锁边界，plan 应给代码证据和最小设计；不能仅把 workflow catch 改文案冒充前置拒绝。下一 gate：Sol plan → Kimi/MiMo 双路 planreview。

用户另已接受 `docs/reviews/upload-material-um-o34-oracle-adjudication.md`：合法公司 identity/meta 在材料转换失败或取消时可以独立保留；材料 manifest 未登记则文档未成功。O12 的缺名前置拒绝仍要求零公司/材料业务写入，但**已合法准入并提交的公司事实**不因后续材料失败而回滚。本项不得以公司与材料单 batch 原子化改写该既定边界；材料发布冲突只约束材料自身的权威 commit。
