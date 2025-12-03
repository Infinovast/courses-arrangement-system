"""
排课管理 API
- 开始排课
- 获取排课结果
- 手动调整
- 导出Excel
"""
import io
from datetime import datetime
from typing import List, Optional
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import pandas as pd

from ..core.database import get_db
from ..models.db_models import ScheduleResult, ScheduleSession, Cohort, FixedSchedule, SubgroupAssignment
from ..schemas.schemas import (
    ScheduleResultResponse, ScheduleResultUpdate, ScheduleSessionResponse,
    StartScheduleRequest, ScheduleResponse, FixedScheduleCreate, FixedScheduleResponse,
    SubgroupAssignmentCreate, SubgroupAssignmentResponse
)
from ..services.schedule_service import ScheduleService

router = APIRouter(prefix="/schedule", tags=["排课管理"])


# ==================== 排课会话 API ====================

@router.post("/start", response_model=ScheduleResponse, summary="开始排课")
def start_scheduling(
    request: StartScheduleRequest = None,
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db)
):
    """
    开始排课流程。
    排课是一个耗时操作，会在后台执行。
    返回会话ID，可用于查询排课状态和结果。
    
    Args:
        request.semester: 学期 - "first"(上册) 或 "second"(下册)
    """
    service = ScheduleService(db)

    try:
        cohort_ids = request.cohort_ids if request else None
        semester = request.semester if request else "first"
        session_id = service.start_scheduling(cohort_ids, semester)

        semester_name = "上册" if semester == "first" else "下册"
        return ScheduleResponse(
            session_id=session_id,
            status="completed",
            message=f"排课完成（{semester_name}）"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"排课失败: {str(e)}")


@router.get("/sessions", response_model=List[ScheduleSessionResponse], summary="获取所有排课会话")
def get_schedule_sessions(db: Session = Depends(get_db)):
    """获取所有排课会话记录"""
    return db.query(ScheduleSession).order_by(ScheduleSession.created_at.desc()).all()


@router.get("/sessions/latest", response_model=Optional[ScheduleSessionResponse], summary="获取最新排课会话")
def get_latest_session(semester: Optional[str] = None, db: Session = Depends(get_db)):
    """获取最新的排课会话
    
    Args:
        semester: 学期筛选 - "first"(上册) 或 "second"(下册)，不传则返回最新的
    
    Returns:
        排课会话信息，没有记录时返回 null
    """
    service = ScheduleService(db)
    return service.get_latest_session(semester)


@router.get("/sessions/{session_id}", response_model=ScheduleSessionResponse, summary="获取排课会话详情")
def get_session(session_id: str, db: Session = Depends(get_db)):
    """获取指定排课会话的状态"""
    session = db.query(ScheduleSession).filter(ScheduleSession.session_id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="排课会话不存在")
    return session


# ==================== 排课结果 API ====================

@router.get("/results/{session_id}", response_model=List[ScheduleResultResponse], summary="获取排课结果")
def get_schedule_results(
    session_id: str,
    cohort_id: Optional[int] = None,
    admin_class_id: Optional[int] = None,
    week: Optional[int] = None,
    day: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """获取指定会话的排课结果，支持筛选
    
    Args:
        cohort_id: 专业年级ID筛选
        admin_class_id: 行政班ID筛选
        week: 周次筛选
        day: 星期几筛选
    """
    from ..models.db_models import AdminClass, Cohort as CohortModel
    
    query = db.query(ScheduleResult).filter(ScheduleResult.session_id == session_id)

    if cohort_id:
        query = query.filter(ScheduleResult.cohort_id == cohort_id)
    if admin_class_id:
        query = query.filter(ScheduleResult.admin_class_id == admin_class_id)
    if week:
        query = query.filter(ScheduleResult.week == week)
    if day:
        query = query.filter(ScheduleResult.day == day)

    results = query.order_by(
        ScheduleResult.week,
        ScheduleResult.day,
        ScheduleResult.period
    ).all()

    # 补充行政班名称和专业年级名称
    response_list = []
    for r in results:
        # 获取行政班名称
        admin_class_name = None
        if r.admin_class_id:
            ac = db.query(AdminClass).filter(AdminClass.id == r.admin_class_id).first()
            if ac:
                cohort = db.query(CohortModel).filter(CohortModel.id == ac.cohort_id).first()
                if cohort:
                    admin_class_name = f"{cohort.major}{ac.class_index}班"
        
        # 获取专业年级名称
        cohort_name = None
        if r.cohort_id:
            cohort = db.query(CohortModel).filter(CohortModel.id == r.cohort_id).first()
            if cohort:
                cohort_name = f"{cohort.major}-{cohort.grade}"
        
        response_list.append(ScheduleResultResponse(
            id=r.id,
            session_id=r.session_id,
            teaching_class_id=r.teaching_class_id,
            course_name=r.course_name,
            teacher_name=r.teacher_name,
            week=r.week,
            day=r.day,
            period=r.period,
            duration=r.duration,
            room_name=r.room_name,
            is_lab=r.is_lab,
            is_combined=r.is_combined,
            is_fixed=r.is_fixed,
            cohort_ids=r.cohort_ids or [],
            subgroup_ids=r.subgroup_ids or [],
            cohort_id=r.cohort_id,
            admin_class_id=r.admin_class_id,
            admin_class_name=admin_class_name,
            cohort_name=cohort_name,
            created_at=r.created_at
        ))

    return response_list


@router.get("/results/{session_id}/cohort/{cohort_id}", summary="获取专业年级课表")
def get_cohort_schedule(session_id: str, cohort_id: int, db: Session = Depends(get_db)):
    """获取指定专业年级的课表视图"""
    service = ScheduleService(db)
    schedule = service.get_schedule_by_cohort(session_id, cohort_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="专业年级不存在")
    return schedule


@router.put("/results/{result_id}", response_model=ScheduleResultResponse, summary="手动调整课程时间")
def update_schedule_result(
    result_id: int,
    data: ScheduleResultUpdate,
    db: Session = Depends(get_db)
):
    """手动调整排课结果的时间或教室"""
    service = ScheduleService(db)
    result = service.update_schedule_result(
        result_id,
        week=data.week,
        day=data.day,
        period=data.period,
        room_name=data.room_name
    )
    if not result:
        raise HTTPException(status_code=404, detail="排课记录不存在")
    return result


@router.delete("/results/{result_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除排课记录")
def delete_schedule_result(result_id: int, db: Session = Depends(get_db)):
    """删除指定的排课记录"""
    result = db.query(ScheduleResult).filter(ScheduleResult.id == result_id).first()
    if not result:
        raise HTTPException(status_code=404, detail="排课记录不存在")

    db.delete(result)
    db.commit()
    return None


# ==================== 导出 API ====================

@router.get("/export/{session_id}", summary="导出Excel课表")
def export_schedule_excel(session_id: str, db: Session = Depends(get_db)):
    """导出排课结果为Excel文件
    
    包含三种视图：
    1. 按行政班的课表 - 方便学生/教务管理员/教师查看班级完整课表
    2. 教学班总览 - 方便教务管理员管理所有教学班，检查冲突
    3. 按机房的课表 - 方便教务管理员管理教室资源，检查冲突
    """
    from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
    from openpyxl.utils import get_column_letter
    from ..models.db_models import AdminClass
    
    # 验证会话存在
    session = db.query(ScheduleSession).filter(ScheduleSession.session_id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="排课会话不存在")

    # 获取所有结果
    results = db.query(ScheduleResult).filter(ScheduleResult.session_id == session_id).all()
    if not results:
        raise HTTPException(status_code=404, detail="没有排课结果")

    # 获取基础数据
    cohorts = db.query(Cohort).all()
    admin_classes = db.query(AdminClass).all()
    cohort_map = {c.id: c for c in cohorts}
    admin_class_map = {ac.id: ac for ac in admin_classes}
    
    # 定义样式
    header_font = Font(bold=True, size=11, color="FFFFFF")
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    cell_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    thin_border = Border(
        left=Side(style='thin', color='B4B4B4'),
        right=Side(style='thin', color='B4B4B4'),
        top=Side(style='thin', color='B4B4B4'),
        bottom=Side(style='thin', color='B4B4B4')
    )
    # 课程填充色
    theory_fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")  # 浅绿色-理论课
    lab_fill = PatternFill(start_color="DDEBF7", end_color="DDEBF7", fill_type="solid")  # 浅蓝色-实验课
    fixed_fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")  # 浅黄色-固定课
    
    # 创建Excel文件
    output = io.BytesIO()
    
    # 星期名称
    day_names = ['星期一', '星期二', '星期三', '星期四', '星期五']
    period_names = [f'第{i}节' for i in range(1, 12)]

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        
        # ==================== 1. 按行政班的课表 ====================
        for admin_class in admin_classes:
            cohort = cohort_map.get(admin_class.cohort_id)
            if not cohort:
                continue
            
            sheet_name = f"{cohort.major}{admin_class.class_index}班"[:31]
            
            # 筛选该行政班的课程
            class_results = [r for r in results if r.admin_class_id == admin_class.id or 
                           (r.cohort_id == cohort.id and r.is_fixed)]
            
            if not class_results:
                continue
            
            # 创建课表网格 (11节课 x 5天)
            # 先聚合数据：按(day, period)分组
            grid_data = defaultdict(list)
            for r in class_results:
                # 收集周次
                key = (r.day, r.period, r.course_name, r.teacher_name, r.is_lab, r.is_fixed, r.room_name, r.duration)
                if key not in [(k[0], k[1], k[2], k[3], k[4], k[5], k[6], k[7]) for k in grid_data.keys()]:
                    grid_data[key] = []
                # 找到对应的key并添加周次
                for k in grid_data.keys():
                    if k == key:
                        grid_data[k].append(r.week)
                        break
                else:
                    grid_data[key].append(r.week)
            
            # 构建表格：行=节次，列=星期
            table_data = [[''] + day_names]  # 表头
            for period in range(1, 12):
                row = [period_names[period-1]]
                for day in range(1, 6):
                    cell_content = []
                    for (d, p, course, teacher, is_lab, is_fixed, room, duration), weeks in grid_data.items():
                        if d == day and p <= period < p + duration:
                            weeks_sorted = sorted(set(weeks))
                            week_str = _format_weeks(weeks_sorted)
                            course_type = "[固定]" if is_fixed else ("[实验]" if is_lab else "")
                            room_str = f"\n{room}" if room else ""
                            cell_content.append(f"{course}{course_type}\n{teacher}\n{week_str}{room_str}")
                    row.append('\n---\n'.join(cell_content) if cell_content else '')
                table_data.append(row)
            
            # 写入Excel
            df = pd.DataFrame(table_data[1:], columns=table_data[0])
            df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=1)
            
            # 应用样式
            ws = writer.sheets[sheet_name]
            
            # 添加标题
            ws.merge_cells('A1:F1')
            ws['A1'] = f"{cohort.major} {cohort.grade}年级 {admin_class.class_index}班 课程表"
            ws['A1'].font = Font(bold=True, size=14)
            ws['A1'].alignment = Alignment(horizontal="center", vertical="center")
            
            # 设置列宽和行高
            ws.column_dimensions['A'].width = 10
            for col in range(2, 7):
                ws.column_dimensions[get_column_letter(col)].width = 22
            for row in range(3, 14):
                ws.row_dimensions[row].height = 80
            
            # 应用表头样式
            for col in range(1, 7):
                cell = ws.cell(row=2, column=col)
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = header_alignment
                cell.border = thin_border
            
            # 应用单元格样式
            for row in range(3, 14):
                for col in range(1, 7):
                    cell = ws.cell(row=row, column=col)
                    cell.alignment = cell_alignment
                    cell.border = thin_border
        
        # ==================== 2. 教学班总览 ====================
        # 按教学班ID聚合
        teaching_class_data = defaultdict(list)
        for r in results:
            teaching_class_data[r.teaching_class_id].append(r)
        
        overview_rows = []
        for tc_id, tc_results in teaching_class_data.items():
            # 取第一条记录的基本信息
            first = tc_results[0]
            
            # 聚合时间信息
            time_slots = defaultdict(list)
            for r in tc_results:
                key = (r.day, r.period, r.duration)
                time_slots[key].append(r.week)
            
            time_str_list = []
            for (day, period, duration), weeks in time_slots.items():
                weeks_sorted = sorted(set(weeks))
                week_str = _format_weeks(weeks_sorted)
                time_str_list.append(f"周{day} 第{period}-{period+duration-1}节 {week_str}")
            
            # 获取行政班信息
            admin_class_name = ""
            if first.admin_class_id:
                ac = admin_class_map.get(first.admin_class_id)
                if ac:
                    cohort = cohort_map.get(ac.cohort_id)
                    if cohort:
                        admin_class_name = f"{cohort.major}{ac.class_index}班"
            
            overview_rows.append({
                '教学班ID': tc_id,
                '课程名称': first.course_name,
                '授课教师': first.teacher_name,
                '行政班': admin_class_name,
                '课程类型': '固定课' if first.is_fixed else ('实验课' if first.is_lab else '理论课'),
                '是否合班': '是' if first.is_combined else '否',
                '教室': first.room_name or '普通教室',
                '上课时间': '; '.join(time_str_list)
            })
        
        if overview_rows:
            df_overview = pd.DataFrame(overview_rows)
            df_overview.to_excel(writer, sheet_name='教学班总览', index=False)
            
            # 应用样式
            ws = writer.sheets['教学班总览']
            for col in range(1, len(overview_rows[0]) + 1):
                cell = ws.cell(row=1, column=col)
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = header_alignment
                cell.border = thin_border
            ws.column_dimensions['A'].width = 30
            ws.column_dimensions['B'].width = 15
            ws.column_dimensions['C'].width = 12
            ws.column_dimensions['D'].width = 18
            ws.column_dimensions['E'].width = 10
            ws.column_dimensions['F'].width = 10
            ws.column_dimensions['G'].width = 12
            ws.column_dimensions['H'].width = 40
        
        # ==================== 3. 按机房的课表 ====================
        # 获取所有使用的机房
        rooms_used = set(r.room_name for r in results if r.room_name and r.is_lab)
        
        for room_name in sorted(rooms_used):
            sheet_name = f"机房-{room_name}"[:31]
            
            # 筛选该机房的课程
            room_results = [r for r in results if r.room_name == room_name]
            
            if not room_results:
                continue
            
            # 聚合数据
            grid_data = defaultdict(list)
            for r in room_results:
                key = (r.day, r.period, r.course_name, r.teacher_name, r.teaching_class_id, r.duration)
                for k in list(grid_data.keys()):
                    if k == key:
                        grid_data[k].append(r.week)
                        break
                else:
                    grid_data[key] = [r.week]
            
            # 构建表格
            table_data = [[''] + day_names]
            for period in range(1, 12):
                row = [period_names[period-1]]
                for day in range(1, 6):
                    cell_content = []
                    for (d, p, course, teacher, tc_id, duration), weeks in grid_data.items():
                        if d == day and p <= period < p + duration:
                            weeks_sorted = sorted(set(weeks))
                            week_str = _format_weeks(weeks_sorted)
                            cell_content.append(f"{course}\n{teacher}\n{week_str}")
                    row.append('\n---\n'.join(cell_content) if cell_content else '')
                table_data.append(row)
            
            df = pd.DataFrame(table_data[1:], columns=table_data[0])
            df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=1)
            
            ws = writer.sheets[sheet_name]
            
            # 添加标题
            ws.merge_cells('A1:F1')
            ws['A1'] = f"机房「{room_name}」课程安排"
            ws['A1'].font = Font(bold=True, size=14)
            ws['A1'].alignment = Alignment(horizontal="center", vertical="center")
            
            ws.column_dimensions['A'].width = 10
            for col in range(2, 7):
                ws.column_dimensions[get_column_letter(col)].width = 22
            for row in range(3, 14):
                ws.row_dimensions[row].height = 80
            
            for col in range(1, 7):
                cell = ws.cell(row=2, column=col)
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = header_alignment
                cell.border = thin_border
            
            for row in range(3, 14):
                for col in range(1, 7):
                    cell = ws.cell(row=row, column=col)
                    cell.alignment = cell_alignment
                    cell.border = thin_border

    output.seek(0)
    
    semester_name = "上册" if session.semester == "first" else "下册"
    filename = f"课程表_{semester_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    return StreamingResponse(
        output,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename*=UTF-8\'\'{"{}".format(filename)}'}
    )


def _format_weeks(weeks: list) -> str:
    """格式化周次显示"""
    if not weeks:
        return ""
    weeks = sorted(list(set(weeks)))

    # 检查常见模式
    if weeks == list(range(1, 17)):
        return "第1-16周"
    if weeks == list(range(1, 17, 2)):
        return "单周"
    if weeks == list(range(2, 17, 2)):
        return "双周"

    # 合并连续周次
    ranges = []
    start = weeks[0]
    for i in range(1, len(weeks)):
        if weeks[i] != weeks[i - 1] + 1:
            end = weeks[i - 1]
            ranges.append(f"{start}-{end}" if start != end else f"{start}")
            start = weeks[i]
    end = weeks[-1]
    ranges.append(f"{start}-{end}" if start != end else f"{start}")

    return "第" + ",".join(ranges) + "周"


# ==================== 固定课程 API ====================

@router.get("/fixed-schedules", response_model=List[FixedScheduleResponse], summary="获取所有固定课程")
def get_fixed_schedules(cohort_id: int = None, db: Session = Depends(get_db)):
    """获取固定课程列表（公共课）"""
    query = db.query(FixedSchedule)
    if cohort_id:
        query = query.filter(FixedSchedule.cohort_id == cohort_id)
    return query.all()


@router.post("/fixed-schedules", response_model=FixedScheduleResponse, status_code=status.HTTP_201_CREATED, summary="添加固定课程")
def create_fixed_schedule(data: FixedScheduleCreate, db: Session = Depends(get_db)):
    """添加固定课程（公共课）"""
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


@router.delete("/fixed-schedules/{fixed_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除固定课程")
def delete_fixed_schedule(fixed_id: int, db: Session = Depends(get_db)):
    """删除固定课程"""
    fixed = db.query(FixedSchedule).filter(FixedSchedule.id == fixed_id).first()
    if not fixed:
        raise HTTPException(status_code=404, detail="固定课程不存在")

    db.delete(fixed)
    db.commit()
    return None


# ==================== 子组预分配 API ====================

@router.get("/subgroup-assignments", response_model=List[SubgroupAssignmentResponse], summary="获取子组预分配")
def get_subgroup_assignments(cohort_id: int = None, db: Session = Depends(get_db)):
    """获取子组预分配配置"""
    query = db.query(SubgroupAssignment)
    if cohort_id:
        query = query.filter(SubgroupAssignment.cohort_id == cohort_id)
    return query.all()


@router.post("/subgroup-assignments", response_model=SubgroupAssignmentResponse, status_code=status.HTTP_201_CREATED, summary="添加子组预分配")
def create_subgroup_assignment(data: SubgroupAssignmentCreate, db: Session = Depends(get_db)):
    """添加子组预分配配置"""
    cohort = db.query(Cohort).filter(Cohort.id == data.cohort_id).first()
    if not cohort:
        raise HTTPException(status_code=404, detail="专业年级不存在")

    assignment = SubgroupAssignment(
        cohort_id=data.cohort_id,
        group_tag=data.group_tag,
        ratio=data.ratio
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return assignment


@router.delete("/subgroup-assignments/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除子组预分配")
def delete_subgroup_assignment(assignment_id: int, db: Session = Depends(get_db)):
    """删除子组预分配配置"""
    assignment = db.query(SubgroupAssignment).filter(SubgroupAssignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="子组预分配不存在")

    db.delete(assignment)
    db.commit()
    return None
