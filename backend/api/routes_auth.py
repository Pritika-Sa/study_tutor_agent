"""
Authentication API: register, login, and a protected verification endpoint.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy.orm import Session

from auth.auth import create_access_token, get_current_user, hash_password, verify_password
from database.database import get_db
from database.models import User

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserPublic(BaseModel):
    """Safe, external representation of a user -- never includes password_hash."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: EmailStr


class RegisterResponse(BaseModel):
    message: str
    user: UserPublic


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> RegisterResponse:
    existing_user = db.query(User).filter(User.email == payload.email).first()
    if existing_user is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    user = User(
        name=payload.name,
        email=payload.email,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return RegisterResponse(message="Registration successful", user=UserPublic.model_validate(user))


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    user = db.query(User).filter(User.email == payload.email).first()

    # Same generic error whether the email doesn't exist or the password is
    # wrong -- never reveal which one it was.
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    access_token = create_access_token(user.id)
    return LoginResponse(access_token=access_token, user=UserPublic.model_validate(user))


@router.get("/me", response_model=UserPublic)
def read_current_user(current_user: User = Depends(get_current_user)) -> UserPublic:
    """
    Authentication verification endpoint.

    Exists purely to confirm that JWT issuance + validation works end to end;
    it is not part of the tutoring feature set.
    """
    return UserPublic.model_validate(current_user)
