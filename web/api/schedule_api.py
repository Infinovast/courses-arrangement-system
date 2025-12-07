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
    
    # 先查询所有结果（不按周筛选），用于聚合周次信息
    all_results_query = db.query(ScheduleResult).filter(ScheduleResult.session_id == session_id)
    if cohort_id:
        all_results_query = all_results_query.filter(ScheduleResult.cohort_id == cohort_id)
    if admin_class_id:
        all_results_query = all_results_query.filter(ScheduleResult.admin_class_id == admin_class_id)
    all_results = all_results_query.all()
    
    # 聚合周次信息：按 (teaching_class_id, day, period, admin_class_id) 分组
    weeks_map = defaultdict(list)
    for r in all_results:
        key = (r.teaching_class_id, r.day, r.period, r.admin_class_id)
        weeks_map[key].append(r.week)
    
    # 按周筛选结果
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

    # 补充行政班名称、专业年级名称、周次字符串和课程类型
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
        
        # 获取聚合的周次信息
        key = (r.teaching_class_id, r.day, r.period, r.admin_class_id)
        weeks = sorted(set(weeks_map.get(key, [r.week])))
        week_str = _format_weeks(weeks)
        
        # 获取课程类型
        if r.is_fixed:
            course_type_str = "固定课"
        elif r.is_lab:
            course_type_str = "实验课"
        else:
            course_type_str = "理论课"
        
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
            week_str=week_str,
            course_type_str=course_type_str,
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
        
        # ==================== 1. 按行政班的课表（网格视图） ====================
        # 排序：专业名称正序，年级倒序，班级正序
        sorted_admin_classes = sorted(
            admin_classes,
            key=lambda ac: (
                cohort_map.get(ac.cohort_id).major if cohort_map.get(ac.cohort_id) else '',
                -(cohort_map.get(ac.cohort_id).grade if cohort_map.get(ac.cohort_id) else 0),
                ac.class_index
            )
        )
        for admin_class in sorted_admin_classes:
            cohort = cohort_map.get(admin_class.cohort_id)
            if not cohort:
                continue
            
            # 筛选该行政班的课程
            # 注意：固定课已经按admin_class_id正确存储，只需按admin_class_id筛选即可
            class_results = [r for r in results if r.admin_class_id == admin_class.id]
            
            if not class_results:
                continue
            
            # 聚合数据：按(day, period, course, teacher, ...)分组收集周次
            # key增加teaching_class_id和subgroup_ids以便后续分组
            grid_data = {}
            for r in class_results:
                # 将subgroup_ids转为排序后的字符串，作为子组集合标识
                subgroup_key = ','.join(sorted(r.subgroup_ids)) if r.subgroup_ids else ''
                key = (r.day, r.period, r.course_name, r.teacher_name, r.is_lab, r.is_fixed, r.room_name, r.duration, r.teaching_class_id, subgroup_key)
                if key not in grid_data:
                    grid_data[key] = {'weeks': [], 'id': r.id}
                grid_data[key]['weeks'].append(r.week)
            
            # 第一步：找出同一门课程的不同教学班
            # 注意：固定课排除在外，因为固定课的teaching_class_id包含时间信息，会被误判为多教学班
            course_name_to_tc_ids = defaultdict(set)
            for key in grid_data.keys():
                d, p, course, teacher, is_lab, is_fixed, room, duration, tc_id, sg_key = key
                if not is_fixed:  # 只统计非固定课
                    course_name_to_tc_ids[course].add(tc_id)
            
            # 第二步：找出当前行政班实际涉及的多教学班课程
            multi_tc_courses = []
            for course, tc_id_set in course_name_to_tc_ids.items():
                if len(tc_id_set) > 1:
                    multi_tc_courses.append({
                        'course_name': course,
                        'tc_ids': list(tc_id_set)
                    })
            
            # 如果没有多教学班课程，检查时间冲突
            if not multi_tc_courses:
                # 回退到时间冲突检测逻辑
                # 注意：只有当两门课的时间槽和周次都有重叠时，才算真正的冲突
                # 例如：形势与政策（第6-7周）和数据挖掘（第1-5,8-16周）在同一时间段，但周次不重叠，不算冲突
                
                def weeks_overlap(weeks1, weeks2):
                    """ 检查两个周次列表是否有重叠 """
                    return bool(set(weeks1) & set(weeks2))
                
                time_slot_map = defaultdict(list)
                for key in grid_data.keys():
                    d, p, course, teacher, is_lab, is_fixed, room, duration, tc_id, sg_key = key
                    for period_offset in range(duration):
                        slot = (d, p + period_offset)
                        time_slot_map[slot].append(key)
                
                # 检测真正的时间冲突（时间槽相同且周次有重叠）
                conflict_keys = set()
                for slot, keys in time_slot_map.items():
                    if len(keys) > 1:
                        # 检查这些课程的周次是否真正重叠
                        for i, k1 in enumerate(keys):
                            for k2 in keys[i+1:]:
                                weeks1 = grid_data[k1]['weeks']
                                weeks2 = grid_data[k2]['weeks']
                                if weeks_overlap(weeks1, weeks2):
                                    conflict_keys.add(k1)
                                    conflict_keys.add(k2)
                
                non_conflict_keys = [k for k in grid_data.keys() if k not in conflict_keys]
                conflict_key_list = [k for k in grid_data.keys() if k in conflict_keys]
                
                # 将有冲突的课程分组（同样要考虑周次重叠）
                schedule_groups = []
                for key in conflict_key_list:
                    d, p, course, teacher, is_lab, is_fixed, room, duration, tc_id, sg_key = key
                    key_slots = set((d, p + offset) for offset in range(duration))
                    key_weeks = set(grid_data[key]['weeks'])
                    
                    placed = False
                    for group in schedule_groups:
                        has_conflict = False
                        for existing_key in group:
                            ed, ep, _, _, _, _, _, edur, _, _ = existing_key
                            existing_slots = set((ed, ep + offset) for offset in range(edur))
                            existing_weeks = set(grid_data[existing_key]['weeks'])
                            # 只有时间槽和周次都重叠才算冲突
                            if (key_slots & existing_slots) and (key_weeks & existing_weeks):
                                has_conflict = True
                                break
                        if not has_conflict:
                            group.append(key)
                            placed = True
                            break
                    
                    if not placed:
                        schedule_groups.append([key])
                
                if not schedule_groups:
                    schedule_groups = [list(grid_data.keys())]
                else:
                    schedule_groups = [non_conflict_keys + group for group in schedule_groups]
            else:
                # 第三步：按子组集合分组（而非笛卡尔积）
                # 核心思想：子组相同的教学班放在同一张课表
                
                # 收集所有多教学班课程的teaching_class_id -> subgroup_key映射
                tc_id_to_subgroup_key = {}
                for key in grid_data.keys():
                    d, p, course, teacher, is_lab, is_fixed, room, duration, tc_id, sg_key = key
                    if sg_key and tc_id not in tc_id_to_subgroup_key:
                        tc_id_to_subgroup_key[tc_id] = sg_key
                
                # 找出所有不同的子组集合，并排序以保证顺序一致
                subgroup_sets_list = []
                for item in multi_tc_courses:
                    for tc_id in item['tc_ids']:
                        sg_key = tc_id_to_subgroup_key.get(tc_id)
                        if sg_key and sg_key not in subgroup_sets_list:
                            subgroup_sets_list.append(sg_key)
                # 排序以保证与前端顺序一致
                subgroup_sets_list.sort()
                
                # 单教学班课程（放到所有课表）
                # 固定课始终视为单教学班课程
                single_tc_keys = [k for k in grid_data.keys() 
                                  if k[5] or len(course_name_to_tc_ids.get(k[2], set())) <= 1]  # k[5] is is_fixed
                
                # 为每个子组集合生成一张课表
                schedule_groups = []
                for subgroup_key in subgroup_sets_list:
                    # 找出属于这个子组集合的多教学班课程
                    matched_keys = []
                    for key in grid_data.keys():
                        d, p, course, teacher, is_lab, is_fixed, room, duration, tc_id, sg_key = key
                        if len(course_name_to_tc_ids.get(course, set())) <= 1:
                            continue
                        if sg_key == subgroup_key:
                            matched_keys.append(key)
                    
                    if matched_keys:
                        schedule_groups.append(single_tc_keys + matched_keys)
                
                if not schedule_groups:
                    schedule_groups = [list(grid_data.keys())]
                
                # 第四步：按子组子集关系 + 时间不冲突合并课表组
                # 合并条件：一个子组集合是另一个的子集，且合并后时间不冲突
                
                import re
                # 将subgroup_key转换为数字集合
                # subgroup_key格式可能是 "1,2,3" 或 "SG_xxx_1,SG_xxx_2,SG_xxx_3"
                def parse_subgroup_key(key):
                    nums = set()
                    for part in key.split(','):
                        # 尝试直接转换为数字
                        try:
                            nums.add(int(part))
                        except ValueError:
                            # 从SG_xxx_N中提取数字N
                            match = re.search(r'_(\d+)$', part)
                            if match:
                                nums.add(int(match.group(1)))
                    return nums
                
                # 检查set1是否是set2的子集（或相等）
                def is_subset(set1, set2):
                    return set1 <= set2
                
                # 检查两个子组集合是否有子集关系（一个包含另一个）
                def has_subset_relation(set1, set2):
                    return is_subset(set1, set2) or is_subset(set2, set1)
                
                # 检查两个课程列表是否有时间冲突
                def courses_have_conflict(keys1, keys2):
                    for key1 in keys1:
                        d1, p1, course1, _, _, _, _, dur1, _, _ = key1
                        weeks1 = set(grid_data[key1]['weeks'])
                        slots1 = set((d1, p1 + offset) for offset in range(dur1))
                        
                        for key2 in keys2:
                            d2, p2, course2, _, _, _, _, dur2, _, _ = key2
                            # 跳过相同课程（同一课程不同教学班不算冲突）
                            if course1 == course2:
                                continue
                            weeks2 = set(grid_data[key2]['weeks'])
                            slots2 = set((d2, p2 + offset) for offset in range(dur2))
                            # 时间槽重叠且周次重叠才算冲突
                            if (slots1 & slots2) and (weeks1 & weeks2):
                                return True
                    return False
                
                # 解析子组集合
                parsed_sets = [parse_subgroup_key(k) for k in subgroup_sets_list]
                
                # 为每个子组集合获取对应的多教学班课程
                subgroup_key_to_multi_keys = {}
                for i, sg_key in enumerate(subgroup_sets_list):
                    multi_keys = [k for k in schedule_groups[i] if k not in single_tc_keys]
                    subgroup_key_to_multi_keys[sg_key] = multi_keys
                
                # 贪心合并
                merged_groups = []
                used = [False] * len(subgroup_sets_list)
                
                for i in range(len(subgroup_sets_list)):
                    if used[i]:
                        continue
                    used[i] = True
                    
                    current_keys = {subgroup_sets_list[i]}
                    current_sets = [parsed_sets[i]]
                    current_multi_keys = list(subgroup_key_to_multi_keys[subgroup_sets_list[i]])
                    
                    # 尝试将其他组合并进来
                    for j in range(i + 1, len(subgroup_sets_list)):
                        if used[j]:
                            continue
                        
                        # 条件1：检查是否与当前组中的某个子组集合有子集关系
                        has_relation = False
                        for existing_set in current_sets:
                            if has_subset_relation(parsed_sets[j], existing_set):
                                has_relation = True
                                break
                        if not has_relation:
                            continue
                        
                        # 条件2：检查合并后是否会产生时间冲突
                        new_multi_keys = subgroup_key_to_multi_keys[subgroup_sets_list[j]]
                        if courses_have_conflict(current_multi_keys, new_multi_keys):
                            continue
                        
                        # 可以合并
                        used[j] = True
                        current_keys.add(subgroup_sets_list[j])
                        current_sets.append(parsed_sets[j])
                        current_multi_keys.extend(new_multi_keys)
                    
                    # 生成合并后的课表组
                    merged_groups.append(single_tc_keys + current_multi_keys)
                
                schedule_groups = merged_groups if merged_groups else schedule_groups
            
            # 过滤重复的课表组（与前端逻辑一致）
            unique_schedule_groups = []
            seen_keys = set()
            for group in schedule_groups:
                if not group:
                    continue
                # 生成组的唯一标识（按课程ID排序后拼接）
                group_key = ','.join(sorted(str(grid_data[k]['id']) for k in group))
                if group_key not in seen_keys:
                    seen_keys.add(group_key)
                    unique_schedule_groups.append(group)
            
            schedule_groups = unique_schedule_groups if unique_schedule_groups else [list(grid_data.keys())]
            
            sheet_name = f"{cohort.major}{cohort.grade}级{admin_class.class_index}班"[:31]
            
            # 构建所有课表组的数据
            all_table_data = []
            for group_idx, group_keys in enumerate(schedule_groups):
                # 添加分组标题（如果有多个分组）
                if len(schedule_groups) > 1:
                    all_table_data.append([f'课表{group_idx+1}', '', '', '', '', ''])
                
                # 表头
                all_table_data.append([''] + day_names)
                
                # 构建表格：行=节次，列=星期
                for period in range(1, 12):
                    row = [period_names[period-1]]
                    for day in range(1, 6):
                        cell_content = []
                        for key in group_keys:
                            d, p, course, teacher, is_lab, is_fixed, room, duration, tc_id, sg_key = key
                            if d == day and p <= period < p + duration:
                                weeks = grid_data[key]['weeks']
                                weeks_sorted = sorted(set(weeks))
                                week_str = _format_weeks(weeks_sorted)
                                course_type = "理论课" if not is_lab and not is_fixed else ("实验课" if is_lab else "固定课")
                                room_str = f", {room}" if room else ""
                                cell_content.append(f"{course}\n({course_type}, {week_str}, {teacher}{room_str})")
                        row.append('\n'.join(cell_content) if cell_content else '')
                    all_table_data.append(row)
                
                # 分组之间添加空行
                if group_idx < len(schedule_groups) - 1:
                    all_table_data.append(['', '', '', '', '', ''])
            
            # 写入Excel
            df = pd.DataFrame(all_table_data)
            df.to_excel(writer, sheet_name=sheet_name, index=False, header=False, startrow=1)
            
            # 应用样式
            ws = writer.sheets[sheet_name]
            
            # 添加标题
            ws.merge_cells('A1:F1')
            ws['A1'] = f"{cohort.major} {cohort.grade}级 {admin_class.class_index}班 课程表"
            ws['A1'].font = Font(bold=True, size=14)
            ws['A1'].alignment = Alignment(horizontal="center", vertical="center")
            
            # 设置列宽
            ws.column_dimensions['A'].width = 8
            for col in range(2, 7):
                ws.column_dimensions[get_column_letter(col)].width = 28
            
            # 应用样式
            current_row = 2
            for group_idx in range(len(schedule_groups)):
                # 分组标题行（如果有多个分组）
                if len(schedule_groups) > 1:
                    ws.merge_cells(f'A{current_row}:F{current_row}')
                    cell = ws.cell(row=current_row, column=1)
                    cell.font = Font(bold=True, size=12)
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                    current_row += 1
                
                # 表头行
                for col in range(1, 7):
                    cell = ws.cell(row=current_row, column=col)
                    cell.font = header_font
                    cell.fill = header_fill
                    cell.alignment = header_alignment
                    cell.border = thin_border
                current_row += 1
                
                # 数据行
                for _ in range(11):
                    ws.row_dimensions[current_row].height = 60
                    for col in range(1, 7):
                        cell = ws.cell(row=current_row, column=col)
                        cell.alignment = cell_alignment
                        cell.border = thin_border
                    current_row += 1
                
                # 空行
                if group_idx < len(schedule_groups) - 1:
                    current_row += 1
        
        # ==================== 2. 教学班总览（列表视图） ====================
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
                time_str_list.append(f"周{day} 第{period}-{period+duration-1}节")
            
            # 获取周次汇总
            all_weeks = sorted(set(r.week for r in tc_results))
            week_str = _format_weeks(all_weeks)
            
            # 获取包含的班级信息
            admin_class_names = set()
            subgroup_count = 0
            for r in tc_results:
                if r.admin_class_id:
                    ac = admin_class_map.get(r.admin_class_id)
                    if ac:
                        cohort = cohort_map.get(ac.cohort_id)
                        if cohort:
                            admin_class_names.add(f"{cohort.major}{ac.class_index}班")
                if r.subgroup_ids:
                    subgroup_count = max(subgroup_count, len(r.subgroup_ids))
            
            overview_rows.append({
                '教学班ID': tc_id,
                '课程名称': first.course_name,
                '教师': first.teacher_name,
                '时间': '; '.join(time_str_list),
                '教室': first.room_name or '',
                '周次': week_str,
                '类型': '固定课' if first.is_fixed else ('实验课' if first.is_lab else '理论课'),
                '包含班级': ', '.join(sorted(admin_class_names)) if admin_class_names else '',
                '子组数量': subgroup_count if subgroup_count > 0 else '',
                '是否合班': '是' if first.is_combined else '否'
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
            ws.column_dimensions['A'].width = 25
            ws.column_dimensions['B'].width = 20
            ws.column_dimensions['C'].width = 10
            ws.column_dimensions['D'].width = 18
            ws.column_dimensions['E'].width = 10
            ws.column_dimensions['F'].width = 12
            ws.column_dimensions['G'].width = 10
            ws.column_dimensions['H'].width = 20
            ws.column_dimensions['I'].width = 10
            ws.column_dimensions['J'].width = 10
        
        # ==================== 3. 机房分配表（列表视图） ====================
        # 获取所有使用的机房
        rooms_used = set(r.room_name for r in results if r.room_name and r.is_lab)
        
        for room_name in sorted(rooms_used):
            sheet_name = f"机房-{room_name}"[:31]
            
            # 筛选该机房的课程
            room_results = [r for r in results if r.room_name == room_name]
            
            if not room_results:
                continue
            
            # 聚合数据：按(day, period, course, teacher, duration)分组
            room_data = {}
            for r in room_results:
                key = (r.day, r.period, r.course_name, r.teacher_name, r.duration)
                if key not in room_data:
                    room_data[key] = []
                room_data[key].append(r.week)
            
            # 构建列表数据
            room_rows = []
            for (day, period, course, teacher, duration), weeks in room_data.items():
                weeks_sorted = sorted(set(weeks))
                week_str = _format_weeks(weeks_sorted)
                room_rows.append({
                    '时间': f'周{day} 第{period}-{period+duration-1}节',
                    '课程名称': course,
                    '教师': teacher,
                    '周次': week_str,
                    '类型': '实验课'
                })
            
            # 按时间排序
            room_rows.sort(key=lambda x: (int(x['时间'][1]), int(x['时间'].split('第')[1].split('-')[0])))
            
            if room_rows:
                df_room = pd.DataFrame(room_rows)
                df_room.to_excel(writer, sheet_name=sheet_name, index=False)
                
                ws = writer.sheets[sheet_name]
                
                # 应用表头样式
                for col in range(1, 6):
                    cell = ws.cell(row=1, column=col)
                    cell.font = header_font
                    cell.fill = header_fill
                    cell.alignment = header_alignment
                    cell.border = thin_border
                
                ws.column_dimensions['A'].width = 15
                ws.column_dimensions['B'].width = 25
                ws.column_dimensions['C'].width = 12
                ws.column_dimensions['D'].width = 12
                ws.column_dimensions['E'].width = 10
                
                # 应用数据行样式
                for row in range(2, len(room_rows) + 2):
                    for col in range(1, 6):
                        cell = ws.cell(row=row, column=col)
                        cell.alignment = cell_alignment
                        cell.border = thin_border

    output.seek(0)
    
    from urllib.parse import quote
    semester_name = "上册" if session.semester == "first" else "下册"
    filename = f"课程表_{semester_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    # URL编码中文文件名
    encoded_filename = quote(filename)

    return StreamingResponse(
        output,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f"attachment; filename*=UTF-8''{encoded_filename}"}
    )


def _format_weeks(weeks: list) -> str:
    """格式化周次显示"""
    if not weeks:
        return ""
    weeks = sorted(list(set(weeks)))
    
    # 检查是否为单周模式（所有周次都是奇数，且间隔为2）
    if len(weeks) >= 4 and all(w % 2 == 1 for w in weeks):
        # 检查是否连续的单周
        is_consecutive_odd = all(weeks[i] == weeks[i-1] + 2 for i in range(1, len(weeks)))
        if is_consecutive_odd:
            return f"第{weeks[0]}-{weeks[-1]}周, 单周"
    
    # 检查是否为双周模式（所有周次都是偶数，且间隔为2）
    if len(weeks) >= 4 and all(w % 2 == 0 for w in weeks):
        # 检查是否连续的双周
        is_consecutive_even = all(weeks[i] == weeks[i-1] + 2 for i in range(1, len(weeks)))
        if is_consecutive_even:
            return f"第{weeks[0]}-{weeks[-1]}周, 双周"
    
    # 检查全周模式（连续周次）
    if len(weeks) >= 10 and weeks == list(range(weeks[0], weeks[-1] + 1)):
        return f"第{weeks[0]}-{weeks[-1]}周"

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
