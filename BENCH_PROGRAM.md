# BENCH_PROGRAM — 全量跑分的作战手册(autoresearch 式)

**分工**(仿 karpathy/autoresearch 的 program.md):本文件是人类(Jace)维护的战略层
——协议、阈值、gate 规则在这里,改这里就是改实验;Claude 是战术层——按本文执行、
在每个 checkpoint 自查日志、修正、更新 § 变更日志。

## 实验总纲

- **范围**:全部可用题(~142,剔除 exclude_recommended)× 3 模型
  (Haiku 4.5 / Sonnet 5 / Opus 4.8;Fable 因成本+已实锤记忆污染不参赛)× k=3 独立采样
- **指标**:Chen 无偏 pass@k(k=3),配对差,clustered SE,pre/post-cutoff 分层,
  memorization/guessable 单列
- **预算**:估 ~$700 agentic + ~$10 探针/judge;熔断线 $780
- **每次采样**:全新一次性容器、无 oracle 反馈、bare 模式、黑名单网络

## Checkpoint 结构(递增批次,批间设 gate)

| 批次 | 题数 | k | 估算 | 目的 |
|---|---|---|---|---|
| cp0 | 3(校准题) | 1 | ~$5 | 纯基建 canary,不计分 |
| cp1 | 12(含校准题) | 3 | ~$59 | 判分校准 + 成本模型验证 |
| cp2 | 25 | 3 | ~$123 | 第一个规模批 |
| cp3 | 45 | 3 | ~$221 | 主体 |
| cp4 | 其余(~57) | 3 | ~$280 | 收尾 |

批内按 (era × 难度) 分层轮发 → 每批都有代表性,早期批的成本/解率外推有效。

## 每个 gate 的固定流程(Claude 执行)

1. 批次跑完 → `analysis.checkpoint --batch plans/checkpoints/cpN.json --name cpN`
2. **HARD-FAIL 自动停**(不许发下一批):错误率>5%、提交率<85%、非 bare、
   图片投递失败、transcript 缺失、作弊标记未审、累计花费>95% 熔断线
3. **WARN 需处理后继续**:超时率>10%、判分 judge 分歧未审、成本偏离预测带
   [0.4×, 2.0×]、handoff
4. Claude 亲自审:①全部 graded-wrong-with-answer 抽样看 transcript(eq-side bug 类);
   ②跑 `grading.llm_judge` 处理难格式;③judge 分歧逐条裁决 → 改 grader → 
   `analysis.regrade`;④pip 安装清单、suspect 明细
5. 修正规则:**judge/grader 修正 → regrade 全量重判,无需重跑**;
   **harness/环境级修正 → 受影响 runs 标 invalid 并重跑该子集**(记录在变更日志)
6. gate 结论写入 `runs/checkpoints/cpN_report.md` + 本文件变更日志,然后才发下一批

## 答案核对流水(批前置)

批 N 发射前,批内所有 grader 必须 needs_review=false:Claude 对照官方 solution
批量核对(抽取加粗答案 → 写 grader + public_answer_format)→ review_sheet 供 Jace
抽查。cp1 全部是已核对题;cp2-4 的核对随批推进,不必一次做完。

## 何时打断 Jace

- 任何 HARD-FAIL 无法用"修 grader + regrade"解决时
- 累计花费到 $400、$600 时(里程碑通报)
- 变更协议级内容(prompt 文本、模型参数、网络名单)之前

## 变更日志(Claude 追加)

- 2026-07-19 v3 定稿:独立采样 k=3、3 模型、checkpoint 护栏建立。
- 2026-07-19 cp0 canary PASS:9/9 runs,错误率/超时率 0%,提交率 100%,bare/容器/
  图片/transcript 全绿,累计 $2.93。1 个"提交但判错"(hooks-2×haiku 12700800 vs
  17418240)经人工核对为真实答错(非判分漏判)。成本均价低于预测带下限(haiku
  $0.15/opus $0.27/sonnet $0.56 vs 预测 0.30/0.55/0.79)—— 单次采样比会话重试便宜,
  全量估算 ~$699 偏保守,实际可能更低。基建可信,放行 cp1。
