# 任务路由与案件清单

## Route lock

每个案件阶段维护：

```json
{
  "active_phase": "search",
  "active_search_engine": "patseek",
  "fallback_approved": false,
  "round_engines": {"R01": "patseek"},
  "queries": [],
  "completed_query_hashes": []
}
```

`case.json` 是动态路由状态的唯一权威源；`evidence.json.case` 只保留不可变案件元数据，`route.json` 只保留初始化时的静态路由。`active_phase` 为 `intake|search|retrieval|official_verify|analysis|reporting|complete`。搜索阶段只允许一个 `active_search_engine`；`round_engines` 保证同一轮不混用主引擎。翻页沿用同一查询组；检索式、市场、日期或目的发生实质变化才建立新检索记录。

查询唯一键：

```text
HMAC-SHA256(per_case_random_key,
            case_id + case_type + engine + paid_command + normalized_query + market
            + page + page_size + enrichment_mode
            + jurisdiction_filter + date_filter + purpose)
```

原始检索式从标准输入或受保护的案件文件读取，不写进 `case.json`。收费调用必须按顺序执行：

```text
transition-phase search
reserve-query --paid-command ... → 成功取得 query_hash
安全包装器实际调用 → 输出一次性 attempt_id
complete-query --attempt-id ... → 记录 success/partial/failed、结果数和积分
```

同一案件内成功或运行中的查询会被原子拒绝重复；失败记录不能解释为 0。只有从未启动上游调用的 `failed/blocked` 才能用 `--retry-failed`；任何已经启动的 `failed/blocked/timeout/uncertain` 都必须先核对 PatSeek 任务与扣费状态，再用 `--retry-uncertain --reconciliation-note ...`。包装器会在整个上游调用期间持有逐查询执行锁，原调用未退出时重试会被拒绝；上游已以 0 退出时也不得把它伪装为失败后重复收费。公开源回退必须先运行 `approve-fallback` 并记录用户批准原因，随后使用新的 `search_round`。

PatSeek 当前 `semantic` 是 CN 语义入口，预留时固定 `market=cn, page=1`；国际检索使用 `bool --market world` 并在查询中明确国家/地区过滤。`bool` 的 `page-size`、`patent` 的增强/不增强模式也纳入预留摘要并在执行前复核；`patent` 详情调用固定 `page=1`。

## 通用必填

- `case_type` 与子类型；复合请求拆成多个子任务，但共用案件号。
- 报告支持的具体决定。
- 目标产品、文件、专利、权项或竞争主体。
- 必要技术特征和明确排除范围。
- 关键日期、数据截止日和目标法域。
- 是否纳入论文、标准、产品资料等非专利文献。
- 已知文献、竞争对手或审查员引文。

## 申请前查新

- 获取拟保护主题、必要特征、预计申请/优先权日、拟定独立权利要求和已知最接近现有技术。
- 正式申请决策走 PatSeek 完整深度：QX、QY-Base、需要时 QY-Comp、CN/world 分库及详情证据。
- 入选公开号才进入 `patent-search` 直取阶段。

## OA

读取 `oa-workflow.md`。OA 不默认重新做完整查新；只有审查员特征映射需反证、区别特征常规性需验证或最接近现有技术需重定时才建立收费补检。

## FTO

- 获取产品版本、制造/使用/销售/进口行为、计划时间、具体实施国、必须实施和可设计绕开特征。
- 对 CN、US、JP、KR 和 EP 实际生效国分别处理。FTO 输入用 `DE`、`FR` 或 `EP-DE` 等实际国家代码；裸 `EP` 会被初始化器拒绝。`CC=EP` 仅是文献前缀过滤，不代表某成员国存在可执行权利。
- 欧洲实施国同时建立国家局与 EP 两条检索/核验路径，例如 DE 对应 `DE + EP`，不得因检出 EP 同族而遗漏德国国家专利或实用新型。
- 逐件核验当前有效独立权项、官方状态、期限、同族和继续/分案申请。

## 公众意见与无效

- 保留 `public_comment` 与 `invalidity` 两个子类型，不在报告名称、期限或目标权项上混用。
- 获取目标申请/专利、当前权项、关键日、主张理由、提交窗口、已知对比文件/决定书和非专利证据。
- 使用 PatSeek 无效检索框架和 Goal Loop；公众意见另行核验待审状态和程序窗口。

## 竞品调研

- 获取竞争主体全称、曾用名、子公司、中外文别名、技术边界、时间范围和决策用途。
- 先确定统计单位：申请、公开、同族或有效授权。申请人正确但技术不相关的记录不得计入。
- 重点文献直取，关键统计样本按官方来源抽核。

## 时间与成本

- 预计超过 35 分钟：开始前说明阶段和预计时间。
- 实际长任务：每 30 分钟给出进度、累计积分、失败项和剩余时间。
- 费用以当前使用者已确认范围为准，每轮记录 `credits_charged`；重复查询、扩大法域或新增语义角度必须有证据目的。
