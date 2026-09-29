from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import transaction
from django.test import TestCase
from django.urls import reverse

from compras.models import CatalogoProdutoEmpresa

from estoque.models import (
    Base,
    CapacidadeRelacionamentoEmpresa,
    CategoriaEquipamentoEmpresa,
    Empresa,
    Modulo,
    ModuloEmpresa,
    Perfil,
    Produto,
    RelacionamentoEmpresa,
    SecaoDocumentacaoEmpresa,
    TermoEmpresa,
)
from estoque.services.tenant_terminology_service import TenantTerminologyService
from estoque.tenant_features import TenantFeatureService


class TenantOnboardingStage24Tests(TestCase):
    def setUp(self):
        self.existing_company = Empresa.objects.create(
            nome='Empresa Existente 24',
            slug='empresa-existente-24',
        )
        self.superuser = User.objects.create_superuser(
            username='root.onboarding.24',
            email='root-onboarding-24@example.test',
            password='Senha-Root-Somente-Teste-24!',
        )
        self.root_password_hash = self.superuser.password
        self.client.force_login(self.superuser)

    @staticmethod
    def step_url(step, company=None):
        url = reverse('estoque:onboarding_empresa_etapa', args=(step,))
        return f'{url}?empresa={company.pk}' if company else url

    def test_complete_flow_keeps_tenant_inactive_until_final_validation(self):
        response = self.client.get(
            f'{reverse("estoque:onboarding_empresa")}?novo=1'
        )
        self.assertRedirects(response, self.step_url('dados'))

        response = self.client.post(self.step_url('dados'), {
            'nome': 'Empresa Nova Etapa 24',
            'slug': 'empresa-nova-etapa-24',
        })
        company = Empresa.objects.get(slug='empresa-nova-etapa-24')
        self.assertFalse(company.ativa)
        self.assertRedirects(response, self.step_url('modulos', company))

        selected_modules = [
            Modulo.Codigo.ESTOQUE,
            Modulo.Codigo.EQUIPAMENTOS,
            Modulo.Codigo.CHAMADOS,
        ]
        response = self.client.post(self.step_url('modulos', company), {
            'modulos': selected_modules,
        })
        self.assertRedirects(response, self.step_url('terminologia', company))
        self.assertEqual(
            set(ModuloEmpresa.objects.filter(
                empresa=company,
                habilitado=True,
            ).values_list('modulo__codigo', flat=True)),
            set(selected_modules),
        )

        for current_step, next_step in (
            ('terminologia', 'categorias'),
            ('categorias', 'catalogo'),
            ('catalogo', 'admin'),
        ):
            page = self.client.get(self.step_url(current_step, company))
            self.assertEqual(page.status_code, 200)
            self.assertEqual(len(page.context['etapas']), 10)
            response = self.client.post(self.step_url(current_step, company))
            self.assertRedirects(response, self.step_url(next_step, company))

        response = self.client.get(self.step_url('documentacao', company))
        self.assertRedirects(response, self.step_url('admin', company))
        self.assertFalse(company.secoes_documentacao.exists())

        response = self.client.post(self.step_url('admin', company), {
            'username': 'primeiro.admin.etapa24',
            'first_name': 'Primeiro',
            'last_name': 'Admin',
            'email': 'primeiro-admin-24@example.test',
            'password': 'Senha-Inicial-Segura-24!x',
            'password_confirmation': 'Senha-Inicial-Segura-24!x',
        })
        self.assertRedirects(response, self.step_url('bases', company))
        first_admin = User.objects.get(username='primeiro.admin.etapa24')
        self.assertFalse(first_admin.is_superuser)
        self.assertFalse(first_admin.is_staff)
        self.assertTrue(first_admin.is_active)
        self.assertTrue(first_admin.check_password('Senha-Inicial-Segura-24!x'))
        self.assertEqual(first_admin.perfil.empresa, company)
        self.assertEqual(first_admin.perfil.role, Perfil.Role.ADMIN)

        response = self.client.post(self.step_url('bases', company), {
            'bases': 'Base Norte 24\nBase Sul 24\nBase Norte 24',
        })
        self.assertRedirects(response, self.step_url('relacionamentos', company))
        self.assertEqual(company.bases.count(), 2)

        response = self.client.post(self.step_url('relacionamentos', company), {
            'relacionamentos': [str(self.existing_company.pk)],
            f'suporte_{self.existing_company.pk}': '1',
        })
        self.assertRedirects(response, self.step_url('revisar', company))
        relationship = RelacionamentoEmpresa.objects.get(
            empresa_origem=company,
            empresa_destino=self.existing_company,
        )
        self.assertTrue(relationship.ativo)
        self.assertTrue(relationship.compartilha_suporte_chamados)
        self.assertTrue(
            CapacidadeRelacionamentoEmpresa.objects.filter(
                relacionamento=relationship,
                recurso=CapacidadeRelacionamentoEmpresa.Recurso.CHAMADOS,
                acao=CapacidadeRelacionamentoEmpresa.Acao.ATENDER,
                ativo=True,
            ).exists()
        )

        company.refresh_from_db()
        self.assertFalse(company.ativa)
        review = self.client.get(self.step_url('revisar', company))
        self.assertTrue(review.context['pronto_para_ativar'])
        self.assertFalse(review.context['pendencias_ativacao'])
        self.assertEqual(review.context['categorias_ativas_revisao'], [])
        self.assertEqual(review.context['produtos_revisao'], [])
        self.assertContains(review, '10. Revisar e ativar')
        response = self.client.post(self.step_url('revisar', company))
        self.assertRedirects(response, reverse('estoque:painel_superuser'))
        company.refresh_from_db()
        self.assertTrue(company.ativa)

        self.superuser.refresh_from_db()
        self.assertEqual(self.superuser.password, self.root_password_hash)

    def test_cannot_activate_without_explicit_modules_or_first_admin(self):
        company = Empresa.objects.create(
            nome='Tenant Incompleto 24',
            slug='tenant-incompleto-24',
            ativa=False,
        )

        response = self.client.post(self.step_url('revisar', company))

        self.assertRedirects(response, self.step_url('modulos', company))
        company.refresh_from_db()
        self.assertFalse(company.ativa)

    def test_terminology_step_persists_only_allowed_terms_and_enabled_modules(self):
        company = Empresa.objects.create(
            nome='Tenant Terminologia 24',
            slug='tenant-terminologia-24',
            ativa=False,
        )
        TenantFeatureService.configure(
            tenant=company,
            codigo=Modulo.Codigo.ESTOQUE,
            enabled=True,
            actor=self.superuser,
        )

        response = self.client.post(self.step_url('terminologia', company), {
            'modulo_nome_estoque': 'Gestão de Ativos',
            'modulo_nome_chamados': 'Nome injetado',
            'termo_equipamento_singular': 'Máquina',
            'termo_equipamento_plural': 'Máquinas',
            'termo_documentacao_singular': 'Acervo indevido',
            'termo_chave_inexistente_singular': 'Inválido',
        })

        self.assertRedirects(response, self.step_url('categorias', company))
        self.assertEqual(
            ModuloEmpresa.objects.get(
                empresa=company, modulo__codigo=Modulo.Codigo.ESTOQUE,
            ).nome_exibicao,
            'Gestão de Ativos',
        )
        self.assertEqual(
            TenantTerminologyService.label(
                company, TermoEmpresa.Chave.EQUIPAMENTO
            ),
            'Máquina',
        )
        self.assertFalse(
            ModuloEmpresa.objects.get(
                empresa=company, modulo__codigo=Modulo.Codigo.CHAMADOS,
            ).nome_exibicao
        )
        self.assertFalse(
            TermoEmpresa.objects.filter(
                empresa=company, chave='chave_inexistente'
            ).exists()
        )
        self.assertFalse(
            TermoEmpresa.objects.filter(
                empresa=company,
                chave=TermoEmpresa.Chave.DOCUMENTACAO,
            ).exists()
        )

        response = self.client.post(self.step_url('terminologia', company), {})
        self.assertRedirects(response, self.step_url('categorias', company))
        self.assertFalse(TermoEmpresa.objects.filter(empresa=company).exists())
        self.assertFalse(
            ModuloEmpresa.objects.get(
                empresa=company, modulo__codigo=Modulo.Codigo.ESTOQUE,
            ).nome_exibicao
        )

    def test_terminology_validation_is_atomic(self):
        company = Empresa.objects.create(
            nome='Tenant Terminologia Inválida 24',
            slug='tenant-terminologia-invalida-24',
            ativa=False,
        )
        TenantFeatureService.configure(
            tenant=company,
            codigo=Modulo.Codigo.ESTOQUE,
            enabled=True,
            actor=self.superuser,
        )

        response = self.client.post(self.step_url('terminologia', company), {
            'modulo_nome_estoque': 'Nome válido que não deve ser salvo',
            'termo_equipamento_singular': 'X' * 151,
        })

        self.assertEqual(response.status_code, 200)
        self.assertFalse(TermoEmpresa.objects.filter(empresa=company).exists())
        self.assertFalse(
            ModuloEmpresa.objects.get(
                empresa=company, modulo__codigo=Modulo.Codigo.ESTOQUE,
            ).nome_exibicao
        )

    def test_categories_step_creates_updates_and_deactivates_only_own_records(self):
        company = Empresa.objects.create(
            nome='Tenant Categorias 24', slug='tenant-categorias-24', ativa=False,
        )
        foreign = CategoriaEquipamentoEmpresa.objects.create(
            empresa=self.existing_company,
            nome='Categoria Estrangeira',
            ordem=7,
        )

        response = self.client.post(self.step_url('categorias', company), {
            'categories_present': '1',
            'novas_categorias': 'Máquinas de impressão\nMáquinas operacionais',
            f'categoria_nome_{foreign.pk}': 'Tentativa de invasão',
        })

        self.assertRedirects(response, self.step_url('catalogo', company))
        categories = list(company.categorias_equipamento.order_by('ordem'))
        self.assertEqual(
            [category.nome for category in categories],
            ['Máquinas de impressão', 'Máquinas operacionais'],
        )
        foreign.refresh_from_db()
        self.assertEqual(foreign.nome, 'Categoria Estrangeira')

        first, second = categories
        response = self.client.post(self.step_url('categorias', company), {
            'categories_present': '1',
            f'categoria_nome_{first.pk}': 'Processadores de tinta',
            f'categoria_ordem_{first.pk}': '9',
            f'categoria_nome_{second.pk}': second.nome,
            f'categoria_ordem_{second.pk}': '2',
            f'categoria_ativa_{second.pk}': '1',
        })

        self.assertRedirects(response, self.step_url('catalogo', company))
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.nome, 'Processadores de tinta')
        self.assertEqual(first.ordem, 9)
        self.assertFalse(first.ativo)
        self.assertTrue(second.ativo)
        self.assertTrue(
            CategoriaEquipamentoEmpresa.objects.filter(pk=first.pk).exists()
        )

    def test_categories_validation_is_atomic(self):
        company = Empresa.objects.create(
            nome='Tenant Categoria Inválida 24',
            slug='tenant-categoria-invalida-24',
            ativa=False,
        )
        category = CategoriaEquipamentoEmpresa.objects.create(
            empresa=company, nome='Categoria Original', ordem=1,
        )

        response = self.client.post(self.step_url('categorias', company), {
            'categories_present': '1',
            f'categoria_nome_{category.pk}': 'Nome que não será salvo',
            f'categoria_ordem_{category.pk}': '4',
            f'categoria_ativa_{category.pk}': '1',
            'novas_categorias': 'Duplicada\nduplicada',
        })

        self.assertEqual(response.status_code, 200)
        category.refresh_from_db()
        self.assertEqual(category.nome, 'Categoria Original')
        self.assertEqual(category.ordem, 1)
        self.assertEqual(company.categorias_equipamento.count(), 1)

        for index, config in enumerate(company.modulos_configurados.all()):
            config.configurado_por = self.superuser
            config.habilitado = index == 0
            config.save(update_fields=['configurado_por', 'habilitado'])
        response = self.client.post(self.step_url('revisar', company))
        self.assertRedirects(response, self.step_url('admin', company))
        company.refresh_from_db()
        self.assertFalse(company.ativa)

    def test_catalog_step_creates_owned_products_and_shares_only_explicit_selection(self):
        company = Empresa.objects.create(
            nome='Tenant Catálogo 24', slug='tenant-catalogo-24', ativa=False,
        )
        CategoriaEquipamentoEmpresa.objects.create(
            empresa=company, nome='Máquinas', ordem=1,
        )
        shared = Produto.objects.create(
            codigo='COMP-24', descricao='Produto compartilhável',
            fabricante='Fabricante Externo', modelo='Modelo Compartilhável',
            categoria='Máquinas', empresa_catalogo_origem=self.existing_company,
        )
        not_selected = Produto.objects.create(
            codigo='NAO-24', descricao='Produto não selecionado',
            fabricante='Fabricante Externo', modelo='Modelo Não Selecionado',
            categoria='Máquinas', empresa_catalogo_origem=self.existing_company,
        )

        response = self.client.post(self.step_url('catalogo', company), {
            'catalog_present': '1',
            'produto_codigo': ['maq-001'],
            'produto_descricao': ['Máquina própria'],
            'produto_fabricante': ['Fabricante próprio'],
            'produto_modelo': ['Modelo próprio'],
            'produto_categoria': ['Máquinas'],
            'produtos_catalogo': [str(shared.pk)],
        })

        self.assertRedirects(response, self.step_url('admin', company))
        owned = Produto.objects.get(
            empresa_catalogo_origem=company, codigo='MAQ-001',
        )
        self.assertEqual(owned.criado_por, self.superuser)
        self.assertTrue(CatalogoProdutoEmpresa.objects.filter(
            empresa=company, produto=owned, ativo=True,
        ).exists())
        self.assertTrue(CatalogoProdutoEmpresa.objects.filter(
            empresa=company, produto=shared, ativo=True,
        ).exists())
        self.assertFalse(CatalogoProdutoEmpresa.objects.filter(
            empresa=company, produto=not_selected,
        ).exists())

        response = self.client.post(self.step_url('catalogo', company), {
            'catalog_present': '1',
        })
        self.assertRedirects(response, self.step_url('admin', company))
        self.assertFalse(CatalogoProdutoEmpresa.objects.get(
            empresa=company, produto=owned,
        ).ativo)
        self.assertFalse(CatalogoProdutoEmpresa.objects.get(
            empresa=company, produto=shared,
        ).ativo)
        self.assertTrue(Produto.objects.filter(pk=owned.pk).exists())

    def test_catalog_validation_is_atomic_and_rejects_incompatible_product(self):
        company = Empresa.objects.create(
            nome='Tenant Catálogo Inválido 24',
            slug='tenant-catalogo-invalido-24',
            ativa=False,
        )
        CategoriaEquipamentoEmpresa.objects.create(
            empresa=company, nome='Máquinas', ordem=1,
        )
        incompatible = Produto.objects.create(
            codigo='EXT-INVALIDO-24', descricao='Produto incompatível',
            fabricante='Externo', modelo='Outro', categoria='Categoria externa',
            empresa_catalogo_origem=self.existing_company,
        )

        response = self.client.post(self.step_url('catalogo', company), {
            'catalog_present': '1',
            'produto_codigo': ['OWN-INVALIDO-24'],
            'produto_descricao': ['Não deve ser criado'],
            'produto_fabricante': ['Fabricante'],
            'produto_modelo': ['Modelo'],
            'produto_categoria': ['Máquinas'],
            'produtos_catalogo': [str(incompatible.pk)],
        })

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Produto.objects.filter(
            empresa_catalogo_origem=company,
        ).exists())
        self.assertFalse(CatalogoProdutoEmpresa.objects.filter(
            empresa=company,
        ).exists())

    def test_documentation_step_configures_only_current_tenant_allowed_sections(self):
        company = Empresa.objects.create(
            nome='Tenant Documentação 24',
            slug='tenant-documentacao-24',
            ativa=False,
        )
        TenantFeatureService.configure(
            tenant=company,
            codigo=Modulo.Codigo.DOCUMENTACAO,
            enabled=True,
            actor=self.superuser,
        )
        foreign = SecaoDocumentacaoEmpresa.objects.create(
            empresa=self.existing_company,
            codigo=SecaoDocumentacaoEmpresa.Codigo.MANUAIS,
            habilitado=True,
            nome_exibicao='Manual estrangeiro',
            permite_conteudo_global_legado=True,
        )

        response = self.client.post(self.step_url('documentacao', company), {
            'documentation_present': '1',
            'secao_manuais_habilitada': '1',
            'secao_manuais_nome': 'Manual Operacional',
            'secao_resolucoes_habilitada': '1',
            'secao_resolucoes_nome': 'Soluções Técnicas',
            'secao_codigo_injetado_habilitada': '1',
            'secao_codigo_injetado_nome': 'Seção inválida',
        })

        self.assertRedirects(response, self.step_url('admin', company))
        self.assertEqual(company.secoes_documentacao.count(), 6)
        manuals = company.secoes_documentacao.get(
            codigo=SecaoDocumentacaoEmpresa.Codigo.MANUAIS,
        )
        resolutions = company.secoes_documentacao.get(
            codigo=SecaoDocumentacaoEmpresa.Codigo.RESOLUCOES,
        )
        drivers = company.secoes_documentacao.get(
            codigo=SecaoDocumentacaoEmpresa.Codigo.DRIVERS,
        )
        self.assertTrue(manuals.habilitado)
        self.assertEqual(manuals.nome_exibicao, 'Manual Operacional')
        self.assertFalse(manuals.permite_conteudo_global_legado)
        self.assertTrue(resolutions.habilitado)
        self.assertEqual(resolutions.nome_exibicao, 'Soluções Técnicas')
        self.assertFalse(drivers.habilitado)
        self.assertFalse(company.secoes_documentacao.filter(
            codigo='codigo_injetado',
        ).exists())
        foreign.refresh_from_db()
        self.assertEqual(foreign.nome_exibicao, 'Manual estrangeiro')
        self.assertTrue(foreign.permite_conteudo_global_legado)

    def test_documentation_step_is_skipped_when_module_is_disabled(self):
        company = Empresa.objects.create(
            nome='Tenant Sem Documentação 24',
            slug='tenant-sem-documentacao-24',
            ativa=False,
        )
        existing = SecaoDocumentacaoEmpresa.objects.create(
            empresa=company,
            codigo=SecaoDocumentacaoEmpresa.Codigo.MANUAIS,
            habilitado=True,
            nome_exibicao='Configuração preservada',
        )

        response = self.client.post(self.step_url('documentacao', company), {
            'documentation_present': '1',
            'secao_drivers_habilitada': '1',
        })

        self.assertRedirects(response, self.step_url('admin', company))
        existing.refresh_from_db()
        self.assertTrue(existing.habilitado)
        self.assertEqual(existing.nome_exibicao, 'Configuração preservada')
        self.assertEqual(company.secoes_documentacao.count(), 1)

    def test_documentation_validation_is_atomic(self):
        company = Empresa.objects.create(
            nome='Tenant Documentação Inválida 24',
            slug='tenant-documentacao-invalida-24',
            ativa=False,
        )
        TenantFeatureService.configure(
            tenant=company,
            codigo=Modulo.Codigo.DOCUMENTACAO,
            enabled=True,
            actor=self.superuser,
        )
        existing = SecaoDocumentacaoEmpresa.objects.create(
            empresa=company,
            codigo=SecaoDocumentacaoEmpresa.Codigo.MANUAIS,
            habilitado=False,
            nome_exibicao='Nome original',
        )

        response = self.client.post(self.step_url('documentacao', company), {
            'documentation_present': '1',
            'secao_manuais_habilitada': '1',
            'secao_manuais_nome': 'X' * 101,
            'secao_drivers_habilitada': '1',
        })

        self.assertEqual(response.status_code, 200)
        existing.refresh_from_db()
        self.assertFalse(existing.habilitado)
        self.assertEqual(existing.nome_exibicao, 'Nome original')
        self.assertEqual(company.secoes_documentacao.count(), 1)

    def test_final_review_summarizes_complete_tenant_configuration(self):
        company = Empresa.objects.create(
            nome='Tenant Revisão Completa 24',
            slug='tenant-revisao-completa-24',
            ativa=False,
        )
        self.client.post(self.step_url('modulos', company), {
            'modulos': [
                Modulo.Codigo.ESTOQUE,
                Modulo.Codigo.DOCUMENTACAO,
            ],
        })
        self.client.post(self.step_url('terminologia', company), {
            'modulo_nome_estoque': 'Gestão de Máquinas',
            'termo_equipamento_singular': 'Máquina',
            'termo_equipamento_plural': 'Máquinas',
        })
        category = CategoriaEquipamentoEmpresa.objects.create(
            empresa=company, nome='Máquinas industriais', ordem=1,
        )
        product = Produto.objects.create(
            codigo='REV-001', descricao='Máquina da revisão',
            fabricante='Fabricante Revisão', modelo='Modelo Revisão',
            categoria=category.nome, empresa_catalogo_origem=company,
            criado_por=self.superuser,
        )
        CatalogoProdutoEmpresa.objects.create(
            empresa=company, produto=product, configurado_por=self.superuser,
        )
        self.client.post(self.step_url('documentacao', company), {
            'documentation_present': '1',
            'secao_manuais_habilitada': '1',
            'secao_manuais_nome': 'Manual Operacional',
        })
        admin = User.objects.create_user(
            'admin.revisao.24', password='Senha-Revisao-24!segura',
        )
        admin.perfil.empresa = company
        admin.perfil.role = Perfil.Role.ADMIN
        admin.perfil.save(update_fields=['empresa', 'role'])
        base = Base.objects.create(empresa=company, nome='Unidade Revisão')
        relationship = RelacionamentoEmpresa.objects.create(
            empresa_origem=company,
            empresa_destino=self.existing_company,
            compartilha_suporte_chamados=True,
            criado_por=self.superuser,
        )

        response = self.client.get(self.step_url('revisar', company))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['pronto_para_ativar'])
        self.assertIn(
            'Gestão de Máquinas',
            [item['nome_apresentacao'] for item in response.context['modulos_habilitados_revisao']],
        )
        self.assertEqual(response.context['categorias_ativas_revisao'], [category])
        self.assertEqual(response.context['produtos_revisao'], [product])
        self.assertEqual(
            response.context['secoes_documentacao_revisao'],
            [{'codigo': 'manuais', 'nome': 'Manual Operacional'}],
        )
        self.assertEqual(response.context['bases_onboarding'], [base])
        self.assertEqual(response.context['relacionamentos_revisao'], [relationship])
        self.assertContains(response, 'Máquinas industriais')
        self.assertContains(response, 'Manual Operacional')

    def test_activation_rejects_enabled_documentation_without_enabled_section(self):
        company = Empresa.objects.create(
            nome='Tenant Documentação Pendente 24',
            slug='tenant-documentacao-pendente-24',
            ativa=False,
        )
        self.client.post(self.step_url('modulos', company), {
            'modulos': [Modulo.Codigo.DOCUMENTACAO],
        })
        admin = User.objects.create_user(
            'admin.docs.pendente.24', password='Senha-Docs-24!segura',
        )
        admin.perfil.empresa = company
        admin.perfil.role = Perfil.Role.ADMIN
        admin.perfil.save(update_fields=['empresa', 'role'])

        review = self.client.get(self.step_url('revisar', company))
        self.assertFalse(review.context['pronto_para_ativar'])
        self.assertContains(review, 'Nenhuma seção habilitada')
        response = self.client.post(self.step_url('revisar', company))

        self.assertRedirects(response, self.step_url('documentacao', company))
        company.refresh_from_db()
        self.assertFalse(company.ativa)

    def test_admin_password_errors_do_not_create_partial_user(self):
        company = Empresa.objects.create(
            nome='Tenant Senha Inválida 24',
            slug='tenant-senha-invalida-24',
            ativa=False,
        )

        response = self.client.post(self.step_url('admin', company), {
            'username': 'admin.parcial.24',
            'password': '123',
            'password_confirmation': 'diferente',
        })

        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='admin.parcial.24').exists())
        self.assertFalse(response.context['admins_onboarding'])

    def test_cancel_keeps_partial_tenant_inactive(self):
        company = Empresa.objects.create(
            nome='Tenant Pausado 24',
            slug='tenant-pausado-24',
            ativa=False,
        )

        response = self.client.post(self.step_url('bases', company), {
            'acao': 'cancelar',
        })

        self.assertRedirects(response, reverse('estoque:painel_superuser'))
        company.refresh_from_db()
        self.assertFalse(company.ativa)
        self.assertTrue(Empresa.objects.filter(pk=company.pk).exists())

    def test_tenant_admin_cannot_open_or_post_onboarding(self):
        admin = User.objects.create_user(
            username='admin.sem.onboarding.24',
            password='Senha-Somente-Teste-24!',
        )
        admin.perfil.empresa = self.existing_company
        admin.perfil.role = Perfil.Role.ADMIN
        admin.perfil.save(update_fields=['empresa', 'role'])
        self.client.force_login(admin)

        self.assertEqual(
            self.client.get(reverse('estoque:onboarding_empresa')).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(self.step_url('dados'), {'nome': 'Intrusa 24'}).status_code,
            403,
        )
        self.assertFalse(Empresa.objects.filter(nome__iexact='Intrusa 24').exists())

    def test_inactive_company_is_not_available_in_operational_company_selects(self):
        inactive = Empresa.objects.create(
            nome='Tenant Inativo Select 24',
            slug='tenant-inativo-select-24',
            ativa=False,
        )

        panel = self.client.get(reverse('estoque:painel_superuser'))

        self.assertIn(inactive, panel.context['empresas'])
        self.assertNotIn(inactive, panel.context['empresas_ativas_select'])
        response = self.client.post(reverse('estoque:painel_superuser'), {
            'acao': 'criar_base',
            'empresa': str(inactive.pk),
            'nome': 'Base indevida',
        })
        self.assertRedirects(response, reverse('estoque:painel_superuser'))
        self.assertFalse(Base.objects.filter(
            empresa=inactive,
            nome='Base indevida',
        ).exists())

    def test_active_tenant_can_be_maintained_through_complete_configuration_flow(self):
        company = self.existing_company
        admin = User.objects.create_user(
            'admin.manutencao.24', password='Senha-Manutencao-24!segura',
        )
        admin.perfil.empresa = company
        admin.perfil.role = Perfil.Role.ADMIN
        admin.perfil.save(update_fields=['empresa', 'role'])
        destination = Empresa.objects.create(
            nome='Destino Manutenção 24', slug='destino-manutencao-24',
        )

        page = self.client.get(self.step_url('dados', company))
        self.assertEqual(page.status_code, 200)
        self.assertTrue(page.context['modo_manutencao'])
        self.assertContains(page, 'Manutenção do tenant')

        self.client.post(self.step_url('modulos', company), {
            'modulos': [Modulo.Codigo.ESTOQUE, Modulo.Codigo.DOCUMENTACAO],
        })
        self.client.post(self.step_url('terminologia', company), {
            'modulo_nome_estoque': 'Ativos Corporativos',
            'termo_equipamento_singular': 'Máquina',
            'termo_equipamento_plural': 'Máquinas',
        })
        category_response = self.client.post(self.step_url('categorias', company), {
            'categories_present': '1',
            'novas_categorias': 'Máquinas de campo',
        })
        self.assertRedirects(category_response, self.step_url('catalogo', company))
        catalog_response = self.client.post(self.step_url('catalogo', company), {
            'catalog_present': '1',
            'produto_codigo': ['MAN-001'],
            'produto_descricao': ['Máquina de manutenção'],
            'produto_fabricante': ['Fabricante manutenção'],
            'produto_modelo': ['Modelo manutenção'],
            'produto_categoria': ['Máquinas de campo'],
        })
        self.assertRedirects(catalog_response, self.step_url('documentacao', company))
        self.client.post(self.step_url('documentacao', company), {
            'documentation_present': '1',
            'secao_manuais_habilitada': '1',
            'secao_manuais_nome': 'Manuais internos',
        })
        self.client.post(self.step_url('bases', company), {
            'bases': 'Unidade de manutenção',
        })
        self.client.post(self.step_url('relacionamentos', company), {
            'relacionamentos': [str(destination.pk)],
        })

        review = self.client.get(self.step_url('revisar', company))
        company.refresh_from_db()
        self.assertTrue(company.ativa)
        self.assertTrue(review.context['modo_manutencao'])
        self.assertTrue(review.context['pronto_para_ativar'])
        self.assertContains(review, 'Concluir revisão')
        response = self.client.post(self.step_url('revisar', company))
        self.assertRedirects(response, reverse('estoque:painel_superuser'))
        company.refresh_from_db()
        self.assertTrue(company.ativa)
        self.assertTrue(company.categorias_equipamento.filter(
            nome='Máquinas de campo', ativo=True,
        ).exists())
        self.assertTrue(CatalogoProdutoEmpresa.objects.filter(
            empresa=company, produto__codigo='MAN-001', ativo=True,
        ).exists())
        self.assertTrue(company.secoes_documentacao.filter(
            codigo='manuais', habilitado=True, nome_exibicao='Manuais internos',
        ).exists())

    def test_deactivate_and_reactivate_tenant_preserves_configuration(self):
        company = self.existing_company
        category = CategoriaEquipamentoEmpresa.objects.create(
            empresa=company, nome='Categoria preservada H',
        )
        product = Produto.objects.create(
            codigo='PRES-H', descricao='Produto preservado H',
            fabricante='Fabricante H', modelo='Modelo H',
            categoria=category.nome, empresa_catalogo_origem=company,
        )
        catalog = CatalogoProdutoEmpresa.objects.create(
            empresa=company, produto=product,
        )
        section = SecaoDocumentacaoEmpresa.objects.create(
            empresa=company, codigo='manuais', habilitado=True,
            nome_exibicao='Manual preservado H',
        )
        term = TermoEmpresa.objects.create(
            empresa=company, chave=TermoEmpresa.Chave.EQUIPAMENTO,
            valor_singular='Máquina preservada H',
        )

        panel = self.client.get(reverse('estoque:painel_superuser'))
        self.assertContains(
            panel,
            f'{self.step_url("dados", company)}',
            html=False,
        )
        response = self.client.post(reverse('estoque:painel_superuser'), {
            'acao': 'alterar_status_empresa',
            'empresa': company.pk,
            'ativa': '0',
        })
        self.assertRedirects(response, reverse('estoque:painel_superuser'))
        company.refresh_from_db()
        self.assertFalse(company.ativa)
        for instance in (category, product, catalog, section, term):
            self.assertTrue(type(instance).objects.filter(pk=instance.pk).exists())

        self.client.post(reverse('estoque:painel_superuser'), {
            'acao': 'alterar_status_empresa',
            'empresa': company.pk,
            'ativa': '1',
        })
        company.refresh_from_db()
        self.assertTrue(company.ativa)
        self.assertTrue(CatalogoProdutoEmpresa.objects.get(pk=catalog.pk).ativo)
        self.assertTrue(SecaoDocumentacaoEmpresa.objects.get(pk=section.pk).habilitado)
        self.assertEqual(
            TermoEmpresa.objects.get(pk=term.pk).valor_singular,
            'Máquina preservada H',
        )


class TenantMembershipHardeningStage24Tests(TestCase):
    def setUp(self):
        self.active_company = Empresa.objects.create(
            nome='Empresa Ativa Hardening 24',
            slug='empresa-ativa-hardening-24',
        )
        self.inactive_company = Empresa.objects.create(
            nome='Empresa Inativa Hardening 24',
            slug='empresa-inativa-hardening-24',
            ativa=False,
        )

    def test_active_non_superuser_profile_requires_company_on_validation(self):
        user = User.objects.create_user('orfao.validacao.24')

        with self.assertRaises(ValidationError):
            user.perfil.full_clean()

        user.is_active = False
        user.save(update_fields=['is_active'])
        user.perfil.full_clean()

    def test_middleware_blocks_missing_or_inactive_tenant_but_not_superuser(self):
        orphan = User.objects.create_user('orfao.middleware.24')
        self.client.force_login(orphan)
        self.assertEqual(self.client.get(reverse('estoque:caixa_comunicados')).status_code, 403)

        inactive = User.objects.create_user('inativo.middleware.24')
        inactive.perfil.empresa = self.inactive_company
        inactive.perfil.save(update_fields=['empresa'])
        self.client.force_login(inactive)
        self.assertEqual(self.client.get(reverse('estoque:caixa_comunicados')).status_code, 403)

        root = User.objects.create_superuser('root.middleware.24')
        self.client.force_login(root)
        self.assertEqual(self.client.get(reverse('estoque:painel_superuser')).status_code, 200)

    def test_cross_tenant_bases_are_rejected_on_profile_relations(self):
        other_company = Empresa.objects.create(
            nome='Outra Empresa Hardening 24',
            slug='outra-empresa-hardening-24',
        )
        own_base = Base.objects.create(nome='Base Própria 24', empresa=self.active_company)
        foreign_base = Base.objects.create(nome='Base Estrangeira 24', empresa=other_company)
        user = User.objects.create_user('bases.hardening.24')
        user.perfil.empresa = self.active_company
        user.perfil.save(update_fields=['empresa'])

        user.perfil.regionais.add(own_base)
        with self.assertRaises(ValidationError), transaction.atomic():
            user.perfil.regionais.add(foreign_base)
        with self.assertRaises(ValidationError), transaction.atomic():
            user.perfil.bases_checklist.add(foreign_base)

    def test_company_slug_is_generated_and_unique(self):
        first = Empresa.objects.create(nome='Tenant Sem Slug 24')
        second = Empresa.objects.create(nome='Tenant Sem Slug 24 - Outra')

        self.assertTrue(first.slug)
        self.assertTrue(second.slug)
        self.assertNotEqual(first.slug, second.slug)
