from __future__ import annotations

import argparse
import csv
import shutil
import sys
import zipfile
from datetime import date
from pathlib import Path

from .analysis import build_analysis
from .config import Settings
from .data import DataRepository
from .feishu import DEFAULT_BASE_URL, FeishuApiError, sync_from_url
from .pdf_report import PdfReportBuilder, safe_filename


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="一键生成夏季班学情报告")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1], help="ClassReport 项目目录")
    parser.add_argument("--date", type=date.fromisoformat, default=date.today(), help="报告日期，格式 YYYY-MM-DD")
    parser.add_argument("--teacher", default="毛远老师", help="指导老师姓名")
    parser.add_argument("--keep-output", action="store_true", help="保留既有 output 文件，不清空旧结果")
    parser.add_argument("--no-encrypt", action="store_true", help="仅调试时使用：不加密 PDF")
    parser.add_argument("--sync-feishu", action="store_true", help="先从飞书多维表格下载最新数据，再生成报告")
    parser.add_argument("--sync-only", action="store_true", help="仅下载飞书多维表格，不生成报告（需配合 --sync-feishu）")
    parser.add_argument("--feishu-url", default=DEFAULT_BASE_URL, help="飞书多维表格 URL")
    parser.add_argument("--data-dir", type=Path, help="指定报告输入 CSV 目录；默认使用 data/")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    source_data_dir = args.data_dir.resolve() if args.data_dir else root / "data"
    if args.sync_only and not args.sync_feishu:
        raise SystemExit("--sync-only 需要与 --sync-feishu 一起使用。")
    if args.sync_feishu:
        try:
            result = sync_from_url(root, args.feishu_url)
        except (FeishuApiError, FileNotFoundError, ValueError) as error:
            raise SystemExit(f"飞书同步失败：{error}") from error
        source_data_dir = result.report_data_dir
        matched = sum(table.report_path is not None for table in result.tables)
        print(f"飞书同步完成：下载 {len(result.tables)} 张数据表，其中 {matched} 张匹配课情报告数据结构。")
        print(f"原始数据：{result.raw_dir}")
        print(f"报告数据：{result.report_data_dir}")
        if args.sync_only:
            return
    settings = Settings(root=root, report_date=args.date, teacher=args.teacher, source_data_dir=source_data_dir)
    if settings.output_dir.exists() and not args.keep_output:
        shutil.rmtree(settings.output_dir)
    for directory in (settings.reports_dir, settings.packages_dir, settings.manifests_dir):
        directory.mkdir(parents=True, exist_ok=True)

    loaded = DataRepository(settings.data_dir).load()
    builder = PdfReportBuilder(settings)
    manifest: list[dict[str, str]] = []
    class_files: dict[str, list[Path]] = {}
    for index, student in enumerate(loaded.students, 1):
        analysis = build_analysis(student)
        class_token = safe_filename(f"{student.term}_{student.grade}{student.programme}_{student.class_name}")
        filename = f"{index:03d}_{safe_filename(student.name)}_学情报告.pdf"
        destination = settings.reports_dir / class_token / filename
        original_phone_tail = student.phone_tail
        if args.no_encrypt:
            student.phone_tail = None
        result = builder.build(analysis, destination)
        student.phone_tail = original_phone_tail
        class_files.setdefault(class_token, []).append(result.path)
        manifest.append(
            {
                "序号": str(index),
                "学员": student.name,
                "期次": student.term,
                "课程": student.course_label,
                "班级": student.class_name,
                "报告文件": str(result.path.relative_to(settings.output_dir)),
                "PDF加密": "是" if result.encrypted and not args.no_encrypt else "否（缺少手机号后四位）" if not student.phone_tail else "否（调试）",
                "入班测均分": "" if analysis.intro_average is None else f"{analysis.intro_average:.2f}",
                "课堂巩固均分": "" if analysis.consolidation_average is None else f"{analysis.consolidation_average:.2f}",
                "期末测评": "" if analysis.final_score is None else str(analysis.final_score),
            }
        )
        print(f"[{index}/{len(loaded.students)}] 已生成：{destination.name}")

    package_rows = []
    for class_token, paths in class_files.items():
        archive = settings.packages_dir / f"{class_token}_学情报告.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in paths:
                zf.write(path, arcname=path.name)
        package_rows.append({"班级": class_token, "学员报告数": str(len(paths)), "压缩包": str(archive.relative_to(settings.output_dir))})

    write_csv(settings.manifests_dir / "report_manifest.csv", manifest)
    write_csv(settings.manifests_dir / "class_packages.csv", package_rows)
    write_csv(settings.manifests_dir / "data_quality_report.csv", loaded.issues)
    print(f"\n完成：生成 {len(manifest)} 份个人报告、{len(package_rows)} 个班级压缩包。")
    print(f"输出目录：{settings.output_dir}")


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fields = list(rows[0]) if rows else ["类型", "说明"]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
