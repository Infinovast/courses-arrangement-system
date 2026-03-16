# 自动运行原始GA和Q-learning增强GA，并对比性能
import time
import multiprocessing
import importlib
import sys
from collections import defaultdict

from data_processor import DataPreprocessor
from campus_pre_scheduler import CampusScheduler
from deap_scheduler import DeapScheduler
from result_parser import export_schedule_to_excel


def run_single_algorithm(selected_semester, use_ql, algorithm_name):

    print(f"\n{'='*60}")
    print(f"  开始运行: {algorithm_name}")
    print(f"{'='*60}\n")
    
    module_name = {'上册': 'data_setup1', '下册': 'data_setup2'}[selected_semester]
    
    try:
        data_module = importlib.import_module(module_name)
    except ImportError as e:
        print(f"错误：无法找到数据模块文件 {module_name}.py。 ({e})")
        return None
    
    start_time = time.time()
    
    # 加载数据
    teachers_list, rooms_list, cohorts_list, admin_classes, course_by_cohort, \
        teacher_course_map, fixed_schedule, teacher_preferences, \
        subgroup_pre_assignment = data_module.get_raw_data()
    
    # 数据预处理
    data_processor = DataPreprocessor(teachers_list, cohorts_list, course_by_cohort, 
                                      teacher_course_map, subgroup_pre_assignment)
    all_subgroups, all_teaching_classes, tc_to_sg_map = data_processor.process_data()
    
    # 课程分离
    campus_tcs, other_tcs = [], []
    campus_teacher_names = {t.name for t in teachers_list if t.is_campus_teacher}
    for tc in all_teaching_classes:
        if tc.teacher_name in campus_teacher_names:
            if tc.teacher_name not in tc.course.campus_teachers:
                tc.course.campus_teachers.append(tc.teacher_name)
            campus_tcs.append(tc)
        else:
            other_tcs.append(tc)
    
    # 校本部确定性排课
    for i in range(100):
        campus_scheduler = CampusScheduler(campus_tcs, all_subgroups, tc_to_sg_map, 
                                          teachers_list, rooms_list, fixed_schedule)
        campus_detailed_results, campus_fixed_results, failed_campus_tcs = campus_scheduler.schedule()
        if failed_campus_tcs == []:
            break
    
    # 遗传算法排课
    ga_tcs_to_schedule = other_tcs
    updated_fixed_schedule = fixed_schedule + campus_fixed_results
    
    ga_start_time = time.time()
    
    with multiprocessing.Pool() as pool:
        scheduler = DeapScheduler(
            teachers=teachers_list,
            rooms=rooms_list,
            subgroups=all_subgroups,
            teaching_classes=ga_tcs_to_schedule,
            tc_to_sg_map=tc_to_sg_map,
            fixed_schedule=updated_fixed_schedule,
            teacher_preferences=teacher_preferences,
            use_ql_optimizer=use_ql
        )
        success = scheduler.solve(pool)
        
        ga_end_time = time.time()
        total_end_time = time.time()
        
        # 收集结果
        best_fitness = scheduler.best_fitness
        
        results = {
            'algorithm_name': algorithm_name,
            'use_ql': use_ql,
            'success': success,
            'best_fitness': best_fitness,
            'ga_time': ga_end_time - ga_start_time,
            'total_time': total_end_time - start_time,
            'num_tasks': len(scheduler.tasks) if hasattr(scheduler, 'tasks') else 0,
        }
        
        # 如果使用Q-learning，添加Q-learning统计
        if use_ql and hasattr(scheduler, 'ql_optimizer'):
            ql_stats = scheduler.ql_optimizer.get_statistics()
            results['ql_stats'] = ql_stats
        
        print(f"\n{algorithm_name} 完成!")
        print(f"  最终惩罚值: {best_fitness:.2f}")
        print(f"  GA耗时: {results['ga_time']:.2f}秒")
        print(f"  总耗时: {results['total_time']:.2f}秒")
        print(f"  成功: {'是' if success else '否'}")
        
        return results


def compare_algorithms(semester='下册', num_runs=1):
    print(f"\n{'#'*70}")
    print(f"#  算法对比测试 - {semester}学期")
    print(f"#  每种算法运行 {num_runs} 次")
    print(f"{'#'*70}\n")
    
    all_results = {
        '原始GA': [],
        'Q-learning GA': []
    }
    
    # 运行原始GA
    for run in range(num_runs):
        print(f"\n--- 原始GA 第 {run + 1}/{num_runs} 次运行 ---")
        result = run_single_algorithm(semester, use_ql=False, 
                                      algorithm_name=f"原始GA-Run{run+1}")
        if result:
            all_results['原始GA'].append(result)
    
    # 运行Q-learning增强GA
    for run in range(num_runs):
        print(f"\n--- Q-learning GA 第 {run + 1}/{num_runs} 次运行 ---")
        result = run_single_algorithm(semester, use_ql=True, 
                                      algorithm_name=f"Q-learning-GA-Run{run+1}")
        if result:
            all_results['Q-learning GA'].append(result)
    
    # 生成对比报告
    print_comparison_report(all_results)


def print_comparison_report(all_results):
    print(f"\n{'='*70}")
    print(f"  算法性能对比报告")
    print(f"{'='*70}\n")
    
    for algo_name, results in all_results.items():
        if not results:
            continue
        
        print(f"\n{algo_name}:")
        print(f"  运行次数: {len(results)}")
        
        # 计算统计指标
        fitness_values = [r['best_fitness'] for r in results]
        ga_times = [r['ga_time'] for r in results]
        total_times = [r['total_time'] for r in results]
        success_count = sum(1 for r in results if r['success'])
        
        print(f"  成功次数: {success_count}/{len(results)}")
        print(f"\n  最终惩罚值:")
        print(f"    最小值: {min(fitness_values):.2f}")
        print(f"    最大值: {max(fitness_values):.2f}")
        print(f"    平均值: {sum(fitness_values)/len(fitness_values):.2f}")
        
        print(f"\n  GA运行时间:")
        print(f"    最小值: {min(ga_times):.2f}秒")
        print(f"    最大值: {max(ga_times):.2f}秒")
        print(f"    平均值: {sum(ga_times)/len(ga_times):.2f}秒")
        
        print(f"\n  总运行时间:")
        print(f"    最小值: {min(total_times):.2f}秒")
        print(f"    最大值: {max(total_times):.2f}秒")
        print(f"    平均值: {sum(total_times)/len(total_times):.2f}秒")
        
        # 如果是Q-learning，显示Q表信息
        if results[0].get('use_ql') and 'ql_stats' in results[0]:
            ql_stats = results[-1]['ql_stats']  # 使用最后一次运行的Q表统计
            print(f"\n  Q-learning信息:")
            print(f"    总episode数: {ql_stats['episode']}")
            print(f"    Q表大小: {ql_stats['q_table_size']}")
            print(f"    平均Q值: {ql_stats['average_q_value']:.3f}")
    
    # 对比分析
    if len(all_results) == 2:
        ga_results = all_results.get('原始GA', [])
        ql_results = all_results.get('Q-learning GA', [])
        
        if ga_results and ql_results:
            print(f"\n{'='*70}")
            print(f"  对比分析")
            print(f"{'='*70}\n")
            
            ga_avg_fitness = sum(r['best_fitness'] for r in ga_results) / len(ga_results)
            ql_avg_fitness = sum(r['best_fitness'] for r in ql_results) / len(ql_results)
            
            improvement = ((ga_avg_fitness - ql_avg_fitness) / ga_avg_fitness) * 100
            
            print(f"  惩罚值对比:")
            print(f"    原始GA平均: {ga_avg_fitness:.2f}")
            print(f"    Q-learning GA平均: {ql_avg_fitness:.2f}")
            
            if improvement > 0:
                print(f"    Q-learning改进: {improvement:.2f}% (更好)")
            elif improvement < 0:
                print(f"    Q-learning改进: {improvement:.2f}% (更差)")
            else:
                print(f"    两者相当")
            
            ga_avg_time = sum(r['ga_time'] for r in ga_results) / len(ga_results)
            ql_avg_time = sum(r['ga_time'] for r in ql_results) / len(ql_results)
            time_overhead = ((ql_avg_time - ga_avg_time) / ga_avg_time) * 100
            
            print(f"\n  运行时间对比:")
            print(f"    原始GA平均: {ga_avg_time:.2f}秒")
            print(f"    Q-learning GA平均: {ql_avg_time:.2f}秒")
            print(f"    时间开销: {time_overhead:+.2f}%")
    
    print(f"\n{'='*70}\n")


if __name__ == '__main__':
    multiprocessing.freeze_support()
    
    # 选择学期
    print("\n算法对比测试工具")
    print("="*50)
    
    selected_semester = ""
    while selected_semester not in ['上册', '下册']:
        choice = input(">>> 请选择要测试的学期 (上册/下册): ").strip()
        if choice in ['上册', '下册']:
            selected_semester = choice
        else:
            print("输入无效！请输入 '上册' 或者 '下册'。")
    
    # 选择运行次数
    num_runs = 1
    try:
        runs_input = input(f">>> 每种算法运行次数 (默认1次，建议3-5次): ").strip()
        if runs_input:
            num_runs = max(1, int(runs_input))
    except ValueError:
        print("输入无效，使用默认值1次")
    
    # 开始对比
    compare_algorithms(semester=selected_semester, num_runs=num_runs)


