# LLM 平台余额查询插件 (LLM Balance Plugin)

💰 **一个让麦麦通过 `.余额` 一条命令查看你 DeepSeek 和硅基流动账号余额的小工具。**

> 本版本基于 **MaiBot SDK v2** 开发，使用 `PluginConfigBase` 强类型配置模型，支持配置热重载和 Web UI 配置。**推荐通过 Web UI 修改配置**。

## ✨ 功能特性

- **一条命令查所有平台**: `.余额` 同时去问已启用的平台，结果汇总成一条消息发出来。
- **支持两家主流平台**: **DeepSeek** 和 **SiliconFlow（硅基流动）** 开箱即用，填好 API Key 就能用。
- **图片卡片输出**: 默认把结果渲染成一张漂亮的卡片图片，带状态徽标、币种分组，比纯文本好看得多。
- **权限控制**: 默认仅指定的管理员能查，避免被群友刷接口。
- **配置热重载**: 通过 Web UI 修改配置后无需重启，插件会自动应用新配置。

---

## 🚀 快速开始

### 1. 安装

- 自动安装：通过 Web UI 在插件市场下载安装（**推荐**）
- 手动安装：下载 `llm_balance_plugin` 文件夹放入麦麦主程序的 `plugins` 目录下，然后重启主程序即可完成插件的注册和加载。

### 2. 环境要求

- **MaiBot 主程序**: v1.0.0+
- **MaiBot SDK**: v2.0.0+

### 3. 配置

首次启动麦麦后，插件会在其目录下自动生成 `config.toml`，开箱即用。**推荐通过 Web UI 在线修改配置**，修改后会自动热重载生效；下面的字段名仅供进阶用户直接编辑配置文件时参考。

**默认配置示例**:

```toml
[plugin]
name = "llm_balance_plugin"
version = "1.3.1"
config_version = "1.3.1"
enabled = true

[settings]
timeout = 10
admin_only = true
admin_user_ids = []
# 输出格式：text 纯文字 / image 卡片图片 / both 两个都发
output_format = "image"

[deepseek]
enabled = false
api_key = ""
base_url = "https://api.deepseek.com"

[siliconflow]
enabled = false
api_key = ""
base_url = "https://api.siliconflow.cn"
```

**⚠️ 重要安全提示**（Web UI 同名项）:

- **「管理员列表」**: 允许使用 `/余额` 命令的 QQ 号字符串列表。**默认 `admin_only = true` + 列表为空** 意味着没人能查，需要你自己加上自己的 QQ 号。例如：`["12345", "67890"]`。
- **「API Key」**: 各平台的 API Key 是**敏感信息**，建议通过 Web UI 配置（密码框会自动遮挡输入）。不要把带有真实 Key 的 `config.toml` 提交到公开仓库；如果怀疑泄露，请立刻到对应平台后台轮换或撤销该 Key。
- **「仅管理员可用」**: 默认开启。**强烈建议保留**——这玩意儿会暴露你账号的真实余额，不该让群友能查。

### 配置项说明

下表第一列为 Web UI 中显示的配置项名称（括号内为对应的 TOML 字段名）。

#### 通用设置

| 配置项（Web UI / TOML） | 默认值 | 说明 |
| ------ | ------ | ---- |
| 请求超时（秒）（`timeout`） | `10` | 单个平台查询的最长等待时间（1~60 秒） |
| 仅管理员可用（`admin_only`） | `true` | 是否只允许管理员查余额 |
| 管理员列表（`admin_user_ids`） | `[]` | 允许查余额的 QQ 号列表，仅在「仅管理员可用」打开时生效 |
| 输出格式（`output_format`） | `"image"` | 输出格式：`text` 纯文字 / `image` 卡片图片 / `both` 两个都发 |

#### 平台配置（DeepSeek / SiliconFlow）

| 配置项（Web UI / TOML） | 默认值 | 说明 |
| ------ | ------ | ---- |
| 启用 XXX（`enabled`） | `false` | 是否启用该平台 |
| API Key（`api_key`） | `""` | 平台官方 API Key |
| API 基地址（`base_url`） | 各平台默认 | 直连受限时可换成代理或自建网关地址 |

### API Key 在哪里拿？

- **DeepSeek**: 登录 [DeepSeek 控制台](https://platform.deepseek.com/api_keys) → 「API Keys」→ 「创建 API Key」
- **SiliconFlow（硅基流动）**: 登录 [硅基流动控制台](https://cloud.siliconflow.cn/account/ak) → 「API 密钥」→ 「新建 API 密钥」

---

## ❓ 常见问题

### Q：卡片渲染失败怎么办？

会自动降级成文字模式，并发一条 `⚠️ 卡片渲染失败，已回退为文本模式` 的提示。常见原因：

- 主程序没提供 `render.html2png` 能力（参考 SDK 文档 Render 章节）
- 截图所需的浏览器组件没装好

### Q：API Key 怎么填进去最安全？

**强烈建议通过 Web UI 配置**，密码框会自动遮挡输入。直接改 `config.toml` 也行，但要注意：

- 不要把带有真实 Key 的 `config.toml` 提交到公开仓库（Git 仓库要把它加进 `.gitignore`）
- 怀疑泄露立即到对应平台后台**更换/撤销** Key

---

## 🔒 安全说明

- 两个平台访问的都是**官方免费的余额查询接口**，不会触发计费请求。
- API Key 保存在本地 `config.toml` 中，请确保该文件不会被意外泄露（不要 commit 到 git、不要发给别人）。
- 若怀疑 Key 泄漏，请立刻到对应平台后台**更换/撤销**该 Key。

---

## 📝 注意事项

- **额度敏感**: 不要把「仅管理员可用」关掉之后公开命令——虽然查询本身免费，但仍可能被恶意刷接口。
- **请求超时**: 默认 10 秒；某家平台响应较慢可以把「请求超时（秒）」调高。

Enjoy! 🎉
