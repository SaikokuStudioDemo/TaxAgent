#!/bin/bash
# start-dev.sh — Claude Code セッション開始時にフロント・バックを自動起動

# バックエンド（8000番が未使用の場合のみ起動）
if ! lsof -ti:8000 >/dev/null 2>&1; then
  cd /Users/yohei/Developer/TaxAgent/backend
  source venv/bin/activate
  uvicorn app.main:app --reload --port 8000 >> uvicorn.log 2>&1 &
  echo "Backend started (PID $!)"
else
  echo "Backend already running on :8000"
fi

# フロントエンド（5173番が未使用の場合のみ起動）
if ! lsof -ti:5173 >/dev/null 2>&1; then
  cd /Users/yohei/Developer/TaxAgent/frontend
  npm run dev >> frontend.log 2>&1 &
  echo "Frontend started (PID $!)"
else
  echo "Frontend already running on :5173"
fi
