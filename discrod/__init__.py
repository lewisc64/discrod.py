import requests

HTTP_API_ENDPOINT = "https://discordapp.com/api/v6"
WS_API_ENDPOINT = requests.get(HTTP_API_ENDPOINT + "/gateway").json()["url"]

from .bot import *
from .gateway import *

