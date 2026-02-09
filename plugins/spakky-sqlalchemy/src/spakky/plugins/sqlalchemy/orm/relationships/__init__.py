"""Relationship metadata for SQLAlchemy ORM."""

from spakky.plugins.sqlalchemy.orm.relationships.base import AbstractRelationship
from spakky.plugins.sqlalchemy.orm.relationships.many_to_one import ManyToOne
from spakky.plugins.sqlalchemy.orm.relationships.one_to_many import OneToMany
from spakky.plugins.sqlalchemy.orm.relationships.one_to_one import OneToOne

__all__ = [
    "AbstractRelationship",
    "ManyToOne",
    "OneToMany",
    "OneToOne",
]
