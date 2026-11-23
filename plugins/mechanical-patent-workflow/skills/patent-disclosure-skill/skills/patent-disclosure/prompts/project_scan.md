# 项目文档扫描（Step 2）

## 目标

按优先级扫描并提取**可专利化**内容。**根据当前项目结构调整扫描路径**。

## 优先级表

| 优先级 | 文档类型 | 关注内容 |
|--------|----------|----------|
| 1 | 专利相关文档 | 专利点分析、已有交底书、专利申报建议、创新点汇总 |
| 2 | 详细设计/方案文档 | 详细设计、方案讨论、流程图、完整流程、技术对比分析 |
| 3 | 核心实现代码 | 算法与策略实现、业务逻辑与流程编排、数据处理与转换、规则引擎与决策逻辑、接口与集成设计、状态机与调度机制、性能优化与缓存策略、安全与权限控制等（依项目领域灵活识别） |
| 4 | 系统设计文档 | 系统设计、架构说明、模块划分、数据流与控制流 |

## 扫描目标目录模版

执行时按项目实际目录填写：

```
[项目根目录]/
├── [专利或文档目录]/     ← 专利点分析、交底书、申报建议
├── [设计文档目录]/       ← 详细设计、方案讨论、流程图、技术对比
├── [代码目录]/           ← 算法实现、业务逻辑、规则引擎、接口与集成、调度机制等
└── [根目录]/             ← 系统设计、架构说明、模块与数据流
```

## 执行提示

- 大仓库先用搜索 / 语义检索定位关键文件，再精读。
- 记录**引用路径或文件名**，便于在交底书中写「参见某设计」时脱敏表述。
- 凡用户指定的扫描根内出现 **`.tex`**：**先 `Read prompts/tex_scan.md` 再按其执行**（按需加载；无 `.tex` **不要**读该文件）。不可只读某一章、不可用同名 PDF 覆盖源码公式。无 `.tex` 则跳过，不向用户索要。
- 凡用户指定的扫描根内出现 **`.docx` / `.pptx` / `.pdf`**，**必须**按 **「Office 文档与 PDF」** 先转 Markdown 再读，不可跳过或只扫纯文本而漏掉 Office/PDF。`node_modules/`、`dist/`、`build/` 等目录下的文件跳过。不要去扫未指定的整仓。
- 凡扫描树内可能有 CAD / 三维文件，按下方 CAD / STEP 分支分类。用户已要求从模型取图或按模型撰写时，直接使用可用环境解析；只有未授权的可选安装或额外处理才另行确认。

## CAD / STEP（按任务授权与材料需要处理）

1. 先运行 `tools/cad_scan.py -r "<扫描根>" --json` 分类；补材料后按需重扫。用户已要求“按模型撰写”“从模型取图”或等价任务，视为已授权必要的只读解析，不在交底落盘后重复询问是否开启。
2. 先用现有用户持久数据目录中的 `cad-env`、用户通过 `PATENT_SKILL_CAD_VENV` 指定的环境或本机可用 CAD 工具；位置规则见 `tools/README.md`，不要将依赖装入会被更新替换的插件缓存。`tools/cad_venv.py` 可探测隔离环境。可用时直接运行 `tools/run_step_to_views.py --enable-step-parse -i "<model.step>" -o "outputs/{案件}/cad_views"`。不要重复安装依赖；确需新增环境时说明具体需要，按当前授权范围处理。
3. 只是目录里发现 CAD、用户未要求使用且现有正文/原图已足够时，记录可选来源，继续有依据的工作；若 CAD 是核实关键构造所必需，先处理可核内容并说明缺口，不为绕过解析生成结构。
4. 原生 CAD 无可用读取工具时，使用用户已提供的 STEP/可信原图，或具体说明需补哪种中性格式。不得假称已读取原生模型。
5. 生成 `views/*.svg` 及可用 PNG、装配树和 schema/figure_plan 种子。原始 CAD 截图或未处理投影先为 `kind: cad`、`drawing_ready: false`。经同源几何核对、黑白化清理、真实剖切/爆炸及正式布标后，可以作为合格机械线稿；记录 `source_kind: cad`、`source_ref`、`geometry_verified: true`、`drawing_ready: true`。不能将 CAD 全部排除，也不能因来源为 CAD 就直接判合格。
6. 按 `fill_structure_schema.md` 联读同源视图、登记部件及子特征；`image_gen.py` 的 `cad_prepare` 表示处理真实几何，不能转为图生图/文生图重画。缺少关键结构来源时为 `needs_structure_sources`，记录待核，不生成技术事实。

安装环境隔离规则保持：不把 CadQuery 装进主环境，不为建环境强制更换已兼容的 Python 版本。

## 外观线稿（必做）

仅**外观设计**。细则：`prompts/image_gen.md` + `prompts/design_lineart_assist.md`。

- **默认开**；**不问用户**。填 Appearance + figure_plan 后跑 `image_gen.py`，再写 brief / 出门禁 / 生成或选用线稿。
- 线稿只有两条路：材料已有合格 `kind: lineart`，或大模型生成（图生图 → 失败则先描述再文生图）。
- 干净实拍 **和** 线稿都写入交底 Markdown 与 Word。实拍不得标成线稿。CAD 不入文。
- 仅用户明确不要线稿或 `PATENT_SKILL_SKIP_LINEART=1` 才跳过。

## 机械结构线稿（发明与实用新型）

- 成文前按 `fill_structure_schema.md` 建立同案部件、子特征和图计划，先运行 `image_gen.py` 判断来源处理方式。
- 真实 CAD 或可信原图可直接清理成合格线稿；保留同源轮廓、剖切和装配关系。机械附图画法以[CAD取图与附图验收](../../../../mechanical-patent-drawings/references/cad-figures.md)为准。
- CAD 矢量可直接保持零件层并叠标，无须为通过旧“拼装”流程先转 PNG、裁窗或生成新轮廓。已有栅格素材确需分件维护时，再使用 `structure_lineart_compose.md`。
- 只在用户明确要求概念示意且有依据时采用生成式示意，并标明用途；它不能作为 CAD 投影、尺寸或隐藏结构的证据。
- 用户明确不要线稿或 `PATENT_SKILL_SKIP_LINEART=1` 时，记录跳过范围及其影响。

## Office 文档与 PDF（.docx / .pptx / .pdf）：必先转换再读

**格式**：脚本仅支持 OOXML（**`.docx` / `.pptx`**）和 PDF（**`.pdf`**）。旧版 **`.doc` / `.ppt`** 须先在 Office / WPS 中**另存为**新格式后再走下列流程。

Agent **不得**因「只能舒适读取文本」而**遗漏**扫描根内的 Word / PPT / PDF：**必须先转为 Markdown 再纳入扫描**，不能只扫 `.md` 与源码。范围由用户指定的扫描目录决定，不要按文件名自行决定转或不转。

1. **发现**：在**用户指定的扫描目录**内 **`Glob` 或列举** `*.docx`、`*.pptx`、`*.pdf`（含子目录，如 `docs/sample_*.docx`）。跳过 `node_modules/`、`dist/`、`build/`、`.next/` 等。
2. **转换（本仓库脚本）**：对每个文件执行（路径相对本技能仓库根）：

   ```bash
   python skills/patent-disclosure/tools/docx_to_md.py -i "<路径>/<名>.docx" -o "<同目录或 docs>/<名>.md"
   python skills/patent-disclosure/tools/pptx_to_md.py -i "<路径>/<名>.pptx" -o "<同目录或 docs>/<名>.md"
   python skills/patent-disclosure/tools/pdf_to_md.py -i "<路径>/<名>.pdf" -o "<同目录或 docs>/<名>.md"
   ```

   Word / PPT 需已 `pip install -r requirements.txt`。PDF 为可选依赖：`pip install -r skills/patent-disclosure/tools/requirements-pdf.txt`（pymupdf）。未装 pymupdf 时按脚本 stderr 提示安装，**不要**改去直接 Read 二进制 PDF。输出旁会生成 **`{md 主名}_media/`**，内为嵌入图，**以生成的 `.md` 正文与图片引用为扫描依据**（PDF 的图跟在对应页标题下）。
3. **再读**：**`Read`** 上述新生成的 `.md`（及必要时扫一眼 `_media` 文件名用于脱敏引用），与原有 `.md`、代码**同等对待**，摘要进专利点材料表。
4. **解析重点**：表格、编号列表、**PPT 每页标题与正文**、**Word 修订区以外的正文**、**备注**（`pptx_to_md` 会写入「备注」小节）、**PDF 每页正文与当页图片**——均属可专利化叙述来源。PDF 文本层对公式不可靠；同目录有 `.tex` 时按 **`prompts/tex_scan.md`**（公式以源码为准，勿把 PDF 转 md 当公式再读一遍）。

## 图片与裸图目录（默认不识图）

- **`sample_assets/`**、`node_modules/`、`dist/`、`build/`、`.next/`、`src/assets/`、前端切图等目录下的独立 `.png` / `.jpg` / `.webp`：**不作为** Step 2 必须逐个打开的对象。
- **例外（才 Read 识图）**：用户**点名**某图片路径或说「这张图是场景示意，补充到交底书」；或某图已嵌在已转换 Office 的 `_media` 且正文当技术示意图引用。
- Word/PPT/PDF 转换后，嵌入图已在 **`![](相对路径)`** 中体现，**以 Markdown 文本扫描为主**即可；不要为了找图去扫整个前端工程。

点名之后：理解图上对象与图例 → 判别（技术示意图 / 拓扑 / 流程照片 / 结构 / 界面截屏 / 图标切图 / 营销场景）→ 匹配章节。图标、切图、营销场景不入文并说明原因。技术示意图拷到案件 `assets/`，在 3.1 或第六章编号嵌入，不要改画。这与外观 `photo_scene`（棚拍/包装默认不入文）不是一类，不要套那条挡技术环境图。

## 按专利类型加扫（实用 / 外观）

当前类型为**实用新型**或**外观设计**时，在通用优先级之外**额外**关注：

| 类型 | 加扫重点 |
|------|----------|
| 实用新型 | 装配图、爆炸图、结构说明、`structure_*.yaml/json`、零件表；再按 `prompts/fill_structure_schema.md` 识图填表并写出 **`figure_plan.yaml`** |
| 外观设计 | 按要点落面收正投影/立体图（非默认六视；官方全称）、效果图、色彩说明、`appearance_*.yaml/json`；再按 `prompts/fill_appearance_schema.md` 与 `references/design_view_cnipa.md` 填表并写出 **`figure_plan.yaml`** |

独立结构/外观附图（用户点名或 schema `source_images`）**需要** Read 识图，不适用下方「sample_assets 跳过」惯例。

## 示例案件 `knowledge/`（练习时勿漏）

### 发明 · `skills/patent-disclosure/examples/example_batch_job_scheduler/knowledge/`

| 路径 | 动作 |
|------|------|
| `docs/architecture.md` | 直接 Read |
| `tex/main.tex` 及 `\input` 链 | 先 **`Read prompts/tex_scan.md`**，按其引用图处理（见 `tex/README.md`），并写 `tex_formula_inventory.md` |
| `docs/sample_architecture_review.docx` | **先** `tools/docx_to_md.py` → 再 Read 生成的 `.md` |
| `docs/sample_scheduler_deck.pptx` | **先** `tools/pptx_to_md.py` → 再 Read 生成的 `.md` |
| `docs/sample_assets/*.png` | **跳过**单独精读（内容已由 Office 内嵌图 + 转换 MD 覆盖） |

### 实用新型 · `skills/patent-disclosure/examples/example_utility_model_ev_powertrain/knowledge/`

| 路径 | 动作 |
|------|------|
| `docs/structure_brief.md` | Read（主材料；部件表与建议剖视/爆炸/局部） |
| `assets/*.jpg` | 展台实拍，**须**识图打分；`kind` 为 `photo_clean` / `photo_scene`，**不入文**；本案例无合格线稿，先按brief记录可信图源与待核范围，不自动生成机械结构事实 |

教学用 STEP 不在本示例：见 `skills/patent-disclosure/tests/fixtures/cad/demo_snap_plate.step`（`cad_scan` / `gen_demo_snap_step.py`）。

### 外观 · `skills/patent-disclosure/examples/example_design_desk_lamp/knowledge/`

| 路径 | 动作 |
|------|------|
| `docs/design_brief.md` | Read |
| `assets/*.{jpg,png}` | **须**识图填 AppearanceSchema + **`figure_plan.yaml`**（教学用；勿依赖预填 yaml；场景图默认低优先级） |
