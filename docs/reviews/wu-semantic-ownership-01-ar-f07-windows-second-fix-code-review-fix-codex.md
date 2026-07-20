# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 第二轮 Windows code-review zero-change disposition — AgentCodex

## Gate 与结论

- Gate：既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 的同一 AR-F07 second Windows fix code-review disposition；不是新 WU 或新 sub-WU。
- immutable baseline / HEAD：`ac5e755ba7148a5d2f30f3f11222548b3c57cd9e`；branch：`phaseflow/host-issues-control`。
- Controller 唯一 finding 裁决真源：`docs/reviews/wu-semantic-ownership-01-ar-f07-windows-second-fix-code-review-controller-adjudication.md`。
- 决策：`ZERO_CHANGE_FIX_PASS / READY_FOR_CONTROLLER_VALIDATION`。
- 两路 material finding 均为 `0`；本 code-review gate 的 accepted/open finding 为 `0`，blocking question、deferred finding、needs-more-evidence finding 均为 `0`。
- 当前没有可修复的 owner-level defect。除新增本 artifact 外，产品、tests、README、workflow、control 与既有 artifacts 均未修改。
- 未 stage、commit、push、创建或修改 PR、dispatch workflow、更新 control，亦未关闭 AR-F07 或 umbrella。

## 已完整读取的 review 与裁决输入

| 输入 | 行数 / 字节数 | SHA-256 | 结论 |
|---|---:|---|---|
| `docs/reviews/wu-semantic-ownership-01-ar-f07-windows-second-fix-code-review-mimo-20260719-234121.md` | 108 / 11,139 | `3530671635e73d21d6efd7445ab12e6792a38c46d8b8a4ecccec511fa1de441b` | `PASS / 0 findings` |
| `docs/reviews/code-review-20260719-233825.md` | 311 / 25,828 | `b7ab6db9e79c1d382fc8ef71377eb8968364d4be632b2dd5effc0373aa86ff6a` | `PASS / NO_MATERIAL_FINDING` |
| `docs/reviews/wu-semantic-ownership-01-ar-f07-windows-second-fix-code-review-controller-adjudication.md` | 46 / 3,831 | `8629f35bd90d38d73cd32e75d36b42bc6b6606da6f01021038f93e3f490d55e2` | `PASS / ACCEPTED_CODE_FINDING=0 / ZERO-CHANGE DISPOSITION REQUIRED` |
| `docs/reviews/wu-semantic-ownership-01-ar-f07-windows-second-fix-controller-validation.md` | 53 / 4,927 | `b87eb1f59a7eaf9ce55d74b777dc0f2c2936fb216041cb796409c8ffa5d9c5bf` | `PASS / READY_FOR_DUAL_COMPLETE_CODE_REVIEW / WINDOWS_RERUN_REQUIRED` |

三份 review/adjudication 输入的逐行排序 manifest digest 为
`2a43a9a049d97225f2d461d4d506a0f3e807ea07318cf12c2bf7eb11f8d4ea75`。Controller validation 也已完整读取；它是 reviewed 10-path target 的既有 validation artifact，因此同时列入下方内容锁。

## 第一性原理与语义 owner 判断

两路 reviewer 都确认 WIN2-F01/F02/F03 的直接根因与修复 owner 正确，且没有提出 material finding。Controller 对所有 observation 逐项裁决后也没有留下当前代码缺陷：

- CLI strict UTF-8 的 owner 仍是共同进程入口 `dayu/cli/main.py`，没有下游 fallback 或多真源。
- fixed argv 的 Windows batch/CRT quote 与 escape owner 仍是 `dayu/cli/upload_script.py`，production 明确拒绝 NUL/CR/LF。
- R11 精确 process probe owner 仍是 `.github/workflows/r11-upload-script-windows.yml`，没有全局弱化 native failure。

因此，修改 comment helper 测试、引入另一套 per-process timeout policy，或让 test oracle 支持 production 输入域外的 line continuation，都不能关闭一个可复现的当前缺陷，反而会增加重复测试、策略 owner 或无关 batch grammar。当前正确修复是只记录裁决并保持实现树不变。

## Finding 与 observation disposition

### Material findings

- AgentMiMo：`0`。
- AgentDS：`0`。
- Controller accepted：`0`。
- Controller rejected material finding：`0`；两路没有提出 material finding。
- deferred-with-owner：`0`；needs-more-evidence：`0`；blocking open question：`0`。

### AgentMiMo observations

1. Windows-only 真实 `cmd.exe` tests 无法在当前 Darwin 主机运行：保留为已经记录的真实 runner residual；`NO CURRENT CODE FIX`。
2. workflow 静态字符串断言不能证明完整 PowerShell 运行行为：由真实 R11 runner 闭环；`NO CURRENT CODE FIX`。
3. `cmd.exe /?` exact exit `1` 的未来平台稳定性：这是 intentional fail-closed behavior；变化时 workflow 应失败并暴露证据，`NO CURRENT CODE FIX`。

以上三项不是 deferred code finding，也不形成新的 residual 分类。

### AgentDS observations

1. `_escape_windows_comment` 独立 parametrized test：`REJECTED-WITH-REASON / NO CURRENT FIX`。现有 renderer contract 已覆盖 regeneration `%` 与 metacharacter；第二轮失败根因位于 body quote owner，没有可复现 comment defect，重复 helper test 不能关闭当前风险。
2. `Invoke-CmdEvidence` 显式 per-process timeout：`REJECTED-WITH-REASON / NO CURRENT FIX`。`ver` 与 help 是本地瞬时命令，workflow 已有 30 分钟 hard timeout及失败 artifact；没有 hang 直接证据，新增第二套 timeout/policy 属于过度设计。
3. `_decode_windows_batch_fixed_token` 不支持 caret line continuation：`REJECTED-WITH-REASON / NO CURRENT FIX`。production renderer 在唯一 owner 拒绝 CR/LF，test oracle 不应实现 production 输入域外的 batch grammar。

### 既有 WIN2 finding 状态

WIN2-F01/F02/F03 不是本轮 reviewer 新 finding，继续保持
`LOCAL_FIX_VALIDATED / ACCEPTED-OPEN UNTIL WINDOWS RERUN`。这不改变“本 code-review gate accepted/open finding = 0”：三项是修复前已接受、当前仅等待外部 runner closure 的既有 release residual。

## 10-path reviewed target 内容锁

验证前后逐路径 SHA-256 相同：

| 分类 | 路径 | SHA-256 |
|---|---|---|
| workflow | `.github/workflows/r11-upload-script-windows.yml` | `4c915a9c79efa5ee0166eb6fae44513ecc077b974217ca1e855e8b7ec4507f43` |
| workflow | `.github/workflows/r12-init-windows.yml` | `ba99b5a40c6d3116e1d83b05cd97139dcc62699722269b0aa6fc1a8d5ebea7b8` |
| product | `dayu/cli/main.py` | `127a7b13c3b8b7738f4b3ecfc9fef73383d8e7952bdef566a4449bafcf932509` |
| product | `dayu/cli/upload_script.py` | `a7b5868e748b3f71b38415f1471f9fed7080bc292110e458888b36e5a5a9daeb` |
| README | `tests/README.md` | `768b7500c616b0a43d53d0b91db73691e6249d98c43ed1302a2af003a2972eb2` |
| test | `tests/cli/test_arg_parsing.py` | `990d90328fb553e8122317abf08d6f6869a46b51eb1dd1448689de3aca1b7341` |
| test | `tests/cli/test_upload_filings_from_command.py` | `548843d329b5d6e8fa3c5aabc4653e9991c06013ec84969b15e2a5df12fc5e2a` |
| control | `docs/host/issues-implementation-control.md` | `7a89d6126db00d9afda8b830759d47fc729bcd5242abe3de0a41ea4db7dc68fc` |
| pre-review artifact | `docs/reviews/wu-semantic-ownership-01-ar-f07-windows-second-fix-codex.md` | `891a020f02c41e8547ea0a60808a4d6f60a3a9be93b227294755fffd058e8e3d` |
| pre-review artifact | `docs/reviews/wu-semantic-ownership-01-ar-f07-windows-second-fix-controller-validation.md` | `b87eb1f59a7eaf9ce55d74b777dc0f2c2936fb216041cb796409c8ffa5d9c5bf` |

- 七个 product/test/README/workflow path 的排序 manifest digest：`27b2b4c22d9ea415ee7f3c2d83968ce62a96b43a44db5c3468fb5e531fac3e13`。
- 10-path reviewed target 的排序 manifest digest：`c7cd8fe875772d30a35ab01cf16d85d9b2d5ffe0ccf54d1d8578ae8569a75936`。
- 七个 tracked path 相对 immutable baseline 的 canonical binary diff SHA-256：`7058c07324a87b3959420f75c963705125ec50c4b6dad160e2bb466d55381e22`，与 implementation artifact、Controller validation 一致。
- Controller review-entry 锁继续引用 target path digest `2f481388c463bc072f3d3f2c73300fef57a56a9a796fb601290e641dd2f35e01` 与 10-path tracked binary diff `41bf22a19b45894dcfd13a351baed6bf4d934c27375b5c144ba98fbe8ea1fd23`；本 gate 未改其任何输入路径。

## New-tree 验证

所有 Python 命令均在 `source .venv/bin/activate` 后运行。

- focused affected tests：`python -m pytest tests/cli/test_arg_parsing.py tests/cli/test_upload_filings_from_command.py -q` → `87 passed, 2 skipped, 3 warnings in 14.20s`；两项 skip 是既有 Windows-only 节点，三项 warning 是既有 `edgar` deprecation warning。
- full pyright：`python -m pyright dayu/ tests/ utils/` → `0 errors, 0 warnings, 0 informations`。仅工具提示存在新版 pyright，不是类型诊断。
- Controller validation 的 exact coverage（`main.py 94%`、`upload_script.py 92%`、合计 `93%`）、完整 `tests/cli`（`519 passed, 7 skipped`）、changed Ruff 与 R11/R12 YAML parse 结果由相同 10-path hash lock直接复用；本 zero-change gate 没有需要另造验证语义的代码变化。
- `git diff --cached --name-only` 为空；staged tree 为空。
- `git diff --check`：PASS。
- 本 artifact 以 `git diff --no-index --check /dev/null <artifact>` 单独检查：PASS；新增文件预期 diff exit `1` 不代表 whitespace failure。
- 前置与终态 10-path hashes、七文件 binary diff、三份 review/adjudication 输入 hashes 均相同；本 gate 唯一新增路径是本 artifact。

没有代码或测试变化，故没有 README 更新触发；没有修改任何 control 或既有 artifact。

## 真实 Windows rerun residual

当前主机是 Darwin；本 gate 没有执行、模拟或伪造 Windows success。修复后真实 `windows-latest` rerun 仍是唯一 release closure：

1. R11 必须证明 `cmd_ver_exit_code=0`、`cmd_help_exit_code=1`，help probe 后继续执行 pytest；recorder fixed/appended argv exact equality、injection marker absent、real CLI storage 均通过。
2. R12 必须证明 init 9 nodes 通过（普通 symlink 只允许按既有精确 privilege contract skip），尤其 four-state/config reload 与真实 `setx` round-trip 不再出现 charmap error；内嵌 R11 两个 nodes 通过。
3. artifacts 必须继续 names-only / secret-plaintext-zero，只包含获准的 JUnit、脚本/oracle、版本、capability、source hash 与环境变量名，不得包含 secret 或 registry value。

在两条真实 runner evidence 到位前，不得声明 WIN2-F01/F02/F03、AR-F07 或 umbrella closed。该 residual 是必要外部验证，不是 deferred/current code-review finding。

## Next entry point

仅允许 Controller validation 本 zero-change disposition 与终态 hash/stage/diff evidence；之后按 Controller 授权进入 AgentMiMo/AgentDS 完整新树 re-review。不得跳到 stage、commit、push、PR、workflow dispatch、control 更新或 closeout。本 artifact 的最终行数、字节数与 SHA-256 由写入完成后的机械核验产生，不回写正文以避免自引用。
