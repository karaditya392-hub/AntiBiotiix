"""
Clinician Role Authorization & Security Layer (Sections 18, 18A)
Enforces server-side token generation, session verification, and role resolution.
"""
import uuid
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

# Server-side token registry mapping access_token -> {"clinician_id": ..., "clinician_role": ...}
# In production, this would be backed by Redis / JWT secret / OAuth2 / SAML
SESSION_REGISTRY: Dict[str, Dict[str, Any]] = {
    # Seed default tokens for automated testing / initial administrative demo access
    "mock_attending_token": {
        "clinician_id": "DOC-ATTENDING-01",
        "clinician_role": "ATTENDING_PHYSICIAN"
    },
    "mock_nurse_token": {
        "clinician_id": "NURSE-STAFF-01",
        "clinician_role": "STAFF_NURSE"
    },
    "mock_id_specialist_token": {
        "clinician_id": "DOC-ID-LEAD-01",
        "clinician_role": "INFECTIOUS_DISEASE_SPECIALIST"
    }
}

security_bearer = HTTPBearer(auto_error=False)


def create_session_token(clinician_id: str, clinician_role: str) -> str:
    """Create a server-side session token encoding clinician identity and role."""
    token = f"tok_{uuid.uuid4().hex}"
    SESSION_REGISTRY[token] = {
        "clinician_id": clinician_id.upper(),
        "clinician_role": clinician_role.upper()
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
