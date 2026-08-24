# The sandbox image in which the agent's generated Python runs.
# Built once: `docker build -t ai-analyst-sandbox:latest ./sandbox-image`
# It is run with --network none and strict resource limits (see backend/app/sandbox).
FROM python:3.12-slim

RUN pip install --no-cache-dir \
    pandas==2.2.3 \
    numpy==2.1.3 \
    matplotlib==3.9.2 \
    scikit-learn==1.5.2 \
    scipy==1.14.1 \
    duckdb==1.1.3

# Non-root user; the runtime also drops caps and disables networking.
RUN useradd --create-home --uid 10001 sandbox
USER sandbox
WORKDIR /work

# Code + data are mounted/copied in at run time; there is no default entrypoint on purpose.
