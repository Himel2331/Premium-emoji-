# Telegram Custom Emoji ID Bot

Telegram `t.me/addemoji/...` or `t.me/addstickers/...` link দিলে এই bot pack-এর IDs বের করে দেয়.

## Features

- `addemoji` link থেকে `custom_emoji_id` list বের করে
- `addstickers` link থেকে `file_unique_id` list বের করে
- Render-ready health check server (`/` and `/healthz`)
- Polling mode deploy
- Long output auto-chunk করে Telegram-এ পাঠায়

## Files

- `bot.py` - main bot
- `requirements.txt` - Python dependencies
- `.env.example` - environment variables example
- `render.yaml` - Render blueprint

## Local Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python bot.py
```

## Render Deploy

1. GitHub-এ project push করুন
2. Render-এ **New +** -> **Blueprint** অথবা **Web Service** নিন
3. Repo connect করুন
4. Render যদি `render.yaml` detect করে, সেটা use করুন
5. Environment variable দিন:
   - `TELEGRAM_BOT_TOKEN`
6. Deploy দিন

## Commands

- `/start`
- `/help`
- `/commands`
- `/ping`
- `/id`
- `/ids <telegram_pack_link>`

## Example

```text
/ids https://t.me/addemoji/prem_28a5b_by_TgEmojis_bot
```

## Notes

- custom emoji pack হলে `custom_emoji_id` পাওয়া যাবে
- regular sticker pack হলে `custom_emoji_id` থাকে না, তাই `file_unique_id` return করা হবে
- output limit `MAX_OUTPUT_IDS` দিয়ে control করতে পারবেন
