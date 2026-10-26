FROM python:3.12-slim
WORKDIR /srv
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir . && mkdir -p /data /scenarios
# scenarios/ is mounted at /scenarios by docker-compose (loader resolves parents[3]/scenarios)
ENV DATABASE_URL=sqlite:////data/cybergenesis.db
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
