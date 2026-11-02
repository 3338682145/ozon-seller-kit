# 17 — Keyword Clustering V2 离线实验与验收方案

版本：v2-experiment-plan-1.0  
基准快照：P8 snapshot_date=2026-10-30  
对象：1,642个关键词，每词最多108个P8 SKU  
状态：实验计划；V1不覆盖

## 0. 已确认并冻结的决策
1. 40%规则A：共有SKU数 ÷ 两个SKU集合中较小集合的SKU数，即Overlap Coefficient。
2. 聚类目标：相同搜索意图、相同需求市场，不是精准同款产品族。
3. 每个关键词最多一个Primary Cluster；允许多个Secondary Cluster，仅作导航/相关需求关联，不参与市场规模加总。
4. V1现有165簇永久保留为baseline；V2独立生成版本。
5. V2簇数量不强制等于165。簇数量是实验结果，不是验收目标。
6. L2a精准同款/跟卖关系独立建设，不由本实验推断。

## 1. 实验目标
- 验证40% Overlap是否适合候选召回。
- 验证Jaccard、Top30、排名权重和SKU流行度惩罚能否减少宽泛词误合并。
- 防止A-B、B-C相似但A-C不相似造成链式合并。
- 对比V1/V2的需求纯度、簇内形态混杂、未归类词和市场排名变化。
- 建立可复现、可回滚、可解释的Primary/Secondary关系。

## 2. 输入与冻结条件
使用：
- keyword_sku：keyword、sku、position、seller_id、price、name、snapshot_date。
- fact_keyword_sku：keyword、sku、cluster_id、rank、match_score、esi。
- query_metrics_v2：top_category3、homogeneity、coverage、search_volume等，仅用于聚类后画像/约束。
- dim_cluster：V1 cluster_id及成员关键词。

冻结条件：
- 只用同一P8快照，当前基准2026-10-30。
- 仅保留position 1–108；每个关键词内部按SKU去重。
- 结果不足108时用实际集合，不补齐；集合少于20个SKU时不自动合并，只进人工复核。
- 不用P6销量、P7搜索人数决定两个词是否同簇，避免市场大小影响需求意图定义。
- seller_id用于卖家结构分析，不作为关键词相似度的主要定义。
- 无有效P8结果的词保留异常/未分配状态，不强制入簇。

## 3. V2相似度特征
令关键词a、b的去重SKU集合为A、B，A30/B30为position<=30的SKU集合。

### 3.1 Overlap Coefficient（40%规则）
O(a,b)=|A∩B|/min(|A|,|B|)。
O>=0.40只进入候选比较，不代表最终合并。

### 3.2 Jaccard
J(a,b)=|A∩B|/|A∪B|，衡量整体集合相似度，降低小集合被大集合包含时的误判。

### 3.3 Top30 Overlap
T(a,b)=|A30∩B30|/min(|A30|,|B30|)。
若任一Top30有效SKU少于10，不自动判定。

### 3.4 排名加权Jaccard
单词内SKU权重：w(s,k)=1/log2(1+position(s,k))。
W(a,b)=Σmin(w(s,a),w(s,b))/Σmax(w(s,a),w(s,b))。
越靠前的共同SKU贡献越大。

### 3.5 SKU流行度惩罚
df(s)=包含SKU s 的关键词数；N=关键词总数。
idf(s)=log((N+1)/(df(s)+1))+1。
计算IDF加权Jaccard，降低跨大量关键词出现的通用热门SKU对相似度的抬高。普通Jaccard与IDF-Jaccard都要输出，不由IDF单项决定聚类。

### 3.6 语义和类目约束
- 规范化大小写、ё/е、空格、标点、词形、单复数、常见拼写变体；保留原始query。
- 使用top_category3、homogeneity和俄语语义相似度作辅助证据。
- 产品形态冲突词（如 шар、кубик、пистолет、клавиатура、набор）标记hard-negative或人工复核。
- 宽泛词（如 игрушка、антистресс）标记为generic，不得仅因热门SKU重合并入窄长尾簇。
- 语义模型用于候选排序和人工辅助，不覆盖P8集合证据。

## 4. 综合分与阈值校准
实验初始综合分：
S=0.20O+0.25J+0.20T+0.20W+0.15IDF_Jaccard。

阈值不预先固定。用标注集对S>=0.50、0.55、0.60、0.65、0.70逐一回测，选择满足Precision门槛时Recall最高的阈值。40% O只是候选生成条件；最终Primary合并必须满足综合分和簇凝聚度条件。任何hard-negative冲突禁止自动合并。

## 5. 聚类算法对照
必须比较：
A. V1现有165簇baseline。
B. Threshold + Connected Components，仅作链式合并反例，不作为生产候选。
C. Average Linkage。
D. Complete Linkage。
E. Medoid-constrained clustering（推荐候选）：新词与簇中心相似度达标，且与簇内平均相似度达标后才加入。

防链式合并规则：
- 与Medoid分数必须达到校准阈值。
- 与簇成员平均相似度必须达标。
- 成员数>=5的簇，簇内P10相似度不得低于校准下限。
- 有形态/类目hard-negative冲突时禁止同簇。
- 不允许仅凭A-B、B-C高分就把A/B/C全部合并。

## 6. Primary / Secondary归属
- 每个关键词最多一个Primary Cluster。
- Primary按最高合格簇分数分配；前两名分差小于校准margin时标记ambiguous并人工复核。
- Secondary最多3个，达到单独校准的关联阈值；仅作导航和关联分析，不参与簇销量、GMV、CR4加总。
- 无合格候选的词进入unassigned，不为追求簇数量而强制归类。
- 每条关系保存relation_type、score、method_version、evidence、review_status。

## 7. 人工标注集
首轮建议300对关键词，分层抽样：
- 60对：高Overlap、高综合分。
- 60对：Overlap在40%–55%的阈值边界。
- 50对：高Overlap但Jaccard低，疑似宽泛词枢纽。
- 50对：形态词冲突或跨三级类目。
- 40对：中低相似度但可能同义/词形变体。
- 40对：低相似度随机负样本。

标签：
1. SAME_INTENT：应进入同一个Primary需求簇。
2. RELATED_INTENT：相关但应分属不同Primary簇，可作Secondary。
3. DIFFERENT_INTENT：不应关联。

建议两名标注者独立标注，冲突仲裁；Cohen's Kappa目标>=0.75。若单人标注，至少间隔一周盲标复核10%样本。

## 8. 评价指标与验收门槛
Pair-level：
- Primary merge Precision >=95%（硬门槛）。
- Recall目标>=75%；不能以降低Precision换取Recall。
- F1建议>=0.84。
- RELATED_INTENT被错误并入Primary的比例单独报告。

Cluster-level：
- B-cubed Precision >=0.95。
- 抽检簇内SAME_INTENT纯度>=95%。
- 大簇检查Medoid、边界成员和低分位相似对。
- 不允许明显不同产品形态/类目被自动混为同一窄需求簇。

Market-impact：
- 比较V1/V2簇数量、簇大小、关键词数、SKU数、P6匹配率、跨簇SKU、Primary/Secondary数量和unassigned比例。
- 比较Top20簇成员变化、Gross/Net规模排名和CR4变化。
- 簇市场规模只用Primary归属关键词下SKU并集；Secondary不参与加总。
- 跨簇全市场总量仍需SKU全局去重。

发布门槛：
- Holdout集Precision>=95%。
- Kappa>=0.75。
- 无未解决的严重跨形态误合并。
- 有可复现脚本、参数、manifest、结果表和错误案例清单。
- 未达标则V2保持实验态，不覆盖V1。

## 9. 数据质量与偏差检查
1. P8仅前108位，簇指标标注为可观测搜索货架市场。
2. 热门SKU跨大量关键词出现会制造虚假重合，报告hub SKU和IDF影响。
3. 结果少于108时用实际集合；少于20不自动合并。
4. position必须来自同一快照。
5. 一个SKU跨多个Primary需求簇可能合理；跨簇总盘必须全局去重。
6. P6 join失败和redemption缺失分别报告，不当作0。
7. 品牌/IP词与通用词分开处理。
8. 若P8包含推广位，做含推广/去推广敏感性对照。

## 10. 实验阶段与交付
E0 Freeze：冻结V1、P8快照、source SHA、字段映射和规则版本。
E1 Candidate：生成1,642词的SKU集合及候选关键词对，计算O/J/T/W/IDF-Jaccard。
E2 Label：抽样300对，双人标注或单人盲复核。
E3 Tune：校准综合分阈值、泛词规则、类目/形态约束。
E4 Cluster：运行Average/Complete/Medoid三种方案，输出Primary、Secondary和unassigned。
E5 Evaluate：计算Pair/Cluster指标，比较V1/V2市场榜单及错误案例。
E6 Gate：通过验收后申请V2升级；否则保留V1并记录失败原因。

交付文件：
- v1_frozen_manifest.json
- keyword_pair_similarity.parquet/csv
- keyword_pair_labels.csv
- cluster_v2_primary.csv
- cluster_v2_secondary.csv
- cluster_v2_unassigned.csv
- cluster_v1_v2_comparison.xlsx
- cluster_v2_metrics.json
- cluster_v2_error_cases.csv
- reproducible build script + README

## 11. 下一步所需用户输入
当前不需要新增市场数据即可开始候选对计算。正式验收需要项目方提供/确认：
1. 300对关键词人工标签（可由项目方标注，模型提供俄文关键词对和理由）。
2. 若有已知误合并/漏合并案例，提供关键词对作为高价值测试集。
3. 确认是否有人工审核者可做第二标注；否则采用单人盲复核。
4. 若P8采集含推广结果，确认是否要把推广位纳入主实验；建议主实验先保留原始全位，另做去推广敏感性对照。

## 12. 重要边界
本文件是离线实验与验收方案，不代表V2聚类已经运行或已通过验收。所有阈值都是待校准假设；V1数据和市场统计保持不变，直到V2通过发布门槛。
