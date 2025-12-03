from models.time_definition import *
from models.course import Course
from models.class_group import Cohort, AdminClass
from models.teacher import Teacher
from models.room import Room

def get_raw_data():
    """我将教学任务那个表格里的信息都定义到这个文件作为原始数据对象"""
    # 1. 教师定义所有参与排课的教师。
    teachers_list = [
        Teacher(id="T01", name="刘寿强", is_campus_teacher=True),
        Teacher(id="T02", name="徐清振", is_campus_teacher=True),
        Teacher(id="T03", name="王晨", is_campus_teacher=False),
        Teacher(id="T04", name="宿营", is_campus_teacher=False),
        Teacher(id="T05", name="袭奇", is_campus_teacher=False),
        Teacher(id="T06", name="陈晨", is_campus_teacher=False),
        Teacher(id="T07", name="董梁", is_campus_teacher=False),
        Teacher(id="T08", name="陈纪龙", is_campus_teacher=False),
        Teacher(id="T09", name="王婧", is_campus_teacher=False),
        Teacher(id="T10", name="王东梅", is_campus_teacher=False),
        Teacher(id="T11", name="陶启", is_campus_teacher=False),
        Teacher(id="T12", name="术洪亮", is_campus_teacher=False),
        Teacher(id="T13", name="许明春", is_campus_teacher=False),
        Teacher(id="T14", name="宋新", is_campus_teacher=False),
        Teacher(id="T15", name="王国铭", is_campus_teacher=False),
        Teacher(id="T16", name="宣丽萍", is_campus_teacher=False),
        Teacher(id="T17", name="赵金华", is_campus_teacher=False),
        Teacher(id="T18", name="未知", is_campus_teacher=False),
        Teacher(id="T19", name="冯刚", is_campus_teacher=True)
    ]

    # 2. 机房教室
    rooms_list = [Room(id="R01", name="机房1"),
                  Room(id="R02", name="机房2")]

    # 3. 各年级专业的群体
    cohorts_list = [
        Cohort(major="大数据", grade=1), Cohort(major="物联网", grade=1),
        Cohort(major="大数据", grade=2), Cohort(major="物联网", grade=2),
        Cohort(major="大数据", grade=3), Cohort(major="物联网", grade=3)
    ]
    cohorts_map = {c.id: c for c in cohorts_list}   # 创建一个从ID到对象的映射，方便后续查找
    # 行政班（以大一为例，并假设每个专业每年级有2个行政班，每班40人）
    admin_classes = [
        AdminClass(id="AC_BD1_1", cohort=cohorts_map['大数据-1'], class_index=1, student_count=40),
        AdminClass(id="AC_BD1_2", cohort=cohorts_map['大数据-1'], class_index=2, student_count=40),
        AdminClass(id="AC_BD1_3", cohort=cohorts_map['大数据-1'], class_index=3, student_count=40),
        AdminClass(id="AC_BD1_4", cohort=cohorts_map['大数据-1'], class_index=4, student_count=40),
        AdminClass(id="AC_TOT1_1", cohort=cohorts_map['物联网-1'], class_index=1, student_count=40),
        AdminClass(id="AC_TOT1_2", cohort=cohorts_map['物联网-1'], class_index=2, student_count=40),
        AdminClass(id="AC_BD2_1", cohort=cohorts_map['大数据-2'], class_index=1, student_count=40),
        AdminClass(id="AC_BD2_2", cohort=cohorts_map['大数据-2'], class_index=2, student_count=40),
        AdminClass(id="AC_TOT2_1", cohort=cohorts_map['物联网-2'], class_index=1, student_count=40),
        AdminClass(id="AC_TOT2_2", cohort=cohorts_map['物联网-2'], class_index=2, student_count=40),
        AdminClass(id="AC_BD3_1", cohort=cohorts_map['大数据-3'], class_index=1, student_count=40),
        AdminClass(id="AC_BD3_2", cohort=cohorts_map['大数据-3'], class_index=2, student_count=40),
        AdminClass(id="AC_BD3_3", cohort=cohorts_map['大数据-3'], class_index=3, student_count=40),
        AdminClass(id="AC_TOT3_1", cohort=cohorts_map['物联网-3'], class_index=1, student_count=40),
        AdminClass(id="AC_TOT3_2", cohort=cohorts_map['物联网-3'], class_index=2, student_count=40),
        AdminClass(id="AC_TOT3_3", cohort=cohorts_map['物联网-3'], class_index=3, student_count=40)
    ]
    # 4. 教学任务 (按Cohort组织)
    course_by_cohort = {
        cohorts_map['大数据-1']: [
            Course(id="BD1_L01", name="Python程序设计及应用", course_type='mixed', theory_hours=32, lab_hours=16,
                   teaching_class_count=2),
            Course(id="BD1_L02", name="线性代数", course_type='theory_only', theory_hours=48, teaching_class_count=3),
            Course(id="BD1_L03", name="高数", course_type='theory_only', theory_hours=96, teaching_class_count=2),
            Course(id="BD1_L04", name="数字逻辑电路", course_type='mixed', theory_hours=48, lab_hours=16,
                   teaching_class_count=0.5, combined_with=["TOT1_L04"])
        ],
        cohorts_map['物联网-1']: [
            Course(id="TOT1_L01", name="Python程序设计及应用", course_type='mixed', theory_hours=32, lab_hours=16,
                   teaching_class_count=1),
            Course(id="TOT1_L02", name="线性代数", course_type='theory_only', theory_hours=48, teaching_class_count=2),
            Course(id="TOT1_L03", name="高数", course_type='theory_only', theory_hours=96, teaching_class_count=1),
            Course(id="TOT1_L04", name="数字逻辑电路", course_type='mixed', theory_hours=48, lab_hours=16,
                   teaching_class_count=0.5, combined_with=["BD1_L04"])
        ],
        cohorts_map['大数据-2']: [
            Course(id="BD2_L01", name="面向对象程序设计(C++语言)", course_type='mixed', theory_hours=32, lab_hours=16,
                   teaching_class_count=1.5, combined_with=["TOT2_L01"]),
            Course(id="BD2_L02", name="数据科学导论", course_type='theory_only', theory_hours=32,
                   teaching_class_count=2),
            Course(id="BD2_L03", name="数学建模", course_type='mixed', theory_hours=32, lab_hours=32,
                   teaching_class_count=2),
            Course(id="BD2_L04", name="数据库系统原理", course_type='mixed', theory_hours=48, lab_hours=16,
                   teaching_class_count=1.5, combined_with=["TOT2_L02"]),
            Course(id="BD2_L05", name="优化算法与智能计算", course_type='theory_only', theory_hours=64,
                   teaching_class_count=2),
        ],
        cohorts_map['物联网-2']: [
            Course(id="TOT2_L01", name="面向对象程序设计(C++语言)", course_type='mixed', theory_hours=32, lab_hours=16,
                   teaching_class_count=1.5, combined_with=["BD2_L01"]),
            Course(id="TOT2_L02", name="数据库系统原理", course_type='mixed', theory_hours=48, lab_hours=16,
                   teaching_class_count=1.5, combined_with=["BD2_L04"]),
            Course(id="TOT2_L03", name="信号与系统", course_type='theory_only', theory_hours=64,
                   teaching_class_count=1),
            Course(id="TOT2_L04", name="操作系统", course_type='mixed', theory_hours=48, lab_hours=16,
                   teaching_class_count=1),
            Course(id="TOT2_L05", name="传感器原理及应用", course_type='theory_only', theory_hours=32,
                   teaching_class_count=1),
        ],
        cohorts_map['大数据-3']: [
            Course(id="BD3_L01", name="大数据安全与应用", course_type='theory_only', theory_hours=32,
                   teaching_class_count=1),
            Course(id="BD3_L02", name="数据挖掘与机器学习", course_type='theory_only', theory_hours=48,
                   teaching_class_count=2),
            Course(id="BD3_L03", name="统计学原理", course_type='theory_only', theory_hours=48, teaching_class_count=2),
            Course(id="BD3_L04", name="大数据分析技术", course_type='theory_only', theory_hours=48,
                   teaching_class_count=2),
            Course(id="BD3_L05", name="工业互联网", course_type='mixed', theory_hours=32, lab_hours=16,
                   teaching_class_count=1),
            Course(id="BD3_L06", name="Android应用系统设计", course_type='mixed', theory_hours=48, lab_hours=16,
                   teaching_class_count=1),
            Course(id="BD3_L07", name="Web开发基础", course_type='mixed', theory_hours=16, lab_hours=32,
                   teaching_class_count=1),
            Course(id="BD3_L08", name="应用随机过程", course_type='theory_only', theory_hours=48,
                   teaching_class_count=1),
            Course(id="BD3_L09", name="统计计算", course_type='theory_only', theory_hours=32, teaching_class_count=2),
        ],
        cohorts_map['物联网-3']: [
            Course(id="TOT3_L01", name="工业互联网", course_type='mixed', theory_hours=32, lab_hours=16,
                   teaching_class_count=1),
            Course(id="TOT3_L02", name="Android应用系统设计", course_type='mixed', theory_hours=48, lab_hours=16,
                   teaching_class_count=1),
            Course(id="TOT3_L03", name="Web开发基础", course_type='mixed', theory_hours=16, lab_hours=32,
                   teaching_class_count=1),
            Course(id="TOT3_L04", name="物联网通信技术", course_type='mixed', theory_hours=32, lab_hours=16,
                   teaching_class_count=1),
            Course(id="TOT3_L05", name="物联网安全", course_type='mixed', theory_hours=48, lab_hours=16,
                   teaching_class_count=2),
            Course(id="TOT3_L06", name="传感器网络", course_type='mixed', theory_hours=48, lab_hours=16,
                   teaching_class_count=2),
            Course(id="TOT3_L07", name="嵌入式系统与设计", course_type='mixed', theory_hours=32, lab_hours=32,
                   teaching_class_count=2),
            Course(id="TOT3_L08", name="单片机原理及应用", course_type='theory_only', theory_hours=48,
                   teaching_class_count=1)
        ]
    }

    # 5. 教师与课程关联
    teacher_course_map = {
        "BD1_L01": "T04","BD1_L02": "T12","BD1_L03": "T14", "BD1_L04": "T16",
        "TOT1_L01": "T10", "TOT1_L02": "T13", "TOT1_L03": "T15", "TOT1_L04": "T16",
        "BD2_L01": "T07", "BD2_L02": "T18", "BD2_L03": "T02", "BD2_L04": "T08", "BD2_L05": "T09",
        "TOT2_L01": "T07", "TOT2_L02": "T08", "TOT2_L03": "T06", "TOT2_L04": "T10", "TOT2_L05": "T01",
        "BD3_L01": "T01", "BD3_L02": "T02", "BD3_L03": "T03", "BD3_L04": "T19", "BD3_L05": "T01",
        "BD3_L06": "T04", "BD3_L07": "T05", "BD3_L08": "T03", "BD3_L09": "T19",
        "TOT3_L01": "T01", "TOT3_L02": "T04", "TOT3_L03": "T05", "TOT3_L04": "T06", "TOT3_L05": "T01",
        "TOT3_L06": "T01", "TOT3_L07": "T02", "TOT3_L08": "T02",

    }

    # 6. 教师偏好
    teacher_preferences = []
    for teacher in teachers_list:
        # 所有校本部教师只能在周一、周二全天和周三上午进行课程安排。
        if teacher.is_campus_teacher:
            teacher_preferences.append({
                'teacher_name': teacher.name,
                'course_name': None,
                'undesired_slots': [(3, p) for p in AFTERNOOM_PERIODS + EVENING_PERIODS] + [(4, -1), (5, -1)]

            })
    '''# 添加其他老师的特定偏好
    teacher_preferences.extend([
        {'teacher_name': '刘寿强', 'course_name': '大数据安全与应用', 'preferred_slots': [(1, -1)]},
        {'teacher_name': '王晨', 'course_name': '应用随机过程', 'preferred_slots': [(3, p) for p in AFTERNOOM_PERIODS],
         'undesired_slots': [(1, p) for p in EVENING_PERIODS]}
        # `undesired_slots`: 教师不希望上课的时间。
        # `preferred_slots`: 教师偏好的上课时间。
    ])
    '''

    # 7. 固定课程 (已安排的公共课)
    # 定义了每个 cohort 的子组应如何按比例分组打标签，因为有些相同固定课程可能分几个班在不同时间上课
    subgroup_pre_assignment = {
        '大数据-1': {
            'group_A': 0.5,  # 50% 的子组属于 A 组
            'group_B': 0.5  # 50% 的子组属于 B 组
        },
        '大数据-2': {
            'default': 1.0  # 100% 的子组属于 default 组（即不分组）
        }
    }

    fixed_schedule=[
        # 大数据大一
        {'cohort_id': '大数据-1', 'course_name': '英语', 'teacher_name': '英语老师', 'duration': 2,
        'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=2, period=1)},
        {'cohort_id': '大数据-1', 'course_name': '思想道德与法治', 'teacher_name': '政治老师', 'duration': 3,
         'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=1, period=5)},
        {'cohort_id': '大数据-1', 'course_name': '军事理论与国家安全教育', 'teacher_name': '政治老师', 'duration': 2,
        'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=3, period=1)},
        {'cohort_id': '大数据-1', 'course_name': '大学日语', 'teacher_name': '日语老师', 'duration': 4,
         'week': DOUBLE_WEEKS, 'start_time': TimePoint(week=None, day=4, period=5)},
        {'cohort_id': '大数据-1', 'course_name': '大学体育', 'teacher_name': '体育老师', 'duration': 2,
        'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=3, period=5)},
        {'cohort_id': '大数据-1', 'course_name': '形势与政策', 'teacher_name': '形势与政策老师', 'duration': 2,
        'week': [9, 10], 'start_time': TimePoint(week=None, day=3, period=9)},
        # 假设大学物理公共课分成两个班不同时间上课
        {'cohort_id': '大数据-1', 'group_tag': 'group_A', 'course_name': '大学物理', 'teacher_name': '物理老师', 'duration': 2,
        'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=5, period=5)},
        {'cohort_id': '大数据-1', 'group_tag': 'group_B', 'course_name': '大学物理', 'teacher_name': '物理老师','duration': 2,
         'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=4, period=1)},
        # 物联网大一
        {'cohort_id': '物联网-1', 'course_name': '大学英语', 'teacher_name': '英语老师', 'duration': 2,
         'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=1, period=1)},
        {'cohort_id': '物联网-1', 'course_name': '大学日语', 'teacher_name': '日语老师', 'duration': 4,
         'week': DOUBLE_WEEKS, 'start_time': TimePoint(week=None, day=4, period=5)},
        {'cohort_id': '物联网-1', 'course_name': '思想道德与法治', 'teacher_name': '政治老师', 'duration': 3,
         'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=2, period=1)},
        {'cohort_id': '物联网-1', 'course_name': '军事理论与国家安全教育', 'teacher_name': '政治老师', 'duration': 4,
         'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=3, period=5)},
        {'cohort_id': '物联网-1', 'course_name': '大学体育', 'teacher_name': '体育老师', 'duration': 2,
         'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=1, period=3)},
        {'cohort_id': '物联网-1', 'course_name': '形势与政策', 'teacher_name': '形势与政策老师', 'duration': 2,
         'week': [9, 10], 'start_time': TimePoint(week=None, day=1, period=9)},
        {'cohort_id': '物联网-1', 'course_name': '大学物理', 'teacher_name': '物理老师', 'duration': 3,
         'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=2, period=5)},
        # 大数据大二
        {'cohort_id': '大数据-2', 'course_name': '大学英语', 'teacher_name': '英语老师', 'duration': 2,
         'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=3, period=5)},
        {'cohort_id': '大数据-2', 'course_name': '大学体育', 'teacher_name': '体育老师', 'duration': 2,
         'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=1, period=7)},
        {'cohort_id': '大数据-2', 'course_name': '形势与政策', 'teacher_name': '形势与政策老师', 'duration': 2,
         'week': [8, 9], 'start_time': TimePoint(week=None, day=2, period=9)},
        {'cohort_id': '大数据-2', 'course_name': '毛泽东思想', 'teacher_name': '政治老师', 'duration': 3,
         'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=2, period=1)},
        # 物联网大二
        {'cohort_id': '物联网-2', 'course_name': '大学英语', 'teacher_name': '英语老师', 'duration': 2,
         'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=3, period=5)},
        {'cohort_id': '物联网-2', 'course_name': '大学体育', 'teacher_name': '体育老师', 'duration': 2,
         'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=2, period=1)},
        {'cohort_id': '物联网-2', 'course_name': '形势与政策', 'teacher_name': '形势与政策老师', 'duration': 2,
         'week': [8, 9], 'start_time': TimePoint(week=None, day=2, period=9)},
        {'cohort_id': '物联网-2', 'course_name': '毛泽东思想', 'teacher_name': '政治老师', 'duration': 3,
         'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=2, period=5)},
        # 大数据大三
        {'cohort_id': '大数据-3', 'course_name': '形势与政策', 'teacher_name': '形势与政策老师', 'duration': 2,
         'week': [6, 7], 'start_time': TimePoint(week=None, day=2, period=9)},
        # 物联网大三
        {'cohort_id': '物联网-3', 'course_name': '形势与政策', 'teacher_name': '形势与政策老师', 'duration': 2,
         'week': [6, 7], 'start_time': TimePoint(week=None, day=2, period=9)}

    ]

    return teachers_list, rooms_list, cohorts_list, admin_classes, course_by_cohort, teacher_course_map, fixed_schedule, teacher_preferences, subgroup_pre_assignment

