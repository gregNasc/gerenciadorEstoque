from estoque.models import Comunicado

class ComunicadoService:

    @staticmethod
    def emp_item_reservado(emp, usuario):

        Comunicado.objects.create(
            titulo="Empréstimo iniciado",
            mensagem=(
                f"{emp.regional_origem.nome} "
                f"reservou equipamentos para "
                f"{emp.regional_destino.nome}."
            ),
            tipo="OPERACIONAL",
            criado_por=usuario,
        )

    @staticmethod
    def emp_enviado(emp, usuario):

        Comunicado.objects.create(
            titulo="Equipamentos enviados",
            mensagem=(
                f"Equipamentos enviados de "
                f"{emp.regional_origem.nome} "
                f"para {emp.regional_destino.nome}."
            ),
            tipo="OPERACIONAL",
            criado_por=usuario,
        )

    @staticmethod
    def emp_divergencia(emp, usuario):

        Comunicado.objects.create(
            titulo="Divergência no empréstimo",
            mensagem=(
                f"Divergência detectada no "
                f"empréstimo {emp.protocolo}."
            ),
            tipo="URGENTE",
            criado_por=usuario,
        )

    @staticmethod
    def emp_recebido(emprestimo, usuario):
        Comunicado.objects.create(
            titulo='Empréstimo recebido',
            mensagem=(
                f'{emprestimo.regional_destino.nome} '
                f'confirmou o recebimento do empréstimo '
                f'{emprestimo.protocolo}.'
            ),
            tipo='EMPRESTIMO',
            enviar_para_todos=False,
            criado_por=usuario,
        )

    @staticmethod
    def emp_devolucao(emp, usuario):

        Comunicado.objects.create(
            titulo="Empréstimo finalizado",
            mensagem=(
                f"Devolução concluída entre "
                f"{emp.regional_origem.nome} e "
                f"{emp.regional_destino.nome}."
            ),
            tipo="OPERACIONAL",
            criado_por=usuario,
        )

    @staticmethod
    def emp_devolucao_pendente(emprestimo, usuario):
            Comunicado.objects.create(
                titulo='Devolução de empréstimo iniciada',

                mensagem=(
                    f'A base '
                    f'"{emprestimo.regional_destino.nome}" '
                    f'registrou a devolução do empréstimo '
                    f'{emprestimo.protocolo}. '
                    f'Aguardando confirmação da base '
                    f'"{emprestimo.regional_origem.nome}".'
                ),

                tipo='EMPRESTIMO',
                criado_por=usuario,
                enviar_para_todos=False,
            )