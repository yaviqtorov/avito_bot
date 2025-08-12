import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from parser import check_new_ads

BOT_TOKEN = "7842845343:AAGCffg57oYZMSpw0X2iyjdQtBt2oVBl220"  # вставь сюда токен от @BotFather

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Храним ссылки пользователей
user_links = {}

@dp.message(Command("start"))
async def start_command(message: types.Message):
    await message.answer("Привет! Пришли ссылку с Авито, которую будем проверять.")

@dp.message(Command("check"))
async def check_command(message: types.Message):
    user_id = message.from_user.id
    if user_id not in user_links:
        await message.answer("Сначала отправь ссылку с Авито!")
        return

    url = user_links[user_id]
    await message.answer("🔍 Проверяю объявления...")

    ads = await asyncio.to_thread(check_new_ads, url)

    if ads:
        for ad in ads:
            await message.answer(f"📌 {ad['title']}\n💰 {ad['price']}\n🔗 {ad['url']}")
    else:
        await message.answer("Пока нет объявлений.")

@dp.message()
async def save_link(message: types.Message):
    text = message.text.strip()
    if text.startswith("https://avito.ru") or text.startswith("https://www.avito.ru") or text.startswith("https://m.avito.ru"):
        user_links[message.from_user.id] = text
        await message.answer("✅ Ссылка сохранена! Теперь можешь ввести /check")
    else:
        await message.answer("⚠ Отправь корректную ссылку на Авито (m.avito.ru или www.avito.ru).")


async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
