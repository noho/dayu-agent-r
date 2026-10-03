# UM-O19-E01：符号链接文件输入真实 CLI 补证

- 状态：证据补跑完成；未修改产品代码，未更新正式 oracle/registry/readiness。
- 代码：隔离 PR #197 集成 checkout `/private/tmp/dayu-upload-pr197-integration`，HEAD `45444785a60d26737cfbd27762946cd08b2e66d1`，Python 3.11.15，使用该 checkout 的 `.venv/bin/python`；不是冻结 validation commit `fac32ecb...`，也不把新结果回填冻结 F15。
- 本轮正式隔离 evidence root：`/private/tmp/dayu-o19-e01-formal.x8gq0rcm`。原始 `command.json`、`result.json`、`stdout.txt`、`stderr.txt`、`filesystem-before.json`、`filesystem-after.json`、`filesystem-diff.json`、`key-json-audit.json`、`process-residue.json` 均留在该目录。先前探索运行 `/private/tmp/dayu-o19-e01.SBPf1P` 不用于正式结论。

## 方法与直接结果

在全新 root 创建 44 字节普通目标 `inputs/probe.txt`（SHA-256 `e65fee366323901effbc6bba2375962e83b8f63749e344ad62e38e3a2b6368ba`）及同目录相对符号链接 `inputs/symlink-material.txt -> probe.txt`。采集器直接构造 argv 列表传 `subprocess.run`，不对文件实参调用 `resolve()`。`command.json` 的 `--files` 值逐字为 `/private/tmp/dayu-o19-e01-formal.x8gq0rcm/inputs/symlink-material.txt`，不是目标路径；同时记录 lexical link、readlink、resolved target、解释器、cwd、HEAD 和环境增量。运行前隔离 workspace 为空，前后树快照与 diff 已落盘。

真实命令为该 checkout 的 `.venv/bin/python -m dayu.cli upload_material --base /private/tmp/dayu-o19-e01-formal.x8gq0rcm/workspace --ticker AAPL --action create --forms MATERIAL_OTHER --material-name SymlinkEvidenceFormal --files /private/tmp/dayu-o19-e01-formal.x8gq0rcm/inputs/symlink-material.txt --company-name 'Apple Inc.'`。退出码 0、耗时 3.405 秒；stdout 有 preparing、started、completed、succeeded，摘要 `requested_files=1 stored_files=1`；stderr 空。`process-residue.json` 在子进程退出后只读查询进程命令行，排除查询进程及其父进程，匹配该 evidence root 的残留为空；workspace 中无 SQLite/DB 文件。

发布的 source meta 记录原件 `probe.txt`（44 字节、SHA 与目标一致）和派生 `probe_docling.json`（984 字节、SHA-256 `b389f768ad0e0335e4aa2b8c9b704d85ab44e009756e33b627c50b5681716352`），两文件均实际存在且与 meta 哈希相等。`primary_document=probe_docling.json`，manifest 恰有同一 document ID 的一条 active、ingest_complete 条目；原件、Docling、meta 与 manifest 均在同一次成功发布树中。具体相对路径和原始 SHA 见 `key-json-audit.json`；不能从 `stored_files=1` 误读为只存一个物理资产。

## owner 归因与裁决边界

当前代码 `dayu/cli/commands/fins.py:_validated_upload_files` 对 argparse 收到的 raw path 执行 `Path(raw_file).expanduser().resolve(strict=False)` 后才构造 Fins selection。因此**这次** CLI 的 argv 确实是 lexical symlink，随后 CLI owner 规范成目标路径，已发布原件名为 `probe.txt`；不应声称存储保留链接名。冻结 F15 的 `command.json` 在 CLI 调用前已经是目标路径，而冻结采集器的具体替换代码不在本轮源文件中，无法据此断定当时是哪一步预先解析；本次通过显式 argv 列表消除了该证据缺口。

可登记的窄结论是：在上述 HEAD、同目录且目标位于隔离 root 内的有效 TXT symlink 输入，CLI 接受 lexical link，规范为目标文件，再成功转换并同时发布 original 与 Docling JSON。不能泛化到悬空链接、目录链接、越界目标、其它格式、不同平台，亦不能把冻结 F15 改写为已验证 symlink。是否把链接名保留为原件身份属于 O04/O23 的路径与资产规划合同，不能由本证据项偷偷定规则。正式 scenario/registry 登记须保持本轮 lineage 与上述边界。
