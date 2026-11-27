# 机械专利全流程插件

一次安装建模、交底、申请撰写、CAD附图、检索、独立质检、Word/PDF和Excel辅助技能。**完整11个根技能现在随同一个 `mechanical-patent-workflow` 插件发布并统一更新。**

## 安装一次，之后统一更新

在支持插件市场的Codex CLI中执行：

```sh
codex plugin marketplace add yidaner4-ship-it/mechanical-patent-skill --ref main
codex plugin add mechanical-patent-workflow@mechanical-patent-toolkit
```

支持本地市场的桌面客户端可在添加此GitHub市场后选择「机械专利全流程（建模·撰写·质检）」安装。安装后按客户端提示开启新对话或重载。仓库公开可读取，不要求下载者拥有本仓库写权限。

以后发布者将新版插件推送到同一GitHub仓库的 `main` 分支，使用者只需更新这个市场，无需逐个下载11个技能：

```sh
codex plugin marketplace upgrade mechanical-patent-toolkit
```

更新命令会刷新Git来源并更新已安装插件。**这不等于所有设备实时自动推送。**手动安装者按客户端刷新；工作区管理员按下节配置GitHub同步，才有工作区的自动每日同步。固定到旧commit或使用ZIP副本不会跟随main。仅修改发布者电脑中的私有技能，也不会自行发布到GitHub。

## 工作区自动同步

工作区管理员在管理控制台的Plugins中选择Import marketplace，Source填写：

```text
https://github.com/yidaner4-ship-it/mechanical-patent-skill
```

Path留空，Branch填写 `main` 或采用默认分支，不固定旧commit。导入后配置插件对角色的可用／安装策略。新市场默认每日同步，也可在Marketplaces选择Sync now立即同步；仍受GitHub访问和工作区策略限制。[官方GitHub导入与同步说明](https://help.openai.com/en/articles/20001504-importing-and-syncing-plugin-marketplaces-from-github)

此仓库提供GitHub插件市场分发，并不表示已经上架OpenAI通用公共插件目录。所需外部应用与服务仍由每位使用者配置和授权。

## 一个插件中的11个根技能

| 阶段 | 技能 | 作用 |
| --- | --- | --- |
| 案件接入与撰写 | `patent-disclosure-skill` | 内含交底、申请、可选案卷会稿等9个子入口 |
| 建模与改模 | `fusion-production-modeling` | 需求与验收、工程计算选型、现实零件、制造装配、工况验证及样机核对回写 |
| CAD附图 | `mechanical-patent-drawings` | 投影、剖视、爆炸、标号、短S引线与图文同步 |
| 定稿检索 | `shensheng-patent-workbench` | 当前权项的实际检索、证据及两性评价 |
| 检索来源 | `patent-search`、`patseek-patent-search` | 公开源及需自行配置的商业客户端适配 |
| 独立质检 | `shensheng-patent-qa`、`patent-draft-review` | 方案、支持、形式、逐处标号及逐根引线审阅整改 |
| 文件成品 | `documents`、`pdf`、`spreadsheets` | Word/PDF/Excel的公开辅助实现、渲染和隐私核验 |

所有根技能保留同级关系，总包的9个子技能保留原层级。发布源码唯一维护在 [`plugins/mechanical-patent-workflow/`](plugins/mechanical-patent-workflow/)，市场直接安装这份源码，不从另一个ZIP解包加载。

## 保留的机械撰写要求

- 权1简洁、概括有据，保留核心部件和必要配合；具体驱动、导向、紧固、方向和尺寸逐项判断必要性。
- 内容依权项顺序展开，各结构就近说明直接效果；实施方式由整机到局部，再以装配或工作过程串联。
- 真实CAD／可信原图优先，一图一页、图体居中、图号置页脚，按具体实施方式首次实质引用排序；固定图号按本案要求处理。
- 保留现行短S、字号、线宽和主要件箭头要求；公开图例仅为同参数通用曲线，不附客户原图。工具成功不能替代几何核验与逐根目视。
- 成稿和实质改稿接入适用检索／补检、独立质检及交付清理；缺关键事实或必要核读时明确阶段成果与未完成范围。

当前1.0.7优化案件执行调度：独权骨架形成后尽早检索，定稿仍按当前权项核对覆盖并完成逐项评价；正文与附图使用同一技术底稿并行协作，集中整改和批量生成副本。首次完整独立审阅后按差异及关联范围复核，已核证据和未变部分有据复用；实际看图、全部交付副本渲染、隐私清理及清理后复验继续执行。旧机械撰写入口同步至0.2.4，随包及独立QA同步至1.2.7。

既有需求、简洁基础方案、工程计算选型、制造装配、分阶段验收与样机实测回写继续执行；方案设计仍核对专利空间与工程价值，完整产品模型与简洁保护构思分别管理。经明确授权的双向核对及保留本地依赖的逐文件同步工具保持原分发范围，定时任务由宿主另行配置。配对关系、量词、新特征引入、简洁独权、唯一名称、图面及隐私标准不变。

## 从旧版迁移与离线使用

原有撰写插件、独立质检插件和旧日期ZIP继续保留。它们不会自动变成完整11技能插件。首次迁移请安装新的 `mechanical-patent-workflow`；确认可用后，按需停用旧插件或移出同名手动技能，避免重复入口。不要删除客户案件、个人模板或原有备份。

- [最新可导入插件ZIP](https://github.com/yidaner4-ship-it/mechanical-patent-skill/raw/refs/heads/main/downloads/mechanical-patent-workflow-latest.zip)：用于支持本地ZIP导入的客户端；离线副本本身不自动订阅更新。
- [最新离线技能整包](https://github.com/yidaner4-ship-it/mechanical-patent-skill/raw/refs/heads/main/downloads/mechanical-patent-toolkit-latest.zip)：解压后可用install.py；这种复制安装仍需手动下载新版。
- [安装、更新及依赖说明](INSTALL.md)
- [维护者发布步骤](MAINTAINER.md)
- [组件分发范围](THIRD_PARTY_NOTICES.md)

## 能力与依赖边界

本插件分发技能规则与公开工具，不附Fusion、Office、LibreOffice、Poppler、原电脑的虚拟环境或账号。Python依赖、商业检索客户端、MCP／服务连接、字体及生产模型按实际任务配置。可写环境、用户配置、模板和案件数据放在插件缓存外，避免升级替换；插件更新不会替他人配置或授权商业账号。

Word/PDF/Excel以及部分审稿、检索入口为独立公开兼容实现，不复制受限官方缓存或未许可第三方原包，也不声称功能完全相同。保留开放组件的许可与署名，详见THIRD_PARTY_NOTICES.md。
