# 安装、依赖与恢复

## 先下载正确的包

点击 **[一键下载全部流程技能](https://github.com/yidaner4-ship-it/mechanical-patent-skill/raw/refs/heads/main/downloads/mechanical-patent-toolkit-20261123.zip)**，解压后进入同时包含以下内容的目录：

```text
install.py
skills/
  fusion-production-modeling/
  patent-disclosure-skill/
    skills/patent-disclosure/
    skills/patent-application/
    skills/patent-docket/
  mechanical-patent-drawings/
  shensheng-patent-workbench/
  shensheng-patent-qa/
  patent-draft-review/
  patent-search/
  patseek-patent-search/
  documents/
  pdf/
  spreadsheets/
```

根技能文件夹须保留同级关系，`patent-disclosure-skill` 内部子技能也须保留原层级。不要仅提取单个 `SKILL.md`。GitHub **Code → Download ZIP** 是仓库快照；其中的 `downloads/` 整包还需要再解压，才能取得上述安装源。

## 安装文件

安装器仅使用 Python 3 标准库，支持 Python 3.10 及以上。选择本机实际可用的 Python 命令；下例使用 `python3`，Windows可用 `py -3`。

先检查计划，不创建任何目录或文件：

```sh
python3 install.py --dry-run
```

安装全部随包根技能：

```sh
python3 install.py
```

默认目标为环境变量 `CODEX_HOME` 指定目录下的 `skills/`；未设置时为当前用户的 `.codex/skills/`。需要其他工具或项目目录时显式指定：

```sh
python3 install.py --dest ./project-skills --dry-run
python3 install.py --dest ./project-skills
```

`--dest` 必须是工具实际支持的技能目录；安装器不会替使用者配置其他产品的技能发现机制。安装后按客户端提示重载技能或在新对话中使用。

只安装部分根技能可用：

```sh
python3 install.py --only fusion-production-modeling
```

部分安装不会自动补齐跨技能依赖。完整撰写与质检建议整包安装；只需建模时可选择建模技能。`--only patent-disclosure-skill` 会保留其全部嵌套子技能，不会将子技能散装到根目录。

安装器不执行 `pip`，不安装原生应用、不连接检索账号、不创建后台任务、不改写全局 `AGENTS.md`，也不移除未选择的其他技能。源目录、目标目录不能重叠；包内符号链接、异常目标和不安全的技能名会被拒绝。

## 更新与恢复

重复运行安装器时，同名旧技能先移入目标安装目录旁的 `<安装目录名>-backups/` 独立备份目录，再替换为已暂存的新副本。安装结果会显示实际备份位置，备份目录中的 `BACKUP.json` 列出被替换的根技能。

复制和验证先在暂存目录完成，单个目录通过同一文件系统内重命名替换。中途提交失败时，安装器会移除本次已安装目录并恢复本次旧目录；保留的其他技能不变。

手动恢复时，先关闭正在使用这些文件的任务，将当前需要恢复的技能目录移到其他位置，再把备份中的同名技能目录复制回原安装位置。只恢复实际需要的目录，不用整批覆盖当前用户的其他技能。

如遇安装锁，先确认没有其他安装进程正在运行。确认锁来自已结束的进程后，再移除报错位置中的 `.mechanical-patent-toolkit-install.lock` 并重试；不要在另一安装进程运行时删锁。

## 运行环境分开准备

安装技能文件成功，只表示文件已到位，不表示全部外部能力可用。按本次任务实际需要配置：

| 能力 | 需要配置 | 不随整包复制 |
| --- | --- | --- |
| 基础技能安装 | Python 3.10+ | 原电脑Python或虚拟环境 |
| 交底、申请及格式工具 | 各子技能要求的公开Python依赖，建议隔离环境 | 依赖缓存、历史输出 |
| Fusion／其他CAD | 可用应用、合法许可及实际可调用的接口 | 应用二进制、登录状态、客户模型 |
| STEP解析 | 子技能要求的隔离CAD环境，按所选解析器配置 | 原电脑 `cad-env` |
| Word套版和修订 | 目标用户的有效Word模板；对应公开Python依赖 | 原用户个人／客户模板 |
| Word／PDF渲染 | LibreOffice或实际可用的渲染能力；Poppler按需配置 | 原系统安装与字体 |
| Excel检索候选表 | 独立公开 `spreadsheets` 技能及openpyxl；需要重算时使用可用的表格应用 | 原用户工作簿、计算缓存、表格账号 |
| 独立审阅 | 支持独立审阅者的运行环境，实际可读的文稿和图页 | 原会话、账号与审核日志 |
| 商业检索 | 下载者自己的服务连接、凭据、可用客户端及费用范围 | 原账户授权、密钥、积分预算 |

各组件的依赖文件以其目录中的说明为准。不要把一个子技能的可选CAD或浏览器依赖全部装进主Python环境。完成后分别测试实际读取、文件生成和渲染；缺少运行能力时记录具体未完成范围，不能以安装成功代替案件验收。

## 公开辅助版本和平台边界

整包中的Word／PDF／Excel辅助技能及部分审稿／检索适配入口为独立公开版本，不包含相应官方缓存、第三方技能源码或商业客户端。按包内各技能说明使用，不将其与原环境功能等同。开放组件的许可证和必要版权声明保持随包。openpyxl可写入和保留公式，本身不会重新计算公式结果；需要计算验收时使用可用的表格应用或明确标记未重算范围。

当前 PatSeek 工作台安全CLI使用 macOS Keychain 与 POSIX `fcntl`。这部分不是Windows开箱即用功能；Windows需要可用的服务连接或自行适配。PatSeek适配入口未配置外部vendor时会明确报告不可用，不会悄悄改用别的检索源或沿用原账号的付费授权。公开检索路线如可用，应作为明确选择使用，并说明实际覆盖。

公开文档辅助工具的典型调用（在整包根目录，示例输出目录应为新目录）：

```sh
python3 skills/documents/render_docx.py SOURCE.docx --output-dir NEW_DIR
python3 skills/documents/scripts/privacy_scrub.py SOURCE.docx CLEAN.docx --revisions accept
python3 skills/pdf/scripts/render_pdf.py SOURCE.pdf --output-dir NEW_DIR
python3 skills/pdf/scripts/privacy_scrub.py SOURCE.pdf CLEAN.pdf
```

需要保留真实修订时将 `--revisions accept` 改为 `--revisions preserve`；结果仍需在Word核对接受态／拒绝态及最终版式。自动接受仅覆盖工具明确支持的文字／属性修订，遇不支持的结构修订时应在Word中处理后重试，不强制生成貌似清洁的文件。渲染脚本可用 `--libreoffice`、`--pdftoppm` 等参数指定本机程序，具体以各脚本 `--help` 为准。PDF清理使用的公开Python库按 `skills/pdf/requirements.txt` 安装。

DOCX清理脚本始终删除批注；`preserve`仅保留文字修订。需交付批注时不要用它处理该副本，应在Word中保留批注内容并匿名化，再完成检查器及实际图文复验。

## 使用前核验

1. 检查客户端能发现所需技能，内部相对引用和嵌套目录存在。
2. 用非客户的临时样例验证本轮实际要用的工具：材料接入、图文台账、文件生成、渲染和清理。
3. 模型复验应采用真实原生模型／STEP及适用工况；演示图不能作为几何证明。
4. 独立质检读取实际拟交付文件；没有独立执行或实际看图条件时明确未完成范围。
5. 对最终交付Word、PDF及打包副本执行隐私清理，核对可打开、内容完整、图页和版式一致。需要真实修订时保留其接受／拒绝功能并匿名化；清洁稿按本案要求去除附带批注和修订历史。

仓库更新和ZIP下载均不会自动更新其他电脑。下载新的整包后，重新运行安装器即可更新所选根技能并保留旧副本。
