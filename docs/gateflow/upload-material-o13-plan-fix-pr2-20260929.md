# UM-O13-F01：MiMo 第二轮 plan review PR2-F1/F2 修复记录

- Gate：`plan review -> fix`。本次仅修订 `docs/gateflow/upload-material-o13-tombstone-plan-20260929.md` 并新增本记录；计划仍是候选，未获有效 Kimi/MiMo 同版双路复审，不称为 accepted，不进入实施。
- 工作区：`/private/tmp/dayu-upload-o13`。输入计划 SHA-256：`fd7fef7080f48a6b208d12d0ecfad10009157618f05cf854186ceaf539690396`；修订后计划 SHA-256：`5b02d9e62362a2dd88006a25dffab76803983bfcb2cb488aa5bea34add7c5d58`。

## 动机、owner 与直接证据

PR2-F1/F2 的动机成立，范围是计划的可执行合同一致性，不改变已确认的同周期重复 delete 成功且业务字节不变合同。已实读 `AGENTS.md`、goal、锁定 SHA 的原计划、MiMo 第二轮 review、总控裁决，以及 core/helper/repository/protocol/README owner。`_fs_source_document_core.py:_toggle_source_deleted` 同时承载 delete/restore，当前 `_read_json_object` 后直接给 `meta["is_deleted"]` 赋目标值，损坏值在 restore 方向会被覆写；`source_meta_contract.py:13-32` 的 canonical reader 对缺失字段抛 `KeyError`、非布尔值抛 `ValueError`。`dayu/fins/README.md:101` 已规定缺失或非布尔值 fail closed。`fs_source_document_repository.py` 和 `repository_protocols.py` 的 delete/restore Raises 当前均未列 `KeyError`。这两个计划缺口与总控 PR2-F1/F2 裁决一致。

## 修订结果

1. 状态表补出损坏/缺失 `is_deleted` 的 restore 行；实现段落要求 delete 与 restore 在任何赋值/no-op 判定前均调用同一个 canonical reader。缺失透传 `KeyError`，非布尔透传 `ValueError`；不通过 restore 静默修复损坏值，不为迁就文档翻译 core 异常。
2. `tests/fins/test_fins_storage_atomicity.py` 的实施计划改为以真实 `Fs*Repository` 和 batch 参数化 filing/material、delete/restore、字段缺失/非布尔值；分别断言异常类型、调用前后 staging 的 source meta/manifest/资产原始字节不变，以及 rollback 后已发布的相同业务字节与 revision 不变。
3. 实施白名单增列 `dayu/fins/storage/fs_source_document_repository.py` 与 `dayu/fins/storage/repository_protocols.py`，**仅**允许各自 delete/restore 的 Raises docstring 同步 `KeyError`/`ValueError` 合同；签名、派发和运行行为不变。core 已在原白名单，其相关 Raises 文档随真实行为核对。README 第 4 项实施时核对 strict reader 描述并同步两方向 fail-closed，当前不改 README 正文。
4. 原 F1–F5 的独立 Python 3.11 venv、锁文件 editable 安装、每步真实 CLI 身份断言、五文件测试/单文件 ≥80% coverage、pyright、全新隔离 CLI 状态链，以及 O14/O15/O18/O33 与 reader follow-up 边界保留。两处新增文件只准改 docstring，不增加可执行语句；行为修改文件的单文件覆盖率门仍针对 core。

## 命令、exit 与失败

| 命令或核对 | exit | 结果 |
| --- | ---: | --- |
| `cat AGENTS.md`、goal、原计划、MiMo review、总控裁决 | 0 | 指定输入已实读。 |
| `shasum -a 256 docs/gateflow/upload-material-o13-tombstone-plan-20260929.md`（修订前） | 0 | 与锁定输入 SHA-256 完全一致。 |
| `nl -ba` / `rg -n` 读取 core、canonical helper、仓储、协议、fins README 与 batch/manifest 路径 | 0 | 确认 owner、异常真源与原有文档缺口。 |
| `python3 - <<'PY' ... PY` 静态检查计划中的 PR2-F1/F2、F1–F5、CLI 和 WU 边界标记 | 0 | 14 项均 PASS；这是文档一致性检查，不代表产品验证。 |
| `shasum -a 256 docs/gateflow/upload-material-o13-tombstone-plan-20260929.md`（修订后） | 0 | `5b02d9e62362a2dd88006a25dffab76803983bfcb2cb488aa5bea34add7c5d58`。 |

本轮命令无失败。只改计划文档，未运行测试、coverage、pyright 或真实 CLI；这些属于后续实施验证，不能将静态检查当成通过。未创建 venv、未改产品/测试/README 正文/goal/旧 review/总控裁决，未实施任何 WU，未提交、推送或派发复审。

## 残余与交接

- 计划仍须在同一 SHA 上获得有效 Kimi/MiMo 双路 plan review；本记录不替代总控接受结论。
- core 单文件覆盖率原复测基线 473 statements / 97 misses / 79%，达到 ≥80% 仍依赖实施期真实仓储状态链测试；若未达标，按计划补同一 owner 的有意义用例并复审。
- 独立 venv 安装与真实 CLI 身份、字节 canary 尚未执行；锁文件依赖获取失败时按计划停止验证 gate。
- 重复 restore-on-active、其它 reader 路径、O14/O15/O18/O33 均维持原边界；batch 物理 swap 的 mtime/inode 与并发语义未由本计划承诺。
