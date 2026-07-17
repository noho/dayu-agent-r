# WU-SEMANTIC-OWNERSHIP-01 / R09 aggregate deepreview Controller adjudication

## 1. Gate 与 immutable target

- 当前仍是同一 umbrella `WU-SEMANTIC-OWNERSHIP-01` 的内部 remediation sub-WU R09。
- 本 artifact 裁决最终 dual cumulative aggregate deepreview；不是新 WU、issue 或 feature。
- immutable product/test/README target：12 paths。
- HEAD：`9d36a115400fb59fd95475189810b43a09fda31b`。
- sorted manifest SHA-256：
  `ce024b6df7e319fe38c3a708ec4a2cec9f66b9286c5d41763c73c17cc2fc5cb4`。
- canonical cumulative binary diff SHA-256：
  `60f52a7ebbd1608b11d28dd0206bf4176eac59e5dfc4a03fa87393c9457caf3e`。
- staged tree：empty。

## 2. Reviewer artifacts

| Reviewer | Artifact | Lines | SHA-256 | Final verdict |
|---|---|---:|---|---|
| AgentMiMo | `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-aggregate-deepreview-mimo.md` | 210 | `9f34f1171c7f199ef020a195658ebf2f67c86671b49e6ad0185b799d12bf729e` | PASS / zero accepted or material finding |
| AgentDS | `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-aggregate-deepreview-ds.md` | 415 | `4afafacc82fd4493d00ac80dd0e51e6b86d9486a37b2a44a7b2d1cdcf7b85ebe` | PASS / zero accepted or material finding |

两路 artifact 的最初 evidence transcription 问题已在同一 reviewer task 内更正：最终 12-path list
不含 control doc并包含 `tests/fins/test_fins_direct_stream.py`；该测试文件是 742 lines / 16 test
functions；`direct_events.py` 的一行变更是 `EVENT_AFTER_RESULT` enum member；artifact 不内嵌
自引用 hash。

## 3. Aggregate findings ledger

| Item | Controller disposition | Reason / owner |
|---|---|---|
| `R09-CR-F01..F04` | closed | 第二轮 code re-review 与 aggregate 两路均复核关闭。 |
| F01 self-cause/context follow-up | closed | same-primary cleanup identity 去重，cause/context 无 self-cycle。 |
| `R09-RR-F01` | closed | README 精确列出两个 R09 stable owner。 |
| AgentMiMo initial R1-R4 residual candidates | rejected-with-reason / removed from final artifact | 没有当前失败反例；不得创建 speculative integration WU；dead-thread fallback 已存在；dataclass invariant 无合法绕过路径；异常 identity 判断本来就必须使用 `is`。 |
| AgentDS daemon-thread / 50ms observations | non-actionable existing design observations | 无当前 failing behavior，不是 R09 finding/residual，不建立新 owner。 |
| Issue 175 process isolation | deferred-with-existing-owner | Fins Docling process isolation 继续由 Issue 175 承接；不是 R09 accepted finding，也未在本树实现。 |

Final aggregate ledger：accepted/open finding = 0；rejected-with-reason evidence-invalid candidate = 4；
non-actionable observation = 2；deferred existing owner record = 1；blocker = 0。

## 4. Controller aggregate judgment

1. Fins `ValidatedFinsEventStream` 是 exactly-one-and-last RESULT、missing/duplicate/event-after、
   terminal availability 与 raw-source lifecycle 的唯一 owner。
2. Runtime producer/raw bridge 只产生 raw events；Service 透传同一 stream/error identity；CLI 机械
   消费并承担自己的 consumer close 与 human-readable error projection。
3. primary error identity、cleanup cause、external cancellation、SIGINT、child drain 和 close-at-most-once
   的组合行为有真实 async generator tests。
4. operation provenance 从 runtime 真源传播；Service/CLI 未按入口名反推或重建。
5. Controller locked evidence仍有效：affected `161 passed`，R06 `242 passed`，R08 `180 passed`，
   full Fins `873 passed / 1 existing skip`，五个 changed production files coverage
   `92.21% / 97.78% / 90.44% / 90.16% / 88.56%`，full pyright zero，Ruff/diff/scans、
   retained security 16 cases和三条 fresh real SEC/Docling smokes全部通过。
6. 12 个 product/test/README hashes、manifest与 cumulative diff在 aggregate 后保持无 drift；staged empty。
7. Issue 142、151、175、177、178、Web/WeChat/render trackers、Topic 8/9 与统一 tool authorization
   都没有偷带进入 R09 实现。

## 5. Verdict、risk 与 accepted commit authorization

- verdict：`PASS / ZERO ACCEPTED OR OPEN FINDING`。
- R09 actual accepted residual risk：0。
- existing deferred owner：只有 Issue 175 Fins Docling process isolation 留痕；不改变其状态或 scope。
- R09 implementation/review/aggregate loop 已闭合，可以进入精确范围 accepted local commit。
- commit 必须只包含：
  1. 12 个 immutable product/test/README paths；
  2. 19 个 R09 implementation/code-review/fix/re-review/aggregate evidence 与 Controller artifacts；
  3. 同步后的 `docs/host/issues-implementation-control.md`。
- exact authorized count：32 paths。
- commit 前必须验证 staged count 32、staged name list exact、unstaged/untracked empty、staged
  `git diff --check` pass、cached product/test binary diff仍匹配
  `60f52a7ebbd1608b11d28dd0206bf4176eac59e5dfc4a03fa87393c9457caf3e`。
- commit message：`fins: accept R09 direct stream validator remediation`。
- 该 commit 只接受 R09 implementation，不能关闭 umbrella 或授权 R10；commit 后仍需 R09 completion
  evidence、Controller validation 与独立 completion commit。
