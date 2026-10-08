"""Read-only account archive, separate from live controller transactions."""

from datetime import datetime, timedelta, timezone

from .api import ZotaAccount
from .protocol import ZotaError, temperature


def utc_time(value: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None:
            raise ValueError
        return result.astimezone(timezone.utc)
    except (ValueError, TypeError, AttributeError) as err:
        raise ZotaError("Use ISO date/time with timezone, for example 2026-10-08T12:00:00+03:00") from err


async def get_history(session, url: str, token: str, allow_http: bool, serial: int,
                      start: str, end: str, stages: tuple[float, ...]) -> dict:
    begin, finish = utc_time(start), utc_time(end)
    duration = finish - begin
    if duration <= timedelta(0) or duration > timedelta(days=31):
        raise ZotaError("History interval must be positive and no longer than 31 days")
    step = next((step for days, step in ((30, 480), (7, 120), (3, 60), (1, 15))
                 if duration >= timedelta(days=days)), 1)
    # Reuse URL/TLS opt-in checks and safe HTTP error handling; no password needed.
    account = ZotaAccount(session, url, "", "", allow_http)
    data = await account._request("GET", "/api/Boilers/GetBoilerHistory", headers={
        "Authorization": f"Bearer {token}"}, params={
        "type": "24", "serial": str(serial), "startDate": begin.strftime("%Y-%m-%dT%H:%M"),
        "endDate": finish.strftime("%Y-%m-%dT%H:%M"), "offset": str(step),
    })
    if data.get("response", {}).get("Result") != 0:
        raise ZotaError("ZOTA rejected history request")
    rows = data.get("boilersData")
    if not isinstance(rows, list) or len(rows) > 10000:
        raise ZotaError("Invalid or oversized ZOTA archive")
    samples = []
    try:
        for row in rows:
            info = row["Info"]
            sample = {"time": utc_time(row["Time"]).isoformat()}
            for source, key, divisor in (("TempWater", "water_temp", 1), ("TempOAir", "outside_temp", 1),
                                         ("TempRoom", "air_temp", 10), ("TempDHW", "dhw_temp", 1),
                                         ("TempSSR", "ssr_temp", 1), ("TempAux", "aux_temp", 1)):
                value = info.get(source)
                sample[key] = temperature(value, divisor) if isinstance(value, int) else None
            pressure = info.get("Pressure")
            sample["pressure"] = pressure / 1000 if isinstance(pressure, int) and 0 <= pressure < 0x4000 else None
            stage = info.get("CurPower")
            sample["power_stage"] = stage
            sample["power_kw"] = stages[stage] if isinstance(stage, int) and 0 <= stage < len(stages) else None
            samples.append(sample)
    except (KeyError, TypeError, AttributeError) as err:
        raise ZotaError("Invalid ZOTA archive sample") from err
    return {"start": begin.isoformat(), "end": finish.isoformat(), "step_minutes": step,
            "count": len(samples), "samples": samples}
