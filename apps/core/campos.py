from django.db import models


class EmailInsensivel(models.EmailField):
    """E-mail em coluna citext do PostgreSQL: comparacao sem diferenciar maiusculas, como no schema de referencia."""

    def db_type(self, connection):
        return 'citext'
