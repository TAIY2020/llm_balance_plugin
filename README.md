# LLM 平台余额查询插件 (LLM Balance Plugin)

💰 **一个让麦麦通过 `/余额` 一条命令查看你 DeepSeek、硅基流动、阿里云（百炼扣费账户）以及自定义源（New API / One API、DeepSeek 风格、JSON 映射）余额的小工具。**

> 本版本基于 **MaiBot SDK v2** 开发，使用 `PluginConfigBase` 强类型配置模型，支持配置热重载和 Web UI 配置。**推荐通过 Web UI 修改配置**。

> [!IMPORTANT]
> **v1.7.0 起 `/余额` 改由主程序「命令管理」统一鉴权**，插件自己的「仅管理员可用 / 管理员列表」已弃用、不再生效。从旧版本升级时，请先把原来列表里的 QQ 号以 `qq:号码` 的格式加入主程序管理员（或在「命令管理」里给 `/余额` 单独授权），否则升级后只有 WebUI 本地控制台能查询。详见下方「权限配置」。

## ✨ 功能特性

- **一条命令查所有平台**: `/余额` 同时去问已启用的平台，结果汇总成一条消息发出来。
- **支持多个余额来源**: **DeepSeek** 和 **阿里云账号余额** 开箱即用，填好凭证就能用。**SiliconFlow（硅基流动）** 见下方说明——该平台已停止通过 API 提供余额数据。
- **自定义源**: 提供 3 个独立槽位，协议可选 **New API / One API**、**DeepSeek `/user/balance` 风格**，或 **通用 JSON 字段映射**（点分路径，如 `data.quota`）。
- **支持百炼扣费账户余额**: 通过阿里云费用中心 `QueryAccountBalance` 查询账号级可用额度，可用于判断百炼后付费扣费账户是否还有余额。
- **图片卡片输出**: 默认把结果渲染成一张漂亮的卡片图片，带状态徽标、币种分组，比纯文本好看得多。
- **配置页一键查询**: 在 Web UI 插件配置页点「立即查询余额」，各平台余额与错误直接显示在页面上，填完凭证就能当场验证，不用再去聊天里发命令。
- **权限控制**: 由主程序「命令管理」统一鉴权，默认只有主程序管理员能查，可按用户或聊天单独授权。
- **配置热重载**: 通过 Web UI 修改配置后无需重启，插件会自动应用新配置。

---

## 🚀 快速开始

### 1. 安装

- 自动安装：通过 Web UI 在插件市场下载安装（**推荐**）
- 手动安装：下载 `llm_balance_plugin` 文件夹放入麦麦主程序的 `plugins` 目录下，然后重启主程序即可完成插件的注册和加载。

### 2. 环境要求

- **MaiBot 主程序**: v1.3.17+（配置页运行时控件需要此版本）
- **MaiBot SDK**: v2.19.0+

### 3. 配置

首次启动麦麦后，插件会在其目录下自动生成 `config.toml`，开箱即用。**推荐通过 Web UI 在线修改配置**，修改后会自动热重载生效；下面的字段名仅供进阶用户直接编辑配置文件时参考。

**⚠️ 重要安全提示**（Web UI 同名项）:

- **「API Key / AccessKey」**: 各平台凭证都是**敏感信息**，建议通过 Web UI 配置（密码框会自动遮挡输入）。不要把带有真实凭证的 `config.toml` 提交到公开仓库；如果怀疑泄露，请立刻到对应平台后台轮换或撤销该凭证。
- **使用权限**: `/余额` 会暴露你账号的真实余额，**不建议把它授权给整个群**。

### 权限配置

`/余额` 是主程序的**受保护命令**，执行前由主程序按「命令管理」检查，插件本身不再判断：

- **主程序管理员**（主程序配置「插件 → 插件管理权限」，格式 `qq:123456789`）可以直接使用。
- 在 Web UI「命令管理」里找到 `/余额`（ID `TAIY2020.llm-balance-plugin.llm_balance_query`），可以额外放行指定用户或指定聊天。
- WebUI 本地控制台的发言自动有权限；其他插件代为投递的消息一律没有权限。
- 没有权限时由主程序回复「你没有权限使用此命令。」，开启主程序的「不显示无权限提示」后静默拦截。

插件配置页的「/余额 使用权限」一栏会显示当前有几位管理员、本命令额外授权了多少用户和聊天，并列出旧版「管理员列表」里**尚未迁移**的 QQ 号。迁移完成后可把旧列表清空。

**从 v1.6.x 升级**：旧的 `admin_only` / `admin_user_ids` 保留在配置里只用于迁移提示，已不再生效。原来 `admin_only = false`（所有人可用）的部署会变为仅管理员可用；如需放开给某个群，请在「命令管理」中为 `/余额` 额外授权该聊天。

### 配置页一键查询

插件配置页顶部提供「立即查询余额」按钮，以及每个已启用平台的状态行：

- 查询的是**已保存**的配置，未保存的修改不会生效；改完凭证请先保存再点查询。
- 查询在后台进行，结果约 2 秒内自动刷新到页面；查询中按钮会暂时变灰。
- 与 `/余额` 命令共用同一轮请求，同时查询不会重复请求平台。
- 修改插件配置后旧结果会被清除，需要重新查询。结果只保存在内存里，不写入配置文件，插件重载后清空。

### 配置项说明

下表第一列为 Web UI 中显示的配置项名称（括号内为对应的 TOML 字段名）。

#### 通用设置

| 配置项（Web UI / TOML） | 默认值 | 说明 |
| ------ | ------ | ---- |
| 请求超时（秒）（`timeout`） | `10` | 单个平台查询的最长等待时间（1~60 秒） |
| 仅管理员可用（已弃用）（`admin_only`） | `true` | 已不再生效，见「权限配置」 |
| 管理员列表（已弃用）（`admin_user_ids`） | `[]` | 已不再生效，仅用于在配置页和日志里提示迁移 |
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

#### 平台配置（自定义源 1 / 2 / 3）

Web UI 无法展开「列表套对象」的嵌套配置，因此自定义源做成 3 个顶层槽位：`[custom_1]`、`[custom_2]`、`[custom_3]`，字段相同。未启用的槽位在配置页余额状态里会隐藏。

| 配置项（Web UI / TOML） | 默认值 | 说明 |
| ------ | ------ | ---- |
| 启用此自定义源（`enabled`） | `false` | 是否启用该槽位 |
| 显示名称（`name`） | `""` | 卡片和 `/余额` 文本里显示的名字；留空则为「自定义源 N」 |
| 协议（`protocol`） | `"newapi"` | `newapi`（New API / One API）、`deepseek`（`/user/balance` 风格）、`json`（自定路径 + JSON 字段） |
| API Key / 访问令牌（`api_key`） | `""` | **New API 请填系统访问令牌**，不是模型调用用的 `sk-` Key |
| API 基地址（`base_url`） | `""` | 必须是 HTTPS。New API 可填站点根或 `.../v1`（去掉末尾 `/v1`、`/api`）；deepseek 会去掉末尾 `/v1` |
| 查询路径（`path`） | `""` | 留空用协议默认：newapi=`/api/user/self`，deepseek=`/user/balance`；json **必须填写** |
| New-Api-User（`new_api_user`） | `""` | 部分 New API 站点要求把用户 ID 放进请求头；填写后会同时发送 `New-Api-User` 和 `New-API-User` |
| 额度换算除数（`quota_divisor`） | `0` | `0`=按协议默认。newapi 默认 `500000`（50 万额度 = 1 美元）；deepseek / json 默认不换算。填 `1` 表示不换算 |
| 展示币种（`currency`） | `""` | 留空则 newapi=`USD`，deepseek=接口返回，json=`CNY` |
| JSON 路径（主金额）（`json_total`） | `""` | 点分路径，如 `data.quota`。newapi 默认 `data.quota`；json 至少填一个金额路径。**deepseek 协议忽略 JSON 路径**，固定解析 `balance_infos` |
| JSON 路径（第二金额）（`json_granted`） | `""` | newapi 默认 `data.used_quota`（已用额度） |
| JSON 路径（第三金额）（`json_topped`） | `""` | 可选附加金额 |
| JSON 路径（成功标志）（`json_success`） | `""` | 如 `success`。值为 false/0 时按业务失败处理；留空时 newapi / json 仍检查根级 `success` |

协议对照：

- **newapi**：`GET {站点根}/api/user/self`，Bearer 鉴权。读 `data.quota` / `data.used_quota`，再除以换算除数。`oneapi` / `one-api` 会当成 `newapi`。
- **deepseek**：`GET {base_url}/user/balance`，按官方 DeepSeek 的 `is_available` + `balance_infos`（多币种）解析。基地址末尾的 `/v1` 会去掉。给兼容该接口的网关用；官方 DeepSeek 请继续用上面的「DeepSeek」节。
- **json**：同样 GET + Bearer，按你填的路径取值。可用来对接字段名不同、但仍然是「一个 HTTPS JSON 对象」的余额口。

> **常见填错**：New API 控制台里「API 密钥」（`sk-...`）只能调模型，查余额要到「个人设置 → 安全设置 → 系统访问令牌」。若接口返回 401/403，插件会提示这一点。站点如果要求用户 ID，到个人中心复制后填进 `New-Api-User`。

TOML 示例（New API 中转）：

```toml
[custom_1]
enabled = true
name = "我的中转"
protocol = "newapi"
api_key = "你的系统访问令牌"
base_url = "https://your-newapi.example.com"
new_api_user = "1"
quota_divisor = 500000
```

JSON 映射示例（字段不在默认位置时）：

```toml
[custom_2]
enabled = true
name = "其他网关"
protocol = "json"
api_key = "sk-..."
base_url = "https://gateway.example.com"
path = "/api/balance"
json_total = "data.balance"
json_granted = "data.used"
json_success = "success"
quota_divisor = 1
currency = "CNY"
```

### API Key / AccessKey 在哪里拿？

- **DeepSeek**: 登录 [DeepSeek 控制台](https://platform.deepseek.com/api_keys) → 「API Keys」→ 「创建 API Key」
- **SiliconFlow（硅基流动）**: 登录 [硅基流动控制台](https://cloud.siliconflow.cn/account/ak) → 「API 密钥」→ 「新建 API 密钥」
- **New API / One API（自定义源）**: 登录站点 → 「个人设置 → 安全设置 → 系统访问令牌」。不要用「API 密钥」页的 `sk-` Key。用户 ID 在个人中心，填到 `New-Api-User`。

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

- DeepSeek / SiliconFlow / 阿里云访问的都是**官方余额查询接口**，不会触发模型调用计费。自定义源只发 GET 查询，但仍取决于对方接口是否计费——请确认那是余额口而不是会走模型的路径。
- API Key 和 AccessKey 保存在本地 `config.toml` 中，请确保该文件不会被意外泄露（不要 commit 到 git、不要发给别人）。
- 若怀疑凭证泄漏，请立刻到对应平台后台**更换/撤销**该凭证；阿里云 AccessKey 可在 RAM 控制台禁用、删除或轮换。

---

## 📝 注意事项

- **SiliconFlow（硅基流动）已停止通过 API 提供余额数据**: `/v1/user/info` 仍然存在且鉴权正常，但 `balance` / `chargeBalance` / `totalBalance` 恒为 `0`、`status` 恒为空串。已向官方提工单确认——旧余额查询接口不可用，且**没有替代接口**（全站 API Reference 里账户类端点只有这一个；2026-03-26 起赠送余额转成的「优惠券」也没有任何查询入口）。插件因此不再显示会误导人的 `￥0.00`，而是标记为「接口受限」并提示到控制台查看。若平台日后恢复下发，插件会自动恢复正常展示，无需改配置或改代码。
- **额度敏感**: 不要把 `/余额` 授权给整个群——虽然查询本身免费，但仍可能被恶意刷接口。
- **请求超时**: 默认 10 秒；某家平台响应较慢可以把「请求超时（秒）」调高。卡片渲染的超时会自动钳在 25 秒以内（主程序渲染 RPC 的默认上限是 30 秒）。
- **并发查询**: 多个管理员同时发 `/余额`（或同时在配置页点查询）时，插件只向各平台发起一轮请求，后到的直接复用这一轮的结果；权限检查仍由主程序对每条命令单独执行。
- **自定义源没有余额接口就查不了**: 纯 OpenAI 兼容、只提供 `/v1/chat/completions` 的站点，没有账户查询口，`json` 协议也无能为力。请改用对方的用户信息 / 额度接口路径。
- **New API 额度单位**: 默认按 `quota / 500000` 显示为美元。若你的站点改过换算比例，把「额度换算除数」改成站点配置值。

Enjoy! 🎉
