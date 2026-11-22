# 机械专利撰写与独立质检

中国机械结构类发明与实用新型的 Codex 技能。适用于起草和修改权利要求、依用户指定的 Word 模板制作文稿，以及核对说明书和附图。使用时提供本案技术资料、所需权项数量、模板和现有附图。

```text
用「机械专利撰写」技能审阅这份机械结构实用新型申请稿。
把独立权利要求概括到核心构造和必要配合，并核对附图标号及引线。
附图每个独立视图一页，按正文首次引用顺序编号，图体在版心居中，图号放页脚，局部裁断处补断裂线。
```

## 从 GitHub 安装和更新

当前包含「机械专利撰写」**0.1.1** 和「申晟专利独立质检」**1.1.0**。安装和更新均使用同一 [GitHub 仓库](https://github.com/yidaner4-ship-it/mechanical-patent-skill)。

1. 用支持插件目录的 Codex CLI 添加 GitHub 来源。

   ```sh
   codex plugin marketplace add yidaner4-ship-it/mechanical-patent-skill --ref main
   ```

2. 在 Codex 桌面版的插件目录选择「机械专利撰写」或「申晟专利独立质检」，安装所需插件后在新对话中调用技能。
3. 发布者将新版本推送到 `main` 后，运行以下命令刷新已跟踪的来源。

   ```sh
   codex plugin marketplace upgrade mechanical-patent-toolkit
   ```

如果当前对话仍显示旧版本，可新开对话，必要时重启客户端。参见 [OpenAI 插件市场命令](https://developers.openai.com/plugins/build/plugins#add-a-marketplace-from-the-cli)。

具备插件管理功能的 ChatGPT 工作区可由管理员从 GitHub 导入此插件市场、跟踪发布分支并配置成员可用范围。新导入的市场每天自动检查更新，管理员也可立即同步。独立安装的个人也可自行在本机定时执行上述刷新命令。参见 [工作区 GitHub 同步](https://learn.chatgpt.com/docs/enterprise/plugin-management#keep-plugins-up-to-date)。

希望离线安装时，可下载仓库 ZIP，解压后将 `plugins/mechanical-patent-drafting/skills/mechanical-patent-drafting` 文件夹复制到用户目录下的 `.agents/skills/`。ZIP 是固定版本，升级时需另行下载。此包不安装钩子或后台任务。参见 [Codex 本地技能位置](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills)。

## 发布维护

内部版有变化时，先选出可共享的改动，核对公开版内容及依赖，再更新公开版和版本号、提交并推送到 `main`。使用者从 GitHub 获取推送后的版本。公开版包含通用撰写、套版和质检规则，撰写所需的案卷、CAD 文件和模板由使用者在本地提供。

## 申晟专利独立质检 1.1.0

独立插件入口：[shensheng-patent-qa](plugins/shensheng-patent-qa/skills/shensheng-patent-qa/SKILL.md)。可单独核稿，也可在初稿或改稿完成后执行。逐处记录每次部件名称、别名、实有标号、段落与字符位置；同段其他位置已带号不能替代当前检查。附图按每图每次标号逐根看落点，术语、权项、图例与最终交付副本同步复核。

公开包包含逐处核对规范、Python 扫描器及机械图文复核规则，不附带客户案卷、CAD、批准样图或本机环境。

### 依赖与使用

- 名称及标号扫描器仅需 Python 3 标准库，可独立运行。配置和示例见[逐处核对说明](plugins/shensheng-patent-qa/skills/shensheng-patent-qa/references/component-occurrences.md)。它读取 DOCX 并输出 JSON、CSV 候选，不能代替人工语义复核或实际核图。
- 完整审稿方法采用独立上游 [patent-review-kit v0.6.1 固定提交](https://github.com/KrisMiao97/patent-review-kit/tree/676ae000af132d7db9ba59821d8fcd2234288fdb)。已有本地 `patent-draft-review` 时优先使用；也可在线读取该固定版本方法和参考。只读取方法，无须上传稿件。
- 生成离线 HTML 报告需要本地完整的上游 `patent-draft-review` 目录及 Python 3.10+。可下载[固定提交 ZIP](https://github.com/KrisMiao97/patent-review-kit/archive/676ae000af132d7db9ba59821d8fcd2234288fdb.zip)，将其中 `patent-draft-review` 目录作为独立技能安装到本地技能目录。保留其 `scripts/`、`assets/` 和 `references/` 等完整结构，不只复制一个脚本。上游单独维护，本仓库未复制其代码；Word 等附加输出按上游实际依赖核验。没有报告组件时交同字段 Markdown，并说明未生成 HTML。
- 已有 `mechanical-patent-drawings` 时连同其参考读取；没有时按随包[机械图文复核](plugins/shensheng-patent-qa/skills/shensheng-patent-qa/references/mechanical-review.md)执行。用户认可的样图由使用者本地提供，未取得样图时记录样式基准未核。

离线安装本入口时，将 `plugins/shensheng-patent-qa/skills/shensheng-patent-qa` 文件夹复制到本地技能目录；上游报告组件按上段另行安装。

```text
用 $shensheng-patent-qa 独立质检本轮实际五书及附图。
按名称每次出现建立逐处表，逐根看附图落点；核实整改后复查实际交付副本，注明未核项。
```
