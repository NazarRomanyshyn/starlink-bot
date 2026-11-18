import asyncio
import os
import re
from calendar import monthrange
from datetime import datetime

import pytz
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message
from aiohttp import web
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from config import BOT_TOKEN, FIXED_STARLINKS, GROUP_CHAT_ID, TIMEZONE
from database import (
    add_download,
    delete_download_by_id,
    get_monthly_report,
    get_recent_downloads,
    get_today_count,
    init_db,
)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler(timezone=pytz.timezone(TIMEZONE))

# Українські назви місяців для звітів
UKRAINIAN_MONTHS_NOMINATIVE = {
    1: "Січень", 2: "Лютий", 3: "Березень", 4: "Квітень",
    5: "Травень", 6: "Червень", 7: "Липень", 8: "Серпень",
    9: "Вересень", 10: "Жовтень", 11: "Листопад", 12: "Грудень"
}


def is_last_day_of_month() -> bool:
    today = datetime.now()
    last_day = monthrange(today.year, today.month)[1]
    return today.day == last_day


# ========= КОМАНДА /report =========
@dp.message(Command("report"))
async def cmd_report(message: Message):
    is_final = is_last_day_of_month()
    await send_report(chat_id=message.chat.id, is_final=is_final)


# ========= СПІЛЬНА ЛОГІКА ЗАПИСУ ТА ВІДПРАВКИ =========
async def process_and_save_report(text: str, chat_id: int):
    if not text or not str(text).strip():
        return

    # Забираємо зайві пробіли та згортаємо зайві переноси рядків
    cleaned_text = re.sub(r'\s+', ' ', str(text)).strip()

    # Парсимо звіт Starlink
    starlink_match = re.search(r"KIT.*?(\d{3})", cleaned_text, re.IGNORECASE)
    volume_match = re.search(r"([\d.,]+)\s*(МБ|ГБ|MB|GB)", cleaned_text, re.IGNORECASE)
    datetime_match = re.search(r"(\d{4}-\d{2}-\d{2})", cleaned_text)

    if starlink_match and volume_match:
        try:
            starlink = starlink_match.group(1).strip()
            raw_volume = float(volume_match.group(1).replace(",", "."))
            unit = volume_match.group(2).upper()

            # Якщо вказано в ГБ — переводимо в МБ для збереження в базу
            if "Г" in unit or "G" in unit:
                volume = raw_volume * 1024
            else:
                volume = raw_volume

            download_date = datetime_match.group(1).strip() if datetime_match else datetime.now().strftime("%Y-%m-%d")

            # Записуємо в базу даних SQLite на ПК (зберігаємо в МБ)
            await add_download(starlink, volume, download_date)
            print(f"[УСПІХ БД] Записано: KIT {starlink} | {raw_volume} {unit} ({volume:.2f} МБ) | {download_date}")
        except Exception as e:
            print(f"[ПОМИЛКА БАЗИ]: {e}")

    # Дублюємо повідомлення в групу (або куди вказано) з очищеним текстом
    try:
        target_chat = GROUP_CHAT_ID if GROUP_CHAT_ID else chat_id
        await bot.send_message(chat_id=target_chat, text=cleaned_text)
    except Exception as e:
        print(f"Помилка відправки в Telegram: {e}")


# ========= ФОРМУВАННЯ ЗВІТУ (ТАБЛИЦЯ) =========
async def send_report(chat_id: int, is_final: bool = False):
    report = await get_monthly_report(FIXED_STARLINKS if FIXED_STARLINKS else None)

    if not report:
        text = "<b>ПІДСУМОК:</b> Даних за місяць немає." if is_final else "<b>ЗВІТ:</b> Даних за місяць поки немає."
        await bot.send_message(chat_id, text, parse_mode="HTML")
        return

    sorted_items = sorted(
        report.items(),
        key=lambda x: (-x[1]["total"], x[0])
    )

    now = datetime.now()
    month_name = f"{UKRAINIAN_MONTHS_NOMINATIVE[now.month]} {now.year}"

    if is_final:
        header = f"<b>ПІДСУМОК СТАРИНК ({month_name})</b>\n<code>KIT|Об'єм     |Дати</code>\n<code>----|-----------|------</code>"
    else:
        header = f"<b>ЗВІТ СТАРИНК ({month_name})</b>\n<code>KIT|Об'єм     |Дати</code>\n<code>----|-----------|------</code>"

    rows = []
    total_all = 0.0
    for starlink, data in sorted_items:
        total_all += data["total"]
        val = data["total"]
        
        if val >= 1024:
            vol_str = f"{val / 1024:.2f} ГБ"
        else:
            vol_str = f"{val:.2f} МБ"

        # Очищуємо дати від зайвих пробілів
        clean_dates = [re.sub(r'\s+', '', str(d)) for d in data["dates"]]
        dates = ", ".join(clean_dates) if clean_dates else "-"
        
        clean_starlink = str(starlink).strip()
        rows.append(f"<code>{clean_starlink:<4} | {vol_str:<9} | {dates}</code>")

    if total_all >= 1024:
        total_str = f"{total_all / 1024:.2f} ГБ"
    else:
        total_str = f"{total_all:.2f} МБ"

    footer = f"<code>-----|-----------|------</code>\n<b>ЗАГАЛОМ:</b> <code>{total_str}</code>"
    if is_final:
        footer += "\n<b>Місяць закрито.</b>"

    full_text = f"{header}\n" + "\n".join(rows) + f"\n{footer}"

    for i in range(0, len(full_text), 4000):
        await bot.send_message(chat_id, full_text[i:i + 4000], parse_mode="HTML")


async def daily_report_job():
    today_count = await get_today_count()
    is_final = is_last_day_of_month()

    if not is_final and today_count == 0:
        return

    if GROUP_CHAT_ID:
        await send_report(chat_id=GROUP_CHAT_ID, is_final=is_final)

@dp.message(Command("list"))
async def cmd_list(message: Message):
    print("👉 НАТИСНУТО КОМАНДУ /list !")
    records = await get_recent_downloads(10)
    if not records:
        await message.answer("База даних порожня.")
        return

    text = "<b>Останні записи в базі:</b>\n<code>ID |KIT|Об'єм    |Дата</code>\n<code>--|------|----------|------------</code>\n"
    for row in records:
        rec_id, kit, volume, date = row
        if volume >= 1024:
            vol_str = f"{volume / 1024:.2f} ГБ"
        else:
            vol_str = f"{volume:.2f} МБ"
        
        # Повне очищення пробілів у полях з бази
        clean_id = str(rec_id).strip()
        clean_kit = str(kit).strip()
        clean_date = str(date).strip()
        
        text += f"<code>{clean_id:<2} | {clean_kit:<4} | {vol_str:<8} | {clean_date}</code>\n"
    
    text += "\nЩоб видалити запис, використайте команду:\n<code>/del [ID]</code> (наприклад: <code>/del 5</code>)"
    await message.answer(text, parse_mode="HTML")


# ========= КОМАНДА /del або /delete (видалити рядок за ID) =========
@dp.message(Command("del", "delete"))
async def cmd_delete(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip().isdigit():
        await message.answer(
            "⚠️ Будь ласка, вкажіть ID запису для видалення.\n"
            "Приклад: <code>/del 5</code>\n"
            "Щоб подивитися список ID, введіть /list",
            parse_mode="HTML"
        )
        return

    record_id = int(args[1].strip())
    success = await delete_download_by_id(record_id)

    if success:
        await message.answer(f"✅ Запис із ID <b>{record_id}</b> успішно видалено з бази даних!", parse_mode="HTML")
        print(f"[БАЗА ДАНИХ] Видалено запис ID {record_id}")
    else:
        await message.answer(f"❌ Запис із ID <b>{record_id}</b> не знайдено в базі.", parse_mode="HTML")

# Звичайні повідомлення в ЛС боту
@dp.message()
async def handle_all_messages(message: Message):
    text = message.text or message.caption or ""
    if text.startswith("/"):
        return
    await process_and_save_report(text, message.chat.id)

# ========= ЛОКАЛЬНИЙ ВЕБ-СЕРВЕР ДЛЯ ДОДАТКУ =========
async def handle_web_request(request):
    try:
        try:
            data = await request.json()
        except:
            data = await request.post()

        chat_id = data.get("chat_id")
        text = data.get("text", "")

        print(f"\n[ВЕБ-СЕРВЕР] Отримано звіт від додатку! Текст: {text}")
        
        await process_and_save_report(text, chat_id)

        return web.json_response({"ok": True})
    except Exception as e:
        print(f"[ПОМИЛКА СЕРВЕРА]: {e}")
        return web.json_response({"ok": False, "error": str(e)}, status=400)


async def handle_ping(request):
    return web.Response(text="Bot is alive!")

async def start_web_server():
    app = web.Application()
    app.router.add_post('/send', handle_web_request)
    app.router.add_get('/', handle_ping)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"🌐 Веб-сервер запущено на порту {port}")


# ========= ЗАПУСК =========
async def main():
    await init_db()

    scheduler.add_job(
        daily_report_job,
        CronTrigger(hour=17, minute=40),
        id="daily_report"
    )
    scheduler.start()

    await start_web_server()

    print("Бот запущений і чекає на звіти...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())