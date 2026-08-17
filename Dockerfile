# Use the official Microsoft Playwright image with all Linux graphics drivers built-in
FROM mcr.microsoft.com/playwright/python:v1.42.0-jammy

# Set the working directory
WORKDIR /app

# Copy the requirements and install them
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy your python code
COPY . .

# Start the bot
CMD gunicorn app:app -b 0.0.0.0:$PORT