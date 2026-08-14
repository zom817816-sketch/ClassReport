from __future__ import annotations

import io
import math
import re
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader, PdfWriter
from reportlab.lib.colors import Color, HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from .analysis import CategoryScore, ReportAnalysis, fmt
from .config import Settings


PAGE_W, PAGE_H = A4
BLUE = HexColor("#2B89B5")
DEEP_BLUE = HexColor("#006EC8")
LIGHT_BLUE = HexColor("#E7F3FF")
PALE_BLUE = HexColor("#F5FAFE")
TEXT = HexColor("#333333")
MUTED = HexColor("#777777")
GREEN = HexColor("#18A849")
ORANGE = HexColor("#F59E0B")
RED = HexColor("#E54E59")
PURPLE = HexColor("#8058D7")
LIGHT_GREY = HexColor("#F4F5F6")
HEADING = HexColor("#146B96")
TITLE = HexColor("#075A8D")
EMOJI_FONT = Path(r"C:\Windows\Fonts\seguiemj.ttf")


def register_fonts() -> tuple[str, str]:
    """Use separate regular/bold Chinese fonts so section hierarchy is visible."""
    if "ReportChinese" not in pdfmetrics.getRegisteredFontNames():
        regular = Path(r"C:\Windows\Fonts\msyh.ttc")
        bold = Path(r"C:\Windows\Fonts\msyhbd.ttc")
        if regular.exists() and bold.exists():
            pdfmetrics.registerFont(TTFont("ReportChinese", str(regular)))
            pdfmetrics.registerFont(TTFont("ReportChineseBold", str(bold)))
        elif Path(r"C:\Windows\Fonts\simhei.ttf").exists():
            # SimHei is intentionally used as the visual-bold fallback.
            pdfmetrics.registerFont(TTFont("ReportChinese", r"C:\Windows\Fonts\simhei.ttf"))
            pdfmetrics.registerFont(TTFont("ReportChineseBold", r"C:\Windows\Fonts\simhei.ttf"))
        else:  # ReportLab's built-in CID font is a portable fallback.
            from reportlab.pdfbase import cidfonts

            pdfmetrics.registerFont(cidfonts.UnicodeCIDFont("STSong-Light"))
            return "STSong-Light", "STSong-Light"
    return "ReportChinese", "ReportChineseBold"


FONT, FONT_BOLD = register_fonts()


def safe_filename(text: str) -> str:
    return re.sub(r'[\\/:*?"<>|\s]+', "_", text).strip("_")


def display_score(score: float | None) -> str:
    if score is None:
        return "—"
    return str(int(score)) if score.is_integer() else f"{score:.1f}"


def category_labels(items: list[CategoryScore]) -> list[str]:
    return [item.category for item in items] or ["暂无数据"]


def set_matplotlib_font() -> None:
    font_path = Path(r"C:\Windows\Fonts\simhei.ttf")
    if font_path.exists():
        font_manager.fontManager.addfont(str(font_path))
        plt.rcParams["font.family"] = "SimHei"
    plt.rcParams["axes.unicode_minus"] = False


@dataclass(frozen=True)
class GeneratedReport:
    path: Path
    encrypted: bool


class PdfReportBuilder:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._emoji_cache: dict[str, io.BytesIO] = {}

    def build(self, report: ReportAnalysis, output_path: Path) -> GeneratedReport:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = output_path.with_suffix(".plain.pdf")
        canvas = Canvas(str(temporary), pagesize=A4, pageCompression=1)
        canvas.setTitle(f"{report.student.name} - 2026夏季班学情报告")
        canvas.setAuthor("ClassReport")
        self._cover(canvas, report)
        self._scores_page(canvas, report)
        self._charts_page(canvas, report)
        self._diagnosis_page(canvas, report)
        self._summary_page(canvas, report)
        canvas.save()
        encrypted = bool(report.student.phone_tail and report.student.phone_tail.isdigit())
        if encrypted:
            self._encrypt(temporary, output_path, report.student.phone_tail or "")
            temporary.unlink(missing_ok=True)
        else:
            temporary.replace(output_path)
        return GeneratedReport(path=output_path, encrypted=encrypted)

    @staticmethod
    def _encrypt(source: Path, destination: Path, password: str) -> None:
        reader = PdfReader(str(source))
        writer = PdfWriter()
        writer.append_pages_from_reader(reader)
        writer.encrypt(password, algorithm="AES-256-R5")
        with destination.open("wb") as handle:
            writer.write(handle)

    def _cover(self, c: Canvas, a: ReportAnalysis) -> None:
        student = a.student
        c.setFillColor(white)
        c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
        # Draw the watermark first so it cannot cover the report metadata.
        self._watermark(c, a, center_y=165)
        c.setStrokeColor(BLUE)
        c.setLineWidth(1.6)
        c.line(48, 595, PAGE_W - 48, 595)
        c.setFillColor(TITLE)
        c.setFont(FONT_BOLD, 27)
        c.drawCentredString(PAGE_W / 2, 608, "2026 夏季班学情报告")
        c.setFillColor(TEXT)
        c.setFont(FONT, 14)
        c.drawCentredString(PAGE_W / 2, 565, f"{student.name} · {student.course_label} · {student.class_name} · {student.term}")
        c.setFillColor(MUTED)
        c.setFont(FONT, 10.5)
        c.drawCentredString(PAGE_W / 2, 486, f"报告时间：{self.settings.report_date.isoformat()}")
        c.drawCentredString(PAGE_W / 2, 467, f"指导老师：{self.settings.teacher}")
        badge = f"{student.course_label} · {student.term} · {student.class_name}"
        c.setFillColor(LIGHT_BLUE)
        c.roundRect(PAGE_W / 2 - 118, 397, 236, 20, 3, fill=1, stroke=0)
        c.setFillColor(DEEP_BLUE)
        c.setFont(FONT, 9)
        c.drawCentredString(PAGE_W / 2, 403.5, badge)
        c.showPage()

    def _scores_page(self, c: Canvas, a: ReportAnalysis) -> None:
        self._page_base(c, a, "① 核心数据")
        y = 727
        highest = max((x for x in a.student.intro_scores if x is not None), default=None)
        lowest = min((x for x in a.student.intro_scores if x is not None), default=None)
        high_count = sum(
            1
            for score, class_score in zip(a.student.intro_scores, a.intro_class_average)
            if score is not None and class_score is not None and score > class_score
        )
        cards = [
            (fmt(a.intro_average, 2), "入班测 14 讲平均分", HexColor("#4D9FD0")),
            (display_score(highest), "最高分", HexColor("#31A84D")),
            (display_score(lowest), "最低分", RED),
            (f"{high_count}/14", "高于班级均分次数", HexColor("#32AB4C")),
            (fmt(a.consolidation_average, 2), "课堂巩固 15 讲均", HexColor("#F5AF00")),
            (display_score(a.final_score), "期末测评", PURPLE),
        ]
        self._cards(c, cards, y)
        y = 622
        self._section(c, "② ★ 课堂巩固（夏季班 · 15讲 · 100 分制）", y)
        y -= 27
        self._note(c, "统计规则：课堂巩固共 15 讲；空白成绩按未完成处理。", y, "📌")
        y -= 28
        headers = ["讲次"] + [str(i) for i in range(1, 16)]
        student_scores = [display_score(x) for x in a.student.consolidation_scores]
        class_scores = [fmt(x, 1) for x in a.consolidation_class_average]
        accuracy = ["—" if x is None else f"{x:.0f}%" for x in a.student.consolidation_scores]
        y = self._table(c, 48, y, [65] + [31.2] * 15, headers, [
            ["分数"] + student_scores,
            [f"班级 {len(a.student.classmates_consolidation)} 人均"] + class_scores,
            ["正确率"] + accuracy,
        ], font_size=7.2)
        difference = None
        cls_avg = average_or_none(a.consolidation_class_average)
        if a.consolidation_average is not None and cls_avg is not None:
            difference = a.consolidation_average - cls_avg
        c.setFillColor(MUTED)
        c.setFont(FONT, 8.6)
        c.drawString(48, y - 15, f"课堂巩固 15 讲均 {fmt(a.consolidation_average, 2)}，班级均 {fmt(cls_avg, 2)}（差 {difference:+.1f}）；{a.completed_consolidation}/15 讲已完成。" if difference is not None else f"课堂巩固已完成 {a.completed_consolidation}/15 讲。")
        y -= 53
        self._section(c, f"③ ◆ 入班测 {len(a.categories)} 板块 + 14 讲分数（100 分制）", y)
        y -= 27
        self._note(c, "入班测覆盖夏季班前 14 讲重点题型，100 分制标准化。", y, "📌")
        y -= 28
        category_rows = []
        for item in a.categories:
            lesson_text = " / ".join(f"第{x.lesson}讲" for x in item.lessons)
            category_rows.append([item.category, fmt(item.score, 1), lesson_text, "强" if item.score is not None and item.score >= 85 else "待加强"])
        y = self._table(c, 48, y, [83, 73, 301, 71], ["板块", "平均分", "包含讲次", "评价"], category_rows, font_size=8)
        y -= 10
        course = a.student.course[:14]
        topic_rows = [
            ["讲次"] + [str(i) for i in range(1, 15)],
            ["板块"] + [(course[i].category if i < len(course) else "—") for i in range(14)],
            ["知识点"] + [(course[i].topic if i < len(course) else "—") for i in range(14)],
            ["分数"] + [display_score(x) for x in a.student.intro_scores],
        ]
        self._mini_matrix(c, 48, y, topic_rows)
        c.showPage()

    def _charts_page(self, c: Canvas, a: ReportAnalysis) -> None:
        self._page_base(c, a, "④ ◆ 板块雷达 + 各讲分数趋势（入班测 vs 课堂巩固 · 100 分制）")
        c.setFillColor(MUTED)
        c.setFont(FONT, 8.5)
        self._emoji(c, "📊", 48, 698, 14)
        c.drawString(67, 712, f"本图组展示 {a.student.name} 的个人成绩与 {len(a.student.classmates_consolidation)} 人班级平均的双维度对比。")
        image = self._charts_image(a)
        c.drawImage(ImageReader(image), 49, 265, width=497, height=420, preserveAspectRatio=True, mask="auto")
        self._section(c, f"⑤ ▲ 入门测 vs 期末测评（5 维度对比 · {len(a.student.classmates_final)} 人班级）", 238)
        final_diff = a.final_score - a.intro_average if a.final_score is not None and a.intro_average is not None else None
        final_rows = [
            ["分数（100 分制）", f"{fmt(a.intro_average, 2)} / 100", f"{display_score(a.final_score)} / 100", f"{final_diff:+.1f}" if final_diff is not None else "未参加"],
            ["班级排名", "—", a.final_rank, f"班级样本 {len(a.student.classmates_final)} 人"],
            ["班级平均分（期末）", "—", fmt(a.final_class_average, 1), "期末班级均分"],
            ["班级中位分（期末）", "—", fmt(a.final_class_median, 1), "班级中位值"],
            ["高于均分次数", f"{a.below_average_count}/14", "—", "入班测对比"],
        ]
        y = self._table(c, 48, 211, [137, 130, 130, 152], ["维度", "入门测（14讲平均）", "期末测评（单次）", "差异/说明"], final_rows, font_size=8.2)
        c.setFillColor(MUTED)
        c.setFont(FONT, 8.4)
        if a.student.classmates_final:
            c.drawString(48, y - 15, f"期末测评 {len(a.student.classmates_final)} 人有效样本，平均 {fmt(a.final_class_average, 1)} / 中位 {fmt(a.final_class_median, 1)} / 最高 {max(a.student.classmates_final):.1f} / 最低 {min(a.student.classmates_final):.1f}。")
        else:
            c.drawString(48, y - 15, "暂无有效期末测评数据，本页保留入班测与课堂巩固对比。")
        c.showPage()

    def _diagnosis_page(self, c: Canvas, a: ReportAnalysis) -> None:
        self._page_base(c, a, "⑦ ★ 核心判断 & 建议")
        strengths = [item for item in a.categories if item.score is not None and item.score >= 85]
        strength_text = " / ".join(f"{x.category} {x.score:.1f} 分" for x in strengths) or "暂无可判断板块"
        low_text = " / ".join(self._lesson_text(number, lesson, score) for number, lesson, score in a.low_lessons) or "暂无弱项（各讲均不低于 85 分）"
        self._callout(c, 48, 646, 499, 101, [
            ("✅", GREEN, f"优势：{strength_text}"),
            ("⚠️", RED, f"不足：{low_text}"),
            ("🚀", DEEP_BLUE, f"建议：{self._recommendation(a)}"),
        ])
        self._section(c, "⑧ ◆ 诊断分析（多维度）", 613)
        c.setFillColor(HEADING)
        c.setFont(FONT_BOLD, 13)
        c.drawString(48, 579, f"强项（{len(a.categories)} 板块 · {len(strengths)} 个强板块）")
        c.setFillColor(TEXT)
        c.setFont(FONT, 9.6)
        bullet_y = 555
        if strengths:
            for item in strengths[:5]:
                c.drawString(70, bullet_y, f"• {item.category} {item.score:.1f} 分（板块均）")
                bullet_y -= 18
        else:
            c.drawString(70, bullet_y, "• 暂无足够成绩判断强项")
            bullet_y -= 18
        full_count = sum(x == 100 for x in a.student.intro_scores if x is not None)
        c.drawString(70, bullet_y, f"• {full_count} 讲满分（100 分）")
        c.setFillColor(HEADING)
        c.setFont(FONT_BOLD, 13)
        c.drawString(48, 445, f"待加强（{sum(x.score is not None and x.score < 85 for x in a.categories)} 板块 · {len(a.low_lessons)} 个弱项讲次）")
        c.setFillColor(TEXT)
        c.setFont(FONT, 9.6)
        weak_y = 420
        if a.low_lessons:
            for number, lesson, score in a.low_lessons[:5]:
                c.drawString(70, weak_y, f"• {self._lesson_text(number, lesson, score)}")
                weak_y -= 18
        else:
            c.drawString(70, weak_y, "• 当前各讲分数稳定，建议保持综合训练。")
        notes = self._diagnostic_lines(a)
        self._multiline_box(c, 48, 166, 499, 195, notes)
        c.showPage()

    def _summary_page(self, c: Canvas, a: ReportAnalysis) -> None:
        self._page_base(c, a, "⑨ ● 整体分析")
        c.setFillColor(HEADING)
        c.setFont(FONT_BOLD, 13)
        c.drawString(70, 714, "整体评价")
        summary = self._summary_text(a)
        self._wrapped(c, summary, 70, 674, 474, 11, 20, TEXT)
        c.setFillColor(HexColor("#FFF8DF"))
        c.rect(70, 622, 476, 21, fill=1, stroke=0)
        c.setFillColor(MUTED)
        c.setFont(FONT, 8.7)
        c.drawString(80, 629, "评级算法：入班测与课堂巩固平均为基础；有期末测评时叠加班级百分位。")
        c.setFillColor(HEADING)
        c.setFont(FONT_BOLD, 13)
        self._emoji(c, "🚀", 70, 582, 15)
        c.drawString(91, 595, "暑假复习建议")
        c.setFillColor(TEXT)
        c.setFont(FONT_BOLD, 11.5)
        c.drawString(70, 567, "建议（得分 < 85，巩固提升）")
        advice_y = 542
        if a.low_lessons:
            c.setFont(FONT, 9.8)
            for number, lesson, score in a.low_lessons[:5]:
                c.drawString(96, advice_y, f"• {self._lesson_text(number, lesson, score)}")
                advice_y -= 20
        else:
            c.setFont(FONT, 9.8)
            c.drawString(96, advice_y, "• 暂无明显弱项，保持综合训练与复盘习惯。")
            advice_y -= 20
        c.setFillColor(HEADING)
        c.setFont(FONT_BOLD, 11.5)
        self._emoji(c, "📚", 70, advice_y - 29, 15)
        c.drawString(91, advice_y - 16, "复习方法（建议家长参与）")
        methods = [
            "家长版教材配套：每个知识点同步使用教材，由家长陪同复习讲解。",
            "同一知识点强化练习：每个知识点至少完成 3-5 道同类型练习题。",
            "每周安排 1 次错题讲解，重点复盘本报告中的待加强知识点。",
        ]
        c.setFillColor(TEXT)
        c.setFont(FONT, 9.4)
        for index, method in enumerate(methods, 1):
            c.drawString(96, advice_y - 42 - 22 * (index - 1), f"{index}. {method}")
        c.setStrokeColor(HexColor("#DDDDDD"))
        c.line(70, 336, 546, 336)
        c.setFillColor(MUTED)
        c.setFont(FONT, 8.5)
        c.drawCentredString(PAGE_W / 2, 318, f"本报告生成于 {self.settings.report_date.isoformat()}")
        c.drawCentredString(PAGE_W / 2, 302, f"{a.student.course_label} · {a.student.name} · {a.student.term} · {a.student.class_name} · 指导老师：{self.settings.teacher}")
        c.drawCentredString(PAGE_W / 2, 286, "本报告可能存在漏填或错填的情况，若有问题敬请谅解。")
        c.showPage()

    def _page_base(self, c: Canvas, a: ReportAnalysis, title: str) -> None:
        c.setFillColor(white)
        c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
        self._watermark(c, a)
        c.setFillColor(HEADING)
        c.setFont(FONT_BOLD, 15)
        c.drawString(48, 766, title)
        c.setStrokeColor(HEADING)
        c.setLineWidth(1.3)
        c.line(48, 753, PAGE_W - 48, 753)
        # Avoid collision with section titles that span most of the page width.
        if c.stringWidth(title, FONT_BOLD, 15) < 390:
            c.setFillColor(MUTED)
            c.setFont(FONT, 8)
            c.drawRightString(PAGE_W - 48, 766, f"{a.student.course_label} · {a.student.name} · {self.settings.teacher}")

    def _section(self, c: Canvas, title: str, y: float) -> None:
        c.setFillColor(HEADING)
        c.setFont(FONT_BOLD, 14.5)
        c.drawString(48, y, title)
        c.setStrokeColor(HEADING)
        c.setLineWidth(1.2)
        c.line(48, y - 11, PAGE_W - 48, y - 11)

    def _cards(self, c: Canvas, cards: list[tuple[str, str, Color]], y: float) -> None:
        width, gap, x = 77, 7, 48
        for value, label, color in cards:
            c.setFillColor(color)
            c.roundRect(x, y - 76, width, 66, 5, fill=1, stroke=0)
            c.setFillColor(white)
            c.setFont(FONT_BOLD, 14)
            c.drawCentredString(x + width / 2, y - 33, value)
            c.setFont(FONT, 7.4)
            self._center_wrapped(c, label, x + width / 2, y - 53, width - 8, 8.2, white)
            x += width + gap

    def _note(self, c: Canvas, text: str, y: float, icon: str = "📌") -> None:
        c.setFillColor(LIGHT_BLUE)
        c.roundRect(48, y - 18, 499, 20, 2, fill=1, stroke=0)
        self._emoji(c, icon, 55, y - 16, 12)
        c.setFillColor(MUTED)
        c.setFont(FONT, 8.4)
        c.drawString(71, y - 11, text)

    def _table(self, c: Canvas, x: float, y: float, widths: list[float], headers: list[str], rows: list[list[str]], font_size: float) -> float:
        header_h, row_h = 21, 20
        total = sum(widths)
        c.setFillColor(BLUE)
        c.rect(x, y - header_h, total, header_h, fill=1, stroke=0)
        cursor = x
        c.setFillColor(white)
        c.setFont(FONT_BOLD, font_size)
        for width, value in zip(widths, headers):
            c.drawCentredString(cursor + width / 2, y - 14, value)
            cursor += width
        y -= header_h
        for index, row in enumerate(rows):
            c.setFillColor(white if index % 2 == 0 else LIGHT_GREY)
            c.rect(x, y - row_h, total, row_h, fill=1, stroke=0)
            cursor = x
            for width, value in zip(widths, row):
                c.setFillColor(GREEN if value == "强" or (value.replace('.', '', 1).isdigit() and value != "—") else TEXT)
                c.setFont(FONT, font_size)
                self._center_ellipsize(c, value, cursor + width / 2, y - 14, width - 5, font_size)
                cursor += width
            y -= row_h
        return y

    def _mini_matrix(self, c: Canvas, x: float, y: float, rows: list[list[str]]) -> None:
        label_width, cell_width, row_h = 65, 34.4, 21
        for row_index, row in enumerate(rows):
            current_y = y - row_index * row_h
            c.setFillColor(BLUE if row_index == 0 else (LIGHT_BLUE if row_index % 2 else white))
            c.rect(x, current_y - row_h, label_width + cell_width * 14, row_h, fill=1, stroke=0)
            c.setFillColor(white if row_index == 0 else TEXT)
            c.setFont(FONT_BOLD if row_index == 0 else FONT, 7.3)
            self._center_ellipsize(c, row[0], x + label_width / 2, current_y - 14, label_width - 4, 7.3)
            for index, value in enumerate(row[1:]):
                color = GREEN if row_index == 3 and value not in ("—", "") and float(value) >= 85 else (ORANGE if row_index == 3 and value not in ("—", "") else (white if row_index == 0 else TEXT))
                c.setFillColor(color)
                self._center_ellipsize(c, value, x + label_width + cell_width * index + cell_width / 2, current_y - 14, cell_width - 3, 7.1)

    def _callout(self, c: Canvas, x: float, y: float, width: float, height: float, lines: list[tuple[str, Color, str]]) -> None:
        c.setFillColor(LIGHT_GREY)
        c.rect(x, y, width, height, fill=1, stroke=0)
        c.setFont(FONT_BOLD, 9.5)
        line_y = y + height - 20
        for icon, color, text in lines:
            c.setFillColor(color)
            self._emoji(c, icon, x + 11, line_y - 7, 13)
            self._wrapped(c, text, x + 30, line_y, width - 41, 9.5, 15, color, max_lines=2)
            line_y -= 32

    def _emoji(self, c: Canvas, icon: str, x: float, y: float, size: float) -> None:
        """Embed color Emoji as a transparent image; ReportLab fonts lack color-emoji support."""
        image = self._emoji_cache.get(icon)
        if image is None and EMOJI_FONT.exists():
            canvas_size = 160
            bitmap = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
            drawer = ImageDraw.Draw(bitmap)
            font = ImageFont.truetype(str(EMOJI_FONT), 116)
            drawer.text((16, 4), icon, font=font, embedded_color=True)
            bbox = bitmap.getbbox()
            if bbox:
                bitmap = bitmap.crop(bbox)
                padded = Image.new("RGBA", (bitmap.width + 12, bitmap.height + 12), (0, 0, 0, 0))
                padded.alpha_composite(bitmap, (6, 6))
                image = io.BytesIO()
                padded.save(image, format="PNG")
                image.seek(0)
                self._emoji_cache[icon] = image
        if image is not None:
            image.seek(0)
            c.drawImage(ImageReader(image), x, y, width=size, height=size, mask="auto")

    def _multiline_box(self, c: Canvas, x: float, y: float, width: float, height: float, lines: list[str]) -> None:
        c.setFillColor(HexColor("#E5F2FF"))
        c.rect(x, y, width, height, fill=1, stroke=0)
        c.setFillColor(DEEP_BLUE)
        c.rect(x, y, 4, height, fill=1, stroke=0)
        cursor = y + height - 22
        for line in lines:
            c.setFillColor(TEXT)
            c.setFont(FONT, 9.4)
            self._wrapped(c, line, x + 12, cursor, width - 24, 9.4, 18, TEXT, max_lines=2)
            cursor -= 34

    def _watermark(self, c: Canvas, a: ReportAnalysis, center_y: float = PAGE_H / 2) -> None:
        c.saveState()
        c.setFillColor(HexColor("#F3FAFD"))
        c.setFont(FONT_BOLD, 27)
        c.translate(PAGE_W / 2, center_y)
        c.rotate(36)
        c.drawCentredString(0, 0, f"{a.student.grade}{a.student.programme} · {a.student.term}")
        c.restoreState()

    def _charts_image(self, a: ReportAnalysis) -> io.BytesIO:
        set_matplotlib_font()
        figure = plt.figure(figsize=(8.2, 7.1), dpi=150)
        grid = figure.add_gridspec(2, 2, hspace=0.46, wspace=0.26)
        self._radar(figure.add_subplot(grid[0, 0], polar=True), a, "入班测板块雷达", False)
        self._radar(figure.add_subplot(grid[0, 1], polar=True), a, "课堂巩固板块雷达", True)
        self._bars(figure.add_subplot(grid[1, 0]), a.student.intro_scores, a.intro_class_average, "入班测 14 讲分数", "#3484A7")
        self._bars(figure.add_subplot(grid[1, 1]), a.student.consolidation_scores, a.consolidation_class_average, "课堂巩固 15 讲分数", "#21A34A")
        output = io.BytesIO()
        figure.savefig(output, format="png", bbox_inches="tight", facecolor="white")
        plt.close(figure)
        output.seek(0)
        return output

    def _radar(self, axis, a: ReportAnalysis, title: str, consolidation: bool) -> None:
        labels = category_labels(a.categories)
        personal = [item.score or 0 for item in a.categories] or [0]
        if consolidation:
            # Consolidation has no per-topic rubric: compare each category's matching lessons.
            class_values = []
            for item in a.categories:
                indices = [lesson.lesson - 1 for lesson in item.lessons if lesson.lesson <= 15]
                class_values.append(average_or_none([a.consolidation_class_average[i] for i in indices]) or 0)
                personal_value = average_or_none([a.student.consolidation_scores[i] for i in indices])
                if personal_value is not None:
                    personal[len(class_values) - 1] = personal_value
        else:
            class_values = []
            for item in a.categories:
                indices = [lesson.lesson - 1 for lesson in item.lessons if lesson.lesson <= 14]
                class_values.append(average_or_none([a.intro_class_average[i] for i in indices]) or 0)
        count = len(labels)
        angles = [2 * math.pi * n / count for n in range(count)]
        axis.set_theta_offset(math.pi / 2)
        axis.set_theta_direction(-1)
        axis.set_xticks(angles)
        axis.set_xticklabels(labels, fontsize=7)
        axis.set_ylim(0, 100)
        axis.set_yticks([20, 40, 60, 80, 100])
        axis.set_yticklabels(["20", "40", "60", "80", "100"], fontsize=5)
        closed_angles = angles + angles[:1]
        axis.plot(closed_angles, personal + personal[:1], color="#2687B6", linewidth=1.4, label="个人")
        axis.fill(closed_angles, personal + personal[:1], color="#2687B6", alpha=0.20)
        axis.plot(closed_angles, class_values + class_values[:1], color="#E76A77", linewidth=1.1, linestyle="--", label="班级均分")
        axis.set_title(title, fontsize=8, pad=14)
        axis.legend(loc="upper right", bbox_to_anchor=(1.24, 1.15), fontsize=5.5)

    @staticmethod
    def _bars(axis, personal: list[float | None], class_scores: list[float | None], title: str, color: str) -> None:
        xs = list(range(1, len(personal) + 1))
        personal_values = [x if x is not None else 0 for x in personal]
        class_values = [x if x is not None else 0 for x in class_scores]
        axis.bar([x - 0.2 for x in xs], personal_values, width=0.38, color=color, label="个人")
        axis.bar([x + 0.2 for x in xs], class_values, width=0.38, color="#E97985", alpha=0.9, label="班级均分")
        axis.set_ylim(0, 110)
        axis.set_title(title, fontsize=8)
        axis.set_xlabel("讲次", fontsize=6)
        axis.set_ylabel("分数", fontsize=6)
        axis.tick_params(labelsize=5.5)
        axis.legend(fontsize=5.5, loc="lower left")
        axis.grid(axis="y", alpha=0.2)

    @staticmethod
    def _lesson_text(number: int, lesson, score: float) -> str:
        if lesson is None:
            return f"第 {number} 讲 {display_score(score)} 分"
        return f"第 {number} 讲 · {lesson.topic}（{lesson.category}） {display_score(score)} 分"

    def _recommendation(self, a: ReportAnalysis) -> str:
        if not a.low_lessons:
            return "保持综合训练，8 月每周安排 1 次讲题复盘。"
        topics = " / ".join((lesson.topic if lesson else f"第{number}讲") for number, lesson, _ in a.low_lessons[:3])
        return f"8 月优先进行 {topics} 专题训练，每周复盘错题。"

    def _diagnostic_lines(self, a: ReportAnalysis) -> list[str]:
        final_text = "期末测评暂无数据，主要参考入班测与课堂巩固。"
        if a.final_score is not None and a.intro_average is not None:
            final_text = f"期末测评 {display_score(a.final_score)} 分，相比入班测 {a.final_score - a.intro_average:+.1f} 分。"
        strong = " / ".join(item.category for item in a.categories if item.score is not None and item.score >= 85) or "暂无"
        weak = " / ".join(lesson.topic for _, lesson, _ in a.low_lessons if lesson) or "暂无明显弱项"
        return [
            f"1. 错因定位：入班测 {fmt(a.intro_average, 2)} 分；{final_text}",
            f"2. 直觉建立：{strong} 板块基础较稳；待巩固：{weak}。",
            f"3. 讲解能力：课堂巩固 15 讲均 {fmt(a.consolidation_average, 2)} 分，建议每周安排 1 次讲题复盘。",
            f"4. 自适应出题：当前 {a.student.grade} {a.rating} 水平，强项可挑战综合应用 2-3 道。",
            f"5. 学习路线图：{self._recommendation(a)}",
        ]

    @staticmethod
    def _summary_text(a: ReportAnalysis) -> str:
        strong_count = sum(item.score is not None and item.score >= 85 for item in a.categories)
        final_text = "期末测评未参加" if a.final_score is None else f"期末测评 {display_score(a.final_score)} 分，班级排名 {a.final_rank}"
        overall = fmt(a.overall_score, 1)
        return (
            f"本次夏季班入班测 14 讲平均 {fmt(a.intro_average, 2)} 分，{strong_count} 个板块均不低于 85 分，"
            f"{len(a.low_lessons)} 个弱项讲次；课堂巩固 15 讲均 {fmt(a.consolidation_average, 2)} 分，{final_text}。"
            f"综合评分 {overall}/100，整体水平 {a.rating}。"
        )

    @staticmethod
    def _center_ellipsize(c: Canvas, text: object, x: float, y: float, width: float, font_size: float) -> None:
        value = str(text)
        while value and c.stringWidth(value, FONT, font_size) > width:
            value = value[:-1]
        if value != str(text) and len(value) > 1:
            value = value[:-1] + "…"
        c.drawCentredString(x, y, value)

    def _wrapped(self, c: Canvas, text: str, x: float, y: float, width: float, size: float, leading: float, color: Color, max_lines: int | None = None) -> int:
        c.setFillColor(color)
        c.setFont(FONT, size)
        lines: list[str] = []
        line = ""
        for character in text:
            candidate = line + character
            if c.stringWidth(candidate, FONT, size) > width and line:
                lines.append(line)
                line = character
            else:
                line = candidate
        if line:
            lines.append(line)
        if max_lines is not None:
            lines = lines[:max_lines]
        for index, line in enumerate(lines):
            c.drawString(x, y - index * leading, line)
        return len(lines)

    def _center_wrapped(self, c: Canvas, text: str, x: float, y: float, width: float, size: float, color: Color) -> None:
        c.setFillColor(color)
        c.setFont(FONT, size)
        if c.stringWidth(text, FONT, size) <= width:
            c.drawCentredString(x, y, text)
            return
        midpoint = max(1, len(text) // 2)
        c.drawCentredString(x, y, text[:midpoint])
        c.drawCentredString(x, y - size - 1, text[midpoint:])


def average_or_none(values: list[float | None]) -> float | None:
    available = [value for value in values if value is not None]
    return sum(available) / len(available) if available else None
