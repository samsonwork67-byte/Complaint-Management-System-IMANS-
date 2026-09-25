import os
import uuid
import re
from datetime import datetime
import db
from psycopg2.extras import Json

ALLOWED_COLUMNS = {
    "complaint": {
        "id", "Timestamp", "Tracking ID", "Complaint Reference ID", "Your Name",
        "Email address", "Your Phone Number", "Name of The Accused",
        "Position of The Accused", "Company of The Accused", "Type of Complaint",
        "Details of Complaint", "Date of Incident", "Time of Incident (General)",
        "Location of Incident", "Other involved parties (If applicable)",
        "Upload file if there are evidences", "Status", "Remarks", "Last Updated Date",
        "Notify Complainant", "Last Email Sent", "FollowupToken", "AdminRemarks",
        "LastReviewDate", "FollowupFiles", "FollowupResponse", "Source",
        "Email UID", "AI Confidence", "Needs Review"
    },
    "governance": {"id", "title", "description", "file_url", "created_at", "updated_at", "created_by", "updated_by"},
    "integrity_events": {"id", "date", "title", "description", "images"},
    "resources": {"id", "title", "description", "file_url", "file_size", "updated_date", "icon", "created_at"},
    "contact_messages": {"id", "name", "email", "message", "created_at"},
    "admin_users": {"id", "username", "email", "password_hash", "role", "is_active", "created_at"},
    "processed_emails": {"id", "message_id", "processed_at"},
    "audit_logs": {"id", "admin_id", "action_type", "target", "details", "session_id", "timestamp"},
    "complaint_sections": {"id", "complaint_id", "section_type", "title", "content", "created_by", "created_at", "updated_at"},
    "complaint_section_files": {"id", "section_id", "file_name", "file_url", "file_type", "uploaded_by", "uploaded_at"},
}

IDENTIFIER_RE = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')

def validate_identifier(name: str, table: str = None) -> str:
    """Validate column/table name against allowlist and regex."""
    if not IDENTIFIER_RE.match(name):
        raise ValueError(f"Invalid identifier: {name}")
    if table and table in ALLOWED_COLUMNS:
        if name not in ALLOWED_COLUMNS[table]:
            raise ValueError(f"Column '{name}' not allowed for table '{table}'")
    return name

class PostgresResponse:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count
        self.error = None

class PostgresQueryBuilder:
    def __init__(self, table):
        self.table = table
        self._action = None  # 'select', 'insert', 'update', 'delete'
        self._select_cols = "*"
        self._count_mode = None
        self._insert_data = None
        self._update_data = None
        self._eq_filters = []   # list of (col, val)
        self._neq_filters = []  # list of (col, val)
        self._like_filters = [] # list of (col, val)
        self._ilike_filters = [] # list of (col, val)
        self._gt_filters = []  # list of (col, val)
        self._gte_filters = [] # list of (col, val)
        self._lt_filters = []  # list of (col, val)
        self._lte_filters = [] # list of (col, val)
        self._in_filters = []   # list of (col, vals)
        self._order_by = []     # list of (col, desc)
        self._limit = None
        self._offset = None
        self._single = False

    def select(self, cols="*", count=None):
        self._action = 'select'
        self._select_cols = cols
        self._count_mode = count
        return self

    def insert(self, data):
        self._action = 'insert'
        self._insert_data = data
        return self

    def update(self, data):
        self._action = 'update'
        self._update_data = data
        return self

    def delete(self):
        self._action = 'delete'
        return self

    def eq(self, col, val):
        self._eq_filters.append((col, val))
        return self

    def neq(self, col, val):
        self._neq_filters.append((col, val))
        return self

    def like(self, col, val):
        self._like_filters.append((col, val))
        return self

    def ilike(self, col, val):
        self._ilike_filters.append((col, val))
        return self

    def gt(self, col, val):
        self._gt_filters.append((col, val))
        return self

    def gte(self, col, val):
        self._gte_filters.append((col, val))
        return self

    def lt(self, col, val):
        self._lt_filters.append((col, val))
        return self

    def lte(self, col, val):
        self._lte_filters.append((col, val))
        return self

    def in_(self, col, vals):
        self._in_filters.append((col, vals))
        return self

    def order(self, col, desc=False):
        self._order_by.append((col, desc))
        return self

    def limit(self, limit_value):
        self._limit = limit_value
        return self

    def range(self, start, end):
        self._offset = start
        self._limit = end - start + 1
        return self

    def single(self):
        self._single = True
        return self

    def maybe_single(self):
        self._single = True
        return self

    def execute(self):
        where_parts = []
        params = []

        # Validate all column identifiers before building SQL
        for col, val in self._eq_filters:
            validate_identifier(col, self.table)
            where_parts.append(f'"{col}" = %s')
            params.append(val)

        for col, val in self._neq_filters:
            validate_identifier(col, self.table)
            where_parts.append(f'"{col}" != %s')
            params.append(val)

        for col, val in self._like_filters:
            validate_identifier(col, self.table)
            where_parts.append(f'"{col}" LIKE %s')
            params.append(val)

        for col, val in self._ilike_filters:
            validate_identifier(col, self.table)
            where_parts.append(f'LOWER("{col}") LIKE LOWER(%s)')
            params.append(val)

        for col, val in self._gt_filters:
            validate_identifier(col, self.table)
            where_parts.append(f'"{col}" > %s')
            params.append(val)

        for col, val in self._gte_filters:
            validate_identifier(col, self.table)
            where_parts.append(f'"{col}" >= %s')
            params.append(val)

        for col, val in self._lt_filters:
            validate_identifier(col, self.table)
            where_parts.append(f'"{col}" < %s')
            params.append(val)

        for col, val in self._lte_filters:
            validate_identifier(col, self.table)
            where_parts.append(f'"{col}" <= %s')
            params.append(val)

        for col, vals in self._in_filters:
            validate_identifier(col, self.table)
            if vals is None:
                where_parts.append(f'"{col}" IS NULL')
            elif isinstance(vals, (list, tuple, set)) and vals:
                placeholders = ', '.join(['%s'] * len(vals))
                where_parts.append(f'"{col}" IN ({placeholders})')
                params.extend(vals)
            else:
                where_parts.append(f'"{col}" = %s')
                params.append(vals)

        where_clause = " AND ".join(where_parts)
        if where_clause:
            where_clause = " WHERE " + where_clause
        else:
            where_clause = ""

        # Count query if needed
        count_val = None
        if self._action == 'select' and self._count_mode == 'exact':
            count_sql = f'SELECT COUNT(*) FROM "{self.table}" {where_clause}'
            count_val = db.count(count_sql, params)

        if self._action == 'select':
            cols = self._select_cols
            if cols != "*":
                cols_list = [c.strip().replace('"', '') for c in cols.split(",")]
                # Validate each column
                for c in cols_list:
                    validate_identifier(c, self.table)
                cols_formatted = ", ".join(f'"{c}"' for c in cols_list)
            else:
                cols_formatted = "*"

            sql = f'SELECT {cols_formatted} FROM "{self.table}" {where_clause}'

            if self._order_by:
                order_parts = []
                for col, desc in self._order_by:
                    validate_identifier(col, self.table)
                    dir_str = "DESC" if desc else "ASC"
                    order_parts.append(f'"{col}" {dir_str}')
                sql += " ORDER BY " + ", ".join(order_parts)

            if self._limit is not None:
                sql += f" LIMIT {self._limit}"
            if self._offset is not None:
                sql += f" OFFSET {self._offset}"

            data = db.query(sql, params)
            if self._single:
                data = data[0] if data else None

            return PostgresResponse(data, count_val)

        elif self._action == 'insert':
            if isinstance(self._insert_data, list):
                res_data = []
                for row in self._insert_data:
                    inserted = db.insert_row(f'"{self.table}"', row)
                    if inserted:
                        res_data.extend(inserted)
                if self._single:
                    res_data = res_data[0] if res_data else None
                return PostgresResponse(res_data)
            else:
                inserted = db.insert_row(f'"{self.table}"', self._insert_data)
                res_data = inserted
                if self._single:
                    res_data = res_data[0] if res_data else None
                return PostgresResponse(res_data)

        elif self._action == 'update':
            if not where_parts:
                raise ValueError("Cannot execute update without filters (where clause)")

            cols = list(self._update_data.keys())
            for c in cols:
                validate_identifier(c, self.table)
            vals = []
            for v in self._update_data.values():
                if isinstance(v, (list, dict)):
                    vals.append(Json(v))
                else:
                    vals.append(v)
            set_clause = ', '.join(f'"{c}" = %s' for c in cols)
            sql = f'UPDATE "{self.table}" SET {set_clause} {where_clause} RETURNING *'
            all_params = vals + params
            res_data = db.execute(sql, all_params)
            if self._single:
                res_data = res_data[0] if res_data else None
            return PostgresResponse(res_data)

        elif self._action == 'delete':
            sql = f'DELETE FROM "{self.table}" {where_clause} RETURNING *'
            res_data = db.execute(sql, params)
            if self._single:
                res_data = res_data[0] if res_data else None
            return PostgresResponse(res_data)

        raise ValueError(f"Unknown action: {self._action}")

class PostgresClient:
    def table(self, table_name):
        return PostgresQueryBuilder(table_name)


db_client = PostgresClient()

def generate_complaint_ref_and_accept(complaint_id):
    """Ensure the complaint has a Complaint Reference ID and mark it ACCEPTED.

    Returns the complaint reference ID (existing or newly generated).
    Raises ValueError if complaint not found or update fails.
    Uses atomic sequence to avoid race conditions.
    """
    resp = db_client.table('complaint').select('*').eq('id', complaint_id).maybe_single().execute()
    if not resp or not getattr(resp, 'data', None):
        raise ValueError('Complaint not found')

    complaint = resp.data
    existing_ref = complaint.get('Complaint Reference ID')
    if existing_ref:
        return existing_ref

    # Atomic reference ID generation using sequence
    new_ref = _generate_ref_id_atomic(db_client)
    
    update_resp = db_client.table('complaint').update({
        'Complaint Reference ID': new_ref,
        'LastReviewDate': datetime.now().isoformat()
    }).eq('id', complaint_id).execute()

    confirm = db_client.table('complaint').select('*').eq('id', complaint_id).maybe_single().execute()
    if not confirm or not getattr(confirm, 'data', None):
        raise ValueError('Failed to confirm complaint update')
    persisted_ref = confirm.data.get('Complaint Reference ID')
    if not persisted_ref:
        raise ValueError('Complaint Reference ID not persisted')
    return persisted_ref


def _generate_ref_id_atomic(client):
    """Generate a unique Complaint Reference ID using atomic database sequence."""
    year = datetime.now().year
    # Use PostgreSQL sequence for atomic increment
    seq_name = f"complaint_ref_seq_{year}"
    sql = f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_class WHERE relname = '{seq_name}') THEN
                CREATE SEQUENCE {seq_name} START 1;
            END IF;
        END $$;
        SELECT nextval('{seq_name}');
    """
    # Execute sequence creation and nextval
    conn = db._get_valid_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            seq_val = cur.fetchone()[0]
        conn.commit()
    finally:
        db._pool.putconn(conn)
    return f"IGD-{year}-{seq_val:03d}"
