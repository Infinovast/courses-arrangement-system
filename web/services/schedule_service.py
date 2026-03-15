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

_time_def_module = _load_algo_module("models.time_definition")
TimePoint = _time_def_module.TimePoint
SEMESTER_WEEKS = _time_def_module.SEMESTER_WEEKS
AFTERNOOM_PERIODS = _time_def_module.AFTERNOOM_PERIODS
EVENING_PERIODS = _time_def_module.EVENING_PERIODS
DAYS = _time_def_module.DAYS
PERIODS = _time_def_module.PERIODS
ALL_WEEKS = _time_def_module.ALL_WEEKS

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
    def __init__(self, db: Session):
        self.db = db

    def _convert_db_to_algo_objects(self, semester: str = "first") -> Tuple:
        db_teachers = self.db.query(Teacher).all()
        db_preferences = self.db.query(TeacherPreference).all()

        pref_dict = defaultdict(lambda: {'pref': [], 'undes': []})
        for pref in db_preferences:
            if pref.preferred_slots:
                pref_dict[pref.teacher_id]['pref'].extend([(s[0], s[1]) for s in pref.preferred_slots])
            if pref.undesired_slots:
                pref_dict[pref.teacher_id]['undes'].extend([(s[0], s[1]) for s in pref.undesired_slots])

        teachers_list = [
            AlgoTeacher(
                id=f"T{t.id:02d}",
                name=t.name,
                is_campus_teacher=t.is_campus_teacher,
                preferred_slots=pref_dict[t.id]['pref'],
                undesired_slots=pref_dict[t.id]['undes']
            )
            for t in db_teachers
        ]
        teacher_id_map = {t.id: f"T{t.id:02d}" for t in db_teachers}
        self._teacher_id_map = teacher_id_map
        self._teacher_db_map = {t.id: t for t in db_teachers}

        db_rooms = self.db.query(Room).all()
        rooms_list = [AlgoRoom(id=f"R{r.id:02d}", name=r.name) for r in db_rooms]

        db_cohorts = self.db.query(Cohort).all()
        cohorts_list = [AlgoCohort(major=c.major, grade=c.grade) for c in db_cohorts]
        cohorts_map = {c.id: f"{c.major}-{c.grade}" for c in db_cohorts}
        algo_cohorts_map = {f"{c.major}-{c.grade}": AlgoCohort(major=c.major, grade=c.grade) for c in db_cohorts}
        self._cohorts_map = cohorts_map
        self._cohorts_db_map = {c.id: c for c in db_cohorts}

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
        self._admin_classes_by_cohort = defaultdict(list)
        for ac in db_admin_classes:
            self._admin_classes_by_cohort[ac.cohort_id].append(ac)

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
                        id=course_id, name=c.name, course_type=c.course_type,
                        theory_hours=c.theory_hours, lab_hours=c.lab_hours,
                        teaching_class_count=teaching_class_count, preferred_pattern=c.preferred_pattern,
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
                    id=course_id, name=c.name, course_type=c.course_type,
                    theory_hours=c.theory_hours, lab_hours=c.lab_hours,
                    teaching_class_count=c.teaching_class_count, preferred_pattern=c.preferred_pattern,
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

        db_fixed = self.db.query(FixedSchedule).filter(
            (FixedSchedule.semester == semester) | (FixedSchedule.semester == "both")
        ).all()
        fixed_schedule = []
        self._fixed_schedule_db = db_fixed

        for f in db_fixed:
            cohort_key = cohorts_map.get(f.cohort_id)
            if not cohort_key: continue

            fixed_schedule.append({
                'cohort_id': cohort_key, 'course_name': f.course_name, 'teacher_name': f.teacher_name,
                'duration': f.duration, 'week': f.weeks, 'start_time': TimePoint(week=None, day=f.day, period=f.period),
                'admin_class_ids': f.admin_class_ids or [], 'db_cohort_id': f.cohort_id
            })

        teacher_preferences = []
        for pref in db_preferences:
            teacher = self.db.query(Teacher).filter(Teacher.id == pref.teacher_id).first()
            course = self.db.query(Course).filter(Course.id == pref.course_id).first() if pref.course_id else None
            if teacher:
                teacher_preferences.append({
                    'teacher_name': teacher.name, 'course_name': course.name if course else None,
                    'preferred_slots': [(s[0], s[1]) for s in (pref.preferred_slots or [])],
                    'undesired_slots': [(s[0], s[1]) for s in (pref.undesired_slots or [])]
                })

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
        session_id = str(uuid.uuid4())[:8]
        session = ScheduleSession(
            session_id=session_id, semester=semester, status="running",
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
                if item.get('admin_class_ids'):
                    sg_ids = set()
                    for ac_id in item['admin_class_ids']:
                        try:
                            ac_id_int = int(ac_id)
                            sg_ids.update(admin_to_subgroup_ids.get(ac_id_int, []))
                        except (ValueError, TypeError): pass
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

            # 【新增：强力硬性排课容量预检截断器】
            campus_teacher_required = defaultdict(int)
            for tc in campus_tcs:
                campus_teacher_required[tc.teacher_name] += (tc.course.theory_hours + tc.course.lab_hours)

            failed_capacity_teachers = []
            teacher_obj_map = {t.name: t for t in teachers_list}

            for t_name, required_hrs in campus_teacher_required.items():
                t_obj = teacher_obj_map.get(t_name)
                if not t_obj: continue

                pref_set = set(t_obj.preferred_slots) if hasattr(t_obj, 'preferred_slots') and t_obj.preferred_slots else set()
                undes_set = set(t_obj.undesired_slots) if hasattr(t_obj, 'undesired_slots') and t_obj.undesired_slots else set()

                # 统计已固定的占用时间槽
                fixed_occupancy = set()
                for item in fixed_schedule:
                    if item.get('teacher_name') == t_name:
                        weeks = item.get('week', [])
                        st = item.get('start_time')
                        dur = item.get('duration', 2)
                        if st and weeks:
                            for w in weeks:
                                for offset in range(dur):
                                    if 1 <= w <= len(ALL_WEEKS) and 1 <= (st.period + offset) <= len(PERIODS):
                                        fixed_occupancy.add((w, st.day, st.period + offset))

                # 遍历核算全局有效可用时间槽位数量
                available_hrs = 0
                for w in SEMESTER_WEEKS:
                    for d in DAYS:
                        for p in PERIODS:
                            is_pref = (d, p) in pref_set or (d, -1) in pref_set
                            is_undes = ((d, p) in undes_set or (d, -1) in undes_set) and not is_pref

                            if is_undes: continue
                            if (w, d, p) in fixed_occupancy: continue

                            available_hrs += 1

                # 若课表上能提供的空闲时间总计小于课程所需的总时数，则纳入容量不足名单
                if available_hrs < required_hrs:
                    failed_capacity_teachers.append(t_name)

            # 如有发生空间溢出，直接终止排课
            if failed_capacity_teachers:
                failed_str = "、".join(failed_capacity_teachers)
                session.status = "failed"
                session.message = f"排课终止！校本部老师【{failed_str}】的排课任务超载，可用的有效排课时间小于其所有的课程所需时间。请调整或减少该老师的不希望时间段、或减轻任课任务后再试。"
                self.db.commit()
                return session_id

            campus_detailed_results = []
            campus_fixed_results = []
            campus_scheduler = None

            if campus_tcs:
                best_detailed, best_fixed, best_failed_tcs = [], [], []
                best_failed_count = len(campus_tcs) + 1
                consecutive_same_failures = 0
                last_failed_count = -1

                for i in range(20):
                    if campus_scheduler is not None: campus_scheduler.cleanup()
                    campus_scheduler = CampusScheduler(campus_tcs, all_subgroups, tc_to_sg_map, teachers_list, rooms_list, fixed_schedule)
                    campus_detailed_results, campus_fixed_results, failed_campus_tcs = campus_scheduler.schedule()
                    current_failed_count = len(failed_campus_tcs)

                    if current_failed_count < best_failed_count:
                        best_detailed, best_fixed, best_failed_count, best_failed_tcs = campus_detailed_results, campus_fixed_results, current_failed_count, failed_campus_tcs
                    if not failed_campus_tcs: break
                    if current_failed_count == last_failed_count:
                        consecutive_same_failures += 1
                        if consecutive_same_failures >= 3: break
                    else:
                        consecutive_same_failures = 1
                    last_failed_count = current_failed_count

                campus_detailed_results, campus_fixed_results = best_detailed, best_fixed

                # 【核心拦截防重复排课】：只将预排中无法塞下的零碎课程下放给 DEAP处理，已成功的完全保留不进 DEAP。
                if best_failed_tcs:
                    other_tcs.extend(best_failed_tcs)

            if campus_scheduler is not None: campus_scheduler.cleanup()

            updated_fixed_schedule = fixed_schedule + campus_fixed_results
            scheduler, pool, penalty_details = None, None, None
            try:
                cpu_count = min(multiprocessing.cpu_count(), 4)
                pool = multiprocessing.Pool(processes=cpu_count)
                scheduler = DeapScheduler(
                    teachers=teachers_list, rooms=rooms_list, subgroups=all_subgroups,
                    teaching_classes=other_tcs, tc_to_sg_map=tc_to_sg_map,
                    fixed_schedule=updated_fixed_schedule, teacher_preferences=teacher_preferences
                )
                success = scheduler.solve(pool)
                ga_results = scheduler.get_results()
                best_fitness = getattr(scheduler, 'best_fitness', 9999)
                penalty_details = scheduler.get_penalty_details()
            finally:
                if pool:
                    pool.close()
                    pool.join()
                if scheduler: scheduler.cleanup()

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
            raise

    def _compute_subgroup_to_admin_mapping(self, all_subgroups: List, cohort_key: str) -> Dict[str, List]:
        """
        【绝对核心修补】：这里将采用与 result_parser.py 里完全镜像的 >=0.5 舍入比例微积分逻辑。
        只有采用这套逻辑，才能保证固定课占用的虚拟子组和输出时所对应的物理行政班完美扣合，杜绝重叠串班！
        """
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

        n_admins = len(admin_classes)
        n_subgroups = len(cohort_subgroups)

        if n_subgroups == 0 or n_admins == 0:
            return {}

        subgroups_per_admin = n_subgroups / n_admins
        subgroup_remaining = {i: 1.0 for i in range(n_subgroups)}
        current_subgroup_index, current_subgroup_used = 0, 0.0

        admin_to_subgroups = {i: [] for i in range(n_admins)}

        for i in range(n_admins):
            assigned = []
            remaining_need = subgroups_per_admin

            while remaining_need > 1e-6 and current_subgroup_index < n_subgroups:
                current_available = subgroup_remaining[current_subgroup_index] - current_subgroup_used
                if current_available >= remaining_need:
                    if remaining_need > 0:
                        assigned.append({'subgroup_idx': current_subgroup_index, 'fraction': remaining_need})
                    current_subgroup_used += remaining_need
                    remaining_need = 0
                else:
                    if current_available > 0:
                        assigned.append({'subgroup_idx': current_subgroup_index, 'fraction': current_available})
                    remaining_need -= current_available
                    current_subgroup_index += 1
                    current_subgroup_used = 0.0

            if n_admins > n_subgroups:
                final_subgroups_idx = [item['subgroup_idx'] for item in assigned]
            else:
                final_subgroups_idx = [item['subgroup_idx'] for item in assigned if item['fraction'] >= 0.5]

            admin_to_subgroups[i] = final_subgroups_idx

        mapping = {sg.id: [] for sg in cohort_subgroups}
        for admin_idx in range(n_admins):
            for sg_idx in admin_to_subgroups[admin_idx]:
                mapping[cohort_subgroups[sg_idx].id].append(admin_classes[admin_idx])

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
            subgroup_ids = [sg.id for sg in tc_to_sg_map.get(tc_id, [])]

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

            week_val, day_val, period_val = (int(tp.week) if tp.week else None, int(tp.day) if tp.day else None, int(tp.period) if tp.period else None)
            duration_val = int(res.get('duration', 2))

            if admin_classes_set:
                for ac in admin_classes_set:
                    self.db.add(ScheduleResult(
                        session_id=session_id, cohort_id=ac.cohort_id, admin_class_id=ac.id, teaching_class_id=tc_id,
                        subgroup_ids=subgroup_ids, course_name=res['course_name'], teacher_name=res['teacher_name'],
                        week=week_val, day=day_val, period=period_val, duration=duration_val,
                        room_name=res.get('room_name'), is_lab=bool(res.get('is_lab', False)),
                        is_combined=bool(res.get('is_combined', False)), is_fixed=False
                    ))
            else:
                self.db.add(ScheduleResult(
                    session_id=session_id, cohort_id=cohort_id, admin_class_id=None, teaching_class_id=tc_id,
                    subgroup_ids=subgroup_ids, course_name=res['course_name'], teacher_name=res['teacher_name'],
                    week=week_val, day=day_val, period=period_val, duration=duration_val,
                    room_name=res.get('room_name'), is_lab=bool(res.get('is_lab', False)),
                    is_combined=bool(res.get('is_combined', False)), is_fixed=False
                ))

        for item in fixed_schedule:
            cohort_id = item.get('db_cohort_id')
            specified_admin_class_ids = item.get('admin_class_ids', [])

            admin_class_db_list = []
            if cohort_id:
                admin_classes_db = self._admin_classes_by_cohort.get(cohort_id, [])
                if specified_admin_class_ids:
                    spec_ids = [int(x) for x in specified_admin_class_ids]
                    admin_class_db_list = [ac for ac in admin_classes_db if ac.id in spec_ids]
                else:
                    admin_class_db_list = admin_classes_db

            for week in item['week']:
                week_val, day_val, period_val, duration_val = (int(week) if week else None, int(item['start_time'].day) if item['start_time'].day else None, int(item['start_time'].period) if item['start_time'].period else None, int(item.get('duration', 2)))
                teaching_class_id = f"FIXED_{item['course_name']}_D{day_val}P{period_val}"

                if admin_class_db_list:
                    for ac in admin_class_db_list:
                        self.db.add(ScheduleResult(
                            session_id=session_id, cohort_id=cohort_id, admin_class_id=ac.id, teaching_class_id=teaching_class_id,
                            course_name=item['course_name'], teacher_name=item['teacher_name'], week=week_val, day=day_val,
                            period=period_val, duration=duration_val, is_fixed=True
                        ))
                else:
                    self.db.add(ScheduleResult(
                        session_id=session_id, cohort_id=cohort_id, admin_class_id=None, teaching_class_id=teaching_class_id,
                        course_name=item['course_name'], teacher_name=item['teacher_name'], week=week_val, day=day_val,
                        period=period_val, duration=duration_val, is_fixed=True
                    ))
        self.db.commit()

    def get_schedule_results(self, session_id: str) -> List[ScheduleResult]:
        return self.db.query(ScheduleResult).filter(ScheduleResult.session_id == session_id).order_by(ScheduleResult.week, ScheduleResult.day, ScheduleResult.period).all()

    def get_latest_session(self, semester: str = None) -> Optional[ScheduleSession]:
        query = self.db.query(ScheduleSession)
        if semester: query = query.filter(ScheduleSession.semester == semester)
        return query.order_by(ScheduleSession.created_at.desc()).first()

    def update_schedule_result(self, result_id: int, week: int = None, day: int = None, period: int = None, room_name: str = None) -> ScheduleResult:
        result = self.db.query(ScheduleResult).filter(ScheduleResult.id == result_id).first()
        if not result: return None
        if week is not None: result.week = week
        if day is not None: result.day = day
        if period is not None: result.period = period
        if room_name is not None: result.room_name = room_name
        self.db.commit()
        self.db.refresh(result)
        return result

    def get_schedule_by_cohort(self, session_id: str, cohort_id: int) -> Dict:
        cohort = self.db.query(Cohort).filter(Cohort.id == cohort_id).first()
        if not cohort: return None
        cohort_key = f"{cohort.major}-{cohort.grade}"
        results = self.db.query(ScheduleResult).filter(ScheduleResult.session_id == session_id).all()
        schedule_data = defaultdict(lambda: defaultdict(list))
        for r in results:
            if cohort_key in r.teaching_class_id or r.is_fixed:
                for d in range(r.duration):
                    period = r.period + d
                    schedule_data[r.day][period].append({
                        'id': r.id, 'course_name': r.course_name, 'teacher_name': r.teacher_name, 'room_name': r.room_name,
                        'week': r.week, 'duration': r.duration, 'is_lab': r.is_lab, 'is_combined': r.is_combined
                    })
        return {'cohort_id': cohort_id, 'cohort_name': cohort_key, 'schedule': dict(schedule_data)}