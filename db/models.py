import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Text, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id:          Mapped[uuid.UUID]   = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    google_sub:  Mapped[str]         = mapped_column(Text, unique=True, nullable=False)
    email:       Mapped[str]         = mapped_column(Text, unique=True, nullable=False)
    name:        Mapped[str | None]  = mapped_column(Text)
    picture_url: Mapped[str | None]  = mapped_column(Text)
    # IANA name (e.g. "Europe/Berlin") read from the user's primary Google
    # Calendar at login. Nullable: if that lookup fails we fall back to
    # config.TIMEZONE rather than blocking sign-in.
    timezone:    Mapped[str | None]  = mapped_column(Text)
    created_at:  Mapped[datetime]    = mapped_column(server_default=func.now(), nullable=False)
    updated_at:  Mapped[datetime]    = mapped_column(server_default=func.now(), onupdate=func.now(), nullable=False)

    credentials: Mapped["GoogleCredentials | None"] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )


class GoogleCredentials(Base):
    __tablename__ = "google_credentials"

    user_id:       Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    refresh_token: Mapped[str]       = mapped_column(Text, nullable=False)
    scope:         Mapped[str]       = mapped_column(Text, nullable=False)
    updated_at:    Mapped[datetime]  = mapped_column(server_default=func.now(), onupdate=func.now(), nullable=False)

    user: Mapped[User] = relationship(back_populates="credentials")
