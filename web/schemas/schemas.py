from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime


# ==================== 专业年级 Schema ====================
class CohortBase(BaseModel):
    major: str = Field(..., description="专业名称", example="大数据")
    grade: int = Field(..., description="年级", example=1)
    is_graduation: bool = Field(default=False, description="是否毕业年级")


class CohortCreate(CohortBase):
    pass


class CohortUpdate(BaseModel):
    major: Optional[str] = None
    grade: Optional[int] = None
    is_graduation: Optional[bool] = None


class CohortResponse(CohortBase):
    id: int
    cohort_key: str = Field(..., description="专业年级标识")
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CohortWithClasses(CohortResponse):
    admin_classes: List["AdminClassResponse"] = []


# ==================== 行政班 Schema ====================
class AdminClassBase(BaseModel):
    class_index: int = Field(..., description="班级序号", example=1)
    student_count: int = Field(default=40, description="学生人数")
    is_graduation_class: bool = Field(default=False, description="是否毕业班(5-17周或 5-16周)")


class AdminClassCreate(AdminClassBase):
    cohort_id: int = Field(..., description="所属专业年级ID")


class AdminClassUpdate(BaseModel):
    class_index: Optional[int] = None
    student_count: Optional[int] = None
    is_graduation_class: Optional[bool] = None


class AdminClassResponse(AdminClassBase):
    id: int
    cohort_id: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
    class Config:
        from_attributes = True


# ==================== 教师 Schema ====================
class TeacherBase(BaseModel):
    name: str = Field(..., description="教师姓名", example="张三")
    is_campus_teacher: bool = Field(default=False, description="是否为校本部教师")


class TeacherCreate(TeacherBase):
    pass


class TeacherUpdate(BaseModel):
    name: Optional[str] = None
    is_campus_teacher: Optional[bool] = None


class TeacherResponse(TeacherBase):
    id: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ==================== 教师偏好 Schema ====================
class TimeSlotSchema(BaseModel):
    day: int = Field(..., ge=1, le=5, description="星期几(1-5)")
    period: int = Field(..., ge=-1, le=11, description="节次(1-11)，-1表示整天")


class TeacherPreferenceBase(BaseModel):
    course_id: Optional[int] = Field(None, description="针对特定课程的偏好")
    preferred_slots: List[List[int]] = Field(default=[], description="偏好时间段 [[day, period], ...]")
    undesired_slots: List[List[int]] = Field(default=[], description="不希望时间段 [[day, period], ...]")


class TeacherPreferenceCreate(TeacherPreferenceBase):
    teacher_id: int


class TeacherPreferenceResponse(TeacherPreferenceBase):
    id: int
    teacher_id: int

    class Config:
        from_attributes = True


# ==================== 机房 Schema ====================
class RoomBase(BaseModel):
    name: str = Field(..., description="机房名称", example="机房1")
    capacity: int = Field(default=50, description="容量")


class RoomCreate(RoomBase):
    pass


class RoomUpdate(BaseModel):
    name: Optional[str] = None
    capacity: Optional[int] = None


class RoomResponse(RoomBase):
    id: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ==================== 课程 Schema ====================
class CourseBase(BaseModel):
    name: str = Field(..., description="课程名称")
    cohort_id: Optional[int] = Field(None, description="所属专业年级ID(单专业课使用)")
    cohort_ids: List[int] = Field(default=[], description="多专业年级ID列表(多专业/公共课使用)")
    cohort_teaching_class_counts: Dict[str, float] = Field(default={}, description="各专业教学班数量配置 {cohort_id: count}")
    teacher_id: Optional[int] = Field(None, description="授课教师ID")
    course_type: str = Field(default="theory_only", description="课程类型: theory_only, mixed, lab_only")
    theory_hours: int = Field(default=0, ge=0, description="理论学时")
    lab_hours: int = Field(default=0, ge=0, description="实验学时")
    teaching_class_count: float = Field(default=1, gt=0, description="教学班数量(单专业课使用)")
    semester: str = Field(default="first", description="学期: first(上册), second(下册), both(全年)")
    # 双教师配置
    dual_teacher_enabled: bool = Field(default=False, description="是否双教师授课")
    second_teacher_id: Optional[int] = Field(None, description="第二位教师ID")
    teacher_split_week: int = Field(default=8, description="教师切换周次")
    # 毕业班课程配置
    is_graduation_course: bool = Field(default=False, description="是否毕业班课程(5-17周或 5-16周)")


class CourseCreate(CourseBase):
    preferred_pattern: Optional[str] = Field(None, description="排课周次模式")
    combined_with: List[int] = Field(default=[], description="合班课程ID列表")
    teacher_override: Dict[int, int] = Field(default={}, description="特定教学班的教师覆盖")
    phase_teachers: Dict[str, List] = Field(default={}, description="分阶段教师配置")


class CourseUpdate(BaseModel):
    name: Optional[str] = None
    cohort_id: Optional[int] = None
    cohort_ids: Optional[List[int]] = None
    cohort_teaching_class_counts: Optional[Dict[str, float]] = None
    teacher_id: Optional[int] = None
    course_type: Optional[str] = None
    theory_hours: Optional[int] = None
    lab_hours: Optional[int] = None
    teaching_class_count: Optional[float] = None
    semester: Optional[str] = None
    dual_teacher_enabled: Optional[bool] = None
    second_teacher_id: Optional[int] = None
    teacher_split_week: Optional[int] = None
    is_graduation_course: Optional[bool] = None
    preferred_pattern: Optional[str] = None
    combined_with: Optional[List[int]] = None
    teacher_override: Optional[Dict[int, int]] = None
    phase_teachers: Optional[Dict[str, List]] = None


class CourseResponse(CourseBase):
    id: int
    is_graduation_course: bool = False
    preferred_pattern: Optional[str] = None
    combined_with: List[int] = []
    teacher_override: Dict[str, Any] = {}
    phase_teachers: Dict[str, Any] = {}
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CourseWithDetails(CourseResponse):
    cohort: Optional[CohortResponse] = None
    teacher: Optional[TeacherResponse] = None


# ==================== 固定课程 Schema ====================
class FixedScheduleBase(BaseModel):
    cohort_id: int
    admin_class_ids: List[int] = Field(default=[], description="行政班ID列表，为空表示该专业年级全部行政班")
    course_name: str
    teacher_name: str
    duration: int = Field(default=2, ge=1, le=4)
    weeks: List[int]
    day: int = Field(..., ge=1, le=5)
    period: int = Field(..., ge=1, le=11)


class FixedScheduleCreate(FixedScheduleBase):
    pass


class FixedScheduleResponse(FixedScheduleBase):
    id: int

    class Config:
        from_attributes = True


# ==================== 子组预分配 Schema ====================
class SubgroupAssignmentBase(BaseModel):
    cohort_id: int
    group_tag: str
    ratio: float = Field(..., gt=0, le=1)


class SubgroupAssignmentCreate(SubgroupAssignmentBase):
    pass


class SubgroupAssignmentResponse(SubgroupAssignmentBase):
    id: int

    class Config:
        from_attributes = True


# ==================== 排课结果 Schema ====================
class ScheduleResultBase(BaseModel):
    teaching_class_id: str
    course_name: str
    teacher_name: str
    week: int
    day: int
    period: int
    duration: int = 2
    room_name: Optional[str] = None
    is_lab: bool = False
    is_combined: bool = False
    is_fixed: bool = False
    cohort_ids: List[int] = []
    subgroup_ids: List[str] = []


class ScheduleResultResponse(ScheduleResultBase):
    id: int
    session_id: str
    cohort_id: Optional[int] = None
    admin_class_id: Optional[int] = None
    admin_class_name: Optional[str] = None  # 行政班名称
    cohort_name: Optional[str] = None  # 专业年级名称
    week_str: Optional[str] = None  # 格式化的周次字符串，如 "第1-8周"
    course_type_str: Optional[str] = None  # 课程类型，如 "理论课"、"实验课"、"固定课"
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ScheduleResultUpdate(BaseModel):
    """手动调整课程时间"""
    week: Optional[int] = Field(None, ge=1, le=17)
    day: Optional[int] = Field(None, ge=1, le=5)
    period: Optional[int] = Field(None, ge=1, le=11)
    room_name: Optional[str] = None


# ==================== 排课会话 Schema ====================
class ScheduleSessionResponse(BaseModel):
    id: int
    session_id: str
    semester: str = "first"
    status: str
    fitness_score: Optional[float] = None
    message: Optional[str] = None
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ==================== 排课请求 Schema ====================
class StartScheduleRequest(BaseModel):
    """开始排课请求"""
    cohort_ids: Optional[List[int]] = Field(None, description="指定要排课的专业年级ID列表")
    semester: str = Field(default="first", description="学期: first(上册), second(下册)")


class ScheduleResponse(BaseModel):
    """排课响应"""
    session_id: str
    status: str
    message: str


# ==================== 课表视图 Schema ====================
class ScheduleSlot(BaseModel):
    """单个时间槽的课程信息"""
    id: int
    course_name: str
    teacher_name: str
    room_name: Optional[str]
    duration: int
    is_lab: bool
    is_combined: bool
    weeks: List[int]
    week_str: str  # 格式化的周次字符串


class DaySchedule(BaseModel):
    """一天的课表"""
    day: int
    periods: Dict[int, List[ScheduleSlot]]  # period -> list of courses


class WeekSchedule(BaseModel):
    """一周的课表"""
    cohort_id: int
    cohort_name: str
    days: List[DaySchedule]


# 解决循环引用
CohortWithClasses.model_rebuild()
