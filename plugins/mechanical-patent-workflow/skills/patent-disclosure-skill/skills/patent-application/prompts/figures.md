# 申请文件 · 附图

发明／实用新型按实际保护对象出图。机械产品先读[CAD取图与附图验收](../../../../mechanical-patent-drawings/references/cad-figures.md)：主要轮廓、剖面及装配关系从真实CAD或可信原图取得；经过同源核验、清理和正式布标的黑白CAD投影可入文。彩色截图、带界面的渲染图不能直接当正式线稿，AI生成不能作几何证据。图号独立于图体，置于正式Word／PDF页脚；每个独立视图单页、图体水平及垂直居中，局部真实裁断处补断裂线。外观走其专用分支。

先按 `figure_plan.md` 写出产出目录 `figures/figure_plan.yaml`。下面出图的 `kind` 必须落在该清单里；不要另画权要没点到的剖视/爆炸。剖视、爆炸、多状态有交底线稿才升格，否则保持 `pending` 并记问题清单。

## 方法／软件系统

| 种类 | `kind` | 标号 |
|------|--------|------|
| 系统框图 | `block_diagram` | 虚线分组 + 框内模块名；**不**标（10）（20），**不**拉引出线。各列按自身模块数自上而下紧排，不要把较少模块的一列撑成与邻列相同槽位数 |
| 方法流程图 | `flowchart` | 框内写「步骤一…」，与独权同序同义；**不**拉引出线，**不**用 S1、201 |
| 点名示意图 | `source_image` | 用户点名或交底已入文的场景/拓扑/对照图；`source` 为源文件；**不**重画楼层剖面 |

主流程图框数与方法独权步骤数一致。分支、回环写在从属和实施例，不要在独权图上另编步骤。

方法摘要图按核心方案选流程图，软件系统按核心方案选框图或流程图；机械产品摘要图选择能体现核心构造及配合的已有图。点名场景图是否作摘要图按用户指令和实际内容核对。

## 点名图（发明 / 实用都适用）

只处理用户自然语言指定或 `@` 的路径，以及交底正文已经编号嵌入的示意图。

1. **理解**：图上对象、关系、图例。
2. **判别**：技术示意图 / 拓扑 / 流程照片 / 结构线稿 / 界面截屏 / 图标切图 / 营销场景。
3. **匹配**：逻辑框图、流程可用相应脚本整理；环境／拓扑／实施例对照图按实际用途入文，机械结构图按CAD标准核验。图号统一依具体实施方式首次实质引用排序，不固定接在图1、图2之后；图标、切图、营销场景不入文并说明原因。

禁止扫描 `node_modules`、`dist`、`build`、`src/assets`、前端切图目录。未点名则不要自己去工程里捞图。不承诺把源图改画成公布稿剖面。

写入 `application_plan.yaml` 的 `named_figures`。

## 机械产品结构图整理（发明／实用新型）

交底合格黑白线稿可在核对几何、标引、纸面样式及清晰度后复用；无需为“升格”重画准确轮廓。需要常规裁切或黑白整理时可用：

```bash
python skills/patent-application/tools/compose_application_figure.py \
  --source <交底线稿.png或.svg> --fig N --out-dir <产出>/figures
```

该脚本仅作图像整理，不能代替CAD投影、剖切或图面验收。标号与本案 `parts`＋`features`／权项同一台账；既有正确号码沿用。未处理CAD截图和实拍不直接作申请附图；经核验的CAD线稿允许入文。主要件三角箭头、短S、图内／外留白和真实落点统一按CAD规则执行，不能仅以overlay或裁切脚本成功判为合格。

## 外观

外观**不走**本节升格。见 `prompts/design_application.md` 与 `references/design_view_cnipa.md`。  
禁止对本案跑 `compose_application_figure.py`。交底入文图原样复制到产出 `figures/`；不合格只写入问题清单。

## 逻辑图生成步骤（仅方法／软件系统对应图型）

1. 按 `figures/figure_plan.yaml` 写 `figures/invention_figures.yaml`（合同见 `references/schemas/invention_figures.schema.yaml`）。只为清单中的 `flowchart` / `block_diagram` / `source_image` 生成 YAML。
2. 运行：

```bash
python skills/patent-application/tools/render_invention_figures.py \
  --plan <产出>/figures/invention_figures.yaml \
  --out-dir <产出>/figures
```

3. 看 `APPLICATION_FIG:`。SVG必有；Word需可用嵌图或相应矢量处理。生成失败记录未完成图页，不能以写入问题单代替完成；机械图不交给逻辑图渲染器。回[共用收尾](../../../../mechanical-patent-drawings/references/drafting-and-review.md#共用收尾)核验实际交付状态。

不做 TIFF。
