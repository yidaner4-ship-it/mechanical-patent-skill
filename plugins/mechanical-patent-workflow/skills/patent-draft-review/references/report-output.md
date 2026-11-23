# 离线报告输出

执行 `python3 scripts/render_review.py --input review.json --output review.html`；支持 `-i/-o`、`--json/--out` 别名，输入或输出用 `-` 表示标准输入或标准输出。输入文件与输出文件不得相同。

只需要 Python 3.9+ 标准库。脚本不加载外部资源、执行输入代码或联网。报告为静态 HTML；未知字段在完整记录中保留。生成器不判断严重程度、意见是否关闭或申请是否通过，状态完全来自提供的记录。

格式及字段见[公开记录模式](template-schema.md)，交付检查见[报告验收](report-validation.md)。
