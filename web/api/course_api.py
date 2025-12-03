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
            "teacher_id": course.teacher_id,
            "course_type": course.course_type,
            "theory_hours": course.theory_hours,
            "lab_hours": course.lab_hours,
            "teaching_class_count": course.teaching_class_count,
            "semester": course.semester or "first",
            "dual_teacher_enabled": course.dual_teacher_enabled or False,
            "second_teacher_id": course.second_teacher_id,
            "teacher_split_week": course.teacher_split_week or 8,
            "preferred_pattern": course.preferred_pattern,
            "combined_with": course.combined_with or [],
            "teacher_override": course.teacher_override or {},
            "phase_teachers": course.phase_teachers or {},
            "created_at": course.created_at,
            "updated_at": course.updated_at,
            "cohort": {
                "id": course.cohort.id,
                "major": course.cohort.major,
                "grade": course.cohort.grade,
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
        "teacher_id": course.teacher_id,
        "course_type": course.course_type,
        "theory_hours": course.theory_hours,
        "lab_hours": course.lab_hours,
        "teaching_class_count": course.teaching_class_count,
        "semester": course.semester or "first",
        "dual_teacher_enabled": course.dual_teacher_enabled or False,
        "second_teacher_id": course.second_teacher_id,
        "teacher_split_week": course.teacher_split_week or 8,
        "preferred_pattern": course.preferred_pattern,
        "combined_with": course.combined_with or [],
        "teacher_override": course.teacher_override or {},
        "phase_teachers": course.phase_teachers or {},
        "created_at": course.created_at,
        "updated_at": course.updated_at,
        "cohort": {
            "id": course.cohort.id,
            "major": course.cohort.major,
            "grade": course.cohort.grade,
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


@router.post("", response_model=CourseResponse, status_code=status.HTTP_201_CREATED, summary="添加课程")
def create_course(data: CourseCreate, db: Session = Depends(get_db)):
    """添加新课程"""
    # 验证专业年级存在
    cohort = db.query(Cohort).filter(Cohort.id == data.cohort_id).first()
    if not cohort:
        raise HTTPException(status_code=404, detail="专业年级不存在")

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

    course = Course(
        name=data.name,
        cohort_id=data.cohort_id,
        teacher_id=data.teacher_id,
        course_type=data.course_type,
        theory_hours=data.theory_hours,
        lab_hours=data.lab_hours,
        teaching_class_count=data.teaching_class_count,
        semester=data.semester,
        dual_teacher_enabled=data.dual_teacher_enabled,
        second_teacher_id=data.second_teacher_id,
        teacher_split_week=data.teacher_split_week,
        preferred_pattern=data.preferred_pattern,
        combined_with=data.combined_with,
        teacher_override=data.teacher_override,
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

    # 更新字段
    update_fields = data.model_dump(exclude_unset=True)
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
        group_tag=data.group_tag,
        course_name=data.course_name,
        teacher_name=data.teacher_name,
        duration=data.duration,
        weeks=data.weeks,
        day=data.day,
        period=data.period
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
    fixed.group_tag = data.group_tag
    fixed.course_name = data.course_name
    fixed.teacher_name = data.teacher_name
    fixed.duration = data.duration
    fixed.weeks = data.weeks
    fixed.day = data.day
    fixed.period = data.period
    
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
            query = query.filter(Course.cohort_id == cohort_id)
        if semester:
            query = query.filter((Course.semester == semester) | (Course.semester == "both"))
        
        courses = query.order_by(Course.cohort_id, Course.name).all()
        
        for course in courses:
            result.append({
                "category": "regular",
                "id": course.id,
                "name": course.name,
                "teacher_name": course.teacher.name if course.teacher else None,
                "teacher_id": course.teacher_id,
                "cohort_id": course.cohort_id,
                "cohort_name": f"{course.cohort.major}-{course.cohort.grade}" if course.cohort else None,
                "semester": course.semester or "first",
                "course_type": course.course_type,
                "theory_hours": course.theory_hours,
                "lab_hours": course.lab_hours,
                "teaching_class_count": course.teaching_class_count,
                "dual_teacher_enabled": course.dual_teacher_enabled or False,
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
                "group_tag": fixed.group_tag,
            })
    
    return result
