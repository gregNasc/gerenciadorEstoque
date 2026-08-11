import re

from django.conf import settings


def normalizar_whatsapp(numero):
    digitos = re.sub(r'\D', '', numero or '')
    if len(digitos) in (10, 11):
        digitos = f'{settings.WHATSAPP_DEFAULT_COUNTRY_CODE}{digitos}'
    return digitos


def whatsapp_valido(numero):
    return bool(numero and numero.isdigit() and 8 <= len(numero) <= 15)


def mascarar_whatsapp(numero):
    digitos = normalizar_whatsapp(numero)
    if len(digitos) < 4:
        return ''
    return f'+{digitos[:2]} •••••• {digitos[-4:]}'
