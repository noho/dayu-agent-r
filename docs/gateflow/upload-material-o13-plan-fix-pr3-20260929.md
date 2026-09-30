# UM-O13-F01 MiMo 第三轮计划修订记录

RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/gpt-6-sol
CANARY=gpt-6-sol-74ec2d44

## 范围与预检

- 绝对工作区：`/private/tmp/dayu-upload-o13`；分支 `codex/upload-material-o13`；HEAD `8d8d494fbbce0052372fb1b42097c9f7222cfa28`。
- 计划输入 SHA-256：`5b02d9e62362a2dd88006a25dffab76803983bfcb2cb488aa5bea34add7c5d58`，与任务锁定值一致。`AGENTS.md` 为 `cb26618ab566804c97a3ef2f269537b7313e59370e5ddd0258d9b753b08ac45e`；goal 为 `32b754b501b5fb4610852a92005650fd813562634fc496cb767041955bc9bf30`。
- 已读 `AGENTS.md`、goal、MiMo 第三轮 review、总控裁决及仓储/协议/服务/溯源代码。原 F1–F5、PR2-F1/F2 计划内容继续保留；本轮仅补总控接受的 O13-PR3-F1/F2。
- 本轮只写 `docs/gateflow/upload-material-o13-tombstone-plan-20260929.md` 和本记录；既有未跟踪 goal、旧 review、裁决和 PR2 修订记录均未改。没有修改产品、测试或 README，没有安装依赖、提交、推送、建 PR、合并或派发 Agent。

## 直接证据与修订

1. `dayu/fins/pipelines/docling_upload_service.py` 的 `prepare_upload` 对 delete 直接生成 `_PreparedDeleteMutation`，不读 `is_deleted`；`publish_prepared_upload` 随后调用 `_delete_source_document`，后者直接调用仓储 `delete_source_document`。现有 `publish_prepared_upload` Raises 缺 `KeyError` 和 delete 路径既有的 `FileNotFoundError`，`_delete_source_document` Raises 缺 `KeyError`/`ValueError`。据此将服务文件列入实施白名单，严格限于这两个方法的 Raises docstring；明确服务的 delete 发布路径异常与既有 `FileNotFoundError`，不要求修改服务行为。
2. `dayu/fins/storage/source_meta_contract.py:require_source_meta_is_deleted` 对缺失 `is_deleted` 抛 `KeyError`，对非布尔值抛 `ValueError`。`_fs_source_document_core.py:_prepare_complete_source_meta` 调用 `SourceDocumentProvenance.from_meta`；其对缺少 `ingest_method`/`source_provider` 等必需 provenance 字段可抛 `KeyError`，对非法值可抛 `ValueError`。真实转换路径的异常可经仓储、协议及上述服务调用链冒出，未见该链上的异常翻译。将仓储、协议、服务 Raises 计划措辞统一为 `KeyError` 覆盖 source meta 缺少必需字段（含 `is_deleted` 与 provenance），`ValueError` 覆盖非布尔/其它非法值；保留既有 `FileNotFoundError`/`OSError` 说明。
3. 实施白名单计数改为三个限定 Raises docstring 的契约文件，覆盖率说明同步改为第 5–7 项。其它状态机、owner 测试、单文件覆盖率、CLI/README 验证及 O14/O15/O18/O33 边界未变。

计划输出 SHA-256：`bb4542115c8823ba2f754768bd15dfbf8ac081d19eba32aeeaaa663ed5af03c8`。

## 命令与退出码

以下为本轮预检和修订验证实际执行的 shell 调用；并列命令的 `exit` 是该次 shell 调用的退出码，未把它冒充每个子命令的独立退出码。`apply_patch` 三次修订计划和一次新增本记录均返回成功，但不是 shell 命令。

| 命令或调用 | exit | 结果 |
| --- | ---: | --- |
| `rg -n "upload_material|O13|O11|O12" /Users/leo/.codex/memories/MEMORY.md` | 0 | 快速定位既有背景；事实仍以本 checkout 直接证据为准。 |
| `pwd && git status --short && shasum -a 256 docs/gateflow/upload-material-o13-tombstone-plan-20260929.md && cat /private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.KIUO03/canary.txt` | 0 | 工作区、输入锁和 canary 读取成功。 |
| `rg --files -g AGENTS.md -g '*goal*' docs . \| head -80` | 0 | 定位项目指令和 goal。 |
| `cat AGENTS.md`、`cat docs/gateflow/upload-material-o13-tombstone-goal-20260929.md`、`cat docs/reviews/plan-review-o13-rereview3-mimo-20260929.md`、`cat docs/gateflow/upload-material-o13-plan-review-adjudication-20260929.md`、`cat docs/gateflow/upload-material-o13-tombstone-plan-20260929.md` | 各 0 | 读取约束、目标、评审、裁决和输入计划。 |
| `rg -n "PR3-F\|剩余\|publish_prepared_upload\|_delete_source_document\|KeyError\|ValueError\|FileNotFoundError" docs/reviews/plan-review-o13-rereview3-mimo-20260929.md` | 0 | 定位第三轮两项 finding。 |
| `rg -n "def (publish_prepared_upload\|_delete_source_document\|delete_source_document\|restore_source_document\|require_source_meta_is_deleted\|_toggle_source_deleted)\|Raises:\|is_deleted" dayu/fins/pipelines/docling_upload_service.py dayu/fins/storage/fs_source_document_repository.py dayu/fins/storage/repository_protocols.py dayu/fins/storage/source_meta_contract.py dayu/fins/storage/_fs_source_document_core.py` | 0 | 定位真实方法及 Raises。 |
| `sed` 读取上述仓储/协议/服务/core/helper 及 `dayu/fins/domain/document_models.py` 的相关行（四次 shell 调用） | 各 0 | 直接核对传播链和溯源字段下标读取。 |
| `git rev-parse HEAD; git branch --show-current; shasum -a 256 AGENTS.md docs/gateflow/upload-material-o13-tombstone-goal-20260929.md` | 0 | 核对基线与输入文档；该调用未单独采集分号前各命令的退出码。 |
| `shasum -a 256 docs/gateflow/upload-material-o13-tombstone-plan-20260929.md`（首次修订后） | 0 | 中间 SHA `51931f557cf594a0fdb0d7bf5d5448ef45436acb773836fd20065fe5b40e89c5`。 |
| `sed -n '38,54p;102,112p' docs/gateflow/upload-material-o13-tombstone-plan-20260929.md` | 0 | 人工核对白名单与覆盖率段。 |
| `python3 - <<'PY' ... PY`（首次静态断言） | 1 | 检查脚本要求三处原因措辞逐字同形，第 6 项原为引用第 5 项；已将第 6 项改成自足文字并重跑。 |
| `git status --short`（首次修订后） | 0 | 未见产品、测试或 README 改动。 |
| `python3 - <<'PY' ... PY`（修正后的六项静态断言） | 0 | PR3-F1、PR3-F2、`FileNotFoundError`、docstring 范围、旧边界与行尾空白均 PASS。 |
| `shasum -a 256 docs/gateflow/upload-material-o13-tombstone-plan-20260929.md`（最终修订后） | 0 | 得到上列输出 SHA。 |
| `git status --short`（最终修订后、本记录写入前） | 0 | 仅见既有未跟踪文档与本次计划；无产品/测试/README 改动。 |
| `test ! -d .venv` | 0 | 隔离环境尚不存在。 |

工具调用另有一次 `functions.exec` JavaScript 语法错误，发生在 shell 命令启动前，故无 shell exit；修正括号后重试成功。首次静态断言 exit 1 已如上保留，不能记作成功验证。

## 验证界限与残余

本轮验证为文档静态核对与代码只读核对。未运行 pytest、coverage、pyright 或真实 CLI；这些属于产品实施后的验证，不能由本轮文档修订替代。实施时仍须按计划建立本 checkout 的 Python 3.11 环境，并验证 owner 状态链、服务路径、单文件覆盖率及 CLI 字节证据。

MiMo 所列 no-op provenance 重校验疑点留在实施期由真实仓储测试和 commit 完整校验证伪；若证伪停点触发，应回裁决。O14/O15 typed 映射、O18 amended、O33 并发与独立 `fins-source-meta-is-deleted-reader-contract` 均不在本轮。下一入口仍是对本次输出 SHA 的有效 Kimi/MiMo 同版双路 plan review；产品未实施，不能据本记录放行 implementation。
