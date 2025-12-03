"""
教师管理 API
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from ..core.database import get_db
from ..models.db_models import Teacher, TeacherPreference
from ..schemas.schemas import (
    TeacherCreate, TeacherUpdate, TeacherResponse,
    TeacherPreferenceCreate, TeacherPreferenceResponse
)

router = APIRouter(prefix="/teachers", tags=["教师管理"])


@router.get("", response_model=List[TeacherResponse], summary="获取所有教师")
def get_teachers(
    is_campus: bool = None,
    db: Session = Depends(get_db)
):
    """获取所有教师列表，可按是否校本部教师筛选"""
    query = db.query(Teacher)
    if is_campus is not None:
        query = query.filter(Teacher.is_campus_teacher == is_campus)
    return query.order_by(Teacher.name).all()


@router.get("/{teacher_id}", response_model=TeacherResponse, summary="获取教师详情")
def get_teacher(teacher_id: int, db: Session = Depends(get_db)):
    """获取指定教师信息"""
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="教师不存在")
    return teacher


@router.post("", response_model=TeacherResponse, status_code=status.HTTP_201_CREATED, summary="添加教师")
def create_teacher(data: TeacherCreate, db: Session = Depends(get_db)):
    """添加新教师"""
    # 检查教师姓名是否已存在
    existing = db.query(Teacher).filter(Teacher.name == data.name).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"教师 {data.name} 已存在")

    teacher = Teacher(
        name=data.name,
        is_campus_teacher=data.is_campus_teacher
    )
    db.add(teacher)
    db.commit()
    db.refresh(teacher)
    return teacher


@router.put("/{teacher_id}", response_model=TeacherResponse, summary="更新教师信息")
def update_teacher(teacher_id: int, data: TeacherUpdate, db: Session = Depends(get_db)):
    """更新教师信息"""
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="教师不存在")

    if data.name is not None:
        # 检查新名称是否与其他教师冲突
        existing = db.query(Teacher).filter(
            Teacher.name == data.name,
            Teacher.id != teacher_id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail=f"教师 {data.name} 已存在")
        teacher.name = data.name

    if data.is_campus_teacher is not None:
        teacher.is_campus_teacher = data.is_campus_teacher

    db.commit()
    db.refresh(teacher)
    return teacher


@router.delete("/{teacher_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除教师")
def delete_teacher(teacher_id: int, db: Session = Depends(get_db)):
    """删除教师"""
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="教师不存在")

    db.delete(teacher)
    db.commit()
    return None


# ==================== 教师偏好 API ====================

@router.get("/{teacher_id}/preferences", response_model=List[TeacherPreferenceResponse], summary="获取教师偏好")
def get_teacher_preferences(teacher_id: int, db: Session = Depends(get_db)):
    """获取教师的时间偏好设置"""
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="教师不存在")

    return db.query(TeacherPreference).filter(
        TeacherPreference.teacher_id == teacher_id
    ).all()


@router.post("/{teacher_id}/preferences", response_model=TeacherPreferenceResponse, status_code=status.HTTP_201_CREATED, summary="添加教师偏好")
def create_teacher_preference(
    teacher_id: int,
    data: TeacherPreferenceCreate,
    db: Session = Depends(get_db)
):
    """为教师添加时间偏好"""
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="教师不存在")

    preference = TeacherPreference(
        teacher_id=teacher_id,
        course_id=data.course_id,
        preferred_slots=data.preferred_slots,
        undesired_slots=data.undesired_slots
    )
    db.add(preference)
    db.commit()
    db.refresh(preference)
    return preference


@router.delete("/{teacher_id}/preferences/{preference_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除教师偏好")
def delete_teacher_preference(
    teacher_id: int,
    preference_id: int,
    db: Session = Depends(get_db)
):
    """删除教师的特定偏好设置"""
    preference = db.query(TeacherPreference).filter(
        TeacherPreference.id == preference_id,
        TeacherPreference.teacher_id == teacher_id
    ).first()
    if not preference:
        raise HTTPException(status_code=404, detail="偏好设置不存在")

    db.delete(preference)
    db.commit()
    return None
