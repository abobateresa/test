import os
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import Command

BOT_TOKEN = os.getenv("8195894653:AAFPPbyT0Y9oTmXjQYo0i7WNMwa68lA_tA8")
if not BOT_TOKEN:
    raise RuntimeError("Переменная окружения BOT_TOKEN не установлена!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def start_handler(message: Message):
    await message.answer("Привет! Напиши 'ping'.")

@dp.message()
async def ping_pong(message: Message):
    if message.text and message.text.strip().lower() == "ping":
        await message.answer("pong 🏓")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
