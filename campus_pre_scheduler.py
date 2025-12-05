import numpy as np
from collections import defaultdict
from itertools import cycle, combinations
import random
from models.time_definition import *


class CampusScheduler:
    MAX_LABS_SIMULTANEOUSLY = 2

    def __init__(self, campus_tcs: list, all_subgroups: list, all_tc_to_sg_map: dict, teachers: list, rooms: list,
                 initial_fixed_schedule: list):
        self.all_tcs_to_schedule = campus_tcs
        self.all_subgroups = all_subgroups
        self.all_tc_to_sg_map = all_tc_to_sg_map
        self.teachers = teachers
        self.rooms = rooms
        self.initial_fixed_schedule = initial_fixed_schedule

        for tc in self.all_tcs_to_schedule:
            tc.subgroups = self.all_tc_to_sg_map.get(tc.id, [])

        self.teacher_to_idx = {t.name: i for i, t in enumerate(teachers)}
        self.subgroup_to_idx = {sg.id: i for i, sg in enumerate(all_subgroups)}
        self.lab_rooms = [r for r in rooms if "机房" in r.name]
        self.room_to_idx = {r.id: i for i, r in enumerate(rooms)}

        self.teacher_grid = np.zeros((len(teachers), len(ALL_WEEKS), len(DAYS), len(PERIODS)), dtype=bool)
        self.subgroup_grid = np.zeros((len(all_subgroups), len(ALL_WEEKS), len(DAYS), len(PERIODS)), dtype=bool)
        self.lab_usage_grid = np.zeros((len(ALL_WEEKS), len(DAYS), len(PERIODS)), dtype=np.int8)
        self.room_grid = np.zeros((len(rooms), len(ALL_WEEKS), len(DAYS), len(PERIODS)), dtype=bool)
        self.cohort_sgs_map = defaultdict(list)
        for sg in self.all_subgroups:
            self.cohort_sgs_map[sg.cohort.id].append(sg)
        self.teacher_schedule = defaultdict(list)

    def _initialize_grids_with_fixed_schedule(self):
        for item in self.initial_fixed_schedule:
            cohort_id = item.get('cohort_id')
            if not cohort_id: continue

            teacher_idx = self.teacher_to_idx.get(item['teacher_name'])
            d_idx, p_start_idx = item['start_time'].day - 1, item['start_time'].period - 1

            # 【关键修复】先标记教师占用，确保无论 relevant_sgs 是否为空都能正确标记
            if teacher_idx is not None:
                for w in item['week']:
                    w_idx = w - 1
                    if not (0 <= w_idx < len(ALL_WEEKS)): continue
                    for p_offset in range(item['duration']):
                        p_idx = p_start_idx + p_offset
                        if 0 <= d_idx < len(DAYS) and 0 <= p_idx < len(PERIODS):
                            self.teacher_grid[teacher_idx, w_idx, d_idx, p_idx] = True

            sgs = self.cohort_sgs_map.get(cohort_id, [])
            tag = item.get('group_tag')
            
            # 【修复】改进子组匹配逻辑：
            # 1. 如果没有 group_tag 或 group_tag 是 'default'，标记所有子组
            # 2. 如果有具体的 group_tag，优先匹配该 tag 的子组
            # 3. 如果没有匹配到任何子组，回退到标记所有子组
            if tag and tag != 'default':
                relevant_sgs = [sg for sg in sgs if sg.fixed_schedule_tag == tag]
                if not relevant_sgs:
                    relevant_sgs = sgs
            else:
                relevant_sgs = sgs

            # 标记子组占用
            for sg in relevant_sgs:
                sg_idx = self.subgroup_to_idx.get(sg.id)
                if sg_idx is None: continue

                for w in item['week']:
                    w_idx = w - 1
                    if not (0 <= w_idx < len(ALL_WEEKS)): continue
                    for p_offset in range(item['duration']):
                        p_idx = p_start_idx + p_offset
                        if 0 <= d_idx < len(DAYS) and 0 <= p_idx < len(PERIODS):
                            self.subgroup_grid[sg_idx, w_idx, d_idx, p_idx] = True

    def schedule(self):
        self._initialize_grids_with_fixed_schedule()

        teacher_hours = defaultdict(int)
        for tc in self.all_tcs_to_schedule:
            main_cohort = tc.subgroups[0].cohort if tc.subgroups else None
            total_hours = tc.course.theory_hours + tc.course.lab_hours
            teacher_hours[tc.teacher_name] += total_hours
            tc.main_cohort_grade = main_cohort.grade if main_cohort else 0

        sorted_tcs = sorted(
            self.all_tcs_to_schedule,
            key=lambda tc: (tc.main_cohort_grade, teacher_hours[tc.teacher_name]),
            reverse=True
        )

        all_tasks = []
        for tc in sorted_tcs:
            reqs = tc.course.get_schedule_requirements()
            phase_weeks = tc.get_effective_weeks()

            # 遍历所有 requirement（支持毕业班课程的多个部分，如 theory_makeup_2h, theory_makeup_3h 等）
            for part_key, req_data in reqs.items():
                req = req_data.copy()
                req['phase_weeks'] = phase_weeks
                # 判断是否为实验课
                is_lab = 'lab' in part_key
                all_tasks.append({'tc': tc, 'req': req, 'is_lab': is_lab, 'id': (tc.id, part_key)})

        successful_placements = []
        placed_task_ids = set()

        preferred_tasks = [t for t in all_tasks if t['tc'].course.preferred_pattern is not None]
        normal_tasks = [t for t in all_tasks if t['tc'].course.preferred_pattern is None]

        self._schedule_preferred_pattern_tasks(preferred_tasks, successful_placements, placed_task_ids)

        tasks_16h = [t for t in normal_tasks if t['req'].get('pattern') in ['single_week', 'double_week']]
        self._schedule_16h_tasks(tasks_16h, successful_placements, placed_task_ids)

        tasks_32h = [t for t in normal_tasks if
                     t['req'].get('pattern') == 'weekly' and t['req']['hours_per_block'] == 2]
        self._schedule_tasks_generic(tasks_32h, [SEMESTER_WEEKS], 2, successful_placements, placed_task_ids,
                                     use_makeup=True)

        tasks_48h_plus = [t for t in normal_tasks if t not in tasks_16h and t not in tasks_32h]
        self._schedule_48h_plus_tasks(tasks_48h_plus, successful_placements, placed_task_ids)

        all_tc_ids = {tc.id for tc in self.all_tcs_to_schedule}
        successful_tc_ids = {key[0] for key in placed_task_ids}
        failed_tc_ids = all_tc_ids - successful_tc_ids
        failed_tcs = [tc for tc in self.all_tcs_to_schedule if tc.id in failed_tc_ids]

        detailed_results, fixed_results = self._format_results(successful_placements)
        return detailed_results, fixed_results, failed_tcs

    def _schedule_preferred_pattern_tasks(self, tasks, successful_placements, placed_task_ids):
        week_pattern_map = {
            'weeks_1_to_14': WEEKS_1_TO_14, 'weeks_5_to_15': WEEKS_5_TO_15, 'weeks_5_to_16': WEEKS_5_TO_16,
            'weeks_5_to_17': WEEKS_5_TO_17, 'weeks_6_to_17': WEEKS_6_TO_17,
            'weeks_1_to_8': WEEKS_1_TO_8, 'weeks_9_to_16': WEEKS_9_TO_16,
            'weeks_16_to_17': WEEKS_16_TO_17,
            # 毕业班特殊模式
            'graduation_48h': WEEKS_5_TO_16,  # 48学时: 第5-16周
            'graduation_32h_main': WEEKS_5_TO_15,  # 32学时主体: 第5-15周
        }
        for task in tasks:
            pattern = task['tc'].course.preferred_pattern
            weeks_options = week_pattern_map.get(pattern, [])
            phase_weeks = task['req'].get('phase_weeks', [])

            # 关键修复：取模式周次和阶段周次的交集
            if phase_weeks:
                phase_week_set = set(phase_weeks)
                weeks_options = [w for w in weeks_options if w in phase_week_set]

            if weeks_options:
                duration = task['req'].get('hours_per_block', 2)
                self._try_place_task(task, [weeks_options], duration, successful_placements, placed_task_ids)

    def _schedule_tasks_generic(self, tasks, weeks_options, duration, successful_placements, placed_task_ids,
                                use_makeup=False, **kwargs):
        for task in tasks:
            if task['id'] in placed_task_ids: continue

            phase_weeks = task['req'].get('phase_weeks', [])
            filtered_weeks = []
            for weeks in weeks_options:
                if phase_weeks:
                    phase_week_set = set(phase_weeks)
                    filtered = [w for w in weeks if w in phase_week_set]
                    if filtered:
                        filtered_weeks.append(filtered)
                else:
                    filtered_weeks.append(weeks)
            if not filtered_weeks:
                continue

            if self._try_place_task(task, filtered_weeks, duration, successful_placements, placed_task_ids, **kwargs):
                continue

            if use_makeup:
                placements_with_makeup = self._find_fit_with_makeup(task, duration, filtered_weeks[0], **kwargs)
                if placements_with_makeup:
                    for p in placements_with_makeup:
                        self._commit_placement(p)
                        successful_placements.append(p)
                    placed_task_ids.add(task['id'])
                    continue

    def _schedule_16h_tasks(self, tasks, successful_placements, placed_task_ids):
        sg_week_cycle = defaultdict(lambda: cycle([SINGLE_WEEKS, DOUBLE_WEEKS]))
        sg_to_tasks = defaultdict(list)
        for task in tasks:
            if task['tc'].subgroups:
                sg_id = frozenset(sg.id for sg in task['tc'].subgroups)
                sg_to_tasks[sg_id].append(task)

        remaining_tasks = []
        for sg_id, task_list in sg_to_tasks.items():
            for task in task_list:
                if task['id'] in placed_task_ids: continue

                phase_weeks = task['req'].get('phase_weeks', [])
                weeks = next(sg_week_cycle[sg_id])

                # 关键修复：过滤单双周中的阶段周次
                if phase_weeks:
                    phase_week_set = set(phase_weeks)
                    weeks = [w for w in weeks if w in phase_week_set]
                if not weeks:
                    remaining_tasks.append(task)
                    continue

                if not self._try_place_task(task, [weeks], 2, successful_placements, placed_task_ids,
                                            prioritize_morning_afternoon=True):
                    remaining_tasks.append(task)

        final_remaining_tasks = []
        for task in remaining_tasks:
            if task['id'] in placed_task_ids: continue
            phase_weeks = task['req'].get('phase_weeks', [])
            candidate_weeks = []
            for week_set in [SINGLE_WEEKS, DOUBLE_WEEKS]:
                if phase_weeks:
                    phase_week_set = set(phase_weeks)
                    filtered = [w for w in week_set if w in phase_week_set]
                    if filtered:
                        candidate_weeks.append(filtered)
                else:
                    candidate_weeks.append(week_set)
            if not candidate_weeks:
                final_remaining_tasks.append(task)
                continue
            if not self._try_place_task(task, candidate_weeks, 2, successful_placements, placed_task_ids,
                                        prioritize_morning_afternoon=True):
                final_remaining_tasks.append(task)

        if final_remaining_tasks:
            self._schedule_16h_alternating(final_remaining_tasks, successful_placements, placed_task_ids)

    def _schedule_16h_alternating(self, tasks, successful_placements, placed_task_ids):
        for task in tasks:
            if task['id'] in placed_task_ids: continue

            slots = self._get_valid_slots(2, teacher_name=task['tc'].teacher_name, prioritize_morning_afternoon=True)
            phase_weeks = task['req'].get('phase_weeks', [])
            phase_week_set = set(phase_weeks) if phase_weeks else set(ALL_WEEKS)

            for slot in slots:
                if task['id'] in placed_task_ids: break

                # 过滤单周中的阶段周次
                single_weeks_filtered = [w for w in SINGLE_WEEKS if w in phase_week_set]
                conflicts_single = self._check_conflict_vectorized(task, slot, single_weeks_filtered)
                if len(conflicts_single) == len(single_weeks_filtered):
                    double_weeks_filtered = [w for w in DOUBLE_WEEKS if w in phase_week_set]
                    conflicts_double = self._check_conflict_vectorized(task, slot, double_weeks_filtered)
                    if not conflicts_double:
                        room_name = self._find_available_lab_room(task, slot, double_weeks_filtered)
                        if task['is_lab'] and room_name is None: continue

                        p = {'task': task, 'slot': slot, 'weeks': double_weeks_filtered, 'duration': 2,
                             'room_name': room_name}
                        self._commit_placement(p)
                        successful_placements.append(p)
                        placed_task_ids.add(task['id'])
                        continue

                # 过滤双周中的阶段周次
                double_weeks_filtered = [w for w in DOUBLE_WEEKS if w in phase_week_set]
                conflicts_double = self._check_conflict_vectorized(task, slot, double_weeks_filtered)
                if len(conflicts_double) == len(double_weeks_filtered):
                    single_weeks_filtered = [w for w in SINGLE_WEEKS if w in phase_week_set]
                    conflicts_single = self._check_conflict_vectorized(task, slot, single_weeks_filtered)
                    if not conflicts_single:
                        room_name = self._find_available_lab_room(task, slot, single_weeks_filtered)
                        if task['is_lab'] and room_name is None: continue

                        p = {'task': task, 'slot': slot, 'weeks': single_weeks_filtered, 'duration': 2,
                             'room_name': room_name}
                        self._commit_placement(p)
                        successful_placements.append(p)
                        placed_task_ids.add(task['id'])
                        continue

    def _schedule_48h_plus_tasks(self, tasks, successful_placements, placed_task_ids):
        # 毕业班课程周次模式映射
        graduation_week_pattern_map = {
            'graduation_48h': WEEKS_5_TO_16,
            'graduation_32h_main': WEEKS_5_TO_15,
            'weeks_16_to_17': WEEKS_16_TO_17,
        }
        
        tasks_to_process = list(tasks)

        for task in tasks_to_process:
            if task['id'] in placed_task_ids:
                continue

            duration = task['req']['hours_per_block']
            phase_weeks = task['req'].get('phase_weeks', [])
            pattern = task['req'].get('pattern', 'weekly')
            weekly_sessions = task['req'].get('weekly_sessions', 1)
            
            # 根据 pattern 选择基础周次
            base_weeks = graduation_week_pattern_map.get(pattern, SEMESTER_WEEKS)

            # 关键修复：过滤48学时课程的阶段周次
            if phase_weeks:
                phase_week_set = set(phase_weeks)
                base_weeks = [w for w in base_weeks if w in phase_week_set]
            if not base_weeks:
                continue

            # 毕业班48学时课程: 每周2次课
            if weekly_sessions == 2:
                if self._try_place_task_multiple_sessions(task, base_weeks, duration, 2, successful_placements, placed_task_ids):
                    continue
            elif self._try_place_task(task, [base_weeks], duration, successful_placements,
                                    placed_task_ids):
                continue

            placements_with_makeup = self._find_fit_with_makeup(task, duration, base_weeks)
            if placements_with_makeup:
                for p in placements_with_makeup:
                    self._commit_placement(p)
                    successful_placements.append(p)
                placed_task_ids.add(task['id'])
                continue

        all_failed_tasks = [t for t in tasks_to_process if t['id'] not in placed_task_ids]

        failed_48h_tasks_to_split = []
        for t in all_failed_tasks:
            total_hours = t['tc'].course.theory_hours if not t['is_lab'] else t['tc'].course.lab_hours
            if total_hours == 48 and t['req'].get('hours_per_block') == 3:
                failed_48h_tasks_to_split.append(t)

        if failed_48h_tasks_to_split:
            self._schedule_48h_dynamic_split(failed_48h_tasks_to_split, successful_placements,
                                             placed_task_ids)

    def _schedule_48h_dynamic_split(self, tasks, successful_placements, placed_task_ids):
        for task in tasks:
            if task['id'] in placed_task_ids:
                continue

            phase_weeks = task['req'].get('phase_weeks', [])
            phase_week_set = set(phase_weeks) if phase_weeks else set(ALL_WEEKS)
            single_week_filtered = [w for w in SINGLE_WEEKS if w in phase_week_set]
            double_week_filtered = [w for w in DOUBLE_WEEKS if w in phase_week_set]
            if not single_week_filtered and not double_week_filtered:
                continue

            single_week_density = self._calculate_schedule_density(task, single_week_filtered)
            double_week_density = self._calculate_schedule_density(task, double_week_filtered)

            patterns_to_try = [(2, 1), (1, 2)]
            if single_week_density > double_week_density * 1.1:
                patterns_to_try = [(1, 2), (2, 1)]
            elif double_week_density > single_week_density * 1.1:
                patterns_to_try = [(2, 1), (1, 2)]
            else:
                random.shuffle(patterns_to_try)

            for pattern in patterns_to_try:
                placements = self._try_place_48h_interleaved_randomized(task, pattern, phase_week_set)
                if placements:
                    for p in placements:
                        self._commit_placement(p)
                        successful_placements.append(p)
                    placed_task_ids.add(task['id'])
                    break

    def _try_place_48h_interleaved_randomized(self, task, pattern, phase_week_set):
        sessions_single, sessions_double = pattern

        weeks_for_2_sessions = SINGLE_WEEKS if sessions_single == 2 else DOUBLE_WEEKS
        weeks_for_1_session = DOUBLE_WEEKS if sessions_double == 1 else SINGLE_WEEKS

        # 过滤阶段周次
        weeks_for_2_filtered = [w for w in weeks_for_2_sessions if w in phase_week_set]
        weeks_for_1_filtered = [w for w in weeks_for_1_session if w in phase_week_set]
        if not weeks_for_2_filtered or not weeks_for_1_filtered:
            return []

        slots = self._get_valid_slots(duration=2, teacher_name=task['tc'].teacher_name)
        random.shuffle(slots)

        for s1, s2 in combinations(slots, 2):
            if self._check_conflict_vectorized(task, s1, weeks_for_2_filtered) or \
                    self._check_conflict_vectorized(task, s2, weeks_for_2_filtered):
                continue

            slot_for_1_session = None
            if not self._check_conflict_vectorized(task, s1, weeks_for_1_filtered):
                slot_for_1_session = s1
            elif not self._check_conflict_vectorized(task, s2, weeks_for_1_filtered):
                slot_for_1_session = s2

            if slot_for_1_session:
                placements_to_commit = []

                room_1 = self._find_available_lab_room(task, slot_for_1_session, weeks_for_1_filtered)
                if task['is_lab'] and room_1 is None: continue
                placements_to_commit.append(
                    {'task': task, 'slot': slot_for_1_session, 'weeks': weeks_for_1_filtered, 'duration': 2,
                     'room_name': room_1}
                )

                room_2a = self._find_available_lab_room(task, s1, weeks_for_2_filtered)
                if task['is_lab'] and room_2a is None: continue
                placements_to_commit.append(
                    {'task': task, 'slot': s1, 'weeks': weeks_for_2_filtered, 'duration': 2, 'room_name': room_2a}
                )

                room_2b = self._find_available_lab_room(task, s2, weeks_for_2_filtered)
                if task['is_lab'] and room_2b is None: continue
                placements_to_commit.append(
                    {'task': task, 'slot': s2, 'weeks': weeks_for_2_filtered, 'duration': 2, 'room_name': room_2b}
                )

                return placements_to_commit

        return []

    # 以下方法保持不变
    def _calculate_schedule_density(self, task, weeks: List[int]) -> int:
        if not weeks:
            return 0

        tc = task['tc']
        teacher_idx = self.teacher_to_idx.get(tc.teacher_name)
        sg_indices = [self.subgroup_to_idx.get(sg.id) for sg in tc.subgroups if sg.id in self.subgroup_to_idx]

        w_indices = [w - 1 for w in weeks]
        total_occupied_slots = 0

        campus_time_slices = []
        for day in [1, 2]:
            d_idx = day - 1
            for period in range(1, len(PERIODS) + 1):
                campus_time_slices.append((d_idx, period - 1))

        d_idx_wed = 2
        for period in [1, 2, 3, 4, 5]:
            campus_time_slices.append((d_idx_wed, period - 1))

        if teacher_idx is not None:
            for d_idx, p_idx in campus_time_slices:
                teacher_slice = self.teacher_grid[teacher_idx, w_indices, d_idx, p_idx]
                total_occupied_slots += np.sum(teacher_slice)

        if sg_indices:
            for d_idx, p_idx in campus_time_slices:
                subgroup_slice = self.subgroup_grid[sg_indices, :, d_idx, p_idx][:, w_indices]
                total_occupied_slots += np.sum(subgroup_slice)

        return total_occupied_slots

    def _check_interleaved_pattern_fit(self, task, session_count_pattern, s1, s2, temp_grids):
        new_placements = []

        for i in range(5):
            cycle_start_week = i * 3 + 1
            for j in range(3):
                num_sessions = session_count_pattern[j]
                target_week = cycle_start_week + j

                slots_to_use = [s1, s2] if num_sessions == 2 else ([s1] if num_sessions == 1 else [])

                for slot in slots_to_use:
                    if self._check_conflict_on_temp_grid(task, slot, [target_week], *temp_grids):
                        return False, []

        if self._check_conflict_on_temp_grid(task, s1, [16], *temp_grids):
            return False, []

        s3_slots = self._get_valid_slots(3, is_makeup=True, teacher_name=task['tc'].teacher_name)
        found_makeup_slots = []

        makeup_temp_grids = [grid.copy() for grid in temp_grids]

        for s3 in s3_slots:
            if not self._check_conflict_on_temp_grid(task, s3, [17], *makeup_temp_grids):
                found_makeup_slots.append(s3)
                self._commit_to_temp_grid({'task': task, 'slot': s3, 'weeks': [17]}, *makeup_temp_grids)
                if len(found_makeup_slots) == 2:
                    break

        if len(found_makeup_slots) < 2:
            return False, []

        for i in range(5):
            cycle_start_week = i * 3 + 1
            for j in range(3):
                num_sessions = session_count_pattern[j]
                target_week = cycle_start_week + j
                slots_to_use = [s1, s2] if num_sessions == 2 else ([s1] if num_sessions == 1 else [])
                for slot in slots_to_use:
                    room = self._find_available_lab_room(task, slot, [target_week])
                    if task['is_lab'] and room is None: return False, []
                    new_placements.append(
                        {'task': task, 'slot': slot, 'weeks': [target_week], 'duration': 2, 'room_name': room})

        room_16 = self._find_available_lab_room(task, s1, [16])
        if task['is_lab'] and room_16 is None: return False, []
        new_placements.append({'task': task, 'slot': s1, 'weeks': [16], 'duration': 2, 'room_name': room_16})

        for s3 in found_makeup_slots:
            room_17 = self._find_available_lab_room(task, s3, [17])
            if task['is_lab'] and room_17 is None: return False, []
            new_placements.append({'task': task, 'slot': s3, 'weeks': [17], 'duration': 3, 'room_name': room_17})

        return True, new_placements

    def _try_place_task(self, task, weeks_options, duration, successful_placements, placed_task_ids, **kwargs):
        if task['id'] in placed_task_ids: return True

        for weeks in weeks_options:
            if not weeks:
                continue
            slots = self._get_valid_slots(duration, teacher_name=task['tc'].teacher_name, **kwargs)
            for slot in slots:
                if not self._check_conflict_vectorized(task, slot, weeks):
                    room_name = self._find_available_lab_room(task, slot, weeks)
                    if task['is_lab'] and room_name is None:
                        continue

                    p = {'task': task, 'slot': slot, 'weeks': weeks, 'duration': duration, 'room_name': room_name}
                    self._commit_placement(p)
                    successful_placements.append(p)
                    placed_task_ids.add(task['id'])
                    return True
        return False

    def _try_place_task_multiple_sessions(self, task, weeks, duration, sessions_per_week, successful_placements, placed_task_ids):
        """处理每周多次课的情况（如毕业班48学时课程，每周2次）"""
        if task['id'] in placed_task_ids:
            return True
        
        if not weeks:
            return False
        
        slots = self._get_valid_slots(duration, teacher_name=task['tc'].teacher_name)
        
        # 尝试找到sessions_per_week个不冲突的时间槽
        from itertools import combinations
        for slot_combo in combinations(slots, sessions_per_week):
            all_valid = True
            placements_to_commit = []
            
            # 检查所有时间槽是否都不冲突
            for slot in slot_combo:
                conflicts = self._check_conflict_vectorized(task, slot, weeks)
                if conflicts:
                    all_valid = False
                    break
                
                room_name = self._find_available_lab_room(task, slot, weeks)
                if task['is_lab'] and room_name is None:
                    all_valid = False
                    break
                
                placements_to_commit.append({
                    'task': task, 
                    'slot': slot, 
                    'weeks': weeks, 
                    'duration': duration, 
                    'room_name': room_name
                })
            
            if all_valid and len(placements_to_commit) == sessions_per_week:
                # 提交所有安排
                for p in placements_to_commit:
                    self._commit_placement(p)
                    successful_placements.append(p)
                placed_task_ids.add(task['id'])
                return True
        
        return False

    def _find_fit_with_makeup(self, task, duration, target_weeks, **kwargs):
        possible_slots = self._get_valid_slots(duration, is_makeup=False, teacher_name=task['tc'].teacher_name,
                                               **kwargs)

        for slot in possible_slots:
            conflicting_weeks = self._check_conflict_vectorized(task, slot, target_weeks)

            if 0 < len(conflicting_weeks) <= 2:
                valid_weeks = [w for w in target_weeks if w not in conflicting_weeks]

                makeup_placements = []
                temp_grids = (self.teacher_grid.copy(), self.subgroup_grid.copy(), self.lab_usage_grid.copy(),
                              self.room_grid.copy())
                can_find_all_makeups = True

                for _ in range(len(conflicting_weeks)):
                    makeup_p = self._find_makeup_slot(task, duration, temp_grids)
                    if makeup_p:
                        makeup_placements.append(makeup_p)
                        self._commit_to_temp_grid(makeup_p, *temp_grids)
                    else:
                        can_find_all_makeups = False
                        break

                if can_find_all_makeups:
                    room_name = self._find_available_lab_room(task, slot, valid_weeks)
                    if task['is_lab'] and room_name is None: continue

                    main_placement = {'task': task, 'slot': slot, 'weeks': valid_weeks, 'duration': duration,
                                      'room_name': room_name}
                    return [main_placement] + makeup_placements
        return None

    def _find_makeup_slot(self, task, duration, temp_grids):
        slots = self._get_valid_slots(duration, is_makeup=True, teacher_name=task['tc'].teacher_name)

        for slot in slots:
            if self._check_conflict_on_temp_grid(task, slot, [FINAL_REVIEW_WEEK], *temp_grids):
                continue

            if task['is_lab']:
                temp_room_grid = temp_grids[3]
                d_idx, p_start_idx = slot.day - 1, slot.period - 1
                w_idx = FINAL_REVIEW_WEEK - 1
                p_indices = list(range(p_start_idx, p_start_idx + slot.duration))

                found_room_name = None
                for room in self.lab_rooms:
                    room_idx = self.room_to_idx[room.id]
                    if not np.any(temp_room_grid[room_idx, w_idx, d_idx, p_indices]):
                        found_room_name = room.name
                        break

                if found_room_name:
                    return {'task': task, 'slot': slot, 'weeks': [FINAL_REVIEW_WEEK], 'duration': duration,
                            'room_name': found_room_name}
            else:
                return {'task': task, 'slot': slot, 'weeks': [FINAL_REVIEW_WEEK], 'duration': duration,
                        'room_name': "N/A"}

        return None

    def _get_valid_slots(self, duration, is_makeup=False, teacher_name=None, **kwargs):
        slots = []
        if is_makeup:
            valid_starts = VALID_STARTS_MAKEUP_2H if duration == 2 else VALID_STARTS_MAKEUP_3H
            for day, period in CAMPUS_MAKEUP_WINDOW:
                if period in valid_starts: slots.append(TimeSlot(day, period, duration))
        else:
            if duration == 2:
                for day, period in CAMPUS_TIME_WINDOW:
                    if day in [1, 2] and period in VALID_STARTS_MON_TUE_2H:
                        slots.append(TimeSlot(day, period, duration))
                    elif day == 3 and period in VALID_STARTS_WED_2H:
                        slots.append(TimeSlot(day, period, duration))
            elif duration == 3:
                for day, period in CAMPUS_TIME_WINDOW:
                    if day in [1, 2] and period in VALID_STARTS_MON_TUE_3H:
                        slots.append(TimeSlot(day, period, duration))
                    elif day == 3 and period in VALID_STARTS_WED_3H:
                        slots.append(TimeSlot(day, period, duration))
        teacher_used_slots = {s for s, w in self.teacher_schedule.get(teacher_name, [])}

        def sort_key(slot):
            is_teacher_preferred = slot in teacher_used_slots
            prioritize_evening = kwargs.get('prioritize_evening', False)
            is_evening = slot.period in EVENING_PERIODS
            return (not is_teacher_preferred, not is_evening if prioritize_evening else is_evening, slot.day,
                    slot.period)

        return sorted(list(set(slots)), key=sort_key)

    def _check_conflict_vectorized(self, task, slot: TimeSlot, weeks: List[int]):
        tc, is_lab = task['tc'], task['is_lab']
        if not tc.subgroups: return weeks
        teacher_idx = self.teacher_to_idx.get(tc.teacher_name)
        sg_indices = [self.subgroup_to_idx.get(sg.id) for sg in tc.subgroups]
        d_idx, p_start_idx = slot.day - 1, slot.period - 1
        if not weeks: return []
        w_indices = [w - 1 for w in weeks]
        p_indices = list(range(p_start_idx, p_start_idx + slot.duration))
        all_conflicting_weeks = set()
        if teacher_idx is not None:
            teacher_slice = self.teacher_grid[teacher_idx, w_indices, d_idx, :][:, p_indices]
            conflict_per_week_mask = np.any(teacher_slice, axis=1)
            for i, has_conflict in enumerate(conflict_per_week_mask):
                if has_conflict: all_conflicting_weeks.add(weeks[i])
        if sg_indices:
            for i, w_idx in enumerate(w_indices):
                week_slice = self.subgroup_grid[sg_indices, w_idx, d_idx, :][:, p_indices]
                if np.any(week_slice): all_conflicting_weeks.add(weeks[i])
        return sorted(list(all_conflicting_weeks))

    def _check_conflict_on_temp_grid(self, task, slot, weeks, teacher_grid, subgroup_grid, lab_usage_grid,
                                     room_grid):
        tc, is_lab = task['tc'], task['is_lab']
        teacher_idx = self.teacher_to_idx.get(tc.teacher_name)
        sg_indices = [self.subgroup_to_idx.get(sg.id) for sg in tc.subgroups if sg.id in self.subgroup_to_idx]
        d_idx, p_start_idx = slot.day - 1, slot.period - 1
        w_indices = [w - 1 for w in weeks if 1 <= w <= len(ALL_WEEKS)]
        if not w_indices: return False
        p_indices = list(range(p_start_idx, p_start_idx + slot.duration))

        if teacher_idx is not None:
            if np.any(teacher_grid[np.ix_([teacher_idx], w_indices, [d_idx], p_indices)]):
                return True

        if sg_indices:
            if np.any(subgroup_grid[np.ix_(sg_indices, w_indices, [d_idx], p_indices)]):
                return True

        if is_lab:
            if np.any(lab_usage_grid[np.ix_(w_indices, [d_idx], p_indices)] >= self.MAX_LABS_SIMULTANEOUSLY):
                return True

            can_find_room = False
            for room in self.lab_rooms:
                room_idx = self.room_to_idx.get(room.id)
                if room_idx is not None:
                    if not np.any(room_grid[np.ix_([room_idx], w_indices, [d_idx], p_indices)]):
                        can_find_room = True
                        break
            if not can_find_room:
                return True

        return False

    def _find_available_lab_room(self, task, slot, weeks):
        if not task['is_lab']:
            return "N/A"

        if not weeks:
            return None

        d_idx, p_start_idx = slot.day - 1, slot.period - 1
        w_indices = [w - 1 for w in weeks]
        p_indices = list(range(p_start_idx, p_start_idx + slot.duration))

        lab_usage_slice = self.lab_usage_grid[np.ix_(w_indices, [d_idx], p_indices)]
        if np.any(lab_usage_slice >= self.MAX_LABS_SIMULTANEOUSLY):
            return None

        shuffled_lab_rooms = list(self.lab_rooms)
        random.shuffle(shuffled_lab_rooms)
        for room in shuffled_lab_rooms:
            room_idx = self.room_to_idx.get(room.id)
            if room_idx is None:
                continue
            room_slice = self.room_grid[np.ix_([room_idx], w_indices, [d_idx], p_indices)]
            if not np.any(room_slice):
                return room.name

        return None

    def _commit_placement(self, p):
        self._commit_to_grid(p, self.teacher_grid, self.subgroup_grid, self.lab_usage_grid)
        if self.teacher_to_idx.get(p['task']['tc'].teacher_name) is not None: self.teacher_schedule[
            p['task']['tc'].teacher_name].append((p['slot'], p['weeks']))

    def _commit_to_grid(self, p, teacher_grid, subgroup_grid, lab_grid):
        task, slot, weeks, room_name = p['task'], p['slot'], p['weeks'], p['room_name']
        tc, is_lab = task['tc'], task['is_lab']
        teacher_idx = self.teacher_to_idx.get(tc.teacher_name)
        sg_indices = [self.subgroup_to_idx.get(sg.id) for sg in tc.subgroups]
        d_idx, p_start_idx = slot.day - 1, slot.period - 1
        w_indices = [w - 1 for w in weeks]
        p_indices = list(range(p_start_idx, p_start_idx + slot.duration))

        if teacher_idx is not None: teacher_grid[np.ix_([teacher_idx], w_indices, [d_idx], p_indices)] = True
        if sg_indices: subgroup_grid[np.ix_(sg_indices, w_indices, [d_idx], p_indices)] = True

        if is_lab:
            lab_grid[np.ix_(w_indices, [d_idx], p_indices)] += 1

            room = next((r for r in self.rooms if r.name == room_name), None)
            if room:
                room_idx = self.room_to_idx.get(room.id)
                if room_idx is not None:
                    self.room_grid[np.ix_([room_idx], w_indices, [d_idx], p_indices)] = True

    def _commit_to_temp_grid(self, p, teacher_grid, subgroup_grid, lab_usage_grid, room_grid):
        task, slot, weeks, room_name = p['task'], p['slot'], p['weeks'], p['room_name']
        tc, is_lab = task['tc'], task['is_lab']
        teacher_idx = self.teacher_to_idx.get(tc.teacher_name)
        sg_indices = [self.subgroup_to_idx.get(sg.id) for sg in tc.subgroups if sg.id in self.subgroup_to_idx]
        d_idx, p_start_idx = slot.day - 1, slot.period - 1
        w_indices = [w - 1 for w in weeks]
        p_indices = list(range(p_start_idx, p_start_idx + slot.duration))

        if teacher_idx is not None: teacher_grid[np.ix_([teacher_idx], w_indices, [d_idx], p_indices)] = True
        if sg_indices: subgroup_grid[np.ix_(sg_indices, w_indices, [d_idx], p_indices)] = True

        if is_lab:
            lab_usage_grid[np.ix_(w_indices, [d_idx], p_indices)] += 1
            room = next((r for r in self.rooms if r.name == room_name), None)
            if room:
                room_idx = self.room_to_idx.get(room.id)
                if room_idx is not None:
                    room_grid[np.ix_([room_idx], w_indices, [d_idx], p_indices)] = True

    def _format_results(self, placements):
        detailed, fixed = [], []
        agg = defaultdict(list)
        for p in placements: key = (p['task']['tc'].id, p['task']['is_lab'], p['slot'], p.get('room_name')); agg[
            key].extend(p['weeks'])
        for key, weeks_list in agg.items():
            tc_id, is_lab, slot, room_name = key
            tc = next((p['task']['tc'] for p in placements if p['task']['tc'].id == tc_id), None)
            if not tc: continue
            # 转numpy类型为Python原生类型
            all_weeks = sorted([int(w) for w in set(weeks_list)])
            if not all_weeks: continue
            day_val = int(slot.day)
            period_val = int(slot.period)
            duration_val = int(slot.duration)
            for sg in tc.subgroups:
                fixed.append(
                    {"cohort_id": sg.cohort.id, "group_tag": sg.fixed_schedule_tag, "course_name": tc.course.name,
                     "teacher_name": tc.teacher_name, "duration": duration_val, "week": all_weeks,
                     "start_time": TimePoint(week=None, day=day_val, period=period_val), "is_lab": bool(is_lab),
                     "room_name": room_name if is_lab else None})
            for w in all_weeks:
                detailed.append(
                    {"teaching_class_id": tc.id, "course_name": tc.course.name, "teacher_name": tc.teacher_name,
                     "time_point": TimePoint(week=w, day=day_val, period=period_val), "duration": duration_val,
                     "room_name": room_name if room_name != "N/A" else None, "is_lab": bool(is_lab),
                     "is_combined": bool(tc.is_combined)})
        return detailed, fixed
    
    def cleanup(self):
        """清理资源，释放内存"""
        # 清理大型 numpy 数组
        if hasattr(self, 'teacher_grid'):
            del self.teacher_grid
        if hasattr(self, 'subgroup_grid'):
            del self.subgroup_grid
        if hasattr(self, 'lab_usage_grid'):
            del self.lab_usage_grid
        if hasattr(self, 'room_grid'):
            del self.room_grid
        # 清理其他引用
        if hasattr(self, 'all_tcs_to_schedule'):
            self.all_tcs_to_schedule.clear()
        if hasattr(self, 'teacher_schedule'):
            self.teacher_schedule.clear()
        if hasattr(self, 'cohort_sgs_map'):
            self.cohort_sgs_map.clear()
        # 强制垃圾回收
        import gc
        gc.collect()
