from fastapi import APIRouter
from app.schemas.capabilities import CapabilitiesResponse
from app.core.environment import evaluate_system_capabilities

router = APIRouter(prefix="/api", tags=["System"])


@router.get("/capabilities", response_model=CapabilitiesResponse)
def get_capabilities():
    return evaluate_system_capabilities()
