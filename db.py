import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path("data/instagram_monitor.db")


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS media_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        collected_at TEXT NOT NULL,
        media_id TEXT NOT NULL,
        media_type TEXT,
        caption TEXT,
        permalink TEXT,
        timestamp TEXT,
        like_count INTEGER DEFAULT 0,
        comments_count INTEGER DEFAULT 0,
        views INTEGER DEFAULT 0,
        saved INTEGER DEFAULT 0,
        shares INTEGER DEFAULT 0
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS account_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        collected_at TEXT NOT NULL,
        followers_count INTEGER DEFAULT 0,
        media_count INTEGER DEFAULT 0
    )
    """)

    conn.commit()
    conn.close()


def insert_media_snapshot(rows):
    conn = get_connection()
    cur = conn.cursor()

    for row in rows:
        cur.execute("""
        INSERT INTO media_snapshots (
            collected_at,
            media_id,
            media_type,
            caption,
            permalink,
            timestamp,
            like_count,
            comments_count,
            views,
            saved,
            shares
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            row.get("collected_at"),
            row.get("media_id"),
            row.get("media_type"),
            row.get("caption"),
            row.get("permalink"),
            row.get("timestamp"),
            row.get("like_count", 0),
            row.get("comments_count", 0),
            row.get("views", 0),
            row.get("saved", 0),
            row.get("shares", 0),
        ))

    conn.commit()
    conn.close()


def insert_account_snapshot(followers_count, media_count):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO account_snapshots (
        collected_at,
        followers_count,
        media_count
    )
    VALUES (?, ?, ?)
    """, (
        datetime.now().isoformat(timespec="seconds"),
        followers_count,
        media_count
    ))

    conn.commit()
    conn.close()