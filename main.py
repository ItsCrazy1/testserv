# -*- coding: utf-8 -*-
import time
import datetime as dt
import json
import os
from threading import Thread
import requests
import psycopg2
import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
from vk_api.utils import get_random_id

# Запись времени запуска для измерения времени безотказной работы
START_TIME = dt.datetime.now()
# Инициализация настроек
try:
    with open('config.json', 'r', encoding='utf8') as file:
        config = json.load(file)
        group_api_token = config['group']['api_token']
        group_id = config['group']['id']
        postgresql_db_url = config['postgresql_db_url']
        poll_interval = config['additional']['poll_interval']
        min_test_users_count = config['additional']['min_test_users_count']
        description = config['description']
except FileNotFoundError:
    with open('config.json', 'w', encoding='utf8') as file:
        group_api_token = input('Input a VK group access token: ')
        group_id = input('Input a VK group ID: ')
        postgresql_db_url = input('Input a PostgreSQL DB URL: ')
        poll_interval = 60
        min_test_users_count = 150
        description = "Cправка по командам\n\nКоманда: + (подписаться, subscribe, подписка)\nОписание: позволяет подписаться на рассылку уведомлений об открытии тестовых серверов ТО\n\nКоманда: - (отписаться, unsubscribe, отписка)\nОписание: позволяет отписаться от рассылки уведомлений об открытии тестовых серверов ТО\n\nКоманда: ТестСервер (тест, testserver, test)\nОписание: показывает список тестовых серверов Танков Онлайн и количество игроков\n\nКоманда: пинг (ping)\nОписание: проверяет работоспособность бота"
        config = {
                    "group": {
                        "api_token": group_api_token,
                        "id": group_id
                        },
                    "additional": {
                        "poll_interval": poll_interval,
                        "min_test_users_count": min_test_users_count
                        },
                    "postgresql_db_url": postgresql_db_url,
                    "description": description
                }
        json.dump(config, file, indent=4)

# Подключение к БД PostgreSQL
try:
    DATABASE_URL = os.environ['DATABASE_URL']
except KeyError:
    DATABASE_URL = postgresql_db_url
conn = psycopg2.connect(DATABASE_URL, sslmode='require')
cursor = conn.cursor()


def td_format(td_object):
    """Функция принимает объект datetime.datetime.timedelta и возвращает строку"""
    seconds = int(td_object.total_seconds())
    periods = [
        ('',        60*60*24*365),
        ('месяц',       60*60*24*30),
        ('д',         60*60*24),
        ('час',        60*60),
        ('минут',      60),
        ('секунд',      1)
    ]

    strings=[]
    for period_name, period_seconds in periods:
        if seconds > period_seconds:
            period_value, seconds = divmod(seconds, period_seconds)
            if (period_name == 'секунд') or (period_name == 'минут'):
                tens = period_value % 10
                if (10 < period_value < 20) or (tens == 0) or (4 < tens < 10):
                    ending = ''
                elif 1 < tens < 5:
                    ending = 'ы'
                else:
                    ending = 'а'
            elif period_name == 'час':
                tens = period_value % 10
                if (10 < period_value < 20) or (tens == 0) or (4 < tens < 10):
                    ending = 'ов'
                elif 1 < tens < 5:
                    ending = 'а'
                else:
                    ending = ''
            elif period_name == 'д':
                tens = period_value % 10
                if (10 < period_value < 20) or (tens == 0) or (4 < tens < 10):
                    ending = 'ней'
                elif 1 < tens < 5:
                    ending = 'ня'
                else:
                    ending = 'ень'
            elif period_name == 'месяц':
                tens = period_value % 10
                if (10 < period_value < 20) or (tens == 0) or (4 < tens < 10):
                    ending = 'ев'
                elif 1 < tens < 5:
                    ending = 'а'
                else:
                    ending = ''
            elif period_name == '':
                tens = period_value % 10
                if (10 < period_value < 20) or (tens == 0) or (4 < tens < 10):
                    ending = 'лет'
                elif 1 < tens < 5:
                    ending = 'года'
                else:
                    ending = 'год'
            strings.append('{} {}{}'.format(period_value, period_name, ending))

    return ", ".join(strings)


def makeMailing(user_ids, message):
    """Функция для рассылки сообщения пользователям от имени группы"""
    n = 100  # Макс. количество идентификаторов пользователей в одном запросе
    for i in range(0, len(user_ids), n):
        sub_user_ids = user_ids[i:i+n]
        vk.messages.send(
            user_ids=sub_user_ids,
            message=message,
            random_id=get_random_id()
            )


class BotKeyboards(object):
    """Набор клавиатур бота"""
    def __init__(self):
        self.defaultKeyboard = self.getDefaultKeyboard()

    def getDefaultKeyboard(self):
        """Функция возвращает клавиатуру с основными командами"""
        keyboard = VkKeyboard()
        keyboard.add_button('ТестСервер', VkKeyboardColor.PRIMARY)
        keyboard.add_line()
        keyboard.add_button('Подписаться', VkKeyboardColor.POSITIVE)
        keyboard.add_button('Отписаться', VkKeyboardColor.NEGATIVE)
        return keyboard.get_keyboard()

# Наследованные классы для обработки исключений, связанных с обрывом соединения
class MyVkBotLongPoll(VkBotLongPoll):
    def listen(self):
        while True:
            try:
                for event in self.check():
                    yield event
            except Exception as e:
                print('Error in Bot LongPoll was excepted:', e)


def CommandMessageHandler(text, event=None, from_id=None,
                          from_chat=False, from_user=False):
    reply = ''
    params = {}
    if text.startswith(('ping', 'пинг')):
        uptime = td_format(dt.datetime.now() - START_TIME)
        reply = '>> понг\n🆙 Время безотказной работы: {}'.format(uptime)
    elif text.startswith(('help', 'помощь', 'команды', 'commands', 'справка', 'начать')):
        reply = description
    elif text.startswith(('тотест', 'тест', 'totest', 'test', 'тестсервер', 'testserver', 'сервер')):
        r = requests.get('https://test.tankionline.com/public_test').json()
        reply = 'https://test.tankionline.com'
        for i in range(len(r)):
            n = i + 1
            s = r[i]
            Users = s["UserCount"]
            reply += '\n{}. Сервер [{}]'.format(n, Users)
            if Users > min_test_users_count:
                reply += '✅'
    elif text.startswith(('подписаться', 'subscribe', '+', 'подписка')):
        user_id = from_id
        cursor.execute('SELECT vk_user_id, sb_testserver_releases \
                        FROM subscribers \
                        WHERE vk_user_id = %s', (user_id,))
        r = cursor.fetchone()
        if r and r[1]:
            reply = 'Вы уже подписаны на уведомления об открытии тестовых серверов'
        else:
            if r and not r[1]:
                cursor.execute('UPDATE subscribers \
                                SET sb_testserver_releases = true \
                                WHERE vk_user_id = %s', (user_id,))
            else:
                cursor.execute('INSERT INTO subscribers (vk_user_id, sb_testserver_releases) \
                                VALUES (%s, true)', (user_id,))
            conn.commit()
            reply = 'Вы подписались на рассылку уведомлений об открытии тестовых серверов Танков Онлайн'
    elif text.startswith(('отписаться', 'unsubscribe', '-', 'отписка')):
        user_id = from_id
        cursor.execute('SELECT vk_user_id, sb_testserver_releases \
                        FROM subscribers \
                        WHERE vk_user_id = %s', (user_id,))
        r = cursor.fetchone()
        if r and r[1]:
            cursor.execute('UPDATE subscribers \
                            SET sb_testserver_releases = false \
                            WHERE vk_user_id = %s', (user_id,))
            conn.commit()
            reply = 'Вы отписались от рассылки уведомлений об открытии тестовых серверов Танков Онлайн'
        else:
            reply = 'Невозможно отписаться: вы не подписаны'
    elif not from_chat:
        reply = 'Команда не найдена. Чтобы получить справку, отправьте "Справка"'

    return reply, params


# Модуль-обработчик сообщений бота
class GroupMessageHandler(Thread):
    def __init__(self, vk_session, group_id):
        Thread.__init__(self)
        self.vk_session = vk_session
        self.group_id = group_id

    def run(self):
        vk = self.vk_session.get_api()
        longpoll = MyVkBotLongPoll(self.vk_session, self.group_id)

        for event in longpoll.listen():
            if event.type == VkBotEventType.MESSAGE_NEW:
                # Обработка личных сообщений
                if event.from_user:
                    if event.obj.text.startswith('!'):
                        text = event.obj.text[1:].lower()
                    else:
                        text = event.obj.text.lower()
                    reply, params = CommandMessageHandler(text, event, event.obj.from_id, from_user=True)
                    if reply:
                        native_params = {'user_id': event.obj.from_id, 'message': reply, 'keyboard': keyboards.defaultKeyboard, 'random_id': get_random_id()}
                        native_params.update(params)
                        vk.messages.send(**native_params)


# Модуль для проверки тестовых серверов ТО
class TOTestChecker(Thread):
    def __init__(self, vk_session):
        Thread.__init__(self)
        self.vk_session = vk_session

    def run(self):
        vk = self.vk_session.get_api()
        Open_Test_Servers = []
        while True:
            try:
                r = requests.get('https://test.tankionline.com/public_test').json()
            except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
                print('Error in TOTestChecker was excepted:', e)
                continue
            for i in range(len(r)):
                n = i + 1
                test_server = r[i]
                if test_server["UserCount"] > min_test_users_count:
                    if n not in Open_Test_Servers:
                        Open_Test_Servers.append(n)
                        # Рассылка уведомления подписчикам
                        reply = 'Кажется, тестовый сервер №{} открыт [{}].\nhttps://test.tankionline.com'.format(n, test_server["UserCount"])
                        cursor.execute('SELECT array_agg(vk_user_id) \
                                        FROM subscribers \
                                        WHERE sb_testserver_releases = true')
                        vk_user_ids = cursor.fetchone()[0]
                        if vk_user_ids:
                            makeMailing(vk_user_ids, reply)

                else:
                    if n in Open_Test_Servers:
                        Open_Test_Servers.remove(n)
                Open_Test_Servers = list(filter(lambda x: x <= len(r), Open_Test_Servers))
            time.sleep(poll_interval)


if __name__ == '__main__':
    # Авторизация аккаунта и группы
    vk_group_session = vk_api.VkApi(token=group_api_token)
    vk = vk_group_session.get_api()

    # Инициализация клавиатур бота
    keyboards = BotKeyboards()

    # Запуск модулей
    chatBot = GroupMessageHandler(vk_group_session, group_id)
    tests = TOTestChecker(vk_group_session)
    chatBot.start()
    tests.start()
