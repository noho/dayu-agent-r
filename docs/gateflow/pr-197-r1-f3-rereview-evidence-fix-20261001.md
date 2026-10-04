RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/unknown
CANARY=gpt-6-sol-19c3a1ff

# PR197 F3-RR-PV01 窄取证修复候选报告

label：`pr197-f3-rereview-evidence-fix-sol-20261001-01`。runtime/provider 按本轮任务路由声明；当前上下文没有可核实际模型标识，故 model 为 unknown，不能从 canary 或 provider 推断实际 model。本轮实际读取指定 canary，独立原始输出保存在下述证据目录的 `canary-read.stdout`（无尾换行）、`canary-read.stderr`、`canary-read.exit.txt`（0）。design_doc=N/A。

状态：PV01 修复候选已完成，等待 root 独立核收；不自行裁定 accepted，不构成产品修复或 F3 code gate pass。F3 整体仍需另一路审查与总控综合裁决；未操作 F3 MiMo7898/F6 MiMo37469。

## 边界与直接根因

唯一 checkout 为 `/Users/leo/workspace/dayu-agent-r`。首轮 branch=`codex/upload-material-oracle`，HEAD=`123fad5dc992c0f87c6d6c7aecad1ab14c6e8e98`，main=`fac32ecbff9bfe792b63ee9667c8697826b631f4`。末次观察 HEAD=`a32ff820623cf16ef631b16db62e61b9f443ed91`，branch/main 不变。`checkpoint-delta.*` 实证期间两个新 checkpoint（`8dcc85be…`、`a32ff820…`）仅变更九个 docs 路径，`dayu/utils/tests/pyrightconfig.json/pyproject.toml` 提交差异为空；这属于允许的总控文档 checkpoint 变化。工作树既有变更不由本轮修改。

已读 AGENTS、sub-agents/gateflow 技能、root 当前裁决和原 DS 脚本。root 将 F3-RR-PV01 裁为低、accepted、未修，owner 为临时 `verify_freeze_hashes.py` 的 JSON 出口。直接代码证据是原件第 62 行 `raw: dict[str, object] = json.load(handle)`；不是产品业务语义或下游消费者问题。原件独立 strict pyright 实际分析 1 file，发现 key/value/item 的四个 unknown 类型错误，exit 1，证据保全。当前批准的直接 owner 修复成立，无需扩大产品 WU。

仅写 label 独占 tmp 与本新报告。原 DS 整个 tmp、旧报告、freeze 与 originals 均只读。未修改产品/utils/tests/README/plan/goal/root queue/handoff/registry/既有配置或依赖；未 stage/commit/push/PR/merge/branch/worktree、派发 Agent、调用网络、真实 PDF/OCR 或私人语料；未重跑 CLI 矩阵、pytest、coverage 或旧完整 type。新增 tmp 内 pyright 配置只是本次显式取证配置。README 职责未触发。

## 精确变更与摘要身份

下文证据目录统一为 `workspace/tmp/pr197-f3-rereview-evidence-fix-sol-20261001-01/`，所有相对 artifact 路径均相对唯一 checkout。

1. 原 DS 脚本复制为本目录 `verify_freeze_hashes.py`。`copy-before.*` 记录实际 cp、SHA 与 cmp，exit 0；修改前 SHA=`99e636298dbe61cb6858e466cbfd88717303bcda772c89978ed2f4c70075f964`，与原件一致。
2. 修复使用公共 `dayu.contracts.json_value.JsonValue` 标注 JSON 读取出口，先断言顶层 dict、逐键验证，形成 `dict[str, JsonValue]`；保留原 files/readonly/source_scope/originals 形状断言及逐字段、逐元素验证。仅将 evidence_dir 指向本目录，补 main 中文参数/返回/异常说明。
3. 待核 freeze 路径、989 current/originals 目标、字段、数据、原有断言、SHA-256 算法、排序、缺失检测、结果格式、退出判据均未改变。没有 ignore/cast/type suppress/Any/object/弱签名或 fallback。

修复后 copy SHA=`509bb4e5248db46cdf2e4cd6b982709e783406ae74c09ef561059701b5d6ed71`；原件仍为上述 before SHA。精确 unified diff=`copy-diff.stdout`，SHA=`81d22dab8537fd4e39e3b828607a10039badb5f4d7890da3e04e10209eee80ce`，diff 真实 exit 1（有差异的正常返回），独立 stderr 为空。其全部有效变化如下：

```diff
+from dayu.contracts.json_value import JsonValue
+    :param: 无参数；读取脚本内固定的冻结清单路径。
+    :raises AssertionError: JSON 顶层或逐字段类型不符合预期。
+    :raises KeyError: freeze 缺少本脚本消费的必填字段。
-    evidence_dir = repo_root / "workspace/tmp/pr197-f3-input-loop-rereview-dsflash-20261001-01"
+    evidence_dir = repo_root / "workspace/tmp/pr197-f3-rereview-evidence-fix-sol-20261001-01"
-        raw: dict[str, object] = json.load(handle)
+        raw_json: JsonValue = json.load(handle)
+    assert isinstance(raw_json, dict)
+    raw: dict[str, JsonValue] = {}
+    for key, value in raw_json.items():
+        assert isinstance(key, str)
+        raw[key] = value
```

上面仅摘要有效行；`copy-diff.stdout` 包含原始行号、时间与空行变更，为精确 diff 真源。辅助验证源码 `validate_evidence.py` SHA=`a8d2f1ddd04315f49d2c9a4060e29eb9ced06e0f04029355051009e4db5fbc8e`，只核本轮 11+11 与 DS 原目录保全；中文函数 docstring 含参数、返回、异常，实际执行且纳入同次 strict type。

## 冻结首末与原件保全

本轮 freeze SHA 首末均为 `bb34ff4dd942d75729e9fd873b215d3579983f3dfc0fbc9de46f11f161d63b1f`。`freeze-before.stdout` 与 `freeze-after.stdout` 为有效 JSON，均逐件保存 11 条 path/expected/current/original：22 个实算 SHA 各自匹配，首末相等；`all_expected_match=true`、`before_after_preserved=true`，两次实际 exit 0。`verify-preservation.*` 用 jq 对数量及每条 SHA 再作实际断言，exit 0。

候选报告落盘后另执行 `freeze-final.*` 末核，同一已通过 strict type 的验证源码再实算 11+11、566 原 DS 文件，全部匹配首轮、exit 0；`report-final-check.*` 的完整 JSON 断言与本轮 canary 逐字比对也为 exit 0。末次 Git 状态另出现四个 `dayu/fins/` 非本轮范围文件及非冻结 root 文档的并发 working-tree 变更；本轮未写这些路径，也不推断其作者或业务状态。`concurrent-scope-check.*` 实查四个 fins 路径均不在待核 989 files 映射中（输出空映射、exit 0），十一项冻结与原 DS 目录保持不变。

十一项为 AGENTS、root F3 当前裁决、原 DS 正式报告、原 DS 脚本、989 清单、公共 JsonValue 和五 utils 源码。完整 SHA 在两个逐件 JSON 中，不以计数或作者自报代替实算。原 DS 报告 `docs/reviews/code-review-20261001-125714.md` 首末 SHA=`59daa878b9c9ba4b2be61592d64c5f5920909ea6b7a655df13be2011695a51a0`。原 DS 脚本首末 SHA=`99e636298dbe61cb6858e466cbfd88717303bcda772c89978ed2f4c70075f964`。原 DS 整个 tmp 下实际 566 个文件的相对路径及逐件 SHA 首末相同，包含历史失败夹具、双流、退出与旧结果；没有写入或覆盖原目录。

## 本轮实际命令与结果

`run_command.sh` 将每步完整命令写入 `<step>.command.txt`，命令 stdout/stderr 分别落盘，真实命令退出写 `<step>.exit.txt`，wrapper 返回同一个码。执行 shell 为 zsh -e，命令失败不会被后续成功或 wrapper 0 掩盖；不会覆盖已存在的同名证据。准备阶段首个 preflight 版本尚未加 -e，但其实际各项均成功；所有关键 checker/type/首末核验均在加 -e 后独立执行。

环境实证：`preflight.stdout` 中 pwd 为唯一 checkout；激活 `.venv` 后 Python=`/Users/leo/workspace/dayu-agent-r/.venv/bin/python`，版本 `3.11.15`，pyright=`/Users/leo/workspace/dayu-agent-r/.venv/bin/pyright`，pyright JSON version=`1.1.409`。Python 命令显式 `PYTHONPATH=/Users/leo/workspace/dayu-agent-r`，type 命令显式 `--pythonpath /Users/leo/workspace/dayu-agent-r/.venv/bin/python`；配置 pythonVersion=3.11、venvPath=唯一 checkout、venv=.venv，extraPaths 也只指唯一 checkout。

| step | 实际命令主体（完整含激活见 command.txt） | 结果 | 真实 exit |
| --- | --- | --- | --- |
| freeze-before | `python validate_evidence.py before` | 11 current + 11 originals 匹配；566 原 DS 文件 SHA 快照 | 0 |
| copy-before | `cp`、`shasum -a 256`、`cmp` | copy before 与原件逐字一致 | 0 |
| copy-after | 两件 `shasum -a 256` | copy after/原件 SHA 如上 | 0 |
| copy-diff | `diff -u` 原件与复制件 | 精确窄变更 | 1 |
| type-original | `pyright --project …/pyright-original.json --pythonpath …/.venv/bin/python --outputjson` | filesAnalyzed=1，errors=4，warnings=0，information=0 | 1 |
| type-new-01 | `pyright --project …/pyright-new.json --pythonpath …/.venv/bin/python --outputjson` | filesAnalyzed=2，errors=0，warnings=0，information=0 | 0 |
| checker-new | `python verify_freeze_hashes.py`（本 label copy） | **989 current + 989 originals = 1978 次逐件身份比较**，两侧 mismatch=0 | 0 |
| verify-results | jq 与真实 exit 文件断言 | checker JSON、type 非空分析与原件失败退出全部符合 | 0 |
| banned-source-scan | 原件 object 匹配；新两源码禁用项搜索 | 原件仍保留弱类型，新源码无禁用项 | 0 |
| freeze-after | `python -B validate_evidence.py after` | 11+11 再实算全匹配，566 DS 原件首末未变 | 0 |
| verify-preservation | jq 首末逐件 SHA/数量断言 | 两份快照均通过 | 0 |

关键命令 `checker-new/type-new-01/type-original` 独立 stderr 均为 0 字节；JSON 在 stdout 内，并有真实非空内容，不以空 stderr 判断成功。`checker-new.stdout` 保留实际输出（汇总 JSON 加 source_scope 行）；结果 `freeze-hash-check.json` SHA=`1636e31e58a9943ab955b019c2a6739e4aaada41ca103f80089487fa7d62e0b0`，files_count=989、readonly_count=989、current_mismatch_count=0、original_mismatch_count=0、scope_missing_from_files=[]、readonly_not_in_files=[]，五 source_scope 的当前 SHA 匹配且 readonly=true。数量是 **989+989**，不是 198 项。

`pyright-new.json` 显式相对 include 为 `["verify_freeze_hashes.py", "validate_evidence.py"]`，exclude=[]，strict；两个文件都被实际分析。`pyright-original.json` 显式相对 include 为 `["../pr197-f3-input-loop-rereview-dsflash-20261001-01/verify_freeze_hashes.py"]`，exclude=[]，strict；只有原件作为对照。没有使用项目默认排除 workspace 的配置作为这两源码的 type 成功证据，filesAnalyzed=0 不算通过。

## 失败、恢复与证据可见性

- 本轮原件 strict type 真实 exit 1、四个 unknown 错误：保在 `type-original.stdout/stderr/exit.txt`，是新独立失败证据，未修改原失败或原脚本。修复 copy 后 strict type 为 2 files/0 errors/exit 0；原 DS 报告从未执行或宣称执行本轮新检查。
- `copy-diff` exit 1 是预期“文件不同”返回，保原双流/退出，无需恢复。
- 最初探索性 `ls` 新报告返回 1（不存在），仅用于确认未存在；后来 `final-git-state` 和写前 `report-absence` 以 `test ! -e` 独立保存 exit 0 后才创建报告。最初读文件/Git 状态的工具输出只有托管合并展示，未伪称当时已保存独立双流；关键身份、执行、type、canary 与缺失确认均有本目录新独立双流/exit。
- 原 root type 证据只读核查：绝对 include 0 files/0 errors/exit 0 已被 root 拒作通过；随后相对 include 7 files/3 missing-import errors/exit 1；补实际搜索路径后 7 files/0 errors/exit 0。原文件未动，本轮读取留 `root-type-failure-preserved.*`，不将其并作本轮新脚本检查。
- 旧 DS 报告记录的过严负例断言、误判缓存 worker 正例、转换调用计数错误、夹具不可幂等、瞬态路径读取失败与 OMP 告警均属旧轮次证据，本轮只保全原目录并读取报告摘录（`old-report-context.*`），未重新执行、恢复或泛化为“旧报告所有中间执行成功”。
- 本轮 checker 和新 type 无缺依赖、取证运行失败、provider switch 或重试；无未恢复关键工具失败。工具展示对大首末 JSON 有截断，磁盘 stdout 未截断，后续 jq 实际读取完整文件断言。

## 残余与交接

PV01 的 owner 出口修复与非空 strict type：本轮已修复候选，交 root 核收。原弱类型及原失败完整保留是授权保全要求。实际 model 不可核为证据限制，交 root 从本轮 runner/event 元数据核验，不能据 canary 推断。

F3 整体代码裁决、另一路审查、后续真实 CLI CI/registry 与其它产品 WU 属既有 root 队列；本轮不推进、不宣称完成，不改变其冻结输入或 owner。无新增业务语义、未分类产品风险或新产品修复。下一入口仅为 root 独立核收本候选报告及原始证据；本执行者完成后停止。
