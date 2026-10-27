DEFAULT_SETTINGS = {
    "shop_name": "Accessories POS",
    "phone": "",
    "address": "",
    "theme": "system",
}

THEMES = {"system", "light", "dark"}


def get_shop_settings(db):
    settings = DEFAULT_SETTINGS.copy()
    settings.update(
        dict(db.execute("SELECT setting_key, setting_value FROM shop_settings").fetchall())
    )
    if settings["theme"] not in THEMES:
        settings["theme"] = DEFAULT_SETTINGS["theme"]
    return settings


def save_shop_settings(db, settings):
    with db:
        db.executemany(
            """
            INSERT INTO shop_settings (setting_key, setting_value) VALUES (?, ?)
            ON CONFLICT(setting_key) DO UPDATE SET setting_value = excluded.setting_value
            """,
            settings.items(),
        )
