import os
import asyncio
import sys
import time
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from openai import AsyncOpenAI

# Твой ID
ADMIN_ID = 8311893594

# Настройки
BOT_TOKEN = os.getenv("BOT_TOKEN")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Клиент DeepSeek
ai_client = AsyncOpenAI(
    base_url="https://api.deepseek.com",
    api_key=DEEPSEEK_API_KEY
)

# Хранилище
user_request_history = {}  # {user_id: [время_запроса1, время_запроса2...]}
admin_reply_map = {}

# --- ФУНКЦИЯ ЛИМИТА ---
def is_ai_rate_limited(user_id):
    if user_id == ADMIN_ID: return False # Админ без лимитов
    
    now = time.time()
    if user_id not in user_request_history:
        user_request_history[user_id] = []
    
    # Очищаем старые запросы (старше 1 часа)
    user_request_history[user_id] = [t for t in user_request_history[user_id] if now - t < 3600]
    
    if len(user_request_history[user_id]) < 7:
        user_request_history[user_id].append(now)
        return False # Лимит не превышен, можно делать запрос
    return True # Лимит превышен

class BotStates(StatesGroup):
    ai_mode = State()
    operator_mode = State()

def get_main_keyboard():
    kb = [[KeyboardButton(text="🤖 Задать вопрос ИИ")], [KeyboardButton(text="👨‍💻 Оператор")], [KeyboardButton(text="📊 О бирже HTX")]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# --- ХЕНДЛЕРЫ ---

@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.set_state(BotStates.ai_mode)
    await message.answer("Привет! Я ИИ-помощник по бирже HTX. Выбери пункт меню или задай вопрос.", reply_markup=get_main_keyboard())

@dp.message(F.text == "📊 О бирже HTX")
async def info_htx(message: types.Message):
    await message.answer("HTX (бывшая Huobi) — биржа с P2P без комиссий.")

@dp.message(F.text.in_({"👨‍💻 Оператор", "оператор", "Оператор"}))
async def switch_to_operator(message: types.Message, state: FSMContext):
    await state.set_state(BotStates.operator_mode)
    await message.answer("Режим связи с оператором включен.", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Вернуться к ИИ")]], resize_keyboard=True))

@dp.message(BotStates.operator_mode, F.text == "❌ Вернуться к ИИ")
async def back_to_ai(message: types.Message, state: FSMContext):
    await state.set_state(BotStates.ai_mode)
    await message.answer("Вернулись к ИИ.", reply_markup=get_main_keyboard())

@dp.message(BotStates.operator_mode)
async def forward_to_admin(message: types.Message):
    msg = await bot.send_message(ADMIN_ID, f"📥 Сообщение от {message.from_user.id}:\n{message.text}")
    admin_reply_map[msg.message_id] = message.from_user.id

@dp.message(F.chat.id == ADMIN_ID, F.reply_to_message)
async def handle_admin_reply(message: types.Message):
    if message.reply_to_message.message_id in admin_reply_map:
        uid = admin_reply_map[message.reply_to_message.message_id]
        await bot.send_message(uid, f"👨‍💻 Ответ оператора:\n{message.text}")
        await message.reply("Отправлено!")

# --- ГЛАВНЫЙ ОБРАБОТЧИК ИИ ---
@dp.message(BotStates.ai_mode)
async def handle_ai_questions(message: types.Message):
    # Игнорируем кнопки, если они попали сюда
    if message.text in ["🤖 Задать вопрос ИИ", "👨‍💻 Оператор", "📊 О бирже HTX"]:
        return

    # ПРОВЕРКА ЛИМИТА (Здесь токены еще не тратятся!)
    if is_ai_rate_limited(message.from_user.id):
        await message.answer("⚠️ Лимит исчерпан (7 сообщений в час). Попробуй позже или позови оператора.")
        return

    # Если лимит пройден — делаем запрос
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    try:
        response = await ai_client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "Ты помощник по бирже HTX. Отвечай кратко."},
                {"role": "user", "content": message.text}
            ]
        )
        await message.answer(response.choices[0].message.content)
    except Exception as e:
        print(f"Ошибка: {e}")
        await message.answer("Ошибка связи с ИИ.")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
