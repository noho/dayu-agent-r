# upload_material 第一轮校准：UM-O12 用户裁决

登记日期：2026-09-28。裁决来源：本轮会话中用户先确认缺失公司名称应在 CLI 运行参数检查中拒绝，随后明确回复“同你你建议的裁决。下一条。”本文件登记 UM-O12 的最终裁决与修复方向，不构成产品修复授权，也不表示 upload_material 全量 calibration 或 readiness 已闭环。

## 证据与追溯

冻结 evidence root：`/Users/leo/workspace/.dayu-cli-ci/upload-material-calibration-20260818-mNeTId`；真实 CLI validation commit：`fac32ecbff9bfe792b63ee9667c8697826b631f4`。原始运行不能证明当前 HEAD 行为。

| 场景 | 原始证据目录 | 已观察结果 |
| --- | --- | --- |
| UM-A19 | `evidence/actions/UM-A19-company-name-required-fresh` | 全新 workspace 中，`--ticker AAPL --action auto` 省略 `--company-name`：exit 1，先显示 `upload.started`，最终为 `failure_kind=runtime`、`failure_code=unexpected_runtime`，未发布公司或材料；新增 7 个 `.dayu` 目录及锁文件。 |
| UM-A20 | `evidence/actions/UM-A20-alias-baseline-msft` | 另一全新 workspace 中，`--ticker MSFT --company-name "Microsoft Corp."`：exit 0，成功发布 MSFT 公司 identity/meta 与材料；公司 meta 中 `ticker_aliases=[]`。 |
| UM-A21 | `evidence/actions/UM-A21-alias-conflict` | 沿用 A20 workspace，`--ticker AAPL,MSFT --company-name "Apple Inc."`：exit 1，`failure_code=ticker_alias_conflict`、`stored_files=0`；没有新建 AAPL 公司或材料，也未修改 MSFT 已发布文件；仅新增两个 AAPL 锁文件。 |

三次均以冻结 run 下 `inputs/probe.txt` 为真实 CLI 输入、cwd 为 run 下 `repo`、stdin 为 `DEVNULL`，各场景 command/result/screen/filesystem-before/after/diff/key-json-artifacts 可独立复核。无超时、无信号与残留进程；各 workspace 的 SQLite、Host EventLog、Trace、Memory、旧 ingestion job 均为 queried-but-absent。A20 与 A21 的 MSFT 公司 meta 摘要一致；A21 的 alias 冲突未污染既有公司。A19 的“无业务持久化”不等于文件系统零变化。

登记时核对的 SHA-256：

- `observed-behavior.md`：`4c73df2f41ed73b728231e64eb8daedb3561c7b49dd695c39a3fe983f60c5d64`
- `observed-behavior.json`：`23497494f9f5e4055f146fdcef93e6502d57a9bd6e27066f3ae518c6950cd8a0`
- `evidence-manifest.json`：`fccbb5464eb8e95450cfc7efa2fad1ad6fab60e976d356a967340c2a19b66abd`

## Accepted 行为

1. 已发布公司的 canonical ticker 与别名不能被另一公司占用。冲突请求应明确呈现 `ticker_alias_conflict` 所表达的业务原因和可执行的纠正方向，不发布新公司或材料，也不改变原公司事实。
2. A20 的成功公司 identity/meta 是 A21 所测冲突的实际前置状态。保留状态依赖与公司元数据的一致性要求；不把该次运行的固定文案、`failure_kind=storage` 或先发出 `upload.started` 的时序冻结为 contract。
3. A19 的通用 runtime 错误与延迟拒绝不予接受；该场景仅作为缺陷发现证据。

## 已裁决修复项

### UM-O12-F01：fresh 公司缺少名称的运行参数校验与错误投影

状态：用户接受修复方向，尚未实施。

动机：全新公司执行 create/update 需要公司名称；当前缺失名称最终由公司元数据决策识别，却在材料上传流程中被通用异常投影成 `unexpected_runtime`，使调用者无法从 CLI 输出识别应补的参数，且在拒绝前已开始上传生命周期并创建锁文件。

语义 owner：`dayu/fins/pipelines/upload_company_meta.py` 的 `resolve_upload_company_meta_decision` 根据已发布公司状态、解析后的动作和请求名称决定是否必须提供名称，并以 `UploadCompanyNameRequiredError` 表达该事实；公司身份别名唯一性由 `dayu/fins.storage` 的发布边界最终保证。Fins material 请求的状态感知前置校验应复用公司决策真源，并将缺名映射为明确的 typed usage 原因；CLI 负责把这一原因投影成指向 `--company-name` 的运行参数错误。filing 上传在 `dayu/fins/ingestion_runtime.py` 已有同源决策及 `COMPANY_NAME_REQUIRED` 映射，material 不能只在 CLI、单一市场流程或最终异常 mapper 中添加补丁。

修复要求：

- 在读取必要的已发布公司状态、确定本次动作后，对 fresh create/update 或确实需要刷新公司元数据的请求检查名称；允许不需要新名称的既有公司路径继续省略该参数。不得将 `--company-name` 设为无条件 argparse 必填。
- 在 `upload.started` 及上传业务持久化之前，以字段明确的 typed usage 错误拒绝缺名请求；CLI 把该错误呈现为运行参数错误。不固化未经补跑确认的具体 exit code 或文案。
- 对这类输入保证零公司和材料业务持久化副作用，并以真实 CLI 补跑核对文件系统是否也做到前置零变化；不得将 A19 当前的锁文件创建误记为已接受行为。
- 别名冲突仍以发布边界的唯一性校验为真源，保留明确冲突原因及不污染已发布公司的原子性；不能只靠前置读取替代并发安全的最终检查。

## 待补跑与 scenario 处置

- A20/A21 可作为已发布公司基线与别名冲突行为的 accepted scenario 证据基础，但正式登记应排除当前固定文案、`failure_kind=storage` 和延迟失败时序。
- A19 仅保留为错误分类与校验时机的发现证据，不转为长期 accepted scenario。
- 修复获单独执行授权并完成后，真实 CLI 在独立 CI workspace 补跑：fresh create/auto 缺名 typed 拒绝且公司/材料零业务副作用；提供名称可上传；既有公司省略名称在适用动作下正常；冲突 alias 明确拒绝且原公司与新公司均无错误 publication。跨市场及非 CLI material 入口须按共用 Fins contract 验证，静态测试不能替代 CLI 证据。

## 裁决替代关系

本裁决替代冻结 observed report 中 UM-O12 的 pending 建议，并吸收用户对“CLI 运行参数检查”的细化：CLI 应在运行中呈现参数错误，条件必填判定仍由状态感知的 Fins 公司元数据决策真源负责。该修复与 UM-O05-F01 的前置校验原则关联，但公司名称为状态条件必填，form/name 为无条件业务必填，不合并修复项。原始 evidence 不作改写。

本次仅登记 UM-O12，不改写已闭环命令的 accepted oracle，不新增正式 accepted scenarios，也不将 upload_material 加入 readiness scope。产品修复尚未执行。
