# 机械专利全流程插件

此插件一次提供11个同级根技能，包含总包内9个子入口。它是公开可迁移版本，保留申晟机械撰写风格、真实CAD取图、短S引线、独立质检与交付隐私要求；不附客户案卷、生产模型、账号、原电脑环境或商业应用。

## 从GitHub市场安装与更新

```sh
codex plugin marketplace add yidaner4-ship-it/mechanical-patent-skill --ref main
codex plugin add mechanical-patent-workflow@mechanical-patent-toolkit
```

以后更新：

```sh
codex plugin marketplace upgrade mechanical-patent-toolkit
```

保持订阅同一市场及main分支。发布者需把公开源码及版本真正发布到GitHub；个人用户按客户端刷新，工作区管理员可配置GitHub市场的自动每日同步。不是所有设备实时强制推送。安装或更新后按宿主提示重载／新开对话。

## 目录与能力

`skills/`保留11个根技能的同级关系，`patent-disclosure-skill/skills/`保留子技能层级，不要单独移动某个SKILL.md。根plugin.json为portable入口，.codex-plugin/plugin.json提供兼容声明；两者版本保持一致。

建模由fusion-production-modeling负责；交底和申请由patent-disclosure-skill路由；机械附图负责同源几何、图文及标引；workbench负责实际检索，QA独立审阅并使用公开审稿辅助；documents、pdf和spreadsheets完成相应文件辅助工作。

Python依赖、Fusion／CAD、LibreOffice／Poppler、字体及商业检索客户端由使用者配置。可写环境、个人模板、vendor和案件放在插件缓存外，避免更新替换；账号不随插件分发或自动授权。公开兼容入口不冒充受限原组件，见THIRD_PARTY_NOTICES.md和各组件许可。

[完整安装与更新说明](https://github.com/yidaner4-ship-it/mechanical-patent-skill/blob/main/INSTALL.md)

[维护者发布说明](https://github.com/yidaner4-ship-it/mechanical-patent-skill/blob/main/MAINTAINER.md)
