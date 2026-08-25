"""
Clinician Role Authorization & Security Layer (Sections 18, 18A)
Enforces server-side token generation, session verification, and role resolution.
"""
import uuid
import hashlib
import hmac
from typing import Optional, Dict, Any
from fastapi import HTTPException, Security, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from backend.config import AUTHORIZED_OVERRIDE_ROLES, AUTHORIZED_RULE_AUTHORING_ROLES

# Roles permitted to create patient records and edit medication lists. A PATIENT
# principal is deliberately absent: patients may report their own allergies, but
# medication reconciliation is a clinical act.
PATIENT_MANAGEMENT_ROLES = [
    "ATTENDING_PHYSICIAN",
    "INFECTIOUS_DISEASE_SPECIALIST",
    "CLINICAL_PHARMACIST",
    "RESIDENT_PHYSICIAN",
    "STAFF_NURSE",
]

# Password Hashing Helpers
def hash_password(password: str, salt: str = "microbe_oauth_salt_2026") -> str:
    """Generate PBKDF2 SHA-256 hash of password."""
    return hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    ).hex()


def verify_password(plain_password: str, hashed_password: str, salt: str = "microbe_oauth_salt_2026") -> bool:
    """Verify plain text password against stored hash using constant-time comparison."""
    if not plain_password or not hashed_password:
        return False
    computed_hash = hash_password(plain_password, salt)
    return hmac.compare_digest(computed_hash, hashed_password)


# Doctor Credential Registry
DOCTOR_CREDENTIALS: Dict[str, Dict[str, Any]] = {}

_DEFAULT_DOCTORS = [
    {
        "doctor_id": "DOC-ATTENDING-01",
        "display_name": "Dr. Rajesh Verma",
        "role": "ATTENDING_PHYSICIAN",
        "password": "doctorpassword123",
    },
    {
        "doctor_id": "DOC-DEMO-01",
        "display_name": "Dr. Suresh Kumar",
        "role": "ATTENDING_PHYSICIAN",
        "password": "doctorpassword123",
    },
    {
        "doctor_id": "DOC-ID-LEAD-01",
        "display_name": "Dr. Ananya Roy",
        "role": "INFECTIOUS_DISEASE_SPECIALIST",
        "password": "doctorpassword123",
    },
    {
        "doctor_id": "DOC-PHARM-01",
        "display_name": "Dr. Priya Sharma",
        "role": "CLINICAL_PHARMACIST",
        "password": "doctorpassword123",
    },
    {
        "doctor_id": "NURSE-STAFF-01",
        "display_name": "Staff Nurse Priya",
        "role": "STAFF_NURSE",
        "password": "nursepassword123",
    },
]

for d in _DEFAULT_DOCTORS:
    DOCTOR_CREDENTIALS[d["doctor_id"].upper()] = {
        "doctor_id": d["doctor_id"].upper(),
        "display_name": d["display_name"],
        "role": d["role"].upper(),
        "password_hash": hash_password(d["password"]),
    }


def verify_doctor_credentials(
    doctor_id: str,
    password: str,
    db: Optional[Any] = None
) -> Optional[Dict[str, Any]]:
    """
    Verify doctor ID and password credentials against Database or Registry.
    Returns doctor metadata dict if valid, or None if invalid.
    """
    if not doctor_id or not password:
        return None

    normalized_id = doctor_id.strip().upper()

    # 1. Check in Database if session available
    if db is not None:
        try:
            from backend.models.database import DoctorDB
            doc_db = db.query(DoctorDB).filter(DoctorDB.doctor_id == normalized_id).first()
            if doc_db and doc_db.password_hash:
                if verify_password(password, doc_db.password_hash):
                    return {
                        "doctor_id": doc_db.doctor_id,
                        "display_name": doc_db.display_name,
                        "role": doc_db.role,
                    }
        except Exception:
            pass

    # 2. Check in In-Memory DOCTOR_CREDENTIALS Registry
    doc_reg = DOCTOR_CREDENTIALS.get(normalized_id)
    if doc_reg and verify_password(password, doc_reg["password_hash"]):
        return {
            "doctor_id": doc_reg["doctor_id"],
            "display_name": doc_reg["display_name"],
            "role": doc_reg["role"],
        }

    return None


# Server-side token registry mapping access_token -> {"clinician_id": ..., "clinician_role": ..., "display_name": ...}
SESSION_REGISTRY: Dict[str, Dict[str, Any]] = {
    # Seed default tokens for automated testing / initial administrative demo access
    "mock_attending_token": {
        "clinician_id": "DOC-ATTENDING-01",
        "clinician_role": "ATTENDING_PHYSICIAN",
        "display_name": "Dr. Rajesh Verma",
    },
    "mock_nurse_token": {
        "clinician_id": "NURSE-STAFF-01",
        "clinician_role": "STAFF_NURSE",
        "display_name": "Staff Nurse Priya",
    },
    "mock_id_specialist_token": {
        "clinician_id": "DOC-ID-LEAD-01",
        "clinician_role": "INFECTIOUS_DISEASE_SPECIALIST",
        "display_name": "Dr. Ananya Roy",
    }
}

security_bearer = HTTPBearer(auto_error=False)


def create_session_token(clinician_id: str, clinician_role: str, display_name: Optional[str] = None) -> str:
    """Create a server-side session token encoding clinician identity and role."""
    token = f"tok_{uuid.uuid4().hex}"
    SESSION_REGISTRY[token] = {
        "clinician_id": clinician_id.upper(),
        "clinician_role": clinician_role.upper(),
        "display_name": display_name or clinician_id.upper(),
    }
    return token


def create_patient_token(patient_id: str) -> str:
    """
    Issue a session token for a patient principal, scoped to one record.

    The scope is carried on the session itself rather than passed by the caller,
    so a patient cannot widen it by changing a request body.
    """
    token = f"ptok_{uuid.uuid4().hex}"
    SESSION_REGISTRY[token] = {
        "clinician_id": patient_id.upper(),
        "clinician_role": "PATIENT",
        "patient_scope": patient_id.upper(),
    }
    return token


def get_current_principal(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer)
) -> Dict[str, str]:
    """
    Resolve any authenticated principal - clinician or patient - from the
    server-side token. Use this where both may act; use get_current_clinician
    where a patient must never be permitted.
    """
    return get_current_clinician(credentials)


def require_clinician(principal: Dict[str, str]) -> Dict[str, str]:
    """Reject a PATIENT principal from a clinician-only action."""
    if principal.get("clinician_role", "").upper() == "PATIENT":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action requires a clinician account. Patient logins may report allergies only.",
        )
    return principal


def require_patient_scope(principal: Dict[str, str], patient_id: str) -> None:
    """
    A patient principal may only act on their own record. Clinicians are not
    scope-limited here; ward-level access control is out of scope for this
    prototype and is documented as such.
    """
    if principal.get("clinician_role", "").upper() != "PATIENT":
        return
    scope = (principal.get("patient_scope") or "").upper()
    if scope != (patient_id or "").upper():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A patient login may only submit information about their own record.",
        )


def get_current_clinician(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer)
) -> Dict[str, str]:
    """
    FastAPI dependency: Resolves authenticated clinician identity and role strictly from server-side token.
    Rejects missing or invalid tokens with HTTP 401.
    """
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials required. Please provide a valid Bearer token in the Authorization header."
        )

    token = credentials.credentials
    session = SESSION_REGISTRY.get(token)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session token. Please authenticate via /api/auth/login."
        )

    return session


class SecurityAuthorizer:
    @staticmethod
    def verify_override_authorization(clinician_role: str, clinician_id: str) -> bool:
        """
        Verify that the resolved user holds a designated clinical role authorized to override safety warnings.
        """
        if not clinician_role or not clinician_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Clinician identity and role are required to perform an override."
            )
            
        role_str = clinician_role.upper()
        if role_str not in AUTHORIZED_OVERRIDE_ROLES:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{clinician_role}' is not authorized to override clinical safety warnings. Authorized roles: {', '.join(AUTHORIZED_OVERRIDE_ROLES)}"
            )
            
        return True

    @staticmethod
    def verify_rule_authoring_authorization(author_role: str, author_id: str) -> bool:
        """
        Verify authorization for modifying or creating clinical safety rules.
        """
        if not author_role or not author_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Author identity and role required for rule management."
            )
            
        if author_role.upper() not in AUTHORIZED_RULE_AUTHORING_ROLES:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{author_role}' is not authorized to author/modify clinical rules. Authorized roles: {', '.join(AUTHORIZED_RULE_AUTHORING_ROLES)}"
            )
            
        return True


authorizer = SecurityAuthorizer()
