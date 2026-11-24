# 布局冲突预筛

当附图有可取得的最终二维矢量和字框时，用标准库脚本定位压字、贴线或实心箭身覆盖。它不读取三维模型，也不代替最终 Word、PDF 逐根目视。人工覆盖布局坐标、换字体或比例、更新几何后，重新导出最终纸面场景再运行，不能对覆盖前的坐标验收。

从技能目录运行，例如：

~~~sh
python3 scripts/audit_scene_clearance.py scene.json --clearance-mm 0.7 --out layout-audit.json
python3 scripts/test_scene_clearance.py
~~~

0.7mm仅为命令示例；阈值由当前图幅、字号、线宽和项目要求确定，不是通用合格值。曲线展开容差可用 --curve-tolerance-mm 指定，默认0.01mm；边界接近容差时回查原始矢量和渲染。命令退出码0表示所给输入没有预警或缺测，1表示存在预警或缺测，2表示输入无效，均不能作为完整质检通过码。

## JSON契约

所有坐标和线宽均为最终纸面毫米，已应用视角、爆炸位移、裁剪、比例及平移。每个图号一页，各页图元和标记ID唯一。

~~~json
{
  "schema_version": 1,
  "units": "mm",
  "pages": [{
    "figure": 1,
    "paths": [
      {"id":"edge-a","kind":"polyline","points":[[20,10],[20,40]],"width_mm":0.2,"role":"structure"},
      {"id":"leader-a","kind":"cubic","points":[[20,20],[24,20],[25,23],[29,23]],"width_mm":0.18,"role":"leader","owner":"label-a"}
    ],
    "labels":[{
      "id":"label-a","text":"42","box":[30,21,35,25],"bounds_source":"measured","target":[20,20]
    }]
  }]
}
~~~

- paths.kind支持polyline、四点cubic、闭合polygon。points是中心线路径，width_mm是实际线宽。role取structure、leader、arrow、hatch、assembly、break或other。实心三角用polygon、role为arrow、filled为true表示，工具同时查填充区域与边界。不能只提供三角边框而把实心覆盖漏掉。
- labels.box为完整文字的[xmin,ymin,xmax,ymax]。使用实际导出字体测量，包含全部字符、实际字宽和字形范围；必要时取渲染字形及字体度量的并集。bounds_source为measured表示调用者已取得测量数据；估算可填estimated，未说明的按provided处理，两者都会保留缺测提示。不能把估算框改名为measured来消除预警。
- owner仅保留组成部分的来源信息，例如三角与其引线，不会免除同owner路径的接触检查。接合点和真实结构端点也可能产生预警，须逐处人工辨认；普通结构路径不应冒用标引owner。
- 可在页级或标记级提供exceptions数组，记录拟保留交叉的理由和人工证据。它们只随报告输出，不会消除冲突。真实结构端点接触也可能产生预警，须逐处辨认；不能据一个正确端点把同一对路径的其余部分一并豁免。

## 结果与边界

工具检查字框与所有已供路径、字框之间的净距，以及涉及引线或箭身的路径对净距。中心线距离扣除两条线的半线宽后才是线条净距。路径对报告保留最差净距和closest_points兼容字段，同时以worst保存最差记录，以conflict_locations保留多个空间分开的冲突。每个位置包含相关路径的segment_indices和最接近坐标；折线索引对应其原段，三次曲线索引对应展开后的段，填充区域本身的边索引可为空。填充箭身还逐结构段记录区域内部的occupied_point，因此一个合法尖端接触不能吞掉同一结构折线在箭身其他位置的穿越。

距离至多min(curve_tolerance_mm,0.05)毫米的同类位置会聚合预警，并在contributing_segment_pairs中保留段对来源；这不修改源图元，也不是净距合格阈值。每对路径默认最多保留128个位置，可用 --max-conflict-locations 改变。发生限量时明确输出truncated为true，candidate_conflict_count保留遇到的候选数量；截断报告不能声称穷举了全部交会，须扩大限额或结合原图逐处复核。任何contact都不会自动豁免，仍需查看整根引线及整支箭身。曲线自交、CAD落点归属、自遮挡与互遮挡、剖切材料区判定均明确标为本工具未核。

incomplete_inputs表示缺矢量、缺标记清单或字框不是测量数据；layout_candidates_found表示发现预警；no_layout_candidates仅表示所供二维图元未触发预筛。报告总状态始终要求人工和几何复核。工具不会判断模型制造可行性，也不会恢复被预先擦掉的断面线；仍须按真实材料区和布标前原始hatch与成品逐段对看。禁止因工具提示而擦白、mask或剪断结构线和断面线。

随包回归全部为合成图元，包括：落点正确但字框压线、中心线不交而线宽重叠、曲线中段压字、填充箭身包住文字或短结构线、同一结构折线先碰尖端再穿箭身、同owner不免除接触、限量显式标记、例外不抹掉预警、缺测状态及平移后的净距一致性。它们验证预筛行为，不构成任何案件的CAD或图面验收。
