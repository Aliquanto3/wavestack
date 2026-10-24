#!/usr/bin/env bash
# Installe uv, WaveStack et le modele Qwen par defaut sans droits administrateur, puis
# lance l'application. Idempotent : relancer ce script ne retelecharge ni le projet ni
# le modele s'ils sont deja presents.
#
# Surcharges (dossiers d'installation, utiles aussi pour les tests) :
#   WAVESTACK_INSTALL_DIR, WAVESTACK_DATA_DIR, WAVESTACK_UV_INSTALL_DIR,
#   WAVESTACK_NO_LAUNCH=1 (n'ouvre pas l'application), WAVESTACK_DRY_RUN=1 (mode a blanc),
#   WAVESTACK_MODELS=id1,id2 (telecharge aussi ces modeles locaux facultatifs, verifies par
#   empreinte SHA-256 ; Qwen reste le modele par defaut ; `list` affiche la table et
#   s'arrete), WAVESTACK_WITH_MINICPM=1 (alias de WAVESTACK_MODELS=minicpm5, publie en 1.2.0).
set -euo pipefail

# Memes valeurs que README.md (une seule source de verite : voir tests/test_installers.py)
QWEN_URL="https://huggingface.co/unsloth/Qwen3.5-2B-GGUF/resolve/main/Qwen3.5-2B-Q4_K_M.gguf"
QWEN_FILE="Qwen3.5-2B-Q4_K_M.gguf"
# Modeles locaux facultatifs : une seule table, lue par WAVESTACK_MODELS. Une ligne par modele :
# identifiant|fichier|taille|licence|sha256|url (revision epinglee).
OPTIONAL_MODELS="qwen3.5-0.8b|Qwen3.5-0.8B-Q4_K_M.gguf|0,5 Go|Apache-2.0|bd258782e35f7f458f8aced1adc053e6e92e89bc735ba3be89d38a06121dc517|https://huggingface.co/unsloth/Qwen3.5-0.8B-GGUF/resolve/6ab461498e2023f6e3c1baea90a8f0fe38ab64d0/Qwen3.5-0.8B-Q4_K_M.gguf
minicpm5|MiniCPM5-2B-Q4_K_M.gguf|1,5 Go|Apache-2.0|ec2d5801640099e97d8d7e8003ad4d81f336e757811f03a26173dddf386602fd|https://huggingface.co/openbmb/MiniCPM5-2B-GGUF/resolve/2079a22f3beaa4e306449978533478fe0522f4b3/MiniCPM5-2B-Q4_K_M.gguf
granite-4.0-350m|granite-4.0-350m-Q4_K_M.gguf|0,3 Go|Apache-2.0|771c588a49607f274a2bba3185733607ebe6f74b996ab90e2d6bee0d98bcec52|https://huggingface.co/ibm-granite/granite-4.0-350m-GGUF/resolve/b8208a86a58427e1739265318028eb5895b74bf2/granite-4.0-350m-Q4_K_M.gguf
granite-4.0-1b|granite-4.0-1b-Q4_K_M.gguf|1,0 Go|Apache-2.0|22ec0f9cc99a90185312de3c882c84e7bd6789bdd050389844380a01a831d7f1|https://huggingface.co/ibm-granite/granite-4.0-1b-GGUF/resolve/b27c2fe3f211b7f44e80fa620177aea371099aaa/granite-4.0-1b-Q4_K_M.gguf"
REPO_URL="https://github.com/Aliquanto3/wavestack.git"
TARBALL_URL="https://github.com/Aliquanto3/wavestack/archive/refs/heads/main.tar.gz"

INSTALL_DIR="${WAVESTACK_INSTALL_DIR:-}"
DATA_DIR="${WAVESTACK_DATA_DIR:-}"
UV_INSTALL_DIR_OVERRIDE="${WAVESTACK_UV_INSTALL_DIR:-}"
NO_LAUNCH="${WAVESTACK_NO_LAUNCH:-}"
DRY_RUN="${WAVESTACK_DRY_RUN:-}"
WITH_MINICPM="${WAVESTACK_WITH_MINICPM:-}"
MODELS_ARG="${WAVESTACK_MODELS:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

# Verifie l'empreinte SHA-256 d'un fichier telecharge ; non conforme : fichier supprime et arret.
verify_sha256() {
    local path="$1" expected="$2" actual
    if command -v sha256sum >/dev/null 2>&1; then
        actual="$(sha256sum "$path" | cut -d' ' -f1)"
    else
        actual="$(shasum -a 256 "$path" | cut -d' ' -f1)"
    fi
    if [ "$actual" != "$expected" ]; then
        rm -f "$path"
        echo "Empreinte SHA-256 non conforme pour $(basename "$path") : fichier supprime. Attendue $expected, obtenue $actual." >&2
        exit 1
    fi
}

# -- Modeles facultatifs demandes : valides avant toute action (rien n'est cree si un
#    identifiant est inconnu). `list` affiche la table et s'arrete.
REQUESTED=","
if [ -n "$MODELS_ARG" ]; then
    for id in $(echo "$MODELS_ARG" | tr ',' ' ' | tr 'A-Z' 'a-z'); do
        REQUESTED="$REQUESTED$id,"
    done
fi
if [ "$WITH_MINICPM" = "1" ]; then
    REQUESTED="${REQUESTED}minicpm5,"
fi
VALID_IDS="$(echo "$OPTIONAL_MODELS" | cut -d'|' -f1 | paste -sd, - | sed 's/,/, /g')"
case "$REQUESTED" in
    *,list,*)
        echo "Modeles facultatifs (Qwen3.5-2B est toujours telecharge) :"
        echo "$OPTIONAL_MODELS" | while IFS='|' read -r id file size license _ _; do
            printf '  %-14s %-28s %-8s %s
' "$id" "$file" "$size" "$license"
        done
        exit 0
        ;;
esac
for id in $(echo "$REQUESTED" | tr ',' ' '); do
    if ! echo "$OPTIONAL_MODELS" | cut -d'|' -f1 | grep -Fxq -- "$id"; then
        echo "Modele facultatif inconnu : '$id'. Identifiants valides : $VALID_IDS." >&2
        exit 1
    fi
done
# Lignes de la table retenues, dans l'ordre de la table (sans doublon).
SELECTED="$(echo "$OPTIONAL_MODELS" | while IFS= read -r line; do
    case "$REQUESTED" in *",${line%%|*},"*) echo "$line" ;; esac
done)"

# -- Dossier du projet : sur place si on est deja dans un clone ou un zip, sinon un
#    dossier visible sous Documents.
if [ -z "$INSTALL_DIR" ]; then
    if [ -f "$SCRIPT_DIR/pyproject.toml" ]; then
        INSTALL_DIR="$SCRIPT_DIR"
    else
        INSTALL_DIR="$HOME/Documents/WaveStack"
    fi
fi

# -- Dossier de donnees : venv, caches et modeles, jamais sous Documents.
if [ -z "$DATA_DIR" ]; then
    DATA_DIR="$HOME/.local/share/wavestack"
fi
VENV_DIR="$DATA_DIR/venv"
CACHE_DIR="$DATA_DIR/uv-cache"
MODELS_DIR="$DATA_DIR/models"
MODEL_PATH="$MODELS_DIR/$QWEN_FILE"

echo "Projet      : $INSTALL_DIR"
echo "Donnees     : $DATA_DIR"
echo "Modele Qwen : $MODEL_PATH"
if [ -n "$SELECTED" ]; then
    echo "$SELECTED" | while IFS='|' read -r id file _; do
        echo "Modele $id : $MODELS_DIR/$file"
    done
fi

if [ -n "$DRY_RUN" ]; then
    echo "(mode a blanc : aucune commande reseau ou d'installation executee)"
    exit 0
fi

# -- uv, dans le profil utilisateur, sans droits administrateur.
if ! command -v uv >/dev/null 2>&1; then
    echo "Installation de uv..."
    if [ -n "$UV_INSTALL_DIR_OVERRIDE" ]; then
        export UV_INSTALL_DIR="$UV_INSTALL_DIR_OVERRIDE"
    fi
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="${UV_INSTALL_DIR_OVERRIDE:-$HOME/.local/bin}:$PATH"
fi

# -- Projet : clone si absent ; inchange s'il est deja la (idempotent).
if [ ! -f "$INSTALL_DIR/pyproject.toml" ]; then
    echo "Recuperation de WaveStack dans $INSTALL_DIR..."
    mkdir -p "$(dirname "$INSTALL_DIR")"
    if command -v git >/dev/null 2>&1; then
        git clone "$REPO_URL" "$INSTALL_DIR"
    else
        # Pas de git sur le poste : archive de la branche main.
        mkdir -p "$INSTALL_DIR"
        curl -fL "$TARBALL_URL" | tar -xz --strip-components=1 -C "$INSTALL_DIR"
    fi
else
    echo "WaveStack deja present dans $INSTALL_DIR, pas de nouveau clone."
fi

# -- Modele Qwen : telecharge si absent (idempotent).
mkdir -p "$MODELS_DIR"
if [ ! -f "$MODEL_PATH" ]; then
    echo "Telechargement du modele Qwen (1,3 Go)..."
    # Telechargement vers .part puis renommage : une coupure ne laisse pas un faux modele.
    curl -fL -o "$MODEL_PATH.part" "$QWEN_URL"
    mv -f "$MODEL_PATH.part" "$MODEL_PATH"
else
    echo "Modele Qwen deja present, pas de nouveau telechargement."
fi

# -- Modeles facultatifs (WAVESTACK_MODELS) : telecharges si absents, verifies par empreinte.
if [ -n "$SELECTED" ]; then
    while IFS='|' read -r id file size _ sha url; do
        path="$MODELS_DIR/$file"
        if [ ! -f "$path" ]; then
            echo "Telechargement du modele $id ($size)..."
            curl -fL -o "$path.part" "$url"
            verify_sha256 "$path.part" "$sha"
            mv -f "$path.part" "$path"
        else
            echo "Modele $id deja present, pas de nouveau telechargement."
        fi
    done <<< "$SELECTED"
fi

# -- Venv et caches sous le dossier de donnees, jamais sous Documents ; l'appli lit ses
#    modeles dans le meme dossier.
export WAVESTACK_DATA_DIR="$DATA_DIR"
export UV_PROJECT_ENVIRONMENT="$VENV_DIR"
export UV_CACHE_DIR="$CACHE_DIR"

if [ -z "$NO_LAUNCH" ]; then
    echo "Lancement de WaveStack..."
    (cd "$INSTALL_DIR" && uv run wavestack)
fi

echo
echo "Pour relancer WaveStack plus tard : reexecutez install.sh dans ce dossier."
