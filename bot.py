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

# Токены из переменных окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Инициализация бота, диспетчера с памятью для состояний и ИИ-клиента
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
ai_client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

# Внутриигровые базы данных (в памяти сервера)
users_db = set()          # Хранит ID всех уникальных пользователей
admin_reply_map = {}      # Связывает id_сообщения_у_админа -> id_пользователя

# Определение состояний для FSM
class BotStates(StatesGroup):
    ai_mode = State()        # Режим общения с нейросетью (по умолчанию)
    operator_mode = State()  # Режим прямой связи с оператором

# Базовые знания для ИИ
HTX_BASE_KNOWLEDGE = """
Ты — полезный ИИ-помощник по криптовалютной бирже HTX. Отвечай кратко, вежливо и по делу.
Используй только эту информацию для ответов:
1. Регистрация: Возможна по почте или телефону. Для работы с P2P нужно пройти верификацию KYC уровня 1.
2. P2P-торговля: Покупка и продажа крипты за фиат. Комиссия отсутствует. Рекомендуется выбирать мерчантов с высоким процентом выполненных ордеров (выше 95%).
3. Пополнение: Можно через P2P или прямым переводом криптовалюты на свой адрес (внимательно проверяй сеть, например, TRC-20 для USDT).

Если информации по вопросу пользователя нет в этом тексте, ответь: "К сожалению, я не владею этой информацией. Рекомендую обратиться в официальную поддержку HTX или вызвать оператора."
"""

# --- КЛАВИАТУРЫ ---
def get_main_keyboard():
    """Главное меню, выходящее при старте"""
    kb = [
        [KeyboardButton(text="🤖 Задать вопрос ИИ")],
        [KeyboardButton(text="👨‍💻 Оператор")],
        [KeyboardButton(text="📊 О бирже HTX")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_operator_keyboard():
    """Клавиатура внутри чата с оператором"""
    kb = [[KeyboardButton(text="❌ Вернуться к ИИ")]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


# --- ХЕНДЛЕРЫ ---

@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    """Стартовая команда. Добавляет пользователя в базу и выводит список"""
    users_db.add(message.from_user.id)
    await state.set_state(BotStates.ai_mode)
    
    await message.answer(
        "Здравствуйте, сэр! Я ваш персональный ИИ-помощник по бирже HTX.\n"
        "Выберите интересующий пункт меню или просто задайте свой вопрос.",
        reply_markup=get_main_keyboard()
    )

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    """Админ-панель со статистикой (доступна только для вашего ID)"""
    if message.from_user.id != ADMIN_ID:
        return  # Обычные пользователи команду не увидят

    # Подсчет характеристик системы
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
        f"└ Используемая модель: deepseek/deepseek-chat:free"
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
    # Уведомление админа
    await bot.send_message(
        ADMIN_ID, 
        f"🔔 **Новый запрос!**\nПользователь ` {message.from_user.id} ` (@{message.from_user.username}) затребовал оператора.",
        parse_mode="Markdown"
    )

@dp.message(BotStates.operator_mode, F.text == "❌ Вернуться к ИИ")
async def back_to_ai(message: types.Message, state: FSMContext):
    """Выход из режима оператора обратно к ИИ"""
    await state.set_state(BotStates.ai_mode)
    await message.answer(
        "Вы вернулись в режим общения с ИИ.",
        reply_markup=get_main_keyboard()
    )

@dp.message(BotStates.operator_mode)
async def forward_to_admin(message: types.Message):
    """Пересылка всех последующих сообщений пользователя админу"""
    # Формируем красивое сообщение для вас
    info_text = f"📥 **Сообщение от пользователя** ` {message.from_user.id} `:\n\n{message.text}"
    
    # Отправляем админу и запоминаем ID сообщения, чтобы админ мог ответить через Reply
    msg_sent_to_admin = await bot.send_message(ADMIN_ID, info_text, parse_mode="Markdown")
    admin_reply_map[msg_sent_to_admin.message_id] = message.from_user.id

@dp.message(F.chat.id == ADMIN_ID, F.reply_to_message)
async def handle_admin_reply(message: types.Message):
    """Обработка ответов админа (ваших ответов пользователям)"""
    reply_to_id = message.reply_to_message.message_id
    
    # Проверяем, есть ли это сообщение в нашей базе связок
    if reply_to_id in admin_reply_map:
        user_id = admin_reply_map[reply_to_id]
        try:
            await bot.send_message(user_id, f"👨‍💻 **Ответ оператора:**\n\n{message.text}", parse_mode="Markdown")
            await message.reply("Отправлено сэр! ✅")
        except Exception as e:
            await message.reply(f"Не удалось доставить сообщение пользователю: {e}")
    else:
        await message.reply("Сэр, не могу определить, какому пользователю принадлежит это сообщение. Возможно, бот перезагружался.")

@dp.message(F.text == "📊 О бирже HTX")
async def info_htx(message: types.Message):
    """Быстрая кнопка информации"""
    await message.answer(
        "**HTX (бывшая Huobi)** — одна из крупнейших мировых криптовалютных платформ.\n"
        "Здесь доступна быстрая регистрация, покупка криптовалюты через P2P без комиссий и безопасное хранение активов.",
        parse_mode="Markdown"
    )

@dp.message()
async def handle_ai_questions(message: types.Message):
    """Обычный режим общения: запросы отправляются ИИ DeepSeek"""
    users_db.add(message.from_user.id) # На случай, если пишут без /start
    
    if message.text == "🤖 Задать вопрос ИИ":
        await message.answer("Просто напишите ваш вопрос текстом в чат, и нейросеть мгновенно сформирует ответ!")
        return

    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")

    try:
        response = await ai_client.chat.completions.create(
            model="deepseek/deepseek-chat:free",
            messages=[
                {"role": "system", "content": HTX_BASE_KNOWLEDGE},
                {"role": "user", "content": message.text}
            ]
        )
        bot_answer = response.choices[0].message.content
        await message.answer(bot_answer)
    except Exception as e:
        print(f"Ошибка API: {e}")
        await message.answer("Извините, временно не удалось связаться с ИИ. Попробуйте позже.")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

