TEMPLATES_SUPORTADOS = {
    'auditoria_aberta',
    'auditoria_proxima_vencimento',
    'auditoria_enviada',
    'auditoria_resultado_final',
    'auditoria_correcao_solicitada',
    'auditoria_divergencia',
    'auditoria_equipamento_mantido',
    'auditoria_transferencia_criada',
    'transferencia_enviada',
    'transferencia_recebida',
    'emprestimo_enviado',
    'emprestimo_recebido',
    'comunicado_urgente',
}


def codigo_template(comunicado):
    dados = comunicado.dados or {}
    codigo = dados.get('template_codigo')
    if codigo in TEMPLATES_SUPORTADOS:
        return codigo
    return 'comunicado_urgente' if comunicado.tipo == 'URGENTE' else 'comunicado_urgente'
