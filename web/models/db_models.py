from sqlalchemy import Column, Integer, String, Boolean, Float, ForeignKey, Table, JSON, DateTime, Text, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..core.database import Base


# ==================== 专业年级（Cohort）====================
class Cohort(Base):
    """专业年级表"""
    __tablename__ = "cohorts"

    id = Column(Integer, primary_key=True, index=True)
    major = Column(String(100), nullable=False, comment="专业名称")
    grade = Column(Integer, nullable=False, comment="年级")
    is_graduation = Column(Boolean, default=False, comment="是否毕业年级")
    created_at = Column(DateTime, server_default=func.now())

    # 关联
    admin_classes = relationship("AdminClass", back_populates="cohort", cascade="all, delete-orphan")
    courses = relationship("Course", back_populates="cohort", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint('major', 'grade', name='uq_cohort_major_grade'),
    )

    @property
    def cohort_key(self) -> str:
        return f"{self.major}-{self.grade}"


# ==================== 行政班 ====================
class AdminClass(Base):
    """行政班表"""
    __tablename__ = "admin_classes"

    id = Column(Integer, primary_key=True, index=True)
    cohort_id = Column(Integer, ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False)
    class_index = Column(Integer, nullable=False, comment="班级序号")
    student_count = Column(Integer, default=40, comment="学生人数")
    is_graduation_class = Column(Boolean, default=False, comment="是否毕业班(5-17周或 5-16周)")
    created_at = Column(DateTime, server_default=func.now())

    # 关联
    cohort = relationship("Cohort", back_populates="admin_classes")


# ==================== 教师 ====================
class Teacher(Base):
    """教师表"""
    __tablename__ = "teachers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True, comment="教师姓名")
    is_campus_teacher = Column(Boolean, default=False, comment="是否为校本部教师")
    created_at = Column(DateTime, server_default=func.now())

    # 关联 - 明确指定foreign_keys解决多外键关系歧义
    courses = relationship("Course", back_populates="teacher", foreign_keys="[Course.teacher_id]")
    courses_as_second = relationship("Course", foreign_keys="[Course.second_teacher_id]")
    preferences = relationship("TeacherPreference", back_populates="teacher", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_teacher_name', 'name'),
    )


# ==================== 教师偏好 ====================
class TeacherPreference(Base):
    """教师时间偏好表"""
    __tablename__ = "teacher_preferences"

    id = Column(Integer, primary_key=True, index=True)
    teacher_id = Column(Integer, ForeignKey("teachers.id", ondelete="CASCADE"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=True, comment="针对特定课程的偏好")
    preferred_slots = Column(JSON, default=list, comment="偏好时间段 [[day, period], ...]")
    undesired_slots = Column(JSON, default=list, comment="不希望时间段 [[day, period], ...]")

    # 关联
    teacher = relationship("Teacher", back_populates="preferences")
    course = relationship("Course", back_populates="preferences")


# ==================== 机房 ====================
class Room(Base):
    """机房表"""
    __tablename__ = "rooms"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True, comment="机房名称")
    capacity = Column(Integer, default=50, comment="容量")
    created_at = Column(DateTime, server_default=func.now())


# ==================== 合班课程组 ====================
class CombinedCourseGroup(Base):
    """合班课程组表 - 用于定义跨专业合班课程"""
    __tablename__ = "combined_course_groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, comment="合班组名称，如'数字逻辑电路合班组'")
    description = Column(Text, nullable=True, comment="描述")
    created_at = Column(DateTime, server_default=func.now())

    # 关联
    courses = relationship("Course", back_populates="combined_group")


# ==================== 课程 ====================
class Course(Base):
    """课程表"""
    __tablename__ = "courses"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, comment="课程名称")
    cohort_id = Column(Integer, ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=True, comment="所属专业年级(单专业课使用)")
    cohort_ids = Column(JSON, default=list, comment="多专业年级ID列表(多专业/公共课使用)")
    cohort_teaching_class_counts = Column(JSON, default=dict, comment="各专业教学班数量配置 {cohort_id: count}")
    teacher_id = Column(Integer, ForeignKey("teachers.id", ondelete="SET NULL"), nullable=True, comment="授课教师")

    # 学期配置
    semester = Column(String(10), default="first", comment="学期: first(上册), second(下册), both(全年)")

    # 课程类型：theory_only, mixed, lab_only
    course_type = Column(String(20), default="theory_only", comment="课程类型")
    theory_hours = Column(Integer, default=0, comment="理论学时")
    lab_hours = Column(Integer, default=0, comment="实验学时")
    total_hours = Column(Integer, default=0, comment="总学时(用于确定排课模式)")
    teaching_class_count = Column(Float, default=1, comment="教学班数量，支持小数如0.5表示合班")

    # 学时模式配置 (16学时:单周每周一次, 32学时:每周一次, 48学时:每周一次连上3节, 64学时:每周二次, 96学时:每周三次)
    hours_pattern = Column(String(50), nullable=True, comment="学时模式: single_week(单周), double_week(双周), every_week(每周), custom")
    sessions_per_week = Column(Integer, default=1, comment="每周次数")
    duration_per_session = Column(Integer, default=2, comment="每次连上节数")

    # 合班课程组关联
    combined_group_id = Column(Integer, ForeignKey("combined_course_groups.id", ondelete="SET NULL"), nullable=True, comment="合班课程组ID")

    # 双教师配置 (A教师上1-8周，B教师上9-16周)
    dual_teacher_enabled = Column(Boolean, default=False, comment="是否双教师授课")
    second_teacher_id = Column(Integer, ForeignKey("teachers.id", ondelete="SET NULL"), nullable=True, comment="第二位教师")
    teacher_split_week = Column(Integer, default=8, comment="教师切换周次(第一位教师上1-N周)")

    # 可选配置
    preferred_pattern = Column(String(50), nullable=True, comment="排课周次模式")
    start_week = Column(Integer, default=1, comment="开始周次")
    end_week = Column(Integer, default=16, comment="结束周次")
    combined_with = Column(JSON, default=list, comment="合班课程ID列表（已废弃，使用combined_group_id）")
    teacher_override = Column(JSON, default=dict, comment="特定教学班的教师覆盖 {班号: 教师ID}【已废弃，使用teacher_configs】")
    teacher_configs = Column(JSON, default=list, comment="多教师配置 [{teacher_id, class_count, dual_enabled, second_teacher_id, split_week}]")
    phase_teachers = Column(JSON, default=dict, comment="分阶段教师 {阶段: [起始周, 结束周, 教师ID]}")

    # 毕业年级特殊处理
    is_graduation_course = Column(Boolean, default=False, comment="是否毕业年级课程(5-17周或 5-16周)")

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # 关联
    cohort = relationship("Cohort", back_populates="courses")
    teacher = relationship("Teacher", back_populates="courses", foreign_keys=[teacher_id])
    second_teacher = relationship("Teacher", foreign_keys=[second_teacher_id], overlaps="courses_as_second")
    combined_group = relationship("CombinedCourseGroup", back_populates="courses")
    preferences = relationship("TeacherPreference", back_populates="course", cascade="all, delete-orphan")


# ==================== 固定课程（公共课）====================
class FixedSchedule(Base):
    """固定课程表（公共课）
    
    公共课与虚拟子组关系：
    - 同一专业年级同一门公共课在相同时间点上课：不为子组贴标签
    - 同一门公共课不同时间点上课，教学班不按顺序分配：为子组设置标签(标签数=行政班数)
    - 同一门公共课不同时间点上课，教学班按顺序分配：为子组设置标签(标签数=教学班数)
    """
    __tablename__ = "fixed_schedules"

    id = Column(Integer, primary_key=True, index=True)
    cohort_id = Column(Integer, ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False)
    semester = Column(String(10), default="first", comment="学期: first(上册), second(下册), both(全年)")
    
    # 行政班配置：指定哪些行政班上这门固定课，为空表示全部行政班
    admin_class_ids = Column(JSON, default=list, comment="行政班ID列表，为空表示该专业年级全部行政班")
    
    course_name = Column(String(200), nullable=False, comment="课程名称")
    teacher_name = Column(String(100), nullable=False, comment="教师姓名")
    duration = Column(Integer, default=2, comment="持续节次")
    weeks = Column(JSON, nullable=False, comment="周次列表")
    day = Column(Integer, nullable=False, comment="星期几(1-5)")
    period = Column(Integer, nullable=False, comment="开始节次(1-11)")

    # 关联
    cohort = relationship("Cohort")


# ==================== 子组预分配 ====================
class SubgroupAssignment(Base):
    """子组预分配配置表"""
    __tablename__ = "subgroup_assignments"

    id = Column(Integer, primary_key=True, index=True)
    cohort_id = Column(Integer, ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False)
    group_tag = Column(String(50), nullable=False, comment="子组标签")
    ratio = Column(Float, nullable=False, comment="比例")

    # 关联
    cohort = relationship("Cohort")


# ==================== 排课结果 ====================
class ScheduleResult(Base):
    """排课结果表 - 按行政班输出"""
    __tablename__ = "schedule_results"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(50), nullable=False, index=True, comment="排课会话ID")
    
    # 行政班关联(按行政班输出课表)
    admin_class_id = Column(Integer, ForeignKey("admin_classes.id", ondelete="CASCADE"), nullable=True, comment="行政班ID")
    cohort_id = Column(Integer, ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=True, comment="专业年级ID")
    
    teaching_class_id = Column(String(100), nullable=False, comment="教学班ID")
    subgroup_ids = Column(JSON, default=list, comment="涉及的虚拟子组ID列表")
    
    course_name = Column(String(200), nullable=False)
    teacher_name = Column(String(100), nullable=False)
    week = Column(Integer, nullable=False, comment="周次")
    day = Column(Integer, nullable=False, comment="星期几")
    period = Column(Integer, nullable=False, comment="开始节次")
    duration = Column(Integer, default=2, comment="持续节次")
    room_name = Column(String(100), nullable=True, comment="教室名称")
    is_lab = Column(Boolean, default=False, comment="是否为实验课")
    is_combined = Column(Boolean, default=False, comment="是否为合班课")
    is_fixed = Column(Boolean, default=False, comment="是否为固定课程")
    cohort_ids = Column(JSON, default=list, comment="涉及的专业年级ID列表")

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # 关联
    admin_class = relationship("AdminClass")
    cohort = relationship("Cohort")

    __table_args__ = (
        Index('idx_schedule_session', 'session_id'),
        Index('idx_schedule_teaching_class', 'teaching_class_id'),
        Index('idx_schedule_admin_class', 'admin_class_id'),
    )


# ==================== 排课会话 ====================
class ScheduleSession(Base):
    """排课会话表（记录每次排课）"""
    __tablename__ = "schedule_sessions"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(50), unique=True, nullable=False, comment="会话ID")
    semester = Column(String(10), default="first", comment="排课学期: first(上册), second(下册)")
    status = Column(String(50), default="pending", comment="状态: pending, running, completed, completed_with_warnings, failed")
    fitness_score = Column(Float, nullable=True, comment="适应度分数")
    penalty_details = Column(JSON, nullable=True, comment="惩罚分数详情")
    message = Column(Text, nullable=True, comment="消息")
    created_at = Column(DateTime, server_default=func.now())
    completed_at = Column(DateTime, nullable=True)
