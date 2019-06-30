# discrod.py

This was created for learning purposes. Doesn't abstract what discord sends. It does do rate limiting, so if you do wish to use it, here is an example of an echo bot:

```python
import discrod

bot = discrod.Bot(TOKEN)

@bot.on_ready
def ready(data):
    print("{}#{} has started.".format(bot.user["username"], bot.user["discriminator"]))

@bot.on_message
def message(data):
    if data["author"]["id"] != bot.user["id"]:
        bot.send_message(data["channel_id"], data["content"])
```
