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
        self._data.setdefault("guilds", {})
        await self._save()

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
        g.setdefault("scores", {})
        g.setdefault("daily_character", {})
        g.setdefault("character_history", {})
        g.setdefault("attempts", {})
        return g

    # ---------- Config serveur ----------
    async def get_guild_config(self, guild_id: int):
        async with self._lock:
            g = self._guild(guild_id)
            return {"channel_id": g["channel_id"], "role_id": g["role_id"]}

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

    # ---------- Scores ----------
    async def add_points(self, guild_id: int, user_id: int, points: int):
        async with self._lock:
            g = self._guild(guild_id)
            uid = str(user_id)
            g["scores"][uid] = g["scores"].get(uid, 0) + points
            await self._save()

    async def get_leaderboard(self, guild_id: int, limit: int = 5):
        async with self._lock:
            g = self._guild(guild_id)
            items = sorted(g["scores"].items(), key=lambda x: x[1], reverse=True)[:limit]
            return [{"user_id": int(uid), "points": pts} for uid, pts in items]

    # ---------- Personnage du jour ----------
    async def get_daily(self, guild_id: int, date_str: str):
        async with self._lock:
            g = self._guild(guild_id)
            entry = g["daily_character"].get(date_str)
            if entry is None:
                return None
            return {"character_name": entry["character_name"], "image_file": entry["image_file"]}

    async def set_daily(self, guild_id: int, date_str: str, character_name: str, image_file: str):
        async with self._lock:
            g = self._guild(guild_id)
            if date_str not in g["daily_character"]:
                g["daily_character"][date_str] = {
                    "character_name": character_name,
                    "image_file": image_file,
                }
                await self._save()

    async def get_character_history(self, guild_id: int):
        async with self._lock:
            g = self._guild(guild_id)
            return dict(g["character_history"])

    async def update_character_history(self, guild_id: int, character_name: str, date_str: str):
        async with self._lock:
            g = self._guild(guild_id)
            g["character_history"][character_name] = date_str
            await self._save()

    # ---------- Tentatives ----------
    async def get_attempt(self, guild_id: int, user_id: int, date_str: str):
        async with self._lock:
            g = self._guild(guild_id)
            day = g["attempts"].get(date_str, {})
            entry = day.get(str(user_id))
            return dict(entry) if entry else None

    async def create_attempt(self, guild_id: int, user_id: int, date_str: str):
        async with self._lock:
            g = self._guild(guild_id)
            day = g["attempts"].setdefault(date_str, {})
            day[str(user_id)] = {
                "attempt_count": 0,
                "start_time": time.time(),
                "finished": 0,
                "points_earned": 0,
            }
            await self._save()

    async def update_attempt_count(self, guild_id: int, user_id: int, date_str: str, count: int):
        async with self._lock:
            g = self._guild(guild_id)
            day = g["attempts"].setdefault(date_str, {})
            entry = day.setdefault(str(user_id), {
                "attempt_count": 0, "start_time": time.time(), "finished": 0, "points_earned": 0
            })
            entry["attempt_count"] = count
            await self._save()

    async def finish_attempt(self, guild_id: int, user_id: int, date_str: str, success: bool, points: int):
        async with self._lock:
            g = self._guild(guild_id)
            day = g["attempts"].setdefault(date_str, {})
            entry = day.setdefault(str(user_id), {
                "attempt_count": 0, "start_time": time.time(), "finished": 0, "points_earned": 0
            })
            entry["finished"] = 1 if success else 2
            entry["points_earned"] = points
            await self._save()
