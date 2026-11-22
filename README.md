# 机械专利撰写（含默认独立质检）

中国机械结构类发明与实用新型的 Codex 插件。**安装「机械专利撰写」一个插件，即同时取得撰写与独立质检两个技能。** 实际初稿或改稿文件生成后、最终交付前，默认执行质检、核实整改及成品复核，无须另行提出质检要求。用户当次明确限定范围或要求跳过时遵从其要求。

当前撰写插件版本为 **0.2.0**，包内质检技能版本为 **1.2.0**。

## 安装与更新

从本 [GitHub 仓库](https://github.com/yidaner4-ship-it/mechanical-patent-skill) 安装。

```sh
codex plugin marketplace add yidaner4-ship-it/mechanical-patent-skill --ref main
codex plugin add mechanical-patent-drafting@mechanical-patent-toolkit
```

支持插件目录的客户端也可从此市场选择「机械专利撰写（含独立质检）」安装。安装包内有两个同级技能：

```text
plugins/mechanical-patent-drafting/
├── plugin.json
└── skills/
    ├── mechanical-patent-drafting/
    └── shensheng-patent-qa/
```

已安装旧版撰写插件的电脑，刷新市场来源以获取新版：

```sh
codex plugin marketplace upgrade mechanical-patent-toolkit
```

在新对话中查看更新后的技能，客户端仍持有旧版时按其提示重载。GitHub 发布不会主动改变尚未刷新来源的设备，也不会为未安装插件的设备代为安装。

离线安装时，下载仓库 ZIP，将上述 `skills/` 中的**两个技能文件夹一起复制**到本地 `.agents/skills/`，保留同级关系。仅复制撰写技能会缺少它调用的质检入口。离线 ZIP 是固定版本，更新时需重新取得文件。

原独立「申晟专利独立质检」插件继续供只需审稿的使用者安装，与撰写包内质检保持同版。已安装新版撰写插件的电脑无需重复安装独立质检；此前两个插件都装过的设备可移除独立质检插件，以减少重复入口。

## 默认撰写与质检流程

1. 从用户提供的交底、模型、附图和指定底稿起草或修改，核实核心结构、必要配合及说明书支持，按本案要求控制权项数量和文本范围。
2. 用指定 Word 模板制作实际文稿及附图，查看实际渲染。
3. 交付前读取同包 [质检入口](plugins/mechanical-patent-drafting/skills/shensheng-patent-qa/SKILL.md)，冻结拟交付版本与依据，交由未参与本轮起草的独立审阅者检查。
4. 按每次名称出现核标号，逐图逐根看引线落点，检查权项引用、因果、工况及支持；逐条核实意见，有依据且获授权的问题整改后同步各交付副本。
5. 复查实际成品、隐私与最终文件摘要值，保存审核记录并说明未核项，再交付。

这是技能工作流指令，不安装后台任务或向外部平台自动上传稿件。未具备独立审阅、实际看图或渲染条件时，完成其他可做项目并明确记录对应未完成范围；扫描器通过不能替代完整质检。

## 随包质检能力与依赖

核心审稿方法、逐处扫描、机械图文复核及报告格式均在安装包内，新电脑无需另装上游技能或联网读取方法。

- [审稿方法与证据](plugins/mechanical-patent-drafting/skills/shensheng-patent-qa/references/review-method.md)：逐项引用路径、先行基础、技术因果、工况和支持。
- [名称及标号逐处核对](plugins/mechanical-patent-drafting/skills/shensheng-patent-qa/references/component-occurrences.md)：每次名称的段落、字符位置、实有标号、结论及例外依据。同段另一处正确标号不能替代当前检查。
- [机械图文与真实修订复核](plugins/mechanical-patent-drafting/skills/shensheng-patent-qa/references/mechanical-review.md)：每图每次标号的实体归属、引线、剖切、图文及交付副本一致性。
- [审核记录格式](plugins/mechanical-patent-drafting/skills/shensheng-patent-qa/references/report-record.md)：覆盖范围、逐处结果、问题证据、整改复核、未核项及最终摘要值。默认输出 Markdown。

随包扫描脚本只需 Python 3 标准库；人工审稿本身不要求安装 Python。Word/PDF 渲染、CAD 查看及独立审阅使用运行环境实际提供的能力；不足处如实列明。新的专利检索及最新法律依据按当轮任务和工具核验。

已有本地 `patent-draft-review` 时，可额外使用其详细参考或兼容的离线 HTML 报告生成器，它不是核心质检的必装条件。该组件单独维护，未复制其代码；来源为 [patent-review-kit v0.6.1 固定提交](https://github.com/KrisMiao97/patent-review-kit/tree/676ae000af132d7db9ba59821d8fcd2234288fdb)。使用前核对完整组件、Python 环境和数据格式；没有该组件时仍按包内格式完成 Markdown 记录。

## 使用示例

```text
用机械专利撰写技能，根据本地交底和指定模板完成实用新型五书。
权利要求控制在15项以内。按包内默认流程完成独立质检、核实整改和最终复核后交付。
```

仅审已有稿件时也可直接调用 `$shensheng-patent-qa`。本包不附带客户案卷、CAD、模板、批准样图或本机路径；所需材料由使用者在本地提供。

## 发布维护

撰写入口与包内质检共同随 `mechanical-patent-drafting` 插件更新。质检源以该插件的 `skills/shensheng-patent-qa/` 为准，独立质检插件保留相同发布副本。发布时核对两处质检目录逐文件一致、相对链接、扫描行为、隐私及实际 GitHub 内容；提升对应版本并推送 `main`。
