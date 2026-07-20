# WU-SEMANTIC-OWNERSHIP-01 / R02 aggregate deepreview fix Controller validation

## 1. 结论

- gate：既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` / R02 aggregate deepreview finding fix；不是新 WU。
- AgentCodex 首轮 artifact：`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-deepreview-fix-codex.md`。
- Controller verdict：`REQUIRES_FIX`。
- `R02-AGG-DS-F02..F05` 的 direct owner test closure 通过；`R02-AGG-DS-F01` 的 create/reuse/re-key/global-publication tests通过，但异常 cleanup contract 未闭合。
- 新 accepted finding：`R02-AGG-CTRL-F01`。它是原 F01 明确要求的异常清理遗漏，不是 Issue 178 storage-state lifecycle，也不扩大为统一 authorization 或新的 browser lifecycle framework。

## 2. 直接代码证据与 owner 裁决

`dayu.tools.web.web_playwright_backend._get_playwright_browser` 是 browser singleton/runtime lifecycle owner。当前实现先执行：

1. `pw = sync_playwright().start()`；
2. `browser = pw.chromium.launch(...)`；
3. launch 成功后才将 `pw/browser/key` 发布到模块全局；
4. 任一异常只记录 warning 并返回 `None`。

因此，当步骤1成功而步骤2失败时，局部 `pw` 没有进入全局状态，`_close_playwright_browser()` 无法回收它，异常分支也没有直接调用 `pw.stop()`。结果是“未发布半状态”成立，但“初始化异常正确清理”不成立。原 DS finding 明确要求异常时正确清理，Controller adjudication也要求失败后状态；AgentCodex 的失败测试只断言三个global为 `None`，未断言已启动 runtime 被停止。

正确 owner仍是 `_get_playwright_browser`。修复必须保留成功前不发布半状态，并在 launch失败时 best-effort停止本次局部 runtime；不得把 cleanup 下沉到 caller、adapter、smoke或 fake，也不得引入 Issue 178 storage-state lifecycle。

## 3. 已通过的独立验证

所有 Python 命令均在 `source .venv/bin/activate` 后执行：

- 11个 qualified direct-owner tests，参数化后 `20 passed`；
- aggregate matrix：`329 passed, 1 skipped, 3 warnings`；唯一skip仍是既有opt-in live cleanup test，warnings仍来自`edgar`依赖弃用提示；
- full pyright：`0 errors, 0 warnings, 0 informations`；
- coverage JSON：`workspace/tmp/coverage-r02-controller-deepreview-fix.json`；
- `dayu/tools/web/web_tools.py`：`575/712`，`80.75842696629213%`；
- `dayu/tools/web/web_playwright_backend.py`：`479/533`，`89.8686679174484%`；
- `git diff --check`：PASS；
- `git diff --exit-code -- dayu utils README.md dayu/config tests/README.md`：首轮 test-only patch下PASS；
- changed-definition中文docstring audit：`59` definitions，`0` issues；
- independent real smoke：`workspace/tmp/r02-web-owner-policy-aggregate-fix-controller`，`11` local passed、`0` failures、`0` skips；requests与Playwright filing均完整读取`1,503,780` bytes，diagnostics schema=`web-diagnostics-v2` revision=`2`。

这些结果证明新增 tests没有破坏既有行为，但不能覆盖上述局部 runtime leak，所以不构成 PASS。

## 4. Fix 要求

AgentCodex 在同一 fix task内完成：

1. 仅在 `dayu/tools/web/web_playwright_backend.py` 的 lifecycle owner及 `tests/tools/web/test_web_tools_provider.py` direct owner test边界修复；
2. launch失败时，对已经成功启动但尚未发布的 runtime执行best-effort `stop()`；
3. 不得为 cleanup而提前发布 `_PW_INSTANCE`，不得新增下游 fallback或兼容分支；
4. direct failure test必须断言 `stop_calls == 1`、三个global均为 `None`；另覆盖 `stop()` 自身异常不会遮蔽原有返回 `None` contract；
5. 按 README触发规则检查 `dayu/tools/web/README.md`（若不存在则检查`dayu/tools/README.md`/相关职责）和`tests/README.md`，只在职责命中时更新；
6. 重跑focused owner tests、完整provider/aggregate、逐文件coverage、full pyright、`git diff --check`、docstring/source/allowed-path scans和独立real Playwright smoke。

下一入口仅为 AgentCodex 同一任务 follow-up。未完成 Controller re-validation和MiMo/DS双路完整aggregate re-review前，不得接受R02、commit、创建completion或进入R03。
