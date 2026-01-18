# --- Stage 1: Build Frontend ---
FROM node:24-alpine AS frontend-builder

WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm install

# Copy source code and build
COPY frontend/ .
# This creates the 'dist' folder with index.html and assets
RUN npm run build 

# --- Stage 2: Setup Backend & Serve ---
FROM python:3.11-slim

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy Backend Code
COPY main.py .

# Copy Built Frontend Assets from Stage 1
# We rename 'dist' to 'static' to match the folder name in main.py
COPY --from=frontend-builder /frontend/dist /app/static

# Expose the single port
EXPOSE 8000

# Run the server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]