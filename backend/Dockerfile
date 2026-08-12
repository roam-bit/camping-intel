FROM python:3.12-slim

WORKDIR /app

# 刻意不装 gcc / libpq-dev：
# libpq-dev 是 psycopg2 编译才需要的，本项目用的是 asyncpg（纯 asyncio 驱动，官方发预编译包）；
# requirements 里其余包也都有 wheel，无需现场编译。
# 去掉这一层的实际收益：构建不再依赖 deb.debian.org —— 那个源在国内经常 502，
# 一卡就是「apt-get exit code 100」，对拿到项目的新人是最劝退的一种失败。
# 依赖源可切换：默认走清华镜像，因为这个项目的使用者主要在国内，
# 官方 pypi 在国内经常慢到超时——而「装依赖卡住」是新人最容易放弃的一步。
# 海外或公司网络下想用官方源：
#   docker compose build --build-arg PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

COPY requirements.txt .
RUN pip install --no-cache-dir --index-url "$PIP_INDEX_URL" \
      --trusted-host pypi.tuna.tsinghua.edu.cn \
      --retries 5 --timeout 60 \
      -r requirements.txt

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
