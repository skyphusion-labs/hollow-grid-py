# syntax=docker/dockerfile:1
#
# Verdigris Spool -- Hollow Grid world server (Python port). Multi-stage: install
# into /install so the COPY paths stay version-agnostic across python:X.Y-slim
# bumps. Character persistence lives on a mounted /data volume.

# --- build ---
FROM python:3.14-slim AS build
WORKDIR /src
COPY pyproject.toml README.md LICENSE ./
COPY hollow_grid hollow_grid
RUN pip install --no-cache-dir --prefix=/install .

# --- run ---
FROM python:3.14-slim AS run
WORKDIR /app
COPY --from=build /install /usr/local
COPY hollow_grid hollow_grid
VOLUME ["/data"]
EXPOSE 8791
ENTRYPOINT ["python", "-m", "hollow_grid"]
CMD ["--host", "0.0.0.0", "--port", "8791", "--data", "/data"]
