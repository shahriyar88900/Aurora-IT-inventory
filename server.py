#!/usr/bin/env python3
"""Aurora Plant IT Inventory - dependency-free authenticated Windows LAN server."""

import base64
import binascii
import csv
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import sqlite3
import time
import webbrowser
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
DATA = ROOT / "data"
DB_PATH = DATA / "inventory.db"
SESSION_COOKIE = "aurora_session"
SESSION_HOURS = 12
APP_VERSION = "4.7.0"

DEPARTMENTS = ("I&C", "EMD", "MMD", "EHS", "Chemical", "Warranty", "OPD", "A&P", "RPQC")
DEPARTMENT_ORDER = {name: index for index, name in enumerate(DEPARTMENTS)}
# Designations offered on the Add/Edit employee form, keyed by department.
DESIGNATIONS_BY_DEPARTMENT = {
    "I&C": ("GM", "Senior Engineer", "Engineer", "Assistant Engineer", "Senior Technician", "Technician", "Junior Technician"),
    "EMD": ("Senior Engineer", "Engineer", "Assistant Engineer"),
    "MMD": ("GM", "Senior Engineer", "Engineer", "Assistant Engineer", "Senior Technician", "Technician", "Welder", "Mechanist"),
    "EHS": ("EHS Head", "Assistant Manager", "Fire Truck Driver", "Fire Fighter"),
    "Chemical": ("Senior Chemist", "Assistant Engineer"),
    "Warranty": ("GM", "Civil Engineer", "Mechanical Engineer"),
    "OPD": ("CRE", "Shift in Charge", "PBE", "BOPE", "Field Engineer"),
    "A&P": ("COO & PM", "Admin GM", "Site Admin", "Admin Assistant", "Purchase Officer",
            "House Keeping Supervisor", "Cook (Bangla)", "Cook (Chinese)", "Office Boy", "Kitchen Assistant"),
    "RPQC": ("Performance Engineer", "Document Controller", "Assistant Engineer"),
}
ASSET_CATEGORIES = ("Laptop", "Desktop", "Monitor", "Mouse", "Keyboard", "Printer", "Server")
# Categories that never carry an IP address (peripherals).
IP_LESS_CATEGORIES = ("Monitor", "Mouse", "Keyboard", "Printer")
# Location choices offered on the Add/Edit asset form.
ASSET_LOCATIONS = ("CCB", "DM Plant", "UEB", "Warehouse", "Workshop")
STORAGE_OPTIONS = ("128 GB", "256 GB", "512 GB", "1 TB", "2 TB")

# --- Network devices (routers & switches) --------------------------------
NETWORK_DEVICE_TYPES = ("Router", "Switch")
NETWORK_LOCATIONS = ("CCB", "DM Plant", "Dormitory", "Workshop", "UEB")
ROUTER_BRANDS = (
    "TP-LINK TL-XVR3000G", "TP-LINK TL-XDR3030", "TL-Archer C20",
    "TL-WR841N", "TL-WR840N", "TP-Deco M5", "TL-MR6400", "TP-Link C54",
)
SWITCH_BRANDS = ("Fast", "TP-Link")


def brands_for(device_type):
    """Return the allowed brand list for a device type. Router and switch
    brand lists are strictly separate so one can never appear for the other."""
    return ROUTER_BRANDS if device_type == "Router" else SWITCH_BRANDS


# Floor options are location-dependent. Only CCB and Dormitory have floors.
CCB_FLOORS = ("Ground Floor", "1st Floor", "2nd Floor", "3rd Floor")
DORM_FLOORS = ("Ground Floor", "1st Floor", "2nd Floor", "3rd Floor", "4th Floor")


def floors_for(location):
    if location == "CCB":
        return CCB_FLOORS
    if location == "Dormitory":
        return DORM_FLOORS
    return ()


FIELDS = [
    "asset_tag", "name", "category", "brand", "model", "serial",
    "department", "assigned_to", "location", "status", "arrival_date",
    "distribution_date", "value", "ip_address", "notes",
    "ram", "cpu", "ssd", "hdd",
    "processor_mfr", "processor", "cpu_generation", "cpu_series",
]

SEED = [
    ("APS-LT-001", "Dell Latitude 5440", "Laptop", "Dell", "Latitude 5440", "DL5440-NEP-01", "IT", "Unassigned", "Admin Building", "In stock", "2025-02-12", "", 0, "192.168.50.21", "Plant IT workstation", "16 GB", "Intel Core i5-1345U", "512 GB", ""),
    ("APS-DT-002", "Dell OptiPlex 7010", "Desktop", "Dell", "OptiPlex 7010", "OP7010-NEP-02", "IT", "Unassigned", "IT Store", "In stock", "2024-06-18", "", 0, "", "Ready for assignment", "16 GB", "Intel Core i5-13500", "512 GB", "1 TB"),
    ("APS-PR-007", "HP Color LaserJet MFP", "Printer", "HP", "E78535", "HP-E78535-07", "A&P", "Unassigned", "Admin Building", "Damaged", "2024-07-16", "", 0, "192.168.50.77", "Print queue under diagnosis", "", "", "", ""),
    ("APS-SRV-003", "ERP Application Server", "Server", "HPE", "ProLiant DL380", "HPE-DL380-03", "I&C", "ERP Service", "Data Center", "In use", "2023-11-05", "2023-11-12", 0, "192.168.50.10", "Linux ERP production server", "128 GB", "Intel Xeon Silver", "1.92 TB", "8 TB"),
    ("APS-MON-026", "Dell 24-inch Monitor", "Monitor", "Dell", "P2422H", "DLP2422-026", "", "Unassigned", "IT Store", "In stock", "2024-05-03", "", 0, "", "Ready for assignment", "", "", "", ""),
    ("APS-MOU-011", "Dell Optical Mouse", "Mouse", "Dell", "MS116", "DELL-MS116-011", "", "Unassigned", "IT Store", "In stock", "2025-01-08", "", 0, "", "New stock", "", "", "", ""),
    ("APS-KB-012", "Dell USB Keyboard", "Keyboard", "Dell", "KB216", "DELL-KB216-012", "", "Unassigned", "IT Store", "In warranty", "2025-01-08", "", 0, "", "Warranty claim in progress", "", "", "", ""),
]


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def today_iso():
    return datetime.now().date().isoformat()


def connection():
    db = sqlite3.connect(DB_PATH, timeout=20)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    return db


def password_hash(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 240000)
    return f"pbkdf2_sha256$240000${salt.hex()}${digest.hex()}"


def password_ok(password, stored):
    try:
        algorithm, rounds, salt_hex, expected = stored.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(rounds)).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def username_base(full_name):
    """Apply the requested Aurora username rule to an employee full name."""
    parts = [part for part in re.split(r"\s+", full_name.strip()) if part]
    if not parts:
        return "user"
    first = re.sub(r"[^a-z0-9]", "", parts[0].lower())
    if first in {"md", "mohammad"} and len(parts) > 1:
        selected = parts[1]
    else:
        selected = parts[0]
    return re.sub(r"[^a-z0-9]", "", selected.lower()) or "user"


def unique_username(db, full_name, employee_id, exclude_id=None):
    base = username_base(full_name)
    candidate = base
    suffix = re.sub(r"[^a-z0-9]", "", employee_id.lower())[-4:] or "1"
    counter = 1
    while True:
        params = [candidate]
        sql = "SELECT 1 FROM users WHERE username=? COLLATE NOCASE"
        if exclude_id is not None:
            sql += " AND id<>?"
            params.append(exclude_id)
        if not db.execute(sql, params).fetchone():
            return candidate
        candidate = f"{base}{suffix}" if counter == 1 else f"{base}{counter}"
        counter += 1


def table_columns(db, table):
    return {row[1] for row in db.execute(f"PRAGMA table_info({table})")}


PHONE_RE = re.compile(r"^[0-9+\-()\s]{6,20}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def clean_employee_payload(payload):
    """Validate and normalize the fields shared by create/update/import.
    Returns (fields_dict, error_message). fields_dict is None on error."""
    employee_id = str(payload.get("employee_id", "")).strip()
    name = str(payload.get("name", "")).strip()
    designation = str(payload.get("designation", "")).strip()
    department = str(payload.get("department", "")).strip()
    phone = str(payload.get("phone", "")).strip()
    email = str(payload.get("email", "")).strip()
    if not employee_id or not name or not designation or department not in DEPARTMENTS:
        return None, "Name, ID, designation and a valid department are required"
    allowed = DESIGNATIONS_BY_DEPARTMENT.get(department, ())
    if allowed and designation not in allowed:
        return None, f"'{designation}' is not a designation available under {department}"
    if phone and not PHONE_RE.match(phone):
        return None, "Contact number looks invalid"
    if email and not EMAIL_RE.match(email):
        return None, "Email address looks invalid"
    return {
        "employee_id": employee_id, "name": name, "designation": designation,
        "department": department, "phone": phone, "email": email,
    }, None


def initialize():
    DATA.mkdir(exist_ok=True)
    with connection() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_tag TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'Other',
            brand TEXT NOT NULL DEFAULT '', model TEXT NOT NULL DEFAULT '',
            serial TEXT NOT NULL DEFAULT '', department TEXT NOT NULL DEFAULT '',
            assigned_to TEXT NOT NULL DEFAULT 'Unassigned',
            location TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'In stock',
            arrival_date TEXT NOT NULL DEFAULT '', distribution_date TEXT NOT NULL DEFAULT '',
            value REAL NOT NULL DEFAULT 0, ip_address TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '', ram TEXT NOT NULL DEFAULT '',
            cpu TEXT NOT NULL DEFAULT '', ssd TEXT NOT NULL DEFAULT '', hdd TEXT NOT NULL DEFAULT '',
            processor_mfr TEXT NOT NULL DEFAULT '', processor TEXT NOT NULL DEFAULT '',
            cpu_generation TEXT NOT NULL DEFAULT '', cpu_series TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        columns = table_columns(db, "assets")
        if "arrival_date" not in columns:
            db.execute("ALTER TABLE assets ADD COLUMN arrival_date TEXT NOT NULL DEFAULT ''")
            if "purchase_date" in columns:
                db.execute("UPDATE assets SET arrival_date=purchase_date WHERE arrival_date='' ")
        if "distribution_date" not in columns:
            db.execute("ALTER TABLE assets ADD COLUMN distribution_date TEXT NOT NULL DEFAULT ''")
            if "warranty_end" in columns:
                db.execute("UPDATE assets SET distribution_date=warranty_end WHERE distribution_date='' ")
        for specification in ("ram", "cpu", "ssd", "hdd", "processor_mfr", "processor", "cpu_generation", "cpu_series"):
            if specification not in columns:
                db.execute(f"ALTER TABLE assets ADD COLUMN {specification} TEXT NOT NULL DEFAULT ''")
        db.execute("CREATE INDEX IF NOT EXISTS idx_assets_status ON assets(status)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_assets_department ON assets(department)")

        db.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            full_name TEXT NOT NULL,
            employee_id TEXT NOT NULL DEFAULT '',
            designation TEXT NOT NULL DEFAULT '',
            employee_pk INTEGER,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('admin','user')),
            is_main_admin INTEGER NOT NULL DEFAULT 0,
            can_read INTEGER NOT NULL DEFAULT 1,
            can_write INTEGER NOT NULL DEFAULT 0,
            can_delete INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1,
            must_change_password INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        user_columns = table_columns(db, "users")
        if "employee_id" not in user_columns:
            db.execute("ALTER TABLE users ADD COLUMN employee_id TEXT NOT NULL DEFAULT ''")
        if "designation" not in user_columns:
            db.execute("ALTER TABLE users ADD COLUMN designation TEXT NOT NULL DEFAULT ''")
        if "employee_pk" not in user_columns:
            db.execute("ALTER TABLE users ADD COLUMN employee_pk INTEGER")
        if "is_main_admin" not in user_columns:
            db.execute("ALTER TABLE users ADD COLUMN is_main_admin INTEGER NOT NULL DEFAULT 0")
        db.execute("""UPDATE users SET employee_id = CASE
            WHEN role='admin' THEN 'APS-ADMIN-' || printf('%03d', id)
            ELSE 'APS-USER-' || printf('%04d', id)
            END WHERE employee_id=''""")
        db.execute("UPDATE users SET designation='Not specified' WHERE designation=''")
        db.execute("UPDATE users SET designation='System Administrator' WHERE role='admin' AND designation='Not specified'")
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_employee_id ON users(employee_id COLLATE NOCASE)")
        db.execute("""CREATE TABLE IF NOT EXISTS sessions (
            token_hash TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT NOT NULL,
            action TEXT NOT NULL,
            target_type TEXT NOT NULL,
            target_id TEXT NOT NULL DEFAULT '',
            detail TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        db.execute("CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at)")

        db.execute("""CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id TEXT NOT NULL UNIQUE COLLATE NOCASE,
            name TEXT NOT NULL,
            designation TEXT NOT NULL,
            department TEXT NOT NULL,
            phone TEXT NOT NULL DEFAULT '',
            email TEXT NOT NULL DEFAULT '',
            active INTEGER NOT NULL DEFAULT 1,
            resignation_date TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        if "resignation_date" not in table_columns(db, "employees"):
            db.execute("ALTER TABLE employees ADD COLUMN resignation_date TEXT NOT NULL DEFAULT ''")
        employee_columns = table_columns(db, "employees")
        if "phone" not in employee_columns:
            db.execute("ALTER TABLE employees ADD COLUMN phone TEXT NOT NULL DEFAULT ''")
        if "email" not in employee_columns:
            db.execute("ALTER TABLE employees ADD COLUMN email TEXT NOT NULL DEFAULT ''")
        db.execute("CREATE INDEX IF NOT EXISTS idx_employees_department ON employees(department)")
        db.execute("""UPDATE users SET employee_pk=(SELECT e.id FROM employees e
            WHERE e.employee_id=users.employee_id COLLATE NOCASE)
            WHERE employee_pk IS NULL AND role<>'admin'""")
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_employee_pk ON users(employee_pk) WHERE employee_pk IS NOT NULL")
        db.execute("""CREATE TABLE IF NOT EXISTS asset_assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE RESTRICT,
            asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE RESTRICT,
            assigned_date TEXT NOT NULL,
            returned_date TEXT,
            assigned_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            returned_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_assignment_per_asset ON asset_assignments(asset_id) WHERE returned_date IS NULL")
        db.execute("CREATE INDEX IF NOT EXISTS idx_assignments_employee ON asset_assignments(employee_id, returned_date)")

        db.execute("""CREATE TABLE IF NOT EXISTS network_devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_type TEXT NOT NULL,
            location TEXT NOT NULL,
            floor TEXT NOT NULL DEFAULT '',
            brand TEXT NOT NULL,
            router_name TEXT NOT NULL DEFAULT '',
            device_mac TEXT NOT NULL DEFAULT '',
            ip_address TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        # Add new network columns to older databases without touching existing rows.
        network_columns = table_columns(db, "network_devices")
        for column in ("floor", "router_name", "device_mac"):
            if column not in network_columns:
                db.execute(f"ALTER TABLE network_devices ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
        db.execute("CREATE INDEX IF NOT EXISTS idx_network_location ON network_devices(location)")

        if db.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0] == 0:
            db.execute("""INSERT INTO users
                (username, full_name, employee_id, designation, password_hash, role,
                 can_read, can_write, can_delete, must_change_password)
                VALUES (?, ?, ?, ?, ?, 'admin', 1, 1, 1, 1)""",
                ("admin", "Aurora Admin", "APS-ADMIN-001", "System Administrator", password_hash("12345678")))
        # The oldest active administrator is the protected Main Admin. Older
        # databases are upgraded automatically without changing other accounts.
        main_admin = db.execute("SELECT id FROM users WHERE is_main_admin=1 LIMIT 1").fetchone()
        if not main_admin:
            first_admin = db.execute("SELECT id FROM users WHERE role='admin' AND active=1 ORDER BY id LIMIT 1").fetchone()
            if first_admin:
                db.execute("UPDATE users SET is_main_admin=1,can_read=1,can_write=1,can_delete=1 WHERE id=?", (first_admin[0],))
        if db.execute("SELECT COUNT(*) FROM assets").fetchone()[0] == 0:
            seed_columns = [
                "asset_tag", "name", "category", "brand", "model", "serial",
                "department", "assigned_to", "location", "status", "arrival_date",
                "distribution_date", "value", "ip_address", "notes",
                "ram", "cpu", "ssd", "hdd",
            ]
            placeholders = ",".join("?" for _ in seed_columns)
            db.executemany(f"INSERT INTO assets ({','.join(seed_columns)}) VALUES ({placeholders})", SEED)
        # A Windows-server launch always starts a fresh work session.  This
        # guarantees that the first browser screen is the login panel, even if
        # the same browser was signed in before the server was stopped.
        db.execute("DELETE FROM sessions")


def clean_asset(payload):
    result = {}
    for field in FIELDS:
        value = payload.get(field, "")
        result[field] = float(value or 0) if field == "value" else str(value or "").strip()
    result["category"] = result["category"] or "Other"
    result["status"] = result["status"] or "In stock"
    result["assigned_to"] = result["assigned_to"] or "Unassigned"
    # Asset name is no longer entered by hand on the Add form; derive a sensible
    # label from brand/model, falling back to the category.
    if not result["name"]:
        result["name"] = " ".join(p for p in (result["brand"], result["model"]) if p) or result["category"]
    if result["category"] not in ASSET_CATEGORIES:
        raise ValueError("Select a valid product category")
    if result["category"] not in ("Laptop", "Desktop"):
        for specification in ("ram", "cpu", "ssd", "hdd", "processor_mfr", "processor", "cpu_generation", "cpu_series"):
            result[specification] = ""
    # Peripherals never carry an IP address.
    if result["category"] in IP_LESS_CATEGORIES:
        result["ip_address"] = ""
    return result


def clean_network_device(payload):
    device_type = str(payload.get("device_type", "")).strip()
    location = str(payload.get("location", "")).strip()
    brand = str(payload.get("brand", "")).strip()
    ip_address = str(payload.get("ip_address", "")).strip()
    floor = str(payload.get("floor", "")).strip()
    router_name = str(payload.get("router_name", "")).strip()
    device_mac = str(payload.get("device_mac", "")).strip()
    if device_type not in NETWORK_DEVICE_TYPES:
        raise ValueError("Select a valid device (Router or Switch)")
    if location not in NETWORK_LOCATIONS:
        raise ValueError("Select a valid location")
    # Enforce the strict brand<->device pairing on the server as well, so a
    # router brand can never be saved for a switch and vice-versa.
    if brand not in brands_for(device_type):
        raise ValueError("Select a brand that matches the chosen device")
    # Floor only applies to CCB and Dormitory; validate against that location's
    # allowed list and clear it for every other location.
    allowed_floors = floors_for(location)
    if allowed_floors:
        if floor and floor not in allowed_floors:
            raise ValueError("Select a valid floor for this location")
    else:
        floor = ""
    # Router name and IP address only apply to routers. Device MAC applies to both.
    if device_type != "Router":
        router_name = ""
        ip_address = ""
    return {
        "device_type": device_type, "location": location, "floor": floor,
        "brand": brand, "router_name": router_name, "device_mac": device_mac,
        "ip_address": ip_address,
    }


# --- Excel / CSV bulk import ---------------------------------------------
# A tiny, dependency-free .xlsx reader (an .xlsx file is a ZIP of XML parts).
# This keeps the Windows package installable with nothing but Python.
XLSX_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _column_index(cell_ref):
    """'B3' -> 1 (zero-based column index)."""
    letters = "".join(ch for ch in cell_ref if ch.isalpha())
    index = 0
    for ch in letters:
        index = index * 26 + (ord(ch.upper()) - ord("A") + 1)
    return index - 1 if index else 0


def read_xlsx_rows(data):
    """Return the first worksheet as a list of rows (each a list of strings)."""
    import zipfile
    import xml.etree.ElementTree as ET
    rows = []
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        shared = []
        if "xl/sharedStrings.xml" in names:
            shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for si in shared_root.findall(f"{XLSX_NS}si"):
                shared.append("".join(t.text or "" for t in si.iter(f"{XLSX_NS}t")))
        sheet_part = next((n for n in names if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")), None)
        if not sheet_part:
            return rows
        sheet_root = ET.fromstring(archive.read(sheet_part))
        sheet_data = sheet_root.find(f"{XLSX_NS}sheetData")
        if sheet_data is None:
            return rows
        for row in sheet_data.findall(f"{XLSX_NS}row"):
            cells, max_col = {}, -1
            for cell in row.findall(f"{XLSX_NS}c"):
                ref = cell.get("r", "")
                col = _column_index(ref) if ref else 0
                cell_type = cell.get("t", "")
                value_node = cell.find(f"{XLSX_NS}v")
                inline_node = cell.find(f"{XLSX_NS}is")
                if cell_type == "s" and value_node is not None and value_node.text is not None:
                    value = shared[int(value_node.text)] if int(value_node.text) < len(shared) else ""
                elif cell_type == "inlineStr" and inline_node is not None:
                    value = "".join(t.text or "" for t in inline_node.iter(f"{XLSX_NS}t"))
                elif value_node is not None:
                    value = value_node.text or ""
                else:
                    value = ""
                cells[col] = str(value).strip()
                max_col = max(max_col, col)
            rows.append([cells.get(i, "") for i in range(max_col + 1)])
    return rows


def read_csv_rows(data):
    text = data.decode("utf-8-sig", errors="replace")
    return [[(cell or "").strip() for cell in row] for row in csv.reader(io.StringIO(text))]


def parse_spreadsheet(filename, data):
    """Pick a reader from the file extension and return rows of strings."""
    name = (filename or "").lower()
    if name.endswith(".csv"):
        return read_csv_rows(data)
    if name.endswith(".xlsx"):
        return read_xlsx_rows(data)
    # Fall back on content sniffing: .xlsx starts with the ZIP magic 'PK'.
    if data[:2] == b"PK":
        return read_xlsx_rows(data)
    return read_csv_rows(data)


def normalize_header(text):
    return re.sub(r"[^a-z0-9]+", "_", str(text or "").strip().lower()).strip("_")


def normalize_import_date(value):
    """Accept ISO dates, common day/month formats, or raw Excel serial numbers."""
    value = str(value or "").strip()
    if not value:
        return ""
    if re.fullmatch(r"\d+(\.\d+)?", value):
        try:
            serial = int(float(value))
            return (datetime(1899, 12, 30) + timedelta(days=serial)).strftime("%Y-%m-%d")
        except (ValueError, OverflowError):
            return value
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return value


# Accepted header spellings (normalized) mapped to a canonical field name.
ASSET_HEADER_ALIASES = {
    "asset_tag": "asset_tag", "asset": "asset_tag", "tag": "asset_tag",
    "category": "category", "product_category": "category", "type": "category",
    "brand": "brand", "make": "brand",
    "model": "model",
    "serial": "serial", "serial_number": "serial", "serial_no": "serial",
    "ip": "ip_address", "ip_address": "ip_address",
    "department": "department", "dept": "department",
    "location": "location",
    "arrival_date": "arrival_date", "arrival": "arrival_date",
    "distribution_date": "distribution_date", "distribution": "distribution_date",
    "ram": "ram", "memory": "ram",
    "processor_mfr": "processor_mfr", "processor_manufacturer": "processor_mfr",
    "cpu_manufacturer": "processor_mfr", "cpu_mfr": "processor_mfr",
    "processor": "processor", "cpu": "processor",
    "generation": "cpu_generation", "cpu_generation": "cpu_generation", "gen": "cpu_generation",
    "series": "cpu_series", "cpu_series": "cpu_series",
    "ssd": "ssd", "hdd": "hdd",
    "notes": "notes", "note": "notes", "remarks": "notes",
}

EMPLOYEE_HEADER_ALIASES = {
    "name": "name", "full_name": "name", "employee_name": "name",
    "id": "employee_id", "employee_id": "employee_id", "emp_id": "employee_id", "employee": "employee_id",
    "designation": "designation", "title": "designation", "role": "designation", "position": "designation",
    "department": "department", "dept": "department",
    "phone": "phone", "contact": "phone", "contact_number": "phone", "mobile": "phone", "phone_number": "phone",
    "email": "email", "email_address": "email",
}


def map_columns(header_row, aliases):
    """Return {canonical_field: column_index} for a header row."""
    mapping = {}
    for index, cell in enumerate(header_row):
        field = aliases.get(normalize_header(cell))
        if field and field not in mapping:
            mapping[field] = index
    return mapping


def _cell(row, index):
    return row[index].strip() if index is not None and index < len(row) else ""


def is_blank_row(row):
    return not any((cell or "").strip() for cell in row)


def import_assets(db, rows, user):
    if not rows:
        return {"added": 0, "skipped": 0, "errors": [{"row": 0, "reason": "The file has no rows"}]}
    columns = map_columns(rows[0], ASSET_HEADER_ALIASES)
    if "asset_tag" not in columns or "category" not in columns:
        raise ValueError("The first row must be a header that includes at least 'asset_tag' and 'category'")
    added, errors = 0, []
    for line, row in enumerate(rows[1:], start=2):
        if is_blank_row(row):
            continue
        payload = {field: _cell(row, index) for field, index in columns.items()}
        for date_field in ("arrival_date", "distribution_date"):
            if date_field in payload:
                payload[date_field] = normalize_import_date(payload[date_field])
        tag = payload.get("asset_tag", "")
        try:
            item = clean_asset(payload)
            if not item["asset_tag"]:
                errors.append({"row": line, "reason": "Missing asset tag"})
                continue
            placeholders = ",".join("?" for _ in FIELDS)
            db.execute(f"INSERT INTO assets ({','.join(FIELDS)}) VALUES ({placeholders})",
                       tuple(item[f] for f in FIELDS))
            audit(db, user, "IMPORT", "asset", "", item["asset_tag"])
            added += 1
        except sqlite3.IntegrityError:
            errors.append({"row": line, "reason": f"Asset tag '{tag}' already exists"})
        except ValueError as exc:
            errors.append({"row": line, "reason": str(exc)})
    return {"added": added, "skipped": len(errors), "errors": errors[:200]}


def import_employees(db, rows, user):
    if not rows:
        return {"added": 0, "skipped": 0, "errors": [{"row": 0, "reason": "The file has no rows"}]}
    columns = map_columns(rows[0], EMPLOYEE_HEADER_ALIASES)
    for required in ("name", "employee_id", "designation", "department"):
        if required not in columns:
            raise ValueError("The header must include name, employee_id (ID), designation and department")
    added, errors = 0, []
    for line, row in enumerate(rows[1:], start=2):
        if is_blank_row(row):
            continue
        payload = {field: _cell(row, index) for field, index in columns.items()}
        fields, error = clean_employee_payload(payload)
        if error:
            errors.append({"row": line, "reason": error})
            continue
        try:
            db.execute(
                "INSERT INTO employees (employee_id,name,designation,department,phone,email) VALUES (?,?,?,?,?,?)",
                (fields["employee_id"], fields["name"], fields["designation"], fields["department"],
                 fields["phone"], fields["email"]))
            audit(db, user, "IMPORT", "employee", "", f"{fields['employee_id']} - {fields['name']}")
            added += 1
        except sqlite3.IntegrityError:
            errors.append({"row": line, "reason": f"Employee ID '{fields['employee_id']}' already exists"})
    return {"added": added, "skipped": len(errors), "errors": errors[:200]}


def public_user(row):
    if not row:
        return None
    main_admin = bool(row["is_main_admin"])
    administrator = row["role"] == "admin"
    return {
        "id": row["id"], "username": row["username"], "full_name": row["full_name"],
        "employee_id": row["employee_id"], "designation": row["designation"],
        "employee_pk": row["employee_pk"], "role": row["role"], "is_main_admin": main_admin,
        "can_read": bool(main_admin or row["can_read"] or not administrator),
        "can_write": bool(main_admin or (administrator and row["can_write"])),
        "can_delete": bool(main_admin or (administrator and row["can_delete"])),
        "active": bool(row["active"]), "must_change_password": bool(row["must_change_password"]),
    }


def audit(db, user, action, target_type, target_id="", detail=""):
    db.execute("INSERT INTO audit_log (user_id,username,action,target_type,target_id,detail) VALUES (?,?,?,?,?,?)",
               (user["id"], user["username"], action, target_type, str(target_id), detail[:500]))


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC), **kwargs)

    def log_message(self, fmt, *args):
        print(f"[{self.log_date_time_string()}] {fmt % args}")

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        # Prevent an earlier extracted release from remaining visible in Edge
        # or Chrome after the Windows package is replaced.
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        super().end_headers()

    def send_json(self, data, status=200, cookie=None):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        size = int(self.headers.get("Content-Length", "0"))
        if size > 16 * 1024 * 1024:
            raise ValueError("Request is too large")
        return json.loads(self.rfile.read(size) or b"{}")

    def cookie_token(self):
        jar = SimpleCookie(self.headers.get("Cookie", ""))
        return jar.get(SESSION_COOKIE).value if jar.get(SESSION_COOKIE) else ""

    def current_user(self):
        token = self.cookie_token()
        if not token:
            return None
        token_digest = hashlib.sha256(token.encode()).hexdigest()
        with connection() as db:
            row = db.execute("""SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id
                WHERE s.token_hash=? AND s.expires_at>? AND u.active=1""", (token_digest, now_iso())).fetchone()
        return public_user(row)

    def require(self, permission=None, admin=False):
        user = self.current_user()
        if not user:
            self.send_json({"error": "Please sign in to continue"}, 401)
            return None
        if admin and user["role"] != "admin":
            self.send_json({"error": "Administrator permission is required"}, 403)
            return None
        if permission and not user.get(permission):
            self.send_json({"error": f"You do not have {permission.replace('can_', '')} permission"}, 403)
            return None
        return user

    def require_main_admin(self):
        user = self.current_user()
        if not user:
            self.send_json({"error": "Please sign in to continue"}, 401)
            return None
        if not user["is_main_admin"]:
            self.send_json({"error": "Main Administrator permission is required"}, 403)
            return None
        return user

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path in ("/", "/login"):
            self.path = "/index.html"
            super().do_GET()
            return
        if path == "/api/auth/me":
            user = self.current_user()
            self.send_json({"user": user}, 200 if user else 401)
            return
        if path == "/api/system":
            self.send_json({"name": "Aurora Plant IT Inventory", "version": APP_VERSION})
            return
        if path == "/api/assets":
            user = self.require("can_read")
            if not user:
                return
            query = parse_qs(parsed.query)
            search = query.get("search", [""])[0].strip()
            with connection() as db:
                if user["role"] == "user":
                    if not user["employee_pk"]:
                        rows = []
                    else:
                        rows = db.execute(f"""SELECT a.id,{','.join('a.' + field for field in FIELDS)},
                            a.created_at,a.updated_at FROM assets a
                            JOIN asset_assignments aa ON aa.asset_id=a.id AND aa.returned_date IS NULL
                            WHERE aa.employee_id=? ORDER BY aa.assigned_date DESC,a.id DESC""",
                            (user["employee_pk"],)).fetchall()
                elif search:
                    pattern = f"%{search}%"
                    rows = db.execute(f"""SELECT id,{','.join(FIELDS)},created_at,updated_at FROM assets WHERE asset_tag LIKE ? OR name LIKE ?
                        OR serial LIKE ? OR assigned_to LIKE ? OR location LIKE ? OR ip_address LIKE ?
                        ORDER BY id DESC""", (pattern,) * 6).fetchall()
                else:
                    rows = db.execute(f"SELECT id,{','.join(FIELDS)},created_at,updated_at FROM assets ORDER BY id DESC").fetchall()
            self.send_json({"assets": [dict(row) for row in rows]})
            return
        if path == "/api/export":
            user = self.require("can_read")
            if not user:
                return
            if user["role"] != "admin":
                self.send_json({"error": "Inventory export is available to administrators only"}, 403)
                return
            with connection() as db:
                export_fields = [field for field in FIELDS if field != "value"]
                rows = db.execute(f"SELECT {','.join(export_fields)} FROM assets ORDER BY id").fetchall()
            stream = io.StringIO()
            writer = csv.writer(stream)
            writer.writerow(export_fields)
            writer.writerows(rows)
            body = stream.getvalue().encode("utf-8-sig")
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", "attachment; filename=aurora-it-inventory.csv")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/api/users":
            if not self.require_main_admin():
                return
            with connection() as db:
                rows = db.execute("SELECT * FROM users ORDER BY role, full_name COLLATE NOCASE").fetchall()
            self.send_json({"users": [public_user(row) for row in rows]})
            return
        if path == "/api/employees":
            user = self.require("can_read")
            if not user:
                return
            if user["role"] != "admin":
                self.send_json({"error": "Employee directory is available to administrators only"}, 403)
                return
            with connection() as db:
                employees = [dict(row) for row in db.execute(
                    "SELECT * FROM employees"
                ).fetchall()]
                assigned = db.execute("""SELECT aa.id assignment_id,aa.employee_id,aa.asset_id,aa.assigned_date,
                    a.asset_tag,a.name asset_name,a.category,a.brand,a.model,a.serial
                    FROM asset_assignments aa JOIN assets a ON a.id=aa.asset_id
                    WHERE aa.returned_date IS NULL ORDER BY aa.assigned_date DESC,aa.id DESC""").fetchall()
            assignment_map = {}
            for row in assigned:
                assignment_map.setdefault(row["employee_id"], []).append(dict(row))
            with connection() as db:
                history = db.execute("""SELECT aa.id assignment_id,aa.employee_id,aa.asset_id,aa.assigned_date,
                    aa.returned_date,a.asset_tag,a.name asset_name,a.category,a.brand,a.model
                    FROM asset_assignments aa JOIN assets a ON a.id=aa.asset_id
                    ORDER BY aa.assigned_date DESC,aa.id DESC""").fetchall()
            history_map = {}
            for row in history:
                history_map.setdefault(row["employee_id"], []).append(dict(row))
            for employee in employees:
                employee["devices"] = assignment_map.get(employee["id"], [])
                employee["history"] = history_map.get(employee["id"], [])
            # Department-wise sequence: all employees of one department listed together,
            # in the same department order used across the app, then alphabetically by name.
            employees.sort(key=lambda e: (0 if e["active"] else 1,
                                           DEPARTMENT_ORDER.get(e["department"], 999),
                                           e["name"].lower()))
            self.send_json({"employees": employees, "departments": DEPARTMENTS,
                             "designations_by_department": DESIGNATIONS_BY_DEPARTMENT})
            return
        if path == "/api/audit":
            if not self.require_main_admin():
                return
            with connection() as db:
                rows = db.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT 100").fetchall()
            self.send_json({"logs": [dict(row) for row in rows]})
            return
        if path == "/api/network-devices":
            user = self.require("can_read")
            if not user:
                return
            if user["role"] != "admin":
                self.send_json({"error": "Network devices are available to administrators only"}, 403)
                return
            with connection() as db:
                rows = db.execute("""SELECT id,device_type,location,floor,brand,router_name,device_mac,ip_address,created_at,updated_at
                    FROM network_devices ORDER BY id DESC""").fetchall()
            self.send_json({
                "devices": [dict(row) for row in rows],
                "device_types": NETWORK_DEVICE_TYPES, "locations": NETWORK_LOCATIONS,
                "router_brands": ROUTER_BRANDS, "switch_brands": SWITCH_BRANDS,
                "ccb_floors": CCB_FLOORS, "dorm_floors": DORM_FLOORS,
            })
            return
        super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            payload = self.read_json()
            if path == "/api/auth/login":
                username = str(payload.get("username", "")).strip()
                password = str(payload.get("password", ""))
                with connection() as db:
                    row = db.execute("SELECT * FROM users WHERE username=? COLLATE NOCASE AND active=1", (username,)).fetchone()
                    if not row or not password_ok(password, row["password_hash"]):
                        time.sleep(0.35)
                        self.send_json({"error": "Invalid username or password"}, 401)
                        return
                    token = secrets.token_urlsafe(32)
                    expiry = (datetime.now(timezone.utc) + timedelta(hours=SESSION_HOURS)).replace(microsecond=0).isoformat()
                    db.execute("INSERT INTO sessions (token_hash,user_id,expires_at) VALUES (?,?,?)",
                               (hashlib.sha256(token.encode()).hexdigest(), row["id"], expiry))
                    user = public_user(row)
                    audit(db, user, "LOGIN", "session")
                cookie = f"{SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={SESSION_HOURS * 3600}"
                self.send_json({"user": user}, cookie=cookie)
                return
            if path == "/api/auth/logout":
                user = self.current_user()
                token = self.cookie_token()
                if token:
                    with connection() as db:
                        db.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),))
                        if user:
                            audit(db, user, "LOGOUT", "session")
                self.send_json({"ok": True}, cookie=f"{SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0")
                return
            if path == "/api/auth/change-password":
                user = self.require()
                if not user:
                    return
                current = str(payload.get("current_password", ""))
                new_password = str(payload.get("new_password", ""))
                if len(new_password) < 8:
                    self.send_json({"error": "New password must be at least 8 characters"}, 400)
                    return
                with connection() as db:
                    row = db.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone()
                    if not password_ok(current, row["password_hash"]):
                        self.send_json({"error": "Current password is incorrect"}, 400)
                        return
                    db.execute("UPDATE users SET password_hash=?,must_change_password=0,updated_at=CURRENT_TIMESTAMP WHERE id=?", (password_hash(new_password), user["id"]))
                    audit(db, user, "PASSWORD_CHANGE", "user", user["id"])
                self.send_json({"ok": True})
                return
            if path == "/api/auth/set-initial-password":
                # Forced first-login change. Only works while a change is pending,
                # so it never becomes a way to change a password without the current one.
                user = self.require()
                if not user:
                    return
                new_password = str(payload.get("new_password", ""))
                if len(new_password) < 8:
                    self.send_json({"error": "New password must be at least 8 characters"}, 400)
                    return
                with connection() as db:
                    row = db.execute("SELECT must_change_password FROM users WHERE id=?", (user["id"],)).fetchone()
                    if not row or not row["must_change_password"]:
                        self.send_json({"error": "A forced password change is not pending for this account"}, 400)
                        return
                    db.execute("UPDATE users SET password_hash=?,must_change_password=0,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                               (password_hash(new_password), user["id"]))
                    audit(db, user, "PASSWORD_CHANGE", "user", user["id"], "initial")
                self.send_json({"ok": True})
                return
            if path == "/api/assets":
                user = self.require("can_write")
                if not user:
                    return
                item = clean_asset(payload)
                if not item["asset_tag"] or not item["name"]:
                    self.send_json({"error": "Asset tag and name are required"}, 400)
                    return
                placeholders = ",".join("?" for _ in FIELDS)
                with connection() as db:
                    cur = db.execute(f"INSERT INTO assets ({','.join(FIELDS)}) VALUES ({placeholders})", tuple(item[f] for f in FIELDS))
                    audit(db, user, "CREATE", "asset", cur.lastrowid, item["asset_tag"])
                self.send_json({"id": cur.lastrowid}, 201)
                return
            if path == "/api/users":
                admin = self.require_main_admin()
                if not admin:
                    return
                employee_pk = int(payload.get("employee_pk", 0))
                password = str(payload.get("password", ""))
                role = "admin" if payload.get("role") == "admin" else "user"
                if not employee_pk or len(password) < 8:
                    self.send_json({"error": "Select an employee and enter an 8-character password"}, 400)
                    return
                with connection() as db:
                    employee = db.execute("SELECT * FROM employees WHERE id=? AND active=1", (employee_pk,)).fetchone()
                    if not employee:
                        self.send_json({"error": "Active employee not found"}, 404)
                        return
                    full_name = employee["name"]
                    employee_id = employee["employee_id"]
                    designation = employee["designation"]
                    username = unique_username(db, full_name, employee_id)
                    permissions = tuple(int(bool(payload.get(p))) for p in ("can_read", "can_write", "can_delete")) if role == "admin" else (1, 0, 0)
                    cur = db.execute("""INSERT INTO users
                        (username,full_name,employee_id,designation,employee_pk,password_hash,role,
                         can_read,can_write,can_delete,must_change_password,is_main_admin)
                        VALUES (?,?,?,?,?,?,?,?,?,?,1,0)""",
                        (username, full_name, employee_id, designation, employee_pk, password_hash(password), role, *permissions))
                    audit(db, admin, "CREATE", "user", cur.lastrowid, username)
                self.send_json({"id": cur.lastrowid, "username": username}, 201)
                return
            if path == "/api/employees":
                user = self.require("can_write")
                if not user:
                    return
                fields, error = clean_employee_payload(payload)
                if error:
                    self.send_json({"error": error}, 400)
                    return
                with connection() as db:
                    cur = db.execute(
                        "INSERT INTO employees (employee_id,name,designation,department,phone,email) VALUES (?,?,?,?,?,?)",
                        (fields["employee_id"], fields["name"], fields["designation"], fields["department"],
                         fields["phone"], fields["email"]))
                    audit(db, user, "CREATE", "employee", cur.lastrowid, f"{fields['employee_id']} - {fields['name']}")
                self.send_json({"id": cur.lastrowid}, 201)
                return
            if path.startswith("/api/employees/") and path.endswith("/resign"):
                user = self.require("can_write")
                if not user:
                    return
                employee_pk = int(path.split("/")[3])
                resignation_date = today_iso()
                with connection() as db:
                    db.execute("BEGIN IMMEDIATE")
                    employee = db.execute("SELECT * FROM employees WHERE id=?", (employee_pk,)).fetchone()
                    if not employee:
                        self.send_json({"error": "Employee not found"}, 404)
                        return
                    if not employee["active"]:
                        self.send_json({"error": "Employee is already resigned"}, 409)
                        return
                    # Return every currently held asset to stock, keeping the
                    # assignment rows so the employee's history is preserved.
                    active_rows = db.execute(
                        "SELECT id,asset_id FROM asset_assignments WHERE employee_id=? AND returned_date IS NULL",
                        (employee_pk,)).fetchall()
                    for row in active_rows:
                        db.execute("UPDATE asset_assignments SET returned_date=?,returned_by=? WHERE id=?",
                                   (resignation_date, user["id"], row["id"]))
                        db.execute("""UPDATE assets SET status='In stock',assigned_to='Unassigned',department='',
                            distribution_date='',updated_at=CURRENT_TIMESTAMP WHERE id=?""", (row["asset_id"],))
                    db.execute("UPDATE employees SET active=0,resignation_date=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                               (resignation_date, employee_pk))
                    audit(db, user, "RESIGN", "employee", employee_pk,
                          f"{employee['employee_id']} - {employee['name']} ({len(active_rows)} assets returned to stock)")
                self.send_json({"resigned": 1, "resignation_date": resignation_date, "assets_returned": len(active_rows)})
                return
            if path == "/api/assignments":
                user = self.require("can_write")
                if not user:
                    return
                employee_id = int(payload.get("employee_id", 0))
                asset_id = int(payload.get("asset_id", 0))
                assigned_date = today_iso()
                with connection() as db:
                    db.execute("BEGIN IMMEDIATE")
                    employee = db.execute("SELECT * FROM employees WHERE id=? AND active=1", (employee_id,)).fetchone()
                    asset = db.execute("SELECT * FROM assets WHERE id=?", (asset_id,)).fetchone()
                    already_assigned = db.execute(
                        "SELECT 1 FROM asset_assignments WHERE asset_id=? AND returned_date IS NULL", (asset_id,)
                    ).fetchone()
                    if not employee:
                        self.send_json({"error": "Active employee not found"}, 404)
                        return
                    if not asset:
                        self.send_json({"error": "Asset not found"}, 404)
                        return
                    if already_assigned or asset["status"].strip().lower() != "in stock":
                        self.send_json({"error": "Only an In stock device can be assigned"}, 409)
                        return
                    cur = db.execute("""INSERT INTO asset_assignments
                        (employee_id,asset_id,assigned_date,assigned_by) VALUES (?,?,?,?)""",
                        (employee_id, asset_id, assigned_date, user["id"]))
                    db.execute("""UPDATE assets SET status='In use',assigned_to=?,department=?,
                        distribution_date=?,updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                        (employee["name"], employee["department"], assigned_date, asset_id))
                    audit(db, user, "ASSIGN", "asset", asset_id,
                          f"{asset['asset_tag']} to {employee['name']} ({employee['department']})")
                self.send_json({"id": cur.lastrowid, "assigned_date": assigned_date}, 201)
                return
            if path.startswith("/api/assignments/") and path.endswith("/return"):
                user = self.require("can_write")
                if not user:
                    return
                assignment_id = int(path.split("/")[3])
                returned_date = today_iso()
                with connection() as db:
                    db.execute("BEGIN IMMEDIATE")
                    assignment = db.execute("""SELECT aa.*,a.asset_tag FROM asset_assignments aa
                        JOIN assets a ON a.id=aa.asset_id WHERE aa.id=? AND aa.returned_date IS NULL""",
                        (assignment_id,)).fetchone()
                    if not assignment:
                        self.send_json({"error": "Active device assignment not found"}, 404)
                        return
                    db.execute("UPDATE asset_assignments SET returned_date=?,returned_by=? WHERE id=?",
                               (returned_date, user["id"], assignment_id))
                    db.execute("""UPDATE assets SET status='In stock',assigned_to='Unassigned',department='',
                        distribution_date='',updated_at=CURRENT_TIMESTAMP WHERE id=?""", (assignment["asset_id"],))
                    audit(db, user, "RETURN", "asset", assignment["asset_id"], assignment["asset_tag"])
                self.send_json({"returned": 1, "returned_date": returned_date})
                return
            if path == "/api/network-devices":
                user = self.require("can_write")
                if not user:
                    return
                item = clean_network_device(payload)
                with connection() as db:
                    cur = db.execute("""INSERT INTO network_devices
                        (device_type,location,floor,brand,router_name,device_mac,ip_address)
                        VALUES (?,?,?,?,?,?,?)""",
                        (item["device_type"], item["location"], item["floor"], item["brand"],
                         item["router_name"], item["device_mac"], item["ip_address"]))
                    audit(db, user, "CREATE", "network_device", cur.lastrowid,
                          f"{item['device_type']} - {item['brand']} @ {item['location']}")
                self.send_json({"id": cur.lastrowid}, 201)
                return
            if path in ("/api/assets/import", "/api/employees/import"):
                user = self.require("can_write")
                if not user:
                    return
                filename = str(payload.get("filename", ""))
                encoded = str(payload.get("data", ""))
                if not encoded:
                    self.send_json({"error": "No file was received"}, 400)
                    return
                try:
                    raw = base64.b64decode(encoded, validate=False)
                except (ValueError, binascii.Error):
                    self.send_json({"error": "The uploaded file could not be read"}, 400)
                    return
                try:
                    rows = parse_spreadsheet(filename, raw)
                except Exception:
                    self.send_json({"error": "This file is not a readable .xlsx or .csv spreadsheet"}, 400)
                    return
                with connection() as db:
                    if path == "/api/assets/import":
                        result = import_assets(db, rows, user)
                    else:
                        result = import_employees(db, rows, user)
                self.send_json(result)
                return
            self.send_json({"error": "Not found"}, 404)
        except sqlite3.IntegrityError:
            self.send_json({"error": "That asset tag, username or employee ID already exists"}, 409)
        except (ValueError, json.JSONDecodeError) as exc:
            self.send_json({"error": str(exc)}, 400)

    def do_PUT(self):
        path = urlparse(self.path).path
        try:
            payload = self.read_json()
            if path.startswith("/api/assets/"):
                user = self.require("can_write")
                if not user:
                    return
                asset_id = int(path.rsplit("/", 1)[1])
                item = clean_asset(payload)
                if not item["asset_tag"] or not item["name"]:
                    self.send_json({"error": "Asset tag and name are required"}, 400)
                    return
                assignments = ",".join(f"{field}=?" for field in FIELDS)
                with connection() as db:
                    active_assignment = db.execute("""SELECT e.name,e.department FROM asset_assignments aa
                        JOIN employees e ON e.id=aa.employee_id
                        WHERE aa.asset_id=? AND aa.returned_date IS NULL""", (asset_id,)).fetchone()
                    if active_assignment:
                        item["status"] = "In use"
                        item["assigned_to"] = active_assignment["name"]
                        item["department"] = active_assignment["department"]
                    cur = db.execute(f"UPDATE assets SET {assignments},updated_at=CURRENT_TIMESTAMP WHERE id=?", (*[item[f] for f in FIELDS], asset_id))
                    audit(db, user, "UPDATE", "asset", asset_id, item["asset_tag"])
                self.send_json({"updated": cur.rowcount})
                return
            if path.startswith("/api/users/"):
                admin = self.require_main_admin()
                if not admin:
                    return
                user_id = int(path.rsplit("/", 1)[1])
                role = "admin" if payload.get("role") == "admin" else "user"
                employee_pk = int(payload.get("employee_pk", 0))
                active = int(bool(payload.get("active", True)))
                if not employee_pk:
                    self.send_json({"error": "Select an employee from the Employee list"}, 400)
                    return
                with connection() as db:
                    target = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
                    if not target:
                        self.send_json({"error": "User not found"}, 404)
                        return
                    if target["is_main_admin"]:
                        self.send_json({"error": "The Main Administrator account is managed from Account Settings"}, 400)
                        return
                    employee = db.execute("SELECT * FROM employees WHERE id=? AND active=1", (employee_pk,)).fetchone()
                    if not employee:
                        self.send_json({"error": "Active employee not found"}, 404)
                        return
                    username = unique_username(db, employee["name"], employee["employee_id"], user_id)
                    permissions = tuple(int(bool(payload.get(p))) for p in ("can_read", "can_write", "can_delete")) if role == "admin" else (1, 0, 0)
                    values = [username, employee["name"], employee["employee_id"], employee["designation"], employee_pk, role, *permissions, active]
                    sql = "UPDATE users SET username=?,full_name=?,employee_id=?,designation=?,employee_pk=?,role=?,can_read=?,can_write=?,can_delete=?,active=?,updated_at=CURRENT_TIMESTAMP"
                    password = str(payload.get("password", ""))
                    if password:
                        if len(password) < 8:
                            self.send_json({"error": "Password must be at least 8 characters"}, 400)
                            return
                        sql += ",password_hash=?,must_change_password=1"
                        values.append(password_hash(password))
                    sql += " WHERE id=?"
                    values.append(user_id)
                    db.execute(sql, values)
                    db.execute("DELETE FROM sessions WHERE user_id=? AND user_id<>?", (user_id, admin["id"]))
                    audit(db, admin, "UPDATE", "user", user_id, username)
                self.send_json({"updated": 1})
                return
            if path.startswith("/api/employees/"):
                user = self.require("can_write")
                if not user:
                    return
                employee_pk = int(path.rsplit("/", 1)[1])
                fields, error = clean_employee_payload(payload)
                if error:
                    self.send_json({"error": error}, 400)
                    return
                employee_id, name = fields["employee_id"], fields["name"]
                designation, department = fields["designation"], fields["department"]
                with connection() as db:
                    cur = db.execute("""UPDATE employees SET employee_id=?,name=?,designation=?,department=?,
                        phone=?,email=?,updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                        (employee_id, name, designation, department, fields["phone"], fields["email"], employee_pk))
                    if not cur.rowcount:
                        self.send_json({"error": "Employee not found"}, 404)
                        return
                    db.execute("""UPDATE assets SET assigned_to=?,department=?,updated_at=CURRENT_TIMESTAMP
                        WHERE id IN (SELECT asset_id FROM asset_assignments WHERE employee_id=? AND returned_date IS NULL)""",
                        (name, department, employee_pk))
                    linked_user = db.execute("SELECT id FROM users WHERE employee_pk=?", (employee_pk,)).fetchone()
                    if linked_user:
                        username = unique_username(db, name, employee_id, linked_user["id"])
                        db.execute("""UPDATE users SET username=?,full_name=?,employee_id=?,designation=?,
                            updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                            (username, name, employee_id, designation, linked_user["id"]))
                    audit(db, user, "UPDATE", "employee", employee_pk, f"{employee_id} - {name}")
                self.send_json({"updated": 1})
                return
            if path.startswith("/api/network-devices/"):
                user = self.require("can_write")
                if not user:
                    return
                device_id = int(path.rsplit("/", 1)[1])
                item = clean_network_device(payload)
                with connection() as db:
                    cur = db.execute("""UPDATE network_devices SET device_type=?,location=?,floor=?,brand=?,
                        router_name=?,device_mac=?,ip_address=?,updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                        (item["device_type"], item["location"], item["floor"], item["brand"],
                         item["router_name"], item["device_mac"], item["ip_address"], device_id))
                    if not cur.rowcount:
                        self.send_json({"error": "Network device not found"}, 404)
                        return
                    audit(db, user, "UPDATE", "network_device", device_id,
                          f"{item['device_type']} - {item['brand']} @ {item['location']}")
                self.send_json({"updated": cur.rowcount})
                return
            self.send_json({"error": "Not found"}, 404)
        except sqlite3.IntegrityError:
            self.send_json({"error": "That asset tag, username or employee ID already exists"}, 409)
        except (ValueError, json.JSONDecodeError) as exc:
            self.send_json({"error": str(exc)}, 400)

    def do_DELETE(self):
        path = urlparse(self.path).path
        try:
            if path.startswith("/api/assets/"):
                user = self.require("can_delete")
                if not user:
                    return
                asset_id = int(path.rsplit("/", 1)[1])
                with connection() as db:
                    if db.execute("SELECT 1 FROM asset_assignments WHERE asset_id=? AND returned_date IS NULL", (asset_id,)).fetchone():
                        self.send_json({"error": "Return this device before deleting the asset"}, 409)
                        return
                    target = db.execute("SELECT asset_tag FROM assets WHERE id=?", (asset_id,)).fetchone()
                    cur = db.execute("DELETE FROM assets WHERE id=?", (asset_id,))
                    audit(db, user, "DELETE", "asset", asset_id, target[0] if target else "")
                self.send_json({"deleted": cur.rowcount})
                return
            if path.startswith("/api/users/"):
                admin = self.require_main_admin()
                if not admin:
                    return
                user_id = int(path.rsplit("/", 1)[1])
                if user_id == admin["id"]:
                    self.send_json({"error": "You cannot delete your own account"}, 400)
                    return
                with connection() as db:
                    target = db.execute("SELECT username,role,is_main_admin FROM users WHERE id=?", (user_id,)).fetchone()
                    if not target:
                        self.send_json({"error": "User not found"}, 404)
                        return
                    if target["is_main_admin"]:
                        self.send_json({"error": "The Main Administrator account cannot be deleted"}, 400)
                        return
                    db.execute("DELETE FROM users WHERE id=?", (user_id,))
                    audit(db, admin, "DELETE", "user", user_id, target["username"])
                self.send_json({"deleted": 1})
                return
            if path.startswith("/api/employees/"):
                user = self.require("can_delete")
                if not user:
                    return
                if user["role"] != "admin":
                    self.send_json({"error": "Administrator permission is required"}, 403)
                    return
                employee_pk = int(path.rsplit("/", 1)[1])
                with connection() as db:
                    target = db.execute("SELECT employee_id,name FROM employees WHERE id=?", (employee_pk,)).fetchone()
                    if not target:
                        self.send_json({"error": "Employee not found"}, 404)
                        return
                    if db.execute("SELECT 1 FROM asset_assignments WHERE employee_id=? AND returned_date IS NULL", (employee_pk,)).fetchone():
                        self.send_json({"error": "Return all devices before deleting this employee"}, 409)
                        return
                    linked = db.execute("SELECT id,is_main_admin FROM users WHERE employee_pk=?", (employee_pk,)).fetchone()
                    if linked and linked["is_main_admin"]:
                        self.send_json({"error": "This employee is linked to the Main Administrator"}, 409)
                        return
                    if linked:
                        db.execute("DELETE FROM users WHERE id=?", (linked["id"],))
                    db.execute("DELETE FROM asset_assignments WHERE employee_id=?", (employee_pk,))
                    db.execute("DELETE FROM employees WHERE id=?", (employee_pk,))
                    audit(db, user, "DELETE", "employee", employee_pk, f"{target['employee_id']} - {target['name']}")
                self.send_json({"deleted": 1, "linked_login_deleted": bool(linked)})
                return
            if path.startswith("/api/network-devices/"):
                user = self.require("can_delete")
                if not user:
                    return
                device_id = int(path.rsplit("/", 1)[1])
                with connection() as db:
                    target = db.execute("SELECT device_type,brand FROM network_devices WHERE id=?", (device_id,)).fetchone()
                    cur = db.execute("DELETE FROM network_devices WHERE id=?", (device_id,))
                    if target:
                        audit(db, user, "DELETE", "network_device", device_id, f"{target['device_type']} - {target['brand']}")
                self.send_json({"deleted": cur.rowcount})
                return
            self.send_json({"error": "Not found"}, 404)
        except ValueError:
            self.send_json({"error": "Invalid record id"}, 400)


if __name__ == "__main__":
    initialize()
    host = os.environ.get("APS_HOST", "0.0.0.0")
    port = int(os.environ.get("APS_PORT", "8090"))
    run_hours = float(os.environ.get("APS_RUN_HOURS", "8"))
    try:
        server = ThreadingHTTPServer((host, port), Handler)
    except OSError as exc:
        print()
        print(f"ERROR: Cannot start Aurora Plant IT Inventory on port {port}.")
        print("An older inventory server or another program may still be running.")
        print("Close the old Aurora server window, then run this launcher again.")
        print(f"Windows detail: {exc}")
        raise SystemExit(1)
    print(f"Aurora Plant IT Inventory running on http://{host}:{port}")
    print(f"Version: {APP_VERSION}")
    print(f"The server will stop automatically after {run_hours:g} hours.")
    print("Press Ctrl+C to stop earlier.")
    if run_hours > 0:
        import threading
        timer = threading.Timer(run_hours * 3600, server.shutdown)
        timer.daemon = True
        timer.start()
    if os.environ.get("APS_OPEN_BROWSER", "0") == "1":
        webbrowser.open(f"http://localhost:{port}/login?release={APP_VERSION}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        print("Aurora Plant IT Inventory server stopped.")
