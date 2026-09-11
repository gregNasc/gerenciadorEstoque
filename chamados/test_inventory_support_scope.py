from importlib import import_module

from django.apps import apps as django_apps
from django.contrib.auth.models import Group, User
from django.test import TestCase

from chamados.models import Chamado
from chamados.policies import ChamadoAccessPolicy, GruposChamados
from estoque.models import (
    Base,
    CapacidadeRelacionamentoEmpresa,
    Empresa,
    Perfil,
    RelacionamentoEmpresa,
)


support_migration = import_module(
    'estoque.migrations.0047_relacionamento_suporte_chamados'
)


class InventorySupportScopeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.brasil = Empresa.objects.create(
            nome='Inventory Brasil suporte', slug='inventory-brasil-suporte'
        )
        cls.latam = Empresa.objects.create(
            nome='Inventory LATAM suporte', slug='inventory-latam-suporte'
        )
        cls.oxxo = Empresa.objects.create(
            nome='OXXO suporte', slug='oxxo-suporte'
        )
        cls.propria = Empresa.objects.create(
            nome='Empresa própria do suporte', slug='empresa-propria-suporte'
        )
        cls.externa = Empresa.objects.create(
            nome='Empresa externa ao suporte', slug='empresa-externa-suporte'
        )
        cls.bases = {
            empresa.pk: Base.objects.create(
                empresa=empresa, nome=f'Base {empresa.nome}'
            )
            for empresa in (cls.brasil, cls.latam, cls.oxxo, cls.propria, cls.externa)
        }

        for destination in (cls.latam, cls.oxxo):
            relationship = RelacionamentoEmpresa.objects.create(
                empresa_origem=cls.brasil,
                empresa_destino=destination,
                compartilha_suporte_chamados=True,
            )
            CapacidadeRelacionamentoEmpresa.objects.create(
                relacionamento=relationship,
                recurso=CapacidadeRelacionamentoEmpresa.Recurso.CHAMADOS,
                acao=CapacidadeRelacionamentoEmpresa.Acao.ATENDER,
            )

        cls.support = User.objects.create_user(
            'suporte.inventory.compartilhado', password='SenhaTeste123!'
        )
        cls.support.perfil.role = Perfil.Role.OPERADOR
        cls.support.perfil.empresa = cls.propria
        cls.support.perfil.save()
        cls.support.perfil.regionais.add(cls.bases[cls.propria.pk])
        cls.support.groups.add(
            Group.objects.get_or_create(name=GruposChamados.SUPORTE)[0]
        )

        cls.opener = User.objects.create_user(
            'abertura.chamados.suporte', password='SenhaTeste123!'
        )
        cls.chamados = {
            empresa.pk: Chamado.objects.create(
                protocolo=f'SUP-{empresa.pk}',
                empresa=empresa,
                base=cls.bases[empresa.pk],
                titulo=f'Chamado {empresa.nome}',
                descricao='Escopo de suporte compartilhado.',
                aberto_por=cls.opener,
            )
            for empresa in (cls.brasil, cls.latam, cls.oxxo, cls.propria, cls.externa)
        }

    def test_support_sees_inventory_group_regardless_of_own_company_and_base(self):
        visible_ids = set(
            ChamadoAccessPolicy.queryset(self.support).values_list('pk', flat=True)
        )

        self.assertEqual(visible_ids, {
            self.chamados[self.brasil.pk].pk,
            self.chamados[self.latam.pk].pk,
            self.chamados[self.oxxo.pk].pk,
            self.chamados[self.propria.pk].pk,
        })
        self.assertNotIn(self.chamados[self.externa.pk].pk, visible_ids)

    def test_shared_support_scope_does_not_expand_opening_bases(self):
        own_base_ids = set(
            ChamadoAccessPolicy.bases(self.support).values_list('pk', flat=True)
        )
        attendance_base_ids = set(
            ChamadoAccessPolicy.bases_atendimento(self.support)
            .values_list('pk', flat=True)
        )

        self.assertEqual(own_base_ids, {self.bases[self.propria.pk].pk})
        self.assertEqual(attendance_base_ids, {
            self.bases[self.propria.pk].pk,
            self.bases[self.brasil.pk].pk,
            self.bases[self.latam.pk].pk,
            self.bases[self.oxxo.pk].pk,
        })

    def test_support_is_candidate_only_for_shared_or_own_scope(self):
        for company in (self.brasil, self.latam, self.oxxo):
            self.assertTrue(
                ChamadoAccessPolicy.atendentes_para(
                    self.chamados[company.pk]
                ).filter(pk=self.support.pk).exists()
            )
        self.assertFalse(
            ChamadoAccessPolicy.atendentes_para(
                self.chamados[self.externa.pk]
            ).filter(pk=self.support.pk).exists()
        )

    def test_relationship_needs_flag_and_exact_chamados_capability(self):
        relationship = RelacionamentoEmpresa.objects.get(
            empresa_origem=self.brasil,
            empresa_destino=self.latam,
        )
        relationship.compartilha_suporte_chamados = False
        relationship.save(update_fields=['compartilha_suporte_chamados'])

        company_ids = set(
            ChamadoAccessPolicy.empresas_suporte_compartilhado(self.support)
            .values_list('pk', flat=True)
        )
        self.assertNotIn(self.latam.pk, company_ids)


class InventorySupportMigrationTests(TestCase):
    def test_migration_marks_only_inventory_directional_relationships(self):
        brasil = Empresa.objects.create(nome='Inventory Brasil', slug='inventory-brasil')
        latam = Empresa.objects.create(nome='Inventory LATAM', slug='inventory-latam')
        oxxo = Empresa.objects.create(nome='OXXO', slug='oxxo')
        externa = Empresa.objects.create(nome='Externa', slug='externa-migration-suporte')
        expected = [
            RelacionamentoEmpresa.objects.create(
                empresa_origem=brasil, empresa_destino=destination
            )
            for destination in (latam, oxxo)
        ]
        unrelated = RelacionamentoEmpresa.objects.create(
            empresa_origem=brasil, empresa_destino=externa
        )

        support_migration.habilitar_suporte_inventory(django_apps, None)

        self.assertEqual(
            RelacionamentoEmpresa.objects.filter(
                pk__in=[item.pk for item in expected],
                compartilha_suporte_chamados=True,
            ).count(),
            2,
        )
        unrelated.refresh_from_db()
        self.assertFalse(unrelated.compartilha_suporte_chamados)
