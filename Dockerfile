FROM python:3.15.2-slim@sha256:65a65fc7b30b06cb6df4930fd4650697cb23f4c2698ab81fc87e4b031bc36928

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Unprivileged runtime user
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app
USER 10001

EXPOSE 8000

# --proxy-headers: take the client IP from X-Forwarded-For so the login throttle
# keys on real addresses — but only from proxies listed in FORWARDED_ALLOW_IPS
# (uvicorn reads that env var; default 127.0.0.1). Set it to the ingress
# controller's pod CIDR in the deployment. Never "*": any client could then
# forge its IP and dodge the per-IP throttle.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
