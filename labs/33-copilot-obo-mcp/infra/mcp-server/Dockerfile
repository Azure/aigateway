# The demo MCP server. An ACR Tasks run builds it from this folder in GitHub, so you don't need Docker.
# The base image comes from Microsoft Container Registry, which avoids Docker Hub pull limits.
FROM mcr.microsoft.com/azurelinux/base/python:3.12

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOME=/tmp \
    PORT=8000

WORKDIR /app
COPY requirements.txt .
RUN python3 -m pip install --break-system-packages -r requirements.txt
COPY server.py .

USER 10001
EXPOSE 8000
CMD ["python3", "server.py"]
