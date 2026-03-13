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
import importlib.util

from sqlalchemy.orm import Session

# 先导入数据库模型（相对导入）
from ..dbmodels.db_models import (
    Cohort, AdminClass, Teacher, Course, Room,
    ScheduleResult, ScheduleSession, FixedSchedule,
    SubgroupAssignment, TeacherPreference, CombinedCourseGroup
)

# 排课算法模块的根目录
_algo_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load_algo_module(module_name: str, file_name: str = None):
    """动态加载排课算法模块"""
    if file_name is None:
        file_name = f"{module_name}.py"
    
    if '.' in module_name:
        parts = module_name.split('.')
        file_path = os.path.join(_algo_path, *parts[:-1], f"{parts[-1]}.py")
    else:
        file_path = os.path.join(_algo_path, file_name)

    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# 导入排课算法模块
_time_def_module = _load_algo_module("models.time_definition")
TimePoint = _time_def_module.TimePoint
SEMESTER_WEEKS = _time_def_module.SEMESTER_WEEKS
AFTERNOOM_PERIODS = _time_def_module.AFTERNOOM_PERIODS
EVENING_PERIODS = _time_def_module.EVENING_PERIODS

_course_module = _load_algo_module("models.course")
AlgoCourse = _course_module.Course

_teacher_module = _load_algo_module("models.teacher")
AlgoTeacher = _teacher_module.Teacher

_class_group_module = _load_algo_module("models.class_group")
AlgoCohort = _class_group_module.Cohort
AlgoAdminClass = _class_group_module.AdminClass

_room_module = _load_algo_module("models.room")
AlgoRoom = _room_module.Room

_data_processor_module = _load_algo_module("data_processor")
DataPreprocessor = _data_processor_module.DataPreprocessor

_campus_scheduler_module = _load_algo_module("campus_pre_scheduler")
CampusScheduler = _campus_scheduler_module.CampusScheduler

_deap_scheduler_module = _load_algo_module("deap_scheduler")
DeapScheduler = _deap_scheduler_module.DeapScheduler


class ScheduleService:
    """排课服务"""

    def __init__(self, db: Session):
        self.db = db

    def _convert_db_to_algo_objects(self, semester: str = "first") -> Tuple:
        """将数据库对象转换为算法所需的对象格式"""
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

        combined_groups = self.db.query(CombinedCourseGroup).all()
        group_courses_map = defaultdict(list)
        for c in db_courses:
            if c.combined_group_id:
                group_courses_map[c.combined_group_id].append(c.id)

        for c in db_courses:
            combined_with = []
            if c.combined_group_id:
                other_course_ids = [cid for cid in group_courses_map[c.combined_group_id] if cid != c.id]
                combined_with = [f"C{cid}" for cid in other_course_ids]
            elif c.combined_with:
                combined_with = [f"C{cid}" for cid in c.combined_with]

            teacher_override = {}
            teacher_dual_configs = {}

            if c.teacher_configs and len(c.teacher_configs) > 0:
                class_num = 1
                for config in c.teacher_configs:
                    tid = config.get('teacher_id')
                    class_count = config.get('class_count', 1)
                    if tid:
                        algo_tid = teacher_id_map.get(int(tid))
                        for _ in range(int(class_count)):
                            teacher_override[class_num] = algo_tid
                            if config.get('dual_enabled') and config.get('second_teacher_id'):
                                teacher_dual_configs[class_num] = {
                                    'second_teacher_id': teacher_id_map.get(int(config['second_teacher_id'])),
                                    'split_week': config.get('split_week', 8)
                                }
                            class_num += 1
            elif c.teacher_override:
                for class_num, tid in c.teacher_override.items():
                    teacher_override[int(class_num)] = teacher_id_map.get(int(tid))

            phase_teachers = {}
            if c.phase_teachers:
                for phase, config in c.phase_teachers.items():
                    if isinstance(config, list) and len(config) >= 3:
                        phase_teachers[phase] = (config[0], config[1], teacher_id_map.get(int(config[2])))

            cohort_ids_list = c.cohort_ids or []
            is_multi_cohort = len(cohort_ids_list) > 1

            if is_multi_cohort:
                cohort_counts = c.cohort_teaching_class_counts or {}
                multi_cohort_course_ids = [f"C{c.id}_cohort{cid}" for cid in cohort_ids_list if cohorts_map.get(cid)]

                for cid in cohort_ids_list:
                    cohort_key = cohorts_map.get(cid)
                    if not cohort_key or cohort_key not in algo_cohorts_map:
                        continue

                    algo_cohort = algo_cohorts_map[cohort_key]
                    course_id = f"C{c.id}_cohort{cid}"
                    teaching_class_count = cohort_counts.get(str(cid), 1.0)

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

                    if c.teacher_configs and len(c.teacher_configs) > 0:
                        first_teacher_id = c.teacher_configs[0].get('teacher_id')
                        if first_teacher_id:
                            teacher_course_map[course_id] = teacher_id_map.get(int(first_teacher_id))
                    elif c.teacher_id:
                        teacher_course_map[course_id] = teacher_id_map.get(c.teacher_id)
            else:
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

                if c.teacher_configs and len(c.teacher_configs) > 0:
                    first_teacher_id = c.teacher_configs[0].get('teacher_id')
                    if first_teacher_id:
                        teacher_course_map[course_id] = teacher_id_map.get(int(first_teacher_id))
                elif c.teacher_id:
                    teacher_course_map[course_id] = teacher_id_map.get(c.teacher_id)

        # 6. 转换固定课程
        db_fixed = self.db.query(FixedSchedule).filter(
            (FixedSchedule.semester == semester) | (FixedSchedule.semester == "both")
        ).all()
        fixed_schedule = []
        self._fixed_schedule_db = db_fixed

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
                'admin_class_ids': f.admin_class_ids or [],
                'db_cohort_id': f.cohort_id
            })

        # 7. 转换教师偏好
        db_preferences = self.db.query(TeacherPreference).all()
        teacher_preferences = []

        for t in teachers_list:
            if t.is_campus_teacher:
                teacher_preferences.append({
                    'teacher_name': t.name,
                    'course_name': None,
                    'undesired_slots': [(3, p) for p in AFTERNOOM_PERIODS + EVENING_PERIODS] + [(4, -1), (5, -1)]
                })

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
        """开始排课，返回会话ID"""
        session_id = str(uuid.uuid4())[:8]

        session = ScheduleSession(
            session_id=session_id,
            semester=semester,
            status="running",
            message=f"排课进行中（{semester == 'first' and '上册' or '下册'}）..."
        )
        self.db.add(session)
        self.db.commit()

        try:
            (teachers_list, rooms_list, cohorts_list, admin_classes,
             course_by_cohort, teacher_course_map, fixed_schedule,
             teacher_preferences, subgroup_pre_assignment) = self._convert_db_to_algo_objects(semester)

            data_processor = DataPreprocessor(
                teachers_list, cohorts_list, course_by_cohort,
                teacher_course_map, subgroup_pre_assignment
            )
            all_subgroups, all_teaching_classes, tc_to_sg_map = data_processor.process_data()

            # [关键修补]: 预先计算行政班对应的虚拟子组，并打在 fixed_schedule 上
            subgroup_to_admin_mapping = {}
            cohort_keys = {sg.cohort.id for sg in all_subgroups}
            for cohort_key in cohort_keys:
                cohort_mapping = self._compute_subgroup_to_admin_mapping(all_subgroups, cohort_key)
                subgroup_to_admin_mapping.update(cohort_mapping)

            admin_to_subgroup_ids = defaultdict(list)
            for sg_id, ac_list in subgroup_to_admin_mapping.items():
                for ac in ac_list:
                    admin_to_subgroup_ids[ac.id].append(sg_id)

            for item in fixed_schedule:
                # 兼容 Web 端的 admin_class_ids 限定策略
                if item.get('admin_class_ids'):
                    sg_ids = set()
                    for ac_id in item['admin_class_ids']:
                        sg_ids.update(admin_to_subgroup_ids.get(ac_id, []))
                    item['subgroup_ids'] = list(sg_ids)
                else:
                    cohort_id = item.get('cohort_id')
                    item['subgroup_ids'] = [sg.id for sg in all_subgroups if sg.cohort.id == cohort_id]

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

            if campus_tcs:
                best_detailed = []
                best_fixed = []
                best_failed_count = len(campus_tcs) + 1
                consecutive_same_failures = 0
                last_failed_count = -1

                for i in range(20):
                    if campus_scheduler is not None:
                        campus_scheduler.cleanup()

                    campus_scheduler = CampusScheduler(
                        campus_tcs, all_subgroups, tc_to_sg_map,
                        teachers_list, rooms_list, fixed_schedule
                    )
                    campus_detailed_results, campus_fixed_results, failed_campus_tcs = campus_scheduler.schedule()
                    current_failed_count = len(failed_campus_tcs)

                    if current_failed_count < best_failed_count:
                        best_detailed = campus_detailed_results
                        best_fixed = campus_fixed_results
                        best_failed_count = current_failed_count

                    if not failed_campus_tcs:
                        break

                    if current_failed_count == last_failed_count:
                        consecutive_same_failures += 1
                        if consecutive_same_failures >= 3:
                            break
                    else:
                        consecutive_same_failures = 1
                    last_failed_count = current_failed_count

                campus_detailed_results = best_detailed
                campus_fixed_results = best_fixed

            if campus_scheduler is not None:
                campus_scheduler.cleanup()

            updated_fixed_schedule = fixed_schedule + campus_fixed_results

            scheduler = None
            pool = None
            penalty_details = None
            try:
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
                penalty_details = scheduler.get_penalty_details()
            finally:
                if pool is not None:
                    pool.close()
                    pool.join()
                    pool.terminate()
                if scheduler is not None:
                    scheduler.cleanup()
                import gc
                gc.collect()

            final_schedule_details = campus_detailed_results + ga_results

            self._save_results(session_id, final_schedule_details, fixed_schedule, tc_to_sg_map, all_subgroups)

            session.status = "completed" if success else "completed_with_warnings"
            session.fitness_score = best_fitness
            session.penalty_details = penalty_details
            session.message = "排课成功" if success else f"排课完成，但存在冲突（惩罚分数: {best_fitness:.2f}）"
            session.completed_at = datetime.now()
            self.db.commit()

            return session_id

        except Exception as e:
            session.status = "failed"
            session.message = f"排课失败: {str(e)}"
            self.db.commit()
            import gc
            gc.collect()
            raise

    def _compute_subgroup_to_admin_mapping(self, all_subgroups: List, cohort_key: str) -> Dict[str, List]:
        import re

        def extract_subgroup_number(sg_id: str) -> int:
            match = re.search(r'_(\d+)$', sg_id)
            return int(match.group(1)) if match else 0

        cohort_subgroups = sorted(
            [sg for sg in all_subgroups if sg.cohort.id == cohort_key],
            key=lambda sg: extract_subgroup_number(sg.id)
        )

        cohort_id = None
        for cid, ckey in self._cohorts_map.items():
            if ckey == cohort_key:
                cohort_id = cid
                break

        if cohort_id is None:
            return {}

        admin_classes = sorted(
            self._admin_classes_by_cohort.get(cohort_id, []),
            key=lambda ac: ac.class_index
        )
        admin_class_count = len(admin_classes)

        if not cohort_subgroups or admin_class_count == 0:
            return {}

        subgroup_count = len(cohort_subgroups)
        subgroups_per_admin = subgroup_count / admin_class_count
        admin_to_subgroups = {i: [] for i in range(admin_class_count)}

        for admin_idx in range(admin_class_count):
            start = admin_idx * subgroups_per_admin
            end = (admin_idx + 1) * subgroups_per_admin

            for sg_idx in range(subgroup_count):
                if sg_idx < end and (sg_idx + 1) > start:
                    admin_to_subgroups[admin_idx].append(sg_idx)

        mapping = {}
        for sg_idx, sg in enumerate(cohort_subgroups):
            sg_admins = []
            for admin_idx in range(admin_class_count):
                if sg_idx in admin_to_subgroups[admin_idx]:
                    sg_admins.append(admin_classes[admin_idx])
            mapping[sg.id] = sg_admins

        return mapping

    def _save_results(self, session_id: str, results: List[Dict], fixed_schedule: List[Dict],
                      tc_to_sg_map: Dict, all_subgroups: List):
        self.db.query(ScheduleResult).filter(ScheduleResult.session_id == session_id).delete()

        subgroup_to_admin_mapping = {}
        cohort_keys = set()
        for sg in all_subgroups:
            cohort_keys.add(sg.cohort.id)

        for cohort_key in cohort_keys:
            cohort_mapping = self._compute_subgroup_to_admin_mapping(all_subgroups, cohort_key)
            subgroup_to_admin_mapping.update(cohort_mapping)

        for res in results:
            tp = res['time_point']
            tc_id = res['teaching_class_id']

            subgroup_ids = []
            subgroups = tc_to_sg_map.get(tc_id, [])
            if subgroups:
                subgroup_ids = [sg.id for sg in subgroups]

            admin_classes_set = set()
            cohort_id = None

            for sg_id in subgroup_ids:
                if sg_id in subgroup_to_admin_mapping:
                    for ac in subgroup_to_admin_mapping[sg_id]:
                        admin_classes_set.add(ac)
                        if cohort_id is None:
                            cohort_id = ac.cohort_id

            if cohort_id is None:
                for cid, ckey in self._cohorts_map.items():
                    if ckey in tc_id:
                        cohort_id = cid
                        break

            week_val = int(tp.week) if tp.week is not None else None
            day_val = int(tp.day) if tp.day is not None else None
            period_val = int(tp.period) if tp.period is not None else None
            duration_val = int(res['duration']) if res.get('duration') is not None else 2

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

        for item in fixed_schedule:
            cohort_id = item.get('db_cohort_id')
            specified_admin_class_ids = item.get('admin_class_ids', [])

            admin_class_db_list = []
            if cohort_id:
                admin_classes_db = self._admin_classes_by_cohort.get(cohort_id, [])
                if specified_admin_class_ids:
                    for ac in admin_classes_db:
                        if ac.id in specified_admin_class_ids:
                            admin_class_db_list.append(ac)
                else:
                    admin_class_db_list = admin_classes_db

            for week in item['week']:
                week_val = int(week) if week is not None else None
                day_val = int(item['start_time'].day) if item['start_time'].day is not None else None
                period_val = int(item['start_time'].period) if item['start_time'].period is not None else None
                duration_val = int(item['duration']) if item.get('duration') is not None else 2

                teaching_class_id = f"FIXED_{item['course_name']}_D{day_val}P{period_val}"

                if admin_class_db_list:
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
        return self.db.query(ScheduleResult).filter(
            ScheduleResult.session_id == session_id
        ).order_by(
            ScheduleResult.week,
            ScheduleResult.day,
            ScheduleResult.period
        ).all()

    def get_latest_session(self, semester: str = None) -> Optional[ScheduleSession]:
        query = self.db.query(ScheduleSession)
        if semester:
            query = query.filter(ScheduleSession.semester == semester)
        return query.order_by(ScheduleSession.created_at.desc()).first()

    def update_schedule_result(self, result_id: int, week: int = None, day: int = None,
                                period: int = None, room_name: str = None) -> ScheduleResult:
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
        cohort = self.db.query(Cohort).filter(Cohort.id == cohort_id).first()
        if not cohort:
            return None

        cohort_key = f"{cohort.major}-{cohort.grade}"

        results = self.db.query(ScheduleResult).filter(
            ScheduleResult.session_id == session_id
        ).all()

        schedule_data = defaultdict(lambda: defaultdict(list))

        for r in results:
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