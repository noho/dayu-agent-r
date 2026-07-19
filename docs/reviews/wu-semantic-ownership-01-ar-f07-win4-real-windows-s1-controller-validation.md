# WU-SEMANTIC-OWNERSHIP-01 AR-F07 WIN4-RW-S1 Controller Validation

## Result

`PASS / LOCAL_IMPLEMENTATION_VALIDATED / READY_FOR_DUAL_COMPLETE_CODE_REVIEW / REAL_WINDOWS_PENDING / COMMIT_NOT_AUTHORIZED`

## Identity and exact scope

- Umbrella：`WU-SEMANTIC-OWNERSHIP-01`；continuation：`AR-F07 WIN4-RW-S1`；不是新 WU。
- Accepted amended-plan commit：`cb2785d9b847e852249d05850c0550c5bcea5467`。
- Clean implementation entry：`8fafe9bad4828c83fa6cf80a1dc2199fe78472d9`。
- Payload path：`tests/cli/test_upload_filings_from_command.py`。
- Payload content SHA-256：
  `71855b783ae1191ed764c69c938f2ca29d0c51ae575f501a431e33615ebb4d3d`。
- AgentCodex artifact：
  `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-s1-implementation-codex.md`，140 lines，SHA-256
  `b12e3489819482b3815bfd6056ce2bbaba66827774405440c42a221b77ca6180`。

Controller完整读取实际diff与implementation artifact。Payload相对entry为44 insertions / 3 deletions，只修改授权测试文件；
另有指定implementation evidence。Staged tree为空。

## Owner and behavior validation

1. 旧`assert "Fins result" in execution.stdout`已删除，新增代码中没有stdout/stderr display文案、prefix、substring、
   regex或parser成功判断。
2. `execution.returncode == 0`与`_assert_single_windows_upload_company_name()`保持。
3. Company facts通过public `FsCompanyMetaRepository(storage).get_company_meta("AAPL")`读取并断言exact ticker与
   `Apple Inc.`。
4. Source facts通过public `FsSourceDocumentRepository(storage)`读取：`SourceKind.FILING` inventory必须只有一个id；
   snapshot使用`with ... read_source_snapshot(..., materialize_files=False) as snapshot`，identity、kind、primary filename与
   descriptors只在块内读取。
5. `source_path`成为本次输入basename的同源值；snapshot primary filename与descriptor name均对齐该basename。
6. 既有`rglob`只在repository facts之后计算physical artifact count；oracle字段集合没有改变且没有新增display字段。
7. Fins production、CLI output、workflow、S2路径、README、control/design零diff。Public repositories能够表达全部facts，
   stop condition未触发。

## Controller fresh validation

所有Python命令均先激活`.venv`：

- Target file：`20 passed, 2 skipped, 3 warnings`。
- Public repository owner nodes：`3 passed, 3 warnings`。
- Full pyright：`0 errors, 0 warnings, 0 informations`。
- Scoped Ruff：`All checks passed!`。
- `git diff --check`：PASS。
- Payload/evidence trailing-whitespace：零命中。
- Staged path：`0`。

AgentCodex另fresh通过POSIX real smoke `1 passed`，并精确比较Ruff 0.15.11 full baseline：entry/final均142项，normalized
SHA-256均为`bcb9e45754ecb183a69859480a286c2c5e3504fb10b1db3958bf44a9deaa2be3`，新增/扩散0。S1没有production
diff，因此production单文件coverage target为N/A；不能借此替代后续S2对`dayu/cli/commands/init.py`的coverage gate。

三个warning均来自已安装`edgar` package deprecated imports，不是本slice新增或扩散。

## README and security/deferred validation

`tests/README.md`职责是测试层级、运行方式与维护规则；S1只替换现有node内部success oracle，没有改变这些读者契约，故
`NO UPDATE REQUIRED`。没有用户可见grammar、工作流、分层、装配或Fins contract变化。

本slice不读取、派生或回显run-specific canary，不读取GitHub Secrets或configured production values；不新增统一
authorization/secret infrastructure，不实施Issue 142、151、175、177、178或Web/WeChat/render。

## Residual and next gate

- 本地macOS真实Windows node按既有marker skip，只是平台事实；fresh R11与R12 embedded-R11仍是后续唯一remote closure。
- Full Ruff 142项是精确未变化的pre-existing baseline，不是current residual。
- 下一gate只允许AgentMiMo/AgentDS并发完整code review实际payload、direct repository contracts、tests与evidence。
- 任何accepted finding必须由AgentCodex全部修复后双路完整re-review。WIN4-RW-S1 commit、WIN4-RW-S2、aggregate、push、
  dispatch与PR review均未授权。
