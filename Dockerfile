FROM python:3.9
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "app.py"]