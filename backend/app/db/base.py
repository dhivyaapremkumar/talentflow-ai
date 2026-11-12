"""Declarative base shared by every model module."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
