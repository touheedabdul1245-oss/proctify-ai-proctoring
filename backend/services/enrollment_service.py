"""
Bulk enrollment service: parse Excel/CSV, validate rows, detect duplicates,
stage a preview, then commit an import transactionally.

Expected columns (in any order, header optional but recommended):
    student_id | student id | id
    name       | full_name  | full name | student name
    email      | email_id
    class      | class_code | batch | class code

Rejects files with unknown/missing columns. Duplicates are detected against:
  - the database (existing students by student_id or email)
  - within the same file (repeated student_id / email in the import)
"""
import io
import re
import uuid

import pandas as pd
from sqlalchemy.orm import Session

from ..config import MAX_BULK_ROWS
from ..models import BulkImport, BulkImportRow, ClassGroup, Enrollment, Exam, Student, User
from ..usernames import slugify_email, unique_username

ID_COLUMNS = ["student_id", "student id", "id", "reg_no", "reg no", "roll_no", "roll no"]
NAME_COLUMNS = ["name", "full_name", "full name", "student name", "student_name"]
EMAIL_COLUMNS = ["email", "email_id", "email id", "mail", "email address"]
CLASS_COLUMNS = ["class", "class_code", "class code", "batch", "section", "class/batch", "class / batch"]

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


class ParsedFile:
    def __init__(self, rows, columns: dict):
        self.rows = rows
        self.columns = columns


def _normalize_col(name: str) -> str:
    return str(name).strip().lower().replace("_", " ")


def parse_upload(raw: bytes, filename: str) -> ParsedFile:
    """Parse an Excel (.xlsx/.xls) or CSV upload into normalized dict rows."""
    name_lower = filename.lower()
    try:
        if name_lower.endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(raw), dtype=str)
        elif name_lower.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(raw), dtype=str)
        else:
            raise ValueError("Unsupported file type. Please upload an Excel (.xlsx/.xls) or CSV file.")

        # try to read data starting after any title/header rows
        df = df.dropna(how="all")
    except Exception as exc:
        raise ValueError(f"Could not read file: {exc}")

    if df.empty:
        raise ValueError("File contains no rows.")

    norm_map = {_normalize_col(c): str(c) for c in df.columns}
    col_map = {"student_id": None, "name": None, "email": None, "class": None}

    for canonical, variants in [
        ("student_id", ID_COLUMNS),
        ("name", NAME_COLUMNS),
        ("email", EMAIL_COLUMNS),
        ("class", CLASS_COLUMNS),
    ]:
        for v in variants:
            key = _normalize_col(v)
            if key in norm_map:
                col_map[canonical] = norm_map[key]
                break

    missing = [k for k, v in col_map.items() if v is None and k != "class"]
    if missing:
        raise ValueError(
            "Missing required column(s): " + ", ".join(missing) +
            ". Expected: student_id, name, email (class optional)."
        )

    rows = []
    for idx, row in df.iterrows():
        get = lambda c: (str(row[col_map[c]]).strip() if col_map[c] else "")
        rows.append({
            "row_number": idx + 2,  # +1 for data idx, +1 for header
            "student_id": get("student_id"),
            "name": get("name"),
            "email": get("email"),
            "class": get("class"),
        })
    return ParsedFile(rows=rows, columns=col_map)


def _validate_row(row) -> str:
    if not row["student_id"]:
        return "Missing student ID"
    if not row["email"]:
        return "Missing email"
    if not row["name"]:
        return "Missing student name"
    if not EMAIL_RE.match(row["email"]):
        return f"Invalid email format: {row['email']}"
    if len(row["student_id"]) > 50:
        return "Student ID too long (max 50 chars)"
    if len(row["name"]) > 255:
        return "Name too long (max 255 chars)"
    return ""


def stage_preview(db: Session, parsed: ParsedFile, total_rows: int) -> BulkImport:
    """Validate rows and stage a BulkImport record with PREVIEWED status rows."""
    if total_rows > MAX_BULK_ROWS:
        raise ValueError(f"Too many rows: {total_rows} (max {MAX_BULK_ROWS}).")

    existing_ids = {sid for (sid,) in db.query(Student.student_id).all()}
    existing_emails = {em for (em,) in db.query(Student.email).all()}

    seen_ids = set()
    seen_emails = set()
    valid, invalid, duplicates = 0, 0, 0

    bi = BulkImport(
        filename="preview",
        total_rows=total_rows,
        status="PREVIEWED",
        summary="",
    )
    db.add(bi)
    db.flush()

    for row in parsed.rows:
        err = _validate_row(row)

        # duplicate check: database + within-file
        is_dup = False
        if not err:
            if row["student_id"] in existing_ids or row["student_id"].lower() in seen_ids:
                is_dup = True
                err = "Duplicate student ID"
            elif row["email"].lower() in existing_emails or row["email"].lower() in seen_emails:
                is_dup = True
                err = "Duplicate email"

        if not err:
            seen_ids.add(row["student_id"].lower())
            seen_emails.add(row["email"].lower())
            rstatus = "VALID"
            valid += 1
        elif is_dup:
            rstatus = "DUPLICATE"
            duplicates += 1
        else:
            rstatus = "INVALID"
            invalid += 1

        db.add(BulkImportRow(
            bulk_import_id=bi.id,
            row_number=row["row_number"],
            student_id=row["student_id"],
            full_name=row["name"],
            email=row["email"],
            class_code=row["class"] or None,
            status=rstatus,
            error_message=err or None,
        ))

    summary = (
        f"Total: {total_rows}, Valid: {valid}, Duplicates: {duplicates}, Invalid: {invalid}"
    )
    bi.valid_rows = valid
    bi.invalid_rows = invalid
    bi.duplicate_rows = duplicates
    bi.summary = summary
    db.commit()
    db.refresh(bi)
    return bi


def confirm_import(db: Session, import_id: int, created_by_user_id: int = None) -> dict:
    """Import all VALID rows transactionally. Returns a summary dict."""
    from ..auth import hash_password
    from ..config import DEFAULT_STUDENT_PASSWORD

    bi = db.query(BulkImport).filter(BulkImport.id == import_id).first()
    if not bi:
        raise ValueError("Preview not found. Upload again.")

    rows = db.query(BulkImportRow).filter(BulkImportRow.bulk_import_id == bi.id).all()
    valid_rows = [r for r in rows if r.status == "VALID"]

    imported, errors = 0, []

    for r in valid_rows:
        try:
            klass = None
            if r.class_code:
                klass = db.query(ClassGroup).filter(ClassGroup.code == r.class_code).first()
                if not klass:
                    klass = ClassGroup(code=r.class_code, name=r.class_code)
                    db.add(klass)
                    db.flush()

            user = User(
                email=r.email,
                username=unique_username(db, slugify_email(r.email)),
                password_hash=hash_password(DEFAULT_STUDENT_PASSWORD),
                full_name=r.full_name,
                role="student",
            )
            db.add(user)
            db.flush()

            student = Student(
                user_id=user.id,
                student_id=r.student_id,
                email=r.email,
                full_name=r.full_name,
                class_id=klass.id if klass else None,
            )
            db.add(student)
            db.flush()

            db.add(Enrollment(
                student_id_db=student.id,
                class_id=klass.id if klass else None,
                source="bulk",
                bulk_import_id=bi.id,
            ))
            r.status = "IMPORTED"
            imported += 1
        except Exception as exc:
            db.rollback()
            r.status = "INVALID"
            r.error_message = f"Import failed: {exc}"
            errors.append(f"Row {r.row_number}: {exc}")

    # mark any remaining non-imported rows SKIPPED
    for r in rows:
        if r.status != "IMPORTED":
            if r.status == "VALID":
                r.status = "SKIPPED"

    bi.status = "IMPORTED"
    bi.imported_count = imported
    bi.valid_rows = len(valid_rows)
    bi.summary = (
        f"Imported: {imported}, Duplicates skipped: {bi.duplicate_rows}, Invalid skipped: {bi.invalid_rows}"
    )
    db.commit()

    return {
        "import_id": bi.id,
        "imported": imported,
        "skipped_duplicates": bi.duplicate_rows,
        "invalid": bi.invalid_rows,
        "errors": errors,
    }


def generate_exam_code(db: Session) -> str:
    """Generate a unique exam code."""
    while True:
        code = "EX-" + uuid.uuid4().hex[:8].upper()
        if not db.query(Exam).filter(Exam.exam_code == code).first():
            return code