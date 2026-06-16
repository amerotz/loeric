import os
import pathlib
import sys

import fastapi as fapi
import uvicorn


def main():
    PORT = int(os.getenv("LOERIC_WEBAPP_PORT", 8080))

    if getattr(sys, "frozen", False):
        print("Running compiled binary.")
        BASE_DIR = pathlib.Path(sys._MEIPASS)
    else:
        print("Running from cli.")
        BASE_DIR = pathlib.Path(__file__).resolve().parents[3]

    STATIC_ROOT = pathlib.Path(
        os.getenv("LOERIC_WEBAPP_DIR", BASE_DIR / "static")
    ).resolve()

    FRONTEND_ROOT = STATIC_ROOT / "site"

    app = fapi.FastAPI()

    app.add_middleware(
        fapi.middleware.cors.CORSMiddleware,
        allow_origins=["*"],  # or restrict to your frontend
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.mount(
        "/",
        fapi.staticfiles.StaticFiles(directory=str(FRONTEND_ROOT), html=True),
        name="static",
    )

    uvicorn.run(app, host="127.0.0.1", port=PORT)


if __name__ == "__main__":
    main()
