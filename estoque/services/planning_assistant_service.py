from datetime import datetime, time, timedelta

from django.utils import timezone

from insumos.services.planning_service import PlanningService


class PlanningAssistantService:
    """Apresenta planejamento à Tory sem permitir acesso direto à API externa."""

    STATUS_LABELS = {
        "DRAFT": "Rascunho",
        "PRE_PLANNED": "Pré-planejado",
        "PLANNED": "Planejado",
        "APPROVED": "Aprovado",
        "IN_PROGRESS": "Em andamento",
        "COMPLETED": "Concluído",
        "CANCELLED": "Cancelado",
        "ADDED": "Adicionado",
        "MODIFIED": "Modificado",
        "REMOVED": "Removido",
    }

    @classmethod
    def respond(cls, user, interpretacao):
        health = PlanningService.sync_health()
        start, end = cls._period_bounds(interpretacao)
        statuses = interpretacao.planning_statuses or PlanningService.ACTIVE_EVENT_STATUSES
        if interpretacao.planning_action == "comparison" and not interpretacao.planning_statuses:
            statuses = (*PlanningService.ACTIVE_EVENT_STATUSES, "COMPLETED")
        show_children = interpretacao.planning_action == "hierarchy"
        queryset = PlanningService.events_for_user(
            user,
            start=start,
            end=end,
            statuses=statuses,
            parents_only=(
                not show_children
                and interpretacao.external_inventory_type_kind != "FILHO"
            ),
            external_event_id=interpretacao.external_event_id,
            external_region_id=interpretacao.external_region_id,
            external_client_id=interpretacao.external_client_id,
            external_store_id=interpretacao.external_store_id,
            inventory_type_kind=interpretacao.external_inventory_type_kind,
            inventory_type_name=interpretacao.external_inventory_type_name,
            location=interpretacao.planning_location,
            local_base=interpretacao.base,
            local_client=interpretacao.cliente,
            store_lookup=interpretacao.loja,
        )

        if interpretacao.planning_action == "highest_pieces":
            queryset = queryset.exclude(planned_pieces__isnull=True).order_by(
                "-planned_pieces",
                "planned_at",
            )
        elif interpretacao.planning_action == "highest_headcount":
            queryset = queryset.exclude(planned_headcount__isnull=True).order_by(
                "-planned_headcount",
                "planned_at",
            )

        events = list(queryset[:100])
        if not events:
            return cls._no_events_response(interpretacao, health)

        cls._update_context_from_events(interpretacao, events)
        if interpretacao.planning_action == "comparison":
            return cls._comparison_response(user, interpretacao, events, health)
        if interpretacao.planning_action in {"availability", "simulate_sporadic"}:
            return cls._availability_response(interpretacao, events, health)
        if interpretacao.planning_action == "highest_pieces":
            return cls._highest_pieces_response(interpretacao, events[0], health)
        if interpretacao.planning_action == "highest_headcount":
            return cls._highest_headcount_response(interpretacao, events[0], health)
        if interpretacao.planning_action == "hierarchy":
            return cls._hierarchy_response(interpretacao, events, health)
        if interpretacao.planning_action == "team":
            return cls._team_response(interpretacao, events, health)
        return cls._list_response(interpretacao, events, health)

    @staticmethod
    def _period_bounds(interpretacao):
        first = interpretacao.periodo_inicio or interpretacao.data
        last = interpretacao.periodo_fim or interpretacao.data
        if not first:
            return None, None
        last = last or first
        start = timezone.make_aware(datetime.combine(first, time.min))
        end = timezone.make_aware(datetime.combine(last + timedelta(days=1), time.min))
        return start, end

    @classmethod
    def _list_response(cls, interpretacao, events, health):
        total_people = sum(event.planned_headcount or 0 for event in events)
        total_pieces = sum(event.planned_pieces or 0 for event in events)
        operation_count = len({event.client_id for event in events if event.client_id})
        rows = events
        lines = [
            f"Encontrei {len(events)} inventário(s) planejado(s){cls._scope_label(interpretacao)}.",
            "",
            f"- Pessoas previstas: {cls._number(total_people)}",
            f"- Peças previstas: {cls._number(total_pieces)}",
            f"- Exibindo: {len(rows)} de {len(events)}",
            "",
            "DATA/HORA | CLIENTE | LOJA | REGIONAL | TIPO | PESSOAS | PEÇAS | STATUS",
        ]
        for event in rows:
            lines.append(cls._event_row(event))
        lines.append("")
        if interpretacao.planning_location and not interpretacao.cliente and operation_count > 1:
            lines.append(
                "Há mais de uma operação nesse local. Se você informar o cliente, eu separo a operação correta sem presumir a base."
            )
        lines.extend([
            "Quer que eu mostre o evento de maior volume, detalhe a estrutura das atividades ou compare com a execução local?",
            cls._source_line(health),
        ])
        return cls._response(
            "planejamento",
            lines,
            actions=[
                {"label": "Maior previsão", "pergunta": "Qual tem maior previsão de peças?"},
                {"label": "Estrutura das atividades", "pergunta": "Mostre a estrutura das atividades vinculadas"},
                {"label": "Planejado × realizado", "pergunta": "Compare planejado e realizado"},
            ],
        )

    @classmethod
    def _highest_pieces_response(cls, interpretacao, event, health):
        cls._update_context_from_events(interpretacao, [event], force_event=True)
        lines = [
            "O maior volume previsto no período é:",
            "",
            f"- Evento: {event.external_id}",
            f"- Data/hora operacional: {cls._datetime(event.planned_at)}",
            f"- Cliente/loja: {cls._client(event)} — {cls._store(event)}",
            f"- Regional: {cls._region(event)}",
            f"- Tipo: {cls._type(event)}",
            f"- Pessoas previstas: {cls._value(event.planned_headcount)}",
            f"- Peças previstas: {cls._value(event.planned_pieces)}",
            f"- Status: {cls._status(event.status)}",
            "",
            "Posso detalhar as atividades vinculadas ou comparar esse planejamento com a execução registrada.",
            cls._source_line(health),
        ]
        return cls._response(
            "planejamento",
            lines,
            actions=[
                {"label": "Ver atividades", "pergunta": "Mostre a estrutura das atividades vinculadas"},
                {"label": "Comparar execução", "pergunta": "E o planejado versus realizado?"},
                {"label": "Equipe prevista", "pergunta": "Qual é a equipe prevista?"},
            ],
        )

    @classmethod
    def _highest_headcount_response(cls, interpretacao, event, health):
        cls._update_context_from_events(interpretacao, [event], force_event=True)
        lines = [
            "O evento com maior demanda prevista de pessoas no período é:",
            "",
            f"- Evento: {event.external_id}",
            f"- Data/hora operacional: {cls._datetime(event.planned_at)}",
            f"- Cliente/loja: {cls._client(event)} — {cls._store(event)}",
            f"- Regional: {cls._region(event)}",
            f"- Pessoas previstas: {cls._value(event.planned_headcount)}",
            f"- Peças previstas: {cls._value(event.planned_pieces)}",
            f"- Status: {cls._status(event.status)}",
            "",
            "Posso comparar essa demanda com a execução local; disponibilidade nominal da equipe ainda não está integrada.",
            cls._source_line(health),
        ]
        return cls._response(
            "planejamento",
            lines,
            actions=[
                {"label": "Simular avulsos", "pergunta": "E se adicionarmos cinco avulsos?"},
                {"label": "Comparar execução", "pergunta": "Compare planejado e realizado"},
            ],
        )

    @classmethod
    def _team_response(cls, interpretacao, events, health):
        rows = events
        lines = [
            "Estas são as quantidades de pessoas previstas no planejamento:",
            "",
            "DATA/HORA | CLIENTE | LOJA | REGIONAL | PESSOAS PREVISTAS | PEÇAS PREVISTAS",
        ]
        for event in rows:
            lines.append(
                f"{cls._datetime(event.planned_at)} | {cls._client(event)} | {cls._store(event)} | "
                f"{cls._region(event)} | {cls._value(event.planned_headcount)} | "
                f"{cls._value(event.planned_pieces)}"
            )
        lines.extend([
            "",
            "A fase atual informa a demanda prevista, mas ainda não expõe nomes, disponibilidade ou composição da equipe.",
            "Quer que eu destaque o evento com maior demanda de pessoas?",
            cls._source_line(health),
        ])
        return cls._response(
            "planejamento",
            lines,
            actions=[
                {"label": "Maior demanda", "pergunta": "Qual evento tem mais pessoas previstas?"},
                {"label": "Peças previstas", "pergunta": "Qual tem maior previsão de peças?"},
            ],
        )

    @classmethod
    def _hierarchy_response(cls, interpretacao, events, health):
        rows = events
        lines = [
            "Estrutura das atividades encontradas no período:",
            "",
            "VÍNCULO | DATA/HORA | EVENTO | EVENTO PRINCIPAL | CLIENTE/LOJA | TIPO | STATUS",
        ]
        for event in rows:
            parent_id = event.parent_external_id or "-"
            lines.append(
                f"{cls._kind_label(event)} | {cls._datetime(event.planned_at)} | {event.external_id} | "
                f"{parent_id} | {cls._client(event)}/{cls._store(event)} | "
                f"{cls._type(event)} | {cls._status(event.status)}"
            )
        lines.extend([
            "",
            "Atividades vinculadas não recebem checklist ou execução própria sem vínculo local explícito.",
            "Quer que eu filtre apenas os eventos principais ou detalhe um evento específico?",
            cls._source_line(health),
        ])
        return cls._response(
            "planejamento",
            lines,
            actions=[
                {"label": "Somente principais", "pergunta": "Mostre somente os eventos principais"},
                {"label": "Maior previsão", "pergunta": "Qual tem maior previsão de peças?"},
            ],
        )

    @classmethod
    def _comparison_response(cls, user, interpretacao, events, health):
        rows = []
        for event in events:
            inventory = PlanningService.local_execution_for_event(user, event)
            if inventory is None:
                rows.append((event, None))
            else:
                rows.append((event, inventory))

        lines = [
            "Comparação entre a fonte oficial de planejamento e a execução local:",
            "",
            "EVENTO | CLIENTE/LOJA | PEÇAS PLAN. | PEÇAS REAL. | DESVIO | PESSOAS PLAN. | PESSOAS REG. | PRODUTIVIDADE",
        ]
        for event, inventory in rows:
            if inventory is None:
                lines.append(
                    f"{event.external_id} | {cls._client(event)}/{cls._store(event)} | "
                    f"{cls._value(event.planned_pieces)} | - | - | "
                    f"{cls._value(event.planned_headcount)} | - | sem execução local vinculada"
                )
                continue
            deviation = cls._difference(inventory.total_pecas, event.planned_pieces)
            productivity = inventory.produtividade_pessoa_hora
            lines.append(
                f"{event.external_id} | {cls._client(event)}/{cls._store(event)} | "
                f"{cls._value(event.planned_pieces)} | {cls._value(inventory.total_pecas)} | "
                f"{deviation} | {cls._value(event.planned_headcount)} | "
                f"{cls._value(inventory.pessoas)} | {cls._productivity(productivity)}"
            )
        lines.extend([
            "",
            "Planejado vem da Inventory Planning; realizado, pessoas registradas e produtividade vêm do gerenciadorEstoque.",
            "Nenhum valor foi estimado quando o vínculo ou o dado real estava ausente.",
            cls._source_line(health, include_local=True),
        ])
        return cls._response(
            "planejado_realizado",
            lines,
            actions=[
                {"label": "Ver planejamento", "pergunta": "Volte ao planejamento desse período"},
                {"label": "Maior desvio", "pergunta": "Qual teve a maior diferença entre planejado e realizado?"},
            ],
        )

    @classmethod
    def _availability_response(cls, interpretacao, events, health):
        event = events[0]
        cls._update_context_from_events(interpretacao, [event], force_event=True)
        planned = event.planned_headcount
        lines = [
            f"O evento {event.external_id} prevê {cls._value(planned)} pessoa(s).",
        ]
        if interpretacao.planning_action == "simulate_sporadic":
            extra = interpretacao.simulated_sporadic_count or 0
            if planned is None:
                lines.append(
                    f"Posso considerar a hipótese de {extra} avulso(s), mas o total original não foi informado."
                )
            else:
                lines.append(
                    f"Como cenário hipotético, adicionar {extra} avulso(s) elevaria a equipe de "
                    f"{planned} para {planned + extra} pessoas. Isso não altera a escala nem o planejamento."
                )
        lines.extend([
            "Ainda não posso confirmar se há pessoas suficientes: equipes, disponibilidade e avulsos pertencem a uma fase posterior da integração.",
            "Posso mostrar a demanda de pessoas e peças ou comparar com uma execução local já vinculada.",
            cls._source_line(health),
        ])
        return cls._response(
            "planejamento_disponibilidade",
            lines,
            actions=[
                {"label": "Ver demanda", "pergunta": "Mostre pessoas e peças previstas"},
                {"label": "Comparar execução", "pergunta": "Compare planejado e realizado"},
            ],
        )

    @classmethod
    def _no_events_response(cls, interpretacao, health):
        if not health["has_data"] and health["last_run_failed"]:
            text = (
                "Os dados de planejamento não estão disponíveis no momento. "
                "Posso responder com os dados locais de execução que já estejam registrados."
            )
        elif not health["has_data"]:
            text = (
                "Ainda não há eventos de planejamento sincronizados. "
                "Posso consultar os inventários e checklists locais enquanto a primeira sincronização é concluída."
            )
        else:
            text = (
                f"Não encontrei inventários planejados{cls._scope_label(interpretacao)} dentro do seu escopo. "
                "Quer ampliar o período ou retirar algum filtro?"
            )
        return cls._response(
            "planejamento",
            [text, cls._source_line(health)],
            actions=[
                {"label": "Próxima semana", "pergunta": "Quais inventários estão planejados para a próxima semana?"},
                {"label": "Dados locais", "pergunta": "Mostre os inventários locais de hoje"},
            ],
        )

    @classmethod
    def _update_context_from_events(cls, interpretacao, events, force_event=False):
        if force_event or len(events) == 1:
            event = events[0]
            interpretacao.external_event_id = event.external_id
            if event.client:
                interpretacao.external_client_id = event.client.external_id
                interpretacao.external_client_name = cls._client(event)
            if event.store:
                interpretacao.external_store_id = event.store.external_id
                interpretacao.external_store_name = cls._store(event)
            if event.region:
                interpretacao.external_region_id = event.region.external_id
                interpretacao.external_region_name = cls._region(event)
            if event.inventory_type:
                interpretacao.external_inventory_type_name = event.inventory_type.name
                interpretacao.external_inventory_type_kind = event.inventory_type.kind
            return

        region_ids = {event.region.external_id for event in events if event.region}
        if len(region_ids) == 1:
            region = next(event.region for event in events if event.region)
            interpretacao.external_region_id = region.external_id
            interpretacao.external_region_name = region.name

    @classmethod
    def _source_line(cls, health, include_local=False):
        if health["synced_at"]:
            timestamp = timezone.localtime(health["synced_at"]).strftime("%d/%m/%Y às %H:%M")
            if health["last_run_failed"]:
                source = f"Fonte: Inventory Planning — snapshot sincronizado em {timestamp}; a última atualização falhou."
            else:
                source = f"Fonte: Inventory Planning — sincronizado em {timestamp}."
        else:
            source = "Fonte: Inventory Planning — sem snapshot disponível."
        if include_local:
            source += " Execução: gerenciadorEstoque."
        return source

    @classmethod
    def _scope_label(cls, interpretacao):
        parts = []
        if interpretacao.periodo_inicio and interpretacao.periodo_fim:
            if interpretacao.periodo_inicio == interpretacao.periodo_fim:
                parts.append(interpretacao.periodo_inicio.strftime("em %d/%m/%Y"))
            else:
                parts.append(
                    f"de {interpretacao.periodo_inicio:%d/%m/%Y} a {interpretacao.periodo_fim:%d/%m/%Y}"
                )
        elif interpretacao.data:
            parts.append(interpretacao.data.strftime("em %d/%m/%Y"))
        if interpretacao.base:
            parts.append(f"na base {interpretacao.base.nome}")
        elif interpretacao.external_region_name:
            parts.append(f"na regional {interpretacao.external_region_name}")
        elif interpretacao.planning_location:
            parts.append(f"em {interpretacao.planning_location}")
        return " " + ", ".join(parts) if parts else ""

    @classmethod
    def _event_row(cls, event):
        return (
            f"{cls._datetime(event.planned_at)} | {cls._client(event)} | {cls._store(event)} | "
            f"{cls._region(event)} | {cls._type(event)} | "
            f"{cls._value(event.planned_headcount)} | {cls._value(event.planned_pieces)} | "
            f"{cls._status(event.status)}"
        )

    @staticmethod
    def _client(event):
        if not event.client:
            return "-"
        return event.client.trade_name or event.client.corporate_name or event.client.code or "-"

    @staticmethod
    def _store(event):
        if not event.store:
            return "-"
        return event.store.code or event.store.nickname or event.store.name or "-"

    @staticmethod
    def _region(event):
        return event.region.name if event.region else "-"

    @staticmethod
    def _type(event):
        return event.inventory_type.name if event.inventory_type else "-"

    @staticmethod
    def _kind(event):
        return event.inventory_type.kind if event.inventory_type else "-"

    @classmethod
    def _kind_label(cls, event):
        return {
            "PAI": "Principal",
            "FILHO": "Atividade vinculada",
        }.get(cls._kind(event), "-")

    @classmethod
    def _status(cls, status):
        return cls.STATUS_LABELS.get(status, status or "-")

    @staticmethod
    def _datetime(value):
        if not value:
            return "-"
        return timezone.localtime(value).strftime("%d/%m/%Y %H:%M")

    @staticmethod
    def _number(value):
        return f"{value:,}".replace(",", ".")

    @classmethod
    def _value(cls, value):
        return "-" if value is None else cls._number(value)

    @classmethod
    def _difference(cls, actual, planned):
        if actual is None or planned is None:
            return "-"
        difference = actual - planned
        sign = "+" if difference > 0 else ""
        return f"{sign}{cls._number(difference)}"

    @staticmethod
    def _productivity(value):
        if value is None:
            return "-"
        return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " peças/pessoa/h"

    @staticmethod
    def _response(category, lines, actions=None):
        return {
            "categoria": category,
            "resposta": "\n".join(line for line in lines if line is not None),
            "acoes": actions or [],
        }
