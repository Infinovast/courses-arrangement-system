# deap_scheduler.py

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
        flat_slot_decode_map, shape_slot_decode_map,
        all_weeks_patterns_flat, all_weeks_patterns_pointers,
        task_phase_weeks_flat, task_phase_weeks_pointers,
        course_group_ids,
        num_course_groups,
        flat_undesired_masks, shape_undesired_masks,
        flat_preferred_masks, shape_preferred_masks,
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
    """计算惩罚分数 - Fitness function"""
    slot_decode_map = flat_slot_decode_map.reshape(shape_slot_decode_map)
    undesired_masks = flat_undesired_masks.reshape(shape_undesired_masks)
    preferred_masks = flat_preferred_masks.reshape(shape_preferred_masks)

    teacher_grid = flat_fixed_teacher_grid.reshape(shape_fixed_teacher_grid).copy()
    subgroup_grid = flat_fixed_subgroup_grid.reshape(shape_fixed_subgroup_grid).copy()
    room_grid = flat_fixed_room_grid.reshape(shape_fixed_room_grid).copy()
    lab_usage_grid = flat_fixed_lab_usage_grid.reshape(shape_fixed_lab_usage_grid).copy()

    day_course_counter = np.zeros((subgroup_grid.shape[0], semester_weeks_len, subgroup_grid.shape[2], num_task_groups),
                                  dtype=np.int32)
    max_phases_per_course = 10
    course_time_array = np.full((num_course_groups, 1 + 1 + 2 * max_phases_per_course), -1, dtype=np.int32)

    for i in range(len(individual)):
        gene = individual[i]
        t_idx, is_lab, duration, task_group_id, _, _ = tasks_meta[i]
        start_ptr, end_ptr = task_to_sg_pointers[i]
        sg_indices = task_to_sg_indices_flat[start_ptr:end_ptr]
        course_group_id = course_group_ids[i]

        week_pattern_idx, d_idx, p_idx, r_idx = slot_decode_map[gene]

        weeks_start_ptr, weeks_end_ptr = all_weeks_patterns_pointers[week_pattern_idx]
        raw_weeks = all_weeks_patterns_flat[weeks_start_ptr:weeks_end_ptr]

        phase_start_ptr, phase_end_ptr = task_phase_weeks_pointers[i]
        phase_weeks = task_phase_weeks_flat[phase_start_ptr:phase_end_ptr]

        effective_weeks = raw_weeks
        if phase_weeks.size > 0:
            mask = np.zeros(raw_weeks.size, dtype=np.bool_)
            for j in range(raw_weeks.size):
                for k in range(phase_weeks.size):
                    if raw_weeks[j] == phase_weeks[k]:
                        mask[j] = True
                        break
            effective_weeks = raw_weeks[mask]

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

        if course_time_array[course_group_id, 0] == -1:
            course_time_array[course_group_id, 0] = course_group_id
            course_time_array[course_group_id, 1] = 0
        time_count = course_time_array[course_group_id, 1]
        if time_count < max_phases_per_course:
            pos = 2 + 2 * time_count
            course_time_array[course_group_id, pos] = d_idx
            course_time_array[course_group_id, pos + 1] = p_idx
            course_time_array[course_group_id, 1] += 1

    penalty = 0.0

    for grid in (teacher_grid, subgroup_grid):
        for val in grid.flat:
            if val > 1:
                penalty += (val - 1) * 10000

    for val in room_grid.flat:
        if val > 1:
            penalty += (val - 1) * 8000

    for val in lab_usage_grid.flat:
        if val > max_labs_simultaneously:
            penalty += (val - max_labs_simultaneously) * 7000

    time_diff_penalty_weight = 100.0
    for c in range(num_course_groups):
        time_count = course_time_array[c, 1]
        if time_count <= 1: continue
        base_d, base_p = course_time_array[c, 2], course_time_array[c, 3]
        for i in range(1, time_count):
            pos = 2 + 2 * i
            current_d, current_p = course_time_array[c, pos], course_time_array[c, pos + 1]
            if current_d != base_d: penalty += time_diff_penalty_weight * abs(current_d - base_d)
            if current_p != base_p: penalty += time_diff_penalty_weight * abs(current_p - base_p)

    progress = current_generation / max_generations
    soft_constraint_weight = 0.1 + progress * 0.9

    for i in range(len(individual)):
        gene = individual[i]
        _, d_idx, p_idx, _ = slot_decode_map[gene]

        if undesired_masks[i, d_idx, p_idx]: penalty += 1000.0 * soft_constraint_weight
        if preferred_masks[i, d_idx, p_idx]: penalty -= 50.0 * soft_constraint_weight

        if d_idx == 3: penalty += 30 * soft_constraint_weight
        if p_idx == 0: penalty += 10 * soft_constraint_weight

    for val in day_course_counter.flat:
        if val > 1: penalty += (val - 1) * 200 * soft_constraint_weight

    for sg_idx in range(subgroup_grid.shape[0]):
        for w_idx in range(semester_weeks_len):
            for d_idx in range(subgroup_grid.shape[2]):
                day_schedule = subgroup_grid[sg_idx, w_idx, d_idx]
                if np.count_nonzero(day_schedule[:4]) == 4: penalty += 10 * soft_constraint_weight
                if np.count_nonzero(day_schedule[4:8]) == 4: penalty += 10 * soft_constraint_weight
    return penalty,


def evaluate_individual_standalone(individual, generation_info, max_gen, **kwargs):
    current_gen = generation_info[0]
    return calculate_fitness_jit(np.array(individual, dtype=np.int32), current_generation=current_gen,
                                 max_generations=max_gen, **kwargs)


class DeapScheduler:
    def __init__(self, teachers, rooms, subgroups, teaching_classes, tc_to_sg_map, fixed_schedule, teacher_preferences):
        self.MAX_LABS_SIMULTANEOUSLY = 2
        self.POP_SIZE, self.MAX_GEN, self.CXPB, self.MUTPB, self.HALL_OF_FAME_SIZE = 1000, 1500, 0.9, 0.4, 10
        self.generation_info = [0]
        self.teachers, self.rooms, self.subgroups, self.teaching_classes = teachers, rooms, subgroups, teaching_classes
        self.tc_to_sg_map, self.fixed_schedule = tc_to_sg_map, fixed_schedule

        self._prepare_mappings()
        self._create_scheduling_tasks()
        self._prepare_jit_parameters()
        self._setup_deap_toolbox()

    def _prepare_mappings(self):
        self.teacher_to_idx = {t.name: i for i, t in enumerate(self.teachers)}
        self.subgroup_to_idx = {sg.id: i for i, sg in enumerate(self.subgroups)}
        self.room_to_idx = {r.id: i for i, r in enumerate(self.rooms)}
        self.lab_room_indices = [self.room_to_idx[r.id] for r in self.rooms]

    def _create_scheduling_tasks(self):
        self.tasks = []
        for tc in self.teaching_classes:
            reqs = tc.course.get_schedule_requirements()
            phase_weeks = tc.get_effective_weeks() if hasattr(tc, 'get_effective_weeks') else []
            for part_key, req_data in reqs.items():
                req = req_data.copy()
                req['phase_weeks'] = phase_weeks
                is_lab = 'lab' in part_key
                weekly_sessions = req.get('weekly_sessions', 1)
                for session_idx in range(weekly_sessions):
                    task_req = req.copy()
                    task_req['session_idx'] = session_idx
                    task_req['time_consistency_group_key'] = f"{tc.id}_{part_key}_{session_idx}"
                    self.tasks.append({'tc': tc, 'is_lab': is_lab, 'req': task_req})

    def _prepare_jit_parameters(self):
        self.jit_params = {}

        self.weeks_patterns = {
            'weekly': SEMESTER_WEEKS, 'single_week': SINGLE_WEEKS, 'double_week': DOUBLE_WEEKS,
            'weeks_1_to_14': WEEKS_1_TO_14, 'weeks_5_to_15': WEEKS_5_TO_15, 'weeks_5_to_16': WEEKS_5_TO_16,
            'weeks_5_to_17': WEEKS_5_TO_17,
            'weeks_6_to_17': WEEKS_6_TO_17, 'weeks_1_to_8': WEEKS_1_TO_8, 'weeks_9_to_16': WEEKS_9_TO_16,
            'weeks_16_to_17': WEEKS_16_TO_17,
            'graduation_48h': WEEKS_5_TO_16,
            'graduation_32h_main': WEEKS_5_TO_15,
        }
        self.pattern_map = {name: i for i, name in enumerate(self.weeks_patterns.keys())}

        all_weeks_flat, all_weeks_pointers = [], []
        cursor = 0
        for name in self.pattern_map.keys():
            weeks = [w - 1 for w in self.weeks_patterns[name]]
            all_weeks_flat.extend(weeks)
            all_weeks_pointers.append((cursor, cursor + len(weeks)))
            cursor += len(weeks)

        self.jit_params['all_weeks_patterns_flat'] = np.array(all_weeks_flat, dtype=np.int32)
        self.jit_params['all_weeks_patterns_pointers'] = np.array(all_weeks_pointers, dtype=np.int32)

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

        tasks_meta_list, task_phase_weeks_flat, task_phase_weeks_pointers, phase_cursor = [], [], [], 0
        course_group_map, course_group_ids = {}, []

        fixed_slots_by_sg = defaultdict(set)
        cohort_sgs_map = defaultdict(list)
        for sg in self.subgroups:
            cohort_sgs_map[sg.cohort.id].append(sg)

        for item in self.fixed_schedule:
            weeks, st, dur = item['week'], item['start_time'], item['duration']
            d_idx, p_start_idx = st.day - 1, st.period - 1
            w_indices = [w - 1 for w in weeks if 1 <= w <= len(ALL_WEEKS)]
            p_indices = list(range(p_start_idx, p_start_idx + dur))

            if not w_indices or not p_indices or p_indices[-1] >= len(PERIODS): continue

            sg_ids = item.get('subgroup_ids')
            if sg_ids is not None:
                relevant_sgs = [sg for sg in self.subgroups if sg.id in sg_ids]
            else:
                sgs = cohort_sgs_map.get(item.get('cohort_id'), [])
                tag = item.get('group_tag')
                if tag and tag != 'default':
                    relevant_sgs = [sg for sg in sgs if
                                    hasattr(sg, 'fixed_schedule_tag') and sg.fixed_schedule_tag == tag]
                    if not relevant_sgs: relevant_sgs = sgs
                else:
                    relevant_sgs = sgs

            for sg in relevant_sgs:
                sg_idx = self.subgroup_to_idx.get(sg.id)
                if sg_idx is not None:
                    for w_idx in w_indices:
                        for p_idx in p_indices:
                            fixed_slots_by_sg[sg_idx].add((w_idx, d_idx, p_idx))

        teacher_objs = {t.name: t for t in self.teachers}

        for task in self.tasks:
            valid_genes, req, is_lab, tc = [], task['req'], task['is_lab'], task['tc']

            teacher = teacher_objs.get(tc.teacher_name)
            is_campus = teacher.is_campus_teacher if teacher else False
            raw_undesired = set(teacher.undesired_slots) if teacher else set()
            raw_preferred = set(teacher.preferred_slots) if teacher else set()

            def is_in_slots(cp, slots_set):
                return cp in slots_set or (cp[0], -1) in slots_set

            group_key = req['time_consistency_group_key']
            if group_key not in course_group_map: course_group_map[group_key] = len(course_group_map)
            course_group_ids.append(course_group_map[group_key])

            pattern = req.get('pattern', 'weekly')
            if pattern == 'flexible_48h': pattern = 'weekly'
            p_indices_to_try = [self.pattern_map[p] for p in ['single_week', 'double_week']] if pattern in [
                'single_week', 'double_week'] else [self.pattern_map.get(pattern, 0)]
            hours_per_block = req.get('hours_per_block', 2)
            valid_starts = VALID_START_PERIODS_2_HOURS if hours_per_block == 2 else VALID_START_PERIODS_3_HOURS
            task_sg_indices = [self.subgroup_to_idx.get(sg.id) for sg in self.tc_to_sg_map.get(tc.id, []) if
                               self.subgroup_to_idx.get(sg.id) is not None]
            phase_weeks = req.get('phase_weeks', [])

            for p_idx_val in p_indices_to_try:
                pattern_weeks_0based = [w - 1 for w in self.weeks_patterns[list(self.pattern_map.keys())[p_idx_val]]]
                effective_weeks = [w for w in pattern_weeks_0based if
                                   w in set(w - 1 for w in phase_weeks)] if phase_weeks else pattern_weeks_0based

                for d in DAYS:
                    for p in valid_starts:
                        if p + hours_per_block - 1 > len(PERIODS): continue

                        covered_periods = [(d, p + offset) for offset in range(hours_per_block)]

                        if is_campus and any(is_in_slots(cp, raw_undesired) for cp in covered_periods) and not any(
                                is_in_slots(cp, raw_preferred) for cp in covered_periods):
                            continue

                        d_0based, p_0based = d - 1, p - 1

                        has_fixed_conflict = False
                        for sg_idx in task_sg_indices:
                            if sg_idx in fixed_slots_by_sg:
                                fixed_slots = fixed_slots_by_sg[sg_idx]
                                for w_idx in effective_weeks:
                                    for p_offset in range(hours_per_block):
                                        if (w_idx, d_0based, p_0based + p_offset) in fixed_slots:
                                            has_fixed_conflict = True
                                            break
                                    if has_fixed_conflict: break
                            if has_fixed_conflict: break

                        if has_fixed_conflict:
                            continue

                        room_options = self.lab_room_indices if is_lab else [-1]
                        for r_idx in room_options:
                            gene = slot_encode_map.get((p_idx_val, d_0based, p_0based, r_idx))
                            if gene is not None: valid_genes.append(gene)

            self.task_to_valid_slots.append(np.array(valid_genes, dtype=np.int32))

            is_campus_teacher = 1 if tc.course.is_taught_by_campus_teacher(tc.teacher_name) else 0
            tasks_meta_list.append([
                self.teacher_to_idx.get(tc.teacher_name, -1), 1 if is_lab else 0, hours_per_block,
                0, is_campus_teacher, self.pattern_map.get(pattern, 0)
            ])

            if phase_weeks:
                phase_weeks_0based = [w - 1 for w in phase_weeks]
                task_phase_weeks_flat.extend(phase_weeks_0based)
                task_phase_weeks_pointers.append((phase_cursor, phase_cursor + len(phase_weeks_0based)))
                phase_cursor += len(phase_weeks_0based)
            else:
                task_phase_weeks_pointers.append((phase_cursor, phase_cursor))

        task_group_map = {}
        for i, task in enumerate(self.tasks):
            key = (task['tc'].course.id, task['is_lab'])
            task_group_map.setdefault(key, len(task_group_map))
            tasks_meta_list[i][3] = task_group_map[key]
        self.jit_params['num_task_groups'] = len(task_group_map)
        self.jit_params['course_group_ids'] = np.array(course_group_ids, dtype=np.int32)
        self.jit_params['num_course_groups'] = len(course_group_map)

        sg_indices_flat, sg_pointers, cursor = [], [], 0
        for task in self.tasks:
            indices = [self.subgroup_to_idx.get(sg.id) for sg in self.tc_to_sg_map.get(task['tc'].id, []) if
                       self.subgroup_to_idx.get(sg.id) is not None]
            sg_indices_flat.extend(indices)
            sg_pointers.append((cursor, cursor + len(indices)))
            cursor += len(indices)

        grid_shape = (len(ALL_WEEKS), len(DAYS), len(PERIODS))
        grids = {
            'fixed_teacher_grid': np.zeros((len(self.teachers),) + grid_shape, dtype=np.int32),
            'fixed_subgroup_grid': np.zeros((len(self.subgroups),) + grid_shape, dtype=np.int32),
            'fixed_room_grid': np.zeros((len(self.rooms),) + grid_shape, dtype=np.int32),
            'fixed_lab_usage_grid': np.zeros(grid_shape, dtype=np.int32),
            'undesired_masks': np.zeros((len(self.tasks), len(DAYS), len(PERIODS)), dtype=bool),
            'preferred_masks': np.zeros((len(self.tasks), len(DAYS), len(PERIODS)), dtype=bool)
        }

        for item in self.fixed_schedule:
            weeks, st, dur = item['week'], item['start_time'], item['duration']
            t_idx = self.teacher_to_idx.get(item['teacher_name'])
            d_idx, p_start_idx = st.day - 1, st.period - 1
            is_lab_item = item.get('is_lab', False)
            room_name = item.get('room_name')
            w_indices = [w - 1 for w in weeks if 1 <= w <= grid_shape[0]]
            p_indices = list(range(p_start_idx, p_start_idx + dur))

            if not w_indices or not p_indices or p_indices[-1] >= len(PERIODS): continue

            if t_idx is not None:
                grids['fixed_teacher_grid'][np.ix_([t_idx], w_indices, [d_idx], p_indices)] = 1

            sg_ids = item.get('subgroup_ids')
            if sg_ids is not None:
                relevant_sgs = [sg for sg in self.subgroups if sg.id in sg_ids]
            else:
                sgs = cohort_sgs_map.get(item.get('cohort_id'), [])
                tag = item.get('group_tag')
                if tag and tag != 'default':
                    relevant_sgs = [sg for sg in sgs if
                                    hasattr(sg, 'fixed_schedule_tag') and sg.fixed_schedule_tag == tag]
                    if not relevant_sgs: relevant_sgs = sgs
                else:
                    relevant_sgs = sgs

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

        for i, task in enumerate(self.tasks):
            tc = task['tc']
            duration = task['req'].get('hours_per_block', 2)
            teacher = teacher_objs.get(tc.teacher_name)

            if teacher:
                raw_undesired = set(teacher.undesired_slots)
                raw_preferred = set(teacher.preferred_slots)

                def is_in_slots(cp, slots_set):
                    return cp in slots_set or (cp[0], -1) in slots_set

                for d in DAYS:
                    for p in PERIODS:
                        if p + duration - 1 > len(PERIODS): continue

                        d_idx, p_idx = d - 1, p - 1
                        covered = [(d, p + offset) for offset in range(duration)]

                        is_pref = any(is_in_slots(cp, raw_preferred) for cp in covered)
                        is_undes = any(is_in_slots(cp, raw_undesired) for cp in covered) and not is_pref

                        if is_undes:
                            grids['undesired_masks'][i, d_idx, p_idx] = True

                        if is_pref:
                            grids['preferred_masks'][i, d_idx, p_idx] = True

        self.jit_params['tasks_meta'] = np.array(tasks_meta_list, dtype=np.int32)
        self.jit_params['task_to_sg_indices_flat'] = np.array(sg_indices_flat, dtype=np.int32)
        self.jit_params['task_to_sg_pointers'] = np.array(sg_pointers, dtype=np.int32)
        self.jit_params['task_phase_weeks_flat'] = np.array(task_phase_weeks_flat, dtype=np.int32)
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
        if not hasattr(creator, "FitnessMin"):
            creator.create("FitnessMin", base.Fitness, weights=(-1.0,))
        if not hasattr(creator, "Individual"):
            creator.create("Individual", list, fitness=creator.FitnessMin)
        self.toolbox = base.Toolbox()

        self.toolbox.register("individual_generator", lambda: [
            random.choice(self.task_to_valid_slots[i]) if i < len(self.task_to_valid_slots) and
                                                          self.task_to_valid_slots[i].size > 0
            else random.randint(0, len(self.slot_decode_map_list) - 1)
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
                else:
                    individual[i] = random.randint(0, len(self.slot_decode_map_list) - 1)
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

            worst_in_pop_indices = sorted(range(len(pop)), key=lambda k: pop[k].fitness, reverse=True)
            for i in range(min(len(worst_in_pop_indices), self.HALL_OF_FAME_SIZE)):
                pop[worst_in_pop_indices[i]] = copy.deepcopy(hof[i])

            if gen % 10 == 0:
                custom_log(pop, gen, stats, hof)

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

        self.penalty_details = self._analyze_penalty_details(self.best_individual)

        return self.best_fitness < 5000

    def _analyze_penalty_details(self, individual):
        if not individual:
            return {}

        slot_decode_map = np.array(self.slot_decode_map_list, dtype=np.int32)
        tasks_meta = self.jit_params['tasks_meta']
        course_group_ids = self.jit_params['course_group_ids']
        num_course_groups = self.jit_params['num_course_groups']
        num_task_groups = self.jit_params['num_task_groups']
        semester_weeks_len = self.jit_params['semester_weeks_len']

        teacher_grid = self.jit_params['flat_fixed_teacher_grid'].reshape(
            self.jit_params['shape_fixed_teacher_grid']).copy()
        subgroup_grid = self.jit_params['flat_fixed_subgroup_grid'].reshape(
            self.jit_params['shape_fixed_subgroup_grid']).copy()
        room_grid = self.jit_params['flat_fixed_room_grid'].reshape(self.jit_params['shape_fixed_room_grid']).copy()
        lab_usage_grid = self.jit_params['flat_fixed_lab_usage_grid'].reshape(
            self.jit_params['shape_fixed_lab_usage_grid']).copy()

        sg_indices_flat = self.jit_params['task_to_sg_indices_flat']
        sg_pointers = self.jit_params['task_to_sg_pointers']
        all_weeks_flat = self.jit_params['all_weeks_patterns_flat']
        all_weeks_pointers = self.jit_params['all_weeks_patterns_pointers']
        phase_weeks_flat = self.jit_params['task_phase_weeks_flat']
        phase_weeks_pointers = self.jit_params['task_phase_weeks_pointers']
        undesired_masks = self.jit_params['flat_undesired_masks'].reshape(self.jit_params['shape_undesired_masks'])
        preferred_masks = self.jit_params['flat_preferred_masks'].reshape(self.jit_params['shape_preferred_masks'])

        day_course_counter = np.zeros((len(self.subgroups), semester_weeks_len, len(DAYS), num_task_groups),
                                      dtype=np.int32)
        course_time_array = np.full((num_course_groups, 2 + 2 * 10), -1, dtype=np.int32)

        task_assignments = []

        for i, gene in enumerate(individual):
            pattern_idx, d_idx, p_idx, r_idx = slot_decode_map[gene]
            t_idx, is_lab, duration, task_group_id = tasks_meta[i, 0], tasks_meta[i, 1], tasks_meta[i, 2], tasks_meta[
                i, 3]
            course_group_id = course_group_ids[i]

            sg_start, sg_end = sg_pointers[i]
            sg_indices = sg_indices_flat[sg_start:sg_end]

            wp_start, wp_end = all_weeks_pointers[pattern_idx]
            raw_weeks = all_weeks_flat[wp_start:wp_end]

            pw_start, pw_end = phase_weeks_pointers[i]
            effective_weeks = list(raw_weeks)
            if pw_end > pw_start:
                phase_weeks = set(phase_weeks_flat[pw_start:pw_end])
                effective_weeks = [w for w in raw_weeks if w in phase_weeks]

            task_assignments.append({'task_idx': i, 'd_idx': d_idx, 'p_idx': p_idx, 'effective_weeks': effective_weeks})

            for w_idx in effective_weeks:
                for p_offset in range(duration):
                    current_p = p_idx + p_offset
                    if current_p < len(PERIODS):
                        if t_idx != -1: teacher_grid[t_idx, w_idx, d_idx, current_p] += 1
                        for sg_idx in sg_indices: subgroup_grid[sg_idx, w_idx, d_idx, current_p] += 1
                        if is_lab == 1:
                            lab_usage_grid[w_idx, d_idx, current_p] += 1
                            if r_idx != -1: room_grid[r_idx, w_idx, d_idx, current_p] += 1

                if w_idx < semester_weeks_len:
                    for sg_idx in sg_indices: day_course_counter[sg_idx, w_idx, d_idx, task_group_id] += 1

            if course_time_array[course_group_id, 0] == -1:
                course_time_array[course_group_id, 0] = course_group_id
                course_time_array[course_group_id, 1] = 0
            time_count = course_time_array[course_group_id, 1]
            if time_count < 9:
                pos = 2 + 2 * time_count
                course_time_array[course_group_id, pos] = d_idx
                course_time_array[course_group_id, pos + 1] = p_idx
                course_time_array[course_group_id, 1] += 1

        details = {
            'hard_constraints': {}, 'soft_constraints': {}, 'teacher_conflicts': [],
            'subgroup_conflicts': [], 'room_conflicts': [], 'summary': {}
        }

        teacher_conflict_count, teacher_conflict_penalty = 0, 0
        for t_idx, w_idx, d_idx, p_idx in np.argwhere(teacher_grid > 1):
            val = teacher_grid[t_idx, w_idx, d_idx, p_idx]
            teacher_conflict_count += 1
            penalty = (val - 1) * 10000
            teacher_conflict_penalty += penalty
            teacher_name = next((name for name, idx in self.teacher_to_idx.items() if idx == t_idx), f"教师{t_idx}")
            if len(details['teacher_conflicts']) < 20:
                details['teacher_conflicts'].append({
                    'type': '教师冲突', 'teacher': teacher_name, 'week': int(w_idx + 1), 'day': int(d_idx + 1),
                    'period': int(p_idx + 1), 'conflict_count': int(val), 'penalty': int(penalty),
                    'desc': f"{teacher_name} 在第{w_idx + 1}周 周{['一', '二', '三', '四', '五'][d_idx]} 第{p_idx + 1}节 同时有{val}门课"
                })

        subgroup_conflict_count, subgroup_conflict_penalty = 0, 0
        for sg_idx, w_idx, d_idx, p_idx in np.argwhere(subgroup_grid > 1):
            val = subgroup_grid[sg_idx, w_idx, d_idx, p_idx]
            subgroup_conflict_count += 1
            penalty = (val - 1) * 10000
            subgroup_conflict_penalty += penalty
            sg_id = next((sid for sid, idx in self.subgroup_to_idx.items() if idx == sg_idx), f"子组{sg_idx}")
            if len(details['subgroup_conflicts']) < 20:
                details['subgroup_conflicts'].append({
                    'type': '学生冲突', 'subgroup': sg_id, 'week': int(w_idx + 1), 'day': int(d_idx + 1),
                    'period': int(p_idx + 1), 'conflict_count': int(val), 'penalty': int(penalty),
                    'desc': f"{sg_id} 在第{w_idx + 1}周 周{['一', '二', '三', '四', '五'][d_idx]} 第{p_idx + 1}节 同时有{val}门课"
                })

        room_conflict_count, room_conflict_penalty = 0, 0
        for r_idx, w_idx, d_idx, p_idx in np.argwhere(room_grid > 1):
            val = room_grid[r_idx, w_idx, d_idx, p_idx]
            room_conflict_count += 1
            penalty = (val - 1) * 8000
            room_conflict_penalty += penalty
            room_id = next((rid for rid, idx in self.room_to_idx.items() if idx == r_idx), None)
            room_name = next((r.name for r in self.rooms if r.id == room_id),
                             f"机房{r_idx}") if room_id else f"机房{r_idx}"
            if len(details['room_conflicts']) < 20:
                details['room_conflicts'].append({
                    'type': '机房冲突', 'room': room_name, 'week': int(w_idx + 1), 'day': int(d_idx + 1),
                    'period': int(p_idx + 1), 'conflict_count': int(val), 'penalty': int(penalty),
                    'desc': f"{room_name} 在第{w_idx + 1}周 周{['一', '二', '三', '四', '五'][d_idx]} 第{p_idx + 1}节 同时有{val}节课"
                })

        details['hard_constraints'] = {
            'teacher_conflict': {'count': teacher_conflict_count, 'penalty': teacher_conflict_penalty, 'weight': 10000,
                                 'desc': '教师时间冲突'},
            'subgroup_conflict': {'count': subgroup_conflict_count, 'penalty': subgroup_conflict_penalty,
                                  'weight': 10000, 'desc': '学生时间冲突'},
            'room_conflict': {'count': room_conflict_count, 'penalty': room_conflict_penalty, 'weight': 8000,
                              'desc': '机房时间冲突'},
        }

        soft_weight, day_names = 1.0, ['一', '二', '三', '四', '五']

        def get_task_info(task_idx):
            task = self.tasks[task_idx]
            tc, cohort_name = task['tc'], ''
            sgs = self.tc_to_sg_map.get(tc.id, [])
            if sgs and hasattr(sgs[0], 'cohort') and sgs[0].cohort:
                cohort = sgs[0].cohort
                cohort_name = f"{cohort.major}{cohort.grade}"
            return {'course_name': tc.course.name, 'teacher_name': tc.teacher_name, 'cohort_name': cohort_name,
                    'class_name': tc.name if hasattr(tc, 'name') else str(tc.id), 'is_lab': task['is_lab']}

        time_diff_details, undesired_slot_details, preferred_details, thursday_details, first_period_details, same_day_course_details, consecutive_4_details = [], [], [], [], [], [], []

        course_group_to_tasks = defaultdict(list)
        for i, gene in enumerate(individual):
            course_group_id = course_group_ids[i]
            _, d_idx, p_idx, _ = slot_decode_map[gene]
            course_group_to_tasks[course_group_id].append((i, d_idx, p_idx))

        time_diff_penalty, time_diff_count, time_diff_weight = 0, 0, 100.0
        for c in range(num_course_groups):
            time_count = course_time_array[c, 1]
            if time_count <= 1: continue

            task_indices = course_group_to_tasks.get(c, [])
            if not task_indices: continue

            # 【重要过滤】：跳过校本部老师的软约束分析记录
            is_campus_teacher = tasks_meta[task_indices[0][0], 4] == 1
            if is_campus_teacher: continue

            base_d, base_p = course_time_array[c, 2], course_time_array[c, 3]
            has_diff = False
            for i in range(1, time_count):
                current_d, current_p = course_time_array[c, 2 + 2 * i], course_time_array[c, 3 + 2 * i]
                if current_d != base_d: time_diff_penalty += time_diff_weight * abs(current_d - base_d); has_diff = True
                if current_p != base_p: time_diff_penalty += time_diff_weight * abs(current_p - base_p); has_diff = True

            if has_diff:
                time_diff_count += 1
                task_info, times = get_task_info(task_indices[0][0]), [f"周{day_names[d]}第{p + 1}节" for _, d, p in
                                                                       task_indices]
                cohort_str = f"[{task_info['cohort_name']}] " if task_info['cohort_name'] else ''
                time_diff_details.append({'course': task_info['course_name'], 'teacher': task_info['teacher_name'],
                                          'times': times,
                                          'desc': f"{cohort_str}{task_info['course_name']} 分阶段时间不同: {' → '.join(times)}"})

        undesired_slot_penalty, undesired_slot_count, undesired_weight = 0, 0, 1000.0
        for i, gene in enumerate(individual):
            _, d_idx, p_idx, _ = slot_decode_map[gene]

            # 【重要过滤】：全面防泄漏校本部偏好被软判定抓取
            is_campus_teacher = tasks_meta[i, 4] == 1
            if is_campus_teacher: continue

            if undesired_masks[i, d_idx, p_idx]:
                undesired_slot_penalty += undesired_weight * soft_weight
                undesired_slot_count += 1
                task_info = get_task_info(i)
                cohort_str = f"[{task_info['cohort_name']}] " if task_info['cohort_name'] else ''
                undesired_slot_details.append({
                    'desc': f"{cohort_str}{task_info['course_name']} 在不希望的时间: 周{day_names[d_idx]}第{p_idx + 1}节"})

        preferred_reward, preferred_count, preferred_weight = 0, 0, -50.0
        for i, gene in enumerate(individual):
            _, d_idx, p_idx, _ = slot_decode_map[gene]

            is_campus_teacher = tasks_meta[i, 4] == 1
            if is_campus_teacher: continue

            if preferred_masks[i, d_idx, p_idx]:
                preferred_reward += preferred_weight * soft_weight
                preferred_count += 1
                task_info = get_task_info(i)
                cohort_str = f"[{task_info['cohort_name']}] " if task_info['cohort_name'] else ''
                preferred_details.append({
                    'desc': f"{cohort_str}{task_info['course_name']} 安排在偏好时间(奖励): 周{day_names[d_idx]}第{p_idx + 1}节"})

        thursday_penalty, thursday_count, thursday_weight = 0, 0, 30.0
        for i, gene in enumerate(individual):
            is_campus_teacher = tasks_meta[i, 4] == 1
            if is_campus_teacher: continue

            _, d_idx, _, _ = slot_decode_map[gene]
            if d_idx == 3: thursday_penalty += thursday_weight * soft_weight; thursday_count += 1

        first_period_penalty, first_period_count, first_period_weight = 0, 0, 10.0
        for i, gene in enumerate(individual):
            is_campus_teacher = tasks_meta[i, 4] == 1
            if is_campus_teacher: continue

            _, _, p_idx, _ = slot_decode_map[gene]
            if p_idx == 0: first_period_penalty += first_period_weight * soft_weight; first_period_count += 1

        same_day_course_penalty, same_day_course_count, same_day_weight = np.sum(
            (day_course_counter - 1)[day_course_counter > 1]) * 200 * soft_weight, np.count_nonzero(
            day_course_counter > 1), 200.0

        consecutive_4_penalty, consecutive_4_count, consecutive_weight = 0, 0, 10.0
        for sg_idx in range(subgroup_grid.shape[0]):
            for w_idx in range(semester_weeks_len):
                for d_idx in range(subgroup_grid.shape[2]):
                    day_schedule = subgroup_grid[sg_idx, w_idx, d_idx]
                    if np.count_nonzero(day_schedule[:4]) == 4:
                        consecutive_4_penalty += consecutive_weight * soft_weight;
                        consecutive_4_count += 1
                    if np.count_nonzero(day_schedule[4:8]) == 4:
                        consecutive_4_penalty += consecutive_weight * soft_weight;
                        consecutive_4_count += 1

        details['soft_constraints'] = {
            'time_diff': {'count': time_diff_count, 'penalty': round(time_diff_penalty, 2), 'weight': time_diff_weight,
                          'desc': '分阶段上课时间不同', 'items': time_diff_details},
            'undesired_slot': {'count': undesired_slot_count, 'penalty': round(undesired_slot_penalty, 2),
                               'weight': undesired_weight, 'desc': '安排在不希望的时间',
                               'items': undesired_slot_details},
            'preferred_reward': {'count': preferred_count, 'penalty': round(preferred_reward, 2),
                                 'weight': preferred_weight, 'desc': '安排在偏好时间(奖励)',
                                 'items': preferred_details},
            'thursday': {'count': thursday_count, 'penalty': round(thursday_penalty, 2), 'weight': thursday_weight,
                         'desc': '周四排课'},
            'first_period': {'count': first_period_count, 'penalty': round(first_period_penalty, 2),
                             'weight': first_period_weight, 'desc': '第一节课'},
            'same_day_course': {'count': int(same_day_course_count), 'penalty': round(same_day_course_penalty, 2),
                                'weight': same_day_weight, 'desc': '同天同课多次'},
            'consecutive_4': {'count': consecutive_4_count, 'penalty': round(consecutive_4_penalty, 2),
                              'weight': consecutive_weight, 'desc': '连续4节课'},
        }

        hard_total = teacher_conflict_penalty + subgroup_conflict_penalty + room_conflict_penalty
        soft_total = sum(v['penalty'] for v in details['soft_constraints'].values())

        details['summary'] = {'total_penalty': round(float(self.best_fitness), 2),
                              'hard_constraint_penalty': round(hard_total, 2),
                              'soft_constraint_penalty': round(soft_total, 2), }
        return details

    def get_penalty_details(self):
        return getattr(self, 'penalty_details', {})

    def cleanup(self):
        if hasattr(self, 'jit_params'): self.jit_params.clear()
        if hasattr(self, 'task_to_valid_slots'): self.task_to_valid_slots.clear()
        if hasattr(self, 'slot_decode_map_list'): self.slot_decode_map_list.clear()
        if hasattr(self, 'tasks'): self.tasks.clear()
        if hasattr(self, 'toolbox'): self.toolbox.unregister("map"); del self.toolbox
        import gc
        gc.collect()

    def get_results(self):
        if not hasattr(self, 'best_individual') or not self.best_individual: return []
        results = []
        slot_decode_map = np.array(self.slot_decode_map_list, dtype=np.int32)
        if slot_decode_map.shape[0] == 0: return []

        pattern_name_list = list(self.pattern_map.keys())

        for i, gene in enumerate(self.best_individual):
            task, req = self.tasks[i], self.tasks[i]['req']
            tc, is_lab = task['tc'], task['is_lab']

            week_pattern_idx, d_idx, period_idx, r_idx = slot_decode_map[gene]

            pattern_name = pattern_name_list[week_pattern_idx]
            raw_weeks = self.weeks_patterns.get(pattern_name, SEMESTER_WEEKS)
            phase_weeks = req.get('phase_weeks', [])

            effective_weeks = [w for w in raw_weeks if w in set(phase_weeks)] if phase_weeks else raw_weeks

            room_name = None
            if is_lab and r_idx != -1:
                room_id = next((rid for rid, idx in self.room_to_idx.items() if idx == r_idx), None)
                if room_id: room_name = next((r.name for r in self.rooms if r.id == room_id), None)

            day_val, period_val, duration_val = int(d_idx) + 1, int(period_idx) + 1, int(req.get('hours_per_block', 2))

            for week in effective_weeks:
                week_val = int(week) if hasattr(week, 'item') else week
                results.append({
                    "teaching_class_id": tc.id, "course_name": tc.course.name, "teacher_name": tc.teacher_name,
                    "time_point": TimePoint(week=week_val, day=day_val, period=period_val),
                    "duration": duration_val, "room_name": room_name,
                    "is_lab": bool(is_lab), "is_combined": bool(tc.is_combined)
                })
        return results