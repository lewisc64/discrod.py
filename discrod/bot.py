from threading import Thread
import requests
import json
import time
import random
import logging

from . import HTTP_API_ENDPOINT
from .gateway import *

class Bot:
    
    def __init__(self, token, shards=1):
        
        self._token = token
        self.user = None

        self._auth_header = "Bot {}".format(self._token)
        
        self._rate_limits = {
            "channel": {}
        }

        self._sockets = []

        for shard in range(shards):
            self._sockets.append(Gateway(self._token, shard, shards))

        self.add_listener(Gateway.DISPATCH, self._ready, event_type="READY")

    def _ready(self, data):
        if self.user is None:
            self.user = data["user"]

    def add_listener(self, opcode, func, event_type=None, pass_data=True, temp=False):
        for socket in self._sockets:
            socket.add_listener(opcode, func, event_type=event_type, pass_data=pass_data, temp=temp)

    def on_message(self, func):
        return self.add_listener(Gateway.DISPATCH, func, event_type="MESSAGE_CREATE")

    def on_ready(self, func):
        return self.add_listener(Gateway.DISPATCH, func, event_type="READY")

    def _init_limits(self, data, key):
        data[key] = {"calls_remaining": 1, "reset_time": 0, "usage_queue": []}

    def _reset_limits_from_headers(self, limits, headers):
        if "X-RateLimit-Remaining" in headers:
            limits["calls_remaining"] = int(headers["X-RateLimit-Remaining"])
        if "X-RateLimit-Reset" in headers:
            limits["reset_time"] = int(headers["X-RateLimit-Reset"])
        limits["usage_queue"].pop(0)

    def _wait_for_limits(self, limits):

        n = random.randint(1000000, 9999999)
        limits["usage_queue"].append(n)
        
        while limits["usage_queue"][0] != n:
            pass

        if limits["calls_remaining"] <= 0:
            while time.time() < limits["reset_time"]:
                pass

    def _rate_limit_channel_request(self, channel_id):
        if channel_id not in self._rate_limits["channel"]:
            self._init_limits(self._rate_limits["channel"], channel_id)
        self._wait_for_limits(self._rate_limits["channel"][channel_id])

    def _request(self, method_func, path, headers=None, body=None, auth=True):

        if headers is None and auth:
            headers = {
                "authorization": self._auth_header
            }
            if body is not None:
                headers["content-type"] = "application/json"

        if path[0] != "/":
            full_path = HTTP_API_ENDPOINT + "/" + path
        else:
            full_path = HTTP_API_ENDPOINT + path

        if body is None:
            r = method_func(full_path, headers=headers)
        else:
            r = method_func(full_path, headers=headers, data=json.dumps(body))
        
        if r.status_code != 200 and r.status_code != 204:
            logging.warning("{} {}".format(r.status_code, r.reason))

        return r
    
    def send_message(self, channel_id, content):

        if len(content) <= 0 or len(content) > 2000:
            raise ValueError("Message length must be > 0 and <= 2000.")

        self._rate_limit_channel_request(channel_id)

        body = {
            "content": content,
            "tts": False
        }

        r = self._request(requests.post, "/channels/{}/messages".format(channel_id), body=body)
        self._reset_limits_from_headers(self._rate_limits["channel"][channel_id], r.headers)

        return r.json()

    def edit_message(self, channel_id, message_id, content):
        
        if len(content) <= 0 or len(content) > 2000:
            raise ValueError("Message length must be > 0 and <= 2000.")

        self._rate_limit_channel_request(channel_id)

        body = {
            "content": content
        }

        r = self._request(requests.patch, "/channels/{}/messages/{}".format(channel_id, message_id), body=body)
        self._reset_limits_from_headers(self._rate_limits["channel"][channel_id], r.headers)

        return r.json()
    
    def send_typing(self, channel_id):
        self._rate_limit_channel_request(channel_id)
        r = self._request(requests.post, "/channels/{}/typing".format(channel_id))
        self._reset_limits_from_headers(self._rate_limits["channel"][channel_id], r.headers)

    def modify_channel(self, channel_id, **settings):
        """ Settings kwargs can have the values listed here: https://ptb.discordapp.com/developers/docs/resources/channel#modify-channel """
        
        self._rate_limit_channel_request(channel_id)
        r = self._request(requests.patch, "/channels/{}".format(channel_id), body=settings)
        self._reset_limits_from_headers(self._rate_limits["channel"][channel_id], r.headers)

    def delete_channel(self, channel_id):
        self._rate_limit_channel_request(channel_id)
        r = self._request(requests.delete, "/channels/{}".format(channel_id))
        self._reset_limits_from_headers(self._rate_limits["channel"][channel_id], r.headers)
    
    def get_channel(self, channel_id):
        return self._request(requests.get, "channels/{}".format(channel_id)).json()

    def get_channel_messages(self, channel_id, limit=50, delay=0.5):
        self._rate_limit_channel_request(channel_id)

        messages = []
        before = None
        
        while limit > 0 or limit == -1:
            
            get_url = "channels/{}/messages?limit={}".format(channel_id, min(100, 100 if limit == -1 else limit))
            if before is not None:
                get_url += "&before={}".format(before)

            r = self._request(requests.get, get_url)
            
            data = r.json()
            
            if r.status_code == 429:
                time.sleep(int(data["retry_after"]) / 1000)
                
            else:
                messages.extend(data)
                before = messages[-1]["id"]
                if len(data) < 100:
                    break
                time.sleep(delay)
                if limit > 0:
                    limit -= 100
        
        self._reset_limits_from_headers(self._rate_limits["channel"][channel_id], r.headers)
        
        return messages[::-1]

    def logout(self):
        for socket in self._sockets:
            socket.close()

