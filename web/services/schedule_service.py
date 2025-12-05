"""
排课服务层 - 集成现有排课算法
支持：
- 学期筛选（上册/下册）
- 校本部教师特殊策略
- 虚拟子组到行政班映射
"""
import uuid
import sys
import os
import math
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Set
from collections import defaultdict
import multiprocessing

from sqlalchemy.orm import Session

# 添加父目录到路径以导入原有模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from models.time_definition import TimePoint, SEMESTER_WEEKS
from models.course import Course as AlgoCourse
from models.class_group import Cohort as AlgoCohort, AdminClass as AlgoAdminClass
from models.teacher import Teacher as AlgoTeacher
from models.room import Room as AlgoRoom
from data_processor import DataPreprocessor
from campus_pre_scheduler import CampusScheduler
from deap_scheduler import DeapScheduler

from ..models.db_models import (
    Cohort, AdminClass, Teacher, Course, Room,
    ScheduleResult, ScheduleSession, FixedSchedule,
    SubgroupAssignment, TeacherPreference, CombinedCourseGroup
)


class ScheduleService:
    """排课服务"""

    def __init__(self, db: Session):
        self.db = db

    def _convert_db_to_algo_objects(self, semester: str = "first") -> Tuple:
        """将数据库对象转换为算法所需的对象格式
        
        Args:
            semester: 学期，"first"(上册) 或 "second"(下册)
        """
        # 1. 转换教师
        db_teachers = self.db.query(Teacher).all()
        teachers_list = [
            AlgoTeacher(
                id=f"T{t.id:02d}",
                name=t.name,
                is_campus_teacher=t.is_campus_teacher
            )
            for t in db_teachers
        ]
        teacher_id_map = {t.id: f"T{t.id:02d}" for t in db_teachers}
        self._teacher_id_map = teacher_id_map  # 保存供后续使用
        self._teacher_db_map = {t.id: t for t in db_teachers}  # DB教师对象映射

        # 2. 转换机房
        db_rooms = self.db.query(Room).all()
        rooms_list = [
            AlgoRoom(id=f"R{r.id:02d}", name=r.name)
            for r in db_rooms
        ]

        # 3. 转换专业年级
        db_cohorts = self.db.query(Cohort).all()
        cohorts_list = [
            AlgoCohort(major=c.major, grade=c.grade)
            for c in db_cohorts
        ]
        cohorts_map = {c.id: f"{c.major}-{c.grade}" for c in db_cohorts}
        algo_cohorts_map = {f"{c.major}-{c.grade}": AlgoCohort(major=c.major, grade=c.grade) for c in db_cohorts}
        self._cohorts_map = cohorts_map  # 保存供后续使用
        self._cohorts_db_map = {c.id: c for c in db_cohorts}  # DB专业年级对象映射

        # 4. 转换行政班
        db_admin_classes = self.db.query(AdminClass).all()
        admin_classes = [
            AlgoAdminClass(
                id=f"AC_{cohorts_map[ac.cohort_id]}_{ac.class_index}",
                cohort=algo_cohorts_map[cohorts_map[ac.cohort_id]],
                class_index=ac.class_index,
                student_count=ac.student_count
            )
            for ac in db_admin_classes
        ]
        # 行政班映射: cohort_id -> [admin_class_db_objects]
        self._admin_classes_by_cohort = defaultdict(list)
        for ac in db_admin_classes:
            self._admin_classes_by_cohort[ac.cohort_id].append(ac)

        # 5. 转换课程 - 按学期筛选
        db_courses = self.db.query(Course).filter(
            (Course.semester == semester) | (Course.semester == "both")
        ).all()
        course_by_cohort = defaultdict(list)
        teacher_course_map = {}

        # 获取合班课程组信息
        combined_groups = self.db.query(CombinedCourseGroup).all()
        group_courses_map = defaultdict(list)  # group_id -> [course_ids]
        for c in db_courses:
            if c.combined_group_id:
                group_courses_map[c.combined_group_id].append(c.id)

        for c in db_courses:
            # 处理合班课程ID - 优先使用combined_group_id
            combined_with = []
            if c.combined_group_id:
                other_course_ids = [cid for cid in group_courses_map[c.combined_group_id] if cid != c.id]
                combined_with = [f"C{cid}" for cid in other_course_ids]
            elif c.combined_with:
                combined_with = [f"C{cid}" for cid in c.combined_with]

            # 处理教师覆盖
            teacher_override = {}
            if c.teacher_override:
                for class_num, tid in c.teacher_override.items():
                    teacher_override[int(class_num)] = teacher_id_map.get(int(tid))

            # 处理分阶段教师
            phase_teachers = {}
            if c.phase_teachers:
                for phase, config in c.phase_teachers.items():
                    if isinstance(config, list) and len(config) >= 3:
                        phase_teachers[phase] = (config[0], config[1], teacher_id_map.get(int(config[2])))

            # 判断是单专业课还是多专业课（公共课/合班课）
            cohort_ids_list = c.cohort_ids or []
            is_multi_cohort = len(cohort_ids_list) > 1
            
            if is_multi_cohort:
                # 多专业课（合班课）：为每个专业独立生成课程对象，通过combined_with关联
                # 教学班数量保持小数，算法会通过分数计算处理合班逻辑
                # 例如: 2.5 + 1.5 = 4个教学班，其中0.5+0.5是合班的
                cohort_counts = c.cohort_teaching_class_counts or {}
                
                # 生成所有专业的课程ID列表
                multi_cohort_course_ids = [f"C{c.id}_cohort{cid}" for cid in cohort_ids_list if cohorts_map.get(cid)]
                
                for cid in cohort_ids_list:
                    cohort_key = cohorts_map.get(cid)
                    if not cohort_key or cohort_key not in algo_cohorts_map:
                        continue
                    
                    algo_cohort = algo_cohorts_map[cohort_key]
                    # 为每个专业生成独立的课程ID
                    course_id = f"C{c.id}_cohort{cid}"
                    # 获取该专业的教学班数量，保持小数用于合班计算
                    teaching_class_count = cohort_counts.get(str(cid), 1.0)
                    
                    # 合班关联：包含同一课程的其他专业版本 + 原有的combined_with
                    multi_cohort_combined = [cid for cid in multi_cohort_course_ids if cid != course_id]
                    full_combined_with = list(set(combined_with + multi_cohort_combined))
                    
                    algo_course = AlgoCourse(
                        id=course_id,
                        name=c.name,
                        course_type=c.course_type,
                        theory_hours=c.theory_hours,
                        lab_hours=c.lab_hours,
                        teaching_class_count=teaching_class_count,
                        preferred_pattern=c.preferred_pattern,
                        combined_with=full_combined_with,
                        teacher_override=teacher_override if teacher_override else None,
                        phase_teachers=phase_teachers if phase_teachers else None,
                        is_graduation_course=c.is_graduation_course if hasattr(c, 'is_graduation_course') else False
                    )
                    
                    course_by_cohort[algo_cohort].append(algo_course)
                    
                    if c.teacher_id:
                        teacher_course_map[course_id] = teacher_id_map.get(c.teacher_id)
            else:
                # 单专业课或无专业课（保持原来的逻辑）
                cohort_key = cohorts_map.get(c.cohort_id)
                if not cohort_key or cohort_key not in algo_cohorts_map:
                    continue

                algo_cohort = algo_cohorts_map[cohort_key]
                course_id = f"C{c.id}"

                algo_course = AlgoCourse(
                    id=course_id,
                    name=c.name,
                    course_type=c.course_type,
                    theory_hours=c.theory_hours,
                    lab_hours=c.lab_hours,
                    teaching_class_count=c.teaching_class_count,
                    preferred_pattern=c.preferred_pattern,
                    combined_with=combined_with,
                    teacher_override=teacher_override if teacher_override else None,
                    phase_teachers=phase_teachers if phase_teachers else None,
                    is_graduation_course=c.is_graduation_course if hasattr(c, 'is_graduation_course') else False
                )

                course_by_cohort[algo_cohort].append(algo_course)

                if c.teacher_id:
                    teacher_course_map[course_id] = teacher_id_map.get(c.teacher_id)

        # 6. 转换固定课程 - 按学期筛选
        db_fixed = self.db.query(FixedSchedule).filter(
            (FixedSchedule.semester == semester) | (FixedSchedule.semester == "both")
        ).all()
        fixed_schedule = []
        self._fixed_schedule_db = db_fixed  # 保存供后续映射使用
        
        for f in db_fixed:
            cohort_key = cohorts_map.get(f.cohort_id)
            if not cohort_key:
                continue

            fixed_schedule.append({
                'cohort_id': cohort_key,
                'course_name': f.course_name,
                'teacher_name': f.teacher_name,
                'duration': f.duration,
                'week': f.weeks,
                'start_time': TimePoint(week=None, day=f.day, period=f.period),
                'admin_class_ids': f.admin_class_ids or [],  # 行政班ID列表，为空表示全部
                'db_cohort_id': f.cohort_id  # 原始数据库cohort_id
            })

        # 7. 转换教师偏好
        db_preferences = self.db.query(TeacherPreference).all()
        teacher_preferences = []

        # 首先为校本部教师添加默认偏好
        for t in teachers_list:
            if t.is_campus_teacher:
                from models.time_definition import AFTERNOOM_PERIODS, EVENING_PERIODS
                teacher_preferences.append({
                    'teacher_name': t.name,
                    'course_name': None,
                    'undesired_slots': [(3, p) for p in AFTERNOOM_PERIODS + EVENING_PERIODS] + [(4, -1), (5, -1)]
                })

        # 添加数据库中的偏好
        for pref in db_preferences:
            teacher = self.db.query(Teacher).filter(Teacher.id == pref.teacher_id).first()
            course = self.db.query(Course).filter(Course.id == pref.course_id).first() if pref.course_id else None

            if teacher:
                teacher_preferences.append({
                    'teacher_name': teacher.name,
                    'course_name': course.name if course else None,
                    'preferred_slots': [(s[0], s[1]) for s in (pref.preferred_slots or [])],
                    'undesired_slots': [(s[0], s[1]) for s in (pref.undesired_slots or [])]
                })

        # 8. 转换子组预分配
        db_assignments = self.db.query(SubgroupAssignment).all()
        subgroup_pre_assignment = defaultdict(dict)
        for a in db_assignments:
            cohort_key = cohorts_map.get(a.cohort_id)
            if cohort_key:
                subgroup_pre_assignment[cohort_key][a.group_tag] = a.ratio

        # 默认分配（如果没有配置）
        for c in db_cohorts:
            cohort_key = f"{c.major}-{c.grade}"
            if cohort_key not in subgroup_pre_assignment:
                subgroup_pre_assignment[cohort_key] = {'default': 1.0}

        return (
            teachers_list, rooms_list, cohorts_list, admin_classes,
            dict(course_by_cohort), teacher_course_map, fixed_schedule,
            teacher_preferences, dict(subgroup_pre_assignment)
        )

    def start_scheduling(self, cohort_ids: List[int] = None, semester: str = "first") -> str:
        """开始排课，返回会话ID
        
        Args:
            cohort_ids: 指定要排课的专业年级ID列表，None表示全部
            semester: 学期，"first"(上册) 或 "second"(下册)
        """
        session_id = str(uuid.uuid4())[:8]

        # 创建排课会话记录
        session = ScheduleSession(
            session_id=session_id,
            semester=semester,
            status="running",
            message=f"排课进行中（{semester == 'first' and '上册' or '下册'}）..."
        )
        self.db.add(session)
        self.db.commit()

        try:
            # 转换数据（按学期筛选）
            (teachers_list, rooms_list, cohorts_list, admin_classes,
             course_by_cohort, teacher_course_map, fixed_schedule,
             teacher_preferences, subgroup_pre_assignment) = self._convert_db_to_algo_objects(semester)

            # 数据预处理
            data_processor = DataPreprocessor(
                teachers_list, cohorts_list, course_by_cohort,
                teacher_course_map, subgroup_pre_assignment
            )
            all_subgroups, all_teaching_classes, tc_to_sg_map = data_processor.process_data()

            # 分离校本部教师课程
            campus_tcs, other_tcs = [], []
            campus_teacher_names = {t.name for t in teachers_list if t.is_campus_teacher}

            for tc in all_teaching_classes:
                if tc.teacher_name in campus_teacher_names:
                    if tc.teacher_name not in tc.course.campus_teachers:
                        tc.course.campus_teachers.append(tc.teacher_name)
                    campus_tcs.append(tc)
                else:
                    other_tcs.append(tc)

            # 校本部教师确定性排课
            campus_detailed_results = []
            campus_fixed_results = []
            campus_scheduler = None

            for i in range(100):
                # 清理上一次的调度器
                if campus_scheduler is not None:
                    campus_scheduler.cleanup()
                    
                campus_scheduler = CampusScheduler(
                    campus_tcs, all_subgroups, tc_to_sg_map,
                    teachers_list, rooms_list, fixed_schedule
                )
                campus_detailed_results, campus_fixed_results, failed_campus_tcs = campus_scheduler.schedule()
                if not failed_campus_tcs:
                    break
            
            # 清理最后一次的调度器
            if campus_scheduler is not None:
                campus_scheduler.cleanup()

            # 遗传算法排课
            updated_fixed_schedule = fixed_schedule + campus_fixed_results
            
            scheduler = None
            pool = None
            try:
                # 限制进程数避免资源耗尽
                cpu_count = min(multiprocessing.cpu_count(), 4)
                pool = multiprocessing.Pool(processes=cpu_count)
                
                scheduler = DeapScheduler(
                    teachers=teachers_list,
                    rooms=rooms_list,
                    subgroups=all_subgroups,
                    teaching_classes=other_tcs,
                    tc_to_sg_map=tc_to_sg_map,
                    fixed_schedule=updated_fixed_schedule,
                    teacher_preferences=teacher_preferences
                )
                success = scheduler.solve(pool)
                
                ga_results = scheduler.get_results()
                best_fitness = getattr(scheduler, 'best_fitness', 9999)
            finally:
                # 确保资源被清理
                if pool is not None:
                    pool.close()
                    pool.join()
                    pool.terminate()
                if scheduler is not None:
                    scheduler.cleanup()
                # 强制垃圾回收
                import gc
                gc.collect()

            final_schedule_details = campus_detailed_results + ga_results

            # 保存排课结果到数据库（包含行政班映射）
            self._save_results(session_id, final_schedule_details, fixed_schedule, tc_to_sg_map, all_subgroups)

            # 更新会话状态
            session.status = "completed" if success else "completed_with_warnings"
            session.fitness_score = best_fitness
            session.message = "排课成功" if success else f"排课完成，但存在冲突（惩罚分数: {best_fitness:.2f}）"
            session.completed_at = datetime.now()
            self.db.commit()

            return session_id

        except Exception as e:
            session.status = "failed"
            session.message = f"排课失败: {str(e)}"
            self.db.commit()
            # 清理实例变量释放内存
            import gc
            gc.collect()
            raise

    def _compute_subgroup_to_admin_mapping(self, all_subgroups: List, cohort_key: str) -> Dict[str, List]:
        """计算虚拟子组到行政班的映射
        
        算法逻辑：
        1. 获取该专业年级的所有子组，按ID排序确保一致性
        2. 将子组平均分配到行政班
        3. 例如：4个子组，4个行政班 -> 每班1个子组
        4. 例如：8个子组，4个行政班 -> 每班2个子组
        
        Args:
            all_subgroups: 所有虚拟子组 (models.class_group.SubGroup 对象列表)
            cohort_key: 专业年级标识 (如 "计算机科学与技术-2024")
            
        Returns:
            Dict[str, List]: 子组ID -> [行政班DB对象列表]
        """
        # 获取该专业年级的子组，按ID排序确保一致性
        cohort_subgroups = sorted(
            [sg for sg in all_subgroups if sg.cohort.id == cohort_key],
            key=lambda sg: sg.id
        )
        
        # 通过cohort_key反查cohort_id
        cohort_id = None
        for cid, ckey in self._cohorts_map.items():
            if ckey == cohort_key:
                cohort_id = cid
                break
        
        if cohort_id is None:
            return {}
        
        # 获取行政班，按class_index排序
        admin_classes = sorted(
            self._admin_classes_by_cohort.get(cohort_id, []),
            key=lambda ac: ac.class_index
        )
        admin_class_count = len(admin_classes)
        
        if not cohort_subgroups or admin_class_count == 0:
            return {}
        
        subgroup_count = len(cohort_subgroups)
        
        # 计算每个行政班分配多少子组
        subgroups_per_admin = subgroup_count / admin_class_count
        
        mapping = {}
        
        # 按子组索引分配到行政班
        for i, sg in enumerate(cohort_subgroups):
            # 计算该子组属于哪个行政班
            admin_idx = int(i / subgroups_per_admin)
            admin_idx = min(admin_idx, admin_class_count - 1)  # 防止越界
            
            # 分配到对应的行政班 (返回DB对象而不是class_index)
            mapping[sg.id] = [admin_classes[admin_idx]]
        
        return mapping

    def _save_results(self, session_id: str, results: List[Dict], fixed_schedule: List[Dict], 
                      tc_to_sg_map: Dict, all_subgroups: List):
        """保存排课结果到数据库，包含行政班映射
        
        核心逻辑：
        1. 每个教学班对应若干虚拟子组
        2. 每个虚拟子组映射到一个行政班
        3. 一门课的所有记录都要写到所有涉及的行政班
        """
        # 清除该会话的旧结果
        self.db.query(ScheduleResult).filter(ScheduleResult.session_id == session_id).delete()

        # 计算所有专业年级的子组到行政班映射
        # 返回: {subgroup_id: [AdminClass DB对象]}
        subgroup_to_admin_mapping = {}
        cohort_keys = set()
        for sg in all_subgroups:
            cohort_keys.add(sg.cohort.id)
        
        for cohort_key in cohort_keys:
            cohort_mapping = self._compute_subgroup_to_admin_mapping(all_subgroups, cohort_key)
            subgroup_to_admin_mapping.update(cohort_mapping)
        
        # 保存算法结果 - 按行政班拆分存储
        for res in results:
            tp = res['time_point']
            tc_id = res['teaching_class_id']
            
            # 获取该教学班对应的子组
            subgroup_ids = []
            subgroups = tc_to_sg_map.get(tc_id, [])
            if subgroups:
                subgroup_ids = [sg.id for sg in subgroups]
            
            # 获取涉及的行政班 (DB对象)
            admin_classes_set = set()
            cohort_id = None
            
            for sg_id in subgroup_ids:
                if sg_id in subgroup_to_admin_mapping:
                    for ac in subgroup_to_admin_mapping[sg_id]:
                        admin_classes_set.add(ac)
                        if cohort_id is None:
                            cohort_id = ac.cohort_id
            
            # 如果从子组没找到cohort_id，从teaching_class_id解析
            if cohort_id is None:
                for cid, ckey in self._cohorts_map.items():
                    if ckey in tc_id:
                        cohort_id = cid
                        break
            
            # 转换numpy类型为Python原生类型
            week_val = int(tp.week) if tp.week is not None else None
            day_val = int(tp.day) if tp.day is not None else None
            period_val = int(tp.period) if tp.period is not None else None
            duration_val = int(res['duration']) if res.get('duration') is not None else 2
            
            # 为每个行政班创建一条记录（这样每个班级都能查到自己的课表）
            if admin_classes_set:
                for ac in admin_classes_set:
                    result = ScheduleResult(
                        session_id=session_id,
                        cohort_id=ac.cohort_id,
                        admin_class_id=ac.id,
                        teaching_class_id=tc_id,
                        subgroup_ids=subgroup_ids,
                        course_name=res['course_name'],
                        teacher_name=res['teacher_name'],
                        week=week_val,
                        day=day_val,
                        period=period_val,
                        duration=duration_val,
                        room_name=res.get('room_name'),
                        is_lab=bool(res.get('is_lab', False)),
                        is_combined=bool(res.get('is_combined', False)),
                        is_fixed=False
                    )
                    self.db.add(result)
            else:
                # 没有行政班映射时，仍然保存一条记录（按cohort）
                result = ScheduleResult(
                    session_id=session_id,
                    cohort_id=cohort_id,
                    admin_class_id=None,
                    teaching_class_id=tc_id,
                    subgroup_ids=subgroup_ids,
                    course_name=res['course_name'],
                    teacher_name=res['teacher_name'],
                    week=week_val,
                    day=day_val,
                    period=period_val,
                    duration=duration_val,
                    room_name=res.get('room_name'),
                    is_lab=bool(res.get('is_lab', False)),
                    is_combined=bool(res.get('is_combined', False)),
                    is_fixed=False
                )
                self.db.add(result)

        # 保存固定课程 - 按行政班拆分存储
        for item in fixed_schedule:
            cohort_id = item.get('db_cohort_id')
            specified_admin_class_ids = item.get('admin_class_ids', [])
            
            # 查找行政班的数据库记录
            admin_class_db_list = []
            if cohort_id:
                admin_classes_db = self._admin_classes_by_cohort.get(cohort_id, [])
                if specified_admin_class_ids:
                    # 只为指定的行政班创建记录（按ID筛选）
                    for ac in admin_classes_db:
                        if ac.id in specified_admin_class_ids:
                            admin_class_db_list.append(ac)
                else:
                    # 没指定则为该专业年级所有行政班创建记录
                    admin_class_db_list = admin_classes_db
            
            for week in item['week']:
                # 转换numpy类型为Python原生类型
                week_val = int(week) if week is not None else None
                day_val = int(item['start_time'].day) if item['start_time'].day is not None else None
                period_val = int(item['start_time'].period) if item['start_time'].period is not None else None
                duration_val = int(item['duration']) if item.get('duration') is not None else 2
                
                # 生成唯一的teaching_class_id，包含时间信息以区分不同时间的同名课程
                teaching_class_id = f"FIXED_{item['course_name']}_D{day_val}P{period_val}"
                
                if admin_class_db_list:
                    # 为每个行政班创建一条记录
                    for ac in admin_class_db_list:
                        result = ScheduleResult(
                            session_id=session_id,
                            cohort_id=cohort_id,
                            admin_class_id=ac.id,
                            teaching_class_id=teaching_class_id,
                            course_name=item['course_name'],
                            teacher_name=item['teacher_name'],
                            week=week_val,
                            day=day_val,
                            period=period_val,
                            duration=duration_val,
                            is_fixed=True
                        )
                        self.db.add(result)
                else:
                    # 没有行政班信息时，保存一条记录
                    result = ScheduleResult(
                        session_id=session_id,
                        cohort_id=cohort_id,
                        admin_class_id=None,
                        teaching_class_id=teaching_class_id,
                        course_name=item['course_name'],
                        teacher_name=item['teacher_name'],
                        week=week_val,
                        day=day_val,
                        period=period_val,
                        duration=duration_val,
                        is_fixed=True
                    )
                    self.db.add(result)

        self.db.commit()

    def get_schedule_results(self, session_id: str) -> List[ScheduleResult]:
        """获取排课结果"""
        return self.db.query(ScheduleResult).filter(
            ScheduleResult.session_id == session_id
        ).order_by(
            ScheduleResult.week,
            ScheduleResult.day,
            ScheduleResult.period
        ).all()

    def get_latest_session(self, semester: str = None) -> Optional[ScheduleSession]:
        """获取最新的排课会话
        
        Args:
            semester: 学期筛选 - "first"(上册) 或 "second"(下册)，不传则返回最新的
        """
        query = self.db.query(ScheduleSession)
        if semester:
            query = query.filter(ScheduleSession.semester == semester)
        return query.order_by(ScheduleSession.created_at.desc()).first()

    def update_schedule_result(self, result_id: int, week: int = None, day: int = None,
                                period: int = None, room_name: str = None) -> ScheduleResult:
        """手动调整排课结果"""
        result = self.db.query(ScheduleResult).filter(ScheduleResult.id == result_id).first()
        if not result:
            return None

        if week is not None:
            result.week = week
        if day is not None:
            result.day = day
        if period is not None:
            result.period = period
        if room_name is not None:
            result.room_name = room_name

        self.db.commit()
        self.db.refresh(result)
        return result

    def get_schedule_by_cohort(self, session_id: str, cohort_id: int) -> Dict:
        """按专业年级获取课表"""
        cohort = self.db.query(Cohort).filter(Cohort.id == cohort_id).first()
        if not cohort:
            return None

        cohort_key = f"{cohort.major}-{cohort.grade}"

        # 获取该专业年级的所有课程结果
        results = self.db.query(ScheduleResult).filter(
            ScheduleResult.session_id == session_id
        ).all()

        # 按天和节次组织数据
        schedule_data = defaultdict(lambda: defaultdict(list))

        for r in results:
            # 简单匹配：检查教学班ID是否包含专业年级标识
            if cohort_key in r.teaching_class_id or r.is_fixed:
                for d in range(r.duration):
                    period = r.period + d
                    schedule_data[r.day][period].append({
                        'id': r.id,
                        'course_name': r.course_name,
                        'teacher_name': r.teacher_name,
                        'room_name': r.room_name,
                        'week': r.week,
                        'duration': r.duration,
                        'is_lab': r.is_lab,
                        'is_combined': r.is_combined
                    })

        return {
            'cohort_id': cohort_id,
            'cohort_name': cohort_key,
            'schedule': dict(schedule_data)
        }
