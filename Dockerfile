FROM python:3.12-slim
WORKDIR /app
COPY common /app/common
COPY services /app/services
COPY web /app/web
ENV PYTHONPATH=/app PYTHONUNBUFFERED=1 DATA_DIR=/data
ARG SERVICE
ENV SERVICE=${SERVICE}
CMD ["sh", "-c", "python -m services.${SERVICE}.app"]
