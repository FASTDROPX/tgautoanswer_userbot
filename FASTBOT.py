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
    
    def update_account_api(self, account_id, api_id, api_hash):
        """Обновляет API данные для конкретного аккаунта"""
        if account_id in self.active_accounts:
            self.active_accounts[account_id]['api_id'] = api_id
            self.active_accounts[account_id]['api_hash'] = api_hash
            self.save_accounts()
            return True
        return False
    
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
    
    def clear_all_data(self):
        """Очищает все данные аккаунтов"""
        self.active_accounts = {}
        self.sessions_data = {}
        self.save_accounts()
        self.save_sessions()
        return True
    
    def get_accounts_list(self):
        return list(self.active_accounts.keys())
    
    def get_account_info(self, account_id):
        return self.active_accounts.get(account_id)
    
    def get_account_by_phone(self, phone):
        for account_id, info in self.active_accounts.items():
            if info['phone'] == phone:
                return account_id, info
        return None, None
    
    def get_next_account_number(self):
        """Получает следующий номер аккаунта по порядку"""
        return len(self.active_accounts) + 1
    
    def can_add_more_accounts(self):
        """Проверяет, можно ли добавить еще аккаунтов (максимум 10)"""
        return len(self.active_accounts) < 10

class AutoResponder:
    """Класс для управления автоответчиком"""
    def __init__(self, user_id):
        self.user_id = user_id
        self.responses_file = f'auto_responses_{user_id}.json'
        self.settings_file = f'auto_responder_settings_{user_id}.json'
        self.user_responses = {}  # user_id -> {'last_response': timestamp, 'first_time': bool}
        self.settings = self.load_settings()
        self.load_responses()
        
        # Настройки по умолчанию
        if 'first_response' not in self.settings:
            self.settings['first_response'] = "Я - автоответчик! Если есть вопросы, пишите сразу."
        if 'follow_up_response' not in self.settings:
            self.settings['follow_up_response'] = "Скоро отвечу!"
        if 'response_timeout' not in self.settings:
            self.settings['response_timeout'] = 20 * 60  # 20 минут в секундах
        if 'enabled' not in self.settings:
            self.settings['enabled'] = True
        if 'send_to_new_users' not in self.settings:
            self.settings['send_to_new_users'] = True
        if 'send_to_existing_users' not in self.settings:
            self.settings['send_to_existing_users'] = True
        if 'ignore_after_my_message' not in self.settings:
            self.settings['ignore_after_my_message'] = True  # НОВАЯ НАСТРОЙКА: игнорировать после моего сообщения
        if 'ignore_timeout' not in self.settings:
            self.settings['ignore_timeout'] = 10 * 60  # 10 минут в секундах
        # Настройки эффекта сообщений
        if 'message_effect_enabled' not in self.settings:
            self.settings['message_effect_enabled'] = False
        if 'message_effect_speed' not in self.settings:
            self.settings['message_effect_speed'] = 75  # ms
        if 'message_effect_initial_char' not in self.settings:
            self.settings['message_effect_initial_char'] = "█"
        
        # Словарь для отслеживания последних сообщений в диалогах
        self.last_message_times = {}  # chat_id -> {'last_outgoing': timestamp, 'last_incoming': timestamp}
    
    def load_settings(self):
        """Загружает настройки автоответчика"""
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except:
            pass
        return {}
    
    def save_settings(self):
        """Сохраняет настройки автоответчика"""
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log_queue.put(f"❌ Ошибка сохранения настроек: {e}")
    
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
    
    def should_respond(self, sender_id, chat_id=None):
        """Проверяет, нужно ли отвечать пользователю"""
        if not self.settings.get('enabled', True):
            return False, None
        
        current_time = datetime.now().isoformat()
        
        is_new_user = str(sender_id) not in self.user_responses
        
        # Проверяем настройки отправки
        if is_new_user and not self.settings.get('send_to_new_users', True):
            return False, None
        if not is_new_user and not self.settings.get('send_to_existing_users', True):
            return False, None
        
        # НОВАЯ ПРОВЕРКА: игнорировать если я написал последним
        if self.settings.get('ignore_after_my_message', True) and chat_id:
            if chat_id in self.last_message_times:
                last_times = self.last_message_times[chat_id]
                if 'last_outgoing' in last_times and 'last_incoming' in last_times:
                    # Если я написал позже чем мне написали
                    if last_times['last_outgoing'] > last_times['last_incoming']:
                        # Проверяем, прошло ли достаточно времени
                        last_outgoing_time = datetime.fromisoformat(last_times['last_outgoing'])
                        current_time_dt = datetime.now()
                        time_diff = (current_time_dt - last_outgoing_time).total_seconds()
                        
                        if time_diff < self.settings.get('ignore_timeout', 10 * 60):
                            # Еще не прошло время игнорирования
                            return False, None
        
        if is_new_user:
            # Первый раз пишет
            self.user_responses[str(sender_id)] = {
                'last_response': current_time,
                'first_time': True,
                'message_count': 1
            }
            self.save_responses()
            return True, self.settings['first_response']
        
        user_data = self.user_responses[str(sender_id)]
        last_response_time = datetime.fromisoformat(user_data['last_response'])
        current_time_dt = datetime.now()
        
        # Проверяем прошло ли timeout с последнего ответа
        time_diff = (current_time_dt - last_response_time).total_seconds()
        timeout = self.settings.get('response_timeout', 20 * 60)
        
        if time_diff >= timeout:
            # Можно отвечать снова
            response_text = self.settings['first_response'] if user_data.get('first_time', True) else self.settings['follow_up_response']
            
            # Обновляем счетчик сообщений
            message_count = user_data.get('message_count', 0) + 1
            self.user_responses[str(sender_id)] = {
                'last_response': current_time,
                'first_time': False,
                'message_count': message_count
            }
            self.save_responses()
            return True, response_text
        
        # Еще не прошло timeout
        return False, None
    
    def update_last_message_time(self, chat_id, is_outgoing=True):
        """Обновляет время последнего сообщения в диалоге"""
        current_time = datetime.now().isoformat()
        
        if chat_id not in self.last_message_times:
            self.last_message_times[chat_id] = {}
        
        if is_outgoing:
            self.last_message_times[chat_id]['last_outgoing'] = current_time
        else:
            self.last_message_times[chat_id]['last_incoming'] = current_time
    
    async def apply_typing_effect(self, client, chat_id, text, is_my_message=True, sender=None):
        """УНИВЕРСАЛЬНЫЙ метод эффекта печати для любых сообщений"""
        try:
            # Проверяем, включен ли эффект
            if not self.settings.get('message_effect_enabled', False):
                return None
            
            # Если это мое сообщение и получатель - бот, НЕ применяем эффект
            if is_my_message and sender:
                if self._is_bot_user(sender):
                    self.log(f"⚠️ Получатель @{sender.username} - бот, эффект печати пропускаем")
                    return None
            
            speed = self.settings.get('message_effect_speed', 75) / 1000
            initial_char = self.settings.get('message_effect_initial_char', "█")
            
            # Отправляем начальное сообщение с курсором
            try:
                message = await client.send_message(chat_id, initial_char)
                self.log(f"🔧 Начало эффекта печати: '{initial_char}'")
            except Exception as e:
                self.log(f"❌ Ошибка отправки начального сообщения: {e}")
                return None
            
            # Даем небольшую паузу для визуального эффекта
            await asyncio.sleep(0.1)
            
            # Постепенно раскрываем текст
            animated_text = ""
            for i in range(len(text)):
                animated_text += text[i]
                try:
                    # Редактируем сообщение, добавляя новый символ и курсор
                    await message.edit(animated_text + initial_char)
                except Exception as e:
                    self.log(f"❌ Ошибка редактирования сообщения: {e}")
                    # Если не удалось редактировать, удаляем сообщение и отправляем обычное
                    try:
                        await message.delete()
                    except:
                        pass
                    message = await client.send_message(chat_id, text)
                    return message
                
                # Задержка между символами
                if text[i] != ' ':  # Меньшая задержка для пробелов
                    await asyncio.sleep(speed)
                else:
                    await asyncio.sleep(speed / 2)
            
            # Убираем курсор в конце
            try:
                await message.edit(animated_text)
                self.log(f"✅ Эффект печати завершен: '{text[:20]}...'")
            except Exception as e:
                self.log(f"❌ Ошибка окончательного редактирования: {e}")
            
            return message
            
        except Exception as e:
            self.log(f"❌ Общая ошибка в эффекте печати: {e}")
            return None
    
    def _is_bot_user(self, user):
        """Проверяет, является ли пользователь ботом"""
        if not user:
            return False
        
        if hasattr(user, 'bot') and user.bot:
            return True
        
        if hasattr(user, 'username') and user.username:
            username_lower = user.username.lower()
            if username_lower.endswith('bot'):
                return True
        
        return False
    
    async def send_with_effect(self, client, chat_id, text):
        """Отправляет сообщение с эффектом печати (для автоответчика)"""
        # Используем универсальный метод
        return await self.apply_typing_effect(client, chat_id, text, is_my_message=False)
    
    async def apply_typing_effect_to_my_message(self, client, message):
        """Применяет эффект печати к МОЕМУ сообщению (старый метод, оставлен для совместимости)"""
        try:
            if not self.settings.get('message_effect_enabled', False):
                return message
            
            chat_id = message.chat_id
            text = message.text
            
            if not text:
                return message
            
            speed = self.settings.get('message_effect_speed', 75) / 1000  # конвертируем в секунды
            initial_char = self.settings.get('message_effect_initial_char', "█")
            
            # Сначала меняем сообщение на начальный символ
            try:
                await message.edit(initial_char)
            except Exception as e:
                self.log(f"Ошибка редактирования сообщения на начальный символ: {e}")
                return message
            
            # Постепенно раскрываем текст
            animated_text = ""
            for char in text:
                animated_text += char
                try:
                    # Редактируем сообщение, добавляя новый символ и курсор
                    await message.edit(animated_text + initial_char)
                except Exception as e:
                    self.log(f"Ошибка редактирования сообщения в процессе анимации: {e}")
                    # Пытаемся восстановить оригинальный текст
                    try:
                        await message.edit(text)
                    except:
                        pass
                    return message
                
                # Задержка между символами
                if char != ' ':  # Меньшая задержка для пробелов
                    await asyncio.sleep(speed)
                else:
                    await asyncio.sleep(speed / 2)
            
            # Убираем курсор в конце
            try:
                await message.edit(animated_text)
            except Exception as e:
                self.log(f"Ошибка окончательного редактирования: {e}")
            
            return message
            
        except Exception as e:
            self.log(f"Общая ошибка в эффекте печати для моего сообщения: {e}")
            return message
    
    def update_settings(self, new_settings):
        """Обновляет настройки автоответчика"""
        # Обновляем только переданные настройки, сохраняя остальные
        for key, value in new_settings.items():
            self.settings[key] = value
        self.save_settings()
    
    def get_settings(self):
        """Возвращает текущие настройки"""
        return self.settings.copy()
    
    def log(self, message):
        log_queue.put(f"[AutoResponder {self.user_id}] {message}")

class TelegramBotUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Telegram Bot Manager")
        self.root.geometry("1000x850")  # Увеличил размер для новых функций
        
        self.account_manager = AccountManager()
        self.bots = {}  # account_id -> (client, tracker, responder, task)
        self.running = True
        self.current_account_phone = None
        self.current_account_id = None
        
        # Файл для отслеживания запусков
        self.launch_count_file = 'launch_count.txt'
        self.launch_count = self.load_launch_count()
        
        self.setup_ui()
        self.start_log_poller()
        self.load_saved_accounts_to_ui()
        
        # Автоматический запуск ботов при втором и последующих запусках
        if self.launch_count >= 2 and len(self.account_manager.active_accounts) >= 2:
            self.root.after(1000, self.auto_start_bots)  # Запускаем через 1 секунду
    
    def load_launch_count(self):
        """Загружает счетчик запусков программы"""
        try:
            if os.path.exists(self.launch_count_file):
                with open(self.launch_count_file, 'r') as f:
                    return int(f.read().strip())
        except:
            pass
        return 1
    
    def save_launch_count(self):
        """Сохраняет счетчик запусков программы"""
        try:
            with open(self.launch_count_file, 'w') as f:
                f.write(str(self.launch_count))
        except Exception as e:
            log_queue.put(f"❌ Ошибка сохранения счетчика запусков: {e}")
    
    def setup_ui(self):
        # Главный фрейм
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Верхняя панель - управление аккаунтами
        top_frame = ttk.LabelFrame(main_frame, text="Управление аккаунтами", padding=10)
        top_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Панель с кнопками управления аккаунтами
        account_buttons_frame = ttk.Frame(top_frame)
        account_buttons_frame.pack(fill=tk.X)
        
        ttk.Button(account_buttons_frame, text="➕ Добавить аккаунт", 
                  command=self.add_account_dialog, width=20).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(account_buttons_frame, text="🔄 Сменить API", 
                  command=self.change_api_dialog, width=20).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(account_buttons_frame, text="⚙️ Настройки автоответчика", 
                  command=self.auto_responder_settings_dialog, width=25).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(account_buttons_frame, text="🗑️ Удалить все сохранения", 
                  command=self.clear_all_data_dialog, width=25).pack(side=tk.LEFT, padx=5)
        
        # Показ текущего аккаунта
        self.current_account_label = ttk.Label(top_frame, text="Текущий аккаунт: Не выбран", 
                                               font=('Arial', 10, 'bold'))
        self.current_account_label.pack(pady=5)
        
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
        self.password_entry = ttk.Entry(left_frame, width=30)
        self.password_entry.pack(fill=tk.X, pady=(0, 20))
        
        # Статус
        self.status_label = ttk.Label(left_frame, text="❓ Не авторизован", foreground="blue")
        self.status_label.pack(pady=(0, 10))
        
        # Кнопки авторизации
        ttk.Button(left_frame, text="🔐 Авторизовать", 
                  command=self.authorize_account, width=25).pack(pady=5)
        
        ttk.Button(left_frame, text="🚀 Запустить бота", 
                  command=self.start_bot, width=25).pack(pady=5)
        
        ttk.Button(left_frame, text="⏹️ Остановить всех", 
                  command=self.stop_all_bots, width=25).pack(pady=5)
        
        ttk.Button(left_frame, text="🧹 Очистить", 
                  command=self.clear_fields, width=25).pack(pady=5)
        
        ttk.Button(left_frame, text="🗑️ Удалить аккаунт", 
                  command=self.delete_selected_account, width=25).pack(pady=5)
        
        # Правая панель - логи и управление
        right_frame = ttk.LabelFrame(main_frame, text="Логи и управление", padding=10)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        # Логи
        self.log_text = scrolledtext.ScrolledText(right_frame, height=25)
        self.log_text.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Кнопки управления логами
        log_buttons = ttk.Frame(right_frame)
        log_buttons.pack(fill=tk.X)
        
        ttk.Button(log_buttons, text="Очистить логи", 
                  command=self.clear_logs).pack(side=tk.LEFT, padx=2)
        
        ttk.Button(log_buttons, text="Сохранить логи", 
                  command=self.save_logs).pack(side=tk.LEFT, padx=2)
        
        # Информация об аккаунтах
        self.accounts_text = scrolledtext.ScrolledText(right_frame, height=10)
        self.accounts_text.pack(fill=tk.BOTH, expand=True)
        self.update_accounts_display()
    
    def add_account_dialog(self):
        """Диалог добавления аккаунта"""
        # Проверяем лимит аккаунтов
        if not self.account_manager.can_add_more_accounts():
            messagebox.showwarning("Лимит аккаунтов", 
                                 f"Достигнут лимит в 10 аккаунтов!\nУдалите ненужные аккаунты.")
            return
        
        # Создаем диалоговое окно
        dialog = tk.Toplevel(self.root)
        dialog.title("Добавление аккаунта")
        dialog.geometry("400x300")
        dialog.transient(self.root)
        dialog.grab_set()
        
        tk.Label(dialog, text="Добавление нового аккаунта", 
                font=("Arial", 12, "bold")).pack(pady=10)
        
        tk.Label(dialog, text="Номер телефона (с +):").pack(anchor=tk.W, padx=20, pady=(10, 5))
        phone_var = tk.StringVar()
        phone_entry = tk.Entry(dialog, textvariable=phone_var, width=30)
        phone_entry.pack(padx=20, pady=(0, 10))
        
        # Используем API из текущего выбранного аккаунта или из первого
        accounts_count = len(self.account_manager.active_accounts)
        if accounts_count >= 1:
            # Берем API из текущего выбранного аккаунта или из первого
            if self.current_account_id:
                current_account = self.account_manager.active_accounts[self.current_account_id]
                api_id = current_account['api_id']
                api_hash = current_account['api_hash']
            else:
                # Берем из первого аккаунта
                first_account_id = list(self.account_manager.active_accounts.keys())[0]
                first_account = self.account_manager.active_accounts[first_account_id]
                api_id = first_account['api_id']
                api_hash = first_account['api_hash']
            
            tk.Label(dialog, text=f"API ID: {api_id} (взято из текущего аккаунта)").pack(anchor=tk.W, padx=20, pady=(5, 5))
            tk.Label(dialog, text=f"API Hash: {api_hash[:10]}...").pack(anchor=tk.W, padx=20, pady=(0, 10))
            
            api_id_var = tk.StringVar(value=str(api_id))
            api_hash_var = tk.StringVar(value=api_hash)
        else:
            tk.Label(dialog, text="API ID:").pack(anchor=tk.W, padx=20, pady=(5, 5))
            api_id_var = tk.StringVar()
            api_id_entry = tk.Entry(dialog, textvariable=api_id_var, width=30)
            api_id_entry.pack(padx=20, pady=(0, 10))
            
            tk.Label(dialog, text="API Hash:").pack(anchor=tk.W, padx=20, pady=(5, 5))
            api_hash_var = tk.StringVar()
            api_hash_entry = tk.Entry(dialog, textvariable=api_hash_var, width=30)
            api_hash_entry.pack(padx=20, pady=(0, 10))
        
        def submit():
            phone = phone_var.get().strip()
            
            if not phone:
                messagebox.showerror("Ошибка", "Введите номер телефона!")
                return
            
            # Проверяем, не существует ли уже такой номер
            session_data = self.account_manager.get_session_data(phone)
            if session_data:
                messagebox.showerror("Ошибка", f"Аккаунт {phone} уже существует!")
                return
            
            if accounts_count >= 1:
                # Используем API из текущего аккаунта
                api_id_val = api_id
                api_hash_val = api_hash
            else:
                api_id_val = api_id_var.get().strip()
                api_hash_val = api_hash_var.get().strip()
                
                if not all([api_id_val, api_hash_val]):
                    messagebox.showerror("Ошибка", "Заполните все поля API!")
                    return
                
                try:
                    api_id_val = int(api_id_val)
                except ValueError:
                    messagebox.showerror("Ошибка", "API ID должен быть числом!")
                    return
            
            # Автозаполнение полей в основном окне
            self.root.after(0, lambda: self._auto_fill_account_data(phone, api_id_val, api_hash_val))
            
            # Сохраняем данные для этого аккаунта
            next_number = self.account_manager.get_next_account_number()
            account_key = f"account_{next_number}"
            
            self.account_manager.sessions_data[account_key] = {
                'api_id': api_id_val,
                'api_hash': api_hash_val,
                'phone': phone,
                'username': f"user_{next_number}",
                'first_name': f"Аккаунт {next_number}",
                'user_id': account_key,
                'last_used': datetime.now().isoformat(),
                'account_number': next_number
            }
            self.account_manager.save_sessions()
            
            # Обновляем список аккаунтов
            self.load_saved_accounts_to_ui()
            
            # Устанавливаем выбранный аккаунт
            display_text = f"{phone} - Аккаунт {next_number}"
            self.account_combo.set(display_text)
            self.current_account_phone = phone
            self.current_account_id = account_key
            
            self.current_account_label.config(
                text=f"Текущий аккаунт: Аккаунт {next_number} ({phone})"
            )
            
            messagebox.showinfo("Успех", f"Аккаунт {phone} добавлен как #{next_number}!\nТеперь можно авторизоваться.")
            dialog.destroy()
        
        def cancel():
            dialog.destroy()
        
        button_frame = tk.Frame(dialog)
        button_frame.pack(pady=20)
        
        tk.Button(button_frame, text="Добавить", command=submit, width=15).pack(side=tk.LEFT, padx=10)
        tk.Button(button_frame, text="Отмена", command=cancel, width=15).pack(side=tk.RIGHT, padx=10)
    
    def _auto_fill_account_data(self, phone, api_id, api_hash):
        """Автозаполнение данных аккаунта (вызывается из основного потока)"""
        self.phone_entry.delete(0, tk.END)
        self.phone_entry.insert(0, phone)
        self.api_id_entry.delete(0, tk.END)
        self.api_id_entry.insert(0, str(api_id))
        self.api_hash_entry.delete(0, tk.END)
        self.api_hash_entry.insert(0, api_hash)
    
    def change_api_dialog(self):
        """Диалог смены API для выбранного аккаунта"""
        sessions = self.account_manager.get_session_data()
        if not sessions:
            messagebox.showinfo("Информация", "Нет сохраненных аккаунтов для смены API")
            return
        
        dialog = tk.Toplevel(self.root)
        dialog.title("Смена API данных")
        dialog.geometry("500x400")
        dialog.transient(self.root)
        dialog.grab_set()
        
        tk.Label(dialog, text="Выберите аккаунт для смены API:", 
                font=("Arial", 12, "bold")).pack(pady=10)
        
        # Создаем список аккаунтов
        listbox_frame = tk.Frame(dialog)
        listbox_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        scrollbar = tk.Scrollbar(listbox_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        accounts_listbox = tk.Listbox(listbox_frame, yscrollcommand=scrollbar.set, 
                                     font=("Arial", 10), height=10, selectmode=tk.SINGLE)
        
        # Заполняем список
        account_items = []
        for phone_key, data in sessions.items():
            phone = data.get('phone', '')
            name = data.get('first_name', '')
            
            if phone and name:
                display_text = f"{phone} - {name}"
                account_items.append((phone_key, display_text, phone, data))
        
        # Сортируем по имени
        account_items.sort(key=lambda x: x[1])
        
        for _, display_text, _, _ in account_items:
            accounts_listbox.insert(tk.END, display_text)
        
        accounts_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=accounts_listbox.yview)
        
        # Поля для ввода новых API данных
        api_frame = tk.Frame(dialog)
        api_frame.pack(fill=tk.X, padx=20, pady=10)
        
        tk.Label(api_frame, text="Новый API ID:").grid(row=0, column=0, sticky=tk.W, pady=5)
        api_id_var = tk.StringVar()
        api_id_entry = tk.Entry(api_frame, textvariable=api_id_var, width=30)
        api_id_entry.grid(row=0, column=1, pady=5, padx=5)
        
        tk.Label(api_frame, text="Новый API Hash:").grid(row=1, column=0, sticky=tk.W, pady=5)
        api_hash_var = tk.StringVar()
        api_hash_entry = tk.Entry(api_frame, textvariable=api_hash_var, width=30)
        api_hash_entry.grid(row=1, column=1, pady=5, padx=5)
        
        def on_account_selected(event):
            selection = accounts_listbox.curselection()
            if selection:
                index = selection[0]
                phone_key, _, phone, data = account_items[index]
                
                # Заполняем поля текущими API
                api_id_var.set(str(data['api_id']))
                api_hash_var.set(data['api_hash'])
        
        accounts_listbox.bind('<<ListboxSelect>>', on_account_selected)
        
        def submit():
            selection = accounts_listbox.curselection()
            if not selection:
                messagebox.showwarning("Внимание", "Выберите аккаунт из списка!")
                return
            
            index = selection[0]
            phone_key, _, phone, data = account_items[index]
            
            new_api_id = api_id_var.get().strip()
            new_api_hash = api_hash_var.get().strip()
            
            if not all([new_api_id, new_api_hash]):
                messagebox.showerror("Ошибка", "Заполните все поля API!")
                return
            
            try:
                new_api_id = int(new_api_id)
            except ValueError:
                messagebox.showerror("Ошибка", "API ID должен быть числом!")
                return
            
            # Обновляем API в сессиях
            if phone_key in self.account_manager.sessions_data:
                self.account_manager.sessions_data[phone_key]['api_id'] = new_api_id
                self.account_manager.sessions_data[phone_key]['api_hash'] = new_api_hash
                self.account_manager.save_sessions()
            
            # Обновляем API в активных аккаунтах
            account_id = data.get('user_id')
            if account_id and account_id in self.account_manager.active_accounts:
                self.account_manager.active_accounts[account_id]['api_id'] = new_api_id
                self.account_manager.active_accounts[account_id]['api_hash'] = new_api_hash
                self.account_manager.save_accounts()
            
            # Если это текущий выбранный аккаунт, обновляем поля ввода
            if self.current_account_phone == phone:
                self.root.after(0, lambda: self._update_api_fields(new_api_id, new_api_hash))
            
            log_queue.put(f"🔄 API для {phone} обновлены")
            messagebox.showinfo("Успех", "API данные обновлены!")
            dialog.destroy()
        
        def cancel():
            dialog.destroy()
        
        button_frame = tk.Frame(dialog)
        button_frame.pack(pady=20)
        
        tk.Button(button_frame, text="Сохранить", command=submit, width=15).pack(side=tk.LEFT, padx=10)
        tk.Button(button_frame, text="Отмена", command=cancel, width=15).pack(side=tk.RIGHT, padx=10)
        
        # Выбираем первый аккаунт по умолчанию
        if account_items:
            accounts_listbox.selection_set(0)
            on_account_selected(None)
    
    def _update_api_fields(self, api_id, api_hash):
        """Обновление полей API (вызывается из основного потока)"""
        self.api_id_entry.delete(0, tk.END)
        self.api_id_entry.insert(0, str(api_id))
        self.api_hash_entry.delete(0, tk.END)
        self.api_hash_entry.insert(0, api_hash)
    
    def auto_responder_settings_dialog(self):
        """Диалог настроек автоответчика"""
        selected_account = self.account_combo.get()
        if not selected_account:
            messagebox.showwarning("Внимание", "Сначала выберите аккаунт из списка!")
            return
        
        # Извлекаем номер телефона
        phone = selected_account.split(' - ')[0]
        session_data = self.account_manager.get_session_data(phone)
        
        if not session_data:
            messagebox.showerror("Ошибка", "Аккаунт не найден!")
            return
        
        account_id = session_data.get('user_id')
        if not account_id:
            messagebox.showerror("Ошибка", "ID аккаунта не найден!")
            return
        
        # Загружаем настройки автоответчика
        responder = AutoResponder(account_id)
        settings = responder.get_settings()
        
        dialog = tk.Toplevel(self.root)
        dialog.title("Настройки автоответчика")
        dialog.geometry("650x800")  # Увеличил размер для новых настроек
        dialog.transient(self.root)
        dialog.grab_set()
        
        tk.Label(dialog, text=f"Настройки автоответчика для:", 
                font=("Arial", 12, "bold")).pack(pady=10)
        
        tk.Label(dialog, text=f"{phone}").pack()
        
        # Создаем Canvas с Scrollbar для прокрутки
        canvas = tk.Canvas(dialog)
        scrollbar = ttk.Scrollbar(dialog, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        main_frame = scrollable_frame
        
        # Включение автоответчика
        enabled_var = tk.BooleanVar(value=settings.get('enabled', True))
        tk.Checkbutton(main_frame, text="Включить автоответчик", 
                      variable=enabled_var, font=("Arial", 10)).pack(anchor=tk.W, pady=5)
        
        # Отправка новым пользователям
        send_new_var = tk.BooleanVar(value=settings.get('send_to_new_users', True))
        tk.Checkbutton(main_frame, text="Отправлять ответы новым пользователям", 
                      variable=send_new_var, font=("Arial", 10)).pack(anchor=tk.W, pady=5)
        
        # Отправка существующим пользователям
        send_existing_var = tk.BooleanVar(value=settings.get('send_to_existing_users', True))
        tk.Checkbutton(main_frame, text="Отправлять ответы существующим пользователям", 
                      variable=send_existing_var, font=("Arial", 10)).pack(anchor=tk.W, pady=5)
        
        # Игнорирование после моего сообщения
        tk.Label(main_frame, text="Поведение после моего сообщения:", 
                font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(15, 5))
        
        ignore_after_var = tk.BooleanVar(value=settings.get('ignore_after_my_message', True))
        tk.Checkbutton(main_frame, text="Не отвечать если я написал последним", 
                      variable=ignore_after_var, font=("Arial", 10)).pack(anchor=tk.W, pady=2)
        
        tk.Label(main_frame, text="Время игнорирования после моего сообщения (минут):", 
                font=("Arial", 9)).pack(anchor=tk.W, pady=(5, 5))
        
        ignore_timeout_var = tk.StringVar(value=str(settings.get('ignore_timeout', 10 * 60) // 60))
        ignore_timeout_entry = tk.Entry(main_frame, textvariable=ignore_timeout_var, width=10)
        ignore_timeout_entry.pack(anchor=tk.W, pady=(0, 10))
        
        # Эффект сообщений
        tk.Label(main_frame, text="Эффект сообщений:", 
                font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(15, 5))
        
        effect_enabled_var = tk.BooleanVar(value=settings.get('message_effect_enabled', False))
        effect_checkbox = tk.Checkbutton(main_frame, text="Включить эффект печати сообщений", 
                                       variable=effect_enabled_var, font=("Arial", 10))
        effect_checkbox.pack(anchor=tk.W, pady=2)
        
        # Фрейм для настроек скорости
        speed_frame = tk.Frame(main_frame)
        speed_frame.pack(fill=tk.X, padx=20, pady=(5, 5), anchor=tk.W)
        
        tk.Label(speed_frame, text="Скорость печати (мс):", font=("Arial", 9)).pack(side=tk.LEFT, padx=(0, 10))
        
        speed_var = tk.StringVar(value=str(settings.get('message_effect_speed', 75)))
        speed_entry = tk.Entry(speed_frame, textvariable=speed_var, width=10, font=("Arial", 9))
        speed_entry.pack(side=tk.LEFT, padx=(0, 10))
        
        tk.Label(speed_frame, text="(10-1000, по умолчанию: 75)", font=("Arial", 8), fg="gray").pack(side=tk.LEFT)
        
        # Фрейм для настройки символа курсора
        char_frame = tk.Frame(main_frame)
        char_frame.pack(fill=tk.X, padx=20, pady=(5, 15), anchor=tk.W)
        
        tk.Label(char_frame, text="Символ курсора:", font=("Arial", 9)).pack(side=tk.LEFT, padx=(0, 10))
        
        char_var = tk.StringVar(value=settings.get('message_effect_initial_char', "█"))
        char_entry = tk.Entry(char_frame, textvariable=char_var, width=5, font=("Arial", 9))
        char_entry.pack(side=tk.LEFT, padx=(0, 10))
        
        tk.Label(char_frame, text="(например: █, |, _)", font=("Arial", 8), fg="gray").pack(side=tk.LEFT)
        
        # Пример эффекта
        tk.Label(main_frame, text="Пример эффекта:", font=("Arial", 9, "bold")).pack(anchor=tk.W, pady=(5, 2))
        
        example_text = tk.Text(main_frame, height=3, width=50, font=("Arial", 8), bg="#f0f0f0")
        example_text.pack(fill=tk.X, pady=(0, 10))
        example_text.insert(tk.END, "Привет -> █ -> п█ -> пр█ -> при█ -> прив█ -> приве█ -> привет█ -> привет")
        example_text.config(state=tk.DISABLED)
        
        # Интервал между ответами (в минутах)
        tk.Label(main_frame, text="Интервал между ответами (минут):", 
                font=("Arial", 10)).pack(anchor=tk.W, pady=(10, 5))
        
        timeout_var = tk.StringVar(value=str(settings.get('response_timeout', 20 * 60) // 60))
        timeout_entry = tk.Entry(main_frame, textvariable=timeout_var, width=10)
        timeout_entry.pack(anchor=tk.W, pady=(0, 10))
        
        # Первое сообщение
        tk.Label(main_frame, text="Первое сообщение:", 
                font=("Arial", 10)).pack(anchor=tk.W, pady=(10, 5))
        
        first_response_var = tk.StringVar(value=settings.get('first_response', "Я - автоответчик! Если есть вопросы, пишите сразу."))
        first_response_text = tk.Text(main_frame, height=3, width=40)
        first_response_text.pack(fill=tk.X, pady=(0, 5))
        first_response_text.insert(tk.END, first_response_var.get())
        
        # Последующие сообщения
        tk.Label(main_frame, text="Последующие сообщения:", 
                font=("Arial", 10)).pack(anchor=tk.W, pady=(10, 5))
        
        follow_up_var = tk.StringVar(value=settings.get('follow_up_response', "Скоро отвечу!"))
        follow_up_text = tk.Text(main_frame, height=3, width=40)
        follow_up_text.pack(fill=tk.X, pady=(0, 5))
        follow_up_text.insert(tk.END, follow_up_var.get())
        
        # Дополнительные функции
        tk.Label(main_frame, text="Дополнительные функции:", 
                font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(20, 5))
        
        # Автоответ на определенные слова
        keyword_response_var = tk.BooleanVar(value=settings.get('keyword_response', False))
        tk.Checkbutton(main_frame, text="Автоответ на ключевые слова", 
                      variable=keyword_response_var, font=("Arial", 10)).pack(anchor=tk.W, pady=2)
        
        # Случайный выбор ответа
        random_response_var = tk.BooleanVar(value=settings.get('random_response', False))
        tk.Checkbutton(main_frame, text="Случайный выбор ответа из списка", 
                      variable=random_response_var, font=("Arial", 10)).pack(anchor=tk.W, pady=2)
        
        # Задержка перед ответом
        delay_response_var = tk.BooleanVar(value=settings.get('delay_response', False))
        tk.Checkbutton(main_frame, text="Задержка перед ответом (5-30 сек)", 
                      variable=delay_response_var, font=("Arial", 10)).pack(anchor=tk.W, pady=2)
        
        def submit():
            try:
                timeout_minutes = int(timeout_var.get())
                if timeout_minutes < 1:
                    timeout_minutes = 1
                timeout_seconds = timeout_minutes * 60
            except ValueError:
                timeout_seconds = 20 * 60
            
            try:
                ignore_minutes = int(ignore_timeout_var.get())
                if ignore_minutes < 1:
                    ignore_minutes = 1
                ignore_seconds = ignore_minutes * 60
            except ValueError:
                ignore_seconds = 10 * 60
            
            # Проверяем скорость эффекта
            try:
                effect_speed = int(speed_var.get())
                if effect_speed < 10:
                    effect_speed = 10
                elif effect_speed > 1000:
                    effect_speed = 1000
            except ValueError:
                effect_speed = 75
            
            # ВАЖНО: Сохраняем ВСЕ настройки
            new_settings = {
                'enabled': enabled_var.get(),
                'send_to_new_users': send_new_var.get(),
                'send_to_existing_users': send_existing_var.get(),
                'response_timeout': timeout_seconds,
                'first_response': first_response_text.get(1.0, tk.END).strip(),
                'follow_up_response': follow_up_text.get(1.0, tk.END).strip(),
                'keyword_response': keyword_response_var.get(),
                'random_response': random_response_var.get(),
                'delay_response': delay_response_var.get(),
                'ignore_after_my_message': ignore_after_var.get(),  # Новая настройка
                'ignore_timeout': ignore_seconds,  # Новая настройка
                'message_effect_enabled': effect_enabled_var.get(),
                'message_effect_speed': effect_speed,
                'message_effect_initial_char': char_var.get()[:3]  # Берем только первые 3 символа
            }
            
            # ВАЖНО: Используем update_settings который сохраняет ВСЕ настройки
            responder.update_settings(new_settings)
            log_queue.put(f"⚙️ Настройки автоответчика для {phone} сохранены")
            log_queue.put(f"   • Эффект сообщений: {'ВКЛ' if effect_enabled_var.get() else 'ВЫКЛ'}")
            log_queue.put(f"   • Игнорирование после моего сообщения: {'ВКЛ' if ignore_after_var.get() else 'ВЫКЛ'}")
            messagebox.showinfo("Успех", "Настройки сохранены!")
            dialog.destroy()
        
        def cancel():
            dialog.destroy()
        
        def reset_to_default():
            confirm = messagebox.askyesno("Сброс настроек", 
                                         "Восстановить настройки по умолчанию?")
            if confirm:
                enabled_var.set(True)
                send_new_var.set(True)
                send_existing_var.set(True)
                ignore_after_var.set(True)
                ignore_timeout_var.set("10")
                effect_enabled_var.set(False)
                speed_var.set("75")
                char_var.set("█")
                timeout_var.set("20")
                first_response_text.delete(1.0, tk.END)
                first_response_text.insert(tk.END, "Я - автоответчик! Если есть вопросы, пишите сразу.")
                follow_up_text.delete(1.0, tk.END)
                follow_up_text.insert(tk.END, "Скоро отвечу!")
                keyword_response_var.set(False)
                random_response_var.set(False)
                delay_response_var.set(False)
        
        button_frame = tk.Frame(main_frame)
        button_frame.pack(pady=20)
        
        tk.Button(button_frame, text="Сохранить", command=submit, width=15).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Сбросить", command=reset_to_default, width=15).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Отмена", command=cancel, width=15).pack(side=tk.RIGHT, padx=5)
    
    def clear_all_data_dialog(self):
        """Диалог удаления всех сохранений"""
        confirm = messagebox.askyesno("Удаление всех сохранений", 
                                     "ВНИМАНИЕ! Все данные всех аккаунтов будут необратимо стерты.\n\n"
                                     "Это включает:\n"
                                     "• Все авторизованные аккаунты\n"
                                     "• Все сохраненные сессии\n"
                                     "• Настройки автоответчиков\n"
                                     "• Историю пользователей\n\n"
                                     "Продолжить?")
        
        if confirm:
            # Останавливаем всех ботов
            self.stop_all_bots()
            
            # Очищаем все данные
            self.account_manager.clear_all_data()
            
            # Удаляем файлы сессий
            for filename in os.listdir('.'):
                if filename.startswith('session_') and filename.endswith('.session'):
                    try:
                        os.remove(filename)
                    except:
                        pass
            
            # Удаляем файлы пользователей
            for filename in os.listdir('.'):
                if filename.startswith('users_data_') and filename.endswith('.json'):
                    try:
                        os.remove(filename)
                    except:
                        pass
            
            # Удаляем файлы автоответчиков
            for filename in os.listdir('.'):
                if filename.startswith('auto_responses_') and filename.endswith('.json'):
                    try:
                        os.remove(filename)
                    except:
                        pass
            
            # Удаляем файлы настроек автоответчиков
            for filename in os.listdir('.'):
                if filename.startswith('auto_responder_settings_') and filename.endswith('.json'):
                    try:
                        os.remove(filename)
                    except:
                        pass
            
            # Очищаем интерфейс
            self.clear_fields()
            self.account_combo['values'] = []
            self.update_accounts_display()
            
            # Сбрасываем счетчик запусков
            self.launch_count = 1
            self.save_launch_count()
            
            log_queue.put("🗑️ Все сохранения удалены!")
            messagebox.showinfo("Успех", "Все сохранения удалены!\nПрограмма перезапущена с заводскими настройками.")
    
    def auto_start_bots(self):
        """Автоматический запуск всех ботов при втором и последующих запусках программы"""
        log_queue.put("🚀 АВТОМАТИЧЕСКИЙ ЗАПУСК БОТОВ")
        
        # Запускаем ботов для всех сохраненных аккаунтов, начиная со второго
        sessions = self.account_manager.get_session_data()
        
        for phone_key, data in sessions.items():
            phone = data.get('phone', '')
            user_id = data.get('user_id', '')
            
            if user_id and user_id not in self.bots:
                # Запускаем бота в отдельном потоке
                threading.Thread(target=self._auto_start_bot_thread, 
                               args=(user_id, data), daemon=True).start()
                time.sleep(1)  # Задержка между запусками
    
    def _auto_start_bot_thread(self, account_id, account_info):
        """Поток для автоматического запуска бота"""
        def run_bot_wrapper():
            try:
                # СОЗДАЕМ НОВЫЙ ЦИКЛ СОБЫТИЙ ДЛЯ КАЖДОГО ПОТОКА
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                try:
                    loop.run_until_complete(self._run_bot_async(account_id, account_info, loop))
                except asyncio.CancelledError:
                    log_queue.put(f"⚠️ Бот {account_info['phone']} был отменен")
                except Exception as e:
                    log_queue.put(f"❌ Ошибка в боте {account_info['phone']}: {e}")
                finally:
                    # Корректное завершение цикла событий
                    try:
                        loop.run_until_complete(loop.shutdown_asyncgens())
                        loop.close()
                    except:
                        pass
            except Exception as e:
                log_queue.put(f"❌ Критическая ошибка в потоке бота {account_info['phone']}: {e}")
        
        # Запускаем обертку
        run_bot_wrapper()
    
    async def _run_bot_async(self, account_id, account_info, loop):
        """Асинхронная функция запуска бота"""
        try:
            session_name = f"session_{account_info['phone'].replace('+', '')}"
            client = TelegramClient(session_name, 
                                   account_info['api_id'], 
                                   account_info['api_hash'])
            
            tracker = UserTracker(account_id)
            responder = AutoResponder(account_id)
            
            await client.start()
            log_queue.put(f"✅ Автозапуск: {account_info['phone']}")
            
            await self.create_pinned_message(client, tracker, account_id)
            
            @client.on(events.NewMessage(incoming=True))
            async def handle_incoming(event):
                try:
                    if not event.is_private or event.out:
                        return
                    
                    sender = await event.get_sender()
                    chat = await event.get_chat()
                    
                    # ПРОВЕРКА НА БОТА
                    if responder._is_bot_user(sender):
                        tracker.log(f"🤖 Игнорирую сообщение от бота: @{sender.username if hasattr(sender, 'username') else sender.id}")
                        return
                    
                    # Обновляем время последнего входящего сообщения
                    responder.update_last_message_time(chat.id, is_outgoing=False)
                    
                    if tracker.add_user(sender.id, sender.username or "None"):
                        username = f"@{sender.username}" if sender.username else f"ID:{sender.id}"
                        tracker.log(f"👤 Новый пользователь: {username}")
                        await self.create_pinned_message(client, tracker, account_id)
                    
                    # ВАЖНО: Передаем chat_id в should_respond
                    should_respond, response_text = responder.should_respond(sender.id, chat.id)
                    
                    if should_respond and response_text:
                        # Дополнительная обработка для новых функций
                        settings = responder.get_settings()
                        
                        # Задержка если включена
                        if settings.get('delay_response', False):
                            import random
                            delay = random.randint(5, 30)
                            await asyncio.sleep(delay)
                        
                        # Отправляем сообщение с эффектом или без
                        if settings.get('message_effect_enabled', False):
                            message = await responder.send_with_effect(client, sender.id, response_text)
                        else:
                            message = await client.send_message(sender.id, response_text)
                        
                        # Обновляем время последнего исходящего сообщения
                        if message:
                            responder.update_last_message_time(chat.id, is_outgoing=True)
                        
                        username = f"@{sender.username}" if sender.username else f"ID:{sender.id}"
                        responder.log(f"📨 Отправлен автоответ {username}: {response_text}")
                        if settings.get('message_effect_enabled', False):
                            responder.log(f"   (с эффектом печати, скорость: {settings.get('message_effect_speed', 75)}мс)")
                
                except Exception as e:
                    tracker.log(f"❌ Ошибка автоответчика: {e}")
            
            @client.on(events.NewMessage(outgoing=True))
            async def handle_outgoing(event):
                try:
                    message = event.message
                    
                    # Получаем чат (получателя)
                    chat = await event.get_chat()
                    
                    # Обновляем время последнего исходящего сообщения
                    responder.update_last_message_time(chat.id, is_outgoing=True)
                    
                    # Проверяем, является ли чат пользователем (не группой/каналом)
                    if hasattr(chat, 'username') or hasattr(chat, 'bot'):
                        # Это пользователь, проверяем на бота
                        is_bot = responder._is_bot_user(chat)
                        
                        # Если получатель - бот, не применяем эффект
                        if is_bot:
                            tracker.log(f"🤖 Получатель @{chat.username if hasattr(chat, 'username') else chat.id} - бот, эффект печати не применяем")
                            return
                    else:
                        # Это группа или канал - применяем эффект если включен
                        tracker.log(f"👥 Это группа/канал {chat.id}, проверяем эффект печати")
                    
                    # ПРИМЕНЯЕМ ЭФФЕКТ ПЕЧАТИ К МОИМ СООБЩЕНИЯМ
                    if message.text and not message.media:
                        # Проверяем, включен ли эффект печати
                        settings = responder.get_settings()
                        
                        if settings.get('message_effect_enabled', False):
                            tracker.log(f"🚀 Применяю эффект печати к моему сообщению для {chat.id}")
                            
                            # УДАЛЯЕМ оригинальное сообщение и отправляем новое с эффектом
                            try:
                                # Получаем текст сообщения
                                text = message.text
                                
                                # Удаляем оригинальное сообщение
                                await message.delete()
                                
                                # Даем небольшую задержку
                                await asyncio.sleep(0.1)
                                
                                # Отправляем сообщение с эффектом печати
                                new_message = await responder.apply_typing_effect(
                                    client, 
                                    chat.id, 
                                    text, 
                                    is_my_message=True,
                                    sender=chat  # Передаем получателя для проверки на бота
                                )
                                
                                if new_message:
                                    tracker.log(f"✅ Эффект печати успешно применен")
                                else:
                                    # Если эффект не сработал, отправляем обычное сообщение
                                    await client.send_message(chat.id, text)
                                    tracker.log(f"⚠️ Эффект печати не применен, отправлено обычное сообщение")
                                    
                            except Exception as e:
                                tracker.log(f"❌ Ошибка применения эффекта печати: {e}")
                                # В случае ошибки пробуем отправить обычное сообщение
                                try:
                                    await client.send_message(chat.id, text)
                                except:
                                    pass
                    
                    # УЛУЧШЕННЫЙ КОД ДЛЯ МЕДИА-СООБЩЕНИЙ - УДАЛЯЕМ СТАТУС СРАЗУ ПОСЛЕ ОТПРАВКИ
                    if message.media:
                        # Определяем тип медиа и создаем соответствующий статус
                        status_text = "📤 Отправляю медиа, подожди⏩"
                        if message.photo:
                            status_text = "🖼️ Отправляю фото, подожди⏩"
                        elif message.video:
                            status_text = "🎥 Отправляю видео, подожди⏩"
                        elif message.audio or message.voice:
                            status_text = "🎵 Отправляю аудио, подожди⏩"
                        elif message.document:
                            status_text = "📄 Отправляю документ, подожди⏩"
                        
                        # Отправляем статус
                        status_msg = await client.send_message(chat.id, f"**{status_text}**", parse_mode='md')
                        tracker.log(f"📤 Отправлен статус: {status_text}")
                        
                        # Ожидаем отправки сообщения с медиа
                        try:
                            # Ждем немного, чтобы сообщение успело отправиться
                            await asyncio.sleep(0.5)
                            
                            # Проверяем, доставлено ли сообщение
                            messages = await client.get_messages(chat.id, limit=1)
                            if messages and messages[0].id == message.id:
                                # Сообщение доставлено, удаляем статус
                                await status_msg.delete()
                                tracker.log(f"✅ Файл доставлен, статус удален")
                            else:
                                # Если не нашли сообщение, ждем еще и проверяем
                                await asyncio.sleep(0.5)
                                await status_msg.delete()
                                tracker.log(f"⚠️ Статус удален (таймаут)")
                                
                        except Exception as e:
                            tracker.log(f"⚠️ Не удалось отследить доставку: {e}")
                            # В любом случае удаляем статус через 1 секунду
                            await asyncio.sleep(1)
                            await status_msg.delete()
                
                except Exception as e:
                    tracker.log(f"❌ Ошибка обработки исходящего сообщения: {e}")
            
            self.bots[account_id] = (client, tracker, responder, loop)
            self.root.after(0, self.update_accounts_display)
            
            await client.run_until_disconnected()
            
        except Exception as e:
            log_queue.put(f"❌ Ошибка автозапуска {account_info['phone']}: {e}")
        finally:
            if account_id in self.bots:
                del self.bots[account_id]
                self.root.after(0, self.update_accounts_display)
                log_queue.put(f"⏹️ Бот {account_info['phone']} остановлен")
    
    def show_accounts_stats(self):
        """Показывает статистику аккаунтов"""
        sessions = self.account_manager.get_session_data()
        active_accounts = len(self.account_manager.active_accounts)
        active_bots = len(self.bots)
        max_accounts = 10
        
        stats_text = f"""
📊 Статистика аккаунтов:

• Всего сохранено аккаунтов: {len(sessions)}
• Авторизовано аккаунтов: {active_accounts}
• Запущено ботов: {active_bots}
• Доступно мест: {max_accounts - active_accounts}/{max_accounts}
• Запуск программы: #{self.launch_count}

📋 Список аккаунтов:
"""
        
        # Сортируем аккаунты по номеру
        sorted_accounts = []
        for phone_key, data in sessions.items():
            account_number = data.get('account_number', 0)
            sorted_accounts.append((account_number, data))
        
        sorted_accounts.sort(key=lambda x: x[0])
        
        for i, (account_number, data) in enumerate(sorted_accounts, 1):
            phone = data.get('phone', '')
            name = data.get('first_name', '')
            username = data.get('username', '')
            
            bot_status = "🟢 Запущен" if str(data.get('user_id', '')) in self.bots else "⭕ Остановлен"
            
            stats_text += f"\n{account_number}. {name} ({phone})\n   Статус: {bot_status}"
        
        messagebox.showinfo("Статистика аккаунтов", stats_text)
    
    def load_saved_accounts_to_ui(self):
        """Загружает сохраненные аккаунты в выпадающий список"""
        sessions = self.account_manager.get_session_data()
        if sessions:
            account_list = []
            # Сортируем аккаунты по номеру
            sorted_accounts = []
            for phone_key, data in sessions.items():
                account_number = data.get('account_number', 0)
                sorted_accounts.append((account_number, data))
            
            sorted_accounts.sort(key=lambda x: x[0])
            
            for account_number, data in sorted_accounts:
                phone = data.get('phone', '')
                name = data.get('first_name', '')
                if phone and name:
                    display_text = f"{phone} - {name}"
                    account_list.append(display_text)
            
            if account_list:
                self.account_combo['values'] = account_list
                log_queue.put(f"📱 Загружено {len(account_list)} сохраненных аккаунтов")
    
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
            self.current_account_id = session_data.get('user_id')
            
            # Заполняем поля данными аккаунта
            self.api_id_entry.delete(0, tk.END)
            self.api_hash_entry.delete(0, tk.END)
            self.phone_entry.delete(0, tk.END)
            self.password_entry.delete(0, tk.END)
            
            self.api_id_entry.insert(0, str(session_data['api_id']))
            self.api_hash_entry.insert(0, session_data['api_hash'])
            self.phone_entry.insert(0, session_data['phone'])
            
            # Обновляем метку текущего аккаунта
            self.current_account_label.config(
                text=f"Текущий аккаунт: {session_data['first_name']} ({phone})"
            )
            
            # Устанавливаем статус
            if str(session_data.get('user_id', '')) in self.bots:
                self.status_label.config(text="✅ Бот запущен", foreground="green")
            else:
                self.status_label.config(text="✅ Данные загружены", foreground="green")
            
            log_queue.put(f"📋 Загружены данные для {session_data['phone']}")
    
    def log(self, message):
        """Добавляет сообщение в лог (только из основного потока)"""
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
                    # Используем after для обновления UI из фонового потока
                    self.root.after(0, self._add_log_message, message)
                except queue.Empty:
                    pass
                time.sleep(0.1)
        
        thread = threading.Thread(target=poll_logs, daemon=True)
        thread.start()
    
    def _add_log_message(self, message):
        """Добавляет сообщение в лог (вызывается через after)"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_message = f"[{timestamp}] {message}\n"
        
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, log_message)
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
        
        print(log_message, end='')
    
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
        dialog_closed.wait()
        return result["code"]
    
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
        
        # Проверяем лимит аккаунтов
        if not self.account_manager.can_add_more_accounts():
            messagebox.showwarning("Лимит аккаунтов", 
                                 f"Достигнут лимит в 10 аккаунтов!\nУдалите ненужные аккаунты.")
            return
        
        try:
            api_id = int(api_id)
        except ValueError:
            messagebox.showerror("Ошибка", "API ID должен быть числом")
            return
        
        self.status_label.config(text="⏳ Авторизация...", foreground="orange")
        
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
                                    # Используем пароль из поля ввода
                                    password = self.password_entry.get()
                                    
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
                                    return False
                        
                        except Exception as e:
                            error_msg = str(e)
                            log_queue.put(f"⚠️ Ошибка отправки кода: {error_msg}")
                            return False
                    
                    else:
                        log_queue.put("✅ Уже авторизован")
                    
                    me = await client.get_me()
                    log_queue.put(f"👤 Информация: {me.first_name} (@{me.username})")
                    
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
                
                result = loop.run_until_complete(auth_async())
                loop.close()
                return result
                    
            except Exception as e:
                log_queue.put(f"❌ Ошибка авторизации: {e}")
                self.root.after(0, lambda: self.status_label.config(
                    text=f"❌ Ошибка", foreground="red"))
                return False
        
        auth()
    
    def _save_account_info(self, account_info):
        """Сохраняет информацию об аккаунте"""
        self.account_manager.add_account(
            account_info['user_id'],
            account_info['api_id'],
            account_info['api_hash'],
            account_info['phone'],
            account_info['username'],
            account_info['first_name']
        )
        
        self.account_manager.save_session_data(
            account_info['phone'],
            account_info['api_id'],
            account_info['api_hash'],
            account_info['username'],
            account_info['first_name'],
            account_info['user_id']
        )
        
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
        
        display_text = f"{account_info['phone']} - {account_info['first_name']}"
        self.account_combo.set(display_text)
        self.current_account_phone = account_info['phone']
        self.current_account_id = account_info['user_id']
        
        self.current_account_label.config(
            text=f"Текущий аккаунт: {account_info['first_name']} ({account_info['phone']})"
        )
        
        self.status_label.config(text="✅ Авторизован", foreground="green")
        self.update_accounts_display()
    
    def delete_selected_account(self):
        """Удаляет выбранный аккаунт"""
        selected = self.account_combo.get()
        if not selected:
            messagebox.showwarning("Предупреждение", "Выберите аккаунт для удаления")
            return
        
        # Извлекаем номер телефона
        phone = selected.split(' - ')[0]
        
        confirm = messagebox.askyesno("Подтверждение", 
                                     f"Удалить аккаунт {phone}?")
        if not confirm:
            return
        
        session_data = self.account_manager.get_session_data(phone)
        if session_data and 'user_id' in session_data:
            user_id = session_data['user_id']
            
            # Останавливаем бота если запущен
            if user_id in self.bots:
                client, tracker, responder, loop = self.bots[user_id]
                
                # Запускаем отключение в отдельном потоке
                def stop_bot():
                    try:
                        # Создаем новую задачу для отключения
                        async def disconnect():
                            await client.disconnect()
                        
                        # Запускаем отключение в существующем цикле
                        loop.create_task(disconnect())
                    except:
                        pass
                
                threading.Thread(target=stop_bot, daemon=True).start()
                del self.bots[user_id]
            
            # Удаляем из менеджера
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
            
            # Удаляем файлы пользователей и автоответчика
            for filename in [f'users_data_{user_id}.json', 
                           f'auto_responses_{user_id}.json',
                           f'auto_responder_settings_{user_id}.json']:
                if os.path.exists(filename):
                    try:
                        os.remove(filename)
                    except:
                        pass
            
            log_queue.put(f"🗑️ Аккаунт {phone} удален")
            
            self.clear_fields()
            self.load_saved_accounts_to_ui()
            self.update_accounts_display()
            
            self.current_account_label.config(text="Текущий аккаунт: Не выбран")
            
            messagebox.showinfo("Успех", f"Аккаунт {phone} удален")
        else:
            messagebox.showerror("Ошибка", "Аккаунт не найден")
    
    def update_accounts_display(self):
        """Обновляет отображение аккаунтов"""
        self.accounts_text.config(state=tk.NORMAL)
        self.accounts_text.delete(1.0, tk.END)
        
        sessions = self.account_manager.get_session_data()
        
        if sessions:
            self.accounts_text.insert(tk.END, "📱 Все аккаунты:\n\n")
            
            # Сортируем аккаунты по номеру
            sorted_accounts = []
            for phone_key, data in sessions.items():
                account_number = data.get('account_number', 0)
                sorted_accounts.append((account_number, data))
            
            sorted_accounts.sort(key=lambda x: x[0])
            
            for account_number, data in sorted_accounts:
                phone = data.get('phone', '')
                name = data.get('first_name', '')
                username = data.get('username', '')
                
                account_id = str(data.get('user_id', ''))
                bot_status = "🚀 Запущен" if account_id in self.bots else "⏸️ Остановлен"
                
                self.accounts_text.insert(tk.END, 
                    f"{account_number}. {name} @{username}\n"
                    f"   {phone}\n"
                    f"   Статус: {bot_status}\n"
                    f"   {'─' * 40}\n"
                )
            
            # Статистика
            total = len(sessions)
            active = len(self.bots)
            available = 10 - total
            
            self.accounts_text.insert(tk.END, 
                f"\n📊 Статистика:\n"
                f"• Всего аккаунтов: {total}/10\n"
                f"• Активных ботов: {active}\n"
                f"• Доступно мест: {available}\n"
                f"• Запуск программы: #{self.launch_count}\n"
            )
        else:
            self.accounts_text.insert(tk.END, "📭 Нет сохраненных аккаунтов\n")
        
        self.accounts_text.config(state=tk.DISABLED)
    
    def start_bot(self):
        """Запускает бота"""
        api_id = self.api_id_entry.get().strip()
        api_hash = self.api_hash_entry.get().strip()
        phone = self.phone_entry.get().strip()
        
        if not all([api_id, api_hash, phone]):
            messagebox.showerror("Ошибка", "Сначала авторизуйте аккаунт")
            return
        
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
        
        # Получаем данные аккаунта
        account_info = self.account_manager.get_account_info(account_id)
        if not account_info:
            log_queue.put(f"❌ Аккаунт не найден")
            return
        
        # Запускаем бота в отдельном потоке
        threading.Thread(target=self._auto_start_bot_thread, 
                        args=(account_id, account_info), daemon=True).start()
    
    def _start_bot_thread(self, account_id):
        """Совместимость со старым кодом"""
        account_info = self.account_manager.get_account_info(account_id)
        if account_info:
            self._auto_start_bot_thread(account_id, account_info)
    
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
                    return tracker.pinned_message_id
                except:
                    pass
            
            message = await client.send_message(me, message_text, parse_mode='md')
            
            try:
                await client.pin_message(me, message.id, notify=False)
            except:
                pass
            
            tracker.pinned_message_id = message.id
            tracker.save_users()
            
            return message.id
            
        except Exception as e:
            tracker.log(f"Ошибка: {e}")
            return None
    
    def stop_all_bots(self):
        """Останавливает всех ботов"""
        if not self.bots:
            messagebox.showinfo("Информация", "Нет запущенных ботов")
            return
        
        log_queue.put("⏹️ Остановка всех ботов...")
        
        for account_id, (client, tracker, responder, loop) in list(self.bots.items()):
            # Останавливаем бота в отдельном потоке
            def stop_bot(client, loop):
                try:
                    # Создаем задачу для отключения
                    async def disconnect():
                        await client.disconnect()
                    
                    # Запускаем отключение
                    if not loop.is_closed():
                        loop.create_task(disconnect())
                except:
                    pass
            
            threading.Thread(target=stop_bot, args=(client, loop), daemon=True).start()
            time.sleep(0.1)  # Небольшая задержка между остановками
        
        # Очищаем словарь ботов
        self.bots.clear()
        self.root.after(0, self.update_accounts_display)
        log_queue.put("✅ Все боты остановлены")
    
    def clear_fields(self):
        """Очищает поля ввода"""
        self.api_id_entry.delete(0, tk.END)
        self.api_hash_entry.delete(0, tk.END)
        self.phone_entry.delete(0, tk.END)
        self.password_entry.delete(0, tk.END)
        self.account_combo.set('')
        self.current_account_phone = None
        self.current_account_id = None
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
        for account_id, (client, tracker, responder, loop) in self.bots.items():
            try:
                # Пытаемся корректно остановить бота
                async def disconnect():
                    await client.disconnect()
                
                if not loop.is_closed():
                    loop.create_task(disconnect())
            except:
                pass

# Запуск
if __name__ == "__main__":
    app = TelegramBotUI()
    
    def load_saved_accounts():
        time.sleep(1)
        log_queue.put("=" * 60)
        log_queue.put("🚀 Telegram Bot Manager запущен")
        log_queue.put("=" * 60)
        log_queue.put(f"📊 Запуск программы: #{app.launch_count}")
        
        if app.launch_count == 1:
            log_queue.put("ℹ️ ПЕРВЫЙ ЗАПУСК: ручной режим")
            log_queue.put("ℹ️ При следующем запуске боты запустятся автоматически")
        else:
            log_queue.put("✅ АВТОМАТИЧЕСКИЙ РЕЖИМ: боты запустятся автоматически")
        
        log_queue.put("📋 Функционал:")
        log_queue.put("• Автоответчик с настраиваемыми фразами и интервалом")
        log_queue.put("• Эффект печати для ВАШИХ сообщений (настраиваемая скорость)")
        log_queue.put("• Фильтрация сообщений от ботов (username заканчивается на 'bot')")
        log_queue.put("• Не отвечать если бот написал последним (настраиваемое время)")
        log_queue.put("• Дополнительные функции автоответчика")
        log_queue.put("• Статусы отправки файлов (удаляются сразу после доставки файла)")
        log_queue.put("• Отслеживание новых пользователей")
        log_queue.put("• Обновление закрепленного сообщения")
        log_queue.put("• Управление до 10 аккаунтами")
        log_queue.put("• Автоматический запуск ботов со 2+ запуска программы")
        log_queue.put("• Индивидуальные настройки API для каждого аккаунта")
        log_queue.put("• Удаление всех сохранений")
        
        sessions = app.account_manager.get_session_data()
        if sessions:
            log_queue.put(f"📱 Загружено {len(sessions)} сохраненных аккаунтов")
            
            # Сортируем аккаунты по номеру
            sorted_accounts = []
            for phone_key, data in sessions.items():
                account_number = data.get('account_number', 0)
                sorted_accounts.append((account_number, data))
            
            sorted_accounts.sort(key=lambda x: x[0])
            
            for account_number, data in sorted_accounts:
                phone = data.get('phone', '')
                name = data.get('first_name', '')
                log_queue.put(f"   {account_number}. {name} ({phone})")
            
            if app.launch_count >= 2:
                log_queue.put("🔄 Запускаю ботов автоматически...")
        else:
            log_queue.put("📭 Нет сохраненных аккаунтов. Начните с авторизации.")
        
        if app.account_manager.active_accounts:
            log_queue.put(f"✅ Авторизовано {len(app.account_manager.active_accounts)} аккаунтов")
        
        log_queue.put("🔥 Эффект печати: применяется к ВАШИМ сообщениям при включении в настройках")
        log_queue.put("🤖 Фильтрация ботов: включена (игнорирует сообщения от username с 'bot')")
        log_queue.put("📦 Статусы файлов: удаляются сразу после доставки файла")
        log_queue.put("=" * 60)
        
        # Сохраняем счетчик запусков
        app.launch_count += 1
        app.save_launch_count()
    
    # Запускаем в основном потоке через after
    app.root.after(100, load_saved_accounts)
    
    app.run()