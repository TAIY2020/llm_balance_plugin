# LLM 平台余额查询插件 (LLM Balance Plugin)

💰 **一个让麦麦通过 `/余额` 一条命令查看你 DeepSeek、硅基流动和阿里云（百炼扣费账户）余额的小工具。**

> 本版本基于 **MaiBot SDK v2** 开发，使用 `PluginConfigBase` 强类型配置模型，支持配置热重载和 Web UI 配置。**推荐通过 Web UI 修改配置**。

## ✨ 功能特性

- **一条命令查所有平台**: `/余额` 同时去问已启用的平台，结果汇总成一条消息发出来。
- **支持多个余额来源**: **DeepSeek**、**SiliconFlow（硅基流动）** 和 **阿里云账号余额** 开箱即用，填好凭证就能用。
- **支持百炼扣费账户余额**: 通过阿里云费用中心 `QueryAccountBalance` 查询账号级可用额度，可用于判断百炼后付费扣费账户是否还有余额。
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

**⚠️ 重要安全提示**（Web UI 同名项）:

- **「管理员列表」**: 允许使用 `/余额` 命令的 QQ 号字符串列表。**默认 `admin_only = true` + 列表为空** 意味着没人能查，需要你自己加上自己的 QQ 号。例如：`["12345", "67890"]`。
- **「API Key / AccessKey」**: 各平台凭证都是**敏感信息**，建议通过 Web UI 配置（密码框会自动遮挡输入）。不要把带有真实凭证的 `config.toml` 提交到公开仓库；如果怀疑泄露，请立刻到对应平台后台轮换或撤销该凭证。
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
| API 基地址（`base_url`） | 各平台默认 | 直连受限时可换成代理或自建网关地址。**必须是 HTTPS**：为保护 API Key，插件会拒绝 `http://` 地址并报「配置错误」，自建网关也需启用 HTTPS |

#### 平台配置（阿里云 / 百炼扣费账户）

阿里云余额查询使用的是费用中心 BSSOpenAPI：`QueryAccountBalance`。它查询的是**阿里云账号级余额**，可用于判断百炼后付费扣费账户的可用额度；它**不等同于**百炼免费额度、Token 剩余额度或资源包剩余量。

| 配置项（Web UI / TOML） | 默认值 | 说明 |
| ------ | ------ | ---- |
| 启用阿里云余额（`enabled`） | `false` | 是否启用阿里云账号余额查询 |
| AccessKey ID（`access_key_id`） | `""` | 阿里云 RAM 用户的 AccessKey ID |
| AccessKey Secret（`access_key_secret`） | `""` | 阿里云 RAM 用户的 AccessKey Secret |
| Endpoint（`endpoint`） | `"https://business.aliyuncs.com"` | 阿里云费用中心 BSSOpenAPI Endpoint，一般保持默认即可 |

阿里云调用权限：用于查询的 RAM 用户需要允许调用 `QueryAccountBalance`。推荐使用下面的最小权限策略，而不是直接绑定 `AliyunBSSReadOnlyAccess`。

### API Key / AccessKey 在哪里拿？

- **DeepSeek**: 登录 [DeepSeek 控制台](https://platform.deepseek.com/api_keys) → 「API Keys」→ 「创建 API Key」
- **SiliconFlow（硅基流动）**: 登录 [硅基流动控制台](https://cloud.siliconflow.cn/account/ak) → 「API 密钥」→ 「新建 API 密钥」

#### 阿里云 `access_key_id` / `access_key_secret` 获取方式

推荐为这个插件单独创建一个 RAM 用户，不建议直接使用主账号 AccessKey。

1. 登录阿里云控制台，确认当前账号就是百炼实际扣费的阿里云账号，或其有权限访问该账号的费用中心。
2. 进入 [RAM 访问控制](https://ram.console.aliyun.com/users/create)，新建 RAM 用户
3. 填写登录名称，比如 `llm_balance`，勾选【使用永久 AccessKey 访问】，再点击【我确认必须创建 AccessKey】，点击确定
4. 创建完成后会得到两项：
   - `AccessKey ID`：填写到 WebUI 插件配置 `access_key_id`
   - `AccessKey Secret`：填写到 WebUI 插件配置 `access_key_secret`
5. 创建一个最小权限自定义策略，只允许查询账户余额。点击左侧 **RAM 访问控制** → **权限管理** → **权限策略** → **创建权限策略**，选择 脚本编辑，填入：

```json
{
  "Version": "1",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "bss:DescribeAcccount"
      ],
      "Resource": "*"
    }
  ]
}
```

> 说明：根据阿里云 `QueryAccountBalance` 官方文档的「授权信息」，该接口在 RAM 权限策略中的 Action 是 `bss:DescribeAcccount`。这里的 `Acccount` 是官方文档给出的拼写，请不要自行改成 `Account`。

策略名称可以写成：`LLMBalanceQueryAccountBalanceOnly`。

6. 返回 [RAM 用户列表](https://ram.console.aliyun.com/users)，点击刚添加的 RAM 用户右侧的【新增授权】，点击【所有策略类型】，下拉列表选择【自定义策略】或直接搜索刚创建的策略名，勾选 `LLMBalanceQueryAccountBalanceOnly`，点击【确认新增授权】。
7. 然后在 WebUI 中启用阿里百炼余额查询，保存配置即可

> 注意：AccessKey Secret 只在创建时完整显示一次，请立刻复制并妥善保存。若遗失，只能重新创建或轮换。

---

## 🔒 安全说明

- DeepSeek / SiliconFlow / 阿里云访问的都是**官方余额查询接口**，不会触发模型调用计费。
- API Key 和 AccessKey 保存在本地 `config.toml` 中，请确保该文件不会被意外泄露（不要 commit 到 git、不要发给别人）。
- 若怀疑凭证泄漏，请立刻到对应平台后台**更换/撤销**该凭证；阿里云 AccessKey 可在 RAM 控制台禁用、删除或轮换。
- SiliconFlow 平台的官方查询 api 返回结果可能因为各种券太多，显示有差异，请以官方控制台为准。

---

## 📝 注意事项

- **额度敏感**: 不要把「仅管理员可用」关掉之后公开命令——虽然查询本身免费，但仍可能被恶意刷接口。
- **请求超时**: 默认 10 秒；某家平台响应较慢可以把「请求超时（秒）」调高。

Enjoy! 🎉
