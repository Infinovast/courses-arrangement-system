from dataclasses import dataclass, field
from typing import Dict, Literal, Optional, Tuple, List

CourseType = Literal['theory_only', 'mixed', 'lab_only']
SchedulePattern = Literal[
    'weekly', 'single_week', 'double_week', 'flexible_48h', 'weeks_1_to_14', 'weeks_5_to_16', 'weeks_5_to_17',
    'weeks_6_to_17', 'weeks_1_to_8', 'weeks_9_to_16', 'weeks_16_to_17'
]


@dataclass
class Course:
    id: str
    name: str
    course_type: CourseType
    theory_hours: int = 0
    lab_hours: int = 0
    teaching_class_count: float = 1
    preferred_pattern: Optional[SchedulePattern] = None
    combined_with: List[str] = field(default_factory=list)
    teacher_override: Optional[Dict[int, str]] = None
    campus_teachers: List[str] = field(default_factory=list)

    # 新增：分阶段教师配置（key：阶段标识，value：(起始周, 结束周, 教师ID)）
    # 示例：{"phase1": (1,8,"T01"), "phase2": (9,16,"T02")}
    phase_teachers: Optional[Dict[str, Tuple[int, int, str]]] = None

    def __post_init__(self):
        if isinstance(self.teaching_class_count, float):
            if not self.teaching_class_count.is_integer() and not self.combined_with:
                raise ValueError("非整数教学班数量必须指定合班课程")

    def is_taught_by_campus_teacher(self, teacher_name: str) -> bool:
        return teacher_name in self.campus_teachers

    def get_schedule_requirements(self, cohort_weekly_hours: Tuple[int, int] = None) -> Dict[str, Dict]:
        reqs = {}
        if self.theory_hours > 0:
            reqs['theory'] = self._calculate_pattern(
                hours=self.theory_hours,
                is_lab=False,
                cohort_weekly_hours=cohort_weekly_hours
            )
        if self.lab_hours > 0:
            reqs['lab'] = self._calculate_pattern(
                hours=self.lab_hours,
                is_lab=True,
                cohort_weekly_hours=cohort_weekly_hours
            )
        return reqs

    def _calculate_pattern(self, hours: int, is_lab: bool, cohort_weekly_hours: Tuple[int, int] = None) -> Dict:
        if hours == 48:
            return self._handle_48_hours(hours, is_lab, cohort_weekly_hours)
        elif hours == 32:
            return {'pattern': 'weekly', 'hours_per_block': 2, 'total_blocks': 16, 'weekly_sessions': 1}
        elif hours == 56:
            return {'pattern': 'weeks_1_to_14', 'hours_per_block': 2, 'total_blocks': 28, 'weekly_sessions': 2}
        elif hours == 64:
            return {'pattern': 'weekly', 'hours_per_block': 2, 'total_blocks': 32, 'weekly_sessions': 2}
        elif hours == 96:
            return {'pattern': 'weekly', 'hours_per_block': 2, 'total_blocks': 48, 'weekly_sessions': 3}
        elif hours == 16:
            return self._handle_16_hours(hours, is_lab, cohort_weekly_hours)

        if self.preferred_pattern:
            if self.preferred_pattern == 'weeks_1_to_8' and hours == 16:
                return {'pattern': 'weeks_1_to_8', 'hours_per_block': 2, 'total_blocks': 8, 'weekly_sessions': 1}
            if self.preferred_pattern == 'weeks_9_to_16' and hours == 16:
                return {'pattern': 'weeks_9_to_16', 'hours_per_block': 2, 'total_blocks': 8, 'weekly_sessions': 1}
            if self.preferred_pattern == 'weeks_5_to_16' and hours == 48:
                return {'pattern': 'weeks_5_to_16', 'hours_per_block': 2, 'total_blocks': 24, 'weekly_sessions': 2}
            if self.preferred_pattern == 'weeks_5_to_17' and hours == 26:
                return {'pattern': 'weeks_5_to_17', 'hours_per_block': 2, 'total_blocks': 13, 'weekly_sessions': 1}
            if self.preferred_pattern == 'weeks_16_to_17' and hours == 6:
                return {'pattern': 'weeks_16_to_17', 'hours_per_block': 3, 'total_blocks': 2, 'weekly_sessions': 1}

        raise ValueError(f"课程 '{self.name}' (ID: {self.id}) 的学时 {hours} 没有找到匹配的排课规则。")

    def _handle_48_hours(self, hours: int, is_lab: bool, cohort_weekly_hours: Tuple[int, int]) -> Dict:
        if cohort_weekly_hours is None:
            return {
                'pattern': 'weekly',
                'hours_per_block': 3,
                'total_blocks': 16,
                'weekly_sessions': 1,
                'description': '每周3学时'
            }

        single_week_hours, double_week_hours = cohort_weekly_hours

        if single_week_hours <= double_week_hours:
            return {
                'pattern': 'flexible_48h',
                'hours_per_block': 2,
                'single_week_hours': 4,
                'double_week_hours': 2,
                'total_blocks': 24,
                'description': '动态分配(单周4h/双周2h)'
            }
        else:
            return {
                'pattern': 'flexible_48h',
                'hours_per_block': 2,
                'single_week_hours': 2,
                'double_week_hours': 4,
                'total_blocks': 24,
                'description': '动态分配(单周2h/双周4h)'
            }

    def _handle_16_hours(self, hours: int, is_lab: bool, cohort_weekly_hours: Tuple[int, int]) -> Dict:
        if cohort_weekly_hours is None:
            return {
                'pattern': 'single_week',
                'hours_per_block': 2,
                'total_blocks': 8,
                'weekly_sessions': 1,
                'description': '单周2学时'
            }

        single_week_hours, double_week_hours = cohort_weekly_hours

        if single_week_hours <= double_week_hours:
            return {
                'pattern': 'single_week',
                'hours_per_block': 2,
                'total_blocks': 8,
                'weekly_sessions': 1,
                'description': '单周2学时'
            }
        else:
            return {
                'pattern': 'double_week',
                'hours_per_block': 2,
                'total_blocks': 8,
                'weekly_sessions': 1,
                'description': '双周2学时'
            }