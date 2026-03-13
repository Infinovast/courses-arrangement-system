"""
排课系统 Web API 主入口
"""
import sys
import os

# 添加父目录到路径以导入原有排课算法模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from .core.config import settings
from .core.database import init_db, engine, Base
from .api import class_api, teacher_api, room_api, course_api, schedule_api

# 创建FastAPI应用
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="""
## 排课系统 API

### 功能模块：
- **班级管理**: 专业年级和行政班的增删查
- **教师管理**: 教师信息和时间偏好管理
- **机房管理**: 机房信息管理
- **课程管理**: 课程信息、教学班配置
- **排课管理**: 自动排课、手动调整、课表导出

### 使用说明：
1. 先配置好 PostgreSQL 数据库连接
2. 启动服务后访问 `/docs` 查看完整 API 文档
3. 按顺序添加：专业年级 → 行政班 → 教师 → 机房 → 课程 → 开始排课
""",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 启动事件：初始化数据库
@app.on_event("startup")
def startup_event():
    """启动时初始化数据库表"""
    # 导入所有模型确保它们被注册
    from .dbmodels import db_models
    Base.metadata.create_all(bind=engine)
    print("数据库表初始化完成")


# 注册路由
app.include_router(class_api.router, prefix=settings.API_PREFIX)
app.include_router(teacher_api.router, prefix=settings.API_PREFIX)
app.include_router(room_api.router, prefix=settings.API_PREFIX)
app.include_router(course_api.router, prefix=settings.API_PREFIX)
app.include_router(schedule_api.router, prefix=settings.API_PREFIX)


# 前端页面
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "frontend")

# 挂载静态文件目录（用于 config.js 等静态资源）
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

@app.get("/", tags=["前端"])
def serve_frontend():
    """返回前端页面"""
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


@app.get("/app", tags=["前端"])
def serve_frontend_app():
    """返回前端页面（兼容路由）"""
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


# 健康检查
@app.get("/health", tags=["系统"])
def health_check():
    """健康检查"""
    return {"status": "healthy"}


# API 信息
@app.get("/api/info", tags=["系统"])
def api_info():
    """API 信息"""
    return {
        "name": settings.PROJECT_NAME,
        "version": "1.0.0",
        "docs": "/docs",
        "api_prefix": settings.API_PREFIX
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "web.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
