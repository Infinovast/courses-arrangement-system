from dataclasses import dataclass, field
from typing import Optional, List, Tuple
from .course import Course


@dataclass(frozen=True, eq=True)
class Cohort:
    major: str
    grade: int
    id: str = field(init=False)

    def __post_init__(self):
        object.__setattr__(self, 'id', f"{self.major}-{self.grade}")

    def __hash__(self):
        return hash(self.id)

    def __lt__(self, other):
        if not isinstance(other, Cohort):
            return NotImplemented
        return self.grade > other.grade


@dataclass
class SubGroup:
    id: str
    cohort: Cohort
    fixed_schedule_tag: Optional[str] = None


@dataclass
class TeachingClass:
    id: str
    course: Course
    class_number: int
    teacher_name: str
    is_combined: bool = False
    subgroups: List[SubGroup] = field(default_factory=list, repr=False)

    # 阶段信息（用于分阶段授课）
    phase: Optional[str] = None  # 阶段标识（如"phase1"）
    phase_weeks: Optional[Tuple[int, int]] = None  # 阶段周次范围（如(1,8)）

    @property
    def main_cohort(self) -> Optional[Cohort]:
        if self.subgroups:
            return self.subgroups[0].cohort
        return None

    # 新增：获取该阶段实际有效的周次列表
    def get_effective_weeks(self) -> List[int]:
        if not self.phase_weeks:
            return []
        start, end = self.phase_weeks
        return list(range(start, end + 1))

    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        if not isinstance(other, TeachingClass):
            return NotImplemented
        return self.id == other.id


@dataclass
class AdminClass:
    id: str
    cohort: Cohort
    class_index: int
    student_count: int

    def __post_init__(self):
        object.__setattr__(self, 'id', f"{self.cohort.major}-{self.cohort.grade}-{self.class_index}")

    def __hash__(self):
        return hash(self.id)