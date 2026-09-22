# MarketLens — Streamlit Deployment Guide

This guide provides step-by-step instructions for deploying the **MarketLens** E-Commerce Analytics Dashboard on **Streamlit Community Cloud**, running locally, or hosting on cloud container platforms (Hugging Face Spaces, Render, Docker).

---

## 🚀 Option 1: Deploy on Streamlit Community Cloud (Recommended & Free)

Streamlit Community Cloud is the fastest and easiest way to host **MarketLens** directly from your GitHub repository for free.

### Step 1: Push Code to GitHub
Ensure your repository is pushed to GitHub:
```bash
git add .
git commit -m "Add Streamlit root deployment entry point and configuration"
git push origin main
```

### Step 2: Connect to Streamlit Community Cloud
1. Go to [share.streamlit.io](https://share.streamlit.io/) and log in with your **GitHub** account.
2. Click **"Create app"** (or **"New app"**).
3. Select **"I already have an app"**.

### Step 3: Configure Deployment Parameters
Fill in the deployment form with the following details:
- **Repository:** `Pranev007/MarketLens` (or your GitHub repo path)
- **Branch:** `main` (or master)
- **Main file path:** `app.py`
- **App URL:** (Optional) Customize your custom sub-domain name (e.g. `marketlens.streamlit.app`)

### Step 4: Environment Variables / Secrets (Optional)
By default, **MarketLens** uses the included pre-processed **Parquet files** in `data/processed/` for maximum speed and zero database dependency.

If you want to connect to a live PostgreSQL database instead:
1. In Streamlit Cloud, click **"Advanced settings..."** before deploying (or go to App Settings > Secrets).
2. Add your secrets in TOML format:
   ```toml
   MARKETLENS_SOURCE = "postgres"
   POSTGRES_HOST = "your-db-host.supabase.co"
   POSTGRES_PORT = "5432"
   POSTGRES_DB = "postgres"
   POSTGRES_USER = "postgres"
   POSTGRES_PASSWORD = "your-password"
   ```
3. Click **"Save"**.

### Step 5: Deploy!
Click **"Deploy!"**. Streamlit Cloud will automatically install `requirements.txt` and launch your dashboard at `https://<your-app-name>.streamlit.app`.

---

## 💻 Option 2: Run Locally

### 1. Prerequisites
- Python 3.10, 3.11, or 3.12 installed.

### 2. Environment Setup
```bash
# Clone the repository
git clone https://github.com/Pranev007/MarketLens.git
cd MarketLens

# Create and activate virtual environment
python -m venv venv

# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Launch the Dashboard
Run either of the following commands from the project root:
```bash
streamlit run app.py
```
*Alternatively:*
```bash
streamlit run dashboard/app.py
```

The app will open automatically in your browser at `http://localhost:8501`.

---

## 🐳 Option 3: Docker & Cloud Container Deployment

If deploying to **Render**, **Railway**, **Hugging Face Spaces**, or AWS/GCP, you can use Docker.

### Dockerfile
Create a `Dockerfile` in the project root:
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Expose Streamlit port
EXPOSE 8501

ENV PYTHONUNBUFFERED=1
ENV PORT=8501

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

### Build & Run Container locally
```bash
docker build -t marketlens-dashboard .
docker run -p 8501:8501 marketlens-dashboard
```

---

## ⚡ Speed Optimization & Build Time Troubleshooting

If your deployment on Streamlit Cloud is taking several minutes, here are the primary reasons and solutions:

1. **Parquet Data Files Not Pushed to GitHub**:
   - The `.parquet` files in `data/processed/` must be committed to your repository so Streamlit Cloud can load them instantly without running pipeline data processing on startup.
   - Run: `git add -f data/processed/*.parquet` and commit them.

2. **Dependency Wheel Compilation**:
   - Unpin exact versions (e.g. use `pandas>=2.0.0` instead of `pandas==2.2.3`) so `pip` installs pre-compiled binary wheels on Streamlit Cloud's Linux base image instantly instead of compiling from source.

3. **First-Time Cold Start**:
   - The initial deployment builds a container and caches dependencies (~2–4 minutes). Subsequent updates re-use cached layers and deploy in <20 seconds.

---

## 🛠️ Verification & Troubleshooting

| Issue | Cause | Resolution |
| :--- | :--- | :--- |
| `ModuleNotFoundError: No module named 'marketlens'` | Python path not resolving root | Run via `app.py` or execute `pip install -e .` locally. |
| `FileNotFoundError: Missing processed files` | Parquet files excluded in `.gitignore` | Ensure `data/processed/*.parquet` files are committed to git or run `python -m marketlens.pipeline` to regenerate them. |
| `Database connection failed` | Postgres host unreachable | Set `MARKETLENS_SOURCE=parquet` in secrets or `.env` to fallback to local Parquet datasets. |
