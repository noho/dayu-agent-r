# UM-O25-F01 首轮 plan review 修复记录

- Gate：仅修订 implementation plan；未实施产品、测试或其它 work unit，未宣称 plan review 通过。
- 绑定 goal：`docs/gateflow/upload-material-o25-primary-goal-20260929.md`；MiMo 首轮 review：`docs/reviews/plan-review-20260929-125449.md`；总控采纳登记：`docs/gateflow/upload-material-o25-plan-review-adjudication-20260929.md`。
- 原计划 SHA-256：`20eb093d0071c654c38582231fcca693ee775115aec2be009ac76df89278fc34`。PR1-F1～F4 修订后、此次 PR1-F5 修改前的计划 SHA-256：`9590f021d8c4316d8166de00b93f1a154945b3774ef633662d0b538d663981fd`，预检实测相符。PR1-F5 修订后计划 SHA-256：`bd5b18013d0bc98d3467c867328de85278ebafff8fdb156247115978baadf72e`。

## 修复映射

| 已采纳项 | 计划修订 | 后续实施验收边界 |
| --- | --- | --- |
| PR1-F1 | §首段新增 O16 material action/files accepted+integrated 实施硬依赖；§前置准入仅定义 O25 selector 规则，删除“现有 files/delete usage”及跨入口总序承诺。`delete + files + selector` 按集成后的同一 owner 判归属；O05 form/name 共边界时共同核对次序。 | 不在 O25 补做 O16 半项；O16 typed code/次序与 O04/O23 最终 handoff 均须先在集成基线核实。复合非法输入以真实 owner 与各入口测试，不固化未集成合同。 |
| PR1-F2 | §共享 usage 文案明确复用四个现有 selector code，列出四条目标 message；仅把共享 missing-primary 改为 kind 中性，并要求 O04/O23 集成后在唯一 usage owner 修改。测试白名单加入其 owner 测试。 | owner 测试逐字断言四条文案，material 缺主原件不得出现 filing；CLI/tool 同源投影 typed reason/message，help/schema 与规则一致。 |
| PR1-F3 | §实施切片改为一个对外行为完整的闭环，入口、Docling 消费、skip/发布和旧“首产物”断言迁移同片；完整验证前无可交付中间态。 | 非首项 selector 到 source meta、manifest、snapshot、真实 `process_material` 与 read runtime 同源，入口不得宣称生效而仍发布首项。 |
| PR1-F4 | §指纹补 `identical_skip_safe=True` 的前提：同一次计划内原件身份唯一且 primary 引用唯一 pair；列明 `_can_skip_upload` 与 `_resolve_document_version` 两处门。 | 真实仓储 A→B→B：A `v1`，B 发布 `v2`，同角色逆序 B skipped 且仍 `v2`，无末次转换/发布。若最终 O04/O23 契约不能保证角色可区分则停止。 |
| PR1-F5 | §共享 usage 文案将四个复用 selector reason 的目标 message 改为通道中性业务句；§公开 selector 契约明确 CLI help 的 `--primary`/`--files` 与 tool schema 的 JSON `primary`/`files` 各说明同一规则。§测试白名单补 `tests/cli/test_arg_parsing.py`，并明确 owner 四句、旧 filing/tool 精确断言迁移及 CLI/tool 公开投影断言。 | 同一 usage owner 逐字生成四句；CLI/tool 错误共享 reason/message，tool 错误不指示 CLI 选项。CLI help 与 tool schema 各保留本入口名称；全局其余 usage 文案仍属 `fins-upload-usage-message-channel-neutral`。 |

PR1-F5 的四条目标句依序为：“多文件必须指定一个主文件”“主文件只能指定一次”“主文件路径必须精确匹配本次上传文件路径之一”“删除时不得指定主文件”。这些句子保留已确认的唯一选择、规范路径精确命中和 delete 禁止选择规则。直接证据：当前 `dayu/fins/ingestion_runtime.py:1036-1039` 的四条共享 message 包含 CLI 选项，`dayu/fins/tools/upload_tools.py:239-248` 的 tool schema 使用 JSON `files`/`primary`，`dayu/fins/upload_format_contract.py:606-613` 已按 CLI/tool 入口分别投影参数名。计划只指定后续 owner 修订，不宣称产品已改变。

## 只读证据与 SHA-256

| 文件 | SHA-256 | 用途 |
| --- | --- | --- |
| `AGENTS.md` | `cb26618ab566804c97a3ef2f269537b7313e59370e5ddd0258d9b753b08ac45e` | owner、文本及计划修改边界。 |
| `docs/gateflow/upload-material-o25-primary-goal-20260929.md` | `e4dd228fc5cf820aebd489c020c65ce4123623c8c782035d626063483cf40ebd` | 绑定目标与 O04/O23 依赖。 |
| `docs/reviews/plan-review-20260929-125449.md` | `f90f8794db25975dc0352053aecd5986458eb9303940ef11e28c739be5bbc203` | MiMo 首轮四项 finding 与 open questions。 |
| `docs/gateflow/upload-material-o25-plan-review-adjudication-20260929.md` | `e3c0bce7d9d88e1b1b4a9755bd3f713cda9925004cceb18b9534e9d98fe5792e` | 总控 PR1-F1～F4 采纳范围。 |
| `/private/tmp/dayu-upload-assets/dayu/fins/upload_asset_plan.py` | `73c00fbfbc66c74cc334331087dccd1f4c3c6c9ae6dc2218487b66f1eb0452ca` | 相邻 O04/O23 候选存在保序 pair；material delete 返回空计划，未证明 O16 已生效。 |
| `/private/tmp/dayu-upload-assets/dayu/fins/upload_usage_contract.py` | `64e5b33a7f907d3b604f3a9efd341b1849b5f9ac8615da1feab13c7e29ae8659` | 候选 usage owner 仍有“多文件 filing”消息；不视为集成接口。 |
| `/private/tmp/dayu-upload-o16/docs/gateflow/upload-material-o16-action-files-goal-20260928.md` | `fc3de44e3a2d74ef66315a4f44d4d5eab5ed558ae297ef89fcd801a1d995b9fe` | O16 独立 action/files owner 与时序目标。 |
| `/private/tmp/dayu-upload-o05/docs/gateflow/upload-material-o05-required-identity-goal-20260929.md` | `43838b255db45d3b1c7e7caeca04372d69905e2db58522d319be3a0dfb6aab2f` | O05 form/name 共边界，需集成时共同核对次序。 |

当前 O25 checkout 的 `dayu/fins/ingestion_runtime.py` 四个 selector usage code 已存在，missing-primary message 仍带 filing；`dayu/fins/pipelines/docling_upload_service.py` material 仍以首个转换产物定 primary，material 指纹 `identical_skip_safe=True`，skip/version 分别检查该标志；`process_material` 经 snapshot 的 `get_primary_source()` 读取。以上是当前代码观察，不是修复完成证据。

## 残余风险与下一 gate

1. O04/O23 最终 typed handoff、pair、usage owner 尚未集成到本 checkout；O16 action/files 亦未集成。后续实施必须先读集成 HEAD 和 owner 测试，核对字段/错误次序，再按最终 public contract 定代码落点。候选路径不是 accepted contract。
2. O05 若与 O16/O25 在同一 admission 边界集成，复合错误总序需共同 owner 裁决；计划没有单方固定。CLI/tool 现有文件存在性预检在多错误输入下可能早于 owner，真实入口测试要区分单因 selector 错误与复合输入。
3. 本轮仅文档变更，无产品测试、pyright、真实 CLI 或覆盖率结果；计划需有效 Kimi/MiMo 同版复审后才可进入 implementation。真实 CLI 的跨命令证据使用 `process_material`，以 snapshot/read runtime 测试补足 read 事实。

## 命令记录

首次探索相邻 `/private/tmp` 目录时有一条命令失败，原样如下；它因无关的 `codex-daemon-501` 目录 stat 权限而退出 1，随后改用逐项捕获 `OSError` 的只读 Python 查询完成定位，未改变任何文件：

```sh
python - <<'PY'
from pathlib import Path
for p in sorted(Path('/private/tmp').iterdir()):
 if p.is_dir() and ('dayu' in p.name or 'upload' in p.name):
  q=p/'dayu/fins/upload_asset_plan.py'; r=p/'docs/gateflow/upload-material-assets-plan-20260929.md'
  print(p, 'asset_code=',q.exists(),'asset_plan=',r.exists())
PY
```

失败末行：`PermissionError: [Errno 1] Operation not permitted: '/private/tmp/codex-daemon-501'`。

第一次 `diff/check` 包装命令也失败，原样如下。`git diff --no-index --check` 在比较 `/dev/null` 与未跟踪文件时以 1 表示存在差异，stdout/stderr 均为空；包装脚本误把这一预期退出码当成空白错误，最终退出 2。它没有发现实际文档空白错误，也没有修改文件。

```sh
python - <<'PY'
from pathlib import Path
import subprocess
for name in ['docs/gateflow/upload-material-o25-primary-plan-20260929.md','docs/gateflow/upload-material-o25-plan-review-pr1-fix-20260929.md']:
 r=subprocess.run(['git','diff','--no-index','--check','--','/dev/null',name],text=True,capture_output=True)
 print(name,'git_diff_no_index_check_exit=',r.returncode,'stdout=',repr(r.stdout),'stderr=',repr(r.stderr))
 if r.returncode != 0: raise SystemExit(2)
r=subprocess.run(['git','diff','--check'],text=True,capture_output=True)
print('git_diff_check_exit=',r.returncode,'stdout=',repr(r.stdout),'stderr=',repr(r.stderr))
if r.returncode != 0: raise SystemExit(2)
PY
```

修正后的只读检查将 `--no-index` 的 0/1 区分为“无差异/有差异”，同时要求 stdout/stderr 为空：两个目标文件均为预期的 `raw_exit=1`、空白错误为空，`git diff --check` 返回 0。哈希读回与关键文案检查均通过。除以上两条，已执行的 shell 命令均返回 0。
