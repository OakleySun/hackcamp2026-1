"""Start Quad's API, SSR website and Databricks exporter in one Maritime box."""

import os
import signal
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen


def stop(_signum, _frame):
    raise SystemExit(0)


def main():
    signal.signal(signal.SIGTERM, stop)
    python = sys.executable
    api = subprocess.Popen([python, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"])
    services = [api]
    try:
        for _ in range(100):
            if api.poll() is not None:
                raise RuntimeError("FastAPI exited during startup")
            try:
                with urlopen("http://127.0.0.1:8000/health", timeout=1):
                    break
            except URLError:
                time.sleep(0.1)
        else:
            raise RuntimeError("FastAPI did not become healthy")

        if all(os.environ.get(key) for key in ("DATABRICKS_HOST", "DATABRICKS_WAREHOUSE_ID", "DATABRICKS_TOKEN")):
            services.append(subprocess.Popen([python, "-m", "scripts.dbx_worker"]))
        web_env = {**os.environ, "NITRO_HOST": "0.0.0.0", "NITRO_PORT": os.environ.get("PORT", "8080")}
        services.append(subprocess.Popen(["node", "web/server/index.mjs"], env=web_env))

        while all(service.poll() is None for service in services):
            time.sleep(1)
        raise RuntimeError("A Quad service exited")
    finally:
        for service in services:
            if service.poll() is None:
                service.terminate()
        for service in services:
            try:
                service.wait(timeout=5)
            except subprocess.TimeoutExpired:
                service.kill()
                service.wait()


if __name__ == "__main__":
    main()
