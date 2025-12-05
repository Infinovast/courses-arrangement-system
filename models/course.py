from dataclasses import dataclass, field
from typing import Dict, Literal, Optional, Tuple, List

CourseType = Literal['theory_only', 'mixed', 'lab_only']
SchedulePattern = Literal[
    'weekly', 'single_week', 'double_week', 'flexible_48h', 'weeks_1_to_14', 'weeks_5_to_15', 'weeks_5_to_16', 'weeks_5_to_17',
    'weeks_6_to_17', 'weeks_1_to_8', 'weeks_9_to_16', 'weeks_16_to_17',
    'graduation_48h', 'graduation_32h_main', 'graduation_32h_makeup'  # 毕业班特殊模式
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
    is_graduation_course: bool = False  # 毕业班课程标志

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
        
        # 毕业班课程特殊处理
        if self.is_graduation_course:
            return self._get_graduation_requirements()
        
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
    
    def _get_graduation_requirements(self) -> Dict[str, Dict]:
        """毕业班课程特殊排课逻辑
        
        48学时课程: 第5-16周每周上2次课，每次连上2节
            - 12周 x 2次 x 2节 = 48学时
        
        32学时课程: 第5-15周每周上1次课，每次连上2节；第16-17周每周上2次，一次连上2节，另一次连上3节
            - 11周 x 1次 x 2节 = 22学时
            - 2周 x 1次 x 2节 = 4学时
            - 2周 x 1次 x 3节 = 6学时
            - 总计: 22 + 4 + 6 = 32学时
        """
        reqs = {}
        total_hours = self.theory_hours + self.lab_hours
        is_lab = self.course_type == 'lab_only'
        
        if total_hours == 48:
            # 48学时: 第5-16周，每周上2次，每次连上2节
            part_key = 'lab' if is_lab else 'theory'
            reqs[part_key] = {
                'pattern': 'graduation_48h',
                'hours_per_block': 2,
                'total_blocks': 24,  # 12周 x 2次
                'weekly_sessions': 2,
                'description': '毕业班48学时: 第5-16周每周上2次课，每次连上2节'
            }
        elif total_hours == 32:
            # 32学时: 拆分为两部分
            part_key = 'lab' if is_lab else 'theory'
            # 主要部分: 第5-15周，每周上1次，每次连上2节 (22学时)
            reqs[part_key] = {
                'pattern': 'graduation_32h_main',
                'hours_per_block': 2,
                'total_blocks': 11,  # 11周 x 1次
                'weekly_sessions': 1,
                'description': '毕业班32学时主体: 第5-15周每周上1次课，每次连上2节'
            }
            # 补课部分: 第16-17周，每周上2次 (2节+3节=5学时 x 2周 = 10学时)
            # 由于32学时-22学时=10学时，需要2周补课
            reqs[f'{part_key}_makeup_2h'] = {
                'pattern': 'weeks_16_to_17',
                'hours_per_block': 2,
                'total_blocks': 2,  # 2周 x 1次
                'weekly_sessions': 1,
                'description': '毕业班32学时补课: 第16-17周每周上1次课，每次连上2节'
            }
            reqs[f'{part_key}_makeup_3h'] = {
                'pattern': 'weeks_16_to_17',
                'hours_per_block': 3,
                'total_blocks': 2,  # 2周 x 1次
                'weekly_sessions': 1,
                'description': '毕业班32学时补课: 第16-17周每周上1次课，每次连上3节'
            }
        else:
            # 其他学时的毕业班课程，默认使用5-17周
            part_key = 'lab' if is_lab else 'theory'
            reqs[part_key] = {
                'pattern': 'weeks_5_to_17',
                'hours_per_block': 2,
                'total_blocks': total_hours // 2,
                'weekly_sessions': 1,
                'description': f'毕业班{total_hours}学时: 第5-17周'
            }
        
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
            if self.preferred_pattern == 'weeks_5_to_15' and hours == 22:
                return {'pattern': 'weeks_5_to_15', 'hours_per_block': 2, 'total_blocks': 11, 'weekly_sessions': 1}
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