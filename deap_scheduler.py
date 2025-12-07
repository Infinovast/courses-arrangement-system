# deap_scheduler.py (修复约束范围+权重问题)

import random
from collections import defaultdict
import numpy as np
from deap import base, creator, tools, algorithms
from functools import partial
import copy
from models.time_definition import *
import numba


@numba.jit(nopython=True, fastmath=True)
def calculate_fitness_jit(
        individual,
        tasks_meta, task_to_sg_indices_flat, task_to_sg_pointers,
        # 解码映射
        flat_slot_decode_map, shape_slot_decode_map,
        # 周次数据
        all_weeks_patterns_flat, all_weeks_patterns_pointers,
        # 阶段周次数据
        task_phase_weeks_flat, task_phase_weeks_pointers,
        # 课程分组数据（修复：改为 (course_id + tc_id) 分组）
        course_group_ids,
        num_course_groups,
        # 偏好与约束掩码
        flat_undesired_masks, shape_undesired_masks,
        flat_preferred_masks, shape_preferred_masks,
        # 固定的资源占用网格
        flat_fixed_teacher_grid, shape_fixed_teacher_grid,
        flat_fixed_subgroup_grid, shape_fixed_subgroup_grid,
        flat_fixed_room_grid, shape_fixed_room_grid,
        flat_fixed_lab_usage_grid, shape_fixed_lab_usage_grid,
        num_task_groups,
        max_labs_simultaneously,
        current_generation,
        max_generations,
        semester_weeks_len
):
    """计算惩罚分数 - 修复约束范围+权重问题"""
    # 1. 重建多维数组（保持不变）
    slot_decode_map = flat_slot_decode_map.reshape(shape_slot_decode_map)
    undesired_masks = flat_undesired_masks.reshape(shape_undesired_masks)
    preferred_masks = flat_preferred_masks.reshape(shape_preferred_masks)
    teacher_grid = flat_fixed_teacher_grid.reshape(shape_fixed_teacher_grid).copy()
    subgroup_grid = flat_fixed_subgroup_grid.reshape(shape_fixed_subgroup_grid).copy()
    room_grid = flat_fixed_room_grid.reshape(shape_fixed_room_grid).copy()
    lab_usage_grid = flat_fixed_lab_usage_grid.reshape(shape_fixed_lab_usage_grid).copy()
    day_course_counter = np.zeros((subgroup_grid.shape[0], semester_weeks_len, subgroup_grid.shape[2], num_task_groups),
                                  dtype=np.int8)

    # 新增：用数组记录课程时间点（保持不变）
    max_phases_per_course = 10
    course_time_array = np.full((num_course_groups, 1 + 1 + 2 * max_phases_per_course), -1, dtype=np.int32)

    # 2. 填充资源网格 + 记录课程时间点（保持不变）
    for i in range(len(individual)):
        gene = individual[i]
        t_idx, is_lab, duration, task_group_id, _, _ = tasks_meta[i]
        start_ptr, end_ptr = task_to_sg_pointers[i]
        sg_indices = task_to_sg_indices_flat[start_ptr:end_ptr]
        course_group_id = course_group_ids[i]

        week_pattern_idx, d_idx, p_idx, r_idx = slot_decode_map[gene]

        # 步骤1：获取模式对应的原始周次
        weeks_start_ptr, weeks_end_ptr = all_weeks_patterns_pointers[week_pattern_idx]
        raw_weeks = all_weeks_patterns_flat[weeks_start_ptr:weeks_end_ptr]

        # 步骤2：获取该任务的阶段周次
        phase_start_ptr, phase_end_ptr = task_phase_weeks_pointers[i]
        if phase_start_ptr == 0 and phase_end_ptr == 0:
            phase_weeks = task_phase_weeks_flat[0:0]
        else:
            phase_weeks = task_phase_weeks_flat[phase_start_ptr:phase_end_ptr]

        # 步骤3：计算有效周次
        effective_weeks = raw_weeks.copy()
        if phase_weeks.size > 0:
            mask = np.zeros(raw_weeks.size, dtype=np.bool_)
            for j in range(raw_weeks.size):
                for k in range(phase_weeks.size):
                    if raw_weeks[j] == phase_weeks[k]:
                        mask[j] = True
                        break
            effective_weeks = raw_weeks[mask]

        # 步骤4：只在有效周次内填充网格
        for w_idx in effective_weeks:
            for p_offset in range(duration):
                current_p = p_idx + p_offset
                if t_idx != -1:
                    teacher_grid[t_idx, w_idx, d_idx, current_p] += 1
                for sg_idx in sg_indices:
                    subgroup_grid[sg_idx, w_idx, d_idx, current_p] += 1
                if is_lab == 1:
                    lab_usage_grid[w_idx, d_idx, current_p] += 1
                    if r_idx != -1:
                        room_grid[r_idx, w_idx, d_idx, current_p] += 1

            if w_idx < semester_weeks_len:
                for sg_idx in sg_indices:
                    day_course_counter[sg_idx, w_idx, d_idx, task_group_id] += 1

        # 记录当前任务的时间点到数组
        if course_time_array[course_group_id, 0] == -1:
            course_time_array[course_group_id, 0] = course_group_id
        time_count = course_time_array[course_group_id, 1]
        if time_count < max_phases_per_course - 1:
            course_time_array[course_group_id, 1] += 1
            pos = 2 + 2 * time_count
            course_time_array[course_group_id, pos] = d_idx
            course_time_array[course_group_id, pos + 1] = p_idx

    # 3. 计算惩罚值
    penalty = 0.0

    # 3.1 原有硬约束（完全保留）
    for grid in (teacher_grid, subgroup_grid):
        for val in grid.flat:
            if val > 1:
                penalty += (val - 1) * 10000

    for room_idx in range(room_grid.shape[0]):
        for w_idx in range(room_grid.shape[1]):
            for d_idx in range(room_grid.shape[2]):
                for p_idx in range(room_grid.shape[3]):
                    if room_grid[room_idx, w_idx, d_idx, p_idx] > 1:
                        penalty += (room_grid[room_idx, w_idx, d_idx, p_idx] - 1) * 8000

    # 3.2 修复：同课程+同教学班分阶段时间差异惩罚（仅针对分阶段任务）
    time_diff_penalty_weight = 100.0  # 权重从500降至100（软约束级别）
    for c in range(num_course_groups):
        time_count = course_time_array[c, 1]
        if time_count < 1:
            continue  # 少于2个阶段的课程（非分阶段）不惩罚
        # 以第一个时间点为基准
        base_d = course_time_array[c, 2]
        base_p = course_time_array[c, 3]
        # 检查后续时间点
        for i in range(1, time_count + 1):
            pos = 2 + 2 * i
            current_d = course_time_array[c, pos]
            current_p = course_time_array[c, pos + 1]
            if current_d == -1:
                continue
            # 计算时间差异惩罚（仅针对分阶段任务）
            if current_d != base_d:
                penalty += time_diff_penalty_weight * abs(current_d - base_d)
            if current_p != base_p:
                penalty += time_diff_penalty_weight * abs(current_p - base_p)

    # 3.3 原有软约束（完全保留）
    progress = current_generation / max_generations
    soft_constraint_weight = 0.1 if progress < 0.2 else 0.1 + (progress - 0.2) / 0.8 * 0.9

    for i in range(len(individual)):
        gene = individual[i]
        _, d_idx, p_idx, _ = slot_decode_map[gene]
        task_meta = tasks_meta[i]
        is_campus_teacher = task_meta[4]

        if undesired_masks[i, d_idx, p_idx]:
            penalty += 1000.0 * soft_constraint_weight

        has_preferred = np.any(preferred_masks[i])
        if has_preferred and not preferred_masks[i, d_idx, p_idx]:
            penalty += 50 * soft_constraint_weight

        if d_idx == 3:
            penalty += 30 * soft_constraint_weight

        if p_idx == 0:
            penalty += 10 * soft_constraint_weight

    for val in day_course_counter.flat:
        if val > 1:
            penalty += (val - 1) * 200 * soft_constraint_weight

    for sg_idx in range(subgroup_grid.shape[0]):
        for w_idx in range(semester_weeks_len):
            for d_idx in range(subgroup_grid.shape[2]):
                day_schedule = subgroup_grid[sg_idx, w_idx, d_idx]
                if np.count_nonzero(day_schedule[:4]) == 4:
                    penalty += 70 * soft_constraint_weight
                if np.count_nonzero(day_schedule[4:8]) == 4:
                    penalty += 70 * soft_constraint_weight
    return penalty,


def evaluate_individual_standalone(individual, generation_info, max_gen, **kwargs):
    current_gen = generation_info[0]
    return calculate_fitness_jit(np.array(individual, dtype=np.int32), current_generation=current_gen,
                                 max_generations=max_gen, **kwargs)


class DeapScheduler:
    def __init__(self, teachers, rooms, subgroups, teaching_classes, tc_to_sg_map, fixed_schedule, teacher_preferences):
        self.MAX_LABS_SIMULTANEOUSLY = 2
        self.POP_SIZE, self.MAX_GEN, self.CXPB, self.MUTPB, self.HALL_OF_FAME_SIZE = 1000, 300, 0.9, 0.4, 10
        self.generation_info = [0]
        self.teachers, self.rooms, self.subgroups, self.teaching_classes = teachers, rooms, subgroups, teaching_classes
        self.tc_to_sg_map, self.fixed_schedule, self.teacher_preferences = tc_to_sg_map, fixed_schedule, teacher_preferences
        self._prepare_mappings()
        self._create_scheduling_tasks()
        self._prepare_jit_parameters()
        self._setup_deap_toolbox()

    def _prepare_mappings(self):
        self.teacher_to_idx = {t.name: i for i, t in enumerate(self.teachers)}
        self.subgroup_to_idx = {sg.id: i for i, sg in enumerate(self.subgroups)}
        self.room_to_idx = {r.id: i for i, r in enumerate(self.rooms)}
        self.lab_room_indices = [self.room_to_idx[r.id] for r in self.rooms if "机房" in r.name]

    def _create_scheduling_tasks(self):
        self.tasks = []
        for tc in self.teaching_classes:
            reqs = tc.course.get_schedule_requirements()
            phase_weeks = tc.get_effective_weeks() if hasattr(tc, 'get_effective_weeks') else []

            # 遍历所有 requirement（支持毕业班课程的多个部分，如 theory_makeup_2h, theory_makeup_3h 等）
            for part_key, req_data in reqs.items():
                req = req_data.copy()
                req['phase_weeks'] = phase_weeks
                # 判断是否为实验课
                is_lab = 'lab' in part_key
                
                # 根据 weekly_sessions 创建多个任务（每周多次课需要多个时间槽）
                weekly_sessions = req.get('weekly_sessions', 1)
                for session_idx in range(weekly_sessions):
                    task_req = req.copy()
                    task_req['session_idx'] = session_idx  # 记录是第几次课
                    # course_tc_id 用于分阶段课程的时间一致性约束
                    # 包含 part_key 以区分理论课和实验课（它们不应被视为同一分组）
                    # 对于 weekly_sessions > 1 的课程，每个 session 有不同的 course_tc_id
                    # 这样它们就不会被误判为"分阶段课程"而被惩罚时间不一致
                    task_req['course_tc_id'] = f"{tc.course.id}_{tc.id}_{part_key}_s{session_idx}"
                    self.tasks.append({'tc': tc, 'is_lab': is_lab, 'req': task_req})

    def _prepare_jit_parameters(self):
        self.jit_params = {}

        self.weeks_patterns = {
            'weekly': SEMESTER_WEEKS, 'single_week': SINGLE_WEEKS, 'double_week': DOUBLE_WEEKS,
            'weeks_1_to_14': WEEKS_1_TO_14, 'weeks_5_to_15': WEEKS_5_TO_15, 'weeks_5_to_16': WEEKS_5_TO_16, 'weeks_5_to_17': WEEKS_5_TO_17,
            'weeks_6_to_17': WEEKS_6_TO_17, 'weeks_1_to_8': WEEKS_1_TO_8, 'weeks_9_to_16': WEEKS_9_TO_16,
            'weeks_16_to_17': WEEKS_16_TO_17,
            # 毕业班特殊模式
            'graduation_48h': WEEKS_5_TO_16,  # 48学时: 第5-16周
            'graduation_32h_main': WEEKS_5_TO_15,  # 32学时主体: 第5-15周
        }
        self.pattern_map = {name: i for i, name in enumerate(self.weeks_patterns.keys())}

        # 周次数据初始化（保持不变）
        all_weeks_flat, all_weeks_pointers = [], []
        cursor = 0
        for name in self.pattern_map.keys():
            weeks = [w - 1 for w in self.weeks_patterns[name]]
            all_weeks_flat.extend(weeks)
            all_weeks_pointers.append((cursor, cursor + len(weeks)))
            cursor += len(weeks)

        self.jit_params['all_weeks_patterns_flat'] = np.array(all_weeks_flat, dtype=np.int8)
        self.jit_params['all_weeks_patterns_pointers'] = np.array(all_weeks_pointers, dtype=np.int32)

        # 时间槽编码（保持不变）
        self.task_to_valid_slots, self.slot_decode_map_list, slot_encode_map, gene_idx = [], [], {}, 0
        valid_starts_all = set(VALID_START_PERIODS_2_HOURS) | set(VALID_START_PERIODS_3_HOURS)

        for pattern_idx in range(len(self.pattern_map)):
            for d in DAYS:
                for p in valid_starts_all:
                    for r_idx_option in ([-1] + self.lab_room_indices):
                        key = (pattern_idx, d - 1, p - 1, r_idx_option)
                        if key not in slot_encode_map:
                            slot_encode_map[key] = gene_idx
                            self.slot_decode_map_list.append(key)
                            gene_idx += 1

        # 任务元数据 + 阶段周次数据 + 课程分组（修复核心）
        tasks_meta_list = []
        task_phase_weeks_flat = []
        task_phase_weeks_pointers = []
        phase_cursor = 0

        # 修复：课程分组键改为 (课程ID + 教学班ID) → 仅同一教学班的分阶段任务归为一组
        course_group_map = {}  # key: course_tc_id, value: group_id
        course_group_ids = []  # 每个任务对应的课程分组ID

        # 【新增】预处理固定课占用，用于过滤合法基因
        # 构建 (子组索引, 周次, 星期, 节次) -> 是否被固定课占用
        fixed_slots_by_sg = defaultdict(set)  # sg_idx -> set of (week_0based, day_0based, period_0based)
        cohort_sgs_map = defaultdict(list)
        for sg in self.subgroups:
            cohort_sgs_map[sg.cohort.id].append(sg)
        
        for item in self.fixed_schedule:
            weeks, st, dur = item['week'], item['start_time'], item['duration']
            d_idx, p_start_idx = st.day - 1, st.period - 1
            w_indices = [w - 1 for w in weeks if 1 <= w <= len(ALL_WEEKS)]
            p_indices = list(range(p_start_idx, p_start_idx + dur))
            if not w_indices or not p_indices:
                continue
            
            sgs = cohort_sgs_map.get(item.get('cohort_id'), [])
            tag = item.get('group_tag')
            if tag and tag != 'default':
                relevant_sgs = [sg for sg in sgs if sg.fixed_schedule_tag == tag]
                if not relevant_sgs:
                    relevant_sgs = sgs
            else:
                relevant_sgs = sgs
            
            for sg in relevant_sgs:
                sg_idx = self.subgroup_to_idx.get(sg.id)
                if sg_idx is not None:
                    for w_idx in w_indices:
                        for p_idx in p_indices:
                            fixed_slots_by_sg[sg_idx].add((w_idx, d_idx, p_idx))

        for task in self.tasks:
            valid_genes, req, is_lab, tc = [], task['req'], task['is_lab'], task['tc']
            course_tc_id = req['course_tc_id']  # 用 (课程ID + 教学班ID) 分组

            # 为 (课程+教学班) 分配分组ID
            if course_tc_id not in course_group_map:
                course_group_map[course_tc_id] = len(course_group_map)
            course_group_ids.append(course_group_map[course_tc_id])

            # 任务基础信息（保持不变）
            pattern = req.get('pattern', 'weekly')
            if pattern == 'flexible_48h':
                pattern = 'weekly'

            p_indices_to_try = []
            if pattern in self.pattern_map:
                p_indices_to_try = [self.pattern_map[pattern]]
            if pattern in ['single_week', 'double_week']:
                p_indices_to_try = [self.pattern_map['single_week'], self.pattern_map['double_week']]
            if not p_indices_to_try:
                p_indices_to_try = [self.pattern_map['weekly']]

            hours_per_block = req.get('hours_per_block', 2)
            valid_starts = VALID_START_PERIODS_2_HOURS if hours_per_block == 2 else VALID_START_PERIODS_3_HOURS
            
            # 【新增】获取该任务的子组索引，用于检查固定课占用
            task_sg_indices = [self.subgroup_to_idx.get(sg.id) for sg in self.tc_to_sg_map.get(tc.id, []) if self.subgroup_to_idx.get(sg.id) is not None]
            
            # 获取任务的阶段周次
            phase_weeks = req.get('phase_weeks', [])

            # 生成合法基因（新增固定课占用检查）
            for p_idx in p_indices_to_try:
                pattern_weeks = self.weeks_patterns[list(self.pattern_map.keys())[p_idx]]
                pattern_weeks_0based = [w - 1 for w in pattern_weeks]
                
                # 计算有效周次（与阶段周次取交集）
                if phase_weeks:
                    phase_weeks_0based = set(w - 1 for w in phase_weeks)
                    effective_weeks = [w for w in pattern_weeks_0based if w in phase_weeks_0based]
                else:
                    effective_weeks = pattern_weeks_0based
                
                for d in DAYS:
                    for p in valid_starts:
                        if p + hours_per_block - 1 > 11:
                            continue
                        
                        d_0based = d - 1
                        p_0based = p - 1
                        
                        # 【新增】检查该时间槽是否与固定课冲突
                        has_fixed_conflict = False
                        for sg_idx in task_sg_indices:
                            if sg_idx in fixed_slots_by_sg:
                                fixed_slots = fixed_slots_by_sg[sg_idx]
                                for w_idx in effective_weeks:
                                    for p_offset in range(hours_per_block):
                                        if (w_idx, d_0based, p_0based + p_offset) in fixed_slots:
                                            has_fixed_conflict = True
                                            break
                                    if has_fixed_conflict:
                                        break
                            if has_fixed_conflict:
                                break
                        
                        if has_fixed_conflict:
                            continue  # 跳过与固定课冲突的时间槽
                        
                        if is_lab:
                            for r_idx in self.lab_room_indices:
                                gene = slot_encode_map.get((p_idx, d - 1, p - 1, r_idx))
                                if gene is not None:
                                    valid_genes.append(gene)
                        else:
                            gene = slot_encode_map.get((p_idx, d - 1, p - 1, -1))
                            if gene is not None:
                                valid_genes.append(gene)

            self.task_to_valid_slots.append(np.array(valid_genes, dtype=np.int32))

            # 任务元数据（保持不变）
            is_campus_teacher = 1 if tc.course.is_taught_by_campus_teacher(tc.teacher_name) else 0
            tasks_meta_list.append([
                self.teacher_to_idx.get(tc.teacher_name, -1), 1 if is_lab else 0, hours_per_block,
                0, is_campus_teacher, self.pattern_map.get(pattern, 0)
            ])

            # 处理阶段周次（保持不变）
            phase_weeks = req.get('phase_weeks', [])
            if phase_weeks:
                phase_weeks_0based = [w - 1 for w in phase_weeks]
                task_phase_weeks_flat.extend(phase_weeks_0based)
                task_phase_weeks_pointers.append((phase_cursor, phase_cursor + len(phase_weeks_0based)))
                phase_cursor += len(phase_weeks_0based)
            else:
                task_phase_weeks_pointers.append((0, 0))

        # 任务组映射（保持不变）
        task_group_map = {}
        for i, task in enumerate(self.tasks):
            key = (task['tc'].course.id, task['is_lab'])
            task_group_map.setdefault(key, len(task_group_map))
            tasks_meta_list[i][3] = task_group_map[key]
        self.jit_params['num_task_groups'] = len(task_group_map)

        # 课程分组参数（保持不变，仅分组键已修复）
        self.jit_params['course_group_ids'] = np.array(course_group_ids, dtype=np.int32)
        self.jit_params['num_course_groups'] = len(course_group_map)

        # 子组索引映射（保持不变）
        sg_indices_flat, sg_pointers, cursor = [], [], 0
        for task in self.tasks:
            indices = [self.subgroup_to_idx.get(sg.id) for sg in self.tc_to_sg_map.get(task['tc'].id, []) if
                       self.subgroup_to_idx.get(sg.id) is not None]
            sg_indices_flat.extend(indices)
            sg_pointers.append((cursor, cursor + len(indices)))
            cursor += len(indices)

        # 网格初始化（保持不变）
        grid_shape = (len(ALL_WEEKS), len(DAYS), len(PERIODS))
        grids = {
            'fixed_teacher_grid': np.zeros((len(self.teachers),) + grid_shape, dtype=np.int8),
            'fixed_subgroup_grid': np.zeros((len(self.subgroups),) + grid_shape, dtype=np.int8),
            'fixed_room_grid': np.zeros((len(self.rooms),) + grid_shape, dtype=np.int8),
            'fixed_lab_usage_grid': np.zeros(grid_shape, dtype=np.int8),
            'undesired_masks': np.zeros((len(self.tasks), len(DAYS), len(PERIODS)), dtype=bool),
            'preferred_masks': np.zeros((len(self.tasks), len(DAYS), len(PERIODS)), dtype=bool)
        }

        # 处理固定课程（复用之前构建的 cohort_sgs_map）
        for item in self.fixed_schedule:
            weeks, st, dur = item['week'], item['start_time'], item['duration']
            t_idx = self.teacher_to_idx.get(item['teacher_name'])
            d_idx, p_start_idx = st.day - 1, st.period - 1
            is_lab_item = item.get('is_lab', False)
            room_name = item.get('room_name')
            w_indices = [w - 1 for w in weeks if 1 <= w <= grid_shape[0]]
            p_indices = list(range(p_start_idx, p_start_idx + dur))
            if not w_indices or not p_indices:
                continue

            # 【关键修复】先标记教师占用，确保无论 relevant_sgs 是否为空都能正确标记
            if t_idx is not None:
                grids['fixed_teacher_grid'][np.ix_([t_idx], w_indices, [d_idx], p_indices)] = 1

            sgs = cohort_sgs_map.get(item.get('cohort_id'), [])
            tag = item.get('group_tag')
            
            # 【修复】改进子组匹配逻辑：
            # 1. 如果没有 group_tag 或 group_tag 是 'default'，标记所有子组
            # 2. 如果有具体的 group_tag，优先匹配该 tag 的子组
            # 3. 如果没有匹配到任何子组（tag 不存在），回退到标记所有子组（保守策略）
            if tag and tag != 'default':
                relevant_sgs = [sg for sg in sgs if sg.fixed_schedule_tag == tag]
                # 如果没有匹配到，回退到所有子组（这个固定课程可能影响整个cohort）
                if not relevant_sgs:
                    relevant_sgs = sgs
            else:
                relevant_sgs = sgs

            # 标记子组占用
            for sg in relevant_sgs:
                sg_idx = self.subgroup_to_idx.get(sg.id)
                if sg_idx is not None:
                    grids['fixed_subgroup_grid'][np.ix_([sg_idx], w_indices, [d_idx], p_indices)] = 1

            if is_lab_item:
                grids['fixed_lab_usage_grid'][np.ix_(w_indices, [d_idx], p_indices)] += 1
                if room_name and room_name != "N/A":
                    room = next((r for r in self.rooms if r.name == room_name), None)
                    if room:
                        r_idx = self.room_to_idx.get(room.id)
                        if r_idx is not None:
                            grids['fixed_room_grid'][np.ix_([r_idx], w_indices, [d_idx], p_indices)] = 1

        # 教师偏好掩码（保持不变）
        for i, task in enumerate(self.tasks):
            tc = task['tc']

            for pref in self.teacher_preferences:
                if pref['teacher_name'] == tc.teacher_name and (
                        pref.get('course_name') is None or pref['course_name'] == tc.course.name):
                    for day, period in pref.get('undesired_slots', []):
                        d = day - 1
                        if 1 <= day <= len(DAYS):
                            p_range = range(len(PERIODS)) if period == -1 else [period - 1]
                            for p in p_range:
                                if 0 <= p < len(PERIODS):
                                    grids['undesired_masks'][i, d, p] = True
                    for day, period in pref.get('preferred_slots', []):
                        d = day - 1
                        if 1 <= day <= len(DAYS):
                            p_range = range(len(PERIODS)) if period == -1 else [period - 1]
                            for p in p_range:
                                if 0 <= p < len(PERIODS):
                                    grids['preferred_masks'][i, d, p] = True

        # 组装JIT参数（保持不变）
        self.jit_params['tasks_meta'] = np.array(tasks_meta_list, dtype=np.int32)
        self.jit_params['task_to_sg_indices_flat'] = np.array(sg_indices_flat, dtype=np.int32)
        self.jit_params['task_to_sg_pointers'] = np.array(sg_pointers, dtype=np.int32)
        self.jit_params['task_phase_weeks_flat'] = np.array(task_phase_weeks_flat, dtype=np.int8)
        self.jit_params['task_phase_weeks_pointers'] = np.array(task_phase_weeks_pointers, dtype=np.int32)

        arr_slot_decode = np.array(self.slot_decode_map_list, dtype=np.int32)
        self.jit_params['flat_slot_decode_map'] = arr_slot_decode.flatten()
        self.jit_params['shape_slot_decode_map'] = arr_slot_decode.shape

        for key, arr in grids.items():
            self.jit_params[f'flat_{key}'] = arr.flatten()
            self.jit_params[f'shape_{key}'] = arr.shape

        self.jit_params['max_labs_simultaneously'] = self.MAX_LABS_SIMULTANEOUSLY
        self.jit_params['semester_weeks_len'] = len(SEMESTER_WEEKS)

    def _setup_deap_toolbox(self):
        # 避免重复创建类导致内存泄漏
        if not hasattr(creator, "FitnessMin"):
            creator.create("FitnessMin", base.Fitness, weights=(-1.0,))
        if not hasattr(creator, "Individual"):
            creator.create("Individual", list, fitness=creator.FitnessMin)
        self.toolbox = base.Toolbox()

        self.toolbox.register("individual_generator", lambda: [
            random.choice(self.task_to_valid_slots[i]) if i < len(self.task_to_valid_slots) and
                                                          self.task_to_valid_slots[i].size > 0 else 0
            for i in range(len(self.tasks))
        ])

        self.toolbox.register("individual", tools.initIterate, creator.Individual, self.toolbox.individual_generator)
        self.toolbox.register("population", tools.initRepeat, list, self.toolbox.individual)
        self.toolbox.register("evaluate", partial(evaluate_individual_standalone, generation_info=self.generation_info,
                                                  max_gen=self.MAX_GEN, **self.jit_params))
        self.toolbox.register("mate", tools.cxTwoPoint)
        self.toolbox.register("mutate", self.mutate_individual, indpb=0.1)
        self.toolbox.register("select", tools.selTournament, tournsize=3)

    def mutate_individual(self, individual, indpb):
        for i in range(len(individual)):
            if random.random() < indpb:
                if i < len(self.task_to_valid_slots) and self.task_to_valid_slots[i].size > 0:
                    individual[i] = random.choice(self.task_to_valid_slots[i])
        return individual,

    def solve(self, pool):
        if not self.tasks:
            print("没有需要通过遗传算法安排的课程。")
            self.best_individual = []
            self.best_fitness = 0.0
            return True
        self.toolbox.register("map", pool.map)
        pop, hof = self.toolbox.population(n=self.POP_SIZE), tools.HallOfFame(self.HALL_OF_FAME_SIZE)
        stats = tools.Statistics(lambda ind: ind.fitness.values[0])
        stats.register("avg", np.mean)
        stats.register("std", np.std)
        stats.register("min", np.min)
        stats.register("max", np.max)

        def custom_log(pop, gen, stats, hof):
            self.generation_info[0] = gen
            record = stats.compile(pop)
            print(f"Gen: {gen:<5} Max: {record['max']:<12.2f} Min: {record['min']:<12.2f}")

        invalid_ind = [ind for ind in pop if not ind.fitness.valid]
        fitnesses = self.toolbox.map(self.toolbox.evaluate, invalid_ind)
        for ind, fit in zip(invalid_ind, fitnesses):
            ind.fitness.values = fit
        hof.update(pop)
        custom_log(pop, 0, stats, hof)

        for gen in range(1, self.MAX_GEN + 1):
            offspring = self.toolbox.select(pop, len(pop))
            offspring = algorithms.varAnd(offspring, self.toolbox, self.CXPB, self.MUTPB)
            invalid_ind = [ind for ind in offspring if not ind.fitness.valid]
            fitnesses = self.toolbox.map(self.toolbox.evaluate, invalid_ind)
            for ind, fit in zip(invalid_ind, fitnesses):
                ind.fitness.values = fit
            hof.update(offspring)
            pop[:] = offspring

            # 精英保留策略（保持不变）
            worst_in_pop_indices = sorted(range(len(pop)), key=lambda k: pop[k].fitness, reverse=True)
            for i in range(min(len(worst_in_pop_indices), self.HALL_OF_FAME_SIZE)):
                pop[worst_in_pop_indices[i]] = copy.deepcopy(hof[i])

            if gen % 10 == 0:
                custom_log(pop, gen, stats, hof)

        # 最终评估（保持不变）
        final_eval_info = [self.MAX_GEN]
        final_toolbox = base.Toolbox()
        final_toolbox.register("map", pool.map)
        final_toolbox.register("evaluate", partial(evaluate_individual_standalone, generation_info=final_eval_info,
                                                   max_gen=self.MAX_GEN, **self.jit_params))
        final_fitnesses = final_toolbox.map(final_toolbox.evaluate, hof)
        for ind, fit in zip(hof, final_fitnesses):
            ind.fitness.values = fit
        hof.update(hof)

        self.best_individual, self.best_fitness = hof[0], hof[0].fitness.values[0]
        print(f"\nGA 演化完成。最优解的最终惩罚值 (所有约束权重最大): {self.best_fitness:.2f}")
        
        # 分析并保存惩罚详情
        self.penalty_details = self._analyze_penalty_details(self.best_individual)

        return self.best_fitness < 5000
    
    def _analyze_penalty_details(self, individual):
        """分析惩罚分数的详细来源"""
        if not individual:
            return {}
        
        # 重建网格并计算各类惩罚
        slot_decode_map = np.array(self.slot_decode_map_list, dtype=np.int32)
        tasks_meta = self.jit_params['tasks_meta']
        course_group_ids = self.jit_params['course_group_ids']
        num_course_groups = self.jit_params['num_course_groups']
        num_task_groups = self.jit_params['num_task_groups']
        semester_weeks_len = self.jit_params['semester_weeks_len']
        
        # 初始化网格
        grid_shape = (len(ALL_WEEKS), len(DAYS), len(PERIODS))
        teacher_grid = self.jit_params['flat_fixed_teacher_grid'].reshape(self.jit_params['shape_fixed_teacher_grid']).copy()
        subgroup_grid = self.jit_params['flat_fixed_subgroup_grid'].reshape(self.jit_params['shape_fixed_subgroup_grid']).copy()
        room_grid = self.jit_params['flat_fixed_room_grid'].reshape(self.jit_params['shape_fixed_room_grid']).copy()
        
        # 子组索引映射
        sg_indices_flat = self.jit_params['task_to_sg_indices_flat']
        sg_pointers = self.jit_params['task_to_sg_pointers']
        
        # 周次模式
        all_weeks_flat = self.jit_params['all_weeks_patterns_flat']
        all_weeks_pointers = self.jit_params['all_weeks_patterns_pointers']
        
        # 阶段周次
        phase_weeks_flat = self.jit_params['task_phase_weeks_flat']
        phase_weeks_pointers = self.jit_params['task_phase_weeks_pointers']
        
        # 偏好掩码
        undesired_masks = self.jit_params['flat_undesired_masks'].reshape(self.jit_params['shape_undesired_masks'])
        preferred_masks = self.jit_params['flat_preferred_masks'].reshape(self.jit_params['shape_preferred_masks'])
        
        # 用于统计软约束
        day_course_counter = np.zeros((len(self.subgroups), semester_weeks_len, len(DAYS), num_task_groups), dtype=np.int8)
        course_time_array = np.full((num_course_groups, 2 + 2 * 10), -1, dtype=np.int32)  # max 10 phases
        
        # 记录每个任务的时间分配
        task_assignments = []
        
        # 填充网格
        for i, gene in enumerate(individual):
            pattern_idx, d_idx, p_idx, r_idx = slot_decode_map[gene]
            t_idx, is_lab, duration, task_group_id = tasks_meta[i, 0], tasks_meta[i, 1], tasks_meta[i, 2], tasks_meta[i, 3]
            course_group_id = course_group_ids[i]
            
            # 获取子组索引
            sg_start, sg_end = sg_pointers[i]
            sg_indices = sg_indices_flat[sg_start:sg_end]
            
            # 获取周次
            wp_start, wp_end = all_weeks_pointers[pattern_idx]
            raw_weeks = all_weeks_flat[wp_start:wp_end]
            
            # 应用阶段周次过滤
            pw_start, pw_end = phase_weeks_pointers[i]
            if pw_end > pw_start:
                phase_weeks = set(phase_weeks_flat[pw_start:pw_end])
                effective_weeks = [w for w in raw_weeks if w in phase_weeks]
            else:
                effective_weeks = list(raw_weeks)
            
            # 记录任务分配
            task_assignments.append({
                'task_idx': i,
                'd_idx': d_idx,
                'p_idx': p_idx,
                'effective_weeks': effective_weeks
            })
            
            # 填充网格
            for w_idx in effective_weeks:
                for p_offset in range(duration):
                    current_p = p_idx + p_offset
                    if current_p < len(PERIODS):
                        if t_idx != -1:
                            teacher_grid[t_idx, w_idx, d_idx, current_p] += 1
                        for sg_idx in sg_indices:
                            subgroup_grid[sg_idx, w_idx, d_idx, current_p] += 1
                        if is_lab == 1 and r_idx != -1:
                            room_grid[r_idx, w_idx, d_idx, current_p] += 1
                
                # 统计同天同课次数
                if w_idx < semester_weeks_len:
                    for sg_idx in sg_indices:
                        day_course_counter[sg_idx, w_idx, d_idx, task_group_id] += 1
            
            # 记录课程时间点（用于分阶段惩罚计算）
            if course_time_array[course_group_id, 0] == -1:
                course_time_array[course_group_id, 0] = course_group_id
            time_count = course_time_array[course_group_id, 1]
            if time_count < 9:
                course_time_array[course_group_id, 1] += 1
                pos = 2 + 2 * time_count
                course_time_array[course_group_id, pos] = d_idx
                course_time_array[course_group_id, pos + 1] = p_idx
        
        # 统计各类冲突
        details = {
            'hard_constraints': {},  # 硬约束
            'soft_constraints': {},  # 软约束
            'teacher_conflicts': [],  # 教师冲突详情
            'subgroup_conflicts': [],  # 学生冲突详情
            'room_conflicts': [],  # 机房冲突详情
            'summary': {}  # 汇总
        }
        
        # ========== 硬约束统计 ==========
        
        # 1. 教师冲突
        teacher_conflict_count = 0
        teacher_conflict_penalty = 0
        for t_idx in range(teacher_grid.shape[0]):
            for w_idx in range(teacher_grid.shape[1]):
                for d_idx in range(teacher_grid.shape[2]):
                    for p_idx in range(teacher_grid.shape[3]):
                        val = teacher_grid[t_idx, w_idx, d_idx, p_idx]
                        if val > 1:
                            teacher_conflict_count += 1
                            penalty = (val - 1) * 10000
                            teacher_conflict_penalty += penalty
                            teacher_name = next((name for name, idx in self.teacher_to_idx.items() if idx == t_idx), f"教师{t_idx}")
                            if len(details['teacher_conflicts']) < 20:
                                details['teacher_conflicts'].append({
                                    'type': '教师冲突',
                                    'teacher': teacher_name,
                                    'week': int(w_idx + 1),
                                    'day': int(d_idx + 1),
                                    'period': int(p_idx + 1),
                                    'conflict_count': int(val),
                                    'penalty': int(penalty),
                                    'desc': f"{teacher_name} 在第{w_idx+1}周 周{['一','二','三','四','五'][d_idx]} 第{p_idx+1}节 同时有{val}门课"
                                })
        
        # 2. 学生冲突
        subgroup_conflict_count = 0
        subgroup_conflict_penalty = 0
        for sg_idx in range(subgroup_grid.shape[0]):
            for w_idx in range(subgroup_grid.shape[1]):
                for d_idx in range(subgroup_grid.shape[2]):
                    for p_idx in range(subgroup_grid.shape[3]):
                        val = subgroup_grid[sg_idx, w_idx, d_idx, p_idx]
                        if val > 1:
                            subgroup_conflict_count += 1
                            penalty = (val - 1) * 10000
                            subgroup_conflict_penalty += penalty
                            sg_id = next((sid for sid, idx in self.subgroup_to_idx.items() if idx == sg_idx), f"子组{sg_idx}")
                            if len(details['subgroup_conflicts']) < 20:
                                details['subgroup_conflicts'].append({
                                    'type': '学生冲突',
                                    'subgroup': sg_id,
                                    'week': int(w_idx + 1),
                                    'day': int(d_idx + 1),
                                    'period': int(p_idx + 1),
                                    'conflict_count': int(val),
                                    'penalty': int(penalty),
                                    'desc': f"{sg_id} 在第{w_idx+1}周 周{['一','二','三','四','五'][d_idx]} 第{p_idx+1}节 同时有{val}门课"
                                })
        
        # 3. 机房冲突
        room_conflict_count = 0
        room_conflict_penalty = 0
        for r_idx in range(room_grid.shape[0]):
            for w_idx in range(room_grid.shape[1]):
                for d_idx in range(room_grid.shape[2]):
                    for p_idx in range(room_grid.shape[3]):
                        val = room_grid[r_idx, w_idx, d_idx, p_idx]
                        if val > 1:
                            room_conflict_count += 1
                            penalty = (val - 1) * 8000
                            room_conflict_penalty += penalty
                            room_id = next((rid for rid, idx in self.room_to_idx.items() if idx == r_idx), None)
                            room_name = next((r.name for r in self.rooms if r.id == room_id), f"机房{r_idx}") if room_id else f"机房{r_idx}"
                            if len(details['room_conflicts']) < 20:
                                details['room_conflicts'].append({
                                    'type': '机房冲突',
                                    'room': room_name,
                                    'week': int(w_idx + 1),
                                    'day': int(d_idx + 1),
                                    'period': int(p_idx + 1),
                                    'conflict_count': int(val),
                                    'penalty': int(penalty),
                                    'desc': f"{room_name} 在第{w_idx+1}周 周{['一','二','三','四','五'][d_idx]} 第{p_idx+1}节 同时有{val}节课"
                                })
        
        details['hard_constraints'] = {
            'teacher_conflict': {'count': teacher_conflict_count, 'penalty': teacher_conflict_penalty, 'weight': 10000, 'desc': '教师时间冲突'},
            'subgroup_conflict': {'count': subgroup_conflict_count, 'penalty': subgroup_conflict_penalty, 'weight': 10000, 'desc': '学生时间冲突'},
            'room_conflict': {'count': room_conflict_count, 'penalty': room_conflict_penalty, 'weight': 8000, 'desc': '机房时间冲突'},
        }
        
        # ========== 软约束统计 ==========
        
        # 计算软约束权重(最终状态)
        soft_weight = 1.0  # 最终评估时权重为1
        day_names = ['一', '二', '三', '四', '五']
        
        # 辅助函数：将numpy类型转为Python原生类型
        def to_native(val):
            if hasattr(val, 'item'):
                return val.item()
            return val
        
        # 辅助函数：获取任务的课程信息
        def get_task_info(task_idx):
            task = self.tasks[task_idx]
            tc = task['tc']
            # 获取专业年级信息
            cohort_name = ''
            if hasattr(tc, 'main_cohort') and tc.main_cohort:
                cohort = tc.main_cohort
                cohort_name = f"{cohort.major}{cohort.grade}"
            elif hasattr(tc, 'subgroups') and tc.subgroups:
                sg = tc.subgroups[0]
                if hasattr(sg, 'cohort') and sg.cohort:
                    cohort = sg.cohort
                    cohort_name = f"{cohort.major}{cohort.grade}"
            # 如果还是没有，尝试从 tc_to_sg_map 获取
            if not cohort_name:
                sgs = self.tc_to_sg_map.get(tc.id, [])
                if sgs and hasattr(sgs[0], 'cohort') and sgs[0].cohort:
                    cohort = sgs[0].cohort
                    cohort_name = f"{cohort.major}{cohort.grade}"
            return {
                'course_name': tc.course.name,
                'teacher_name': tc.teacher_name,
                'cohort_name': cohort_name,
                'class_name': tc.name if hasattr(tc, 'name') else str(tc.id),
                'is_lab': task['is_lab']
            }
        
        # 辅助函数：获取子组名称（优化显示格式）
        def get_subgroup_name(sg_idx):
            sg_id = next((sid for sid, idx in self.subgroup_to_idx.items() if idx == sg_idx), None)
            if sg_id:
                sg = next((s for s in self.subgroups if s.id == sg_id), None)
                if sg and hasattr(sg, 'cohort') and sg.cohort:
                    # 例如: SG_大数据科学与技术大二2023_1 -> 大数据科学与技术2023-子组1
                    cohort = sg.cohort
                    # 从 sg.id 提取组号 (最后的数字)
                    parts = sg.id.split('_')
                    group_num = parts[-1] if parts else '1'
                    return f"{cohort.major}{cohort.grade}-子组{group_num}"
                elif sg:
                    # 简化显示：移除 SG_ 前缀
                    display_id = sg.id.replace('SG_', '').replace('_', '-子组')
                    return display_id
            return f"子组{sg_idx}"
        
        # 记录详情的列表
        time_diff_details = []
        undesired_slot_details = []
        not_preferred_details = []
        thursday_details = []
        first_period_details = []
        same_day_course_details = []
        consecutive_4_details = []
        
        # 构建 course_group_id 到任务索引的映射
        course_group_to_tasks = defaultdict(list)
        for i, gene in enumerate(individual):
            course_group_id = course_group_ids[i]
            _, d_idx, p_idx, _ = slot_decode_map[gene]
            course_group_to_tasks[course_group_id].append((i, d_idx, p_idx))
        
        # 1. 分阶段时间不一致惩罚
        time_diff_penalty = 0
        time_diff_count = 0
        time_diff_weight = 100.0
        for c in range(num_course_groups):
            time_count = course_time_array[c, 1]
            if time_count < 1:
                continue
            base_d = course_time_array[c, 2]
            base_p = course_time_array[c, 3]
            task_indices = course_group_to_tasks.get(c, [])
            if not task_indices:
                continue
            task_info = get_task_info(task_indices[0][0])
            has_diff = False
            diff_desc_parts = []
            for i in range(1, time_count + 1):
                pos = 2 + 2 * i
                current_d = course_time_array[c, pos]
                current_p = course_time_array[c, pos + 1]
                if current_d == -1:
                    continue
                if current_d != base_d:
                    time_diff_penalty += time_diff_weight * abs(current_d - base_d)
                    time_diff_count += 1
                    has_diff = True
                if current_p != base_p:
                    time_diff_penalty += time_diff_weight * abs(current_p - base_p)
                    time_diff_count += 1
                    has_diff = True
            if has_diff:
                # 获取所有阶段的时间
                times = [f"周{day_names[d]}第{p+1}节" for _, d, p in task_indices]
                cohort_str = f"[{task_info['cohort_name']}] " if task_info['cohort_name'] else ''
                # 构建更清晰的描述
                phase_count = len(times)
                time_diff_details.append({
                    'course': task_info['course_name'],
                    'teacher': task_info['teacher_name'],
                    'cohort': task_info['cohort_name'],
                    'class': task_info['class_name'],
                    'times': times,
                    'desc': f"{cohort_str}{task_info['course_name']}({task_info['teacher_name']}) 分{phase_count}个阶段上课，各阶段时间不同: {' → '.join(times)}"
                })
        
        # 2. 不希望的时间槽惩罚
        undesired_slot_penalty = 0
        undesired_slot_count = 0
        undesired_weight = 1000.0
        for i, gene in enumerate(individual):
            _, d_idx, p_idx, _ = slot_decode_map[gene]
            if undesired_masks[i, d_idx, p_idx]:
                undesired_slot_penalty += undesired_weight * soft_weight
                undesired_slot_count += 1
                if True:
                    task_info = get_task_info(i)
                    cohort_str = f"[{task_info['cohort_name']}] " if task_info['cohort_name'] else ''
                    undesired_slot_details.append({
                        'course': task_info['course_name'],
                        'teacher': task_info['teacher_name'],
                        'cohort': task_info['cohort_name'],
                        'class': task_info['class_name'],
                        'time': f"周{day_names[d_idx]}第{p_idx+1}节",
                        'desc': f"{cohort_str}{task_info['course_name']}({task_info['teacher_name']}) 被安排在不希望的时间: 周{day_names[d_idx]}第{p_idx+1}节"
                    })
        
        # 3. 未在偏好时间惩罚
        not_preferred_penalty = 0
        not_preferred_count = 0
        preferred_weight = 50.0
        for i, gene in enumerate(individual):
            _, d_idx, p_idx, _ = slot_decode_map[gene]
            has_preferred = np.any(preferred_masks[i])
            if has_preferred and not preferred_masks[i, d_idx, p_idx]:
                not_preferred_penalty += preferred_weight * soft_weight
                not_preferred_count += 1
                if True:
                    task_info = get_task_info(i)
                    # 找出偏好的时间
                    pref_times = []
                    for pd in range(preferred_masks.shape[1]):
                        for pp in range(preferred_masks.shape[2]):
                            if preferred_masks[i, pd, pp]:
                                pref_times.append(f"周{day_names[pd]}第{pp+1}节")
                    cohort_str = f"[{task_info['cohort_name']}] " if task_info['cohort_name'] else ''
                    not_preferred_details.append({
                        'course': task_info['course_name'],
                        'teacher': task_info['teacher_name'],
                        'cohort': task_info['cohort_name'],
                        'class': task_info['class_name'],
                        'actual_time': f"周{day_names[d_idx]}第{p_idx+1}节",
                        'preferred_times': pref_times[:5],  # 最多显示5个
                        'desc': f"{cohort_str}{task_info['course_name']}({task_info['teacher_name']}) 未安排在偏好时间, 实际: 周{day_names[d_idx]}第{p_idx+1}节"
                    })
        
        # 4. 周四惩罚
        thursday_penalty = 0
        thursday_count = 0
        thursday_weight = 30.0
        for i, gene in enumerate(individual):
            _, d_idx, p_idx, _ = slot_decode_map[gene]
            if d_idx == 3:  # 周四
                thursday_penalty += thursday_weight * soft_weight
                thursday_count += 1
                if True:
                    task_info = get_task_info(i)
                    cohort_str = f"[{task_info['cohort_name']}] " if task_info['cohort_name'] else ''
                    thursday_details.append({
                        'course': task_info['course_name'],
                        'teacher': task_info['teacher_name'],
                        'cohort': task_info['cohort_name'],
                        'class': task_info['class_name'],
                        'time': f"周四第{p_idx+1}节",
                        'desc': f"{cohort_str}{task_info['course_name']}({task_info['teacher_name']}) 安排在周四第{p_idx+1}节"
                    })
        
        # 5. 第一节课惩罚
        first_period_penalty = 0
        first_period_count = 0
        first_period_weight = 10.0
        for i, gene in enumerate(individual):
            _, d_idx, p_idx, _ = slot_decode_map[gene]
            if p_idx == 0:  # 第一节
                first_period_penalty += first_period_weight * soft_weight
                first_period_count += 1
                if True:
                    task_info = get_task_info(i)
                    cohort_str = f"[{task_info['cohort_name']}] " if task_info['cohort_name'] else ''
                    first_period_details.append({
                        'course': task_info['course_name'],
                        'teacher': task_info['teacher_name'],
                        'cohort': task_info['cohort_name'],
                        'class': task_info['class_name'],
                        'time': f"周{day_names[d_idx]}第1节",
                        'desc': f"{cohort_str}{task_info['course_name']}({task_info['teacher_name']}) 安排在周{day_names[d_idx]}第1节"
                    })
        
        # 6. 同天同课多次惩罚 - 需要跟踪具体信息
        same_day_course_penalty = 0
        same_day_course_count = 0
        same_day_weight = 200.0
        # 重新计算并记录详情
        day_course_info = {}  # (sg_idx, w_idx, d_idx, task_group_id) -> list of task_idx
        for i, gene in enumerate(individual):
            _, d_idx, p_idx, _ = slot_decode_map[gene]
            task = self.tasks[i]
            task_group_id = tasks_meta[i, 3]
            sg_start, sg_end = sg_pointers[i]
            sg_indices_list = sg_indices_flat[sg_start:sg_end]
            
            # 获取有效周次
            pattern_idx = slot_decode_map[gene][0]
            wp_start, wp_end = all_weeks_pointers[pattern_idx]
            raw_weeks = all_weeks_flat[wp_start:wp_end]
            pw_start, pw_end = phase_weeks_pointers[i]
            if pw_end > pw_start:
                phase_weeks_set = set(phase_weeks_flat[pw_start:pw_end])
                effective_weeks = [w for w in raw_weeks if w in phase_weeks_set]
            else:
                effective_weeks = list(raw_weeks)
            
            for sg_idx in sg_indices_list:
                for w_idx in effective_weeks:
                    if w_idx < semester_weeks_len:
                        key = (sg_idx, w_idx, d_idx, task_group_id)
                        if key not in day_course_info:
                            day_course_info[key] = []
                        day_course_info[key].append(i)
        
        for key, task_list in day_course_info.items():
            if len(task_list) > 1:
                sg_idx, w_idx, d_idx, task_group_id = key
                same_day_course_penalty += (len(task_list) - 1) * same_day_weight * soft_weight
                same_day_course_count += 1
                if True:
                    task_info = get_task_info(task_list[0])
                    sg_name = get_subgroup_name(sg_idx)
                    same_day_course_details.append({
                        'course': task_info['course_name'],
                        'teacher': task_info['teacher_name'],
                        'class': sg_name,
                        'week': to_native(w_idx) + 1,
                        'day': day_names[to_native(d_idx)],
                        'times': len(task_list),
                        'desc': f"{sg_name} 在第{to_native(w_idx)+1}周周{day_names[to_native(d_idx)]} {task_info['course_name']} 有{len(task_list)}次课"
                    })
        
        # 7. 连续4节课惩罚 - 记录具体信息
        consecutive_4_penalty = 0
        consecutive_4_count = 0
        consecutive_weight = 70.0
        for sg_idx in range(subgroup_grid.shape[0]):
            for w_idx in range(semester_weeks_len):
                for d_idx in range(subgroup_grid.shape[2]):
                    day_schedule = subgroup_grid[sg_idx, w_idx, d_idx]
                    if np.count_nonzero(day_schedule[:4]) == 4:  # 上午14节全满
                        consecutive_4_penalty += consecutive_weight * soft_weight
                        consecutive_4_count += 1
                        if True:
                            sg_name = get_subgroup_name(sg_idx)
                            consecutive_4_details.append({
                                'class': sg_name,
                                'week': to_native(w_idx) + 1,
                                'day': day_names[to_native(d_idx)],
                                'period': '上午1-4节',
                                'desc': f"{sg_name} 在第{to_native(w_idx)+1}周周{day_names[to_native(d_idx)]} 上午连续4节课"
                            })
                    if np.count_nonzero(day_schedule[4:8]) == 4:  # 下午14节全满
                        consecutive_4_penalty += consecutive_weight * soft_weight
                        consecutive_4_count += 1
                        if True:
                            sg_name = get_subgroup_name(sg_idx)
                            consecutive_4_details.append({
                                'class': sg_name,
                                'week': to_native(w_idx) + 1,
                                'day': day_names[to_native(d_idx)],
                                'period': '下午5-8节',
                                'desc': f"{sg_name} 在第{to_native(w_idx)+1}周周{day_names[to_native(d_idx)]} 下午连续4节课"
                            })
        
        details['soft_constraints'] = {
            'time_diff': {
                'count': time_diff_count, 
                'penalty': round(time_diff_penalty, 2), 
                'weight': time_diff_weight, 
                'desc': '分阶段上课时间不同(建议各阶段保持相同时间)',
                'items': time_diff_details
            },
            'undesired_slot': {
                'count': undesired_slot_count, 
                'penalty': round(undesired_slot_penalty, 2), 
                'weight': undesired_weight, 
                'desc': '安排在不希望的时间',
                'items': undesired_slot_details
            },
            'not_preferred': {
                'count': not_preferred_count, 
                'penalty': round(not_preferred_penalty, 2), 
                'weight': preferred_weight, 
                'desc': '未安排在偏好时间',
                'items': not_preferred_details
            },
            'thursday': {
                'count': thursday_count, 
                'penalty': round(thursday_penalty, 2), 
                'weight': thursday_weight, 
                'desc': '周四排课惩罚',
                'items': thursday_details
            },
            'first_period': {
                'count': first_period_count, 
                'penalty': round(first_period_penalty, 2), 
                'weight': first_period_weight, 
                'desc': '第一节课惩罚',
                'items': first_period_details
            },
            'same_day_course': {
                'count': same_day_course_count, 
                'penalty': round(same_day_course_penalty, 2), 
                'weight': same_day_weight, 
                'desc': '同天同课多次',
                'items': same_day_course_details
            },
            'consecutive_4': {
                'count': consecutive_4_count, 
                'penalty': round(consecutive_4_penalty, 2), 
                'weight': consecutive_weight, 
                'desc': '连续4节课',
                'items': consecutive_4_details
            },
        }
        
        # 计算汇总
        hard_total = teacher_conflict_penalty + subgroup_conflict_penalty + room_conflict_penalty
        soft_total = time_diff_penalty + undesired_slot_penalty + not_preferred_penalty + thursday_penalty + first_period_penalty + same_day_course_penalty + consecutive_4_penalty
        
        details['summary'] = {
            'total_penalty': round(float(self.best_fitness), 2),
            'hard_constraint_penalty': round(hard_total, 2),
            'soft_constraint_penalty': round(soft_total, 2),
            'teacher_conflict_count': teacher_conflict_count,
            'teacher_conflict_penalty': teacher_conflict_penalty,
            'subgroup_conflict_count': subgroup_conflict_count,
            'subgroup_conflict_penalty': subgroup_conflict_penalty,
            'room_conflict_count': room_conflict_count,
            'room_conflict_penalty': room_conflict_penalty,
        }
        
        return details
    
    def get_penalty_details(self):
        """获取惩罚详情"""
        return getattr(self, 'penalty_details', {})
    
    def cleanup(self):
        """清理资源，释放内存"""
        # 清理大型数组
        if hasattr(self, 'jit_params'):
            self.jit_params.clear()
        if hasattr(self, 'task_to_valid_slots'):
            self.task_to_valid_slots.clear()
        if hasattr(self, 'slot_decode_map_list'):
            self.slot_decode_map_list.clear()
        if hasattr(self, 'tasks'):
            self.tasks.clear()
        # 清理 toolbox
        if hasattr(self, 'toolbox'):
            self.toolbox.unregister("map")
            del self.toolbox
        # 强制垃圾回收
        import gc
        gc.collect()

    def get_results(self):
        if not hasattr(self, 'best_individual') or not self.best_individual:
            return []
        results = []
        slot_decode_map = np.array(self.slot_decode_map_list, dtype=np.int32)
        if slot_decode_map.shape[0] == 0:
            return []

        pattern_name_list = list(self.pattern_map.keys())

        for i, gene in enumerate(self.best_individual):
            task, req = self.tasks[i], self.tasks[i]['req']
            tc, is_lab = task['tc'], task['is_lab']

            week_pattern_idx, d_idx, period_idx, r_idx = slot_decode_map[gene]

            # 应用阶段周次过滤（保持不变）
            pattern_name = pattern_name_list[week_pattern_idx]
            raw_weeks = self.weeks_patterns.get(pattern_name, SEMESTER_WEEKS)
            phase_weeks = req.get('phase_weeks', [])

            if phase_weeks:
                phase_week_set = set(phase_weeks)
                effective_weeks = [w for w in raw_weeks if w in phase_week_set]
            else:
                effective_weeks = raw_weeks

            # 查找教室（保持不变）
            room_name = None
            if is_lab and r_idx != -1:
                room_id = next((rid for rid, idx in self.room_to_idx.items() if idx == r_idx), None)
                if room_id:
                    room_name = next((r.name for r in self.rooms if r.id == room_id), None)

            # 生成结果 - 转numpy类型为Python原生类型
            day_val = int(d_idx) + 1
            period_val = int(period_idx) + 1
            duration_val = int(req.get('hours_per_block', 2))
            
            for week in effective_weeks:
                week_val = int(week) if hasattr(week, 'item') else week
                results.append({
                    "teaching_class_id": tc.id, "course_name": tc.course.name, "teacher_name": tc.teacher_name,
                    "time_point": TimePoint(week=week_val, day=day_val, period=period_val),
                    "duration": duration_val, "room_name": room_name,
                    "is_lab": bool(is_lab), "is_combined": bool(tc.is_combined)
                })
        return results
