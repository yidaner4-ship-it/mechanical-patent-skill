# 安装与统一更新

## 推荐：安装完整插件

需要支持插件市场的Codex CLI或相应桌面客户端。在CLI执行：

```sh
codex plugin marketplace add yidaner4-ship-it/mechanical-patent-skill --ref main
codex plugin add mechanical-patent-workflow@mechanical-patent-toolkit
```

默认市场名为 `mechanical-patent-toolkit`。完整插件名为 `mechanical-patent-workflow`，界面显示「机械专利全流程（建模·撰写·质检）」。它一次提供11个根技能和总包内9个子入口。安装后按客户端提示重载或开启新对话。

不要只稀疏拉取`.agents/plugins`：市场条目还需要同仓库完整的`plugins/mechanical-patent-workflow`目录。上述推荐命令不设置稀疏过滤。

## 更新

```sh
codex plugin marketplace upgrade mechanical-patent-toolkit
```

Git来源跟踪main时，此命令刷新源并更新已安装的插件缓存。保持同一插件名和市场名即可续接更新，不用每次重新添加11个技能。发布者须真正更新GitHub插件目录和版本；只改本机文件不能传播。固定旧commit、复制到手动skills目录或离线ZIP不会自行更新。

工作区管理员可按[官方说明](https://help.openai.com/en/articles/20001504-importing-and-syncing-plugin-marketplaces-from-github)导入同一仓库、跟踪main并配置访问策略。新市场默认每日同步，可用Sync now立即刷新。这是工作区同步，不是对任何个人设备的实时强制推送；无管理员权限的使用者按其客户端支持的方式更新。

升级会替换插件缓存。个人偏好可放本地AGENTS或独立配置，模板、生产模型、案件、凭据及运行环境必须放缓存外，不能依赖手工修改已安装插件保存长期内容。商业服务配置不会因插件发布自动完成。

## 从旧安装迁移

旧`mechanical-patent-drafting`及独立`shensheng-patent-qa`插件继续供兼容使用，安装范围保持原样。需要完整流程时安装新插件。先确认新插件可用，再按需停用旧插件或备份移出手动安装的同名技能；不要自动删除其他技能、全局AGENTS、用户模板和案件。

## 离线与源码副本

[插件ZIP](https://github.com/yidaner4-ship-it/mechanical-patent-skill/raw/refs/heads/main/downloads/mechanical-patent-workflow-latest.zip)的根目录为plugin.json、.codex-plugin/及skills/，用于支持导入的客户端。导入的ZIP本身是版本快照。

[离线技能整包](https://github.com/yidaner4-ship-it/mechanical-patent-skill/raw/refs/heads/main/downloads/mechanical-patent-toolkit-latest.zip)解压后可执行：

```sh
python3 install.py --dry-run
python3 install.py
```

这种方式只复制技能，保留已有目录的备份，不提供市场自动更新。Windows可用`py -3`代替python3。安装器要求Python3.10+；默认目标为`$CODEX_HOME/skills`，未设置时为当前用户的`.codex/skills`。支持`--dest`及`--only`；部分安装不自动补齐跨技能依赖。

源码检出目录中的install.py从`plugins/mechanical-patent-workflow/skills`读取；离线整包从根skills读取。它不安装依赖、不登录账号、不改全局AGENTS。已有同名目录先备份，失败则回滚；恢复前确认无并行安装进程。

## 外部运行环境

- 建模需使用者自己的Fusion／其他CAD、合法许可及实际应用接口；不随插件分发或自动配置。
- Word/PDF渲染需本地LibreOffice及Poppler等可用程序和字体；公开Python库按所用子技能requirements安装到独立环境。
- Excel辅助使用openpyxl保留数据、格式及公式；公式重算需可用的表格应用，不能把写入公式等同于已计算。
- 检索服务需要自己的授权、账号、合法客户端与费用范围。PatSeek工作台安全CLI使用macOS Keychain和POSIX文件锁，Windows需相应服务连接或另行适配；不能承诺所有平台开箱运行全部商业服务。
- 独立质检需要真实可读文件、适用图页及未参与起草的审阅者；缺少条件如实报告，不把扫描通过当成全稿通过。
- 可写数据和依赖放插件缓存之外，具体环境变量和路径见对应技能说明；升级只更新受版本管理的程序和规则。

CAD环境可通过`PATENT_SKILL_CAD_VENV`指定现有环境的绝对路径，或用`PATENT_TOOLKIT_DATA_HOME`指定持久数据根，CAD工具会使用其中的`cad-env/`。未指定时依次采用系统用户数据目录，最终回退至`~/.local/share/mechanical-patent-workflow/`。PatSeek需由使用者显式设置`PATSEEK_VENDOR_ROOT`和根内的`PATSEEK_CLIENT_PATH`，仍须通过权限、接口与安全包装检查；不会自动信任或分发第三方代码。详见对应技能INSTALL。

## 成品工具示例

在完整插件根目录或离线整包根目录运行，输出位置使用新路径：

```sh
python3 skills/documents/render_docx.py SOURCE.docx --output-dir NEW_DIR
python3 skills/documents/scripts/privacy_scrub.py SOURCE.docx CLEAN.docx --revisions accept
python3 skills/pdf/scripts/render_pdf.py SOURCE.pdf --output-dir NEW_DIR
python3 skills/pdf/scripts/privacy_scrub.py SOURCE.pdf CLEAN.pdf
```

DOCX清理器始终删除批注；preserve只保留文字修订。需要批注交付时不要用它处理该副本，应在Word保留内容、匿名化并复查。自动接受不支持的结构修订时，先在Word正确处理再重试。清理后仍须检查实际内容、接受／拒绝功能、图页及版式。

## 更新前后检查

核对插件名称、版本、11个根技能和所需引用。用非客户夹具验证当前任务需要的读取、出稿、渲染及清理能力。实际案件继续执行模型工况复验、定稿检索、独立质检、Word/PDF逐页核读和所有交付副本的隐私清理，不能以安装或升级成功代替案件验收。
