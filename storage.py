import json
import os
import asyncio
import time


class JSONStore:
    """
    Stockage des données du bot dans un fichier JSON unique.
    Toutes les opérations passent par un verrou asyncio pour éviter les accès
    concurrents, et l'écriture est atomique (fichier temporaire + rename)
    pour éviter toute corruption en cas de crash pendant l'écriture.

    Le leaderboard, le personnage du jour, l'historique des personnages et
    les tentatives sont désormais GLOBAUX (partagés entre tous les serveurs
    Discord). Seule la config par serveur (channel_id / role_id / date de
    dernière annonce) reste propre à chaque serveur.
    """

    def __init__(self, path: str):
        self.path = path
        self._lock = asyncio.Lock()
        self._data: dict = {}

    async def connect(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        if os.path.isfile(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                try:
                    self._data = json.load(f)
                except json.JSONDecodeError:
                    self._data = {}
        else:
            self._data = {}

        self._migrate_to_global_schema()
        await self._save()

    def _migrate_to_global_schema(self):
        """
        Convertit l'ancien format (scores / personnage du jour / historique /
        tentatives stockés séparément pour chaque serveur) vers le nouveau
        format global partagé.

        Les anciens scores et tentatives, imbriqués dans chaque serveur dans
        l'ancien format, ne sont PAS repris (remise à zéro demandée) : seuls
        channel_id et role_id de chaque serveur sont conservés.
        """
        self._data.setdefault("guilds", {})
        self._data.setdefault("scores", {})
        self._data.setdefault("daily_character", {})
        self._data.setdefault("character_history", {})
        self._data.setdefault("attempts", {})

        for gid, g in list(self._data["guilds"].items()):
            # On ne garde que la config propre au serveur ; tout le reste
            # (ancien scores/daily_character/character_history/attempts
            # imbriqués) est abandonné.
            self._data["guilds"][gid] = {
                "channel_id": g.get("channel_id"),
                "role_id": g.get("role_id"),
                "last_announced": g.get("last_announced"),
            }

    async def close(self):
        pass  # rien à fermer, méthode gardée pour compatibilité avec main.py

    async def _save(self):
        tmp_path = self.path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, self.path)  # remplacement atomique

    def _guild(self, guild_id: int) -> dict:
        gid = str(guild_id)
        g = self._data["guilds"].setdefault(gid, {})
        g.setdefault("channel_id", None)
        g.setdefault("role_id", None)
        g.setdefault("last_announced", None)
        return g

    # ---------- Config serveur ----------
    async def get_guild_config(self, guild_id: int):
        async with self._lock:
            g = self._guild(guild_id)
            return {"channel_id": g["channel_id"], "role_id": g["role_id"]}

    async def get_all_guild_configs(self) -> dict:
        """Retourne {guild_id_str: {channel_id, role_id, last_announced}} pour tous les serveurs connus."""
        async with self._lock:
            return {
                gid: {
                    "channel_id": g.get("channel_id"),
                    "role_id": g.get("role_id"),
                    "last_announced": g.get("last_announced"),
                }
                for gid, g in self._data["guilds"].items()
            }

    async def set_channel(self, guild_id: int, channel_id: int):
        async with self._lock:
            g = self._guild(guild_id)
            g["channel_id"] = channel_id
            await self._save()

    async def set_role(self, guild_id: int, role_id: int):
        async with self._lock:
            g = self._guild(guild_id)
            g["role_id"] = role_id
            await self._save()

    async def set_last_announced(self, guild_id: int, date_str: str):
        async with self._lock:
            g = self._guild(guild_id)
            g["last_announced"] = date_str
            await self._save()

    # ---------- Scores (globaux, communs à tous les serveurs) ----------
    async def add_points(self, user_id: int, points: int):
        async with self._lock:
            uid = str(user_id)
            self._data["scores"][uid] = self._data["scores"].get(uid, 0) + points
            await self._save()

    async def get_leaderboard(self, limit: int = 5):
        async with self._lock:
            items = sorted(self._data["scores"].items(), key=lambda x: x[1], reverse=True)[:limit]
            return [{"user_id": int(uid), "points": pts} for uid, pts in items]

    # ---------- Personnage du jour (global) ----------
    async def get_daily(self, date_str: str):
        async with self._lock:
            entry = self._data["daily_character"].get(date_str)
            if entry is None:
                return None
            return {"character_name": entry["character_name"], "image_file": entry["image_file"]}

    async def set_daily(self, date_str: str, character_name: str, image_file: str):
        async with self._lock:
            if date_str not in self._data["daily_character"]:
                self._data["daily_character"][date_str] = {
                    "character_name": character_name,
                    "image_file": image_file,
                }
                await self._save()

    async def get_character_history(self):
        async with self._lock:
            return dict(self._data["character_history"])

    async def update_character_history(self, character_name: str, date_str: str):
        async with self._lock:
            self._data["character_history"][character_name] = date_str
            await self._save()

    # ---------- Tentatives (globales, communes à tous les serveurs) ----------
    async def get_attempts_for_date(self, date_str: str) -> dict:
        """Retourne {user_id_str: {attempt_count, start_time, finished, points_earned}} pour une date donnée."""
        async with self._lock:
            day = self._data["attempts"].get(date_str, {})
            return {uid: dict(entry) for uid, entry in day.items()}

    async def get_attempt(self, user_id: int, date_str: str):
        async with self._lock:
            day = self._data["attempts"].get(date_str, {})
            entry = day.get(str(user_id))
            return dict(entry) if entry else None

    async def create_attempt(self, user_id: int, date_str: str):
        async with self._lock:
            day = self._data["attempts"].setdefault(date_str, {})
            day[str(user_id)] = {
                "attempt_count": 0,
                "start_time": time.time(),
                "finished": 0,
                "points_earned": 0,
            }
            await self._save()

    async def update_attempt_count(self, user_id: int, date_str: str, count: int):
        async with self._lock:
            day = self._data["attempts"].setdefault(date_str, {})
            entry = day.setdefault(str(user_id), {
                "attempt_count": 0, "start_time": time.time(), "finished": 0, "points_earned": 0
            })
            entry["attempt_count"] = count
            await self._save()

    async def finish_attempt(self, user_id: int, date_str: str, success: bool, points: int):
        async with self._lock:
            day = self._data["attempts"].setdefault(date_str, {})
            entry = day.setdefault(str(user_id), {
                "attempt_count": 0, "start_time": time.time(), "finished": 0, "points_earned": 0
            })
            entry["finished"] = 1 if success else 2
            entry["points_earned"] = points
            await self._save()