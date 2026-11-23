# 组件来源与公开分发范围

本合集不统一替换各组件已有许可证。技能规则、公开兼容入口、外部服务和第三方程序分别管理；仓库公开不代表商业应用、账号或未附分发许可组件已经获准转让。

| 组件 | 随包范围与许可 |
| --- | --- |
| `patent-disclosure-skill` | 保留原包MIT许可证及版权；仅导出可迁移副本，省略缓存、本机安装记录、截图及演示照片 |
| `patent-search` | 保留原包MIT许可证及版权 |
| 建模、机械附图、工作台、申晟QA | 发布者的可复用定制规则及工具；个人授权改为由当前使用者决定。公开图例为同参数通用曲线，不含客户原图 |
| `documents`、`pdf`、`spreadsheets` | 本项目独立公开辅助版本，不是官方受限缓存包；新增辅助代码的MIT许可见对应目录 |
| `patent-draft-review` | 本项目独立公开兼容实现，不是第三方上游原包，不承诺上游全部功能或数据模式一致 |
| `patseek-patent-search` | 本项目独立公开外部客户端适配；不含第三方原客户端、密钥或积分，必须由使用者自行合法取得兼容客户端并授权使用 |

第三方原审稿组件来源供识别：[patent-review-kit](https://github.com/KrisMiao97/patent-review-kit)。未将该仓库源码或文档复制入本合集。PatSeek服务和客户端按[服务方](https://patseek.cn)实际提供的授权和接口配置，不能把原作者安装过客户端视为下载者已经获得分发或使用许可。

`patent-disclosure-skill`中已有前端vendor保留其随文件声明的许可证与署名，包括Mermaid及其捆绑依赖、Three.js。Mermaid 11.4.1的MIT全文及内嵌声明涉及的DOMPurify双重许可、js-yaml、Lodash、Cytoscape许可全文放在`skills/patent-disclosure-skill/skills/patent-disclosure/tools/vendor/licenses/`，来源记录见该目录的`SOURCES.json`；原JS尾部版权声明保留。Three.js的完整许可随其原vendor文件保留。其他公开Python依赖按requirements文件由使用者安装，本合集不复制其运行环境。LibreOffice、Poppler、Fusion和其他CAD应用、浏览器、连接器及账号不随包分发。

官方缓存Word材料存在禁止第三方分发条款，因此没有复制；官方PDF缓存和其他未明确许可的本机组件也没有直接复制。这里的独立辅助版本只实现其文档列明的通用功能，不能当作官方产品或商业服务的再发布。

测试使用独立的合成夹具。公开包不包含本机AGENTS背景、客户案卷、生产模型、个人模板、凭据、虚拟环境、系统缓存或内部审核日志。
