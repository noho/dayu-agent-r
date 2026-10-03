RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/gpt-6-sol-b96d9ca3
CANARY=gpt-6-sol-b96d9ca3

# UM-O20-F02：第二轮 MiMo plan findings 修订记录

- 工作区：`/private/tmp/dayu-upload-o20-f02`；HEAD：`9735800cb55a40336469593fa2fddae43c9c69ad`，未提交。
- 输入计划 SHA-256：`4d01db5528156e30ea177b8c76fb2e081f7d505bbe08c2d92417f138462f9deb`；本次输出计划 SHA-256：`b2723237bb528bfb873add47370b8344b7daa814a1e852857b6ccc9df1f043b4`。审查输入：`docs/reviews/plan-review-20260929-120634.md`，SHA-256 `a6b4348f76722152557eae5a7c38ee8599937d2189169d24c526691758e79deb`。
- 本文件只登记计划文字修复与一手核查；**不裁定 plan pass**，不执行 P0、产品实现、第三方 taxonomy 下载或下一 gate。冻结 E01、goal、probe、旧 review 与总控 adjudication 均未修改。

## 动机、owner 与直接核查

动机成立：Docling 2.127.0 `backend_options.py:505-521` 的 `taxonomy` 描述明确允许相对位置的散文件与可选 zip catalog 同目录；`xbrl_backend.py:125-148` 对一个目录 `copytree`，然后收集顶层合法 zip。AAPL fixture 的 `aapl-20240928_htm.xml:16` 是相对 `schemaRef`，`aapl-20240928.xsd:7-16` 有绝对 import，`:19-22` 有相对 linkbaseRef。旧互斥 layout 会错排这个引用图；源码支持**可表达性**，尚不证明该组合实际验证通过。`dayu/documents/docling_runtime.py:603` 是唯一 `DocumentConverter` 构造点，`:554-605` 只注入 PDF option；`dayu/fins/pipelines/docling_process_converter.py:99-128` 是闭合配置；`dayu/fins/pipelines/docling_upload_service.py:1504-1505` 对 material 逐文件转换。因此未来输入配置 owner 在 Documents runtime，Fins 只传 typed 参数。版本、typed/explicit 分支与已发上游 #4437 的归因保持原裁决，不借计划文字改成产品已支持。

证据持久性问题也成立：probe 原始产物在 `/private/tmp/dayu-o20-f02-probe.AdlwrW/`，旧计划只写“保存”；`.gitignore:4` 确认 `workspace/` 被忽略，但当前 worktree 本身位于 `/private/tmp`，目标归档目录尚不存在。故新计划把保留与可回读验证列为 P0 前置，不能凭路径名称宣称已经持久。受许可限制真实包归管理员受控归档 owner，若位置、许可或回读不能成立则相应 P0-B 步骤 blocked，不能擅自把包放仓库或降低 goal。

## F02-PR2-F1–F7 文字处置

| Finding | 本次计划修订 | 尚未证明 |
| --- | --- | --- |
| F1 同根组合 | §3 以 `taxonomy_root` 加可选顶层 `catalog_zip_name` 表达相对散文件与单份 catalog zip 共存；绝对 import 与相对引用各有解析分工；§5 指定 AAPL 同构、完全合成的离线混合引用图，先 Arelle 验证再 Docling Path/Stream 对照。 | zip/catalog 组合的真实运行与有效财报 CLI。 |
| F2 P0-A 完成态 | §5 逐平台 `pass`/各类 `blocked`、候选版本与生产 pin 分开；任一平台 blocked 则 P0-A blocked、生产 pin 未定，回 goal/总控裁决 runner 或平台承诺。 | 三平台真实安装、`pip check`、lock 与 pin。 |
| F3 证据 owner | §5 指定本 work unit 证据 owner、忽略目录内可公开原件与相对清单/逐文件 SHA；真实受限包由管理员受控持久归档，保留许可、布局、哈希、保留期限与回读；易失 worktree 需先建立留存/备份。 | 实际迁移、备份、回读和管理员真实包归档。 |
| F4 P0-B 顺序 | §5 先裸目录与混合 zip/catalog 自足探针，再盘点外部许可和闭包；许可阻断不吞掉已独立得到的机制结果。 | 探针执行与真实来源许可。 |
| F5 零出站 | §4 把承诺统一成转换进程及子进程零出站，含非 taxonomy URL；远端获取仍须回 goal。 | 任一平台 OS 网络强制边界。 |
| F6 非 schemaRef 向量 | §6 加 C8：DOCTYPE/ENTITY、XInclude、样式/链接导入、非常规 scheme、扩展/插件；逐向量合成输入及 OS trace，明确有限矩阵不能穷尽未知向量。 | 全矩阵与三平台 OS trace。 |
| F7 root/provenance | §3 指定管理员清单 owner 与 Documents runtime 校验 owner；绝对规范、解析后 workspace 外、清单不匹配即拒绝；TOCTOU 留到实施计划闭合并实测。 | 运行时校验、受控快照与强制隔离。 |

第二轮修订保留原 F1 版本真源、F2 typed 与 explicit 独立分支、原 F4/F5 的三平台 blocked 出口和总控对 #4437 的已发事实。P0 仍只是 evidence/probe 规格；S1/S2、受控支持 goal 与三平台承诺没有因本文本改变。

## 命令、结果与失败

- `git rev-parse HEAD`：exit 0，输出 `9735800cb55a40336469593fa2fddae43c9c69ad`；`shasum -a 256 docs/gateflow/upload-material-o20-xbrl-runtime-plan-20260929.md`：修改前 exit 0 且与输入 SHA 匹配，修改后 exit 0 且为上列输出 SHA。
- `git check-ignore -v workspace/evidence/upload-material-o20-f02/manifest.json`：exit 0，命中 `.gitignore:4:workspace/`；`test ! -e .venv && test ! -d workspace/evidence/upload-material-o20-f02`：exit 0，说明本 worktree 既无 `.venv`，也未建立 P0 归档。
- 对 Docling `backend_options.py:505-521`、`xbrl_backend.py:105-175`，Dayu 的唯一 converter 构造、闭合配置与 material 转换路径，以及 AAPL fixture 引用图作只读 `sed`/`rg`：命令 exit 0；仅用于上述源码可表达性判断，不是 zip 可用性探针。
- `git diff --check -- docs/gateflow/upload-material-o20-xbrl-runtime-plan-20260929.md`：exit 0；该计划是既有 untracked 文件，此命令没有把它作为 tracked diff 展示，故另按全文 `cat`/`rg` 阅读并作哈希复核。
- `git diff --no-index --check /dev/null <计划文件>` 与同命令的 `<本 artifact>`：各 exit 1、无输出；`--no-index` 对新文件与空文件存在差异即返回 1，此处未报告空白错误，不能把 exit 1 写作命令成功。末次 `rg -n 'C0–C7|--xbrl-taxonomy-layout|layout: Literal|默认无 taxonomy 网络请求|仅本机.*resolver|项目全树.*未证' <计划文件>`：exit 1、无匹配，表示这些旧措词未再出现。
- 初次检查归档路径的组合命令 `rg -n 'workspace/evidence|workspace/|^workspace|evidence' .gitignore && ls -ld workspace workspace/evidence workspace/evidence/upload-material-o20-f02 2>&1 && rg -n 'archive|归档|provenance' <计划文件>`：exit 1，原始 `ls` 输出是 `ls: workspace: No such file or directory`、`ls: workspace/evidence: No such file or directory`、`ls: workspace/evidence/upload-material-o20-f02: No such file or directory`；由 `&&` 短路，末段 `rg` 未执行。该失败是归档尚未创建的直接观察，未擅自创建目录。
- 第一次大块 `apply_patch`：**失败**，原文 `apply_patch verification failed: Failed to find expected lines in /private/tmp/dayu-upload-o20-f02/docs/gateflow/upload-material-o20-xbrl-runtime-plan-20260929.md: 最低安全承诺：转换进程只读经批准的 taxonomy/程序资源，不读受信输入树外 sentinel；默认无 taxonomy 网络请求；拒绝有界、可取消、可清理。`；该次未落笔。随后分段 `apply_patch` 成功，已读回全文核对。
- 本轮仅修改文档，未运行产品测试或 pyright；本 worktree 无 `.venv`。README 更新触发未命中。既有探针失败命令及 exit 原文仍见 probe §P1–P3，未重跑，也没有把那些失败写成本轮执行结果。

## 未证条件与停点

本轮没有做同根 zip/catalog 运行探针、真实 taxonomy 下载、真实财报正样本、任何平台的 OS 隔离、证据实际迁移/回读、fresh venv 安装或 Dayu CLI 验收。若后续源码/运行证据反证混合布局可达性，则停止该接口承诺；若管理员受限包无法合规持久归档，则真实样本步骤 blocked；若须改变 binding goal 或平台承诺，只能回 goal/总控裁决。本文本不是 plan pass，下一步仅可对输出计划同 SHA 复审，本轮到此停止。
