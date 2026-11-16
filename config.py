import os

from dotenv import load_dotenv

load_dotenv()
print("DEBUG TOKEN:", os.getenv("BOT_TOKEN")) # Додайте цей рядок для перевірки

# Пропишіть ваш реальний токен сюди напряму в дужках:
BOT_TOKEN = "9236224615:AAFsGUDGe9wCFddTvw0q8Rx9vGMljHbfqas"
GROUP_CHAT_ID = -1003941866775
TIMEZONE = "Europe/Kiev"

# Якщо хочеш завжди показувати певний список KIT (навіть з 0) — заповни тут
# Якщо залишити порожнім — показує тільки ті, по яких були дані цього місяця
FIXED_STARLINKS = [
    # "123",
    # "456",
    # "789",
]