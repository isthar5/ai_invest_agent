from fastapi import FastAPI
from app.api.chat import router as chat_router
from app.api.upload_signal import router as upload_router
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

app = FastAPI(title="AI Invest Agent API")

# 注册路由
app.include_router(chat_router, prefix="/api", tags=["Chat"])
app.include_router(upload_router, prefix="/api", tags=["DataSync"])