# bot.py
import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
import sqlite3
import os
from dotenv import load_dotenv

# === Настройки ===
load_dotenv()
TOKEN = os.getenv("VK_TOKEN")
LABORANT_IDS = set(map(int, os.getenv("LABORANT_IDS", "").split(",")))

# Состояния: {user_id: {"step": "...", "data": {...}}}
user_states = {}

# === Инициализация ВК ===
vk_session = vk_api.VkApi(token=TOKEN)
longpoll = VkLongPoll(vk_session)
vk = vk_session.get_api()

# === БД ===
def init_db():
    conn = sqlite3.connect('requests.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            topic TEXT,
            description TEXT,
            status TEXT DEFAULT "🔔 новая",
            location TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# === Вспомогательные функции ===
def send_message(user_id, message, keyboard=None):
    try:
        kwargs = {'user_id': user_id, 'message': message, 'random_id': 0}
        if keyboard:
            kwargs['keyboard'] = keyboard.get_keyboard()
        vk.messages.send(**kwargs)
    except Exception as e:
        print(f"Ошибка отправки: {e}")
def get_user_name(user_id):
    try:
        user = vk.users.get(user_ids=user_id)[0]
        return f"{user['first_name']} {user['last_name']}"
    except:
        return str(user_id)
def save_request(user_id, topic, description, location):
    username = get_user_name(user_id)
    conn = sqlite3.connect('requests.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO requests (user_id, username, topic, description, location) VALUES (?, ?, ?, ?, ?)',
                   (user_id, username, topic, description, location))
    req_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return req_id
def get_request(req_id):
    conn = sqlite3.connect('requests.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM requests WHERE id = ?', (req_id,))
    row = cursor.fetchone()
    conn.close()
    return row
def update_status(req_id, status):
    conn = sqlite3.connect('requests.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE requests SET status = ? WHERE id = ?', (status, req_id))
    conn.commit()
    conn.close()
def notify_to_lab(req_id):
    conn = sqlite3.connect('requests.db')
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username, topic, description, location FROM requests WHERE id = ?", (req_id,))
    rows = cursor.fetchall()
    conn.close()
    if rows:
        msg = ""
        for r in rows:
            lab_msg = f"🔔 Новая заявка №{req_id}\nОт: {r[1]} (id{r[0]})\nТема: {r[2]}\nОписание: {r[3]}\nКабинет: {r[4]}"
        for lab_id in LABORANT_IDS:
            send_message(lab_id, lab_msg)
    else:
        for lab_id in LABORANT_IDS:
            send_message(lab_id, f"Заявка №{req_id} не найдена для уведомления.")
# === Клавиатуры ===
def employee_menu():
    kb = VkKeyboard(one_time=False)
    kb.add_button("Новая заявка", color=VkKeyboardColor.PRIMARY)
    kb.add_line()
    kb.add_button("Мои заявки", color=VkKeyboardColor.SECONDARY)
    return kb
def topic_menu():
    kb = VkKeyboard(one_time=True)
    for i, t in enumerate(["Принтер", "Интернет", "Другое"]):
        if i % 2 == 0 and i > 0:
            kb.add_line()
        kb.add_button(t, color=VkKeyboardColor.SECONDARY)
    kb.add_button("Назад", color=VkKeyboardColor.SECONDARY)
    return kb
def employee_action_kb(req_id):
    kb = VkKeyboard(one_time=True)
    kb.add_button(f"Готово ({req_id})", color=VkKeyboardColor.POSITIVE)
    kb.add_button(f"Отменить ({req_id})", color=VkKeyboardColor.NEGATIVE)
    return kb
def laborant_main_menu():
    kb = VkKeyboard(one_time=False)
    kb.add_button("Все заявки", color=VkKeyboardColor.PRIMARY)
    kb.add_button("Активные заявки", color=VkKeyboardColor.SECONDARY)
    kb.add_line()
    kb.add_button("Новая заявка", color=VkKeyboardColor.SECONDARY)
    return kb

def laborant_action_kb(req_id):
    kb = VkKeyboard(one_time=True)
    kb.add_button(f"Готово ({req_id})", color=VkKeyboardColor.POSITIVE)
    kb.add_button(f"В пути ({req_id})", color=VkKeyboardColor.SECONDARY)
    kb.add_line()
    kb.add_button(f"Отменить ({req_id})", color=VkKeyboardColor.NEGATIVE)
    kb.add_button("Назад", color=VkKeyboardColor.SECONDARY)
    return kb

# === Основной цикл ===
print("✅ Бот запущен. Ожидание сообщений...")
for event in longpoll.listen():
    if event.type == VkEventType.MESSAGE_NEW and event.to_me:
        user_id = event.user_id
        text = event.text.strip()

        # Обработка /back — сброс состояния
        if text == "/back":
            if user_id in user_states:
                del user_states[user_id]
            if user_id == LABORANT_IDS:
                send_message(user_id, "Вы в панели лаборанта.", laborant_main_menu())
            else:
                send_message(user_id, "Выберите действие:", employee_menu())
            continue

        # === РЕЖИМ ЛАБОРАНТА ===
        #if user_id == 2:
        if user_id in LABORANT_IDS:
            # Обработка действий над заявкой
            if user_id in user_states and 'viewing_request' in user_states[user_id]:
                req_id = user_states[user_id]['viewing_request']
                #🔔💊✅📍⚙️⏳
                if text == f"Готово ({req_id})":
                    update_status(req_id, "✅ готово")
                    req = get_request(req_id)
                    if req:
                        send_message(req[1], f"✅ Ваша заявка №{req_id} выполнена!")

                    username = get_user_name(user_id)
                    for lab_id in LABORANT_IDS:
                        if lab_id != user_id:  # кроме меня
                            send_message(lab_id, f"✅ Коллега {get_user_name(user_id)} выполнил заявку №{req_id}")

                    del user_states[user_id]
                    send_message(user_id, "Вы в панели лаборанта.", laborant_main_menu())
                    continue
                elif text == f"В пути ({req_id})":
                    update_status(req_id, "️📍 в пути")
                    req = get_request(req_id)
                    if req:
                        send_message(req[1], f"🔧 Лаборант в пути к вам по заявке №{req_id}.")
                    #уведомление всех лаборантов
                    for lab_id in LABORANT_IDS:
                        if lab_id != user_id:  # кроме меня
                            send_message(lab_id, f"📍 Коллега {get_user_name(user_id)} выехал по заявке №{req_id}")
                    del user_states[user_id]
                    send_message(user_id, "Вы в панели лаборанта.", laborant_main_menu())
                    continue
                elif text == f"Отменить ({req_id})":
                    update_status(req_id, "️️❌ отменена")
                    req = get_request(req_id)
                    if req:
                        send_message(req[1], f"❌ Ваша заявка №{req_id} отменена.")
                    for lab_id in LABORANT_IDS:
                        if lab_id != user_id:  # кроме меня
                            send_message(lab_id, f"❌ Коллега {get_user_name(user_id)} отменил заявку №{req_id}")
                    del user_states[user_id]
                    send_message(user_id, "Вы в панели лаборанта.", laborant_main_menu())
                    continue
                elif text == "Назад":
                    del user_states[user_id]
                    send_message(user_id, "Вы в панели лаборанта.", laborant_main_menu())
                    continue

            # Главное меню лаборанта
            if text == "Все заявки":
                conn = sqlite3.connect('requests.db')
                cursor = conn.cursor()
                cursor.execute("SELECT id, username, topic, status, description, location FROM requests ORDER BY id DESC")
                rows = cursor.fetchall()
                conn.close()
                if rows:
                    msg = ""
                    for r in rows:
                        msg = (f"🧩 №{r[0]} — {r[1]}"
                               f"\nСтатус: {r[3]}"
                               f"\n Тема: {r[2]}"
                               f"\nОписание: {r[4]}"
                               f"\n Кабинет: {r[5]}\n\n") + msg
                    msg = "📋 Все заявки:\n" + msg
                    send_message(user_id, msg)
                else:
                    send_message(user_id, "Нет заявок.")

            elif text == "Активные заявки":
                conn = sqlite3.connect('requests.db')
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, username, topic, status, description, location FROM requests ORDER BY id DESC")
                rows = cursor.fetchall()
                conn.close()
                msg = ""
                if rows:
                    for r in rows:
                        if r[3] == "🔔 новая":
                            msg = (f" ⏳ №{r[0]} — {r[1]}"
                                   f"\nСтатус: {r[3]} "
                                   f"\n Тема: {r[2]}"
                                   f"\nОписание: {r[4]}"
                                   f"\n Кабинет: {r[5]}\n\n") + msg
                    msg = "📋 Активные заявки:\n\n " + msg
                    send_message(user_id, msg)
                else:
                    send_message(user_id, "Нет заявок.")
                continue

            elif text.isdigit():
                req_id = int(text)
                req = get_request(req_id)
                # Вывод заявки по id
                if req:
                    # Показываем информацию
                    uid = req[1]
                    name = req[2]
                    topic = req[3]
                    desc = req[4]
                    status = req[5]
                    location = req[6]
                    msg = f"📄 Заявка №{req_id}\nОт: {name} (id{user_id})\nТема: {topic}\nСтатус: {status}\nОписание: {desc}\nКаб:{location}"
                    user_states[user_id] = {'viewing_request': req_id}
                    send_message(user_id, msg, laborant_action_kb(req_id))
                else:
                    send_message(user_id, "Заявка не найдена.")



            elif text == "Новая заявка":
                user_states[user_id] = {"step": "waiting_topic"}
                send_message(user_id, "Выберите тему проблемы:", topic_menu())
            elif user_id in user_states and user_states[user_id].get("step") == "waiting_topic":
                if text in ["Принтер", "Интернет", "Другое"]:
                    user_states[user_id] = {"step": "waiting_description", "topic": text}
                    send_message(user_id, f"Тема: {text}\nОпишите проблему:")
                elif text == "Назад":
                    del user_states[user_id]
                    send_message(user_id, "Вы в панели лаборанта.", laborant_main_menu())
                    continue
                else:
                    send_message(user_id, "Выберите тему из списка.", topic_menu())
            elif user_id in user_states and user_states[user_id].get("step") == "waiting_description":
                topic = user_states[user_id]["topic"]
                user_states[user_id] = {"step": "waiting location", "topic": topic, "description": text}
                send_message(user_id,"Укажите кабинет:\n (корпус, аудитория)")
            elif user_id in user_states and user_states[user_id].get("step") == "waiting location":
                desc = user_states[user_id]["description"]
                loc = text
                req_id = save_request(user_id, topic, desc, loc)
                del user_states[user_id]
                send_message(user_id, f"✅ Заявка №{req_id} принята!", laborant_main_menu())

                # Уведомление лаборанту
                notify_to_lab(req_id)
            else:
                send_message(user_id, "Вы в панели лаборанта.", laborant_main_menu())


##==##==##==##==##==##==##==##==##==##==##==##==##==##==##==##==##==##
##==##==##==##==##==##==##==##==##==##==##==##==##==##==##==##==##==##
##==##==##==##==##==##==##==##==##==##==##==##==##==##==##==##==##==##
        # === РЕЖИМ СОТРУДНИКА ===
        else:
            # Обработка действий по кнопкам
            if text.startswith("Готово (") or text.startswith("Отменить ("):
                # Извлекаем ID из текста: "Готово (5)" → "5"
                try:
                    req_id = int(text.split("(")[1].rstrip(")"))
                except (IndexError, ValueError):
                    send_message(user_id, "Ошибка в номере заявки.", employee_menu())
                    continue

                req = get_request(req_id)
                if not req or req[1] != user_id:
                    send_message(user_id, "Заявка не найдена или не принадлежит вам.", employee_menu())
                    continue

                if text.startswith("Готово"):
                    update_status(req_id, "✅ готово")
                    send_message(user_id, f"✅ Заявка №{req_id} помечена как выполненная.", employee_menu())
                    # Уведомление лаборанту (опционально)
                    for lab_id in LABORANT_IDS:
                        send_message(lab_id,f"Сотрудник отметил заявку №{req_id} как выполненную.")

                elif text.startswith("Отменить"):
                    update_status(req_id, "❌ отменена")
                    send_message(user_id, f"❌ Заявка №{req_id} отменена.", employee_menu())

                continue
            if text == "Новая заявка":
                user_states[user_id] = {"step": "waiting_topic"}
                send_message(user_id, "Выберите тему проблемы:", topic_menu())
            elif user_id in user_states and user_states[user_id].get("step") == "waiting_topic":
                if text in ["Принтер", "Интернет", "Другое"]:
                    user_states[user_id] = {"step": "waiting_description", "topic": text}
                    send_message(user_id, f"Тема: {text}\nОпишите проблему:")
                elif text == "Назад":
                    del user_states[user_id]
                    send_message(user_id, "Выберите действие:", employee_menu())
                    continue
                else:
                    send_message(user_id, "Выберите тему из списка.", topic_menu())
            elif user_id in user_states and user_states[user_id].get("step") == "waiting_description":
                topic = user_states[user_id]["topic"]
                user_states[user_id] = {"step": "waiting location", "topic": topic, "description": text}
                send_message(user_id, "Укажите кабинет:\n (корпус, аудитория)")
            elif user_id in user_states and user_states[user_id].get("step") == "waiting location":
                desc = user_states[user_id]["description"]
                loc = text
                req_id = save_request(user_id, topic, desc, loc)
                del user_states[user_id]
                send_message(user_id, f"✅ Заявка №{req_id} принята!", employee_menu())

                # Уведомление лаборанту
                notify_to_lab(req_id)
            elif text == "Мои заявки":
                conn = sqlite3.connect('requests.db')
                cursor = conn.cursor()
                cursor.execute("SELECT id, username, status, topic, description, location FROM requests WHERE user_id = ? ORDER BY id DESC", (user_id,))
                rows = cursor.fetchall()
                conn.close()
                if rows:
                    msg = ""
                    for r in rows:
                        if r[2] != "❌ отменена" and r[2] != "✅ готово":
                            msg = (f"🧩 №{r[0]} — {r[1]}"
                                   f"\nСтатус:{r[2]}"
                                   f"\n Тема: {r[3]}"
                                   f"\nОписание: {r[4]}"
                                   f"\n Каб.: {r[5]}\n\n") + msg
                    msg = "📋 Ваши заявки:\n" + msg
                    send_message(user_id, msg, employee_menu())
                else:
                    send_message(user_id, "У вас нет активных заявок.", employee_menu())

            elif text.isdigit():
                req_id = int(text)
                req = get_request(req_id)
                if req and req[1] == user_id:
                    # Показываем заявку + кнопки
                    topic = req[3]
                    desc = req[4]
                    status = req[5]
                    location = req[6]
                    msg = f"📄 Заявка №{req_id}\nТема: {topic}\nСтатус: {status}\nОписание: {desc}"\
                          f"\nКабинет: {location}"
                    send_message(user_id, msg, employee_action_kb(req_id))
                else:
                    send_message(user_id, "Заявка не найдена или не принадлежит вам.")
            else:
                send_message(user_id, "Выберите действие:", employee_menu())

"""
try:
    for event in longpoll.listen():
        if event.type == VkEventType.MESSAGE_NEW and event.to_me:
            # ВЕСЬ твой существующий код обработки сообщений
            # (режим лаборанта, сотрудника, /back и т.д.)

except KeyboardInterrupt:
    print("\n🛑 Бот остановлен вручную.")
except Exception as e:
    print(f"❌ Критическая ошибка: {e}")
"""