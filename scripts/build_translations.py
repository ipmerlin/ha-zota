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
    "air_hysteresis_upper": ("Room upper hysteresis", "Гистерезис воздуха сверху"),
    "air_hysteresis_lower": ("Room lower hysteresis", "Гистерезис воздуха снизу"),
    "air_correction": ("Room sensor correction", "Поправка датчика воздуха"),
    "water_max": ("Maximum water target", "Максимальная уставка воды"),
    "water_min": ("Minimum water target", "Минимальная уставка воды"),
    "water_low_warning": ("Low water temperature warning", "Порог низкой температуры воды"),
    "dhw_target": ("DHW target", "Уставка ГВС"),
    "dhw_max": ("Maximum DHW target", "Максимальная уставка ГВС"),
    "dhw_correction": ("DHW sensor correction", "Поправка датчика ГВС"),
    "pressure_max": ("Maximum pressure protection threshold", "Верхний порог защиты по давлению"),
    "pressure_min": ("Minimum pressure protection threshold", "Нижний порог защиты по давлению"),
    "pressure_high_warning": ("High pressure warning threshold", "Верхний порог предупреждения по давлению"),
    "pressure_low_warning": ("Low pressure warning threshold", "Нижний порог предупреждения по давлению"),
    "weather_coefficient": ("Weather curve coefficient", "Коэффициент ПЗА"),
    "outside_correction": ("Outside sensor correction", "Поправка уличного датчика"),
    "summer_threshold": ("Summer transition temperature", "Температура перехода в лето"),
    "weather_room_target": ("Weather virtual room target", "Виртуальная температура помещения ПЗА"),
    "pump_delay": ("Pump stop delay", "Задержка отключения насоса"),
    "valve_travel_time": ("Valve travel time", "Время полного хода клапана"),
    "external_water_reduction": ("External thermostat water reduction", "Снижение температуры внешним термостатом"),
    "external_power_stage": ("External thermostat power stage", "Ступень мощности внешнего термостата"),
    "antilegionella_enabled": ("DHW antilegionella", "Антилегионелла ГВС"),
    "pressure_protection": ("Pressure protection", "Защита по давлению"),
    "power_on_delay": ("Power activation delay", "Задержка включения мощности"),
    "auto_winter_summer": ("Automatic winter/summer", "Автоматический переход зима/лето"),
    "power_accuracy": ("Power regulation accuracy", "Точность регулирования мощности"),
    "pump_circuit": ("Pump circuit setting", "Назначение контура насоса"),
    "valve_type": ("Valve type", "Тип клапана"),
    "valve_mode": ("Valve mode", "Режим клапана"),
    "external_response": ("External thermostat response", "Реакция на внешний термостат"),
    "external_contact": ("External thermostat contact", "Контакт внешнего термостата"),
    "aux_temp": ("AUX temperature", "Температура AUX"),
    "ssr_temp": ("SSR temperature", "Температура SSR"),
    "scheme": ("Hydraulic scheme", "Схема подключения"),
    "weather_target": ("Weather target", "Уставка ПЗА контроллера"),
    "gsm_signal": ("GSM signal code", "Уровень GSM (код)"),
    "dhw_state": ("DHW circuit state", "Состояние контура ГВС"),
    "thermostat_program": ("Thermostat program", "Программа термостата"),
    "controller_time": ("Controller time", "Время контроллера"),
    "nominal_power": ("Nominal power", "Номинальная мощность"),
    "firmware": ("Controller firmware", "Прошивка контроллера"),
    "indicator_firmware": ("Indicator firmware", "Прошивка индикатора"),
    "antilegionella_active": ("Antilegionella active", "Антилегионелла активна"),
    "thermostat_active": ("Thermostat program active", "Программа термостата активна"),
    "valve_open_output": ("Valve opening output", "Выход открытия клапана"),
    "valve_close_output": ("Valve closing output", "Выход закрытия клапана"),
}

# Load the descriptions without importing Home Assistant's integration package.
import importlib.util
import sys

spec = importlib.util.spec_from_file_location("zota_setting_descriptions", ROOT / "settings.py")
settings = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = settings
spec.loader.exec_module(settings)

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
                    "No MK-X found in this account.",
                    "В учётной записи нет котлов MK-X.",
                ),
                "boiler_missing": tr(
                    "The configured boiler is missing from this account.",
                    "Настроенного котла нет в этой учётной записи.",
                ),
            },
            "abort": {
                "already_configured": tr("This boiler is already configured.", "Этот котёл уже настроен."),
                "reauth_successful": tr("Authentication updated.", "Учётные данные обновлены."),
                "reconfigure_successful": tr("Configuration updated.", "Настройки обновлены."),
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
        "services": {},
    }
    service_names = {
        "get_schedule": ("Read boiler schedule", "Прочитать расписание котла"),
        "preview_schedule": ("Preview schedule changes", "Предпросмотр изменения расписания"),
        "save_schedule": ("Save schedule changes", "Сохранить изменение расписания"),
        "get_history": ("Get ZOTA history", "Получить архив показаний ZOTA"),
    }
    service_descriptions = {
        "get_schedule": ("Read the returned program and its revision.", "Прочитать возвращённую котлом программу и её версию."),
        "preview_schedule": ("Preview changes without writing to the boiler.", "Проверить изменения без записи в котёл."),
        "save_schedule": ("Write once using the preview revision, then verify readback.", "Записать один раз с проверкой версии предпросмотра, затем проверить чтением."),
        "get_history": ("Get up to 31 days of archived readings using ISO times with timezone.", "Получить архив показаний за интервал до 31 дня. Укажите ISO-время с часовым поясом."),
    }
    service_fields = {
        "entry_id": ("ZOTA integration", "Интеграция ZOTA"),
        "changes": ("Period changes", "Изменения периодов"),
        "expected_revision": ("Before revision from preview", "Версия до изменения из предпросмотра"),
        "start": ("Start, ISO time with timezone", "Начало, ISO-время с часовым поясом"),
        "end": ("End, ISO time with timezone", "Конец, ISO-время с часовым поясом"),
    }
    for service, name in service_names.items():
        fields = ["entry_id"]
        if service in ("preview_schedule", "save_schedule"):
            fields.append("changes")
        if service == "save_schedule":
            fields.append("expected_revision")
        if service == "get_history":
            fields.extend(("start", "end"))
        data["services"][service] = {
            "name": name[index],
            "description": service_descriptions[service][index],
            "fields": {field: {"name": service_fields[field][index]} for field in fields},
        }
    groups = {
        "climate": ["room"],
        "number": ["water_target", *settings.NUMBERS],
        "switch": ["enabled", "weather_enabled", *settings.SWITCHES],
        "select": ["power_stage", "pump_mode", "thermostat_type", *settings.SELECTS],
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
            "aux_temp", "ssr_temp", "scheme", "weather_target", "gsm_signal", "dhw_state",
            "thermostat_program", "controller_time", "nominal_power", "firmware", "indicator_firmware",
        ],
        "binary_sensor": ["pump_status", "external_off", "errors", "warnings", "antilegionella_active",
                          "thermostat_active", "valve_open_output", "valve_close_output"],
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
    option_names = {
        "coarse": ("Coarse", "Грубая"), "fine": ("Fine", "Точная"),
        "boiler": ("Boiler", "Котёл"), "heating": ("Heating", "Отопление"),
        "heating_dhw": ("Heating/DHW valve", "Клапан отопление/ГВС"),
        "off_after_water_heating": ("Stop after water heating", "Отключать после нагрева воды"),
        "off_after_dhw_heating": ("Stop after DHW heating", "Отключать после нагрева ГВС"),
        "none": ("Not used", "Не используется"), "switching": ("Switching", "Переключающий"),
        "dhw_priority": ("DHW priority", "Приоритет ГВС"), "dhw": ("DHW", "ГВС"),
        "boiler_off": ("Stop boiler", "Отключить котёл"), "pump_off": ("Stop pump", "Отключить насос"),
        "reduce_water": ("Reduce water temperature", "Снизить температуру воды"),
        "reduce_power": ("Reduce power", "Снизить мощность"),
        "normally_closed": ("Normally closed", "Нормально замкнутый"),
        "normally_open": ("Normally open", "Нормально разомкнутый"),
    }
    for key, (_, options) in settings.SELECTS.items():
        data["entity"]["select"][key]["state"] = {name: option_names[name][index] for name in options}
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
