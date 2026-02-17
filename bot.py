# bot_oop.py
import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
import sqlite3
import os
from dotenv import load_dotenv


class RequestSystem:
    """Главный класс системы заявок: управляет БД, состояниями и логикой."""

    def __init__(self):
        # === Загрузка настроек ===
        load_dotenv()
        self.TOKEN = os.getenv("VK_TOKEN")
        self.LABORANT_IDS = set(map(int, os.getenv("LABORANT_IDS", "").split(",")))

        # === Инициализация ВК ===
        self.vk_session = vk_api.VkApi(token=self.TOKEN)
        self.longpoll = VkLongPoll(self.vk_session)
        self.vk = self.vk_session.get_api()

        # === Состояния пользователей ===
        self.user_states = {}

        # === Инициализация БД ===
        self.init_db()

    def init_db(self):
        """Создаёт таблицу заявок, если её нет."""
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

    def send_message(self, user_id, message, keyboard=None):
        """Универсальная отправка сообщения."""
        try:
            kwargs = {'user_id': user_id, 'message': message, 'random_id': 0}
            if keyboard:
                kwargs['keyboard'] = keyboard.get_keyboard()
            self.vk.messages.send(**kwargs)
        except Exception as e:
            print(f"Ошибка отправки: {e}")

    def get_user_name(self, user_id):
        """Получает имя пользователя по ID."""
        try:
            user = self.vk.users.get(user_ids=user_id)[0]
            return f"{user['first_name']} {user['last_name']}"
        except:
            return str(user_id)

    def save_request(self, user_id, topic, description, location):
        """Сохраняет новую заявку в БД."""
        username = self.get_user_name(user_id)
        conn = sqlite3.connect('requests.db')
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO requests (user_id, username, topic, description, location) VALUES (?, ?, ?, ?, ?)',
            (user_id, username, topic, description, location)
        )
        req_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return req_id

    def get_request(self, req_id):
        """Возвращает заявку по ID."""
        conn = sqlite3.connect('requests.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM requests WHERE id = ?', (req_id,))
        row = cursor.fetchone()
        conn.close()
        return row

    def update_status(self, req_id, status):
        """Обновляет статус заявки."""
        conn = sqlite3.connect('requests.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE requests SET status = ? WHERE id = ?', (status, req_id))
        conn.commit()
        conn.close()

    def notify_to_lab(self, req_id):
        """Отправляет уведомление всем лаборантам о новой заявке."""
        conn = sqlite3.connect('requests.db')
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, username, topic, description, location FROM requests WHERE id = ?", (req_id,))
        rows = cursor.fetchall()
        conn.close()
        if rows:
            for r in rows:
                lab_msg = f"🔔 Новая заявка №{req_id}\nОт: {r[1]} (id{r[0]})\nТема: {r[2]}\nОписание: {r[3]}\nКабинет: {r[4]}"
                for lab_id in self.LABORANT_IDS:
                    self.send_message(lab_id, lab_msg)
        else:
            for lab_id in self.LABORANT_IDS:
                self.send_message(lab_id, f"Заявка №{req_id} не найдена для уведомления.")

    # === КЛАВИАТУРЫ ===
    def employee_menu(self):
        kb = VkKeyboard(one_time=False)
        kb.add_button("Новая заявка", color=VkKeyboardColor.PRIMARY)
        kb.add_line()
        kb.add_button("Мои заявки", color=VkKeyboardColor.SECONDARY)
        return kb

    def topic_menu(self):
        kb = VkKeyboard(one_time=True)
        for i, t in enumerate(["Принтер", "Интернет", "Другое"]):
            if i % 2 == 0 and i > 0:
                kb.add_line()
            kb.add_button(t, color=VkKeyboardColor.SECONDARY)
        kb.add_button("Назад", color=VkKeyboardColor.SECONDARY)
        return kb

    def employee_action_kb(self, req_id):
        kb = VkKeyboard(one_time=True)
        kb.add_button(f"Готово ({req_id})", color=VkKeyboardColor.POSITIVE)
        kb.add_button(f"Отменить ({req_id})", color=VkKeyboardColor.NEGATIVE)
        return kb

    def laborant_main_menu(self):
        kb = VkKeyboard(one_time=False)
        kb.add_button("Все заявки", color=VkKeyboardColor.PRIMARY)
        kb.add_button("Активные заявки", color=VkKeyboardColor.SECONDARY)
        kb.add_line()
        kb.add_button("Новая заявка", color=VkKeyboardColor.SECONDARY)
        return kb

    def laborant_action_kb(self, req_id):
        kb = VkKeyboard(one_time=True)
        kb.add_button(f"Готово ({req_id})", color=VkKeyboardColor.POSITIVE)
        kb.add_button(f"В пути ({req_id})", color=VkKeyboardColor.SECONDARY)
        kb.add_line()
        kb.add_button(f"Отменить ({req_id})", color=VkKeyboardColor.NEGATIVE)
        kb.add_button("Назад", color=VkKeyboardColor.SECONDARY)
        return kb

    # === ОБРАБОТКА СООБЩЕНИЙ ===
    def handle_laborant(self, user_id, text):
        """Обработка сообщений от лаборанта."""
        # Обработка действий над заявкой
        if user_id in self.user_states and 'viewing_request' in self.user_states[user_id]:
            req_id = self.user_states[user_id]['viewing_request']
            if text == f"Готово ({req_id})":
                self.update_status(req_id, "✅ готово")
                req = self.get_request(req_id)
                if req:
                    self.send_message(req[1], f"✅ Ваша заявка №{req_id} выполнена!")
                username = self.get_user_name(user_id)
                for lab_id in self.LABORANT_IDS:
                    if lab_id != user_id:
                        self.send_message(lab_id, f"✅ Коллега {username} выполнил заявку №{req_id}")
                del self.user_states[user_id]
                self.send_message(user_id, "Пометил! Вы в панели лаборанта.", self.laborant_main_menu())
                return True
            elif text == f"В пути ({req_id})":
                self.update_status(req_id, "📍 в пути")
                req = self.get_request(req_id)
                if req:
                    self.send_message(req[1], f"🔧 К вам идет сотрудник по заявке №{req_id}!")
                username = self.get_user_name(user_id)
                for lab_id in self.LABORANT_IDS:
                    if lab_id != user_id:
                        self.send_message(lab_id, f"📍 Коллега {username} выехал по заявке №{req_id}")
                del self.user_states[user_id]
                self.send_message(user_id, "Пометил! Вы в панели лаборанта.", self.laborant_main_menu())
                return True
            elif text == f"Отменить ({req_id})":
                self.update_status(req_id, "❌ отменена")
                req = self.get_request(req_id)
                if req:
                    self.send_message(req[1], f"❌ Ваша заявка №{req_id} отменена.")
                username = self.get_user_name(user_id)
                for lab_id in self.LABORANT_IDS:
                    if lab_id != user_id:
                        self.send_message(lab_id, f"❌ Коллега {username} отменил заявку №{req_id}")
                del self.user_states[user_id]
                self.send_message(user_id, "Пометил! Вы в панели лаборанта.", self.laborant_main_menu())
                return True
            elif text == "Назад":
                del self.user_states[user_id]
                self.send_message(user_id, "Вы в панели лаборанта.", self.laborant_main_menu())
                return True

        # Главное меню лаборанта
        if text == "Все заявки":
            conn = sqlite3.connect('requests.db')
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, username, topic, status, description, location
                FROM requests
                ORDER BY
                    CASE status
                        WHEN "🔔 новая" THEN 1
                        WHEN "✅ готово" THEN 2
                        WHEN "❌ отменена" THEN 3
                        WHEN "📍 в пути" THEN 4
                        ELSE 5
                END,
                id DESC
                           ''')
            rows = cursor.fetchall()
            conn.close()
            if not rows:
                self.send_message(user_id, "Нет заявок.")
                return True
            msg = ""
            last_status = None
            headers = {
                "🔔 новая": "\n\n🔔🔔НОВЫЕ ЗАЯВКИ🔔🔔:\n",
                "✅ готово": "\n \n\n✅✅ВЫПОЛНЕННЫЕ✅✅:\n",
                "❌ отменена": "\n \n\n───────────────────────────\n❌─────❌ОТМЕНЕННЫЕ❌─────❌\n",
                "📍 в пути": "\n \n\n============================\n"
                            "📍======📍В ПУТИ📍======📍\n"
            }
            for r in rows:
                status = r[3]
                if status != last_status:
                    header = headers.get(status, f"\n⚪ {status}:\n")
                    msg += header
                    last_status = status
                msg += (
                    f"🧩 №{r[0]} — {r[1]}\n"
                    f"Статус: {r[3]}\n"
                    f" Тема: {r[2]}\n"
                    f"Описание: {r[4]}\n"
                    f" Кабинет: {r[5]}\n\n"
                )
            self.send_message(user_id, "📋 Все заявки (sort):"+ msg)
            return True

        elif text == "Активные заявки":
            conn = sqlite3.connect('requests.db')
            cursor = conn.cursor()
            cursor.execute("SELECT id, username, topic, status, description, location FROM requests ORDER BY id DESC")
            rows = cursor.fetchall()
            conn.close()
            msg = ""
            for r in rows:
                if r[3] == "🔔 новая":
                    msg = f" ⏳ №{r[0]} — {r[1]}\nСтатус: {r[3]}\n Тема: {r[2]}\nОписание: {r[4]}\n Кабинет: {r[5]}\n\n" + msg
            if msg:
                self.send_message(user_id, "📋 Активные заявки:\n\n " + msg)
            else:
                self.send_message(user_id, "Нет активных заявок.")
            return True

        elif text.isdigit():
            req_id = int(text)
            req = self.get_request(req_id)
            if req:
                uid, name, topic, desc, status, location = req[1], req[2], req[3], req[4], req[5], req[6]
                msg = f"📄 Заявка №{req_id}\nОт: {name} (id{uid})\nСтатус: {status}\nТема: {topic}\nОписание: {desc}\nКабинет: {location}"
                self.user_states[user_id] = {'viewing_request': req_id}
                self.send_message(user_id, msg, self.laborant_action_kb(req_id))
            else:
                self.send_message(user_id, "Заявка не найдена.")
            return True

        elif text == "Новая заявка":
            self.user_states[user_id] = {"step": "waiting_topic"}
            self.send_message(user_id, "Выберите тему проблемы:", self.topic_menu())
            return True

        elif user_id in self.user_states:
            state = self.user_states[user_id]
            if state.get("step") == "waiting_topic":
                if text in ["Принтер", "Интернет", "Другое"]:
                    self.user_states[user_id] = {"step": "waiting_description", "topic": text}
                    self.send_message(user_id, f"Тема: {text}\nОпишите проблему:")
                elif text == "Назад":
                    del self.user_states[user_id]
                    self.send_message(user_id, "Вы в панели лаборанта.", self.laborant_main_menu())
                else:
                    self.send_message(user_id, "Выберите тему из списка.", self.topic_menu())
                return True
            elif state.get("step") == "waiting_description":
                topic = state["topic"]
                self.user_states[user_id] = {"step": "waiting location", "topic": topic, "description": text}
                self.send_message(user_id, "Укажите кабинет:\n (корпус, аудитория)")
                return True
            elif state.get("step") == "waiting location":
                desc = state["description"]
                loc = text
                topic = state["topic"]
                req_id = self.save_request(user_id, topic, desc, loc)
                del self.user_states[user_id]
                self.send_message(user_id, f"✅ Заявка №{req_id} принята!", self.laborant_main_menu())
                self.notify_to_lab(req_id)
                return True

        self.send_message(user_id, "Вы в панели лаборанта.", self.laborant_main_menu())
        return True

    def handle_employee(self, user_id, text):
        """Обработка сообщений от сотрудника."""
        # Обработка кнопок Готово/Отменить
        if text.startswith("Готово (") or text.startswith("Отменить ("):
            try:
                req_id = int(text.split("(")[1].rstrip(")"))
            except (IndexError, ValueError):
                self.send_message(user_id, "Ошибка в номере заявки.", self.employee_menu())
                return True

            req = self.get_request(req_id)
            if not req or req[1] != user_id:
                self.send_message(user_id, "Заявка не найдена или не принадлежит вам.", self.employee_menu())
                return True

            if text.startswith("Готово"):
                self.update_status(req_id, "✅ готово")
                self.send_message(user_id, f"✅ Заявка №{req_id} помечена как выполненная.", self.employee_menu())
                for lab_id in self.LABORANT_IDS:
                    self.send_message(lab_id, f"Сотрудник отметил заявку №{req_id} как выполненную.")
            elif text.startswith("Отменить"):
                self.update_status(req_id, "❌ отменена")
                self.send_message(user_id, f"❌ Заявка №{req_id} отменена.", self.employee_menu())
            return True

        if text == "Новая заявка":
            self.user_states[user_id] = {"step": "waiting_topic"}
            self.send_message(user_id, "Выберите тему проблемы:", self.topic_menu())
            return True
        elif user_id in self.user_states:
            state = self.user_states[user_id]
            if state.get("step") == "waiting_topic":
                if text in ["Принтер", "Интернет", "Другое"]:
                    self.user_states[user_id] = {"step": "waiting_description", "topic": text}
                    self.send_message(user_id, f"Тема: {text}\nОпишите проблему:")
                elif text == "Назад":
                    del self.user_states[user_id]
                    self.send_message(user_id, "Выберите действие:", self.employee_menu())
                else:
                    self.send_message(user_id, "Выберите тему из списка.", self.topic_menu())
                return True
            elif state.get("step") == "waiting_description":
                topic = state["topic"]
                self.user_states[user_id] = {"step": "waiting location", "topic": topic, "description": text}
                self.send_message(user_id, "Укажите кабинет:\n (корпус, аудитория)")
                return True
            elif state.get("step") == "waiting location":
                desc = state["description"]
                topic = state["topic"]
                loc = text
                req_id = self.save_request(user_id, topic, desc, loc)
                del self.user_states[user_id]
                self.send_message(user_id, f"✅ Заявка №{req_id} принята!", self.employee_menu())
                self.notify_to_lab(req_id)
                return True

        if text == "Мои заявки":
            conn = sqlite3.connect('requests.db')
            cursor = conn.cursor()
            cursor.execute("SELECT id, username, status, topic, description, location FROM requests WHERE user_id = ? ORDER BY id DESC", (user_id,))
            rows = cursor.fetchall()
            conn.close()
            msg = ""
            for r in rows:
                if r[2] not in ("❌ отменена", "✅ готово"):
                    msg = f"🧩 №{r[0]} — {r[1]}\nСтатус:{r[2]}\n Тема: {r[3]}\nОписание: {r[4]}\n Каб.: {r[5]}\n\n" + msg
            if msg:
                self.send_message(user_id, "📋 Ваши заявки:\n" + msg, self.employee_menu())
            else:
                self.send_message(user_id, "У вас нет активных заявок.", self.employee_menu())
            return True

        elif text.isdigit():
            req_id = int(text)
            req = self.get_request(req_id)
            if req and req[1] == user_id:
                topic, desc, status, location = req[3], req[4], req[5], req[6]
                msg = f"📄 Заявка №{req_id}\nТема: {topic}\nСтатус: {status}\nОписание: {desc}\nКабинет: {location}"
                self.send_message(user_id, msg, self.employee_action_kb(req_id))
            else:
                self.send_message(user_id, "Заявка не найдена или не принадлежит вам.")
            return True

        self.send_message(user_id, "Выберите действие:", self.employee_menu())
        return True

    def run(self):
        """Основной цикл бота."""
        print("✅ Бот запущен. Ожидание сообщений...")
        try:
            for event in self.longpoll.listen():
                if event.type == VkEventType.MESSAGE_NEW and event.to_me:
                    user_id = event.user_id
                    text = event.text.strip()

                    if text.lower() == "начать":
                        if user_id in self.LABORANT_IDS:
                            self.send_message(user_id, "Привет. \nЯ помощник по заявкам, веду учет, присылаю уведомления и меняю статус заявок!")
                        else:
                            self.send_message(user_id, "Добро пожаловать!"
                                                   "\nЯ бот, который поможет вам создавать заявки и отслеживать их статус.")
                    # /back — сброс состояния
                    if text == "/back":
                        if user_id in self.user_states:
                            del self.user_states[user_id]
                        if user_id in self.LABORANT_IDS:
                            self.send_message(user_id, "Вы в панели лаборанта.", self.laborant_main_menu())
                        else:
                            self.send_message(user_id, "Выберите действие:", self.employee_menu())
                        continue
                    # Режим лаборанта или сотрудника
                    if user_id in self.LABORANT_IDS:
                        self.handle_laborant(user_id, text)
                    else:
                        self.handle_employee(user_id, text)
        except KeyboardInterrupt:
            print("\n🛑 Бот остановлен вручную.")


# === ЗАПУСК ===
if __name__ == "__main__":
    bot = RequestSystem()
    bot.run()