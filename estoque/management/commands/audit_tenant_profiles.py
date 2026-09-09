from collections import defaultdict

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count

from estoque.models import Empresa, Perfil


CONFIGURED_SCOPE_SPECS = (
    ('regionais', 'regionais', 'empresa_id'),
    ('bases_checklist', 'bases_checklist', 'empresa_id'),
    ('empresas_escopo_compras', 'empresas_escopo_compras', 'pk'),
    ('bases_escopo_compras', 'bases_escopo_compras', 'empresa_id'),
)


# Estes registros revelam onde a conta atuou, mas nao constituem, isoladamente,
# autorizacao para definir seu tenant. A lista e propositalmente explicita para
# que novas heuristicas nao sejam introduzidas silenciosamente.
OPERATIONAL_SIGNAL_SPECS = (
    ('chamados', 'Chamado', 'aberto_por_id', 'empresa_id', 'chamados.aberto_por'),
    ('chamados', 'Chamado', 'atendente_id', 'empresa_id', 'chamados.atendente'),
    ('insumos', 'Inventario', 'criado_por_id', 'base__empresa_id', 'inventarios.criado_por'),
    ('insumos', 'Inventario', 'lider_usuario_id', 'base__empresa_id', 'inventarios.lider'),
    ('insumos', 'SolicitacaoInsumo', 'solicitante_id', 'base__empresa_id', 'insumos.solicitante'),
    ('insumos', 'SolicitacaoInsumo', 'aprovado_por_id', 'base__empresa_id', 'insumos.aprovado_por'),
    ('insumos', 'SolicitacaoInsumo', 'finalizado_por_id', 'base__empresa_id', 'insumos.finalizado_por'),
    ('insumos', 'SolicitacaoInsumo', 'em_compra_por_id', 'base__empresa_id', 'insumos.em_compra_por'),
    ('insumos', 'MovimentacaoInsumo', 'usuario_id', 'base__empresa_id', 'insumos.movimentacoes'),
    ('estoque', 'Emprestimo', 'solicitado_por_id', 'regional_origem__empresa_id', 'emprestimos.solicitante.origem'),
    ('estoque', 'Emprestimo', 'solicitado_por_id', 'regional_destino__empresa_id', 'emprestimos.solicitante.destino'),
    ('estoque', 'Emprestimo', 'aprovado_por_id', 'regional_origem__empresa_id', 'emprestimos.aprovador.origem'),
    ('estoque', 'Emprestimo', 'aprovado_por_id', 'regional_destino__empresa_id', 'emprestimos.aprovador.destino'),
    ('estoque', 'Solicitacao', 'criado_por_id', 'regional_solicitante__empresa_id', 'equipamentos.solicitacao.criador'),
    ('estoque', 'Solicitacao', 'aprovado_por_id', 'regional_solicitante__empresa_id', 'equipamentos.solicitacao.aprovador'),
    ('estoque', 'Solicitacao', 'recusado_por_id', 'regional_solicitante__empresa_id', 'equipamentos.solicitacao.recusador'),
    ('estoque', 'Transferencia', 'solicitado_por_id', 'regional_origem__empresa_id', 'transferencias.solicitante.origem'),
    ('estoque', 'Transferencia', 'solicitado_por_id', 'regional_destino__empresa_id', 'transferencias.solicitante.destino'),
    ('compras', 'Aquisicao', 'cadastrado_por_id', 'empresa_id', 'compras.aquisicao.cadastro'),
    ('compras', 'Aquisicao', 'aprovado_por_id', 'empresa_id', 'compras.aquisicao.aprovacao'),
    ('compras', 'RemessaCompra', 'criada_por_id', 'empresa_id', 'compras.remessa.criacao'),
    ('compras', 'RemessaCompra', 'enviada_por_id', 'empresa_id', 'compras.remessa.envio'),
    ('ordens_servico', 'OrdemServico', 'solicitante_id', 'empresa_id', 'ordens.solicitante'),
    ('ordens_servico', 'OrdemServico', 'responsavel_operacional_id', 'empresa_id', 'ordens.responsavel'),
    ('ordens_servico', 'OrdemServico', 'autorizador_id', 'empresa_id', 'ordens.autorizador'),
    ('ordens_servico', 'OrdemServico', 'recebedor_id', 'empresa_id', 'ordens.recebedor'),
    ('auditorias', 'CampanhaAuditoria', 'criado_por_id', 'empresa_id', 'auditorias.campanha.criador'),
)


class Command(BaseCommand):
    help = (
        'Audita o tenant dos perfis Admin. O modo padrao e somente leitura; '
        '--apply preenche apenas casos inequivocos por configuracao explicita.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Aplica o backfill somente aos casos classificados como ELEGIVEL.',
        )
        parser.add_argument(
            '--username',
            action='append',
            default=[],
            help='Limita a auditoria ao username informado; pode ser repetido.',
        )

    def handle(self, *args, **options):
        usernames = [value.strip() for value in options['username'] if value.strip()]
        queryset = (
            Perfil.objects.select_related('user', 'empresa')
            .filter(role=Perfil.Role.ADMIN)
            .prefetch_related(
                'user__groups',
                'regionais__empresa',
                'bases_checklist__empresa',
                'empresas_escopo_compras',
                'bases_escopo_compras__empresa',
            )
            .order_by('user__username')
        )
        if usernames:
            queryset = queryset.filter(user__username__in=usernames)

        profiles = list(queryset)
        if usernames:
            found = {profile.user.username for profile in profiles}
            missing = sorted(set(usernames) - found)
            if missing:
                raise CommandError(
                    'Nenhum perfil Admin encontrado para: ' + ', '.join(missing)
                )

        self.stdout.write('AUDITORIA DE TENANT DOS PERFIS ADMIN')
        self.stdout.write(
            'Modo: ' + ('BACKFILL SEGURO (--apply)' if options['apply'] else 'SOMENTE LEITURA')
        )
        self.stdout.write(
            'Regra: atividade operacional e apenas indicio; o backfill exige '
            'um unico tenant em configuracao explicita e nenhum conflito.'
        )

        summary = defaultdict(int)
        applied = 0
        for profile in profiles:
            audit = self._audit_profile(profile)
            summary[audit['decision']] += 1
            self._write_profile(profile, audit)
            if options['apply'] and audit['decision'] == 'ELEGIVEL':
                if self._apply_backfill(profile.pk, audit['candidate_id']):
                    applied += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  BACKFILL_APLICADO: empresa={self._company_label(audit['candidate_id'])}"
                        )
                    )

        self.stdout.write('')
        self.stdout.write(f'TOTAL_ADMINS: {len(profiles)}')
        for decision in (
            'ASSOCIADO',
            'SUPERUSER_PLATAFORMA',
            'ELEGIVEL',
            'PROVAVEL_REVISAO_MANUAL',
            'AMBIGUO',
            'SEM_EVIDENCIA',
        ):
            self.stdout.write(f'{decision}: {summary[decision]}')
        if options['apply']:
            self.stdout.write(f'BACKFILLS_APLICADOS: {applied}')

    def _audit_profile(self, profile):
        configured = self._configured_evidence(profile)
        operational = self._operational_evidence(profile.user_id)
        configured_ids = set(configured)
        operational_ids = set(operational)

        if profile.empresa_id:
            decision = 'ASSOCIADO'
            candidate_id = profile.empresa_id
            reason = 'Perfil ja possui empresa definida.'
        elif profile.user.is_superuser:
            decision = 'SUPERUSER_PLATAFORMA'
            candidate_id = None
            reason = 'Superuser e excecao de plataforma; empresa nao e inferida.'
        elif len(configured_ids) > 1:
            decision = 'AMBIGUO'
            candidate_id = None
            reason = 'Configuracoes explicitas apontam para mais de uma empresa.'
        elif len(configured_ids) == 1:
            only_id = next(iter(configured_ids))
            conflicts = operational_ids - {only_id}
            if conflicts:
                decision = 'AMBIGUO'
                candidate_id = None
                reason = 'Configuracao explicita conflita com atividade em outro tenant.'
            else:
                decision = 'ELEGIVEL'
                candidate_id = only_id
                reason = 'Um unico tenant configurado explicitamente, sem conflito operacional.'
        elif len(operational_ids) == 1:
            decision = 'PROVAVEL_REVISAO_MANUAL'
            candidate_id = next(iter(operational_ids))
            reason = 'Ha um unico indicio operacional, insuficiente para backfill automatico.'
        elif len(operational_ids) > 1:
            decision = 'AMBIGUO'
            candidate_id = None
            reason = 'Atividade historica envolve mais de uma empresa e nao ha configuracao explicita.'
        else:
            decision = 'SEM_EVIDENCIA'
            candidate_id = None
            reason = 'Nenhum vinculo configurado ou registro operacional tenant-aware foi encontrado.'

        return {
            'configured': configured,
            'operational': operational,
            'decision': decision,
            'candidate_id': candidate_id,
            'reason': reason,
        }

    @staticmethod
    def _configured_evidence(profile):
        evidence = defaultdict(list)
        for source, relation_name, company_field in CONFIGURED_SCOPE_SPECS:
            relation = getattr(profile, relation_name).all()
            for item in relation:
                company_id = getattr(item, company_field)
                evidence[company_id].append(source)
        return dict(evidence)

    @staticmethod
    def _operational_evidence(user_id):
        evidence = defaultdict(list)
        for app_label, model_name, user_field, company_path, source in OPERATIONAL_SIGNAL_SPECS:
            model = apps.get_model(app_label, model_name)
            rows = (
                model.objects.filter(**{user_field: user_id})
                .exclude(**{f'{company_path}__isnull': True})
                .values(company_path)
                .annotate(total=Count('pk'))
            )
            for row in rows:
                evidence[row[company_path]].append(f"{source}({row['total']})")
        return dict(evidence)

    def _write_profile(self, profile, audit):
        groups = ', '.join(group.name for group in profile.user.groups.all()) or '-'
        regionais = self._format_bases(profile.regionais.all())
        checklist = self._format_bases(profile.bases_checklist.all())
        companies_scope = self._format_companies(profile.empresas_escopo_compras.all())
        bases_scope = self._format_bases(profile.bases_escopo_compras.all())

        self.stdout.write('')
        self.stdout.write(f'USUARIO: {profile.user.username}')
        self.stdout.write(f'  role: {profile.role}')
        self.stdout.write(f'  ativo: {profile.user.is_active}')
        self.stdout.write(f'  staff: {profile.user.is_staff}')
        self.stdout.write(f'  superuser: {profile.user.is_superuser}')
        self.stdout.write(
            f"  empresa_atual: {self._company_label(profile.empresa_id) if profile.empresa_id else '-'}"
        )
        self.stdout.write(f'  grupos: {groups}')
        self.stdout.write(f'  regionais: {regionais}')
        self.stdout.write(f'  bases_checklist: {checklist}')
        self.stdout.write(f'  empresas_escopo_compras: {companies_scope}')
        self.stdout.write(f'  bases_escopo_compras: {bases_scope}')
        self.stdout.write(
            '  evidencias_configuradas: ' + self._format_evidence(audit['configured'])
        )
        self.stdout.write(
            '  sinais_operacionais: ' + self._format_evidence(audit['operational'])
        )
        candidate = audit['candidate_id']
        self.stdout.write(f"  decisao: {audit['decision']}")
        self.stdout.write(
            f"  tenant_candidato: {self._company_label(candidate) if candidate else '-'}"
        )
        self.stdout.write(f"  motivo: {audit['reason']}")

    @staticmethod
    def _apply_backfill(profile_id, company_id):
        with transaction.atomic():
            locked = Perfil.objects.select_for_update().select_related('user').get(pk=profile_id)
            if locked.empresa_id or locked.user.is_superuser or locked.role != Perfil.Role.ADMIN:
                return False
            current_audit = Command()._audit_profile(locked)
            if (
                current_audit['decision'] != 'ELEGIVEL'
                or current_audit['candidate_id'] != company_id
            ):
                return False
            return Perfil.objects.filter(pk=profile_id, empresa__isnull=True).update(
                empresa_id=company_id
            ) == 1

    def _format_evidence(self, evidence):
        if not evidence:
            return '-'
        return '; '.join(
            f"{self._company_label(company_id)} <- {', '.join(sorted(sources))}"
            for company_id, sources in sorted(evidence.items())
        )

    @staticmethod
    def _format_bases(bases):
        values = [f'{base.pk}:{base.nome} [{base.empresa.nome}]' for base in bases]
        return ', '.join(values) or '-'

    @staticmethod
    def _format_companies(companies):
        values = [f'{company.pk}:{company.nome}' for company in companies]
        return ', '.join(values) or '-'

    @staticmethod
    def _company_label(company_id):
        company = Empresa.objects.only('pk', 'nome').get(pk=company_id)
        return f'{company.pk}:{company.nome}'
