# 排课系统 (Course Scheduling System)

一个基于遗传算法和确定性预排课策略的智能排课系统，支持Web界面管理和API调用。

## 目录结构

```
paike/
├── main.py                    # 命令行排课入口
├── data_processor.py          # 数据预处理器
├── campus_pre_scheduler.py    # 校本部教师确定性排课算法
├── deap_scheduler.py          # 遗传算法排课引擎 (DEAP框架)
├── result_parser.py           # 结果解析与Excel导出
├── data_setup1.py             # 上册学期数据配置
├── data_setup2.py             # 下册学期数据配置
│
├── models/                    # 算法模型定义
│   ├── class_group.py         # 专业年级、行政班、虚拟子组、教学班
│   ├── course.py              # 课程定义
│   ├── teacher.py             # 教师定义
│   ├── room.py                # 机房定义
│   └── time_definition.py     # 时间定义（周次、星期、节次）
│
└── web/                       # Web应用层
    ├── main.py                # FastAPI 应用入口
    ├── init_mock_data.py      # 测试数据初始化
    │
    ├── api/                   # RESTful API 路由
    │   ├── class_api.py       # 班级管理 API
    │   ├── teacher_api.py     # 教师管理 API
    │   ├── room_api.py        # 机房管理 API
    │   ├── course_api.py      # 课程管理 API
    │   └── schedule_api.py    # 排课管理 API
    │
    ├── core/                  # 核心配置
    │   ├── config.py          # 应用配置
    │   └── database.py        # 数据库连接
    │
    ├── models/                # 数据库模型 (SQLAlchemy ORM)
    │   └── db_models.py       # 所有数据表定义
    │
    ├── schemas/               # Pydantic 数据校验
    │   └── schemas.py         # 请求/响应模型
    │
    ├── services/              # 业务逻辑层
    │   └── schedule_service.py # 排课服务（整合算法）
    │
    └── frontend/              # 前端界面
        └── index.html         # Vue 3 单页应用
```

---

## 系统架构

```
┌──────────────────────────────────────────────────────────────────┐
│                        前端界面 (Vue 3)                           │
│         班级管理 | 教师管理 | 机房管理 | 课程管理 | 排课管理        │
└──────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│                     FastAPI Web 服务层                            │
│                                                                  │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌────────────┐ │
│  │ class_api   │ │ teacher_api │ │ course_api  │ │schedule_api│ │
│  └─────────────┘ └─────────────┘ └─────────────┘ └────────────┘ │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                  ScheduleService (排课服务)                   │  │
│  │  • 数据库 ↔ 算法对象转换                                      │  │
│  │  • 学期筛选 (上册/下册)                                        │  │
│  │  • 虚拟子组 → 行政班映射                                       │  │
│  │  • 结果持久化                                                 │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│                       排课算法层                                  │
│                                                                  │
│  ┌─────────────────────┐      ┌─────────────────────────────┐   │
│  │   DataPreprocessor  │─────▶│     教学班 & 子组生成         │   │
│  │   (数据预处理器)      │      │  • 合班课程处理               │   │
│  └─────────────────────┘      │  • 分阶段教师处理              │   │
│                               └─────────────────────────────┘   │
│                                           │                      │
│              ┌────────────────────────────┼────────────────┐     │
│              │                            │                │     │
│              ▼                            ▼                │     │
│  ┌─────────────────────┐      ┌─────────────────────┐     │     │
│  │  CampusScheduler    │      │   DeapScheduler     │     │     │
│  │  (校本部确定性排课)   │      │   (遗传算法排课)     │     │     │
│  │                     │      │                     │     │     │
│  │  • 确定性时间槽分配   │      │  • DEAP 框架        │     │     │
│  │  • 优先处理校本部教师 │      │  • Numba JIT 加速   │     │     │
│  │  • 支持补课安排       │      │  • 多进程并行计算    │     │     │
│  └─────────────────────┘      └─────────────────────┘     │     │
│              │                            │                │     │
│              └────────────────────────────┼────────────────┘     │
│                                           ▼                      │
│                              ┌─────────────────────┐            │
│                              │    合并最终课表      │            │
│                              └─────────────────────┘            │
└──────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│                     PostgreSQL 数据库                             │
│                                                                  │
│  cohorts | admin_classes | teachers | rooms | courses            │
│  schedule_sessions | schedule_results | fixed_schedules          │
│  teacher_preferences | subgroup_assignments | combined_groups    │
└──────────────────────────────────────────────────────────────────┘
```

---

## 核心组件说明

### 1. 数据预处理器 (`data_processor.py`)

**职责**：将原始数据转换为排课算法所需的结构化对象。

**核心功能**：
- **子组生成**：根据教学班数量计算最小公倍数，生成虚拟子组 (SubGroup)
- **教学班创建**：为每门课程创建教学班 (TeachingClass)，处理合班课程
- **分阶段教师**：支持一门课程不同周次由不同教师授课（如1-8周张老师，9-16周李老师）
- **子组标签分配**：支持公共课的分班标签（用于区分不同时间点上课的学生群体）

**关键数据结构**：
```python
# 虚拟子组 - 代表可独立排课的最小学生单元
SubGroup(id="SG_大数据1_1", cohort=Cohort, fixed_schedule_tag="A")

# 教学班 - 代表一次具体的授课安排
TeachingClass(id="TC_C01_1", course=Course, teacher_name="张三", 
              phase="1-8周", phase_weeks=(1, 8))

# 子组映射 - 教学班ID → 包含的子组列表
tc_to_sg_map = {"TC_C01_1": [SubGroup1, SubGroup2, ...]}
```

### 2. 校本部教师排课器 (`campus_pre_scheduler.py`)

**职责**：为校本部教师进行确定性时间槽分配，优先保证其时间偏好。

**算法特点**：
- **贪心策略**：按年级、教师总课时排序，优先安排高年级和课时多的教师
- **资源网格**：维护教师、子组、机房的占用状态矩阵
- **补课机制**：当无法在常规时间安排时，尝试在其他时间段补课
- **周次模式**：支持单周、双周、每周、自定义周次模式

**时间偏好（校本部教师默认）**：
- 不希望：周四、周五、下午、晚上
- 优先安排：周一至周三上午

### 3. 遗传算法排课器 (`deap_scheduler.py`)

**职责**：使用遗传算法为非校本部教师课程寻找最优排课方案。

**算法参数**：
```python
POP_SIZE = 1000       # 种群大小
MAX_GEN = 1500        # 最大迭代代数
CXPB = 0.9            # 交叉概率
MUTPB = 0.4           # 变异概率
HALL_OF_FAME_SIZE = 10  # 精英保留数
```

**适应度函数（惩罚项）**：

| 约束类型 | 权重 | 说明 |
|---------|------|------|
| 教师时间冲突 | 10000 | 同一教师同一时间只能上一门课 |
| 子组时间冲突 | 10000 | 同一子组同一时间只能上一门课 |
| 机房冲突 | 8000 | 同一机房同一时间只能安排一门课 |
| 不希望时间段 | 1000 | 安排在教师不希望的时间段 |
| 同课程时间不一致 | 100 | 同一课程不同阶段的时间点不同 |
| 同组一天多课 | 200 | 同一子组同一天上同一门课多次 |
| 全天满课 | 70 | 子组某半天4节课全满 |
| 周四安排 | 30 | 课程安排在周四 |
| 第一节安排 | 10 | 课程安排在第一节 |

**优化技术**：
- **Numba JIT**：适应度函数使用 `@numba.jit` 加速
- **多进程**：使用 `multiprocessing.Pool` 并行评估种群
- **动态权重**：软约束权重随迭代进度逐渐增加

### 4. 排课服务 (`web/services/schedule_service.py`)

**职责**：作为Web层与算法层的桥梁，协调整个排课流程。

**核心方法**：

```python
class ScheduleService:
    def start_scheduling(self, cohort_ids=None, semester="first") -> str:
        """
        启动排课流程
        
        Args:
            cohort_ids: 指定专业年级ID列表，None表示全部
            semester: "first"(上册) 或 "second"(下册)
        
        Returns:
            session_id: 排课会话ID
        """
    
    def _convert_db_to_algo_objects(self, semester) -> Tuple:
        """将数据库模型转换为算法对象"""
    
    def _compute_subgroup_to_admin_mapping(self, subgroups, cohort_key) -> Dict:
        """计算虚拟子组到行政班的映射关系"""
    
    def _save_results(self, session_id, results, ...) -> None:
        """保存排课结果到数据库"""
```

**虚拟子组 → 行政班映射算法**：
```
假设：专业年级有 4 个行政班，生成了 8 个虚拟子组

子组分配：
  SG_1, SG_2 → 1班
  SG_3, SG_4 → 2班
  SG_5, SG_6 → 3班
  SG_7, SG_8 → 4班

当子组数不能整除行政班数时，按比例分配
```

---

## 数据库模型

### 核心表结构

```sql
-- 专业年级
cohorts (id, major, grade, created_at)

-- 行政班
admin_classes (id, cohort_id, class_index, student_count)

-- 教师
teachers (id, name, is_campus_teacher, created_at)

-- 课程
courses (
    id, name, cohort_id, teacher_id,
    semester,              -- 学期: first/second/both
    course_type,           -- 类型: theory_only/mixed/lab_only
    theory_hours, lab_hours, teaching_class_count,
    dual_teacher_enabled,  -- 是否双教师
    second_teacher_id,     -- 第二教师
    teacher_split_week,    -- 教师切换周次
    phase_teachers,        -- 分阶段教师配置 JSON
    combined_group_id,     -- 合班课程组
    preferred_pattern      -- 排课周次模式
)

-- 排课会话
schedule_sessions (id, session_id, semester, status, fitness_score, message)

-- 排课结果
schedule_results (
    id, session_id, teaching_class_id,
    course_name, teacher_name,
    week, day, period, duration,
    room_name, is_lab, is_combined, is_fixed,
    cohort_id, admin_class_id  -- 行政班关联
)
```

---

## 快速启动

### 环境要求

- Python 3.9+
- PostgreSQL 12+
- 依赖包：见下方安装命令

### 1. 安装依赖

```bash
pip install fastapi uvicorn sqlalchemy psycopg2-binary pydantic numpy deap numba openpyxl
```

### 2. 配置数据库

编辑 `web/core/config.py` 或设置环境变量：

```python
# 默认配置
DATABASE_URL = "postgresql://postgres:1478963a@localhost:5433/paike_db"
```

或使用环境变量：
```bash
# Windows PowerShell
$env:DATABASE_URL = "postgresql://user:password@localhost:5432/paike_db"

# Linux/Mac
export DATABASE_URL="postgresql://user:password@localhost:5432/paike_db"
```

### 3. 初始化数据库

```bash
# 进入项目目录
cd C:\project\python\danzi\2\paike\paike

# 初始化测试数据（可选）
python -c "from web.init_mock_data import init_mock_data; init_mock_data()"
```

### 4. 启动Web服务

```bash
# 方式一：直接运行
python -m uvicorn web.main:app --host 0.0.0.0 --port 8000 --reload

# 方式二：通过模块运行
python -m web.main
```

### 5. 访问系统

- **前端界面**: http://localhost:8000
- **API文档 (Swagger)**: http://localhost:8000/docs
- **API文档 (ReDoc)**: http://localhost:8000/redoc

### 6. 命令行排课（独立模式）

如需直接使用命令行排课（不经过Web）：

```bash
cd C:\project\python\danzi\2\paike\paike
python main.py
# 根据提示选择：上册 或 下册
```

输出文件：`Final_Schedule_上册_perfect.xlsx` 或 `Final_Schedule_下册_perfect.xlsx`

---

## API 快速参考

### 班级管理
```http
GET    /api/cohorts                    # 获取所有专业年级
POST   /api/cohorts                    # 创建专业年级
GET    /api/cohorts/{id}/classes       # 获取专业年级下的行政班
POST   /api/cohorts/{id}/classes       # 添加行政班
```

### 教师管理
```http
GET    /api/teachers                   # 获取所有教师
POST   /api/teachers                   # 添加教师
PUT    /api/teachers/{id}              # 更新教师
DELETE /api/teachers/{id}              # 删除教师
```

### 课程管理
```http
GET    /api/courses                    # 获取所有课程 (?semester=first)
POST   /api/courses                    # 添加课程
PUT    /api/courses/{id}               # 更新课程
DELETE /api/courses/{id}               # 删除课程
```

### 排课管理
```http
POST   /api/schedule/start             # 开始排课 {semester: "first"}
GET    /api/schedule/sessions          # 获取排课会话列表
GET    /api/schedule/sessions/{id}     # 获取排课会话详情
GET    /api/schedule/results/{id}      # 获取排课结果 (?admin_class_id=1)
DELETE /api/schedule/sessions/{id}     # 删除排课会话
```

---

## 配置说明

### 课程学期配置

```json
{
  "semester": "first",    // 上册
  "semester": "second",   // 下册
  "semester": "both"      // 全年（两学期都排）
}
```

### 双教师配置

```json
{
  "dual_teacher_enabled": true,
  "teacher_id": 1,           // 1-8周教师
  "second_teacher_id": 2,    // 9-16周教师
  "teacher_split_week": 8    // 切换周次
}
```

### 分阶段教师配置（高级）

```json
{
  "phase_teachers": {
    "1-8周": [1, 8, 1],      // [开始周, 结束周, 教师ID]
    "9-16周": [9, 16, 2]
  }
}
```

### 周次模式

| 模式 | 说明 | 周次 |
|-----|------|------|
| `single_week` | 单周 | 1,3,5,7,9,11,13,15 |
| `double_week` | 双周 | 2,4,6,8,10,12,14,16 |
| `weeks_1_to_8` | 前8周 | 1-8 |
| `weeks_9_to_16` | 后8周 | 9-16 |
| `weeks_5_to_16` | 毕业年级 | 5-16 |
| `weeks_5_to_17` | 毕业年级+17周 | 5-17 |

---

## 常见问题

### Q: 排课失败，提示惩罚分数很高
**A**: 可能原因：
1. 教师课时过多，无法满足时间约束
2. 机房数量不足
3. 存在无法调和的时间偏好冲突

尝试：增加机房、调整教师课时分配、放宽时间偏好

### Q: 校本部教师课程没有排好
**A**: 检查：
1. 教师的 `is_campus_teacher` 是否设为 `true`
2. 课程是否关联了正确的教师
3. 是否存在过多的时间约束导致无解

### Q: 虚拟子组和行政班对应关系不正确
**A**: 虚拟子组数量由课程的 `teaching_class_count` 最小公倍数决定。确保行政班数量与课程配置匹配。

---

## 技术栈

- **后端**: Python 3.9+, FastAPI, SQLAlchemy, PostgreSQL
- **算法**: DEAP (遗传算法), Numba (JIT加速), NumPy
- **前端**: Vue 3 (CDN), Tailwind CSS (CDN)
- **API文档**: Swagger UI, ReDoc

---

## License

MIT License
