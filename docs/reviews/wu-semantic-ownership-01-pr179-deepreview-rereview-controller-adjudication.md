# WU-SEMANTIC-OWNERSHIP-01 PR179 deepreview re-review Controller adjudication

## Evidence lock

- PR：draft PR 179，base `main`，committed reviewed HEAD `86174133b51f2e34cac5d93c4128d9b40a8c48b8`，叠加当前未提交 fix/review delta。
- AgentMiMo re-review：`docs/reviews/wu-semantic-ownership-01-pr179-deepreview-rereview-mimo.md`，187 lines，SHA-256 `4231e65427f3643954253205287574764ec00e76252be0dcd9fbad49fac2ca27`。
- AgentDS re-review：`docs/reviews/wu-semantic-ownership-01-pr179-deepreview-rereview-ds.md`，254 lines，SHA-256 `c11cac6f4f8e139c35f300f6c53e34f1a31f3492d4884d332c334d46204d648c`。
- Production/test fix binary diff SHA-256：`810bfb9cc01728cc98725177b613b29cc6483be22f5d833a1fcbf627d8aab6ba`。
- Production/test final file SHA-256：`f376dfe547f5f72c314fe018b28f49b5bdf504476b72484602eed3ba04ec28ea` / `d73a69e900baaf619004c061f18c62288783026ea8258fb699ab9370cc80c8b3`。
- 两路 reviewer 均独立复跑 focused `6 passed`、ToolRuntime owner aggregate `179 passed`、accepted-result/Phase6 projection `37 passed` 与 pyright，并逐个核对 9 个 production call sites。

## Finding adjudication

### PR179-DR-F01 — ACCEPTED FIX / CLOSED

Controller 接受两路 re-review 的一致结论：

1. `_TOOL_RUNTIME_GOVERNED_ERROR` 及其内部码 fallback 已从 production 删除。
2. Malformed non-`ALLOW` decision 的 `None`、空字符串、纯空白 message 在 `ToolFailedOutcome` 产生前 fail closed；同一 invariant 也保护 accept/audit 构造边界。
3. `ALLOW` 与 `REUSE` 不得误入 governed-failure projection；`REUSE` 继续由独立成功路径拥有。
4. `HINT`、`REQUIRE_JUSTIFICATION`、`HARD_STOP`、`GOVERNED_ERROR` 等合法 governed failure 使用各自非空业务 message，原行为不变。
5. Reason code 继续作为 Host internal governance/digest/audit/diagnostic 事实，不充当 LLM-readable message。
6. Tool Trace、accepted-result projection、Memory、RunInput、Compact、renderer、prompt/schema 均未增加下游 fallback、normalization、blacklist 或 compatibility shim。

`PR179-DR-F01` 由此从 root cause 关闭。

### Other findings

- New finding：0。
- Backflow：0。
- Blocker：0。
- Open：0。
- Unclassified：0。
- Pending：0。
- 初轮 DS 001/002/017/019 保持 rejected-with-reason / closed；003-015、018 保持 nonfinding / closed。
- MiMo 初轮与 re-review 均为 0 material finding。

## Aggregate design and safety adjudication

- Controller discussion Topic 1-7 均 closed；本 fix 没有回归 Doc、Web、Host LLM-safe projection、OpaqueEvidenceRef、wait poller、Fins 或 CLI/init/upload 语义。
- Topic 8 和 Topic 9 是 no-code decisions；统一 tool authorization framework 未实施，也未被列为当前 deferred implementation。
- Config 与 Host internal SQLite/EventLog 是 trusted-local domain，API key/headers 可存在；Tool Trace、audit、public/log/LLM/review evidence 的 credential/header plaintext prohibition 保持。
- Web private/custom port 默认 allow、DNS/peer/resource budgets、allowed paths、filesystem containment、symlink/no-follow、atomic write、process fencing 均保持。
- Issue 142、151、175、177、178 与既有 Web/WeChat/render trackers 保持原 owner；没有偷带 deferred capability。
- R01-R12、explicit fresh Windows evidence与当前 PR-head R11/R12 checks均保持 closed/pass。
- Gemini test-account quota 保持 `EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING`。

## Gate result

- Verdict：PASS。
- Accepted/open finding：0。
- Remaining remediation sub-WU：0。
- Correct next gate：Controller 形成 exact accepted PR review commit，non-force push 当前 branch；随后产出 final closeout artifact、更新 control doc、形成 accepted closeout commit 并 push。
- 本 artifact 不授权 merge、mark-ready、delete branch、关闭 deferred issues 或创建替代 WU。
