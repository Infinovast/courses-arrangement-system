"""
课程管理 API
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional, Any, Dict

from ..core.database import get_db
from ..models.db_models import Course, Cohort, Teacher, TeacherPreference, FixedSchedule
from ..schemas.schemas import (
    CourseCreate, CourseUpdate, CourseResponse, CourseWithDetails,
    TeacherPreferenceCreate, TeacherPreferenceResponse,
    FixedScheduleCreate, FixedScheduleResponse
)

router = APIRouter(prefix="/courses", tags=["课程管理"])


@router.get("", response_model=List[CourseWithDetails], summary="获取所有课程")
def get_courses(
    cohort_id: Optional[int] = Query(None, description="按专业年级筛选"),
    teacher_id: Optional[int] = Query(None, description="按教师筛选"),
    semester: Optional[str] = Query(None, description="按学期筛选: first(上册), second(下册), both(全年)"),
    db: Session = Depends(get_db)
):
    """获取所有课程列表，可按专业年级、教师或学期筛选"""
    query = db.query(Course).options(
        joinedload(Course.cohort),
        joinedload(Course.teacher)
    )

    if cohort_id:
        query = query.filter(Course.cohort_id == cohort_id)
    if teacher_id:
        query = query.filter(Course.teacher_id == teacher_id)
    if semester:
        query = query.filter(Course.semester == semester)

    courses = query.order_by(Course.cohort_id, Course.name).all()

    # 构建响应
    result = []
    for course in courses:
        course_dict = {
            "id": course.id,
            "name": course.name,
            "cohort_id": course.cohort_id,
            "cohort_ids": course.cohort_ids or [],
            "cohort_teaching_class_counts": course.cohort_teaching_class_counts or {},
            "teacher_id": course.teacher_id,
            "course_type": course.course_type,
            "theory_hours": course.theory_hours,
            "lab_hours": course.lab_hours,
            "teaching_class_count": course.teaching_class_count,
            "semester": course.semester or "first",
            "dual_teacher_enabled": course.dual_teacher_enabled or False,
            "second_teacher_id": course.second_teacher_id,
            "teacher_split_week": course.teacher_split_week or 8,
            "is_graduation_course": course.is_graduation_course or False,
            "preferred_pattern": course.preferred_pattern,
            "combined_with": course.combined_with or [],
            "teacher_override": course.teacher_override or {},
            "teacher_configs": course.teacher_configs or [],
            "phase_teachers": course.phase_teachers or {},
            "created_at": course.created_at,
            "updated_at": course.updated_at,
            "cohort": {
                "id": course.cohort.id,
                "major": course.cohort.major,
                "grade": course.cohort.grade,
                "is_graduation": course.cohort.is_graduation or False,
                "cohort_key": f"{course.cohort.major}-{course.cohort.grade}",
                "created_at": course.cohort.created_at
            } if course.cohort else None,
            "teacher": {
                "id": course.teacher.id,
                "name": course.teacher.name,
                "is_campus_teacher": course.teacher.is_campus_teacher,
                "created_at": course.teacher.created_at
            } if course.teacher else None
        }
        result.append(course_dict)

    return result


@router.get("/{course_id}", response_model=CourseWithDetails, summary="获取课程详情")
def get_course(course_id: int, db: Session = Depends(get_db)):
    """获取指定课程详情"""
    course = db.query(Course).options(
        joinedload(Course.cohort),
        joinedload(Course.teacher)
    ).filter(Course.id == course_id).first()

    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")

    return {
        "id": course.id,
        "name": course.name,
        "cohort_id": course.cohort_id,
        "cohort_ids": course.cohort_ids or [],
        "cohort_teaching_class_counts": course.cohort_teaching_class_counts or {},
        "teacher_id": course.teacher_id,
        "course_type": course.course_type,
        "theory_hours": course.theory_hours,
        "lab_hours": course.lab_hours,
        "teaching_class_count": course.teaching_class_count,
        "semester": course.semester or "first",
        "dual_teacher_enabled": course.dual_teacher_enabled or False,
        "second_teacher_id": course.second_teacher_id,
        "teacher_split_week": course.teacher_split_week or 8,
        "is_graduation_course": course.is_graduation_course or False,
        "preferred_pattern": course.preferred_pattern,
        "combined_with": course.combined_with or [],
        "teacher_override": course.teacher_override or {},
        "teacher_configs": course.teacher_configs or [],
        "phase_teachers": course.phase_teachers or {},
        "created_at": course.created_at,
        "updated_at": course.updated_at,
        "cohort": {
            "id": course.cohort.id,
            "major": course.cohort.major,
            "grade": course.cohort.grade,
            "is_graduation": course.cohort.is_graduation or False,
            "cohort_key": f"{course.cohort.major}-{course.cohort.grade}",
            "created_at": course.cohort.created_at
        } if course.cohort else None,
        "teacher": {
            "id": course.teacher.id,
            "name": course.teacher.name,
            "is_campus_teacher": course.teacher.is_campus_teacher,
            "created_at": course.teacher.created_at
        } if course.teacher else None
    }


def _validate_cohort_teaching_class_counts(cohort_ids: List[int], counts: Dict[str, float], db: Session):
    """校验多专业教学班配置
    
    1. 所有cohort_ids中的专业都必须存在
    2. counts中的cohort_id必须在cohort_ids中
    3. 所有教学班数量总和必须是整数
    """
    if not cohort_ids:
        return
    
    # 验证所有专业都存在
    for cid in cohort_ids:
        cohort = db.query(Cohort).filter(Cohort.id == cid).first()
        if not cohort:
            raise HTTPException(status_code=404, detail=f"专业年级ID {cid} 不存在")
    
    # 多专业时需要校验教学班配置
    if len(cohort_ids) > 1:
        if not counts:
            raise HTTPException(status_code=400, detail="多专业课程必须配置各专业的教学班数量")
        
        # 校验counts中的cohort_id是否都在cohort_ids中
        for cid_str in counts.keys():
            if int(cid_str) not in cohort_ids:
                raise HTTPException(status_code=400, detail=f"教学班配置中的专业ID {cid_str} 不在选择的专业列表中")
        
        # 校验总和是否为整数
        total = sum(counts.values())
        if not total.is_integer():
            raise HTTPException(status_code=400, detail=f"各专业教学班数量总和必须是整数，当前总和为 {total}")


@router.post("", response_model=CourseResponse, status_code=status.HTTP_201_CREATED, summary="添加课程")
def create_course(data: CourseCreate, db: Session = Depends(get_db)):
    """添加新课程
    
    课程分类：
    - 专业课：cohort_id不为空，或cohort_ids只有一个元素
    - 公共课：cohort_id为空且cohort_ids为空，或cohort_ids有多个元素
    """
    # 判断是单专业还是多专业
    is_multi_cohort = len(data.cohort_ids) > 1
    is_single_cohort = data.cohort_id is not None or len(data.cohort_ids) == 1
    
    # 验证专业年级存在
    if is_single_cohort and not is_multi_cohort:
        # 单专业课
        effective_cohort_id = data.cohort_id if data.cohort_id else (data.cohort_ids[0] if data.cohort_ids else None)
        if effective_cohort_id:
            cohort = db.query(Cohort).filter(Cohort.id == effective_cohort_id).first()
            if not cohort:
                raise HTTPException(status_code=404, detail="专业年级不存在")
    elif is_multi_cohort:
        # 多专业课，校验所有专业和教学班配置
        _validate_cohort_teaching_class_counts(data.cohort_ids, data.cohort_teaching_class_counts, db)

    # 验证教师存在（如果指定）
    if data.teacher_id:
        teacher = db.query(Teacher).filter(Teacher.id == data.teacher_id).first()
        if not teacher:
            raise HTTPException(status_code=404, detail="教师不存在")

    # 验证课程类型和学时
    if data.course_type == "theory_only" and data.theory_hours <= 0:
        raise HTTPException(status_code=400, detail="纯理论课程必须有理论学时")
    if data.course_type == "lab_only" and data.lab_hours <= 0:
        raise HTTPException(status_code=400, detail="纯实验课程必须有实验学时")
    if data.course_type == "mixed" and (data.theory_hours <= 0 or data.lab_hours <= 0):
        raise HTTPException(status_code=400, detail="混合课程必须同时有理论和实验学时")

    # 确定有效的cohort_id（单专业时使用）
    effective_cohort_id = None
    if data.cohort_id:
        effective_cohort_id = data.cohort_id
    elif len(data.cohort_ids) == 1:
        effective_cohort_id = data.cohort_ids[0]

    course = Course(
        name=data.name,
        cohort_id=effective_cohort_id,
        cohort_ids=data.cohort_ids,  # 保留cohort_ids，单专业时也保留[cohort_id]
        cohort_teaching_class_counts=data.cohort_teaching_class_counts if len(data.cohort_ids) > 1 else {},
        teacher_id=data.teacher_id,
        course_type=data.course_type,
        theory_hours=data.theory_hours,
        lab_hours=data.lab_hours,
        teaching_class_count=data.teaching_class_count,
        semester=data.semester,
        dual_teacher_enabled=data.dual_teacher_enabled,
        second_teacher_id=data.second_teacher_id,
        teacher_split_week=data.teacher_split_week,
        is_graduation_course=data.is_graduation_course,
        preferred_pattern=data.preferred_pattern,
        combined_with=data.combined_with,
        teacher_override=data.teacher_override,
        teacher_configs=data.teacher_configs,
        phase_teachers=data.phase_teachers
    )
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


@router.put("/{course_id}", response_model=CourseResponse, summary="更新课程")
def update_course(course_id: int, data: CourseUpdate, db: Session = Depends(get_db)):
    """更新课程信息"""
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")

    # 验证教师存在（如果指定）
    if data.teacher_id is not None and data.teacher_id:
        teacher = db.query(Teacher).filter(Teacher.id == data.teacher_id).first()
        if not teacher:
            raise HTTPException(status_code=404, detail="教师不存在")

    # 如果更新了cohort_ids，需要校验
    if data.cohort_ids is not None and len(data.cohort_ids) > 1:
        counts = data.cohort_teaching_class_counts if data.cohort_teaching_class_counts else course.cohort_teaching_class_counts
        _validate_cohort_teaching_class_counts(data.cohort_ids, counts or {}, db)

    # 更新字段
    update_fields = data.model_dump(exclude_unset=True)
    
    # 处理cohort_id和cohort_ids的关联逻辑
    if 'cohort_ids' in update_fields:
        cohort_ids = update_fields['cohort_ids']
        if len(cohort_ids) == 1:
            # 单专业，设置cohort_id，保留cohort_ids以便前端正确显示
            update_fields['cohort_id'] = cohort_ids[0]
            # 保留 cohort_ids = [cohort_id]，不清空
            update_fields['cohort_teaching_class_counts'] = {}
        elif len(cohort_ids) > 1:
            # 多专业，清空cohort_id
            update_fields['cohort_id'] = None
        else:
            # 空列表，保持cohort_id不变或清空
            pass
    
    for field, value in update_fields.items():
        setattr(course, field, value)

    db.commit()
    db.refresh(course)
    return course


@router.delete("/{course_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除课程")
def delete_course(course_id: int, db: Session = Depends(get_db)):
    """删除课程"""
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")

    db.delete(course)
    db.commit()
    return None


# ==================== 课程偏好 API ====================

@router.get("/{course_id}/preferences", response_model=List[TeacherPreferenceResponse], summary="获取课程相关偏好")
def get_course_preferences(course_id: int, db: Session = Depends(get_db)):
    """获取与该课程相关的教师偏好设置"""
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")

    return db.query(TeacherPreference).filter(
        TeacherPreference.course_id == course_id
    ).all()


@router.post("/{course_id}/preferences", response_model=TeacherPreferenceResponse, status_code=status.HTTP_201_CREATED, summary="添加课程偏好")
def create_course_preference(
    course_id: int,
    data: TeacherPreferenceCreate,
    db: Session = Depends(get_db)
):
    """为课程添加教师时间偏好"""
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")

    # 使用课程的教师ID
    teacher_id = data.teacher_id or course.teacher_id
    if not teacher_id:
        raise HTTPException(status_code=400, detail="必须指定教师ID")

    preference = TeacherPreference(
        teacher_id=teacher_id,
        course_id=course_id,
        preferred_slots=data.preferred_slots,
        undesired_slots=data.undesired_slots
    )
    db.add(preference)
    db.commit()
    db.refresh(preference)
    return preference


# ==================== 固定课程 API ====================

@router.get("/fixed/list", response_model=List[FixedScheduleResponse], summary="获取所有固定课程")
def get_fixed_courses(
    cohort_id: Optional[int] = Query(None, description="按专业年级筛选"),
    semester: Optional[str] = Query(None, description="按学期筛选"),
    db: Session = Depends(get_db)
):
    """获取固定课程列表（如英语、体育等公共课）"""
    query = db.query(FixedSchedule)
    
    if cohort_id:
        query = query.filter(FixedSchedule.cohort_id == cohort_id)
    if semester:
        query = query.filter((FixedSchedule.semester == semester) | (FixedSchedule.semester == "both"))
    
    return query.order_by(FixedSchedule.cohort_id, FixedSchedule.course_name).all()


@router.post("/fixed", response_model=FixedScheduleResponse, status_code=status.HTTP_201_CREATED, summary="添加固定课程")
def create_fixed_course(data: FixedScheduleCreate, db: Session = Depends(get_db)):
    """添加固定课程（如英语、体育等公共课）"""
    # 验证专业年级存在
    cohort = db.query(Cohort).filter(Cohort.id == data.cohort_id).first()
    if not cohort:
        raise HTTPException(status_code=404, detail="专业年级不存在")
    
    fixed = FixedSchedule(
        cohort_id=data.cohort_id,
        admin_class_ids=data.admin_class_ids or [],
        course_name=data.course_name,
        teacher_name=data.teacher_name,
        duration=data.duration,
        weeks=data.weeks,
        day=data.day,
        period=data.period,
        semester=data.semester or "first"
    )
    db.add(fixed)
    db.commit()
    db.refresh(fixed)
    return fixed


@router.get("/fixed/{fixed_id}", response_model=FixedScheduleResponse, summary="获取固定课程详情")
def get_fixed_course(fixed_id: int, db: Session = Depends(get_db)):
    """获取指定固定课程详情"""
    fixed = db.query(FixedSchedule).filter(FixedSchedule.id == fixed_id).first()
    if not fixed:
        raise HTTPException(status_code=404, detail="固定课程不存在")
    return fixed


@router.put("/fixed/{fixed_id}", response_model=FixedScheduleResponse, summary="更新固定课程")
def update_fixed_course(fixed_id: int, data: FixedScheduleCreate, db: Session = Depends(get_db)):
    """更新固定课程信息"""
    fixed = db.query(FixedSchedule).filter(FixedSchedule.id == fixed_id).first()
    if not fixed:
        raise HTTPException(status_code=404, detail="固定课程不存在")
    
    # 验证专业年级存在
    cohort = db.query(Cohort).filter(Cohort.id == data.cohort_id).first()
    if not cohort:
        raise HTTPException(status_code=404, detail="专业年级不存在")
    
    fixed.cohort_id = data.cohort_id
    fixed.admin_class_ids = data.admin_class_ids or []
    fixed.course_name = data.course_name
    fixed.teacher_name = data.teacher_name
    fixed.duration = data.duration
    fixed.weeks = data.weeks
    fixed.day = data.day
    fixed.period = data.period
    fixed.semester = data.semester or "first"
    
    db.commit()
    db.refresh(fixed)
    return fixed


@router.delete("/fixed/{fixed_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除固定课程")
def delete_fixed_course(fixed_id: int, db: Session = Depends(get_db)):
    """删除固定课程"""
    fixed = db.query(FixedSchedule).filter(FixedSchedule.id == fixed_id).first()
    if not fixed:
        raise HTTPException(status_code=404, detail="固定课程不存在")
    
    db.delete(fixed)
    db.commit()
    return None


# ==================== 统一课程视图 API ====================

@router.get("/all/unified", summary="获取所有课程（包含固定课）")
def get_all_courses_unified(
    cohort_id: Optional[int] = Query(None, description="按专业年级筛选"),
    semester: Optional[str] = Query(None, description="按学期筛选"),
    course_category: Optional[str] = Query(None, description="课程分类: regular(普通课), fixed(固定课), all(全部)"),
    db: Session = Depends(get_db)
) -> List[Dict[str, Any]]:
    """获取所有课程的统一视图，包含普通课程和固定课程
    
    返回格式统一为:
    - category: "regular" 或 "fixed"
    - id: 课程ID
    - name: 课程名称
    - teacher_name: 教师名称
    - cohort_id: 专业年级ID
    - cohort_name: 专业年级名称
    - semester: 学期
    - ... 其他字段
    """
    result = []
    
    # 获取普通课程
    if course_category in [None, "all", "regular"]:
        query = db.query(Course).options(
            joinedload(Course.cohort),
            joinedload(Course.teacher)
        )
        
        if cohort_id:
            # 筛选单专业课或多专业课中包含该专业的
            from sqlalchemy import or_, func
            query = query.filter(
                or_(
                    Course.cohort_id == cohort_id,
                    func.json_contains(Course.cohort_ids, str(cohort_id))
                )
            )
        if semester:
            query = query.filter((Course.semester == semester) | (Course.semester == "both"))
        
        courses = query.order_by(Course.cohort_id, Course.name).all()
        
        # 预加载所有cohort用于多专业课程显示
        all_cohorts = {c.id: c for c in db.query(Cohort).all()}
        
        for course in courses:
            # 构建cohort_name
            cohort_name = None
            cohort_ids = course.cohort_ids or []
            if course.cohort_id:
                cohort_name = f"{course.cohort.major}-{course.cohort.grade}" if course.cohort else None
            elif cohort_ids:
                # 多专业课，显示所有专业名称
                names = []
                for cid in cohort_ids:
                    c = all_cohorts.get(cid)
                    if c:
                        names.append(f"{c.major}-{c.grade}")
                cohort_name = ", ".join(names) if names else None
            
            result.append({
                "category": "regular",
                "id": course.id,
                "name": course.name,
                "teacher_name": course.teacher.name if course.teacher else None,
                "teacher_id": course.teacher_id,
                "cohort_id": course.cohort_id,
                "cohort_ids": cohort_ids,
                "cohort_teaching_class_counts": course.cohort_teaching_class_counts or {},
                "cohort_name": cohort_name,
                "semester": course.semester or "first",
                "course_type": course.course_type,
                "theory_hours": course.theory_hours,
                "lab_hours": course.lab_hours,
                "teaching_class_count": course.teaching_class_count,
                "dual_teacher_enabled": course.dual_teacher_enabled or False,
                "second_teacher_id": course.second_teacher_id,
                "teacher_split_week": course.teacher_split_week or 8,
                "is_graduation_course": course.is_graduation_course or False,
                "teacher_configs": course.teacher_configs or [],
                # 固定课特有字段设置为Null
                "day": None,
                "period": None,
                "duration": None,
                "weeks": None,
            })
    
    # 获取固定课程
    if course_category in [None, "all", "fixed"]:
        query = db.query(FixedSchedule)
        
        if cohort_id:
            query = query.filter(FixedSchedule.cohort_id == cohort_id)
        if semester:
            query = query.filter((FixedSchedule.semester == semester) | (FixedSchedule.semester == "both"))
        
        fixed_courses = query.order_by(FixedSchedule.cohort_id, FixedSchedule.course_name).all()
        
        for fixed in fixed_courses:
            cohort = db.query(Cohort).filter(Cohort.id == fixed.cohort_id).first()
            result.append({
                "category": "fixed",
                "id": fixed.id,
                "name": fixed.course_name,
                "teacher_name": fixed.teacher_name,
                "teacher_id": None,
                "cohort_id": fixed.cohort_id,
                "cohort_name": f"{cohort.major}-{cohort.grade}" if cohort else None,
                "semester": fixed.semester or "first",
                "course_type": "fixed",
                "theory_hours": None,
                "lab_hours": None,
                "teaching_class_count": None,
                "dual_teacher_enabled": False,
                # 固定课特有字段
                "day": fixed.day,
                "period": fixed.period,
                "duration": fixed.duration,
                "weeks": fixed.weeks,
                "admin_class_ids": fixed.admin_class_ids or [],
            })
    
    return result
