# 排课系统 (Paike - Course Scheduling System)

一个基于遗传算法和确定性预排课策略的智能高校排课系统，支持Web界面管理、API调用和手动课程调整。

---

## 目录

1. [项目概述](#项目概述)
2. [系统架构](#系统架构)
3. [项目结构](#项目结构)
4. [核心组件](#核心组件)
5. [快速启动](#快速启动)
6. [前端功能](#前端功能)
7. [API 文档](#api-文档)
8. [数据库设计](#数据库设计)
9. [配置说明](#配置说明)
10. [常见问题](#常见问题)

---

## 项目概述

### 功能特性

- **智能排课**：采用遗传算法 (DEAP) 和确定性算法结合
- **校本部优先**：对校本部教师的时间偏好进行优先满足
- **灵活的课程配置**：支持
  - 合班课程（多个专业共同修读）
  - 双教师教学（同一课程分阶段由不同教师授课）
  - 多教学班分班（同一课程分多个班级讲授）
  - 理论课与实验课分离排课
  - 固定课程（如公共课、体育等）

- **Web管理界面**：
  - 班级、教师、机房、课程管理
  - 教师时间偏好设置
  - 排课历史记录与结果查看
  - 课表导出（Excel格式）
  - **手动课程调整**：支持拖拽调课，实时冲突检测

- **多学期支持**：上册/下册分别排课

---

## 系统架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                        前端界面 (Vue 3 + Tailwind)                    │
│     班级管理 | 教师管理 | 机房管理 | 课程管理 | 课表查看 | 调课编辑    │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        FastAPI Web 服务层                            │
│                                                                     │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│  │class_api │ │teach_api │ │room_api  │ │cours_api │ │sched_api │ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘ │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │          ScheduleService (排课服务层)                          │  │
│  │  • 数据库 ↔ 算法对象转换  • 学期筛选  • 子组→行政班映射          │  │
│  │  • 冲突检测  • 调课执行   • 结果持久化                           │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          排课算法层                                   │
│                                                                     │
│  ┌─────────────────────┐          ┌──────────────────────────┐    │
│  │ DataPreprocessor    │─────────▶│  教学班 & 虚拟子组生成     │    │
│  │ (数据预处理器)        │          │  • 合班课程处理           │    │
│  └─────────────────────┘          │  • 分阶段教师处理          │    │
│                                   └──────────────────────────┘    │
│           ┌──────────────────────────────┬──────────────────────┐ │
│           │                              │                      │ │
│           ▼                              ▼                      │ │
│  ┌──────────────────┐      ┌──────────────────────┐             │ │
│  │ CampusScheduler  │      │   DeapScheduler      │             │ │
│  │ (校本部排课)      │      │   (遗传算法排课)      │             │ │
│  │                  │      │                      │             │ │
│  │ • 确定性时间分配  │      │  • DEAP 框架         │             │ │
│  │ • 优先处理校本部  │      │  • Numba JIT 加速    │             │ │
│  │ • 支持补课安排    │      │  • 多进程并行计算     │             │ │
│  └──────────────────┘      └──────────────────────┘             │ │
│           │                              │                      │ │
│           └──────────────────┬───────────┘                       │ │
│                              ▼                                   │ │
│                    ┌─────────────────┐                           │ │
│                    │  合并最终课表    │                           │ │
│                    └─────────────────┘                           │ │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      PostgreSQL 数据库                               │
│                                                                     │
│  cohorts | admin_classes | teachers | rooms | courses              │
│  schedule_sessions | schedule_results | fixed_schedules            │
│  teacher_preferences | subgroup_assignments | combined_groups      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 项目结构

```
paike/
├── README.md                    # 项目文档（本文件）
├── main.py                      # 命令行排课入口
├── data_processor.py            # 数据预处理器（DB → 算法对象）
├── campus_pre_scheduler.py      # 校本部教师确定性排课算法
├── deap_scheduler.py            # 遗传算法排课引擎 (DEAP框架)
├── result_parser.py             # 结果解析与Excel导出
├── data_setup1.py               # 上册学期数据配置示例
├── data_setup2.py               # 下册学期数据配置示例
│
├── models/                      # 算法模型定义
│   ├── class_group.py           # 专业年级、行政班、虚拟子组、教学班
│   ├── course.py                # 课程定义
│   ├── teacher.py               # 教师定义
│   ├── room.py                  # 机房定义
│   └── time_definition.py       # 时间定义（周次、星期、节次）
│
└── web/                         # Web应用层（FastAPI）
    ├── main.py                  # FastAPI 应用入口
    ├── init_mock_data.py        # 测试数据初始化
    │
    ├── api/                     # RESTful API 路由
    │   ├── class_api.py         # 班级管理 API
    │   ├── teacher_api.py       # 教师管理 API (含偏好设置)
    │   ├── room_api.py          # 机房管理 API
    │   ├── course_api.py        # 课程管理 API
    │   └── schedule_api.py      # 排课管理 & 调课 API
    │
    ├── core/                    # 核心配置
    │   ├── config.py            # 应用配置
    │   └── database.py          # 数据库连接
    │
    ├── models/                  # 数据库模型 (SQLAlchemy ORM)
    │   └── db_models.py         # 所有数据表定义
    │
    ├── schemas/                 # Pydantic 数据校验
    │   └── schemas.py           # 请求/响应模型
    │
    ├── services/                # 业务逻辑层
    │   └── schedule_service.py  # 排课服务（整合算法）
    │
    └── frontend/                # 前端界面
        └── index.html           # Vue 3 单页应用
```

---

## 核心组件

### 1. 数据预处理器 (DataPreprocessor)

**文件**：`data_processor.py`

**职责**：将数据库中的原始数据转换为排课算法所需的结构化对象。

**核心功能**：

- **虚拟子组生成**：根据各课程的教学班数量计算最小公倍数，生成虚拟子组
  - 虚拟子组是可独立排课的最小学生单元
  - 例：课A有2个教学班，课B有3个教学班 → LCM(2,3)=6个虚拟子组

- **教学班创建**：为每门课程创建教学班对象
  - 处理合班课程（多个专业共同修读）
  - 处理双教师课程
  - 处理分阶段教师课程

- **分阶段教师支持**：
  - 允许同一课程在不同周次由不同教师授课
  - 例：第1-8周由张老师，第9-16周由李老师

**关键数据结构**：

```python
# 虚拟子组 - 代表可独立排课的最小学生单元
class SubGroup:
    id: str                      # "SG_大数据科学与技术大二2023_1"
    cohort: Cohort               # 所属专业年级
    fixed_schedule_tag: str      # 分班标签，用于固定课程分配

# 教学班 - 代表一次具体的授课安排
class TeachingClass:
    id: str                      # "TC_C35_1"
    course: Course
    teacher_name: str
    phase_weeks: List[int]       # 该教师负责的周次范围 [1,8] 表示1-8周

# 子组映射
tc_to_sg_map = {
    "TC_C35_1": [SG1, SG2, SG3],  # 教学班1包含的所有子组
    "TC_C35_2": [SG4, SG5, SG6]   # 教学班2包含的所有子组
}
```

### 2. 校本部教师排课器 (CampusScheduler)

**文件**：`campus_pre_scheduler.py`

**职责**：为校本部教师进行确定性的时间槽分配，优先满足其时间偏好。

**算法特点**：

- **贪心策略**：按年级（高年级优先）和教师总课时（课时多优先）排序
- **资源网格**：维护教师、子组、机房的占用状态矩阵 (week × day × period)
- **补课机制**：当无法在常规时间安排时，支持补课（如周末、晚间）
- **周次模式**：支持单周、双周、每周、自定义周次等多种模式

**校本部教师的默认时间偏好**：

| 偏好 | 说明 |
|------|------|
| 不希望 | 周四、周五、下午(5-8节)、晚上(9-11节) |
| 优先   | 周一至周三、上午(1-4节) |

### 3. 遗传算法排课器 (DeapScheduler)

**文件**：`deap_scheduler.py`

**职责**：使用遗传算法为非校本部教师课程寻找最优排课方案。

**算法参数**：

```python
POP_SIZE = 1000              # 种群大小
MAX_GEN = 300                # 最大迭代代数
CXPB = 0.9                   # 交叉概率（遗传算子应用概率）
MUTPB = 0.4                  # 变异概率
HALL_OF_FAME_SIZE = 10       # 精英保留数（保留最佳个体）
```

**适应度函数（惩罚项）**：

| 约束类型 | 权重 | 说明 |
|---------|------|------|
| **硬约束** | | |
| 教师时间冲突 | 10000 | 同一教师同一时间只能上一门课 |
| 子组时间冲突 | 10000 | 同一子组同一时间只能上一门课 |
| 机房冲突 | 8000 | 同一机房同一时间只能安排一门课 |
| **软约束** | | |
| 不希望时间段 | 1000 | 安排在教师不希望的时间段（需配置） |
| 同课程时间不一致 | 100 | 同一课程理论课和实验课、不同阶段的时间点应相同 |
| 同组一天多课 | 200 | 同一子组同一天上同一门课多次（降低学生疲劳） |
| 连续4节课 | 70 | 子组某半天(1-4节或5-8节)4节课全满 |
| 周四安排 | 30 | 课程安排在周四（视为不太优先） |
| 第一节安排 | 10 | 课程安排在第一节（早起不方便） |

**优化技术**：

- **Numba JIT**：适应度函数使用 `@numba.jit(nopython=True)` 编译为机器码，提升计算速度20-50倍
- **多进程并行**：使用 `multiprocessing.Pool` 并行评估种群中的个体
- **动态权重**：软约束权重随迭代进度逐渐增加，早期关注硬约束，后期优化软约束

### 4. 排课服务 (ScheduleService)

**文件**：`web/services/schedule_service.py`

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
        # 1. 从数据库加载数据
        # 2. 转换为算法对象
        # 3. 执行CampusScheduler（校本部教师）
        # 4. 执行DeapScheduler（其他教师）
        # 5. 合并结果
        # 6. 保存到数据库
        # 7. 计算惩罚分数和冲突详情
        
    def _convert_db_to_algo_objects(self, semester) -> Tuple:
        """将数据库模型转换为算法对象"""
        # 返回: (teachers_list, rooms_list, subgroups, teaching_classes, 
        #        tc_to_sg_map, fixed_schedule, teacher_preferences)
        
    def _compute_subgroup_to_admin_mapping(self, subgroups, cohort_key) -> Dict:
        """
        计算虚拟子组到行政班的映射关系
        
        算法：按比例分配虚拟子组到行政班
        例：6个虚拟子组，4个行政班
        - 1班: SG1, SG2
        - 2班: SG2, SG3  (边界子组可共享)
        - 3班: SG4, SG5
        - 4班: SG5, SG6
        """
        
    def _save_results(self, session_id, results, ...) -> None:
        """保存排课结果到数据库"""
        # 对每条课程结果，确定其所属的行政班
        # 保存ScheduleResult记录
```

**虚拟子组 → 行政班映射算法**：

当虚拟子组数不能整除行政班数时，采用按比例分配策略：

```
假设：4个行政班，生成了6个虚拟子组

每班覆盖范围 = 6 / 4 = 1.5 个虚拟子组

- 1班: 覆盖范围 [0, 1.5)   → 包含 SG1, SG2
- 2班: 覆盖范围 [1.5, 3)   → 包含 SG2, SG3  (SG2被共享)
- 3班: 覆盖范围 [3, 4.5)   → 包含 SG4, SG5
- 4班: 覆盖范围 [4.5, 6)   → 包含 SG5, SG6  (SG5被共享)

这样确保每个虚拟子组都被至少一个行政班覆盖
```

---

## 快速启动

### 环境要求

- Python 3.9+
- PostgreSQL 12+
- 4GB+ RAM（建议8GB+，因为遗传算法需要大量内存）

### 1. 安装依赖

```bash
pip install fastapi uvicorn sqlalchemy psycopg2-binary pydantic numpy deap numba openpyxl pandas
```

### 2. 配置数据库

编辑 `web/core/config.py` 或设置环境变量：

```python
# 默认配置
DATABASE_URL = "postgresql://postgres:password@localhost:5432/paike_db"
```

或使用环境变量（Windows PowerShell）：

```powershell
$env:DATABASE_URL = "postgresql://postgres:password@localhost:5432/paike_db"
```

### 3. 初始化数据库表

```bash
cd C:\project\python\danzi\2\paike\paike

# 运行初始化（创建所有表）
python -c "from web.core.database import Base, engine; Base.metadata.create_all(bind=engine)"

# 可选：加载示例数据
python -c "from web.init_mock_data import init_mock_data; init_mock_data()"
```

### 4. 启动Web服务

```bash
# 方式一：开发模式（自动重载）
python -m uvicorn web.main:app --reload --host 0.0.0.0 --port 8000

# 方式二：生产模式
uvicorn web.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### 5. 访问系统

- **前端界面**：http://localhost:8000
- **API 文档 (Swagger)**：http://localhost:8000/docs
- **API 文档 (ReDoc)**：http://localhost:8000/redoc

---

## 前端功能

### 仪表盘 (Dashboard)

- 系统统计信息（班级数、教师数、课程数、机房数）
- 最近的排课记录与状态
- 排课历史总览

### 班级管理

- 添加/编辑/删除专业年级
- 为专业年级添加行政班
- 查看各班级的课程统计

### 教师管理

- 添加/编辑/删除教师
- 设置教师属性（校本部/校外）
- **时间偏好设置**：
  - 按周次(1-5)和节次(1-11)的网格选择
  - 绿色 = 偏好时间（优先排课）
  - 红色 = 不希望时间（尽量避免排课）
  - 支持全天偏好/不希望快速设置

### 机房管理

- 添加/编辑/删除机房
- 查看各机房的使用情况

### 课程管理

- 添加/编辑/删除课程
- 配置课程属性：
  - 学期（上册/下册/全年）
  - 课程类型（纯理论/混合/纯实验）
  - 理论学时、实验学时
  - 教学班数量
  - 双教师配置
  - 分阶段教师配置
  - 合班信息
  - 周次模式

### 课表查看

- 按学期(上册/下册)查看全校课表
- 按专业年级和行政班筛选课表
- 按周次筛选
- 课程信息悬停提示

### 手动课程调整（调课功能）

**功能描述**：支持拖拽课程卡片到新时间槽进行手动调课。

**使用步骤**：

1. **进入课表查看**：选择学期、行政班、周次
2. **拖拽课程**：
   - 将非固定课程卡片拖拽到另一时间槽
   - 课程卡片显示抓取光标 (`cursor-grab`)
   - 拖拽时显示"正在拖拽"提示栏
3. **冲突检测**：
   - 时间槽实时显示可用性：
     - 🟢 绿色 = 无冲突，可放置
     - 🔴 红色 = 有冲突，需确认
     - 🔵 蓝色 = 当前位置
4. **放置**：
   - 放置在绿色槽：直接调课
   - 放置在红色槽：弹出冲突确认对话框，可选择强制调课
   - 松开鼠标：取消调课

**冲突检测包括**：

- 教师冲突：同一教师同一时间是否有其他课
- 学生冲突：同一行政班同一时间是否有其他课
- 机房冲突：实验课机房同一时间是否有其他课
- 合班检测：同一课程的所有教学班都一起移动

**约束条件**：

- 只能拖拽**非固定课程**（固定课如公共课、体育等灰显）
- 理论课和实验课**独立调课**（同一课程的理论课与实验课可分别调整）
- **连续课程**：2节课或3节课自动占用对应时间段

### 课表导出

- 导出为Excel格式 (.xlsx)
- 包含：
  - 按行政班的课表（学生/教务员查看）
  - 教学班总览（教务员管理）
  - 按机房的课表（资源管理）
- 彩色标记：绿色(理论课)、蓝色(实验课)、黄色(固定课)

---

## API 文档

### 基础 URL

```
http://localhost:8000/api/v1
```

### 班级管理 `/classes`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/cohorts` | 获取所有专业年级 |
| POST | `/cohorts` | 创建专业年级 |
| PUT | `/cohorts/{id}` | 更新专业年级 |
| DELETE | `/cohorts/{id}` | 删除专业年级 |
| GET | `/admin-classes` | 获取所有行政班 |
| POST | `/admin-classes` | 创建行政班 |
| PUT | `/admin-classes/{id}` | 更新行政班 |
| DELETE | `/admin-classes/{id}` | 删除行政班 |

**示例**：

```bash
# 创建专业年级
curl -X POST "http://localhost:8000/api/v1/classes/cohorts" \
  -H "Content-Type: application/json" \
  -d '{
    "major": "大数据科学与技术",
    "grade": 2
  }'

# 创建行政班
curl -X POST "http://localhost:8000/api/v1/classes/admin-classes" \
  -H "Content-Type: application/json" \
  -d '{
    "cohort_id": 1,
    "class_index": 1,
    "student_count": 40
  }'
```

### 教师管理 `/teachers`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 获取所有教师 |
| POST | `/` | 创建教师 |
| PUT | `/{id}` | 更新教师 |
| DELETE | `/{id}` | 删除教师 |
| GET | `/{id}/preferences` | 获取教师时间偏好 |
| POST | `/{id}/preferences` | 设置教师时间偏好 |

**示例**：

```bash
# 创建教师
curl -X POST "http://localhost:8000/api/v1/teachers/" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "张三",
    "is_campus_teacher": false
  }'

# 设置时间偏好
curl -X POST "http://localhost:8000/api/v1/teachers/1/preferences" \
  -H "Content-Type: application/json" \
  -d '{
    "preferred_slots": [[1,1], [1,2], [2,1]],
    "undesired_slots": [[4,9], [5,10]]
  }'
```

### 机房管理 `/rooms`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 获取所有机房 |
| POST | `/` | 创建机房 |
| PUT | `/{id}` | 更新机房 |
| DELETE | `/{id}` | 删除机房 |

### 课程管理 `/courses`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 获取所有课程 (?semester=first) |
| POST | `/` | 创建课程 |
| PUT | `/{id}` | 更新课程 |
| DELETE | `/{id}` | 删除课程 |
| POST | `/unified-group` | 创建合班课程组 |

**示例**：

```bash
# 创建课程（混合类型）
curl -X POST "http://localhost:8000/api/v1/courses/" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "数据结构",
    "cohort_id": 1,
    "teacher_id": 1,
    "semester": "first",
    "course_type": "mixed",
    "theory_hours": 48,
    "lab_hours": 16,
    "teaching_class_count": 2
  }'

# 创建合班课程组
curl -X POST "http://localhost:8000/api/v1/courses/unified-group" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Python编程",
    "cohort_ids": [1, 2],
    "teacher_id": 3,
    "course_type": "theory_only",
    "teaching_class_count": 3,
    "weeks": "1-16",
    "hours": 32
  }'
```

### 排课管理 `/schedule`

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/start` | 开始排课 |
| GET | `/sessions` | 获取所有排课会话 |
| GET | `/sessions/latest` | 获取最新排课会话 |
| GET | `/sessions/{id}` | 获取排课会话详情 |
| GET | `/results` | 获取排课结果列表 |
| GET | `/results/{id}` | 获取单条排课结果 |
| GET | `/results/{result_id}/available-slots` | **获取可调整时间槽** |
| POST | `/results/{result_id}/adjust` | **执行调课** |
| DELETE | `/sessions/{id}` | 删除排课会话 |
| GET | `/export/{session_id}` | 导出Excel课表 |

**排课请求**：

```bash
# 排课（全部专业年级）
curl -X POST "http://localhost:8000/api/v1/schedule/start" \
  -H "Content-Type: application/json" \
  -d '{
    "semester": "first"
  }'

# 排课（指定专业年级）
curl -X POST "http://localhost:8000/api/v1/schedule/start" \
  -H "Content-Type: application/json" \
  -d '{
    "cohort_ids": [1, 2],
    "semester": "first"
  }'
```

**调课 API**：

```bash
# 获取可调整的时间槽
curl -X GET "http://localhost:8000/api/v1/schedule/results/191226/available-slots"

# 响应示例
{
  "teaching_class_id": "TC_C35_1",
  "course_name": "数学建模",
  "duration": 2,
  "weeks": [1, 2, 3, ...],
  "available_slots": [
    {
      "day": 1,
      "day_name": "周一",
      "period": 1,
      "period_range": "第1-2节",
      "has_conflict": false,
      "is_current": false,
      "conflicts": []
    },
    {
      "day": 1,
      "day_name": "周一",
      "period": 3,
      "period_range": "第3-4节",
      "has_conflict": true,
      "is_current": false,
      "conflicts": [
        {
          "type": "student",
          "week": 1,
          "day": 1,
          "period": 3,
          "desc": "第1周 学生已有课: 数据结构"
        }
      ]
    }
  ]
}

# 执行调课（无冲突）
curl -X POST "http://localhost:8000/api/v1/schedule/results/191226/adjust" \
  -H "Content-Type: application/json" \
  -d '{
    "new_day": 2,
    "new_period": 3,
    "force": false
  }'

# 执行调课（有冲突，强制调课）
curl -X POST "http://localhost:8000/api/v1/schedule/results/191226/adjust" \
  -H "Content-Type: application/json" \
  -d '{
    "new_day": 3,
    "new_period": 5,
    "force": true
  }'
```

---

## 数据库设计

### 核心表

#### cohorts（专业年级）

```sql
CREATE TABLE cohorts (
    id SERIAL PRIMARY KEY,
    major VARCHAR(100) NOT NULL,          -- 专业名称
    grade INT NOT NULL,                   -- 年级
    is_graduation BOOLEAN DEFAULT false,  -- 是否毕业年级
    created_at TIMESTAMP DEFAULT now()
);
```

#### admin_classes（行政班）

```sql
CREATE TABLE admin_classes (
    id SERIAL PRIMARY KEY,
    cohort_id INT NOT NULL REFERENCES cohorts(id),
    class_index INT NOT NULL,             -- 班级序号
    student_count INT,                    -- 学生人数
    is_graduation_class BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT now()
);
```

#### teachers（教师）

```sql
CREATE TABLE teachers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    is_campus_teacher BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT now()
);
```

#### teacher_preferences（教师时间偏好）

```sql
CREATE TABLE teacher_preferences (
    id SERIAL PRIMARY KEY,
    teacher_id INT NOT NULL REFERENCES teachers(id),
    preferred_slots JSONB,    -- [[day, period], ...] 偏好时间
    undesired_slots JSONB,    -- [[day, period], ...] 不希望时间
    created_at TIMESTAMP DEFAULT now()
);
```

#### rooms（机房）

```sql
CREATE TABLE rooms (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    capacity INT,
    created_at TIMESTAMP DEFAULT now()
);
```

#### courses（课程）

```sql
CREATE TABLE courses (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    cohort_id INT REFERENCES cohorts(id),
    teacher_id INT NOT NULL REFERENCES teachers(id),
    semester VARCHAR(10),                 -- 'first', 'second', 'both'
    course_type VARCHAR(20),              -- 'theory_only', 'mixed', 'lab_only'
    theory_hours INT,
    lab_hours INT,
    teaching_class_count INT DEFAULT 1,
    dual_teacher_enabled BOOLEAN DEFAULT false,
    second_teacher_id INT REFERENCES teachers(id),
    teacher_split_week INT,
    preferred_pattern VARCHAR(50),        -- 周次模式
    created_at TIMESTAMP DEFAULT now()
);
```

#### schedule_sessions（排课会话）

```sql
CREATE TABLE schedule_sessions (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(32) UNIQUE NOT NULL,
    semester VARCHAR(10) NOT NULL,
    status VARCHAR(20),                   -- 'running', 'completed', 'completed_with_warnings', 'failed'
    fitness_score FLOAT,                  -- 惩罚分数（越低越好）
    penalty_details JSONB,                -- 详细的惩罚信息
    message TEXT,
    created_at TIMESTAMP DEFAULT now(),
    completed_at TIMESTAMP
);
```

#### schedule_results（排课结果）

```sql
CREATE TABLE schedule_results (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(32) NOT NULL REFERENCES schedule_sessions(session_id),
    teaching_class_id VARCHAR(100),
    course_name VARCHAR(200),
    teacher_name VARCHAR(100),
    week INT,                  -- 第几周
    day INT,                   -- 周几 (1-5)
    period INT,                -- 第几节 (1-11)
    duration INT DEFAULT 2,    -- 持续节数
    room_name VARCHAR(100),
    is_lab BOOLEAN DEFAULT false,
    is_combined BOOLEAN DEFAULT false,
    is_fixed BOOLEAN DEFAULT false,
    cohort_id INT,
    admin_class_id INT,
    created_at TIMESTAMP DEFAULT now()
);
```

---

## 配置说明

### 学期配置

```json
{
  "semester": "first",   // 上册（第1-16周）
  "semester": "second",  // 下册（第1-16周）
  "semester": "both"     // 全年（两学期都排）
}
```

### 课程类型

```json
{
  "course_type": "theory_only",  // 纯理论课
  "course_type": "mixed",        // 混合（理论+实验）
  "course_type": "lab_only"      // 纯实验课
}
```

### 双教师配置

同一课程分两个阶段由不同教师授课：

```json
{
  "dual_teacher_enabled": true,
  "teacher_id": 1,              // 主教师 ID
  "second_teacher_id": 2,       // 第二教师 ID
  "teacher_split_week": 8       // 切换周次（第8周之后换教师）
}
```

### 周次模式

| 模式 | 说明 | 周次 |
|------|------|------|
| `single_week` | 单周 | 1,3,5,7,9,11,13,15 |
| `double_week` | 双周 | 2,4,6,8,10,12,14,16 |
| `weekly` | 每周 | 1-16 |
| `weeks_1_to_8` | 前8周 | 1-8 |
| `weeks_9_to_16` | 后8周 | 9-16 |
| `weeks_5_to_16` | 毕业年级 | 5-16 |
| `weeks_5_to_17` | 毕业年级+复习 | 5-17 |

### 时间定义

| 参数 | 值 | 说明 |
|------|---|------|
| 周 | 1-17 | 第1-16周 + 第17周(考试周) |
| 天 | 1-5 | 周一至周五 |
| 节 | 1-11 | 第1-11节课 |
| 课程时长 | 2 或 3 | 2节或3节连排 |

---

## 常见问题

### Q: 排课失败，提示惩罚分数很高

**A**: 可能原因和解决方案：

1. **教师课时过多**
   - 检查某个教师的总课时是否过高（>30小时）
   - 尝试分配更多教师或减少班级数量

2. **机房不足**
   - 增加机房数量
   - 合理安排实验课在不同周次

3. **时间偏好冲突**
   - 放宽校本部教师的时间偏好设置
   - 检查是否有过多限制条件

4. **课程配置问题**
   - 确保 `teaching_class_count` 设置合理
   - 避免创建过多的虚拟子组

### Q: 校本部教师的课没有排好

**A**: 检查以下几点：

1. 教师的 `is_campus_teacher` 是否设为 `true`
2. 课程是否正确关联了校本部教师
3. 是否存在过多的硬约束条件导致无解
4. 机房是否充足（如果是实验课）

### Q: 虚拟子组和行政班对应关系不对

**A**: 虚拟子组数量由各课程的 `teaching_class_count` 的最小公倍数决定：

```
例：课程A有2个班，课程B有3个班，课程C有4个班
虚拟子组数 = LCM(2, 3, 4) = 12 个

如果行政班数是4，则每班分配3个虚拟子组
```

确保课程配置与行政班数量相匹配。

### Q: 拖拽调课时总是有冲突

**A**: 检查以下几点：

1. **当前课程的位置** - 某些时间槽可能被多个班级占用
2. **合班课程** - 合班课程会占用更多的时间槽组合
3. **理论课vs实验课** - 同一课程的理论课和实验课是否堆积在一起
4. **教师时间** - 该教师在其他班级是否有课

尝试先调整冲突较少的课程。

### Q: 导出的Excel格式不对

**A**: 检查：

1. 确保安装了 `openpyxl` 库
2. 文件名中文显示问题 - 这是正常的，可在导出后重命名
3. 如果导出失败，查看服务器日志

---

## 性能优化建议

### 对于大规模排课（100+课程）

1. **增加内存**：建议8GB+
2. **调整算法参数**：
   ```python
   # 在 deap_scheduler.py 中调整
   POP_SIZE = 500    # 从1000减少到500
   MAX_GEN = 200     # 从300减少到200
   ```

3. **使用多进程**：
   ```python
   # 自动使用所有可用CPU核心
   cpu_count = multiprocessing.cpu_count()
   ```

4. **加快排课**：
   - 先排校本部教师课程
   - 按专业年级分批排课，而不是全部一起排

---

## 技术栈

| 组件 | 技术 | 版本 |
|------|------|------|
| 后端框架 | FastAPI | 0.95+ |
| 数据库 | PostgreSQL | 12+ |
| ORM | SQLAlchemy | 2.0+ |
| 遗传算法 | DEAP | 1.3+ |
| 数值计算 | NumPy | 1.23+ |
| JIT编译 | Numba | 0.56+ |
| Excel导出 | openpyxl | 3.9+ |
| 前端框架 | Vue 3 | 3.3+ (CDN) |
| 样式框架 | Tailwind CSS | 3.3+ (CDN) |

---

## License

MIT License

---

## 联系方式

如有问题或建议，请提交Issue或联系开发团队。
