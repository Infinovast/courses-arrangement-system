"""
班级管理 API
- 专业年级 (Cohort) 的增删查
- 行政班 (AdminClass) 的增删查
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from ..core.database import get_db
from ..models.db_models import Cohort, AdminClass
from ..schemas.schemas import (
    CohortCreate, CohortUpdate, CohortResponse, CohortWithClasses,
    AdminClassCreate, AdminClassUpdate, AdminClassResponse
)

router = APIRouter(prefix="/classes", tags=["班级管理"])


# ==================== 专业年级 API ====================

@router.get("/cohorts", response_model=List[CohortResponse], summary="获取所有专业年级")
def get_cohorts(db: Session = Depends(get_db)):
    """获取所有专业年级列表"""
    cohorts = db.query(Cohort).order_by(Cohort.grade.desc(), Cohort.major).all()
    # 手动构造响应以包含 cohort_key
    result = []
    for c in cohorts:
        result.append(CohortResponse(
            id=c.id,
            major=c.major,
            grade=c.grade,
            cohort_key=f"{c.major}-{c.grade}",
            created_at=c.created_at
        ))
    return result


@router.get("/cohorts/{cohort_id}", response_model=CohortWithClasses, summary="获取专业年级详情")
def get_cohort(cohort_id: int, db: Session = Depends(get_db)):
    """获取指定专业年级及其行政班"""
    cohort = db.query(Cohort).filter(Cohort.id == cohort_id).first()
    if not cohort:
        raise HTTPException(status_code=404, detail="专业年级不存在")

    admin_classes = [
        AdminClassResponse(
            id=ac.id,
            cohort_id=ac.cohort_id,
            class_index=ac.class_index,
            student_count=ac.student_count,
            created_at=ac.created_at
        )
        for ac in cohort.admin_classes
    ]

    return CohortWithClasses(
        id=cohort.id,
        major=cohort.major,
        grade=cohort.grade,
        cohort_key=f"{cohort.major}-{cohort.grade}",
        created_at=cohort.created_at,
        admin_classes=admin_classes
    )


@router.post("/cohorts", response_model=CohortResponse, status_code=status.HTTP_201_CREATED, summary="添加专业年级")
def create_cohort(cohort_data: CohortCreate, db: Session = Depends(get_db)):
    """添加新的专业年级"""
    # 检查是否已存在
    existing = db.query(Cohort).filter(
        Cohort.major == cohort_data.major,
        Cohort.grade == cohort_data.grade
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"专业年级 {cohort_data.major}-{cohort_data.grade} 已存在")

    cohort = Cohort(major=cohort_data.major, grade=cohort_data.grade)
    db.add(cohort)
    db.commit()
    db.refresh(cohort)

    return CohortResponse(
        id=cohort.id,
        major=cohort.major,
        grade=cohort.grade,
        cohort_key=f"{cohort.major}-{cohort.grade}",
        created_at=cohort.created_at
    )


@router.put("/cohorts/{cohort_id}", response_model=CohortResponse, summary="更新专业年级")
def update_cohort(cohort_id: int, data: CohortUpdate, db: Session = Depends(get_db)):
    """更新专业年级信息"""
    cohort = db.query(Cohort).filter(Cohort.id == cohort_id).first()
    if not cohort:
        raise HTTPException(status_code=404, detail="专业年级不存在")

    if data.major is not None:
        cohort.major = data.major
    if data.grade is not None:
        cohort.grade = data.grade

    # 检查更新后是否与其他记录冲突
    existing = db.query(Cohort).filter(
        Cohort.major == cohort.major,
        Cohort.grade == cohort.grade,
        Cohort.id != cohort_id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"专业年级 {cohort.major}-{cohort.grade} 已存在")

    db.commit()
    db.refresh(cohort)
    return CohortResponse(
        id=cohort.id,
        major=cohort.major,
        grade=cohort.grade,
        cohort_key=f"{cohort.major}-{cohort.grade}",
        created_at=cohort.created_at
    )


@router.delete("/cohorts/{cohort_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除专业年级")
def delete_cohort(cohort_id: int, db: Session = Depends(get_db)):
    """删除专业年级（会级联删除该年级下的所有行政班和课程）"""
    cohort = db.query(Cohort).filter(Cohort.id == cohort_id).first()
    if not cohort:
        raise HTTPException(status_code=404, detail="专业年级不存在")

    db.delete(cohort)
    db.commit()
    return None


# ==================== 行政班 API ====================

@router.get("/admin-classes", response_model=List[AdminClassResponse], summary="获取所有行政班")
def get_admin_classes(cohort_id: int = None, db: Session = Depends(get_db)):
    """获取行政班列表，可按专业年级筛选"""
    query = db.query(AdminClass)
    if cohort_id:
        query = query.filter(AdminClass.cohort_id == cohort_id)
    return query.order_by(AdminClass.cohort_id, AdminClass.class_index).all()


@router.post("/admin-classes", response_model=AdminClassResponse, status_code=status.HTTP_201_CREATED, summary="添加行政班")
def create_admin_class(data: AdminClassCreate, db: Session = Depends(get_db)):
    """为指定专业年级添加行政班"""
    # 检查专业年级是否存在
    cohort = db.query(Cohort).filter(Cohort.id == data.cohort_id).first()
    if not cohort:
        raise HTTPException(status_code=404, detail="专业年级不存在")

    # 检查班级序号是否已存在
    existing = db.query(AdminClass).filter(
        AdminClass.cohort_id == data.cohort_id,
        AdminClass.class_index == data.class_index
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"该专业年级的{data.class_index}班已存在")

    admin_class = AdminClass(
        cohort_id=data.cohort_id,
        class_index=data.class_index,
        student_count=data.student_count
    )
    db.add(admin_class)
    db.commit()
    db.refresh(admin_class)
    return admin_class


@router.put("/admin-classes/{admin_class_id}", response_model=AdminClassResponse, summary="更新行政班")
def update_admin_class(admin_class_id: int, data: AdminClassUpdate, db: Session = Depends(get_db)):
    """更新行政班信息"""
    admin_class = db.query(AdminClass).filter(AdminClass.id == admin_class_id).first()
    if not admin_class:
        raise HTTPException(status_code=404, detail="行政班不存在")

    if data.class_index is not None:
        # 检查班级序号是否与同专业年级其他班级冲突
        existing = db.query(AdminClass).filter(
            AdminClass.cohort_id == admin_class.cohort_id,
            AdminClass.class_index == data.class_index,
            AdminClass.id != admin_class_id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail=f"该专业年级的{data.class_index}班已存在")
        admin_class.class_index = data.class_index

    if data.student_count is not None:
        admin_class.student_count = data.student_count

    db.commit()
    db.refresh(admin_class)
    return admin_class


@router.delete("/admin-classes/{admin_class_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除行政班")
def delete_admin_class(admin_class_id: int, db: Session = Depends(get_db)):
    """删除指定行政班"""
    admin_class = db.query(AdminClass).filter(AdminClass.id == admin_class_id).first()
    if not admin_class:
        raise HTTPException(status_code=404, detail="行政班不存在")

    db.delete(admin_class)
    db.commit()
    return None


@router.post("/cohorts/{cohort_id}/batch-create-classes", response_model=List[AdminClassResponse], summary="批量创建行政班")
def batch_create_admin_classes(
    cohort_id: int,
    count: int,
    student_count: int = 40,
    db: Session = Depends(get_db)
):
    """为专业年级批量创建行政班"""
    cohort = db.query(Cohort).filter(Cohort.id == cohort_id).first()
    if not cohort:
        raise HTTPException(status_code=404, detail="专业年级不存在")

    # 获取现有最大班级序号
    max_index = db.query(AdminClass).filter(
        AdminClass.cohort_id == cohort_id
    ).count()

    created_classes = []
    for i in range(count):
        admin_class = AdminClass(
            cohort_id=cohort_id,
            class_index=max_index + i + 1,
            student_count=student_count
        )
        db.add(admin_class)
        created_classes.append(admin_class)

    db.commit()
    for ac in created_classes:
        db.refresh(ac)

    return created_classes
