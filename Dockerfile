# CardioLens 3D: the self-contained page plus the optional prediction API, one small container.
#   docker build -t cardiolens . && docker run --rm -p 8000:8000 cardiolens     ->  http://localhost:8000
#
# Stage 1 re-proves, at every image build, that the server's maths equals the original scikit-learn pipelines (needs scikit-learn;
# the build fails on a mismatch). Stage 2 is the runtime image and does not ship scikit-learn / pandas.
FROM python:3.12-slim AS verify
WORKDIR /app
COPY requirements-server.txt ./
RUN pip install --no-cache-dir numpy pandas scikit-learn==1.9.1 joblib -r requirements-server.txt
COPY backend ./backend
COPY models ./models
COPY web/web_model.json ./web/
RUN python -c "import backend.server as s; assert s.SELF_CHECK == 'ok', s.SELF_CHECK; print('model parity verified')"

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PORT=8000
WORKDIR /app
COPY requirements-server.txt .
RUN pip install -r requirements-server.txt && useradd --system --uid 10001 --no-create-home cardiolens
COPY backend ./backend
COPY web/web_model.json web/index.offline.html ./web/
USER cardiolens
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=4s --start-period=10s \
  CMD python -c "import os,urllib.request as u; u.urlopen('http://127.0.0.1:%s/api/health' % os.environ.get('PORT', '8000'), timeout=3)"
CMD ["sh", "-c", "exec uvicorn backend.server:app --host 0.0.0.0 --port ${PORT} --no-server-header"]
