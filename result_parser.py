import pandas as pd
from collections import defaultdict
from models.time_definition import DAYS, PERIODS, SEMESTER_WEEKS

'''
生成Excel表格课表结果的
'''


def _format_weeks(weeks: list) -> str:
    weeks = sorted(list(set(weeks)))
    if not weeks: return ""
    if weeks == SEMESTER_WEEKS: return f"第{SEMESTER_WEEKS[0]}-{SEMESTER_WEEKS[-1]}周"
    if weeks == list(range(1, 17, 2)): return "单周"
    if weeks == list(range(2, 18, 2)): return "双周"
    if weeks == list(range(1, 9)): return "第1-8周"
    if weeks == list(range(9, 17)): return "第9-16周"
    if weeks == list(range(5, 18)): return "第5-17周"
    if weeks == list(range(16, 18)): return "第16-17周"
    if weeks == list(range(5, 17)): return "第5-16周"

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
    if not solver_results and not fixed_schedule:
        print("没有结果可以导出。")
        return

    teaching_class_dict = {tc.id: tc for tc in teaching_classes}
    schedule_data = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

    # 处理固定课程
    cohort_to_subgroups = defaultdict(list)
    for sg in all_subgroups:
        cohort_to_subgroups[sg.cohort.id].append(sg)
    for item in fixed_schedule:
        cohort_id = item.get('cohort_id')
        group_tag = item.get('group_tag')
        if not cohort_id: continue
        all_cohort_subgroups = cohort_to_subgroups.get(cohort_id, [])
        if group_tag:
            relevant_subgroups = [sg for sg in all_cohort_subgroups if sg.fixed_schedule_tag == group_tag]
        else:
            relevant_subgroups = all_cohort_subgroups
        key = (item['course_name'], item['teacher_name'], False, None)
        start_tp, duration, weeks = item['start_time'], item['duration'], item['week']
        for sg in relevant_subgroups:
            for d in range(duration):
                period = start_tp.period + d
                if 1 <= start_tp.day <= len(DAYS) and 1 <= period <= len(PERIODS):
                    schedule_data[sg.id][(start_tp.day, period)][key].extend(weeks)

    # 处理算法安排的课程
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

    # 写入Excel文件
    with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        print("正在生成按行政班的课表...")
        _export_by_adminclass(writer, schedule_data, all_subgroups, admin_classes)
        #print("正在生成按子组的课表...")
        #_export_by_subgroup(writer, schedule_data, all_subgroups)
        print("正在生成教学班总览...")
        _export_by_teaching_class(writer, solver_results, tc_to_sg_map, teaching_class_dict)
        if rooms:
            print("正在生成按教室的课表...")
            _export_by_room(writer, solver_results, rooms)


def _export_by_adminclass(writer, schedule_data, all_subgroups, admin_classes=None):
    """为每个行政班生成一个单独的课表，按照分数比例分配虚拟子组。"""
    # 1) 将所有子组按 Cohort 聚类，并按子组序号排序
    cohort_to_sgs = defaultdict(list)
    for sg in all_subgroups:
        cohort_key = f"{sg.cohort.major}-{sg.cohort.grade}"
        cohort_to_sgs[cohort_key].append(sg)
    for key in cohort_to_sgs:
        cohort_to_sgs[key].sort(key=lambda x: int(x.id.split('_')[-1]))

    print("=== 调试信息：各Cohort的虚拟子组数量 ===")
    for cohort_key, sgs in cohort_to_sgs.items():
        print(f"{cohort_key}: {len(sgs)} 个子组")

    # 2) 使用传入的行政班数据
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

    # 3) 按照分数比例分配：行政班 -> 子组映射
    admin_to_sgs_map = []

    for cohort_key, sgs in cohort_to_sgs.items():
        admins = cohort_to_admins.get(cohort_key, [])
        if not admins:
            print(f"警告：{cohort_key} 没有对应的行政班定义")
            continue

        n_subgroups = len(sgs)
        n_admins = len(admins)

        print(f"=== 分配信息：{cohort_key} ===")
        print(f"行政班数量: {n_admins}, 虚拟子组数量: {n_subgroups}")

        # 统一使用分数比例分配逻辑
        # 每个行政班分配的子组比例 = 虚拟子组数量 ÷ 行政班数量
        subgroups_per_admin = n_subgroups / n_admins
        print(f"每个行政班分配 {subgroups_per_admin} 个子组")

        # 初始化每个子组的剩余比例（初始都为1.0，表示完整的一个子组）
        subgroup_remaining = {i: 1.0 for i in range(n_subgroups)}
        current_subgroup_index = 0
        current_subgroup_used = 0.0

        for i, ac in enumerate(admins):
            assigned = []
            remaining_need = subgroups_per_admin

            # 从当前子组开始分配
            while remaining_need > 0 and current_subgroup_index < n_subgroups:
                current_available = subgroup_remaining[current_subgroup_index] - current_subgroup_used

                if current_available >= remaining_need:
                    # 当前子组足够分配剩余需求
                    if remaining_need > 0:
                        # 只分配部分子组
                        assigned.append({
                            'subgroup': sgs[current_subgroup_index],
                            'fraction': remaining_need
                        })
                    current_subgroup_used += remaining_need
                    remaining_need = 0
                else:
                    # 当前子组不够，全部分配
                    if current_available > 0:
                        assigned.append({
                            'subgroup': sgs[current_subgroup_index],
                            'fraction': current_available
                        })
                    remaining_need -= current_available
                    current_subgroup_index += 1
                    current_subgroup_used = 0.0

            # 对于行政班数量 > 虚拟子组数量的情况，每个行政班可能只分配到很小比例的子组
            # 这种情况下，我们保留所有分配比例大于0的子组
            if n_admins > n_subgroups:
                # 情况2：行政班数量 > 虚拟子组数量，每个行政班分配的子组比例很小
                # 保留所有分配的子组，因为每个行政班都需要显示课表
                final_subgroups = [item['subgroup'] for item in assigned]
            else:
                # 情况1：行政班数量 ≤ 虚拟子组数量，只保留分配比例较大的子组
                filtered_assigned = [item for item in assigned if item['fraction'] >= 0.5]
                final_subgroups = [item['subgroup'] for item in filtered_assigned]

            sheet_name = f"行政班_{ac.cohort.major}{ac.cohort.grade}_{getattr(ac, 'class_index', i + 1)}"[:31]
            admin_to_sgs_map.append((sheet_name, cohort_key, final_subgroups))

            subgroup_indices = [int(sg.id.split('_')[-1]) for sg in final_subgroups]
            fractions = [f"{item['fraction']:.2f}" for item in assigned]
            print(f"行政班 {getattr(ac, 'class_index', i + 1)}: 分配子组 {subgroup_indices} (比例: {fractions})")

    # 4) 按行政班写出工作表：合并相同课表的子组
    weekday_cols = [f"星期{d}" for d in DAYS]
    columns = ["子组", "节次"] + weekday_cols

    for sheet_name, cohort_key, sgs in admin_to_sgs_map:
        if not sgs:
            # 如果没有分配到子组，创建空表
            _write_empty_table(writer, sheet_name, columns)
            continue

        # 检查子组数量，如果只有一个子组，直接显示
        if len(sgs) == 1:
            _write_single_subgroup_table(writer, sheet_name, sgs[0], schedule_data, columns, weekday_cols)
            continue

        # 多个子组时，检查课表是否相同
        subgroup_tables = {}
        for sg in sgs:
            # 获取该子组的课表数据
            sg_table = _get_subgroup_table(sg, schedule_data, weekday_cols)
            # 将课表数据转换为可哈希的格式进行比较
            table_key = _get_table_key(sg_table, weekday_cols)

            if table_key not in subgroup_tables:
                subgroup_tables[table_key] = {
                    'table': sg_table,
                    'subgroups': [sg]
                }
            else:
                subgroup_tables[table_key]['subgroups'].append(sg)

        # 如果所有子组课表都相同，合并显示
        if len(subgroup_tables) == 1:
            table_data = list(subgroup_tables.values())[0]
            _write_merged_subgroups_table(writer, sheet_name, table_data['subgroups'],
                                          table_data['table'], columns, weekday_cols)
        else:
            # 课表不同，分别显示（但合并相同课表的子组）
            _write_mixed_subgroups_table(writer, sheet_name, subgroup_tables,
                                         columns, weekday_cols)

# 其他辅助函数保持不变
def _write_empty_table(writer, sheet_name, columns):
    """写入空表"""
    df = pd.DataFrame(columns=columns)
    df.to_excel(writer, sheet_name=sheet_name, index=False)

    # 设置样式
    ws = writer.sheets[sheet_name]
    ws.column_dimensions['A'].width = 25
    ws.column_dimensions['B'].width = 10
    for idx in range(3, 3 + len([col for col in columns if col.startswith('星期')])):
        col_letter = chr(ord('A') + idx - 1)
        ws.column_dimensions[col_letter].width = 35


def _get_subgroup_table(sg, schedule_data, weekday_cols):
    """获取子组的课表数据"""
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
    """生成课表的唯一标识键，用于比较课表是否相同"""
    key_parts = []
    for period in range(1, len(PERIODS) + 1):
        for col in weekday_cols:
            cell_content = sg_table.get(col, {}).get(period, "")
            key_parts.append(cell_content)
    return tuple(key_parts)


def _write_single_subgroup_table(writer, sheet_name, sg, schedule_data, columns, weekday_cols):
    """写入单个子组的课表"""
    sg_table = _get_subgroup_table(sg, schedule_data, weekday_cols)
    rows = _build_table_rows([sg], sg_table, weekday_cols)
    _write_table_to_excel(writer, sheet_name, rows, columns)


def _write_merged_subgroups_table(writer, sheet_name, subgroups, sg_table, columns, weekday_cols):
    """写入合并的多个子组课表（课表相同）"""
    rows = _build_table_rows(subgroups, sg_table, weekday_cols)
    _write_table_to_excel(writer, sheet_name, rows, columns)


def _write_mixed_subgroups_table(writer, sheet_name, subgroup_tables, columns, weekday_cols):
    """写入混合子组课表（课表不同，但合并相同课表的子组）"""
    rows = []
    for table_data in subgroup_tables.values():
        subgroups = table_data['subgroups']
        sg_table = table_data['table']
        subgroup_rows = _build_table_rows(subgroups, sg_table, weekday_cols)
        rows.extend(subgroup_rows)
        # 不同课表组之间添加空行分隔
        if len(subgroup_tables) > 1:
            rows.append({col: "" for col in columns})

    # 去掉尾部多余分隔空行
    if rows and all(v == "" for v in rows[-1].values()):
        rows.pop()

    _write_table_to_excel(writer, sheet_name, rows, columns)


def _build_table_rows(subgroups, sg_table, weekday_cols):
    """构建表格行数据"""
    rows = []
    subgroup_names = "、".join([sg.id for sg in subgroups])

    for p in PERIODS:
        row = {
            "子组": subgroup_names,
            "节次": f"第{p}节",
        }
        for col in weekday_cols:
            row[col] = sg_table.get(col, {}).get(p, "")
        rows.append(row)

    return rows


def _write_table_to_excel(writer, sheet_name, rows, columns):
    """将表格数据写入Excel"""
    df = pd.DataFrame(rows, columns=columns)
    df.to_excel(writer, sheet_name=sheet_name, index=False)

    # 设置样式
    ws = writer.sheets[sheet_name]
    # 列宽：子组列根据内容调整，节次列固定，星期列较宽
    ws.column_dimensions['A'].width = 25  # 子组列
    ws.column_dimensions['B'].width = 10  # 节次列
    # 按列字母设置后续列宽
    for idx in range(3, 3 + len([col for col in columns if col.startswith('星期')])):
        col_letter = chr(ord('A') + idx - 1)
        ws.column_dimensions[col_letter].width = 35

    # 设置单元格样式
    for row in ws.iter_rows():
        for cell in row:
            cell.alignment = cell.alignment.copy(wrap_text=True, horizontal='center', vertical='center')
        # 标题行以后统一行高
        if row[0].row > 1:
            ws.row_dimensions[row[0].row].height = 60

def _export_by_subgroup(writer, schedule_data, all_subgroups):
    """为每个虚拟子组生成一个单独的课表。"""
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

        ws = writer.sheets[sheet_name]
        ws.column_dimensions['A'].width = 10
        for col_idx in range(2, len(df.columns) + 2):
            ws.column_dimensions[chr(ord('A') + col_idx - 1)].width = 35
        for row in ws.iter_rows():
            for cell in row:
                cell.alignment = cell.alignment.copy(wrap_text=True, horizontal='center', vertical='center')
            if row[0].row > 1: ws.row_dimensions[row[0].row].height = 60


def _export_by_teaching_class(writer, solver_results, tc_to_sg_map, teaching_class_dict):
    """生成一个总览表，列出所有教学班的排课信息。"""
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
                f"周{tp.day} 第{tp.period}-{tp.period + res['duration'] - 1}节",
                res.get('room_name', '理论教室'), _format_weeks(data['weeks']),
                '实验课' if res['is_lab'] else '理论课', "/".join(cohorts),
                len(subgroups), "是" if tc.is_combined else "否"
            ])

    df = pd.DataFrame(df_data,
                      columns=["教学班ID", "课程名称", "教师", "时间", "教室", "周次", "类型", "包含年级", "子组数量",
                               "是否合班"])
    df = df.sort_values(by=["包含年级", "教学班ID", "周次", "时间"]).reset_index(drop=True)
    df.to_excel(writer, sheet_name="教学班总览", index=False)

    ws = writer.sheets["教学班总览"]
    widths = {'A': 20, 'B': 30, 'C': 10, 'D': 15, 'E': 15, 'F': 20, 'G': 8, 'H': 20, 'I': 10, 'J': 8}
    for col, width in widths.items(): ws.column_dimensions[col].width = width


def _export_by_room(writer, solver_results, rooms):
    """为每个机房生成一个单独的工作表，显示其使用情况。"""
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
                f"周{tp.day} 第{tp.period}-{tp.period + res['duration'] - 1}节",
                res['course_name'], res['teacher_name'], _format_weeks(data['weeks']),
                '实验课' if res['is_lab'] else '理论课'
            ])

        df = pd.DataFrame(df_data, columns=["时间", "课程名称", "教师", "周次", "类型"])
        df = df.sort_values(by=["时间", "周次"]).reset_index(drop=True)
        sheet_name = f"教室_{room.name.replace('/', '_')}"[:31]
        df.to_excel(writer, sheet_name=sheet_name, index=False)

        ws = writer.sheets[sheet_name]
        widths = {'A': 15, 'B': 30, 'C': 10, 'D': 20, 'E': 8}
        for col, width in widths.items(): ws.column_dimensions[col].width = width