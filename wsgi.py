import os
import uvicorn
from main import main

if __name__ == "__main__":
    uvicorn.run(main(), host="0.0.0.0", port=int(os.getenv("PORT", default=8443)))
