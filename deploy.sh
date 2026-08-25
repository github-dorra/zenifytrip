#!/bin/bash
# ══════════════════════════════════════════════════════════════════════════════
# ZenifyTrip — Script de déploiement Hetzner CX32 (Ubuntu 22.04)
# LLM : Gemini (primary) → Groq fallback automatique
# Usage : bash deploy.sh
# ══════════════════════════════════════════════════════════════════════════════

set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

info "═══════════════════════════════════════════"
info " ZenifyTrip — Déploiement staging Hetzner  "
info "═══════════════════════════════════════════"


# ── Étape 1 : Mise à jour système ─────────────────────────────────────────────
info "[1/6] Mise à jour du système Ubuntu..."
apt-get update -qq && apt-get upgrade -y -qq
apt-get install -y -qq curl git


# ── Étape 2 : Installation Docker ─────────────────────────────────────────────
info "[2/6] Installation de Docker..."
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | sh
    usermod -aG docker $USER
    info "Docker installé : $(docker --version)"
else
    info "Docker déjà présent : $(docker --version)"
fi


# ── Étape 3 : Installation Docker Compose ─────────────────────────────────────
info "[3/6] Installation de Docker Compose..."
if ! command -v docker-compose &>/dev/null; then
    COMPOSE_VERSION=$(curl -s https://api.github.com/repos/docker/compose/releases/latest | grep '"tag_name"' | cut -d'"' -f4)
    curl -SL "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-$(uname -s)-$(uname -m)" \
         -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
    info "Docker Compose installé : $(docker-compose --version)"
else
    info "Docker Compose déjà présent : $(docker-compose --version)"
fi


# ── Étape 4 : Configuration du fichier .env ────────────────────────────────────
info "[4/6] Configuration des variables d'environnement..."
if [ ! -f ".env" ]; then
    cp .env.example .env
    warn "⚠️  Fichier .env créé — remplir les clés API avant de continuer :"
    warn "   GEMINI_API_KEY  →  Google AI Studio"
    warn "   GROQ_API_KEY    →  console.groq.com (fallback automatique)"
    warn "   MONGODB_URI     →  MongoDB Atlas"
    warn "   API_KEY         →  staging.zenifytrip.com"
    echo ""
    read -p "Appuyez sur ENTRÉE après avoir configuré .env (nano .env)..." _
else
    info "Fichier .env existant conservé."
fi


# ── Étape 5 : Build et démarrage ───────────────────────────────────────────────
info "[5/6] Build de l'image Docker et démarrage des services..."
docker-compose up --build -d

info "Attente stabilisation des services (20s)..."
sleep 20


# ── Étape 6 : Vérification ────────────────────────────────────────────────────
info "[6/6] Vérification de santé..."

docker-compose ps
echo ""

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/health)
if [ "$HTTP_CODE" = "200" ]; then
    info "✅ API ZenifyTrip opérationnelle"
else
    warn "Health check HTTP $HTTP_CODE — vérifier : docker-compose logs app"
fi

REDIS_OK=$(docker exec zenify-redis redis-cli ping 2>/dev/null)
[ "$REDIS_OK" = "PONG" ] && info "✅ Redis opérationnel" || warn "Redis ne répond pas"


# ── Résumé ────────────────────────────────────────────────────────────────────
SERVER_IP=$(curl -s ifconfig.me 2>/dev/null || echo 'SERVER_IP')
echo ""
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo -e "${GREEN}  ZenifyTrip — Staging opérationnel     ${NC}"
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo ""
echo "  API    : http://${SERVER_IP}/chat"
echo "  Health : http://${SERVER_IP}/health"
echo "  LLM    : Gemini (primary) → Groq llama-3.3-70b (fallback)"
echo ""
echo "  Logs   : docker-compose logs -f app"
echo "  Stop   : docker-compose down"
echo ""
echo "  Test :"
echo "  curl -X POST http://localhost/chat \\"
echo "       -H 'Content-Type: application/json' \\"
echo "       -d '{\"user_id\":\"test123\",\"user_message\":\"Je veux visiter Djerba\"}'"
echo ""
