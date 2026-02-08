# InfraMinds Deployment Guide

This guide provides instructions for deploying the **InfraMinds** project to production using common cloud platforms (Vercel and Render).

## 1. Backend Deployment (FastAPI)

We recommend using **Render** or **Fly.io** for simplicity, or **AWS App Runner** for a more native experience.

### Deployment on Render.com
1.  **Connect Repo**: Link your GitHub repository.
2.  **Environment Settings**:
    *   **Runtime**: `Python`
    *   **Build Command**: `pip install -r backend/requirements.txt`
    *   **Start Command**: `gunicorn main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT` (Run from the `backend/` directory)
3.  **Environment Variables**:
    *   `GEMINI_API_KEY`: Your Google Gemini API Key.
    *   `PORT`: `8000` (Render will set this automatically).

---

## 2. Frontend Deployment (Next.js)

The frontend is best suited for **Vercel**.

### Deployment on Vercel
1.  **Connect Repo**: Link your GitHub repository.
2.  **Project Configuration**:
    *   **Framework Preset**: `Next.js`
    *   **Root Directory**: `frontend`
3.  **Environment Variables**:
    *   `NEXT_PUBLIC_API_URL`: The URL of your deployed backend (e.g., `https://inframinds-api.onrender.com`).
4.  **Deploy**: Click deploy.

---

## 3. Environment Variables Overview

| Variable | Location | Description |
| :--- | :--- | :--- |
| `GEMINI_API_KEY` | Backend | Required for architecture generation and reasoning. |
| `NEXT_PUBLIC_API_URL` | Frontend | The endpoint for your FastAPI backend. |

---

## 4. Local Verification Before Pushing
Ensure everything works locally by using the provided script:
```bash
./start_dev.sh
```

## 5. Deployment Checklist
- [ ] Backend is live and returning `{"status": "ok"}` at `/agent/health`.
- [ ] Frontend environment variable `NEXT_PUBLIC_API_URL` is set to the HTTPS backend URL.
- [ ] CORS is configured on the backend to allow your frontend domain (updated in `main.py`).
