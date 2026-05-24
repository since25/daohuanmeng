import logging
import os

import uvicorn

from backend.api import create_app


app = create_app()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    uvicorn.run(
        app,
        host=os.environ.get("DAOYUFAN_HOST", "127.0.0.1"),
        port=int(os.environ.get("DAOYUFAN_PORT", "8765")),
    )
