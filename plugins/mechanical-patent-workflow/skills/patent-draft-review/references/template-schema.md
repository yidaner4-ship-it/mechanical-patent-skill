# 公开记录模式

输入为 UTF-8 JSON 对象或数组。建议对象如下；所有字段可选，空字段表示未提供，不能由记录器推定通过。

```json
{
  "title": "某案审阅记录",
  "review_status": "待整改",
  "scope": ["权利要求和说明书", "附图逐根目视"],
  "files": [{"name": "申请稿.docx", "sha256": "按实际文件填写"}],
  "checks": {"independent_review": "已执行", "visual_review": "部分未核"},
  "issues": [{
    "id": "R001",
    "severity": "重要",
    "location": "权利要求2；图3标号12",
    "evidence": "实际材料中的定位证据",
    "impact": "缺少配合关系导致作用链无法确认",
    "recommendation": "请补充原始结构依据后核定措辞",
    "status": "待确认",
    "recheck": "尚无新增依据"
  }],
  "unverified": ["图4局部不清晰，标号18落点未核"]
}
```

记录器兼容 `issues`、`findings`、`problems` 为问题列表，以及 `id/issue_id`、`severity/priority`、`location/where` 等常见显示别名。顶层数组视作问题列表。每条完整输入及所有顶层未知字段均在报告中保留并转义展示，不能视作上游其他模式已完整兼容。

文件名及摘要可用于对应交付版本。报告将展示输入中所有信息：将内部路径、姓名等移至不交付的内部记录，交付用 JSON 只保留用户核定内容。脚本不自行删改事实字段。
