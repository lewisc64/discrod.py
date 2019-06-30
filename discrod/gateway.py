from threading import Thread
import websocket
import sys
import json
import time
import logging

from . import WS_API_ENDPOINT

class Gateway:

    DISPATCH = 0
    HEARTBEAT = 1
    IDENTIFY = 2
    STATUS_UPDATE = 3
    VOICE_STATE_UPDATE = 4
    RESUME = 6
    RECONNECT = 7
    REQUEST_GUILD_MEMBERS = 8
    INVALID_SESSION = 9
    HELLO = 10
    HEARTBEAT_ACK = 11
    
    def __init__(self, token, shard_number=0, shard_count=1):
        self._token = token
        self.log_socket_messages = True

        self.shard_number = shard_number
        self.shard_count = shard_count

        self._identify = {
            "token": self._token,
            "shard": [shard_number, shard_count],
            "properties": {
                "$os": sys.platform,
                "$browser": "python",
                "$device": "python",
                "$referrer": "",
                "$referring_domain": ""
            },
        }

        self._session_id = None
        self._sequence = None
        self._listeners = {}

        self.add_listener(Gateway.HELLO, self._setup)
        self.add_listener(Gateway.DISPATCH, self._ready, event_type="READY")
        self.add_listener(Gateway.HEARTBEAT_ACK, self._heart, pass_data=False)
        self.add_listener(Gateway.RECONNECT, self._reconnect, pass_data=False)
        self.add_listener(Gateway.INVALID_SESSION, lambda: logging.warning("{} has an invalid session.".format(self.get_name())), pass_data=False)
        self.add_listener(Gateway.INVALID_SESSION, self._reconnect, pass_data=False)

        self._ws = websocket.WebSocketApp(WS_API_ENDPOINT)
        self._ws.on_message = self._on_message

        logging.info("{} is connecting.".format(self.get_name()))
        self._ws_thread = Thread(target=self._ws.run_forever, name=self.get_name())
        self._ws_thread.start()

    def get_name(self):
        return "SHARD-{}".format(self.shard_number)

    def send_json(self, data):
        self._ws.send(json.dumps(data))
        if self.log_socket_messages:
            logging.debug("{} SENT: {}".format(self.get_name(), data))

    def _ready(self, data):
        
        logging.info("{} is ready.".format(self.get_name()))
        
        self._session_id = data["session_id"]
        
        self.send_json({
            "op": Gateway.HEARTBEAT,
            "d": self._sequence
        })

    def _heart(self):

        session = self._session_id
        
        time.sleep(self.heartbeat_interval / 1000)
        
        if session != self._session_id:
            logging.warning("{}'s session changed while waiting. Dropping heartbeat.".format(self.get_name()))
            return
        
        try:
            self.send_json({"op":Gateway.HEARTBEAT, "d":self._sequence})
        except:
            logging.warning("{} is experiencing a cardiac arrest!".format(self.get_name()))

        self.last_heartbeat = time.time()

    def _setup(self, data):
        self.heartbeat_interval = data["heartbeat_interval"]
        self.send_json({
            "op": Gateway.IDENTIFY,
            "d": self._identify
        })
    
    def _on_message(self, message):
        
        data = json.loads(message)
        self._sequence = data["s"]

        if self.log_socket_messages:
            logging.debug("{} RECIEVED: {}".format(self.get_name(), data))

        if data["op"] in self._listeners:
            for listener in self._listeners[data["op"]]:
                if listener["t"] == data["t"]:
                    name = "Listener-{}".format(data["op"])
                    if listener["t"] is not None:
                        name += "-" + listener["t"]
                    if listener["pass_data"]:
                        Thread(target=listener["func"], args=(data["d"],), name=name, daemon=True).start()
                    else:
                        Thread(target=listener["func"], name=name, daemon=True).start()
                    if listener["temp"]:
                        self._listeners[data["op"]].remove(listener)

    def _reconnect(self):
        logging.warning("{} is reconnecting.".format(self.get_name()))
        self._ws.close()

        #self.add_listener(Gateway.HELLO, lambda: self.send_json({
        #    "op": Gateway.RESUME,
        #    "d": {
        #      "token": self._token,
        #      "session_id": self._session_id,
        #      "seq": self._sequence
        #    }
        #}), pass_data=False, temp=True)
        
        self._ws.run_forever()

    def add_listener(self, opcode, func, event_type=None, pass_data=True, temp=False):
        
        if opcode not in self._listeners:
            self._listeners[opcode] = []
        
        self._listeners[opcode].append({
            "t": event_type,
            "func":func,
            "pass_data": pass_data,
            "temp": temp
        })

    def close(self):
        self._ws.close()

