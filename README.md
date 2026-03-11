# Tax-Agent

Tax-Agent is a powerful accounting and tax management system for corporations and tax firms.

## Project Structure

- **frontend/**: Vue.js + Vite + Tailwind CSS dashboard.
- **backend/**: FastAPI + MongoDB server.
- **InvoiceSample/**: (Excluded from Git) Sample PDFs for AI training.

## Key Features

- AI Chat Advisor (Gemini 3.1 Pro/Flash)
- AI Invoice Extraction & Template Training
- Automated Bank Transaction Matching
- Multi-step Approval Workflows
- Real-time Notifications

## Setup

### Backend
1. `cd backend`
2. `python -m venv venv`
3. `source venv/bin/activate`
4. `pip install -r requirements.txt`
5. Create `.env` and `firebase-admin-key.json`
6. `uvicorn app.main:app --reload`

### Frontend
1. `cd frontend`
2. `npm install`
3. `npm run dev`

## Deployment

Pushed to: https://github.com/SaikokuStudioDemo/TaxAgent
