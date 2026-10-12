"""Validacao de documentos (so numeros, com digito verificador)."""
import re

from django.core.exceptions import ValidationError


def so_digitos(valor):
    return re.sub(r'\D', '', valor or '')


def _digito_cpf(digitos, tamanho):
    soma = sum(int(digitos[i]) * (tamanho + 1 - i) for i in range(tamanho))
    return (soma * 10 % 11) % 10


def validar_cpf(valor):
    d = so_digitos(valor)
    if len(d) != 11 or d == d[0] * 11 or any(_digito_cpf(d, n) != int(d[n]) for n in (9, 10)):
        raise ValidationError('CPF inválido.')


def validar_cnpj(valor):
    d = so_digitos(valor)
    if len(d) != 14 or d == d[0] * 14:
        raise ValidationError('CNPJ inválido.')
    pesos = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    for n, p in ((12, pesos), (13, [6] + pesos)):
        resto = sum(int(d[i]) * p[i] for i in range(n)) % 11
        if int(d[n]) != (0 if resto < 2 else 11 - resto):
            raise ValidationError('CNPJ inválido.')


def validar_cpf_ou_cnpj(valor):
    (validar_cnpj if len(so_digitos(valor)) > 11 else validar_cpf)(valor)
