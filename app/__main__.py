import os

import uvicorn
from dotenv import load_dotenv

from porovnu_logging import configure_logging


def main() -> None:
    load_dotenv()
    configure_logging("web")
    uvicorn.run(
        "app.main:app",
        host=os.environ.get("UVICORN_HOST", "127.0.0.1"),
        port=int(os.environ.get("UVICORN_PORT", "8000")),
        log_config=None,
        access_log=False,
    )


if __name__ == "__main__":
    main()
