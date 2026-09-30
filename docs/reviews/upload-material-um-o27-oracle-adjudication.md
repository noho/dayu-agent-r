# upload_material 第一轮校准：UM-O27 用户裁决

登记日期：2026-09-28。状态：**用户已接受，正式 oracle/scenario 尚未更新**。用户明确要求上传后单独运行 `process_material`；`upload_material` 成功只表示 source 已发布，不表示 processed 产物已生成。本项核对真实 `process_material` 在另一次 CLI 命令中消费 UM-R01～R03 已发布的 material 并持久化 processed 产物；未发现独立修复项。processed 内容的抽取准确性不在本项裁决。

## 冻结 evidence 与运行

冻结 evidence root：`/Users/leo/workspace/.dayu-cli-ci/upload-material-calibration-20260818-mNeTId`；validation commit：`fac32ecbff9bfe792b63ee9667c8697826b631f4`。本次核对 SHA-256：observed-behavior.md `4c73df2f41ed73b728231e64eb8daedb3561c7b49dd695c39a3fe983f60c5d64`、observed-behavior.json `23497494f9f5e4055f146fdcef93e6502d57a9bd6e27066f3ae518c6950cd8a0`、evidence-manifest.json `fccbb5464eb8e95450cfc7efa2fad1ad6fab60e976d356a967340c2a19b66abd`。

`matrix-inventory.json` 对 X01～X03 分别规定前置为 R01～R03 已完成；`filesystem-before.json` 直接显示相同 workspace 中相应 material source 的 identity、meta、原件、Docling JSON、manifest 已存在，processed 尚无文档产物。随后从冻结 run 的 `repo`、stdin=`DEVNULL` 运行 `.venv/bin/dayu-cli process_material --base <同一 workspace> --ticker <canonical> --document-id <刚上传的 stable ID>`：

| 场景与前置 | ticker / document ID | 输出与持久化 |
| --- | --- | --- |
| UM-X01 ← UM-R01 | `MSFT` / `mat_a9864e9ea49aff01eb286513d2b4a533425aea49` | selected=1、processed=1、failed=0；processed sections=1、tables=0。 |
| UM-X02 ← UM-R02 | `600519` / `mat_70f1c12b6d1efe731f38ba55467cbb677f58480a` | selected=1、processed=1、failed=0；sections=17、tables=14。 |
| UM-X03 ← UM-R03 | `0700` / `mat_1784891741790344863048b780f46adc5e6a6b1e` | selected=1、processed=1、failed=0；sections=1、tables=0。 |

三次 `result.json` 均为 exit 0、execution_outcome=success、evidence_status=sufficient、未超时、残留进程 0；`screen.txt` 显示 preprocess.selected、document_started、document_processed、completed，终态 skipped=0、not_supported=0、stderr 为空。`filesystem-diff.json` 仅新增各自 processed document 的 identity、`sections.json`、`tables.json`、`tool_snapshot_meta.json` 和 processed manifest；无材料 source 文件修改或删除。`key-json-artifacts.json` 的 processed snapshot meta 在每个场景均有 `source_kind=material`、`source_provider=user_upload`、同一个 document ID、`source_document_version=v1`、与 R01～R03 source meta 完全相同的 `source_fingerprint` 和 `primary_document`，`ingest_complete=true`、`reprocess_required=false`；processed manifest 的 document ID、版本、section/table count 与 snapshot 一致。三个 sections/tables JSON 的条目数量分别与 snapshot meta 的 1/0、17/14、1/0 相等。上述 exact identity、前置文件状态及处理后物理差异共同证明跨命令消费链路，不能只凭 exit 0 宣称成功。

SQLite count=0；Host/EventLog/Trace/Memory/job roots 均 queried-but-absent。这与本 direct CLI 处理范围一致，跨入口 durable 边界由 UM-O28 另行裁决。US/HK 的零表或单章节不据此判定 Docling 内容正确/错误，也不把 processed manifest 的 `quality=full` 当作准确性审计。

## 语义 owner 与 Accepted 行为

`dayu/cli/commands/fins.py:_process_material_stream` 把 canonical ticker 与 document ID 交给 `dayu/service/fins_direct.py:process_material`，该 Service 明确要求 `SourceKind.MATERIAL`，由 Fins preprocess owner 选择仓储中的同一 source；processed repository 持久化摘要。下游 read/runtime 只能消费已发布的 source primary 和 processed facts，不能从文件名或 argv 重新推断。由于三例均为单文件 source，UM-O25 的“多文件必须显式主文件”规则不改变这些历史成功样本；UM-O23 的统一派生名实施后，processed snapshot 必须继续回指实际发布的主资产身份。

接受**仅针对 X01～X03 的跨命令可消费性与独立运行边界**：真实 `process_material` 能在相同 workspace 按精确 document ID 找到 R01～R03 的已发布材料，终态各处理 1 份且零失败，并新建与 source ID/版本/指纹/primary 一致的 processed 产物。上传成功不自动运行 process，调用方需单独执行。这个观察不证明所有文件类型、损坏源、重复处理、并发处理或处理内容的语义准确性；也不代表 Host/Engine 处理路径。未见 owner 级修复动机，本项不登记产品修复。

当前不新增正式 oracle/scenario，不改写冻结 evidence、registry/readiness 或产品代码。正式 scenario 应逐一配对 R01→X01、R02→X02、R03→X03 的同 workspace 前后证据，并核对上传后 processed 尚不存在、单独 process 后新建以及 processed/source exact identity，不仅断言 CLI exit。

直接证据路径：

- `matrix-inventory.json` 的 X01～X03 precondition
- `evidence/cross/UM-X01-process-us-material/command.json`、`screen.txt`、`result.json`、`filesystem-before.json`、`filesystem-diff.json`、`key-json-artifacts.json`
- `evidence/cross/UM-X02-process-cn-material/command.json`、`screen.txt`、`result.json`、`filesystem-before.json`、`filesystem-diff.json`、`key-json-artifacts.json`
- `evidence/cross/UM-X03-process-hk-material/command.json`、`screen.txt`、`result.json`、`filesystem-before.json`、`filesystem-diff.json`、`key-json-artifacts.json`
