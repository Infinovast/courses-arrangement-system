# 排课系统 Web API

基于 FastAPI + PostgreSQL 的排课系统 Web 接口。

## 环境要求

- Python 3.10+
- PostgreSQL 12+

## 安装

1. 安装依赖：
```bash
pip install -r requirements.txt
```

2. 创建数据库：
```sql
CREATE DATABASE paike_db;
```

3. 配置环境变量：
```bash
cp .env.example .env
# 编辑 .env 文件，配置数据库连接信息
```

## 启动服务

```bash
# 在 paike 目录下运行
cd C:\project\python\danzi\2\paike\paike

# 启动开发服务器
python -m uvicorn web.main:app --reload --host 0.0.0.0 --port 8000
```

## API 文档

启动服务后访问：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## API 接口概览

### 班级管理 `/api/v1/classes`
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /cohorts | 获取所有专业年级 |
| POST | /cohorts | 添加专业年级 |
| DELETE | /cohorts/{id} | 删除专业年级 |
| GET | /admin-classes | 获取所有行政班 |
| POST | /admin-classes | 添加行政班 |
| DELETE | /admin-classes/{id} | 删除行政班 |

### 教师管理 `/api/v1/teachers`
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | / | 获取所有教师 |
| POST | / | 添加教师 |
| PUT | /{id} | 更新教师 |
| DELETE | /{id} | 删除教师 |
| GET | /{id}/preferences | 获取教师偏好 |
| POST | /{id}/preferences | 添加教师偏好 |

### 机房管理 `/api/v1/rooms`
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | / | 获取所有机房 |
| POST | / | 添加机房 |
| PUT | /{id} | 更新机房 |
| DELETE | /{id} | 删除机房 |

### 课程管理 `/api/v1/courses`
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | / | 获取所有课程 |
| POST | / | 添加课程 |
| PUT | /{id} | 更新课程 |
| DELETE | /{id} | 删除课程 |

### 排课管理 `/api/v1/schedule`
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /start | 开始排课 |
| GET | /sessions | 获取所有排课会话 |
| GET | /sessions/latest | 获取最新排课会话 |
| GET | /results/{session_id} | 获取排课结果 |
| PUT | /results/{id} | 手动调整课程时间 |
| GET | /export/{session_id} | 导出Excel课表 |

## 使用流程

1. **添加基础数据**
   - 添加专业年级（如：大数据-1年级）
   - 为每个专业年级添加行政班
   - 添加教师信息
   - 添加机房信息

2. **配置课程**
   - 添加课程，关联专业年级和教师
   - 设置课程类型、学时、教学班数量

3. **配置偏好（可选）**
   - 设置教师时间偏好
   - 添加固定课程（公共课）
   - 配置子组预分配

4. **执行排课**
   - 调用 `/api/v1/schedule/start` 开始排课
   - 查看排课状态和结果

5. **调整和导出**
   - 手动调整不合适的课程时间
   - 导出最终课表为Excel

## 示例请求

### 添加专业年级
```bash
curl -X POST "http://localhost:8000/api/v1/classes/cohorts" \
  -H "Content-Type: application/json" \
  -d '{"major": "大数据", "grade": 1}'
```

### 添加教师
```bash
curl -X POST "http://localhost:8000/api/v1/teachers" \
  -H "Content-Type: application/json" \
  -d '{"name": "张三", "is_campus_teacher": false}'
```

### 添加课程
```bash
curl -X POST "http://localhost:8000/api/v1/courses" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "数据结构",
    "cohort_id": 1,
    "teacher_id": 1,
    "course_type": "mixed",
    "theory_hours": 48,
    "lab_hours": 16,
    "teaching_class_count": 2
  }'
```

### 开始排课
```bash
curl -X POST "http://localhost:8000/api/v1/schedule/start" \
  -H "Content-Type: application/json" \
  -d '{}'
```

### 导出课表
```bash
curl -X GET "http://localhost:8000/api/v1/schedule/export/{session_id}" \
  --output schedule.xlsx
```

## 数据库表结构

- `cohorts` - 专业年级
- `admin_classes` - 行政班
- `teachers` - 教师
- `teacher_preferences` - 教师偏好
- `rooms` - 机房
- `courses` - 课程
- `fixed_schedules` - 固定课程
- `subgroup_assignments` - 子组预分配
- `schedule_sessions` - 排课会话
- `schedule_results` - 排课结果
