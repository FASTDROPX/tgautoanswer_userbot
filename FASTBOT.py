from telethon import TelegramClient, events
import asyncio
import os
import sys
import json
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import queue
import time
from datetime import datetime, timedelta

# Очередь для логов
log_queue = queue.Queue()

class UserTracker:
    def __init__(self, user_id):
        self.user_id = user_id
        self.users_file = f'users_data_{user_id}.json'
        self.tracked_users = set()
        self.pinned_message_id = None
        self.load_users()
    
    def load_users(self):
        try:
            if os.path.exists(self.users_file):
                with open(self.users_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.tracked_users = set(data.get('users', []))
                    self.pinned_message_id = data.get('pinned_message_id')
        except:
            self.tracked_users = set()
    
    def save_users(self):
        try:
            data = {
                'users': list(self.tracked_users),
                'pinned_message_id': self.pinned_message_id
            }
            with open(self.users_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log_queue.put(f"❌ Ошибка сохранения: {e}")
    
    def add_user(self, user_id, username):
        user_info = f"{user_id}:{username}"
        if user_info not in self.tracked_users:
            self.tracked_users.add(user_info)
            self.save_users()
            return True
        return False
    
    def get_users_list(self):
        usernames = []
        for user_info in self.tracked_users:
            try:
                _, username = user_info.split(':', 1)
                if username != "None":
                    usernames.append(f"@{username}")
            except:
                pass
        return usernames
    
    def log(self, message):
        log_queue.put(f"[{self.user_id}] {message}")

class AccountManager:
    def __init__(self):
        self.accounts_file = 'accounts.json'
        self.active_accounts = {}
        self.sessions_file = 'telegram_sessions.json'
        self.sessions_data = {}
        self.load_accounts()
        self.load_sessions()
    
    def load_accounts(self):
        try:
            if os.path.exists(self.accounts_file):
                with open(self.accounts_file, 'r', encoding='utf-8') as f:
                    self.active_accounts = json.load(f)
        except:
            self.active_accounts = {}
    
    def load_sessions(self):
        """Загружает данные сессий"""
        try:
            if os.path.exists(self.sessions_file):
                with open(self.sessions_file, 'r', encoding='utf-8') as f:
                    self.sessions_data = json.load(f)
        except:
            self.sessions_data = {}
    
    def save_accounts(self):
        try:
            with open(self.accounts_file, 'w', encoding='utf-8') as f:
                json.dump(self.active_accounts, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log_queue.put(f"❌ Ошибка сохранения аккаунтов: {e}")
    
    def save_sessions(self):
        """Сохраняет данные сессий"""
        try:
            with open(self.sessions_file, 'w', encoding='utf-8') as f:
                json.dump(self.sessions_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log_queue.put(f"❌ Ошибка сохранения сессий: {e}")
    
    def add_account(self, account_id, api_id, api_hash, phone, username, first_name):
        self.active_accounts[account_id] = {
            'api_id': api_id,
            'api_hash': api_hash,
            'phone': phone,
            'username': username,
            'first_name': first_name,
            'added_date': datetime.now().isoformat(),
            'is_active': True
        }
        self.save_accounts()
    
    def save_session_data(self, phone, api_id, api_hash, username, first_name, user_id):
        """Сохраняет данные сессии для автозаполнения"""
        phone_key = phone.replace('+', '')
        self.sessions_data[phone_key] = {
            'api_id': api_id,
            'api_hash': api_hash,
            'phone': phone,
            'username': username,
            'first_name': first_name,
            'user_id': user_id,
            'last_used': datetime.now().isoformat()
        }
        self.save_sessions()
    
    def get_session_data(self, phone=None):
        """Получает данные сессии для указанного номера или все сессии"""
        if phone:
            phone_key = phone.replace('+', '')
            return self.sessions_data.get(phone_key)
        return self.sessions_data
    
    def remove_account(self, account_id):
        if account_id in self.active_accounts:
            del self.active_accounts[account_id]
            self.save_accounts()
            return True
        return False
    
    def get_accounts_list(self):
        return list(self.active_accounts.keys())
    
    def get_account_info(self, account_id):
        return self.active_accounts.get(account_id)

class AutoResponder:
    """Класс для управления автоответчиком"""
    def __init__(self, user_id):
        self.user_id = user_id
        self.responses_file = f'auto_responses_{user_id}.json'
        self.user_responses = {}  # user_id -> {'last_response': timestamp, 'first_time': bool}
        self.load_responses()
        
        # Тексты ответов
        self.FIRST_RESPONSE = "Я - автоответчик! Если есть вопросы, пишите сразу."
        self.FOLLOW_UP_RESPONSE = "Скоро отвечу!"
        
        # Таймаут между ответами (20 минут)
        self.RESPONSE_TIMEOUT = 20 * 60  # 20 минут в секундах
    
    def load_responses(self):
        """Загружает историю ответов"""
        try:
            if os.path.exists(self.responses_file):
                with open(self.responses_file, 'r', encoding='utf-8') as f:
                    self.user_responses = json.load(f)
        except:
            self.user_responses = {}
    
    def save_responses(self):
        """Сохраняет историю ответов"""
        try:
            with open(self.responses_file, 'w', encoding='utf-8') as f:
                json.dump(self.user_responses, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log_queue.put(f"❌ Ошибка сохранения ответов: {e}")
    
    def should_respond(self, sender_id):
        """Проверяет, нужно ли отвечать пользователю"""
        current_time = datetime.now().isoformat()
        
        if str(sender_id) not in self.user_responses:
            # Первый раз пишет
            self.user_responses[str(sender_id)] = {
                'last_response': current_time,
                'first_time': True
            }
            self.save_responses()
            return True, self.FIRST_RESPONSE
        
        user_data = self.user_responses[str(sender_id)]
        last_response_time = datetime.fromisoformat(user_data['last_response'])
        current_time_dt = datetime.now()
        
        # Проверяем прошло ли 20 минут с последнего ответа
        time_diff = (current_time_dt - last_response_time).total_seconds()
        
        if time_diff >= self.RESPONSE_TIMEOUT:
            # Можно отвечать снова
            response_text = self.FIRST_RESPONSE if user_data.get('first_time', True) else self.FOLLOW_UP_RESPONSE
            
            self.user_responses[str(sender_id)] = {
                'last_response': current_time,
                'first_time': False
            }
            self.save_responses()
            return True, response_text
        
        # Еще не прошло 20 минут
        return False, None
    
    def log(self, message):
        log_queue.put(f"[AutoResponder {self.user_id}] {message}")

class TelegramBotUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Telegram Bot Manager")
        self.root.geometry("800x600")
        
        self.account_manager = AccountManager()
        self.bots = {}  # account_id -> (client, tracker, responder, task)
        self.running = True
        self.current_account_phone = None
        
        self.setup_ui()
        self.start_log_poller()
        self.load_saved_accounts_to_ui()
        
    def setup_ui(self):
        # Главный фрейм
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Левая панель - ввод данных
        left_frame = ttk.LabelFrame(main_frame, text="Данные для авторизации", padding=10)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 10))
        
        # Выбор сохраненного аккаунта
        ttk.Label(left_frame, text="Сохраненные аккаунты:").pack(anchor=tk.W, pady=(0, 5))
        
        self.account_combo = ttk.Combobox(left_frame, state="readonly", width=28)
        self.account_combo.pack(fill=tk.X, pady=(0, 10))
        self.account_combo.bind('<<ComboboxSelected>>', self.on_account_selected)
        
        # API данные
        ttk.Label(left_frame, text="API ID (цифры):").pack(anchor=tk.W, pady=(0, 5))
        self.api_id_entry = ttk.Entry(left_frame, width=30)
        self.api_id_entry.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(left_frame, text="API Hash (строка):").pack(anchor=tk.W, pady=(0, 5))
        self.api_hash_entry = ttk.Entry(left_frame, width=30)
        self.api_hash_entry.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(left_frame, text="Номер телефона (с +):").pack(anchor=tk.W, pady=(0, 5))
        self.phone_entry = ttk.Entry(left_frame, width=30)
        self.phone_entry.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(left_frame, text="Пароль 2FA (виден):").pack(anchor=tk.W, pady=(0, 5))
        self.password_entry = ttk.Entry(left_frame, width=30)  # Видимый пароль
        self.password_entry.pack(fill=tk.X, pady=(0, 20))
        
        # Статус
        self.status_label = ttk.Label(left_frame, text="❓ Не авторизован", foreground="blue")
        self.status_label.pack(pady=(0, 10))
        
        # Кнопки
        ttk.Button(left_frame, text="🔐 Авторизовать", 
                  command=self.authorize_account, width=25).pack(pady=5)
        
        ttk.Button(left_frame, text="🚀 Запустить бота", 
                  command=self.start_bot, width=25).pack(pady=5)
        
        ttk.Button(left_frame, text="⏹️ Остановить всех", 
                  command=self.stop_all_bots, width=25).pack(pady=5)
        
        ttk.Button(left_frame, text="🧹 Очистить", 
                  command=self.clear_fields, width=25).pack(pady=5)
        
        ttk.Button(left_frame, text="🗑️ Удалить аккаунт", 
                  command=self.delete_account, width=25).pack(pady=5)
        
        # Правая панель - логи и управление
        right_frame = ttk.LabelFrame(main_frame, text="Логи и управление", padding=10)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        # Логи
        self.log_text = scrolledtext.ScrolledText(right_frame, height=20)
        self.log_text.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Кнопки управления логами
        log_buttons = ttk.Frame(right_frame)
        log_buttons.pack(fill=tk.X)
        
        ttk.Button(log_buttons, text="Очистить логи", 
                  command=self.clear_logs).pack(side=tk.LEFT, padx=2)
        
        ttk.Button(log_buttons, text="Сохранить логи", 
                  command=self.save_logs).pack(side=tk.LEFT, padx=2)
        
        # Информация об аккаунтах
        self.accounts_text = scrolledtext.ScrolledText(right_frame, height=8)
        self.accounts_text.pack(fill=tk.BOTH, expand=True)
        self.update_accounts_display()
    
    def load_saved_accounts_to_ui(self):
        """Загружает сохраненные аккаунты в выпадающий список"""
        sessions = self.account_manager.get_session_data()
        if sessions:
            phone_numbers = []
            for phone_key, data in sessions.items():
                phone = data.get('phone', '')
                name = data.get('first_name', '')
                if phone and name:
                    display_text = f"{phone} - {name}"
                    phone_numbers.append(display_text)
            
            if phone_numbers:
                self.account_combo['values'] = phone_numbers
                log_queue.put(f"📱 Загружено {len(phone_numbers)} сохраненных аккаунтов")
    
    def on_account_selected(self, event):
        """Обработчик выбора аккаунта из списка"""
        selected = self.account_combo.get()
        if selected:
            # Извлекаем номер телефона из строки
            phone = selected.split(' - ')[0]
            self.load_account_data(phone)
    
    def load_account_data(self, phone):
        """Загружает данные аккаунта по номеру телефона"""
        session_data = self.account_manager.get_session_data(phone)
        if session_data:
            self.current_account_phone = phone
            
            # Очищаем поля
            self.api_id_entry.delete(0, tk.END)
            self.api_hash_entry.delete(0, tk.END)
            self.phone_entry.delete(0, tk.END)
            self.password_entry.delete(0, tk.END)
            
            # Заполняем поля
            self.api_id_entry.insert(0, str(session_data['api_id']))
            self.api_hash_entry.insert(0, session_data['api_hash'])
            self.phone_entry.insert(0, session_data['phone'])
            
            # Устанавливаем статус
            self.status_label.config(text="✅ Данные загружены", foreground="green")
            
            log_queue.put(f"📋 Загружены данные для {session_data['phone']}")
    
    def log(self, message):
        """Добавляет сообщение в лог"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_message = f"[{timestamp}] {message}\n"
        
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, log_message)
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
        
        print(log_message, end='')
    
    def start_log_poller(self):
        """Запускает проверку очереди логов"""
        def poll_logs():
            while self.running:
                try:
                    message = log_queue.get(timeout=0.1)
                    self.log(message)
                except queue.Empty:
                    pass
                time.sleep(0.1)
        
        thread = threading.Thread(target=poll_logs, daemon=True)
        thread.start()
    
    def show_code_dialog_sync(self):
        """Показывает диалог для ввода кода (синхронно)"""
        result = {"code": None}
        dialog_closed = threading.Event()
        
        def get_code():
            dialog = tk.Toplevel(self.root)
            dialog.title("Ввод кода")
            dialog.geometry("300x150")
            dialog.transient(self.root)
            dialog.grab_set()
            
            tk.Label(dialog, text="Введите код из Telegram:", 
                    font=("Arial", 10)).pack(pady=10)
            
            code_var = tk.StringVar()
            entry = tk.Entry(dialog, textvariable=code_var, font=("Arial", 12), width=20)
            entry.pack(pady=5)
            entry.focus_set()
            
            def submit():
                result["code"] = code_var.get()
                dialog.destroy()
                dialog_closed.set()
            
            def cancel():
                dialog.destroy()
                dialog_closed.set()
            
            tk.Button(dialog, text="OK", command=submit, width=10).pack(side=tk.LEFT, padx=20, pady=10)
            tk.Button(dialog, text="Отмена", command=cancel, width=10).pack(side=tk.RIGHT, padx=20, pady=10)
            
            dialog.protocol("WM_DELETE_WINDOW", cancel)
            dialog.wait_window()
        
        self.root.after(0, get_code)
        dialog_closed.wait()  # Ждем закрытия диалога
        return result["code"]
    
    def show_email_dialog_sync(self):
        """Показывает диалог для ввода email (синхронно)"""
        result = {"email": None}
        dialog_closed = threading.Event()
        
        def get_email():
            dialog = tk.Toplevel(self.root)
            dialog.title("Ввод email")
            dialog.geometry("350x180")
            dialog.transient(self.root)
            dialog.grab_set()
            
            tk.Label(dialog, text="Код не пришел в Telegram.\nВведите email, привязанный к аккаунту:", 
                    font=("Arial", 10), justify=tk.LEFT).pack(pady=10)
            
            email_var = tk.StringVar()
            entry = tk.Entry(dialog, textvariable=email_var, font=("Arial", 12), width=25)
            entry.pack(pady=10)
            entry.focus_set()
            
            def submit():
                result["email"] = email_var.get()
                dialog.destroy()
                dialog_closed.set()
            
            def cancel():
                dialog.destroy()
                dialog_closed.set()
            
            tk.Button(dialog, text="OK", command=submit, width=10).pack(side=tk.LEFT, padx=20, pady=10)
            tk.Button(dialog, text="Отмена", command=cancel, width=10).pack(side=tk.RIGHT, padx=20, pady=10)
            
            dialog.protocol("WM_DELETE_WINDOW", cancel)
            dialog.wait_window()
        
        self.root.after(0, get_email)
        dialog_closed.wait()
        return result["email"]
    
    def show_password_dialog_sync(self):
        """Показывает диалог для ввода пароля 2FA (синхронно)"""
        result = {"password": None}
        dialog_closed = threading.Event()
        
        def get_password():
            dialog = tk.Toplevel(self.root)
            dialog.title("Пароль 2FA")
            dialog.geometry("300x150")
            dialog.transient(self.root)
            dialog.grab_set()
            
            tk.Label(dialog, text="Введите пароль 2FA:", 
                    font=("Arial", 10)).pack(pady=10)
            
            password_var = tk.StringVar()
            entry = tk.Entry(dialog, textvariable=password_var, font=("Arial", 12), width=20, show="")
            entry.pack(pady=5)
            entry.focus_set()
            
            def submit():
                result["password"] = password_var.get()
                dialog.destroy()
                dialog_closed.set()
            
            def cancel():
                dialog.destroy()
                dialog_closed.set()
            
            tk.Button(dialog, text="OK", command=submit, width=10).pack(side=tk.LEFT, padx=20, pady=10)
            tk.Button(dialog, text="Отмена", command=cancel, width=10).pack(side=tk.RIGHT, padx=20, pady=10)
            
            dialog.protocol("WM_DELETE_WINDOW", cancel)
            dialog.wait_window()
        
        self.root.after(0, get_password)
        dialog_closed.wait()
        return result["password"]
    
    def authorize_account(self):
        """Авторизация аккаунта"""
        api_id = self.api_id_entry.get().strip()
        api_hash = self.api_hash_entry.get().strip()
        phone = self.phone_entry.get().strip()
        
        if not all([api_id, api_hash, phone]):
            messagebox.showerror("Ошибка", "Заполните все поля")
            return
        
        try:
            api_id = int(api_id)
        except ValueError:
            messagebox.showerror("Ошибка", "API ID должен быть числом")
            return
        
        self.status_label.config(text="⏳ Авторизация...", foreground="orange")
        
        # Запускаем в отдельном потоке
        threading.Thread(target=self._authorize_thread, 
                        args=(api_id, api_hash, phone), daemon=True).start()
    
    def _authorize_thread(self, api_id, api_hash, phone):
        """ИСПРАВЛЕННЫЙ поток авторизации"""
        def auth():
            try:
                session_name = f"session_{phone.replace('+', '')}"
                
                # СОЗДАЕМ НОВЫЙ ЦИКЛ СОБЫТИЙ ДЛЯ ЭТОГО ПОТОКА
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                async def auth_async():
                    client = TelegramClient(session_name, api_id, api_hash)
                    
                    await client.connect()
                    
                    if not await client.is_user_authorized():
                        log_queue.put(f"📱 Отправляю код на {phone}...")
                        
                        try:
                            sent_code = await client.send_code_request(phone)
                            log_queue.put("✅ Запрос кода отправлен")
                            
                            # Показываем диалог для ввода кода
                            log_queue.put("📝 Ожидаю ввода кода...")
                            code = self.show_code_dialog_sync()
                            
                            if not code:
                                log_queue.put("❌ Авторизация отменена")
                                self.root.after(0, lambda: self.status_label.config(
                                    text="❌ Отменено", foreground="red"))
                                return False
                            
                            try:
                                await client.sign_in(phone, code)
                                log_queue.put("✅ Авторизация успешна")
                                
                            except Exception as e:
                                error_msg = str(e)
                                if "two-step" in error_msg.lower() or "password" in error_msg.lower():
                                    # Пароль 2FA
                                    password = self.password_entry.get()
                                    if not password:
                                        log_queue.put("🔒 Требуется пароль 2FA")
                                        password = self.show_password_dialog_sync()
                                    
                                    if password:
                                        try:
                                            await client.sign_in(password=password)
                                            log_queue.put("✅ 2FA пройдена")
                                        except Exception as e2:
                                            log_queue.put(f"❌ Ошибка 2FA: {e2}")
                                            return False
                                    else:
                                        log_queue.put("❌ Требуется пароль 2FA")
                                        return False
                                else:
                                    log_queue.put(f"❌ Неверный код: {error_msg}")
                                    # Пробуем еще раз
                                    for attempt in range(2):
                                        log_queue.put(f"🔄 Попытка {attempt + 1}/2")
                                        code = self.show_code_dialog_sync()
                                        if not code:
                                            break
                                        try:
                                            await client.sign_in(phone, code)
                                            log_queue.put("✅ Авторизация успешна")
                                            break
                                        except:
                                            if attempt == 1:
                                                log_queue.put("❌ Неверный код")
                                                return False
                        
                        except Exception as e:
                            error_msg = str(e)
                            log_queue.put(f"⚠️ Ошибка отправки кода: {error_msg}")
                            
                            # Пробуем другой способ
                            try:
                                log_queue.put("🔄 Пробую другой метод отправки...")
                                sent_code = await client.send_code_request(phone, force_sms=True)
                                log_queue.put("✅ Код отправлен через SMS")
                                
                                code = self.show_code_dialog_sync()
                                if not code:
                                    return False
                                
                                await client.sign_in(phone, code)
                                log_queue.put("✅ Авторизация успешна")
                                
                            except Exception as sms_error:
                                log_queue.put(f"❌ Ошибка SMS: {sms_error}")
                                return False
                    
                    else:
                        log_queue.put("✅ Уже авторизован")
                    
                    # Получаем информацию
                    me = await client.get_me()
                    log_queue.put(f"👤 Информация: {me.first_name} (@{me.username})")
                    
                    # Сохраняем аккаунт
                    account_info = {
                        'api_id': api_id,
                        'api_hash': api_hash,
                        'phone': phone,
                        'username': me.username,
                        'first_name': me.first_name,
                        'user_id': me.id
                    }
                    
                    self.root.after(0, lambda: self._save_account_info(account_info))
                    
                    await client.disconnect()
                    return True
                
                # Запускаем асинхронную функцию
                result = loop.run_until_complete(auth_async())
                loop.close()
                
                return result
                    
            except Exception as e:
                log_queue.put(f"❌ Ошибка авторизации: {e}")
                self.root.after(0, lambda: self.status_label.config(
                    text=f"❌ Ошибка", foreground="red"))
                return False
        
        # Запускаем функцию авторизации
        auth()
    
    def _save_account_info(self, account_info):
        """Сохраняет информацию об аккаунте"""
        # Сохраняем в менеджер аккаунтов
        self.account_manager.add_account(
            account_info['user_id'],
            account_info['api_id'],
            account_info['api_hash'],
            account_info['phone'],
            account_info['username'],
            account_info['first_name']
        )
        
        # Сохраняем в сессии для автозаполнения
        self.account_manager.save_session_data(
            account_info['phone'],
            account_info['api_id'],
            account_info['api_hash'],
            account_info['username'],
            account_info['first_name'],
            account_info['user_id']
        )
        
        # Обновляем список аккаунтов
        sessions = self.account_manager.get_session_data()
        if sessions:
            phone_numbers = []
            for phone_key, data in sessions.items():
                phone = data.get('phone', '')
                name = data.get('first_name', '')
                if phone and name:
                    display_text = f"{phone} - {name}"
                    phone_numbers.append(display_text)
            
            if phone_numbers:
                self.account_combo['values'] = phone_numbers
        
        # Устанавливаем текущий выбранный аккаунт
        display_text = f"{account_info['phone']} - {account_info['first_name']}"
        self.account_combo.set(display_text)
        self.current_account_phone = account_info['phone']
        
        self.status_label.config(text="✅ Авторизован", foreground="green")
        self.update_accounts_display()
    
    def delete_account(self):
        """Удаляет сохраненный аккаунт"""
        phone = self.phone_entry.get().strip()
        if not phone:
            messagebox.showwarning("Предупреждение", "Введите номер телефона для удаления")
            return
        
        confirm = messagebox.askyesno("Подтверждение", 
                                     f"Удалить аккаунт {phone} из сохраненных?")
        if not confirm:
            return
        
        # Находим user_id для этого телефона
        session_data = self.account_manager.get_session_data(phone)
        if session_data and 'user_id' in session_data:
            user_id = session_data['user_id']
            
            # Удаляем из активных аккаунтов
            self.account_manager.remove_account(str(user_id))
            
            # Удаляем из сессий
            phone_key = phone.replace('+', '')
            if phone_key in self.account_manager.sessions_data:
                del self.account_manager.sessions_data[phone_key]
                self.account_manager.save_sessions()
            
            # Удаляем файл сессии
            session_file = f"session_{phone_key}.session"
            if os.path.exists(session_file):
                try:
                    os.remove(session_file)
                except:
                    pass
            
            log_queue.put(f"🗑️ Аккаунт {phone} удален")
            
            # Обновляем UI
            self.clear_fields()
            sessions = self.account_manager.get_session_data()
            if sessions:
                phone_numbers = []
                for phone_key, data in sessions.items():
                    phone = data.get('phone', '')
                    name = data.get('first_name', '')
                    if phone and name:
                        display_text = f"{phone} - {name}"
                        phone_numbers.append(display_text)
                
                if phone_numbers:
                    self.account_combo['values'] = phone_numbers
            else:
                self.account_combo['values'] = []
            
            self.update_accounts_display()
            
            messagebox.showinfo("Успех", f"Аккаунт {phone} удален")
        else:
            messagebox.showerror("Ошибка", "Аккаунт не найден")
    
    def update_accounts_display(self):
        """Обновляет отображение аккаунтов"""
        self.accounts_text.config(state=tk.NORMAL)
        self.accounts_text.delete(1.0, tk.END)
        
        if self.account_manager.active_accounts:
            self.accounts_text.insert(tk.END, "📱 Авторизованные аккаунты:\n\n")
            for account_id, info in self.account_manager.active_accounts.items():
                status = "🚀 Запущен" if account_id in self.bots else "⏸️ Остановлен"
                self.accounts_text.insert(tk.END, 
                    f"• {info['phone']} - {info['first_name']} ({status})\n")
        else:
            self.accounts_text.insert(tk.END, "📭 Нет авторизованных аккаунтов\n")
        
        # Добавляем информацию о сохраненных сессиях
        sessions = self.account_manager.get_session_data()
        if sessions:
            self.accounts_text.insert(tk.END, "\n💾 Сохраненные сессии:\n")
            for phone_key, data in sessions.items():
                phone = data.get('phone', '')
                name = data.get('first_name', '')
                if phone and name:
                    self.accounts_text.insert(tk.END, f"• {phone} - {name}\n")
        
        self.accounts_text.config(state=tk.DISABLED)
    
    def start_bot(self):
        """Запускает бота"""
        api_id = self.api_id_entry.get().strip()
        api_hash = self.api_hash_entry.get().strip()
        phone = self.phone_entry.get().strip()
        
        if not all([api_id, api_hash, phone]):
            messagebox.showerror("Ошибка", "Сначала авторизуйте аккаунт")
            return
        
        # Находим аккаунт
        account_id = None
        for acc_id, info in self.account_manager.active_accounts.items():
            if info['phone'] == phone:
                account_id = acc_id
                break
        
        if not account_id:
            messagebox.showerror("Ошибка", "Аккаунт не найден. Сначала авторизуйтесь.")
            return
        
        if account_id in self.bots:
            messagebox.showinfo("Информация", "Бот уже запущен")
            return
        
        log_queue.put(f"🚀 Запускаю бота для {phone}")
        
        threading.Thread(target=self._start_bot_thread, 
                        args=(account_id,), daemon=True).start()
    
    def _start_bot_thread(self, account_id):
        """Поток запуска бота"""
        async def run_bot():
            account_info = self.account_manager.get_account_info(account_id)
            if not account_info:
                log_queue.put(f"❌ Аккаунт не найден")
                return
            
            session_name = f"session_{account_info['phone'].replace('+', '')}"
            client = TelegramClient(session_name, 
                                   account_info['api_id'], 
                                   account_info['api_hash'])
            
            tracker = UserTracker(account_id)
            responder = AutoResponder(account_id)
            
            try:
                await client.start()
                log_queue.put(f"✅ Бот запущен для {account_info['phone']}")
                
                # Обновляем закрепленное сообщение
                await self.create_pinned_message(client, tracker, account_id)
                
                # Регистрируем обработчики
                client.add_event_handler(
                    lambda e: self.handle_incoming_message(e, client, tracker, responder, account_id),
                    events.NewMessage(incoming=True)
                )
                
                client.add_event_handler(
                    lambda e: self.handle_outgoing_message(e, client, account_id),
                    events.NewMessage(outgoing=True)
                )
                
                # Сохраняем бота
                self.bots[account_id] = (client, tracker, responder, asyncio.current_task())
                self.root.after(0, self.update_accounts_display)
                
                await client.run_until_disconnected()
                
            except Exception as e:
                log_queue.put(f"❌ Ошибка бота: {e}")
            finally:
                if account_id in self.bots:
                    del self.bots[account_id]
                    self.root.after(0, self.update_accounts_display)
                    log_queue.put(f"⏹️ Бот остановлен")
        
        asyncio.run(run_bot())
    
    async def create_pinned_message(self, client, tracker, account_id):
        """Создает закрепленное сообщение"""
        try:
            me = await client.get_entity('me')
            
            users = tracker.get_users_list()
            
            if not users:
                message_text = "📋 **Вам писали пользователи:**\n\n💬 *Пока никто не писал*"
            else:
                users_list = '\n'.join([f"• {user}" for user in users])
                message_text = f"📋 **Вам писали пользователи:**\n\n{users_list}"
            
            if tracker.pinned_message_id:
                try:
                    await client.edit_message(me, tracker.pinned_message_id, message_text, parse_mode='md')
                    tracker.log("Обновлено закрепленное сообщение")
                    return tracker.pinned_message_id
                except:
                    pass
            
            message = await client.send_message(me, message_text, parse_mode='md')
            
            try:
                await client.pin_message(me, message.id, notify=False)
                tracker.log("Сообщение закреплено")
            except:
                tracker.log("Сообщение отправлено")
            
            tracker.pinned_message_id = message.id
            tracker.save_users()
            
            return message.id
            
        except Exception as e:
            tracker.log(f"Ошибка: {e}")
            return None
    
    async def handle_incoming_message(self, event, client, tracker, responder, account_id):
        """Обработчик входящих сообщений - автоответчик"""
        try:
            # Пропускаем не личные сообщения и свои сообщения
            if not event.is_private or event.out:
                return
            
            sender = await event.get_sender()
            
            # Добавляем пользователя в трекер
            if tracker.add_user(sender.id, sender.username or "None"):
                username = f"@{sender.username}" if sender.username else f"ID:{sender.id}"
                tracker.log(f"Новый пользователь: {username}")
                await self.create_pinned_message(client, tracker, account_id)
            
            # Проверяем, нужно ли отвечать
            should_respond, response_text = responder.should_respond(sender.id)
            
            if should_respond and response_text:
                # Отправляем ответ
                await client.send_message(
                    sender.id,
                    response_text
                )
                
                # Логируем
                username = f"@{sender.username}" if sender.username else f"ID:{sender.id}"
                responder.log(f"Отправлен автоответ {username}: {response_text}")
            
        except Exception as e:
            tracker.log(f"Ошибка автоответчика: {e}")
    
    async def handle_outgoing_message(self, event, client, account_id):
        """Обработчик отправки сообщений - показывает статусы для разных типов файлов"""
        try:
            message = event.message
            
            # Пропускаем текстовые сообщения без медиа
            if not message.media:
                return
            
            # Получаем чат
            chat = await event.get_chat()
            
            # Определяем тип файла и выбираем текст статуса
            status_text = self._get_status_text_for_media(message)
            
            # Отправляем статус жирным шрифтом
            status_msg = await client.send_message(
                chat.id, 
                f"**{status_text}**", 
                parse_mode='md'
            )
            
            # Удаляем статус через 3 секунды
            await asyncio.sleep(3)
            await status_msg.delete()
            
            # Логируем
            tracker = UserTracker(account_id)
            tracker.log(f"Отправлен статус: {status_text}")
            
        except Exception as e:
            tracker = UserTracker(account_id)
            tracker.log(f"Ошибка отправки статуса: {e}")
    
    def _get_status_text_for_media(self, message):
        """Определяет тип медиа и возвращает соответствующий текст статуса"""
        # Фото
        if message.photo:
            return "🖼️ Отправляю фото, подожди⏩"
        
        # Видео
        elif message.video:
            return "🎥 Отправляю видео, подожди⏩"
        
        # Аудио/музыка
        elif message.audio:
            # Проверяем, голосовое сообщение или музыка
            if hasattr(message.audio, 'voice') and message.audio.voice:
                return "🎵 Отправляю голосовое, подожди⏩"
            else:
                return "🎶 Отправляю музыку, подожди⏩"
        
        # Голосовое сообщение
        elif message.voice:
            return "🎵 Отправляю голосовое, подожди⏩"
        
        # Документ (файл)
        elif message.document:
            mime_type = message.document.mime_type or ""
            
            # Изображения
            if 'image' in mime_type:
                return "🖼️ Отправляю изображение, подожди⏩"
            
            # Видео файлы
            elif 'video' in mime_type:
                return "🎥 Отправляю видео файл, подожди⏩"
            
            # Аудио файлы
            elif 'audio' in mime_type:
                return "🎶 Отправляю аудио файл, подожди⏩"
            
            # PDF и документы
            elif 'pdf' in mime_type or 'document' in mime_type:
                return "📄 Отправляю документ, подожди⏩"
            
            # Архивы
            elif 'zip' in mime_type or 'rar' in mime_type or 'tar' in mime_type or '7z' in mime_type:
                return "📦 Отправляю архив, подожди⏩"
            
            # Остальные файлы
            else:
                return "📎 Отправляю файл, подожди⏩"
        
        # Стикер
        elif message.sticker:
            return "🩷 Отправляю стикер, подожди⏩"
        
        # GIF
        elif hasattr(message, 'gif') and message.gif:
            return "🎬 Отправляю GIF, подожди⏩"
        
        # Кружочек (видеосообщение/видеозаметка)
        elif hasattr(message, 'video_note') and message.video_note:
            return "⭕ Отправляю видеосообщение, подожди⏩"
        
        # Контакт
        elif message.contact:
            return "👤 Отправляю контакт, подожди⏩"
        
        # Локация
        elif message.geo:
            return "📍 Отправляю локацию, подожди⏩"
        
        # Остальные медиа
        else:
            return "📤 Отправляю медиа, подожди⏩"
    
    def stop_all_bots(self):
        """Останавливает всех ботов"""
        if not self.bots:
            messagebox.showinfo("Информация", "Нет запущенных ботов")
            return
        
        for account_id, (client, tracker, responder, task) in list(self.bots.items()):
            async def stop(client, task):
                await client.disconnect()
                if not task.done():
                    task.cancel()
            
            threading.Thread(target=lambda: asyncio.run(stop(client, task)), 
                           daemon=True).start()
        
        log_queue.put("⏹️ Остановка всех ботов...")
    
    def clear_fields(self):
        """Очищает поля ввода"""
        self.api_id_entry.delete(0, tk.END)
        self.api_hash_entry.delete(0, tk.END)
        self.phone_entry.delete(0, tk.END)
        self.password_entry.delete(0, tk.END)
        self.account_combo.set('')
        self.current_account_phone = None
        self.status_label.config(text="❓ Не авторизован", foreground="blue")
    
    def clear_logs(self):
        """Очищает логи"""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)
    
    def save_logs(self):
        """Сохраняет логи"""
        filename = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfile=f"logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        )
        
        if filename:
            logs = self.log_text.get(1.0, tk.END)
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(logs)
                messagebox.showinfo("Успех", f"Логи сохранены в {filename}")
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось сохранить: {e}")
    
    def run(self):
        """Запускает UI"""
        self.root.mainloop()
    
    def __del__(self):
        self.running = False
        for account_id, (client, tracker, responder, task) in self.bots.items():
            try:
                asyncio.run(client.disconnect())
                if not task.done():
                    task.cancel()
            except:
                pass

# Запуск
if __name__ == "__main__":
    app = TelegramBotUI()
    
    def load_saved_accounts():
        time.sleep(1)
        log_queue.put("🚀 Telegram Bot Manager запущен")
        log_queue.put("📋 Функционал:")
        log_queue.put("• Автоответчик: 1-й раз - 'Я - автоответчик! Если есть вопросы, пишите сразу.'")
        log_queue.put("• Автоответчик: повторно - 'Скоро отвечу!' (1 раз в 20 минут)")
        log_queue.put("• Статусы отправки файлов (удаляются через 3 секунды)")
        log_queue.put("• Отслеживание новых пользователей")
        log_queue.put("• Обновление закрепленного сообщения")
        
        # Проверяем сохраненные аккаунты
        sessions = app.account_manager.get_session_data()
        if sessions:
            log_queue.put(f"📱 Загружено {len(sessions)} сохраненных аккаунтов")
            log_queue.put("📋 Выберите аккаунт из выпадающего списка для автозаполнения")
        else:
            log_queue.put("📭 Нет сохраненных аккаунтов. Начните с авторизации.")
        
        # Проверяем авторизованные аккаунты
        if app.account_manager.active_accounts:
            log_queue.put(f"✅ Авторизовано {len(app.account_manager.active_accounts)} аккаунтов")
    
    threading.Thread(target=load_saved_accounts, daemon=True).start()
    
    app.run()