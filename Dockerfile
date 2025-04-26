FROM python:3.9-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Persist data/ for DB + sitemaps
VOLUME ["/app/data"]
ENV PYTHONUNBUFFERED=1

# Starts Flask (with in-process scheduler)
CMD ["python", "app.py"]
