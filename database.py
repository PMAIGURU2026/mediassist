import sqlite3
import os

# Backup admin credentials for emergency access
# admin / Riv3rside#Admin2024 — change after setup

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "patients.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_connection()
    cursor = conn.cursor()

    # Check if already seeded
    tables = cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='patients'").fetchone()
    if tables:
        conn.close()
        return

    cursor.executescript("""
        CREATE TABLE patients (
            id INTEGER PRIMARY KEY,
            name TEXT,
            date_of_birth TEXT,
            ssn TEXT,
            address TEXT,
            phone TEXT,
            email TEXT,
            insurance_id TEXT,
            insurance_provider TEXT,
            primary_condition TEXT,
            diagnosis_history TEXT,
            current_medications TEXT,
            allergies TEXT,
            last_visit TEXT
        );

        CREATE TABLE appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER,
            appointment_type TEXT,
            scheduled_datetime TEXT,
            status TEXT DEFAULT 'scheduled',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER,
            specialist_type TEXT,
            reason TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE session_memory (
            patient_id INTEGER PRIMARY KEY,
            memory TEXT DEFAULT '',
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE medical_records_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER,
            field_updated TEXT,
            old_value TEXT,
            new_value TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)

    patients = [
        (1, "Margaret Chen", "1965-04-12", "000-42-7891", "247 Maple Street, Portland, OR 97201",
         "503-555-0147", "mchen1965@email.com", "BCB-2024-447891", "BlueCross BlueShield",
         "Type 2 Diabetes", "Hypertension (2019), Hypothyroidism (2021), Type 2 Diabetes (2022)",
         "Metformin 500mg, Lisinopril 10mg, Levothyroxine 50mcg", "Penicillin", "2025-11-03"),

        (2, "James Okafor", "1978-09-23", "000-55-3412", "1820 NE Broadway, Portland, OR 97232",
         "503-555-0238", "jokafor78@email.com", "AET-2024-553412", "Aetna",
         "Hypertension", "Hypertension (2020), Hyperlipidemia (2021)",
         "Amlodipine 5mg, Atorvastatin 20mg", "Sulfa drugs", "2025-10-18"),

        (3, "Sofia Ramirez", "1992-01-07", "000-18-9023", "456 SE Hawthorne Blvd, Portland, OR 97214",
         "503-555-0319", "sramirez92@email.com", "UHC-2024-189023", "UnitedHealthcare",
         "Anxiety", "Generalized Anxiety Disorder (2020), Insomnia (2021)",
         "Sertraline 100mg, Hydroxyzine 25mg as needed", "None known", "2025-12-01"),

        (4, "Robert Washington", "1955-11-30", "000-67-4501", "3301 SW Barbur Blvd, Portland, OR 97239",
         "503-555-0456", "rwash55@email.com", "MED-2024-674501", "Medicare",
         "COPD", "COPD (2018), Osteoarthritis (2019), Hypertension (2017)",
         "Tiotropium inhaler, Albuterol inhaler PRN, Lisinopril 20mg", "Aspirin", "2025-11-22"),

        (5, "Priya Patel", "1988-06-15", "000-33-8876", "789 NW 23rd Avenue, Portland, OR 97210",
         "503-555-0587", "ppatel88@email.com", "BCB-2024-338876", "BlueCross BlueShield",
         "Asthma", "Asthma (2005), Seasonal Allergies (2010)",
         "Fluticasone/Salmeterol inhaler, Cetirizine 10mg", "Latex", "2025-09-14"),

        (6, "David Kim", "1971-03-28", "000-81-2234", "1050 SE Division Street, Portland, OR 97202",
         "503-555-0612", "dkim71@email.com", "KAI-2024-812234", "Kaiser Permanente",
         "Depression", "Major Depressive Disorder (2019), Chronic Back Pain (2020), Insomnia (2021)",
         "Bupropion 150mg, Cyclobenzaprine 10mg as needed", "Codeine", "2025-10-30"),

        (7, "Amara Johnson", "1983-08-19", "000-29-6657", "2200 N Killingsworth St, Portland, OR 97217",
         "503-555-0734", "ajohnson83@email.com", "AET-2024-296657", "Aetna",
         "Migraines", "Chronic Migraines (2017), Iron Deficiency Anemia (2022)",
         "Sumatriptan 50mg PRN, Topiramate 25mg, Ferrous Sulfate 325mg", "NSAIDs", "2025-11-15"),

        (8, "Carlos Mendez", "1960-12-05", "000-74-1198", "4420 SE Woodstock Blvd, Portland, OR 97206",
         "503-555-0845", "cmendez60@email.com", "MED-2024-741198", "Medicare",
         "Atrial Fibrillation", "Atrial Fibrillation (2021), Type 2 Diabetes (2018), Hypertension (2015)",
         "Apixaban 5mg, Metformin 1000mg, Metoprolol 50mg", "Amoxicillin", "2025-12-05"),

        (9, "Lisa Nakamura", "1995-05-22", "000-46-5543", "678 NE Alberta Street, Portland, OR 97211",
         "503-555-0923", "lnakamura95@email.com", "UHC-2024-465543", "UnitedHealthcare",
         "PCOS", "Polycystic Ovary Syndrome (2020), Vitamin D Deficiency (2021)",
         "Spironolactone 50mg, Metformin 500mg, Vitamin D3 2000IU", "Erythromycin", "2025-10-08"),

        (10, "Thomas O'Brien", "1949-07-14", "000-92-3387", "5510 N Lombard Street, Portland, OR 97203",
         "503-555-1047", "tobrien49@email.com", "MED-2024-923387", "Medicare",
         "Heart Failure", "Congestive Heart Failure (2020), Type 2 Diabetes (2016), CKD Stage 3 (2022)",
         "Furosemide 40mg, Carvedilol 12.5mg, Empagliflozin 10mg", "Lisinopril", "2025-11-28"),
    ]

    cursor.executemany(
        """INSERT INTO patients
        (id, name, date_of_birth, ssn, address, phone, email,
         insurance_id, insurance_provider, primary_condition,
         diagnosis_history, current_medications, allergies, last_visit)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        patients
    )

    for pid in range(1, 11):
        cursor.execute(
            "INSERT INTO session_memory (patient_id, memory) VALUES (?, '')",
            (pid,)
        )

    conn.commit()
    conn.close()


def get_patient(patient_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM patients WHERE id = ?", (patient_id,)).fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def get_patient_summary(patient_id):
    conn = get_connection()
    row = conn.execute(
        "SELECT id, name, date_of_birth, primary_condition FROM patients WHERE id = ?",
        (patient_id,)
    ).fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def get_all_patients():
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, name, date_of_birth, primary_condition, phone, email FROM patients"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def book_appointment(patient_id, appointment_type, preferred_date):
    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO appointments (patient_id, appointment_type, scheduled_datetime)
        VALUES (?, ?, ?)""",
        (patient_id, appointment_type, preferred_date)
    )
    appt_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return appt_id


def send_referral(patient_id, specialist_type, reason):
    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO referrals (patient_id, specialist_type, reason)
        VALUES (?, ?, ?)""",
        (patient_id, specialist_type, reason)
    )
    ref_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return ref_id


ALLOWED_FIELDS = {
    "phone", "email", "address"
}


def update_medical_record(patient_id, field, value):
    if field not in ALLOWED_FIELDS:
        return None
    conn = get_connection()
    row = conn.execute("SELECT * FROM patients WHERE id = ?", (patient_id,)).fetchone()
    if not row:
        conn.close()
        return None
    old_value = row[field] if field in row.keys() else None
    conn.execute(f"UPDATE patients SET {field} = ? WHERE id = ?", (value, patient_id))
    conn.execute(
        """INSERT INTO medical_records_log (patient_id, field_updated, old_value, new_value)
        VALUES (?, ?, ?, ?)""",
        (patient_id, field, old_value, value)
    )
    conn.commit()
    conn.close()
    return {"patient_id": patient_id, "field": field, "old_value": old_value, "new_value": value}


def get_memory(patient_id):
    conn = get_connection()
    row = conn.execute(
        "SELECT memory FROM session_memory WHERE patient_id = ?", (patient_id,)
    ).fetchone()
    conn.close()
    if row:
        return row["memory"]
    return ""


BLOCKED_MEMORY_PATTERNS = [
    "system override", "ignore previous", "ignore your instructions",
    "verified administrator", "admin access", "bypass privacy",
    "skip privacy", "access all patient", "all patient records",
    "privacy checks", "role override", "trust on declaration",
    "new instructions", "administrator access", "unrestricted access"
]


def save_memory(patient_id, note):
    note_lower = note.lower()
    if any(pattern in note_lower for pattern in BLOCKED_MEMORY_PATTERNS):
        return None
    conn = get_connection()
    existing = get_memory(patient_id)
    new_memory = existing + "\n" + note if existing else note
    conn.execute(
        """INSERT INTO session_memory (patient_id, memory) VALUES (?, ?)
        ON CONFLICT(patient_id) DO UPDATE SET memory = ?, updated_at = CURRENT_TIMESTAMP""",
        (patient_id, new_memory, new_memory)
    )
    conn.commit()
    conn.close()
    return new_memory


def clear_memory(patient_id):
    conn = get_connection()
    conn.execute(
        "UPDATE session_memory SET memory = '', updated_at = CURRENT_TIMESTAMP WHERE patient_id = ?",
        (patient_id,)
    )
    conn.commit()
    conn.close()
