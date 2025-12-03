"""
机房管理 API
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from ..core.database import get_db
from ..models.db_models import Room
from ..schemas.schemas import RoomCreate, RoomUpdate, RoomResponse

router = APIRouter(prefix="/rooms", tags=["机房管理"])


@router.get("", response_model=List[RoomResponse], summary="获取所有机房")
def get_rooms(db: Session = Depends(get_db)):
    """获取所有机房列表"""
    return db.query(Room).order_by(Room.name).all()


@router.get("/{room_id}", response_model=RoomResponse, summary="获取机房详情")
def get_room(room_id: int, db: Session = Depends(get_db)):
    """获取指定机房信息"""
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="机房不存在")
    return room


@router.post("", response_model=RoomResponse, status_code=status.HTTP_201_CREATED, summary="添加机房")
def create_room(data: RoomCreate, db: Session = Depends(get_db)):
    """添加新机房"""
    # 检查机房名称是否已存在
    existing = db.query(Room).filter(Room.name == data.name).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"机房 {data.name} 已存在")

    room = Room(name=data.name, capacity=data.capacity)
    db.add(room)
    db.commit()
    db.refresh(room)
    return room


@router.put("/{room_id}", response_model=RoomResponse, summary="更新机房信息")
def update_room(room_id: int, data: RoomUpdate, db: Session = Depends(get_db)):
    """更新机房信息"""
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="机房不存在")

    if data.name is not None:
        # 检查新名称是否与其他机房冲突
        existing = db.query(Room).filter(
            Room.name == data.name,
            Room.id != room_id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail=f"机房 {data.name} 已存在")
        room.name = data.name

    if data.capacity is not None:
        room.capacity = data.capacity

    db.commit()
    db.refresh(room)
    return room


@router.delete("/{room_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除机房")
def delete_room(room_id: int, db: Session = Depends(get_db)):
    """删除机房"""
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="机房不存在")

    db.delete(room)
    db.commit()
    return None


@router.post("/batch", response_model=List[RoomResponse], status_code=status.HTTP_201_CREATED, summary="批量添加机房")
def batch_create_rooms(count: int, name_prefix: str = "机房", capacity: int = 50, db: Session = Depends(get_db)):
    """批量添加机房"""
    # 获取现有机房数量以确定起始编号
    existing_count = db.query(Room).count()

    created_rooms = []
    for i in range(count):
        room_name = f"{name_prefix}{existing_count + i + 1}"
        # 检查是否存在
        if db.query(Room).filter(Room.name == room_name).first():
            continue
        room = Room(name=room_name, capacity=capacity)
        db.add(room)
        created_rooms.append(room)

    db.commit()
    for room in created_rooms:
        db.refresh(room)

    return created_rooms
