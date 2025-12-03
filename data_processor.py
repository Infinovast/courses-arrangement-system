from fractions import Fraction
from typing import Dict, List
import numpy as np
from collections import defaultdict
from models.course import Course
from models.class_group import SubGroup, TeachingClass, Cohort


class DataPreprocessor:
    def __init__(self, teachers_list, cohorts_list, course_by_cohort, teacher_course_map, subgroup_pre_assignment=None):
        self.teachers_map = {t.id: t for t in teachers_list}
        self.cohorts_list = cohorts_list
        self.course_by_cohort = course_by_cohort
        self.teacher_course_map = teacher_course_map
        self.subgroup_pre_assignment = subgroup_pre_assignment if subgroup_pre_assignment else {}
        self.course_by_id = {c.id: c for courses in course_by_cohort.values() for c in courses}

    def process_data(self):
        lcm_per_cohort, combined_groups = self._calculate_subgroup_counts()
        all_subgroups, subgroups_by_cohort = self._create_subgroups(lcm_per_cohort)
        self._assign_tags_to_subgroups(subgroups_by_cohort)
        all_teaching_classes, tc_to_sg_map = self._create_teaching_classes(
            lcm_per_cohort, combined_groups, subgroups_by_cohort
        )

        return all_subgroups, all_teaching_classes, dict(tc_to_sg_map)

    def _calculate_subgroup_counts(self):
        lcm_per_cohort = defaultdict(int)
        combined_groups = {}

        for cohort, courses in self.course_by_cohort.items():
            for course in courses:
                if course.combined_with:
                    group_key = tuple(sorted([course.id] + course.combined_with))
                    if group_key not in combined_groups:
                        combined_groups[group_key] = {'courses': set(), 'cohorts': set()}
                    combined_groups[group_key]['courses'].add(course.id)
                    combined_groups[group_key]['cohorts'].add(cohort)

        combined_group_reqs = {}
        for group_key, group_data in combined_groups.items():
            group_courses = [self.course_by_id[c_id] for c_id in group_data['courses']]
            total_tc_frac = sum(Fraction(c.teaching_class_count) for c in group_courses)
            if total_tc_frac.numerator == 0: continue
            denominators = [Fraction(c.teaching_class_count).denominator for c in group_courses if
                            c.teaching_class_count > 0]
            lcm_den = np.lcm.reduce(denominators) if denominators else 1
            req_sgs = int(total_tc_frac.numerator * (lcm_den // total_tc_frac.denominator))
            combined_group_reqs[group_key] = req_sgs

        for cohort in self.cohorts_list:
            courses = self.course_by_cohort.get(cohort, [])
            normal_counts = [int(c.teaching_class_count) for c in courses if not c.combined_with and Fraction(
                c.teaching_class_count).denominator == 1 and c.teaching_class_count > 0]
            lcm_normal = np.lcm.reduce(normal_counts) if normal_counts else 1

            max_lcm_combined = 0
            for group_key, group_data in combined_groups.items():
                if cohort in group_data['cohorts']:
                    max_lcm_combined = max(max_lcm_combined, combined_group_reqs.get(group_key, 0))

            lcm_per_cohort[cohort] = max(lcm_normal, max_lcm_combined)

        return lcm_per_cohort, combined_groups

    def _create_subgroups(self, lcm_per_cohort):
        all_subgroups = []
        subgroups_by_cohort = defaultdict(list)
        for cohort, lcm in lcm_per_cohort.items():
            if lcm == 0: continue
            cohort_sgs = [SubGroup(id=f"SG_{cohort.major}{cohort.grade}_{i + 1}", cohort=cohort) for i in range(lcm)]
            subgroups_by_cohort[cohort] = cohort_sgs
            all_subgroups.extend(cohort_sgs)
        return all_subgroups, subgroups_by_cohort

    def _assign_tags_to_subgroups(self, subgroups_by_cohort: Dict[Cohort, List[SubGroup]]):
        if not self.subgroup_pre_assignment:
            return
        for cohort, subgroups in subgroups_by_cohort.items():
            assignment = self.subgroup_pre_assignment.get(cohort.id)
            if not assignment:
                continue
            num_subgroups = len(subgroups)
            if num_subgroups == 0: continue
            cursor = 0
            sorted_tags = sorted(assignment.keys())
            for i, tag in enumerate(sorted_tags):
                ratio = assignment[tag]
                if i == len(sorted_tags) - 1:
                    end_index = num_subgroups
                else:
                    count = int(round(num_subgroups * ratio))
                    end_index = cursor + count
                for j in range(cursor, end_index):
                    if j < num_subgroups:
                        subgroups[j].fixed_schedule_tag = tag
                cursor = end_index

    def _create_teaching_classes(self, lcm_per_cohort, combined_groups, subgroups_by_cohort):
        all_tc = []
        tc_to_sg_map = defaultdict(list)
        processed_groups = set()

        # 处理合班课
        for group_key, group_data in combined_groups.items():
            if group_key in processed_groups: continue

            group_courses = [self.course_by_id[c_id] for c_id in group_data['courses']]
            rep_course = group_courses[0]

            v_course_id = f"COM_{'_'.join(sorted(c.id for c in group_courses))}"
            v_course = Course(id=v_course_id, name=rep_course.name, course_type=rep_course.course_type,
                              theory_hours=max(c.theory_hours for c in group_courses),
                              lab_hours=max(c.lab_hours for c in group_courses))

            subgroup_pool = [sg for cohort in group_data['cohorts'] for sg in subgroups_by_cohort.get(cohort, [])]
            total_tc_frac = sum(Fraction(c.teaching_class_count) for c in group_courses)
            num_tc = total_tc_frac.numerator
            if num_tc == 0: continue

            sgs_per_tc = len(subgroup_pool) // num_tc
            teacher_id = self.teacher_course_map.get(rep_course.id)
            teacher_name = self.teachers_map[teacher_id].name if teacher_id else "未知"
            cursor = 0

            for i in range(num_tc):
                tc_id = f"TC_{v_course.id}_{i + 1}"
                tc = TeachingClass(id=tc_id, course=v_course, class_number=i + 1, teacher_name=teacher_name,
                                   is_combined=True)
                all_tc.append(tc)
                assigned_sgs = subgroup_pool[cursor: cursor + sgs_per_tc]
                tc_to_sg_map[tc.id].extend(assigned_sgs)
                cursor += sgs_per_tc

            processed_groups.add(group_key)

        # 处理非合班课（支持分阶段）
        for cohort, courses in self.course_by_cohort.items():
            lcm = lcm_per_cohort.get(cohort)
            if not lcm or lcm == 0: continue

            cohort_sgs = subgroups_by_cohort.get(cohort, [])
            for course in courses:
                if course.combined_with or Fraction(course.teaching_class_count).denominator != 1: continue

                num_tc = int(course.teaching_class_count)
                if num_tc == 0: continue

                sgs_per_tc = lcm // num_tc
                default_teacher_id = self.teacher_course_map.get(course.id)

                # 处理分阶段授课
                if course.phase_teachers:
                    # 为每个阶段创建独立教学班
                    for phase, (start_week, end_week, phase_teacher_id) in course.phase_teachers.items():
                        for i in range(num_tc):
                            class_number = i + 1
                            # 阶段教师优先于override
                            final_teacher_id = phase_teacher_id
                            teacher_name = self.teachers_map[final_teacher_id].name if final_teacher_id else "未知"

                            # 阶段教学班ID：原ID_阶段
                            tc_id = f"TC_{course.id}_{class_number}_{phase}"
                            tc = TeachingClass(
                                id=tc_id,
                                course=course,
                                class_number=class_number,
                                teacher_name=teacher_name,
                                is_combined=False,
                                phase=phase,
                                phase_weeks=(start_week, end_week)
                            )
                            all_tc.append(tc)
                            start, end = i * sgs_per_tc, (i + 1) * sgs_per_tc
                            tc_to_sg_map[tc.id].extend(cohort_sgs[start:end])
                else:
                    # 无分阶段
                    for i in range(num_tc):
                        class_number = i + 1
                        teacher_id_override = course.teacher_override.get(
                            class_number) if course.teacher_override else None
                        final_teacher_id = teacher_id_override if teacher_id_override else default_teacher_id

                        teacher_name = self.teachers_map[final_teacher_id].name if final_teacher_id else "未知"
                        tc_id = f"TC_{course.id}_{i + 1}"
                        tc = TeachingClass(id=tc_id, course=course, class_number=i + 1, teacher_name=teacher_name,
                                           is_combined=False)
                        all_tc.append(tc)
                        start, end = i * sgs_per_tc, (i + 1) * sgs_per_tc
                        tc_to_sg_map[tc.id].extend(cohort_sgs[start:end])

        return all_tc, tc_to_sg_map