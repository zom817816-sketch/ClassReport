#!/usr/bin/env python3
"""
飞书多维表格（Bitable）数据导出脚本
===================================
将飞书多维表格的全部数据导出为 CSV 文件。

使用方式:
    python feishu_bitable_export.py \
        --app-id cli_xxxxx \
        --app-secret xxxxx \
        --base-token S5l6bknB4avHNssU4iqc2YVMnud \
        --output ./output

    # 只导出指定表
    python feishu_bitable_export.py \
        --app-id cli_xxxxx \
        --app-secret xxxxx \
        --base-token S5l6bknB4avHNssU4iqc2YVMnud \
        --table-id tblwdPozAp30tj5R \
        --output ./output

前置条件:
    1. 在飞书开放平台 (https://open.feishu.cn) 创建应用，获取 App ID 和 App Secret
    2. 为应用开通权限:
       - bitable:app (读写多维表格)  或
       - bitable:app:readonly (只读多维表格)
    3. 发布应用版本并审批通过
    4. 将应用添加为多维表格的协作者（至少「可阅读」权限）

安装依赖:
    pip install requests

参数说明:
    --app-id        飞书应用的 App ID
    --app-secret    飞书应用的 App Secret
    --base-token    多维表格的 base_token（从表格 URL 中获取）
    --table-id      指定导出的数据表 ID（可选，不填则导出全部表）
    --output        输出目录（默认 ./output）
    --view-id       指定视图 ID（可选，按视图过滤）
    --page-size     每页记录数（默认 100，最大 500）

URL 解析示例:
    https://xinzhoujy.feishu.cn/base/S5l6bknB4avHNssU4iqc2YVMnud?table=tblwdPozAp30tj5R&view=vewi1blH6s
    ├─ base_token = S5l6bknB4avHNssU4iqc2YVMnud
    ├─ table_id   = tblwdPozAp30tj5R
    └─ view_id    = vewi1blH6s
"""

import argparse
import csv
import json
import os
import sys
import time
import requests

# ============================================================
# 飞书 API 基础配置
# ============================================================
BASE_URL = "https://open.feishu.cn/open-apis"


def get_tenant_access_token(app_id: str, app_secret: str) -> str:
    """获取 tenant_access_token（应用凭证）"""
    url = f"{BASE_URL}/auth/v3/tenant_access_token/internal"
    resp = requests.post(url, json={"app_id": app_id, "app_secret": app_secret}, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        print(f"❌ 获取 token 失败: {data.get('msg', '未知错误')}")
        sys.exit(1)
    print(f"✅ 获取 tenant_access_token 成功")
    return data["tenant_access_token"]


def api_get(token: str, path: str, params: dict = None) -> dict:
    """发起 GET 请求（带鉴权）"""
    url = f"{BASE_URL}{path}"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise Exception(f"API 错误 [{data.get('code')}]: {data.get('msg')}")
    return data.get("data", {})


# ============================================================
# 数据获取
# ============================================================
def list_tables(token: str, base_token: str) -> list:
    """获取多维表格中所有数据表"""
    result = api_get(token, f"/bitable/v1/apps/{base_token}/tables", {"page_size": 100})
    tables = result.get("items", [])
    print(f"📋 共找到 {len(tables)} 张数据表:")
    for t in tables:
        print(f"   - {t['name']} (table_id: {t['table_id']})")
    return tables


def list_fields(token: str, base_token: str, table_id: str) -> list:
    """获取数据表的字段列表"""
    result = api_get(token, f"/bitable/v1/apps/{base_token}/tables/{table_id}/fields", {"page_size": 100})
    return result.get("items", [])


def fetch_all_records(token: str, base_token: str, table_id: str,
                      view_id: str = None, page_size: int = 100) -> list:
    """分页获取全部记录"""
    all_records = []
    page_token = None
    page_num = 0

    while True:
        params = {"page_size": min(page_size, 500)}
        if page_token:
            params["page_token"] = page_token
        if view_id:
            params["view_id"] = view_id

        result = api_get(token, f"/bitable/v1/apps/{base_token}/tables/{table_id}/records", params)
        items = result.get("items", [])
        all_records.extend(items)
        page_num += 1

        has_more = result.get("has_more", False)
        page_token = result.get("page_token")
        print(f"   📥 第 {page_num} 页: 获取 {len(items)} 条 (累计 {len(all_records)} 条)")

        if not has_more:
            break

    return all_records


# ============================================================
# 数据处理
# ============================================================
def flatten_cell_value(value) -> str:
    """将单元格值转为 CSV 友好的字符串"""
    if value is None:
        return ""

    # 多选 / 数组
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                # 人员类型: {"id": "ou_xxx", "name": "张三"}
                # 附件类型: {"file_token": "xxx", "name": "file.pdf"}
                if "name" in item:
                    parts.append(item["name"])
                elif "text" in item:
                    parts.append(item["text"])
                else:
                    parts.append(json.dumps(item, ensure_ascii=False))
            else:
                parts.append(str(item))
        return ", ".join(parts)

    # 人员 / URL 等对象
    if isinstance(value, dict):
        if "text" in value:
            return value["text"]
        if "name" in value:
            return value["name"]
        if "link" in value:
            return value["link"]
        return json.dumps(value, ensure_ascii=False)

    # 时间戳（毫秒）→ 可读时间
    if isinstance(value, (int, float)) and value > 1e12:
        try:
            from datetime import datetime, timezone, timedelta
            tz = timezone(timedelta(hours=8))
            dt = datetime.fromtimestamp(value / 1000, tz=tz)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return str(value)

    return str(value)


def records_to_csv(fields: list, records: list, output_path: str):
    """将记录写入 CSV 文件"""
    # 构建表头
    field_names = [f["field_name"] for f in fields]
    headers = ["record_id"] + field_names

    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)

        for record in records:
            record_id = record.get("record_id", "")
            row_data = record.get("fields", {})
            row = [record_id]
            for field_name in field_names:
                cell = row_data.get(field_name)
                row.append(flatten_cell_value(cell))
            writer.writerow(row)

    print(f"   ✅ 已导出 {len(records)} 条记录 → {output_path}")


# ============================================================
# 主流程
# ============================================================
def main():
    parser = argparse.ArgumentParser(
        description="飞书多维表格数据导出工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 导出全部表
  python feishu_bitable_export.py --app-id cli_xxx --app-secret xxx --base-token S5l6bk...

  # 只导出指定表
  python feishu_bitable_export.py --app-id cli_xxx --app-secret xxx --base-token S5l6bk... --table-id tblwdPoz...

  # 按视图导出
  python feishu_bitable_export.py --app-id cli_xxx --app-secret xxx --base-token S5l6bk... --view-id vewi1b...
        """
    )
    parser.add_argument("--app-id", required=True, help="飞书应用 App ID")
    parser.add_argument("--app-secret", required=True, help="飞书应用 App Secret")
    parser.add_argument("--base-token", required=True, help="多维表格 base_token")
    parser.add_argument("--table-id", help="指定数据表 ID（不填则导出全部）")
    parser.add_argument("--view-id", help="指定视图 ID（可选）")
    parser.add_argument("--output", default="./output", help="输出目录（默认 ./output）")
    parser.add_argument("--page-size", type=int, default=100, help="每页记录数（默认 100，最大 500）")

    args = parser.parse_args()

    # 创建输出目录
    os.makedirs(args.output, exist_ok=True)

    # 1. 获取 token
    print("🔐 正在获取访问凭证...")
    token = get_tenant_access_token(args.app_id, args.app_secret)

    # 2. 获取表列表
    print(f"\n📊 多维表格: {args.base_token}")
    if args.table_id:
        tables = [{"table_id": args.table_id, "name": args.table_id}]
        print(f"📋 指定导出表: {args.table_id}")
    else:
        tables = list_tables(token, args.base_token)

    if not tables:
        print("❌ 未找到数据表")
        sys.exit(1)

    # 3. 逐表导出
    exported_files = []
    for table in tables:
        table_id = table["table_id"]
        table_name = table["name"]
        print(f"\n{'='*50}")
        print(f"📑 正在导出: {table_name} ({table_id})")

        # 获取字段
        fields = list_fields(token, args.base_token, table_id)
        print(f"   字段数: {len(fields)}")

        # 获取记录
        records = fetch_all_records(token, args.base_token, table_id,
                                     view_id=args.view_id, page_size=args.page_size)
        print(f"   记录数: {len(records)}")

        # 写入 CSV
        safe_name = table_name.replace("/", "_").replace("\\", "_")
        output_path = os.path.join(args.output, f"{safe_name}.csv")
        records_to_csv(fields, records, output_path)
        exported_files.append(output_path)

        # 避免触发限流
        time.sleep(0.3)

    # 4. 完成
    print(f"\n{'='*50}")
    print(f"🎉 导出完成！共 {len(exported_files)} 个 CSV 文件:")
    for f in exported_files:
        print(f"   📄 {f}")
    print(f"\n输出目录: {os.path.abspath(args.output)}")


if __name__ == "__main__":
    main()
