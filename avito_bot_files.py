# === FILE: README.md ===
# Avito monitor bot — быстрый старт

Этот проект — минимальный бот для Telegram, который принимает ссылку поиска с Avito и присылает пользователю новые объявления.

Шаги по запуску (Windows):
1. Открой папку проекта в терминале/CMD/PowerShell.
2. Создай виртуальное окружение (если ещё не создано):
   ```bash
   python -m venv venv
   ```
3. Активируй окружение:
   - PowerShell:
     ```powershell
     .\venv\Scripts\Activate.ps1
     ```
     Если выдаёт ошибку про ExecutionPolicy — открой PowerShell как администратор и выполни:
     ```powershell
     Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
     ```
   - или в cmd:
     ```cmd
     venv\Scripts\activate.bat
     ```
4. Установи зависимости:
   ```bash
   pip install -r requirements.txt
   ```
5. Открой файл `config.py` и вставь туда токен от BotFather (переменная TOKEN).
6. (Для тестирования) в `config.py` можно временно уменьшить `CHECK_INTERVAL` до 60 (1 минута).
7. Запусти бота:
   ```bash
   python bot.py
   ```

Тест: в Telegram отправь боту ссылку поиска Avito (например, ту, что ты уже пробовал). Бот должен ответить, что добавил запрос. Через заданный интервал (по умолчанию 30 минут, или значение CHECK_INTERVAL) бот пришлёт новые объявления.


# === FILE: requirements.txt ===
aiogram
requests
beautifulsoup4
lxml

# === FILE: config.py ===
# Настройки проекта — отредактируй перед запуском
TOKEN = "7842845343:AAGCffg57oYZMSpw0X2iyjdQtBt2oVBl220"  # <-- Вставь сюда токен от BotFather
DB_PATH = "avito_bot.db"
# Интервал проверки в секундах (для теста можно поставить 60)
CHECK_INTERVAL = 60  # 30 минут
# User-Agent для запросов — имитируем обычный браузер
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0 Safari/537.36"
)


# === FILE: db.py ===
import sqlite3
from typing import List, Tuple, Dict


def get_conn(path: str = "avito_bot.db") -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    c = conn.cursor()
    c.execute(
        """
    CREATE TABLE IF NOT EXISTS searches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        link TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """
    )
    c.execute(
        """
    CREATE TABLE IF NOT EXISTS seen_ads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        search_id INTEGER NOT NULL,
        ad_id TEXT NOT NULL,
        url TEXT,
        title TEXT,
        price TEXT,
        UNIQUE(search_id, ad_id),
        FOREIGN KEY(search_id) REFERENCES searches(id) ON DELETE CASCADE
    )
    """
    )
    conn.commit()


def add_search(conn: sqlite3.Connection, user_id: int, link: str) -> int:
    c = conn.cursor()
    c.execute("INSERT INTO searches (user_id, link) VALUES (?, ?)", (user_id, link))
    conn.commit()
    return c.lastrowid


def get_all_searches(conn: sqlite3.Connection) -> List[Tuple[int, int, str]]:
    c = conn.cursor()
    c.execute("SELECT id, user_id, link FROM searches")
    return c.fetchall()


def is_seen(conn: sqlite3.Connection, search_id: int, ad_id: str) -> bool:
    c = conn.cursor()
    c.execute("SELECT 1 FROM seen_ads WHERE search_id = ? AND ad_id = ?", (search_id, ad_id))
    return c.fetchone() is not None


def mark_seen(
    conn: sqlite3.Connection,
    search_id: int,
    ad_id: str,
    url: str = None,
    title: str = None,
    price: str = None,
) -> None:
    c = conn.cursor()
    c.execute(
        """
    INSERT OR IGNORE INTO seen_ads (search_id, ad_id, url, title, price)
    VALUES (?, ?, ?, ?, ?)
    """,
        (search_id, ad_id, url, title, price),
    )
    conn.commit()


# === FILE: avito_parser.py ===
import re
from bs4 import BeautifulSoup
from typing import List, Dict


def parse_avito_search(html: str) -> List[Dict]:
    """
    Пытаемся извлечь список объявлений из HTML страницы поиска Avito.
    Возвращаем список словарей: {id, title, price, url}

    Примечание: Avito меняет структуру страниц — этот простой парсер работает для многих
    случаев, но при проблемах можно перейти на Playwright (эмуляция браузера) — я помогу.
    """
    soup = BeautifulSoup(html, "lxml")
    results = []
    seen = set()

    anchors = soup.find_all("a", href=True)
    for a in anchors:
        href = a["href"]
        if href.startswith("//"):
            href = "https:" + href
        elif href.startswith("/"):
            href = "https://www.avito.ru" + href

        if "avito.ru" not in href:
            continue

        m = re.search(r"(\d{6,})", href)
        if not m:
            continue
        ad_id = m.group(1)
        if ad_id in seen:
            continue

        title = a.get_text(strip=True)

        # Ищем цену вокруг ссылки (поднимаемся по DOM)
        price = None
        parent = a.parent
        for _ in range(4):
            if parent is None:
                break
            text = parent.get_text(" ", strip=True)
            p_match = re.search(r"(\d[\d\s\u00A0]*₽|\d[\d\s\u00A0]* руб\.?)", text)
            if p_match:
                price = p_match.group(0)
                break
            parent = parent.parent

        results.append({
            "id": ad_id,
            "title": title or "(без заголовка)",
            "price": price or "(цена не найдена)",
            "url": href,
        })
        seen.add(ad_id)

    return results


# === FILE: bot.py ===
import asyncio
import logging
import requests

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

import config
import db
import avito_parser

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Создаём подключение к БД
conn = db.get_conn(config.DB_PATH)

bot = Bot(token=config.TOKEN)
dp = Dispatcher()


@dp.message(Command("start"))
async def start_command(message: types.Message):
    await message.answer(
        "Привет! Пришли мне ссылку на поиск Авито — я буду мониторить её и присылать новые объявления."
    )


@dp.message()
async def handle_message(message: types.Message):
    text = (message.text or "").strip()
    if "avito.ru" in text:
        # Сохраняем запрос в БД в отдельном потоке (чтобы не блокировать event loop)
        await asyncio.to_thread(db.add_search, conn, message.from_user.id, text)
        await message.answer("✅ Запрос добавлен! Я буду проверять и отправлять новые объявления.")
    else:
        await message.answer("Пожалуйста, пришли ссылку поиска с avito.ru")


async def check_once_for_search(search_tuple):
    search_id, user_id, link = search_tuple
    try:
        resp = requests.get(link, headers={"User-Agent": config.USER_AGENT}, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        logger.warning("Ошибка при загрузке %s: %s", link, e)
        return

    ads = avito_parser.parse_avito_search(resp.text)

    for ad in ads:
        seen = await asyncio.to_thread(db.is_seen, conn, search_id, ad["id"])
        if not seen:
            await asyncio.to_thread(db.mark_seen, conn, search_id, ad["id"], ad["url"], ad["title"], ad["price"])
            text = f"🔔 Новое объявление:\n{ad['title']}\n{ad['price']}\n{ad['url']}"
            try:
                await bot.send_message(user_id, text)
            except Exception as e:
                logger.warning("Не удалось отправить сообщение пользователю %s: %s", user_id, e)


async def monitor_loop():
    while True:
        searches = await asyncio.to_thread(db.get_all_searches, conn)
        if not searches:
            logger.info("Нет сохранённых поисков — жду %s секунд", config.CHECK_INTERVAL)
        for search in searches:
            await check_once_for_search(search)
        await asyncio.sleep(config.CHECK_INTERVAL)


async def main():
    db.init_db(conn)
    # Старт фоновой задачи монитора
    asyncio.create_task(monitor_loop())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
