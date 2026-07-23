import subprocess
import sys
from setuptools import setup, find_packages

# Post-install hook: download Playwright Chromium during the Docker build stage
print("--> Running setup.py build hook: Baking Playwright Chromium into the container image...")
try:
    # We run the playwright install command. During docker build, /root is fully writable,
    # so this downloads the browser directly into the image layers.
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
    print("--> Playwright Chromium successfully baked into the container image.")
except Exception as e:
    print(f"--> Warning: Playwright install failed during build phase: {e}. Falling back to runtime download.", file=sys.stderr)

setup(
    name="ecommerce-mcp",
    version="1.0.0",
    description="E-Commerce Product Recommendation MCP Server with pre-baked Playwright Chromium",
    packages=find_packages(),
    install_requires=[
        "fastmcp",
        "playwright",
        "pydantic>=2.0",
        "pydantic-settings",
        "structlog",
        "tenacity",
        "aiocache",
        "uvicorn",
        "python-dotenv"
    ]
)
