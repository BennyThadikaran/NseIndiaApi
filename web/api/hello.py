from fastapi import APIRouter
from datetime import datetime

router = APIRouter()

@router.get("/hello")
def hello_world(name: str = "Trader"):
    return {
        "success": True,
        "data": {
            "message": f"Hello {name}, welcome to NSE Analytics API 🚀",
            "timestamp": datetime.utcnow().isoformat(),
            "type": "hello_world"
        }
    }
