# 配置用户自己的客户端

公开包没有原 PatSeek 客户端或授权。请自行从合法渠道取得客户端和其依赖，核实使用许可、兼容接口与导入时的行为。服务方入口为 [PatSeek](https://patseek.cn)，本说明不承诺具体下载地址、API 路径或收费标准。

1. 在当前用户自己管理的持久数据目录中创建 `vendor/patseek/`，把合法取得的 Python 客户端及必要依赖放入其中；不要放进会被插件更新替换的缓存。将 `PATSEEK_VENDOR_ROOT` 显式设为这个受信目录的绝对路径。本变量仅由当前用户主动设置时生效，不随插件提供，不自动获得别人的客户端、账号或授权。不要把第三方代码、Key 或案件数据提交到公开仓库。
2. 设置 `PATSEEK_CLIENT_PATH` 为该根目录内部 `.py` 文件的绝对路径。两个变量都只指定路径，不是 API Key。路径支持 `~` 展开，拒绝相对路径；客户端、到受信根之间的每层目录及根本身均不能为符号链接，须由当前用户拥有，不可被组或其他用户写入；必要时由安装者自行调整权限。本适配器不擅自改权限，也不移动旧文件。未设置 `PATSEEK_VENDOR_ROOT` 时仅兼容技能本地 `vendor/`，同时核验至技能根；此旧位置会被插件更新替换，不建议继续使用。
3. 客户端须提供可调用的 `load_cache`、`save_cache`、`recent_calls`、`log_call`、`throttle`、`main`，并支持运行期 `API_KEY`、`CALL_LOG_DISABLED`。适配器不会猜测新接口或使用另一套服务。接口变化时先停止查询并由使用者核实兼容性。
4. 按工作台安装说明配置凭据并从其安全包装器调用。付费查询须继续遵守工作台的案件、查询摘要及预算控制。使用包装器的 `--query-file` 或 `--query-stdin` 输入，不能把原始查询放在系统 argv，也不能把 Key 当参数。

示意配置只包含路径，无凭据：

```bash
export PATSEEK_VENDOR_ROOT="$HOME/.local/share/mechanical-patent-workflow/vendor/patseek"
export PATSEEK_CLIENT_PATH="$PATSEEK_VENDOR_ROOT/client.py"
```

也可选择自定义 `PATENT_TOOLKIT_DATA_HOME` 下的 `vendor/patseek`，但必须自行显式设置以上两个变量；适配器不会自动信任数据根里的任意代码。插件更新保留外部根中的文件。更换客户端及其依赖前重新核验许可、接口、权限和行为。当前实现要求系统提供 POSIX 所有者校验；无法执行该校验的平台会拒绝加载，不自动降低检查。

适配器模块导入时不会读取或加载 vendor。只有工作台注入当前 Key、禁用存储标记及替换全部五个 no-store hooks 后，`main()` 才会在当前进程内加载它，验证接口、转交 hooks 与参数并调用 `main()`。结束时清空双方 `API_KEY` 并恢复进程参数和标准流；不会创建新进程。no-store 仅覆盖约定 hooks，不能约束第三方代码绕开这些 hooks 的行为。

直接运行 `python3 scripts/patseek_client.py --help` 只显示适配器说明；其他直接调用返回非零，提示使用工作台。缺配置或运行失败不会伪装为成功。若外部调用已开始后失败，费用及任务状态可能需要向服务方核实，勿自动重试。

该原创适配器采用 MIT；用户客户端保留其原有许可和使用条件，不能据此获得再分发权。免费 CNIPA 检索另见 `patent-search`。
