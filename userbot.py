import os
import json
import asyncio
import threading
from telethon import TelegramClient, events, Button, types
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, FloodWaitError

# ========== SOZLAMALAR ==========
BOT_TOKEN = os.environ.get('BOT_TOKEN')          # BotFather tokeni
ADMIN_ID = int(os.environ.get('ADMIN_ID') or 0) # Sizning Telegram ID
# ==================================

# Oddiy JSON fayl orqali sessiyalarni saqlash (Render qayta ishga tushganda saqlanib qoladi)
STATE_FILE = 'userbot_state.json'

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {'accounts': [], 'states': {}, 'temp': {}}

def save_state(data):
    with open(STATE_FILE, 'w') as f:
        json.dump(data, f)

state = load_state()

# ---------- Bot klienti ----------
bot = TelegramClient('bot_session', api_id=2040, api_hash='b18441a1ff607e10a989891a5462e627').start(bot_token=BOT_TOKEN)

# ---------- Inline menyu ----------
MAIN_MENU = [
    [Button.inline('➕ Akkaunt qo‘shish', 'add_account')],
    [Button.inline('📋 Akkauntlar ro‘yxati', 'list_accounts')],
]

# ---------- Buyruqlar ----------
@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    if event.sender_id != ADMIN_ID:
        await event.reply('⛔ Ruxsat yo‘q')
        return
    await event.respond('🤖 **Userbot Manager**\nTanlang:', buttons=MAIN_MENU)

# ---------- Callback handler ----------
@bot.on(events.CallbackQuery)
async def callback_handler(event):
    if event.sender_id != ADMIN_ID:
        await event.answer('Ruxsat yo‘q', alert=True)
        return
    data = event.data.decode('utf-8')
    chat_id = event.chat_id

    if data == 'add_account':
        await event.edit('Akkaunt qo‘shish uchun **api_id** va **api_hash** ni quyidagi formatda yuboring:\n`123456 abcdef123456`\n\n(my.telegram.org dan oling)')
        state['states'][chat_id] = 'waiting_app'
        save_state(state)

    elif data == 'list_accounts':
        accs = state.get('accounts', [])
        if not accs:
            await event.edit('Hozircha hech qanday akkaunt yo‘q.', buttons=MAIN_MENU)
            return
        text = '📋 **Ulangan akkauntlar:**\n'
        buttons = []
        for i, acc in enumerate(accs):
            status = '✅' if acc.get('active', True) else '❌'
            text += f"{i+1}. {acc['phone']} {status}\n"
            buttons.append([Button.inline(f"🔄 Qayta login #{i+1}", f"relogin_{i}")])
        buttons.append([Button.inline('🔙 Orqaga', 'menu')])
        await event.edit(text, buttons=buttons)

    elif data.startswith('relogin_'):
        idx = int(data.split('_')[1])
        state['states'][chat_id] = {'action': 'relogin', 'account_idx': idx}
        state['temp'][chat_id] = {}
        save_state(state)
        await event.edit('📱 Shu akkaunt uchun telefon raqamini xalqaro formatda yuboring: (+998...)')
        state['states'][chat_id] = {'action': 'relogin_phone', 'account_idx': idx}
        save_state(state)

    elif data == 'menu':
        await event.edit('🤖 **Userbot Manager**\nTanlang:', buttons=MAIN_MENU)

    await event.answer()

# ---------- Xabarlar (telefon raqam, kod, api_id/api_hash) ----------
@bot.on(events.NewMessage(func=lambda e: e.sender_id == ADMIN_ID and not e.text.startswith('/')))
async def handle_text(event):
    chat_id = event.chat_id
    text = event.text.strip()
    user_state = state['states'].get(chat_id)

    if not user_state:
        return

    if user_state == 'waiting_app':
        # api_id va api_hash ni qabul qilish
        parts = text.split()
        if len(parts) != 2:
            await event.reply('❌ Noto‘g‘ri format. Iltimos, `123456 abcdef123456` ko‘rinishida yuboring')
            return
        api_id = int(parts[0])
        api_hash = parts[1]
        state['temp'][chat_id] = {'api_id': api_id, 'api_hash': api_hash}
        state['states'][chat_id] = 'waiting_phone'
        save_state(state)
        await event.reply('📱 Endi telefon raqamini xalqaro formatda yuboring (+998...)')

    elif user_state == 'waiting_phone':
        phone = text
        temp = state['temp'].get(chat_id, {})
        api_id = temp.get('api_id')
        api_hash = temp.get('api_hash')
        if not api_id or not api_hash:
            await event.reply('Avval api_id va api_hash ni kiriting. /start orqali qayta boshlang.')
            return
        # Yangi client yaratish va kod so‘rash
        client = TelegramClient(StringSession(), api_id, api_hash)
        await client.connect()
        try:
            await client.send_code_request(phone)
        except Exception as e:
            await event.reply(f'❌ Xatolik: {e}')
            await event.reply('/start orqali qayta urining.')
            del state['states'][chat_id]
            save_state(state)
            return
        # Vaqtinchalik saqlash
        state['temp'][chat_id] = {'client_session': client.session.save(), 'phone': phone, 'api_id': api_id, 'api_hash': api_hash, 'client': client}
        state['states'][chat_id] = 'waiting_code'
        save_state(state)
        await event.reply('📞 Kod so‘raldi. Iltimos, telefoningizga kelgan kodni yuboring:')

    elif user_state == 'waiting_code':
        code = text
        temp = state['temp'].get(chat_id, {})
        session_str = temp.get('client_session')
        phone = temp.get('phone')
        api_id = temp.get('api_id')
        api_hash = temp.get('api_hash')
        if not session_str:
            await event.reply('Xatolik: oldin telefon raqamni kiriting.')
            return
        client = TelegramClient(StringSession(session_str), api_id, api_hash)
        await client.connect()
        try:
            await client.sign_in(phone, code)
        except SessionPasswordNeededError:
            await event.reply('Ikki bosqichli tekshiruv paroli kerak. Uni yuboring:')
            state['states'][chat_id] = 'waiting_password'
            save_state(state)
            return
        except PhoneCodeInvalidError:
            await event.reply('❌ Kod noto‘g‘ri. Qayta urining yoki /start.')
            del state['states'][chat_id]
            save_state(state)
            return
        except Exception as e:
            await event.reply(f'❌ Xatolik: {e}')
            del state['states'][chat_id]
            save_state(state)
            return
        me = await client.get_me()
        sess_str = client.session.save()
        # Akkauntni qo‘shish
        state['accounts'].append({'phone': phone, 'session': sess_str, 'active': True})
        del state['states'][chat_id]
        del state['temp'][chat_id]
        save_state(state)
        await event.reply(f'✅ Akkaunt muvaffaqiyatli ulandi!\nTelefon: {phone}\nIsm: {me.first_name}', buttons=MAIN_MENU)

    elif isinstance(user_state, dict) and user_state.get('action') == 'relogin_phone':
        phone = text
        idx = user_state['account_idx']
        acc = state['accounts'][idx]
        client = TelegramClient(StringSession(acc['session']), acc.get('api_id'), acc.get('api_hash'))
        await client.connect()
        try:
            await client.send_code_request(phone)
        except Exception as e:
            await event.reply(f'❌ {e}')
            del state['states'][chat_id]
            save_state(state)
            return
        state['temp'][chat_id] = {'client': client, 'phone': phone, 'account_idx': idx}
        state['states'][chat_id] = {'action': 'relogin_code', 'account_idx': idx}
        save_state(state)
        await event.reply('📞 Kod so‘raldi. Kodni yuboring:')

    elif isinstance(user_state, dict) and user_state.get('action') == 'relogin_code':
        code = text
        idx = user_state['account_idx']
        temp = state['temp'].get(chat_id, {})
        client = temp.get('client')
        phone = temp.get('phone')
        if not client:
            await event.reply('Xatolik')
            return
        try:
            await client.sign_in(phone, code)
        except SessionPasswordNeededError:
            await event.reply('Ikki bosqichli parolni yuboring:')
            state['states'][chat_id] = {'action': 'relogin_password', 'account_idx': idx}
            save_state(state)
            return
        except Exception as e:
            await event.reply(f'❌ {e}')
            del state['states'][chat_id]
            save_state(state)
            return
        sess_str = client.session.save()
        state['accounts'][idx]['session'] = sess_str
        state['accounts'][idx]['active'] = True
        del state['states'][chat_id]
        del state['temp'][chat_id]
        save_state(state)
        await event.reply('✅ Akkaunt qayta tiklandi.', buttons=MAIN_MENU)

    elif isinstance(user_state, dict) and user_state.get('action') == 'relogin_password':
        password = text
        idx = user_state['account_idx']
        temp = state['temp'].get(chat_id, {})
        client = temp.get('client')
        if not client:
            await event.reply('Xatolik')
            return
        try:
            await client.sign_in(password=password)
        except Exception as e:
            await event.reply(f'❌ {e}')
            del state['states'][chat_id]
            save_state(state)
            return
        sess_str = client.session.save()
        state['accounts'][idx]['session'] = sess_str
        state['accounts'][idx]['active'] = True
        del state['states'][chat_id]
        del state['temp'][chat_id]
        save_state(state)
        await event.reply('✅ Akkaunt qayta tiklandi.', buttons=MAIN_MENU)

# ---------- Flask server (Render.com uchun) ----------
from flask import Flask
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return 'Userbot ishlamoqda'

def run_flask():
    flask_app.run(host='0.0.0.0', port=10000)

# ---------- Asosiy ishga tushirish ----------
async def main():
    await bot.start()
    print('Bot ishga tushdi...')
    threading.Thread(target=run_flask, daemon=True).start()
    await bot.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
