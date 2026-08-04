FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt monitor_olx.py ./
RUN pip install --no-cache-dir -r requirements.txt
# Runtime env vars are provided by Railway
CMD ["python", "monitor_olx.py"]
