import logging
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils import executor
import sqlite3
from datetime import datetime

API_TOKEN = 'токен'
CODE_PHRASE = 'тест'

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

conn = sqlite3.connect('exit_poll.db')
cursor = conn.cursor()

cursor.execute('''CREATE TABLE IF NOT EXISTS users
                  (id INTEGER PRIMARY KEY AUTOINCREMENT,
                   user_id INTEGER UNIQUE,
                   username TEXT,
                   full_name TEXT)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS votes
                  (id INTEGER PRIMARY KEY AUTOINCREMENT,
                   user_id INTEGER,
                   username TEXT,
                   vote TEXT,
                   timestamp TEXT,
                   district TEXT,
                   polling_station INTEGER,
                   nadezhdin_vote TEXT,
                   registration_vote TEXT,
                   last_10_years_vote TEXT,
                   age TEXT,
                   gender TEXT,
                   FOREIGN KEY (user_id) REFERENCES users (user_id))''')
conn.commit()

class Registration(StatesGroup):
    code_word = State()
    full_name = State()

class ExitPoll(StatesGroup):
    district = State()
    polling_station = State()
    voting = State()
    nadezhdin_vote = State()
    registration_vote = State()
    last_10_years_vote = State()
    age = State()
    gender = State()

@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    
    if user:
        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
        keyboard.add(types.KeyboardButton('Открыть смену'))
        await message.answer("С возвращением! Нажмите 'Открыть смену' для начала голосования.", reply_markup=keyboard)
    else:
        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
        keyboard.add(types.KeyboardButton('Регистрация'))
        await message.answer("Привет! Я бот для проведения экзит-пола. Пожалуйста, зарегистрируйтесь.", reply_markup=keyboard)

@dp.message_handler(Text(equals='Регистрация'))
async def registration(message: types.Message):
    await message.answer("Введите кодовое слово для регистрации:")
    await Registration.code_word.set()

@dp.message_handler(state=Registration.code_word)
async def process_code_word(message: types.Message, state: FSMContext):
    if message.text == CODE_PHRASE:
        await message.answer("Введите ФИО:")
        await Registration.full_name.set()
    else:
        await message.answer("Неверное кодовое слово. Регистрация не разрешена.")
        await state.finish()

@dp.message_handler(state=Registration.full_name)
async def process_full_name(message: types.Message, state: FSMContext):
    full_name = message.text
    cursor.execute("INSERT INTO users (user_id, username, full_name) VALUES (?, ?, ?)",
                   (message.from_user.id, message.from_user.username, full_name))
    conn.commit()
    await message.answer("Регистрация успешно завершена.")
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(types.KeyboardButton('Открыть смену'))
    await message.answer("Нажмите 'Открыть смену' для начала голосования.", reply_markup=keyboard)
    await state.finish()

@dp.message_handler(Text(equals='Открыть смену'))
async def open_shift(message: types.Message):
    await message.answer("Введите район:")
    await ExitPoll.district.set()

@dp.message_handler(Text(equals='Закрыть смену'), state=ExitPoll.voting)
async def close_shift(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        district = data['district']
        polling_station = data['polling_station']

    cursor.execute("SELECT vote, COUNT(*) as count FROM votes WHERE district = ? AND polling_station = ? GROUP BY vote", (district, polling_station))
    results = cursor.fetchall()
    statistics = f"Статистика голосования для района {district}, участок {polling_station}:\n\n"
    for result in results:
        statistics += f"{result[0]}: {result[1]} голосов\n"
    await message.answer(statistics)

    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(types.KeyboardButton('Открыть смену'))
    await message.answer("Смена закрыта. Нажмите 'Открыть смену' для начала новой смены.", reply_markup=keyboard)
    await state.finish()

@dp.message_handler(state=ExitPoll.district)
async def process_district(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['district'] = message.text
    await message.answer("Введите номер избирательного участка:")
    await ExitPoll.polling_station.set()

@dp.message_handler(state=ExitPoll.polling_station)
async def process_polling_station(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['polling_station'] = message.text
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(types.KeyboardButton('Даванков'), types.KeyboardButton('Путин'))
    keyboard.add(types.KeyboardButton('Слуцкий'), types.KeyboardButton('Харитонов'))
    keyboard.add(types.KeyboardButton('Испортил бюллетень (не называть)'), types.KeyboardButton('Забрал бюллетень (не называть)'))
    keyboard.add(types.KeyboardButton('Отказ от ответа'), types.KeyboardButton('Закрыть смену'))
    await message.answer("Смена открыта. Выберите, как человек проголосовал:", reply_markup=keyboard)
    await ExitPoll.voting.set()

@dp.message_handler(state=ExitPoll.voting)
async def process_vote(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['vote'] = message.text
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(types.KeyboardButton('Да'), types.KeyboardButton('Возможно'))
    keyboard.add(types.KeyboardButton('Нет'), types.KeyboardButton('Не знаю/Отказ'))
    keyboard.add(types.KeyboardButton('Пропустить все вопросы'))
    await message.answer("Вы бы проголосовали за Бориса Надеждина, если бы он был в бюллетене?", reply_markup=keyboard)
    await ExitPoll.nadezhdin_vote.set()

@dp.message_handler(state=ExitPoll.nadezhdin_vote)
async def process_nadezhdin_vote(message: types.Message, state: FSMContext):
    if message.text == 'Пропустить все вопросы':
        await process_gender(message, state)  # Перейти сразу к сохранению данных
    else:
        async with state.proxy() as data:
            data['nadezhdin_vote'] = message.text
        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
        keyboard.add(types.KeyboardButton('Да'), types.KeyboardButton('Нет'))
        keyboard.add(types.KeyboardButton('Отказ от ответа'), types.KeyboardButton('Пропустить все вопросы'))
        await message.answer("Вы голосовали по месту регистрации?", reply_markup=keyboard)
        await ExitPoll.registration_vote.set()

@dp.message_handler(state=ExitPoll.registration_vote)
async def process_registration_vote(message: types.Message, state: FSMContext):
    if message.text == 'Пропустить все вопросы':
        await process_gender(message, state)  # Перейти сразу к сохранению данных
    else:
        async with state.proxy() as data:
            data['registration_vote'] = message.text
        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
        keyboard.add(types.KeyboardButton('Голосовал и раньше'), types.KeyboardButton('Не голосовал, в этот раз решил принять участие'))
        keyboard.add(types.KeyboardButton('Это мои первые выборы (для тех, кому 23 и меньше)'), types.KeyboardButton('Пропустить все вопросы'))
        await message.answer("Вы голосовали на выборах последние 10 лет?", reply_markup=keyboard)
        await ExitPoll.last_10_years_vote.set()

@dp.message_handler(state=ExitPoll.last_10_years_vote)
async def process_first_election(message: types.Message, state: FSMContext):
    if message.text == 'Пропустить все вопросы':
        await process_gender(message, state)  # Перейти сразу к сохранению данных
    else:
        async with state.proxy() as data:
            data['last_10_years_vote'] = message.text
        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
        keyboard.add(types.KeyboardButton('18-29'), types.KeyboardButton('30-44'))
        keyboard.add(types.KeyboardButton('45-59'), types.KeyboardButton('60+'))
        keyboard.add(types.KeyboardButton('Отказ от ответа'), types.KeyboardButton('Пропустить все вопросы'))
        await message.answer("Ваш возраст?", reply_markup=keyboard)
        await ExitPoll.age.set()

@dp.message_handler(state=ExitPoll.age)
async def process_age(message: types.Message, state: FSMContext):
    if message.text == 'Пропустить все вопросы':
        await process_gender(message, state)  # Перейти сразу к сохранению данных
    else:
        async with state.proxy() as data:
            data['age'] = message.text
        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
        keyboard.add(types.KeyboardButton('Мужской'), types.KeyboardButton('Женский'))
        keyboard.add(types.KeyboardButton('Пропустить все вопросы'))
        await message.answer("Ваш пол?", reply_markup=keyboard)
        await ExitPoll.gender.set()

@dp.message_handler(state=ExitPoll.gender)
async def process_gender(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['gender'] = message.text if message.text != 'Пропустить все вопросы' else None
        district = data['district']
        polling_station = data['polling_station']
        vote = data['vote']
        nadezhdin_vote = data.get('nadezhdin_vote')
        registration_vote = data.get('registration_vote')
        last_10_years_vote = data.get('last_10_years_vote')
        age = data.get('age')
        gender = data.get('gender')
        
        cursor.execute("INSERT INTO votes (user_id, username, vote, timestamp, district, polling_station, nadezhdin_vote, registration_vote, last_10_years_vote, age, gender) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (message.from_user.id, message.from_user.username, vote, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), district, polling_station, nadezhdin_vote, registration_vote, last_10_years_vote, age, gender))
        conn.commit()
        await message.answer("Спасибо за ваши ответы! Они записаны.")
        
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(types.KeyboardButton('Даванков'), types.KeyboardButton('Путин'))
    keyboard.add(types.KeyboardButton('Слуцкий'), types.KeyboardButton('Харитонов'))
    keyboard.add(types.KeyboardButton('Испортил бюллетень (не называть)'), types.KeyboardButton('Забрал бюллетень (не называть)'))
    keyboard.add(types.KeyboardButton('Отказ от ответа'), types.KeyboardButton('Закрыть смену'))
    await message.answer("Выберите, как человек проголосовал:", reply_markup=keyboard)
    await ExitPoll.voting.set()

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)