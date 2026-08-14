from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from .data import CourseLesson, StudentRecord


def average(values: list[float | None]) -> float | None:
    available = [value for value in values if value is not None]
    return round(sum(available) / len(available), 2) if available else None


def lesson_averages(rows: list[list[float | None]], lesson_count: int) -> list[float | None]:
    return [average([row[index] for row in rows if len(row) > index]) for index in range(lesson_count)]


def fmt(value: float | None, digits: int = 1, blank: str = "—") -> str:
    return blank if value is None else f"{value:.{digits}f}"


@dataclass(frozen=True)
class CategoryScore:
    category: str
    score: float | None
    lessons: list[CourseLesson]


@dataclass
class ReportAnalysis:
    student: StudentRecord
    intro_average: float | None
    consolidation_average: float | None
    final_score: float | None
    intro_class_average: list[float | None]
    consolidation_class_average: list[float | None]
    final_class_average: float | None
    final_class_median: float | None
    final_rank: str
    categories: list[CategoryScore]
    below_average_count: int
    low_lessons: list[tuple[int, CourseLesson | None, float]]
    completed_consolidation: int
    overall_score: float | None
    rating: str

    @property
    def category_map(self) -> dict[str, float | None]:
        return {item.category: item.score for item in self.categories}


def build_analysis(student: StudentRecord) -> ReportAnalysis:
    intro_avg = average(student.intro_scores)
    consolidation_avg = average(student.consolidation_scores)
    intro_class = lesson_averages(student.classmates_intro, 14)
    consolidation_class = lesson_averages(student.classmates_consolidation, 15)
    final_avg = average(student.classmates_final)
    final_median = round(median(student.classmates_final), 2) if student.classmates_final else None
    categories = category_scores(student.course, student.intro_scores)
    low_lessons = [
        (index + 1, student.course[index] if index < len(student.course) else None, score)
        for index, score in enumerate(student.intro_scores)
        if score is not None and score < 85
    ]
    comparison_count = sum(
        1
        for score, class_score in zip(student.intro_scores, intro_class)
        if score is not None and class_score is not None and score > class_score
    )
    final_rank = rank_text(student.final_score, student.classmates_final)
    overall = overall_score(intro_avg, consolidation_avg, student.final_score, student.classmates_final)
    return ReportAnalysis(
        student=student,
        intro_average=intro_avg,
        consolidation_average=consolidation_avg,
        final_score=student.final_score,
        intro_class_average=intro_class,
        consolidation_class_average=consolidation_class,
        final_class_average=final_avg,
        final_class_median=final_median,
        final_rank=final_rank,
        categories=categories,
        below_average_count=comparison_count,
        low_lessons=low_lessons,
        completed_consolidation=sum(score is not None for score in student.consolidation_scores),
        overall_score=overall,
        rating=rating(overall),
    )


def category_scores(course: list[CourseLesson], scores: list[float | None]) -> list[CategoryScore]:
    grouped: dict[str, list[tuple[CourseLesson, float | None]]] = {}
    for lesson in course[:14]:
        grouped.setdefault(lesson.category or "未分类", []).append((lesson, scores[lesson.lesson - 1]))
    return [
        CategoryScore(name, average([score for _, score in values]), [lesson for lesson, _ in values])
        for name, values in grouped.items()
    ]


def rank_text(score: float | None, peers: list[float]) -> str:
    if score is None or not peers:
        return "未参加"
    ordered = sorted(peers, reverse=True)
    first = ordered.index(score) + 1
    same = ordered.count(score)
    last = first + same - 1
    label = f"第 {first}" if first == last else f"第 {first}-{last}"
    return f"{label} / {len(ordered)} 人"


def overall_score(
    intro: float | None, consolidation: float | None, final: float | None, peers_final: list[float]
) -> float | None:
    primary = [score for score in (intro, consolidation) if score is not None]
    if not primary:
        return None
    # The final test has a variable raw maximum across classes. Its percentile, not raw score, is used.
    base = sum(primary) / len(primary)
    if final is None or not peers_final:
        return round(base, 1)
    percentile = sum(value <= final for value in peers_final) / len(peers_final) * 100
    return round(base * 0.8 + percentile * 0.2, 1)


def rating(score: float | None) -> str:
    if score is None:
        return "待补充"
    if score >= 90:
        return "卓越"
    if score >= 80:
        return "良好"
    if score >= 70:
        return "稳步提升"
    return "需要巩固"
