
class Perms:

    APROVAR_SOLICITACAO = 'aprovar_solicitacao'
    REPROVAR_SOLICITACAO = 'reprovar_solicitacao'
    COLOCAR_EM_COMPRA = 'colocar_em_compra'
    FINALIZAR_SOLICITACAO = 'finalizar_solicitacao'

    REALIZAR_ENTRADA = 'realizar_entrada'
    REALIZAR_SAIDA = 'realizar_saida'
    REALIZAR_DEVOLUCAO = 'realizar_devolucao'
    REALIZAR_PERDA = 'realizar_perda'
    REALIZAR_AJUSTE = 'realizar_ajuste'

    GERENCIAR_INVENTARIOS = 'gerenciar_inventarios'

    GERENCIAR_CHECKLISTS = 'gerenciar_checklists'
    FINALIZAR_CHECKLISTS = 'finalizar_checklists'

    VISUALIZAR_CUSTOS = 'visualizar_custos'
    VISUALIZAR_DASHBOARDS_FINANCEIROS = 'visualizar_dashboards_financeiros'

    GERENCIAR_TAGS = 'gerenciar_tags'

    @classmethod
    def full(cls, codename):
        return f'insumos.{codename}'