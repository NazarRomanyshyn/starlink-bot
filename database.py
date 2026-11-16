from datetime import datetime

import aiosqlite

DB_NAME = "starlink.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                starlink TEXT NOT NULL,
                volume REAL NOT NULL,
                download_date TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()

async def add_download(starlink: str, volume: float, download_date: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO downloads (starlink, volume, download_date) VALUES (?, ?, ?)",
            (starlink, volume, download_date)
        )
        await db.commit()

async def get_today_count() -> int:
    today = datetime.now().strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_NAME) as db, db.execute(
        "SELECT COUNT(*) FROM downloads WHERE date(created_at) = ?", (today,)
    ) as cursor:
        row = await cursor.fetchone()
        return row[0] if row else 0

async def get_monthly_report(fixed_list: list[str] | None = None):
    now = datetime.now()
    year_month = now.strftime("%Y-%m")

    async with aiosqlite.connect(DB_NAME) as db, db.execute("""
            SELECT starlink, volume, download_date
            FROM downloads
            WHERE strftime('%Y-%m', download_date) = ?
            ORDER BY download_date
        """, (year_month,)) as cursor:
        rows = await cursor.fetchall()

    report = {}

    if fixed_list:
        for s in fixed_list:
            report[s] = {"total": 0.0, "dates": []}

    for starlink, volume, date in rows:
        if starlink not in report:
            report[starlink] = {"total": 0.0, "dates": []}
        report[starlink]["total"] += volume
        if date not in report[starlink]["dates"]:
            report[starlink]["dates"].append(date)

    return report

async def get_recent_downloads(limit: int = 10):
    """Повертає останні записи з бази даних"""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT id, starlink, volume, download_date FROM downloads ORDER BY id DESC LIMIT ?",
            (limit,)
        )
        rows = await cursor.fetchall()
        return rows

async def delete_download_by_id(record_id: int) -> bool:
    """Видаляє запис за його ID"""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("DELETE FROM downloads WHERE id = ?", (record_id,))
        await db.commit()
        return cursor.rowcount > 0