from fastapi import APIRouter, UploadFile, File, HTTPException
import os
import shutil
import glob
from app.config.settings import settings

router = APIRouter()

REPORT_PATH = str(settings.REPORT_PATH)

@router.post("/upload_signal")
async def upload_signal(file: UploadFile = File(...)):
    """
    接收来自 Windows 端生成的 JSON 信号文件
    """
    # 验证文件类型是否为 JSON 或 PDF
    if not file.filename.endswith((".json", ".pdf")):
        raise HTTPException(status_code=400, detail="Only JSON or PDF files are allowed")
    
    # 确保目录存在
    os.makedirs(REPORT_PATH, exist_ok=True)
    
    file_location = os.path.join(REPORT_PATH, file.filename)
    
    try:
        with open(file_location, "wb+") as file_object:
            shutil.copyfileobj(file.file, file_object)
        return {"info": f"File '{file.filename}' saved at '{file_location}'"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
