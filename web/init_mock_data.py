"""
模拟数据初始化脚本
用于填充测试数据到数据库
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from web.core.database import SessionLocal, engine, Base
from web.models.db_models import Cohort, AdminClass, Teacher, Room, Course, CombinedCourseGroup, FixedSchedule

def init_mock_data():
    """初始化模拟数据（先删除旧表，再重新建表并插入数据）"""
    # 先删除已有表，再重新创建表结构
    from web.core.database import Base as _Base, engine as _engine
    _Base.metadata.drop_all(bind=_engine)
    _Base.metadata.create_all(bind=_engine)

    db = SessionLocal()
    
    try:
        # 清空现有数据
        db.query(Course).delete()
        db.query(CombinedCourseGroup).delete()
        db.query(FixedSchedule).delete()
        db.query(AdminClass).delete()
        db.query(Cohort).delete()
        db.query(Teacher).delete()
        db.query(Room).delete()
        db.commit()
        
        print("已清空现有数据...")
        
        # ==================== 专业年级 ====================
        cohorts_data = [
            {"major": "计算机科学与技术", "grade": 2024},
            {"major": "计算机科学与技术", "grade": 2023},
            {"major": "软件工程", "grade": 2024},
            {"major": "软件工程", "grade": 2023},
            {"major": "数据科学与大数据技术", "grade": 2024},
            {"major": "人工智能", "grade": 2024},
        ]
        
        cohorts = []
        for data in cohorts_data:
            cohort = Cohort(**data)
            db.add(cohort)
            cohorts.append(cohort)
        db.commit()
        print(f"已创建 {len(cohorts)} 个专业年级")
        
        # 刷新获取ID
        for c in cohorts:
            db.refresh(c)
        
        # ==================== 行政班 ====================
        admin_classes = []
        for cohort in cohorts:
            # 每个专业年级创建3-4个班
            class_count = 4 if "计算机" in cohort.major else 3
            for i in range(1, class_count + 1):
                ac = AdminClass(
                    cohort_id=cohort.id,
                    class_index=i,
                    student_count=40 + (i * 5)  # 45, 50, 55...
                )
                db.add(ac)
                admin_classes.append(ac)
        db.commit()
        print(f"已创建 {len(admin_classes)} 个行政班")
        
        # ==================== 教师 ====================
        teachers_data = [
            {"name": "张三", "is_campus_teacher": True},
            {"name": "李四", "is_campus_teacher": True},
            {"name": "王五", "is_campus_teacher": False},
            {"name": "赵六", "is_campus_teacher": False},
            {"name": "钱七", "is_campus_teacher": True},
            {"name": "孙八", "is_campus_teacher": False},
            {"name": "周九", "is_campus_teacher": True},
            {"name": "吴十", "is_campus_teacher": False},
            {"name": "郑一一", "is_campus_teacher": True},
            {"name": "冯一二", "is_campus_teacher": False},
            {"name": "胡一五", "is_campus_teacher": False},
            {"name": "贾一六", "is_campus_teacher": False},
            {"name": "沈一七", "is_campus_teacher": False},
            {"name": "顾一八", "is_campus_teacher": False},
            {"name": "何一九", "is_campus_teacher": False},
            {"name": "朱二十", "is_campus_teacher": False},
            {"name": "秦二一", "is_campus_teacher": False},
            {"name": "薛二二", "is_campus_teacher": False},
        ]
        
        teachers = []
        for data in teachers_data:
            teacher = Teacher(**data)
            db.add(teacher)
            teachers.append(teacher)
        db.commit()
        print(f"已创建 {len(teachers)} 位教师")
        
        # 刷新获取ID
        for t in teachers:
            db.refresh(t)
        
        # ==================== 机房 ====================
        rooms_data = [
            {"name": "机房101", "capacity": 50},
            {"name": "机房102", "capacity": 50},
            {"name": "机房103", "capacity": 50},
            {"name": "机房201", "capacity": 60},
            {"name": "机房202", "capacity": 60},
            {"name": "机房203", "capacity": 60},
            {"name": "机房301", "capacity": 45},
            {"name": "机房302", "capacity": 45},
            {"name": "多媒体教室A", "capacity": 100},
            {"name": "多媒体教室B", "capacity": 100},
        ]
        
        rooms = []
        for data in rooms_data:
            room = Room(**data)
            db.add(room)
            rooms.append(room)
        db.commit()
        print(f"已创建 {len(rooms)} 个机房")
        
        # ==================== 合班课程组 ====================
        # 创建合班课程组（跨专业合班）
        combined_group1 = CombinedCourseGroup(
            name="数字逻辑电路合班组",
            description="数据科学与人工智能专业合班上课"
        )
        db.add(combined_group1)
        db.commit()
        db.refresh(combined_group1)
        print(f"已创建 1 个合班课程组")

        # ==================== 课程 ====================
        # 学时模式说明:
        # - 16学时: 单周每周一次, 每次连上2节
        # - 32学时: 每周一次, 每次连上2节
        # - 48学时: 每周一次, 每次连上3节
        # - 64学时: 每周二次, 每次连上2节
        # - 96学时: 每周三次, 每次连上2节
        courses_data = [
            # ==================== 上册课程 ====================
            # 计算机科学与技术 2024 - 上册
            {"name": "程序设计基础", "cohort_idx": 0, "teacher_idx": 0, "course_type": "mixed", 
             "theory_hours": 32, "lab_hours": 16, "total_hours": 48, "teaching_class_count": 2,
             "semester": "first", "sessions_per_week": 1, "duration_per_session": 3},
            {"name": "计算机导论", "cohort_idx": 0, "teacher_idx": 1, "course_type": "theory_only", 
             "theory_hours": 32, "lab_hours": 0, "total_hours": 32, "teaching_class_count": 1,
             "semester": "first", "sessions_per_week": 1, "duration_per_session": 2},
            
            # 计算机科学与技术 2023 - 上册
            {"name": "操作系统", "cohort_idx": 1, "teacher_idx": 3, "course_type": "mixed", 
             "theory_hours": 48, "lab_hours": 16, "total_hours": 64, "teaching_class_count": 2,
             "semester": "first", "sessions_per_week": 2, "duration_per_session": 2},
            {"name": "计算机网络", "cohort_idx": 1, "teacher_idx": 4, "course_type": "mixed", 
             "theory_hours": 48, "lab_hours": 16, "total_hours": 64, "teaching_class_count": 2,
             "semester": "first", "sessions_per_week": 2, "duration_per_session": 2,
             "is_campus_teacher": True},  # 校本部教师课程
            
            # 软件工程 2024 - 上册
            {"name": "Python程序设计", "cohort_idx": 2, "teacher_idx": 6, "course_type": "mixed", 
             "theory_hours": 32, "lab_hours": 32, "total_hours": 64, "teaching_class_count": 2,
             "semester": "first", "sessions_per_week": 2, "duration_per_session": 2},
            {"name": "软件工程导论", "cohort_idx": 2, "teacher_idx": 7, "course_type": "theory_only", 
             "theory_hours": 32, "lab_hours": 0, "total_hours": 32, "teaching_class_count": 1,
             "semester": "first", "sessions_per_week": 1, "duration_per_session": 2},
            
            # 软件工程 2023 - 上册
            {"name": "软件测试", "cohort_idx": 3, "teacher_idx": 8, "course_type": "mixed", 
             "theory_hours": 32, "lab_hours": 16, "total_hours": 48, "teaching_class_count": 1,
             "semester": "first", "sessions_per_week": 1, "duration_per_session": 3},
            
            # 数据科学 2024 - 上册 (包含合班课程)
            {"name": "大数据导论", "cohort_idx": 4, "teacher_idx": 0, "course_type": "theory_only", 
             "theory_hours": 32, "lab_hours": 0, "total_hours": 32, "teaching_class_count": 2,
             "semester": "first", "sessions_per_week": 1, "duration_per_session": 2},
            # 合班课程: 数字逻辑电路 (0.5教学班, 与人工智能专业合班)
            {"name": "数字逻辑电路", "cohort_idx": 4, "teacher_idx": 1, "course_type": "mixed", 
             "theory_hours": 32, "lab_hours": 16, "total_hours": 48, "teaching_class_count": 0.5,
             "semester": "first", "sessions_per_week": 1, "duration_per_session": 3, "combined_group": 1},
            
            # 人工智能 2024 - 上册 (包含合班课程)
            {"name": "人工智能导论", "cohort_idx": 5, "teacher_idx": 4, "course_type": "theory_only", 
             "theory_hours": 32, "lab_hours": 0, "total_hours": 32, "teaching_class_count": 1,
             "semester": "first", "sessions_per_week": 1, "duration_per_session": 2},
            # 合班课程: 数字逻辑电路 (0.5教学班, 与数据科学专业合班)
            {"name": "数字逻辑电路", "cohort_idx": 5, "teacher_idx": 1, "course_type": "mixed", 
             "theory_hours": 32, "lab_hours": 16, "total_hours": 48, "teaching_class_count": 0.5,
             "semester": "first", "sessions_per_week": 1, "duration_per_session": 3, "combined_group": 1},
            
            # ==================== 下册课程 ====================
            # 计算机科学与技术 2024 - 下册
            {"name": "数据结构", "cohort_idx": 0, "teacher_idx": 2, "course_type": "mixed", 
             "theory_hours": 48, "lab_hours": 16, "total_hours": 64, "teaching_class_count": 2,
             "semester": "second", "sessions_per_week": 2, "duration_per_session": 2},
            {"name": "离散数学", "cohort_idx": 0, "teacher_idx": 1, "course_type": "theory_only", 
             "theory_hours": 48, "lab_hours": 0, "total_hours": 48, "teaching_class_count": 1,
             "semester": "second", "sessions_per_week": 1, "duration_per_session": 3},
            
            # 计算机科学与技术 2023 - 下册
            {"name": "数据库原理", "cohort_idx": 1, "teacher_idx": 5, "course_type": "mixed", 
             "theory_hours": 32, "lab_hours": 16, "total_hours": 48, "teaching_class_count": 1,
             "semester": "second", "sessions_per_week": 1, "duration_per_session": 3},
            
            # 软件工程 2024 - 下册 (双教师课程示例)
            {"name": "Web开发技术", "cohort_idx": 2, "teacher_idx": 6, "course_type": "mixed", 
             "theory_hours": 32, "lab_hours": 32, "total_hours": 64, "teaching_class_count": 2,
             "semester": "second", "sessions_per_week": 2, "duration_per_session": 2,
             "dual_teacher": True, "second_teacher_idx": 8, "split_week": 8},  # 教师1上1-8周, 教师2上9-16周
            
            # 软件工程 2023 - 下册
            {"name": "软件项目管理", "cohort_idx": 3, "teacher_idx": 9, "course_type": "theory_only", 
             "theory_hours": 32, "lab_hours": 0, "total_hours": 32, "teaching_class_count": 1,
             "semester": "second", "sessions_per_week": 1, "duration_per_session": 2},
            
            # 数据科学 2024 - 下册
            {"name": "数据分析基础", "cohort_idx": 4, "teacher_idx": 2, "course_type": "mixed", 
             "theory_hours": 32, "lab_hours": 32, "total_hours": 64, "teaching_class_count": 1,
             "semester": "second", "sessions_per_week": 2, "duration_per_session": 2},
            
            # 人工智能 2024 - 下册
            {"name": "机器学习基础", "cohort_idx": 5, "teacher_idx": 6, "course_type": "mixed", 
             "theory_hours": 32, "lab_hours": 16, "total_hours": 48, "teaching_class_count": 2,
             "semester": "second", "sessions_per_week": 1, "duration_per_session": 3},
        ]
        
        courses = []
        for data in courses_data:
            course = Course(
                name=data["name"],
                cohort_id=cohorts[data["cohort_idx"]].id,
                teacher_id=teachers[data["teacher_idx"]].id,
                semester=data.get("semester", "first"),
                course_type=data["course_type"],
                theory_hours=data["theory_hours"],
                lab_hours=data["lab_hours"],
                total_hours=data.get("total_hours", data["theory_hours"] + data["lab_hours"]),
                teaching_class_count=data["teaching_class_count"],
                sessions_per_week=data.get("sessions_per_week", 1),
                duration_per_session=data.get("duration_per_session", 2),
                combined_group_id=combined_group1.id if data.get("combined_group") == 1 else None,
                dual_teacher_enabled=data.get("dual_teacher", False),
                second_teacher_id=teachers[data["second_teacher_idx"]].id if data.get("dual_teacher") else None,
                teacher_split_week=data.get("split_week", 8)
            )
            db.add(course)
            courses.append(course)
        db.commit()
        
        # 追加更多课程 - 确保每个专业至少有一门课程的teaching_class_count等于行政班数量
        # 这样才能确保每个行政班有独立的时间安排
        extra_courses_data = [
            # 计算机2024 - 4个行政班，需要teaching_class_count=4的课程
            {"name": "线性代数", "cohort_idx": 0, "teacher_idx": 8, "course_type": "theory_only",
             "theory_hours": 48, "lab_hours": 0, "teaching_class_count": 4,  # 匹配4个行政班
             "semester": "first"},
            {"name": "数字电路实验", "cohort_idx": 0, "teacher_idx": 2, "course_type": "lab_only",
             "theory_hours": 0, "lab_hours": 32, "teaching_class_count": 4,  # 匹配4个行政班
             "semester": "first"},
            # 计算机2023 - 4个行政班
            {"name": "教网技术概论", "cohort_idx": 1, "teacher_idx": 10, "course_type": "theory_only",
             "theory_hours": 32, "lab_hours": 0, "teaching_class_count": 4,  # 匹配4个行政班
             "semester": "first"},
            {"name": "并发编程", "cohort_idx": 1, "teacher_idx": 3, "course_type": "mixed",
             "theory_hours": 32, "lab_hours": 16, "teaching_class_count": 4,  # 匹配4个行政班
             "semester": "second"},
            # 软件2024 - 3个行政班
            {"name": "Java程序设计", "cohort_idx": 2, "teacher_idx": 6, "course_type": "mixed",
             "theory_hours": 32, "lab_hours": 32, "teaching_class_count": 3,  # 匹配3个行政班
             "semester": "first"},
            # 软件2023 - 3个行政班
            {"name": "Web前端基础", "cohort_idx": 3, "teacher_idx": 7, "course_type": "mixed",
             "theory_hours": 32, "lab_hours": 32, "teaching_class_count": 3,  # 匹配3个行政班
             "semester": "first"},
            # 数据科学2024 - 3个行政班
            {"name": "Python数据分析", "cohort_idx": 4, "teacher_idx": 11, "course_type": "mixed",
             "theory_hours": 32, "lab_hours": 32, "teaching_class_count": 3,  # 匹配3个行政班
             "semester": "first"},
            {"name": "数据可视化", "cohort_idx": 4, "teacher_idx": 12, "course_type": "mixed",
             "theory_hours": 32, "lab_hours": 16, "teaching_class_count": 3,
             "semester": "second"},
            # 人工智能2024 - 3个行政班
            {"name": "深度学习基础", "cohort_idx": 5, "teacher_idx": 13, "course_type": "mixed",
             "theory_hours": 32, "lab_hours": 16, "teaching_class_count": 3,  # 匹配3个行政班
             "semester": "first"},
            {"name": "自然语言处理", "cohort_idx": 5, "teacher_idx": 14, "course_type": "mixed",
             "theory_hours": 32, "lab_hours": 16, "teaching_class_count": 3,
             "semester": "second"},
        ]
        for data in extra_courses_data:
            course = Course(
                name=data["name"],
                cohort_id=cohorts[data["cohort_idx"]].id,
                teacher_id=teachers[data["teacher_idx"]].id,
                semester=data.get("semester", "first"),
                course_type=data["course_type"],
                theory_hours=data.get("theory_hours", 0),
                lab_hours=data.get("lab_hours", 0),
                total_hours=data.get("theory_hours", 0) + data.get("lab_hours", 0),
                teaching_class_count=data["teaching_class_count"],
                sessions_per_week=data.get("sessions_per_week", 1),
                duration_per_session=data.get("duration_per_session", 2),
                combined_group_id=None,
                dual_teacher_enabled=False,
                second_teacher_id=None,
                teacher_split_week=8
            )
            db.add(course)
        db.commit()
        
        # 添加公共课（cohort_id 为 NULL）
        public_courses_data = [
            {"name": "思想道德与法律基础", "teacher_idx": 15, "course_type": "theory_only",
             "theory_hours": 32, "lab_hours": 0, "teaching_class_count": 1, "semester": "first"},
            {"name": "形势与政策", "teacher_idx": 16, "course_type": "theory_only",
             "theory_hours": 16, "lab_hours": 0, "teaching_class_count": 1, "semester": "first"},
            {"name": "军事理论", "teacher_idx": 17, "course_type": "theory_only",
             "theory_hours": 16, "lab_hours": 0, "teaching_class_count": 1, "semester": "second"},
            {"name": "大学生心理健康", "teacher_idx": 15, "course_type": "theory_only",
             "theory_hours": 32, "lab_hours": 0, "teaching_class_count": 1, "semester": "both"},
        ]
        for data in public_courses_data:
            course = Course(
                name=data["name"],
                cohort_id=None,  # 公共课无专业年级
                teacher_id=teachers[data["teacher_idx"]].id,
                semester=data.get("semester", "first"),
                course_type=data["course_type"],
                theory_hours=data.get("theory_hours", 0),
                lab_hours=data.get("lab_hours", 0),
                total_hours=data.get("theory_hours", 0) + data.get("lab_hours", 0),
                teaching_class_count=data["teaching_class_count"],
            )
            db.add(course)
        db.commit()
        
        # 统计
        total_courses = db.query(Course).count()
        first_semester = db.query(Course).filter(Course.semester == "first").count()
        second_semester = db.query(Course).filter(Course.semester == "second").count()
        dual_teacher = db.query(Course).filter(Course.dual_teacher_enabled == True).count()
        combined = db.query(Course).filter(Course.combined_group_id.isnot(None)).count()
        public_courses = db.query(Course).filter(Course.cohort_id.is_(None)).count()
        print(f"已创建 {total_courses} 门课程 (上册:{first_semester}, 下册:{second_semester}, 双教师:{dual_teacher}, 合班:{combined}, 公共课:{public_courses})")
        
        # ==================== 公共课/固定课程 ====================
        # 计算机科学与技术 2024 - 英语课（不同行政班在不同时间上课）
        fixed_schedules = [
            # 英语课 - 1班和2班 周一上午
            {"cohort_idx": 0, "course_name": "大学英语", "teacher_name": "外聘教师1", 
             "day": 1, "period": 1, "duration": 2, "weeks": list(range(1, 17)),
             "group_tag": "A", "admin_class_indices": [1, 2]},
            # 英语课 - 3班 周二上午
            {"cohort_idx": 0, "course_name": "大学英语", "teacher_name": "外聘教师1", 
             "day": 2, "period": 1, "duration": 2, "weeks": list(range(1, 17)),
             "group_tag": "B", "admin_class_indices": [3]},
            # 体育课 - 全专业同一时间 (不需要标签区分)
            {"cohort_idx": 0, "course_name": "体育", "teacher_name": "体育教师", 
             "day": 3, "period": 5, "duration": 2, "weeks": list(range(1, 17)),
             "group_tag": None, "admin_class_indices": []},
        ]
        
        fixed_count = 0
        for fs_data in fixed_schedules:
            fs = FixedSchedule(
                cohort_id=cohorts[fs_data["cohort_idx"]].id,
                semester="first",
                course_name=fs_data["course_name"],
                teacher_name=fs_data["teacher_name"],
                day=fs_data["day"],
                period=fs_data["period"],
                duration=fs_data["duration"],
                weeks=fs_data["weeks"],
                group_tag=fs_data["group_tag"],
                requires_tag=fs_data["group_tag"] is not None,
                admin_class_indices=fs_data["admin_class_indices"]
            )
            db.add(fs)
            fixed_count += 1
        db.commit()
        
        # 追加一些公共课/固定课
        extra_fixed = [
            {"cohort_idx": 1, "course_name": "大学英语", "teacher_name": "外聘教师2",
             "day": 1, "period": 3, "duration": 2, "weeks": list(range(1, 17)),
             "group_tag": None, "admin_class_indices": []},
            {"cohort_idx": 2, "course_name": "大学英语", "teacher_name": "外聘教师1",
             "day": 2, "period": 3, "duration": 2, "weeks": list(range(1, 17)),
             "group_tag": None, "admin_class_indices": []},
            {"cohort_idx": 3, "course_name": "大学英语", "teacher_name": "外聘教师3",
             "day": 4, "period": 3, "duration": 2, "weeks": list(range(1, 17)),
             "group_tag": None, "admin_class_indices": []},
            {"cohort_idx": 4, "course_name": "大学英语", "teacher_name": "外聘教师4",
             "day": 5, "period": 3, "duration": 2, "weeks": list(range(1, 17)),
             "group_tag": None, "admin_class_indices": []},
            {"cohort_idx": 5, "course_name": "大学体育", "teacher_name": "体育教师3",
             "day": 5, "period": 7, "duration": 2, "weeks": list(range(1, 17)),
             "group_tag": None, "admin_class_indices": []},
            {"cohort_idx": 0, "course_name": "体育", "teacher_name": "体育教师1",
             "day": 4, "period": 7, "duration": 2, "weeks": list(range(1, 17)),
             "group_tag": None, "admin_class_indices": []},
        ]
        for fs_data in extra_fixed:
            fs = FixedSchedule(
                cohort_id=cohorts[fs_data["cohort_idx"]].id,
                semester="first",
                course_name=fs_data["course_name"],
                teacher_name=fs_data["teacher_name"],
                day=fs_data["day"],
                period=fs_data["period"],
                duration=fs_data["duration"],
                weeks=fs_data["weeks"],
                group_tag=fs_data["group_tag"],
                requires_tag=fs_data["group_tag"] is not None,
                admin_class_indices=fs_data["admin_class_indices"]
            )
            db.add(fs)
        db.commit()
        fixed_count = db.query(FixedSchedule).count()
        print(f"已创建 {fixed_count} 个固定课程/公共课")
        
        print("\n" + "="*60)
        print("模拟数据初始化完成！")
        print("="*60)
        print(f"  专业年级:   {len(cohorts)} 个")
        print(f"  行政班:     {len(admin_classes)} 个")
        campus_teacher_count = len([t for t in teachers_data if t['is_campus_teacher']])
        print(f"  教师:       {len(teachers)} 位 (校本部:{campus_teacher_count} 位)")
        print(f"  机房:       {len(rooms)} 个")
        print(f"  课程:       {total_courses} 门")
        print(f"    - 上册:   {first_semester} 门")
        print(f"    - 下册:   {second_semester} 门")
        print(f"    - 双教师: {dual_teacher} 门")
        print(f"    - 合班:   {combined} 门")
        print(f"    - 公共课: {public_courses} 门")
        print(f"  合班课程组: 1 个")
        print(f"  固定课程:   {fixed_count} 个")
        print("="*60)
        
    except Exception as e:
        db.rollback()
        print(f"错误: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    init_mock_data()
