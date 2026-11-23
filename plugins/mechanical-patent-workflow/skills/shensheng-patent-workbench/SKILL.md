---
name: shensheng-patent-workbench
description: 申晟知产统一专利工作台。在 patent-search 与 PatSeek 之间路由申请前查新、OA、FTO、公众意见/无效和竞品调研，以 CN 为主并按需覆盖 US/EP/JP/KR，生成可复核的 Excel 候选表、机械特征对照 Word 与同版 PDF。用户要求正式专利检索、OA 证据复核、FTO、无效证据或申晟格式报告时使用；普通外观设计图像检索不适用。
---

# 申晟专利工作台

这是面向用户的统一入口。`patseek-patent-search` 是正式检索与分析主引擎，`patent-search` 是公开源补检和已知公开号原文直取器；不要让两个上游 Skill 对同一检索式并行搜索。

## 固定业务配置

- 任务：申请前查新、OA、FTO、公众意见/无效、竞品调研。
- 法域：CN 为默认主法域；按案件需要覆盖 US、EP、JP、KR。FTO 的 EP 必须落实到实际实施国，写 `DE`、`FR` 或 `EP-DE` 等形式，不能只写“EP”。
- 交付：Excel 候选表 + 特征对照 Word + 由最终 Word 转换的同版 PDF。
- 品牌：使用 `assets/shensheng-logo.png`，保持比例和原有字样，不重绘、不删改注册标记。
- 外发：在当前使用者已授权的范围内向可用检索服务发送必要技术内容；仍删除客户姓名、项目代号等与召回无关的信息，并默认使用无痕 PatSeek 包装器。
- 成本：费用范围由当前使用者确定；每次记录实际积分，不重复收费检索，不继承原作者的账号或预算授权。
- 耗时：预计超过 35 分钟时先告知；实际长任务至少每 30 分钟报告已完成、剩余工作和预计时间，不因耗时自动中止。

上述是工作台默认值。只有案件的具体决定、关键日期、目标权项、实施国、程序期限或保密范围发生实质变化时才补问，不要每案重复询问固定配置。

## 路由

开始前读取 `references/routing.md`，确定唯一任务类型和 `route_lock`。

| 任务 | 检索主引擎 | `patent-search` 的角色 | 必须外部核验 |
|---|---|---|---|
| 申请前查新 | PatSeek 完整深度 | 仅直取入选文献 PDF/Word/附图 | 关键日和重点文献日期 |
| OA | 先解析案卷；仅有证据缺口时定向 PatSeek | 下载本申请、审查员引文和新增候选 | 当前权项、OA、期限、审查档案 |
| FTO | PatSeek，按目标国分开 | 直取重点权利原文 | 有效权项、官方状态、期限、同族/继续申请 |
| 公众意见/无效 | PatSeek 无效检索/Goal Loop | 直取目标文本和证据 | 当前权项、程序窗口、在先公开及证据链 |
| 竞品调研 | PatSeek 技术调研 | 下载代表性专利和附图 | 重点权利与统计样本按需核验 |
| 已知公开号下载 | 不调用 PatSeek | `patent-search` Mode B | 按需 |

同一 `search_round` 只能有一个主引擎。PatSeek 不可用时停止，向用户说明后再由用户选择是否切换公开源；不得静默切换或混写来源。

## 案件流程

1. 确定任务要支持的决定，以及目标文件、关键日期、法域和必要技术特征。OA 读取 `references/oa-workflow.md`；其他任务按 `references/routing.md` 加载相应上游参考。
2. 用 `scripts/workbench init-case ...` 建立案件目录、`case.json`、证据骨架和 `working/templates/` 品牌模板副本。不要在 Skill 目录内存放案件数据；`deliverables/` 只放通过终验的成品。
3. 按 `references/evidence-schema.md` 拆解机械特征：部件、连接、相对位置、运动/装配状态、力/动力/介质路径、控制逻辑、参数和技术效果。
4. 收费检索前展示范围、预计耗时和深度。正式申请决策、FTO、OA 正式答复、公众意见/无效默认完整深度；按当前使用者已确认的范围和费用执行；未获相应授权时先说明范围，不继承原机器的服务或预算授权。
5. 进入检索阶段先运行 `scripts/workbench transition-phase ... search`。每次收费调用前必须用 `reserve-query --paid-command <bool|semantic|patent>` 从标准输入或受保护文件读取检索式并取得 `query_hash`；`bool` 的 `--page-size`、`patent` 的 `--no-enrichment` 必须在预留时与实际调用保持一致。成功预留后才调用 `scripts/workbench patseek --case-dir <案件目录> --query-hash <摘要> --query-file <0600文件> <bool|semantic|patent> ...`（或 `--query-stdin`）。包装器会输出一次性 `attempt_id`，结束后立即用 `complete-query --attempt-id <该值>` 记录结果、积分或失败。包装器会重新核验实际子命令、查询、市场、页码、结果深度和 running 预留，并在整个上游调用期间持有逐查询执行锁；不得把已成功返回的调用改写为可立即重试的失败。不得把未公开检索式写成位置参数。
6. PatSeek 调用一律走安全包装器。它从 macOS Keychain 取 Key，并禁用隐式缓存、调用日志和历史读取。禁止把 Key 写进聊天、命令参数、报告或工作簿。
7. 候选归一化、按同族去重后，再用 `patent-search` 直取重点文献。公开源失败必须记为 `partial` 或 `failed`，不能记成 0 命中。
8. 逐件记录权项/段落/附图证据。模型推断与文献明确记载分栏；无证据定位不得标记“覆盖”。
9. 需要法律状态或程序信息时使用目标专利局官方登记簿/案卷核验。聚合状态只能用于筛查。
10. 工作中可运行 `validate-evidence --stage draft` 检查引用；交付前必须运行默认的 `validate-evidence --stage final`。使用 Spreadsheets、Documents 和 PDF Skill，将同一证据数据填入案件 `working/templates/` 的副本并输出到 `deliverables/`；不得回写 Skill 模板。Word 必须渲染逐页检查，正式 PDF 必须由最终 Word 转换并再次逐页检查。

## API Key

用户不要把 Key 发到聊天。让用户在 Mac 终端执行：

```bash
<skill-dir>/scripts/workbench keychain set
```

终端会由 macOS Keychain 隐式询问 Key。用户完成后只需回复“已设置”。检查是否存在但不显示 Key：

```bash
<skill-dir>/scripts/workbench keychain check
```

Key 在 [PatSeek](https://patseek.cn) 的“个人中心 → API Key 管理”创建。

## 证据与结论硬门

- 新颖性 X 文献：同一篇关键日前适格文献覆盖全部必要特征；不得拼接多篇。
- 创造性/OA：记录最接近现有技术、区别特征、技术效果、实际技术问题和技术启示；OA 修改还必须有原始申请依据。
- FTO：未核验目标国有效权项和官方状态时，只能称“候选权利筛查”。
- 公众意见/无效：区分程序类型，记录目标权项版本、关键日、公开可获得性和证据位置。
- 竞品统计：公开同族去重、申请人归一化、截断和统计分母。
- 超时、限流、WAF、解析失败和未访问来源必须显式披露，不能解释为“未检出”。

完整字段和校验规则见 `references/evidence-schema.md`；品牌化交付要求见 `references/reporting.md`；本地凭据与无痕边界见 `references/security.md`。
