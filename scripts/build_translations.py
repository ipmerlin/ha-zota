"""Generate the shipped English and Russian UI dictionaries."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "custom_components/zota"
NAMES = {
    "room": ("Room thermostat", "Термостат помещения"),
    "water_target": ("Water target temperature", "Уставка теплоносителя"),
    "air_target": ("Room target temperature", "Уставка воздуха"),
    "actual_temp": ("Water temperature", "Фактическая температура"),
    "air_temp": ("Room temperature", "Датчик воздуха"),
    "outside_temp": ("Outside temperature", "Температура на улице"),
    "dhw_temp": ("DHW temperature", "Температура ГВС"),
    "calculated_target": ("Calculated water target", "Расчётная уставка"),
    "actual_power": ("Actual power", "Фактическая мощность"),
    "target_power": ("Power limit", "Установленная мощность"),
    "pressure": ("Pressure", "Давление"),
    "operation_mode": ("Operating mode", "Режим работы"),
    "circuit_mode": ("Pump circuit", "Контур"),
    "pump_status": ("Pump output", "Состояние насоса"),
    "external_off": ("External shutdown", "Внешнее отключение"),
    "errors": ("Faults", "Ошибки"),
    "warnings": ("Warnings", "Предупреждения"),
    "power_stage": ("Power limit", "Ограничение мощности"),
    "pump_mode": ("Pump mode", "Режим насоса"),
    "thermostat_type": ("Thermostat source", "Источник термостата"),
    "enabled": ("Boiler", "Котёл"),
    "weather_enabled": ("Weather regulation", "Погодозависимое регулирование"),
}

for language, index in (("en", 0), ("ru", 1)):

    def tr(en, ru):
        return (en, ru)[index]

    data = {
        "config": {
            "step": {
                "user": {
                    "title": "ZOTA Net",
                    "description": tr(
                        "Sign in to ZOTA Net. The app uses HTTP port 81: credentials travel without TLS. Enable the checkbox only if you accept this. MK-X communication uses cloud TCP without TLS. Password is used only for setup. Turning OFF the room thermostat stops the entire boiler.",
                        "Войдите в ZOTA Net. Приложение использует HTTP, порт 81: логин и пароль передаются без TLS. Подтвердите это отдельным флажком. Обмен с MK-X идёт через облако по TCP без TLS. Пароль учётной записи используется только при настройке. Режим OFF термостата выключает весь котёл.",
                    ),
                    "data": {
                        "username": tr("Username", "Логин"),
                        "password": tr("Password", "Пароль"),
                        "api_url": tr("Account API URL", "Адрес API учётной записи"),
                        "allow_http": tr(
                            "Allow account credentials over HTTP without TLS",
                            "Разрешить передачу логина и пароля по HTTP без TLS",
                        ),
                    },
                },
                "boiler": {
                    "title": tr("Select MK-X", "Выберите MK-X"),
                    "description": tr(
                        "Only Internet-connected MK-X boilers are supported.",
                        "Поддерживаются котлы MK-X с подключением к Интернету.",
                    ),
                    "data": {"boiler": tr("Boiler", "Котёл")},
                },
            },
            "error": {
                "invalid_auth": tr("ZOTA rejected the credentials.", "ZOTA отклонила учётные данные."),
                "cannot_connect": tr(
                    "Cannot read ZOTA data. Check API URL, HTTP checkbox and network access to TCP 1977.",
                    "Не удалось прочитать данные ZOTA. Проверьте адрес API, флажок HTTP и доступ к TCP 1977.",
                ),
                "no_boilers": tr(
                    "No Internet-connected MK-X found.",
                    "В учётной записи нет MK-X с подключением к Интернету.",
                ),
                "boiler_missing": tr(
                    "The configured boiler is missing from this account.",
                    "Настроенного котла нет в этой учётной записи.",
                ),
            },
            "abort": {
                "already_configured": tr("This boiler is already configured.", "Этот котёл уже настроен."),
                "reauth_successful": tr("Authentication updated.", "Учётные данные обновлены."),
            },
        },
        "options": {
            "step": {
                "init": {
                    "title": tr("Polling", "Обновление данных"),
                    "data": {
                        "update_interval": tr(
                            "Polling interval (seconds, 60–3600)", "Интервал обновления (секунды, 60–3600)"
                        )
                    },
                }
            }
        },
        "entity": {},
    }
    groups = {
        "climate": ["room"],
        "number": ["water_target"],
        "switch": ["enabled", "weather_enabled"],
        "select": ["power_stage", "pump_mode", "thermostat_type"],
        "sensor": [
            "actual_temp",
            "air_temp",
            "outside_temp",
            "dhw_temp",
            "air_target",
            "water_target",
            "calculated_target",
            "actual_power",
            "target_power",
            "pressure",
            "operation_mode",
            "circuit_mode",
        ],
        "binary_sensor": ["pump_status", "external_off", "errors", "warnings"],
    }
    for group, keys in groups.items():
        data["entity"][group] = {key: {"name": NAMES[key][index]} for key in keys}
    data["entity"]["select"]["pump_mode"]["state"] = {
        "auto": tr("Automatic", "Автоматически"),
        "on": tr("On", "Включён"),
        "off": tr("Off", "Выключен"),
    }
    data["entity"]["select"]["power_stage"]["state"] = {"off": tr("Off", "Выключено")}
    data["entity"]["select"]["thermostat_type"]["state"] = {
        "none": tr("Not used", "Не используется"),
        "external": tr("External", "Внешний"),
        "internal": tr("Internal", "Внутренний"),
        "opentherm": "OpenTherm",
    }
    data["entity"]["sensor"]["operation_mode"]["state"] = {
        "work": tr("Running", "Работа"),
        "stop": tr("Stopped", "Остановлен"),
        "pause": tr("Paused", "Пауза"),
        "full_stop": tr("Fully stopped", "Полный останов"),
    }
    (ROOT / "translations").mkdir(exist_ok=True)
    (ROOT / "translations" / f"{language}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if language == "en":
        (ROOT / "strings.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
