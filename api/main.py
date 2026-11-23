"""Small demo API for the GitOps platform lab.

Endpoints:
  GET  /health         liveness: the process is up (no database needed)
  GET  /ready          readiness: the database answers
  GET  /api/version    app version and environment name
  GET  /api/notes      last 20 notes from MySQL
  POST /api/notes      add a note
"""
import asyncio
import os
from contextlib import asynccontextmanager

import pymysql
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

APP_VERSION = os.getenv("APP_VERSION", "1.0.0")
ENVIRONMENT = os.getenv("ENVIRONMENT", "local")

DB_HOST = os.getenv("DB_HOST", "mysql")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_NAME = os.getenv("DB_NAME", "demo")
DB_USER = os.getenv("DB_USER", "demo")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")


def connect():
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=3,
        autocommit=True,
    )


def init_table():
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "CREATE TABLE IF NOT EXISTS notes ("
                "id INT AUTO_INCREMENT PRIMARY KEY, "
                "text VARCHAR(200) NOT NULL, "
                "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
            )
    finally:
        conn.close()


async def init_db_with_retry():
    # MySQL can take a while to start, so keep trying in the background.
    # The API itself starts right away and /ready reports when the database is up.
    for _ in range(90):
        try:
            await asyncio.to_thread(init_table)
            return
        except Exception:
            await asyncio.sleep(2)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(init_db_with_retry())
    yield
    task.cancel()


app = FastAPI(title="demo-api", lifespan=lifespan)


class NoteIn(BaseModel):
    text: str = Field(min_length=1, max_length=200)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    try:
        conn = connect()
        conn.close()
    except Exception:
        raise HTTPException(status_code=503, detail="database not ready")
    return {"status": "ready"}


@app.get("/api/version")
def version():
    return {"version": APP_VERSION, "environment": ENVIRONMENT}


@app.get("/api/notes")
def list_notes():
    try:
        conn = connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, text, created_at FROM notes ORDER BY id DESC LIMIT 20"
                )
                rows = cur.fetchall()
        finally:
            conn.close()
    except Exception:
        raise HTTPException(status_code=503, detail="database not ready")
    for row in rows:
        row["created_at"] = row["created_at"].isoformat()
    return rows


@app.post("/api/notes", status_code=201)
def add_note(note: NoteIn):
    try:
        conn = connect()
        try:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO notes (text) VALUES (%s)", (note.text,))
        finally:
            conn.close()
    except Exception:
        raise HTTPException(status_code=503, detail="database not ready")
    return {"status": "saved"}
