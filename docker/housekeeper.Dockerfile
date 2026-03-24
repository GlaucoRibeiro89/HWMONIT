FROM python:3.12-slim

WORKDIR /app

COPY requirements/housekeeper.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY housekeeper /app/housekeeper

CMD ["python", "-m", "housekeeper.housekeeper_service"]