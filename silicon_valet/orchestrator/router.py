from time import time
from sqlalchemy import create_engine, text
import aio_pika
from aio_pika import IncomingMessage
import asyncio
import logging
import json
import re
from typing import Callable, Awaitable

logger = logging.getLogger(__name__)

# --- État persistant (module-level) ---
ont_offline_serials: set = set()          # ONTs actuellement offline
ont_offline_times: dict = {}              # serial -> (timestamp, tap_id)
ont_outage_counted: set = set()           # ONTs qui ont déclenché un outage_off

OUTAGE_WINDOW_SECONDS = 30


# --- Helpers SQL ---

def get_tap_id(conn, serial: str):
    result = conn.execute(
        text('SELECT tap_id FROM "ONTS" WHERE serial = :serial'),
        {"serial": serial}
    ).fetchone()
    return result.tap_id if result else None


# --- Fonctions TAP ---

def tap_total_off_increment(conn, serial: str):
    if serial in ont_offline_serials:
        logger.info(f"Already tracking {serial} as offline — skip increment")
        return

    tap_id = get_tap_id(conn, serial)
    if tap_id is None:
        logger.warning(f"No tap_id found for serial {serial}")
        return

    conn.execute(
        text('UPDATE "TAPS" SET total_off = total_off + 1 WHERE tap_id = :tap_id'),
        {"tap_id": tap_id}
    )
    ont_offline_serials.add(serial)
    ont_offline_times[serial] = (time(), tap_id)
    logger.info(f"Incremented total_off for tap {tap_id} (ONT {serial})")


def tap_outage_off_increment(conn, serial: str):
    if serial not in ont_offline_times:
        return

    offline_time, tap_id = ont_offline_times[serial]
    now = time()

    # D'autres ONTs sur le même TAP sont tombés dans la fenêtre de 30s ?
    recent_on_same_tap = [
        s for s, (t, tid) in ont_offline_times.items()
        if s != serial and tid == tap_id and abs(now - t) <= OUTAGE_WINDOW_SECONDS
    ]

    if recent_on_same_tap:
        conn.execute(
            text('UPDATE "TAPS" SET outage_off = outage_off + 1 WHERE tap_id = :tap_id'),
            {"tap_id": tap_id}
        )
        ont_outage_counted.add(serial)
        logger.info(
            f"Incremented outage_off for tap {tap_id} — "
            f"{len(recent_on_same_tap) + 1} ONTs offline within {OUTAGE_WINDOW_SECONDS}s"
        )


def tap_total_off_decrement(conn, serial: str):
    if serial not in ont_offline_serials:
        logger.info(f"{serial} not in offline set — skip decrement")
        return

    tap_id = get_tap_id(conn, serial)
    if tap_id is None:
        logger.warning(f"No tap_id found for serial {serial}")
        return

    conn.execute(
        text('UPDATE "TAPS" SET total_off = total_off - 1 WHERE tap_id = :tap_id'),
        {"tap_id": tap_id}
    )
    ont_offline_serials.discard(serial)
    ont_offline_times.pop(serial, None)
    logger.info(f"Decremented total_off for tap {tap_id} (ONT {serial})")


def tap_outage_off_decrement(conn, serial: str):
    # Cet ONT avait-il déclenché un outage_off ?
    if serial not in ont_outage_counted:
        return

    if serial not in ont_offline_times:
        return

    _, tap_id = ont_offline_times[serial]

    conn.execute(
        text('UPDATE "TAPS" SET outage_off = outage_off - 1 WHERE tap_id = :tap_id'),
        {"tap_id": tap_id}
    )
    ont_outage_counted.discard(serial)
    logger.info(f"Decremented outage_off for tap {tap_id} (ONT {serial})")


# --- Fonctions principales ---

def set_ont_offline(serial: str):
    try:
        engine = create_engine(f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}")
        with engine.connect() as conn:
            conn.execute(
                text('UPDATE "ONTS" SET is_online = false WHERE serial = :serial'),
                {"serial": serial}
            )
            tap_total_off_increment(conn, serial)
            tap_outage_off_increment(conn, serial)
            conn.commit()
        logger.info(f"ONT {serial} set offline")
    except Exception as e:
        logger.error(f"Error setting ONT offline: {e}")
        raise


def set_ont_online(serial: str):
    try:
        engine = create_engine(f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}")
        with engine.connect() as conn:
            conn.execute(
                text('UPDATE "ONTS" SET is_online = true WHERE serial = :serial'),
                {"serial": serial}
            )
            # Décrementer outage AVANT total — on a besoin de ont_offline_times encore intact
            tap_outage_off_decrement(conn, serial)
            tap_total_off_decrement(conn, serial)
            conn.commit()
        logger.info(f"ONT {serial} set online")
    except Exception as e:
        logger.error(f"Error setting ONT online: {e}")
        raise