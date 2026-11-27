"""Робота з базою даних SQLite для обліку завантажень Starlink."""

from datetime import datetime

import aiosqlite

DB_PATH = "starlink_downloads.db"

ALLOWED_KITS = [
    "499", "666", "091", "083", "721", "681", "726", "507", "817",
    "145", "785", "481", "674", "214", "243", "033", "558", "226",
]

ALLOWED_KITS_SET = set(ALLOWED_KITS)


def normalize_kit(starlink: str) -> str:
    """Нормалізує номер KIT до рядка з цифр."""
    digits = "".join(ch for ch in str(starlink).strip() if ch.isdigit())
    if not digits:
        return ""
    if len(digits) < 3:
        digits = digits.zfill(3)
    return digits


def is_allowed_kit(starlink: str) -> bool:
    """Перевіряє, чи входить номер KIT у дозволений список."""
    kit = normalize_kit(starlink)
    return kit in ALLOWED_KITS_SET


async def init_db():
    """Ініціалізує таблиці бази даних і синхронізує список KIT."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                starlink TEXT NOT NULL,
                volume REAL NOT NULL,
                download_date TEXT NOT NULL
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS kits (
                starlink TEXT PRIMARY KEY
            )
            """
        )
        await db.execute("DELETE FROM kits")
        for kit in ALLOWED_KITS:
            await db.execute(
                "INSERT OR IGNORE INTO kits (starlink) VALUES (?)",
                (kit,),
            )
        await db.commit()


async def get_all_kits() -> list[str]:
    """Повертає список усіх дозволених номерів KIT."""
    return list(ALLOWED_KITS)


async def add_download(starlink: str, volume: float, download_date: str) -> bool:
    """Додає запис про завантаження, якщо KIT дозволений."""
    kit = normalize_kit(starlink)
    if not is_allowed_kit(kit):
        return False

    clean_date = str(download_date).strip()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO downloads (starlink, volume, download_date) VALUES (?, ?, ?)",
            (kit, float(volume), clean_date),
        )
        await db.commit()
    return True


async def delete_download_by_id(record_id: int) -> bool:
    """Видаляє запис за ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("DELETE FROM downloads WHERE id = ?", (record_id,))
        await db.commit()
        return cursor.rowcount > 0


async def get_recent_downloads(limit: int = 10):
    """Повертає останні записи з бази."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id, starlink, volume, download_date FROM downloads ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        return await cursor.fetchall()


async def get_today_count() -> int:
    """Повертає кількість записів за сьогодні по дозволених KIT."""
    today_str = datetime.now().strftime("%Y-%m-%d")
    placeholders = ",".join("?" for _ in ALLOWED_KITS)
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            f"SELECT COUNT(*) FROM downloads WHERE download_date = ? AND starlink IN ({placeholders})",
            (today_str, *ALLOWED_KITS),
        )
        row = await cursor.fetchone()
        return int(row[0]) if row else 0


async def get_monthly_report() -> dict:
    """Формує місячний звіт по всіх дозволених KIT."""
    month_prefix = datetime.now().strftime("%Y-%m")
    report: dict[str, dict] = {
        kit: {"total": 0.0, "dates": []} for kit in ALLOWED_KITS
    }

    placeholders = ",".join("?" for _ in ALLOWED_KITS)
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            f"""
            SELECT starlink, volume, download_date
            FROM downloads
            WHERE download_date LIKE ? AND starlink IN ({placeholders})
            ORDER BY download_date ASC, id ASC
            """,
            (f"{month_prefix}%", *ALLOWED_KITS),
        )
        rows = await cursor.fetchall()

    for starlink, volume, download_date in rows:
        kit = normalize_kit(starlink)
        if kit not in report:
            continue
        vol = float(volume or 0.0)
        dt = str(download_date).strip()

        report[kit]["total"] += vol
        if dt and dt not in report[kit]["dates"]:
            report[kit]["dates"].append(dt)

    return report