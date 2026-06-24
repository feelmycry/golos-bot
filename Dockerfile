FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Chromium browser for Playwright (enables news parsing from alfabank.ru)
RUN playwright install chromium --with-deps

COPY . .

CMD ["python", "bot.py"]
