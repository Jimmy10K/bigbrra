# Biglobe Validator

Un validateur SMTP professionnel pour les comptes Biglobe.

## Fonctionnalités
- Validation Biglobe rapide et fiable
- Connexion sécurisée SSL/TLS
- Support du format email:password
- Résultats sauvegardés proprement
- Multi-threading pour plus de vitesse
- Notifications Telegram en temps réel
- Statistiques détaillées

## Installation sur VPS Debian 12
```bash
# Mise à jour du système
apt update && apt upgrade -y

# Installation des dépendances
apt install python3 python3-pip python3-venv git -y

# Création du dossier
mkdir -p /opt/biglobe
cd /opt/biglobe

# Téléchargement du programme
wget https://raw.githubusercontent.com/JYMMI10K/biglobe/main/main.py

# Création de l'environnement virtuel
python3 -m venv venv
source venv/bin/activate

# Installation des dépendances Python
pip install python-telegram-bot

# Création du fichier de configuration
nano .env
```

## Configuration
Créez un fichier `.env` avec :
```
TELEGRAM_BOT_TOKEN=votre_token
TELEGRAM_CHAT_ID=votre_chat_id
```

## Utilisation
```bash
python3 main.py
```

## Service Systemd
```bash
# Création du service
nano /etc/systemd/system/biglobe.service
```

Contenu du service :
```ini
[Unit]
Description=Biglobe Validator Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/biglobe
Environment=PYTHONPATH=/opt/biglobe
ExecStart=/opt/biglobe/venv/bin/python3 /opt/biglobe/main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## Commandes utiles
```bash
# Démarrer le service
systemctl start biglobe

# Voir les logs
journalctl -u biglobe -f

# Arrêter le service
systemctl stop biglobe

# Redémarrer le service
systemctl restart biglobe

# Voir le statut
systemctl status biglobe
```

## Support
Pour toute question ou support : @JYMMI10K

