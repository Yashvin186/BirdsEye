import asyncio
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.core.job_manager import job_manager
from app.schemas.pipeline import JobStatusResponse

router = APIRouter(prefix="/api/jobs", tags=["Jobs"])


@router.get("/{job_id}", response_model=JobStatusResponse)
def get_job_status(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    return job


@router.post("/{job_id}/cancel")
def cancel_job(job_id: str):
    success = job_manager.cancel_job(job_id)
    if not success:
        raise HTTPException(status_code=404, detail="Job not found or already finished")
    return {"cancelled": True, "job_id": job_id}


@router.get("/{job_id}/events")
async def job_events_stream(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_generator():
        while True:
            current = job_manager.get_job(job_id)
            if not current:
                break

            data = current.model_dump_json()
            yield f"data: {data}\n\n"

            if current.status in ("completed", "failed", "cancelled"):
                break

            await asyncio.sleep(1.0)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
