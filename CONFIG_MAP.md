# jsbench — 完整测试配置图(终版 v4)

生成:2026-07-19 · 仓库:github.com/jaceyang97/jsbench(代码公开;data/runs 本地)
v3:回归文献标准 —— k 次独立采样、无 oracle 反馈、Chen 无偏 pass@k(v2 的反馈重试
经评审否决,保留为默认关闭的实验 flag)。
v4:**全量 144 题 × 3 模型(去 Fable)× k=3,checkpoint 护栏分批推进**(§12)。

---

## 1. 评测目标与主指标(v3:文献标准的独立采样 pass@k)

**问题**:Anthropic 模型(Haiku 4.5 / Sonnet 5 / Opus 4.8;**Fable 5 不参赛**,
理由见 §10)在 Claude Code harness 下解 Jane Street 月度谜题的能力。

**主指标:pass@k,k 次完全独立采样**(HumanEval / Chen et al. 2021 无偏估计器
`1 − C(n−c,k)/C(n,k)`,逐题计算后对题平均)。每次尝试 = 全新容器 + 全新会话,
**无任何 oracle 反馈** —— agent 永远不知道自己对错,判分完全在 agent 世界之外。
"多次尝试补一次做不对"由估计器统计学地处理,而非由反馈循环行为化地处理。

**为何不用"告诉模型错了让它重试"**(v2 方案,已否决):oracle 反馈把测量对象从
"解题能力"变成"对判分器的自适应搜索";小答案空间的题(单字母、二选一)可被垫底
命中;成熟基准(HumanEval、FrontierMath、SWE-bench、ARC-AGI)无一采用 oracle
反馈 —— ARC 的"每题 2 次提交"也是同时提交、之间无反馈。**"迭代改进"的合法形态**
是 FrontierMath 式的 run 内自我验证(agent 用代码检查自己的答案再提交),
TASK_RULES 已明确要求。

| 模型 | model_id | k(独立采样) | 单次预算上限 | max_turns | reliable cutoff |
|---|---|---|---|---|---|
| Haiku 4.5 | claude-haiku-4-5-20251001 | **3** | $0.75 | 30 | 2025-02 |
| Sonnet 5 | claude-sonnet-5 | **3** | $1.50 | 40 | 2026-01 |
| Opus 4.8 | claude-opus-4-8 | **3** | $3.00 | 40 | 2026-01 |
| ~~Fable 5~~ | ~~claude-fable-5~~ | 不参赛 | — | — | 成本+记忆污染,见 §10 |

k 统一 = 3:跨模型 pass@1/pass@2/pass@3 全部可比。

**guessproof 原则**(FrontierMath):答案空间小的题(如单字母、人名二选一)标
`guessable: true`,主表之外单列;大数值答案(13,682,882 类)天然防猜。

报告呈现:pass@k(k=3)± SEM 为主 + pass@1 + 配对差(同题配对 95% CI)+
clustered SE(系列题成簇)+ pre/post-cutoff 分层 + 记忆污染剔除敏感性 +
guessable 单列。辅助:成本、turns、工具调用、pip 安装行为。

*(v2 的同会话反馈重试保留为 `max_attempts>1` 的实验 flag,默认 1=关闭;
若未来想测"反馈增益"作为附加研究臂,改配置即可,但不进主指标。)*

---

## 2. 题库与 Phase 1 题集

- 全档案 **148 题**已抓取(2014-01 至 2026-06),原始 HTML/图片/leaderboard JSON
  快照存 `data/raw/`(带时间戳与 SHA-256,离线可复现)。
- **正式题集 = 全部可用题 144 道**(148 − 4 道无固定答案的开放题,标
  `exclude_

---

## 3. 运行环境(每 run 一个一次性容器)

```
宿主(Windows) ── orchestrator(asyncio,并发 3)
   │  每个 run: docker compose run --rm agent …   ← 全新容器,用后即毁,绝不复用
   ▼
容器(node:20-slim,以 node 用户运行)
   ├─ Claude Code CLI 2.1.215(SDK 0.2.123 wheel 捆绑,版本双锁定)
   ├─ Python3 + 预装:numpy scipy sympy pandas z3-solver ortools networkx pillow matplotlib
   ├─ agent 可自装:pip install 任意 PyPI 包(哲学:给坚实基座,环境由 agent 自行演化)
   └─ 出网:仅经 tinyproxy sidecar(deny-by-default 白名单)
```

**网络:黑名单模型(v2,default-allow + 经验封锁)** —— 按 Jace addendum item 7:
agent 可查数学/编程参考资料,只封锁"解答可能存在的地方"。容器网络为 internal(无外网
网关),tinyproxy 是唯一出口,每条请求都过滤器且**全量记录日志**。

- **放行**(实测 200):维基百科、OEIS、Wolfram MathWorld、Python 文档、arXiv、
  StackOverflow、PyPI、Anthropic API —— 一切未列入黑名单的站点。
- **封锁**(实测 000,`docker/proxy/filter`):
  - 源站:janestreet.com
  - 代码托管(解题仓库 gowen100/miguelbper/iamzr…):github.com、*.github.io、
    githubusercontent、gist、gitlab、bitbucket、codeberg、sourceforge
  - 搜索引擎(发现层,防止用题名搜到解答页):google/bing/duckduckgo/yandex/
    baidu/brave/ecosia/startpage/qwant/kagi/you.com/perplexity/phind
  - 视频/社交/博客写作:youtube、reddit、twitter/x、medium、substack、quora
  - Jane Street 解答专区:puzzling.stackexchange.com
  - 其他 LLM 端点(防外包求解):openai、googleapis、deepseek、mistral
- **WebSearch / WebFetch 工具保持禁用**:这两个是 Anthropic 服务端工具,**绕过容器
  代理**(我的黑名单管不到),所以禁用它们才能让网络层封锁真正有效。agent 通过 Bash
  (curl/python)访问网络 —— 这条路径受代理黑名单治理且全程留痕。
- 直连(绕过代理)无路由。验证脚本 `docker/verify_isolation.sh`:最近一次
  放行 8/8、封锁 12/12、直连拦截、pip 成功,全过。

**残余风险(如实)**:未列入黑名单的某个站点若恰好托管了某题解答(个人博客等),
agent 理论上可达;但无搜索引擎则难以"发现"该 URL。**Jace 明确接受此权衡**
("do your best, I have logs post hoc"),transcript 全量记录每个 Bash 网络访问供事后审计。

---

## 4. 单次采样流程(v3:独立会话,无反馈)

```
1. orchestrator 生成 run_id,启动一次性容器(用后 --rm 销毁)
2. harness 把 data/puzzles/<id>/ 复制进独立 workdir,建空 output/
3. 首条消息 [图片 base64 blocks] + [题面 + TASK_RULES]
   → 图片走模型原生 vision 通道;agent loop(bare 模式)自主工作,
   期间可用代码自我验证(FrontierMath 式),写 output/answer.json 后停止
   工具:Bash, Read, Write, Edit, Glob, Grep;禁用 WebSearch/WebFetch
   上限:max_turns(SDK)+ max_budget_usd + 45min wall-clock
4. 会话结束,容器销毁;场外判分(agent 永远不知道结果);
   同一 (题,模型) 的 k 次采样彼此完全隔离 —— 零信息流动
```

Prompt 全文 `harness/prompts.py`(SYSTEM_APPEND + TASK_RULES),SHA-256 每 run
记录 —— 漂移可检测。

---

## 5. 防泄漏控制(“只给谜题本身,一分不多”)

**Bundle 构成**(agent 可见的全部内容):`problem.md`(原文措辞)+ `images/`
(仅题面页图片)+ `metadata.json`(id/日期/标题/答案格式提示)。逐项控制:

| # | 控制 | 机制 |
|---|---|---|
| 1 | 答案/解析隔离 | grader 存 `data/graders/`,永不进 bundle;solution 页任何内容不参与打包 |
| 2 | 超链接剥离 | 题面中所有 `<a>` 仅保留可见文字,URL 一律不输出(extract 层) |
| 3 | janestreet 令牌清洗 | 投稿邮箱/字面 URL 替换为 `[removed]`(package 层) |
| 4 | 图片来源 | 仅题面页 `<img>`;文件名含 "sol" 的图片直接报错拦截 |
| 5 | 图片 URL 隐藏 | metadata 只含文件名+SHA-256,无 source_url |
| 6 | 答案串扫描 | validate 全 bundle 扫描:答案字符串(≥4 字符)出现即 FAIL;角色名等必然出现的白名单需人工 `answer_in_problem_ok` |
| 7 | 反馈最小化 | 答错只回传"错误"一个 bit + 被拒的值;无"错在哪/正确答案";答对则会话结束 |
| 8 | 环境隔离 | 每 run 全新容器(pip 状态/临时文件不跨 run);bare 模式屏蔽宿主配置 |
| 9 | answer_format 提示 | 只描述格式(如 "integer"),源自题面要求,人工复核过无解析信息 |

**当前状态:144 题(剔除开放题后)全量 validate 通过;已核对答案的题 strict 模式通过。**

**已知残余风险(如实记录,不假装不存在)**:
- **记忆污染**:模型可能记得旧题答案 —— 按 Jace 决定,允许但必须留痕:
  零工具记忆探针(每题×每模型)已建档;Phase 0 已实锤 1 例(fable×knight-moves,
  probe 直接吐出正确答案)+ 1 例疑似(三大模型提交完全相同的 sum-of-squares 最优网格)。
  报告含剔除探针命中的敏感性分析。
- **PyPI 侧信道**:理论上某 PyPI 包可能内含谜题解答(如个人解题合集包)。
  接受为低风险;**每个 pip install 的包名记录在 run.json**,事后可审。
- **Anthropic API 侧信道**:agent 理论上可用容器内 API key 手工调 web_search
  服务端工具。工具层已禁 WebSearch/WebFetch;审计层扫描 tool 输入中的
  `api.anthropic.com`/`web_search` 等模式并打 `suspect_cheating` 标志人工复核。

---

## 6. 日志与可审计性(“事后可被其他 agent 探查”)

**每 run 目录**(`runs/<run_id>/`,永久保留):

| 文件 | 内容 |
|---|---|
| `initial_message.json` | 发给模型的首条消息逐字记录(全部文本块 + 每张图的 media_type/大小/SHA-256/块顺序) |
| `options.json` | 全部生效参数:模型、上限、工具白名单、system prompt 全文、SDK/CLI 版本、非密 env |
| `transcript.jsonl` | SDK 全消息流:每条 assistant 消息、**每次工具调用及其完整输入输出**、思考块、ResultMessage(token/成本/每模型用量明细) |
| `stderr.log` | CLI 进程原始 stderr(错误诊断) |
| `workdir/` | agent 工作目录终态:它写的每个脚本、每个中间文件、output/answer.json |
| `run.json` | 结构化总账(见下) |

**run.json 字段**:run_id/puzzle/arm/model_requested/**model_actual(每模型 token,
Fable 静默转交检测)**/harness 版本/bare_mode/prompt SHA-256×2/时间戳/wall_time/
num_turns/tool_calls/token 四项/cost_usd/exit_reason/image_delivered/
**suspect_cheating + suspect_details(命中样本)**/**pip_installs(包名列表)**/
submitted_answer/correct/grade_method/**grader_snapshot(判分时刻的
answer/type/tolerance/verifier 快照 —— grader 后续被改也能复现当时判分)**。

**全局账本**:`runs/runs.jsonl`(逐行、幂等续跑)、`runs/probes.jsonl`(记忆探针:
模型原话、UNKNOWN 与否、是否命中)、`runs/image_smoke.jsonl`(每图×每模型的描述全文)。

**判分可回溯**(针对“题多了判分 bug 会更多”):grader_snapshot + workdir 保留
= 任何时候可用 `analysis.regrade` 全量重判并列出每个 verdict 翻转(Phase 0 实战
验证过:等号格式 bug 修复后 regrade 翻转 3 个误判,备份原账本)。审计工具:
`analysis.audit_transcripts`(20 秒生成全部 run 的审查表:答案/flags/工具统计/bash 样本)。

---

## 7. 判分体系(确定性为主 + LLM judge 兜底)

1. **确定性归一化链**(`grading/normalize.py`,**主判分**):清洗(空白/千分位/货币/
   引号)→ 整数 → 数值(浮点或 sympy 求值精确式,支持 `sqrt/π/^`)→ 容差比较
   (exact/rel/abs)→ sympy 符号等价 → casefold 字符串 + 别名。
   特殊:`精确式 = 小数` 等号复合取任一侧;multi 型逗号切分逐项(顺序敏感)。
2. **证书验证器**(`grading/verifiers.py`):需要"作品"的题(如 sum-of-squares 的
   (总和,25数字))做可编程验证 —— 格式/自洽/约束/最优性逐项检查,防裸报数字作弊。
3. **LLM judge 兜底**(`grading/llm_judge.py`,**次级、批次后运行**,Jace addendum 2):
   有些答案格式刁钻(自由文本、多种等价写法、怪分隔)。judge 用 opus(关思考、
   结构化输出)判定语义/数学等价,只对"难格式"case 触发(grader 标 `grading_mode:llm`、
   或 answer_type ∈ {string,expression,multi}、或确定性判错但有非空答案=疑似漏判)。
   **判定写入独立字段 `llm_judge_correct`,绝不覆盖确定性主判**;报告两个数并列,
   分歧逐条列出。judge 被要求"不确定就判否、不给部分分",防止分数虚高。
   正确用法:judge 发现确定性漏判 → 人工修 grader(加 alias/容差)→ `analysis.regrade`
   全量重判,而非盲信 LLM。
4. **单元测试**:`grading/test_normalize.py` 22 用例(含对抗性变体),全过。
5. 所有 ground truth 有人工核对记录(review_note)。

**针对"题多了判分 bug 更频繁"**:①judge 兜底自动标出确定性可能漏判的 case;
②每 run 存 grader_snapshot + 完整 workdir → `analysis.regrade` 可在修 grader 后
全量重判并列出每个 verdict 翻转(Phase 0 实战翻正过 3 个);③`analysis.audit_transcripts`
秒级生成全 run 审查表。判分对错永远可追溯、可回放、可复核。

---

## 8. 编排与护栏

- 并发 3(rate-limit 友好);**预算熔断 $190**(累计 cost_usd 实时核算,超线停队);
- 幂等续跑:(题, 模型, sample) 已有终态记录即跳过,中断后重跑同命令续上;
- 重试:仅基础设施错误 ≤2 次;答错永不重试;
- 每 run 三重上限:max_turns(SDK)/ max_budget_usd / 30min wall-clock(harness 内部)。

---

## 9. 执行序列(checkpoint 分批,详见 BENCH_PROGRAM.md)

```bash
# 0) 网络隔离 gate(黑名单模型)
docker compose -f docker/docker-compose.yml up -d proxy
docker compose -f docker/docker-compose.yml run --rm agent bash docker/verify_isolation.sh

# 1) 构建分批计划
python -m orchestrate.checkpoints

# 2) 逐批:发射 → gate 审计 → 通过才发下批(以 cp0 金丝雀为例)
python -m harness.probe          # 记忆探针(当批题 × 3 模型)
python -m harness.image_smoke    # 图片冒烟(当批题 × 3 模型)
python -m orchestrate.runner --plan plans/checkpoints/cp0.json
python -m grading.llm_judge      # 难格式复核
python -m analysis.checkpoint --batch plans/checkpoints/cp0.json --name cp0
#   PASS → cp1;WARN → 处理后继续;HARD-FAIL → 停,修正后重跑受影响子集

# 3) 全部批次完成后
python -m analysis.report
python -m analysis.audit_transcripts
```

---

## 10. 预算与功效(v4 定稿:Jace 已批全量三模型)

**选定配置:全部可用题(144)× 3 模型(Haiku/Sonnet/Opus,去 Fable)× k=3**
= 1,296 个独立采样会话。实测单次均价 haiku $0.30 / sonnet $0.79 / opus $0.55 →
每题 $4.92 → **agentic 总估 ~$699** + 探针/judge ~$10;**熔断线 $780**。

去 Fable 的理由:最贵($0.82/次 × $50/MTok 输出)且探针已实锤记忆污染
(knight-moves 零工具背出答案);三模型对比覆盖了产品上最重要的档位梯度。

**统计功效(P=144)**:配对 MDE **±9pp**(相邻档如 Sonnet vs Opus 的真实差距
大概率可检出);单模型 pass@1 95% CI 半宽 ~±8pp;post-cutoff 子组(~5 题)只做
描述性报告。墙钟:并发 3 约 ~28h,分批跨夜执行,断点可续。
Sonnet 介绍价 2026-08-31 到期,全程在此前完成则按介绍价计费(估算已按介绍价)。

---

## 11-bis. Checkpoint 护栏(v4,autoresearch 式分批推进)

全量跑分不一次性发射,而是 **5 个递增成本批次,批间设自动 gate**
(详细协议在 `BENCH_PROGRAM.md`,那是人类可改的方向盘;此处为摘要):

| 批次 | 题数 | k | 估算 | 定位 |
|---|---|---|---|---|
| cp0 | 3(校准题) | 1 | ~$5 | 基建金丝雀,不计分 |
| cp1 | 12(含校准题) | 3 | ~$59 | 判分校准 + 成本模型验证 |
| cp2 | 25 | 3 | ~$123 | 第一个规模批 |
| cp3 | 45 | 3 | ~$221 | 主体 |
| cp4 | 59 | 3 | ~$290 | 收尾 |

批内按 年代×难度 分层轮发(每批有代表性,外推有效)。每个 gate
(`analysis.checkpoint`)自动审:错误率/超时率/提交率/bare/图片投递/transcript
完整性(HARD 级,命中即停)、judge 分歧队列与判错样本(逐批人工过)、各模型
均价 vs 预测带 [0.4×,2.0×]、累计花费 vs $780 熔断线、作弊标记/pip 清单。
修正规则:grader 层修正 → regrade 重判不重跑;harness 层修正 → 受影响子集标
invalid 重跑。答案核对随批推进(批 N 发射前该批 grader 全 reviewed)。
里程碑 $400/$600 通报 Jace;协议级变更先问后改。

## 11. 已知偏差与诚实声明

- **统计功效**:P=144 → 配对 MDE ≈ ±9pp;报告如实标注 —— 只能可靠区分大于该
  阈值的模型差距,分层子组(如 post-cutoff ~5 题)只做描述性报告。
- **指标语义**:solve@N 是"N 次带反馈尝试内解出",非独立采样,不能与 Chen pass@k
  或 Phase 0 的 v1 数据直接比较;Phase 0 账本已归档隔离。
- **反馈的双刃**:同会话重试让 agent 能纠错(更贴近真实解题),但也意味着一次会话
  的 N 次尝试相关性高,SEM 只来自题间方差(P 题);无跨会话重复的方差缩减。
  若某题预算允许,可跑多个独立会话(replicate)进一步收窄,当前默认每题 1 会话
  以把预算铺给更多题。
- **网络黑名单是经验性的**:未列入的站点若托管解答理论可达(无搜索引擎则难发现);
  Jace 接受此权衡,transcript 全量留痕供事后审计。
- Sonnet 5 介绍价 2026-08-31 到期,在此之前跑完按介绍价计费。
- 探针无法完全证伪"解题中回忆起答案";证书验证器 + LLM judge + transcript 审计
  是多道防线,报告分层呈现记忆污染剔除敏感性。
