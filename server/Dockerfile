# Hugging Face Space (Docker). make_space.sh copies this file to the Space's root.
FROM python:3.13-slim

# Spaces run the container as user 1000
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH \
    SPX_WORK_DIR=/home/user/work SPX_SIZES=51 SPX_PREVIEW_FRAMES=120 SPX_CACHE_CAP_GB=20
WORKDIR /home/user/app

COPY --chown=user requirements.txt server_requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r server_requirements.txt

COPY --chown=user spx ./spx
COPY --chown=user scripts ./scripts
COPY --chown=user server ./server
COPY --chown=user scoring ./scoring

EXPOSE 7860
CMD ["python", "-m", "uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "7860"]
