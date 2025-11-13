import asyncio
from aiogram import Bot, Dispatcher, Router
from aiogram.types import Message
from aiogram.filters import Command, CommandObject

# Вставьте свой токен сюда
BOT_TOKEN = "8195894653:AAFPPbyT0Y9oTmXjQYo0i7WNMwa68lA_tA8"

# Инициализация
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()

# Хэндлер на команду /start
@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer("Привет! Напиши мне 'ping', и я отвечу 'pong 🏓'!")

# Хэндлер на любое сообщение "ping"
@router.message()
async def echo_ping(message: Message):
    if message.text and message.text.lower() == "ping":
        await message.answer("pong 🏓")
    # Можно добавить else, если нужно — но обычно не требуется

# Главная функция запуска
async def main():
    dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
