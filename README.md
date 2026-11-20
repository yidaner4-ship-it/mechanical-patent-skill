# 机械专利撰写

中国机械结构类发明与实用新型的 Codex 技能。适用于起草和修改权利要求、依用户指定的 Word 模板制作文稿，以及核对说明书和附图。使用时提供本案技术资料、所需权项数量、模板和现有附图。

```text
用「机械专利撰写」技能审阅这份机械结构实用新型申请稿。
把独立权利要求概括到核心构造和必要配合，并核对附图标号及引线。
```

## 从 GitHub 安装和更新

当前发布版本为 **0.1.0**。安装和更新均使用同一 [GitHub 仓库](https://github.com/yidaner4-ship-it/mechanical-patent-skill)。

1. 用支持插件目录的 Codex CLI 添加 GitHub 来源。

   ```sh
   codex plugin marketplace add yidaner4-ship-it/mechanical-patent-skill --ref main
   ```

2. 在 Codex 桌面版的插件目录选择「机械专利撰写」，安装该插件后在新对话中调用技能。
3. 发布者将新版本推送到 `main` 后，运行以下命令刷新已跟踪的来源。

   ```sh
   codex plugin marketplace upgrade mechanical-patent-toolkit
   ```

如果当前对话仍显示旧版本，可新开对话，必要时重启客户端。参见 [OpenAI 插件市场命令](https://developers.openai.com/plugins/build/plugins#add-a-marketplace-from-the-cli)。

具备插件管理功能的 ChatGPT 工作区可由管理员从 GitHub 导入此插件市场、跟踪发布分支并配置成员可用范围。新导入的市场每天自动检查更新，管理员也可立即同步。独立安装的个人也可自行在本机定时执行上述刷新命令。参见 [工作区 GitHub 同步](https://learn.chatgpt.com/docs/enterprise/plugin-management#keep-plugins-up-to-date)。

希望离线安装时，可下载仓库 ZIP，解压后将 `plugins/mechanical-patent-drafting/skills/mechanical-patent-drafting` 文件夹复制到用户目录下的 `.agents/skills/`。ZIP 是固定版本，升级时需另行下载。此包不安装钩子或后台任务。参见 [Codex 本地技能位置](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills)。

## 发布维护

内部版有变化时，先选出可共享的改动，核对公开版内容及依赖，再更新公开版和版本号、提交并推送到 `main`。使用者从 GitHub 获取推送后的版本。公开版包含通用撰写、套版和质检规则，撰写所需的案卷、CAD 文件和模板由使用者在本地提供。
