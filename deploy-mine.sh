#!/usr/bin/env bash
#
# deploy-mine.sh — Weg A: eigene Python-Tweaks auf die laufende HA bringen.
#
# NUR auf Branch 'meine-anpassungen'. Bewusst KEIN Bestandteil von Upstream-PRs
# (PRs zweigen von 'main' ab, dort existiert diese Datei nicht).
#
# Eigenschaften:
#   - Sichert das HA-Component-Verzeichnis VOR dem Deploy (lokal, timestamped).
#   - Überträgt nur custom_components/roommind/ OHNE frontend/ (das gebaute
#     Frontend liegt nur im HACS-Zip, nicht im Repo — niemals überschreiben/löschen).
#   - KEIN --delete: entfernt nichts auf der HA, überlagert nur.
#   - Fasst .storage/ und die HA-DB NICHT an.
#   - Startet HA NICHT neu. Reload macht der Mensch (siehe Ausgabe am Ende).
#
set -euo pipefail

HA_IP="192.168.1.48"
HA_USER="root"
REMOTE="/config/custom_components/roommind"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC="${SCRIPT_DIR}/custom_components/roommind"
CREDS="/root/.local_credentials"
TS="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="${SCRIPT_DIR}/backups"

[[ -f "${CREDS}" ]] || { echo "FEHLER: ${CREDS} fehlt"; exit 1; }
[[ -d "${SRC}" ]]   || { echo "FEHLER: ${SRC} fehlt"; exit 1; }

HA_PASS="$(grep ha_pass "${CREDS}" | cut -d= -f2)"
[[ -n "${HA_PASS}" ]] || { echo "FEHLER: ha_pass nicht in ${CREDS}"; exit 1; }

SSH="sshpass -p ${HA_PASS} ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 ${HA_USER}@${HA_IP}"

echo "==> Sicherung des HA-Verzeichnisses (${REMOTE})"
mkdir -p "${BACKUP_DIR}"
BACKUP_FILE="${BACKUP_DIR}/roommind-ha-${TS}.tar.gz"
${SSH} "tar czf - -C ${REMOTE} ." > "${BACKUP_FILE}"
if ! gzip -t "${BACKUP_FILE}" 2>/dev/null; then
  echo "FEHLER: Backup defekt (gzip-Test fehlgeschlagen) — Deploy abgebrochen"
  exit 1
fi
echo "    -> ${BACKUP_FILE} ($(ls -lh "${BACKUP_FILE}" | awk '{print $5}'), $(tar tzf "${BACKUP_FILE}" | wc -l) Dateien, gzip OK)"

echo "==> Deploy Python-Dateien (ohne frontend/, ohne __pycache__)"
tar czf - -C "${SRC}" \
    --exclude='frontend' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    . | ${SSH} "tar xzf - -C ${REMOTE}/"

echo "==> Stale Bytecode auf HA aufräumen"
${SSH} "find ${REMOTE} -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null; true"

echo ""
echo "==> Fertig. Nächster Schritt (manuell, KEIN Auto-Restart):"
echo "    Python-Logik geändert:  HA → Einstellungen → Geräte & Dienste"
echo "                            → RoomMind → ⋮ → Neu laden"
echo "    manifest.json / WS-API: voller HA-Neustart nötig (vorher fragen!)"
echo "    Rollback:               Backup aus ${BACKUP_DIR}/ zurückspielen"
