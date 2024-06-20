import os
import uvicorn
import asyncio
from main import create_app

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    app = loop.run_until_complete(create_app())
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", default=8443)))
