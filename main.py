import json
import tornado.web
import tornado.websocket
import tornado.ioloop
import redis
import logging
import os
import asyncio

# Настройки Redis
redis_client = redis.StrictRedis(host='localhost', port=6379, decode_responses=True)
PUBSUB_CHANNEL = "chat"

# Хранилище подключений
connections = {}

# Загрузка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s]: %(message)s")

# WebSocket обработчик
class ChatWebSocket(tornado.websocket.WebSocketHandler):
    def open(self):
        # Добавляем клиента в список подключений
        connections[self] = self
        logging.info(f"New connection from {self.request.remote_ip}")
        self.update_clients_count()

    def on_message(self, message):
        # Обрабатываем сообщение от клиента
        try:
            data = json.loads(message)
            logging.info(f"Message received: {data}")
            # Публикуем сообщение в Redis
            redis_client.publish(PUBSUB_CHANNEL, json.dumps({
                "type": "message",
                "sender": self.request.remote_ip,
                "message": data['message']
            }))
        except Exception as e:
            logging.error(f"Error processing message: {str(e)}")

    def on_close(self):
        # Удаляем клиента из списка
        if self in connections:
            del connections[self]
        logging.info(f"Connection from {self.request.remote_ip} closed.")
        self.update_clients_count()

    def update_clients_count(self):
        # Обновляем количество клиентов
        count = len(connections)
        logging.info(f"Current clients count: {count}")
        for client in connections.values():
            client.write_message(json.dumps({"type": "clients", "count": count}))

# Функция для отправки сообщений всем клиентам
async def broadcast_message(message):
    for client in connections.values():
        try:
            await client.write_message(message)
            logging.info(f"Broadcasting message: {message}")
        except Exception as e:
            logging.error(f"Error sending message to {client}: {str(e)}")

# Асинхронный подписчик на Redis
async def redis_listener():
    pubsub = redis_client.pubsub()
    pubsub.subscribe(PUBSUB_CHANNEL)
    logging.info("Subscribed to chat channel...")

    while True:
        # Ожидаем сообщение от Redis (асинхронно)
        message = await asyncio.to_thread(pubsub.get_message, ignore_subscribe_messages=True)
        if message:
            logging.info(f"Received message: {message}")
            if message['type'] == 'message':
                # Обрабатываем полученное сообщение
                message_data = json.loads(message['data'])
                await broadcast_message(message_data)

# Запуск сервера Tornado
def make_app():
    return tornado.web.Application([
        (r"/ws", ChatWebSocket),  # WebSocket обработчик
        (r"/(.*)", tornado.web.StaticFileHandler, {
            "path": os.path.dirname(__file__),  # Путь к папке с index.html
            "default_filename": "index.html",   # Главная страница
        }),
    ])

# Запуск сервера Tornado с использованием asyncio
if __name__ == "__main__":
    app = make_app()
    app.listen(8888)
    logging.info("Server started at ws://localhost:8888/ws")

    # Запуск асинхронной работы с Redis
    loop = asyncio.get_event_loop()
    loop.create_task(redis_listener())

    tornado.ioloop.IOLoop.current().start()
