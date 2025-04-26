# Sitemapz

Génerateur de Sitemap multi sites  open source developpé avec Python et dockerisé pour faciliter son déploiement

## 🚀 Guide d'installation

Suivez ces étapes pour déployer **Sitemapz** sur votre machine ou sur un serveur distant (testé sur Arch Linux, mais devrait fonctionner sur d'autres distributions).

---

### 1. Prérequis

- **Git**  

  ```bash
  sudo pacman -S git
  ```

- **Docker & Docker Compose**  

  ```bash
  sudo pacman -S docker docker-compose
  sudo systemctl enable --now docker.service
  # (Optionnel) Permettre à votre utilisateur d'exécuter Docker sans sudo :
  sudo groupadd docker || true
  sudo usermod -aG docker $USER
  # déconnectez-vous et reconnectez-vous, ou exécutez :
  newgrp docker
  ```

- **Un éditeur de code** (par ex. VS Code, Vim, etc.)

---

### 2. Cloner le dépôt

```bash
git clone https://github.com/herrkruger/sitemapz.git
cd sitemapz
```

---

### 3. Créer et configurer `.env`

Copiez l'exemple ou créez un nouveau fichier `.env` à la racine du projet :

```bash
cp .env.example .env
```

Ouvrez `.env` dans votre éditeur et remplissez :

```ini
# Base de données (utilise SQLite dans data/)
DATABASE_URL=sqlite:///data/scans.db

# Notifications par email (paramètres SMTP)
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=notify@example.com
SMTP_PASS=your_smtp_password
ADMIN_EMAIL=you@yourdomain.com

# URL publique où l'application sera accessible
BASE_URL=https://reports.yourdomain.com
```

---

### 4. Construire & Lancer avec Docker Compose

```bash
# Construire l'image Docker et démarrer le conteneur en arrière-plan
docker compose up -d --build

# Vérifier que le conteneur fonctionne
docker ps

# Afficher les logs pour s'assurer que tout a démarré correctement
docker compose logs -f sitemap
```

- Cela créera un dossier `data/` (contient votre base de données SQLite et les sitemaps générés).  
- L'interface web sera disponible à `http://localhost:8000/` (ou à l'adresse IP de votre serveur).

---

### 5. Première configuration

1. Ouvrez votre navigateur à l'adresse `http://<votre-serveur>:8000/`  
2. **Ajoutez un site** :  
   - Collez son URL (par ex. `https://example.com`)  
   - Choisissez l'un des calendriers par défaut (horaire / quotidien / hebdomadaire / mensuel)  
   - Cliquez sur **Add Website**  
3. Vous verrez immédiatement votre site listé avec :  
   - **ID**  
   - **URL**  
   - **Planification**  
   - **Dernier scan** / **Statut**  
   - Un **jeton API** unique  
   - Un lien pour télécharger le script PHP  

---

### 6. Déployer le récupérateur PHP

Pour chaque site :

1. Téléchargez le récupérateur : cliquez sur **Download** → `sitemap_fetcher_<ID>.php`  
2. Uploadez ce fichier PHP sur l’hébergement du site (par ex. à la racine).  
3. En accédant à `https://mon-site.com/sitemap_fetcher_<ID>.php`, vous récupérerez en toute sécurité son XML de sitemap.

---

### 7. Gestion du service

- **Arrêter** le conteneur :

  ```bash
  docker compose down
  ```

- **Reconstruire** après des modifications de code :

  ```bash
  docker compose up -d --build
  ```

- **Accéder** au shell du conteneur en cours d'exécution :

  ```bash
  docker exec -it sitemap /bin/sh
  ```

---

🎉 Et Voilà ! .
