FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=3978
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --uid 10001 --create-home agent
COPY app.py teams_app.py graph_chat.py a365_bootstrap.py ./
USER 10001
EXPOSE 3978
CMD ["python", "teams_app.py"]