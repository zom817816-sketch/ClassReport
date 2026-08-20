from __future__ import annotations

import csv
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import requests


API_ROOT = "https://open.feishu.cn/open-apis"
DEFAULT_BASE_URL = "https://xinzhoujy.feishu.cn/base/Hk0Cbddrqa6ClmsIUTMcIhTdnOh"

# Expected report-input tables. A table may be named either the short key or the
# historical CSV filename; normalised matching covers both forms.
REPORT_TABLES = {
    "16讲课程": "学生名单导入_16讲课程.csv",
    "入门测分数": "学生名单导入_入门测分数.csv",
    "学生名单_学员信息": "学生名单导入_学生名单_学员信息.csv",
    "期末测评分数": "学生名单导入_期末测评分数.csv",
    "课堂巩固分数": "学生名单导入_课堂巩固分数.csv",
}

# Current Base uses this concise title for the student profile table, while the
# original offline source includes the longer import prefix.
REPORT_TABLE_ALIASES = {
    "学生名单": "学生名单导入_学生名单_学员信息.csv",
}


class FeishuApiError(RuntimeError):
    """A safe-to-display API failure. It never includes tokens or secrets."""


@dataclass(frozen=True)
class ExportedTable:
    name: str
    table_id: str
    records: int
    raw_path: Path
    report_path: Path | None


@dataclass(frozen=True)
class ExportResult:
    app_token: str
    raw_dir: Path
    report_data_dir: Path
    tables: list[ExportedTable]


def parse_base_token(base_url: str) -> str:
    """Extract an app_token from /base/<token> or /base/workspace/<token> URLs."""
    parts = [part for part in urlparse(base_url).path.split("/") if part]
    if "base" not in parts:
        raise ValueError("不是有效的飞书多维表格链接：URL 中缺少 /base/。")
    base_index = parts.index("base")
    token_parts = parts[base_index + 1 :]
    if token_parts and token_parts[0] == "workspace":
        raise ValueError(
            "该链接是多维表格工作区页，不能作为具体数据表的 app_token。"
            "请进入目标多维表格后，复制形如 https://<tenant>.feishu.cn/base/<app_token> 的链接。"
        )
    if not token_parts or not re.fullmatch(r"[A-Za-z0-9]+", token_parts[0]):
        raise ValueError("无法从多维表格链接中识别 app_token。")
    return token_parts[0]


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        raise FileNotFoundError(f"未找到飞书应用配置文件：{path}")
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    _validate_credentials(values)
    return values


def _validate_credentials(values: dict[str, str]) -> None:
    if not values.get("USER_ACCESS_TOKEN") and (not values.get("APP_ID") or not values.get("APP_SECRET")):
        raise ValueError(".env 必须包含 USER_ACCESS_TOKEN，或同时包含 APP_ID 和 APP_SECRET。")


def read_project_env(project_root: Path) -> dict[str, str]:
    """Read bundled defaults first, then let local configuration override them."""
    values: dict[str, str] = {}
    bundled_root = getattr(sys, "_MEIPASS", None)
    paths = []
    if bundled_root:
        paths.append(Path(bundled_root) / "embedded" / ".env")
        paths.append(Path(bundled_root) / "embedded" / "app_credentials.env")
    paths.extend([
        project_root / ".env",
        project_root / "app_credentials.env",
        project_root / "ClassReportGenerator.config.env",
    ])
    for path in paths:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    _validate_credentials(values)
    return values


def safe_filename(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|\s]+', "_", name).strip("_") or "未命名数据表"


def normalise_name(name: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]", "", name).replace("学生名单导入", "")


def report_filename(table_name: str) -> str | None:
    normalised = normalise_name(table_name)
    if normalised in REPORT_TABLE_ALIASES:
        return REPORT_TABLE_ALIASES[normalised]
    matches = []
    for short_name, filename in REPORT_TABLES.items():
        expected = normalise_name(short_name)
        if normalised == expected or normalised.endswith(expected) or expected.endswith(normalised):
            matches.append(filename)
    return matches[0] if len(matches) == 1 else None


def cell_to_text(value: object) -> str:
    """Flatten Feishu's rich cell values while keeping unsupported values inspectable."""
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    if isinstance(value, list):
        texts: list[str] = []
        for item in value:
            if isinstance(item, str):
                texts.append(item)
            elif isinstance(item, dict):
                for key in ("text", "name", "email", "url", "link"):
                    if key in item and item[key] not in (None, ""):
                        texts.append(str(item[key]))
                        break
                else:
                    texts.append(json.dumps(item, ensure_ascii=False, sort_keys=True))
            else:
                texts.append(str(item))
        return "\n".join(texts)
    if isinstance(value, dict):
        for key in ("text", "name", "url", "link"):
            if key in value and value[key] not in (None, ""):
                return str(value[key])
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


class FeishuBitableExporter:
    def __init__(
        self,
        app_id: str | None,
        app_secret: str | None,
        app_token: str,
        user_access_token: str | None = None,
    ):
        self.app_id = app_id
        self.app_secret = app_secret
        self.app_token = app_token
        self.user_access_token = user_access_token
        self.session = requests.Session()

    def _request(self, method: str, path: str, *, token: str | None = None, **kwargs) -> dict:
        headers = {"Content-Type": "application/json; charset=utf-8"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            response = self.session.request(method, f"{API_ROOT}{path}", headers=headers, timeout=30, **kwargs)
        except requests.RequestException as error:
            raise FeishuApiError(f"飞书 API 请求失败：{error}") from error
        try:
            payload = response.json()
        except ValueError as error:
            if not response.ok:
                raise FeishuApiError(f"飞书 API 返回 HTTP {response.status_code}，且响应无法解析。") from error
            raise FeishuApiError("飞书 API 返回了无法解析的响应。") from error
        if not response.ok:
            raise FeishuApiError(
                f"飞书 API 返回 HTTP {response.status_code} / {payload.get('code', '未知错误')}："
                f"{payload.get('msg', '未知错误')}"
            )
        if payload.get("code", 0) != 0:
            raise FeishuApiError(f"飞书 API 返回错误 {payload.get('code')}：{payload.get('msg', '未知错误')}")
        return payload

    def tenant_access_token(self) -> str:
        if not self.app_id or not self.app_secret:
            raise FeishuApiError("未配置 APP_ID / APP_SECRET，无法获取应用身份令牌。")
        payload = self._request(
            "POST",
            "/auth/v3/tenant_access_token/internal/",
            json={"app_id": self.app_id, "app_secret": self.app_secret},
        )
        token = payload.get("tenant_access_token")
        if not token:
            raise FeishuApiError("飞书未返回 tenant_access_token。")
        return token

    def access_token(self) -> str:
        """Prefer a user token so the export follows the user's Base permissions."""
        return self.user_access_token or self.tenant_access_token()

    def list_tables(self, token: str) -> list[dict]:
        tables: list[dict] = []
        page_token: str | None = None
        while True:
            params = {"page_size": 100}
            if page_token:
                params["page_token"] = page_token
            payload = self._request("GET", f"/bitable/v1/apps/{self.app_token}/tables", token=token, params=params)
            tables.extend(payload.get("data", {}).get("items", []))
            if not payload.get("data", {}).get("has_more"):
                return tables
            page_token = payload.get("data", {}).get("page_token")
            if not page_token:
                raise FeishuApiError("数据表分页响应缺少 page_token。")

    def list_records(self, token: str, table_id: str) -> list[dict]:
        records: list[dict] = []
        page_token: str | None = None
        while True:
            params = {"page_size": 500}
            if page_token:
                params["page_token"] = page_token
            payload = self._request(
                "GET",
                f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/records",
                token=token,
                params=params,
            )
            records.extend(payload.get("data", {}).get("items", []))
            if not payload.get("data", {}).get("has_more"):
                return records
            page_token = payload.get("data", {}).get("page_token")
            if not page_token:
                raise FeishuApiError("记录分页响应缺少 page_token。")

    @staticmethod
    def write_csv(records: list[dict], destination: Path) -> None:
        columns: list[str] = []
        for record in records:
            for field in record.get("fields", {}):
                if field not in columns:
                    columns.append(field)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            for record in records:
                fields = record.get("fields", {})
                writer.writerow({column: cell_to_text(fields.get(column)) for column in columns})

    def export(self, destination_root: Path) -> ExportResult:
        raw_dir = destination_root / "feishu_raw"
        report_data_dir = destination_root / "feishu"
        raw_dir.mkdir(parents=True, exist_ok=True)
        report_data_dir.mkdir(parents=True, exist_ok=True)
        token = self.access_token()
        exported: list[ExportedTable] = []
        manifest_rows: list[dict[str, str]] = []
        for table in self.list_tables(token):
            table_id = str(table.get("table_id", ""))
            name = str(table.get("name", table_id))
            if not table_id:
                raise FeishuApiError("数据表列表中存在缺少 table_id 的记录。")
            records = self.list_records(token, table_id)
            raw_path = raw_dir / f"{safe_filename(name)}_{table_id}.csv"
            self.write_csv(records, raw_path)
            target_name = report_filename(name)
            report_path = report_data_dir / target_name if target_name else None
            if report_path:
                self.write_csv(records, report_path)
            exported.append(ExportedTable(name, table_id, len(records), raw_path, report_path))
            manifest_rows.append(
                {
                    "数据表": name,
                    "table_id": table_id,
                    "记录数": str(len(records)),
                    "原始导出": str(raw_path),
                    "报告数据文件": str(report_path) if report_path else "未匹配",
                }
            )
        manifest_path = destination_root / "feishu_download_manifest.csv"
        with manifest_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["数据表", "table_id", "记录数", "原始导出", "报告数据文件"])
            writer.writeheader()
            writer.writerows(manifest_rows)
        return ExportResult(self.app_token, raw_dir, report_data_dir, exported)


def sync_from_url(project_root: Path, base_url: str = DEFAULT_BASE_URL) -> ExportResult:
    env = read_project_env(project_root)
    if base_url == DEFAULT_BASE_URL and env.get("FEISHU_URL"):
        base_url = env["FEISHU_URL"]
    app_token = env.get("FEISHU_APP_TOKEN") or parse_base_token(base_url)
    if not re.fullmatch(r"[A-Za-z0-9]+", app_token):
        raise ValueError("FEISHU_APP_TOKEN 格式无效，应为多维表格链接中的 app_token。")
    exporter = FeishuBitableExporter(
        env.get("APP_ID"),
        env.get("APP_SECRET"),
        app_token,
        env.get("USER_ACCESS_TOKEN"),
    )
    return exporter.export(project_root / "data")
