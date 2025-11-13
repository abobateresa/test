import asyncio
import re
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, \
    ReplyKeyboardRemove, KeyboardButton
from aiogram.client.default import DefaultBotProperties

# ====================================================================
#                          1. КОНФИГУРАЦИЯ
# ====================================================================

TOKEN = "8337680800:AAGk5N64XH3djrKhaPfF0oD9auPGgw-1eXE"

ADMIN_IDS = [
    7918233960,
    7875703787,
    1535122557 #@pmlip
]

# Глобальные хранилища тикетов
# OPEN_TICKETS: {user_id: (admin_id, admin_message_id, has_keyboard, close_task)} - Активные диалоги
OPEN_TICKETS = {}
# PENDING_MESSAGES: {user_id: [message_id_1, message_id_2, ...]} - Накопленные сообщения
PENDING_MESSAGES = {}
# PENDING_TICKETS: {user_id: {admin_id: message_id, ...}} - Уведомления, отправленные админам
PENDING_TICKETS = {}

# Константа таймаута
TIMEOUT_SECONDS = 43200

# Инициализация Bot и Dispatcher
bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# --- КЛАВИАТУРЫ ---

# Reply клавиатура для админа "Закрыть тикет"
ADMIN_CLOSE_TICKET_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="❌ Закрыть тикет")]],
    resize_keyboard=True,
    one_time_keyboard=False
)

# Клавиатура для удаления пользовательской Reply клавиатуры
KEYBOARD_REMOVE = ReplyKeyboardRemove()


# ====================================================================
#                     2. ЛОГИКА АВТОМАТИЧЕСКОГО ЗАКРЫТИЯ
# ====================================================================

def cancel_existing_timer(user_id: int) -> None:
    """Отменяет активный таймер автоматического закрытия для данного тикета."""
    if user_id in OPEN_TICKETS:
        # close_task находится на индексе 3
        close_task = OPEN_TICKETS[user_id][3]
        if close_task and not close_task.done():
            close_task.cancel()
            # print(f"Timer for ticket #{user_id} cancelled.")


async def start_new_timer(user_id: int, admin_id: int) -> None:
    """Запускает новый таймер автоматического закрытия."""

    # 1. Отмена предыдущего таймера
    cancel_existing_timer(user_id)

    # 2. Создание новой асинхронной задачи
    task = asyncio.create_task(auto_close_ticket_task(user_id, admin_id))

    # 3. Обновление состояния в OPEN_TICKETS
    if user_id in OPEN_TICKETS:
        admin_id, admin_message_id, has_keyboard, _ = OPEN_TICKETS[user_id]
        OPEN_TICKETS[user_id] = (admin_id, admin_message_id, has_keyboard, task)


async def auto_close_ticket_task(user_id: int, admin_id: int) -> None:
    """Задача, которая ждет 60 секунд и закрывает тикет, если не была отменена."""
    try:
        await asyncio.sleep(TIMEOUT_SECONDS)

        # Проверка, что тикет все еще открыт и назначен этому админу
        if user_id in OPEN_TICKETS and OPEN_TICKETS[user_id][0] == admin_id:
            await _close_ticket_logic_auto(user_id, admin_id)

    except asyncio.CancelledError:
        # Таймер был отменен, так как пришло новое сообщение
        pass
    except Exception as e:
        print(f"Ошибка в задаче auto_close_ticket_task: {e}")


async def _close_ticket_logic_auto(user_id_to_close: int, admin_id: int) -> None:
    """Вспомогательная функция для выполнения автоматического закрытия тикета."""

    if user_id_to_close not in OPEN_TICKETS:
        return

        # Удаление тикета из активных
    del OPEN_TICKETS[user_id_to_close]

    # 1. Уведомление АДМИНИСТРАТОРА
    await bot.send_message(
        chat_id=admin_id,
        text=f"✅ <b>Тикет для пользователя {user_id_to_close} закрыт автоматически</b> из-за неактивности пользователя в течение {TIMEOUT_SECONDS} секунд.",
        reply_markup=KEYBOARD_REMOVE  # Удаляем клавиатуру "Закрыть тикет"
    )

    # 2. Уведомление ПОЛЬЗОВАТЕЛЯ (Кастомный текст)
    user_close_text = (
        "К сожалению, так как мы не получили от Вас обратную связь, обращение будет завершено. "
        "Если Вам потребуется дальнейшая помощь или возникнут другие вопросы, Вы всегда можете связаться с нами снова. "
        "Благодарим за обращение в службу поддержки Velmonté!\n\n"
        "Также приглашаем Вас присоединиться к Telegram каналу, где публикуются <b>актуальные новости</b> и <b>полезная информация</b>: "
        "https://t.me/+jg-6MkjHa8kyMDFi"
    )
    await bot.send_message(
        chat_id=user_id_to_close,
        text=user_close_text,
    )


# ====================================================================
#                     3. ОСНОВНЫЕ ОБРАБОТЧИКИ
# ====================================================================

@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    """Обработка команды /start."""
    user_id = message.from_user.id
    if user_id in ADMIN_IDS:
        await message.answer("👋 Добро пожаловать, Администратор!", reply_markup=KEYBOARD_REMOVE)
    else:
        await message.answer(
            "👋 Приветствуем вас в нашей службе поддержки!\n\n"
            "Чтобы начать, просто <b>напишите свое сообщение</b> в этот чат. "
            "Мы уведомим администраторов, и они скоро ответят.",
        )


@dp.callback_query(F.data.startswith('accept_'))
async def process_admin_accept_callback(callback_query: CallbackQuery) -> None:
    """Обрабатывает нажатие инлайн-кнопки 'Открыть тикет'."""

    admin_id = callback_query.from_user.id
    user_id = int(callback_query.data.split('_')[1])

    await callback_query.answer("Вы приняли тикет...")

    if admin_id not in ADMIN_IDS:
        await callback_query.message.answer("🚫 У вас нет прав администратора.")
        return

    # Двойная проверка на занятость
    if admin_id in {a_id for _, (a_id, _, _, _) in OPEN_TICKETS.items()}:
        await callback_query.message.answer(
            "🛑 <b>Внимание:</b> Вы уже ведете активный диалог. Пожалуйста, закройте текущий тикет, прежде чем принимать новый.",
            reply_markup=ADMIN_CLOSE_TICKET_KEYBOARD
        )
        return

    if user_id in OPEN_TICKETS:
        await callback_query.message.answer(f"❌ Тикет для пользователя {user_id} уже принят другим администратором.")
        try:
            await bot.delete_message(admin_id, callback_query.message.message_id)
        except:
            pass
        return

    if user_id not in PENDING_TICKETS:
        await callback_query.message.answer("⚠️ Этот запрос устарел или был уже принят/отклонен.")
        return

    # --- ПРИНЯТИЕ ТИКЕТА ---
    messages_to_process = PENDING_TICKETS.pop(user_id)
    # Устанавливаем has_keyboard = False и close_task = None при открытии
    OPEN_TICKETS[user_id] = (admin_id, callback_query.message.message_id, False, None)

    admin_name = callback_query.from_user.full_name

    # 1. Редактируем сообщение о новом тикете (оно же первое подтверждение)
    accepted_text = f"✅ Тикет #{user_id} принят администратором <a href='tg://user?id={admin_id}'>{admin_name}</a>."

    # Редактируем/Удаляем сообщения о тикете у всех админов
    for current_admin_id, message_id_to_process in messages_to_process.items():
        try:
            if current_admin_id == admin_id:
                await bot.edit_message_text(
                    chat_id=current_admin_id, message_id=message_id_to_process, text=accepted_text,
                )
            else:
                await bot.delete_message(
                    chat_id=current_admin_id, message_id=message_id_to_process
                )
        except Exception as e:
            print(f"Не удалось обработать сообщение для админа {current_admin_id}: {e}")

    # 2. АГРЕГИРОВАННАЯ ПЕРЕСЫЛКА СООБЩЕНИЙ
    if user_id in PENDING_MESSAGES:
        message_ids_to_forward = PENDING_MESSAGES.pop(user_id)

        for msg_id in message_ids_to_forward:
            try:
                # Отправка сообщений пользователя
                await bot.copy_message(
                    chat_id=admin_id,
                    from_chat_id=user_id,
                    message_id=msg_id
                )
            except Exception as e:
                print(f"Не удалось скопировать сообщение {msg_id}: {e}")

    # 3. Уведомление пользователя: НИЧЕГО НЕ ПИШЕМ


# --- ОБРАБОТКА РУЧНОГО ЗАКРЫТИЯ ТИКЕТА ---

@dp.message(F.text == "❌ Закрыть тикет")
async def handle_close_button(message: Message) -> None:
    """Обработчик нажатия кнопки '❌ Закрыть тикет'."""
    admin_id = message.from_user.id

    if admin_id not in ADMIN_IDS:
        await message.answer("🚫 У вас нет прав администратора.")
        return

    assigned_tickets = [
        user_id for user_id, (a_id, msg_id, _, _)
        in OPEN_TICKETS.items()
        if a_id == admin_id
    ]

    if not assigned_tickets:
        await message.answer(
            "❓ У вас нет активных тикетов, которые можно закрыть.",
            reply_markup=KEYBOARD_REMOVE
        )
        return

    user_id_to_close = assigned_tickets[0]

    await _close_ticket_logic_manual(message, user_id_to_close, admin_id)


async def _close_ticket_logic_manual(message: Message, user_id_to_close: int, admin_id: int) -> None:
    """Вспомогательная функция для выполнения ручного закрытия тикета."""

    if user_id_to_close not in OPEN_TICKETS:
        await message.answer(f"❓ Тикет для пользователя {user_id_to_close} не найден или уже закрыт.",
                             reply_markup=KEYBOARD_REMOVE)
        return

    assigned_admin_id, _, _, _ = OPEN_TICKETS[user_id_to_close]

    if admin_id != assigned_admin_id:
        await message.answer(
            f"🚫 Вы не назначены на этот тикет. Назначенный администратор: <code>{assigned_admin_id}</code>"
        )
        return

    # --- ЗАКРЫТИЕ ТИКЕТА ---
    # NEW: Отмена таймера перед закрытием
    cancel_existing_timer(user_id_to_close)
    del OPEN_TICKETS[user_id_to_close]

    await message.answer(
        f"✅ <b>Тикет для пользователя {user_id_to_close} закрыт.</b>\n\n"
        "Диалог успешно завершен. Вы снова готовы принимать новые запросы.",
        reply_markup=KEYBOARD_REMOVE
    )

    # --- СООБЩЕНИЕ ДЛЯ ПОЛЬЗОВАТЕЛЯ ---
    await bot.send_message(
        chat_id=user_id_to_close,
        text="🌟 <b>Благодарим Вас за обращение!</b>\n\n"
             "Если в дальнейшем у Вас возникнут вопросы или потребуется дополнительная помощь, мы всегда на связи. "
             "Наша команда готова оказать Вам любую необходимую поддержку. Желаем Вам успешной рабочей среды и всего наилучшего!\n\n"
             "Также приглашаем Вас присоединиться к Telegram каналу, где публикуются <b>актуальные новости</b> и <b>полезная информация</b>: "
             "https://t.me/+jg-6MkjHa8kyMDFi",
    )


# ====================================================================
#                  4. УНИВЕРСАЛЬНЫЙ ОБРАБОТЧИК ДИАЛОГА
# ====================================================================

@dp.message()
async def forward_messages(message: Message) -> None:
    """Обрабатывает все сообщения и управляет таймерами."""

    sender_id = message.from_user.id

    # 1. Если сообщение от АДМИНА
    if sender_id in ADMIN_IDS:
        target_user_info = next(
            ((user_id, a_id, msg_id, has_keyboard, close_task) for user_id, (a_id, msg_id, has_keyboard, close_task) in
             OPEN_TICKETS.items() if a_id == sender_id),
            None
        )

        if target_user_info:
            target_user_id, admin_id, admin_message_id, has_keyboard, _ = target_user_info

            # Админ отвечает на открытый тикет
            await bot.copy_message(chat_id=target_user_id, from_chat_id=sender_id, message_id=message.message_id)

            # NEW: Запускаем/перезапускаем таймер после ответа администратора
            await start_new_timer(target_user_id, admin_id)

            # Отправляем клавиатуру при первом ответе
            if not has_keyboard:
                await message.answer(
                    "Системное сообщение: Закрыть тикет?",
                    reply_markup=ADMIN_CLOSE_TICKET_KEYBOARD
                )
                # Обновляем флаг состояния клавиатуры в OPEN_TICKETS
                OPEN_TICKETS[target_user_id] = (admin_id, admin_message_id, True, OPEN_TICKETS[target_user_id][3])

            return

        # Если админ пишет, но у него нет открытого тикета, удаляем клавиатуру
        await message.answer("❓ У вас нет активных тикетов для ответа.", reply_markup=KEYBOARD_REMOVE)
        return

    # 2. Если сообщение от ПОЛЬЗОВАТЕЛЯ

    # 2.1. Диалог уже ОТКРЫТ (в OPEN_TICKETS) - форвардим назначенному админу
    if sender_id in OPEN_TICKETS:
        target_admin_id, _, _, _ = OPEN_TICKETS[sender_id]
        await bot.copy_message(chat_id=target_admin_id, from_chat_id=sender_id, message_id=message.message_id)

        # NEW: Отменяем таймер, так как пользователь ответил
        cancel_existing_timer(sender_id)
        return

    # 2.2. Сообщения НАКАПЛИВАЮТСЯ (в PENDING_MESSAGES)
    if sender_id in PENDING_MESSAGES:
        # Добавляем ID нового сообщения в список накопления
        PENDING_MESSAGES[sender_id].append(message.message_id)

        # Обновляем текст в уведомлениях админов о количестве сообщений
        num_messages = len(PENDING_MESSAGES[sender_id])
        num_suffix = f"сообщени{'е' if num_messages == 1 else 'я' if 1 < num_messages < 5 else 'й'}"

        new_text = (
            f"Новое обращение #{sender_id}\n"
            f"username: @{message.from_user.username or 'N/A'}\n\n"
            f"Тикет содержит <b>{num_messages}</b> {num_suffix}. Нажмите 'Открыть тикет'."
        )

        for admin_id, msg_id in PENDING_TICKETS.get(sender_id, {}).items():
            try:
                await bot.edit_message_text(
                    chat_id=admin_id,
                    message_id=msg_id,
                    text=new_text,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="✅ Открыть тикет", callback_data=f"accept_{sender_id}")]
                    ])
                )
            except Exception as e:
                pass

        return

    # 2.3. НОВЫЙ тикет - начинаем накопление и отправляем УВЕДОМЛЕНИЕ
    if sender_id not in OPEN_TICKETS and sender_id not in PENDING_MESSAGES:

        # Начинаем накопление сообщений
        PENDING_MESSAGES[sender_id] = [message.message_id]

        # --- ОТПРАВКА УВЕДОМЛЕНИЯ АДМИНАМ ---
        user_id = sender_id
        username = message.from_user.username or "N/A"

        admin_message_text = (
            f"Новое обращение #{user_id}\n"
            f"username: @{username}\n\n"
            f"Тикет содержит <b>1</b> сообщение. Нажмите 'Открыть тикет'."
        )

        admin_accept_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Открыть тикет", callback_data=f"accept_{user_id}")]
        ])

        PENDING_TICKETS[user_id] = {}
        busy_admin_ids = {admin_id for _, (admin_id, _, _, _) in OPEN_TICKETS.items()}
        admin_sent_count = 0

        for admin_id in ADMIN_IDS:
            if admin_id in busy_admin_ids:
                continue

            try:
                msg = await bot.send_message(
                    chat_id=admin_id,
                    text=admin_message_text,
                    reply_markup=admin_accept_keyboard
                )
                PENDING_TICKETS[user_id][admin_id] = msg.message_id
                admin_sent_count += 1

            except Exception as e:
                print(f"Не удалось отправить сообщение админу {admin_id}: {e}")

        # --- ОТВЕТ ПОЛЬЗОВАТЕЛЮ ---
        if admin_sent_count > 0:
            await message.answer("Вы обратились в поддержку клиентов Velmonté.\nЗдравствуйте!")
        else:
            await message.answer("⚠️ Все администраторы заняты. Мы уведомим вас, как только освободится специалист.")
            PENDING_MESSAGES.pop(user_id, None)
            PENDING_TICKETS.pop(user_id, None)


# ====================================================================
#                          5. ЗАПУСК БОТА
# ====================================================================

async def main() -> None:
    """Инициализация и запуск бота."""
    print("Бот поддержки запущен и готов к работе...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот остановлен пользователем.")
