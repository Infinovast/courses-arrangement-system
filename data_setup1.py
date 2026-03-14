from models.time_definition import *
from models.course import Course
from models.class_group import Cohort, AdminClass
from models.teacher import Teacher
from models.room import Room


# 上册教学任务
def get_raw_data():
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
        Teacher(id="T18", name="薛博桓", is_campus_teacher=False),
        Teacher(id="T19", name="冯刚", is_campus_teacher=True),
        Teacher(id="T20", name="谢承旺", is_campus_teacher=False),
        Teacher(id="T21", name="庞雄文", is_campus_teacher=False),
        Teacher(id="T22", name="教师甲", is_campus_teacher=False),
        Teacher(id="T23", name="教师丙", is_campus_teacher=False),
        Teacher(id="T24", name="教师丁", is_campus_teacher=True),
    ]

    # 2. 机房教室
    rooms_list = [Room(id="R01", name="机房1"),
                  Room(id="R02", name="机房2")]

    # 3. 各年级专业的群体
    cohorts_list = [
        Cohort(major="大数据", grade=1),
        Cohort(major="大数据", grade=2), Cohort(major="物联网", grade=2),
        Cohort(major="大数据", grade=3), Cohort(major="物联网", grade=3),
        Cohort(major="大数据", grade=4), Cohort(major="物联网", grade=4),
    ]
    cohorts_map = {c.id: c for c in cohorts_list}  # 创建一个从ID到对象的映射，方便后续查找
    # 行政班（以大一为例，并假设每个专业每年级有2个行政班，每班40人）
    admin_classes = [
        AdminClass(id="AC_BD1_1", cohort=cohorts_map['大数据-1'], class_index=1, student_count=40),
        AdminClass(id="AC_BD1_2", cohort=cohorts_map['大数据-1'], class_index=2, student_count=40),
        AdminClass(id="AC_BD1_3", cohort=cohorts_map['大数据-1'], class_index=3, student_count=40),
        AdminClass(id="AC_BD1_4", cohort=cohorts_map['大数据-1'], class_index=4, student_count=40),
        AdminClass(id="AC_BD1_5", cohort=cohorts_map['大数据-1'], class_index=5, student_count=40),
        AdminClass(id="AC_BD1_6", cohort=cohorts_map['大数据-1'], class_index=6, student_count=40),
        AdminClass(id="AC_BD2_1", cohort=cohorts_map['大数据-2'], class_index=1, student_count=40),
        AdminClass(id="AC_BD2_2", cohort=cohorts_map['大数据-2'], class_index=2, student_count=40),
        AdminClass(id="AC_BD2_3", cohort=cohorts_map['大数据-2'], class_index=3, student_count=40),
        AdminClass(id="AC_BD2_4", cohort=cohorts_map['大数据-2'], class_index=4, student_count=40),
        AdminClass(id="AC_TOT2_1", cohort=cohorts_map['物联网-2'], class_index=1, student_count=40),
        AdminClass(id="AC_TOT2_2", cohort=cohorts_map['物联网-2'], class_index=2, student_count=40),
        AdminClass(id="AC_BD3_1", cohort=cohorts_map['大数据-3'], class_index=1, student_count=40),
        AdminClass(id="AC_BD3_2", cohort=cohorts_map['大数据-3'], class_index=2, student_count=40),
        AdminClass(id="AC_TOT3_1", cohort=cohorts_map['物联网-3'], class_index=1, student_count=40),
        AdminClass(id="AC_TOT3_2", cohort=cohorts_map['物联网-3'], class_index=2, student_count=40),
        AdminClass(id="AC_BD4_1", cohort=cohorts_map['大数据-4'], class_index=1, student_count=40),
        AdminClass(id="AC_BD4_2", cohort=cohorts_map['大数据-4'], class_index=2, student_count=40),
        AdminClass(id="AC_BD4_3", cohort=cohorts_map['大数据-4'], class_index=3, student_count=40),
        AdminClass(id="AC_TOT4_1", cohort=cohorts_map['物联网-4'], class_index=1, student_count=40),
        AdminClass(id="AC_TOT4_2", cohort=cohorts_map['物联网-4'], class_index=2, student_count=40),
        AdminClass(id="AC_TOT4_3", cohort=cohorts_map['物联网-4'], class_index=3, student_count=40)
    ]

    # 4. 教学任务 (按Cohort组织)
    course_by_cohort = {
        cohorts_map['大数据-1']: [
            Course(id="BD1_L01", name="计算机科学技术导论", course_type='theory_only', theory_hours=32,
                   teaching_class_count=3, teacher_override={1: "T20"}),
            Course(id="BD1_L02", name="高等数学", course_type='theory_only', theory_hours=96, teaching_class_count=4,
                   teacher_override={3: "T15", 4: "T15"}),
            Course(id="BD1_L03", name="程序设计基础（C语言）", course_type='mixed', theory_hours=32, lab_hours=16,
                   teaching_class_count=4, teacher_override={3: "T08", 4: "T08"}),
            Course(id="BD1_L04", name="两个教师课程1", course_type='theory_only', theory_hours=32,
                   teaching_class_count=1, phase_teachers={"phase1": (1, 8, "T22"), "phase2": (9, 16, "T23")}),
            Course(id="BD1_L05", name="两个教师课程2", course_type='lab_only', lab_hours=16,
                   teaching_class_count=2, phase_teachers={"phase1": (1, 8, "T22"), "phase2": (9, 16, "T23")}),
            Course(id="BD1_L06", name="两个教师课程3", course_type='mixed', theory_hours=48, lab_hours=16,
                   teaching_class_count=2, phase_teachers={"phase1": (1, 8, "T24"), "phase2": (9, 16, "T23")}),
        ],
        cohorts_map['大数据-2']: [
            Course(id="BD2_L01", name="离散数学", course_type='theory_only', theory_hours=48, teaching_class_count=2),
            Course(id="BD2_L02", name="计算机组成原理", course_type='theory_only', theory_hours=56,
                   teaching_class_count=2),
            Course(id="BD2_L03", name="数据结构", course_type='theory_only', theory_hours=64, teaching_class_count=2,
                   teacher_override={2: "T17"}),
            Course(id="BD2_L04", name="数据结构实验", course_type='lab_only', lab_hours=32, teaching_class_count=2,
                   teacher_override={2: "T17"}),
            Course(id="BD2_L05", name="概率论与数理统计", course_type='theory_only', theory_hours=48,
                   teaching_class_count=2),
        ],
        cohorts_map['物联网-2']: [
            Course(id="TOT2_L01", name="离散数学", course_type='theory_only', theory_hours=48, teaching_class_count=2),
            Course(id="TOT2_L02", name="计算机组成原理", course_type='theory_only', theory_hours=56,
                   teaching_class_count=2),
            Course(id="TOT2_L03", name="数据结构", course_type='theory_only', theory_hours=64, teaching_class_count=1),
            Course(id="TOT2_L04", name="数据结构实验", course_type='lab_only', lab_hours=32, teaching_class_count=1),
            Course(id="TOT2_L05", name="概率论与数理统计", course_type='theory_only', theory_hours=48,
                   teaching_class_count=2),
        ],
        cohorts_map['大数据-3']: [
            Course(id="BD3_L01", name="运筹学", course_type='theory_only', theory_hours=48, teaching_class_count=1),
            Course(id="BD3_L02", name="JAVA语言程序设计", course_type='theory_only', theory_hours=32,
                   teaching_class_count=1),
            Course(id="BD3_L03", name="JAVA语言程序设计", course_type='lab_only', lab_hours=16, teaching_class_count=2),
            Course(id="BD3_L04", name="编译原理", course_type='theory_only', theory_hours=48, teaching_class_count=1),
            Course(id="BD3_L05", name="软件工程", course_type='mixed', theory_hours=48, lab_hours=16,
                   teaching_class_count=2, teacher_override={2: "T08"}),
            Course(id="BD3_L06", name="算法设计与分析", course_type='mixed', theory_hours=32, lab_hours=32,
                   teaching_class_count=2),
            Course(id="BD3_L07", name="Linux操作系统与应用", course_type='mixed', theory_hours=16, lab_hours=32,
                   teaching_class_count=2),
            Course(id="BD3_L08", name="并行与分布式计算", course_type='mixed', theory_hours=32, lab_hours=16,
                   teaching_class_count=2),
            Course(id="BD3_L09", name="决策论", course_type='theory_only', theory_hours=32, teaching_class_count=1),
        ],
        cohorts_map['物联网-3']: [
            Course(id="TOT3_L01", name="工程伦理", course_type='theory_only', theory_hours=32, teaching_class_count=1),
            Course(id="TOT3_L02", name="JAVA语言程序设计", course_type='mixed', theory_hours=32, lab_hours=16,
                   teaching_class_count=1),
            Course(id="TOT3_L03", name="编译原理", course_type='theory_only', theory_hours=48, teaching_class_count=1),
            Course(id="TOT3_L04", name="计算机网络", course_type='mixed', theory_hours=48, lab_hours=16,
                   teaching_class_count=1),
            Course(id="TOT3_L05", name="软件工程", course_type='mixed', theory_hours=48, lab_hours=16,
                   teaching_class_count=1),
            Course(id="TOT3_L06", name="数字信号处理", course_type='mixed', theory_hours=48, lab_hours=16,
                   teaching_class_count=1),
            Course(id="TOT3_L07", name="通信原理", course_type='mixed', theory_hours=48, lab_hours=16,
                   teaching_class_count=1),
            Course(id="TOT3_L08", name="Linux操作系统与应用", course_type='mixed', theory_hours=16, lab_hours=32,
                   teaching_class_count=1)
        ],
        cohorts_map['大数据-4']: [
            Course(id="BD4_L01_A", name="云计算", course_type='theory_only', theory_hours=26, teaching_class_count=1,
                   preferred_pattern='weeks_5_to_17'),
            Course(id="BD4_L01_B", name="云计算", course_type='theory_only', theory_hours=6, teaching_class_count=1,
                   preferred_pattern='weeks_16_to_17'),
            Course(id="BD4_L02", name="人工智能", course_type='theory_only', theory_hours=48, teaching_class_count=1,
                   preferred_pattern='weeks_5_to_16'),
            Course(id="BD4_L03_A", name="区块链技术及应用", course_type='theory_only', theory_hours=26,
                   teaching_class_count=1, preferred_pattern='weeks_5_to_17'),
            Course(id="BD4_L03_B", name="区块链技术及应用", course_type='theory_only', theory_hours=6,
                   teaching_class_count=1, preferred_pattern='weeks_16_to_17'),

        ],
        cohorts_map['物联网-4']: [
            Course(id="TOT4_L01", name="人工智能", course_type='theory_only', theory_hours=48, teaching_class_count=1,
                   preferred_pattern='weeks_5_to_17'),
            Course(id="TOT4_L02_A", name="区块链技术及应用", course_type='theory_only', theory_hours=26,
                   teaching_class_count=1, preferred_pattern='weeks_5_to_17'),
            Course(id="TOT4_L02_B", name="区块链技术及应用", course_type='theory_only', theory_hours=6,
                   teaching_class_count=1, preferred_pattern='weeks_16_to_17')
        ],
    }

    # 5. 教师与课程关联
    teacher_course_map = {
        "BD1_L01": "T19", "BD1_L02": "T14", "BD1_L03": "T07",
        "BD2_L01": "T11", "BD2_L02": "T16", "BD2_L03": "T04", "BD2_L04": "T04", "BD2_L05": "T12",
        "TOT2_L01": "T11", "TOT2_L02": "T16", "TOT2_L03": "T04", "TOT2_L04": "T04", "TOT2_L05": "T12",
        "BD3_L01": "T09", "BD3_L02": "T07", "BD3_L03": "T07", "BD3_L04": "T18", "BD3_L05": "T21",
        "BD3_L06": "T18", "BD3_L07": "T19", "BD3_L08": "T02", "BD3_L09": "T02",
        "TOT3_L01": "T02", "TOT3_L02": "T07", "TOT3_L03": "T18", "TOT3_L04": "T05", "TOT3_L05": "T21",
        "TOT3_L06": "T06", "TOT3_L07": "T06", "TOT3_L08": "T10",
        "BD4_L01_A": "T02", "BD4_L01_B": "T02", "BD4_L02": "T09", "BD4_L03_A": "T02", "BD4_L03_B": "T02",
        "TOT4_L01": "T09", "TOT4_L02_A": "T02", "TOT4_L02_B": "T02"
    }

    # 6. 教师偏好
    teacher_preferences = []
    # (修改点：去除了原先写死的校本部教师时间硬限制)
    # 添加其他老师的特定偏好可按照下例进行（如果是在代码层面直接配置）：
    '''
    teacher_preferences.extend([
        {'teacher_name': '刘寿强', 'course_name': '大数据安全与应用', 'preferred_slots': [(1, -1)]},
        {'teacher_name': '王晨', 'course_name': '应用随机过程', 'preferred_slots': [(3, p) for p in AFTERNOOM_PERIODS],
         'undesired_slots': [(1, p) for p in EVENING_PERIODS]}
        # `undesired_slots`: 教师不希望上课的时间。
        # `preferred_slots`: 教师偏好的上课时间。
    ])
    '''

    # 7. 固定课程 (已安排的公共课)
    subgroup_pre_assignment = {
        '大数据-1': {
            'group_A': float(1 / 6),
            'group_B': float(1 / 6),
            'group_C': float(1 / 6),
            'group_D': float(1 / 6),
            'group_E': float(1 / 6),
            'group_F': float(1 / 6),
        },
        '大数据-2': {
            'group_A': 0.5,
            'group_B': 0.5,
        },
        '物联网-2': {
            'default': 1.0
        },
        '大数据-3': {
            'default': 1.0
        },
        '物联网-3': {
            'default': 1.0
        },
        '大数据-4': {
            'default': 1.0
        },
        '物联网-4': {
            'default': 1.0
        }
    }
    fixed_schedule = [
        # 大数据大一
        {'cohort_id': '大数据-1', 'group_tag': 'group_A', 'course_name': '大学英语', 'teacher_name': '英语老师',
         'duration': 2,
         'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=2, period=7)},
        {'cohort_id': '大数据-1', 'group_tag': 'group_B', 'course_name': '大学英语', 'teacher_name': '英语老师',
         'duration': 2,
         'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=2, period=7)},
        {'cohort_id': '大数据-1', 'group_tag': 'group_C', 'course_name': '大学英语', 'teacher_name': '英语老师',
         'duration': 2,
         'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=4, period=3)},
        {'cohort_id': '大数据-1', 'group_tag': 'group_D', 'course_name': '大学英语', 'teacher_name': '英语老师',
         'duration': 2,
         'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=4, period=1)},
        {'cohort_id': '大数据-1', 'group_tag': 'group_E', 'course_name': '大学英语', 'teacher_name': '英语老师',
         'duration': 2,
         'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=2, period=7)},
        {'cohort_id': '大数据-1', 'group_tag': 'group_F', 'course_name': '大学英语', 'teacher_name': '英语老师',
         'duration': 2,
         'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=4, period=1)},
        {'cohort_id': '大数据-1', 'group_tag': 'group_A', 'course_name': '习近平新时代中国特色社会主义思想概论',
         'teacher_name': '政治老师', 'duration': 3,
         'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=1, period=5)},
        {'cohort_id': '大数据-1', 'group_tag': 'group_B', 'course_name': '习近平新时代中国特色社会主义思想概论',
         'teacher_name': '政治老师', 'duration': 3,
         'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=1, period=1)},
        {'cohort_id': '大数据-1', 'group_tag': 'group_C', 'course_name': '习近平新时代中国特色社会主义思想概论',
         'teacher_name': '政治老师', 'duration': 3,
         'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=1, period=1)},
        {'cohort_id': '大数据-1', 'group_tag': 'group_D', 'course_name': '习近平新时代中国特色社会主义思想概论',
         'teacher_name': '政治老师', 'duration': 3,
         'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=1, period=5)},
        {'cohort_id': '大数据-1', 'group_tag': 'group_E', 'course_name': '习近平新时代中国特色社会主义思想概论',
         'teacher_name': '政治老师', 'duration': 3,
         'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=2, period=1)},
        {'cohort_id': '大数据-1', 'group_tag': 'group_F', 'course_name': '习近平新时代中国特色社会主义思想概论',
         'teacher_name': '政治老师', 'duration': 3,
         'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=2, period=1)},
        {'cohort_id': '大数据-1', 'group_tag': 'group_A', 'course_name': '大学心理健康教育', 'teacher_name': '政治老师',
         'duration': 2,
         'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=2, period=3)},
        {'cohort_id': '大数据-1', 'group_tag': 'group_B', 'course_name': '大学心理健康教育', 'teacher_name': '政治老师',
         'duration': 2,
         'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=2, period=3)},
        {'cohort_id': '大数据-1', 'group_tag': 'group_C', 'course_name': '大学心理健康教育', 'teacher_name': '政治老师',
         'duration': 2,
         'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=2, period=7)},
        {'cohort_id': '大数据-1', 'group_tag': 'group_D', 'course_name': '大学心理健康教育', 'teacher_name': '政治老师',
         'duration': 2,
         'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=2, period=7)},
        {'cohort_id': '大数据-1', 'group_tag': 'group_E', 'course_name': '大学心理健康教育', 'teacher_name': '政治老师',
         'duration': 2,
         'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=3, period=3)},
        {'cohort_id': '大数据-1', 'group_tag': 'group_F', 'course_name': '大学心理健康教育', 'teacher_name': '政治老师',
         'duration': 2,
         'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=3, period=3)},
        {'cohort_id': '大数据-1', 'group_tag': 'group_A', 'course_name': '中国近现代史纲要', 'teacher_name': '政治老师',
         'duration': 2,
         'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=3, period=3)},
        {'cohort_id': '大数据-1', 'group_tag': 'group_B', 'course_name': '中国近现代史纲要', 'teacher_name': '政治老师',
         'duration': 2,
         'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=3, period=3)},
        {'cohort_id': '大数据-1', 'group_tag': 'group_C', 'course_name': '中国近现代史纲要', 'teacher_name': '政治老师',
         'duration': 2,
         'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=3, period=3)},
        {'cohort_id': '大数据-1', 'group_tag': 'group_D', 'course_name': '中国近现代史纲要', 'teacher_name': '政治老师',
         'duration': 2,
         'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=3, period=3)},
        {'cohort_id': '大数据-1', 'group_tag': 'group_E', 'course_name': '中国近现代史纲要', 'teacher_name': '政治老师',
         'duration': 2,
         'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=3, period=7)},
        {'cohort_id': '大数据-1', 'group_tag': 'group_F', 'course_name': '中国近现代史纲要', 'teacher_name': '政治老师',
         'duration': 2,
         'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=2, period=5)},
        {'cohort_id': '大数据-1', 'course_name': '大学日语', 'teacher_name': '日语老师', 'duration': 4,
         'week': DOUBLE_WEEKS, 'start_time': TimePoint(week=None, day=5, period=1)},
        {'cohort_id': '大数据-1', 'group_tag': 'group_A', 'course_name': '大学体育', 'teacher_name': '体育老师',
         'duration': 2,
         'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=1, period=1)},
        {'cohort_id': '大数据-1', 'group_tag': 'group_B', 'course_name': '大学体育', 'teacher_name': '体育老师',
         'duration': 2,
         'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=5, period=7)},
        {'cohort_id': '大数据-1', 'group_tag': 'group_C', 'course_name': '大学体育', 'teacher_name': '体育老师',
         'duration': 2,
         'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=5, period=7)},
        {'cohort_id': '大数据-1', 'group_tag': 'group_D', 'course_name': '大学体育', 'teacher_name': '体育老师',
         'duration': 2,
         'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=3, period=1)},
        {'cohort_id': '大数据-1', 'group_tag': 'group_E', 'course_name': '大学体育', 'teacher_name': '体育老师',
         'duration': 2, 'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=1, period=1)},
        {'cohort_id': '大数据-1', 'group_tag': 'group_F', 'course_name': '大学体育', 'teacher_name': '体育老师',
         'duration': 2, 'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=1, period=1)},
        {'cohort_id': '大数据-1', 'course_name': '形势与政策', 'teacher_name': '形势与政策老师', 'duration': 2,
         'week': [9, 10], 'start_time': TimePoint(week=None, day=2, period=9)},
        # 大数据大二
        {'cohort_id': '大数据-2', 'group_tag': 'group_A', 'course_name': '大学英语', 'teacher_name': '英语老师',
         'duration': 2,
         'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=2, period=1)},
        {'cohort_id': '大数据-2', 'group_tag': 'group_B', 'course_name': '大学英语', 'teacher_name': '英语老师',
         'duration': 2, 'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=2, period=5)},
        {'cohort_id': '大数据-2', 'group_tag': 'group_A', 'course_name': '大学物理', 'teacher_name': '物理老师',
         'duration': 2, 'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=1, period=5)},
        {'cohort_id': '大数据-2', 'group_tag': 'group_B', 'course_name': '大学物理', 'teacher_name': '物理老师',
         'duration': 2, 'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=1, period=3)},
        {'cohort_id': '大数据-2', 'course_name': '大学体育', 'teacher_name': '体育老师', 'duration': 2,
         'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=3, period=7)},
        {'cohort_id': '大数据-2', 'course_name': '形势与政策', 'teacher_name': '形势与政策老师', 'duration': 2,
         'week': [6, 7], 'start_time': TimePoint(week=None, day=3, period=9)},
        {'cohort_id': '大数据-2', 'group_tag': 'group_A', 'course_name': '马克思主义基本原理',
         'teacher_name': '政治老师', 'duration': 3,
         'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=2, period=5)},
        {'cohort_id': '大数据-2', 'group_tag': 'group_B', 'course_name': '马克思主义基本原理',
         'teacher_name': '政治老师', 'duration': 3, 'week': SEMESTER_WEEKS,
         'start_time': TimePoint(week=None, day=2, period=1)},
        {'cohort_id': '大数据-2', 'course_name': '大学日语', 'teacher_name': '日语老师', 'duration': 4,
         'week': DOUBLE_WEEKS, 'start_time': TimePoint(week=None, day=4, period=5)},
        {'cohort_id': '大数据-2', 'course_name': '大学基础物理实验', 'teacher_name': '物理老师', 'duration': 4,
         'week': list(range(7, 18, 2)), 'start_time': TimePoint(week=None, day=4, period=5)},
        # 物联网大二
        {'cohort_id': '物联网-2', 'course_name': '大学英语', 'teacher_name': '英语老师', 'duration': 2,
         'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=2, period=1)},
        {'cohort_id': '物联网-2', 'course_name': '大学体育', 'teacher_name': '体育老师', 'duration': 2,
         'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=2, period=3)},
        {'cohort_id': '物联网-2', 'course_name': '形势与政策', 'teacher_name': '形势与政策老师', 'duration': 2,
         'week': [8, 9], 'start_time': TimePoint(week=None, day=4, period=9)},
        {'cohort_id': '物联网-2', 'course_name': '马克思主义基本原理', 'teacher_name': '政治老师', 'duration': 3,
         'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=5, period=5)},
        {'cohort_id': '物联网-2', 'course_name': '大学日语', 'teacher_name': '日语老师', 'duration': 4,
         'week': DOUBLE_WEEKS, 'start_time': TimePoint(week=None, day=4, period=5)},
        {'cohort_id': '物联网-2', 'course_name': '大学基础物理实验', 'teacher_name': '物理老师', 'duration': 4,
         'week': list(range(7, 18, 2)), 'start_time': TimePoint(week=None, day=4, period=5)},
        {'cohort_id': '物联网-2', 'course_name': '大学物理', 'teacher_name': '物理老师', 'duration': 2,
         'week': SEMESTER_WEEKS, 'start_time': TimePoint(week=None, day=5, period=3)},
        # 大数据大三
        {'cohort_id': '大数据-3', 'course_name': '形势与政策', 'teacher_name': '形势与政策老师', 'duration': 2,
         'week': [10, 11], 'start_time': TimePoint(week=None, day=5, period=7)},
        {'cohort_id': '大数据-3', 'course_name': '思想政治理论社会实践', 'teacher_name': '政治老师', 'duration': 3,
         'week': [6, 7, 8, 9], 'start_time': TimePoint(week=None, day=3, period=9)},
        # 物联网大三
        {'cohort_id': '物联网-3', 'course_name': '形势与政策', 'teacher_name': '形势与政策老师', 'duration': 2,
         'week': [8, 9], 'start_time': TimePoint(week=None, day=3, period=9)},
        {'cohort_id': '物联网-3', 'course_name': '思想政治理论社会实践', 'teacher_name': '政治老师', 'duration': 3,
         'week': [6, 7, 8, 9], 'start_time': TimePoint(week=None, day=4, period=9)},
        {'cohort_id': '大数据-4', 'course_name': '形势与政策', 'teacher_name': '形势与政策老师', 'duration': 2,
         'week': [6, 7], 'start_time': TimePoint(week=None, day=3, period=9)},
        {'cohort_id': '物联网-4', 'course_name': '形势与政策', 'teacher_name': '形势与政策老师', 'duration': 2,
         'week': [6, 7], 'start_time': TimePoint(week=None, day=4, period=9)}
    ]

    # 将偏好同步到 Teacher 对象，以便算法在单机运行时直接读取
    for pref in teacher_preferences:
        for t in teachers_list:
            if t.name == pref.get('teacher_name'):
                if 'preferred_slots' in pref:
                    t.preferred_slots.extend(pref['preferred_slots'])
                if 'undesired_slots' in pref:
                    t.undesired_slots.extend(pref['undesired_slots'])
                break

    return teachers_list, rooms_list, cohorts_list, admin_classes, course_by_cohort, teacher_course_map, fixed_schedule, teacher_preferences, subgroup_pre_assignment