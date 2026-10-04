RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/unknown
CANARY=gpt-6-sol-050009c0

# US1-R03 精确文档契约修复报告

任务 label：`upload-material-unified-s1-doc-closeout-sol-20261002-02`。gate：同一统一修复 WU 的 S1 fix → 等待 root 派发同版精确 delta 双复审；本报告不赋予 gate pass，不表示 S1 或 WU 完成。

runtime/provider 来自本轮 root runner preflight；实际模型标识未暴露，记为 unknown。CANARY 由工具读取本轮指定 canary.txt，并在独占证据 pre-06.stdout 保留原始字节。沿用正文明确允许的独占目录 `workspace/tmp/upload-material-unified-s1-doc-closeout-sol-20261002-02`；“路径仍原正文01”是附注，但正文实际路径为02；未新写任何01目录或旧报告。

## 动机、owner 与真实路径

已读 AGENTS.md、Gateflow SKILL.md、本轮 root task/preflight、binding pending finding 与 root rereview adjudication。US1-R03 的动机成立：`dayu/cli/commands/fins.py:1219–1236` 的 `_single_batch_material_form` 只验证单一非空项，返回未经 strip/upper 的原文；唯一 caller 在同文件342行接收结果、372–378行原样传给 `_upload_batch_regeneration_argv`；该函数508–509行原样写入 `--material-forms`。来源 helper 的返回文档已准确声明原文保留、规范化由身份 owner 完成；本轮 owner 是再生成函数自己的参数文档。旧参数描述误称已规范化，只需纠正文案。唯一 caller 的符号定位及来源片段见 pre-04/pre-05 双流证据。

## 唯一产品 delta

仅 `dayu/cli/commands/fins.py:473` 的 material_form 参数中文 docstring 从“已规范化单一 material form 候选。”改为“保留原文的单一 material form 候选。”。其他 docstring、可执行 AST、tests、README 均未更改。无新增行为、norm/fallback 或 slice；资料报告只记录本次精确 delta。

```diff
--- before/dayu/cli/commands/fins.py
+++ after/dayu/cli/commands/fins.py
@@ -470,7 +470,7 @@
     :param ticker: 已规范化的用户 ticker CSV。
     :param source_dir: 用户 source directory。
     :param explicit_company_name: 用户显式 company name，不含 FMP 推断值。
-    :param material_form: 已规范化单一 material form 候选。
+    :param material_form: 保留原文的单一 material form 候选。
     :returns: 可安全写入注释的 argv。
     :raises Exception: 不主动抛出异常。
     """
```

## 首末精确身份

| 项目 | 首次 | 末次 |
| --- | --- | --- |
| workspace | /Users/leo/workspace/dayu-agent-r | /Users/leo/workspace/dayu-agent-r |
| branch | codex/upload-material-oracle | codex/upload-material-oracle |
| HEAD | 6c49f818efd5a11b4dbd91d9a44f3bcfb2c01e58 | 6c49f818efd5a11b4dbd91d9a44f3bcfb2c01e58 |
| main | fac32ecbff9bfe792b63ee9667c8697826b631f4 | fac32ecbff9bfe792b63ee9667c8697826b631f4 |
| accepted plan SHA256 | c99c35adba919a8baf371b0142e0ab1abf256a951e89b2fc15e8a2d38988e8ea | c99c35adba919a8baf371b0142e0ab1abf256a951e89b2fc15e8a2d38988e8ea |
| allowed source SHA256 | ed5a48d0705396ff11326410d033a709c7695aec5ce041b98947caa515d911ac | 65e3f7166a3f00c40784f6e003d5a6609b8abf944e8b2e4744de54dfc0193c36 |
| root protected manifest SHA256 | 18fe0d0e64f93ee3f6ac2838688e56c93b4be432153c619fdef271497e9ce8e9 | 18fe0d0e64f93ee3f6ac2838688e56c93b4be432153c619fdef271497e9ce8e9 |

plan：`docs/gateflow/upload-material-unified-repair-plan-20261002.md`。root protected manifest：`workspace/tmp/upload-material-unified-repair-20261002/s1-doc-closeout-fix-01/input-sha256.json`。首末均逐项核对其9710件；首次9710件全匹配，末次9709件保持原SHA，唯一允许 source 发生上述单行变化，无 missing / 非授权变化。哈希检查仅针对该清单指明的文件，不遍扫 tmp/venv，不展示私有材料内容。

## 验证与承接

- 原source完整副本 `source-before.py`、newsource完整副本 `source-after.py` 与完整 `fix.diff` 保留；精确替换检查通过。整个模块去除 module/class/function docstring 后 AST 全等；仅 `_upload_batch_regeneration_argv` 一个 docstring 改变。结果与归一 AST SHA 见 `delta-verification.json`；末次重新验证全等。
- 激活 `.venv` 后仅执行一次完整 pyright。actual argv：`["/bin/zsh", "-c", "source .venv/bin/activate && exec pyright"]`；实际 pyright 路径与 argv、cwd、双流文件、实际 exit 见 `pyright.command.json`。stdout 为 `0 errors, 0 warnings, 0 informations`，actual exit=0，stderr=0 bytes。stdout 附 pyright 可用新版本提示，不是类型错误；未安装或更新依赖。
- 本轮不造镜像测试、不跑宽 suite、不写根 coverage/pytest cache。既有2175 passed / 3 skipped、full pyright 0、19 prod ≥80% 仅作为 root 既有同版核收记录承接：依据 `docs/gateflow/upload-material-unified-s1-rereview-root-adjudication-20261002.md`，以及本轮9710件冻结输入首末SHA、唯一 source 去doc AST全等。不是本轮重新运行所得。
- 无用户可见行为/参数/边界变化，不触发 README 内容更新；明确授权亦禁止改 tests/README。

## 证据、命令与失败登记

所有本次证据新写在独占 `workspace/tmp/upload-material-unified-s1-doc-closeout-sol-20261002-02/`：`identity-before.json` / `identity-after.json`、`protected-before.json` / `protected-after.json`、source副本、fix.diff、delta-verification.json、closeout-verification.json。首末 git/source 定位/canary 等命令按 `pre-*` / `post-*` 保留 actual argv、cwd、stdout、stderr、actual exit；pyright resolution 与 full pyright 同样留存双流和命令元数据。探索读取及内联哈希/修改/AST核验的原始工具调用与输出同时保留在本轮 root runner JSONL/stderr，未重写旧 Raw/report。目录 artifact SHA inventory 见 `artifact-sha256.json`，报告SHA另存 `report-sha256.json`。

当前执行未发生失败，所有已捕获命令 exit=0；无恢复或影响项。此前01是 root setup task文件不存在的预检失败，Agent未启动；root已按02恢复，本轮不重试 provider、不删除失败证据、不改旧输入。pyright版本提示按上文登记，未采取环境变更。

## 剩余边界与交接

US1-R03：指定修复已落地，等待 MiMo / ds-flash 对同版精确 delta、真实 caller、AST/identity/protection/pyright 证据独立复审，由 root 裁决；本轮不派发子 Agent。

分类：文档差异已在当前 fix 修复；S2/S3 为后续已批准 slices；Linux/Windows 为用户已延期的平台 WU；全部 slices + aggregate 后 PR review，完整 CLI campaign/registry 在修复 WU 后。未增加新风险；本轮未覆盖后续 slice/平台/最终行为验收，不改变其原owner或排程。未 stage/commit/push/PR、未改 main/branch/worktree、未外发。交付后停止。
