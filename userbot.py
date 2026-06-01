import os
import sys
import json
import asyncio
import threading
from flask import Flask
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError

# ========== TOKEN VA ADMIN ID NI SHU YERGA KIRITING ==========
BOT_TOKEN = '8458434487:AAFaCK8kvCGs2-5GZc24cHv31FaLg_-ik4c'  # BotFather'dan olgan tokeningiz
ADMIN_ID = 6850166021                   # O'zingizning Telegram ID'ingiz
# ============================================================

# Tokenni tekshirish
if not BOT_TOKEN or BOT_TOKEN == '8458434487:AAFaCK8kvCGs2-5GZc24cHv31FaLg_-ik4c':
    print("Iltimos, BOT_TOKEN ni o'zgartiring!")
    sys.exit(1)

if not ADMIN_ID or ADMIN_ID == 6850166021:
    print("Iltimos, ADMIN_ID ni o'zgartiring!")
    sys.exit(1)

# JSON sessiya fayli
STATE_FILE = '/tmp/userbot_state.json'

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {'accounts': [], 'states': {}, 'temp': {}}

def save_state(data):
    with open(STATE_FILE, 'w') as f:
        json.dump(data, f)

state = load_state()

# Bot klienti
bot = TelegramClient('bot_session', api_id=2040, api_hash='b18441a1ff607e10a989891a5462e627')
bot.start(bot_token=BOT_TOKEN)

# Inline menyu
MAIN_MENU = [
    [Button.inline('➕ Akkaunt qo\'shish', 'add_account')],
    [Button.inline('📋 Akkauntlar ro\'yxati', 'list_accounts')],
]

@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    if event.sender_id != ADMIN_ID:
        await event.reply('⛔ Ruxsat yo\'q')
        return
    await event.respond('🤖 **Userbot Manager**\nTanlang:', buttons=MAIN_MENU)

@bot.on(events.CallbackQuery)
async def callback_handler(event):
    if event.sender_id != ADMIN_ID:
        await event.answer('Ruxsat yo\'q', alert=True)
        return
    data = event.data.decode('utf-8')
    chat_id = event.chat_id

    if data == 'add_account':
        await event.edit('Akkaunt qo\'shish uchun **api_id** va **api_hash** ni quyidagi formatda yuboring:\n`123456 abcdef123456`')
        state['states'][chat_id] = 'waiting_app'
        save_state(state)

    elif data == 'list_accounts':
        accs = state.get('accounts', [])
        if not accs:
            await event.edit('Hozircha akkaunt yo\'q.', buttons=MAIN_MENU)
            return
        text = '📋 **Akkauntlar:**\n'
        btns = []
        for i, a in enumerate(accs):
            status = '✅' if a.get('active', True) else '❌'
            text += f"{i+1}. {a['phone']} {status}\n"
            btns.append([Button.inline(f"🔄 Qayta login #{i+1}", f"relogin_{i}")])
        btns.append([Button.inline('🔙 Orqaga', 'menu')])
        await event.edit(text, buttons=btns)

    elif data.startswith('relogin_'):
        idx = int(data.split('_')[1])
        state['states'][chat_id] = {'action': 'relogin_phone', 'idx': idx}
        state['temp'][chat_id] = {}
        save_state(state)
        await event.edit('📱 Shu akkaunt uchun telefon raqamini yuboring: (+998...)')

    elif data == 'menu':
        await event.edit('🤖 **Userbot Manager**\nTanlang:', buttons=MAIN_MENU)

    await event.answer()

# Matnli kiritishlar
@bot.on(events.NewMessage(func=lambda e: e.sender_id == ADMIN_ID and not e.text.startswith('/')))
async def handle_text(event):
    chat_id = event.chat_id
    text = event.text.strip()
    user_state = state['states'].get(chat_id)
    if not user_state:
        return

    if user_state == 'waiting_app':
        parts = text.split()
        if len(parts) != 2:
            await event.reply('❌ `123456 abcdef123456` formatida yuboring')
            return
        try:
            api_id = int(parts[0])
        except ValueError:
            await event.reply('❌ API ID raqam bo\'lishi kerak')
            return
        api_hash = parts[1]
        state['temp'][chat_id] = {'api_id': api_id, 'api_hash': api_hash}
        state['states'][chat_id] = 'waiting_phone'
        save_state(state)
        await event.reply('📱 Telefon raqamini xalqaro formatda yuboring (+998...)')

    elif user_state == 'waiting_phone':
        phone = text
        temp = state['temp'].get(chat_id, {})
        api_id = temp.get('api_id')
        api_hash = temp.get('api_hash')
        if not api_id or not api_hash:
            await event.reply('Avval API ma\'lumotlarni kiriting. /start')
            return
        try:
            client = TelegramClient(StringSession(), api_id, api_hash)
            await client.connect()
            await client.send_code_request(phone)
        except Exception as e:
            await event.reply(f'❌ Xatolik: {e}')
            del state['states'][chat_id]
            save_state(state)
            return
        state['temp'][chat_id].update({
            'client_session': client.session.save(),
            'phone': phone
        })
        state['states'][chat_id] = 'waiting_code'
        save_state(state)
        await event.reply('📞 Kod so\'raldi. Iltimos, telefoningizga kelgan kodni yuboring:')

    elif user_state == 'waiting_code':
        code = text
        temp = state['temp'].get(chat_id, {})
        sess_str = temp.get('client_session')
        phone = temp.get('phone')
        api_id = temp.get('api_id')
        api_hash = temp.get('api_hash')
        if not sess_str:
            await event.reply('Xatolik: sessiya topilmadi. /start')
            return
        try:
            client = TelegramClient(StringSession(sess_str), api_id, api_hash)
            await client.connect()
            await client.sign_in(phone, code)
        except SessionPasswordNeededError:
            await event.reply('Ikki bosqichli tekshiruv paroli kerak. Uni yuboring:')
            state['states'][chat_id] = 'waiting_password'
            save_state(state)
            return
        except PhoneCodeInvalidError:
            await event.reply('❌ Kod noto\'g\'ri yoki muddati o\'tgan.')
            del state['states'][chat_id]
            save_state(state)
            return
        except Exception as e:
            await event.reply(f'❌ Xatolik: {e}')
            del state['states'][chat_id]
            save_state(state)
            return
        me = await client.get_me()
        new_sess = client.session.save()
        state['accounts'].append({
            'phone': phone,
            'session': new_sess,
            'api_id': api_id,
            'api_hash': api_hash,
            'active': True
        })
        del state['states'][chat_id]
        del state['temp'][chat_id]
        save_state(state)
        await event.reply(f'✅ Akkaunt muvaffaqiyatli ulandi!\nIsm: {me.first_name}\nTelefon: {phone}', buttons=MAIN_MENU)

    elif user_state == 'waiting_password':
        password = text
        temp = state['temp'].get(chat_id, {})
        sess_str = temp.get('client_session')
        api_id = temp.get('api_id')
        api_hash = temp.get('api_hash')
        if not sess_str:
            await event.reply('Xatolik: sessiya topilmadi.')
            return
        try:
            client = TelegramClient(StringSession(sess_str), api_id, api_hash)
            await client.connect()
            await client.sign_in(password=password)
        except Exception as e:
            await event.reply(f'❌ Xatolik: {e}')
            del state['states'][chat_id]
            save_state(state)
            return
        me = await client.get_me()
        new_sess = client.session.save()
        state['accounts'].append({
            'phone': temp['phone'],
            'session': new_sess,
            'api_id': api_id,
            'api_hash': api_hash,
            'active': True
        })
        del state['states'][chat_id]
        del state['temp'][chat_id]
        save_state(state)
        await event.reply(f'✅ Akkaunt ulandi!\nIsm: {me.first_name}', buttons=MAIN_MENU)

    # Qayta login
    elif isinstance(user_state, dict) and user_state.get('action') == 'relogin_phone':
        phone = text
        idx = user_state['idx']
        acc = state['accounts'][idx]
        try:
            client = TelegramClient(StringSession(acc['session']), acc['api_id'], acc['api_hash'])
            await client.connect()
            await client.send_code_request(phone)
        except Exception as e:
            await event.reply(f'❌ {e}')
            return
        state['temp'][chat_id] = {'client': client, 'phone': phone, 'idx': idx}
        state['states'][chat_id] = {'action': 'relogin_code', 'idx': idx}
        save_state(state)
        await event.reply('📞 Kod so\'raldi. Kodni yuboring:')

    elif isinstance(user_state, dict) and user_state.get('action') == 'relogin_code':
        code = text
        temp = state['temp'].get(chat_id, {})
        client = temp.get('client')
        phone = temp.get('phone')
        idx = temp.get('idx')
        try:
            await client.sign_in(phone, code)
        except SessionPasswordNeededError:
            await event.reply('Ikki bosqichli parolni yuboring:')
            state['states'][chat_id] = {'action': 'relogin_password', 'idx': idx}
            save_state(state)
            return
        except Exception as e:
            await event.reply(f'❌ {e}')
            return
        me = await client.get_me()
        state['accounts'][idx]['session'] = client.session.save()
        state['accounts'][idx]['active'] = True
        del state['states'][chat_id]
        del state['temp'][chat_id]
        save_state(state)
        await event.reply(f'✅ Akkaunt yangilandi: {me.first_name}', buttons=MAIN_MENU)

# Flask server
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return 'Userbot ishlamoqda'

def run_flask():
    port = int(os.environ.get('PORT', 10000))
    flask_app.run(host='0.0.0.0', port=port)

async def main():
    await bot.start()
    threading.Thread(target=run_flask, daemon=True).start()
    print('Bot ishga tushdi')
    await bot.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
