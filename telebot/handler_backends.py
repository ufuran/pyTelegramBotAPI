import os
import pickle
import threading

from telebot import apihelper


class HandlerBackend(object):
    """
    Class for saving (next step|reply) handlers
    """
    def __init__(self, handlers=None):
        if handlers is None:
            handlers = {}
        self.handlers = handlers

    def register_handler(self, handler_group_id, handler):
        raise NotImplementedError()

    def clear_handlers(self, handler_group_id):
        raise NotImplementedError()

    def get_handlers(self, handler_group_id):
        raise NotImplementedError()


class MemoryHandlerBackend(HandlerBackend):
    def register_handler(self, handler_group_id, handler):
        if handler_group_id in self.handlers:
            self.handlers[handler_group_id].append(handler)
        else:
            self.handlers[handler_group_id] = [handler]

    def clear_handlers(self, handler_group_id):
        self.handlers.pop(handler_group_id, [])

    def get_handlers(self, handler_group_id):
        return self.handlers.pop(handler_group_id, [])


class FileHandlerBackend(HandlerBackend):
    def __init__(self, handlers=None, filename='./.handler-saves/handlers.save', delay=120):
        super(FileHandlerBackend, self).__init__(handlers)
        self.filename = filename
        self.delay = delay
        self.timer = threading.Timer(delay, self.save_handlers)

    def register_handler(self, handler_group_id, handler):
        if handler_group_id in self.handlers:
            self.handlers[handler_group_id].append(handler)
        else:
            self.handlers[handler_group_id] = [handler]

        self.start_save_timer()

    def clear_handlers(self, handler_group_id):
        self.handlers.pop(handler_group_id, [])

        self.start_save_timer()

    def get_handlers(self, handler_group_id):
        handlers = self.handlers.pop(handler_group_id, [])

        self.start_save_timer()

        return handlers

    def start_save_timer(self):
        if not self.timer.is_alive():
            if self.delay <= 0:
                self.save_handlers()
            else:
                self.timer = threading.Timer(self.delay, self.save_handlers)
                self.timer.start()

    def save_handlers(self):
        self.dump_handlers(self.handlers, self.filename)

    def load_handlers(self, filename=None, del_file_after_loading=True):
        if not filename:
            filename = self.filename
        tmp = self.return_load_handlers(filename, del_file_after_loading=del_file_after_loading)
        if tmp is not None:
            self.handlers.update(tmp)

    @staticmethod
    def dump_handlers(handlers, filename, file_mode="wb"):
        dirs = filename.rsplit('/', maxsplit=1)[0]
        os.makedirs(dirs, exist_ok=True)

        with open(filename + ".tmp", file_mode) as file:
            if (apihelper.CUSTOM_SERIALIZER is None):
                pickle.dump(handlers, file)
            else:
                apihelper.CUSTOM_SERIALIZER.dump(handlers, file)

        if os.path.isfile(filename):
            os.remove(filename)

        os.rename(filename + ".tmp", filename)

    @staticmethod
    def return_load_handlers(filename, del_file_after_loading=True):
        if os.path.isfile(filename) and os.path.getsize(filename) > 0:
            with open(filename, "rb") as file:
                if (apihelper.CUSTOM_SERIALIZER is None):
                    handlers = pickle.load(file)
                else:
                    handlers = apihelper.CUSTOM_SERIALIZER.load(file)

            if del_file_after_loading:
                os.remove(filename)

            return handlers


class RedisHandlerBackend(HandlerBackend):
    def __init__(self, handlers=None, host='localhost', port=6379, db=0, prefix='telebot'):
        super(RedisHandlerBackend, self).__init__(handlers)
        from redis import Redis
        self.prefix = prefix
        self.redis = Redis(host, port, db)

    def _key(self, handle_group_id):
        return ':'.join((self.prefix, str(handle_group_id)))

    def register_handler(self, handler_group_id, handler):
        handlers = []
        value = self.redis.get(self._key(handler_group_id))
        if value:
            handlers = pickle.loads(value)
        handlers.append(handler)
        self.redis.set(self._key(handler_group_id), pickle.dumps(handlers))

    def clear_handlers(self, handler_group_id):
        self.redis.delete(self._key(handler_group_id))

    def get_handlers(self, handler_group_id):
        handlers = []
        value = self.redis.get(self._key(handler_group_id))
        if value:
            handlers = pickle.loads(value)
            self.clear_handlers(handler_group_id)

        return handlers


class MongoHandlerBackend(HandlerBackend):
    def __init__(self, host, port, username, password, auth_source, collection, handlers=None):
        super().__init__(handlers)
        from pymongo import MongoClient
        self.client = MongoClient(host, port, username=username, password=password, authSource=auth_source)
        self.db = self.client[auth_source]
        self.collection = self.db[collection]

    def register_handler(self, handler_group_id, handler):
        from bson import Binary
        handlers = []
        value = self.collection.find_one({'user_id': handler_group_id})
        if value:
            handlers = pickle.loads(value['handlers'])
        handlers.append(handler)
        self.collection.update_one({'user_id': handler_group_id}, {'$set': {'handlers': Binary(pickle.dumps(handlers))}}, upsert=True)

    def clear_handlers(self, handler_group_id):
        self.collection.delete_one({'user_id': handler_group_id})

    def get_handlers(self, handler_group_id):
        handlers = []
        value = self.collection.find_one({'user_id': handler_group_id})
        if value:
            try:
                handlers = pickle.loads(value['handlers'])
            except:
                pass
            self.clear_handlers(handler_group_id)

        return handlers
