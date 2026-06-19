import os
import uvicorn
from app.api.routes import app

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    reload = os.getenv("APP_ENV", "development") == "development"
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=reload,
        log_level="info",
    )
