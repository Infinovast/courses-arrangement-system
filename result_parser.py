import pandas as pd
from collections import defaultdict
from models.time_definition import DAYS, PERIODS, SEMESTER_WEEKS

'''
生成Excel表格课表结果的
'''


def _format_weeks(weeks: list) -> str:
    """格式化周次列表为易读的字符串，例如 '第1-8,10周'"""
    weeks = sorted(list(set(weeks)))
    if not weeks: return ""
    # 常见周次模式的快捷格式化
    if weeks == SEMESTER_WEEKS: return f"第{SEMESTER_WEEKS[0]}-{SEMESTER_WEEKS[-1]}周"
    if weeks == list(range(1, 17, 2)): return "单周"
    if weeks == list(range(2, 18, 2)): return "双周"
    if weeks == list(range(1, 9)): return "第1-8周"
    if weeks == list(range(9, 17)): return "第9-16周"
    if weeks == list(range(5, 18)): return "第5-17周"
    if weeks == list(range(16, 18)): return "第16-17周"
    if weeks == list(range(5, 17)): return "第5-16周"

    # 通用周次范围合并逻辑
    ranges, start = [], weeks[0]
    for i in range(1, len(weeks)):
        if weeks[i] != weeks[i - 1] + 1:
            end = weeks[i - 1]
            ranges.append(f"{start}-{end}" if start != end else f"{start}")
            start = weeks[i]
    end = weeks[-1]
    ranges.append(f"{start}-{end}" if start != end else f"{start}")
    return "第" + ",".join(ranges) + "周"


def export_schedule_to_excel(
        solver_results: list, fixed_schedule: list, all_subgroups: list,
        tc_to_sg_map: dict, teaching_classes: list, rooms: list = None,
        filename="course_schedule_final.xlsx",
        admin_classes=None
):
    """主函数，导出所有排课结果到Excel文件"""
    if not solver_results and not fixed_schedule:
        print("没有结果可以导出。")
        return

    teaching_class_dict = {tc.id: tc for tc in teaching_classes}
    # schedule_data[subgroup_id][(day, period)][course_key] = [weeks]
    schedule_data = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

    # 1. 处理固定课程
    cohort_to_subgroups = defaultdict(list)
    for sg in all_subgroups:
        cohort_to_subgroups[sg.cohort.id].append(sg)
    for item in fixed_schedule:
        cohort_id = item.get('cohort_id')
        group_tag = item.get('group_tag')
        if not cohort_id: continue
        all_cohort_subgroups = cohort_to_subgroups.get(cohort_id, [])

        if group_tag and group_tag != 'default':
            relevant_subgroups = [sg for sg in all_cohort_subgroups if sg.fixed_schedule_tag == group_tag]
            if not relevant_subgroups:
                relevant_subgroups = all_cohort_subgroups
        else:
            relevant_subgroups = all_cohort_subgroups

        key = (item['course_name'], item['teacher_name'], False, None)
        start_tp, duration, weeks = item['start_time'], item['duration'], item['week']
        for sg in relevant_subgroups:
            for d in range(duration):
                period = start_tp.period + d
                if 1 <= start_tp.day <= len(DAYS) and 1 <= period <= len(PERIODS):
                    schedule_data[sg.id][(start_tp.day, period)][key].extend(weeks)

    # 2. 处理算法安排的课程
    for res in solver_results:
        tc = teaching_class_dict.get(res['teaching_class_id'])
        if not tc: continue
        for sg in tc_to_sg_map.get(tc.id, []):
            tp, dur = res['time_point'], res['duration']
            course_name = res['course_name'] + ("(合班)" if tc.is_combined else "")
            key = (course_name, res['teacher_name'], res['is_lab'], res['room_name'])
            for d in range(dur):
                period = tp.period + d
                if 1 <= tp.day <= len(DAYS) and 1 <= period <= len(PERIODS):
                    schedule_data[sg.id][(tp.day, period)][key].append(tp.week)

    # 3. 写入Excel文件
    with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        print("正在生成按行政班的课表...")
        _export_by_adminclass(writer, schedule_data, all_subgroups, admin_classes)
        # print("正在生成按子组的课表...")
        # _export_by_subgroup(writer, schedule_data, all_subgroups)
        print("正在生成教学班总览...")
        _export_by_teaching_class(writer, solver_results, tc_to_sg_map, teaching_class_dict)
        if rooms:
            print("正在生成按教室的课表...")
            _export_by_room(writer, solver_results, rooms)


def _export_by_adminclass(writer, schedule_data, all_subgroups, admin_classes=None):
    """
    为每个行政班生成课表。
    【核心修改】如果一个行政班内存在多种不同的课表，则会生成多个带后缀的工作表。
    """
    # 1) 将所有子组按 Cohort (年级专业) 聚类
    cohort_to_sgs = defaultdict(list)
    for sg in all_subgroups:
        cohort_key = f"{sg.cohort.major}-{sg.cohort.grade}"
        cohort_to_sgs[cohort_key].append(sg)
    for key in cohort_to_sgs:
        cohort_to_sgs[key].sort(key=lambda x: int(x.id.split('_')[-1]))

    # (此部分保留了原有的调试打印信息)
    print("=== 调试信息：各Cohort的虚拟子组数量 ===")
    for cohort_key, sgs in cohort_to_sgs.items():
        print(f"{cohort_key}: {len(sgs)} 个子组")

    # 2) 使用传入的行政班数据按 Cohort 聚类
    cohort_to_admins = defaultdict(list)
    if admin_classes is not None:
        print(f"成功接收到行政班数据，共 {len(admin_classes)} 个行政班")
        for ac in admin_classes:
            cohort_key = f"{ac.cohort.major}-{ac.cohort.grade}"
            cohort_to_admins[cohort_key].append(ac)
        for key in cohort_to_admins:
            cohort_to_admins[key].sort(key=lambda a: getattr(a, 'class_index', 0))
    else:
        print("警告：未传入行政班数据")

    print("=== 调试信息：各Cohort的行政班数量 ===")
    for cohort_key, admins in cohort_to_admins.items():
        print(f"{cohort_key}: {len(admins)} 个行政班")

    # 3) 按分数比例分配：行政班 -> 子组映射 (此部分为原版逻辑，保持不变)
    admin_to_sgs_map = []
    for cohort_key, sgs in cohort_to_sgs.items():
        admins = cohort_to_admins.get(cohort_key, [])
        if not admins:
            print(f"警告：{cohort_key} 没有对应的行政班定义")
            continue

        n_subgroups, n_admins = len(sgs), len(admins)
        print(f"=== 分配信息：{cohort_key} | 行政班: {n_admins}, 虚拟子组: {n_subgroups} ===")
        subgroups_per_admin = n_subgroups / n_admins

        subgroup_remaining = {i: 1.0 for i in range(n_subgroups)}
        current_subgroup_index, current_subgroup_used = 0, 0.0

        for i, ac in enumerate(admins):
            assigned, remaining_need = [], subgroups_per_admin
            while remaining_need > 1e-6 and current_subgroup_index < n_subgroups:
                current_available = subgroup_remaining[current_subgroup_index] - current_subgroup_used
                if current_available >= remaining_need:
                    if remaining_need > 0:
                        assigned.append({'subgroup': sgs[current_subgroup_index], 'fraction': remaining_need})
                    current_subgroup_used += remaining_need
                    remaining_need = 0
                else:
                    if current_available > 0:
                        assigned.append({'subgroup': sgs[current_subgroup_index], 'fraction': current_available})
                    remaining_need -= current_available
                    current_subgroup_index += 1
                    current_subgroup_used = 0.0

            if n_admins > n_subgroups:
                final_subgroups = [item['subgroup'] for item in assigned]
            else:
                filtered_assigned = [item for item in assigned if item['fraction'] >= 0.5]
                final_subgroups = [item['subgroup'] for item in filtered_assigned]

            sheet_name_prefix = f"行政班_{ac.cohort.major}{ac.cohort.grade}_{getattr(ac, 'class_index', i + 1)}"
            admin_to_sgs_map.append((sheet_name_prefix, final_subgroups))

            subgroup_indices = [int(sg.id.split('_')[-1]) for sg in final_subgroups]
            fractions = [f"{item['fraction']:.2f}" for item in assigned]
            print(f"行政班 {getattr(ac, 'class_index', i + 1)} -> 分配子组 {subgroup_indices} (原始比例: {fractions})")

    # 4) 按行政班写出工作表：【此部分为核心修改区域】
    weekday_cols = [f"星期{d}" for d in DAYS]
    columns = ["子组ID", "节次"] + weekday_cols

    for sheet_name_prefix, sgs in admin_to_sgs_map:
        if not sgs:
            _write_empty_table(writer, sheet_name_prefix[:31], columns)
            continue

        # 将分配给该行政班的子组，按其课表内容进行分组
        # key是课表的唯一标识, value是共享该课表的子组列表和课表内容
        schedules = {}
        for sg in sgs:
            sg_table = _get_subgroup_table(sg, schedule_data, weekday_cols)
            table_key = _get_table_key(sg_table, weekday_cols)
            if table_key not in schedules:
                schedules[table_key] = {'subgroups': [], 'table': sg_table}
            schedules[table_key]['subgroups'].append(sg)

        # 根据分组结果生成工作表
        if len(schedules) == 1:
            # 所有子组课表都相同，生成一张总课表
            table_data = list(schedules.values())[0]
            _write_merged_subgroups_table(writer, sheet_name_prefix[:31], table_data['subgroups'],
                                          table_data['table'], columns, weekday_cols)
        else:
            # 存在多种不同的课表，为每种课表生成一个单独的工作表
            # 对课表进行排序以保证输出顺序稳定
            sorted_schedules = sorted(schedules.values(), key=lambda x: x['subgroups'][0].id)

            for i, table_data in enumerate(sorted_schedules):
                # 创建带后缀的唯一工作表名，如 "行政班_计科21_1 (课表1)"
                new_sheet_name = f"{sheet_name_prefix} (课表{i + 1})"[:31]
                _write_merged_subgroups_table(writer, new_sheet_name, table_data['subgroups'],
                                              table_data['table'], columns, weekday_cols)


# --- 以下为辅助函数 ---

def _write_empty_table(writer, sheet_name, columns):
    """写入一个空的课表框架"""
    df = pd.DataFrame(index=[f"第{p}节" for p in PERIODS], columns=columns[2:])
    df.reset_index(inplace=True)
    df.rename(columns={'index': '节次'}, inplace=True)
    df["子组ID"] = ""
    df = df[columns]  # 保证列顺序
    df.to_excel(writer, sheet_name=sheet_name, index=False)
    _set_excel_style(writer.sheets[sheet_name], columns)


def _get_subgroup_table(sg, schedule_data, weekday_cols):
    """为单个子组生成其课表数据字典"""
    sg_table = {col: {} for col in weekday_cols}
    sg_slots = schedule_data.get(sg.id, {})
    for (day, period), courses in sg_slots.items():
        cell_texts = []
        for (course, teacher, is_lab, room), weeks in courses.items():
            week_str = _format_weeks(weeks)
            type_str = "实验课" if is_lab else "理论课"
            text = f"{course}\n({type_str}, {week_str}, {teacher}"
            if room: text += f", {room}"
            text += ")"
            cell_texts.append(text)
        sg_table[f"星期{day}"][period] = "\n".join(cell_texts)
    return sg_table


def _get_table_key(sg_table, weekday_cols):
    """为课表内容生成一个可哈希的唯一标识，用于比较两个课表是否相同"""
    key_parts = []
    for period in PERIODS:
        for col in weekday_cols:
            cell_content = sg_table.get(col, {}).get(period, "")
            key_parts.append(cell_content)
    return tuple(key_parts)


def _write_merged_subgroups_table(writer, sheet_name, subgroups, sg_table, columns, weekday_cols):
    """将具有相同课表的(一个或多个)子组合并写入一个工作表"""
    rows = _build_table_rows(subgroups, sg_table, weekday_cols)
    _write_table_to_excel(writer, sheet_name, rows, columns)


def _build_table_rows(subgroups, sg_table, weekday_cols):
    """根据课表数据构建DataFrame所需的行列表"""
    rows = []
    # 将共享此课表的所有子组ID合并成一个字符串
    subgroup_names = "、".join(sorted([sg.id for sg in subgroups]))

    for p in PERIODS:
        row = {
            "子组ID": subgroup_names,
            "节次": f"第{p}节",
        }
        for col in weekday_cols:
            row[col] = sg_table.get(col, {}).get(p, "")
        rows.append(row)
    return rows


def _write_table_to_excel(writer, sheet_name, rows, columns):
    """将格式化好的行数据写入Excel工作表并设置样式"""
    df = pd.DataFrame(rows, columns=columns)
    df.to_excel(writer, sheet_name=sheet_name, index=False)
    _set_excel_style(writer.sheets[sheet_name], columns)


def _set_excel_style(ws, columns):
    """设置Excel工作表的列宽和单元格样式"""
    ws.column_dimensions['A'].width = 25  # 子组ID列
    ws.column_dimensions['B'].width = 10  # 节次列
    for i, col_name in enumerate(columns):
        if col_name.startswith('星期'):
            col_letter = chr(ord('A') + i)
            ws.column_dimensions[col_letter].width = 35

    for row in ws.iter_rows():
        for cell in row:
            cell.alignment = cell.alignment.copy(wrap_text=True, horizontal='center', vertical='center')
        if row[0].row > 1:
            ws.row_dimensions[row[0].row].height = 60


def _export_by_subgroup(writer, schedule_data, all_subgroups):
    """(未修改)为每个虚拟子组生成一个单独的课表"""
    for sg in all_subgroups:
        df = pd.DataFrame(index=[f"第{p}节" for p in PERIODS], columns=[f"星期{d}" for d in DAYS]).fillna("")
        for (day, period), courses in schedule_data.get(sg.id, {}).items():
            cell_texts = []
            for (course, teacher, is_lab, room), weeks in courses.items():
                week_str = _format_weeks(weeks)
                type_str = "实验课" if is_lab else "理论课"
                text = f"{course}\n({type_str}, {week_str}, {teacher}"
                if room: text += f", {room}"
                text += ")"
                cell_texts.append(text)
            df.loc[f"第{period}节", f"星期{day}"] = "\n".join(cell_texts)

        sheet_name = f"{sg.cohort.major}{sg.cohort.grade}_{sg.id.split('_')[-1]}"[:31]
        df.to_excel(writer, sheet_name=sheet_name, index=True)
        _set_excel_style(writer.sheets[sheet_name], list(df.columns))


def _export_by_teaching_class(writer, solver_results, tc_to_sg_map, teaching_class_dict):
    """(未修改)生成一个总览表，列出所有教学班的排课信息"""
    agg_data = defaultdict(lambda: defaultdict(lambda: {'weeks': [], 'res': None}))
    for res in solver_results:
        tp = res['time_point']
        key = (res['teaching_class_id'], tp.day, tp.period, res['room_name'], res['is_lab'])
        agg_data[res['teaching_class_id']][key]['weeks'].append(tp.week)
        agg_data[res['teaching_class_id']][key]['res'] = res

    df_data = []
    for tc_id, items_by_slot in agg_data.items():
        tc = teaching_class_dict.get(tc_id)
        if not tc: continue
        subgroups = tc_to_sg_map.get(tc_id, [])
        cohorts = sorted(list({f"{sg.cohort.major}{sg.cohort.grade}" for sg in subgroups}))

        for data in items_by_slot.values():
            res, tp = data['res'], data['res']['time_point']
            df_data.append([
                tc_id, res['course_name'] + ("(合班)" if tc.is_combined else ""), res['teacher_name'],
                f"周{DAYS[tp.day - 1]} 第{tp.period}-{tp.period + res['duration'] - 1}节",
                res.get('room_name', '理论教室'), _format_weeks(data['weeks']),
                '实验课' if res['is_lab'] else '理论课', "/".join(cohorts),
                len(subgroups), "是" if tc.is_combined else "否"
            ])

    df = pd.DataFrame(df_data,
                      columns=["教学班ID", "课程名称", "教师", "时间", "教室", "周次", "类型", "面向群体", "子组数",
                               "合班"])
    df = df.sort_values(by=["面向群体", "教学班ID", "周次", "时间"]).reset_index(drop=True)
    df.to_excel(writer, sheet_name="教学班总览", index=False)

    ws = writer.sheets["教学班总览"]
    widths = {'A': 20, 'B': 30, 'C': 10, 'D': 20, 'E': 15, 'F': 20, 'G': 8, 'H': 25, 'I': 8, 'J': 8}
    for col, width in widths.items(): ws.column_dimensions[col].width = width


def _export_by_room(writer, solver_results, rooms):
    """(未修改)为每个机房生成一个单独的工作表，显示其使用情况"""
    if not rooms: return
    agg_data = defaultdict(lambda: defaultdict(lambda: {'weeks': [], 'res': None}))
    for res in solver_results:
        if not res.get('room_name'): continue
        tp = res['time_point']
        key = (res['room_name'], tp.day, tp.period, res['teaching_class_id'])
        agg_data[res['room_name']][key]['weeks'].append(tp.week)
        agg_data[res['room_name']][key]['res'] = res

    for room in rooms:
        if room.name not in agg_data: continue
        df_data = []
        for data in agg_data[room.name].values():
            res, tp = data['res'], data['res']['time_point']
            df_data.append([
                f"周{DAYS[tp.day - 1]} 第{tp.period}-{tp.period + res['duration'] - 1}节",
                res['course_name'], res['teacher_name'], _format_weeks(data['weeks']),
                '实验课' if res['is_lab'] else '理论课'
            ])

        df = pd.DataFrame(df_data, columns=["时间", "课程名称", "教师", "周次", "类型"])
        df = df.sort_values(by=["时间", "周次"]).reset_index(drop=True)
        sheet_name = f"教室_{room.name.replace('/', '_')}"[:31]
        df.to_excel(writer, sheet_name=sheet_name, index=False)

        ws = writer.sheets[sheet_name]
        widths = {'A': 20, 'B': 30, 'C': 10, 'D': 20, 'E': 8}
        for col, width in widths.items(): ws.column_dimensions[col].width = width