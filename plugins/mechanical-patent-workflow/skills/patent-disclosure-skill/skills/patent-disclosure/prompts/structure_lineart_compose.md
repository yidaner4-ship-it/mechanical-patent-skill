# 实用新型结构线稿 · 按件拼装（独立模块）

**何时读**：栅格来源确需按物理零件维护时，在无号轮廓之后、锚点叠标之前使用。真实 CAD 矢量已有零件层时直接保留，不为套此流程栅格化或裁碎。  
**合同**：`references/schemas/structure_lineart_compose.schema.yaml`  
**脚本**：`tools/structure_lineart_compose.py`  
**不要**把本文件与外观 `design_lineart_*` 混用。

目标：交付物的**可编辑源**是「子文件 + 总图引用」，不是一张嵌了整图的扁 SVG。

```
lineart_assist/parts/{视}_{id}.svg   # 可单独打开、替换
lineart_assist/{视}_composed.svg     # <g id="part-N"> 相对路径引用 parts/*.svg
lineart_assist/{视}_…_callouts.svg   # overlay 注入件号（零件层仍指向子文件）
```

入文 PNG 只是预览。换某一件：改对应 `parts/{视}_{id}.svg`（或该件 PNG 后重跑拼装），不必重出整张大图。

**不承诺**子 SVG 内是可改贝塞尔 path：`crop` 是总装 PNG 的裁窗；`image` 是单件 PNG 的包装。总装 `crop` 隔离弱（同源图开窗），爆炸/可分离件必须 `image` 并先出单件图。

## 物理零件层与子特征

默认三层：视（一份 SVG）→ 本视物理 `parts` 各一件一层 → 标号组 `structure-callouts`。已登记 `features` 只在标号层指向其真实母件特征，不强制拆成独立零件层。  
拼装条目对应本视物理部件，标号须事先在 parts/features 登记。孔槽、筋齿等可以有子特征号而不成为可分离零件；不为画图自创结构，剖切符号不是零件。crop 窗可以重叠，但不得把一件切成多组。

爆炸 / 抽拔视：只对 schema **已经分开**、且构造上可分离的件出单件小图（如端盖、定子、转子、轴）。壳体、腔体、水套等一体或仅局部的件仍是一层，不要拆筋/凸台。  
crop / image 写的是该件整块子文件，不要在同一件内再拆轮廓、剖面线、紧固件等子层。总图用相对 `href` 引用子文件。有 `source_image` 的总装/剖视（以及用 `crop` 开窗的爆炸图）会在零件层下自动铺 `id="view-source"`（相对 href 整张轮廓，**不是** base64、**不是** clipPath），避免 crop 窗没盖满时入文预览把整机上下裁掉。禁止把整张总装 PNG 再 base64 进总 SVG、禁止用 clipPath 当图层。

## 步骤

### 1. 写 `structure_lineart_compose.yaml`

与 `structure_schema.yaml` 同级。按每个视（与 `structure_lineart_brief.views` 对齐）：

| `layout` | `source` 怎么选 | 槽位 |
|----------|-----------------|------|
| `assembly`（总装/剖视） | 已有轮廓 → **`crop`**，`crop_box` 须包住该件**完整**可见轮廓（含接管、底脚），不要只裁中段 | `slot` 可与 `crop_box` 相同；允许重叠 |
| `exploded`（爆炸/分件） | 仅对 schema 已分开的可分离件用 **`image`** | `slot` 尽量不重叠；可留空让脚本自动网格 |
| 还没图 / `uncertain` | **`placeholder`** | 只占槽，禁止画成已确定结构 |

- `id`/`name` **不得改号改名**，须与 StructureSchema 一致。  
- 本视实际物理部件都要有一条；子特征的标引单独在锚点登记；`uncertain` 只用 placeholder 或不要。  
- `canvas`：有总装轮廓则宽高等于该 PNG；爆炸图可加宽。

### 2. 缺小图时按件出图（仅 `source: image`）

```bash
python skills/patent-disclosure/tools/structure_lineart_compose.py \
  --case-dir "outputs/{案件标识}" --prepare-jobs
```

对 jobs 里缺文件的件：优先从同源 CAD 或可信原图取得该件视图；只有明确授权的示意才按 `image_gen.md` **只画该一件**（白底、黑白结构线、无件号、无邻件）。写入 `image_path`（默认 `lineart_assist/parts/{视}_{id}.png`）。禁止一张图里塞全套零件再假装「单件」。

### 3. 拼装

```bash
python skills/patent-disclosure/tools/structure_lineart_compose.py \
  --case-dir "outputs/{案件标识}"
```

成功则写出各视 `output_svg_path`，并在同目录 `parts/` 下落每件子 SVG。stderr 前缀 `STRUCTURE_LINEART_COMPOSE:`。  
抽查：磁盘上存在 `parts/{视}_{id}.svg`；总 SVG 含 `href="parts/`；总装/crop 视应有 `id="view-source"`。**没有** `src-assembly` / `clipPath` / 整图 `data:image`。每个可见件都有 `id="part-…"` / `data-part-id`。  
出 PNG 预览须用 `svg_screenshot.py`（会把相对 `href` 内联）；不要只把 SVG 文本贴进无路径的 HTML。

### 4. 再叠件号（注入，不压扁零件层）

锚点 YAML 的该视增加：

```yaml
base_svg_path: lineart_assist/总装立体图_composed.svg
image_path: lineart_assist/总装立体图_structure_lineart.png   # 可选；有拼装 SVG 时 overlay 以 SVG 画布为准
output_svg_path: lineart_assist/总装立体图_structure_lineart_callouts.svg
```

然后运行 `structure_callout_overlay.py`，填写最终图体 `paper_width_mm` 及真实目标类别；脚本保留已确认锚点，不按最近墨线改归属。校正件号只改锚点 YAML，**禁止**为纠号而重绘轮廓或重拼零件。需要 PNG 预览再用 `svg_screenshot.py`。

## 自检（内部）

- [ ] 已写 compose YAML；件号与 StructureSchema 一致；一层一件，无自创子件号  
- [ ] 输出为 `parts/{视}_{id}.svg` + 总图相对引用；总装/crop 视有 `view-source`；不是无 `part-*` 的扁图，也不是总图内 clip 整图  
- [ ] 一层一件号，未把筋/齿/螺栓/剖面线拆成独立组  
- [ ] 爆炸视仅对 schema 已有的可分离件用 `image`（先有单件图）；壳体未拆碎；总装 `crop` 未冒充可改轮廓  
- [ ] overlay 注入后零件组仍指向子文件；序号组 id 为 `structure-callouts`  
- [ ] 未对 uncertain 使用 crop/image  
