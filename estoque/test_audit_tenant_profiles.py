from io import StringIO

from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import TestCase

from auditorias.models import CampanhaAuditoria
from estoque.models import Base, Empresa, Perfil


class AuditTenantProfilesCommandTests(TestCase):
    def setUp(self):
        self.empresa_a = Empresa.objects.create(nome='Tenant Alfa')
        self.empresa_b = Empresa.objects.create(nome='Tenant Beta')
        self.base_a = Base.objects.create(nome='Base Alfa', empresa=self.empresa_a)
        self.base_b = Base.objects.create(nome='Base Beta', empresa=self.empresa_b)

    @staticmethod
    def _admin(username, *, superuser=False, empresa=None):
        user = User.objects.create_user(username=username, password='senha-de-teste')
        user.is_superuser = superuser
        user.is_staff = superuser
        user.save(update_fields=['is_superuser', 'is_staff'])
        profile = user.perfil
        profile.role = Perfil.Role.ADMIN
        profile.empresa = empresa
        profile.save()
        return user

    @staticmethod
    def _run(*args):
        output = StringIO()
        call_command('audit_tenant_profiles', *args, stdout=output)
        return output.getvalue()

    def test_default_mode_is_read_only_even_for_eligible_profile(self):
        user = self._admin('admin.elegivel')
        user.perfil.empresas_escopo_compras.add(self.empresa_a)

        output = self._run('--username', user.username)

        user.perfil.refresh_from_db()
        self.assertIsNone(user.perfil.empresa_id)
        self.assertIn('Modo: SOMENTE LEITURA', output)
        self.assertIn('decisao: ELEGIVEL', output)
        self.assertIn('empresas_escopo_compras', output)

    def test_apply_backfills_one_explicit_tenant_and_is_idempotent(self):
        user = self._admin('admin.backfill')
        user.perfil.bases_escopo_compras.add(self.base_a)

        first_output = self._run('--apply', '--username', user.username)
        user.perfil.refresh_from_db()

        self.assertEqual(user.perfil.empresa_id, self.empresa_a.pk)
        self.assertIn('BACKFILL_APLICADO', first_output)
        self.assertIn('BACKFILLS_APLICADOS: 1', first_output)

        second_output = self._run('--apply', '--username', user.username)
        self.assertIn('decisao: ASSOCIADO', second_output)
        self.assertIn('BACKFILLS_APLICADOS: 0', second_output)

    def test_superuser_is_never_assigned_automatically(self):
        user = self._admin('admin.plataforma', superuser=True)
        user.perfil.empresas_escopo_compras.add(self.empresa_a)

        output = self._run('--apply', '--username', user.username)

        user.perfil.refresh_from_db()
        self.assertIsNone(user.perfil.empresa_id)
        self.assertIn('decisao: SUPERUSER_PLATAFORMA', output)
        self.assertIn('BACKFILLS_APLICADOS: 0', output)

    def test_single_operational_signal_requires_manual_review(self):
        user = self._admin('admin.sinal')
        CampanhaAuditoria.objects.create(
            empresa=self.empresa_a,
            nome='Campanha Alfa',
            criado_por=user,
        )

        output = self._run('--apply', '--username', user.username)

        user.perfil.refresh_from_db()
        self.assertIsNone(user.perfil.empresa_id)
        self.assertIn('auditorias.campanha.criador(1)', output)
        self.assertIn('decisao: PROVAVEL_REVISAO_MANUAL', output)
        self.assertIn('BACKFILLS_APLICADOS: 0', output)

    def test_conflicting_explicit_scopes_are_ambiguous(self):
        user = self._admin('admin.ambiguo.config')
        user.perfil.empresas_escopo_compras.add(self.empresa_a, self.empresa_b)

        output = self._run('--apply', '--username', user.username)

        user.perfil.refresh_from_db()
        self.assertIsNone(user.perfil.empresa_id)
        self.assertIn('decisao: AMBIGUO', output)
        self.assertIn('BACKFILLS_APLICADOS: 0', output)

    def test_operational_conflict_blocks_explicit_scope_backfill(self):
        user = self._admin('admin.ambiguo.historico')
        user.perfil.empresas_escopo_compras.add(self.empresa_a)
        CampanhaAuditoria.objects.create(
            empresa=self.empresa_b,
            nome='Campanha Beta',
            criado_por=user,
        )

        output = self._run('--apply', '--username', user.username)

        user.perfil.refresh_from_db()
        self.assertIsNone(user.perfil.empresa_id)
        self.assertIn('decisao: AMBIGUO', output)
        self.assertIn('conflita com atividade em outro tenant', output)

    def test_report_includes_role_groups_and_related_bases(self):
        user = self._admin('admin.relatorio')
        group = Group.objects.create(name='GRUPO_AUDITORIA_TESTE')
        user.groups.add(group)
        user.perfil.bases_checklist.add(self.base_a)

        output = self._run('--username', user.username)

        self.assertIn('role: admin', output)
        self.assertIn('grupos: GRUPO_AUDITORIA_TESTE', output)
        self.assertIn('bases_checklist:', output)
        self.assertIn('BASE ALFA [TENANT ALFA]', output)
