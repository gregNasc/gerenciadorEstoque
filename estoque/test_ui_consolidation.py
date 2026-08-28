from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from estoque.models import Base, Empresa, Equipamento, Produto
from insumos.models import CategoriaInsumo, Insumo, MovimentacaoInsumo


class UIConsolidationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username='admin-ui',
            email='admin-ui@example.test',
            password='senha-temporaria-ui',
        )
        self.empresa = Empresa.objects.create(nome='Empresa UI')
        self.base = Base.objects.create(nome='Base UI', empresa=self.empresa)
        self.user.perfil.role = 'admin'
        self.user.perfil.empresa = self.empresa
        self.user.perfil.save()
        self.user.perfil.regionais.add(self.base)
        self.client.force_login(self.user)

    def test_paginas_prioritarias_concentram_navegacao_e_conta_na_sidebar(self):
        urls = (
            reverse('estoque:index'),
            reverse('estoque:estoque'),
            reverse('insumos:estoque_insumos'),
            reverse('chamados:lista'),
            reverse('auditorias:campanha_lista'),
        )
        for url in urls:
            with self.subTest(url=url):
                resposta = self.client.get(url)
                self.assertEqual(resposta.status_code, 200)
                self.assertContains(resposta, 'id="appSidebar"')
                self.assertContains(resposta, 'id="appSidebarCollapse"')
                self.assertContains(resposta, 'id="appMobileSidebarToggle"')
                self.assertContains(resposta, 'id="appMobileSidebarClose"')
                self.assertContains(resposta, 'id="appSidebarAccount"')
                self.assertContains(resposta, 'Dashboard de Ativos')
                self.assertContains(resposta, 'Preferências')
                self.assertContains(resposta, "sidebar.addEventListener('click'")
                self.assertContains(resposta, "collapseToggle?.addEventListener('click'")
                self.assertContains(resposta, "mobileClose?.addEventListener('click', fecharMobile)")
                self.assertContains(resposta, 'id="navbarEstoque"')
                self.assertContains(resposta, 'data-bs-toggle="dropdown"')
                self.assertContains(resposta, 'id="estoqueDropdownMenu"')
                self.assertContains(resposta, 'aria-labelledby="navbarEstoque"')
                self.assertContains(resposta, "if (typeof bootstrap !== 'undefined')")
                self.assertContains(resposta, "if (typeof bootstrap === 'undefined')")
                self.assertContains(resposta, "toggle.addEventListener('click'")
                self.assertContains(resposta, 'bootstrap.Dropdown.getOrCreateInstance(toggle).hide()')
                self.assertContains(resposta, 'bootstrap.Tooltip.getOrCreateInstance')
                self.assertNotContains(resposta, 'data-app-sidebar-submenu="estoque"')
                self.assertNotContains(resposta, 'data-bs-display="static"')
                self.assertNotContains(resposta, 'app-sidebar-stock-menu')
                self.assertNotContains(resposta, "estoqueToggle?.addEventListener('click'")
                self.assertNotContains(resposta, 'function definirEstoqueAberto')
                self.assertNotContains(resposta, 'function definirDropdownAberto')
                self.assertNotContains(resposta, 'event.stopImmediatePropagation()')
                self.assertNotContains(resposta, 'id="appSidebarToggle"')
                self.assertNotContains(resposta, 'class="top-navbar app-topbar"')
                self.assertNotContains(resposta, 'id="perfilDropdown"')

    def test_navegacao_nao_recolhe_sidebar_no_desktop_e_fecha_no_mobile(self):
        conteudo = self.client.get(reverse('estoque:index')).content.decode()
        inicio = conteudo.index('destinos.forEach(function (destino)')
        fim = conteudo.index('function abrirMobile()', inicio)
        bloco_destinos = conteudo[inicio:fim]

        self.assertNotIn("body.classList.add('app-sidebar-collapsed')", bloco_destinos)
        self.assertNotIn('guardarRecolhida(true)', bloco_destinos)
        self.assertIn('if (!desktop.matches)', bloco_destinos)
        self.assertIn("body.classList.remove('app-sidebar-open')", bloco_destinos)
        self.assertIn('aplicarEstado()', bloco_destinos)

        self.assertIn(
            "body.classList.toggle('app-sidebar-collapsed', recolher)",
            conteudo,
        )
        self.assertIn('guardarRecolhida(recolher)', conteudo)

    def test_sidebar_mantem_um_unico_scroll_e_nao_quebra_itens_no_mobile(self):
        css = (
            Path(settings.BASE_DIR) / 'estoque' / 'static' / 'css' / 'style.css'
        ).read_text(encoding='utf-8')

        self.assertIn('.app-sidebar > .app-sidebar-inner {', css)
        self.assertIn('flex-wrap: nowrap;', css)
        self.assertIn('.app-sidebar-nav {', css)
        self.assertIn('overflow-y: auto;', css)
        self.assertIn('.app-sidebar .dropdown-menu {', css)
        self.assertIn('position: static !important;', css)
        self.assertNotIn('.app-sidebar .app-sidebar-stock-menu', css)

    def test_dashboard_usa_filtros_explicitos_e_bootstrap_modal(self):
        resposta = self.client.get(reverse('estoque:index'))
        self.assertContains(resposta, 'app-filter-panel')
        self.assertContains(resposta, 'modal-dialog modal-xl')
        self.assertNotContains(resposta, 'form-select form-select-sm bg-white auto-submit')

    def test_lista_chamados_tem_labels_status_e_linha_acessivel(self):
        resposta = self.client.get(reverse('chamados:lista'), {'q': 'sem-resultado'})
        self.assertContains(resposta, 'for="chamados-q"')
        self.assertContains(resposta, 'for="chamados-status"')
        self.assertContains(resposta, 'app-empty-state')
        self.assertContains(resposta, 'chamados encontrados')

    def test_alerta_sonoro_nao_e_suprimido_na_conversa_aberta(self):
        conteudo = self.client.get(reverse('estoque:index')).content.decode()
        tocar = conteudo.index('tocar();', conteudo.index('function alertar(evento)'))
        retorno = conteudo.index('if (naConversa) return;', tocar)
        self.assertLess(tocar, retorno)

    def test_cadastro_de_equipamento_reabre_o_formulario_limpo(self):
        produto = Produto.objects.create(
            codigo='EQP-CAD-RAPIDO',
            descricao='Equipamento para cadastro rápido',
            categoria='Notebooks',
        )
        url = reverse('estoque:cadastrar_equipamento')
        resposta = self.client.post(url, {
            'categoria': 'Notebooks',
            'produto': produto.pk,
            'numero_serie': 'SERIE-RAPIDA-001',
            'patrimonio': 'PAT-RAPIDO-001',
            'regional': self.base.pk,
            'finalidade': Equipamento.Finalidade.OPERACIONAL,
            'responsavel': 'Equipe de estoque',
        }, follow=True)

        self.assertRedirects(resposta, url)
        self.assertTrue(
            Equipamento.objects.filter(numero_serie='SERIE-RAPIDA-001').exists()
        )
        self.assertContains(resposta, 'Equipamento cadastrado com sucesso.')
        self.assertNotContains(resposta, 'value="SERIE-RAPIDA-001"')

    def test_cadastro_de_insumo_permanece_na_tela_e_limpa_quantidade(self):
        categoria = CategoriaInsumo.objects.create(nome='Categoria cadastro rápido')
        insumo = Insumo.objects.create(
            descricao='Insumo para cadastro rápido',
            categoria=categoria,
            unidade_medida='UN',
        )
        url = reverse('insumos:cadastrar_insumos')
        resposta = self.client.post(url, {
            'base': self.base.pk,
            'categoria': categoria.pk,
            'insumo': insumo.pk,
            'quantidade': '3',
        }, follow=True)

        self.assertRedirects(resposta, url)
        self.assertTrue(
            MovimentacaoInsumo.objects.filter(
                base=self.base,
                insumo=insumo,
                tipo='ENTRADA',
                quantidade=3,
            ).exists()
        )
        self.assertContains(resposta, 'Entrada registrada com sucesso.')
        self.assertNotContains(resposta, 'value="3"')
