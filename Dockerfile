ARG BUILD_FROM
FROM $BUILD_FROM

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY rootfs /

RUN chmod a+x /etc/services.d/budgetbakers_wallet/run
