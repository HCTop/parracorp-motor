FROM python:3.12-slim

# Install Node.js 20 (sin Chromium: Baileys usa WebSocket directo)
# git: necesario para sub-dependencias de Baileys que vienen de github (git+https)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gnupg \
    git \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Node dependencies
COPY package.json ./
RUN npm install --production

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy all source
COPY . .

# Make start script executable
RUN chmod +x start.sh

EXPOSE 5000

CMD bash start.sh
