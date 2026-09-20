# ---- 构建阶段无需额外工具，单阶段即可 ----
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 先装依赖，充分利用镜像层缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 拷贝应用代码与静态资源
COPY app ./app

EXPOSE 8000

# 初始化即启动：FastAPI 直接托管静态页面与 API，无需额外迁移步骤
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
