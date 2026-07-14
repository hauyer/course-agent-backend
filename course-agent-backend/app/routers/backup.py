from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from app.database import get_db
from app.models.user import User
from app.services.auth_service import get_current_user
from app.services.backup_service import MAX_BACKUP_BYTES, export_user_backup, import_user_backup
from app.services.llm_config_service import verify_current_password
from app.services.vector_service import index_material_vectors_background


router = APIRouter()
UPLOAD_ROOT = Path("uploads")


@router.post("/export")
def export_backup(
    current_password: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        verify_current_password(user=current_user, current_password=current_password)
        output = export_user_backup(db, user_id=current_user.id, upload_root=UPLOAD_ROOT)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FileResponse(
        output,
        media_type="application/zip",
        filename="course-study-backup.zip",
        background=BackgroundTask(output.unlink, missing_ok=True),
    )


@router.post("/import")
async def import_backup(
    background_tasks: BackgroundTasks,
    current_password: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        verify_current_password(user=current_user, current_password=current_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    temp = NamedTemporaryFile(prefix="course-study-import-", suffix=".zip", delete=False)
    temp_path = Path(temp.name)
    size = 0
    try:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_BACKUP_BYTES:
                raise HTTPException(status_code=413, detail="备份文件不能超过 512 MB")
            temp.write(chunk)
        temp.close()
        result = import_user_backup(
            db,
            user_id=current_user.id,
            backup_path=temp_path,
            upload_root=UPLOAD_ROOT,
        )
        for material_id in result.pop("vector_material_ids"):
            background_tasks.add_task(
                index_material_vectors_background,
                material_id=material_id,
                user_id=current_user.id,
            )
        return {"message": "数据导入完成，资料向量正在后台重建", **result}
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"数据导入失败：{exc}") from exc
    finally:
        temp.close()
        temp_path.unlink(missing_ok=True)
        await file.close()
