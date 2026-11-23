# 内置 mermaid（供 Playwright 出图，无需 Node / mmdc）

| 文件 | 版本 | 来源 |
|------|------|------|
| `mermaid.min.js` | **11.4.1** | https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js |

与历史 `@mermaid-js/mermaid-cli` 11.4.x 同系列。出图由 `tools/mermaid_render.py` 经 Playwright 加载本文件，**禁止**运行时从 CDN 再拉。

升级时请同步改本表版本号，并替换 `mermaid.min.js`。

公开分发副本保留JS内的捆绑版权声明，完整许可文本及对应原始来源另见`licenses/`目录。不要将本项目许可证解释为替代这些第三方许可。
