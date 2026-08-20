from __future__ import annotations

import argparse
import csv
import shutil
import sys
import zipfile
from datetime import date, datetime
from pathlib import Path

from .analysis import build_analysis
from .config import Settings
from .data import DataRepository
from .feishu import DEFAULT_BASE_URL, FeishuApiError, sync_from_url
from .pdf_report import PdfReportBuilder, safe_filename


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="一键生成夏季班学情报告")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1], help="ClassReport 项目目录")
    parser.add_argument("--date", type=date.fromisoformat, default=date.today(), help="报告日期，格式 YYYY-MM-DD")
    parser.add_argument("--teacher", default="毛远老师", help="指导老师姓名")
    parser.add_argument(
        "--template",
        choices=("standard", "cartoon", "memphis", "notebook"),
        default="standard",
        help="报告模板：standard（标准专业风）、cartoon（手绘卡通风）、memphis（孟菲斯几何风）或 notebook（校园笔记风）",
    )
    parser.add_argument("--keep-output", action="store_true", help="保留既有 output 文件，不清空旧结果")
    parser.add_argument("--no-encrypt", action="store_true", help="仅调试时使用：不加密 PDF")
    parser.add_argument("--sync-feishu", action="store_true", help="先从飞书多维表格下载最新数据，再生成报告")
    parser.add_argument("--sync-only", action="store_true", help="仅下载飞书多维表格，不生成报告（需配合 --sync-feishu）")
    parser.add_argument("--validate-only", action="store_true", help="下载并预检数据，不生成报告（需配合 --sync-feishu）")
    parser.add_argument("--feishu-url", default=DEFAULT_BASE_URL, help="飞书多维表格 URL")
    parser.add_argument("--data-dir", type=Path, help="指定报告输入 CSV 目录；默认使用 data/")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    root = args.root.resolve()
    source_data_dir = args.data_dir.resolve() if args.data_dir else root / "data"
    if args.sync_only and not args.sync_feishu:
        raise SystemExit("--sync-only 需要与 --sync-feishu 一起使用。")
    if args.sync_only and args.validate_only:
        raise SystemExit("--sync-only 与 --validate-only 不能同时使用。")
    if args.sync_feishu:
        try:
            result = sync_from_url(root, args.feishu_url)
        except (FeishuApiError, FileNotFoundError, ValueError) as error:
            detail = str(error)
            if "99991672" in detail:
                detail += "\n应用身份请在飞书开放平台开通并发布 bitable:app:readonly（或 bitable:app / base:table:read）权限后重试。"
            raise SystemExit(f"飞书同步失败：{detail}") from error
        source_data_dir = result.report_data_dir
        matched = sum(table.report_path is not None for table in result.tables)
        print(f"飞书同步完成：下载 {len(result.tables)} 张数据表，其中 {matched} 张匹配课情报告数据结构。")
        print(f"原始数据：{result.raw_dir}")
        print(f"报告数据：{result.report_data_dir}")
        if args.sync_only:
            return
        if matched < len(DataRepository.FILES):
            raise SystemExit(f"数据预检失败：仅识别到 {matched}/{len(DataRepository.FILES)} 张报告数据表，请检查表名和字段。")
    settings = Settings(
        root=root,
        report_date=args.date,
        teacher=args.teacher,
        source_data_dir=source_data_dir,
        template=args.template,
    )
    try:
        loaded = DataRepository(settings.data_dir).load()
    except (FileNotFoundError, KeyError, ValueError) as error:
        raise SystemExit(f"数据预检失败：{error}") from error
    preflight_report_data(loaded)
    if args.validate_only:
        return
    archive_previous_output(settings.output_dir)
    for directory in (settings.reports_dir, settings.packages_dir, settings.manifests_dir):
        directory.mkdir(parents=True, exist_ok=True)

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
                "报告模板": {
                    "cartoon": "手绘卡通风",
                    "memphis": "孟菲斯几何风",
                    "notebook": "校园笔记风",
                }.get(settings.template, "标准专业风"),
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


def preflight_report_data(loaded) -> None:
    if not loaded.students:
        raise SystemExit("数据预检失败：未识别到可生成报告的学员记录。")
    print(f"数据预检通过：可生成 {len(loaded.students)} 份报告。")
    if not loaded.issues:
        print("数据质量：未发现需要人工核对的问题。")
        return
    issue_types: dict[str, int] = {}
    for issue in loaded.issues:
        issue_type = issue.get("类型", "数据异常")
        issue_types[issue_type] = issue_types.get(issue_type, 0) + 1
    summary = "；".join(f"{kind} {count} 条" for kind, count in issue_types.items())
    print(f"数据质量提醒：发现 {len(loaded.issues)} 条需人工核对的问题（{summary}）。报告仍可生成，详情见 data_quality_report.csv。")


def archive_previous_output(output_dir: Path) -> None:
    active_names = ("reports", "packages", "manifests")
    active_paths = [output_dir / name for name in active_names if (output_dir / name).exists()]
    if not active_paths:
        return
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_dir = output_dir / "history" / timestamp
    archive_dir.mkdir(parents=True, exist_ok=False)
    for source in active_paths:
        shutil.move(str(source), str(archive_dir / source.name))
    print(f"已归档上一次输出：{archive_dir}")


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fields = list(rows[0]) if rows else ["类型", "说明"]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
