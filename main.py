import time
import multiprocessing
import importlib
import sys

from data_processor import DataPreprocessor
from campus_pre_scheduler import CampusScheduler
from deap_scheduler import DeapScheduler
from result_parser import export_schedule_to_excel


def main():
    global campus_detailed_results, campus_fixed_results
    selected_semester = ""
    while selected_semester not in ['上册', '下册']:
        choice = input(">>> 请选择要排课的学期 (上册/下册): ").strip()
        if choice in ['上册', '下册']:
            selected_semester = choice
        else:
            print("输入无效！请输入 '上册' 或者 '下册'。")

    module_name = {'上册': 'data_setup1', '下册': 'data_setup2'}[selected_semester]
    try:
        data_module = importlib.import_module(module_name)
    except ImportError as e:
        print(f"错误：无法找到数据模块文件 {module_name}.py。 ({e})")
        sys.exit(1)

    start_time = time.time()
    print(f"\n正在加载 {selected_semester} 学期的数据 (来自 {module_name}.py)...")
    teachers_list, rooms_list, cohorts_list, admin_classes, course_by_cohort, \
        teacher_course_map, fixed_schedule, teacher_preferences, \
        subgroup_pre_assignment = data_module.get_raw_data()

    print("\n--- 阶段1: 预处理数据 ---")
    data_processor = DataPreprocessor(teachers_list, cohorts_list, course_by_cohort, teacher_course_map,
                                      subgroup_pre_assignment)
    all_subgroups, all_teaching_classes, tc_to_sg_map = data_processor.process_data()
    print(f"数据总览：共 {len(all_subgroups)} 个子组, {len(all_teaching_classes)} 个教学班。")

    print("\n--- 阶段2: 课程分离 ---")
    campus_tcs, other_tcs = [], []
    campus_teacher_names = {t.name for t in teachers_list if t.is_campus_teacher}
    for tc in all_teaching_classes:
        if tc.teacher_name in campus_teacher_names:
            if tc.teacher_name not in tc.course.campus_teachers:
                tc.course.campus_teachers.append(tc.teacher_name)
            campus_tcs.append(tc)
        else:
            other_tcs.append(tc)

    print(f"待确定性预排课的校本部教学班: {len(campus_tcs)} 个")
    print(f"待遗传算法排课的教学班: {len(other_tcs)} 个")

    print("\n--- 阶段3: 为校本部教师进行确定性排课 ---")

    for i in range(100):
        campus_scheduler = CampusScheduler(campus_tcs, all_subgroups, tc_to_sg_map, teachers_list, rooms_list,
                                       fixed_schedule)
        campus_detailed_results, campus_fixed_results, failed_campus_tcs = campus_scheduler.schedule()
        if failed_campus_tcs==[]:
            break


    print("\n--- 阶段4: 为其他教师及预排失败的课程进行遗传算法排课 ---")
    ga_tcs_to_schedule = other_tcs

    # GA的硬性约束 = 原始公共课 + 预排成功的校本部课程
    updated_fixed_schedule = fixed_schedule + campus_fixed_results

    with multiprocessing.Pool() as pool:
        scheduler = DeapScheduler(
            teachers=teachers_list,
            rooms=rooms_list,
            subgroups=all_subgroups,
            teaching_classes=ga_tcs_to_schedule,
            tc_to_sg_map=tc_to_sg_map,
            fixed_schedule=updated_fixed_schedule,
            teacher_preferences=teacher_preferences
        )
        success = scheduler.solve(pool)

        end_time = time.time()
        print(f"\n排课流程结束，总耗时: {end_time - start_time:.2f} 秒。")

        print("\n--- 阶段5: 结果合并与导出 ---")
        ga_results = scheduler.get_results()
        final_schedule_details = campus_detailed_results + ga_results

        if not final_schedule_details and not fixed_schedule:
            print("错误：未能生成任何排课结果。")
            return

        base_filename = f"Final_Schedule_{selected_semester}"
        best_fitness = getattr(scheduler, 'best_fitness', 9999)
        filename = f"{base_filename}_perfect.xlsx" if success else f"{base_filename}_Attempt.xlsx"

        if success:
            print("成功找到高质量解！")
        else:
            print(f"警告：未找到完美解。最佳方案的惩罚分数为: {best_fitness}")


        export_schedule_to_excel(
            solver_results=final_schedule_details,
            fixed_schedule=fixed_schedule,
            all_subgroups=all_subgroups,
            tc_to_sg_map=tc_to_sg_map,
            teaching_classes=all_teaching_classes,
            rooms=rooms_list,
            filename=filename,
            admin_classes=admin_classes
        )
        print(f"\n所有课表已成功导出到: {filename}")


if __name__ == '__main__':
    multiprocessing.freeze_support()
    main()