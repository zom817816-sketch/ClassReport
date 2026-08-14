from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd


LESSON_COLUMNS = [f"第{i}讲" for i in range(1, 16)]


def clean_text(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def normalise_name(value: object) -> str:
    """Match names while tolerating source-file nicknames in parentheses."""
    return re.sub(r"[（(].*?[）)]", "", clean_text(value)).strip()


def normalise_programme(value: object, grade: object) -> str:
    """The roster stores values such as ``L2光明顶`` while score files use ``光明顶``."""
    programme = clean_text(value)
    grade_text = clean_text(grade)
    return programme[len(grade_text) :] if grade_text and programme.startswith(grade_text) else programme


def normalise_phone_tail(value: object) -> str | None:
    """Preserve leading zeroes and remove pandas' ``.0`` representation."""
    if pd.isna(value) or clean_text(value) == "":
        return None
    numeric = pd.to_numeric(value, errors="coerce")
    if not pd.isna(numeric):
        return f"{int(numeric):04d}"
    digits = re.sub(r"\D", "", clean_text(value))
    return digits[-4:] if len(digits) >= 4 else None


def class_key(row: pd.Series) -> tuple[str, str, str, str]:
    grade = clean_text(row.get("年级"))
    return (
        clean_text(row.get("上课时间")),
        grade,
        normalise_programme(row.get("班型", row.get("夏季")), grade),
        clean_text(row.get("班级")),
    )


def student_key(row: pd.Series) -> tuple[str, str, str, str, str]:
    return (*class_key(row), normalise_name(row.get("学生姓名")))


def numeric_series(row: pd.Series, columns: Iterable[str]) -> list[float | None]:
    values: list[float | None] = []
    for column in columns:
        value = pd.to_numeric(row.get(column), errors="coerce")
        values.append(None if pd.isna(value) else float(value))
    return values


@dataclass(frozen=True)
class CourseLesson:
    lesson: int
    topic: str
    category: str


@dataclass
class StudentRecord:
    name: str
    term: str
    grade: str
    programme: str
    class_name: str
    phone_tail: str | None
    intro_scores: list[float | None]
    consolidation_scores: list[float | None]
    final_score: float | None
    course: list[CourseLesson]
    classmates_intro: list[list[float | None]]
    classmates_consolidation: list[list[float | None]]
    classmates_final: list[float]

    @property
    def course_label(self) -> str:
        return f"{self.grade}{self.programme} 夏季班"

    @property
    def display_class(self) -> str:
        return f"{self.term} · {self.class_name}"


@dataclass
class LoadedData:
    students: list[StudentRecord]
    issues: list[dict[str, str]]


class DataRepository:
    """Loads four source CSVs and produces report-ready student records."""

    FILES = {
        "course": "学生名单导入_16讲课程.csv",
        "intro": "学生名单导入_入门测分数.csv",
        "roster": "学生名单导入_学生名单_学员信息.csv",
        "final": "学生名单导入_期末测评分数.csv",
        "consolidation": "学生名单导入_课堂巩固分数.csv",
    }

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.issues: list[dict[str, str]] = []

    def _read(self, kind: str) -> pd.DataFrame:
        path = self.data_dir / self.FILES[kind]
        if not path.exists():
            raise FileNotFoundError(f"缺少数据文件：{path}")
        table = pd.read_csv(path, encoding="utf-8-sig")
        table = table.dropna(how="all").copy()
        for column in table.columns:
            if table[column].dtype == object:
                table[column] = table[column].map(clean_text)
        # The classroom-consolidation export has legacy headers shifted by one
        # column: 夏季=年级, 班级=班型, 年级=实际上课班级. Canonicalise it once
        # so all later joins use the same four fields as the other score files.
        if kind == "consolidation":
            grade = table["夏季"].copy()
            programme = table["班级"].copy()
            class_name = table["年级"].copy()
            table["年级"] = grade
            table["班型"] = programme
            table["班级"] = class_name
        return table

    @staticmethod
    def _index(table: pd.DataFrame) -> dict[tuple[str, str, str, str, str], pd.Series]:
        result: dict[tuple[str, str, str, str, str], pd.Series] = {}
        for _, row in table.iterrows():
            if not clean_text(row.get("学生姓名")):
                continue
            result[student_key(row)] = row
        return result

    def _courses(self, table: pd.DataFrame) -> dict[str, list[CourseLesson]]:
        courses: dict[str, list[CourseLesson]] = {}
        for label, group in table.dropna(subset=["班级", "讲次1"]).groupby("班级"):
            lessons = []
            for _, row in group.sort_values("讲次1").iterrows():
                lessons.append(
                    CourseLesson(int(row["讲次1"]), clean_text(row["知识点"]), clean_text(row["板块"]))
                )
            courses[clean_text(label)] = lessons
        return courses

    def load(self) -> LoadedData:
        course_table = self._read("course")
        intro = self._read("intro")
        roster = self._read("roster")
        final = self._read("final")
        consolidation = self._read("consolidation")

        course_by_label = self._courses(course_table)
        intro_index = self._index(intro)
        final_index = self._index(final)
        roster_index = self._index(roster)

        # Consolidation is the authoritative list: it has the complete 15-lesson roster.
        valid_consolidation = consolidation[consolidation["学生姓名"].map(clean_text).ne("")].copy()
        groups: dict[tuple[str, str, str, str], pd.DataFrame] = {}
        for _, group in valid_consolidation.groupby(["上课时间", "年级", "班型", "班级"], dropna=False):
            groups[class_key(group.iloc[0])] = group
        students: list[StudentRecord] = []
        for _, row in valid_consolidation.iterrows():
            key = student_key(row)
            class_id = class_key(row)
            intro_row = intro_index.get(key)
            final_row = final_index.get(key)
            roster_row = roster_index.get(key)
            programme = clean_text(row.get("班型"))
            course_label = f"{clean_text(row.get('年级'))}{programme}"
            course = course_by_label.get(course_label, [])
            if not course:
                self.issues.append(
                    {
                        "学员": clean_text(row["学生姓名"]),
                        "类型": "课程映射缺失",
                        "说明": f"未找到 {course_label} 的知识点映射，报告将仅展示成绩。",
                    }
                )

            if intro_row is None:
                self.issues.append(
                    {
                        "学员": clean_text(row["学生姓名"]),
                        "类型": "入门测缺失",
                        "说明": "未匹配到入门测记录。",
                    }
                )

            class_group = groups.get(class_id, valid_consolidation.iloc[0:0])
            class_intro = []
            class_final: list[float] = []
            for _, peer in class_group.iterrows():
                peer_key = student_key(peer)
                peer_intro = intro_index.get(peer_key)
                class_intro.append(numeric_series(peer_intro, LESSON_COLUMNS[:14]) if peer_intro is not None else [None] * 14)
                peer_final = final_index.get(peer_key)
                final_value = pd.to_numeric(
                    peer_final.get("期末测评分数") if peer_final is not None else None, errors="coerce"
                )
                if not pd.isna(final_value):
                    class_final.append(float(final_value))

            phone_tail = normalise_phone_tail(roster_row.get("手机号后四位")) if roster_row is not None else None
            if phone_tail is None:
                self.issues.append(
                    {
                        "学员": clean_text(row["学生姓名"]),
                        "类型": "手机号后四位缺失",
                        "说明": "未匹配到手机号后四位，将生成未加密 PDF。",
                    }
                )
            students.append(
                StudentRecord(
                    name=clean_text(row["学生姓名"]),
                    term=clean_text(row["上课时间"]),
                    grade=clean_text(row["年级"]),
                    programme=programme,
                    class_name=clean_text(row["班级"]),
                    phone_tail=phone_tail,
                    intro_scores=numeric_series(intro_row, LESSON_COLUMNS[:14]) if intro_row is not None else [None] * 14,
                    consolidation_scores=numeric_series(row, LESSON_COLUMNS),
                    final_score=self._score(final_row, "期末测评分数"),
                    course=course,
                    classmates_intro=class_intro,
                    classmates_consolidation=[numeric_series(peer, LESSON_COLUMNS) for _, peer in class_group.iterrows()],
                    classmates_final=class_final,
                )
            )
        return LoadedData(students=students, issues=self.issues)

    @staticmethod
    def _score(row: pd.Series | None, column: str) -> float | None:
        if row is None:
            return None
        score = pd.to_numeric(row.get(column), errors="coerce")
        return None if pd.isna(score) else float(score)
