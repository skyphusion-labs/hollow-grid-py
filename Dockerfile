# syntax=docker/dockerfile:1
#
# Verdigris Spool -- Hollow Grid world server (Python port). Multi-stage: install the
# package on python:3.12-slim, ship a minimal runtime image. Character persistence
# lives on a mounted /data volume.

# --- build ---
FROM python:3.14-slim AS build
WORKDIR /src
COPY pyproject.toml README.md LICENSE ./
COPY hollow_grid hollow_grid
RUN pip install --no-cache-dir .

# --- run ---
FROM python:3.14-slim AS run
WORKDIR /app
COPY --from=build /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=build /usr/local/bin/hollow-grid-world /usr/local/bin/hollow-grid-world
COPY hollow_grid hollow_grid
VOLUME ["/data"]
EXPOSE 8791
ENTRYPOINT ["python", "-m", "hollow_grid"]
CMD ["--host", "0.0.0.0", "--port", "8791", "--data", "/data"]
