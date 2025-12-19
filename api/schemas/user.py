# schemas/user.py
from typing import Optional
from pydantic import BaseModel, EmailStr, field_validator

class UserCreate(BaseModel):
    name: Optional[str] = None
    email: EmailStr
    password: str

    # ------------- validators -------------
    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8 or len(v) > 32:
            raise ValueError("Password must be 8-32 characters long")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        if not any(c in "!@#$%^&*()-_=+[]{}|;:'\",.<>?/\\`~" for c in v):
            raise ValueError("Password must contain at least one special character")
        return v

    @field_validator("name")
    @classmethod
    def name_format(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if len(v) < 2 or len(v) > 50:
            raise ValueError("Name must be 2-50 characters")
        if not all(c.isalpha() or c in " -" for c in v):
            raise ValueError("Name can only contain letters, spaces or hyphens")
        return v

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: Optional[str] = None
    token_type: Optional[str] = "bearer"
    email: Optional[EmailStr] = None
    msg: Optional[bool] = None 

class TokenData(BaseModel):
    user_id: Optional[int] = None


class ForgotPassword(BaseModel):
    email: EmailStr
    flag: str

class ResetPassword(BaseModel):
    token: str
    new_password: str
    flag: str

    # ------------- validators -------------
    @field_validator("new_password")
    @classmethod
    def new_password_strength(cls, v: str) -> str:
        if len(v) < 8 or len(v) > 32:
            raise ValueError("new_password must be 8-32 characters long")
        if not any(c.isupper() for c in v):
            raise ValueError("new_password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("new_password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("new_password must contain at least one digit")
        if not any(c in "!@#$%^&*()-_=+[]{}|;:'\",.<>?/\\`~" for c in v):
            raise ValueError("new_password must contain at least one special character")
        return v