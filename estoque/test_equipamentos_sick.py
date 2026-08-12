import json
from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied, ValidationError
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from estoque.forms import EquipamentoForm
from estoque.models import Base, Comunicado, Empresa, Equipamento, Historico, Perfil, Produto, Sick
from estoque.services.sick_service import SickService
from estoque.policies.compras import GruposCorporativos
from insumos.constants import GruposInsumos


class EquipamentosSickBaseTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(nome='Empresa Teste')
        self.base = Base.objects.create(nome='Base A', empresa=self.empresa)
        self.outra_base = Base.objects.create(nome='Base B', empresa=self.empresa)
        self.produto = Produto.objects.create(
            codigo='PROD-SICK', descricao='Notebook Teste', fabricante='Dell',
            modelo='Latitude', categoria='Notebooks',
        )
        self.admin = self._usuario('admin_sick', Perfil.Role.ADMIN)
        self.admin2 = self._usuario('admin_sick_2', Perfil.Role.ADMIN)
        self.admin_inativo = self._usuario('admin_inativo_sick', Perfil.Role.ADMIN, ativo=False)
        self.gestor = self._usuario('gestor_sick', Perfil.Role.GESTOR, self.base)
        self.operador = self._usuario('operador_sick', Perfil.Role.OPERADOR, self.base)
        grupo_matriz, _ = Group.objects.get_or_create(
            name=GruposCorporativos.SICK_MANUTENCAO,
        )
        self.admin.groups.add(grupo_matriz)
        self.equipamento = Equipamento.objects.create(
            produto=self.produto, numero_serie='SERIE-SICK-1', patrimonio='PAT-SICK-1',
            regional=self.base, codigo='EQP-SICK-1', status='ATIVO',
        )

    @staticmethod
    def _usuario(username, role, base=None, ativo=True):
        user = User.objects.create_user(username=username, password='senha-forte', is_active=ativo)
        perfil = user.perfil
        perfil.role = role
        perfil.empresa = None if role == Perfil.Role.ADMIN else base.empresa
        perfil.save()
        if base and role != Perfil.Role.ADMIN:
            perfil.regionais.add(base)
        return user

    def _abrir(self, usuario=None, equipamento=None):
        return SickService.marcar_como_sick(
            equipamento_id=(equipamento or self.equipamento).pk,
            usuario=usuario or self.gestor,
            categoria='HARDWARE', motivo='Não liga', observacao='Falha ao iniciar',
        )

@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
)
class RecuperacaoSenhaTests(TestCase):
    def test_fluxo_envia_link_com_namespace_correto(self):
        User.objects.create_user(
            username='usuario.email',
            email='usuario@example.com',
            password='senha-antiga',
        )

        response = self.client.post(
            reverse('estoque:password_reset'),
            {'email': 'usuario@example.com'},
        )

        self.assertRedirects(
            response,
            reverse('estoque:password_reset_done'),
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('/reset/', mail.outbox[0].body)
        self.assertIn('usuario.email', mail.outbox[0].body)

    def test_telas_de_recuperacao_renderizam_sem_autenticacao(self):
        for url in (
            reverse('estoque:password_reset'),
            reverse('estoque:password_reset_done'),
            reverse('estoque:password_reset_complete'),
        ):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'auth-card')
            self.assertNotContains(response, 'Site de administração do Django')

class FinalidadeEquipamentoTests(EquipamentosSickBaseTests):
    def test_novo_equipamento_e_operacional_por_padrao(self):
        self.assertEqual(self.equipamento.finalidade, Equipamento.Finalidade.OPERACIONAL)

    def test_administrativo_fica_no_total_mas_nao_em_ativos_operacionais(self):
        self.equipamento.finalidade = Equipamento.Finalidade.ADMINISTRATIVO
        self.equipamento.save(update_fields=['finalidade'])
        qs = Equipamento.objects.filter(regional=self.base)
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.filter(status='ATIVO', finalidade='OPERACIONAL').count(), 0)
        self.assertEqual(qs.filter(finalidade='ADMINISTRATIVO').count(), 1)

    def test_finalidade_administrativa_aparece_em_sick_e_e_preservada(self):
        self.equipamento.finalidade = Equipamento.Finalidade.ADMINISTRATIVO
        self.equipamento.save(update_fields=['finalidade'])
        sick = self._abrir()
        self.assertTrue(Sick.objects.filter(pk=sick.pk, equipamento__finalidade='ADMINISTRATIVO').exists())

    def test_edicao_de_finalidade_gera_historico(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('estoque:editar_equipamento', args=[self.equipamento.pk]), {
            'numero_serie': self.equipamento.numero_serie,
            'patrimonio': self.equipamento.patrimonio,
            'produto': self.produto.pk,
            'regional': self.base.pk,
            'responsavel': '',
            'status': 'ATIVO',
            'finalidade': 'ADMINISTRATIVO',
            'observacao_edicao': 'Uso interno',
            'senha_confirmacao': 'senha-forte',
        })
        self.assertEqual(response.status_code, 302)
        self.equipamento.refresh_from_db()
        self.assertEqual(self.equipamento.finalidade, 'ADMINISTRATIVO')
        historico = Historico.objects.filter(equipamento=self.equipamento, tipo_acao='EDICAO').latest('data')
        self.assertEqual(historico.detalhes['alteracoes']['finalidade']['antes'], 'OPERACIONAL')

    def test_gestor_pode_escolher_finalidade_na_edicao(self):
        self.client.force_login(self.gestor)

        response = self.client.post(
            reverse('estoque:editar_equipamento', args=[self.equipamento.pk]),
            {
                'numero_serie': self.equipamento.numero_serie,
                'patrimonio': self.equipamento.patrimonio,
                'finalidade': 'ADMINISTRATIVO',
                'observacao_edicao': 'Alteração de uso do equipamento',
                'senha_confirmacao': 'senha-forte',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.equipamento.refresh_from_db()
        self.assertEqual(self.equipamento.finalidade, 'ADMINISTRATIVO')
        historico = Historico.objects.filter(
            equipamento=self.equipamento,
            tipo_acao='EDICAO',
        ).latest('data')
        self.assertEqual(
            historico.detalhes['alteracoes']['finalidade'],
            {'antes': 'OPERACIONAL', 'depois': 'ADMINISTRATIVO'},
        )

    def test_edicao_exibe_as_duas_finalidades(self):
        self.client.force_login(self.gestor)

        response = self.client.get(
            reverse('estoque:editar_equipamento', args=[self.equipamento.pk])
        )

        self.assertContains(response, 'name="finalidade"', count=2)
        self.assertContains(response, 'value="OPERACIONAL"')
        self.assertContains(response, 'value="ADMINISTRATIVO"')

    def test_modal_de_historico_exibe_as_duas_finalidades(self):
        self.client.force_login(self.gestor)
        Historico.objects.create(
            equipamento=self.equipamento,
            usuario=self.gestor,
            tipo_acao='EDICAO',
            detalhes={'motivo': 'Teste do modal'},
        )

        response = self.client.get(
            reverse('estoque:historico_modal', args=[self.equipamento.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="finalidade"', count=2)
        self.assertContains(response, 'value="OPERACIONAL"')
        self.assertContains(response, 'value="ADMINISTRATIVO"')

    def test_kpi_da_tela_separa_ativo_operacional_de_administrativo(self):
        self.equipamento.finalidade = Equipamento.Finalidade.ADMINISTRATIVO
        self.equipamento.save(update_fields=['finalidade'])
        self.client.force_login(self.admin)
        response = self.client.get(reverse('estoque:estoque'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['kpis_estoque']['total'], 1)
        self.assertEqual(response.context['kpis_estoque']['ativos'], 0)
        self.assertEqual(response.context['kpis_estoque']['administrativos'], 1)

class ContextoBaseTests(EquipamentosSickBaseTests):
    def test_usuario_com_uma_base_recebe_contexto_automatico(self):
        self.gestor.groups.add(Group.objects.get_or_create(name=GruposInsumos.COMPRAS)[0])
        self.client.force_login(self.gestor)
        response = self.client.get(reverse('estoque:cadastrar_equipamento'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['base_selecionada'], self.base)
        self.assertTrue(response.context['form'].fields['regional'].disabled)

    def test_gestor_sem_compras_nao_acessa_cadastro_de_equipamento(self):
        self.client.force_login(self.gestor)
        response = self.client.get(reverse('estoque:cadastrar_equipamento'))
        self.assertEqual(response.status_code, 403)

    def test_formulario_rejeita_base_fora_das_regionais(self):
        form = EquipamentoForm({
            'categoria': 'Notebooks', 'produto': self.produto.pk,
            'numero_serie': 'SERIE-FORA', 'patrimonio': 'PAT-FORA',
            'regional': self.outra_base.pk, 'finalidade': 'OPERACIONAL',
            'responsavel': '',
        }, user=self.gestor)
        self.assertFalse(form.is_valid())
        self.assertIn('regional', form.errors)

    def test_admin_reutiliza_base_selecionada(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('estoque:cadastrar_equipamento'), {'regional': self.outra_base.pk})
        self.assertEqual(response.context['base_selecionada'], self.outra_base)
        self.assertTrue(response.context['form'].fields['regional'].disabled)

class FluxoSickTests(EquipamentosSickBaseTests):
    def _marcar_sick_ajax(self, senha=None):
        payload = {
            'categoria': 'HARDWARE',
            'motivo': 'Não liga',
            'observacao': 'Falha ao iniciar',
        }
        if senha is not None:
            payload['senha'] = senha
        return self.client.post(
            reverse('estoque:marcar_sick', args=[self.equipamento.pk]),
            data=json.dumps(payload),
            content_type='application/json',
        )

    def test_marcar_sick_ajax_exige_senha(self):
        self.client.force_login(self.gestor)

        response = self._marcar_sick_ajax()

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Sick.objects.filter(equipamento=self.equipamento).exists())
        self.equipamento.refresh_from_db()
        self.assertEqual(self.equipamento.status, 'ATIVO')

    def test_marcar_sick_ajax_rejeita_senha_incorreta(self):
        self.client.force_login(self.gestor)

        response = self._marcar_sick_ajax('senha-incorreta')

        self.assertEqual(response.status_code, 403)
        self.assertContains(response, 'Senha incorreta', status_code=403)
        self.assertFalse(Sick.objects.filter(equipamento=self.equipamento).exists())
        self.equipamento.refresh_from_db()
        self.assertEqual(self.equipamento.status, 'ATIVO')

    def test_marcar_sick_ajax_aceita_senha_do_usuario(self):
        self.client.force_login(self.gestor)

        response = self._marcar_sick_ajax('senha-forte')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['sucesso'])
        self.assertTrue(Sick.objects.filter(equipamento=self.equipamento).exists())
        self.equipamento.refresh_from_db()
        self.assertEqual(self.equipamento.status, 'SICK')

    def test_tela_de_estoque_exibe_confirmacao_de_senha_para_sick(self):
        self.client.force_login(self.gestor)

        response = self.client.get(reverse('estoque:estoque'))

        self.assertContains(response, 'id="sickSenha"')
        self.assertContains(response, 'autocomplete="current-password"')

    def test_usuario_da_base_enxerga_menu_e_somente_sicks_da_sua_base(self):
        sick_base = self._abrir(usuario=self.operador)
        equipamento_outra_base = Equipamento.objects.create(
            produto=self.produto, numero_serie='SERIE-OUTRA-BASE',
            patrimonio='PAT-OUTRA-BASE', regional=self.outra_base,
            codigo='EQP-OUTRA-BASE', status='ATIVO',
        )
        self._abrir(usuario=self.admin, equipamento=equipamento_outra_base)
        self.client.force_login(self.operador)
        response = self.client.get(reverse('estoque:sick'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('estoque:sick'))
        self.assertContains(response, sick_base.equipamento.numero_serie)
        self.assertNotContains(response, equipamento_outra_base.numero_serie)
        self.assertContains(response, 'SICKs das suas bases')

    def test_base_envia_e_nao_pode_confirmar_o_proprio_recebimento(self):
        sick = self._abrir(usuario=self.operador)
        self.client.force_login(self.operador)
        response = self.client.post(reverse('estoque:sick'), {
            'acao': 'enviar_para_manutencao',
            'sick_id': sick.pk,
            'destino_manutencao': 'Central de manutenção',
            'transportadora_ou_portador': 'Malote interno',
            'protocolo_envio': 'PROTO-BASE-1',
        })
        sick.refresh_from_db()
        self.assertEqual(sick.etapa, Sick.Etapa.EM_TRANSITO)
        self.assertIn('etapa=EM_TRANSITO', response.url)

        response = self.client.get(reverse('estoque:sick'), {'etapa': 'EM_TRANSITO'})
        self.assertContains(
            response,
            'Envio registrado. Aguardando manutenção confirmar o recebimento',
        )
        self.assertNotContains(response, '>Confirmar recebimento</button>', html=False)
        response = self.client.post(reverse('estoque:sick'), {
            'acao': 'confirmar_recebimento', 'sick_id': sick.pk,
        })
        sick.refresh_from_db()
        self.assertEqual(sick.etapa, Sick.Etapa.EM_TRANSITO)

    def test_terceirizada_fica_restrita_a_base_e_controla_envio_e_retorno(self):
        rafael = User.objects.create_user(username='rafael.ribeiro', password='senha-forte')
        rafael.perfil.role = Perfil.Role.OPERADOR
        rafael.perfil.save()
        sick = self._abrir(usuario=self.operador)

        SickService.enviar_para_manutencao(
            sick_id=sick.pk,
            usuario=self.operador,
            destino='Assistência externa',
            tipo_destino=Sick.TipoDestino.TERCEIRIZADA,
            codigo_rastreio='AA123456789BR',
        )
        sick.refresh_from_db()

        self.assertEqual(sick.base_origem, self.base)
        self.assertEqual(sick.etapa, Sick.Etapa.AGUARDANDO_RETORNO)
        self.assertIn('objetos=AA123456789BR', sick.url_rastreio_envio)
        self.assertTrue(SickService.visiveis_para(self.operador).filter(pk=sick.pk).exists())
        self.assertFalse(SickService.visiveis_para(self.admin).filter(pk=sick.pk).exists())
        self.assertFalse(SickService.visiveis_para(rafael).filter(pk=sick.pk).exists())
        historicos_sick = Historico.objects.filter(detalhes__sick_id=sick.pk)
        self.assertTrue(SickService.filtrar_historicos_visiveis(self.operador, historicos_sick).exists())
        self.assertFalse(SickService.filtrar_historicos_visiveis(self.admin, historicos_sick).exists())
        comunicado_envio = Comunicado.objects.filter(dados__sick_id=sick.pk).latest('pk')
        self.assertTrue(comunicado_envio.usuarios.filter(pk=self.operador.pk).exists())
        self.assertTrue(comunicado_envio.usuarios.filter(pk=self.admin.pk).exists())
        self.assertTrue(comunicado_envio.usuarios.filter(pk=self.admin2.pk).exists())
        self.assertFalse(comunicado_envio.usuarios.filter(pk=rafael.pk).exists())
        with self.assertRaises(PermissionDenied):
            SickService.confirmar_retorno(sick_id=sick.pk, usuario=self.admin)
        with self.assertRaises(PermissionDenied):
            SickService.confirmar_retorno(sick_id=sick.pk, usuario=rafael)

        self.client.force_login(self.admin)
        response = self.client.get(reverse('estoque:sick'), {'etapa': 'AGUARDANDO_RETORNO'})
        self.assertNotContains(response, self.equipamento.numero_serie)

        SickService.confirmar_retorno(
            sick_id=sick.pk,
            usuario=self.operador,
            codigo_rastreio_retorno='BB987654321BR',
        )
        sick.refresh_from_db()
        self.equipamento.refresh_from_db()
        self.assertEqual(sick.etapa, Sick.Etapa.FINALIZADO)
        self.assertEqual(self.equipamento.status, 'ATIVO')
        self.assertIn('objetos=BB987654321BR', sick.url_rastreio_retorno)

    def test_admin_confirma_recebimento_mas_nao_recebe_botao_de_envio_da_base(self):
        sick = self._abrir(usuario=self.operador)
        self.client.force_login(self.admin)
        response = self.client.get(reverse('estoque:sick'))
        self.assertNotContains(response, 'Enviar para manutenção — etapa 2')
        with self.assertRaises(PermissionDenied):
            SickService.enviar_para_manutencao(
                sick_id=sick.pk, usuario=self.admin, destino='Central',
            )
        sick.refresh_from_db()
        self.assertEqual(sick.etapa, Sick.Etapa.IDENTIFICADO)
        SickService.enviar_para_manutencao(
            sick_id=sick.pk, usuario=self.operador, destino='Central',
        )
        response = self.client.get(reverse('estoque:sick'), {'etapa': 'EM_TRANSITO'})
        self.assertContains(response, 'Confirmar recebimento')
        response = self.client.post(reverse('estoque:sick'), {
            'acao': 'confirmar_recebimento', 'sick_id': sick.pk,
        })
        sick.refresh_from_db()
        self.assertEqual(sick.etapa, Sick.Etapa.RECEBIDO)

    def test_indice_abre_detalhes_com_classe_show_e_botao_mobile(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('estoque:index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'regional-details-button')
        self.assertContains(response, "DOM.modal.classList.add('show')")
        self.assertContains(response, 'role="button"')

    def test_tela_exibe_timeline_finalidade_e_etapa(self):
        sick = self._abrir(usuario=self.operador)
        self.client.force_login(self.operador)
        response = self.client.get(reverse('estoque:sick'), {'sick': sick.pk})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Identificado na base')
        self.assertContains(response, 'Operacional')
        self.assertContains(response, 'Enviar para manutenção — etapa 2')

    def test_tela_abre_em_sem_acao_e_separa_as_etapas_em_abas(self):
        identificado = self._abrir(usuario=self.admin)
        outro_equipamento = Equipamento.objects.create(
            produto=self.produto, numero_serie='SERIE-SICK-2', patrimonio='PAT-SICK-2',
            regional=self.base, codigo='EQP-SICK-2', status='ATIVO',
        )
        em_transito = self._abrir(usuario=self.admin, equipamento=outro_equipamento)
        SickService.enviar_para_manutencao(
            sick_id=em_transito.pk, usuario=self.operador, destino='Central',
        )
        self.client.force_login(self.admin)
        response = self.client.get(reverse('estoque:sick'))
        self.assertEqual(response.context['etapa_filter'], Sick.Etapa.IDENTIFICADO)
        self.assertQuerySetEqual(response.context['sicks'], [identificado], transform=lambda item: item)
        self.assertContains(response, 'Inativos / sucata')
        self.assertContains(response, 'sick-stage-tabs')

    def test_historico_mostra_reincidencia_e_quantidade_de_manutencoes(self):
        anterior = self._abrir(usuario=self.admin)
        SickService.enviar_para_manutencao(
            sick_id=anterior.pk, usuario=self.operador, destino='Central',
        )
        anterior.refresh_from_db()
        anterior.etapa = Sick.Etapa.FINALIZADO
        anterior.ativo = False
        anterior.status_final = 'ATIVO'
        anterior.data_resolucao = anterior.data_ocorrencia
        anterior.save()
        self.equipamento.status = 'ATIVO'
        self.equipamento.save(update_fields=['status'])
        atual = self._abrir(usuario=self.admin)
        self.client.force_login(self.admin)
        response = self.client.get(reverse('estoque:sick'))
        sick_renderizado = next(item for item in response.context['sicks'] if item.pk == atual.pk)
        self.assertTrue(sick_renderizado.reincidente)
        self.assertEqual(sick_renderizado.total_ocorrencias, 2)
        self.assertEqual(sick_renderizado.total_envios_manutencao, 1)
        self.assertContains(response, 'Histórico do equipamento')
        self.assertContains(response, 'Reincidente')

    def test_historico_legado_sem_detalhes_renderiza_todas_as_abas(self):
        sick = self._abrir(usuario=self.admin)
        Historico.objects.filter(equipamento=self.equipamento).update(detalhes=None)
        self.client.force_login(self.admin)

        response = self.client.get(reverse('estoque:sick'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'history-stage-tabs')
        self.assertContains(response, 'hist-{}-identificado'.format(sick.pk))
        self.assertContains(response, 'hist-{}-final'.format(sick.pk))

    def test_base_envia_e_manutencao_recebe_sem_vinculo_regional(self):
        manutencao = User.objects.create_user(username='tecnico.manutencao', password='senha-forte')
        manutencao.perfil.role = Perfil.Role.OPERADOR
        manutencao.perfil.empresa = None
        manutencao.perfil.save()
        grupo, _ = Group.objects.get_or_create(name=GruposCorporativos.SICK_MANUTENCAO)
        manutencao.groups.add(grupo)
        sick = self._abrir(usuario=self.gestor)
        SickService.enviar_para_manutencao(
            sick_id=sick.pk, usuario=self.gestor, destino='Central',
        )
        SickService.confirmar_recebimento(sick_id=sick.pk, usuario=manutencao)
        sick.refresh_from_db()
        self.assertEqual(sick.etapa, Sick.Etapa.RECEBIDO)

    def test_previsao_e_salva_e_redireciona_para_mesmo_item_na_nova_aba(self):
        sick = self._abrir(usuario=self.admin)
        SickService.enviar_para_manutencao(sick_id=sick.pk, usuario=self.operador, destino='Central')
        SickService.confirmar_recebimento(sick_id=sick.pk, usuario=self.admin)
        SickService.iniciar_avaliacao(sick_id=sick.pk, usuario=self.admin)
        self.client.force_login(self.admin)
        response = self.client.post(reverse('estoque:sick'), {
            'acao': 'iniciar_manutencao',
            'sick_id': sick.pk,
            'causa_identificada': 'Fonte',
            'diagnostico': 'Fonte queimada',
            'observacao_tecnica': 'Substituir componente',
            'previsao_retorno': '2026-07-30',
        })
        sick.refresh_from_db()
        self.assertEqual(str(sick.previsao_retorno), '2026-07-30')
        self.assertEqual(sick.etapa, Sick.Etapa.EM_MANUTENCAO)
        self.assertIn('etapa=EM_MANUTENCAO', response.url)
        self.assertTrue(response.url.endswith(f'#sick-{sick.pk}'))

    def test_fluxo_completo_respeita_status_etapas_finalidade_historico_e_comunicados(self):
        self.equipamento.finalidade = Equipamento.Finalidade.ADMINISTRATIVO
        self.equipamento.save(update_fields=['finalidade'])
        sick = self._abrir(usuario=self.admin)
        SickService.enviar_para_manutencao(sick_id=sick.pk, usuario=self.operador, destino='Central')
        SickService.confirmar_recebimento(sick_id=sick.pk, usuario=self.admin)
        SickService.iniciar_avaliacao(sick_id=sick.pk, usuario=self.admin)
        SickService.iniciar_manutencao(
            sick_id=sick.pk, usuario=self.admin, causa='Fonte', diagnostico='Fonte queimada',
            observacao='Trocar fonte',
        )
        self.equipamento.refresh_from_db()
        self.assertEqual(self.equipamento.status, 'MANUTENCAO')
        SickService.concluir_manutencao(
            sick_id=sick.pk, usuario=self.admin, solucao='Fonte trocada',
            resultado='Testes aprovados', apto_retorno=True,
        )
        self.equipamento.refresh_from_db()
        self.assertEqual(self.equipamento.status, 'SICK')
        SickService.confirmar_retorno(sick_id=sick.pk, usuario=self.admin)
        sick.refresh_from_db()
        self.equipamento.refresh_from_db()
        self.assertEqual(sick.etapa, Sick.Etapa.FINALIZADO)
        self.assertEqual(self.equipamento.status, 'ATIVO')
        self.assertEqual(self.equipamento.finalidade, 'ADMINISTRATIVO')
        self.assertEqual(Historico.objects.filter(equipamento=self.equipamento).count(), 7)
        self.assertEqual(Comunicado.objects.count(), 7)
        for comunicado in Comunicado.objects.all():
            self.assertTrue(comunicado.usuarios.filter(pk=self.admin.pk).exists())
            self.assertTrue(comunicado.usuarios.filter(pk=self.admin2.pk).exists())
            self.assertFalse(comunicado.usuarios.filter(pk=self.admin_inativo.pk).exists())

    def test_nao_permite_pular_etapa(self):
        sick = self._abrir(usuario=self.admin)
        with self.assertRaises(ValidationError):
            SickService.iniciar_manutencao(
                sick_id=sick.pk, usuario=self.admin, causa='Causa',
                diagnostico='Diagnóstico', observacao='Ação',
            )

    def test_edicao_do_sick_gera_historico_e_comunicado_para_admins(self):
        sick = self._abrir(usuario=self.admin)
        SickService.atualizar_informacoes(
            sick_id=sick.pk, usuario=self.admin, categoria='SOFTWARE',
            motivo='Sistema não inicia', observacao='Erro na inicialização',
        )
        sick.refresh_from_db()
        self.assertEqual(sick.categoria, 'SOFTWARE')
        self.assertTrue(Historico.objects.filter(
            equipamento=self.equipamento, tipo_acao='SICK_ATUALIZADO'
        ).exists())
        comunicado = Comunicado.objects.latest('criado_em')
        self.assertTrue(comunicado.usuarios.filter(pk=self.admin2.pk).exists())

    def test_comunicado_de_cada_etapa_chega_a_usuarios_da_base(self):
        usuario_outra_base = self._usuario(
            'operador_outra_base_sick',
            Perfil.Role.OPERADOR,
            self.outra_base,
        )
        sick = self._abrir(usuario=self.gestor)
        comunicado = Comunicado.objects.latest('criado_em')
        self.assertTrue(comunicado.usuarios.filter(pk=self.gestor.pk).exists())
        self.assertTrue(comunicado.usuarios.filter(pk=self.operador.pk).exists())
        self.assertTrue(comunicado.usuarios.filter(pk=self.admin.pk).exists())
        self.assertFalse(
            comunicado.usuarios.filter(pk=usuario_outra_base.pk).exists()
        )

        SickService.enviar_para_manutencao(
            sick_id=sick.pk,
            usuario=self.operador,
            destino='Central',
        )
        comunicado = Comunicado.objects.latest('criado_em')
        self.assertTrue(comunicado.usuarios.filter(pk=self.gestor.pk).exists())
        self.assertTrue(comunicado.usuarios.filter(pk=self.operador.pk).exists())

    def test_gestor_nao_opera_equipamento_de_outra_base(self):
        equipamento = Equipamento.objects.create(
            produto=self.produto, numero_serie='SERIE-FORA-2', patrimonio='PAT-FORA-2',
            regional=self.outra_base, codigo='EQP-FORA-2', status='ATIVO',
        )
        with self.assertRaises(Exception):
            self._abrir(usuario=self.gestor, equipamento=equipamento)

    def test_falha_no_historico_reverte_abertura_integralmente(self):
        with patch('estoque.services.sick_service.Historico.objects.create', side_effect=RuntimeError('falha')):
            with self.assertRaises(RuntimeError):
                self._abrir(usuario=self.admin)
        self.equipamento.refresh_from_db()
        self.assertEqual(self.equipamento.status, 'ATIVO')
        self.assertFalse(Sick.objects.filter(equipamento=self.equipamento).exists())
        self.assertFalse(Comunicado.objects.exists())

    def test_sem_reparo_nao_faz_baixa_automatica(self):
        sick = self._abrir(usuario=self.admin)
        SickService.enviar_para_manutencao(sick_id=sick.pk, usuario=self.operador, destino='Central')
        SickService.confirmar_recebimento(sick_id=sick.pk, usuario=self.admin)
        SickService.iniciar_avaliacao(sick_id=sick.pk, usuario=self.admin)
        SickService.iniciar_manutencao(
            sick_id=sick.pk, usuario=self.admin, causa='Placa', diagnostico='Sem componentes',
            observacao='Avaliar baixa',
        )
        SickService.concluir_manutencao(
            sick_id=sick.pk, usuario=self.admin, solucao='Sem reparo',
            resultado='Irrecuperável', apto_retorno=False,
        )
        sick.refresh_from_db()
        self.equipamento.refresh_from_db()
        self.assertEqual(sick.etapa, Sick.Etapa.EM_MANUTENCAO)
        self.assertEqual(self.equipamento.status, 'MANUTENCAO')
        self.assertNotEqual(self.equipamento.status, 'BAIXA')

    def test_manutencao_pode_inativar_explicitamente_e_item_vai_para_aba(self):
        sick = self._abrir(usuario=self.admin)
        SickService.enviar_para_manutencao(sick_id=sick.pk, usuario=self.operador, destino='Central')
        SickService.confirmar_recebimento(sick_id=sick.pk, usuario=self.admin)
        SickService.iniciar_avaliacao(sick_id=sick.pk, usuario=self.admin)
        SickService.iniciar_manutencao(
            sick_id=sick.pk, usuario=self.admin, causa='Placa',
            diagnostico='Placa sem componentes', observacao='Testes concluídos',
        )
        SickService.concluir_manutencao(
            sick_id=sick.pk, usuario=self.admin, solucao='Sem reparo',
            resultado='Irrecuperável', apto_retorno=False,
        )
        SickService.inativar_sem_reparo(
            sick_id=sick.pk, usuario=self.admin,
            motivo='Placa principal irrecuperável e sem reposição.',
        )
        sick.refresh_from_db()
        self.equipamento.refresh_from_db()
        self.assertEqual(sick.etapa, Sick.Etapa.FINALIZADO)
        self.assertEqual(sick.status_final, 'INATIVO')
        self.assertFalse(sick.ativo)
        self.assertEqual(self.equipamento.status, 'INATIVO')
        self.assertTrue(Historico.objects.filter(
            equipamento=self.equipamento, tipo_acao='SICK_INATIVADO'
        ).exists())
        self.client.force_login(self.admin)
        response = self.client.get(reverse('estoque:sick'), {'etapa': 'INATIVOS'})
        self.assertContains(response, self.equipamento.numero_serie)
