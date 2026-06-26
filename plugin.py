"""LLM 平台余额查询插件 — MaiBot SDK v2

通过聊天命令 `/余额` 并行查询 LLM 平台的账号余额，统一汇总输出。

"""

import asyncio
import base64
import datetime
import hashlib
import hmac
import html
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
import uuid
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Sequence, Tuple

from maibot_sdk import CONFIG_RELOAD_SCOPE_SELF, Command, Field, MaiBotPlugin, PluginConfigBase

logger = logging.getLogger(__name__)

# --- 常量 ---

def _load_manifest_version() -> str:
    """从 _manifest.json 读取版本号，保持插件元数据单一来源。"""
    try:
        manifest_path = Path(__file__).parent / "_manifest.json"
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        version = data.get("version")
        if isinstance(version, str) and version.strip():
            return version.strip()
        logger.warning(
            "_manifest.json 中 version 字段缺失或非法 (%r)，回落到 0.0.0", version,
        )
    except Exception:
        logger.warning("读取 _manifest.json 失败，回落到 0.0.0", exc_info=True)
    return "0.0.0"


PLUGIN_VERSION = _load_manifest_version()
CONFIG_SCHEMA_VERSION = "1.5.0"
DEFAULT_TIMEOUT = 10  # 秒

DEEPSEEK_DEFAULT_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_BALANCE_PATH = "/user/balance"

SILICONFLOW_DEFAULT_BASE_URL = "https://api.siliconflow.cn"
SILICONFLOW_USER_INFO_PATH = "/v1/user/info"

ALIYUN_DEFAULT_ENDPOINT = "https://business.aliyuncs.com"
ALIYUN_BSSOPENAPI_VERSION = "2017-12-14"
ALIYUN_QUERY_ACCOUNT_BALANCE_ACTION = "QueryAccountBalance"

CURRENCY_SYMBOLS = {"CNY": "￥", "USD": "$", "EUR": "€", "JPY": "¥"}

OUTPUT_FORMAT_TEXT = "text"
OUTPUT_FORMAT_IMAGE = "image"
OUTPUT_FORMAT_BOTH = "both"
OUTPUT_FORMATS = (OUTPUT_FORMAT_TEXT, OUTPUT_FORMAT_IMAGE, OUTPUT_FORMAT_BOTH)

MAX_FETCH_ATTEMPTS = 2
RETRY_BACKOFF_SECONDS = 0.5
RETRYABLE_HTTP_STATUSES = (429, 500, 502, 503, 504)
DEFAULT_PROVIDER_CONCURRENCY = 3


# --- 网络层 ---

class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """禁止跟随 3xx 重定向的 handler。

    余额请求会带着 `Authorization: Bearer <api_key>` 头。urllib 默认会自动跟随
    重定向——若端点（尤其是用户自建网关/代理）返回 302 跳到第三方或降级到
    http://，凭证就会被原样转发给重定向目标，造成泄露。这里让 redirect_request
    返回 None，urllib 便不再构造跟随请求，3xx 会落到默认错误处理器抛
    HTTPError，由上层统一当作 HTTP 错误展示，既不泄露 key 也不会静默。
    """

    def redirect_request(self, *args, **kwargs):  # type: ignore[override]
        return None


# 携带敏感凭证的请求统一走这个不跟随重定向的 opener。
_NO_REDIRECT_OPENER = urllib.request.build_opener(_NoRedirectHandler)


# --- 自定义异常 ---

class _BalanceRequestError(RuntimeError):
    """网络层异常（连接失败、超时、JSON 解析失败等）。"""


class _BalanceHTTPError(RuntimeError):
    """HTTP 非 2xx 异常，携带状态码与可读详情。"""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(f"HTTP {status}: {detail}")
        self.status = status
        self.detail = detail


class _BalanceBusinessError(RuntimeError):
    """业务层异常（接口返回 2xx 但 body 表示失败）。"""


class _BalanceConfigError(RuntimeError):
    """插件配置错误（如非 HTTPS API 地址）。"""


def _is_retryable_fetch_error(exc: Exception) -> bool:
    """判断一次余额查询失败是否适合短暂重试。"""
    if isinstance(exc, _BalanceHTTPError):
        return exc.status in RETRYABLE_HTTP_STATUSES
    return isinstance(exc, _BalanceRequestError)


async def _fetch_with_retry(provider: "_BalanceProvider") -> Dict[str, Any]:
    """执行 Provider 查询，并对网络抖动、限流和 5xx 做一次轻量重试。"""
    last_exc: Optional[Exception] = None
    for attempt in range(1, MAX_FETCH_ATTEMPTS + 1):
        try:
            return await asyncio.to_thread(provider.fetch_sync)
        except Exception as exc:
            last_exc = exc
            if attempt >= MAX_FETCH_ATTEMPTS or not _is_retryable_fetch_error(exc):
                raise
            delay = RETRY_BACKOFF_SECONDS * attempt
            logger.info(
                "%s 查询失败，%.1f 秒后重试（%s/%s）：%s",
                provider.display_name,
                delay,
                attempt + 1,
                MAX_FETCH_ATTEMPTS,
                exc,
            )
            await asyncio.sleep(delay)
    assert last_exc is not None
    raise last_exc


# --- 配置模型 ---

class PluginSection(PluginConfigBase):
    """插件基本配置。"""

    __ui_label__ = "插件设置"

    name: str = Field(default="llm_balance_plugin", json_schema_extra={"disabled": True})
    config_version: str = Field(default=CONFIG_SCHEMA_VERSION, json_schema_extra={"disabled": True})
    enabled: bool = Field(default=True, description="是否启用插件",
                          json_schema_extra={"label": "启用插件"})


class SettingsSection(PluginConfigBase):
    """通用设置。"""

    __ui_label__ = "通用设置"

    timeout: int = Field(
        default=DEFAULT_TIMEOUT,
        description="单平台请求超时秒数",
        ge=1, le=60,
        json_schema_extra={"label": "请求超时（秒）"},
    )
    admin_only: bool = Field(
        default=True,
        description="是否仅允许管理员使用 /余额 命令",
        json_schema_extra={"label": "仅管理员可用"},
    )
    admin_user_ids: List[str] = Field(
        default_factory=list,
        description="允许使用 /余额 命令的用户 QQ 号列表",
        json_schema_extra={"label": "管理员列表", "hint": "仅 admin_only=true 时生效"},
    )
    output_format: Literal["text", "image", "both"] = Field(
        default=OUTPUT_FORMAT_IMAGE,
        description='输出格式：text 纯文本 / image HTML 卡片 / both 卡片 + 文本',
        json_schema_extra={
            "label": "输出格式",
            "hint": "text=纯文本；image=HTML 卡片图片；both=卡片+文本（image/both 需要主程序提供 render.html2png 能力）",
        },
    )


class DeepSeekProviderSection(PluginConfigBase):
    """DeepSeek 平台配置"""

    __ui_label__ = "DeepSeek"

    enabled: bool = Field(default=False, json_schema_extra={"label": "启用 DeepSeek"})
    api_key: str = Field(default="", json_schema_extra={"label": "API Key", "x-widget": "password"})
    base_url: str = Field(default=DEEPSEEK_DEFAULT_BASE_URL,
                          json_schema_extra={"label": "API 基地址"})


class SiliconFlowProviderSection(PluginConfigBase):
    """硅基流动平台配置"""

    __ui_label__ = "SiliconFlow（硅基流动）"

    enabled: bool = Field(default=False, json_schema_extra={"label": "启用硅基流动"})
    api_key: str = Field(default="", json_schema_extra={"label": "API Key", "x-widget": "password"})
    base_url: str = Field(default=SILICONFLOW_DEFAULT_BASE_URL,
                          json_schema_extra={"label": "API 基地址"})


class AliyunProviderSection(PluginConfigBase):
    """阿里云 BSSOpenAPI 账户余额配置。"""

    __ui_label__ = "阿里云（百炼扣费账户）"

    enabled: bool = Field(default=False, json_schema_extra={"label": "启用阿里云余额"})
    access_key_id: str = Field(default="", json_schema_extra={"label": "AccessKey ID"})
    access_key_secret: str = Field(
        default="",
        json_schema_extra={"label": "AccessKey Secret", "x-widget": "password"},
    )
    endpoint: str = Field(
        default=ALIYUN_DEFAULT_ENDPOINT,
        description="阿里云费用中心 BSSOpenAPI Endpoint",
        json_schema_extra={"label": "Endpoint"},
    )


class LLMBalanceConfig(PluginConfigBase):
    """插件完整配置。

    deepseek / siliconflow 提升到顶层 Section，以便 WebUI 正确展开
    （嵌套两层的 Pydantic Section WebUI 无法渲染，会显示成 [object Object]）。
    """

    plugin: PluginSection = Field(default_factory=PluginSection)
    settings: SettingsSection = Field(default_factory=SettingsSection)
    deepseek: DeepSeekProviderSection = Field(default_factory=DeepSeekProviderSection)
    siliconflow: SiliconFlowProviderSection = Field(default_factory=SiliconFlowProviderSection)
    aliyun: AliyunProviderSection = Field(default_factory=AliyunProviderSection)


# --- Provider 抽象 ---

class _BalanceProvider:
    """单个 LLM 平台余额查询的抽象基类。

    子类需要：
      - 设置 display_name
      - 覆盖 default_base_url（属性）
      - 设置 path 或覆盖 _build_url
      - 实现 to_record(payload) 返回结构化 _BalanceRecord
    """

    display_name: str = ""
    path: str = ""
    user_agent: str = f"MaiBot-LLMBalance/{PLUGIN_VERSION}"

    def __init__(self, api_key: str, base_url: str, timeout: int) -> None:
        self.api_key = api_key
        self.base_url = self._normalize_base_url(base_url)
        self.timeout = timeout

    @property
    def default_base_url(self) -> str:
        raise NotImplementedError

    def _normalize_base_url(self, base_url: str) -> str:
        candidate = (base_url or "").strip().rstrip("/")
        return candidate or self.default_base_url

    def _require_https_base_url(self) -> str:
        parsed = urllib.parse.urlsplit(self.base_url)
        if parsed.scheme.lower() != "https":
            scheme = parsed.scheme or "空"
            raise _BalanceConfigError(
                f"{self.display_name} API 基地址必须使用 HTTPS，当前协议：{scheme}",
            )
        if not parsed.netloc:
            raise _BalanceConfigError(f"{self.display_name} API 基地址不是合法 URL")
        if parsed.username or parsed.password:
            raise _BalanceConfigError(f"{self.display_name} API 基地址不能包含用户名或密码")
        if parsed.query or parsed.fragment:
            raise _BalanceConfigError(f"{self.display_name} API 基地址不能包含查询参数或片段")
        return self.base_url

    def _build_url(self) -> str:
        return self._require_https_base_url() + self.path

    def fetch_sync(self) -> Dict[str, Any]:
        url = self._build_url()
        req = urllib.request.Request(url, method="GET")
        req.add_header("Authorization", f"Bearer {self.api_key}")
        req.add_header("Accept", "application/json")
        req.add_header("User-Agent", self.user_agent)

        try:
            with _NO_REDIRECT_OPENER.open(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            raise _BalanceHTTPError(exc.code, self._extract_http_error_detail(exc))
        except urllib.error.URLError as exc:
            # Python 3.10+ socket.timeout == TimeoutError；urlopen 超时实际抛 URLError(reason=TimeoutError())，
            # 不会直接进 except TimeoutError——所以从 exc.reason 还原超时语义。
            if isinstance(exc.reason, TimeoutError):
                raise _BalanceRequestError(f"请求超时：{exc.reason}")
            raise _BalanceRequestError(str(exc.reason or exc))

        try:
            return json.loads(body)
        except ValueError as exc:
            raise _BalanceRequestError(f"响应不是合法 JSON：{exc}")

    @staticmethod
    def _extract_http_error_detail(exc: urllib.error.HTTPError) -> str:
        try:
            raw = exc.read().decode("utf-8", errors="replace")
        except OSError:
            return str(exc.reason or "未知错误")[:200]
        if not raw:
            return str(exc.reason or "未知错误")[:200]
        try:
            parsed = json.loads(raw)
        except ValueError:
            return raw[:200]
        if isinstance(parsed, dict):
            err = parsed.get("error")
            if isinstance(err, dict):
                msg = str(err.get("message") or "")
                if msg:
                    return msg[:200]
            msg = str(parsed.get("message") or "")
            if msg:
                return msg[:200]
        return raw[:200]

    def to_record(self, payload: Dict[str, Any]) -> "_BalanceRecord":
        """把原始响应转换为结构化 _BalanceRecord，由子类实现。"""
        raise NotImplementedError

    @staticmethod
    def _format_amount(value: Any) -> Optional[str]:
        if value is None:
            return None
        try:
            amount = Decimal(str(value).strip())
            if not amount.is_finite():
                return str(value)
            return format(amount.quantize(Decimal("0.01")), "f")
        except (InvalidOperation, TypeError, ValueError):
            return str(value)


class _BalanceRecord:
    """单个平台余额的结构化结果，供文本/HTML 两种输出复用。

    一个 record 可能携带多条 entries（如 DeepSeek 同时返回 CNY/USD）。
    """

    def __init__(self, display_name: str, status: Optional[str] = None,
                 status_ok: bool = True,
                 entries: Optional[List[Dict[str, Any]]] = None,
                 note: Optional[str] = None) -> None:
        self.display_name = display_name
        self.status = status                    # 已格式化的状态描述
        self.status_ok = status_ok
        self.entries = entries or []            # [{currency, total, granted, topped, labels?}]
        self.note = note                        # 额外说明（如解析失败、空响应）


# --- 内置 Provider ---

class _DeepSeekProvider(_BalanceProvider):
    display_name = "DeepSeek"
    path = DEEPSEEK_BALANCE_PATH

    @property
    def default_base_url(self) -> str:
        return DEEPSEEK_DEFAULT_BASE_URL

    def to_record(self, payload: Dict[str, Any]) -> _BalanceRecord:
        is_available = bool(payload.get("is_available", False))
        infos = payload.get("balance_infos") or []
        if not isinstance(infos, list):
            infos = []

        record = _BalanceRecord(
            display_name=self.display_name,
            status="正常" if is_available else "异常（余额不足或被限制）",
            status_ok=is_available,
        )
        for info in infos:
            if not isinstance(info, dict):
                continue
            currency = str(info.get("currency") or "?").upper()
            record.entries.append({
                "currency": currency,
                "total": self._format_amount(info.get("total_balance")),
                "granted": self._format_amount(info.get("granted_balance")),
                "topped": self._format_amount(info.get("topped_up_balance")),
            })
        if not record.entries:
            record.note = "未返回任何币种余额信息"
        return record


class _SiliconFlowProvider(_BalanceProvider):
    display_name = "硅基流动"
    path = SILICONFLOW_USER_INFO_PATH

    @property
    def default_base_url(self) -> str:
        return SILICONFLOW_DEFAULT_BASE_URL

    def fetch_sync(self) -> Dict[str, Any]:
        payload = super().fetch_sync()
        # SiliconFlow 即使 HTTP 200 也可能在 body 里返回业务失败
        if isinstance(payload, dict) and payload.get("status") is False:
            msg = str(payload.get("message") or "硅基流动返回业务失败")
            raise _BalanceBusinessError(msg)
        return payload

    def to_record(self, payload: Dict[str, Any]) -> _BalanceRecord:
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            return _BalanceRecord(self.display_name, note="响应缺少 data 字段，无法解析",
                                   status_ok=False)
        status = str(data.get("status") or "").lower()
        return _BalanceRecord(
            display_name=self.display_name,
            status="正常" if status == "normal" else (status or "未知"),
            status_ok=(status == "normal"),
            note="数据来自官方 API，与控制台显示口径可能略有差异",
            entries=[{
                "currency": "CNY",
                "total": self._format_amount(data.get("totalBalance")),
                # SiliconFlow API 字段命名反直觉：balance 实际是代金券/赠金，
                # chargeBalance 才是真正的充值余额。用 labels 把展示标签改为
                # 跟硅基流动控制台一致的"代金券 / 余额"。
                "granted": self._format_amount(data.get("balance")),
                "topped": self._format_amount(data.get("chargeBalance")),
                "labels": {"granted": "代金券", "topped": "余额"},
            }],
        )


class _AliyunBssOpenApiProvider(_BalanceProvider):
    """阿里云费用中心余额查询。

    QueryAccountBalance 查询的是账号级余额，可用于判断百炼后付费扣费账户的
    可用额度，但不等同于百炼免费额度、Token 额度或资源包剩余量。
    """

    display_name = "阿里百炼"

    def __init__(self, access_key_id: str, access_key_secret: str,
                 endpoint: str, timeout: int) -> None:
        super().__init__(api_key=access_key_id, base_url=endpoint, timeout=timeout)
        self.access_key_secret = access_key_secret

    @property
    def default_base_url(self) -> str:
        return ALIYUN_DEFAULT_ENDPOINT

    def fetch_sync(self) -> Dict[str, Any]:
        base_url = self._require_https_base_url()
        params: Dict[str, str] = {
            "Action": ALIYUN_QUERY_ACCOUNT_BALANCE_ACTION,
            "Version": ALIYUN_BSSOPENAPI_VERSION,
            "Format": "JSON",
            "AccessKeyId": self.api_key,
            "SignatureMethod": "HMAC-SHA1",
            "SignatureVersion": "1.0",
            "SignatureNonce": str(uuid.uuid4()),
            "Timestamp": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        params["Signature"] = self._sign(params)
        url = f"{base_url}/?{self._canonical_query(params)}"
        req = urllib.request.Request(url, method="GET")
        req.add_header("Accept", "application/json")
        req.add_header("User-Agent", self.user_agent)

        try:
            with _NO_REDIRECT_OPENER.open(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            raise _BalanceHTTPError(exc.code, self._extract_http_error_detail(exc))
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise _BalanceRequestError(f"请求超时：{exc.reason}")
            raise _BalanceRequestError(str(exc.reason or exc))

        try:
            payload = json.loads(body)
        except ValueError as exc:
            raise _BalanceRequestError(f"响应不是合法 JSON：{exc}")

        if isinstance(payload, dict):
            code = str(payload.get("Code") or "").strip()
            success = payload.get("Success")
            success_text = str(success).strip().lower()
            data = payload.get("Data")

            if success is False or success_text == "false":
                message = str(payload.get("Message") or "阿里云返回业务失败")
                raise _BalanceBusinessError(f"{code}: {message}" if code else message)

            # 阿里云成功响应不总是 Code=200；部分接口会返回 Success/OK，或只返回 Data。
            success_codes = {"", "200", "success", "ok"}
            has_success_flag = success is True or success_text == "true"
            has_balance_data = isinstance(data, dict)
            if code.lower() not in success_codes and not has_success_flag and not has_balance_data:
                message = str(payload.get("Message") or "阿里云返回业务失败")
                raise _BalanceBusinessError(f"{code}: {message}" if code else message)
        return payload

    def to_record(self, payload: Dict[str, Any]) -> _BalanceRecord:
        data = payload.get("Data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            return _BalanceRecord(self.display_name, note="响应缺少 Data 字段，无法解析", status_ok=False)

        currency = str(data.get("Currency") or "CNY").upper()
        note = "账号级余额；可判断百炼后付费扣费账户可用额度，不代表百炼免费额度/Token/资源包剩余"

        return _BalanceRecord(
            display_name=self.display_name,
            status="正常",
            status_ok=True,
            note=note,
            entries=[{
                "currency": currency,
                "total": self._format_amount(data.get("AvailableAmount")),
                "granted": self._format_amount(data.get("CreditAmount")),
                "topped": self._format_amount(data.get("AvailableCashAmount")),
                "labels": {"total": "可用额度", "granted": "信控额度", "topped": "现金余额"},
            }],
        )

    def _sign(self, params: Dict[str, str]) -> str:
        canonical = self._canonical_query(params)
        string_to_sign = f"GET&%2F&{self._percent_encode(canonical)}"
        key = f"{self.access_key_secret}&".encode("utf-8")
        digest = hmac.new(key, string_to_sign.encode("utf-8"), hashlib.sha1).digest()
        return base64.b64encode(digest).decode("utf-8")

    @classmethod
    def _canonical_query(cls, params: Dict[str, str]) -> str:
        return "&".join(
            f"{cls._percent_encode(key)}={cls._percent_encode(value)}"
            for key, value in sorted(params.items())
        )

    @staticmethod
    def _percent_encode(value: Any) -> str:
        return urllib.parse.quote(str(value), safe="~")


# --- 主插件类 ---

class LLMBalancePlugin(MaiBotPlugin):
    """LLM 平台余额查询插件。"""

    config_model = LLMBalanceConfig

    def __init__(self) -> None:
        super().__init__()
        self._admin_set: set[str] = set()

    async def on_load(self) -> None:
        self._refresh_admin_cache()
        logger.info("LLM 余额查询插件(v%s)初始化完成。", PLUGIN_VERSION)

    async def on_unload(self) -> None:
        logger.info("LLM 余额查询插件已卸载。")

    async def on_config_update(
        self,
        scope: str,
        config_data: dict[str, object],
        version: str,
    ) -> None:
        if scope == CONFIG_RELOAD_SCOPE_SELF:
            self._refresh_admin_cache()
            self.ctx.logger.info("LLM 余额插件配置已更新: version=%s", version)
        del config_data

    # ===== 辅助 =====

    def _refresh_admin_cache(self) -> None:
        self._admin_set = {str(uid) for uid in self.config.settings.admin_user_ids}

    def _check_admin(self, user_id: str) -> bool:
        return str(user_id) in self._admin_set

    @staticmethod
    def _capability_error_message(result: Any) -> Optional[str]:
        """兼容部分能力调用以返回值(bool 或 dict)而不是异常表达失败的情况。

        send.* 系列经 SDK 归一化后返回 bool（失败为 False）；render.html2png 等
        多字段能力在失败时返回带 success=False 的 dict。两种都要能识破，否则会把
        "发送/渲染失败"误判为成功——例如 image 模式下发图失败时静默吞掉结果。
        """
        if result is False:
            return "能力调用返回失败(success=false)"
        if isinstance(result, dict) and result.get("success") is False:
            error = result.get("error") or result.get("message")
            return str(error or "能力调用返回 success=false")
        return None

    def _collect_providers(self) -> Tuple[List[_BalanceProvider], List[str]]:
        """根据当前配置构造所有 enabled 平台的 Provider 实例。

        Returns:
            (providers, skipped_notes)：providers 为可查询的 Provider 列表；
            skipped_notes 为"已启用但凭证不完整、已跳过"的平台提示，用于在结果里
            明确告知用户，而不是只写进日志后静默消失。
        """
        settings = self.config.settings
        result: List[_BalanceProvider] = []
        skipped: List[str] = []

        if self.config.deepseek.enabled:
            api_key = self.config.deepseek.api_key.strip()
            if api_key:
                result.append(_DeepSeekProvider(
                    api_key=api_key,
                    base_url=self.config.deepseek.base_url.strip(),
                    timeout=settings.timeout,
                ))
            else:
                logger.warning("DeepSeek 已启用 (enabled=true) 但 api_key 为空，已跳过查询")
                skipped.append("DeepSeek：已启用但未配置 API Key")
        if self.config.siliconflow.enabled:
            api_key = self.config.siliconflow.api_key.strip()
            if api_key:
                result.append(_SiliconFlowProvider(
                    api_key=api_key,
                    base_url=self.config.siliconflow.base_url.strip(),
                    timeout=settings.timeout,
                ))
            else:
                logger.warning("硅基流动已启用 (enabled=true) 但 api_key 为空，已跳过查询")
                skipped.append("硅基流动：已启用但未配置 API Key")
        if self.config.aliyun.enabled:
            access_key_id = self.config.aliyun.access_key_id.strip()
            access_key_secret = self.config.aliyun.access_key_secret.strip()
            if access_key_id and access_key_secret:
                result.append(_AliyunBssOpenApiProvider(
                    access_key_id=access_key_id,
                    access_key_secret=access_key_secret,
                    endpoint=self.config.aliyun.endpoint.strip(),
                    timeout=settings.timeout,
                ))
            else:
                logger.warning("阿里云已启用 (enabled=true) 但 AccessKey 配置不完整，已跳过查询")
                skipped.append("阿里百炼：已启用但 AccessKey ID/Secret 不完整")
        return result, skipped

    # ===== 命令处理 =====

    @Command(
        "llm_balance_query",
        description="查询所有已启用 LLM 平台的账号余额。格式：/余额",
        pattern=r"^\/余额$",
    )
    async def handle_balance(self, stream_id: str = "", group_id: str = "",
                             user_id: str = "", text: str = "",
                             plugin_config: Optional[dict] = None, **kwargs):
        """查询余额：/余额"""
        if self.config.settings.admin_only and not self._check_admin(user_id):
            if not self._admin_set:
                # admin_only=true 但没人配进白名单 → 所有人(含部署者自己)都被拒。
                # 这种"全员拒绝"最容易让人摸不着头脑，给出针对性引导而非笼统提示。
                deny_msg = (
                    "❌ 『仅管理员可用』已开启，但管理员列表为空，当前没有人能查询。\n"
                    "请在配置 [settings].admin_user_ids 中加入你的 QQ 号，或把 admin_only 关掉。"
                )
            else:
                deny_msg = "❌ 你没有权限查询 LLM 平台余额"
            await self.ctx.send.text(deny_msg, stream_id)
            return False, "用户 %s 无权限" % user_id, 1

        providers, skipped_notes = self._collect_providers()
        if not providers:
            if skipped_notes:
                # 平台都 enabled 了，只是凭证没填全：给出针对性的缺失清单，
                # 而不是笼统的"未启用任何平台"，方便用户直接定位要补哪个凭证。
                detail = "\n".join(f"· {note}" for note in skipped_notes)
                await self.ctx.send.text(
                    "❌ 已启用的平台都没有配置完整凭证，无法查询：\n" + detail,
                    stream_id,
                )
                return False, "启用的平台凭证不完整", 1
            await self.ctx.send.text(
                "❌ 未启用任何平台，请在配置文件 [deepseek] / [siliconflow] / [aliyun] 段"
                "设置 enabled=true 并填入对应凭证",
                stream_id,
            )
            return False, "无可用平台", 1

        await self.ctx.send.text(
            f"⏳ 正在并行查询 {len(providers)} 个平台...", stream_id,
        )

        # 并行查询；阻塞式 urllib 放进线程池时限制并发，避免多平台扩展后压垮默认线程池。
        fetch_semaphore = asyncio.Semaphore(
            max(1, min(DEFAULT_PROVIDER_CONCURRENCY, len(providers))),
        )

        async def _run(provider: _BalanceProvider) -> Tuple[_BalanceProvider, Any]:
            try:
                async with fetch_semaphore:
                    payload = await _fetch_with_retry(provider)
                return provider, payload
            except Exception as exc:
                return provider, exc

        results = await asyncio.gather(*[_run(p) for p in providers])

        # 转换为结构化记录（成功项保留 record，失败项保留异常）
        records: List[Tuple[_BalanceProvider, Any]] = []
        for provider, payload_or_exc in results:
            if isinstance(payload_or_exc, Exception):
                records.append((provider, payload_or_exc))
                continue
            try:
                records.append((provider, provider.to_record(payload_or_exc)))
            except Exception as exc:
                records.append((provider, exc))

        self._log_provider_errors(records)

        # 按 output_format 输出
        fmt = (self.config.settings.output_format or OUTPUT_FORMAT_TEXT).lower()
        if fmt not in OUTPUT_FORMATS:
            fmt = OUTPUT_FORMAT_TEXT
        render_fallback_notice: Optional[str] = None

        if fmt in (OUTPUT_FORMAT_IMAGE, OUTPUT_FORMAT_BOTH):
            # 拆三段 try：render_html / html2png / send.image 分别报错，避免发图失败
            # 时仍提示"卡片渲染失败"误导用户排查方向。
            image_b64: Optional[str] = None
            failure_stage: str = ""
            failure_exc: Optional[Exception] = None
            try:
                html_doc = self._render_html_card(records, skipped_notes)
            except Exception as exc:
                failure_stage = "html_compose"
                failure_exc = exc
            else:
                try:
                    rendered = await self.ctx.render.html2png(
                        html_doc,
                        selector="body",
                        viewport={"width": 720, "height": self._estimate_card_viewport_height(records)},
                        device_scale_factor=2.0,
                        full_page=True,
                        render_timeout_ms=max(1, self.config.settings.timeout) * 1000,
                    )
                except Exception as exc:
                    failure_stage = "html2png"
                    failure_exc = exc
                else:
                    if isinstance(rendered, dict):
                        render_error = self._capability_error_message(rendered)
                        if render_error:
                            failure_stage = "html2png"
                            failure_exc = RuntimeError(render_error)
                        else:
                            image_b64 = rendered.get("image_base64")
                    if not image_b64 and not failure_stage:
                        failure_stage = "html2png_empty"

            if image_b64:
                try:
                    send_result = await self.ctx.send.image(image_b64, stream_id)
                    send_error = self._capability_error_message(send_result)
                    if send_error:
                        raise RuntimeError(send_error)
                except Exception as exc:
                    failure_stage = "send_image"
                    failure_exc = exc

            if failure_stage:
                stage_msg = {
                    "html_compose": ("HTML 卡片组装失败", "⚠️ 卡片组装失败，已自动切换为文本。"),
                    "html2png": ("html2png 渲染失败", "⚠️ 卡片渲染失败，已自动切换为文本。"),
                    "html2png_empty": ("html2png 未返回 image_base64", "⚠️ 渲染结果为空，已自动切换为文本。"),
                    "send_image": ("图片发送失败", "⚠️ 图片发送失败，已自动切换为文本。"),
                }[failure_stage]
                if failure_exc is not None:
                    logger.error("%s，回退文本模式: %s", stage_msg[0], failure_exc, exc_info=True)
                else:
                    logger.warning("%s，回退文本模式", stage_msg[0])
                render_fallback_notice = stage_msg[1]
                fmt = OUTPUT_FORMAT_TEXT

        if fmt in (OUTPUT_FORMAT_TEXT, OUTPUT_FORMAT_BOTH):
            report = self._format_text_report(records, skipped_notes)
            if render_fallback_notice:
                report = f"{render_fallback_notice}\n\n{report}"
            send_result = await self.ctx.send.text(report, stream_id)
            text_error = self._capability_error_message(send_result)
            if text_error:
                logger.error("余额文本报告发送失败：%s", text_error)
                return False, "文本报告发送失败：%s" % text_error, 1

        return True, "余额查询完成", 1

    # ===== 报告组装：文本 =====

    @classmethod
    def _format_text_report(cls,
                            records: Sequence[Tuple[_BalanceProvider, Any]],
                            skipped_notes: Sequence[str] = ()) -> str:
        """把所有 Provider 的结果（record 或异常）汇总为发送给用户的文本。"""
        lines: List[str] = ["💰 LLM 平台余额"]
        for provider, item in records:
            lines.append("———")
            lines.append(f"【{provider.display_name}】")
            error_line = cls._format_error_line(provider, item)
            if error_line is not None:
                lines.append(error_line)
                continue
            assert isinstance(item, _BalanceRecord)
            lines.extend(cls._format_record_text_lines(item))
        for note in skipped_notes:
            lines.append("———")
            lines.append(f"⚠️ {note}")
        return "\n".join(lines)

    @staticmethod
    def _log_provider_errors(records: Sequence[Tuple[_BalanceProvider, Any]]) -> None:
        """集中记录 Provider 异常，避免文本和 HTML 两种输出重复打日志。"""
        for provider, item in records:
            if isinstance(item, _BalanceHTTPError):
                logger.warning("%s 查询 HTTP %s: %s",
                               provider.display_name, item.status, item.detail)
            elif isinstance(item, _BalanceBusinessError):
                logger.warning("%s 业务失败: %s", provider.display_name, item)
            elif isinstance(item, _BalanceRequestError):
                logger.warning("%s 网络异常: %s", provider.display_name, item)
            elif isinstance(item, _BalanceConfigError):
                logger.warning("%s 配置错误: %s", provider.display_name, item)
            elif isinstance(item, Exception):
                logger.error(
                    "%s 查询或解析失败: %s",
                    provider.display_name,
                    item,
                    exc_info=(type(item), item, item.__traceback__),
                )

    @staticmethod
    def _format_error_line(provider: _BalanceProvider, item: Any) -> Optional[str]:
        """识别异常类型并返回单行错误描述；非异常返回 None。"""
        if isinstance(item, _BalanceHTTPError):
            if item.status in (401, 403):
                return "❌ API Key 无效或权限不足"
            return f"❌ HTTP {item.status}：{item.detail}"
        if isinstance(item, _BalanceBusinessError):
            return f"❌ 业务失败：{item}"
        if isinstance(item, _BalanceRequestError):
            return f"❌ 网络错误：{item}"
        if isinstance(item, _BalanceConfigError):
            return f"❌ 配置错误：{item}"
        if isinstance(item, Exception):
            return "❌ 内部错误（详见日志）"
        return None

    @staticmethod
    def _format_record_text_lines(record: _BalanceRecord) -> List[str]:
        lines: List[str] = []
        if record.status:
            mark = "✅" if record.status_ok else "⚠️"
            lines.append(f"状态：{mark} {record.status}")
        if record.note:
            lines.append(f"（{record.note}）")
        for entry in record.entries:
            currency = entry.get("currency") or "?"
            symbol = CURRENCY_SYMBOLS.get(currency, "")
            labels = entry.get("labels") or {}
            total = entry.get("total")
            granted = entry.get("granted")
            topped = entry.get("topped")
            if total is not None:
                total_label = labels.get("total") or "总余额"
                lines.append(f"[{currency}] {total_label}：{symbol}{total}")
            if granted is not None:
                granted_label = labels.get("granted") or "赠金余额"
                lines.append(f"{granted_label}：{symbol}{granted}")
            if topped is not None:
                topped_label = labels.get("topped") or "充值余额"
                lines.append(f"{topped_label}：{symbol}{topped}")
        return lines

    # ===== 报告组装：HTML 卡片 =====

    @classmethod
    def _estimate_card_viewport_height(cls,
                                       records: Sequence[Tuple[_BalanceProvider, Any]]) -> int:
        """估算初始视口高度；实际截图仍使用 full_page，避免卡片内容被裁切。"""
        height = 160
        for _, item in records:
            height += 86
            if isinstance(item, _BalanceRecord):
                if item.note:
                    height += 24
                height += max(1, len(item.entries)) * 64
            else:
                height += 32
        return min(max(height, 480), 2400)

    @classmethod
    def _render_html_card(cls,
                         records: Sequence[Tuple[_BalanceProvider, Any]],
                         skipped_notes: Sequence[str] = ()) -> str:
        """把所有平台的结果渲染为单张 HTML 卡片，供 html2png 截图。"""
        sections: List[str] = []
        for provider, item in records:
            sections.append(cls._render_provider_section(provider, item))
        for note in skipped_notes:
            sections.append(
                f'<div class="provider">'
                f'  <div class="provider-head">'
                f'    <span class="provider-name">⚠️ 已跳过</span>'
                f'    <span class="status-pill status-warn">未配置</span>'
                f'  </div>'
                f'  <div class="error-text">{html.escape(note)}</div>'
                f'</div>'
            )
        return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><style>
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
  background: linear-gradient(135deg, #f6f7fb 0%, #e9edf7 100%);
  padding: 24px;
  color: #1f2937;
}}
#card {{
  width: 672px;
  background: #ffffff;
  border-radius: 16px;
  padding: 24px 28px;
  box-shadow: 0 16px 48px -16px rgba(20, 30, 60, 0.18);
}}
.card-title {{
  font-size: 22px;
  font-weight: 600;
  margin: 0 0 4px 0;
  letter-spacing: 0.5px;
}}
.card-subtitle {{
  font-size: 13px;
  color: #6b7280;
  margin: 0 0 18px 0;
}}
.provider {{
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 14px 16px 12px 16px;
  margin-bottom: 12px;
  background: #fafbff;
}}
.provider:last-child {{ margin-bottom: 0; }}
.provider-head {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}}
.provider-name {{
  font-size: 16px;
  font-weight: 600;
  color: #111827;
}}
.status-pill {{
  font-size: 12px;
  padding: 2px 10px;
  border-radius: 999px;
  font-weight: 500;
}}
.status-ok    {{ background: #dcfce7; color: #166534; }}
.status-warn  {{ background: #fee2e2; color: #991b1b; }}
.status-info  {{ background: #e0e7ff; color: #3730a3; }}
.entry {{
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  padding: 8px 0 0 0;
  border-top: 1px dashed #e5e7eb;
  margin-top: 8px;
}}
.entry:first-of-type {{ border-top: 0; margin-top: 0; padding-top: 0; }}
.entry-cell .label {{
  font-size: 11px;
  color: #6b7280;
  margin-bottom: 2px;
}}
.entry-cell .value {{
  font-size: 16px;
  font-weight: 600;
  color: #111827;
  font-variant-numeric: tabular-nums;
}}
.entry-cell .value.total {{ color: #2563eb; }}
.entry-currency {{
  font-size: 11px;
  color: #6b7280;
  margin-bottom: 6px;
  letter-spacing: 0.5px;
}}
.error-text {{
  color: #991b1b;
  font-size: 13px;
  padding: 4px 0;
}}
.note-text {{
  color: #6b7280;
  font-size: 12px;
  padding: 2px 0 6px 0;
}}
.footer {{
  text-align: right;
  font-size: 11px;
  color: #9ca3af;
  margin-top: 16px;
}}
</style></head>
<body>
<div id="card">
  <h1 class="card-title">💰 LLM 平台余额</h1>
  <p class="card-subtitle">共 {len(records)} 个平台</p>
  {''.join(sections)}
  <div class="footer">MaiBot · LLM Balance Plugin v{PLUGIN_VERSION}</div>
</div>
</body></html>"""

    @classmethod
    def _render_provider_section(cls, provider: _BalanceProvider, item: Any) -> str:
        name_esc = html.escape(provider.display_name)
        error_line = cls._format_error_line(provider, item)
        if error_line is not None:
            return (
                f'<div class="provider">'
                f'  <div class="provider-head">'
                f'    <span class="provider-name">{name_esc}</span>'
                f'    <span class="status-pill status-warn">错误</span>'
                f'  </div>'
                f'  <div class="error-text">{html.escape(error_line)}</div>'
                f'</div>'
            )

        assert isinstance(item, _BalanceRecord)
        pill_cls = "status-ok" if item.status_ok else "status-warn"
        pill_text = html.escape(item.status or ("正常" if item.status_ok else "异常"))
        note_html = (
            f'<div class="note-text">{html.escape(item.note)}</div>'
            if item.note else ""
        )

        entry_blocks: List[str] = []
        for entry in item.entries:
            currency = (entry.get("currency") or "?").upper()
            symbol = CURRENCY_SYMBOLS.get(currency, "")
            labels = entry.get("labels") or {}
            cells: List[str] = []
            for default_label, key, klass in (
                ("总余额", "total", "value total"),
                ("赠金", "granted", "value"),
                ("充值", "topped", "value"),
            ):
                v = entry.get(key)
                if v is None:
                    continue
                label = labels.get(key) or default_label
                cells.append(
                    f'<div class="entry-cell">'
                    f'  <div class="label">{html.escape(label)}</div>'
                    f'  <div class="{klass}">{html.escape(symbol + str(v))}</div>'
                    f'</div>'
                )
            if not cells:
                continue
            entry_blocks.append(
                f'<div class="entry-currency">{html.escape(currency)}</div>'
                f'<div class="entry">{"".join(cells)}</div>'
            )

        entries_html = "".join(entry_blocks) or '<div class="note-text">无可展示的余额条目</div>'

        return (
            f'<div class="provider">'
            f'  <div class="provider-head">'
            f'    <span class="provider-name">{name_esc}</span>'
            f'    <span class="status-pill {pill_cls}">{pill_text}</span>'
            f'  </div>'
            f'  {note_html}'
            f'  {entries_html}'
            f'</div>'
        )


def create_plugin() -> LLMBalancePlugin:
    """创建 LLM 余额查询插件实例。"""
    return LLMBalancePlugin()
