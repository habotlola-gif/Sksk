import os
import asyncio
import sys
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from openai import AsyncOpenAI

# Твой Telegram ID для проверки прав администратора
ADMIN_ID = 8311893594

# Токены из переменных окружения Railway
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Инициализация бота, диспетчера и ИИ-клиента
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Подключение к OpenRouter с дополнительными заголовками для стабильности
ai_client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
    default_headers={
        "HTTP-Referer": "https://railway.app",
        "X-Title": "HTX Support Bot"
    }
)

# Временные базы данных в оперативной памяти
users_db = set()          # Хранит ID всех уникальных пользователей
admin_reply_map = {}      # Связывает id_сообщения_у_админа -> id_пользователя

# Состояния для переключения режимов (FSM)
class BotStates(StatesGroup):
    ai_mode = State()        # Режим общения с нейросетью
    operator_mode = State()  # Режим прямой связи с тобой

# База знаний для ИИ по бирже HTX
HTX_BASE_KNOWLEDGE = """
Ты — полезный ИИ-помощник по криптовалютной бирже HTX. Отвечай кратко, вежливо и по делу на русском языке.
Используй только эту информацию для ответов:
1. Регистрация: Возможна по почте или телефону. Для работы с P2P нужно пройти верификацию KYC уровня 1.
2. P2P-торговля: Покупка и продажа крипты за фиат (рубли/гривны/тенге). Комиссия отсутствует. Рекомендуется выбирать мерчантов с высоким процентом выполненных ордеров (выше 95%).
3. Пополнение: Можно через P2P или прямым переводом криптовалюты на свой адрес в соответствующей сети (внимательно проверяй сеть, например, TRC-20 для USDT).

Если информации по вопросу пользователя нет в этом тексте, ответь: "К сожалению, я не владею этой информацией. Рекомендую обратиться в официальную поддержку HTX или позвать оператора нажав на кнопку в меню."
"""

# --- КЛАВИАТУРЫ ---
def get_main_keyboard():
    kb = [
        [KeyboardButton(text="🤖 Задать вопрос ИИ")],
        [KeyboardButton(text="👨‍💻 Оператор")],
        [KeyboardButton(text="📊 О бирже HTX")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_operator_keyboard():
    kb = [[KeyboardButton(text="❌ Вернуться к ИИ")]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


# --- ХЕНДЛЕРЫ ---

@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    """Стартовая команда /start"""
    users_db.add(message.from_user.id)
    await state.set_state(BotStates.ai_mode)
    
    # Обращение "сэр" будет выводиться ТОЛЬКО тебе
    if message.from_user.id == ADMIN_ID:
        greeting = (
            "Здравствуйте, сэр! Рад вас видеть. Я ваш персональный ИИ-помощник по бирже HTX.\n"
            "Вы можете управлять системой и смотреть статистику через команду /admin."
        )
    else:
        greeting = (
            "Здравствуйте! Добро пожаловать в ИИ-помощник по бирже HTX.\n"
            "Выберите интересующий пункт меню или просто задайте свой вопрос."
        )
        
    await message.answer(greeting, reply_markup=get_main_keyboard())

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    """Админ-панель (доступна только для твоего ID)"""
    if message.from_user.id != ADMIN_ID:
        return  

    total_users = len(users_db)
    python_version = sys.version.split()[0]
    
    admin_text = (
        "⚙️ **Админ-панель ИИ-Помощника**\n\n"
        f"📊 **Статистика:**\n"
        f"├ Всего уникальных пользователей: {total_users}\n"
        f"└ Активных связок «сообщение-юзер»: {len(admin_reply_map)}\n\n"
        f"🖥 **Характеристики системы:**\n"
        f"├ Платформа деплоя: Railway\n"
        f"├ Язык: Python {python_version}\n"
        f"├ Библиотека: aiogram v3\n"
        f"└ Модель: meta-llama/llama-3-8b-instruct:free"
    )
    await message.answer(admin_text, parse_mode="Markdown")

@dp.message(F.text.in_({"👨‍💻 Оператор", "оператор", "Оператор"}))
async def switch_to_operator(message: types.Message, state: FSMContext):
    """Перевод пользователя в режим оператора"""
    await state.set_state(BotStates.operator_mode)
    await message.answer(
        "Вы переключены на режим связи с оператором.\n"
        "Отправьте ваше сообщение, и оператор ответит вам в ближайшее время.",
        reply_markup=get_operator_keyboard()
    )
    # Уведомление приходит тебе в чат
    await bot.send_message(
        ADMIN_ID, 
        f"🔔 Новый запрос оператора от пользователя {message.from_user.id} (@{message.from_user.username or 'нет_юзернейма'})"
    )

@dp.message(BotStates.operator_mode, F.text == "❌ Вернуться к ИИ")
async def back_to_ai(message: types.Message, state: FSMContext):
    """Выход из режима оператора обратно к ИИ"""
    await state.set_state(BotStates.ai_mode)
    await message.answer("Вы вернулись в режим общения с ИИ.", reply_markup=get_main_keyboard())

@dp.message(BotStates.operator_mode)
async def forward_to_admin(message: types.Message):
    """Пересылка сообщений пользователя тебе в чат"""
    info_text = f"📥 Сообщение от пользователя {message.from_user.id}:\n\n{message.text}"
    msg_sent_to_admin = await bot.send_message(ADMIN_ID, info_text)
    # Запоминаем связку, чтобы ты мог ответить через Reply
    admin_reply_map[msg_sent_to_admin.message_id] = message.from_user.id

@dp.message(F.chat.id == ADMIN_ID, F.reply_to_message)
async def handle_admin_reply(message: types.Message):
    """Твой ответ пользователю (через функцию Ответить/Reply)"""
    reply_to_id = message.reply_to_message.message_id
    
    if reply_to_id in admin_reply_map:
        user_id = admin_reply_map[reply_to_id]
        try:
            await bot.send_message(user_id, f"👨‍💻 Ответ оператора:\n\n{message.text}")
            await message.reply("Отправлено! ✅")
        except Exception as e:
            await message.reply(f"Не удалось доставить сообщение пользователю: {e}")
    else:
        await message.reply("Не могу определить, какому пользователю принадлежит это сообщение.")

@dp.message(F.text == "📊 О бирже HTX")
async def info_htx(message: types.Message):
    """Информационная кнопка"""
    await message.answer(
        "HTX (бывшая Huobi) — одна из крупнейших мировых криптовалютных платформ.\n"
        "Здесь доступна быстрая регистрация, покупка криптовалюты через P2P без комиссий и безопасное хранение активов."
    )

@dp.message()
async def handle_ai_questions(message: types.Message):
    """Режим ответов ИИ (использует бесплатную модель Llama 3)"""
    users_db.add(message.from_user.id)
    
    if message.text == "🤖 Задать вопрос ИИ":
        await message.answer("Просто напишите ваш вопрос текстом в чат, и нейросеть мгновенно сформирует ответ!")
        return

    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")

    try:
        # Запрос к бесплатной и стабильной модели на OpenRouter
        response = await ai_client.chat.completions.create(
            model="meta-llama/llama-3-8b-instruct:free",
            messages=[
                {"role": "system", "content": HTX_BASE_KNOWLEDGE},
                {"role": "user", "content": message.text}
            ]
        )
        bot_answer = response.choices[0].message.content
        await message.answer(bot_answer)
    except Exception as e:
        print(f"!!! ОШИБКА API OPENROUTER: {e}", flush=True)
        await message.answer("Извините, временно не удалось связаться с ИИ. Попробуйте позже или позовите оператора.")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
